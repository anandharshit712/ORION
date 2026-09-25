"""
Adversarial search tests (Phase 2.3).

Running a scenario 500 times with random draws finds the failures that happen
to be common. Adversarial search goes looking for the ones that are rare and
bad, and hands back the parameter set that produced them — which is the part a
customer can act on.

Two things have to be right or the whole exercise inverts:
  - the fitness sign. CMA-ES minimises; the objective is higher-is-worse. Get
    that backwards and the search confidently hunts for the *safest* scenario.
  - the bounds. CMA-ES proposes points outside the box routinely, and running
    one would score a model on a scenario the customer never declared.
"""

from __future__ import annotations

import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from arep.models.examples.example_models import (  # noqa: E402
    ConstantActionModel,
    EmergencyBrakeModel,
)
from arep.scenario.parser import ScenarioParser  # noqa: E402
from arep.search.objective import ObjectiveFunction  # noqa: E402
from arep.search.optimizer import CMAESOptimizer, RandomSearchOptimizer  # noqa: E402
from arep.search.space import SearchSpace  # noqa: E402

PARAMETERISED = "../scenarios/lon/LON-003_emergency_stop.yaml"
FLAT = "scenarios/basic/straight_road_lead_vehicle.yaml"


def _space(path=PARAMETERISED):
    scenario, _ = ScenarioParser().parse_file(path)
    return scenario, SearchSpace(scenario)


# -- The search space -----------------------------------------------------


def test_every_declared_range_becomes_a_dimension():
    _, space = _space()
    names = [d.name for d in space.dimensions]
    assert "ego_velocity" in names
    assert any(
        n.startswith("npc_overrides.") for n in names
    ), "nested NPC overrides must be searchable too"
    assert space.n_dims == len(names)


def test_dimension_order_is_stable():
    """x[0] must mean the same parameter across runs, or a resumed search
    applies its history to the wrong knobs."""
    _, first = _space()
    _, second = _space()
    assert [d.name for d in first.dimensions] == [d.name for d in second.dimensions]


def test_a_scenario_with_no_parameterisation_has_no_dimensions():
    _, space = _space(FLAT)
    assert space.n_dims == 0


def test_bounds_match_the_declared_ranges():
    scenario, space = _space()
    lows, highs = space.bounds
    ego = next(d for d in space.dimensions if d.name == "ego_velocity")
    index = [d.name for d in space.dimensions].index("ego_velocity")
    assert lows[index] == ego.low == scenario.parameterization["ego_velocity"]["min"]
    assert highs[index] == ego.high == scenario.parameterization["ego_velocity"]["max"]


def test_a_vector_round_trips_into_a_parameterization_block():
    """The search must feed the ordinary run path, not a parallel one."""
    _, space = _space()
    params = space.to_params_dict(space.midpoint())

    assert isinstance(params["ego_velocity"], float)
    assert isinstance(
        params["npc_overrides"]["lead_vehicle"], dict
    ), "nesting must survive, or the parameterizer will not find the overrides"


def test_out_of_bounds_proposals_are_clipped():
    """CMA-ES proposes outside the box routinely. Running one would score the
    model on a scenario the customer never declared."""
    _, space = _space()
    lows, highs = space.bounds

    params = space.to_params_dict(highs + 1000.0)
    ego = next(d for d in space.dimensions if d.name == "ego_velocity")
    assert params["ego_velocity"] <= ego.high

    params = space.to_params_dict(lows - 1000.0)
    assert params["ego_velocity"] >= ego.low


def test_a_wrong_length_vector_is_refused():
    _, space = _space()
    with pytest.raises(ValueError, match="Expected"):
        space.to_params_dict(np.zeros(space.n_dims + 3))


# -- The fitness landscape ------------------------------------------------


def test_a_collision_scores_far_above_a_clean_run():
    safe = ObjectiveFunction.compute_fitness(False, 10.0, 1.0, 1.0)
    crash = ObjectiveFunction.compute_fitness(True, 0.0, 0.0, 0.5)
    assert crash > safe * 10


def test_a_tighter_near_miss_scores_higher():
    loose = ObjectiveFunction.compute_fitness(False, 8.0, 0.9, 1.0)
    tight = ObjectiveFunction.compute_fitness(False, 0.5, 0.9, 1.0)
    assert tight > loose


