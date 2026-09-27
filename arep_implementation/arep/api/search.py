"""
Adversarial search over HTTP (Phase 2.3).

CMA-ES has worked since Phase 2 but was reachable only from the CLI, so as far
as a customer was concerned the feature did not exist. This is the same shape
as `POST /api/compare`: charge up front, queue, poll, refund on failure.

**Pricing is `max_evals` credits.** That is honest only because the search
spends its whole budget — `stop_on_first_falsification` is off, so it keeps
going past the first collision and reports every distinct failure it finds.
Under the old stop-at-first behaviour the same price would have billed 200
evaluations and run one. No tier gate: credits are the limiter, and a customer
who hits this once on the free plan is the best argument for the paid one.

**A scenario with no `parameterization` block cannot be searched** and is
refused at request time rather than queued. Eleven of the twenty-one scenarios
were in that state until Phase 2.3 parameterised them; a search over zero
dimensions returns "no failure found" for a model that was never varied, which
is the dangerous answer.
"""

from __future__ import annotations

import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from arep.api.auth import get_request_principal, require_verified_email
from arep.database.connection import session_scope
from arep.database.models import SearchJobRecord
from arep.database.repository import OrganisationRepository
from arep.utils.logging_config import get_logger

logger = get_logger("api.search")

search_router = APIRouter(
    prefix="/api/search",
    tags=["Adversarial search"],
    dependencies=[Depends(get_request_principal)],
)

# A budget below this cannot say anything about CMA-ES. Measured on LON-003:
# at 50 evaluations over 8 dimensions random search wins 13.51 to 1.57, because
# CMA-ES spends its early evaluations learning the shape of the space. It only
# pulls ahead around 10 evaluations per dimension.
MIN_EVALS = 10
MAX_EVALS = 2000


class SearchRequest(BaseModel):
    scenario_id: str = Field(..., description="Scenario path to search")
    model_id: str = Field(..., description="Model to break (built-in name or UUID)")
    max_evals: Optional[int] = Field(
        None,
        ge=MIN_EVALS,
        le=MAX_EVALS,
        description=(
            "Evaluation budget, and the price in credits. Omit it to use the "
            "budget recommended for this scenario's dimensionality."
        ),
    )
    optimizer: str = Field("cma_es", pattern="^(cma_es|random)$")
    physics_mode: str = Field("kinematic", pattern="^(kinematic|dynamic)$")
    seed: int = Field(42, description="Search seed; the same seed repeats the search")


class SearchEnqueueResponse(BaseModel):
    search_id: int
    status: str
    scenario_id: str
    model_id: str
    optimizer: str
    max_evals: int
    n_dims: int
    recommended_evals: int
    credits_charged: int
    credits_remaining: int


class SearchStatusResponse(BaseModel):
    search_id: int
    status: str
    scenario_id: str
    model_id: str
    optimizer: str
    physics_mode: str
    max_evals: int
    n_dims: int
    seed: int
    evals_done: int
    best_fitness: Optional[float] = None
    falsification_found: Optional[bool] = None
    credits_charged: int
    error_message: Optional[str] = None
    created_at: Optional[datetime.datetime] = None
    completed_at: Optional[datetime.datetime] = None


class SearchResultResponse(SearchStatusResponse):
    result: Optional[Dict[str, Any]] = None


def _space_for(scenario_id: str):
    """Parse the scenario and build its search space, or explain why not."""
    from pathlib import Path

    from arep.scenario.parser import ScenarioParser
    from arep.search.space import SearchSpace

    # Checked here rather than caught: the parser reports a missing file as a
    # ScenarioParseError like any other, and "you sent a path that is not
    # there" and "that file is malformed" are different answers for the caller.
    if not Path(scenario_id).exists():
        raise HTTPException(404, f"Scenario not found: {scenario_id}")

    try:
        scenario, _ = ScenarioParser().parse_file(scenario_id)
    except Exception as exc:  # noqa: BLE001 - a parse error is the caller's input
        raise HTTPException(400, f"Could not read scenario: {exc}")

    space = SearchSpace(scenario)
    if space.n_dims == 0:
        # Refused, not run. A search over nothing reports "no failure found"
        # about a model whose scenario was never varied — a pass that tested
        # one fixed setting, which reads exactly like a pass that tested 200.
        raise HTTPException(
            400,
            f"{scenario_id} has no parameterization block, so there is nothing "
            "to search. Add parameter ranges to the scenario first — every "
            "scenario in the library is expected to carry them.",
        )
    return space


