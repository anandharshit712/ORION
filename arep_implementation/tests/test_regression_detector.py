"""
Regression detector tests (Phase 2.4).

Compares model vN against vN-1 so a safety regression is caught before it
ships. The thresholds are deliberately strict — a false positive costs a
conversation, a missed regression ships a worse driver.

The behaviour worth pinning is not the arithmetic but the judgement calls:
a regression outranks a win count, collision rate is inverted, and both models
must face the same parameter draws or the comparison measures the sampler.
"""

from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from arep.analysis.regression_detector import (   # noqa: E402
    REGRESSION_COLLISION_THRESHOLD,
    REGRESSION_COMPOSITE_THRESHOLD,
    REGRESSION_SAFETY_THRESHOLD,
    RegressionDetector,
    _summarise,
)
from arep.statistics.aggregator import AggregatedMetrics   # noqa: E402

SCENARIO = "scenarios/basic/straight_road_lead_vehicle.yaml"


def _agg(composite=0.9, safety=0.9, compliance=0.9, stability=0.9,
         reactivity=0.9, collision_rate=0.0, num_runs=10):
    return AggregatedMetrics(
        num_runs=num_runs,
        composite_mean=composite, safety_mean=safety,
        compliance_mean=compliance, stability_mean=stability,
        reactivity_mean=reactivity, collision_rate=collision_rate,
    )


def _compare(agg_a, agg_b):
    detector = RegressionDetector()
    comparison = detector._compare_aggregates("s1", "a", "b", agg_a, agg_b, 10)
    from arep.analysis.regression_detector import ComparisonReport
    report = ComparisonReport(model_a_id="a", model_a_name="a",
                              model_b_id="b", model_b_name="b")
    report.scenario_comparisons.append(comparison)
    return detector._finalise(report)


# -- Detecting a regression ----------------------------------------------

def test_a_composite_drop_past_the_threshold_is_a_regression():
    report = _compare(_agg(composite=0.90), _agg(composite=0.90 - 0.06))
    assert report.regressions
    assert "do not deploy" in report.recommendation


def test_a_composite_drop_inside_the_threshold_is_not():
    report = _compare(_agg(composite=0.90), _agg(composite=0.90 - 0.01))
    assert not report.regressions
    assert "Safe to deploy" in report.recommendation


def test_safety_has_its_own_looser_threshold():
    """Safety tolerates a larger absolute move than composite because it is a
    noisier measure, and the collision term dominates it."""
    assert REGRESSION_SAFETY_THRESHOLD > REGRESSION_COMPOSITE_THRESHOLD

    inside = _compare(_agg(safety=0.90), _agg(safety=0.90 - 0.08))
    outside = _compare(_agg(safety=0.90), _agg(safety=0.90 - 0.12))
    assert not any(d.metric == "safety_score" for d in inside.regressions)
    assert any(d.metric == "safety_score" for d in outside.regressions)


def test_a_rise_in_collision_rate_is_the_regression_not_a_fall():
    worse = _compare(_agg(collision_rate=0.00), _agg(collision_rate=0.05))
    better = _compare(_agg(collision_rate=0.05), _agg(collision_rate=0.00))

    assert any(d.metric == "collision_rate" for d in worse.regressions)
    assert not better.regressions


def test_collision_delta_is_signed_so_positive_always_means_improved():
    """Every other metric is higher-is-better; collision rate is not, and a
    reader comparing deltas across metrics would otherwise be misled."""
    report = _compare(_agg(collision_rate=0.10), _agg(collision_rate=0.02))
    delta = next(d for d in report.scenario_comparisons[0].metric_deltas
                 if d.metric == "collision_rate")
    assert delta.delta > 0, "a drop in collisions should read as an improvement"


def test_a_one_point_collision_rise_is_the_boundary():
    assert REGRESSION_COLLISION_THRESHOLD == 0.01


# -- Judgement --------------------------------------------------------------

def test_a_regression_outranks_the_win_count():
    """A candidate better on most scenarios and dangerous on one does not ship."""
    detector = RegressionDetector()
    from arep.analysis.regression_detector import ComparisonReport

    report = ComparisonReport(model_a_id="a", model_a_name="a",
                              model_b_id="b", model_b_name="b")
    # Two clear wins...
    for scenario in ("win1", "win2"):
        report.scenario_comparisons.append(detector._compare_aggregates(
            scenario, "a", "b", _agg(composite=0.70), _agg(composite=0.90), 10))
    # ...and one scenario where safety collapses.
    report.scenario_comparisons.append(detector._compare_aggregates(
        "danger", "a", "b", _agg(safety=0.95), _agg(safety=0.50), 10))

    detector._finalise(report)

    assert report.overall_winner == "a"
    assert "do not deploy" in report.recommendation


