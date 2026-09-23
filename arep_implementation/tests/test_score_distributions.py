"""
Score distributions and confidence intervals (Phase 2.1).

The aggregator computed Wilson and t-distribution intervals from the start and
then discarded them inside the function, so every consumer saw a point estimate.
This closes that: per-metric distributions with intervals and percentiles,
surfaced through GET /api/runs/batch/{id}/results.

What these tests pin is the statistics, not the plumbing. The failure that
matters here is a number that looks authoritative and is not: an interval that
does not widen when the sample shrinks, a percentile computed over the wrong
axis, or a "worst run" that is not the run a reviewer needs to reproduce.
"""

from __future__ import annotations

import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from arep.statistics.aggregator import (  # noqa: E402
    ScoreDistribution,
    StatisticalAggregator,
)

AGG = StatisticalAggregator()


# -- The interval ---------------------------------------------------------


def test_the_interval_widens_as_the_sample_shrinks():
    """The acceptance criterion, at n = 5 / 20 / 100.

    This is the whole point of reporting an interval: a 5-run batch must not
    look as certain as a 100-run one.
    """
    values = np.random.default_rng(0).normal(0.75, 0.10, 100)

    widths = []
    for n in (5, 20, 100):
        d = AGG.distribution(values[:n])
        widths.append(d.ci_95_high - d.ci_95_low)

    assert (
        widths[0] > widths[1] > widths[2]
    ), f"interval did not narrow with n: {widths}"


def test_the_interval_brackets_the_mean():
    d = AGG.distribution(np.random.default_rng(1).normal(0.6, 0.2, 50))
    assert d.ci_95_low <= d.mean <= d.ci_95_high


def test_a_single_run_reports_no_spread_rather_than_a_fake_interval():
    """n=1 has no spread to estimate. Zero std and a collapsed interval are the
    honest answer; a made-up width would read as evidence."""
    d = AGG.distribution(np.array([0.8]))
    assert d.n == 1
    assert d.std == 0.0
    assert d.ci_95_low == d.ci_95_high == d.mean == 0.8


def test_identical_runs_give_a_zero_width_interval():
    """No variance means the mean is known exactly for this sample, and the
    t-interval would otherwise divide by a zero standard error."""
    d = AGG.distribution(np.full(20, 0.5))
    assert d.std == 0.0
    assert d.ci_95_low == d.ci_95_high == 0.5


def test_an_empty_series_is_empty_not_zero():
    """A batch with no scored runs must not report a model that scored 0.0."""
    d = AGG.distribution(np.array([]))
    assert d == ScoreDistribution()
    assert d.n == 0


def test_the_standard_deviation_is_the_sample_one():
    """ddof=1: these runs are a sample of the scenario's parameter space, not
    the whole of it. ddof=0 would understate the spread."""
    values = np.array([0.1, 0.5, 0.9])
    assert AGG.distribution(values).std == pytest.approx(np.std(values, ddof=1))


# -- Percentiles ----------------------------------------------------------


def test_percentiles_are_ordered():
    d = AGG.distribution(np.random.default_rng(2).uniform(0, 1, 200))
    assert d.minimum <= d.percentile_5 <= d.percentile_25
    assert (
        d.percentile_25 <= d.mean <= d.percentile_75
        or d.percentile_25 <= d.percentile_75
    )
    assert d.percentile_75 <= d.percentile_95 <= d.maximum


def test_percentiles_separate_two_models_a_mean_cannot():
    """The reason percentiles are reported at all.

    One model is reliably mediocre. The other is usually excellent and
    occasionally catastrophic. Their means are close; for a safety argument
    they are nothing alike, and only the lower tail says so.
    """
    steady = np.full(100, 0.70)  # no spread at all
    spiky = np.concatenate([np.full(85, 0.775), np.full(15, 0.27)])

    a = AGG.distribution(steady)
    b = AGG.distribution(spiky)

    assert abs(a.mean - b.mean) < 0.05, "means should be close for this to be the point"
    assert b.percentile_5 < a.percentile_5 - 0.3, "the tail must separate them"


# -- Determinism ----------------------------------------------------------


def test_the_same_values_produce_identical_statistics():
    """Acceptance criterion: same seed -> identical distribution statistics."""
    values = np.random.default_rng(7).normal(0.5, 0.1, 40)
    assert AGG.distribution(values).to_dict() == AGG.distribution(values).to_dict()


# -- Wilson interval for the collision rate -------------------------------


def test_wilson_interval_stays_inside_zero_and_one():
    """The normal approximation runs off the end of the scale near 0 and 1,
    which is exactly where a collision rate lives."""
    for successes, total in ((0, 10), (10, 10), (1, 100), (99, 100)):
        low, high = AGG._wilson_ci(successes, total)
        assert 0.0 <= low <= high <= 1.0


