"""
ORION Database Repository.

CRUD operations for scenarios, runs, and batch jobs.
Provides a clean interface between the evaluation pipeline
and the persistence layer.
"""

from __future__ import annotations

import datetime
from typing import List, Optional

from sqlalchemy.orm import Session

from arep.database.models import (
    ScenarioRecord,
    RunRecord,
    BatchJobRecord,
    OrganisationRecord,
    ApiKeyRecord,
    UserRecord,
    ModelRecord,
    PasswordResetRecord,
    WebhookEventRecord,
    RunFailureRecord,
)
from arep.evaluation.composite import EvaluationResult
from arep.statistics.aggregator import AggregatedMetrics
from arep.utils.logging_config import get_logger

logger = get_logger("database.repository")


class ScenarioRepository:
    """CRUD for scenario records."""

    def __init__(self, session: Session):
        self.session = session

    def upsert(
        self,
        name: str,
        version: str,
        content_hash: str,
        yaml_content: str,
        duration: float,
        description: str = "",
        road_type: str = "",
        num_traffic_objects: int = 0,
    ) -> ScenarioRecord:
        """Insert or return existing scenario (by content_hash)."""
        existing = (
            self.session.query(ScenarioRecord)
            .filter_by(content_hash=content_hash)
            .first()
        )
        if existing:
            return existing

        record = ScenarioRecord(
            name=name,
            version=version,
            description=description,
            content_hash=content_hash,
            yaml_content=yaml_content,
            duration=duration,
            road_type=road_type,
            num_traffic_objects=num_traffic_objects,
        )
        self.session.add(record)
        self.session.flush()
        return record

    def get_by_name(self, name: str) -> Optional[ScenarioRecord]:
        return (
            self.session.query(ScenarioRecord)
            .filter_by(name=name)
            .order_by(ScenarioRecord.created_at.desc())
            .first()
        )

    def get_all(self) -> List[ScenarioRecord]:
        return self.session.query(ScenarioRecord).all()


class RunRepository:
    """CRUD for individual simulation run records."""

    def __init__(self, session: Session):
        self.session = session

    def claim_failure(
        self,
        batch_job_id: int,
        master_seed: int,
        error: str = "",
    ) -> bool:
        """Record a terminal failure once. False if it was already recorded.

        The caller must skip both the runs_failed increment and the credit
        refund when this returns False — a Celery redelivery of a failing task
        would otherwise refund a second credit for one run.

        Relies on the composite primary key rather than a read-then-write:
        two workers can reach this at the same moment for the same redelivered
        message, and only the database can arbitrate that.
        """
        from sqlalchemy.exc import IntegrityError

        savepoint = self.session.begin_nested()
        try:
            self.session.add(
                RunFailureRecord(
                    batch_id=batch_job_id,
                    master_seed=master_seed,
                    error=(error or "")[:2000],
                )
            )
            savepoint.commit()
            return True
        except IntegrityError:
            savepoint.rollback()
            return False

    def get_by_batch_and_seed(
        self,
        batch_job_id: int,
        master_seed: int,
    ) -> Optional[RunRecord]:
        """Find the row for one run of a batch, if it has already been written.

        (batch_job_id, master_seed) identifies a run: a batch fans out N tasks
        with distinct seeds. Used by the worker to stay idempotent under Celery
        redelivery, which happens on its own whenever a worker dies mid-task
        with acks_late (Phase 0.6, defect D-08).
        """
        return (
            self.session.query(RunRecord)
            .filter(
                RunRecord.batch_job_id == batch_job_id,
                RunRecord.master_seed == master_seed,
            )
            .first()
        )

    def save_result(
        self,
        scenario_id: int,
        result: EvaluationResult,
        batch_job_id: Optional[int] = None,
        org_id: Optional[str] = None,
    ) -> RunRecord:
        """Save an EvaluationResult as a RunRecord."""
        record = RunRecord(
            scenario_id=scenario_id,
            batch_job_id=batch_job_id,
            org_id=org_id,
            model_name=result.model_name,
            master_seed=result.master_seed,
            duration=result.duration,
            termination_reason=result.termination_reason,
            composite_score=result.composite_score,
            safety_score=result.safety.safety_score,
            collision_occurred=result.safety.collision_occurred,
            min_ttc=result.safety.min_ttc,
            compliance_score=result.compliance.compliance_score,
            speed_compliance=result.compliance.speed_compliance_fraction,
            stability_score=result.stability.stability_score,
            mean_jerk=result.stability.mean_jerk,
            reactivity_score=result.reactivity.reactivity_score,
            brake_response_time=(
                result.reactivity.brake_response_time
                if result.reactivity.brake_response_time != float("inf")
                else None
            ),
            # Determinism digest: lets a customer re-run and compare rather
            # than take the reproducibility claim on trust. None for records
            # produced without frame emission.
            frame_hash=result.frame_hash or None,
        )
        self.session.add(record)
        self.session.flush()
        return record

    def get_runs_for_model(
        self,
        model_name: str,
        limit: int = 100,
        org_id: Optional[str] = None,
    ) -> List[RunRecord]:
        q = self.session.query(RunRecord).filter_by(model_name=model_name)
        if org_id is not None:
            q = q.filter(RunRecord.org_id == org_id)
        return q.order_by(RunRecord.created_at.desc()).limit(limit).all()

    def get_runs_for_scenario(
        self,
        scenario_id: int,
        limit: int = 100,
        org_id: Optional[str] = None,
    ) -> List[RunRecord]:
        q = self.session.query(RunRecord).filter_by(scenario_id=scenario_id)
        if org_id is not None:
            q = q.filter(RunRecord.org_id == org_id)
        return q.order_by(RunRecord.created_at.desc()).limit(limit).all()

    def get_runs_for_batch(
        self,
        batch_job_id: int,
        org_id: Optional[str] = None,
    ) -> List[RunRecord]:
        q = self.session.query(RunRecord).filter_by(batch_job_id=batch_job_id)
        if org_id is not None:
            q = q.filter(RunRecord.org_id == org_id)
        return q.all()


