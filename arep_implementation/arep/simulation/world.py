"""
ORION World State Manager.

Handles world initialization, dynamic object updates, and spatial queries.
Does NOT handle physics updates to the ego vehicle (that's the engine's job).
"""

from __future__ import annotations

import math
from typing import List, Optional

import numpy as np

from arep.config import SimulationConfig
from arep.core.state import (
    WorldState, VehicleState, Vector2D,
    TrafficLightInfo, LaneInfo,
)
from arep.core.random_manager import RandomManager


class WorldManager:
    """
    Manages world state initialization and updates.

    Responsibilities:
      - Create initial WorldState from components
      - Update dynamic objects (constant-velocity for now)
      - Update traffic lights
      - Spatial queries (objects in range, objects ahead)
    """

    def __init__(self, config: SimulationConfig):
        self.config = config

    def create_initial_world(
        self,
        ego_initial: VehicleState,
        dynamic_objects: Optional[List[VehicleState]] = None,
        traffic_lights: Optional[List[TrafficLightInfo]] = None,
        lanes: Optional[List[LaneInfo]] = None,
        weather_condition: str = "clear",
        visibility: float = 1000.0,
    ) -> WorldState:
        """
        Create the initial world state from components.

        Args:
            ego_initial: Initial ego vehicle state.
            dynamic_objects: List of traffic objects.
            traffic_lights: List of traffic lights.
            lanes: List of lane definitions.
            weather_condition: Weather string.
            visibility: Visibility in metres.

        Returns:
            Initialized WorldState.
        """
        return WorldState(
            sim_time=0.0,
            timestep_count=0,
            ego_vehicle=ego_initial.copy(),
            dynamic_objects=[o.copy() for o in (dynamic_objects or [])],
            traffic_lights=[t.copy() for t in (traffic_lights or [])],
            lanes=[l.copy() for l in (lanes or [])],
            weather_condition=weather_condition,
            visibility=visibility,
            is_terminated=False,
            termination_reason=None,
            has_collision=False,
            collision_object_id=None,
            collision_time=None,
            last_action=None,
        )

    def update_dynamic_objects(
        self,
        world: WorldState,
        dt: float,
        rng: RandomManager,
    ) -> WorldState:
        """
        Update dynamic object positions using constant-velocity motion.

        Each object moves forward along its heading at its current speed.

        Args:
            world: Current world state (will be modified in-place).
            dt: Timestep in seconds.
            rng: Random manager (for future stochastic behaviors).

        Returns:
            Updated world state.
        """
        updated_objects = []

        for obj in world.dynamic_objects:
            new_obj = self._update_constant_velocity(obj, dt)
            updated_objects.append(new_obj)

        new_world = world.copy()
        new_world.dynamic_objects = updated_objects
        return new_world

    def update_traffic_lights(
        self,
        world: WorldState,
        rng: RandomManager,
    ) -> WorldState:
        """
        Update traffic light states based on time.

        Currently a no-op (static lights). Future: implement signal
        timing plans.

        Args:
            world: Current world state.
            rng: Random manager.

        Returns:
            Updated world state.
        """
        # Traffic lights are static for now
        return world

    # ── Spatial queries ──────────────────────────────────────────────

    def get_objects_in_range(
        self,
        world: WorldState,
        center: Vector2D,
        radius: float,
    ) -> List[VehicleState]:
        """Get all objects within radius of center point."""
        result = []
        for obj in world.dynamic_objects:
            if obj.position.distance_to(center) <= radius:
                result.append(obj)
        return result

    def get_objects_ahead(
        self,
        world: WorldState,
        max_distance: float = 100.0,
        max_lateral: float = 5.0,
    ) -> List[VehicleState]:
        """
        Get objects ahead of the ego vehicle, sorted by distance.

        Args:
            world: World state.
            max_distance: Max forward distance (metres).
            max_lateral: Max lateral distance (metres).

        Returns:
            Objects ahead, sorted nearest-first.
        """
        ego = world.ego_vehicle
        cos_ego = math.cos(-ego.heading)
        sin_ego = math.sin(-ego.heading)

        ahead = []
        for obj in world.dynamic_objects:
            dx = obj.position.x - ego.position.x
            dy = obj.position.y - ego.position.y

            forward = dx * cos_ego - dy * sin_ego
            lateral = dx * sin_ego + dy * cos_ego

            if 0.0 < forward <= max_distance and abs(lateral) <= max_lateral:
                ahead.append(obj)

        ahead.sort(key=lambda o: o.position.distance_to(ego.position))
        return ahead

    # ── Private helpers ──────────────────────────────────────────────

    @staticmethod
    def _update_constant_velocity(
        obj: VehicleState,
        dt: float,
    ) -> VehicleState:
        """Update object with constant-velocity straight-line motion."""
        new_obj = obj.copy()
        new_obj.position = Vector2D(
            obj.position.x + obj.velocity * math.cos(obj.heading) * dt,
            obj.position.y + obj.velocity * math.sin(obj.heading) * dt,
        )
        return new_obj
