"""
ORION Core State Representations.

Defines the fundamental data structures for the simulation:
  - Vector2D: 2D vector math
  - VehicleState: individual vehicle state
  - WorldState: complete simulation world
  - TrafficLightInfo / LaneInfo: environment elements
  - Enums: ObjectType, TrafficLightState, TerminationReason

All structures support deterministic serialization and deep copying.
"""

from __future__ import annotations

import copy
import json
import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

import numpy as np


# ── Enums ────────────────────────────────────────────────────────────────

class ObjectType(Enum):
    """Types of dynamic objects in the simulation."""
    CAR = "car"
    TRUCK = "truck"
    MOTORCYCLE = "motorcycle"
    PEDESTRIAN = "pedestrian"
    BICYCLE = "bicycle"
    UNKNOWN = "unknown"


class TrafficLightState(Enum):
    """Traffic light states."""
    RED = "red"
    YELLOW = "yellow"
    GREEN = "green"
    OFF = "off"


class TerminationReason(Enum):
    """Reasons the simulation can terminate."""
    COLLISION = "collision"
    OFF_ROAD = "off_road"
    TIMEOUT = "timeout"
    SUCCESS = "success"
    MODEL_ERROR = "model_error"
    INVALID_ACTION = "invalid_action"


# ── Vector2D ─────────────────────────────────────────────────────────────

@dataclass
class Vector2D:
    """
    Immutable-style 2D vector with full arithmetic support.

    Provides deterministic operations for position, velocity, and
    direction calculations throughout the simulation.
    """
    x: float = 0.0
    y: float = 0.0

    # ── Arithmetic ───────────────────────────────────────────────────

    def __add__(self, other: Vector2D) -> Vector2D:
        return Vector2D(self.x + other.x, self.y + other.y)

    def __sub__(self, other: Vector2D) -> Vector2D:
        return Vector2D(self.x - other.x, self.y - other.y)

    def __mul__(self, scalar: float) -> Vector2D:
        return Vector2D(self.x * scalar, self.y * scalar)

    def __rmul__(self, scalar: float) -> Vector2D:
        return self.__mul__(scalar)

    def __truediv__(self, scalar: float) -> Vector2D:
        return Vector2D(self.x / scalar, self.y / scalar)

    def __neg__(self) -> Vector2D:
        return Vector2D(-self.x, -self.y)

    # ── Geometry ─────────────────────────────────────────────────────

    def dot(self, other: Vector2D) -> float:
        """Dot product."""
        return self.x * other.x + self.y * other.y

    def cross(self, other: Vector2D) -> float:
        """2D cross product (scalar)."""
        return self.x * other.y - self.y * other.x

    def norm(self) -> float:
        """Euclidean length."""
        return math.sqrt(self.x * self.x + self.y * self.y)

    def norm_squared(self) -> float:
        """Squared Euclidean length (avoids sqrt)."""
        return self.x * self.x + self.y * self.y

    def normalize(self) -> Vector2D:
        """Unit vector, or zero vector if length is ~0."""
        n = self.norm()
        if n < 1e-12:
            return Vector2D(0.0, 0.0)
        return Vector2D(self.x / n, self.y / n)

    def distance_to(self, other: Vector2D) -> float:
        """Euclidean distance to another point."""
        return (self - other).norm()

    def rotate(self, angle: float) -> Vector2D:
        """Rotate by angle (radians, CCW positive)."""
        cos_a = math.cos(angle)
        sin_a = math.sin(angle)
        return Vector2D(
            self.x * cos_a - self.y * sin_a,
            self.x * sin_a + self.y * cos_a,
        )

    # ── Conversion ───────────────────────────────────────────────────

    def to_array(self) -> np.ndarray:
        """Convert to numpy array [x, y]."""
        return np.array([self.x, self.y], dtype=np.float64)

    @staticmethod
    def from_array(arr: np.ndarray) -> Vector2D:
        """Create from numpy array."""
        return Vector2D(float(arr[0]), float(arr[1]))

    def to_dict(self) -> Dict[str, float]:
        return {"x": self.x, "y": self.y}

    @staticmethod
    def from_dict(d: Dict[str, float]) -> Vector2D:
        return Vector2D(d["x"], d["y"])

    def __repr__(self) -> str:
        return f"Vector2D({self.x:.4f}, {self.y:.4f})"


