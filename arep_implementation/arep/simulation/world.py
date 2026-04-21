"""
ORION World State Manager.

Handles world initialization, dynamic object updates, and spatial queries.
Does NOT handle physics updates to the ego vehicle (that's the engine's job).
"""

from __future__ import annotations

import math
from typing import Dict, List, Optional

import numpy as np

from arep.config import SimulationConfig
from arep.core.state import (
    WorldState, VehicleState, Vector2D,
    TrafficLightInfo, LaneInfo,
)
from arep.core.random_manager import RandomManager
from arep.simulation import npc_bt


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
        Update dynamic object positions.

        Dispatches to constant-velocity or scripted behavior per NPC.
        Scripted behavior state (_triggered) is stored in world.npc_behaviors
        and persists across ticks via WorldState.copy().
        """
        updated_objects = []

        for obj in world.dynamic_objects:
            behavior = world.npc_behaviors.get(obj.object_id)
            btype = behavior["type"] if behavior else "constant_velocity"

            if btype in ("reactive_vehicle", "reactive_pedestrian"):
                bt = npc_bt.get_bt(behavior["bt_type"])
                new_obj = bt.tick(obj, behavior, world, rng, dt)
            elif btype == "scripted":
                new_obj = self._update_scripted(obj, behavior, world, dt)
            else:
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

    def _update_scripted(
        self,
        obj: VehicleState,
        behavior: dict,
        world: WorldState,
        dt: float,
    ) -> VehicleState:
        """
        Execute one tick of scripted NPC behavior.

        Trigger types:
          proximity  — fires when Euclidean distance to ego <= trigger_value (m)
          time       — fires when world.sim_time >= trigger_value (s)
          ttc        — fires when computed TTC to ego <= trigger_value (s)

        Post-trigger actions:
          Longitudinal deceleration/acceleration toward min_velocity.
          cut_in: lateral maneuver toward lateral_target_y at lateral_speed.
          start_velocity: override velocity to this value on first trigger tick.
        """
        params = behavior["parameters"]

        # ── Check trigger ──────────────────────────────────────────────
        if not behavior["_triggered"]:
            trigger_type = params.get("trigger_type", "time")
            trigger_value = float(params.get("trigger_value", 0.0))

            fired = False
            if trigger_type == "time":
                fired = world.sim_time >= trigger_value
            elif trigger_type == "proximity":
                dist = obj.position.distance_to(world.ego_vehicle.position)
                fired = dist <= trigger_value
            elif trigger_type == "ttc":
                ttc = self._compute_ttc(obj, world.ego_vehicle)
                fired = (ttc is not None) and (ttc <= trigger_value)

            if fired:
                behavior["_triggered"] = True
                behavior["_trigger_time"] = world.sim_time

        # ── Apply behavior ─────────────────────────────────────────────
        new_obj = obj.copy()

        if behavior["_triggered"]:
            # On the very first trigger tick, override velocity if requested
            if behavior["_trigger_time"] == world.sim_time:
                start_v = params.get("start_velocity")
                if start_v is not None:
                    new_obj.velocity = float(start_v)

            cut_in = params.get("cut_in", False)

            if cut_in:
                new_obj = self._apply_cut_in(new_obj, params, dt)
            else:
                new_obj = self._apply_longitudinal(new_obj, params, dt)
        else:
            # Pre-trigger: constant velocity
            new_obj.position = Vector2D(
                obj.position.x + obj.velocity * math.cos(obj.heading) * dt,
                obj.position.y + obj.velocity * math.sin(obj.heading) * dt,
            )

        return new_obj

    @staticmethod
    def _apply_longitudinal(
        obj: VehicleState,
        params: dict,
        dt: float,
    ) -> VehicleState:
        """Apply longitudinal acceleration/deceleration toward min_velocity."""
        accel = float(params.get("post_acceleration", 0.0))
        min_v = float(params.get("min_velocity", 0.0))
        max_v = float(params.get("max_velocity", 1000.0))

        new_v = obj.velocity + accel * dt
        new_v = max(min_v, min(max_v, new_v))

        new_obj = obj.copy()
        new_obj.velocity = new_v
        new_obj.acceleration = accel
        new_obj.position = Vector2D(
            obj.position.x + new_v * math.cos(obj.heading) * dt,
            obj.position.y + new_v * math.sin(obj.heading) * dt,
        )
        return new_obj

    @staticmethod
    def _apply_cut_in(
        obj: VehicleState,
        params: dict,
        dt: float,
    ) -> VehicleState:
        """
        Execute a lateral cut-in maneuver.

        The NPC moves laterally toward lateral_target_y at lateral_speed (m/s)
        while maintaining its longitudinal velocity. Once at the target y,
        heading snaps back to 0 (east).
        """
        target_y = float(params.get("lateral_target_y", obj.position.y))
        lat_speed = float(params.get("lateral_speed", 1.0))
        lon_v = float(params.get("post_velocity", obj.velocity))

        dy = target_y - obj.position.y
        if abs(dy) < 0.05:
            # Already in target lane — resume straight
            new_obj = obj.copy()
            new_obj.heading = 0.0 if obj.velocity >= 0 else math.pi
            new_obj.position = Vector2D(
                obj.position.x + lon_v * math.cos(new_obj.heading) * dt,
                target_y,
            )
            return new_obj

        lat_delta = math.copysign(min(lat_speed * dt, abs(dy)), dy)
        lon_delta = lon_v * dt

        new_obj = obj.copy()
        new_obj.velocity = lon_v
        new_obj.position = Vector2D(
            obj.position.x + lon_delta * math.cos(obj.heading),
            obj.position.y + lat_delta,
        )
        # Tilt heading toward target for visual correctness
        new_obj.heading = math.atan2(lat_delta, max(abs(lon_delta), 1e-6))
        if obj.heading > math.pi / 2 or obj.heading < -math.pi / 2:
            new_obj.heading = math.pi - new_obj.heading
        return new_obj

    @staticmethod
    def _compute_ttc(
        obj: VehicleState,
        ego: VehicleState,
    ) -> Optional[float]:
        """
        Compute 1-D Time-To-Collision between obj and ego along ego's heading.

        Returns None if objects are diverging or gap is already zero.
        """
        dx = obj.position.x - ego.position.x
        dy = obj.position.y - ego.position.y
        gap = math.sqrt(dx * dx + dy * dy) - (obj.length / 2.0 + ego.length / 2.0)
        if gap <= 0.0:
            return 0.0

        # Relative closing speed along the line connecting them
        rel_vx = ego.velocity * math.cos(ego.heading) - obj.velocity * math.cos(obj.heading)
        rel_vy = ego.velocity * math.sin(ego.heading) - obj.velocity * math.sin(obj.heading)
        rel_v = math.sqrt(rel_vx * rel_vx + rel_vy * rel_vy)

        if rel_v < 1e-6:
            return None   # not closing
        return gap / rel_v