class BatchJobRepository:
    """CRUD for batch job records."""

    def __init__(self, session: Session):
        self.session = session

    def create(
        self,
        scenario_name: str,
        model_name: str,
        num_runs: int,
        master_seed: int,
        org_id: Optional[str] = None,
        scenario_path: Optional[str] = None,
        status: str = "pending",
    ) -> BatchJobRecord:
        record = BatchJobRecord(
            scenario_name=scenario_name,
            model_name=model_name,
            num_runs=num_runs,
            master_seed=master_seed,
            org_id=org_id,
            scenario_path=scenario_path,
            status=status,
        )
        self.session.add(record)
        self.session.flush()
        return record

    def mark_running(self, job_id: int) -> None:
        job = self.session.query(BatchJobRecord).get(job_id)
        if job:
            job.status = "running"
            job.started_at = datetime.datetime.utcnow()

    def mark_queued(self, job_id: int) -> None:
        job = self.session.query(BatchJobRecord).get(job_id)
        if job:
            job.status = "queued"

    def increment_completed(self, job_id: int) -> None:
        """Atomically bump runs_completed by 1."""
        job = (
            self.session.query(BatchJobRecord)
            .filter_by(id=job_id)
            .with_for_update()
            .first()
        )
        if job:
            job.runs_completed = (job.runs_completed or 0) + 1
            if job.status == "queued":
                job.status = "running"
                job.started_at = datetime.datetime.utcnow()

    def increment_failed(self, job_id: int) -> None:
        """Atomically bump runs_failed by 1."""
        job = (
            self.session.query(BatchJobRecord)
            .filter_by(id=job_id)
            .with_for_update()
            .first()
        )
        if job:
            job.runs_failed = (job.runs_failed or 0) + 1
            if job.status == "queued":
                job.status = "running"
                job.started_at = datetime.datetime.utcnow()

    def set_error(self, job_id: int, message: str) -> None:
        job = self.session.query(BatchJobRecord).get(job_id)
        if job:
            job.error_message = (message or "")[:2000]

    def finalise_if_done(self, job_id: int) -> Optional[BatchJobRecord]:
        """If all runs accounted for, aggregate per-run rows and mark completed/failed.

        Returns the job if it transitioned to a terminal state, else None.
        """
        job = (
            self.session.query(BatchJobRecord)
            .filter_by(id=job_id)
            .with_for_update()
            .first()
        )
        if job is None or job.status in ("completed", "failed"):
            return None
        done = (job.runs_completed or 0) + (job.runs_failed or 0)
        if done < job.num_runs:
            return None

        # Aggregate from per-run rows. Lazy import to avoid heavy deps in DB layer.
        runs = self.session.query(RunRecord).filter_by(batch_job_id=job_id).all()
        if runs:
            import numpy as np

            comp = np.array([r.composite_score for r in runs])
            safe = np.array([r.safety_score for r in runs])
            comp_l = np.array([r.compliance_score for r in runs])
            stab = np.array([r.stability_score for r in runs])
            reac = np.array([r.reactivity_score for r in runs])
            collisions = sum(1 for r in runs if r.collision_occurred)
            n = len(runs)
            job.composite_mean = float(np.mean(comp))
            job.composite_std = float(np.std(comp, ddof=1)) if n > 1 else 0.0
            job.safety_mean = float(np.mean(safe))
            job.compliance_mean = float(np.mean(comp_l))
            job.stability_mean = float(np.mean(stab))
            job.reactivity_mean = float(np.mean(reac))
            job.collision_rate = collisions / n
        # Status: failed if every run failed, else completed
        if (job.runs_completed or 0) == 0 and (job.runs_failed or 0) > 0:
            job.status = "failed"
        else:
            job.status = "completed"
        job.completed_at = datetime.datetime.utcnow()
        return job

    def mark_completed(
        self,
        job_id: int,
        aggregated: AggregatedMetrics,
    ) -> None:
        job = self.session.query(BatchJobRecord).get(job_id)
        if job:
            job.status = "completed"
            job.completed_at = datetime.datetime.utcnow()
            job.composite_mean = aggregated.composite_mean
            job.composite_std = aggregated.composite_std
            job.safety_mean = aggregated.safety_mean
            job.compliance_mean = aggregated.compliance_mean
            job.stability_mean = aggregated.stability_mean
            job.reactivity_mean = aggregated.reactivity_mean
            job.collision_rate = aggregated.collision_rate

    def mark_failed(self, job_id: int) -> None:
        job = self.session.query(BatchJobRecord).get(job_id)
        if job:
            job.status = "failed"
            job.completed_at = datetime.datetime.utcnow()

    def get_recent(
        self,
        limit: int = 20,
        org_id: Optional[str] = None,
    ) -> List[BatchJobRecord]:
        q = self.session.query(BatchJobRecord)
        if org_id is not None:
            q = q.filter(BatchJobRecord.org_id == org_id)
        return q.order_by(BatchJobRecord.created_at.desc()).limit(limit).all()

    def get_by_id(
        self,
        job_id: int,
        org_id: Optional[str] = None,
    ) -> Optional[BatchJobRecord]:
        q = self.session.query(BatchJobRecord).filter(BatchJobRecord.id == job_id)
        if org_id is not None:
            q = q.filter(BatchJobRecord.org_id == org_id)
        return q.first()


