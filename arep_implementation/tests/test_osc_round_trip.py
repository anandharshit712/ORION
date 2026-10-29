"""
OpenSCENARIO 2.0 round trip across the whole library (Phase 4.4).

The roadmap criterion is "ORION → OSC → ORION preserves triggers and NPC
parameters". Checking it on LON-003 alone is how the parameterisation loss
went unnoticed for a phase, so this walks every scenario file and compares the
*entire* ScenarioDefinition, field by field. A field the exporter forgets —
including one added to the schema later — fails here by name instead of
passing by omission.

The second half is the import side against a file ORION did not write.
"""

from __future__ import annotations

import dataclasses
import logging
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from arep.scenario.osc_exporter import OpenSCENARIOExporter  # noqa: E402
from arep.scenario.osc_importer import OpenSCENARIOImporter  # noqa: E402
from arep.scenario.parser import ScenarioParser  # noqa: E402
from arep.scenario.schema import ScenarioDefinition  # noqa: E402
from arep.scenario.validator import ScenarioValidator  # noqa: E402
from arep.utils.exceptions import ScenarioValidationError  # noqa: E402

TESTS = Path(__file__).resolve().parent
LIBRARY = sorted((TESTS.parent.parent / "scenarios").glob("*/*.yaml"))
FIXTURE = TESTS / "fixtures" / "osc" / "cut_in_hand_authored.osc"
LON003 = TESTS.parent.parent / "scenarios" / "lon" / "LON-003_emergency_stop.yaml"

# Scenarios the parser refuses, and why. Asserted, not just skipped: if one
# starts loading, the test fails until it is removed from here and round-trips.
KNOWN_REFUSED = {
    "EMG-004": "DI-02: declares a change_weather event the engine cannot "
    "execute, so ScenarioValidator refuses it at load",
}


def _round_trip(scenario: ScenarioDefinition):
    osc = OpenSCENARIOExporter().export(scenario)
    return OpenSCENARIOImporter().read(osc, source=scenario.name)


def test_the_library_is_found():
    assert len(LIBRARY) >= 60


@pytest.mark.parametrize("path", LIBRARY, ids=lambda p: p.stem.split("_")[0])
def test_every_scenario_round_trips_exactly(path):
    scenario_id = path.stem.split("_")[0]
    if scenario_id in KNOWN_REFUSED:
        with pytest.raises(ScenarioValidationError):
            ScenarioParser().parse_file(path)
        pytest.skip(KNOWN_REFUSED[scenario_id])

    original, _ = ScenarioParser().parse_file(path)
    imported, skipped = _round_trip(original)

    assert skipped == [], f"importer skipped part of ORION's own export: {skipped}"
    before, after = dataclasses.asdict(original), dataclasses.asdict(imported)
    lost = sorted(k for k in before if before[k] != after[k])
    assert not lost, f"{scenario_id} changed in the round trip: {lost}"


def test_the_osc2_constructs_carry_their_fields_without_annotations():
    """The fields the spec maps to OSC2 must survive on the OSC2 alone.

    Otherwise the "OSC2 export" is an annotation with OSC2 decoration, and any
    other tool reading the file sees none of it.
    """
    original, _ = ScenarioParser().parse_file(LON003)
    osc = OpenSCENARIOExporter().export(original)
    stripped = "\n".join(
        line for line in osc.splitlines() if not line.strip().startswith("#@orion")
    )
    imported, skipped = OpenSCENARIOImporter().read(stripped)

    assert skipped == []
    assert imported.duration == original.duration
    assert imported.ego_initial == original.ego_initial
    assert imported.parameterization == original.parameterization

    before, after = original.traffic_objects[0], imported.traffic_objects[0]
    assert (after.id, after.type) == (before.id, before.type)
    assert after.initial == before.initial
    assert after.behavior.type == before.behavior.type
    for key in ("bt_type", "trigger_type", "trigger_value", "final_decel"):
        assert after.behavior.parameters[key] == before.behavior.parameters[key]


def test_integer_ranges_stay_integers():
    scenario = ScenarioDefinition(name="ints")
    scenario.parameterization = {"ego_x": {"min": 1, "max": 3}, "ego_y": 2}
    imported, _ = _round_trip(scenario)
    assert imported.parameterization == {"ego_x": {"min": 1, "max": 3}, "ego_y": 2}
    assert isinstance(imported.parameterization["ego_x"]["min"], int)


