"""
ORION OpenDRIVE Map Parser.  [Phase 4.2]

Parses a subset of the OpenDRIVE (.xodr) format into an AREP RoadGraph.
Uses Python's built-in xml.etree.ElementTree — no external XML dependencies.

Supported OpenDRIVE elements:
  <road> planView: line, arc, spiral, poly3, paramPoly3      ✅
  <laneSection> driving lanes (first section of each road)    ✅
  <junction> with connection roads                            ✅
  <signal dynamic="yes"> (traffic lights) at a junction       ✅
  <object> (static obstacles)                                 ⚠ counted and reported, not imported
  laneOffset, width tapers, later laneSections                ⚠ reported, not modelled
  Superelevation, banking, elevation                          ❌ out of scope

Everything not modelled is skipped *and reported*: logged as a warning and
listed on ``XodrMap.warnings``. A road whose plan view contains a geometry this
subset cannot place is dropped whole — interpolating across the gap would put
road where the map has none.

How a road becomes a RoadSegment
--------------------------------
The OpenDRIVE reference line is generally *not* the middle of the carriageway:
a one-way road with lanes -1 and -2 has its reference line on the left edge.
ORION's RoadSegment centres its lanes on the centreline with
``(i - (n-1)/2) * lane_width``, so the segment centreline is the reference line
offset (along the true normal) to the middle of the driving lanes, and
``lane_width`` is the driving span divided by the lane count. For contiguous
equal-width driving lanes — the ordinary case — every lane centre lands exactly
where the map puts it.

ORION lane index ``i`` counts from the rightmost driving lane (index 0) to the
leftmost, matching ``RoadSegment.get_lane_centerline``. Lanes that travel
against the reference line (positive ids under right-hand traffic, negative
under ``rule="LHT"``) are listed in ``RoadSegment.reversed_lanes``; the scenario
executor reverses their centrelines so the lane a model is measured against runs
the way traffic in it drives.

Reference: ASAM OpenDRIVE 1.7 specification
"""

from __future__ import annotations

import hashlib
import math
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np

from arep.core.road import Junction, RoadGraph, RoadSegment
from arep.core.state import Vector2D
from arep.utils.logging_config import get_logger

logger = get_logger("maps.xodr_parser")

# Discretisation step for centerline generation (metres)
CENTERLINE_STEP_M = 1.0
# Integration step for curved geometry. Trapezoid error on an arc of curvature
# k over length L is about L * step^2 * k^2 / 12: under a millimetre for any
# road a car can drive.
DENSE_STEP_M = 0.05
SUPPORTED_GEOMETRY = ("line", "arc", "spiral", "poly3", "paramPoly3")


@dataclass
class _Road:
    """One parsed road: dense reference line plus its driving-lane layout."""

    s: np.ndarray
    x: np.ndarray
    y: np.ndarray
    hdg: np.ndarray
    t_mid: float
    lane_width: float
    lane_count: int
    index_of: Dict[str, int]  # OpenDRIVE lane id -> ORION lane index
    reversed_lanes: Tuple[int, ...]

    @property
    def length(self) -> float:
        return float(self.s[-1])


@dataclass
class XodrMap:
    """A parsed map: the graph, the per-road data to place things on it, and
    everything the parser could not model."""

    graph: RoadGraph
    roads: Dict[str, _Road] = field(default_factory=dict)
    warnings: List[str] = field(default_factory=list)

    def lane_pose(
        self, road_id: str, s: float, lane_id: str
    ) -> Tuple[float, float, float]:
        """World (x, y, heading) at the centre of a driving lane, ``s`` metres
        along the road's reference line. Heading is the lane's direction of
        travel. Raises ValueError naming what is valid when it is not."""
        road = self.roads.get(str(road_id))
        if road is None:
            known = sorted(self.roads)
            raise ValueError(
                f"road id {road_id!r} is not a parsed road in this map; "
                f"known: {known[:20]}{' ...' if len(known) > 20 else ''}"
            )
        if not 0.0 <= s <= road.length:
            raise ValueError(
                f"s={s} is outside road {road_id!r} (length {road.length:.2f} m)"
            )
        index = road.index_of.get(str(lane_id))
        if index is None:
            raise ValueError(
                f"lane id {lane_id!r} is not a driving lane of road {road_id!r}; "
                f"driving lanes: {sorted(road.index_of, key=int)}"
            )
        h_ref = float(np.interp(s, road.s, road.hdg))
        t = road.t_mid + (index - (road.lane_count - 1) / 2.0) * road.lane_width
        x = float(np.interp(s, road.s, road.x)) - t * math.sin(h_ref)
        y = float(np.interp(s, road.s, road.y)) + t * math.cos(h_ref)
        h = h_ref + (math.pi if index in road.reversed_lanes else 0.0)
        return x, y, math.atan2(math.sin(h), math.cos(h))