# ── Multi-tenancy repositories ──────────────────────────────────────────


class OrganisationRepository:
    """CRUD for organisations."""

    def __init__(self, session: Session):
        self.session = session

    def create(
        self,
        name: str,
        slug: str,
        plan: str = "free",
        run_credits: int = 50,
    ) -> OrganisationRecord:
        record = OrganisationRecord(
            name=name,
            slug=slug,
            plan=plan,
            run_credits=run_credits,
        )
        self.session.add(record)
        self.session.flush()
        return record

    def get_by_id(self, org_id: str) -> Optional[OrganisationRecord]:
        return self.session.query(OrganisationRecord).filter_by(id=org_id).first()

    def get_by_slug(self, slug: str) -> Optional[OrganisationRecord]:
        return self.session.query(OrganisationRecord).filter_by(slug=slug).first()

    def list_all(self) -> List[OrganisationRecord]:
        return (
            self.session.query(OrganisationRecord)
            .order_by(OrganisationRecord.created_at.desc())
            .all()
        )

    def get_or_create_system_org(self) -> OrganisationRecord:
        """Get the global 'system' org used for superadmin users.

        Idempotent. Created with unlimited credits + plan='enterprise' + is_system=True.
        """
        existing = self.get_by_slug("system")
        if existing is not None:
            return existing
        record = OrganisationRecord(
            name="ORION System",
            slug="system",
            plan="enterprise",
            run_credits=10**9,
            is_system=True,
        )
        self.session.add(record)
        self.session.flush()
        return record

    UNLIMITED_CREDITS = -1

    def deduct_credits(self, org_id: str, amount: int) -> bool:
        """Atomically deduct credits. Returns False if insufficient.

        ``run_credits == -1`` means unlimited and always succeeds without
        decrementing. That sentinel is used by the system org and by the admin
        set-credits route, and the plain ``<`` comparison here refused it: -1 is
        less than any positive amount, so every org with unlimited credits was
        unable to start a single run.
        """
        org = (
            self.session.query(OrganisationRecord)
            .filter_by(id=org_id)
            .with_for_update()
            .first()
        )
        if org is None:
            return False
        if org.run_credits == self.UNLIMITED_CREDITS:
            return True
        if org.run_credits < amount:
            return False
        org.run_credits -= amount
        return True

    def allows_pickle_models(self, org_id: str) -> bool:
        """
        Whether this org may run cloudpickle (Python SDK) model artefacts.

        Phase 0.2 / D-01: the pickle path executes arbitrary customer code, so
        it is off unless a superadmin enables it. An unknown org is denied.
        """
        org = self.get_by_id(org_id)
        return bool(org is not None and org.allow_pickle_models)

    def set_allow_pickle_models(
        self, org_id: str, enabled: bool
    ) -> Optional[OrganisationRecord]:
        """Enable/disable the cloudpickle path for one org. Returns None if unknown."""
        org = self.get_by_id(org_id)
        if org is None:
            return None
        org.allow_pickle_models = bool(enabled)
        self.session.flush()
        return org

    def add_credits(self, org_id: str, amount: int) -> None:
        """Grant credits. A no-op for unlimited orgs (see deduct_credits)."""
        org = (
            self.session.query(OrganisationRecord)
            .filter_by(id=org_id)
            .with_for_update()
            .first()
        )
        if org is not None and org.run_credits != self.UNLIMITED_CREDITS:
            org.run_credits += amount

    # ── Subscription state (Phase 1.4) ───────────────────────────────

    def get_by_stripe_customer_id(
        self, customer_id: str
    ) -> Optional[OrganisationRecord]:
        """Find the org a Stripe webhook is about.

        Webhooks identify the account by customer id, never by our org id, so
        this is the only way in from an inbound event.
        """
        if not customer_id:
            return None
        return (
            self.session.query(OrganisationRecord)
            .filter_by(stripe_customer_id=customer_id)
            .first()
        )

    def set_stripe_customer_id(self, org_id: str, customer_id: str) -> None:
        org = self.get_by_id(org_id)
        if org is not None:
            org.stripe_customer_id = customer_id
            self.session.flush()

    def apply_subscription(
        self,
        org_id: str,
        *,
        plan: str,
        subscription_id: Optional[str] = None,
        status: Optional[str] = None,
        current_period_end: Optional[datetime.datetime] = None,
    ) -> Optional[OrganisationRecord]:
        """Record what Stripe says the subscription now is.

        Deliberately does not touch run_credits: a plan change and a credit
        grant are different events (``customer.subscription.updated`` versus
        ``invoice.paid``). Coupling them would grant a month of credits every
        time someone changed their card.
        """
        org = self.get_by_id(org_id)
        if org is None:
            return None
        org.plan = plan
        if subscription_id is not None:
            org.stripe_subscription_id = subscription_id
        if status is not None:
            org.subscription_status = status
        if current_period_end is not None:
            org.current_period_end = current_period_end
        self.session.flush()
        return org


