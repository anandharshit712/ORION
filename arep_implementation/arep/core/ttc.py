"""
ORION Time-To-Collision Calculator.

Computes TTC under constant acceleration (Phase 2.1, closing defect D-11).

Both vehicles are projected forward using their current velocity *and* their
current acceleration, solving 0.5·a·t² + v·t − d = 0 along the line between
them. The previous constant-velocity form, d / v, credited a braking ego with
closing speed it was never going to carry, so TTC read high in exactly the
manoeuvre the safety score exists to judge — a model that braked late scored
much like one that braked early, right up until it collided.

When the closing rate eases off enough that relative motion reverses before the
gap is covered, the result is None: "no collision on this trajectory" rather
than a large number that still reads as danger.

Remaining assumptions, and they matter:
  - Acceleration is held constant over the projection. A vehicle that brakes
    harder a moment later closes sooner than predicted, so TTC still leans
    optimistic during a developing manoeuvre — far less than before, but not
    zero.
  - Straight-line motion. Steering is not projected, so a vehicle turning into
    or out of the path is mispredicted.
  - Point-mass. Physical overlap is the collision detector's job, and that one
    does use vehicle dimensions.

TTC values are comparable between models on the same scenario, which is what
the score uses them for. They are not a calibrated time-to-impact.

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
        lateral_threshold: float = 5.0,  # metres
        max_ttc: float = 30.0,  # seconds cap
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

        # ── Approach speed and acceleration ──────────────────────────
        ego_vel = ego.get_velocity_vector()
        obj_vel = obj.get_velocity_vector()
        rel_vel = ego_vel - obj_vel  # relative velocity of ego w.r.t. object

        # Project onto the line connecting them
        direction = rel_pos.normalize()
        approach_speed = rel_vel.dot(direction)

        # Must be approaching (positive = closing)
        if approach_speed <= 0:
            return None

        rel_accel = self._relative_acceleration(ego, obj, direction)
        ttc = self._solve_ttc(distance, approach_speed, rel_accel)

        if ttc is None or ttc > self.max_ttc:
            return None

        return ttc

    @staticmethod
    def _relative_acceleration(
        ego: VehicleState,
        obj: VehicleState,
        direction: Vector2D,
    ) -> float:
        """Closing acceleration along the line between the two vehicles.

        Positive means the gap is closing ever faster; negative means the
        closing is easing off, which is what braking looks like from here.

        Both vehicles carry acceleration as a scalar along their own heading,
        so each is turned into a vector before projecting.
        """
        ego_accel = Vector2D(
            ego.acceleration * math.cos(ego.heading),
            ego.acceleration * math.sin(ego.heading),
        )
        obj_accel = Vector2D(
            obj.acceleration * math.cos(obj.heading),
            obj.acceleration * math.sin(obj.heading),
        )
        return (ego_accel - obj_accel).dot(direction)

    @staticmethod
    def _solve_ttc(distance: float, speed: float, accel: float) -> Optional[float]:
        """Smallest positive t with  0.5·a·t² + v·t − d = 0.

        Constant acceleration rather than constant velocity (Phase 2.1, D-11).
        The old form, d / v, ignored that a braking ego will not carry its
        current closing speed — so TTC was biased high in exactly the manoeuvre
        the safety score exists to judge, and a model that braked late looked
        much like one that braked early.

        Returns None when the gap never closes: with the closing rate easing
        off fast enough, relative motion reverses before contact, and the
        honest answer is "no collision on this trajectory" rather than a large
        number that still reads as danger.
        """
        # Negligible acceleration: fall back to the linear form rather than
        # dividing by something near zero.
        if abs(accel) < 1e-9:
            return distance / speed if speed > 0 else None

        discriminant = speed * speed + 2.0 * accel * distance
        if discriminant < 0.0:
            # Closing stops before the gap is covered.
            return None

        root = math.sqrt(discriminant)
        # Roots of a·t² + 2v·t − 2d = 0 are (−v ± root) / a. Take whichever is
        # positive and smaller: contact happens the first time the gap is zero.
        candidates = [
            t for t in ((-speed + root) / accel, (-speed - root) / accel) if t > 0.0
        ]
        if not candidates:
            return None
        return min(candidates)

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
