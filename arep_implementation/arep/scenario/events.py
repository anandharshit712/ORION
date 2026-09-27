"""
ORION Scenario Event System.

Handles timed events during simulation:
  - spawn_vehicle / spawn_pedestrian
  - change_traffic_light

Each event fires exactly once, in deterministic order.

`change_traffic_light` and `change_weather` were advertised here and never
implemented (DI-02). `_execute` returned the world unchanged for any type it
did not know, with no error and no log line, so EMG-004 loaded, ran and scored
as if its ice patch were there. That is the exact failure the project rules out
everywhere else: unsupported input is skipped *and reported*, never silently
dropped, because a scenario missing its hazard still produces a score.

`IMPLEMENTED_EVENT_TYPES` is now the single list, and `ScenarioValidator`
refuses a scenario that uses anything else. Add a type here only when its
handler exists.

`change_traffic_light` is implemented rather than removed, because INT-002
needs it: that scenario has been testing a light that never changed, which is
precisely the silent-hazard problem. `change_weather` stays unimplemented and
therefore refused until DI-01 gives weather something to change.
"""

from __future__ import annotations

from typing import List

from arep.scenario.schema import ScenarioEvent
from arep.core.state import (
    ObjectType,
    TrafficLightState,
    Vector2D,
    VehicleState,
    WorldState,
)
from arep.core.random_manager import RandomManager
from arep.utils.exceptions import ScenarioParseError

# The only event types with a handler. Read by ScenarioValidator, so adding a
# name here without writing the handler re-opens the silent-drop hole.
IMPLEMENTED_EVENT_TYPES = frozenset(
    {"spawn_vehicle", "spawn_pedestrian", "change_traffic_light"}
)


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
        elif event.type == "change_traffic_light":
            return self._change_traffic_light(world, event)

        # Unreachable through a validated scenario: the validator refuses these
        # at load. Kept as an assertion rather than a silent `return world`,
        # because a scenario reaching here has a hazard that will not happen
        # and must not be scored as though it did.
        raise ScenarioParseError(
            f"Event type {event.type!r} has no handler. Implemented types: "
            f"{sorted(IMPLEMENTED_EVENT_TYPES)}."
        )

    @staticmethod
    def _change_traffic_light(world: WorldState, event: ScenarioEvent) -> WorldState:
        """Set one light's state.

        A light_id that does not exist raises rather than passing silently:
        a scenario that schedules a change to a light it cannot name is
        testing a light that never changes, which is the bug this whole entry
        is about.
        """
        p = event.parameters
        light_id = str(p["light_id"])
        state = TrafficLightState(str(p["state"]))

        known = [t.light_id for t in world.traffic_lights]
        if light_id not in known:
            raise ScenarioParseError(
                f"change_traffic_light refers to unknown light {light_id!r}; "
                f"this scenario defines {known}."
            )

        new_world = world.copy()
        for light in new_world.traffic_lights:
            if light.light_id == light_id:
                light.state = state
                # The countdown belonged to the previous phase; leaving it
                # would have the frame advertise a change that is not coming.
                light.time_remaining = float(p.get("time_remaining", 0.0))
        return new_world

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
        world: WorldState,
        event: ScenarioEvent,
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
