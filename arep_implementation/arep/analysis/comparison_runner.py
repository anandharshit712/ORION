"""
Execute a queued model comparison (Phase 2.4).

Kept out of `api/compare.py` so the same code runs whether the job came from
Celery or was executed inline because no broker was reachable. The alternative —
duplicating it in the task — is how the two paths drift.
"""

from __future__ import annotations

import datetime
from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Optional

from arep.database.connection import session_scope
from arep.database.models import ComparisonJobRecord
from arep.database.repository import OrganisationRepository
from arep.utils.logging_config import get_logger

logger = get_logger("analysis.comparison_runner")


@dataclass
class _JobParams:
    """The job's inputs, read inside the session and used outside it.

    A dict of mixed types would erase them, and the whole point of reading these
    out is to hand them to a typed call.
    """

    model_a_id: str
    model_b_id: str
    scenario_ids: List[str]
    runs_per_scenario: int
    seed: int
    org_id: Optional[str]
    credits_charged: int


def execute_comparison(comparison_id: int) -> None:
    """Run one comparison to completion and record the outcome.

    Never raises. The caller is a Celery task or a request thread, and in both
    cases an escaping exception loses the refund — the customer was charged
    before the work was queued.
    """
    from arep.analysis.regression_detector import RegressionDetector

    with session_scope() as db:
        job = db.get(ComparisonJobRecord, comparison_id)
        if job is None:
            logger.error("Comparison %s vanished before it ran", comparison_id)
            return
        if job.status not in ("queued", "running"):
            # Already finished. A Celery redelivery must not re-run the work or
            # re-charge for it.
            logger.info(
                "Comparison %s is already %s — not re-running",
                comparison_id,
                job.status,
            )
            return

        job.status = "running"
        params = _JobParams(
            model_a_id=job.model_a_id,
            model_b_id=job.model_b_id,
            scenario_ids=job.scenario_ids.splitlines(),
            runs_per_scenario=job.runs_per_scenario,
            seed=job.seed,
            org_id=job.org_id,
            credits_charged=job.credits_charged,
        )

    try:
        report = RegressionDetector().compare(
            model_a_id=params.model_a_id,
            model_b_id=params.model_b_id,
            scenario_ids=params.scenario_ids,
            runs_per_scenario=params.runs_per_scenario,
            seed=params.seed,
        )
    except Exception as exc:  # noqa: BLE001 - see docstring
        logger.exception("Comparison %s failed", comparison_id)
        _fail(comparison_id, params, exc)
        return

    with session_scope() as db:
        job = db.get(ComparisonJobRecord, comparison_id)
        if job is None:
            return
        job.status = "completed"
        job.overall_winner = report.overall_winner
        job.recommendation = report.recommendation
        job.has_regression = bool(report.regressions)
        job.report_json = _serialise(report)
        job.completed_at = datetime.datetime.utcnow()

    logger.info(
        "Comparison %s complete: winner=%s regressions=%d",
        comparison_id,
        report.overall_winner,
        len(report.regressions),
    )


def _fail(comparison_id: int, params: "_JobParams", exc: Exception) -> None:
    """Mark the job failed and refund what was charged.

    The refund uses the recorded `credits_charged`, not a recomputed cost: the
    pricing formula can change between charge and refund, and the customer is
    owed what they actually paid.
    """
    with session_scope() as db:
        job = db.get(ComparisonJobRecord, comparison_id)
        if job is not None:
            job.status = "failed"
            job.error_message = f"{type(exc).__name__}: {exc}"
            job.completed_at = datetime.datetime.utcnow()

        org_id = params.org_id
        charged = params.credits_charged or 0
        if org_id and charged:
            OrganisationRepository(db).add_credits(org_id, charged)
            logger.info(
                "Refunded %d credits to org %s for failed comparison %s",
                charged,
                org_id,
                comparison_id,
            )


def _serialise(report) -> Dict[str, Any]:
    """Comparison report as plain JSON for storage and the API.

    `asdict` on the nested dataclasses rather than a hand-written mapping, so a
    field added to `MetricDelta` or `ScenarioComparison` reaches the API without
    anyone remembering to update this.
    """
    return {
        "model_a_id": report.model_a_id,
        "model_a_name": report.model_a_name,
        "model_b_id": report.model_b_id,
        "model_b_name": report.model_b_name,
        "overall_winner": report.overall_winner,
        "recommendation": report.recommendation,
        "regressions": [asdict(d) for d in report.regressions],
        "scenario_comparisons": [asdict(c) for c in report.scenario_comparisons],
    }
