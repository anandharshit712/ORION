"""
ORION Scenario Executor.

Converts a ScenarioDefinition into an initial WorldState
that the simulation engine can run.
"""

from __future__ import annotations

from typing import List

import numpy as np

from arep.config import SimulationConfig
from arep.core.state import (
    WorldState, VehicleState, Vector2D,
    TrafficLightInfo, LaneInfo, ObjectType,
)
from arep.core.random_manager import RandomManager
from arep.scenario.schema import ScenarioDefinition
from arep.scenario.parameterizer import ScenarioParameterizer
from arep.simulation.world import WorldManager


# Mapping from string type to ObjectType enum
_TYPE_MAP = {
    "car": ObjectType.CAR,
    "truck": ObjectType.TRUCK,
    "motorcycle": ObjectType.MOTORCYCLE,
    "pedestrian": ObjectType.PEDESTRIAN,
    "bicycle": ObjectType.BICYCLE,
}

# Default dimensions by type
_DIMENSIONS = {
    ObjectType.CAR: (4.5, 2.0),
    ObjectType.TRUCK: (8.0, 2.5),
    ObjectType.MOTORCYCLE: (2.2, 0.8),
    ObjectType.PEDESTRIAN: (0.5, 0.5),
    ObjectType.BICYCLE: (1.8, 0.6),
}


class ScenarioExecutor:
    """
    Convert ScenarioDefinition → initial WorldState.

    Creates the ego vehicle, traffic objects, lane graph, and
    traffic lights from the scenario definition.
    """

    def __init__(self, config: SimulationConfig):
        self.config = config
        self.world_manager = WorldManager(config)
        self.parameterizer = ScenarioParameterizer()

    def create_initial_world(
        self,
        scenario: ScenarioDefinition,
        rng: RandomManager,
    ) -> WorldState:
        """
        Build the initial WorldState.

        Args:
            scenario: Parsed and validated scenario.
            rng: Random manager.

        Returns:
            Ready-to-simulate WorldState.
        """
        # L2: apply dynamic parameterization ranges before building world
        self.parameterizer.apply(scenario, rng)

        ego = self._create_ego(scenario)
        objects = self._create_traffic_objects(scenario)
        lanes = self._create_lanes(scenario)
        lights = self._create_traffic_lights(scenario, rng)
        npc_behaviors = self._build_npc_behaviors(scenario)

        world = self.world_manager.create_initial_world(
            ego_initial=ego,
            dynamic_objects=objects,
            traffic_lights=lights,
            lanes=lanes,
            weather_condition=scenario.weather.condition,
            visibility=scenario.weather.visibility,
        )
        world.npc_behaviors = npc_behaviors
        return world

    # ── Private builders ─────────────────────────────────────────────

    def _create_ego(self, scenario: ScenarioDefinition) -> VehicleState:
        init = scenario.ego_initial
        return VehicleState(
            position=Vector2D(init.x, init.y),
            heading=init.heading,
            velocity=init.velocity,
            acceleration=0.0,
            length=self.config.vehicle_length,
            width=self.config.vehicle_width,
            wheelbase=self.config.wheelbase,
            object_type=ObjectType.CAR,
            object_id="ego",
        )

    def _create_traffic_objects(
        self, scenario: ScenarioDefinition,
    ) -> List[VehicleState]:
        objects = []
        for obj_def in scenario.traffic_objects:
            init = obj_def.initial
            obj_type = _TYPE_MAP.get(obj_def.type, ObjectType.CAR)
            length, width = _DIMENSIONS.get(obj_type, (4.5, 2.0))

            objects.append(VehicleState(
                position=Vector2D(init.x, init.y),
                heading=init.heading,
                velocity=init.velocity,
                acceleration=0.0,
                length=length,
                width=width,
                wheelbase=2.7,
                object_type=obj_type,
                object_id=obj_def.id,
            ))
        return objects

    def _create_lanes(
        self, scenario: ScenarioDefinition,
    ) -> List[LaneInfo]:
        """Create simple straight-road lanes from road config."""
        road = scenario.road
        lanes = []

        for lane_idx in range(road.lanes):
            # Lane center y-coordinate (centered around y=0)
            lane_y = (lane_idx - road.lanes / 2.0 + 0.5) * road.lane_width

            # Straight centerline (1 km)
            centerline = [
                Vector2D(float(x), lane_y)
                for x in np.linspace(0, 1000, 100)
            ]

            lanes.append(LaneInfo(
                lane_id=f"lane_{lane_idx}",
                centerline_points=centerline,
                width=road.lane_width,
                speed_limit=road.speed_limit,
            ))

        return lanes

    def _build_npc_behaviors(
        self, scenario: ScenarioDefinition,
    ) -> dict:
        """Build the npc_behaviors registry from traffic object behavior definitions."""
        registry = {}
        for obj_def in scenario.traffic_objects:
            btype = obj_def.behavior.type
            if btype == "constant_velocity":
                continue
            entry: dict = {
                "type": btype,
                "parameters": dict(obj_def.behavior.parameters),
                "_triggered": False,
                "_trigger_time": None,
            }
            # Carry bt_type for reactive_vehicle / reactive_pedestrian dispatch
            if btype in ("reactive_vehicle", "reactive_pedestrian"):
                entry["bt_type"] = obj_def.behavior.parameters.get("bt_type", "")
            registry[obj_def.id] = entry
        return registry

    def _create_traffic_lights(
        self,
        scenario: ScenarioDefinition,
        rng: RandomManager,
    ) -> List[TrafficLightInfo]:
        """Placeholder — no traffic lights from scenario yet."""
        return []
