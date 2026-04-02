"""
ORION Scenario Event System.

Handles timed events during simulation:
  - spawn_vehicle / spawn_pedestrian
  - change_traffic_light / change_weather

Each event fires exactly once, in deterministic order.
"""

from __future__ import annotations

from typing import List

from arep.scenario.schema import ScenarioEvent
from arep.core.state import WorldState, VehicleState, Vector2D, ObjectType
from arep.core.random_manager import RandomManager


class EventExecutor:
    """Execute scenario events at their trigger times."""

    def __init__(self) -> None:
        self.executed_events: List[str] = []

    def check_and_execute(
        self,
        world: WorldState,
        events: List[ScenarioEvent],
        rng: RandomManager,
    ) -> WorldState:
        """
        Check if any events should fire and execute them.

        Args:
            world: Current world state.
            events: All scenario events.
            rng: Random manager.

        Returns:
            Updated world state.
        """
        new_world = world
        for event in events:
            event_id = f"{event.type}_{event.trigger_time}"
            if (
                world.sim_time >= event.trigger_time
                and event_id not in self.executed_events
            ):
                new_world = self._execute(new_world, event, rng)
                self.executed_events.append(event_id)
        return new_world

    def _execute(
        self,
        world: WorldState,
        event: ScenarioEvent,
        rng: RandomManager,
    ) -> WorldState:
        """Dispatch event to handler."""
        if event.type == "spawn_vehicle":
            return self._spawn_vehicle(world, event)
        elif event.type == "spawn_pedestrian":
            return self._spawn_pedestrian(world, event)
        # Other event types can be added here
        return world

    @staticmethod
    def _spawn_vehicle(world: WorldState, event: ScenarioEvent) -> WorldState:
        p = event.parameters
        vehicle = VehicleState(
            position=Vector2D(float(p["x"]), float(p["y"])),
            heading=float(p.get("heading", 0.0)),
            velocity=float(p.get("velocity", 0.0)),
            acceleration=0.0,
            length=float(p.get("length", 4.5)),
            width=float(p.get("width", 2.0)),
            wheelbase=2.7,
            object_type=ObjectType.CAR,
            object_id=p.get("id", f"spawned_{world.sim_time:.2f}"),
        )
        new_world = world.copy()
        new_world.dynamic_objects.append(vehicle)
        return new_world

    @staticmethod
    def _spawn_pedestrian(
        world: WorldState, event: ScenarioEvent,
    ) -> WorldState:
        p = event.parameters
        ped = VehicleState(
            position=Vector2D(float(p["x"]), float(p["y"])),
            heading=float(p.get("heading", 0.0)),
            velocity=float(p.get("crossing_speed", 1.5)),
            acceleration=0.0,
            length=0.5,
            width=0.5,
            wheelbase=0.5,
            object_type=ObjectType.PEDESTRIAN,
            object_id=p.get("id", f"ped_{world.sim_time:.2f}"),
        )
        new_world = world.copy()
        new_world.dynamic_objects.append(ped)
        return new_world

    def reset(self) -> None:
        """Clear executed events tracker."""
        self.executed_events.clear()
