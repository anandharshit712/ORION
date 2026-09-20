"""
NPC behaviour tree tests (Phase 0.6, defect D-09).

npc_bt.py drives every reactive object in the scenario library — the cut-in, the
hesitant brake, the pedestrian who steps out — and had no tests at all. These
trees are what makes a scenario a *test* rather than a replay: if a lead vehicle
brakes differently than the scenario claims, every score computed against it is
measuring something other than what the report says.

They must also be deterministic. Each tree samples from a seeded generator, so
the same seed has to produce the same manoeuvre or the determinism guarantee
stops at the first NPC.
"""

from __future__ import annotations

import math
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from arep.core.random_manager import RandomManager          # noqa: E402
from arep.core.state import Vector2D, VehicleState, WorldState  # noqa: E402
from arep.simulation import npc_bt                          # noqa: E402

DT = 0.02


def _vehicle(x=0.0, y=0.0, velocity=10.0, heading=0.0, object_id="npc"):
    return VehicleState(
        position=Vector2D(x, y), velocity=velocity, heading=heading,
        object_id=object_id,
    )


def _world(sim_time=0.0, ego=None, npc=None):
    return WorldState(
        sim_time=sim_time,
        timestep_count=int(sim_time / DT),
        ego_vehicle=ego or _vehicle(x=0.0, velocity=20.0, object_id="ego"),
        dynamic_objects=[npc] if npc is not None else [],
    )


def _behavior(**params):
    return {
        "type": "reactive_vehicle",
        "parameters": params,
        "_triggered": False,
        "_trigger_time": None,
    }


# -- Helpers --------------------------------------------------------------

def test_sample_returns_a_scalar_unchanged():
    gen = RandomManager(1).get("traffic")
    assert npc_bt._sample(-4.0, gen) == -4.0


def test_sample_draws_inside_a_range():
    gen = RandomManager(1).get("traffic")
    for _ in range(50):
        value = npc_bt._sample({"min": -6.0, "max": -3.0}, gen)
        assert -6.0 <= value <= -3.0


def test_sample_is_seed_determined():
    """A tree that samples differently per run breaks the whole guarantee."""
    spec = {"min": 0.0, "max": 100.0}
    a = [npc_bt._sample(spec, RandomManager(7).get("traffic")) for _ in range(3)]
    b = [npc_bt._sample(spec, RandomManager(7).get("traffic")) for _ in range(3)]
    assert a == b


def test_apply_accel_clamps_to_the_velocity_floor():
    obj = _vehicle(velocity=1.0)
    braked = npc_bt._apply_accel(obj, -9.0, min_v=0.0, max_v=50.0, dt=DT)
    assert braked.velocity >= 0.0


def test_apply_accel_clamps_to_the_ceiling():
    obj = _vehicle(velocity=49.9)
    sped = npc_bt._apply_accel(obj, 100.0, min_v=0.0, max_v=50.0, dt=DT)
    assert sped.velocity == 50.0


def test_apply_accel_does_not_mutate_its_input():
    """WorldState immutability is a hard rule; the trees are no exception."""
    obj = _vehicle(velocity=10.0)
    npc_bt._apply_accel(obj, -5.0, 0.0, 50.0, DT)
    assert obj.velocity == 10.0
    assert obj.position.x == 0.0


def test_const_vel_advances_along_heading():
    obj = _vehicle(x=0.0, velocity=10.0, heading=0.0)
    moved = npc_bt._const_vel(obj, dt=1.0)
    assert moved.position.x == pytest.approx(10.0)
    assert moved.position.y == pytest.approx(0.0)


def test_const_vel_respects_a_diagonal_heading():
    obj = _vehicle(velocity=10.0, heading=math.pi / 2)
    moved = npc_bt._const_vel(obj, dt=1.0)
    assert moved.position.x == pytest.approx(0.0, abs=1e-9)
    assert moved.position.y == pytest.approx(10.0)


def test_move_along_heading_reverses_on_negative_speed():
    obj = _vehicle(x=10.0, heading=0.0)
    backed = npc_bt._move_along_heading(obj, speed=-5.0, dt=1.0)
    assert backed.position.x == pytest.approx(5.0)
    assert backed.velocity == 5.0, "velocity is a magnitude"


# -- Triggers -------------------------------------------------------------

def test_time_trigger_fires_at_its_threshold():
    behavior = _behavior(trigger_type="time", trigger_value=2.0)
    npc = _vehicle()

    assert not npc_bt._check_trigger(behavior, npc, _world(sim_time=1.99, npc=npc))
    assert npc_bt._check_trigger(behavior, npc, _world(sim_time=2.0, npc=npc))


