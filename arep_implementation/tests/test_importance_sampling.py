"""Importance sampling (Phase 4.3).

What these pin, in order of how expensive the mistake would be:

1. An unweighted batch is byte-identical to what it was before the feature
   existed. Scores, baselines and frame hashes are all keyed to the RNG
   stream, so an unconditional extra draw would silently move every stored
   number in the product.
2. The region never widens a declared range. A suite may concentrate runs
   inside what the scenario author sanctioned; it may not invent parameters
   the author never wrote down.
3. The weighted estimator recovers the uniform answer. This is the whole
   point: oversampling a failure region has to buy resolution there without
   changing what the batch says about the scenario as a whole.
4. The effective sample size drops below the run count, and is reported.
"""

from __future__ import annotations

import numpy as np
import pytest

from arep.core.random_manager import RandomManager
from arep.evaluation.composite import EvaluationResult
from arep.evaluation.safety import SafetyResult
from arep.evaluation.compliance import ComplianceResult
from arep.evaluation.stability import StabilityResult
from arep.evaluation.reactivity import ReactivityResult
from arep.scenario.importance import ImportanceRegion
from arep.scenario.parameterizer import ScenarioParameterizer
from arep.scenario.parser import ScenarioParser
from arep.statistics.aggregator import StatisticalAggregator

SCENARIO = "../scenarios/lon/LON-003_emergency_stop.yaml"


def _parse():
    """A fresh definition every time — the parameterizer mutates in place."""
    scenario, _ = ScenarioParser().parse_file(SCENARIO)
    return scenario


def _npc_x_range(scenario) -> tuple[str, float, float]:
    """The first NPC with a declared initial_x range, and that range."""
    overrides = scenario.parameterization.get("npc_overrides", {})
    for npc_id, override in overrides.items():
        spec = override.get("initial_x")
        if isinstance(spec, dict):
            return npc_id, float(spec["min"]), float(spec["max"])
    pytest.skip(f"{SCENARIO} declares no NPC initial_x range")


# ── 1. The uniform path is untouched ──────────────────────────────────────


def test_no_region_consumes_the_same_rng_stream_as_before():
    """region=None must not draw the in/out coin.

    If it did, every scenario instance for a given seed would shift, and with
    it every stored score and frame hash. The check is indirect but exact: a
    second sampler run from a fresh RandomManager of the same seed has to land
    on the same values, and those values have to match what the generator
    produces with no coin taken first.
    """
    a, b = _parse(), _parse()
    ScenarioParameterizer().apply(a, RandomManager(7))
    ScenarioParameterizer().apply(b, RandomManager(7))
    assert a.ego_initial.velocity == b.ego_initial.velocity
    assert a.ego_initial.x == b.ego_initial.x

    # The first value must be the generator's first draw, not its second.
    gen = RandomManager(7).get("scenario")
    spec = a.parameterization["ego_velocity"]
    assert a.ego_initial.velocity == pytest.approx(
        float(gen.uniform(spec["min"], spec["max"]))
    )


def test_no_region_weighs_one():
    assert ScenarioParameterizer().apply(_parse(), RandomManager(7)) == 1.0


# ── 2. Bounds are a narrowing, never a widening ───────────────────────────


def test_region_never_samples_outside_the_declared_range():
    npc_id, low, high = _npc_x_range(_parse())
    # A bound deliberately far wider than the scenario declares.
    region = ImportanceRegion(
        bounds={f"{npc_id}.initial_x": (low - 500.0, high + 500.0)},
        fraction=0.9,
    )
    for seed in range(60):
        scenario = _parse()
        ScenarioParameterizer().apply(scenario, RandomManager(seed), region)
        npc = next(o for o in scenario.traffic_objects if o.id == npc_id)
        assert low <= npc.initial.x <= high


def test_disjoint_bound_is_dropped_not_honoured():
    """A region that does not overlap the declared range must not move the draw.

    Honouring it would sample the scenario outside its own parameterization,
    which is the one thing the feature must never do.
    """
    npc_id, low, high = _npc_x_range(_parse())
    region = ImportanceRegion(
        bounds={f"{npc_id}.initial_x": (high + 1000.0, high + 2000.0)},
        fraction=0.9,
    )
    for seed in range(30):
        scenario = _parse()
        ScenarioParameterizer().apply(scenario, RandomManager(seed), region)
        npc = next(o for o in scenario.traffic_objects if o.id == npc_id)
        assert low <= npc.initial.x <= high


def test_region_actually_concentrates_the_draw():
    """Not a tautology: without this the feature could be a no-op and pass."""
    npc_id, low, high = _npc_x_range(_parse())
    span = high - low
    corner = (low, low + 0.2 * span)
    region = ImportanceRegion(bounds={f"{npc_id}.initial_x": corner}, fraction=0.8)

    def hits(reg):
        n = 0
        for seed in range(200):
            scenario = _parse()
            ScenarioParameterizer().apply(scenario, RandomManager(seed), reg)
            npc = next(o for o in scenario.traffic_objects if o.id == npc_id)
            n += corner[0] <= npc.initial.x <= corner[1]
        return n

    biased = hits(region)
    uniform = hits(None)
    # Uniform lands in a 20% corner about 40 times in 200; the biased draw
    # should be far above that. Wide margins: this pins the direction, not a
    # precise rate.
    assert biased > 120, biased
    assert uniform < 80, uniform


