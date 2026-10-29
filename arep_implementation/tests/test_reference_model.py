"""The reference driver (Phase 4.3 follow-up).

This model exists to make a claim testable. When `EmergencyBrake` fails a
scenario, nothing distinguishes "the scenario correctly demands a behaviour this
model lacks" from "the scenario is impossible" — every other model in the repo
is degenerate, so every failure has the same shape. A model that can actually
pass is what turns that argument into a measurement.

So what matters here is not that it drives well. It is that it is **competent
enough to be a meaningful upper bound** and **deterministic enough to be one
twice**. A reference that drifts between runs, or that is secretly just
`EmergencyBrake` with extra steps, is worse than none: it would licence exactly
the conclusion nobody has earned.
"""

from __future__ import annotations

import pytest

from arep.core.action import Action
from arep.core.observation import ObjectObservation, Observation
from arep.execution.runner import EvaluationRunner
from arep.models.examples.example_models import (
    EmergencyBrakeModel,
    ReferenceDriverModel,
)

LON_FOLLOW = "../scenarios/lon/LON-001_gradual_slowdown.yaml"
LON_STOP = "../scenarios/lon/LON-003_emergency_stop.yaml"


def _obs(**kw) -> Observation:
    base = dict(ego_velocity=20.0, speed_limit=27.78, lane_offset=0.0)
    base.update(kw)
    return Observation(**base)


def _lead(distance: float, speed: float, lateral: float = 0.0) -> ObjectObservation:
    return ObjectObservation(
        object_id="lead",
        relative_x=distance,
        relative_y=lateral,
        relative_vx=speed - 20.0,
        relative_vy=0.0,
        speed=speed,
        length=4.5,
        width=2.0,
    )


# ── It is not EmergencyBrake in disguise ──────────────────────────────


def test_open_road_accelerates_rather_than_brakes():
    """The whole point: it is not degenerate.

    `EmergencyBrake` would return brake=1.0 here. A reference that also brakes
    on an empty road proves nothing about any scenario.
    """
    action = ReferenceDriverModel().predict(_obs(ego_velocity=12.0))
    assert action.throttle > 0.0
    assert action.brake == 0.0


def test_at_the_speed_limit_it_stops_accelerating():
    action = ReferenceDriverModel().predict(_obs(ego_velocity=27.78, speed_limit=27.78))
    assert action.throttle == pytest.approx(0.0, abs=1e-6)


def test_a_distant_slower_lead_produces_easing_not_emergency():
    """Graded response. A model with one reaction is not a driver."""
    action = ReferenceDriverModel().predict(_obs(objects=[_lead(70.0, 16.0)]))
    assert action.brake < 1.0, "a lead 70 m away is not an emergency"


def test_a_close_lead_produces_full_braking():
    action = ReferenceDriverModel().predict(_obs(objects=[_lead(8.0, 0.0)]))
    assert action.brake == 1.0


# ── Perception behaviours the scenarios rely on ───────────────────────


def test_an_object_in_the_next_lane_is_ignored_while_it_stays_there():
    steady = ObjectObservation(
        object_id="neighbour",
        relative_x=15.0,
        relative_y=3.5,
        relative_vx=0.0,
        relative_vy=0.0,
        speed=20.0,
        length=4.5,
        width=2.0,
    )
    action = ReferenceDriverModel().predict(_obs(objects=[steady]))
    assert action.brake == 0.0


def test_an_object_moving_into_the_lane_is_not_ignored():
    """The cut-in case. Waiting for it to arrive spends the room it needs."""
    cutting = ObjectObservation(
        object_id="cutter",
        relative_x=15.0,
        relative_y=3.0,
        relative_vx=-4.0,
        relative_vy=-1.5,  # closing on the lane centre
        speed=16.0,
        length=4.5,
        width=2.0,
    )
    action = ReferenceDriverModel().predict(_obs(objects=[cutting]))
    assert action.brake > 0.0 or action.throttle == 0.0


def test_the_gap_is_bumper_to_bumper_not_centre_to_centre():
    """Centre distance invents most of a car length of margin at speed."""
    model = ReferenceDriverModel()
    near = model._gap(_lead(10.0, 0.0))
    assert near < 10.0 - 2.0, "vehicle bodies were not subtracted"


# ── Determinism ───────────────────────────────────────────────────────