class ApiKeyRepository:
    """CRUD for API keys. Keys stored as SHA256 hash, never plaintext."""

    def __init__(self, session: Session):
        self.session = session

    def create(
        self,
        org_id: str,
        user_id: int,
        key_hash: str,
        key_prefix: str,
        label: str,
    ) -> ApiKeyRecord:
        record = ApiKeyRecord(
            org_id=org_id,
            user_id=user_id,
            key_hash=key_hash,
            key_prefix=key_prefix,
            label=label,
        )
        self.session.add(record)
        self.session.flush()
        return record

    def get_by_hash(self, key_hash: str) -> Optional[ApiKeyRecord]:
        """Lookup non-revoked key by hash."""
        return (
            self.session.query(ApiKeyRecord)
            .filter_by(key_hash=key_hash, revoked_at=None)
            .first()
        )

    def list_for_org(self, org_id: str) -> List[ApiKeyRecord]:
        return (
            self.session.query(ApiKeyRecord)
            .filter_by(org_id=org_id)
            .order_by(ApiKeyRecord.created_at.desc())
            .all()
        )

    def revoke(self, key_id: str, org_id: str) -> bool:
        """Revoke key. Returns True if found and revoked."""
        key = (
            self.session.query(ApiKeyRecord)
            .filter_by(id=key_id, org_id=org_id, revoked_at=None)
            .first()
        )
        if key is None:
            return False
        key.revoked_at = datetime.datetime.utcnow()
        return True

    def touch(self, key_id: str) -> None:
        """Update last_used_at. Best-effort, no flush."""
        key = self.session.query(ApiKeyRecord).filter_by(id=key_id).first()
        if key is not None:
            key.last_used_at = datetime.datetime.utcnow()


