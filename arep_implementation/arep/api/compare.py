"""
Model comparison over HTTP (Phase 2.4).

`RegressionDetector` has worked since Phase 2 but was reachable only from the
CLI, so the dashboard's Compare section had nothing to call and the feature did
not exist as far as a customer was concerned.

Comparison runs `2 x runs_per_scenario x len(scenario_ids)` simulations, which
is minutes of work, so it is queued rather than run inside the request. The
response is a job id the client polls, matching how batches already behave.

Credits are charged up front and refunded if the job fails, which is the same
contract `POST /api/runs/batch` uses. Charging on completion would let a
customer queue unlimited work.
"""

from __future__ import annotations

import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from arep.api.auth import get_request_principal, require_verified_email
from arep.database.connection import session_scope
from arep.database.models import ComparisonJobRecord
from arep.database.repository import OrganisationRepository
from arep.utils.logging_config import get_logger

logger = get_logger("api.compare")

compare_router = APIRouter(
    prefix="/api/compare",
    tags=["Comparison"],
    dependencies=[Depends(get_request_principal)],
)

# Each scenario is run once per model, so the cost is two batches' worth. Stated
# as a constant because the roadmap specifies the formula and the dashboard
# quotes it back to the customer before they commit.
RUNS_PER_SCENARIO_PER_MODEL = 2

MAX_SCENARIOS = 60
MAX_RUNS_PER_SCENARIO = 500


def comparison_cost(runs_per_scenario: int, scenario_count: int) -> int:
    """Credits a comparison will consume.

    `2 x runs_per_scenario x len(scenario_ids)` — both models run every
    scenario the same number of times, because comparing one model on one sample
    against another on a different sample measures the sampler.
    """
    return RUNS_PER_SCENARIO_PER_MODEL * runs_per_scenario * scenario_count


class CompareRequest(BaseModel):
    model_a_id: str = Field(..., description="Baseline model (built-in name or UUID)")
    model_b_id: str = Field(..., description="Candidate model")
    scenario_ids: List[str] = Field(
        ...,
        min_length=1,
        max_length=MAX_SCENARIOS,
        description="Scenario paths, or a single-element list containing 'all'",
    )
    runs_per_scenario: int = Field(10, ge=1, le=MAX_RUNS_PER_SCENARIO)
    seed: int = Field(42, description="Both models face this same seed")


class CompareEnqueueResponse(BaseModel):
    comparison_id: int
    status: str
    model_a_id: str
    model_b_id: str
    scenario_count: int
    runs_per_scenario: int
    credits_charged: int
    credits_remaining: int


class CompareStatusResponse(BaseModel):
    comparison_id: int
    status: str
    model_a_id: str
    model_b_id: str
    scenario_count: int
    runs_per_scenario: int
    seed: int
    overall_winner: Optional[str] = None
    recommendation: Optional[str] = None
    has_regression: Optional[bool] = None
    report: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None
    created_at: Optional[datetime.datetime] = None
    completed_at: Optional[datetime.datetime] = None


@compare_router.post(
    "/",
    response_model=CompareEnqueueResponse,
    status_code=202,
    dependencies=[Depends(require_verified_email)],
)
def enqueue_comparison(req: CompareRequest, request: Request):
    """Queue a model comparison. Poll `GET /api/compare/{id}` for the result."""
    org_id, user_id, _ = get_request_principal(request)

    if req.model_a_id == req.model_b_id:
        raise HTTPException(400, "A model cannot be compared against itself")

    scenario_ids = _resolve_scenarios(req.scenario_ids)
    cost = comparison_cost(req.runs_per_scenario, len(scenario_ids))

    with session_scope() as db:
        org_repo = OrganisationRepository(db)

        if org_id is not None:
            # Charged before the work is queued, refunded if it fails. Charging
            # on completion would let a customer queue unlimited work.
            if not org_repo.deduct_credits(org_id, cost):
                raise HTTPException(
                    402,
                    f"Insufficient run credits: a comparison over "
                    f"{len(scenario_ids)} scenario(s) at {req.runs_per_scenario} "
                    f"runs each costs {cost} credits "
                    f"({RUNS_PER_SCENARIO_PER_MODEL} models x "
                    f"{req.runs_per_scenario} x {len(scenario_ids)}).",
                )
            org = org_repo.get_by_id(org_id)
            remaining = org.run_credits if org is not None else 0
        else:
            remaining = 0

        job = ComparisonJobRecord(
            org_id=org_id,
            user_id=user_id,
            model_a_id=req.model_a_id,
            model_b_id=req.model_b_id,
            scenario_ids="\n".join(scenario_ids),
            runs_per_scenario=req.runs_per_scenario,
            seed=req.seed,
            credits_charged=cost,
            status="queued",
        )
        db.add(job)
        db.flush()
        comparison_id = job.id

    _dispatch(comparison_id)

    return CompareEnqueueResponse(
        comparison_id=comparison_id,
        status="queued",
        model_a_id=req.model_a_id,
        model_b_id=req.model_b_id,
        scenario_count=len(scenario_ids),
        runs_per_scenario=req.runs_per_scenario,
        credits_charged=cost,
        credits_remaining=remaining,
    )


