"""
ORION Road Graph Data Model.  [Phase 1]

Defines the composable road network used by the simulation engine.
A RoadGraph is built from RoadSegments connected at Junctions.

This replaces the implicit flat-2-lane-straight-road assumption
that is currently hard-coded into the scenario executor.

All road geometry is represented in the same 2D coordinate space
as VehicleState positions. Centerline points are spaced at 1m intervals.

Design rules:
  - RoadGraph is immutable after construction.
  - All positions are Vector2D (same space as WorldState).
  - Ego spawn is always defined in the scenario YAML, not here.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, List, Literal, Optional, Tuple

from arep.core.state import Vector2D
from arep.core.physics import SurfaceType


# ── RoadSegment ───────────────────────────────────────────────────────────

@dataclass
class RoadSegment:
    """
    A single road segment — straight, curved, or an intersection arm.

    The centerline is a list of Vector2D points at 1m intervals defining
    the road centre. Lane centerlines are computed by offsetting from this
    by multiples of lane_width.
    """
    segment_id: str
    segment_type: Literal["straight", "curve", "intersection_arm", "ramp"]
    centerline: List[Vector2D]           # 1m-spaced points along road centre
    lane_count: int
    lane_width: float                    # metres per lane
    speed_limit: float                   # m/s
    surface: SurfaceType = SurfaceType.DRY_ASPHALT
    heading_start: float = 0.0          # radians at start of segment
    heading_end: float = 0.0            # radians at end of segment

    @property
    def length(self) -> float:
        """Approximate arc length of this segment in metres."""
        if len(self.centerline) < 2:
            return 0.0
        total = 0.0
        for i in range(len(self.centerline) - 1):
            total += self.centerline[i].distance_to(self.centerline[i + 1])
        return total

    @property
    def total_width(self) -> float:
        """Total road width in metres."""
        return self.lane_count * self.lane_width

    def get_lane_centerline(self, lane_index: int) -> List[Vector2D]:
        """
        Return the centerline points for a specific lane.

        Lane 0 = leftmost, lane (lane_count - 1) = rightmost.
        Offset is perpendicular to the road centerline at each point.
        """
        if not (0 <= lane_index < self.lane_count):
            raise ValueError(
                f"lane_index {lane_index} out of range for segment "
                f"{self.segment_id!r} ({self.lane_count} lanes)"
            )
        # Offset from road center: negative = left of travel direction
        lane_offset = (lane_index - (self.lane_count - 1) / 2.0) * self.lane_width
        result = []
        for i, pt in enumerate(self.centerline):
            # Compute local perpendicular direction
            if i < len(self.centerline) - 1:
                fwd = self.centerline[i + 1] - pt
            else:
                fwd = pt - self.centerline[i - 1]
            fwd_len = fwd.norm()
            if fwd_len < 1e-9:
                perp = Vector2D(0.0, 1.0)
            else:
                # Perpendicular: rotate forward vector 90° CCW
                perp = Vector2D(-fwd.y / fwd_len, fwd.x / fwd_len)
            result.append(Vector2D(
                pt.x + perp.x * lane_offset,
                pt.y + perp.y * lane_offset,
            ))
        return result

    def contains_point(self, position: Vector2D, margin: float = 0.5) -> bool:
        """
        Return True if position is within (total_width/2 + margin) of the centerline.
        """
        half_road = self.total_width / 2.0 + margin
        for i in range(len(self.centerline) - 1):
            p1 = self.centerline[i]
            p2 = self.centerline[i + 1]
            seg = p2 - p1
            seg_len_sq = seg.norm_squared()
            if seg_len_sq < 1e-12:
                dist = position.distance_to(p1)
            else:
                t = max(0.0, min(1.0, (position - p1).dot(seg) / seg_len_sq))
                closest = p1 + seg * t
                dist = position.distance_to(closest)
            if dist <= half_road:
                return True
        return False


# ── Junction ──────────────────────────────────────────────────────────────

@dataclass
class Junction:
    """
    A point where multiple road segments meet.

    right_of_way maps each arm's segment_id to "priority" or "yield".
    Traffic light state is managed by the simulation engine separately.
    """
    junction_id: str
    junction_type: Literal["t_junction", "4way", "roundabout", "merge"]
    arms: List[str]                          # segment_ids that connect here
    position: Vector2D = field(default_factory=Vector2D)
    has_traffic_light: bool = False
    right_of_way: Dict[str, str] = field(default_factory=dict)
    # e.g. {"south_arm": "priority", "east_arm": "yield"}


# ── RoadGraph ─────────────────────────────────────────────────────────────

@dataclass
class RoadGraph:
    """
    Complete road network for a simulation scenario.

    Built by road_templates factory functions or by the OpenDRIVE parser.
    Immutable after construction — do not modify segments or junctions
    after the graph is handed to the scenario executor.
    """
    segments: Dict[str, RoadSegment] = field(default_factory=dict)
    junctions: Dict[str, Junction] = field(default_factory=dict)

    # ── Queries ──────────────────────────────────────────────────────

    def get_segment(self, segment_id: str) -> RoadSegment:
        if segment_id not in self.segments:
            raise KeyError(f"No segment with id {segment_id!r}")
        return self.segments[segment_id]

    def get_ego_segment(self, position: Vector2D) -> Optional[RoadSegment]:
        """Find which segment the ego vehicle is currently on."""
        for seg in self.segments.values():
            if seg.contains_point(position):
                return seg
        return None

    def is_off_road(self, position: Vector2D, margin: float = 0.5) -> bool:
        """Return True if position is not on any road segment."""
        return self.get_ego_segment(position) is None

    def get_junction_at(self, position: Vector2D, radius: float = 5.0) -> Optional[Junction]:
        """Find a junction within radius metres of position."""
        for junc in self.junctions.values():
            if junc.position.distance_to(position) <= radius:
                return junc
        return None

    def get_speed_limit_at(self, position: Vector2D) -> float:
        """Return the speed limit of the segment the position is on, or 0."""
        seg = self.get_ego_segment(position)
        return seg.speed_limit if seg else 0.0

    def get_lane_centerline(
        self, segment_id: str, lane_index: int
    ) -> List[Vector2D]:
        """Convenience: get lane centerline from segment_id + lane_index."""
        return self.get_segment(segment_id).get_lane_centerline(lane_index)

    def all_lane_centerlines(self) -> List[List[Vector2D]]:
        """All lane centerlines across all segments, flattened."""
        result = []
        for seg in self.segments.values():
            for lane_idx in range(seg.lane_count):
                result.append(seg.get_lane_centerline(lane_idx))
        return result

    def summary(self) -> str:
        total_length = sum(s.length for s in self.segments.values())
        total_lanes = sum(s.lane_count for s in self.segments.values())
        return (
            f"RoadGraph({len(self.segments)} segments, "
            f"{len(self.junctions)} junctions, "
            f"~{total_length:.0f}m total length, "
            f"{total_lanes} total lanes)"
        )

    def __repr__(self) -> str:
        return self.summary()