class OpenDRIVEParser:
    """
    Parses a .xodr file and returns an AREP RoadGraph.

    Only the subset of OpenDRIVE needed for evaluation scenarios is
    implemented. What is not modelled is logged and collected in ``warnings``.
    """

    def __init__(self) -> None:
        self.warnings: List[str] = []

    def parse(self, xodr_path: str) -> RoadGraph:
        """Parse a .xodr file and return its RoadGraph."""
        path = Path(xodr_path)
        if not path.exists():
            raise FileNotFoundError(f"OpenDRIVE file not found: {xodr_path}")
        return self.read(path.read_bytes(), path.name).graph

    def read(self, data: bytes, name: str = "map.xodr") -> XodrMap:
        """Parse OpenDRIVE bytes into an XodrMap.

        Raises ValueError for malformed XML, a DOCTYPE, or a map with no usable
        road. Unsupported content inside an otherwise usable map is skipped and
        reported rather than failing the file: a vendor map always contains
        something this subset does not model.
        """
        # OpenDRIVE never needs a DTD. Refusing one closes entity-expansion
        # attacks without a dependency, whatever expat version is underneath.
        if b"<!DOCTYPE" in data or b"<!ENTITY" in data:
            raise ValueError(f"{name} declares a DOCTYPE/ENTITY; refused")
        logger.info("Parsing OpenDRIVE file: %s", name)
        try:
            root = ET.fromstring(data)
        except ET.ParseError as exc:
            raise ValueError(f"{name} is not well-formed XML: {exc}") from exc

        xmap = XodrMap(graph=RoadGraph(), warnings=self.warnings)
        for road_el in root.findall("road"):
            road_id = road_el.get("id", "")
            parsed = self._parse_road(road_el, road_id)
            if parsed is not None:
                xmap.roads[road_id] = parsed[0]
                xmap.graph.segments[parsed[1].segment_id] = parsed[1]

        if not xmap.graph.segments:
            raise ValueError(
                f"{name} produced no usable road segments; "
                f"supported geometry is {', '.join(SUPPORTED_GEOMETRY)}. "
                f"Reported: {self.warnings}"
            )

        junction_roads = set()
        for junction_el in root.findall("junction"):
            junction = self._parse_junction(junction_el, root, xmap.graph)
            if junction is not None:
                xmap.graph.junctions[junction.junction_id] = junction
                junction_roads.update(junction.arms)

        self._report_unmodelled(root, junction_roads)
        logger.info("Parsed %s: %s", name, xmap.graph.summary())
        return xmap

    # ── Reporting ────────────────────────────────────────────────────

    def _warn(self, message: str) -> None:
        self.warnings.append(message)
        logger.warning(message)

    def _report_unmodelled(self, root: ET.Element, junction_roads: set) -> None:
        objects = root.findall("road/objects/object")
        if objects:
            self._warn(
                f"{len(objects)} <object> element(s) not imported: static "
                f"obstacles from the map are not placed in the world"
            )
        static = 0
        for road_el in root.findall("road"):
            for signal in road_el.findall("signals/signal"):
                if signal.get("dynamic") != "yes":
                    static += 1
                elif f"road_{road_el.get('id', '')}" not in junction_roads:
                    self._warn(
                        f"Road {road_el.get('id')}: traffic light signal "
                        f"{signal.get('id')} is not on a junction road — skipped"
                    )
        if static:
            self._warn(f"{static} static <signal> element(s) (signs) not modelled")

    # ── Element parsers ──────────────────────────────────────────────

    def _parse_road(
        self, road_el: ET.Element, road_id: str
    ) -> Optional[Tuple[_Road, RoadSegment]]:
        """One <road> to (_Road, RoadSegment), or None if nothing usable."""
        reference = self._reference_line(road_el, road_id)
        if reference is None:
            return None
        layout = self._lane_layout(road_el, road_id)
        if layout is None:
            return None
        t_mid, width, count, index_of, reversed_lanes = layout
        s, x, y, hdg = reference

        stations = np.arange(0.0, s[-1], CENTERLINE_STEP_M)
        if s[-1] - stations[-1] > 1e-6:
            stations = np.append(stations, s[-1])
        sx = np.interp(stations, s, x)
        sy = np.interp(stations, s, y)
        sh = np.interp(stations, s, hdg)
        # Offset along the true normal, not a finite difference of the points.
        cx = sx - t_mid * np.sin(sh)
        cy = sy + t_mid * np.cos(sh)
        centerline = [Vector2D(float(a), float(b)) for a, b in zip(cx, cy)]

        road = _Road(s, x, y, hdg, t_mid, width, count, index_of, reversed_lanes)
        segment = RoadSegment(
            segment_id=f"road_{road_id}" if road_id else f"road_{id(road_el)}",
            # A road inside a junction is an arm; OpenDRIVE marks that with a
            # junction attribute of something other than "-1".
            segment_type=(
                "intersection_arm"
                if road_el.get("junction", "-1") != "-1"
                else "straight"
            ),
            centerline=centerline,
            lane_count=count,
            lane_width=width,
            speed_limit=self._speed_from_element(road_el, road_id),
            heading_start=float(math.atan2(math.sin(sh[0]), math.cos(sh[0]))),
            heading_end=float(math.atan2(math.sin(sh[-1]), math.cos(sh[-1]))),
            reversed_lanes=reversed_lanes,
        )
        return road, segment

    def _reference_line(self, road_el: ET.Element, road_id: str):
        """Dense (s, x, y, hdg) arrays along the road's reference line."""
        geometries = road_el.findall("planView/geometry")
        pieces = []
        for geometry in geometries:
            piece = _dense_geometry(geometry)
            if piece is None:
                # Interpolating across a missing piece would invent road; a
                # road with a hole in it is not a road this subset can place.
                kinds = [child.tag for child in geometry]
                self._warn(
                    f"Road {road_id}: unsupported geometry {kinds} — road skipped"
                )
                return None
            if piece[0][-1] > 0:
                pieces.append((float(geometry.get("s", "0")), piece))

        if not pieces:
            self._warn(f"Road {road_id} has no usable geometry — skipped")
            return None

        s_all, x_all, y_all, h_all = [], [], [], []
        last = -1.0
        for s0, (s, x, y, h) in pieces:
            keep = (s0 + s) > last + 1e-9
            s_all.append(s0 + s[keep])
            x_all.append(x[keep])
            y_all.append(y[keep])
            h_all.append(h[keep])
            last = s_all[-1][-1]
        s_cat = np.concatenate(s_all)
        return (
            s_cat - s_cat[0],
            np.concatenate(x_all),
            np.concatenate(y_all),
            np.unwrap(np.concatenate(h_all)),
        )

    def _lane_layout(self, road_el: ET.Element, road_id: str):
        """(t_mid, lane_width, lane_count, index_of, reversed_lanes) from the
        first laneSection, or None when the road has no driving lane.

        Only lanes of type "driving" count: including sidewalks and shoulders
        would widen the road the ego is allowed to occupy, and off-road
        detection reads that width.
        """
        sections = road_el.findall("lanes/laneSection")
        if not sections:
            self._warn(f"Road {road_id} declares no laneSection — skipped")
            return None
        if len(sections) > 1:
            self._warn(
                f"Road {road_id}: {len(sections)} laneSections; only the first "
                f"is modelled for the whole road"
            )
        for offset in road_el.findall("lanes/laneOffset"):
            if any(float(offset.get(k, "0")) != 0.0 for k in "abcd"):
                self._warn(f"Road {road_id}: laneOffset not modelled — ignored")
                break

        rule_lht = road_el.get("rule", "RHT").upper() == "LHT"
        driving = []  # (lane id, t_low, t_high)
        widths = []
        for side, sign in (("right", -1.0), ("left", 1.0)):
            lanes = sections[0].findall(f"{side}/lane")
            lanes.sort(key=lambda el: abs(int(el.get("id", "0"))))
            edge = 0.0
            for lane_el in lanes:
                width_el = lane_el.find("width")
                if width_el is None:
                    self._warn(
                        f"Road {road_id} lane {lane_el.get('id')}: no <width> "
                        f"(border lanes are not modelled) — road skipped"
                    )
                    return None
                width = float(width_el.get("a", "0"))
                if any(float(width_el.get(k, "0")) != 0.0 for k in "bcd"):
                    self._warn(
                        f"Road {road_id} lane {lane_el.get('id')}: width taper "
                        f"not modelled — width at section start used"
                    )
                inner, edge = edge, edge + sign * width
                if lane_el.get("type") == "driving" and width > 0:
                    driving.append(
                        (lane_el.get("id", ""), min(inner, edge), max(inner, edge))
                    )
                    widths.append(width)

        if not driving:
            self._warn(f"Road {road_id} declares no driving lanes — skipped")
            return None

        t_low = min(d[1] for d in driving)
        t_high = max(d[2] for d in driving)
        count = len(driving)
        width = (t_high - t_low) / count
        if (
            abs(sum(widths) - (t_high - t_low)) > 0.01
            or max(widths) - min(widths) > 0.01
        ):
            self._warn(
                f"Road {road_id}: driving lanes are not contiguous and equal width; "
                f"modelled as {count} lanes of {width:.2f} m across the driving span"
            )
        ordered = sorted(driving, key=lambda d: d[1])
        index_of = {lane_id: i for i, (lane_id, _, _) in enumerate(ordered)}
        reversed_lanes = tuple(
            i
            for i, (lane_id, _, _) in enumerate(ordered)
            if (int(lane_id) < 0 if rule_lht else int(lane_id) > 0)
        )
        return (t_low + t_high) / 2.0, width, count, index_of, reversed_lanes

    def _parse_junction(
        self, junction_el: ET.Element, root: ET.Element, graph: RoadGraph
    ) -> Optional[Junction]:
        """One <junction> to one Junction."""
        junction_id = junction_el.get("id", "")
        arms: List[str] = []
        connecting: List[str] = []
        for connection in junction_el.findall("connection"):
            for attribute in ("incomingRoad", "connectingRoad"):
                road_id = connection.get(attribute)
                if road_id and f"road_{road_id}" not in arms:
                    arms.append(f"road_{road_id}")
            if connection.get("connectingRoad"):
                connecting.append(f"road_{connection.get('connectingRoad')}")

        if not arms:
            self._warn(f"Junction {junction_id} connects nothing — skipped")
            return None

        # OpenDRIVE does not place a junction directly; its connecting roads lie
        # inside it, so their end points bound the box. (Incoming roads start
        # far outside it and would drag the centre away.)
        ends = [
            point
            for seg_id in connecting
            if seg_id in graph.segments
            for point in (
                graph.segments[seg_id].centerline[0],
                graph.segments[seg_id].centerline[-1],
            )
        ]
        if not ends:
            self._warn(
                f"Junction {junction_id}: none of its connecting roads parsed — "
                f"skipped"
            )
            return None
        position = Vector2D(
            sum(p.x for p in ends) / len(ends), sum(p.y for p in ends) / len(ends)
        )

        has_signal = any(
            signal.get("dynamic") == "yes"
            for road_el in root.findall("road")
            if f"road_{road_el.get('id', '')}" in arms
            for signal in road_el.findall("signals/signal")
        )

        # OpenDRIVE priority elements name the high and low road per pair.
        # Anything not named is treated as yield: assuming priority where the
        # map does not grant it is the dangerous default.
        right_of_way = {arm: "yield" for arm in arms}
        for priority in junction_el.findall("priority"):
            high = priority.get("high")
            if high:
                right_of_way[f"road_{high}"] = "priority"

        return Junction(
            junction_id=f"junction_{junction_id}",
            junction_type="4way" if len(arms) >= 4 else "t_junction",
            arms=arms,
            position=position,
            has_traffic_light=has_signal,
            right_of_way=right_of_way,
        )

    def _speed_from_element(self, road_el: ET.Element, road_id: str) -> float:
        """Extract speed limit in m/s from a <road> element."""
        speed_el = road_el.find("type/speed")
        if speed_el is not None:
            max_speed = float(speed_el.get("max", "0"))
            unit = speed_el.get("unit", "m/s")
            if unit == "km/h":
                return max_speed / 3.6
            if unit == "mph":
                return max_speed * 0.44704
            return max_speed
        self._warn(f"Road {road_id}: no speed limit declared — 50 km/h assumed")
        return 13.89