@compare_router.get("/{comparison_id}", response_model=CompareStatusResponse)
def get_comparison(comparison_id: int, request: Request):
    """Status, and the full report once the comparison has finished."""
    org_id, _, _ = get_request_principal(request)

    with session_scope() as db:
        job = db.get(ComparisonJobRecord, comparison_id)
        if job is None or (org_id is not None and job.org_id != org_id):
            # 404 rather than 403: whether an id exists is not a stranger's
            # business.
            raise HTTPException(404, "Comparison not found")

        return CompareStatusResponse(
            comparison_id=job.id,
            status=job.status,
            model_a_id=job.model_a_id,
            model_b_id=job.model_b_id,
            scenario_count=len(job.scenario_ids.splitlines()),
            runs_per_scenario=job.runs_per_scenario,
            seed=job.seed,
            overall_winner=job.overall_winner,
            recommendation=job.recommendation,
            has_regression=job.has_regression,
            report=job.report_json,
            error_message=job.error_message,
            created_at=job.created_at,
            completed_at=job.completed_at,
        )


@compare_router.get("/", response_model=List[CompareStatusResponse])
def list_comparisons(request: Request, limit: int = 50):
    """This org's comparisons, newest first."""
    org_id, _, _ = get_request_principal(request)

    with session_scope() as db:
        query = db.query(ComparisonJobRecord)
        if org_id is not None:
            query = query.filter(ComparisonJobRecord.org_id == org_id)
        jobs = query.order_by(ComparisonJobRecord.id.desc()).limit(limit).all()

        return [
            CompareStatusResponse(
                comparison_id=j.id,
                status=j.status,
                model_a_id=j.model_a_id,
                model_b_id=j.model_b_id,
                scenario_count=len(j.scenario_ids.splitlines()),
                runs_per_scenario=j.runs_per_scenario,
                seed=j.seed,
                overall_winner=j.overall_winner,
                recommendation=j.recommendation,
                has_regression=j.has_regression,
                # The full report is omitted from the list: it is large, and a
                # list view never renders it.
                report=None,
                error_message=j.error_message,
                created_at=j.created_at,
                completed_at=j.completed_at,
            )
            for j in jobs
        ]


def _resolve_scenarios(requested: List[str]) -> List[str]:
    """Expand the "all" shorthand, and reject a selection that matches nothing.

    Exiting successfully on zero scenarios would report a comparison that
    compared nothing, which is the worst available outcome: a green result that
    tested nothing.
    """
    if len(requested) == 1 and requested[0].strip().lower() == "all":
        from pathlib import Path

        root = Path(__file__).resolve().parent.parent.parent.parent / "scenarios"
        found = sorted(str(p) for p in root.rglob("*.yaml"))
        if not found:
            raise HTTPException(500, "Scenario library is empty")
        return found[:MAX_SCENARIOS]

    return requested


def _dispatch(comparison_id: int) -> None:
    """Hand the job to Celery, or run it inline when there is no broker.

    A missing broker must not leave the job sitting at "queued" forever with the
    customer's credits already taken.
    """
    try:
        from arep.worker.tasks import run_comparison

        run_comparison.delay(comparison_id)
    except Exception as exc:  # noqa: BLE001 - broker availability is an env fact
        logger.warning(
            "Could not queue comparison %s (%s); running inline",
            comparison_id,
            exc,
        )
        from arep.analysis.comparison_runner import execute_comparison

        execute_comparison(comparison_id)
