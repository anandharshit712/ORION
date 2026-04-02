"""
ORION Collision Detection System.

Uses Oriented Bounding Boxes (OBB) and the Separating Axis Theorem (SAT).

Determinism guarantees:
  - Objects are iterated in sorted order (by object_id)
  - Vertices are computed in deterministic CCW order
  - Axes are tested in fixed order (edges of A, then edges of B)
  - Overlap tolerance is configurable (default 1e-6)
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import List, Optional

from arep.config import SimulationConfig
from arep.core.state import VehicleState, WorldState, Vector2D


@dataclass
class CollisionEvent:
    """Record of a collision between ego and a dynamic object."""
    ego_id: str
    object_id: str
    sim_time: float
    impact_speed: float
    impact_angle: float
    collision_point: Vector2D


class CollisionDetector:
    """
    SAT-based collision detector with deterministic ordering.

    Usage:
        detector = CollisionDetector(config)
        collisions = detector.detect_all_collisions(world)
    """

    def __init__(self, config: SimulationConfig):
        self.tolerance = config.collision_tolerance

    # ── Public API ───────────────────────────────────────────────────

    def check_collision(
        self,
        vehicle_a: VehicleState,
        vehicle_b: VehicleState,
    ) -> bool:
        """
        Check if two vehicles' OBBs overlap using SAT.

        Args:
            vehicle_a: First vehicle.
            vehicle_b: Second vehicle.

        Returns:
            True if overlapping (collision).
        """
        corners_a = vehicle_a.get_bounding_box_corners()
        corners_b = vehicle_b.get_bounding_box_corners()

        # Test all axes from A's edges, then B's edges
        axes_a = self._get_edge_normals(corners_a)
        axes_b = self._get_edge_normals(corners_b)

        for axis in axes_a + axes_b:
            min_a, max_a = self._project_polygon(corners_a, axis)
            min_b, max_b = self._project_polygon(corners_b, axis)

            # Check for separation
            if max_a < min_b + self.tolerance or max_b < min_a + self.tolerance:
                return False  # Separating axis found → no collision

        return True  # No separating axis → collision

    def detect_all_collisions(
        self,
        world: WorldState,
    ) -> List[CollisionEvent]:
        """
        Check ego vehicle against all dynamic objects for collisions.

        Objects are checked in sorted order by object_id for determinism.

        Args:
            world: Current world state.

        Returns:
            List of CollisionEvent for each collision detected.
        """
        ego = world.ego_vehicle
        collisions: List[CollisionEvent] = []

        # Sort objects deterministically by ID
        sorted_objects = sorted(
            world.dynamic_objects, key=lambda o: o.object_id
        )

        for obj in sorted_objects:
            if self.check_collision(ego, obj):
                # Compute impact details
                rel_vel = ego.get_velocity_vector() - obj.get_velocity_vector()
                impact_speed = rel_vel.norm()

                # Impact angle = angle between ego heading and relative position
                rel_pos = obj.position - ego.position
                impact_angle = math.atan2(rel_pos.y, rel_pos.x) - ego.heading

                # Collision point = midpoint between centers
                collision_point = Vector2D(
                    (ego.position.x + obj.position.x) / 2.0,
                    (ego.position.y + obj.position.y) / 2.0,
                )

                collisions.append(CollisionEvent(
                    ego_id=ego.object_id,
                    object_id=obj.object_id,
                    sim_time=world.sim_time,
                    impact_speed=impact_speed,
                    impact_angle=impact_angle,
                    collision_point=collision_point,
                ))

        return collisions

    def check_off_road(
        self,
        vehicle: VehicleState,
        world: WorldState,
    ) -> bool:
        """
        Check if vehicle is off-road.

        A vehicle is off-road if its lateral offset from the nearest
        lane centerline exceeds half the lane width.

        Args:
            vehicle: Vehicle to check.
            world: Current world state (provides lane info).

        Returns:
            True if off-road.
        """
        if not world.lanes:
            return False  # No lanes defined → can't be off-road

        # Find nearest lane
        nearest_lane = min(
            world.lanes,
            key=lambda lane: lane.get_lateral_offset(vehicle.position),
        )

        lateral_offset = nearest_lane.get_lateral_offset(vehicle.position)
        return lateral_offset > nearest_lane.width / 2.0

    # ── SAT internals ────────────────────────────────────────────────

    @staticmethod
    def _get_edge_normals(corners: List[Vector2D]) -> List[Vector2D]:
        """
        Compute outward-facing edge normals for SAT.

        Iterates edges in the deterministic order of the corner list.
        For a CCW polygon, the outward normal of edge (p1→p2) is
        (dy, -dx) normalized.

        Only 2 unique axes are needed for a rectangle (adjacent edges
        are perpendicular), but we return all 4 for clarity and
        generality.

        Args:
            corners: Polygon vertices in order.

        Returns:
            List of unit normal vectors.
        """
        normals: List[Vector2D] = []
        n = len(corners)
        for i in range(n):
            p1 = corners[i]
            p2 = corners[(i + 1) % n]
            edge = p2 - p1
            # Outward normal for CCW polygon
            normal = Vector2D(edge.y, -edge.x).normalize()
            normals.append(normal)
        return normals

    @staticmethod
    def _project_polygon(
        corners: List[Vector2D],
        axis: Vector2D,
    ) -> tuple[float, float]:
        """
        Project polygon vertices onto an axis.

        Args:
            corners: Polygon vertices.
            axis: Unit axis vector.

        Returns:
            (min_projection, max_projection)
        """
        projections = [c.dot(axis) for c in corners]
        return min(projections), max(projections)