@pytest.mark.parametrize(
    "block",
    [
        {"ego_velocity": "fast"},
        {"ego_velocity": {"min": 1.0, "max": 2.0, "distribution": "normal"}},
        {"npc_overrides": {"lead-vehicle": {"initial_x": {"min": 1, "max": 2}}}},
    ],
)
def test_unexportable_parameterisation_is_refused_not_dropped(block):
    scenario = ScenarioDefinition(name="bad")
    scenario.parameterization = block
    with pytest.raises(ValueError):
        OpenSCENARIOExporter().export(scenario)


def test_a_non_identifier_npc_id_survives():
    scenario = ScenarioDefinition(name="ids")
    original, _ = ScenarioParser().parse_file(LON003)
    npc = original.traffic_objects[0]
    npc.id = "lead-vehicle"
    scenario.traffic_objects = [npc]
    imported, skipped = _round_trip(scenario)
    assert skipped == []
    assert imported.traffic_objects[0].id == "lead-vehicle"


# -- Third-party-style import --------------------------------------------


def _fixture():
    return OpenSCENARIOImporter().read(FIXTURE.read_text(encoding="utf-8"), "fixture")


def test_the_fixture_is_labelled_honestly():
    header = FIXTURE.read_text(encoding="utf-8").splitlines()[:3]
    assert "Hand-authored" in header[0]
    assert "NOT an ASAM sample" in header[0]


def test_hand_authored_cut_in_imports_what_orion_models():
    scenario, _ = _fixture()

    assert scenario.name == "cut_in_hand_authored"
    assert scenario.duration == 18.0
    assert scenario.termination.timeout == 18.0
    assert scenario.ego_initial.velocity == pytest.approx(80 / 3.6)
    assert [(o.id, o.type) for o in scenario.traffic_objects] == [("npc", "car")]

    npc = scenario.traffic_objects[0]
    assert npc.initial.velocity == pytest.approx(90 / 3.6)
    assert npc.behavior.type == "reactive_vehicle"
    params = npc.behavior.parameters
    assert params["bt_type"] == "hesitant_brake"
    assert (params["trigger_type"], params["trigger_value"]) == ("proximity", 20.0)
    assert params["final_decel"] == -5.0

    velocity = scenario.parameterization["ego_velocity"]
    assert velocity["min"] == pytest.approx(60 / 3.6)
    assert velocity["max"] == pytest.approx(100 / 3.6)
    assert ScenarioValidator().validate(scenario) == []


def test_hand_authored_cut_in_reports_everything_it_skips(caplog):
    """The cut-in itself (change_lane) is one of the losses. It has to be
    named: an imported cut-in without its cut-in still runs and still scores."""
    with caplog.at_level(logging.WARNING):
        _, skipped = _fixture()

    text = "\n".join(skipped)
    for construct in (
        "path.set_map",
        "path: Path",
        "lane(1, at: start)",
        "position(15m, behind: ego_vehicle, at: start)",
        "npc.change_lane",
        "time trigger 4.0",
        "cut_in_gap",
        "npc.drive(path): arguments not imported",
    ):
        assert construct in text, f"{construct!r} was dropped without a report"
    assert any("not imported" in r.message for r in caplog.records)
    assert any("change_lane" in r.message for r in caplog.records)


def test_a_condition_against_another_actor_is_not_an_ego_trigger():
    osc = (
        "scenario t:\n"
        "    ego: Vehicle\n"
        "    a: Vehicle\n"
        "    b: Vehicle\n"
        "    serial:\n"
        "        wait distance_to(a) < 5m\n"
        "        b.brake()\n"
    )
    scenario, skipped = OpenSCENARIOImporter().read(osc)
    assert "trigger_type" not in scenario.traffic_objects[1].behavior.parameters
    assert "wait distance_to(a) < 5m" in skipped


def test_a_bad_annotation_is_reported():
    osc = (
        "scenario t:\n"
        "    #@orion actor ghost {}\n"
        "    #@orion event {not json}\n"
        '    #@orion scenario {"no_such_field": 1}\n'
    )
    _, skipped = OpenSCENARIOImporter().read(osc)
    assert len(skipped) == 3
