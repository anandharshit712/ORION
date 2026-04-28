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
    ScenarioRecord, RunRecord, BatchJobRecord,
    OrganisationRecord, ApiKeyRecord, UserRecord,
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
        )
        self.session.add(record)
        self.session.flush()
        return record

    def get_runs_for_model(
        self, model_name: str, limit: int = 100,
        org_id: Optional[str] = None,
    ) -> List[RunRecord]:
        q = self.session.query(RunRecord).filter_by(model_name=model_name)
        if org_id is not None:
            q = q.filter(RunRecord.org_id == org_id)
        return (
            q.order_by(RunRecord.created_at.desc())
            .limit(limit)
            .all()
        )

    def get_runs_for_scenario(
        self, scenario_id: int, limit: int = 100,
        org_id: Optional[str] = None,
    ) -> List[RunRecord]:
        q = self.session.query(RunRecord).filter_by(scenario_id=scenario_id)
        if org_id is not None:
            q = q.filter(RunRecord.org_id == org_id)
        return (
            q.order_by(RunRecord.created_at.desc())
            .limit(limit)
            .all()
        )

    def get_runs_for_batch(
        self, batch_job_id: int, org_id: Optional[str] = None,
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
    ) -> BatchJobRecord:
        record = BatchJobRecord(
            scenario_name=scenario_name,
            model_name=model_name,
            num_runs=num_runs,
            master_seed=master_seed,
            org_id=org_id,
            status="pending",
        )
        self.session.add(record)
        self.session.flush()
        return record

    def mark_running(self, job_id: int) -> None:
        job = self.session.query(BatchJobRecord).get(job_id)
        if job:
            job.status = "running"
            job.started_at = datetime.datetime.utcnow()

    def mark_completed(
        self, job_id: int, aggregated: AggregatedMetrics,
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
        self, limit: int = 20, org_id: Optional[str] = None,
    ) -> List[BatchJobRecord]:
        q = self.session.query(BatchJobRecord)
        if org_id is not None:
            q = q.filter(BatchJobRecord.org_id == org_id)
        return (
            q.order_by(BatchJobRecord.created_at.desc())
            .limit(limit)
            .all()
        )

    def get_by_id(
        self, job_id: int, org_id: Optional[str] = None,
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
        self, name: str, slug: str, plan: str = "free", run_credits: int = 50,
    ) -> OrganisationRecord:
        record = OrganisationRecord(
            name=name, slug=slug, plan=plan, run_credits=run_credits,
        )
        self.session.add(record)
        self.session.flush()
        return record

    def get_by_id(self, org_id: str) -> Optional[OrganisationRecord]:
        return self.session.query(OrganisationRecord).filter_by(id=org_id).first()

    def get_by_slug(self, slug: str) -> Optional[OrganisationRecord]:
        return self.session.query(OrganisationRecord).filter_by(slug=slug).first()

    def deduct_credits(self, org_id: str, amount: int) -> bool:
        """Atomically deduct credits. Returns False if insufficient."""
        org = (
            self.session.query(OrganisationRecord)
            .filter_by(id=org_id)
            .with_for_update()
            .first()
        )
        if org is None or org.run_credits < amount:
            return False
        org.run_credits -= amount
        return True

    def add_credits(self, org_id: str, amount: int) -> None:
        org = (
            self.session.query(OrganisationRecord)
            .filter_by(id=org_id)
            .with_for_update()
            .first()
        )
        if org is not None:
            org.run_credits += amount


class ApiKeyRepository:
    """CRUD for API keys. Keys stored as SHA256 hash, never plaintext."""

    def __init__(self, session: Session):
        self.session = session

    def create(
        self, org_id: str, user_id: int, key_hash: str,
        key_prefix: str, label: str,
    ) -> ApiKeyRecord:
        record = ApiKeyRecord(
            org_id=org_id, user_id=user_id, key_hash=key_hash,
            key_prefix=key_prefix, label=label,
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
                (UserRecord.email == identifier)
                | (UserRecord.username == identifier)
            )
            .first()
        )

    def list_for_org(self, org_id: str) -> List[UserRecord]:
        return self.session.query(UserRecord).filter_by(org_id=org_id).all()
