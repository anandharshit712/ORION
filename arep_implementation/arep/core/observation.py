"""
ORION Observation Generation.

Creates the Observation that models receive each timestep.

Two output formats:
  1. Structured dict (Observation.to_dict)
  2. Fixed-size vector (Observation.to_vector → np.ndarray shape (93,))

Vector layout (93 elements):
  [0:7]   ego state (x, y, heading, velocity, accel, heading_rate, speed_limit)
  [7:13]  lane info   (offset, heading_error, width, curvature, is_valid, pad)
  [13:93] 10 objects × 8 features each (rel_x, rel_y, rel_vx, rel_vy,
           heading, speed, length, width)
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import numpy as np

from arep.core.state import (
    WorldState,
    VehicleState,
    Vector2D,
    TrafficLightState,
)


MAX_OBJECTS = 10
OBJECT_FEATURES = 8
EGO_FEATURES = 7
LANE_FEATURES = 6
VECTOR_SIZE = EGO_FEATURES + LANE_FEATURES + MAX_OBJECTS * OBJECT_FEATURES  # 93


@dataclass
class ObjectObservation:
    """
    A single object as observed from the ego vehicle's reference frame.

    All positions and velocities are relative to the ego.
    """
    object_id: str = ""
    relative_x: float = 0.0       # metres, ego frame (forward)
    relative_y: float = 0.0       # metres, ego frame (lateral)
    relative_vx: float = 0.0      # m/s, ego frame
    relative_vy: float = 0.0      # m/s, ego frame
    heading: float = 0.0          # relative heading (radians)
    speed: float = 0.0            # scalar speed (m/s)
    length: float = 0.0           # metres
    width: float = 0.0            # metres

    def to_array(self) -> np.ndarray:
        """Convert to numpy array (8 floats)."""
        return np.array([
            self.relative_x,
            self.relative_y,
            self.relative_vx,
            self.relative_vy,
            self.heading,
            self.speed,
            self.length,
            self.width,
        ], dtype=np.float64)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "object_id": self.object_id,
            "relative_x": self.relative_x,
            "relative_y": self.relative_y,
            "relative_vx": self.relative_vx,
            "relative_vy": self.relative_vy,
            "heading": self.heading,
            "speed": self.speed,
            "length": self.length,
            "width": self.width,
        }


@dataclass
class Observation:
    """
    Complete observation given to the model at each timestep.

    Generated from WorldState via from_world_state().
    """
    # Ego state
    ego_x: float = 0.0
    ego_y: float = 0.0
    ego_heading: float = 0.0
    ego_velocity: float = 0.0
    ego_acceleration: float = 0.0
    ego_heading_rate: float = 0.0     # computed via finite difference
    speed_limit: float = 0.0

    # Lane info
    lane_offset: float = 0.0          # lateral offset from centerline
    lane_heading_error: float = 0.0   # heading error relative to lane
    lane_width: float = 3.5
    lane_curvature: float = 0.0
    lane_valid: bool = False

    # Traffic light
    traffic_light_state: TrafficLightState = TrafficLightState.OFF
    traffic_light_distance: float = 1000.0

    # Nearby objects (up to MAX_OBJECTS, sorted by distance)
    objects: List[ObjectObservation] = field(default_factory=list)

    # Simulation time
    sim_time: float = 0.0

    # ── Factory ──────────────────────────────────────────────────────

    @classmethod
    def from_world_state(
        cls,
        world: WorldState,
        previous_world: Optional[WorldState] = None,
    ) -> Observation:
        """
        Generate observation from world state.

        Args:
            world: Current world state.
            previous_world: Previous world state (for heading rate).

        Returns:
            Observation for the model.
        """
        ego = world.ego_vehicle

        # ── Heading rate (finite difference) ─────────────────────────
        heading_rate = 0.0
        if previous_world is not None:
            dh = ego.heading - previous_world.ego_vehicle.heading
            # Wrap to [-π, π]
            dh = math.atan2(math.sin(dh), math.cos(dh))
            # Assume constant dt (would need config, but use sim_time diff)
            dt = world.sim_time - previous_world.sim_time
            if dt > 1e-9:
                heading_rate = dh / dt

        # ── Lane info ────────────────────────────────────────────────
        lane = world.get_current_lane()
        lane_offset = 0.0
        lane_heading_error = 0.0
        lane_width = 3.5
        lane_curvature = 0.0
        lane_valid = False

        if lane is not None:
            lane_valid = True
            lane_width = lane.width
            closest = lane.get_closest_point(ego.position)
            lane_offset = ego.position.distance_to(closest)

            # Heading error: difference between ego heading and lane direction
            # Approximate lane direction from nearest segment
            # (simplified: use centerline direction at closest point)
            lane_heading_error = 0.0  # Simplified for initial implementation

        # ── Speed limit ──────────────────────────────────────────────
        speed_limit = world.get_speed_limit()

        # ── Traffic light ────────────────────────────────────────────
        tl = world.get_nearest_traffic_light()
        tl_state = TrafficLightState.OFF
        tl_distance = 1000.0
        if tl is not None:
            tl_state = tl.state
            tl_distance = tl.position.distance_to(ego.position)

        # ── Nearby objects ───────────────────────────────────────────
        obj_observations = _convert_objects_to_relative(
            ego, world.dynamic_objects
        )

        return cls(
            ego_x=ego.position.x,
            ego_y=ego.position.y,
            ego_heading=ego.heading,
            ego_velocity=ego.velocity,
            ego_acceleration=ego.acceleration,
            ego_heading_rate=heading_rate,
            speed_limit=speed_limit,
            lane_offset=lane_offset,
            lane_heading_error=lane_heading_error,
            lane_width=lane_width,
            lane_curvature=lane_curvature,
            lane_valid=lane_valid,
            traffic_light_state=tl_state,
            traffic_light_distance=tl_distance,
            objects=obj_observations,
            sim_time=world.sim_time,
        )

    # ── Conversion ───────────────────────────────────────────────────

    def to_vector(self) -> np.ndarray:
        """
        Convert to fixed-size numpy vector for ML models.

        Shape: (93,).  Pads with zeros if < MAX_OBJECTS.
        """
        vec = np.zeros(VECTOR_SIZE, dtype=np.float64)

        # Ego state [0:7]
        vec[0] = self.ego_x
        vec[1] = self.ego_y
        vec[2] = self.ego_heading
        vec[3] = self.ego_velocity
        vec[4] = self.ego_acceleration
        vec[5] = self.ego_heading_rate
        vec[6] = self.speed_limit

        # Lane info [7:13]
        vec[7] = self.lane_offset
        vec[8] = self.lane_heading_error
        vec[9] = self.lane_width
        vec[10] = self.lane_curvature
        vec[11] = 1.0 if self.lane_valid else 0.0
        vec[12] = 0.0  # padding

        # Objects [13:93]  (10 objects × 8 features)
        for i, obj in enumerate(self.objects[:MAX_OBJECTS]):
            base = EGO_FEATURES + LANE_FEATURES + i * OBJECT_FEATURES
            arr = obj.to_array()
            vec[base:base + OBJECT_FEATURES] = arr

        return vec

    def to_dict(self) -> Dict[str, Any]:
        """Structured dictionary format."""
        return {
            "ego": {
                "x": self.ego_x,
                "y": self.ego_y,
                "heading": self.ego_heading,
                "velocity": self.ego_velocity,
                "acceleration": self.ego_acceleration,
                "heading_rate": self.ego_heading_rate,
            },
            "lane": {
                "offset": self.lane_offset,
                "heading_error": self.lane_heading_error,
                "width": self.lane_width,
                "curvature": self.lane_curvature,
                "valid": self.lane_valid,
            },
            "speed_limit": self.speed_limit,
            "traffic_light": {
                "state": self.traffic_light_state.value,
                "distance": self.traffic_light_distance,
            },
            "objects": [o.to_dict() for o in self.objects],
            "sim_time": self.sim_time,
        }


# ── Private helpers ──────────────────────────────────────────────────────

def _convert_objects_to_relative(
    ego: VehicleState,
    objects: List[VehicleState],
) -> List[ObjectObservation]:
    """
    Convert dynamic objects to ego-relative observations.

    Objects are sorted by distance (nearest first) and limited
    to MAX_OBJECTS.

    Args:
        ego: Ego vehicle state.
        objects: List of dynamic objects in world frame.

    Returns:
        List of ObjectObservation (up to MAX_OBJECTS).
    """
    cos_ego = math.cos(-ego.heading)
    sin_ego = math.sin(-ego.heading)

    observations: List[ObjectObservation] = []

    for obj in objects:
        # World-frame relative position
        dx = obj.position.x - ego.position.x
        dy = obj.position.y - ego.position.y

        # Rotate to ego frame
        rel_x = dx * cos_ego - dy * sin_ego   # forward
        rel_y = dx * sin_ego + dy * cos_ego    # lateral

        # World-frame relative velocity
        dvx = (
            obj.velocity * math.cos(obj.heading)
            - ego.velocity * math.cos(ego.heading)
        )
        dvy = (
            obj.velocity * math.sin(obj.heading)
            - ego.velocity * math.sin(ego.heading)
        )

        # Rotate velocity to ego frame
        rel_vx = dvx * cos_ego - dvy * sin_ego
        rel_vy = dvx * sin_ego + dvy * cos_ego

        # Relative heading
        rel_heading = obj.heading - ego.heading
        rel_heading = math.atan2(math.sin(rel_heading), math.cos(rel_heading))

        observations.append(ObjectObservation(
            object_id=obj.object_id,
            relative_x=rel_x,
            relative_y=rel_y,
            relative_vx=rel_vx,
            relative_vy=rel_vy,
            heading=rel_heading,
            speed=obj.velocity,
            length=obj.length,
            width=obj.width,
        ))

    # Sort by distance (nearest first) — deterministic
    observations.sort(key=lambda o: o.relative_x**2 + o.relative_y**2)

    return observations[:MAX_OBJECTS]
