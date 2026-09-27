"""
Scenario events must be implemented or refused (DI-02).

`EventExecutor._execute` returned the world unchanged for any type it did not
recognise — no error, no log line. EMG-004 declared a black-ice
`change_weather` and INT-002 declared two `change_traffic_light` events; both
loaded, ran, and scored as though their hazards had happened. INT-002 in
particular had been testing a traffic light that never changed colour.

That is the failure the project rules out everywhere else: unsupported input is
skipped *and reported*, never silently dropped, because a scenario missing its
hazard still produces a score and a score is what a customer reads.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from arep.core.random_manager import RandomManager  # noqa: E402
from arep.core.state import TrafficLightInfo, TrafficLightState, Vector2D  # noqa: E402
from arep.scenario.events import (  # noqa: E402
    IMPLEMENTED_EVENT_TYPES,
    EventExecutor,
)
from arep.scenario.parser import ScenarioParser  # noqa: E402
from arep.scenario.schema import ScenarioEvent  # noqa: E402
from arep.utils.exceptions import ScenarioParseError  # noqa: E402

LIBRARY = Path(__file__).resolve().parent.parent.parent / "scenarios"

# Refused on purpose until DI-01 gives weather something to change. Listed here
# rather than silently skipped so that the day it starts loading, this test
# fails and someone has to decide whether that is correct.
KNOWN_UNLOADABLE = {"EMG-004_black_ice_friction_loss.yaml"}


def _world_with_light(state=TrafficLightState.GREEN):
    from arep.core.state import VehicleState, WorldState

    return WorldState(
        sim_time=0.0,
        timestep_count=0,
        ego_vehicle=VehicleState(position=Vector2D(0.0, 0.0), velocity=10.0),
        traffic_lights=[
            TrafficLightInfo(
                light_id="tl_intersection",
                position=Vector2D(50.0, 0.0),
                state=state,
                time_remaining=5.0,
            )
        ],
    )


# -- The refusal -----------------------------------------------------------


def test_an_unimplemented_event_type_fails_validation():
    """At load, not at run time. A scenario that reaches the engine with a
    hazard nobody will execute is already too late — it will be scored.

    The validator is exercised directly rather than through the parser: the
    parser raises on the first validation error, and what is being pinned here
    is the message, which is what a customer sees.
    """
    from arep.scenario.schema import ScenarioDefinition
    from arep.scenario.validator import ScenarioValidator

    scenario = ScenarioDefinition(name="unimplemented event", duration=10.0)
    scenario.events = [
        ScenarioEvent(
            type="change_weather", trigger_time=2.0, parameters={"condition": "ice"}
        )
    ]

    errors = ScenarioValidator().validate(scenario)
    assert any("change_weather" in e for e in errors), errors
    assert any("unimplemented" in e.lower() for e in errors), errors


def test_the_executor_refuses_rather_than_returning_the_world_unchanged():
    """Defence in depth. The validator is the gate, but a `return world` here
    is what made the whole class of bug invisible, so it must not come back."""
    executor = EventExecutor()
    event = ScenarioEvent(
        type="change_weather", trigger_time=0.0, parameters={"condition": "ice"}
    )

    with pytest.raises(ScenarioParseError, match="no handler"):
        executor._execute(_world_with_light(), event, RandomManager(1))


def test_implemented_types_are_exactly_the_ones_with_handlers():
    """Adding a name to the set without writing its handler would re-open the
    hole, and would do it quietly."""
    executor = EventExecutor()
    for event_type in IMPLEMENTED_EVENT_TYPES:
        assert hasattr(
            executor, f"_{event_type}"
        ), f"{event_type} is declared implemented but has no _{event_type} handler"


# -- change_traffic_light --------------------------------------------------


def test_changing_a_light_actually_changes_it():
    """INT-002 declared two of these and neither did anything, so the scenario
    scored a model against a light stuck on its initial colour."""
    executor = EventExecutor()
    world = _world_with_light(TrafficLightState.GREEN)
    event = ScenarioEvent(
        type="change_traffic_light",
        trigger_time=0.0,
        parameters={"light_id": "tl_intersection", "state": "red"},
    )

    new_world = executor._execute(world, event, RandomManager(1))

    assert new_world.traffic_lights[0].state is TrafficLightState.RED
    # Immutability (CLAUDE.md §4): the input world is never modified.
    assert world.traffic_lights[0].state is TrafficLightState.GREEN


def test_changing_an_unknown_light_is_refused():
    """A light_id nobody defined is a scenario that schedules a change to
    nothing — the same silent hazard, one level down."""
    executor = EventExecutor()
    event = ScenarioEvent(
        type="change_traffic_light",
        trigger_time=0.0,
        parameters={"light_id": "tl_does_not_exist", "state": "red"},
    )

    with pytest.raises(ScenarioParseError, match="unknown light"):
        executor._execute(_world_with_light(), event, RandomManager(1))


def test_the_countdown_does_not_survive_a_change():
    """time_remaining belonged to the previous phase. Carrying it over would
    have the frame advertise a change that is not coming."""
    executor = EventExecutor()
    event = ScenarioEvent(
        type="change_traffic_light",
        trigger_time=0.0,
        parameters={"light_id": "tl_intersection", "state": "red"},
    )

    new_world = executor._execute(_world_with_light(), event, RandomManager(1))
    assert new_world.traffic_lights[0].time_remaining == 0.0


# -- The library -----------------------------------------------------------


def test_every_scenario_uses_only_implemented_event_types():
    """The library-wide check. It is expected to fail on EMG-004 until DI-01
    ships, which is the point — the gap is loud rather than silent."""
    parser = ScenarioParser()
    offenders = {}

    for path in sorted(LIBRARY.rglob("*.yaml")):
        if path.name in KNOWN_UNLOADABLE:
            continue
        scenario, _ = parser.parse_file(str(path))
        unknown = [
            e.type for e in scenario.events if e.type not in IMPLEMENTED_EVENT_TYPES
        ]
        if unknown:
            offenders[path.name] = unknown

    assert not offenders, f"scenarios declare unimplemented events: {offenders}"


def test_the_known_unloadable_scenario_is_still_unloadable():
    """EMG-004 declares a black-ice change_weather that the engine cannot
    execute. It must stay refused: the day it loads, either DI-01 shipped and
    this list needs updating, or the refusal was weakened."""
    parser = ScenarioParser()

    for name in KNOWN_UNLOADABLE:
        matches = list(LIBRARY.rglob(name))
        if not matches:
            continue
        with pytest.raises(Exception):
            parser.parse_file(str(matches[0]))
