"""
Execute a queued adversarial search (Phase 2.3).

Kept out of `api/search.py` so the same code runs whether the job arrived via
Celery or was executed inline because no broker was reachable. Duplicating it
in the task is how the two paths drift — see `comparison_runner`, which this
mirrors deliberately.
"""

from __future__ import annotations

import datetime
from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Optional

from arep.database.connection import session_scope
from arep.database.models import SearchJobRecord
from arep.database.repository import OrganisationRepository
from arep.utils.logging_config import get_logger

logger = get_logger("analysis.search_runner")

# The full evaluation history is the interesting part of a search, but 200
# records with nested parameter dicts is a large JSON column and a larger HTTP
# response. Stored in full up to this many; beyond it, the failures are kept and
# the successes are dropped, because nobody debugs a model from the runs where
# nothing went wrong.
MAX_STORED_EVALUATIONS = 200


@dataclass
class _JobParams:
    """The job's inputs, read inside the session and used outside it."""

    scenario_id: str
    model_id: str
    optimizer: str
    physics_mode: str
    max_evals: int
    seed: int
    org_id: Optional[str]
    credits_charged: int


def execute_search(search_id: int) -> None:
    """Run one search to completion and record the outcome.

    Never raises. The caller is a Celery task or a request thread, and in both
    cases an escaping exception loses the refund — the customer was charged
    before the work was queued.
    """
    with session_scope() as db:
        job = db.get(SearchJobRecord, search_id)
        if job is None:
            logger.error("Search %s vanished before it ran", search_id)
            return
        if job.status not in ("queued", "running"):
            # Already finished. A Celery redelivery must not re-run the work,
            # which would be the whole budget again, or re-charge for it.
            logger.info(
                "Search %s is already %s — not re-running", search_id, job.status
            )
            return

        job.status = "running"
        params = _JobParams(
            scenario_id=job.scenario_id,
            model_id=job.model_id,
            optimizer=job.optimizer,
            physics_mode=job.physics_mode,
            max_evals=job.max_evals,
            seed=job.seed,
            org_id=job.org_id,
            credits_charged=job.credits_charged,
        )

    try:
        result = _run(params, params.org_id)
    except Exception as exc:  # noqa: BLE001 - see docstring
        logger.exception("Search %s failed", search_id)
        _fail(search_id, params, exc)
        return

    with session_scope() as db:
        job = db.get(SearchJobRecord, search_id)
        if job is None:
            return
        job.status = "completed"
        job.evals_done = result.n_evals
        job.best_fitness = float(result.best_fitness)
        job.falsification_found = bool(result.falsification_found)
        job.result_json = serialise(result)
        job.completed_at = datetime.datetime.utcnow()

    logger.info(
        "Search %s complete: %d evals, falsified=%s, %d distinct failure(s)",
        search_id,
        result.n_evals,
        result.falsification_found,
        result.distinct_failure_count,
    )

    # `search.completed` is a declared webhook event that nothing fired. A
    # search is minutes of work, so the whole reason to register an endpoint is
    # to not sit polling for it.
    try:
        from arep.api.webhooks import dispatch

        dispatch(
            "search.completed",
            params.org_id,
            {
                "search_id": search_id,
                "scenario_id": params.scenario_id,
                "model_id": params.model_id,
                "optimizer": result.optimizer_used,
                "evals": result.n_evals,
                "falsification_found": bool(result.falsification_found),
                "distinct_failure_count": result.distinct_failure_count,
                "failure_rate": result.failure_rate,
                # The settings that broke the model, so a pipeline can act on
                # the notification without a second request.
                "falsification_params": result.falsification_params,
            },
        )
    except Exception:  # noqa: BLE001 - a customer's endpoint is not our failure
        logger.exception("Could not dispatch webhook for search %s", search_id)


