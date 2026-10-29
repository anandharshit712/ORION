"""
Phase 4.5 standards alignment: scenario requirement metadata, the
traceability matrix and the ODD statement.

The metadata is human documentation the engine never reads, which is exactly
why it needs a test: nothing else would notice a scenario that lost its
requirement, or two scenarios that quietly became one.
"""

from __future__ import annotations

import csv
import json
import re
from collections import Counter
from pathlib import Path

import pytest
import yaml

from arep.cli import standards
from arep.cli.run_suite import SUITES
from arep.scenario.parser import ScenarioParser

REPO = Path(__file__).resolve().parent.parent.parent
LIBRARY = sorted((REPO / "scenarios").glob("*/*.yaml"))
BASIC = sorted(
    (Path(__file__).resolve().parent.parent / "scenarios" / "basic").glob("*.yaml")
)


def _meta(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))["scenario"]


# ── Metadata ─────────────────────────────────────────────────────────────


@pytest.mark.parametrize("path", LIBRARY, ids=lambda p: p.stem)
def test_every_production_scenario_states_requirement_and_hazard(path):
    meta = _meta(path)
    requirement = " ".join(str(meta.get("behavioral_requirement") or "").split())
    hazard = " ".join(str(meta.get("hazard") or "").split())
    assert requirement.startswith("The ego"), requirement
    # ISO 21448 vocabulary, in a fixed shape so the matrix reads uniformly.
    assert "Triggering condition:" in hazard and "Hazardous event:" in hazard, hazard
    # A folded YAML line that ends on a hyphen rejoins as "time-to- collision".
    for text in (requirement, hazard, str(meta.get("verification_gap") or "")):
        assert not re.search(r"\w- \w", " ".join(text.split())), text


def test_no_two_scenarios_share_a_behavioral_requirement():
    """One scenario = one behavioural requirement (ARCHITECTURE.md §1.1)."""
    requirements = Counter(
        " ".join(str(_meta(p)["behavioral_requirement"]).split()).lower()
        for p in LIBRARY
    )
    duplicates = [r for r, n in requirements.items() if n > 1]
    assert not duplicates, duplicates


def test_the_parser_carries_the_metadata():
    scenario, _ = ScenarioParser().parse_file(
        REPO / "scenarios" / "lon" / "LON-003_emergency_stop.yaml"
    )
    assert scenario.behavioral_requirement.startswith("The ego must stop")
    assert "Hazardous event:" in scenario.hazard
    assert "\n" not in scenario.hazard  # YAML folding undone
    assert scenario.to_dict()["scenario"]["hazard"] == scenario.hazard


@pytest.mark.parametrize("path", BASIC, ids=lambda p: p.stem)
def test_v1_fixtures_still_load_without_the_fields(path):
    scenario, _ = ScenarioParser().parse_file(path)
    assert scenario.behavioral_requirement == ""
    assert scenario.hazard == ""
    assert scenario.verification_gap == ""


# ── Traceability matrix ──────────────────────────────────────────────────


@pytest.fixture(scope="module")
def full_suite():
    return standards.load_scenarios("full", REPO)


def test_without_a_report_every_result_is_not_run(full_suite):
    rows = standards.traceability_rows(full_suite)
    assert len(rows) == 60
    assert {r["result"] for r in rows} == {standards.NOT_RUN}


def test_results_come_from_the_report_and_nowhere_else(full_suite):
    report = {
        "model": "m",
        "seed": 7,
        "scenarios": [
            {
                "scenario": "LON-003_emergency_stop",
                "passed": True,
                "runs": 2,
                "collision_rate": 0.0,
                "off_road_rate": 0.0,
                "composite_mean": 0.9,
            },
            {
                "scenario": "LAT-003_oncoming_encroachment",
                "passed": False,
                "runs": 2,
                "collision_rate": 1.0,
                "off_road_rate": 0.0,
                "composite_mean": 0.4,
            },
        ],
        "unloadable": [{"scenario": "EMG-004_black_ice_friction_loss", "error": "x"}],
    }
    rows = {r["scenario"]: r for r in standards.traceability_rows(full_suite, report)}
    assert rows["LON-003"]["result"] == "PASS"
    assert rows["LON-003"]["model"] == "m"
    assert rows["LAT-003"]["result"] == "FAIL"
    assert rows["EMG-004"]["result"].startswith("NOT RUN")
    assert rows["LON-001"]["result"] == standards.NOT_RUN
    assert rows["LON-001"]["model"] == ""


@pytest.mark.parametrize("suite", sorted(SUITES))
def test_matrix_exports_for_every_suite(suite, tmp_path):
    assert (
        standards.main(
            ["traceability", "--suite", suite, "--output-dir", str(tmp_path)]
        )
        == 0
    )
    with (tmp_path / f"traceability_{suite}.csv").open(encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    assert rows and all(r["behavioral_requirement"] and r["hazard"] for r in rows)
    html = (tmp_path / f"traceability_{suite}.html").read_text(encoding="utf-8")
    assert rows[0]["scenario"] in html and "not run" in html


def test_a_named_report_that_is_missing_is_an_error(tmp_path):
    code = standards.main(
        [
            "traceability",
            "--suite",
            "core",
            "--report",
            str(tmp_path / "nope.json"),
            "--output-dir",
            str(tmp_path),
        ]
    )
    assert code == standards.EXIT_ERROR


# ── ODD statement ────────────────────────────────────────────────────────


def test_odd_is_derived_from_the_yaml(full_suite):
    odd = standards.odd_statement(full_suite, "full")
    assert odd["executable"] == odd["scenarios"] - len(odd["refused_at_load"])
    # Ranges come from the files: recompute one endpoint independently.
    fastest = max(
        float(s["data"]["parameterization"]["ego_velocity"]["max"])
        for s in full_suite
        if not s["refused"]
    )
    assert odd["speeds"]["ego_initial_speed"]["max_ms"] == pytest.approx(
        fastest, abs=0.01
    )
    assert odd["actors"]["types"]["pedestrian"] > 0
    assert "four_way_intersection" in odd["road"]["templates"]


def test_odd_names_what_is_not_covered(full_suite):
    odd = standards.odd_statement(full_suite, "full")
    topics = " ".join(item["topic"] for item in odd["not_covered"]).lower()
    for absent in ("weather", "sensors", "routes", "progress", "traffic-rule"):
        assert absent in topics
    assert [r["scenario"] for r in odd["refused_at_load"]] == ["EMG-004"]
    # A refused scenario exercises nothing, so it must not widen coverage.
    assert "rural" in odd["road"]["types"]  # LAT-007 still loads
    assert odd["weather_labels_declared"].get("snow") == 1


def test_odd_cli_writes_json_and_html(tmp_path):
    assert (
        standards.main(["odd", "--suite", "core", "--output-dir", str(tmp_path)]) == 0
    )
    odd = json.loads((tmp_path / "odd_core.json").read_text(encoding="utf-8"))
    assert odd["scenarios"] == 20
    html = (tmp_path / "odd_core.html").read_text(encoding="utf-8")
    assert "Not covered" in html


def test_report_footer_states_the_weights_the_code_uses():
    from arep.evaluation.composite import CompositeEvaluator
    from arep.reporting.pdf_generator import PDFGenerator

    html = PDFGenerator(require_pdf=False).render_html(
        "odd.html",
        {
            "odd": standards.odd_statement(
                standards.load_scenarios("LON-001", REPO), "x"
            )
        },
    )
    assert f"Safety×{CompositeEvaluator.SAFETY_WEIGHT:.2f}" in html
