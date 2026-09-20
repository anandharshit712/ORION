"""
Road topology tests (Phase 1.5).

core/road.py and core/road_templates.py were written months ago and never
connected to anything: nothing in simulation/, scenario/ or core/state.py
referenced RoadGraph, so every scenario ran on the same flat two-lane straight
road regardless of what it claimed to be modelling. An INT-* scenario named
"four way stop" executed on a straight line.

These tests cover the wiring: a scenario declares a template, the executor
builds the graph, and the graph — not a bundle of parallel lines — answers
"am I on the road" and "what is the limit here".

Backward compatibility is part of the contract. A scenario with no template
must produce byte-identical behaviour to before, because every stored result
was produced that way.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from arep.config import get_config                      # noqa: E402
from arep.core import road_templates                    # noqa: E402
from arep.core.state import Vector2D                    # noqa: E402
from arep.scenario.executor import ScenarioExecutor     # noqa: E402
from arep.scenario.parser import ScenarioParser         # noqa: E402
from arep.utils.exceptions import ScenarioParseError    # noqa: E402

REPO = Path(__file__).resolve().parent.parent
BASIC = str(REPO / "scenarios" / "basic" / "straight_road_lead_vehicle.yaml")
INT_SCENARIOS = sorted((REPO.parent / "scenarios" / "int").glob("*.yaml"))

TEMPLATES = [
    "highway_straight", "urban_straight", "t_junction",
    "four_way_intersection", "highway_onramp", "roundabout",
]


def _executor() -> ScenarioExecutor:
    return ScenarioExecutor(get_config())


def _scenario(path: str):
    return ScenarioParser().parse_file(path)[0]


# -- The templates themselves ---------------------------------------------

@pytest.mark.parametrize("name", TEMPLATES)
def test_every_template_builds_a_usable_graph(name):
    graph = getattr(road_templates, name)()

    assert graph.segments, f"{name} produced no segments"
    for segment in graph.segments.values():
        assert len(segment.centerline) >= 2, "a segment needs a direction"
        assert segment.lane_count >= 1
        assert segment.lane_width > 0
        assert segment.speed_limit > 0
        assert segment.length > 0


@pytest.mark.parametrize("name", TEMPLATES)
def test_every_template_places_lanes_inside_its_road(name):
    """A lane centreline outside its own segment would score every vehicle
    driving it as off-road."""
    graph = getattr(road_templates, name)()

    for segment in graph.segments.values():
        for lane_idx in range(segment.lane_count):
            centerline = segment.get_lane_centerline(lane_idx)
            assert len(centerline) == len(segment.centerline)
            midpoint = centerline[len(centerline) // 2]
            assert segment.contains_point(midpoint), (
                f"{name}/{segment.segment_id} lane {lane_idx} lies outside the road"
            )


def test_junction_templates_actually_have_junctions():
    assert road_templates.four_way_intersection().junctions
    assert road_templates.t_junction().junctions
    assert not road_templates.highway_straight().junctions


def test_lane_indices_are_bounds_checked():
    segment = next(iter(road_templates.highway_straight(lanes=2).segments.values()))
    with pytest.raises(ValueError):
        segment.get_lane_centerline(5)


# -- Scenario wiring ------------------------------------------------------

def test_a_scenario_without_a_template_gets_no_graph():
    """Every scenario written before 1.5 keeps the flat road it was scored on."""
    scenario = _scenario(BASIC)
    assert scenario.road.template is None
    assert _executor()._create_road_graph(scenario) is None


def test_a_scenario_without_a_template_keeps_its_old_lanes():
    scenario = _scenario(BASIC)
    lanes = _executor()._create_lanes(scenario, None)

    assert len(lanes) == scenario.road.lanes
    assert lanes[0].centerline_points[0].y == 0.0     # lane 0 on the travel line


def test_a_named_template_produces_a_graph():
    scenario = _scenario(BASIC)
    scenario.road.template = "four_way_intersection"
    graph = _executor()._create_road_graph(scenario)

    assert graph is not None
    assert len(graph.segments) == 4
    assert len(graph.junctions) == 1


def test_lanes_are_derived_from_the_graph_when_there_is_one():
    """Two geometries that can disagree is worse than one that is wrong."""
    scenario = _scenario(BASIC)
    scenario.road.template = "four_way_intersection"
    graph = _executor()._create_road_graph(scenario)
    lanes = _executor()._create_lanes(scenario, graph)

    expected = sum(seg.lane_count for seg in graph.segments.values())
    assert len(lanes) == expected
    assert all(lane.centerline_points for lane in lanes)


def test_template_params_reach_the_factory():
    scenario = _scenario(BASIC)
    scenario.road.template = "four_way_intersection"
    scenario.road.template_params = {"arm_length": 150.0}

    graph = _executor()._create_road_graph(scenario)
    longest = max(seg.length for seg in graph.segments.values())
    assert longest > 100.0, "arm_length was ignored"


def test_an_unknown_template_fails_at_build_time():
    """Better a refused scenario than a silent fallback to a straight road that
    scores a model on geometry it was never shown."""
    scenario = _scenario(BASIC)
    scenario.road.template = "figure_of_eight"

    with pytest.raises(ScenarioParseError, match="Unknown road template"):
        _executor()._create_road_graph(scenario)


def test_an_unknown_template_param_fails_loudly():
    """Silently dropping it would produce a road nobody asked for."""
    scenario = _scenario(BASIC)
    scenario.road.template = "four_way_intersection"
    scenario.road.template_params = {"arm_lenght": 150.0}      # typo

    with pytest.raises(ScenarioParseError, match="does not accept"):
        _executor()._create_road_graph(scenario)


def test_road_block_defaults_feed_the_template():
    """lane_width and speed_limit are declared once, on the road block."""
    scenario = _scenario(BASIC)
    scenario.road.template = "urban_straight"
    scenario.road.lane_width = 4.25
    scenario.road.speed_limit = 9.5

    graph = _executor()._create_road_graph(scenario)
    segment = next(iter(graph.segments.values()))
    assert segment.lane_width == 4.25
    assert segment.speed_limit == 9.5


# -- The graph changes behaviour ------------------------------------------

def test_off_road_uses_the_graph_when_one_is_present():
    """The point of the whole exercise: on a junction, the nearest-centreline
    test cannot tell the verge from another arm."""
    from arep.core.collision import CollisionDetector
    from arep.core.state import VehicleState, WorldState

    scenario = _scenario(BASIC)
    scenario.road.template = "four_way_intersection"
    graph = _executor()._create_road_graph(scenario)
    lanes = _executor()._create_lanes(scenario, graph)

    detector = CollisionDetector(get_config().simulation)

    def off_road_at(x: float, y: float) -> bool:
        world = WorldState(
            sim_time=0.0, timestep_count=0,
            ego_vehicle=VehicleState(position=Vector2D(x, y), velocity=5.0),
            lanes=lanes, road_graph=graph,
        )
        return detector.check_off_road(world.ego_vehicle, world)

    assert not off_road_at(0.0, -30.0), "on a southern arm, but reported off-road"
    assert not off_road_at(0.0, 0.0), "in the junction, but reported off-road"
    assert off_road_at(500.0, 500.0), "far outside the junction, but reported on-road"


def test_speed_limit_comes_from_the_segment():
    from arep.core.state import VehicleState, WorldState

    scenario = _scenario(BASIC)
    scenario.road.template = "urban_straight"
    scenario.road.speed_limit = 9.5
    graph = _executor()._create_road_graph(scenario)

    world = WorldState(
        sim_time=0.0, timestep_count=0,
        ego_vehicle=VehicleState(position=Vector2D(0.0, 0.0), velocity=5.0),
        lanes=_executor()._create_lanes(scenario, graph), road_graph=graph,
    )
    assert world.get_speed_limit() == 9.5


def test_a_world_without_a_graph_still_answers_off_road_the_old_way():
    """Backward compatibility is the contract: stored results were produced
    under the old rule."""
    from arep.core.collision import CollisionDetector
    from arep.core.state import VehicleState, WorldState

    scenario = _scenario(BASIC)
    lanes = _executor()._create_lanes(scenario, None)
    detector = CollisionDetector(get_config().simulation)

    on_lane = WorldState(
        sim_time=0.0, timestep_count=0,
        ego_vehicle=VehicleState(position=Vector2D(10.0, 0.0), velocity=5.0),
        lanes=lanes,
    )
    way_out = WorldState(
        sim_time=0.0, timestep_count=0,
        ego_vehicle=VehicleState(position=Vector2D(10.0, 40.0), velocity=5.0),
        lanes=lanes,
    )
    assert on_lane.road_graph is None
    assert not detector.check_off_road(on_lane.ego_vehicle, on_lane)
    assert detector.check_off_road(way_out.ego_vehicle, way_out)


# -- The scenarios this unblocks ------------------------------------------

def test_the_int_library_is_present():
    assert len(INT_SCENARIOS) >= 3, "intersection scenarios not found"


@pytest.mark.parametrize("path", INT_SCENARIOS, ids=lambda p: p.name)
def test_intersection_scenarios_declare_a_junction_topology(path):
    """They were executing on a flat straight road while claiming to be
    intersections."""
    scenario = _scenario(str(path))
    assert scenario.road.template, f"{path.name} still has no topology"

    graph = _executor()._create_road_graph(scenario)
    assert graph.junctions, f"{path.name} built a road with no junction"


@pytest.mark.parametrize("path", INT_SCENARIOS, ids=lambda p: p.name)
def test_intersection_scenarios_run_end_to_end(path):
    from arep.execution.runner import EvaluationRunner
    from arep.models.examples.example_models import EmergencyBrakeModel

    result = EvaluationRunner().run_batch(
        scenario_path=str(path), model=EmergencyBrakeModel(),
        num_runs=1, master_seed=42,
    )
    run = result.per_run_results[0]
    assert 0.0 <= run.composite_score <= 1.0
    assert run.duration > 0