def _run(params: _JobParams, org_id: Optional[str] = None):
    """Build the space, objective and optimizer, and run the search."""
    from arep.api.routes import AVAILABLE_MODELS
    from arep.models.resolver import resolve_model
    from arep.scenario.parser import ScenarioParser
    from arep.search.objective import ObjectiveFunction
    from arep.search.optimizer import CMAESOptimizer, RandomSearchOptimizer
    from arep.search.space import SearchSpace

    scenario, _ = ScenarioParser().parse_file(params.scenario_id)
    space = SearchSpace(scenario)
    model = resolve_model(params.model_id, AVAILABLE_MODELS, org_id=org_id)

    try:
        objective = ObjectiveFunction(
            scenario=scenario,
            model=model,
            space=space,
            physics_mode=params.physics_mode,
        )

        if params.optimizer == "random":
            # n_samples, not max_evals: the random baseline names its budget
            # differently, and passing the wrong keyword is a TypeError only at
            # run time - inside a worker, after the credits are spent.
            optimizer: Any = RandomSearchOptimizer(
                space=space,
                n_samples=params.max_evals,
                seed=params.seed,
                stop_on_first_falsification=False,
            )
        else:
            optimizer = CMAESOptimizer(
                space=space,
                max_evals=params.max_evals,
                seed=params.seed,
                # Spend the whole budget and report every distinct failure.
                # Stopping at the first one returns a single counter-example
                # and bills for the budget it did not use; it also hides the
                # failure *rate*, which is the real finding when most of the
                # space fails.
                stop_on_first_falsification=False,
            )

        return optimizer.run(objective)
    finally:
        _release(model)


def _release(model) -> None:
    """Close an out-of-process model, or leak a child process per search."""
    closer = getattr(model, "close", None)
    if callable(closer):
        try:
            closer()
        except Exception:  # noqa: BLE001 - cleanup must not mask the result
            logger.exception("Could not release model after search")


def _fail(search_id: int, params: _JobParams, exc: Exception) -> None:
    """Mark the job failed and refund what was charged.

    Refunds the recorded `credits_charged`, not a recomputed cost: the pricing
    formula can change between charge and refund, and the customer is owed what
    they actually paid.
    """
    with session_scope() as db:
        job = db.get(SearchJobRecord, search_id)
        if job is not None:
            job.status = "failed"
            job.error_message = f"{type(exc).__name__}: {exc}"
            job.completed_at = datetime.datetime.utcnow()

        if params.org_id and params.credits_charged:
            OrganisationRepository(db).add_credits(
                params.org_id, params.credits_charged
            )
            logger.info(
                "Refunded %d credits to org %s for failed search %s",
                params.credits_charged,
                params.org_id,
                search_id,
            )


def serialise(result) -> Dict[str, Any]:
    """Search result as plain JSON for storage and the API."""
    evaluations = [asdict(r) for r in result.all_evaluations]

    return {
        "optimizer_used": result.optimizer_used,
        "best_params": result.best_params,
        "best_fitness": float(result.best_fitness),
        "n_evals": result.n_evals,
        "converged": bool(result.converged),
        "falsification_found": bool(result.falsification_found),
        "falsification_params": result.falsification_params,
        # Every distinct way the model failed, worst first. One counter-example
        # proves it can fail; several show how many different ways, and two
        # from opposite corners of the space are two bugs rather than one.
        "falsifications": result.falsifications,
        "falsification_count": result.falsification_count,
        "distinct_failure_count": result.distinct_failure_count,
        # The rate matters on its own. When most of the space fails, a list of
        # eighty settings buries that; one number does not.
        "failure_rate": result.failure_rate,
        "all_evaluations": _trim(evaluations),
        "evaluations_truncated": len(evaluations) > MAX_STORED_EVALUATIONS,
    }


def _trim(evaluations: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Keep the history small enough to store and send, failures first.

    A dropped successful evaluation costs nothing: nobody debugs a model from
    the runs where nothing went wrong. A dropped *failure* would lose a
    counter-example the customer paid to find, so those are never dropped.
    """
    if len(evaluations) <= MAX_STORED_EVALUATIONS:
        return evaluations

    failures = [e for e in evaluations if e.get("collision_occurred")]
    remaining = MAX_STORED_EVALUATIONS - len(failures)
    if remaining <= 0:
        return failures[:MAX_STORED_EVALUATIONS]

    successes = [e for e in evaluations if not e.get("collision_occurred")]
    return failures + successes[:remaining]