# ── TrafficLightInfo ─────────────────────────────────────────────────────

@dataclass
class TrafficLightInfo:
    """Traffic light state at a specific position."""
    light_id: str
    position: Vector2D
    state: TrafficLightState
    time_remaining: float = 0.0  # seconds until next change

    def to_dict(self) -> Dict[str, Any]:
        return {
            "light_id": self.light_id,
            "position": self.position.to_dict(),
            "state": self.state.value,
            "time_remaining": self.time_remaining,
        }

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> TrafficLightInfo:
        return TrafficLightInfo(
            light_id=d["light_id"],
            position=Vector2D.from_dict(d["position"]),
            state=TrafficLightState(d["state"]),
            time_remaining=d.get("time_remaining", 0.0),
        )

    def copy(self) -> TrafficLightInfo:
        return TrafficLightInfo(
            light_id=self.light_id,
            position=Vector2D(self.position.x, self.position.y),
            state=self.state,
            time_remaining=self.time_remaining,
        )


# ── LaneInfo ─────────────────────────────────────────────────────────────

@dataclass
class LaneInfo:
    """Lane definition with centerline and properties."""
    lane_id: str
    centerline_points: List[Vector2D]
    width: float
    speed_limit: float

    def get_closest_point(self, position: Vector2D) -> Vector2D:
        """
        Find the closest point on the lane centerline to a given position.

        Uses brute-force search over centerline segments.
        Deterministic: iterates in list order.
        """
        if not self.centerline_points:
            return position

        best_point = self.centerline_points[0]
        best_dist_sq = (position - best_point).norm_squared()

        for i in range(len(self.centerline_points) - 1):
            p1 = self.centerline_points[i]
            p2 = self.centerline_points[i + 1]

            # Project position onto segment p1 → p2
            seg = p2 - p1
            seg_len_sq = seg.norm_squared()
            if seg_len_sq < 1e-12:
                candidate = p1
            else:
                t = max(0.0, min(1.0, (position - p1).dot(seg) / seg_len_sq))
                candidate = p1 + seg * t

            dist_sq = (position - candidate).norm_squared()
            if dist_sq < best_dist_sq:
                best_dist_sq = dist_sq
                best_point = candidate

        return best_point

    def get_lateral_offset(self, position: Vector2D) -> float:
        """Distance from position to closest point on centerline."""
        closest = self.get_closest_point(position)
        return position.distance_to(closest)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "lane_id": self.lane_id,
            "centerline_points": [p.to_dict() for p in self.centerline_points],
            "width": self.width,
            "speed_limit": self.speed_limit,
        }

    def copy(self) -> LaneInfo:
        return LaneInfo(
            lane_id=self.lane_id,
            centerline_points=[Vector2D(p.x, p.y) for p in self.centerline_points],
            width=self.width,
            speed_limit=self.speed_limit,
        )


# ── VehicleState ─────────────────────────────────────────────────────────

