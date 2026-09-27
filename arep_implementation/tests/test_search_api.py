"""
Adversarial search over HTTP (Phase 2.3).

The optimiser itself is covered by `test_adversarial_search.py`. What is pinned
here is the part that costs money and the part that could report a false pass:

  - credits are charged up front and refunded when the search fails, because a
    customer charged for work that never ran will notice, and a customer never
    charged lets anyone queue unlimited compute;
  - a scenario with no parameterization block is refused rather than searched,
    because a search over zero dimensions returns "no failure found" about a
    model whose scenario was never varied — which reads exactly like a real
    pass;
  - one org cannot see another's searches.
"""

from __future__ import annotations

import os
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests.conftest import verify_email_for  # noqa: E402

pytest.importorskip("cma", reason="needs arep[search]")

PARAMETERISED = "../scenarios/lon/LON-003_emergency_stop.yaml"


@pytest.fixture(scope="module")
def client():
    db_fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(db_fd)
    os.environ["ORION_DATABASE_URL"] = f"sqlite:///{db_path}"

    from arep.database import connection as conn_mod

    conn_mod._engine = None
    conn_mod._SessionFactory = None
    conn_mod.init_database(url=f"sqlite:///{db_path}")

    from fastapi.testclient import TestClient

    from arep.api.app import create_app

    with TestClient(create_app()) as c:
        yield c

    conn_mod._engine = None
    conn_mod._SessionFactory = None
    try:
        os.unlink(db_path)
    except OSError:
        pass


@pytest.fixture(scope="module")
def account(client):
    """One shared account — signup is rate limited to 3/hour/IP."""
    email = "search@example.com"
    client.post(
        "/api/auth/signup",
        json={
            "email": email,
            "username": "searcher",
            "password": "password123",
            "org_name": "search org",
            "org_slug": "searchorg",
        },
    )
    verify_email_for(email)
    login = client.post(
        "/api/auth/login", json={"identifier": email, "password": "password123"}
    )
    assert login.status_code == 200, login.text
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    org_id = client.get("/api/orgs/me", headers=headers).json()["id"]
    return headers, org_id


@pytest.fixture(autouse=True)
def dont_actually_search(monkeypatch):
    """Stop `_dispatch` running a real search inside the request.

    With no broker the endpoint falls back to running inline, and a real search
    is minutes of simulation. The runner is exercised directly in the tests
    that care about it.
    """
    from arep.api import search as search_api

    monkeypatch.setattr(search_api, "_dispatch", lambda search_id: None)


def _credits(client, headers) -> int:
    return client.get("/api/orgs/me", headers=headers).json()["run_credits"]


def _start(client, headers, **overrides):
    body = {
        "scenario_id": PARAMETERISED,
        "model_id": "EmergencyBrake",
        "max_evals": 20,
    }
    body.update(overrides)
    return client.post("/api/search/", headers=headers, json=body)


# -- Pricing ---------------------------------------------------------------


def test_a_search_costs_one_credit_per_evaluation(client, account):
    """`max_evals` credits, the roadmap's formula. Honest only because the
    search spends its whole budget rather than stopping at the first
    collision — otherwise this bills 200 and runs one."""
    headers, _ = account

    before = _credits(client, headers)
    r = _start(client, headers, max_evals=20)

    assert r.status_code == 202, r.text
    body = r.json()
    assert body["credits_charged"] == 20
    assert body["max_evals"] == 20
    assert _credits(client, headers) == before - 20
    assert body["credits_remaining"] == before - 20


def test_credits_are_taken_before_the_work_is_queued(client, account):
    """Charging on completion lets a customer queue unlimited work."""
    headers, _ = account

    before = _credits(client, headers)
    r = _start(client, headers, max_evals=15)

    assert r.json()["status"] == "queued"
    assert _credits(client, headers) == before - 15


def test_omitting_the_budget_uses_the_recommendation_for_the_dimensionality(
    client, account
):
    """A flat floor overcharges a one-dimensional scenario fifteenfold for a
    search that converged at evaluation ten."""
    from arep.search.optimizer import recommended_evals

    headers, _ = account

    r = _start(client, headers, max_evals=None)
    assert r.status_code == 202, r.text

    body = r.json()
    assert body["n_dims"] > 0
    assert body["recommended_evals"] == recommended_evals(body["n_dims"])
    assert body["max_evals"] == body["recommended_evals"]
    assert body["credits_charged"] == body["recommended_evals"]


def test_an_unaffordable_search_is_refused_with_the_price_explained(client, account):
    """402, and the message says what it would have cost and what the
    recommended budget is — a bare "insufficient credits" makes the customer
    guess."""
    headers, _ = account

    r = _start(client, headers, max_evals=2000)

    assert r.status_code == 402
    detail = r.json()["detail"]
    assert "2000" in detail
    assert "credits" in detail.lower()


def test_a_refused_search_takes_no_credits(client, account):
    """The failure mode that costs a customer money for nothing."""
    headers, _ = account

    before = _credits(client, headers)
    assert _start(client, headers, max_evals=2000).status_code == 402
    assert _credits(client, headers) == before


# -- Refusing what cannot be searched --------------------------------------


def test_a_scenario_without_parameters_is_refused_not_searched(client, account):
    """The dangerous case. Zero dimensions means nothing varies, so the search
    reports "no failure found" about a model that faced one fixed setting —
    indistinguishable from a real pass over 200."""
    headers, _ = account

    # A real v1 fixture, which genuinely has no parameterization block.
    r = _start(
        client, headers, scenario_id="scenarios/basic/straight_road_lead_vehicle.yaml"
    )

    assert r.status_code == 400, r.text
    assert "parameterization" in r.json()["detail"]


