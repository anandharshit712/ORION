"""
ORION Road Templates.  [Phase 1]

Factory functions that generate RoadGraph objects for common road layouts.
Every scenario uses one of these templates rather than defining raw geometry.

All templates follow the same coordinate convention:
  - Origin (0, 0) is at the ego vehicle's spawn point
  - Ego always spawns heading in the +x direction (heading = 0)
  - Y+ = left of travel, Y- = right of travel

Available templates:
  highway_straight       — simple 2-lane (or N-lane) straight road
  urban_straight         — lower speed, same geometry
  t_junction             — T-intersection, ego approaches from south
  four_way_intersection  — 4-way crossing, ego approaches from south
  highway_onramp         — main carriageway + merging ramp
  roundabout             — circular junction with N arms
"""

from __future__ import annotations

import math
from typing import List

from arep.core.state import Vector2D
from arep.core.physics import SurfaceType
from arep.core.road import RoadGraph, RoadSegment, Junction


# ── Internal helpers ──────────────────────────────────────────────────────

def _straight_centerline(
    start: Vector2D,
    heading: float,
    length: float,
    step: float = 1.0,
) -> List[Vector2D]:
    """Generate centerline points for a straight road at 1m intervals."""
    dx = math.cos(heading)
    dy = math.sin(heading)
    n = max(2, int(length / step) + 1)
    return [
        Vector2D(start.x + dx * i * step, start.y + dy * i * step)
        for i in range(n)
    ]


def _arc_centerline(
    center: Vector2D,
    radius: float,
    angle_start: float,
    angle_end: float,
    step_deg: float = 1.0,
) -> List[Vector2D]:
    """Generate centerline points along an arc."""
    points = []
    step_rad = math.radians(step_deg)
    a = angle_start
    direction = 1.0 if angle_end >= angle_start else -1.0
    while direction * (angle_end - a) > 0:
        points.append(Vector2D(
            center.x + radius * math.cos(a),
            center.y + radius * math.sin(a),
        ))
        a += direction * step_rad
    points.append(Vector2D(
        center.x + radius * math.cos(angle_end),
        center.y + radius * math.sin(angle_end),
    ))
    return points


# ── Public factory functions ──────────────────────────────────────────────

def highway_straight(
    lanes: int = 2,
    length: float = 300.0,
    lane_width: float = 3.5,
    speed_limit: float = 27.78,           # 100 km/h in m/s
    surface: SurfaceType = SurfaceType.DRY_ASPHALT,
) -> RoadGraph:
    """
    Simple straight highway segment.

    Ego spawns at x=0, y=0, heading=0 (rightward).
    Road extends from x=-50 to x=(length-50) to give room behind ego.
    """
    start = Vector2D(-50.0, 0.0)
    centerline = _straight_centerline(start, heading=0.0, length=length + 50)
    seg = RoadSegment(
        segment_id="main",
        segment_type="straight",
        centerline=centerline,
        lane_count=lanes,
        lane_width=lane_width,
        speed_limit=speed_limit,
        surface=surface,
        heading_start=0.0,
        heading_end=0.0,
    )
    return RoadGraph(segments={"main": seg}, junctions={})


def urban_straight(
    lanes: int = 2,
    length: float = 200.0,
    lane_width: float = 3.0,
    speed_limit: float = 13.89,           # 50 km/h in m/s
    surface: SurfaceType = SurfaceType.DRY_ASPHALT,
) -> RoadGraph:
    """Urban straight road — lower speed limit, narrower lanes."""
    return highway_straight(
        lanes=lanes,
        length=length,
        lane_width=lane_width,
        speed_limit=speed_limit,
        surface=surface,
    )


def t_junction(
    approach_length: float = 80.0,
    cross_length: float = 80.0,
    lanes: int = 2,
    lane_width: float = 3.5,
    speed_limit: float = 13.89,
    has_traffic_light: bool = False,
    surface: SurfaceType = SurfaceType.DRY_ASPHALT,
) -> RoadGraph:
    """
    T-intersection. Ego approaches from south arm.

    Layout:
           west_arm  ---[JCT]--- east_arm
                          |
                       south_arm  (ego)
    """
    jct_pos = Vector2D(0.0, 0.0)

    south_cl = _straight_centerline(
        Vector2D(0.0, -approach_length), heading=math.pi / 2, length=approach_length
    )
    west_cl = _straight_centerline(
        Vector2D(-cross_length / 2, 0.0), heading=0.0, length=cross_length / 2
    )
    east_cl = _straight_centerline(
        Vector2D(0.0, 0.0), heading=0.0, length=cross_length / 2
    )

    segments = {
        "south_arm": RoadSegment("south_arm", "intersection_arm", south_cl, lanes, lane_width, speed_limit, surface, math.pi / 2, math.pi / 2),
        "west_arm":  RoadSegment("west_arm",  "intersection_arm", west_cl,  lanes, lane_width, speed_limit, surface, 0.0, 0.0),
        "east_arm":  RoadSegment("east_arm",  "intersection_arm", east_cl,  lanes, lane_width, speed_limit, surface, 0.0, 0.0),
    }
    junction = Junction(
        junction_id="jct_main",
        junction_type="t_junction",
        arms=["south_arm", "west_arm", "east_arm"],
        position=jct_pos,
        has_traffic_light=has_traffic_light,
        right_of_way={
            "south_arm": "yield",
            "west_arm": "priority",
            "east_arm": "priority",
        },
    )
    return RoadGraph(segments=segments, junctions={"jct_main": junction})