# ── Geometry ─────────────────────────────────────────────────────────────


def _dense_geometry(geometry: ET.Element):
    """Dense (s, x, y, hdg) samples of one planView geometry, s from 0.

    line / arc / spiral share one form: heading is quadratic in s
    (hdg + k0*s + 0.5*k'*s^2) and position is its integral, done by the
    trapezoid rule. poly3 and paramPoly3 are evaluated in their local (u, v)
    frame and measured by chord length. Returns None for anything else.
    """
    x0 = float(geometry.get("x", "0"))
    y0 = float(geometry.get("y", "0"))
    h0 = float(geometry.get("hdg", "0"))
    length = float(geometry.get("length", "0"))
    if length <= 0:
        return np.zeros(1), np.full(1, x0), np.full(1, y0), np.full(1, h0)
    n = max(2, int(math.ceil(length / DENSE_STEP_M)) + 1)
    kind = next(iter(geometry), None)
    if kind is None:
        return None
    tag = kind.tag

    if tag in ("line", "arc", "spiral"):
        k0 = dk = 0.0
        if tag == "arc":
            k0 = float(kind.get("curvature", "0"))
        elif tag == "spiral":
            k0 = float(kind.get("curvStart", "0"))
            dk = (float(kind.get("curvEnd", "0")) - k0) / length
        s = np.linspace(0.0, length, n)
        hdg = h0 + k0 * s + 0.5 * dk * s * s
        return s, x0 + _cumtrapz(np.cos(hdg), s), y0 + _cumtrapz(np.sin(hdg), s), hdg

    if tag == "poly3":
        a, b, c, d = (float(kind.get(k, "0")) for k in "abcd")
        # u never exceeds the arc length, so sampling u over [0, length] covers
        # the curve; the excess is cut at s = length below.
        u = np.linspace(0.0, length, n)
        v = a + b * u + c * u**2 + d * u**3
        du = np.ones_like(u)
        dv = b + 2 * c * u + 3 * d * u**2
    elif tag == "paramPoly3":
        coeff = {
            k: float(kind.get(k, "0"))
            for k in ("aU", "bU", "cU", "dU", "aV", "bV", "cV", "dV")
        }
        normalized = kind.get("pRange", "normalized") != "arcLength"
        p = np.linspace(0.0, 1.0 if normalized else length, n)
        u = coeff["aU"] + coeff["bU"] * p + coeff["cU"] * p**2 + coeff["dU"] * p**3
        v = coeff["aV"] + coeff["bV"] * p + coeff["cV"] * p**2 + coeff["dV"] * p**3
        du = coeff["bU"] + 2 * coeff["cU"] * p + 3 * coeff["dU"] * p**2
        dv = coeff["bV"] + 2 * coeff["cV"] * p + 3 * coeff["dV"] * p**2
    else:
        return None

    cos_h, sin_h = math.cos(h0), math.sin(h0)
    x = x0 + u * cos_h - v * sin_h
    y = y0 + u * sin_h + v * cos_h
    hdg = h0 + np.arctan2(dv, du)
    s = np.concatenate(([0.0], np.cumsum(np.hypot(np.diff(x), np.diff(y)))))
    if s[-1] <= 1e-9:
        return None  # a degenerate curve has no direction to place lanes on
    if tag == "paramPoly3":
        # The curve is the whole p range; its measured length differs from
        # the declared one only by authoring rounding, so stretch s to the
        # declared length rather than cut the curve or overlap the next piece.
        return s * (length / s[-1]), x, y, np.unwrap(hdg)
    keep = s <= length + 1e-9
    return s[keep], x[keep], y[keep], np.unwrap(hdg[keep])


def _cumtrapz(values: np.ndarray, s: np.ndarray) -> np.ndarray:
    """Cumulative trapezoid integral, starting at 0."""
    return np.concatenate(
        ([0.0], np.cumsum(0.5 * (values[1:] + values[:-1]) * np.diff(s)))
    )


# ── Scenario loading ─────────────────────────────────────────────────────


def file_sha256(path: str) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


# ponytail: maps are re-read only when their hash changes; a long-lived worker
# holding many distinct maps would want a size bound tuned to them.
@lru_cache(maxsize=16)
def load_map(path: str, sha256: str) -> XodrMap:
    """Parse a scenario's map once per process, keyed by path and content.

    The hash is the one recorded when the scenario was parsed. A map edited
    between parse and run is refused rather than run against geometry the
    scenario's content hash does not describe. The returned map is shared, so
    it must be treated as immutable — as RoadGraph already is.
    """
    data = Path(path).read_bytes()
    if hashlib.sha256(data).hexdigest() != sha256:
        raise ValueError(f"{path} changed since the scenario was parsed")
    return OpenDRIVEParser().read(data, Path(path).name)