@dataclass
class VehicleState:
    """
    Complete state of one vehicle at a single point in time.

    Position, heading, velocity, dimensions, and identity.
    """
    position: Vector2D = field(default_factory=Vector2D)
    heading: float = 0.0        # radians, 0 = +x direction
    velocity: float = 0.0       # m/s (scalar, along heading)
    acceleration: float = 0.0   # m/s²
    length: float = 4.5         # metres
    width: float = 2.0
    wheelbase: float = 2.7
    object_type: ObjectType = ObjectType.CAR
    object_id: str = "ego"

    # ── Derived quantities ───────────────────────────────────────────

    def get_velocity_vector(self) -> Vector2D:
        """Velocity as a 2D vector along the heading."""
        return Vector2D(
            self.velocity * math.cos(self.heading),
            self.velocity * math.sin(self.heading),
        )

    def get_front_center(self) -> Vector2D:
        """Center of the front edge."""
        half_len = self.length / 2.0
        return Vector2D(
            self.position.x + half_len * math.cos(self.heading),
            self.position.y + half_len * math.sin(self.heading),
        )

    def get_rear_center(self) -> Vector2D:
        """Center of the rear edge."""
        half_len = self.length / 2.0
        return Vector2D(
            self.position.x - half_len * math.cos(self.heading),
            self.position.y - half_len * math.sin(self.heading),
        )

    def get_bounding_box_corners(self) -> List[Vector2D]:
        """
        Compute 4 corners of the OBB in DETERMINISTIC order.

        Order: front-left, front-right, rear-right, rear-left (CCW).
        This order MUST be preserved for collision detection consistency.
        """
        half_l = self.length / 2.0
        half_w = self.width / 2.0
        cos_h = math.cos(self.heading)
        sin_h = math.sin(self.heading)

        # Local-frame corners → world frame
        # Forward vector: (cos_h, sin_h), Right vector: (sin_h, -cos_h)
        forward_x = half_l * cos_h
        forward_y = half_l * sin_h
        right_x = half_w * sin_h
        right_y = -half_w * cos_h

        cx, cy = self.position.x, self.position.y
        return [
            Vector2D(cx + forward_x - right_x, cy + forward_y - right_y),  # FL
            Vector2D(cx + forward_x + right_x, cy + forward_y + right_y),  # FR
            Vector2D(cx - forward_x + right_x, cy - forward_y + right_y),  # RR
            Vector2D(cx - forward_x - right_x, cy - forward_y - right_y),  # RL
        ]

    # ── Serialization ────────────────────────────────────────────────

    def to_dict(self) -> Dict[str, Any]:
        return {
            "position": self.position.to_dict(),
            "heading": self.heading,
            "velocity": self.velocity,
            "acceleration": self.acceleration,
            "length": self.length,
            "width": self.width,
            "wheelbase": self.wheelbase,
            "object_type": self.object_type.value,
            "object_id": self.object_id,
        }

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> VehicleState:
        return VehicleState(
            position=Vector2D.from_dict(d["position"]),
            heading=d["heading"],
            velocity=d["velocity"],
            acceleration=d.get("acceleration", 0.0),
            length=d.get("length", 4.5),
            width=d.get("width", 2.0),
            wheelbase=d.get("wheelbase", 2.7),
            object_type=ObjectType(d.get("object_type", "car")),
            object_id=d.get("object_id", "unknown"),
        )

    def copy(self) -> VehicleState:
        """Deep copy of this state."""
        return VehicleState(
            position=Vector2D(self.position.x, self.position.y),
            heading=self.heading,
            velocity=self.velocity,
            acceleration=self.acceleration,
            length=self.length,
            width=self.width,
            wheelbase=self.wheelbase,
            object_type=self.object_type,
            object_id=self.object_id,
        )

    def __repr__(self) -> str:
        return (
            f"VehicleState(id={self.object_id!r}, "
            f"pos={self.position}, "
            f"h={self.heading:.3f}, "
            f"v={self.velocity:.2f})"
        )


# ── WorldState ───────────────────────────────────────────────────────────