def test_a_fired_trigger_stays_fired():
    """Otherwise a manoeuvre restarts every time the condition lapses."""
    behavior = _behavior(trigger_type="time", trigger_value=1.0)
    npc = _vehicle()

    npc_bt._check_trigger(behavior, npc, _world(sim_time=1.0, npc=npc))
    assert behavior["_triggered"]
    assert npc_bt._check_trigger(behavior, npc, _world(sim_time=0.0, npc=npc))


def test_trigger_records_when_it_fired():
    behavior = _behavior(trigger_type="time", trigger_value=1.5)
    npc = _vehicle()
    npc_bt._check_trigger(behavior, npc, _world(sim_time=1.5, npc=npc))
    assert behavior["_trigger_time"] == 1.5


def test_proximity_trigger_fires_on_distance():
    behavior = _behavior(trigger_type="proximity", trigger_value=10.0)
    npc = _vehicle(x=30.0)
    ego = _vehicle(x=0.0, object_id="ego")

    assert not npc_bt._check_trigger(behavior, npc, _world(ego=ego, npc=npc))

    close = _vehicle(x=8.0)
    assert npc_bt._check_trigger(behavior, close, _world(ego=ego, npc=close))


def test_ttc_trigger_fires_when_closing_fast_enough():
    behavior = _behavior(trigger_type="ttc", trigger_value=2.0)
    npc = _vehicle(x=20.0, velocity=0.0)
    ego = _vehicle(x=0.0, velocity=20.0, object_id="ego")
    assert npc_bt._check_trigger(behavior, npc, _world(ego=ego, npc=npc))


def test_an_unresolved_range_never_fires():
    """The parameterizer should have resolved it; firing on a dict would be
    an arbitrary manoeuvre at an arbitrary time."""
    behavior = _behavior(trigger_type="time", trigger_value={"min": 1.0, "max": 2.0})
    npc = _vehicle()
    assert not npc_bt._check_trigger(behavior, npc, _world(sim_time=99.0, npc=npc))


# -- TTC helper -----------------------------------------------------------

def test_ttc_is_zero_when_already_overlapping():
    npc = _vehicle(x=1.0)
    ego = _vehicle(x=0.0, object_id="ego")
    assert npc_bt._compute_ttc(npc, ego) == 0.0


def test_ttc_is_none_when_not_closing():
    """Two vehicles at the same speed never meet; a number would be a lie."""
    npc = _vehicle(x=50.0, velocity=20.0)
    ego = _vehicle(x=0.0, velocity=20.0, object_id="ego")
    assert npc_bt._compute_ttc(npc, ego) is None


def test_ttc_shrinks_as_the_gap_closes():
    ego = _vehicle(x=0.0, velocity=20.0, object_id="ego")
    far = npc_bt._compute_ttc(_vehicle(x=100.0, velocity=0.0), ego)
    near = npc_bt._compute_ttc(_vehicle(x=40.0, velocity=0.0), ego)
    assert far > near > 0


# -- The registry ---------------------------------------------------------

def test_every_registered_tree_is_reachable():
    for name in npc_bt._BT_REGISTRY:
        assert npc_bt.get_bt(name) is not None


def test_an_unknown_tree_fails_loudly():
    with pytest.raises(ValueError, match="Unknown BT type"):
        npc_bt.get_bt("not_a_real_behaviour")


# adaptive_tailgate has no trigger by design: it is a continuous follower that
# closes on the ego from the first tick. Gating it would turn a tailgater into a
# car that ignores you until a stopwatch says otherwise.
TRIGGERED_TREES = sorted(set(npc_bt._BT_REGISTRY) - {"adaptive_tailgate"})


@pytest.mark.parametrize("bt_type", TRIGGERED_TREES)
def test_every_tree_ticks_without_moving_before_its_trigger(bt_type):
    """An NPC that acts before its trigger changes what the scenario tests."""
    tree = npc_bt.get_bt(bt_type)
    behavior = _behavior(trigger_type="time", trigger_value=99.0)
    npc = _vehicle(x=50.0, velocity=10.0)
    rng = RandomManager(42)

    result = tree.tick(npc, behavior, _world(sim_time=0.0, npc=npc), rng, DT)

    assert result is not None
    assert result.velocity == pytest.approx(10.0), "speed changed before trigger"