def test_zero_ttc_does_not_divide_by_zero():
    assert np.isfinite(ObjectiveFunction.compute_fitness(True, 0.0, 0.0, 0.0))


def test_a_worse_safety_score_scores_higher():
    better = ObjectiveFunction.compute_fitness(False, 5.0, 0.9, 1.0)
    worse = ObjectiveFunction.compute_fitness(False, 5.0, 0.3, 1.0)
    assert worse > better


# -- Running a search -----------------------------------------------------


def test_random_search_finds_the_counter_example_for_a_model_that_never_brakes():
    """ConstantAction drives into a braking lead vehicle. If the search cannot
    falsify that, it cannot falsify anything."""
    scenario, space = _space()
    objective = ObjectiveFunction(scenario, ConstantActionModel(throttle=0.4), space)

    result = RandomSearchOptimizer(space, n_samples=30, seed=3).run(objective)

    assert result.falsification_found
    assert result.falsification_params, "a falsification with no parameters is useless"
    assert result.n_evals < 30, "should stop as soon as it finds one"


def test_the_counter_example_is_reproducible():
    """A parameter set a customer cannot re-run is not evidence."""
    from arep.core.random_manager import RandomManager
    from arep.execution.runner import EvaluationRunner
    from arep.scenario.parameterizer import ScenarioParameterizer
    import copy

    scenario, space = _space()
    objective = ObjectiveFunction(scenario, ConstantActionModel(throttle=0.4), space)
    result = RandomSearchOptimizer(space, n_samples=30, seed=3).run(objective)
    assert result.falsification_found

    record = objective.falsification_record
    replay = copy.deepcopy(scenario)
    replay.parameterization = record.params
    ScenarioParameterizer().apply(replay, RandomManager(record.seed))

    rerun = EvaluationRunner().run_scenario_definition(
        replay,
        ConstantActionModel(throttle=0.4),
        record.seed,
    )
    assert (
        rerun.safety.collision_occurred
    ), "the reported counter-example did not reproduce"


def test_cma_es_runs_and_records_every_evaluation():
    scenario, space = _space()
    objective = ObjectiveFunction(scenario, EmergencyBrakeModel(), space)

    result = CMAESOptimizer(space, max_evals=12, popsize=4, seed=7).run(objective)

    assert result.n_evals > 0
    assert len(result.all_evaluations) == result.n_evals
    assert result.optimizer_used == "cma-es"
    # The search itself is the deliverable: a customer wants the parameters.
    assert result.best_params


def test_cma_es_maximises_rather_than_minimises_the_objective():
    """The sign check. If flipped, this search returns the *safest* scenario it
    can find and reports it as the worst."""
    scenario, space = _space()
    objective = ObjectiveFunction(scenario, EmergencyBrakeModel(), space)

    result = CMAESOptimizer(space, max_evals=12, popsize=4, seed=7).run(objective)

    fitnesses = [record.fitness for record in objective.history]
    assert result.best_fitness == max(fitnesses)


def test_a_search_over_nothing_returns_immediately():
    """A scenario with no parameterisation has no space to search; running 200
    identical simulations and reporting the last is worse than saying so."""
    scenario, space = _space(FLAT)
    objective = ObjectiveFunction(scenario, EmergencyBrakeModel(), space)

    result = CMAESOptimizer(space, max_evals=50).run(objective)

    assert result.n_evals == 0
    assert result.best_params == {}
    assert result.converged


def test_the_same_seed_reproduces_the_same_search():
    scenario, space = _space()

    def search():
        objective = ObjectiveFunction(
            scenario, ConstantActionModel(throttle=0.3), space
        )
        result = RandomSearchOptimizer(space, n_samples=6, seed=11).run(objective)
        return [round(r.fitness, 9) for r in result.all_evaluations]

    assert search() == search()


def test_every_evaluation_is_kept_for_the_report():
    scenario, space = _space()
    objective = ObjectiveFunction(scenario, EmergencyBrakeModel(), space)

    RandomSearchOptimizer(space, n_samples=5, seed=2).run(objective)

    assert len(objective.history) == 5
    for record in objective.history:
        assert record.params
        assert np.isfinite(record.fitness)