def test_a_marginal_improvement_is_a_tie_not_a_win():
    """Without a margin every comparison resolves to a winner on noise."""
    report = _compare(_agg(composite=0.900), _agg(composite=0.905))
    assert report.scenario_comparisons[0].winner == "tie"
    assert report.overall_winner == "tie"


def test_a_clear_improvement_wins():
    report = _compare(_agg(composite=0.80), _agg(composite=0.90))
    assert report.scenario_comparisons[0].winner == "b"
    assert report.overall_winner == "b"
    assert "Safe to deploy" in report.recommendation


def test_a_baseline_that_stays_ahead_is_reported_as_no_improvement():
    """Not a regression, but not worth shipping either — say both."""
    report = _compare(_agg(composite=0.90), _agg(composite=0.87))
    assert report.overall_winner == "a"
    assert "no improvement" in report.recommendation


def test_the_recommendation_names_the_worst_metric():
    report = _compare(_agg(composite=0.9, safety=0.95), _agg(composite=0.5, safety=0.5))
    assert "safety_score" in report.recommendation or "composite_score" in report.recommendation


# -- Summarising stored runs ---------------------------------------------

def test_summarise_recomputes_from_the_rows():
    """Reading the batch's stored aggregate would compare across whatever
    scoring version wrote it."""
    class Row:
        def __init__(self, composite, collision):
            self.composite_score = composite
            self.safety_score = composite
            self.compliance_score = composite
            self.stability_score = composite
            self.reactivity_score = composite
            self.collision_occurred = collision

    summary = _summarise([Row(0.8, False), Row(0.6, True)])
    assert summary.num_runs == 2
    assert summary.composite_mean == pytest.approx(0.7)
    assert summary.collision_rate == pytest.approx(0.5)


def test_summarise_handles_an_empty_batch():
    assert _summarise([]).num_runs == 0


# -- End to end ------------------------------------------------------------

def test_two_real_models_compare_end_to_end():
    """EmergencyBrake against ConstantAction on a scenario where one brakes and
    the other does not — the comparison must call it."""
    detector = RegressionDetector()
    report = detector.compare(
        model_a_id="EmergencyBrake",
        model_b_id="ConstantAction",
        scenario_ids=[SCENARIO],
        runs_per_scenario=2,
        seed=42,
    )

    assert report.model_a_name
    assert len(report.scenario_comparisons) == 1
    # ConstantAction does not brake, so it should not come out ahead.
    assert report.overall_winner in ("a", "tie")
    assert report.recommendation


def test_both_models_face_the_same_seed():
    """Comparing one model on one sample against another on a different sample
    measures the sampler, not the models."""
    import inspect

    source = inspect.getsource(RegressionDetector.compare)
    assert "runs_per_scenario, seed)" in source.replace("\n", " ").replace("  ", " ")


def test_comparing_batches_of_different_scenarios_is_refused(tmp_path):
    from arep.database import connection as conn_mod
    from arep.database.models import BatchJobRecord

    conn_mod._engine = None
    conn_mod._SessionFactory = None
    conn_mod.init_database(url=f"sqlite:///{tmp_path / 'cmp.db'}")
    try:
        with conn_mod.session_scope() as session:
            for name in ("scenario-one", "scenario-two"):
                session.add(BatchJobRecord(
                    scenario_name=name, model_name="m", num_runs=1,
                    master_seed=1, status="completed",
                ))

        with pytest.raises(ValueError, match="different scenarios"):
            RegressionDetector().compare_from_db("1", "2")
    finally:
        conn_mod._engine = None
        conn_mod._SessionFactory = None


def test_comparing_an_unknown_batch_raises(tmp_path):
    from arep.database import connection as conn_mod

    conn_mod._engine = None
    conn_mod._SessionFactory = None
    conn_mod.init_database(url=f"sqlite:///{tmp_path / 'cmp2.db'}")
    try:
        with pytest.raises(ValueError, match="No batch job"):
            RegressionDetector().compare_from_db("404", "405")
    finally:
        conn_mod._engine = None
        conn_mod._SessionFactory = None
