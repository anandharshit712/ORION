"""
AREP API Routes.

FastAPI route handlers organized by resource:
  - /health         - Health check
  - /models         - List available models
  - /scenarios      - Scenario CRUD
  - /evaluate       - Run evaluations
  - /jobs           - Batch job management
  - /results        - Query results
"""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query

from arep.api.schemas import (
    RunSingleRequest, RunBatchRequest,
    MetricsResponse, BatchResultResponse, AggregatedResponse,
    ScenarioResponse, BatchJobResponse, RunRecordResponse,
    HealthResponse, ModelListResponse,
)
from arep.config import get_config
from arep.database.connection import session_scope
from arep.database.repository import (
    ScenarioRepository, RunRepository, BatchJobRepository,
)
from arep.execution.runner import EvaluationRunner
from arep.models.examples.example_models import (
    ConstantActionModel, EmergencyBrakeModel,
    SimpleLaneKeepModel, RandomModel,
)
from arep.models.interface import ModelInterface
from arep.scenario.parser import ScenarioParser
from arep.utils.logging_config import get_logger

logger = get_logger("api.routes")

# ── Available models registry ────────────────────────────────────────────

AVAILABLE_MODELS = {
    "ConstantAction": lambda: ConstantActionModel(throttle=0.3),
    "EmergencyBrake": lambda: EmergencyBrakeModel(),
    "SimpleLaneKeep": lambda: SimpleLaneKeepModel(),
    "Random": lambda: RandomModel(seed=42),
}


def _get_model(name: str) -> ModelInterface:
    if name not in AVAILABLE_MODELS:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown model: {name!r}. Available: {list(AVAILABLE_MODELS.keys())}",
        )
    return AVAILABLE_MODELS[name]()


# ── Routers ──────────────────────────────────────────────────────────────

health_router = APIRouter(tags=["Health"])
models_router = APIRouter(prefix="/models", tags=["Models"])
scenarios_router = APIRouter(prefix="/scenarios", tags=["Scenarios"])
evaluate_router = APIRouter(prefix="/evaluate", tags=["Evaluate"])
jobs_router = APIRouter(prefix="/jobs", tags=["Jobs"])
results_router = APIRouter(prefix="/results", tags=["Results"])


# ── Health ───────────────────────────────────────────────────────────────

@health_router.get("/health", response_model=HealthResponse)
def health_check():
    return HealthResponse(
        status="healthy",
        version="1.0.0",
        components={
            "simulation_engine": "ok",
            "database": "ok",
        },
    )


# ── Models ───────────────────────────────────────────────────────────────

@models_router.get("/", response_model=ModelListResponse)
def list_models():
    return ModelListResponse(models=list(AVAILABLE_MODELS.keys()))


# ── Scenarios ────────────────────────────────────────────────────────────

@scenarios_router.get("/", response_model=List[ScenarioResponse])
def list_scenarios():
    with session_scope() as session:
        repo = ScenarioRepository(session)
        scenarios = repo.get_all()
        return [
            ScenarioResponse.model_validate(s) for s in scenarios
        ]


@scenarios_router.get("/{scenario_id}", response_model=ScenarioResponse)
def get_scenario(scenario_id: int):
    with session_scope() as session:
        repo = ScenarioRepository(session)
        scenario = session.query(
            __import__('arep.database.models', fromlist=['ScenarioRecord']).ScenarioRecord
        ).get(scenario_id)
        if not scenario:
            raise HTTPException(404, "Scenario not found")
        return ScenarioResponse.model_validate(scenario)


# ── Evaluate ─────────────────────────────────────────────────────────────

@evaluate_router.post("/single", response_model=MetricsResponse)
def run_single(req: RunSingleRequest):
    """Run a single simulation and return metrics."""
    if not Path(req.scenario_path).exists():
        raise HTTPException(404, f"Scenario file not found: {req.scenario_path}")

    model = _get_model(req.model_name)
    runner = EvaluationRunner()

    try:
        result = runner.run_single(req.scenario_path, model, req.master_seed)
    except Exception as e:
        raise HTTPException(500, f"Simulation error: {e}")

    # Save to database
    parser = ScenarioParser()
    scenario_def, content_hash = parser.parse_file(req.scenario_path)

    with session_scope() as session:
        scenario_repo = ScenarioRepository(session)
        scenario_rec = scenario_repo.upsert(
            name=scenario_def.name,
            version=scenario_def.version,
            content_hash=content_hash,
            yaml_content=Path(req.scenario_path).read_text(encoding="utf-8"),
            duration=scenario_def.duration,
            road_type=scenario_def.road.road_type,
            num_traffic_objects=len(scenario_def.traffic_objects),
        )
        run_repo = RunRepository(session)
        run_repo.save_result(scenario_rec.id, result)

    return MetricsResponse(**result.to_dict())


