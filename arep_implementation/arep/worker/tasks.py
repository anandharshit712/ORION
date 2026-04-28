"""
ORION Celery Tasks  (P1.3 — async batch execution).

Each batch enqueues N copies of ``run_single_simulation``. Workers consume
from the ``simulation`` queue, run a headless ``EvaluationRunner.run_single``,
write results to the database, and increment the parent batch progress.

Failure semantics:
  - max_retries=0 — a failing simulation is logged, the run counts as failed,
    and one credit is refunded to the org. The batch keeps going.
  - When the batch's ``runs_completed + runs_failed`` reaches ``num_runs`` the
    last task to write triggers ``finalise_if_done`` which aggregates per-run
    rows and flips the status to ``completed`` (or ``failed`` if every run died).

Tasks are JSON-serialisable only — never pass ORM objects across the wire.
"""

from __future__ import annotations

from typing import Optional

from arep.database.connection import session_scope
from arep.database.repository import (
    BatchJobRepository, OrganisationRepository,
    RunRepository, ScenarioRepository,
)
from arep.execution.runner import EvaluationRunner
from arep.models.examples.example_models import (
    ConstantActionModel, EmergencyBrakeModel,
    SimpleLaneKeepModel, RandomModel,
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


def _refund_credit(org_id: Optional[str]) -> None:
    if not org_id:
        return
    try:
        with session_scope() as db:
            OrganisationRepository(db).add_credits(org_id, 1)
    except Exception:
        logger.exception("credit refund failed for org=%s", org_id)


@celery_app.task(
    bind=True,
    name="arep.worker.tasks.run_single_simulation",
    max_retries=0,
    acks_late=True,
)
def run_single_simulation(
    self,
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
        batch_id, scenario_path, model_name, seed,
    )

    try:
        model = resolve_model(model_name, _BUILTIN_MODELS, org_id=org_id)
        runner = EvaluationRunner()
        result = runner.run_single(scenario_path, model, seed)
    except Exception as exc:
        logger.exception("run failed batch=%s seed=%d", batch_id, seed)
        with session_scope() as db:
            batch_repo = BatchJobRepository(db)
            batch_repo.increment_failed(batch_id)
            batch_repo.set_error(batch_id, str(exc))
            batch_repo.finalise_if_done(batch_id)
        _refund_credit(org_id)
        raise

    with session_scope() as db:
        RunRepository(db).save_result(
            scenario_id, result, batch_job_id=batch_id, org_id=org_id,
        )
        batch_repo = BatchJobRepository(db)
        batch_repo.increment_completed(batch_id)
        batch_repo.finalise_if_done(batch_id)

    return {
        "batch_id": batch_id,
        "seed": seed,
        "composite_score": float(result.composite_score),
        "collision": bool(result.safety.collision_occurred),
    }


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