@search_router.post(
    "/",
    response_model=SearchEnqueueResponse,
    status_code=202,
    dependencies=[Depends(require_verified_email)],
)
def enqueue_search(req: SearchRequest, request: Request):
    """Queue an adversarial search. Poll `GET /api/search/{id}/status`."""
    from arep.search.optimizer import recommended_evals

    org_id, user_id, _ = get_request_principal(request)

    space = _space_for(req.scenario_id)
    recommended = recommended_evals(space.n_dims)

    # Scaled per scenario rather than a flat floor: the library runs 1 to 11
    # dimensions, and charging a one-dimensional scenario for 150 evaluations
    # bills fifteen times over for a search that converged at ten.
    budget = req.max_evals if req.max_evals is not None else recommended
    cost = budget

    with session_scope() as db:
        org_repo = OrganisationRepository(db)

        if org_id is not None:
            # Charged before the work is queued, refunded if it fails — the
            # same contract as batches and comparisons. Charging on completion
            # would let a customer queue unlimited work.
            if not org_repo.deduct_credits(org_id, cost):
                raise HTTPException(
                    402,
                    f"Insufficient run credits: a {budget}-evaluation search "
                    f"costs {budget} credits. This scenario has {space.n_dims} "
                    f"searchable dimension(s); {recommended} evaluations is the "
                    "recommended budget for it.",
                )
            org = org_repo.get_by_id(org_id)
            remaining = org.run_credits if org is not None else 0
        else:
            remaining = 0

        job = SearchJobRecord(
            org_id=org_id,
            user_id=user_id,
            scenario_id=req.scenario_id,
            model_id=req.model_id,
            optimizer=req.optimizer,
            physics_mode=req.physics_mode,
            max_evals=budget,
            seed=req.seed,
            n_dims=space.n_dims,
            credits_charged=cost,
            status="queued",
        )
        db.add(job)
        db.flush()
        search_id = job.id

    _dispatch(search_id)

    return SearchEnqueueResponse(
        search_id=search_id,
        status="queued",
        scenario_id=req.scenario_id,
        model_id=req.model_id,
        optimizer=req.optimizer,
        max_evals=budget,
        n_dims=space.n_dims,
        recommended_evals=recommended,
        credits_charged=cost,
        credits_remaining=remaining,
    )


@search_router.get("/{search_id}/status", response_model=SearchStatusResponse)
def get_search_status(search_id: int, request: Request):
    """Progress only. The result is a separate, much larger response."""
    return _status(_load(search_id, request), SearchStatusResponse)


@search_router.get("/{search_id}/result", response_model=SearchResultResponse)
def get_search_result(search_id: int, request: Request):
    """Everything the search found, including the evaluation history."""
    job = _load(search_id, request)
    response = _status(job, SearchResultResponse)
    response.result = job["result_json"]
    return response


@search_router.get("/", response_model=List[SearchStatusResponse])
def list_searches(request: Request, limit: int = 50):
    """This org's searches, newest first."""
    org_id, _, _ = get_request_principal(request)

    with session_scope() as db:
        query = db.query(SearchJobRecord)
        if org_id is not None:
            query = query.filter(SearchJobRecord.org_id == org_id)
        jobs = query.order_by(SearchJobRecord.id.desc()).limit(limit).all()
        return [_status(_row(j), SearchStatusResponse) for j in jobs]


def _load(search_id: int, request: Request) -> Dict[str, Any]:
    org_id, _, _ = get_request_principal(request)

    with session_scope() as db:
        job = db.get(SearchJobRecord, search_id)
        if job is None or (org_id is not None and job.org_id != org_id):
            # 404 rather than 403: whether an id exists is not a stranger's
            # business.
            raise HTTPException(404, "Search not found")
        return _row(job)


def _row(job: SearchJobRecord) -> Dict[str, Any]:
    """Read the record inside its session; the response is built outside it."""
    return {
        "search_id": job.id,
        "status": job.status,
        "scenario_id": job.scenario_id,
        "model_id": job.model_id,
        "optimizer": job.optimizer,
        "physics_mode": job.physics_mode,
        "max_evals": job.max_evals,
        "n_dims": job.n_dims,
        "seed": job.seed,
        "evals_done": job.evals_done,
        "best_fitness": job.best_fitness,
        "falsification_found": job.falsification_found,
        "credits_charged": job.credits_charged,
        "error_message": job.error_message,
        "created_at": job.created_at,
        "completed_at": job.completed_at,
        "result_json": job.result_json,
    }


def _status(row: Dict[str, Any], model):
    return model(**{k: v for k, v in row.items() if k != "result_json"})


def _dispatch(search_id: int) -> None:
    """Hand the job to Celery, or run it inline when there is no broker.

    A missing broker must not leave the job at "queued" forever with the
    customer's credits already taken.
    """
    try:
        from arep.worker.tasks import run_search

        run_search.delay(search_id)
    except Exception as exc:  # noqa: BLE001 - broker availability is an env fact
        logger.warning("Could not queue search %s (%s); running inline", search_id, exc)
        from arep.analysis.search_runner import execute_search

        execute_search(search_id)