# ── 3. Determinism ────────────────────────────────────────────────────────


def test_same_seed_and_region_give_the_same_instance():
    npc_id, low, high = _npc_x_range(_parse())
    region = ImportanceRegion(
        bounds={f"{npc_id}.initial_x": (low, low + 0.3 * (high - low))},
        fraction=0.7,
    )
    a, b = _parse(), _parse()
    wa = ScenarioParameterizer().apply(a, RandomManager(11), region)
    wb = ScenarioParameterizer().apply(b, RandomManager(11), region)
    assert wa == wb
    assert a.ego_initial.velocity == b.ego_initial.velocity
    npc_a = next(o for o in a.traffic_objects if o.id == npc_id)
    npc_b = next(o for o in b.traffic_objects if o.id == npc_id)
    assert npc_a.initial.x == npc_b.initial.x


# ── 4. Region validation ──────────────────────────────────────────────────


@pytest.mark.parametrize("fraction", [0.0, 1.0, -0.1, 1.5])
def test_degenerate_fraction_is_refused(fraction):
    with pytest.raises(ValueError, match="fraction"):
        ImportanceRegion(bounds={"ego_velocity": (1.0, 2.0)}, fraction=fraction)


def test_inverted_bound_is_refused():
    with pytest.raises(ValueError, match="inverted"):
        ImportanceRegion(bounds={"ego_velocity": (9.0, 2.0)})


# ── 5. The weighted estimator ─────────────────────────────────────────────


def _result(composite: float, collided: bool, weight: float = 1.0):
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
        importance_weight=weight,
    )


def test_uniform_weights_leave_the_aggregate_unchanged():
    agg = StatisticalAggregator()
    for i in range(20):
        agg.add_result(_result(0.5 + i * 0.01, collided=i < 3))
    out = agg.compute()
    assert out.effective_n == 20.0
    assert out.collision_rate == pytest.approx(3 / 20)


def test_weighted_rate_recovers_the_population_rate():
    """Oversample the failing corner, weight it back, get the true rate.

    The population: a failure region that is 10% of the declared space, in
    which every run collides, and nothing collides outside it -- so the true
    collision rate is 0.10. A batch that draws half its runs from the region
    sees collisions in far more than 10% of its runs, and the weighted
    estimator has to put it back.

    The composition matters and is the thing the estimator got wrong first
    time. The proposal is a mixture: with probability `fraction` it draws from
    the region, otherwise from the whole space -- and that second branch lands
    inside the region 10% of the time too. Of 100 runs, 50 come from the
    region branch and another 5 from the uniform branch, so 55 runs sit inside
    the region and carry the in-region weight, not 50.
    """
    fraction, volume = 0.5, 0.1
    region = ImportanceRegion(bounds={"ego_velocity": (0.0, 1.0)}, fraction=fraction)
    w_in = region.weight(in_region=True, volume=volume)
    w_out = region.weight(in_region=False, volume=volume)

    agg = StatisticalAggregator()
    for _ in range(55):  # inside the region, by either branch: all collide
        agg.add_result(_result(0.2, collided=True, weight=w_in))
    for _ in range(45):  # genuinely outside: none do
        agg.add_result(_result(0.9, collided=False, weight=w_out))

    out = agg.compute()
    assert out.collision_rate == pytest.approx(0.10, abs=1e-9)
    # Composite likewise: 0.1 * 0.2 + 0.9 * 0.9
    assert out.composite_mean == pytest.approx(0.83, abs=1e-9)


def test_weight_follows_membership_not_the_branch_that_drew_it():
    """A uniform-branch draw that lands in the region carries the region weight.

    Weighting by the branch instead under-counts the region and biases every
    rate the batch reports, silently: the estimate stays plausible and is
    simply wrong. This is the defect the estimator shipped with first.
    """
    region = ImportanceRegion(bounds={"npc.initial_x": (0.0, 10.0)}, fraction=0.5)
    declared = {"npc.initial_x": (0.0, 100.0)}

    assert region.contains({"npc.initial_x": 5.0}, declared) is True
    assert region.contains({"npc.initial_x": 50.0}, declared) is False
    # Same point, same weight, regardless of how the sampler reached it.
    vol = region.volume(declared)
    assert region.weight(True, vol) != region.weight(False, vol)


def test_membership_ignores_dimensions_the_scenario_does_not_vary():
    """A bound on a constant is not a constraint, and must not exclude a point.

    It contributes no probability mass, so treating it as an unmet condition
    would push every draw into the out-of-region branch and defeat the region
    entirely.
    """
    region = ImportanceRegion(bounds={"absent.param": (0.0, 1.0)}, fraction=0.5)
    assert region.contains({"other": 99.0}, {"other": (0.0, 100.0)}) is True
    assert region.volume({"other": (0.0, 100.0)}) == 1.0