class ModelRepository:
    """CRUD for customer-submitted models, org-scoped."""

    def __init__(self, session: Session):
        self.session = session

    def create(
        self,
        org_id: str,
        user_id: Optional[int],
        name: str,
        version: str,
        submission_type: str,
        artefact_uri: str,
        content_hash: Optional[str] = None,
        size_bytes: Optional[int] = None,
        status: str = "ready",
    ) -> ModelRecord:
        record = ModelRecord(
            org_id=org_id,
            user_id=user_id,
            name=name,
            version=version,
            submission_type=submission_type,
            artefact_uri=artefact_uri,
            content_hash=content_hash,
            size_bytes=size_bytes,
            status=status,
        )
        self.session.add(record)
        self.session.flush()
        return record

    def get(self, model_id: str, org_id: Optional[str] = None) -> Optional[ModelRecord]:
        q = self.session.query(ModelRecord).filter_by(id=model_id)
        if org_id is not None:
            q = q.filter(ModelRecord.org_id == org_id)
        return q.first()

    def list_for_org(self, org_id: str) -> List[ModelRecord]:
        return (
            self.session.query(ModelRecord)
            .filter_by(org_id=org_id)
            .order_by(ModelRecord.created_at.desc())
            .all()
        )

    def delete(self, model_id: str, org_id: str) -> Optional[ModelRecord]:
        record = (
            self.session.query(ModelRecord)
            .filter_by(id=model_id, org_id=org_id)
            .first()
        )
        if record is None:
            return None
        self.session.delete(record)
        return record

    def set_status(
        self, model_id: str, status: str, error: Optional[str] = None
    ) -> None:
        record = self.session.query(ModelRecord).filter_by(id=model_id).first()
        if record is not None:
            record.status = status
            if error is not None:
                record.error = error


class UserRepository:
    """CRUD for users (org-scoped)."""

    def __init__(self, session: Session):
        self.session = session

    def get_by_id(self, user_id: int) -> Optional[UserRecord]:
        return self.session.query(UserRecord).filter_by(id=user_id).first()

    def get_by_email_or_username(self, identifier: str) -> Optional[UserRecord]:
        return (
            self.session.query(UserRecord)
            .filter(
                (UserRecord.email == identifier) | (UserRecord.username == identifier)
            )
            .first()
        )

    def list_for_org(self, org_id: str) -> List[UserRecord]:
        return self.session.query(UserRecord).filter_by(org_id=org_id).all()

    def list_all(self) -> List[UserRecord]:
        return (
            self.session.query(UserRecord).order_by(UserRecord.created_at.desc()).all()
        )

    def set_role(self, user_id: int, role: str) -> Optional[UserRecord]:
        user = self.get_by_id(user_id)
        if user is None:
            return None
        user.role = role
        return user


