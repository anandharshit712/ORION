"""
OpenDRIVE and OpenSCENARIO interoperability tests (Phase 4).

These importers exist so a customer can bring the maps and scenarios they
already have instead of re-authoring them. Both cover a deliberate subset:
the full standards describe geometry and composition this engine cannot
execute, and accepting them silently would hand back a scenario that runs but
does not test what the file describes.

So the contract under test is as much about what is *refused and reported* as
what is read. A dropped hazard still produces a score, which is the dangerous
failure.
"""

from __future__ import annotations

import logging
import os
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from arep.maps.xodr_parser import OpenDRIVEParser          # noqa: E402
from arep.scenario.osc_exporter import OpenSCENARIOExporter  # noqa: E402
from arep.scenario.osc_importer import OpenSCENARIOImporter  # noqa: E402
from arep.scenario.parser import ScenarioParser            # noqa: E402

LON003 = "../scenarios/lon/LON-003_emergency_stop.yaml"

XODR = """<?xml version="1.0"?>
<OpenDRIVE>
  <header revMajor="1" revMinor="7"/>
  <road name="main" length="100" id="1" junction="-1">
    <type s="0" type="motorway"><speed max="120" unit="km/h"/></type>
    <planView>
      <geometry s="0" x="0" y="0" hdg="0" length="60"><line/></geometry>
      <geometry s="60" x="60" y="0" hdg="0" length="40"><arc curvature="0.02"/></geometry>
    </planView>
    <lanes><laneSection s="0"><right>
      <lane id="-1" type="driving"><width sOffset="0" a="3.75"/></lane>
      <lane id="-2" type="driving"><width sOffset="0" a="3.75"/></lane>
      <lane id="-3" type="sidewalk"><width sOffset="0" a="2.0"/></lane>
    </right></laneSection></lanes>
  </road>
  <road name="side" length="50" id="2" junction="10">
    <planView><geometry s="0" x="100" y="-50" hdg="1.5708" length="50"><line/></geometry></planView>
    <lanes><laneSection s="0"><right>
      <lane id="-1" type="driving"><width a="3.5"/></lane>
    </right></laneSection></lanes>
    <signals><signal id="9" name="light"/></signals>
  </road>
  <junction id="10" name="jct">
    <connection id="0" incomingRoad="1" connectingRoad="2"/>
    <priority high="1" low="2"/>
  </junction>
</OpenDRIVE>"""


@pytest.fixture
def xodr_file():
    with tempfile.NamedTemporaryFile("w", suffix=".xodr", delete=False,
                                     encoding="utf-8") as handle:
        handle.write(XODR)
        path = handle.name
    yield path
    os.unlink(path)


# -- OpenDRIVE ------------------------------------------------------------

def test_a_map_becomes_a_road_graph(xodr_file):
    graph = OpenDRIVEParser().parse(xodr_file)
    assert len(graph.segments) == 2
    assert len(graph.junctions) == 1


def test_only_driving_lanes_are_counted(xodr_file):
    """Counting the sidewalk would widen the road the ego may occupy, and
    off-road detection reads that width."""
    graph = OpenDRIVEParser().parse(xodr_file)
    assert graph.segments["road_1"].lane_count == 2
    assert graph.segments["road_1"].lane_width == pytest.approx(3.75)


def test_speed_units_are_converted(xodr_file):
    """120 km/h declared, metres per second everywhere inside ORION."""
    graph = OpenDRIVEParser().parse(xodr_file)
    assert graph.segments["road_1"].speed_limit == pytest.approx(33.33, abs=0.01)


def test_arc_geometry_actually_curves(xodr_file):
    """Straight-lining an arc would put the road somewhere it is not."""
    graph = OpenDRIVEParser().parse(xodr_file)
    centerline = graph.segments["road_1"].centerline
    assert abs(centerline[-1].y) > 1.0


def test_an_arc_with_no_curvature_is_a_straight_line():
    points = OpenDRIVEParser._discretise_arc(0.0, 0.0, 0.0, 10.0, 0.0)
    assert all(abs(p.y) < 1e-9 for p in points)


def test_junction_right_of_way_defaults_to_yield(xodr_file):
    """Assuming priority the map does not grant is the dangerous default."""
    graph = OpenDRIVEParser().parse(xodr_file)
    junction = graph.junctions["junction_10"]
    assert junction.right_of_way["road_1"] == "priority"   # declared high
    assert junction.right_of_way["road_2"] == "yield"      # not declared


