"""
OpenDRIVE geometry and `source: xodr` scenarios (Phase 4.2).

The map under test is tests/fixtures/xodr/orion_junction.xodr, hand-authored
for these tests. The claims that matter are the ones that fail quietly:
a curve drawn in the wrong place still produces a score, and a lane offset
with the wrong sign or a lane centred on the wrong line moves every lane
metric without an error anywhere (see METHODOLOGY's 4.3 change log).
"""

from __future__ import annotations

import math
import shutil
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest
from scipy.special import fresnel

from arep.config import get_config
from arep.core.observation import Observation
from arep.core.random_manager import RandomManager
from arep.core.state import Vector2D
from arep.execution.runner import EvaluationRunner
from arep.maps.xodr_parser import OpenDRIVEParser, _dense_geometry, load_map
from arep.models.examples.example_models import EmergencyBrakeModel
from arep.scenario.executor import ScenarioExecutor
from arep.scenario.osc_exporter import OpenSCENARIOExporter
from arep.scenario.parser import ScenarioParser
from arep.utils.exceptions import ScenarioParseError

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "xodr"
MAP = FIXTURES / "orion_junction.xodr"
SCENARIO = FIXTURES / "XODR-001_curved_signal_approach.yaml"


def _geometry(xml: str):
    return _dense_geometry(ET.fromstring(xml))


def _map():
    return OpenDRIVEParser().read(MAP.read_bytes(), MAP.name)


def _world():
    scenario, _ = ScenarioParser().parse_file(SCENARIO)
    world = ScenarioExecutor(get_config().simulation).create_initial_world(
        scenario, RandomManager(7)
    )
    return scenario, world


def _place(world, x, y, heading):
    placed = world.copy()
    ego = placed.ego_vehicle.copy()
    ego.position = Vector2D(x, y)
    ego.heading = heading
    placed.ego_vehicle = ego
    return placed


# ── Geometry against closed forms ────────────────────────────────────────


def test_arc_matches_the_circle():
    _, x, y, h = _geometry(
        '<geometry x="0" y="0" hdg="0" length="50"><arc curvature="0.02"/></geometry>'
    )
    assert x[-1] == pytest.approx(50 * math.sin(1.0), abs=1e-4)
    assert y[-1] == pytest.approx(50 * (1 - math.cos(1.0)), abs=1e-4)
    assert h[-1] == pytest.approx(1.0)


def test_spiral_matches_the_fresnel_integrals():
    """A clothoid from curvature 0 to k over L is the Fresnel curve scaled by
    a = sqrt(pi * L / k)."""
    _, x, y, h = _geometry(
        '<geometry x="0" y="0" hdg="0" length="30">'
        '<spiral curvStart="0" curvEnd="0.02"/></geometry>'
    )
    a = math.sqrt(math.pi * 30 / 0.02)
    s_term, c_term = fresnel(30 / a)
    assert x[-1] == pytest.approx(a * c_term, abs=1e-4)
    assert y[-1] == pytest.approx(a * s_term, abs=1e-4)
    assert h[-1] == pytest.approx(0.3)


def test_param_poly3_normalized_and_arc_length_draw_the_same_curve():
    """The same cubic written in both pRange conventions."""
    _, xn, yn, _ = _geometry(
        '<geometry x="1" y="2" hdg="0.4" length="40"><paramPoly3 aU="0" bU="40" '
        'cU="0" dU="0" aV="0" bV="0" cV="4" dV="-2" pRange="normalized"/></geometry>'
    )
    _, xa, ya, _ = _geometry(
        '<geometry x="1" y="2" hdg="0.4" length="40"><paramPoly3 aU="0" bU="1" '
        'cU="0" dU="0" aV="0" bV="0" cV="0.0025" dV="-0.00003125" '
        'pRange="arcLength"/></geometry>'
    )
    assert xn[-1] == pytest.approx(xa[-1], abs=1e-6)
    assert yn[-1] == pytest.approx(ya[-1], abs=1e-6)


def test_poly3_is_the_cubic_in_the_local_frame():
    _, x, y, h = _geometry(
        '<geometry x="0" y="0" hdg="0" length="30">'
        '<poly3 a="0" b="0" c="0.002" d="0"/></geometry>'
    )
    # every sample lies on v = 0.002 u^2, and the heading is its slope
    assert max(abs(yi - 0.002 * xi * xi) for xi, yi in zip(x, y)) < 1e-9
    assert h[-1] == pytest.approx(math.atan(0.004 * x[-1]))