def four_way_intersection(
    arm_length: float = 80.0,
    lanes: int = 2,
    lane_width: float = 3.5,
    speed_limit: float = 13.89,
    has_traffic_light: bool = True,
    surface: SurfaceType = SurfaceType.DRY_ASPHALT,
) -> RoadGraph:
    """
    4-way intersection. Ego approaches from south arm heading north.

    Layout:
                north_arm
                   |
    west_arm ---[JCT]--- east_arm
                   |
                south_arm  (ego)
    """
    jct_pos = Vector2D(0.0, 0.0)
    half = arm_length / 2

    arm_defs = {
        "south_arm": (Vector2D(0.0, -arm_length), math.pi / 2,  math.pi / 2),
        "north_arm": (Vector2D(0.0, 0.0),          math.pi / 2,  math.pi / 2),
        "west_arm":  (Vector2D(-arm_length, 0.0),  0.0,          0.0),
        "east_arm":  (Vector2D(0.0, 0.0),           0.0,          0.0),
    }

    segments = {}
    for arm_id, (start, h_start, h_end) in arm_defs.items():
        cl = _straight_centerline(start, heading=h_start, length=arm_length)
        segments[arm_id] = RoadSegment(
            arm_id, "intersection_arm", cl, lanes, lane_width,
            speed_limit, surface, h_start, h_end,
        )

    junction = Junction(
        junction_id="jct_main",
        junction_type="4way",
        arms=list(arm_defs.keys()),
        position=jct_pos,
        has_traffic_light=has_traffic_light,
        right_of_way={arm: "controlled" for arm in arm_defs},
    )
    return RoadGraph(segments=segments, junctions={"jct_main": junction})


def highway_onramp(
    main_length: float = 400.0,
    ramp_length: float = 150.0,
    merge_point: float = 250.0,
    lanes: int = 3,
    lane_width: float = 3.75,
    speed_limit: float = 33.33,           # 120 km/h
    surface: SurfaceType = SurfaceType.DRY_ASPHALT,
) -> RoadGraph:
    """
    Highway main carriageway with an on-ramp merging from the right.

    Ego is on the main carriageway. An NPC may spawn on the ramp.
    The merge point is where the ramp lane joins the main road.
    """
    main_cl = _straight_centerline(Vector2D(-50.0, 0.0), heading=0.0, length=main_length + 50)
    # Ramp approaches at ~15° angle from the right
    ramp_angle = math.radians(15)
    ramp_start = Vector2D(merge_point - ramp_length * math.cos(ramp_angle),
                           -(ramp_length * math.sin(ramp_angle)))
    ramp_cl = _straight_centerline(ramp_start, heading=ramp_angle, length=ramp_length)

    segments = {
        "main":  RoadSegment("main",  "straight",       main_cl, lanes,     lane_width, speed_limit, surface, 0.0, 0.0),
        "ramp":  RoadSegment("ramp",  "ramp",           ramp_cl, 1,         lane_width, speed_limit * 0.75, surface, ramp_angle, 0.0),
    }
    junction = Junction(
        junction_id="merge_point",
        junction_type="merge",
        arms=["main", "ramp"],
        position=Vector2D(merge_point, 0.0),
        has_traffic_light=False,
        right_of_way={"main": "priority", "ramp": "yield"},
    )
    return RoadGraph(segments=segments, junctions={"merge_point": junction})


def roundabout(
    radius: float = 20.0,
    arm_count: int = 4,
    arm_length: float = 60.0,
    lane_width: float = 3.5,
    speed_limit: float = 8.33,            # 30 km/h
    surface: SurfaceType = SurfaceType.DRY_ASPHALT,
) -> RoadGraph:
    """
    Circular roundabout with arm_count entry/exit arms equally spaced.

    Ego approaches from the south arm (index 0).
    """
    segments = {}
    arm_ids = []

    # Circulating lane
    circle_cl = _arc_centerline(
        center=Vector2D(0.0, 0.0),
        radius=radius,
        angle_start=0.0,
        angle_end=2 * math.pi - 0.001,
        step_deg=2.0,
    )
    segments["circle"] = RoadSegment(
        "circle", "curve", circle_cl, 1, lane_width,
        speed_limit, surface, 0.0, 2 * math.pi,
    )

    # Arms
    for i in range(arm_count):
        angle = -math.pi / 2 + i * (2 * math.pi / arm_count)
        arm_start = Vector2D(
            (radius + arm_length) * math.cos(angle),
            (radius + arm_length) * math.sin(angle),
        )
        arm_toward_center = Vector2D(-math.cos(angle), -math.sin(angle))
        cl = _straight_centerline(
            arm_start,
            heading=math.atan2(arm_toward_center.y, arm_toward_center.x),
            length=arm_length,
        )
        arm_id = f"arm_{i}"
        arm_ids.append(arm_id)
        segments[arm_id] = RoadSegment(
            arm_id, "intersection_arm", cl, 1, lane_width,
            speed_limit, surface,
            heading_start=math.atan2(arm_toward_center.y, arm_toward_center.x),
            heading_end=math.atan2(arm_toward_center.y, arm_toward_center.x),
        )

    junction = Junction(
        junction_id="roundabout",
        junction_type="roundabout",
        arms=["circle"] + arm_ids,
        position=Vector2D(0.0, 0.0),
        has_traffic_light=False,
        right_of_way={arm: "yield" for arm in arm_ids} | {"circle": "priority"},
    )
    return RoadGraph(segments=segments, junctions={"roundabout": junction})