def test_a_signal_marks_the_junction_as_signalised(xodr_file):
    graph = OpenDRIVEParser().parse(xodr_file)
    assert graph.junctions["junction_10"].has_traffic_light


def test_unsupported_geometry_is_skipped_and_reported(caplog):
    """A vendor map will contain spirals this subset does not model. Refusing
    the whole file would make the importer useless for its real inputs."""
    xodr = XODR.replace('<arc curvature="0.02"/>', "<spiral curvStart='0' curvEnd='0.1'/>")
    with tempfile.NamedTemporaryFile("w", suffix=".xodr", delete=False,
                                     encoding="utf-8") as handle:
        handle.write(xodr)
        path = handle.name
    try:
        with caplog.at_level(logging.WARNING):
            graph = OpenDRIVEParser().parse(path)
        assert graph.segments, "the rest of the map should still load"
        assert any("unsupported geometry" in r.message.lower() for r in caplog.records)
    finally:
        os.unlink(path)


def test_a_missing_map_file_raises():
    with pytest.raises(FileNotFoundError):
        OpenDRIVEParser().parse("no-such-map.xodr")


def test_malformed_xml_says_so():
    with tempfile.NamedTemporaryFile("w", suffix=".xodr", delete=False,
                                     encoding="utf-8") as handle:
        handle.write("<OpenDRIVE><road>")
        path = handle.name
    try:
        with pytest.raises(ValueError, match="not well-formed"):
            OpenDRIVEParser().parse(path)
    finally:
        os.unlink(path)


def test_a_map_with_no_usable_roads_raises_rather_than_returning_empty():
    """An empty graph would make every position off-road, which reads as a
    model failure rather than a bad import."""
    with tempfile.NamedTemporaryFile("w", suffix=".xodr", delete=False,
                                     encoding="utf-8") as handle:
        handle.write("<OpenDRIVE><header/></OpenDRIVE>")
        path = handle.name
    try:
        with pytest.raises(ValueError, match="no usable road segments"):
            OpenDRIVEParser().parse(path)
    finally:
        os.unlink(path)


def test_an_imported_map_works_with_the_simulation():
    """The point of the importer: the result is a RoadGraph like any other."""
    with tempfile.NamedTemporaryFile("w", suffix=".xodr", delete=False,
                                     encoding="utf-8") as handle:
        handle.write(XODR)
        path = handle.name
    try:
        graph = OpenDRIVEParser().parse(path)
        from arep.core.state import Vector2D

        assert graph.get_ego_segment(Vector2D(10.0, 0.0)) is not None
        assert graph.is_off_road(Vector2D(10_000.0, 10_000.0))
        assert graph.get_speed_limit_at(Vector2D(10.0, 0.0)) > 0
    finally:
        os.unlink(path)


# -- OpenSCENARIO export --------------------------------------------------

def test_export_names_the_scenario_and_its_actors():
    scenario, _ = ScenarioParser().parse_file(LON003)
    osc = OpenSCENARIOExporter().export(scenario)

    assert "scenario LON_003" in osc
    assert "ego: Vehicle" in osc
    assert "lead_vehicle: Vehicle" in osc


def test_export_carries_the_trigger():
    scenario, _ = ScenarioParser().parse_file(LON003)
    osc = OpenSCENARIOExporter().export(scenario)
    assert "wait time_to_collision" in osc


def test_export_flags_what_it_cannot_express():
    """An exported scenario that quietly loses a behaviour is worse than no
    export: the recipient runs it believing it is the same test."""
    scenario, _ = ScenarioParser().parse_file(LON003)
    osc = OpenSCENARIOExporter().export(scenario)
    assert "no direct equivalent" in osc or "not represented" in osc


def test_export_records_the_parameter_ranges():
    scenario, _ = ScenarioParser().parse_file(LON003)
    osc = OpenSCENARIOExporter().export(scenario)
    assert "ego_velocity" in osc


def test_export_produces_a_safe_identifier():
    """Scenario names carry spaces, dashes and em-dashes; OSC2 identifiers
    cannot."""
    scenario, _ = ScenarioParser().parse_file(LON003)
    osc = OpenSCENARIOExporter().export(scenario)
    declaration = next(line for line in osc.splitlines()
                       if line.startswith("scenario "))
    identifier = declaration[len("scenario "):-1]
    assert identifier.replace("_", "").isalnum()


def test_export_to_file_writes_it(tmp_path):
    scenario, _ = ScenarioParser().parse_file(LON003)
    target = tmp_path / "nested" / "scenario.osc"
    OpenSCENARIOExporter().export_to_file(scenario, str(target))
    assert target.exists()
    assert "scenario " in target.read_text(encoding="utf-8")


