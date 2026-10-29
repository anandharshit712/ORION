"""Every NPC behaviour a scenario declares must actually run.

Found after Phase 4: eleven pedestrians in nine scenarios named a behaviour tree
under `type: pedestrian`, and only `reactive_*` types dispatched to one, so they
walked straight lines. Under that, seven of them called the hesitation knob
`hesitate_prob` (the tree reads `mid_hesitation_prob`), the erratic ones called
their speed `walk_speed` (the tree reads `walk_speed_range`), MLT-005's tailgater
sampled a `target_gap` its tree never looked at, and LON-001 sampled an
`initial_decel` its script never read. Each scenario still ran and still scored
-- against a hazard it did not have.

So the rule, checked against source rather than a hand-kept list: every
parameter a scenario declares or overrides for an NPC is one that NPC's
behaviour reads. A tree or script that starts reading a new key is picked up
automatically; a scenario that names a key nobody reads fails here.
"""

from __future__ import annotations

import inspect
import re
from pathlib import Path

import pytest
import yaml

from arep.config import get_config
from arep.core.random_manager import RandomManager
from arep.core.state import Vector2D
from arep.scenario.executor import ScenarioExecutor
from arep.scenario.parser import ScenarioParser
from arep.scenario.validator import ScenarioValidator
from arep.simulation import npc_bt
from arep.simulation.world import WorldManager

LIBRARY = Path(__file__).resolve().parents[2] / "scenarios"
SCENARIOS = sorted(LIBRARY.glob("*/*.yaml"))

_READ = re.compile(r"""params(?:\.get\(|\[)\s*["'](\w+)["']""")


def _reads(*objs) -> set[str]:
    return {key for obj in objs for key in _READ.findall(inspect.getsource(obj))}


_TRIGGER = _reads(npc_bt._check_trigger) | {"bt_type"}
TREE_READS = {
    name: _reads(type(tree)) | _TRIGGER for name, tree in npc_bt._BT_REGISTRY.items()
}
SCRIPTED_READS = _reads(
    WorldManager._update_scripted,
    WorldManager._apply_longitudinal,
    WorldManager._apply_cut_in,
)


def test_the_source_scan_sees_the_keys_it_should():
    """Guard the guard: a regex that silently matched nothing would pass everything."""
    assert {"walk_speed", "mid_hesitation_prob"} <= TREE_READS["cautious_pedestrian"]
    assert {"target_gap", "target_ttc"} <= TREE_READS["adaptive_tailgate"]
    assert {"start_velocity", "post_acceleration", "lateral_speed"} <= SCRIPTED_READS


@pytest.mark.parametrize("path", SCENARIOS, ids=lambda p: p.stem[:7])
def test_every_declared_npc_parameter_is_read(path):
    doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    overrides = (doc.get("parameterization") or {}).get("npc_overrides") or {}
    unread = []
    for obj in doc.get("traffic") or []:
        behavior = obj.get("behavior") or {}
        params = set(behavior.get("parameters") or {})
        params |= set((overrides.get(obj["id"]) or {}).get("parameters") or {})
        bt_type = (behavior.get("parameters") or {}).get("bt_type")
        if bt_type:
            reads = TREE_READS[bt_type]
        elif behavior.get("type") == "scripted":
            reads = SCRIPTED_READS
        else:
            reads = set()  # constant velocity reads nothing
        if params - reads:
            unread.append(f"{obj['id']}: {sorted(params - reads)}")
    assert not unread, f"{path.name} declares parameters nothing reads: {unread}"


def _world(scenario_path):
    scenario, _ = ScenarioParser().parse_file(str(scenario_path))
    executor = ScenarioExecutor(get_config().simulation)
    return executor.create_initial_world(scenario, RandomManager(1))


def test_a_pedestrian_typed_npc_runs_its_tree():
    """VRU-006 declares `type: pedestrian` + cautious_pedestrian. The tree waits
    at the kerb until triggered; the old constant-velocity fallback walked off
    on the first tick."""
    world = _world(next(LIBRARY.glob("vru/VRU-006_*.yaml")))
    assert world.npc_behaviors["stepping_pedestrian"]["bt_type"] == (
        "cautious_pedestrian"
    )
    # Push the ego far away so the proximity trigger cannot fire.
    world.ego_vehicle = world.ego_vehicle.copy()
    world.ego_vehicle.position = Vector2D(-500.0, 0.0)
    before = world.get_object_by_id("stepping_pedestrian").position
    after_world = WorldManager(get_config().simulation).update_dynamic_objects(
        world, 0.02, RandomManager(1)
    )
    assert after_world.get_object_by_id("stepping_pedestrian").position == before


def test_an_unknown_tree_is_refused_at_load():
    scenario, _ = ScenarioParser().parse_file(
        str(next(LIBRARY.glob("vru/VRU-006_*.yaml")))
    )
    scenario.traffic_objects[0].behavior.parameters["bt_type"] = "nonexistent"
    errors = ScenarioValidator().validate(scenario)
    assert any("unknown bt_type 'nonexistent'" in e for e in errors)


def test_a_script_and_a_tree_on_one_npc_is_refused():
    scenario, _ = ScenarioParser().parse_file(
        str(next(LIBRARY.glob("lon/LON-001_*.yaml")))
    )
    scenario.traffic_objects[0].behavior.parameters["bt_type"] = "hesitant_brake"
    errors = ScenarioValidator().validate(scenario)
    assert any("only one of them can drive it" in e for e in errors)
