"""
OpenDRIVE maps this project did not write (Phase 4.2 / 4.4 fixture gap).

Every other map test reads tests/fixtures/xodr/orion_junction.xodr, which was
written alongside the parser, so a misreading shared by both would pass. These
three come unmodified from esmini (MPL-2.0; provenance in
fixtures/xodr/third_party/esmini/SOURCE.md). The strongest check is the
geometry: each planView record states where the next one starts, so the
parser's integrated end of one record must land on the start the authoring
tool wrote for the next.
"""

from __future__ import annotations

import hashlib
import math
import re
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from arep.execution.runner import EvaluationRunner
from arep.maps.xodr_parser import OpenDRIVEParser, _dense_geometry
from arep.models.examples.example_models import ReferenceDriverModel

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "xodr"
ESMINI = FIXTURES / "third_party" / "esmini"
MAPS = sorted(ESMINI.glob("*.xodr"))
SCENARIO = FIXTURES / "XODR-002_third_party_curves.yaml"


def _read(path: Path):
    return OpenDRIVEParser().read(path.read_bytes(), path.name)


def test_the_files_are_the_ones_source_md_names():
    """Unmodified is a licence condition and the point of the exercise."""
    recorded = dict(
        re.findall(
            r"`([\w.]+\.xodr)` \| `([0-9a-f]{64})`", (ESMINI / "SOURCE.md").read_text()
        )
    )
    assert sorted(recorded) == [p.name for p in MAPS]
    for path in MAPS:
        assert hashlib.sha256(path.read_bytes()).hexdigest() == recorded[path.name]


@pytest.mark.parametrize("path", MAPS, ids=lambda p: p.stem)
def test_every_road_in_the_file_becomes_a_segment(path):
    roads = ET.parse(path).getroot().findall("road")
    assert len(_read(path).graph.segments) == len(roads)


@pytest.mark.parametrize("path", MAPS, ids=lambda p: p.stem)
def test_each_geometry_ends_where_the_file_says_the_next_begins(path):
    joins = 0
    for road in ET.parse(path).getroot().iter("road"):
        records = list(road.find("planView"))
        for this, following in zip(records, records[1:]):
            _, x, y, hdg = _dense_geometry(this)
            gap = math.hypot(
                x[-1] - float(following.get("x")), y[-1] - float(following.get("y"))
            )
            turn = (hdg[-1] - float(following.get("hdg")) + math.pi) % (
                2 * math.pi
            ) - math.pi
            assert gap < 1e-3, f"road {road.get('id')}: {gap * 1000:.2f} mm gap"
            assert abs(turn) < 1e-6
            joins += 1
    assert joins > 0


def test_the_junction_with_dynamic_signals_is_signalised():
    junctions = _read(ESMINI / "fabriksgatan_traffic_lights.xodr").graph.junctions
    assert [(j.junction_type, j.has_traffic_light) for j in junctions.values()] == [
        ("4way", True)
    ]


def test_what_the_parser_does_not_model_is_reported_not_dropped():
    fabriksgatan = " | ".join(
        _read(ESMINI / "fabriksgatan_traffic_lights.xodr").warnings
    )
    assert "laneOffset not modelled" in fabriksgatan
    assert "<object>" in fabriksgatan
    e6mini = " | ".join(_read(ESMINI / "e6mini.xodr").warnings)
    assert "not contiguous" in e6mini  # the median, approximated as lane width


def test_a_lane_keeper_drives_the_third_party_road_without_leaving_it():
    result = EvaluationRunner().run_single(
        scenario_path=str(SCENARIO), model=ReferenceDriverModel(), master_seed=42
    )
    assert result.termination_reason not in ("off_road", "collision")
    assert result.duration == pytest.approx(20.0, abs=0.05)
