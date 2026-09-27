"""
The last two backend gaps in Phases 2 and 3.

`GET /api/compare/{id}/report.pdf` (2.4) — the document a safety reviewer is
handed. The interesting case is the machine without GTK, which is every Windows
developer and every slim container: the report falls back to HTML rather than
503ing, because the value is the content and a feature that only exists where
GTK happens to be installed is not a feature.

Auto-compare on resubmission (3.4) — nobody runs the vN-vs-vN−1 comparison by
hand on the day they ship, which is exactly the day it matters. What is pinned
here is that it does not fire when there is nothing to compare, that it cannot
fail an upload, and that it discloses what it charged: it spends credits the
customer did not explicitly ask to spend.
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

REPO = Path(__file__).resolve().parent.parent


# -- The auto-compare scenario list ---------------------------------------


def test_the_auto_compare_scenarios_exist():
    """These paths are never typed by a user, so a typo shows up as a
    comparison that silently fails in a worker after taking the credits. One
    of them was wrong when this was written — `VRU-001_pedestrian_crossing`
    against a file called `VRU-001_pedestrian_crosswalk`."""
    from arep.api.models_routes import AUTO_COMPARE_SCENARIOS

    for scenario in AUTO_COMPARE_SCENARIOS:
        assert (REPO / scenario).resolve().exists(), f"{scenario} does not exist"


def test_auto_compare_stays_small():
    """It fires on every resubmission without anyone asking. A full-library
    comparison would spend a customer's credits the moment they pushed."""
    from arep.api.compare import comparison_cost
    from arep.api.models_routes import AUTO_COMPARE_RUNS, AUTO_COMPARE_SCENARIOS

    cost = comparison_cost(AUTO_COMPARE_RUNS, len(AUTO_COMPARE_SCENARIOS))
    assert cost <= 40, f"an unrequested comparison costing {cost} credits is too much"


def test_auto_compare_does_nothing_without_an_org():
    """A local upload has no tenancy to scope versions by and no credits."""
    from arep.api.models_routes import maybe_auto_compare

    assert maybe_auto_compare(None, None, "anything", "some-id") is None


