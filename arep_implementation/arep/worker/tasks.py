"""
ORION Celery Tasks.  [Phase 1]

Async simulation tasks consumed by Celery workers.
Each task runs a single simulation headlessly and writes results to the DB.

Task lifecycle:
  1. API server enqueues task after deducting org run credits
  2. Worker picks up task, fetches model artefact from model store
  3. Worker deserialises/spins-up model, runs simulation, writes results
  4. Worker updates run status to "completed" or "failed"
  5. On failure: credits are refunded to the org

Never call these tasks directly — always enqueue via .delay() or .apply_async().
"""

from __future__ import annotations

from arep.utils.logging_config import get_logger
from arep.worker.celery_app import celery_app

logger = get_logger("worker.tasks")


@celery_app.task(
    bind=True,
    name="arep.worker.tasks.run_single_simulation",
    max_retries=0,           # do not retry — refund credits on failure instead
    acks_late=True,
)
def run_single_simulation(
    self,
    run_id: str,
    scenario_id: str,
    model_id: str,
    seed: int,
    org_id: str,
    physics_mode: str = "kinematic",
) -> dict:
    """
    Run one simulation headlessly and persist results.

    Args:
        run_id:       UUID of the RunRecord (pre-created by API server).
        scenario_id:  Scenario name/ID to load from the library.
        model_id:     UUID of the ModelRecord to fetch from model store.
        seed:         Deterministic seed for this run.
        org_id:       Organisation UUID (for credit refund on failure).
        physics_mode: "kinematic" or "dynamic".

    Returns:
        dict with composite_score, safety_score, etc.

    TODO [P1]: Load scenario YAML from DB or scenarios/ directory.
    TODO [P1]: Fetch model artefact from ModelStore.
    TODO [P1]: Deserialise with SubprocessModelRunner or spin up HttpModelAdapter.
    TODO [P1]: Run EvaluationRunner.run_single() headlessly.
    TODO [P1]: Write results to run_metrics table via RunRepository.
    TODO [P1]: Update run status to "completed".
    TODO [P1]: On any exception, call refund_credits(org_id, 1) and mark run "failed".
    """
    logger.info(f"[run_single_simulation] run_id={run_id} scenario={scenario_id} seed={seed}")

    try:
        # TODO [P1]: implement full task body
        raise NotImplementedError("run_single_simulation not yet implemented")

    except Exception as exc:
        logger.error(f"[run_single_simulation] FAILED run_id={run_id}: {exc}")
        # TODO [P1]: refund_credits(org_id, 1)
        # TODO [P1]: mark run as "failed" in DB
        raise


@celery_app.task(
    bind=True,
    name="arep.worker.tasks.run_batch_simulations",
    max_retries=0,
    acks_late=True,
)
def run_batch_simulations(
    self,
    batch_id: str,
    scenario_id: str,
    model_id: str,
    seed_start: int,
    seed_step: int,
    num_runs: int,
    org_id: str,
    physics_mode: str = "kinematic",
) -> dict:
    """
    Enqueue N individual run_single_simulation tasks for a batch job.

    This task itself is lightweight — it fans out to N individual tasks
    and returns immediately. Progress is tracked via the batch_jobs table.

    TODO [P1]: Create N RunRecord rows (status=queued) in the DB.
    TODO [P1]: Enqueue N run_single_simulation.delay() calls.
    TODO [P1]: Return immediately with { batch_id, run_ids }.
    """
    logger.info(
        f"[run_batch_simulations] batch_id={batch_id} "
        f"scenario={scenario_id} n={num_runs}"
    )
    raise NotImplementedError("run_batch_simulations not yet implemented")