def test_identical_observations_give_identical_actions():
    a, b = ReferenceDriverModel(), ReferenceDriverModel()
    for _ in range(25):
        obs = _obs(objects=[_lead(30.0, 15.0)])
        act_a, act_b = a.predict(obs), b.predict(obs)
        assert (act_a.steering, act_a.throttle, act_a.brake) == (
            act_b.steering,
            act_b.throttle,
            act_b.brake,
        )


def test_reset_clears_the_steering_state():
    model = ReferenceDriverModel()
    model.predict(_obs(lane_offset=2.0, objects=[_lead(6.0, 0.0)]))
    assert model._prev_steering != 0.0
    model.reset()
    assert model._prev_steering == 0.0


def test_a_full_run_is_reproducible():
    runner = EvaluationRunner()
    first = runner.run_single(LON_STOP, ReferenceDriverModel(), master_seed=7)
    second = runner.run_single(LON_STOP, ReferenceDriverModel(), master_seed=7)
    assert first.frame_hash == second.frame_hash
    assert first.composite_score == pytest.approx(second.composite_score)


# ── Competence, measured against the model it replaces ────────────────


def test_it_clears_a_following_scenario_without_colliding():
    result = EvaluationRunner().run_batch(
        scenario_path=LON_FOLLOW,
        model=ReferenceDriverModel(),
        num_runs=10,
        master_seed=42,
    )
    assert result.aggregated.collision_rate == 0.0


def test_it_scores_as_a_competent_driver_not_merely_a_surviving_one():
    """Competence floor for the upper bound.

    This deliberately does NOT assert that the reference beats
    `EmergencyBrake`. It does not, and the reason is a property of the scoring
    rather than of the model: on LON-001 the braking model scores 0.962
    stability and 0.988 composite by stopping dead in the first second and
    sitting still for the remaining thirty. Nothing in safety, compliance,
    stability or reactivity rewards making progress, so a car that refuses to
    move is close to unbeatable wherever it does not get hit.

    That is a real gap in the composite and is written up in `docs/PENDING.md`;
    it is not something this test should paper over by asserting a comparison
    that is false. What is assertable is that the reference clears the scenario
    on its own terms.
    """
    aggregated = (
        EvaluationRunner()
        .run_batch(
            scenario_path=LON_FOLLOW,
            model=ReferenceDriverModel(),
            num_runs=10,
            master_seed=42,
        )
        .aggregated
    )
    assert aggregated.collision_rate == 0.0
    assert aggregated.composite_mean > 0.80, aggregated.composite_mean
    assert aggregated.safety_mean > 0.85, aggregated.safety_mean


def test_a_model_that_never_moves_still_scores_well():
    """Pins the gap above so it cannot regress unnoticed.

    If a progress or efficiency term is ever added to the composite, this test
    fails and the PENDING entry comes off the list. Until then it records, in
    executable form, that ORION's score does not distinguish driving from
    refusing to.
    """
    aggregated = (
        EvaluationRunner()
        .run_batch(
            scenario_path=LON_FOLLOW,
            model=EmergencyBrakeModel(),
            num_runs=10,
            master_seed=42,
        )
        .aggregated
    )
    assert aggregated.composite_mean > 0.95, (
        "a model that brakes to a standstill and never moves again no longer "
        "scores near-perfect — if that is intentional, delete this test and the "
        "corresponding docs/PENDING.md entry"
    )


def test_it_is_registered_where_the_suite_and_the_api_look():
    from arep.api.routes import AVAILABLE_MODELS
    from arep.cli.run_suite import BUILTIN_MODELS

    assert "ReferenceDriver" in AVAILABLE_MODELS
    assert isinstance(AVAILABLE_MODELS["ReferenceDriver"](), ReferenceDriverModel)
    assert BUILTIN_MODELS["reference"].endswith("ReferenceDriverModel")


def test_actions_are_always_in_range():
    """An out-of-range Action is rejected by the engine and voids the run."""
    model = ReferenceDriverModel()
    for distance in (2.0, 5.0, 15.0, 60.0, 200.0):
        for offset in (-3.0, 0.0, 3.0):
            action = model.predict(
                _obs(lane_offset=offset, objects=[_lead(distance, 0.0)])
            )
            assert -1.0 <= action.steering <= 1.0
            assert 0.0 <= action.throttle <= 1.0
            assert 0.0 <= action.brake <= 1.0
            assert isinstance(action, Action)
