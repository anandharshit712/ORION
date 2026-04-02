"""
ORION Time-To-Collision Calculator.

Computes TTC using constant-velocity linear approximation.

Assumptions:
  - Constant velocity (no acceleration)
  - Straight-line motion (no steering)
  - Point-mass approximation for TTC (size handled by collision detector)

TTC Categories:
  > 10s:     Safe
  5–10s:     Attention
  2–5s:      Caution
  ≤ 2s:      Critical
"""

from __future__ import annotations

import math
from typing import List, Optional

from arep.core.state import VehicleState, Vector2D


class TTCCalculator:
    """
    Compute Time-To-Collision between ego and objects.

    Uses forward-cone and lateral-threshold filters to ignore
    objects that are not in the path of the ego vehicle.
    """

    def __init__(
        self,
        forward_cone_angle: float = math.pi / 3.0,  # 60° half-angle
        lateral_threshold: float = 5.0,               # metres
        max_ttc: float = 30.0,                         # seconds cap
    ):
        self.forward_cone_angle = forward_cone_angle
        self.lateral_threshold = lateral_threshold
        self.max_ttc = max_ttc

    def compute_ttc(
        self,
        ego: VehicleState,
        obj: VehicleState,
    ) -> Optional[float]:
        """
        Compute TTC between ego and a single object.

        Returns None if:
          - Object is outside forward cone
          - Object is too far laterally
          - Vehicles are not approaching each other
          - TTC exceeds max_ttc

        Args:
            ego: Ego vehicle state.
            obj: Object vehicle state.

        Returns:
            TTC in seconds, or None if not applicable.
        """
        # ── Relative position in world frame ─────────────────────────
        rel_pos = obj.position - ego.position
        distance = rel_pos.norm()

        if distance < 1e-6:
            return 0.0  # Already overlapping

        # ── Forward cone filter ──────────────────────────────────────
        # Transform relative position to ego-local frame
        cos_ego = math.cos(-ego.heading)
        sin_ego = math.sin(-ego.heading)

        forward = rel_pos.x * cos_ego - rel_pos.y * sin_ego
        lateral = rel_pos.x * sin_ego + rel_pos.y * cos_ego

        # Must be ahead of ego
        if forward <= 0:
            return None

        # Must be within forward cone
        angle_to_obj = abs(math.atan2(abs(lateral), forward))
        if angle_to_obj > self.forward_cone_angle:
            return None

        # ── Lateral threshold filter ─────────────────────────────────
        if abs(lateral) > self.lateral_threshold:
            return None

        # ── Approach speed ───────────────────────────────────────────
        ego_vel = ego.get_velocity_vector()
        obj_vel = obj.get_velocity_vector()
        rel_vel = ego_vel - obj_vel  # relative velocity of ego w.r.t. object

        # Project relative velocity onto the line connecting them
        direction = rel_pos.normalize()
        approach_speed = rel_vel.dot(direction)

        # Must be approaching (positive = closing)
        if approach_speed <= 0:
            return None

        # ── TTC = distance / approach speed ──────────────────────────
        ttc = distance / approach_speed

        if ttc > self.max_ttc:
            return None

        return ttc

    def compute_min_ttc(
        self,
        ego: VehicleState,
        objects: List[VehicleState],
    ) -> float:
        """
        Compute minimum TTC across all objects.

        Args:
            ego: Ego vehicle state.
            objects: List of dynamic objects.

        Returns:
            Minimum TTC in seconds, or max_ttc if no valid TTC found.
        """
        min_ttc = self.max_ttc

        for obj in objects:
            ttc = self.compute_ttc(ego, obj)
            if ttc is not None and ttc < min_ttc:
                min_ttc = ttc

        return min_ttc

    @staticmethod
    def categorize(ttc: float) -> str:
        """
        Categorize TTC into safety levels.

        Args:
            ttc: Time-to-collision in seconds.

        Returns:
            Safety category string.
        """
        if ttc <= 2.0:
            return "critical"
        elif ttc <= 5.0:
            return "caution"
        elif ttc <= 10.0:
            return "attention"
        else:
            return "safe"