@dataclass
class WorldState:
    """
    Complete state of the simulation world at a single point in time.

    This is the master data structure passed through the simulation loop.
    Contains the ego vehicle, all dynamic objects, environment state,
    and simulation metadata.
    """
    # Simulation time
    sim_time: float = 0.0
    timestep_count: int = 0

    # Vehicles
    ego_vehicle: VehicleState = field(default_factory=VehicleState)
    dynamic_objects: List[VehicleState] = field(default_factory=list)

    # Environment
    traffic_lights: List[TrafficLightInfo] = field(default_factory=list)
    lanes: List[LaneInfo] = field(default_factory=list)
    weather_condition: str = "clear"
    visibility: float = 1000.0

    # Termination
    is_terminated: bool = False
    termination_reason: Optional[TerminationReason] = None

    # Collision info
    has_collision: bool = False
    collision_object_id: Optional[str] = None
    collision_time: Optional[float] = None

    # Last applied action (for recording / replay)
    last_action: Optional[Any] = None

    # NPC behavior registry: object_id → {type, parameters, _triggered, ...}
    # Populated by ScenarioExecutor; mutated each tick by WorldManager.
    npc_behaviors: Dict[str, dict] = field(default_factory=dict)

    # ── Queries ──────────────────────────────────────────────────────

    def get_object_by_id(self, object_id: str) -> Optional[VehicleState]:
        """Find a dynamic object by its ID."""
        for obj in self.dynamic_objects:
            if obj.object_id == object_id:
                return obj
        return None

    def get_nearest_traffic_light(self) -> Optional[TrafficLightInfo]:
        """Get the traffic light closest to the ego vehicle."""
        if not self.traffic_lights:
            return None
        return min(
            self.traffic_lights,
            key=lambda tl: tl.position.distance_to(self.ego_vehicle.position),
        )

    def get_current_lane(self) -> Optional[LaneInfo]:
        """Get the lane the ego vehicle is currently in."""
        if not self.lanes:
            return None
        return min(
            self.lanes,
            key=lambda lane: lane.get_lateral_offset(self.ego_vehicle.position),
        )

    def get_speed_limit(self) -> float:
        """Get speed limit of the ego's current lane, or 0 if no lanes."""
        lane = self.get_current_lane()
        return lane.speed_limit if lane else 0.0

    # ── Serialization ────────────────────────────────────────────────

    def to_dict(self) -> Dict[str, Any]:
        return {
            "sim_time": self.sim_time,
            "timestep_count": self.timestep_count,
            "ego_vehicle": self.ego_vehicle.to_dict(),
            "dynamic_objects": [o.to_dict() for o in self.dynamic_objects],
            "traffic_lights": [t.to_dict() for t in self.traffic_lights],
            "weather_condition": self.weather_condition,
            "visibility": self.visibility,
            "is_terminated": self.is_terminated,
            "termination_reason": (
                self.termination_reason.value if self.termination_reason else None
            ),
            "has_collision": self.has_collision,
            "collision_object_id": self.collision_object_id,
            "collision_time": self.collision_time,
        }

    def to_json(self) -> str:
        """JSON string with sorted keys for deterministic hashing."""
        return json.dumps(self.to_dict(), sort_keys=True)

    def copy(self) -> WorldState:
        """Deep copy of the entire world state."""
        return WorldState(
            sim_time=self.sim_time,
            timestep_count=self.timestep_count,
            ego_vehicle=self.ego_vehicle.copy(),
            dynamic_objects=[o.copy() for o in self.dynamic_objects],
            traffic_lights=[t.copy() for t in self.traffic_lights],
            lanes=[l.copy() for l in self.lanes],
            weather_condition=self.weather_condition,
            visibility=self.visibility,
            is_terminated=self.is_terminated,
            termination_reason=self.termination_reason,
            has_collision=self.has_collision,
            collision_object_id=self.collision_object_id,
            collision_time=self.collision_time,
            last_action=(
                self.last_action.copy() if self.last_action is not None else None
            ),
            npc_behaviors=copy.deepcopy(self.npc_behaviors),
        )

    def __repr__(self) -> str:
        return (
            f"WorldState(t={self.sim_time:.3f}, "
            f"ego={self.ego_vehicle}, "
            f"objects={len(self.dynamic_objects)}, "
            f"terminated={self.is_terminated})"
        )