def test_a_zero_collision_rate_still_reports_an_upper_bound():
    """Zero collisions in 20 runs is not proof of zero collision probability,
    and the interval is what says so."""
    low, high = AGG._wilson_ci(0, 20)
    assert low == 0.0
    assert high > 0.10, "20 clean runs should not imply a tight bound at zero"


def test_the_collision_bound_tightens_with_more_runs():
    _, high_20 = AGG._wilson_ci(0, 20)
    _, high_500 = AGG._wilson_ci(0, 500)
    assert high_500 < high_20


# -- Aggregation over real results ----------------------------------------


def _batch(n=12, seed=42):
    from arep.execution.runner import EvaluationRunner
    from arep.models.examples.example_models import EmergencyBrakeModel

    return EvaluationRunner().run_batch(
        scenario_path="../scenarios/lon/LON-003_emergency_stop.yaml",
        model=EmergencyBrakeModel(),
        num_runs=n,
        master_seed=seed,
    )


def test_every_metric_gets_a_distribution():
    agg = _batch().aggregated
    for metric in (
        "composite",
        "safety",
        "compliance",
        "stability",
        "reactivity",
        "min_ttc",
    ):
        assert metric in agg.distributions, f"{metric} has no distribution"
        assert agg.distributions[metric].n == agg.num_runs


def test_the_distribution_mean_agrees_with_the_scalar_field():
    """The scalar fields are what stored baselines and the batch row use. If the
    two ever disagree the dashboard and the database tell different stories."""
    agg = _batch().aggregated
    assert agg.distributions["composite"].mean == pytest.approx(agg.composite_mean)
    assert agg.distributions["safety"].mean == pytest.approx(agg.safety_mean)
    assert agg.distributions["composite"].std == pytest.approx(agg.composite_std)


def test_the_worst_and_best_runs_are_named_by_seed():
    """A row id cannot be re-run. A seed can, which is the only reason to name
    the worst run."""
    result = _batch()
    agg = result.aggregated
    seeds = {r.master_seed for r in result.per_run_results}

    assert agg.worst_run_seed in seeds
    assert agg.best_run_seed in seeds

    by_seed = {r.master_seed: r.composite_score for r in result.per_run_results}
    assert by_seed[agg.worst_run_seed] <= by_seed[agg.best_run_seed]


def test_a_collision_outranks_a_low_composite_when_picking_the_worst_run():
    """The run worth reproducing is the one that crashed, even when another
    scored lower on the weighted average."""
    from arep.evaluation.composite import EvaluationResult
    from arep.evaluation.safety import SafetyResult
    from arep.evaluation.compliance import ComplianceResult
    from arep.evaluation.stability import StabilityResult
    from arep.evaluation.reactivity import ReactivityResult

    def result(seed, composite, collided):
        return EvaluationResult(
            safety=SafetyResult(
                collision_occurred=collided,
                collision_penalty=0.0 if collided else 1.0,
                min_ttc=1.0,
                min_ttc_score=composite,
                critical_ttc_fraction=0.0,
                safety_score=composite,
            ),
            compliance=ComplianceResult(
                speed_compliance_fraction=1.0,
                mean_speed_excess=0.0,
                max_speed_excess=0.0,
                lane_compliance_fraction=1.0,
                compliance_score=composite,
            ),
            stability=StabilityResult(
                acceleration_std=0.0,
                mean_jerk=0.0,
                max_jerk=0.0,
                steering_std=0.0,
                stability_score=composite,
            ),
            reactivity=ReactivityResult(
                brake_response_time=0.5,
                steering_response_time=0.5,
                response_adequate=True,
                deceleration_magnitude=0.0,
                reactivity_score=composite,
            ),
            composite_score=composite,
            master_seed=seed,
        )

    agg = StatisticalAggregator()
    agg.add_result(result(seed=1, composite=0.20, collided=False))  # lowest score
    agg.add_result(result(seed=2, composite=0.60, collided=True))  # but this crashed
    agg.add_result(result(seed=3, composite=0.90, collided=False))

    out = agg.compute()
    assert out.worst_run_seed == 2, "the crashed run is the one to reproduce"
    assert out.best_run_seed == 3


def test_the_dict_form_carries_the_distributions():
    """to_dict is what reaches the API and the PDF report."""
    payload = _batch().aggregated.to_dict()

    assert "distributions" in payload
    composite = payload["distributions"]["composite"]
    assert set(composite) == {"mean", "std", "ci_95", "percentiles", "min", "max", "n"}
    assert len(composite["ci_95"]) == 2
    assert set(composite["percentiles"]) == {"p5", "p25", "p75", "p95"}
    assert payload["worst_run_seed"] is not None