class PasswordResetRepository:
    """CRUD for password reset tokens. Stores SHA256 hash, never raw token."""

    def __init__(self, session: Session):
        self.session = session

    def create(
        self,
        user_id: int,
        token_hash: str,
        expires_at: datetime.datetime,
        requested_ip: Optional[str] = None,
    ) -> PasswordResetRecord:
        record = PasswordResetRecord(
            user_id=user_id,
            token_hash=token_hash,
            expires_at=expires_at,
            requested_ip=requested_ip,
        )
        self.session.add(record)
        self.session.flush()
        return record

    def get_active_by_hash(self, token_hash: str) -> Optional[PasswordResetRecord]:
        """Return token only if unused AND not expired."""
        now = datetime.datetime.utcnow()
        return (
            self.session.query(PasswordResetRecord)
            .filter(
                PasswordResetRecord.token_hash == token_hash,
                PasswordResetRecord.used_at.is_(None),
                PasswordResetRecord.expires_at > now,
            )
            .first()
        )

    def mark_used(self, record_id: str) -> None:
        record = self.session.query(PasswordResetRecord).filter_by(id=record_id).first()
        if record is not None:
            record.used_at = datetime.datetime.utcnow()

    def invalidate_all_for_user(self, user_id: int) -> int:
        """Mark every outstanding token for this user as used. Returns count."""
        now = datetime.datetime.utcnow()
        rows = (
            self.session.query(PasswordResetRecord)
            .filter(
                PasswordResetRecord.user_id == user_id,
                PasswordResetRecord.used_at.is_(None),
            )
            .all()
        )
        for r in rows:
            r.used_at = now
        return len(rows)

    def count_recent_for_user(self, user_id: int, since: datetime.datetime) -> int:
        return (
            self.session.query(PasswordResetRecord)
            .filter(
                PasswordResetRecord.user_id == user_id,
                PasswordResetRecord.created_at >= since,
            )
            .count()
        )


class WebhookEventRepository:
    """
    Idempotency ledger for inbound provider webhooks (Phase 0.3).

    Payment providers retry a delivery whenever the response is slow, non-2xx or
    lost, so the same event id arrives repeatedly in normal operation. Every
    handler must therefore claim the event before acting on it and only mark it
    processed once the side effect is durable.
    """

    def __init__(self, session: Session):
        self.session = session

    def claim(
        self,
        event_id: str,
        provider: str = "stripe",
        event_type: Optional[str] = None,
    ) -> bool:
        """Try to take ownership of an event.

        Returns True when the caller should process it, False when it is a
        replay of an already-completed delivery.

        A row left in ``received`` is claimable again on purpose: it means a
        previous attempt verified the signature and then died before finishing,
        so the side effect may never have been applied. Dropping the retry there
        would lose the event entirely, which is worse than the handler running
        twice — handlers are expected to be idempotent in their own right.
        """
        existing = self.get(event_id)
        if existing is not None:
            return existing.status != "processed"

        self.session.add(
            WebhookEventRecord(
                event_id=event_id,
                provider=provider,
                event_type=event_type,
                status="received",
            )
        )
        self.session.flush()
        return True

    def mark_processed(self, event_id: str) -> None:
        """Record that the handler finished. Later retries become no-ops."""
        record = self.get(event_id)
        if record is not None:
            record.status = "processed"
            record.processed_at = datetime.datetime.utcnow()
            self.session.flush()

    def get(self, event_id: str) -> Optional[WebhookEventRecord]:
        """Look up an event by id alone.

        ``provider`` labels the row for operators; it is not part of the key.
        Provider event ids are globally unique within a provider and prefixed
        by it in practice ("evt_" for Stripe), so a composite key would buy a
        collision guarantee nothing needs.
        """
        return (
            self.session.query(WebhookEventRecord)
            .filter(WebhookEventRecord.event_id == event_id)
            .first()
        )