def test_a_missing_scenario_is_a_404(client, account):
    headers, _ = account
    r = _start(client, headers, scenario_id="scenarios/nope/NOPE-001.yaml")
    assert r.status_code == 404


def test_an_unknown_optimizer_is_rejected_by_validation(client, account):
    headers, _ = account
    assert _start(client, headers, optimizer="simulated_annealing").status_code == 422


def test_a_budget_too_small_to_mean_anything_is_rejected(client, account):
    """Below ~10 evaluations per dimension CMA-ES loses to random sampling, so
    a 2-evaluation search would sell a result that says nothing."""
    headers, _ = account
    assert _start(client, headers, max_evals=2).status_code == 422


# -- Status and result -----------------------------------------------------


def test_status_and_result_are_separate_endpoints(client, account):
    """The evaluation history is large and a progress poll must not carry it."""
    headers, _ = account
    search_id = _start(client, headers).json()["search_id"]

    status = client.get(f"/api/search/{search_id}/status", headers=headers)
    assert status.status_code == 200
    assert "result" not in status.json()

    result = client.get(f"/api/search/{search_id}/result", headers=headers)
    assert result.status_code == 200
    assert "result" in result.json()


def test_falsification_found_is_null_until_the_search_finishes(client, account):
    """Not false. Before the search runs, "no failure found" and "not looked
    yet" are different answers, and reporting the first says a model is safe."""
    headers, _ = account
    search_id = _start(client, headers).json()["search_id"]

    body = client.get(f"/api/search/{search_id}/status", headers=headers).json()
    assert body["status"] == "queued"
    assert body["falsification_found"] is None


def test_searches_are_listed_newest_first(client, account):
    headers, _ = account
    first = _start(client, headers).json()["search_id"]
    second = _start(client, headers).json()["search_id"]

    listed = client.get("/api/search/", headers=headers).json()
    ids = [s["search_id"] for s in listed]
    assert ids.index(second) < ids.index(first)


# -- Tenancy ---------------------------------------------------------------


def test_another_orgs_search_is_invisible(client, account):
    headers, _ = account
    search_id = _start(client, headers).json()["search_id"]

    from arep.database.connection import session_scope
    from arep.database.models import SearchJobRecord

    with session_scope() as db:
        db.get(SearchJobRecord, search_id).org_id = "someone-else"

    for path in (f"/api/search/{search_id}/status", f"/api/search/{search_id}/result"):
        assert client.get(path, headers=headers).status_code == 404


def test_search_endpoints_require_auth(client):
    from fastapi.testclient import TestClient

    with TestClient(client.app) as anonymous:
        assert anonymous.get("/api/search/").status_code == 401
        assert anonymous.post("/api/search/", json={}).status_code == 401


# -- The runner ------------------------------------------------------------


def test_a_failed_search_refunds_exactly_what_was_charged(client, account, monkeypatch):
    """The customer paid before the work was queued. If it never ran, they are
    owed the money back — and owed what they paid, not what the same search
    would cost under a later pricing formula."""
    from arep.analysis import search_runner

    headers, _ = account
    enqueued = _start(client, headers, max_evals=20).json()
    search_id = enqueued["search_id"]
    after_charge = _credits(client, headers)

    def explode(params, org_id=None):
        raise RuntimeError("optimizer exploded")

    monkeypatch.setattr(search_runner, "_run", explode)
    search_runner.execute_search(search_id)

    assert _credits(client, headers) == after_charge + 20

    body = client.get(f"/api/search/{search_id}/status", headers=headers).json()
    assert body["status"] == "failed"
    assert "optimizer exploded" in body["error_message"]


def test_a_redelivered_task_does_not_run_the_search_twice(client, account, monkeypatch):
    """`acks_late` means Celery can deliver the same job again. Re-running a
    search spends the whole budget a second time."""
    from arep.analysis import search_runner

    headers, _ = account
    search_id = _start(client, headers, max_evals=20).json()["search_id"]

    calls = []

    class _Result:
        n_evals = 20
        best_fitness = 1.0
        falsification_found = False
        falsification_params = None
        falsifications: list = []
        falsification_count = 0
        distinct_failure_count = 0
        failure_rate = 0.0
        all_evaluations: list = []
        optimizer_used = "cma-es"
        converged = True
        best_params: dict = {}

    def once(params, org_id=None):
        calls.append(1)
        return _Result()

    monkeypatch.setattr(search_runner, "_run", once)

    search_runner.execute_search(search_id)
    search_runner.execute_search(search_id)

    assert len(calls) == 1, "a redelivery re-ran the search and re-spent the budget"


def test_the_history_keeps_every_failure_when_it_has_to_be_trimmed():
    """Dropping a successful evaluation costs nothing. Dropping a failure loses
    a counter-example the customer paid to find."""
    from arep.analysis.search_runner import MAX_STORED_EVALUATIONS, _trim

    failures = [{"collision_occurred": True, "i": i} for i in range(5)]
    successes = [
        {"collision_occurred": False, "i": i} for i in range(MAX_STORED_EVALUATIONS * 2)
    ]

    kept = _trim(successes[:100] + failures + successes[100:])

    assert len(kept) == MAX_STORED_EVALUATIONS
    assert all(f in kept for f in failures), "a failure was dropped"


def test_a_short_history_is_kept_whole():
    from arep.analysis.search_runner import _trim

    evaluations = [{"collision_occurred": False, "i": i} for i in range(10)]
    assert _trim(evaluations) == evaluations
