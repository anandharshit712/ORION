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

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

from arep.api.auth import get_request_principal
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
from arep.models.resolver import resolve_model, is_uuid
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


def _get_model(name: str, org_id: Optional[str] = None) -> ModelInterface:
    """Resolve built-in name OR customer model UUID → ModelInterface."""
    try:
        return resolve_model(name, AVAILABLE_MODELS, org_id=org_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Model not found: {name}")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Routers ──────────────────────────────────────────────────────────────

health_router = APIRouter(tags=["Health"])
models_router = APIRouter(prefix="/models", tags=["Models"])
scenarios_router = APIRouter(prefix="/scenarios", tags=["Scenarios"])
evaluate_router = APIRouter(prefix="/evaluate", tags=["Evaluate"])
jobs_router = APIRouter(prefix="/jobs", tags=["Jobs"])
results_router = APIRouter(prefix="/results", tags=["Results"])
runs_router = APIRouter(prefix="/api/runs", tags=["Runs"])


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
def run_single(req: RunSingleRequest, request: Request):
    """Run a single simulation and return metrics."""
    org_id, _, _ = get_request_principal(request)
    if not Path(req.scenario_path).exists():
        raise HTTPException(404, f"Scenario file not found: {req.scenario_path}")

    model = _get_model(req.model_name, org_id=org_id)
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
        run_repo.save_result(scenario_rec.id, result, org_id=org_id)

    return MetricsResponse(**result.to_dict())


@evaluate_router.post("/batch", response_model=BatchResultResponse)
def run_batch(req: RunBatchRequest, request: Request):
    """Run a batch evaluation and return aggregated metrics."""
    org_id, _, _ = get_request_principal(request)
    if not Path(req.scenario_path).exists():
        raise HTTPException(404, f"Scenario file not found: {req.scenario_path}")

    model = _get_model(req.model_name, org_id=org_id)
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
            org_id=org_id,
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
            run_repo.save_result(scenario_id, result, batch_job_id=job_id, org_id=org_id)

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
def list_jobs(request: Request, limit: int = Query(20, ge=1, le=100)):
    org_id, _, _ = get_request_principal(request)
    with session_scope() as session:
        repo = BatchJobRepository(session)
        jobs = repo.get_recent(limit, org_id=org_id)
        return [BatchJobResponse.model_validate(j) for j in jobs]


@jobs_router.get("/{job_id}", response_model=BatchJobResponse)
def get_job(job_id: int, request: Request):
    org_id, _, _ = get_request_principal(request)
    with session_scope() as session:
        repo = BatchJobRepository(session)
        job = repo.get_by_id(job_id, org_id=org_id)
        if not job:
            raise HTTPException(404, "Job not found")
        return BatchJobResponse.model_validate(job)


# ── Results ──────────────────────────────────────────────────────────────

@results_router.get("/model/{model_name}", response_model=List[RunRecordResponse])
def get_results_by_model(
    model_name: str, request: Request, limit: int = Query(100, ge=1, le=1000),
):
    org_id, _, _ = get_request_principal(request)
    with session_scope() as session:
        repo = RunRepository(session)
        runs = repo.get_runs_for_model(model_name, limit, org_id=org_id)
        return [RunRecordResponse.model_validate(r) for r in runs]


@results_router.get("/batch/{batch_job_id}", response_model=List[RunRecordResponse])
def get_results_by_batch(batch_job_id: int, request: Request):
    org_id, _, _ = get_request_principal(request)
    with session_scope() as session:
        repo = RunRepository(session)
        runs = repo.get_runs_for_batch(batch_job_id, org_id=org_id)
        return [RunRecordResponse.model_validate(r) for r in runs]


# ── Runs (live streaming) ────────────────────────────────────────────────

class StartRunRequest(BaseModel):
    scenario_path: str
    model_name: str
    master_seed: int = Field(default=42)
    tick_interval: float = Field(
        default=0.02,
        description="Wall-clock seconds between ticks; <=0 runs as fast as possible.",
    )


class StartRunResponse(BaseModel):
    run_id: str
    status: str
    scenario_name: str
    model_name: str
    master_seed: int
    ws_url: str


class RunStatusResponse(BaseModel):
    run_id: str
    id: str
    status: str
    scenario_name: str
    model_name: str
    master_seed: int
    started_at: str
    completed_at: Optional[str] = None
    subscribers: int
    error: Optional[str] = None
    composite_score: float = 0.0
    safety_score: float = 0.0
    compliance_score: float = 0.0
    stability_score: float = 0.0
    reactivity_score: float = 0.0
    collision_occurred: bool = False


@runs_router.post("/", response_model=StartRunResponse, status_code=201)
async def start_run(req: StartRunRequest, request: Request):
    """Launch a live simulation run. Clients connect to the returned
    ``ws_url`` (with ``?token=<jwt>``) to receive 50 Hz tick frames."""
    org_id, user_id, _ = get_request_principal(request)
    if not Path(req.scenario_path).exists():
        raise HTTPException(404, f"Scenario file not found: {req.scenario_path}")
    # Validate model resolution before launching producer task
    if req.model_name not in AVAILABLE_MODELS and not is_uuid(req.model_name):
        raise HTTPException(
            400,
            f"Unknown model: {req.model_name!r}. "
            f"Available built-ins: {list(AVAILABLE_MODELS.keys())} or pass a model UUID.",
        )

    from arep.api.sim_registry import start_run as _start_run

    try:
        run = await _start_run(
            scenario_path=req.scenario_path,
            model_name=req.model_name,
            master_seed=req.master_seed,
            tick_interval=req.tick_interval,
            org_id=org_id,
            user_id=user_id,
        )
    except Exception as e:
        logger.exception("Failed to start live run")
        raise HTTPException(500, f"Failed to start run: {e}")

    return StartRunResponse(
        run_id=run.run_id,
        status=run.status,
        scenario_name=run.scenario_name,
        model_name=run.model_name,
        master_seed=run.master_seed,
        ws_url=f"/ws/simulation/{run.run_id}",
    )


@runs_router.get("/", response_model=List[RunStatusResponse])
async def list_live_runs(request: Request):
    org_id, _, _ = get_request_principal(request)
    from arep.api.sim_registry import get_registry
    runs = await get_registry().list()
    return [
        RunStatusResponse(**r.to_dict())
        for r in runs
        if r.org_id == org_id
    ]


@runs_router.get("/{run_id}", response_model=RunStatusResponse)
async def get_live_run(run_id: str, request: Request):
    org_id, _, _ = get_request_principal(request)
    from arep.api.sim_registry import get_registry
    run = await get_registry().get(run_id)
    if run is None or run.org_id != org_id:
        raise HTTPException(404, "Run not found")
    return RunStatusResponse(**run.to_dict())


@runs_router.delete("/{run_id}", status_code=204)
async def cancel_live_run(run_id: str, request: Request):
    org_id, _, _ = get_request_principal(request)
    from arep.api.sim_registry import get_registry
    registry = get_registry()
    run = await registry.get(run_id)
    if run is None or run.org_id != org_id:
        raise HTTPException(404, "Run not found")
    if run.producer_task is not None and not run.producer_task.done():
        run.producer_task.cancel()
    await registry.remove(run_id)
    return None
