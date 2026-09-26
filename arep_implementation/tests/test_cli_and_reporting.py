"""
CLI suite runner and PDF reporting tests (Phases 3 and 2.4).

The CLI is the CI-facing surface, so its exit codes are the contract: 0 passed,
1 the model is worse than the threshold, 2 ORION could not answer. Conflating
1 and 2 is the failure that matters — a broken harness reported as a failing
model sends someone debugging their driver instead of their pipeline.

The reporting tests assert HTML content rather than PDF bytes. Every content
bug lives in the template — a missing figure, a mislabelled column — while the
PDF step is one library call. WeasyPrint also cannot load its GTK native
libraries on Windows at all, so a PDF-only test would simply not run here.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from arep.cli.run_suite import (  # noqa: E402
    COLLISION_RATE_LIMIT,
    EXIT_ERROR,
    EXIT_FAIL,
    EXIT_PASS,
    find_regressions,
    load_baseline,
    load_model,
    main,
    resolve_scenarios,
    write_report,
)
from arep.reporting.pdf_generator import PDFGenerator  # noqa: E402

REPO = Path(__file__).resolve().parent.parent.parent

BATCH = {
    "scenario_name": "LON-003 Emergency Stop",
    "model_name": "EmergencyBrake",
    "num_runs": 100,
    "master_seed": 42,
    "physics_mode": "kinematic",
    "aggregated": {
        "composite_mean": 0.8912,
        "composite_std": 0.0241,
        "pass_rate": 0.99,
        "safety_mean": 0.95,
        "compliance_mean": 0.88,
        "stability_mean": 0.82,
        "reactivity_mean": 0.90,
    },
}


# -- Scenario selection ---------------------------------------------------


def test_all_resolves_the_whole_library():
    paths = resolve_scenarios("all", REPO)
    assert len(paths) >= 18
    assert all(p.suffix == ".yaml" for p in paths)


def test_a_category_resolves_to_that_category_only():
    paths = resolve_scenarios("LON", REPO)
    assert paths
    assert all(p.name.startswith("LON-") for p in paths)


def test_category_matching_is_case_insensitive():
    assert resolve_scenarios("lon", REPO) == resolve_scenarios("LON", REPO)


def test_selection_is_ordered():
    """A CI report whose row order changes between machines is not diffable."""
    assert resolve_scenarios("all", REPO) == sorted(resolve_scenarios("all", REPO))


def test_a_scenario_id_resolves_to_one_file():
    paths = resolve_scenarios("LON-003", REPO)
    assert len(paths) == 1
    assert "LON-003" in paths[0].name


def test_an_unknown_selector_raises_rather_than_running_nothing():
    """Exiting 0 because zero scenarios matched is the worst CI outcome
    available: a green build that tested nothing."""
    with pytest.raises(FileNotFoundError, match="Unknown scenario selector"):
        resolve_scenarios("NOPE-999", REPO)


# -- Model loading --------------------------------------------------------


def test_a_builtin_name_loads():
    model = load_model("emergency_brake")
    assert model is not None
    assert hasattr(model, "predict")


def test_an_import_path_loads():
    """What makes this usable in CI: a customer points it at their own class."""
    model = load_model("arep.models.examples.example_models.EmergencyBrakeModel")
    assert hasattr(model, "predict")


def test_an_unknown_model_names_the_alternatives():
    with pytest.raises(ValueError) as excinfo:
        load_model("not_a_model")
    assert "emergency_brake" in str(excinfo.value)


def test_an_import_path_that_does_not_exist_raises_cleanly():
    with pytest.raises(ValueError, match="Could not load model"):
        load_model("arep.models.nope.NoSuchModel")


# -- Exit codes -----------------------------------------------------------


def test_a_passing_model_exits_zero(tmp_path):
    code = main(
        [
            "--scenarios",
            "LON-003",
            "--model",
            "emergency_brake",
            "--runs-per-scenario",
            "2",
            "--output-dir",
            str(tmp_path),
        ]
    )
    assert code == EXIT_PASS


def test_a_crashing_model_exits_one(tmp_path):
    code = main(
        [
            "--scenarios",
            "LON-004",
            "--model",
            "constant",
            "--runs-per-scenario",
            "2",
            "--output-dir",
            str(tmp_path),
        ]
    )
    assert code == EXIT_FAIL


def test_a_bad_model_exits_two_not_one(tmp_path):
    """The distinction that matters: a broken harness is not a failing model."""
    code = main(
        [
            "--scenarios",
            "LON-003",
            "--model",
            "not_a_model",
            "--output-dir",
            str(tmp_path),
        ]
    )
    assert code == EXIT_ERROR


def test_a_bad_scenario_selector_exits_two(tmp_path):
    code = main(
        [
            "--scenarios",
            "NOPE-999",
            "--model",
            "emergency_brake",
            "--output-dir",
            str(tmp_path),
        ]
    )
    assert code == EXIT_ERROR


def test_the_threshold_is_honoured(tmp_path):
    """Passing every scenario is not always required; the threshold decides."""
    lenient = main(
        [
            "--scenarios",
            "LON-004",
            "--model",
            "constant",
            "--runs-per-scenario",
            "2",
            "--pass-threshold",
            "0.0",
            "--output-dir",
            str(tmp_path),
        ]
    )
    assert lenient == EXIT_PASS


# -- The report -----------------------------------------------------------


def test_the_json_report_is_written_and_parseable(tmp_path):
    main(
        [
            "--scenarios",
            "LON-003",
            "--model",
            "emergency_brake",
            "--runs-per-scenario",
            "2",
            "--output-dir",
            str(tmp_path),
            "--format",
            "json",
        ]
    )
    report_path = tmp_path / "orion_suite_report.json"
    assert report_path.exists()

    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["scenario_count"] == 1
    assert report["collision_rate_limit"] == COLLISION_RATE_LIMIT
    assert report["scenarios"][0]["scenario"].startswith("LON-003")


def test_a_scenario_passes_on_collision_rate_not_composite(tmp_path):
    """A model can be uncomfortable and safe; it cannot be comfortable and
    crashing. The verdict must follow the collision rate."""
    report = {
        "scenarios": [
            {
                "scenario": "s",
                "composite_mean": 0.2,
                "collision_rate": 0.0,
                "passed": True,
            },
        ],
        "model": "m",
        "seed": 1,
        "runs_per_scenario": 1,
        "scenario_count": 1,
        "scenarios_passed": 1,
        "pass_rate": 1.0,
    }
    path = write_report(report, tmp_path, "html")
    assert "PASS" in path.read_text(encoding="utf-8")


def test_the_html_report_lists_every_scenario(tmp_path):
    report = {
        "scenarios": [
            {
                "scenario": "alpha",
                "composite_mean": 0.9,
                "collision_rate": 0.0,
                "passed": True,
            },
            {
                "scenario": "beta",
                "composite_mean": 0.4,
                "collision_rate": 0.5,
                "passed": False,
            },
        ],
        "model": "m",
        "seed": 1,
        "runs_per_scenario": 3,
        "scenario_count": 2,
        "scenarios_passed": 1,
        "pass_rate": 0.5,
    }
    html = write_report(report, tmp_path, "html").read_text(encoding="utf-8")
    assert "alpha" in html and "beta" in html
    assert "PASS" in html and "FAIL" in html


# -- PDF reporting --------------------------------------------------------


def test_the_batch_report_renders_its_numbers():
    html = PDFGenerator(require_pdf=False).render_html(
        "batch_report.html",
        {"batch": BATCH},
    )
    assert "LON-003" in html
    assert "EmergencyBrake" in html
    assert "0.89" in html, "the composite mean must actually appear"


def test_the_verdict_follows_the_pass_rate():
    generator = PDFGenerator(require_pdf=False)

    good = dict(BATCH, aggregated=dict(BATCH["aggregated"], pass_rate=1.0))
    bad = dict(BATCH, aggregated=dict(BATCH["aggregated"], pass_rate=0.4))

    assert "PASS" in generator.render_html("batch_report.html", {"batch": good})
    assert "FAIL" in generator.render_html("batch_report.html", {"batch": bad})


def test_a_missing_field_fails_loudly_rather_than_rendering_blank():
    """A safety report with a silently empty number is worse than one that
    does not build."""
    from jinja2 import UndefinedError

    incomplete = {k: v for k, v in BATCH.items() if k != "model_name"}
    with pytest.raises(UndefinedError):
        PDFGenerator(require_pdf=False).render_html(
            "batch_report.html",
            {"batch": incomplete},
        )


def test_html_rendering_needs_no_pdf_toolchain():
    """WeasyPrint cannot load its GTK libraries on Windows; the content path
    must not depend on them."""
    generator = PDFGenerator(require_pdf=False)
    assert generator.render_html("batch_report.html", {"batch": BATCH})


def test_pdf_generation_explains_a_missing_native_library():
    """pip install does not fix a missing GTK runtime, so the message must not
    suggest it."""
    try:
        PDFGenerator(require_pdf=True)
    except ImportError as exc:
        assert "GTK" in str(exc) or "weasyprint is not installed" in str(exc)
    else:
        # The toolchain is present (Linux CI): rendering must then work.
        pdf = PDFGenerator().render_batch_report(BATCH)
        assert pdf.startswith(b"%PDF")


# -- Regression against a baseline ----------------------------------------
#
# The suite exits on the collision limit, which is an absolute bar. A model can
# clear it while getting steadily worse, and a CI integration that only watches
# the bar never says so until the day it drops through.


def _report(**scenario):
    base = {
        "scenario": "LON-003",
        "composite_mean": 0.90,
        "safety_mean": 0.95,
        "collision_rate": 0.0,
    }
    base.update(scenario)
    return {"scenarios": [base]}


def test_an_unchanged_model_reports_no_regression():
    assert find_regressions(_report(), _report()) == []


def test_a_small_drop_is_noise_not_a_regression():
    """Below the threshold nothing is reported. A check that fires on every
    run of a stochastic suite gets switched off within a week."""
    assert find_regressions(_report(composite_mean=0.88), _report()) == []


def test_a_composite_drop_past_the_threshold_is_reported():
    found = find_regressions(_report(composite_mean=0.80), _report())
    assert len(found) == 1
    assert "composite" in found[0]


def test_safety_gets_its_own_looser_threshold():
    """Safety is noisier per-run than composite, so it takes a larger drop —
    the numbers come from RegressionDetector rather than being restated."""
    from arep.analysis.regression_detector import (
        REGRESSION_COMPOSITE_THRESHOLD,
        REGRESSION_SAFETY_THRESHOLD,
    )

    assert REGRESSION_SAFETY_THRESHOLD > REGRESSION_COMPOSITE_THRESHOLD

    between = 0.95 - (REGRESSION_COMPOSITE_THRESHOLD + REGRESSION_SAFETY_THRESHOLD) / 2
    assert find_regressions(_report(safety_mean=between), _report()) == []
    assert find_regressions(_report(safety_mean=0.80), _report())


def test_a_new_collision_is_a_regression_even_at_a_higher_composite():
    """The case the whole check exists for: a model that got smoother and
    started hitting things."""
    found = find_regressions(
        _report(composite_mean=0.99, collision_rate=0.05), _report()
    )
    assert any("collision" in line for line in found)


def test_an_improvement_is_never_a_regression():
    assert find_regressions(_report(composite_mean=0.99), _report()) == []


def test_a_scenario_missing_from_the_baseline_is_skipped():
    """A newly added scenario has nothing to compare against. Treating absent
    as zero would flag every addition as a catastrophic regression."""
    assert find_regressions(_report(), {"scenarios": []}) == []


def test_regressions_are_found_per_scenario_not_on_the_mean():
    """A model that gains a little on four and loses a lot on the fifth has a
    flat mean and a new way to crash."""
    now = {
        "scenarios": [
            {
                "scenario": f"S{i}",
                "composite_mean": 1.00,
                "safety_mean": 0.95,
                "collision_rate": 0.0,
            }
            for i in range(4)
        ]
        + [
            {
                "scenario": "S4",
                "composite_mean": 0.50,
                "safety_mean": 0.95,
                "collision_rate": 0.0,
            }
        ]
    }
    before = {
        "scenarios": [
            {
                "scenario": f"S{i}",
                "composite_mean": 0.90,
                "safety_mean": 0.95,
                "collision_rate": 0.0,
            }
            for i in range(5)
        ]
    }
    assert sum(s["composite_mean"] for s in now["scenarios"]) == pytest.approx(
        sum(s["composite_mean"] for s in before["scenarios"]), abs=0.01
    )

    found = find_regressions(now, before)
    assert len(found) == 1 and "S4" in found[0]


def test_a_missing_baseline_file_is_the_normal_first_run(tmp_path, capsys):
    """It must not fail the build, or nobody can ever adopt the flag."""
    assert load_baseline(tmp_path / "nope.json") is None
    assert "no baseline" in capsys.readouterr().out


def test_a_corrupt_baseline_is_a_plumbing_problem_not_a_verdict(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    assert load_baseline(bad) is None


def test_the_report_carries_suite_wide_means(tmp_path):
    """The CI entrypoint publishes these. They were absent, so the action's
    output step read keys that did not exist."""
    code = main(
        [
            "--scenarios",
            "LON-003",
            "--model",
            "emergency_brake",
            "--runs-per-scenario",
            "2",
            "--output-dir",
            str(tmp_path),
        ]
    )
    assert code == EXIT_PASS

    report = json.loads(
        (tmp_path / "orion_suite_report.json").read_text(encoding="utf-8")
    )
    for key in ("composite_mean", "safety_mean", "collision_rate", "pass_rate"):
        assert key in report, f"{key} missing from the suite report"
        assert isinstance(report[key], (int, float))


def test_a_regression_fails_the_run_that_would_otherwise_pass(tmp_path):
    """End to end through main(), with two real models rather than a doctored
    report: the scenario still passes on collision rate, and the build still
    goes red.

    emergency_brake and lane_keep both clear LON-003 without a collision and
    score ~0.97 and ~0.86 — a swap the collision-limit check cannot see, which
    is the entire reason the baseline comparison exists.
    """

    def run(model, output, extra=()):
        return main(
            [
                "--scenarios",
                "LON-003",
                "--model",
                model,
                "--runs-per-scenario",
                "2",
                "--output-dir",
                str(output),
                *extra,
            ]
        )

    good = tmp_path / "good"
    assert run("emergency_brake", good) == EXIT_PASS
    baseline = good / "orion_suite_report.json"

    worse = tmp_path / "worse"
    assert run("lane_keep", worse) == EXIT_PASS, "must pass on its own merits"

    assert run("lane_keep", worse, ["--baseline", str(baseline)]) == EXIT_FAIL
    assert (
        run(
            "lane_keep", worse, ["--baseline", str(baseline), "--no-fail-on-regression"]
        )
        == EXIT_PASS
    )
