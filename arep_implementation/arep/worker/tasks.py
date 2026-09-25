"""
ORION Celery Tasks  (P1.3 — async batch execution).

Each batch enqueues N copies of ``run_single_simulation``. Workers consume
from the ``simulation`` queue, run a headless ``EvaluationRunner.run_single``,
write results to the database, and increment the parent batch progress.

Failure semantics:
  - max_retries=3 with 5s/15s/60s backoff for transient infrastructure errors
    (database disconnect, broker hiccup). A model or scenario that fails
    deterministically is not retried — it would fail identically three more
    times and bill the customer for the privilege.
  - The credit is refunded once, on the terminal failure, never per attempt.
  - Tasks are idempotent on (batch_id, seed): Celery redelivers with acks_late
    whenever a worker dies mid-task, and a second RunRecord would corrupt the
    batch aggregate.
  - When the batch's ``runs_completed + runs_failed`` reaches ``num_runs`` the
    last task to write triggers ``finalise_if_done`` which aggregates per-run
    rows and flips the status to ``completed`` (or ``failed`` if every run died).

Tasks are JSON-serialisable only — never pass ORM objects across the wire.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from sqlalchemy.exc import DBAPIError, OperationalError

from arep.database.connection import session_scope
from arep.database.repository import (
    BatchJobRepository,
    OrganisationRepository,
    RunRepository,
    ScenarioRepository,
)
from arep.execution.frame_store import should_store, store_frames
from arep.execution.runner import EvaluationRunner
from arep.models.examples.example_models import (
    ConstantActionModel,
    EmergencyBrakeModel,
    SimpleLaneKeepModel,
    RandomModel,
)
from arep.models.resolver import resolve_model
from arep.scenario.parser import ScenarioParser
from arep.utils.logging_config import get_logger
from arep.worker.celery_app import celery_app

logger = get_logger("worker.tasks")


# Built-in model registry mirrors api/routes.py — workers can't import the API
# package without dragging FastAPI in, so duplicate the small dict here.
_BUILTIN_MODELS = {
    "ConstantAction": lambda: ConstantActionModel(throttle=0.3),
    "EmergencyBrake": lambda: EmergencyBrakeModel(),
    "SimpleLaneKeep": lambda: SimpleLaneKeepModel(),
    "Random": lambda: RandomModel(seed=42),
}


def _fail_run(
    batch_id: int,
    seed: int,
    org_id: Optional[str],
    exc: BaseException,
) -> None:
    """Record a run as failed and refund its credit. Terminal path only, once.

    Called after retries are exhausted or for a failure that will never
    succeed — never on an intermediate retry, or the customer would be refunded
    one credit per attempt for a single run.

    Claims (batch_id, seed) in run_failures first. A successful run is guarded
    by its RunRecord row; a failed one used to write nothing, so a Celery
    redelivery — which acks_late makes routine whenever a worker dies mid-task —
    bumped runs_failed a second time and refunded a second credit. The refund is
    the part that mattered: a wrong charge, in the customer's favour, on every
    redelivered failure.
    """
    with session_scope() as db:
        if not RunRepository(db).claim_failure(batch_id, seed, str(exc)):
            logger.info(
                "failure already recorded for batch=%s seed=%s — not counting twice",
                batch_id,
                seed,
            )
            return

        batch_repo = BatchJobRepository(db)
        batch_repo.increment_failed(batch_id)
        batch_repo.set_error(batch_id, str(exc))
        batch_repo.finalise_if_done(batch_id)

    _refund_credit(org_id)


def _refund_credit(org_id: Optional[str]) -> None:
    if not org_id:
        return
    try:
        with session_scope() as db:
            OrganisationRepository(db).add_credits(org_id, 1)
    except Exception:
        logger.exception("credit refund failed for org=%s", org_id)


# Failures that are worth another attempt: the broker blinked, the database
# dropped the connection, the pool timed out. Retrying these turns a transient
# infrastructure hiccup into a slower run instead of a lost one the customer
# paid for.
#
# Deliberately NOT retried: ModelSandboxError (the artefact broke its limits and
# the run is void), ValueError and friends from a bad scenario or model. Those
# fail the same way every time, and retrying them three times just bills three
# times the compute before the same answer.
TRANSIENT_ERRORS = (
    OperationalError,  # includes disconnects and pool timeouts
    DBAPIError,
    ConnectionError,  # builtin; redis.ConnectionError subclasses it
    TimeoutError,
)

# 5s, 15s, 60s. Spread out enough that a database restart or a broker failover
# has time to finish before the last attempt.
RETRY_BACKOFF_SECONDS = (5, 15, 60)
MAX_RETRIES = len(RETRY_BACKOFF_SECONDS)


def execute_single_run(
    task,
    batch_id: int,
    scenario_id: int,
    scenario_path: str,
    model_name: str,
    seed: int,
    org_id: Optional[str] = None,
) -> dict:
    """Run one simulation headlessly, persist result, update batch progress.

    Args:
        batch_id:      BatchJobRecord.id this run belongs to.
        scenario_id:   ScenarioRecord.id (already upserted by the API).
        scenario_path: Filesystem path to the scenario YAML.
        model_name:    Built-in model name OR customer model UUID.
        seed:          Per-run seed (master_seed + run_index).
        org_id:        Org owning the batch. Used for credit refund on failure.
    """
    logger.info(
        "[run_single_simulation] batch=%s scenario=%s model=%s seed=%d",
        batch_id,
        scenario_path,
        model_name,
        seed,
    )

    # Idempotency (D-08). acks_late means Celery redelivers this message if the
    # worker dies after starting it, so the task can legitimately run twice for
    # one (batch, seed). Writing a second RunRecord would corrupt the batch
    # aggregate and double-bump runs_completed, reporting more runs than were
    # paid for. (batch_id, seed) identifies the run.
    with session_scope() as db:
        if RunRepository(db).get_by_batch_and_seed(batch_id, seed) is not None:
            logger.info(
                "run already recorded, skipping redelivery batch=%s seed=%d",
                batch_id,
                seed,
            )
            return {"batch_id": batch_id, "seed": seed, "skipped": "already_recorded"}

    try:
        model = resolve_model(model_name, _BUILTIN_MODELS, org_id=org_id)
        # Frames are collected for every run and kept only for the ones worth
        # scrubbing (2.5). Collecting is cheap - a 30 s run is ~1,500 dicts held
        # for the length of one run - and there is no way to know in advance
        # whether a run will collide, which is the only interesting case.
        runner = EvaluationRunner(collect_frames=True)
        result = runner.run_single(scenario_path, model, seed)
    except TRANSIENT_ERRORS as exc:
        if task.request.retries < MAX_RETRIES:
            countdown = RETRY_BACKOFF_SECONDS[task.request.retries]
            logger.warning(
                "transient failure batch=%s seed=%d, retry %d/%d in %ds: %s",
                batch_id,
                seed,
                task.request.retries + 1,
                MAX_RETRIES,
                countdown,
                exc,
            )
            # No refund and no counter bump here: the run is still in flight.
            # Refunding on every attempt would hand back one credit per retry.
            raise task.retry(exc=exc, countdown=countdown)

        logger.exception(
            "transient failure exhausted retries batch=%s seed=%d",
            batch_id,
            seed,
        )
        _fail_run(batch_id, seed, org_id, exc)
        raise
    except Exception as exc:
        # Deterministic failure — a bad model or scenario fails identically on
        # every attempt, so retrying only burns the customer's compute.
        logger.exception("run failed batch=%s seed=%d", batch_id, seed)
        _fail_run(batch_id, seed, org_id, exc)
        raise

    with session_scope() as db:
        run_row = RunRepository(db).save_result(
            scenario_id,
            result,
            batch_job_id=batch_id,
            org_id=org_id,
        )

        # Keep the frames only when the run is worth watching. store_frames
        # never raises: losing playback for one run is a degraded experience,
        # failing a run that already executed and scored is worse.
        if should_store(result.safety.collision_occurred, result.termination_reason):
            db.flush()
            store_frames(
                db,
                run_row.id,
                result.frames,
                reason=(
                    "collision"
                    if result.safety.collision_occurred
                    else result.termination_reason or "flagged"
                ),
            )

        batch_repo = BatchJobRepository(db)
        batch_repo.increment_completed(batch_id)
        finished = batch_repo.finalise_if_done(batch_id)
        notify: Optional[Dict[str, Any]] = None
        if finished is not None and finished.status == "completed":
            # Captured inside the session, dispatched outside it: a webhook can
            # take seconds, and holding a database transaction open across a
            # network call to an address the customer chose is how a slow
            # endpoint becomes a connection-pool outage.
            notify = {
                "batch_id": finished.id,
                "org_id": finished.org_id,
                "scenario_name": finished.scenario_name,
                "model_name": finished.model_name,
                "num_runs": finished.num_runs,
                "runs_completed": finished.runs_completed,
                "runs_failed": finished.runs_failed,
                "composite_mean": finished.composite_mean,
                "collision_rate": finished.collision_rate,
            }

    if notify is not None:
        from arep.api.webhooks import dispatch

        org_id = notify.pop("org_id")
        dispatch("batch.completed", org_id, notify)

    return {
        "batch_id": batch_id,
        "seed": seed,
        "composite_score": float(result.composite_score),
        "collision": bool(result.safety.collision_occurred),
    }


@celery_app.task(
    bind=True,
    name="arep.worker.tasks.run_single_simulation",
    max_retries=MAX_RETRIES,
    acks_late=True,
)
def run_single_simulation(self, *args, **kwargs):
    """Celery entry point. The logic lives in execute_single_run().

    Split so the retry decisions can be tested directly: the decorator binds
    `self`, so a test cannot pass its own task double to the task object, and
    driving retries through eager-mode Celery hides the decision behind its
    outcome.
    """
    return execute_single_run(self, *args, **kwargs)


@celery_app.task(
    bind=True,
    name="arep.worker.tasks.run_batch_simulations",
    max_retries=0,
)
def run_batch_simulations(
    self,
    batch_id: int,
    scenario_path: str,
    model_name: str,
    master_seed: int,
    num_runs: int,
    org_id: Optional[str] = None,
) -> dict:
    """Fan out N ``run_single_simulation`` tasks for a batch.

    Used when the API wants to defer the fan-out itself (large batches).
    Looks up scenario_id by re-parsing the scenario; the scenario row is
    expected to exist already.
    """
    parser = ScenarioParser()
    scenario_def, content_hash = parser.parse_file(scenario_path)
    with session_scope() as db:
        scenario_repo = ScenarioRepository(db)
        from pathlib import Path

        scenario_rec = scenario_repo.upsert(
            name=scenario_def.name,
            version=scenario_def.version,
            content_hash=content_hash,
            yaml_content=Path(scenario_path).read_text(encoding="utf-8"),
            duration=scenario_def.duration,
            road_type=scenario_def.road.road_type,
            num_traffic_objects=len(scenario_def.traffic_objects),
        )
        scenario_id = scenario_rec.id
        BatchJobRepository(db).mark_queued(batch_id)

    for i in range(num_runs):
        run_single_simulation.delay(
            batch_id=batch_id,
            scenario_id=scenario_id,
            scenario_path=scenario_path,
            model_name=model_name,
            seed=master_seed + i,
            org_id=org_id,
        )

    return {"batch_id": batch_id, "enqueued": num_runs}


@celery_app.task(
    name="arep.worker.tasks.run_comparison",
    bind=True,
    acks_late=True,
    max_retries=MAX_RETRIES,
)
def run_comparison(task, comparison_id: int) -> None:
    """Execute a queued model comparison (Phase 2.4).

    The body lives in `analysis.comparison_runner` so the inline fallback in
    `api/compare.py` runs exactly the same code. It handles its own failure and
    refund, and never raises, so there is nothing to retry here: a comparison
    that failed deterministically fails identically on every attempt, and one
    that failed transiently has already refunded the customer.
    """
    from arep.analysis.comparison_runner import execute_comparison

    execute_comparison(comparison_id)