def test_a_doctype_is_refused():
    """OpenDRIVE never needs a DTD; refusing one closes entity expansion."""
    with pytest.raises(ValueError, match="DOCTYPE"):
        OpenDRIVEParser().read(b'<!DOCTYPE x [<!ENTITY a "b">]><OpenDRIVE/>')


# ── The fixture map ──────────────────────────────────────────────────────


def test_the_fixture_map_parses_every_road_and_its_junction():
    xmap = _map()
    assert set(xmap.graph.segments) == {
        "road_1",
        "road_10",
        "road_11",
        "road_2",
        "road_3",
    }
    junction = xmap.graph.junctions["junction_100"]
    assert junction.has_traffic_light
    # inside the box the connecting roads span, not at an incoming road's start
    assert junction.position.distance_to(Vector2D(162.4, 54.7)) < 1.0


def test_what_is_not_modelled_is_reported():
    warnings = " | ".join(_map().warnings)
    assert "<object>" in warnings
    assert "static <signal>" in warnings


def test_a_static_sign_does_not_signalise_a_junction():
    """A stop sign read as a light would be a red light that never changes."""
    data = MAP.read_bytes().replace(b'dynamic="yes"', b'dynamic="no"')
    xmap = OpenDRIVEParser().read(data)
    assert not xmap.graph.junctions["junction_100"].has_traffic_light


def test_only_driving_lanes_and_oncoming_lanes_are_marked():
    road = _map().graph.segments["road_1"]
    assert road.lane_count == 2  # lane -2 is a sidewalk
    assert road.lane_width == pytest.approx(3.5)
    assert road.reversed_lanes == (1,)  # lane 1 runs against s under RHT


def test_a_one_sided_road_is_centred_on_its_lanes_not_its_reference_line():
    """Road 11 has only lane -1: its reference line is the lane's left edge.
    Centring the carriageway on the reference line would put the lane 1.75 m
    off, and every lane metric with it."""
    xmap = _map()
    segment = xmap.graph.segments["road_11"]
    x, y, h = xmap.lane_pose("11", 0.0, "-1")
    start = segment.get_lane_centerline(0)[0]
    assert start.distance_to(Vector2D(x, y)) < 0.01
    # and 1.75 m right of the reference line's start
    ref = Vector2D(154.074532, 52.595760)
    assert ref.distance_to(start) == pytest.approx(1.75, abs=0.01)


def test_left_hand_traffic_flips_which_lanes_are_oncoming():
    data = MAP.read_bytes().replace(
        b'id="1" junction="-1"', b'id="1" junction="-1" rule="LHT"'
    )
    assert OpenDRIVEParser().read(data).graph.segments["road_1"].reversed_lanes == (0,)


# ── Scenario wiring ──────────────────────────────────────────────────────


def test_the_scenario_places_the_ego_from_road_s_and_lane():
    scenario, world = _world()
    assert scenario.road.source == "xodr"
    assert (scenario.road.lanes, scenario.road.speed_limit) == (
        2,
        pytest.approx(50 / 3.6),
    )
    ego = world.ego_vehicle
    assert (ego.position.x, ego.position.y) == pytest.approx((15.0, -1.75))
    assert ego.heading == pytest.approx(0.0)
    obs = Observation.from_world_state(world)
    assert abs(obs.lane_offset) < 1e-6
    assert world.get_current_lane().lane_id == "road_1_lane_0"
    assert not world.road_graph.is_off_road(ego.position)


@pytest.mark.parametrize("s", [55.0, 90.0, 125.0, 155.0])
@pytest.mark.parametrize("lane", ["-1", "1"])
def test_observation_offset_is_zero_at_a_lane_centre_on_a_curve(s, lane):
    """Spiral, arc, spiral and cubic, in both directions of travel."""
    xmap = _map()
    _, world = _world()
    x, y, h = xmap.lane_pose("1", s, lane)
    obs = Observation.from_world_state(_place(world, x, y, h))
    assert abs(obs.lane_offset) < 0.02
    assert abs(obs.lane_heading_error) < 0.02
    expected = "road_1_lane_0" if lane == "-1" else "road_1_lane_1"
    assert _place(world, x, y, h).get_current_lane().lane_id == expected