@pytest.mark.parametrize("bt_type", sorted(npc_bt._BT_REGISTRY))
def test_every_tree_is_deterministic_for_one_seed(bt_type):
    """Same seed, same manoeuvre — or the run hash means nothing."""
    def drive() -> list[tuple[float, float]]:
        tree = npc_bt.get_bt(bt_type)
        behavior = _behavior(trigger_type="time", trigger_value=0.1)
        npc = _vehicle(x=50.0, velocity=10.0)
        rng = RandomManager(1234)
        trace = []
        for step in range(80):
            world = _world(sim_time=step * DT, npc=npc)
            npc = tree.tick(npc, behavior, world, rng, DT)
            trace.append((round(npc.position.x, 6), round(npc.velocity, 6)))
        return trace

    assert drive() == drive()


@pytest.mark.parametrize("bt_type", sorted(npc_bt._BT_REGISTRY))
def test_every_tree_keeps_speed_physically_plausible(bt_type):
    tree = npc_bt.get_bt(bt_type)
    behavior = _behavior(trigger_type="time", trigger_value=0.1)
    npc = _vehicle(x=50.0, velocity=10.0)
    rng = RandomManager(7)

    for step in range(200):
        npc = tree.tick(npc, behavior, _world(sim_time=step * DT, npc=npc), rng, DT)
        assert npc.velocity >= 0.0, f"{bt_type} produced a negative speed"
        assert npc.velocity < 100.0, f"{bt_type} produced {npc.velocity} m/s"
        assert math.isfinite(npc.position.x) and math.isfinite(npc.position.y)


# -- Individual manoeuvres ------------------------------------------------

def test_hesitant_brake_actually_slows_down():
    tree = npc_bt.get_bt("hesitant_brake")
    behavior = _behavior(
        trigger_type="time", trigger_value=0.0,
        initial_decel=-4.0, initial_brake_duration=0.5,
        hesitation_prob=0.0, final_decel=-8.0,
    )
    npc = _vehicle(x=50.0, velocity=20.0)
    rng = RandomManager(3)

    for step in range(150):
        npc = tree.tick(npc, behavior, _world(sim_time=step * DT, npc=npc), rng, DT)

    assert npc.velocity < 20.0, "a braking NPC that never slows is not braking"


def test_hesitant_brake_reaches_a_stop_eventually():
    tree = npc_bt.get_bt("hesitant_brake")
    behavior = _behavior(
        trigger_type="time", trigger_value=0.0,
        initial_decel=-6.0, initial_brake_duration=0.2,
        hesitation_prob=0.0, final_decel=-9.0, min_velocity=0.0,
    )
    npc = _vehicle(x=50.0, velocity=15.0)
    rng = RandomManager(5)

    for step in range(400):
        npc = tree.tick(npc, behavior, _world(sim_time=step * DT, npc=npc), rng, DT)

    assert npc.velocity == pytest.approx(0.0, abs=0.1)


def test_the_tailgater_closes_the_gap_without_waiting_for_a_trigger():
    """Its defining behaviour, and the reason it is exempt above."""
    tree = npc_bt.get_bt("adaptive_tailgate")
    behavior = _behavior(target_ttc=0.6)
    ego = _vehicle(x=0.0, velocity=20.0, object_id="ego")
    npc = _vehicle(x=-60.0, velocity=20.0)
    rng = RandomManager(21)

    start_gap = ego.position.x - npc.position.x
    for step in range(200):
        npc = tree.tick(npc, behavior, _world(sim_time=step * DT, ego=ego, npc=npc),
                        rng, DT)

    assert ego.position.x - npc.position.x < start_gap, "the tailgater fell behind"


def test_hesitation_probability_of_one_takes_the_hesitation_branch():
    """The branch that makes this scenario interesting — release, then brake."""
    tree = npc_bt.get_bt("hesitant_brake")
    behavior = _behavior(
        trigger_type="time", trigger_value=0.0,
        initial_decel=-4.0, initial_brake_duration=0.1,
        hesitation_prob=1.0, hesitation_duration=0.3, hesitation_accel=0.5,
        final_decel=-8.0,
    )
    npc = _vehicle(x=50.0, velocity=20.0)
    rng = RandomManager(11)

    states = set()
    for step in range(60):
        npc = tree.tick(npc, behavior, _world(sim_time=step * DT, npc=npc), rng, DT)
        states.add(behavior.get("_bt_state"))

    assert "hesitation" in states, f"never hesitated; saw {states}"
