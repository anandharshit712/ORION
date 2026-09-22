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
