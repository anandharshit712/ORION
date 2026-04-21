"""
ORION Scenario Schema.

Data structures representing a complete scenario definition.
Loaded from YAML by the ScenarioParser.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


# ── Enums ────────────────────────────────────────────────────────────────

class RoadType(Enum):
    HIGHWAY = "highway"
    URBAN = "urban"
    RESIDENTIAL = "residential"
    RURAL = "rural"


class WeatherCondition(Enum):
    CLEAR = "clear"
    RAIN = "rain"
    FOG = "fog"
    SNOW = "snow"


class EventType(Enum):
    SPAWN_VEHICLE = "spawn_vehicle"
    SPAWN_PEDESTRIAN = "spawn_pedestrian"
    CHANGE_TRAFFIC_LIGHT = "change_traffic_light"
    CHANGE_WEATHER = "change_weather"
    OBJECT_BEHAVIOR_CHANGE = "object_behavior_change"


# ── Component dataclasses ────────────────────────────────────────────────

@dataclass
class VehicleInitialCondition:
    """Initial conditions for a vehicle."""
    x: float = 0.0
    y: float = 0.0
    heading: float = 0.0
    velocity: float = 0.0
    object_type: str = "car"
    object_id: Optional[str] = None


@dataclass
class VehicleConstraints:
    """Physical constraints for the ego vehicle."""
    max_velocity: float = 30.0
    max_acceleration: float = 3.0
    max_deceleration: float = 8.0
    max_steering: float = 0.5


@dataclass
class RoadConfiguration:
    """Road environment configuration."""
    road_type: str = "highway"
    lanes: int = 2
    lane_width: float = 3.5
    speed_limit: float = 27.8  # ~100 km/h


@dataclass
class WeatherConfiguration:
    """Weather and visibility configuration."""
    condition: str = "clear"
    visibility: float = 1000.0


@dataclass
class TrafficObjectBehavior:
    """Behavior specification for a traffic object."""
    type: str = "constant_velocity"  # constant_velocity, scripted, follow_lane
    parameters: Dict[str, Any] = field(default_factory=dict)


@dataclass
class TrafficObjectDefinition:
    """Complete definition of a traffic object."""
    id: str = ""
    type: str = "car"
    initial: VehicleInitialCondition = field(
        default_factory=VehicleInitialCondition
    )
    behavior: TrafficObjectBehavior = field(
        default_factory=TrafficObjectBehavior
    )


@dataclass
class ScenarioEvent:
    """Timed event during simulation."""
    type: str = ""
    trigger_time: float = 0.0
    parameters: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ScenarioTermination:
    """Termination conditions for the scenario."""
    conditions: List[str] = field(
        default_factory=lambda: ["collision", "off_road", "timeout"]
    )
    timeout: float = 60.0


# ── Master ScenarioDefinition ───────────────────────────────────────────

@dataclass
class ScenarioDefinition:
    """
    Complete scenario definition.

    This is the master data structure loaded from YAML.
    """
    # Metadata
    name: str = "unnamed"
    version: str = "1.0"
    description: str = ""
    duration: float = 60.0

    # Ego vehicle
    ego_initial: VehicleInitialCondition = field(
        default_factory=VehicleInitialCondition
    )
    ego_constraints: VehicleConstraints = field(
        default_factory=VehicleConstraints
    )

    # Environment
    road: RoadConfiguration = field(default_factory=RoadConfiguration)
    weather: WeatherConfiguration = field(default_factory=WeatherConfiguration)

    # Traffic
    traffic_objects: List[TrafficObjectDefinition] = field(
        default_factory=list
    )

    # Events
    events: List[ScenarioEvent] = field(default_factory=list)

    # Termination
    termination: ScenarioTermination = field(
        default_factory=ScenarioTermination
    )

    # Seed (optional override)
    master_seed: Optional[int] = None

    # Dynamic parameterization ranges (applied by ScenarioParameterizer at run time)
    parameterization: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "scenario": {
                "name": self.name,
                "version": self.version,
                "description": self.description,
                "duration": self.duration,
            },
            "ego": {
                "initial": {
                    "x": self.ego_initial.x,
                    "y": self.ego_initial.y,
                    "heading": self.ego_initial.heading,
                    "velocity": self.ego_initial.velocity,
                },
                "constraints": {
                    "max_velocity": self.ego_constraints.max_velocity,
                    "max_acceleration": self.ego_constraints.max_acceleration,
                    "max_deceleration": self.ego_constraints.max_deceleration,
                    "max_steering": self.ego_constraints.max_steering,
                },
            },
            "environment": {
                "road": {
                    "type": self.road.road_type,
                    "lanes": self.road.lanes,
                    "lane_width": self.road.lane_width,
                    "speed_limit": self.road.speed_limit,
                },
                "weather": {
                    "condition": self.weather.condition,
                    "visibility": self.weather.visibility,
                },
            },
            "traffic": [
                {
                    "id": o.id,
                    "type": o.type,
                    "initial": {
                        "x": o.initial.x,
                        "y": o.initial.y,
                        "heading": o.initial.heading,
                        "velocity": o.initial.velocity,
                    },
                    "behavior": {
                        "type": o.behavior.type,
                        "parameters": o.behavior.parameters,
                    },
                }
                for o in self.traffic_objects
            ],
            "events": [
                {
                    "type": e.type,
                    "trigger_time": e.trigger_time,
                    "parameters": e.parameters,
                }
                for e in self.events
            ],
            "termination": {
                "conditions": self.termination.conditions,
                "timeout": self.termination.timeout,
            },
        }
