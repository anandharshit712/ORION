"""
Scenario library validation (Phase 0.6, defect D-09).

A parameterised parse-and-validate pass over every YAML in the library. Until
now the only scenarios exercised by tests were the two in
arep_implementation/scenarios/basic/, so a typo in any of the eighteen
production scenarios stayed invisible until someone tried to run it — which for
the intersection and multi-agent categories is "not yet", since they need road
topology that does not exist.

That is precisely why this matters: a scenario nobody can execute is also a
scenario nobody notices is broken.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from arep.scenario.parser import ScenarioParser  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
LIBRARY = REPO_ROOT / "scenarios"
BASIC = Path(__file__).resolve().parent.parent / "scenarios" / "basic"

CATEGORIES = {"LON", "LAT", "INT", "VRU", "EMG", "MLT"}


def _all_scenarios() -> list[Path]:
    return sorted(LIBRARY.rglob("*.yaml")) + sorted(BASIC.rglob("*.yaml"))


ALL = _all_scenarios()


def test_the_library_is_actually_there():
    """Guard against the glob silently matching nothing and every test below
    vacuously passing."""
    assert len(ALL) >= 20, f"expected the full library, found {len(ALL)}"


@pytest.mark.parametrize("path", ALL, ids=lambda p: p.name)
def test_every_scenario_parses(path: Path):
    scenario, content_hash = ScenarioParser().parse_file(str(path))
    assert scenario is not None
    assert len(content_hash) == 64, "content hash is what versions a scenario"


@pytest.mark.parametrize("path", ALL, ids=lambda p: p.name)
def test_every_scenario_has_the_fields_execution_needs(path: Path):
    scenario, _ = ScenarioParser().parse_file(str(path))

    assert scenario.name, "a scenario without a name cannot be reported on"
    assert scenario.ego_initial is not None
    assert scenario.ego_constraints is not None
    assert scenario.road is not None
    assert scenario.road.lanes >= 1
    assert scenario.road.lane_width > 0
    assert scenario.road.speed_limit > 0
    assert scenario.duration > 0


@pytest.mark.parametrize("path", ALL, ids=lambda p: p.name)
def test_every_scenario_terminates(path: Path):
    """A scenario with no timeout can hang a worker until the wall-clock kill."""
    scenario, _ = ScenarioParser().parse_file(str(path))
    assert scenario.termination is not None
    assert scenario.termination.timeout > 0


@pytest.mark.parametrize(
    "path",
    [p for p in ALL if p.parent.name != "basic"],
    ids=lambda p: p.name,
)
def test_library_filenames_follow_the_naming_convention(path: Path):
    """[CATEGORY]-[SEQ]_description.yaml, and the directory must agree.

    The convention is load-bearing: the category prefix is how coverage is
    reported per behaviour class.
    """
    stem = path.stem
    assert "_" in stem, f"{stem} is missing the _description part"

    code = stem.split("_")[0]
    assert "-" in code, f"{code} is not [CATEGORY]-[SEQ]"

    category, seq = code.split("-", 1)
    assert category in CATEGORIES, f"{category} is not a known category"
    assert seq.isdigit(), f"{seq} is not a sequence number"
    assert (
        path.parent.name == category.lower()
    ), f"{path.name} sits in {path.parent.name}/ but declares {category}"


# Behaviour types the executor knows how to build (see _build_npc_behaviors).
KNOWN_BEHAVIOURS = {
    "constant_velocity",
    "reactive_vehicle",
    "reactive_pedestrian",
    "follow_lane",
    "scripted",
    "pedestrian",
}


@pytest.mark.parametrize("path", ALL, ids=lambda p: p.name)
def test_traffic_objects_declare_a_known_behaviour(path: Path):
    """A behaviour the simulator cannot build fails only at run time."""
    scenario, _ = ScenarioParser().parse_file(str(path))

    for obj in scenario.traffic_objects:
        assert obj.behavior.type in KNOWN_BEHAVIOURS, (
            f"{path.name}: traffic object '{obj.id}' declares unknown behaviour "
            f"'{obj.behavior.type}'"
        )


@pytest.mark.parametrize("path", ALL, ids=lambda p: p.name)
def test_reactive_objects_name_a_registered_behaviour_tree(path: Path):
    """reactive_* dispatches on bt_type, and get_bt() raises on an unknown one.

    A typo here is a ValueError deep inside a worker mid-batch, after the
    customer's credits have already been deducted.
    """
    from arep.simulation.npc_bt import _BT_REGISTRY

    scenario, _ = ScenarioParser().parse_file(str(path))

    for obj in scenario.traffic_objects:
        if obj.behavior.type not in ("reactive_vehicle", "reactive_pedestrian"):
            continue
        bt_type = obj.behavior.parameters.get("bt_type", "")
        assert bt_type in _BT_REGISTRY, (
            f"{path.name}: '{obj.id}' asks for bt_type '{bt_type}', "
            f"which is not registered. Available: {sorted(_BT_REGISTRY)}"
        )


def test_scenario_ids_are_unique_across_the_library():
    """Two scenarios sharing a code would silently overwrite each other in any
    per-scenario report."""
    codes = [p.stem.split("_")[0] for p in ALL if p.parent.name != "basic"]
    duplicates = {c for c in codes if codes.count(c) > 1}
    assert not duplicates, f"duplicate scenario codes: {duplicates}"


def test_content_hash_is_stable_across_parses():
    """The hash versions a scenario; if it moves, stored results lose their
    link to what produced them."""
    parser = ScenarioParser()
    path = str(ALL[0])
    assert parser.parse_file(path)[1] == parser.parse_file(path)[1]


def test_content_hash_differs_between_scenarios():
    parser = ScenarioParser()
    hashes = {parser.parse_file(str(p))[1] for p in ALL}
    assert len(hashes) == len(ALL), "two scenarios hash identically"


# ── Lane geometry ────────────────────────────────────────────────────────
#
# Added after the flat-road builder and RoadSegment.get_lane_centerline were
# found to disagree about where lane 0 sits: the flat path put it on y=0, the
# graph path on y=-1.75. 15 of the 21 production scenarios start the ego at
# y=-1.75, so on the flat path they straddled the lane line for their entire
# run and scored a lane-compliance fraction of exactly 0.0 — a scoring penalty
# with no behavioural cause. Nothing caught it because the suite ran on the two
# v1 fixtures in scenarios/basic/, which are the only ones that used y=0.


def test_both_lane_builders_agree_on_where_lane_zero_is():
    """The flat road and the road graph must lay out lanes identically.

    A scenario must not sit on different geometry depending on whether it
    happens to declare a `template`.
    """
    from arep.config import get_config
    from arep.core.road_templates import highway_straight
    from arep.scenario.executor import ScenarioExecutor

    lanes, width = 2, 3.5
    graph = highway_straight(lanes=lanes, lane_width=width, length=200.0)
    graph_ys = sorted(
        seg.get_lane_centerline(i)[0].y
        for seg in graph.segments.values()
        for i in range(seg.lane_count)
    )

    class _Road:
        pass

    road = _Road()
    road.lanes, road.lane_width, road.speed_limit = lanes, width, 27.8

    class _Scenario:
        pass

    scenario = _Scenario()
    scenario.road = road
    scenario.name = "lane-convention-check"

    executor = ScenarioExecutor(get_config().simulation)
    flat_ys = sorted(
        lane.centerline_points[0].y
        for lane in executor._create_lanes(scenario, road_graph=None)
    )

    assert flat_ys == pytest.approx(
        graph_ys
    ), f"flat road put lanes at {flat_ys}, road graph at {graph_ys}"


@pytest.mark.parametrize("path", ALL, ids=lambda p: p.name)
def test_every_scenario_starts_the_ego_inside_a_lane(path: Path):
    """The ego must begin the run within its lane, body included.

    This is the same body-edge test lane compliance scores with
    (|offset| + half_width <= lane_width / 2), so a scenario failing here is one
    that starts already out of lane and is scored down for the whole run.
    """
    from arep.config import get_config
    from arep.core.random_manager import RandomManager
    from arep.scenario.executor import ScenarioExecutor

    scenario, _ = ScenarioParser().parse_file(str(path))
    world = ScenarioExecutor(get_config().simulation).create_initial_world(
        scenario,
        RandomManager(42),
    )

    lane = world.get_current_lane()
    assert lane is not None, "no lane under the ego at t=0"

    offset = lane.get_signed_lateral_offset(world.ego_vehicle.position)
    half_width = world.ego_vehicle.width / 2.0
    assert abs(offset) + half_width <= lane.width / 2.0 + 1e-6, (
        f"ego starts straddling the lane line: offset={offset:+.3f} m, "
        f"half-width={half_width:.3f} m, lane width={lane.width:.3f} m"
    )


# The production library only. LIBRARY and BASIC both sit under a directory
# called "scenarios", so they cannot be told apart by name.
PRODUCTION = [p for p in ALL if LIBRARY in p.parents]


# ── Parameterisation (docs/ARCHITECTURE.md §1.6.1) ───────────────────────
#
# The schema always listed a "Parameterization Profile" as required, and it was
# never enforced: by 2026-09-24 eleven of the twenty-one production scenarios
# had no `parameterization:` block. Those could be run but not *searched* —
# adversarial search varies declared ranges, so with none declared it returns
# immediately. Half the library was invisible to the feature built to find its
# hardest cases.


@pytest.mark.parametrize(
    "path",
    PRODUCTION,
    ids=lambda p: p.name,
)
def test_every_production_scenario_declares_ranges(path: Path):
    """A scenario with no ranges is one fixed situation, not a test.

    The two v1 fixtures under arep_implementation/scenarios/basic/ are exempt:
    they exist to pin engine behaviour, not to challenge a model.
    """
    from arep.search.space import SearchSpace

    scenario, _ = ScenarioParser().parse_file(str(path))
    n_dims = SearchSpace(scenario).n_dims

    assert n_dims > 0, (
        f"{path.name} declares no parameterization ranges, so adversarial "
        f"search has nothing to explore and will return immediately"
    )


@pytest.mark.parametrize(
    "path",
    PRODUCTION,
    ids=lambda p: p.name,
)
def test_declared_ranges_are_ordered_and_non_empty(path: Path):
    """min < max, always.

    An inverted range samples nothing meaningful, and an equal one is a scalar
    wearing a range's clothes — it would count as a search dimension while
    having nothing to search.
    """
    from arep.search.space import SearchSpace

    scenario, _ = ScenarioParser().parse_file(str(path))

    for dim in SearchSpace(scenario).dimensions:
        assert dim.low < dim.high, (
            f"{path.name}: range {dim.name} is [{dim.low}, {dim.high}] — "
            f"min must be strictly less than max"
        )