@evaluate_router.post("/batch", response_model=BatchResultResponse)
def run_batch(req: RunBatchRequest):
    """Run a batch evaluation and return aggregated metrics."""
    if not Path(req.scenario_path).exists():
        raise HTTPException(404, f"Scenario file not found: {req.scenario_path}")

    model = _get_model(req.model_name)
    runner = EvaluationRunner()

    # Create batch job record
    parser = ScenarioParser()
    scenario_def, content_hash = parser.parse_file(req.scenario_path)

    with session_scope() as session:
        scenario_repo = ScenarioRepository(session)
        scenario_rec = scenario_repo.upsert(
            name=scenario_def.name,
            version=scenario_def.version,
            content_hash=content_hash,
            yaml_content=Path(req.scenario_path).read_text(encoding="utf-8"),
            duration=scenario_def.duration,
            road_type=scenario_def.road.road_type,
            num_traffic_objects=len(scenario_def.traffic_objects),
        )

        batch_repo = BatchJobRepository(session)
        job = batch_repo.create(
            scenario_name=scenario_def.name,
            model_name=req.model_name,
            num_runs=req.num_runs,
            master_seed=req.master_seed,
        )
        batch_repo.mark_running(job.id)
        job_id = job.id
        scenario_id = scenario_rec.id

    try:
        batch_result = runner.run_batch(
            req.scenario_path, model, req.num_runs, req.master_seed,
        )
    except Exception as e:
        with session_scope() as session:
            batch_repo = BatchJobRepository(session)
            batch_repo.mark_failed(job_id)
        raise HTTPException(500, f"Batch error: {e}")

    # Save results
    with session_scope() as session:
        run_repo = RunRepository(session)
        batch_repo = BatchJobRepository(session)

        for result in batch_result.per_run_results:
            run_repo.save_result(scenario_id, result, batch_job_id=job_id)

        batch_repo.mark_completed(job_id, batch_result.aggregated)

    agg = batch_result.aggregated
    return BatchResultResponse(
        scenario_name=batch_result.scenario_name,
        model_name=batch_result.model_name,
        num_runs=batch_result.num_runs,
        aggregated=AggregatedResponse(**agg.to_dict()),
        per_run=[
            MetricsResponse(**r.to_dict())
            for r in batch_result.per_run_results
        ],
    )


# ── Jobs ─────────────────────────────────────────────────────────────────

@jobs_router.get("/", response_model=List[BatchJobResponse])
def list_jobs(limit: int = Query(20, ge=1, le=100)):
    with session_scope() as session:
        repo = BatchJobRepository(session)
        jobs = repo.get_recent(limit)
        return [BatchJobResponse.model_validate(j) for j in jobs]


@jobs_router.get("/{job_id}", response_model=BatchJobResponse)
def get_job(job_id: int):
    with session_scope() as session:
        repo = BatchJobRepository(session)
        job = repo.get_by_id(job_id)
        if not job:
            raise HTTPException(404, "Job not found")
        return BatchJobResponse.model_validate(job)


# ── Results ──────────────────────────────────────────────────────────────

@results_router.get("/model/{model_name}", response_model=List[RunRecordResponse])
def get_results_by_model(
    model_name: str, limit: int = Query(100, ge=1, le=1000),
):
    with session_scope() as session:
        repo = RunRepository(session)
        runs = repo.get_runs_for_model(model_name, limit)
        return [RunRecordResponse.model_validate(r) for r in runs]


@results_router.get("/batch/{batch_job_id}", response_model=List[RunRecordResponse])
def get_results_by_batch(batch_job_id: int):
    with session_scope() as session:
        repo = RunRepository(session)
        runs = repo.get_runs_for_batch(batch_job_id)
        return [RunRecordResponse.model_validate(r) for r in runs]