# -- OpenSCENARIO import --------------------------------------------------

def test_import_reads_actors_and_behaviour():
    osc = """
import basic.osc

scenario cut_in_test:
    ego: Vehicle
    other_car: Vehicle

    do parallel:
        ego.drive() with:
            speed(20.00mps)

        serial:
            wait elapsed(3.00s)
            other_car.brake() with:
                deceleration(6.50mpsps)
"""
    scenario = OpenSCENARIOImporter().import_string(osc)

    assert scenario.name == "cut_in_test"
    assert [o.id for o in scenario.traffic_objects] == ["other_car"]

    npc = scenario.traffic_objects[0]
    assert npc.behavior.parameters["bt_type"] == "hesitant_brake"
    assert npc.behavior.parameters["trigger_type"] == "time"
    assert npc.behavior.parameters["trigger_value"] == 3.0
    # OSC2 states deceleration as a magnitude; ORION signs it.
    assert npc.behavior.parameters["final_decel"] == -6.5


def test_import_maps_each_condition_type():
    for condition, expected_type, expected_value in [
        ("elapsed(2.50s)", "time", 2.5),
        ("time_to_collision(ego) < 1.80s", "ttc", 1.8),
        ("distance_to(ego) < 25.00m", "proximity", 25.0),
    ]:
        osc = (
            "scenario t:\n"
            "    ego: Vehicle\n"
            "    npc: Vehicle\n"
            "    do parallel:\n"
            "        serial:\n"
            f"            wait {condition}\n"
            "            npc.brake()\n"
        )
        scenario = OpenSCENARIOImporter().import_string(osc)
        params = scenario.traffic_objects[0].behavior.parameters
        assert params["trigger_type"] == expected_type
        assert params["trigger_value"] == expected_value


def test_a_pedestrian_actor_keeps_its_type():
    osc = "scenario t:\n    ego: Vehicle\n    walker: Pedestrian\n"
    scenario = OpenSCENARIOImporter().import_string(osc)
    assert scenario.traffic_objects[0].type == "pedestrian"


def test_the_ego_is_not_imported_as_traffic():
    osc = "scenario t:\n    ego: Vehicle\n    npc: Vehicle\n"
    scenario = OpenSCENARIOImporter().import_string(osc)
    assert [o.id for o in scenario.traffic_objects] == ["npc"]


def test_unsupported_constructs_are_named_in_the_log(caplog):
    """A scenario missing its hazard still runs and still produces a score."""
    osc = (
        "scenario t:\n"
        "    ego: Vehicle\n"
        "    npc: Vehicle\n"
        "    do parallel:\n"
        "        npc.follow_trajectory(spline_42)\n"
    )
    with caplog.at_level(logging.WARNING):
        OpenSCENARIOImporter().import_string(osc)

    assert any("not imported" in r.message for r in caplog.records)
    assert any("follow_trajectory" in r.message for r in caplog.records)


def test_a_file_with_no_scenario_declaration_raises():
    with pytest.raises(ValueError, match="declares no scenario"):
        OpenSCENARIOImporter().import_string("ego: Vehicle\n")


def test_a_missing_scenario_file_raises():
    with pytest.raises(FileNotFoundError):
        OpenSCENARIOImporter().import_file("no-such-scenario.osc")


def test_export_then_import_preserves_the_essentials():
    """The round trip is the claim customers care about."""
    original, _ = ScenarioParser().parse_file(LON003)
    osc = OpenSCENARIOExporter().export(original)
    imported = OpenSCENARIOImporter().import_string(osc, source="round-trip")

    assert imported.name.startswith("LON_003")
    assert [o.id for o in imported.traffic_objects] == \
           [o.id for o in original.traffic_objects]

    npc = imported.traffic_objects[0]
    assert npc.behavior.parameters["bt_type"] == "hesitant_brake"
    assert npc.behavior.parameters["trigger_type"] == "ttc"


def test_the_round_trip_is_lossy_and_says_so():
    """Stated rather than implied: the parameterisation block does not
    survive, because OSC2 parameter declarations are written as comments."""
    original, _ = ScenarioParser().parse_file(LON003)
    imported = OpenSCENARIOImporter().import_string(
        OpenSCENARIOExporter().export(original),
    )
    assert original.parameterization
    assert not imported.parameterization, (
        "if this starts surviving, update the docstring that says it does not"
    )