def test_cma_es_survives_finding_a_collision():
    """The regression that mattered: CMA-ES crashed when it succeeded.

    The inner loop breaks as soon as a falsification appears, leaving `costs`
    shorter than the population cma proposed. Passing that truncated list to
    `tell()` raises "population size 1 is too small", so the search blew up
    precisely when it did its job.

    It stayed hidden because every other CMA-ES test here drives
    EmergencyBrakeModel, which does not collide. This one uses a model that
    does.
    """
    scenario, space = _space()
    objective = ObjectiveFunction(scenario, ConstantActionModel(throttle=0.4), space)

    result = CMAESOptimizer(space, max_evals=50, popsize=10, seed=7).run(objective)

    assert result.falsification_found, "the search never found the collision"
    assert (
        result.falsification_params
    ), "a counter-example with no parameters is useless"
    assert result.n_evals > 0


# -- Collecting every failure, not just the first -------------------------


def test_the_search_is_reproducible_down_to_the_failing_setting():
    """A tester re-running a search must get the same counter-example.

    Without this the finding is not evidence: "we found a failure at these
    settings" is only useful if asking again produces the same settings.
    """
    scenario, _ = _space()

    def search():
        space = SearchSpace(scenario)
        objective = ObjectiveFunction(
            scenario, ConstantActionModel(throttle=0.4), space
        )
        result = CMAESOptimizer(space, max_evals=50, popsize=10, seed=3).run(objective)
        record = objective.falsification_record
        return result.n_evals, record.seed, record.params

    assert search() == search()


def test_continuing_past_the_first_failure_finds_more_of_them():
    """Stopping at the first collision returns one counter-example for the least
    compute. A customer fixing the model wants every failure mode, which is what
    the whole budget buys."""
    scenario, _ = _space()

    def search(stop_first):
        space = SearchSpace(scenario)
        objective = ObjectiveFunction(
            scenario, ConstantActionModel(throttle=0.4), space
        )
        return CMAESOptimizer(
            space,
            max_evals=60,
            popsize=10,
            seed=3,
            stop_on_first_falsification=stop_first,
        ).run(objective)

    stopped = search(True)
    exhaustive = search(False)

    assert stopped.falsification_count == 1, "stopping should return exactly one"
    assert exhaustive.falsification_count > stopped.falsification_count
    assert exhaustive.n_evals == 60, "continuing should spend the whole budget"


def test_the_failure_rate_is_reported():
    """When most of the space fails, the rate is the finding — a list of
    individual settings buries it."""
    scenario, _ = _space()
    space = SearchSpace(scenario)
    objective = ObjectiveFunction(scenario, ConstantActionModel(throttle=0.4), space)

    result = CMAESOptimizer(
        space, max_evals=40, popsize=10, seed=3, stop_on_first_falsification=False
    ).run(objective)

    assert 0.0 < result.failure_rate <= 1.0
    assert result.failure_rate == pytest.approx(
        result.falsification_count / result.n_evals
    )


def test_reported_failures_are_capped_and_worst_first():
    """A reviewer reproduces the worst few; the rest is what failure_rate and
    the clusterer are for."""
    from arep.search.optimizer import MAX_REPORTED_FAILURES

    scenario, _ = _space()
    space = SearchSpace(scenario)
    objective = ObjectiveFunction(scenario, ConstantActionModel(throttle=0.4), space)

    result = CMAESOptimizer(
        space, max_evals=60, popsize=10, seed=3, stop_on_first_falsification=False
    ).run(objective)

    assert len(result.falsifications) <= MAX_REPORTED_FAILURES
    fitnesses = [f["fitness"] for f in result.falsifications]
    assert fitnesses == sorted(fitnesses, reverse=True), "worst case must come first"
    # Every reported failure carries the seed that reproduces it.
    assert all(f["seed"] is not None and f["params"] for f in result.falsifications)


def test_near_identical_failures_collapse_into_one():
    """CMA-ES converges, so a search that keeps going resamples the region it
    found. Reporting forty variations of one bug buries the other bugs."""
    from arep.search.optimizer import distinct_failures

    class Rec:
        def __init__(self, params, fitness):
            self.params = params
            self.fitness = fitness
            self.seed = 1

    a = Rec({"ego_velocity": 20.0, "gap": 30.0}, 15.0)
    twin = Rec({"ego_velocity": 20.05, "gap": 30.1}, 14.0)
    far = Rec({"ego_velocity": 33.0, "gap": 5.0}, 13.0)

    kept = distinct_failures([a, twin, far])

    assert len(kept) == 2, "the twin should have collapsed into the first"
    assert kept[0] is a, "the worst example of a group is the one kept"
    assert far in kept
