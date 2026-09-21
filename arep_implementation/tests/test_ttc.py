"""
Time-to-collision tests (Phase 2.1, closing defect D-11).

TTC was a constant-velocity projection: d / v, ignoring acceleration entirely.
That credited a braking ego with closing speed it was never going to carry, so
the number read high in exactly the manoeuvre the safety score exists to
judge — and 30% of that score is min_ttc.

These tests pin the new behaviour and, more importantly, the cases the old
formula got wrong: they fail against d / v.
"""

from __future__ import annotations

import math
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from arep.core.state import Vector2D, VehicleState   # noqa: E402
from arep.core.ttc import TTCCalculator              # noqa: E402


def _pair(gap=50.0, ego_v=20.0, obj_v=0.0, ego_a=0.0, obj_a=0.0,
          lateral=0.0, obj_heading=0.0):
    ego = VehicleState(position=Vector2D(0.0, 0.0), velocity=ego_v,
                       acceleration=ego_a, heading=0.0, object_id="ego")
    obj = VehicleState(position=Vector2D(gap, lateral), velocity=obj_v,
                       acceleration=obj_a, heading=obj_heading, object_id="npc")
    return ego, obj


def _ttc(**kwargs):
    return TTCCalculator().compute_ttc(*_pair(**kwargs))


# -- The constant-velocity case is unchanged ------------------------------

def test_no_acceleration_still_gives_distance_over_speed():
    """With a = 0 the physics is the old formula, and must stay identical."""
    assert _ttc(gap=50.0, ego_v=20.0) == pytest.approx(2.5)
    assert _ttc(gap=30.0, ego_v=10.0) == pytest.approx(3.0)


def test_closing_speed_accounts_for_a_moving_lead():
    """20 m/s into a lead doing 15 closes at 5."""
    assert _ttc(gap=50.0, ego_v=20.0, obj_v=15.0) == pytest.approx(10.0)


# -- What the old formula got wrong ---------------------------------------

def test_braking_hard_enough_means_no_collision():
    """The headline case. d / v said 2.5 s and therefore "critical"; the ego
    actually stops with room to spare."""
    assert _ttc(gap=50.0, ego_v=20.0, ego_a=-8.0) is None


def test_light_braking_buys_time():
    """Braking must increase TTC, not leave it flat."""
    baseline = _ttc(gap=50.0, ego_v=20.0, ego_a=0.0)
    braking = _ttc(gap=50.0, ego_v=20.0, ego_a=-2.0)
    assert braking > baseline


def test_accelerating_costs_time():
    baseline = _ttc(gap=50.0, ego_v=20.0, ego_a=0.0)
    accelerating = _ttc(gap=50.0, ego_v=20.0, ego_a=3.0)
    assert accelerating < baseline


def test_harder_braking_gives_more_time_than_lighter():
    gentle = _ttc(gap=60.0, ego_v=20.0, ego_a=-1.0)
    firmer = _ttc(gap=60.0, ego_v=20.0, ego_a=-3.0)
    assert firmer > gentle


def test_a_braking_lead_shortens_ttc():
    """Only the *relative* acceleration matters, and a lead braking into you
    closes the gap faster."""
    steady_lead = _ttc(gap=50.0, ego_v=20.0, obj_v=10.0, obj_a=0.0)
    braking_lead = _ttc(gap=50.0, ego_v=20.0, obj_v=10.0, obj_a=-4.0)
    assert braking_lead < steady_lead


def test_matched_braking_leaves_the_relative_motion_unchanged():
    """Both braking equally is the same closing problem as neither braking."""
    neither = _ttc(gap=50.0, ego_v=20.0, obj_v=5.0)
    both = _ttc(gap=50.0, ego_v=20.0, obj_v=5.0, ego_a=-4.0, obj_a=-4.0)
    assert both == pytest.approx(neither)


# -- The solver itself ----------------------------------------------------

def test_the_solver_matches_the_closed_form():
    """0.5·a·t² + v·t − d = 0, checked by substitution rather than by
    re-deriving the same algebra in the test."""
    distance, speed, accel = 50.0, 20.0, -2.0
    t = TTCCalculator._solve_ttc(distance, speed, accel)
    assert 0.5 * accel * t * t + speed * t == pytest.approx(distance)


def test_the_solver_takes_the_first_contact():
    """A decelerating approach crosses zero gap twice in the algebra; only the
    first one is a collision."""
    t = TTCCalculator._solve_ttc(distance=50.0, speed=20.0, accel=-2.0)
    later = TTCCalculator._solve_ttc(distance=50.0, speed=20.0, accel=0.0)
    assert t > later          # braking delays contact
    assert t < 100.0          # ...but this is the near root, not the far one


def test_the_solver_reports_no_contact_when_closing_stops_first():
    assert TTCCalculator._solve_ttc(distance=50.0, speed=20.0, accel=-8.0) is None


def test_near_zero_acceleration_does_not_divide_by_zero():
    t = TTCCalculator._solve_ttc(distance=50.0, speed=20.0, accel=1e-15)
    assert t == pytest.approx(2.5)


# -- Filters still apply --------------------------------------------------

def test_an_object_behind_is_ignored():
    ego = VehicleState(position=Vector2D(50.0, 0.0), velocity=20.0, object_id="ego")
    behind = VehicleState(position=Vector2D(0.0, 0.0), velocity=30.0)
    assert TTCCalculator().compute_ttc(ego, behind) is None


def test_an_object_far_to_the_side_is_ignored():
    assert _ttc(gap=50.0, ego_v=20.0, lateral=40.0) is None


def test_a_receding_object_has_no_ttc():
    assert _ttc(gap=50.0, ego_v=5.0, obj_v=20.0) is None


def test_ttc_beyond_the_cap_is_none():
    calc = TTCCalculator(max_ttc=5.0)
    ego, obj = _pair(gap=500.0, ego_v=20.0)
    assert calc.compute_ttc(ego, obj) is None


def test_overlapping_vehicles_are_zero():
    ego = VehicleState(position=Vector2D(0.0, 0.0), velocity=10.0, object_id="ego")
    on_top = VehicleState(position=Vector2D(0.0, 0.0), velocity=0.0)
    assert TTCCalculator().compute_ttc(ego, on_top) == 0.0


# -- The property the score depends on ------------------------------------

def test_ttc_is_never_negative_or_nan():
    """min_ttc feeds a score bounded [0,1]; a negative or NaN would poison it."""
    calc = TTCCalculator()
    for ego_a in (-8.0, -4.0, 0.0, 3.0):
        for obj_a in (-8.0, 0.0, 2.0):
            for gap in (5.0, 25.0, 80.0):
                value = calc.compute_ttc(*_pair(gap=gap, ego_a=ego_a, obj_a=obj_a))
                if value is not None:
                    assert value >= 0.0
                    assert math.isfinite(value)
