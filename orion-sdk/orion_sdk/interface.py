"""
ORION SDK — ModelInterface, Action, Observation.

These mirror the corresponding classes in arep.core and arep.models.interface.
They are re-implemented here so customers only need to install orion-sdk,
not the full arep backend package.

IMPORTANT: Keep in sync with arep/core/action.py, observation.py, models/interface.py.
If the protocol changes in arep, update this file to match.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class Action:
    """
    Control action produced by the model each tick.

    All fields are normalised to [-1.0, 1.0]:
      steering : negative = left, positive = right
      throttle : 0.0 = no acceleration, 1.0 = max acceleration
      brake    : 0.0 = no braking, 1.0 = max braking
    """
    steering: float = 0.0
    throttle: float = 0.0
    brake: float = 0.0

    @staticmethod
    def zero() -> "Action":
        """No steering, no throttle, no brake."""
        return Action(0.0, 0.0, 0.0)

    @staticmethod
    def emergency_brake() -> "Action":
        """Full braking, no steering, no throttle."""
        return Action(steering=0.0, throttle=0.0, brake=1.0)

    def to_dict(self) -> Dict[str, float]:
        return {"steering": self.steering, "throttle": self.throttle, "brake": self.brake}

    @staticmethod
    def from_dict(d: Dict[str, float]) -> "Action":
        return Action(
            steering=float(d.get("steering", 0.0)),
            throttle=float(d.get("throttle", 0.0)),
            brake=float(d.get("brake", 0.0)),
        )


@dataclass
class NearbyObject:
    """A nearby vehicle or pedestrian in the ego's observation."""
    object_id: str
    relative_x: float          # metres ahead (+) or behind (-) of ego
    relative_y: float          # metres left (+) or right (-) of ego
    relative_speed: float      # m/s, positive = moving away
    object_type: str           # "car" | "truck" | "pedestrian" | etc.
    ttc: float                 # time to collision in seconds (inf if no threat)


@dataclass
class Observation:
    """
    What the model sees at each timestep.

    Ground-truth values — no sensor noise unless the scenario
    has a sensor configuration with noise parameters.
    """
    ego_speed: float = 0.0                          # m/s
    ego_heading: float = 0.0                        # radians
    ego_acceleration: float = 0.0                   # m/s²
    ego_x: float = 0.0                              # world position
    ego_y: float = 0.0
    speed_limit: float = 0.0                        # m/s
    nearby_objects: List[NearbyObject] = field(default_factory=list)
    traffic_light_state: Optional[str] = None       # "red" | "green" | "yellow" | None
    lane_lateral_offset: float = 0.0                # metres from lane centre
    sim_time: float = 0.0                           # seconds

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ego_speed": self.ego_speed,
            "ego_heading": self.ego_heading,
            "ego_acceleration": self.ego_acceleration,
            "ego_x": self.ego_x,
            "ego_y": self.ego_y,
            "speed_limit": self.speed_limit,
            "nearby_objects": [
                {
                    "object_id": o.object_id,
                    "relative_x": o.relative_x,
                    "relative_y": o.relative_y,
                    "relative_speed": o.relative_speed,
                    "object_type": o.object_type,
                    "ttc": o.ttc,
                }
                for o in self.nearby_objects
            ],
            "traffic_light_state": self.traffic_light_state,
            "lane_lateral_offset": self.lane_lateral_offset,
            "sim_time": self.sim_time,
        }

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "Observation":
        nearby = [
            NearbyObject(**obj) for obj in d.get("nearby_objects", [])
        ]
        return Observation(
            ego_speed=d.get("ego_speed", 0.0),
            ego_heading=d.get("ego_heading", 0.0),
            ego_acceleration=d.get("ego_acceleration", 0.0),
            ego_x=d.get("ego_x", 0.0),
            ego_y=d.get("ego_y", 0.0),
            speed_limit=d.get("speed_limit", 0.0),
            nearby_objects=nearby,
            traffic_light_state=d.get("traffic_light_state"),
            lane_lateral_offset=d.get("lane_lateral_offset", 0.0),
            sim_time=d.get("sim_time", 0.0),
        )


class ModelInterface(ABC):
    """
    Abstract base class for all models submitted to ORION.

    Subclass this, implement predict() and reset(), then submit
    your model using upload_model() or OrionClient.submit_model().

    Your predict() method MUST be deterministic for a given observation
    and internal state — the same inputs must always produce the same output.
    """

    @abstractmethod
    def predict(self, observation: Observation) -> Action:
        """
        Produce a control action from the current observation.

        Called once per simulation tick (50 Hz = every 20ms).
        Must be fast: target < 5ms per call.
        Must be deterministic: same observation → same action.
        """
        ...

    @abstractmethod
    def reset(self) -> None:
        """
        Reset any internal state before a new simulation run starts.

        Called once before each run in a batch. If your model has
        stateful components (e.g. an LSTM hidden state), reset them here.
        """
        ...