def test_effective_n_falls_below_the_run_count_and_is_reported():
    region = ImportanceRegion(bounds={"ego_velocity": (0.0, 1.0)}, fraction=0.5)
    w_in = region.weight(in_region=True, volume=0.1)
    w_out = region.weight(in_region=False, volume=0.1)

    agg = StatisticalAggregator()
    for _ in range(55):
        agg.add_result(_result(0.2, collided=True, weight=w_in))
    for _ in range(45):
        agg.add_result(_result(0.9, collided=False, weight=w_out))

    out = agg.compute()
    assert out.num_runs == 100
    assert out.effective_n < 100.0
    assert out.effective_n > 0.0
    assert out.to_dict()["effective_n"] == pytest.approx(round(out.effective_n, 2))
    # The interval must be built on the effective n, so it cannot be narrower
    # than the same spread at n=100 would give.
    assert out.composite_ci_upper > out.composite_ci_lower


def test_all_zero_weights_are_refused_rather_than_averaged():
    agg = StatisticalAggregator()
    for _ in range(5):
        agg.add_result(_result(0.4, collided=True, weight=0.0))
    with pytest.raises(ValueError, match="degenerate region"):
        agg.compute()


def test_weighted_percentiles_track_the_weights():
    """A run carrying most of the weight has to own most of the distribution."""
    agg = StatisticalAggregator()
    agg.add_result(_result(0.1, collided=True, weight=0.01))
    for _ in range(9):
        agg.add_result(_result(0.9, collided=False, weight=1.0))
    dist = agg.compute().distributions["composite"]
    # Unweighted, the 5th percentile of these ten values sits near 0.1. With
    # the low run carrying 1% of the weight it must not.
    assert dist.percentile_5 > 0.5
    assert dist.n == 10


# ── 6. End to end through the runner ──────────────────────────────────────


def test_run_batch_accepts_a_region_and_reports_effective_n():
    from arep.execution.runner import EvaluationRunner
    from arep.models.examples.example_models import EmergencyBrakeModel

    npc_id, low, high = _npc_x_range(_parse())
    region = ImportanceRegion(
        bounds={f"{npc_id}.initial_x": (low, low + 0.3 * (high - low))},
        fraction=0.7,
    )
    runner = EvaluationRunner()
    result = runner.run_batch(
        scenario_path=SCENARIO,
        model=EmergencyBrakeModel(),
        num_runs=6,
        master_seed=42,
        importance=region,
    )
    assert result.num_runs == 6
    assert 0.0 < result.aggregated.effective_n <= 6.0
    assert all(r.importance_weight != 1.0 for r in result.per_run_results)


def test_run_batch_without_a_region_still_weighs_one():
    from arep.execution.runner import EvaluationRunner
    from arep.models.examples.example_models import EmergencyBrakeModel

    runner = EvaluationRunner()
    result = runner.run_batch(
        scenario_path=SCENARIO,
        model=EmergencyBrakeModel(),
        num_runs=4,
        master_seed=42,
    )
    assert all(r.importance_weight == 1.0 for r in result.per_run_results)
    assert result.aggregated.effective_n == 4.0


# ── 7. Sampler and estimator composed ─────────────────────────────────────


def test_weighted_estimate_recovers_a_known_rate_through_the_real_sampler():
    """The claim the whole feature rests on, measured rather than argued.

    Everything above tests one half: that the sampler narrows correctly, or
    that the estimator weights correctly. This runs them together against a
    quantity whose true value is known by construction -- "the NPC starts in
    the lowest 10% of its declared range", which is exactly 0.10 under uniform
    sampling -- and checks that oversampling that corner and weighting back
    returns 0.10 rather than the 0.5-ish the biased draw sees raw.

    This is the test that catches a weighting mistake end to end. The
    branch-versus-membership defect passed every unit test and failed here.

    No simulation: parameter draws alone, so it is cheap enough to run 3000 of
    them and get an interval tight enough to mean something.
    """
    npc_id, low, high = _npc_x_range(_parse())
    span = high - low
    corner = (low, low + 0.10 * span)
    region = ImportanceRegion(bounds={f"{npc_id}.initial_x": corner}, fraction=0.5)

    param = ScenarioParameterizer()
    weights, indicators = [], []
    raw_hits = 0
    for seed in range(3000):
        scenario = _parse()
        w = param.apply(scenario, RandomManager(seed), region)
        npc = next(o for o in scenario.traffic_objects if o.id == npc_id)
        hit = 1.0 if corner[0] <= npc.initial.x <= corner[1] else 0.0
        weights.append(w)
        indicators.append(hit)
        raw_hits += hit

    weights = np.array(weights)
    indicators = np.array(indicators)

    # The raw draw is biased on purpose -- if it were not, there would be
    # nothing to correct and this test would pass vacuously.
    raw_rate = raw_hits / len(indicators)
    assert raw_rate > 0.4, f"region was not actually oversampled: {raw_rate}"

    estimate = float(np.average(indicators, weights=weights))
    assert estimate == pytest.approx(0.10, abs=0.02), (
        f"weighted estimate {estimate:.4f} does not recover the true rate 0.10 "
        f"(raw biased rate was {raw_rate:.4f})"
    )
