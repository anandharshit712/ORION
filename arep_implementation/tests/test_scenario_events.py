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


# ══ Events reaching a real run ═══════════════════════════════════════════════
#
# EventExecutor was written, unit-tested and called from nowhere. Every event in
# the library was a no-op: LON-007's obstacle never spawned, INT-002's traffic
# light never changed. The unit tests above all passed the whole time, because
# they exercised the executor directly.
#
# So these go through the engine and the batch runner instead. A test that calls
# _execute() cannot tell whether anything in the product calls _execute().


def test_due_events_fire_once_on_the_tick_that_contains_them():
    from arep.scenario.events import due_events

    events = [
        ScenarioEvent(type="spawn_vehicle", trigger_time=0.0, parameters={}),
        ScenarioEvent(type="spawn_vehicle", trigger_time=3.0, parameters={}),
    ]

    # t=0 fires the zero-time event: the interval is (t-dt, t].
    assert len(due_events(events, 0.0, 0.02)) == 1
    # Nothing in between.
    assert due_events(events, 1.5, 0.02) == []
    # The 3.0 s event fires on the tick that ends at 3.0, and only then.
    assert len(due_events(events, 3.0, 0.02)) == 1
    assert due_events(events, 3.02, 0.02) == []


def test_a_spawn_event_actually_spawns_during_a_run():
    """The whole defect in one assertion. LON-007 declares a stationary vehicle
    appearing at t=3; before this was wired the scenario ran to timeout with an
    empty road and scored a non-braking model as safe."""
    from arep.config import get_config
    from arep.core.action import Action
    from arep.core.random_manager import RandomManager
    from arep.scenario.executor import ScenarioExecutor
    from arep.scenario.parser import ScenarioParser
    from arep.simulation.engine import SimulationEngine

    cfg = get_config().simulation
    scenario, _ = ScenarioParser().parse_file(
        str(LIBRARY / "lon" / "LON-007_sudden_obstacle_in_lane.yaml")
    )
    rng = RandomManager(42)
    world = ScenarioExecutor(cfg).create_initial_world(scenario, rng)
    engine = SimulationEngine(cfg)

    assert world.dynamic_objects == [], "LON-007 should start with an empty road"

    # Coast past the 3 s trigger.
    for _ in range(int(4.0 / cfg.timestep)):
        world = engine.step(world, Action.zero(), rng, scenario.events)
        if world.is_terminated:
            break

    assert world.dynamic_objects, "the spawn event never fired during the run"


def test_a_scenario_without_events_is_unaffected():
    """The event stage runs on every tick of every scenario. It must cost
    nothing and change nothing where there are no events."""
    from arep.config import get_config
    from arep.core.action import Action
    from arep.core.random_manager import RandomManager
    from arep.scenario.executor import ScenarioExecutor
    from arep.scenario.parser import ScenarioParser
    from arep.simulation.engine import SimulationEngine

    cfg = get_config().simulation
    path = str(LIBRARY / "lon" / "LON-003_emergency_stop.yaml")

    # Parsed twice, deliberately. `ScenarioParameterizer` mutates the
    # definition it is given — `ego_x_jitter` is added to the existing x — so
    # building two worlds from one parsed scenario applies the jitter twice and
    # they diverge for a reason that has nothing to do with events. The batch
    # runner re-parses per run, so this is a trap for callers rather than a
    # live defect, but it is one worth not falling into here.
    scenario_a, _ = ScenarioParser().parse_file(path)
    scenario_b, _ = ScenarioParser().parse_file(path)
    assert scenario_a.events == []

    engine = SimulationEngine(cfg)
    a = ScenarioExecutor(cfg).create_initial_world(scenario_a, RandomManager(9))
    b = ScenarioExecutor(cfg).create_initial_world(scenario_b, RandomManager(9))

    rng_a, rng_b = RandomManager(9), RandomManager(9)
    for _ in range(50):
        a = engine.step(a, Action.zero(), rng_a, scenario_a.events)
        b = engine.step(b, Action.zero(), rng_b, None)

    assert a.ego_vehicle.position.x == b.ego_vehicle.position.x


def test_a_junction_that_declares_a_light_gets_one():
    """`Junction.has_traffic_light` was set by the road templates and read by
    nobody: world.traffic_lights was always empty, so
    Observation.traffic_light_state was always OFF at 1000 m."""
    from arep.config import get_config
    from arep.core.random_manager import RandomManager
    from arep.core.state import TrafficLightState
    from arep.scenario.executor import ScenarioExecutor
    from arep.scenario.parser import ScenarioParser

    cfg = get_config().simulation
    scenario, _ = ScenarioParser().parse_file(
        str(LIBRARY / "int" / "INT-002_traffic_light_stop_and_go.yaml")
    )
    world = ScenarioExecutor(cfg).create_initial_world(scenario, RandomManager(1))

    assert world.traffic_lights, "the junction declares a light and got none"
    assert world.get_nearest_traffic_light() is not None
    assert world.traffic_lights[0].state is TrafficLightState.RED


def test_the_model_can_see_the_light():
    """A light in the world that the observation does not carry is still a
    scenario testing nothing."""
    from arep.config import get_config
    from arep.core.observation import Observation
    from arep.core.random_manager import RandomManager
    from arep.core.state import TrafficLightState
    from arep.scenario.executor import ScenarioExecutor
    from arep.scenario.parser import ScenarioParser

    cfg = get_config().simulation
    scenario, _ = ScenarioParser().parse_file(
        str(LIBRARY / "int" / "INT-002_traffic_light_stop_and_go.yaml")
    )
    world = ScenarioExecutor(cfg).create_initial_world(scenario, RandomManager(1))

    obs = Observation.from_world_state(world, None)
    assert obs.traffic_light_state is not TrafficLightState.OFF
    assert obs.traffic_light_distance < 1000.0


def test_changing_a_light_mid_run_reaches_the_observation():
    """INT-002's two events, end to end: the light starts red and is green
    after the second event fires."""
    from arep.config import get_config
    from arep.core.action import Action
    from arep.core.observation import Observation
    from arep.core.random_manager import RandomManager
    from arep.core.state import TrafficLightState
    from arep.scenario.executor import ScenarioExecutor
    from arep.scenario.parser import ScenarioParser
    from arep.simulation.engine import SimulationEngine

    cfg = get_config().simulation
    scenario, _ = ScenarioParser().parse_file(
        str(LIBRARY / "int" / "INT-002_traffic_light_stop_and_go.yaml")
    )
    rng = RandomManager(5)
    world = ScenarioExecutor(cfg).create_initial_world(scenario, rng)
    engine = SimulationEngine(cfg)

    seen = set()
    for _ in range(int(12.0 / cfg.timestep)):
        world = engine.step(world, Action.zero(), rng, scenario.events)
        seen.add(Observation.from_world_state(world, None).traffic_light_state)
        if world.is_terminated:
            break

    assert TrafficLightState.GREEN in seen, (
        "the light never turned green — the 10 s change_traffic_light event "
        "did not reach the run"
    )