@pytest.mark.parametrize("side, sign", [(-1.0, 1.0), (1.0, -1.0)])
def test_offset_sign_on_a_curve_is_right_positive(side, sign):
    """0.5 m to the right reads +0.5, to the left -0.5 -- on the arc, where a
    finite-difference normal pointing the wrong way would flip it."""
    xmap = _map()
    _, world = _world()
    x, y, h = xmap.lane_pose("1", 90.0, "-1")
    nx, ny = -math.sin(h), math.cos(h)  # left normal
    placed = _place(world, x + side * 0.5 * nx, y + side * 0.5 * ny, h)
    assert Observation.from_world_state(placed).lane_offset == pytest.approx(
        sign * 0.5, abs=0.02
    )


def test_the_signal_becomes_the_light_the_scenario_names():
    _, world = _world()
    assert [t.light_id for t in world.traffic_lights] == ["tl_junction_100"]


def test_the_scenario_runs_to_completion():
    """Stopping on a curve keeps the car on the road until the timeout."""
    result = EvaluationRunner().run_single(str(SCENARIO), EmergencyBrakeModel(), 4201)
    assert result.termination_reason not in ("off_road", "collision")
    assert result.duration == pytest.approx(30.0, abs=0.05)
    assert result.frame_hash


def test_the_same_seed_gives_the_same_frame_hash():
    a = EvaluationRunner().run_single(str(SCENARIO), EmergencyBrakeModel(), 3)
    b = EvaluationRunner().run_single(str(SCENARIO), EmergencyBrakeModel(), 3)
    assert a.frame_hash == b.frame_hash


def test_osc_export_refuses_a_map_scenario():
    """The map does not travel in the .osc; the re-import would be a flat road."""
    scenario, _ = ScenarioParser().parse_file(SCENARIO)
    with pytest.raises(ValueError, match="OpenDRIVE"):
        OpenSCENARIOExporter().export(scenario)


# ── Refusals: never a silent flat road ───────────────────────────────────


def _variant(tmp_path, old: str, new: str) -> Path:
    """A copy of the fixture scenario (and map) with one substitution."""
    lib = tmp_path / "lib" / "cat"
    lib.mkdir(parents=True)
    shutil.copy(MAP, lib / MAP.name)
    text = SCENARIO.read_text(encoding="utf-8")
    assert old in text
    path = lib / SCENARIO.name
    path.write_text(text.replace(old, new), encoding="utf-8")
    return path


@pytest.mark.parametrize(
    "old, new, message",
    [
        ('ego_start_road_id: "1"', 'ego_start_road_id: "99"', "road id"),
        ('ego_start_lane_id: "-1"', 'ego_start_lane_id: "-2"', "not a driving lane"),
        ("ego_start_s: 15.0", "ego_start_s: 500.0", "outside road"),
        ("file: orion_junction.xodr", "file: missing.xodr", "not found"),
        ("file: orion_junction.xodr", "file: ../../outside.xodr", "outside"),
        ("source: xodr", "source: osm", "Unknown road source"),
        ("    type: urban\n", "    type: urban\n    lanes: 2\n", "from the map"),
        ("    velocity: 11.11", "    x: 0.0\n    velocity: 11.11", "ego.initial.x"),
        ("    ego_start_s: 15.0\n", "", "requires"),
        ("parameterization:\n", "parameterization:\n  ego_x_jitter: 1.0\n", "world"),
    ],
)
def test_a_bad_reference_is_a_parse_error(tmp_path, old, new, message):
    with pytest.raises(ScenarioParseError, match=message):
        ScenarioParser().parse_file(_variant(tmp_path, old, new))


def test_a_scenario_string_cannot_resolve_a_map():
    with pytest.raises(ScenarioParseError, match="loaded from a file"):
        ScenarioParser().parse_string(SCENARIO.read_text(encoding="utf-8"))


def test_the_map_is_part_of_the_content_hash(tmp_path):
    path = _variant(tmp_path, "master_seed: 4201", "master_seed: 4201")
    _, before = ScenarioParser().parse_file(path)
    map_path = path.parent / MAP.name
    map_path.write_bytes(
        map_path.read_bytes().replace(b'max="50" unit="km/h"', b'max="60" unit="km/h"')
    )
    _, after = ScenarioParser().parse_file(path)
    assert before != after


def test_a_map_edited_after_parsing_is_refused_at_run_time(tmp_path):
    path = _variant(tmp_path, "master_seed: 4201", "master_seed: 4201")
    scenario, _ = ScenarioParser().parse_file(path)
    map_path = path.parent / MAP.name
    map_path.write_bytes(map_path.read_bytes() + b"\n")
    load_map.cache_clear()
    with pytest.raises(ScenarioParseError, match="changed"):
        ScenarioExecutor(get_config().simulation).create_initial_world(
            scenario, RandomManager(1)
        )