# -- The report endpoint ---------------------------------------------------


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
    from tests.conftest import verify_email_for

    email = "reports@example.com"
    client.post(
        "/api/auth/signup",
        json={
            "email": email,
            "username": "reporter",
            "password": "password123",
            "org_name": "report org",
            "org_slug": "reportorg",
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


REPORT = {
    "model_a_id": "EmergencyBrake",
    "model_a_name": "EmergencyBrake",
    "model_b_id": "ConstantAction",
    "model_b_name": "ConstantAction",
    "overall_winner": "a",
    "recommendation": "Do not deploy candidate",
    "regressions": [],
    "scenario_comparisons": [],
}


def _completed_comparison(org_id, status="completed", report=REPORT):
    from arep.database.connection import session_scope
    from arep.database.models import ComparisonJobRecord

    with session_scope() as db:
        job = ComparisonJobRecord(
            org_id=org_id,
            user_id=None,
            model_a_id="EmergencyBrake",
            model_b_id="ConstantAction",
            scenario_ids="../scenarios/lon/LON-003_emergency_stop.yaml",
            runs_per_scenario=5,
            seed=42,
            credits_charged=10,
            status=status,
            report_json=report,
        )
        db.add(job)
        db.flush()
        return job.id


def test_a_report_is_served_in_whichever_format_the_host_can_produce(client, account):
    """PDF where WeasyPrint's native libraries are present, HTML where they are
    not — not a 503. The report's value is the executive summary, the score
    tables and the methodology section, none of which depend on GTK."""
    headers, org_id = account
    comparison_id = _completed_comparison(org_id)

    r = client.get(f"/api/compare/{comparison_id}/report.pdf", headers=headers)

    assert r.status_code == 200, r.text
    assert r.headers["X-ORION-Report-Format"] in ("pdf", "html")
    assert r.content, "an empty report is worse than an error"


def test_the_response_says_which_format_it_actually_sent(client, account):
    """A client offering a "Download PDF" button needs to know it is about to
    hand over HTML."""
    headers, org_id = account
    comparison_id = _completed_comparison(org_id)

    r = client.get(f"/api/compare/{comparison_id}/report.pdf", headers=headers)
    fmt = r.headers["X-ORION-Report-Format"]

    assert fmt in r.headers["Content-Disposition"], (
        "Content-Disposition names a file extension that contradicts "
        "X-ORION-Report-Format"
    )
    expected = "application/pdf" if fmt == "pdf" else "text/html"
    assert r.headers["content-type"].startswith(expected)


def test_the_report_contains_both_model_names(client, account):
    """A report that does not say what was compared is not a report."""
    headers, org_id = account
    comparison_id = _completed_comparison(org_id)

    r = client.get(f"/api/compare/{comparison_id}/report.pdf", headers=headers)
    if r.headers["X-ORION-Report-Format"] != "html":
        pytest.skip("PDF bytes are not searchable as text")

    body = r.content.decode("utf-8")
    assert "EmergencyBrake" in body
    assert "ConstantAction" in body


def test_an_unfinished_comparison_has_no_report(client, account):
    """409, not an empty PDF. A blank report reads like a clean comparison."""
    headers, org_id = account
    comparison_id = _completed_comparison(org_id, status="running")

    r = client.get(f"/api/compare/{comparison_id}/report.pdf", headers=headers)
    assert r.status_code == 409
    assert "running" in r.json()["detail"]


def test_a_completed_comparison_with_no_report_is_an_error_not_a_blank_page(
    client, account
):
    headers, org_id = account
    comparison_id = _completed_comparison(org_id, report=None)

    r = client.get(f"/api/compare/{comparison_id}/report.pdf", headers=headers)
    assert r.status_code == 500


def test_another_orgs_report_is_invisible(client, account):
    headers, _ = account
    comparison_id = _completed_comparison("someone-else")

    r = client.get(f"/api/compare/{comparison_id}/report.pdf", headers=headers)
    assert r.status_code == 404


# -- Webhooks on completion ------------------------------------------------


def test_a_regression_fires_its_own_event_not_a_flag_on_another(monkeypatch):
    """A CI pipeline subscribes to the event it acts on. Making it filter a
    `comparison.completed` payload to decide whether to block a deploy is how
    a regression ships past a webhook that fired correctly."""
    from arep.analysis import comparison_runner

    import arep.api.webhooks as webhooks_module

    sent = []

    monkeypatch.setattr(
        webhooks_module,
        "dispatch",
        lambda event, org_id, payload: sent.append(event) or 1,
    )

    class _Delta:
        metric = "safety_score"
        value_a = 0.9
        value_b = 0.7
        delta = -0.2
        threshold_used = 0.1

    class _Report:
        overall_winner = "a"
        recommendation = "Do not deploy"
        regressions = [_Delta()]

    params = comparison_runner._JobParams(
        model_a_id="a",
        model_b_id="b",
        scenario_ids=["s"],
        runs_per_scenario=5,
        seed=42,
        org_id="org-1",
        credits_charged=10,
    )
    comparison_runner._notify(1, params, _Report())

    assert "comparison.completed" in sent
    assert "regression.detected" in sent


def test_no_regression_means_no_regression_event(monkeypatch):
    """Crying wolf on every comparison is how the event gets unsubscribed."""
    from arep.analysis import comparison_runner
    import arep.api.webhooks as webhooks_module

    sent = []
    monkeypatch.setattr(
        webhooks_module,
        "dispatch",
        lambda event, org_id, payload: sent.append(event) or 1,
    )

    class _Report:
        overall_winner = "b"
        recommendation = "Ship it"
        regressions = []

    params = comparison_runner._JobParams(
        model_a_id="a",
        model_b_id="b",
        scenario_ids=["s"],
        runs_per_scenario=5,
        seed=42,
        org_id="org-1",
        credits_charged=10,
    )
    comparison_runner._notify(1, params, _Report())

    assert sent == ["comparison.completed"]


def test_a_broken_endpoint_does_not_fail_the_comparison(monkeypatch):
    """The comparison is finished and stored. A customer's dead webhook must
    not turn a successful job into a failed one — and a failed one refunds."""
    from arep.analysis import comparison_runner
    import arep.api.webhooks as webhooks_module

    def explode(*args, **kwargs):
        raise RuntimeError("receiver is on fire")

    monkeypatch.setattr(webhooks_module, "dispatch", explode)

    class _Report:
        overall_winner = "a"
        recommendation = "x"
        regressions = []

    params = comparison_runner._JobParams(
        model_a_id="a",
        model_b_id="b",
        scenario_ids=["s"],
        runs_per_scenario=5,
        seed=42,
        org_id="org-1",
        credits_charged=10,
    )

    # Must return, not raise.
    comparison_runner._notify(1, params, _Report())


def test_every_event_the_code_dispatches_is_a_declared_event():
    """A typo'd event name is delivered to nobody and reported as success."""
    import re

    from arep.api.webhooks import VALID_EVENTS

    dispatched = set()
    for path in (REPO / "arep").rglob("*.py"):
        for match in re.finditer(r'dispatch\(\s*"([a-z_.]+)"', path.read_text("utf-8")):
            dispatched.add(match.group(1))

    assert dispatched, "no dispatch call sites found — has the helper been renamed?"
    assert dispatched <= VALID_EVENTS, (
        f"dispatched but not declared in VALID_EVENTS: "
        f"{sorted(dispatched - VALID_EVENTS)}"
    )


# -- The report template against real producer output ----------------------
#
# The comparison report could not render *any* comparison that found a
# regression, and could not render the scenario table at all. Both were missing
# fields, and both survived because every existing test fed the template a
# hand-built dict that happened to carry the right keys. So this one builds the
# report the way the product does and serialises it the way the API does.


def _real_report():
    from arep.analysis.regression_detector import (
        ComparisonReport,
        MetricDelta,
        RegressionDetector,
        ScenarioComparison,
    )

    scenario = ScenarioComparison(
        scenario_id="LON-003_emergency_stop",
        model_a_name="EmergencyBrake",
        model_b_name="ConstantAction",
        runs_per_model=5,
        baseline_composite=0.91,
        candidate_composite=0.42,
        delta=-0.49,
    )
    scenario.metric_deltas = [
        MetricDelta(
            metric="composite_score",
            value_a=0.91,
            value_b=0.42,
            delta=-0.49,
            is_regression=True,
            threshold_used=0.05,
        )
    ]
    scenario.has_regression = True
    scenario.winner = "a"

    report = ComparisonReport(
        model_a_id="EmergencyBrake",
        model_a_name="EmergencyBrake",
        model_b_id="ConstantAction",
        model_b_name="ConstantAction",
        scenario_comparisons=[scenario],
    )
    # _finalise is what attaches scenario_id to each regression. Calling it
    # rather than hand-filling `regressions` is the whole point: that step is
    # where the field the template needs gets set.
    return RegressionDetector()._finalise(report)


def test_a_report_with_regressions_renders():
    """The case the report exists for, and the one that crashed."""
    from arep.analysis.comparison_runner import _serialise
    from arep.reporting.pdf_generator import PDFGenerator

    payload = _serialise(_real_report())
    assert payload["regressions"], "the fixture has no regression to render"

    html = PDFGenerator(require_pdf=False).render_html(
        "comparison_report.html", {"comparison": payload}
    )

    assert "REGRESSION DETECTED" in html
    assert "LON-003_emergency_stop" in html
    assert "composite_score" in html


def test_a_regression_carries_the_scenario_it_came_from():
    """`regressions` is flattened out of the per-scenario comparisons. Without
    the id it is a list of numbers nobody can act on — and the template asks
    for it by name, under StrictUndefined."""
    report = _real_report()

    assert report.regressions
    for delta in report.regressions:
        assert delta.scenario_id == "LON-003_emergency_stop"


def test_the_scenario_table_has_the_composites_it_renders():
    """`asdict` serialises fields and drops properties, so these have to be
    real fields or they vanish between the detector and the template."""
    from arep.analysis.comparison_runner import _serialise

    payload = _serialise(_real_report())
    scenario = payload["scenario_comparisons"][0]

    for key in ("baseline_composite", "candidate_composite", "delta"):
        assert key in scenario, f"{key} is missing from the serialised comparison"
