"""
Lane compliance tests (Phase 0.5, defect D-05).

Covers the roadmap acceptance criterion "a lane-keeping scenario where the ego
drifts out of lane scores < 1.0 on compliance".

The stub this replaces returned lane_frac = 1.0 unconditionally, so the lane
half of the compliance score was decorative. The tests here are written to fail
against that stub *and* against the first real implementation, which tested the
vehicle centre against the nearest lane centreline — a condition that is true by
construction on a road of equal-width adjacent lanes.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from arep.core.state import LaneInfo, Vector2D  # noqa: E402
from arep.evaluation.collector import EgoSnapshot, SimulationRecord  # noqa: E402
from arep.evaluation.compliance import ComplianceMetrics  # noqa: E402

LANE_WIDTH = 3.5
HALF_VEHICLE = 1.0  # VehicleState.width defaults to 2.0 m


def _snapshot(offset: float, *, lane_valid: bool = True, velocity: float = 10.0):
    return EgoSnapshot(
        sim_time=0.0,
        x=0.0,
        y=offset,
        heading=0.0,
        velocity=velocity,
        acceleration=0.0,
        lane_offset=offset,
        lane_width=LANE_WIDTH,
        vehicle_half_width=HALF_VEHICLE,
        lane_valid=lane_valid,
    )


def _record(snapshots, *, termination="timeout", speed_limit=30.0, duration=10.0):
    return SimulationRecord(
        ego_snapshots=snapshots,
        duration=duration,
        num_timesteps=len(snapshots),
        termination_reason=termination,
        speed_limit=speed_limit,
    )


# -- Signed offset geometry -----------------------------------------------


def test_signed_offset_is_negative_to_the_left_of_travel():
    """The sign is the point: unsigned drift hides which way a model pulls."""
    lane = LaneInfo(
        "l0", [Vector2D(0, 0), Vector2D(100, 0)], width=LANE_WIDTH, speed_limit=30.0
    )
    assert lane.get_signed_lateral_offset(Vector2D(50, 1.2)) < 0  # left
    assert lane.get_signed_lateral_offset(Vector2D(50, -1.2)) > 0  # right
    assert lane.get_signed_lateral_offset(Vector2D(50, 0.0)) == 0.0


def test_signed_offset_magnitude_matches_the_unsigned_one():
    lane = LaneInfo(
        "l0", [Vector2D(0, 0), Vector2D(100, 0)], width=LANE_WIDTH, speed_limit=30.0
    )
    p = Vector2D(50, 0.8)
    assert abs(lane.get_signed_lateral_offset(p)) == lane.get_lateral_offset(p)


# -- The in-lane test -----------------------------------------------------


def test_centred_driving_scores_full_lane_compliance():
    result = ComplianceMetrics().compute(_record([_snapshot(0.0) for _ in range(50)]))
    assert result.lane_compliance_fraction == 1.0
    assert result.mean_lane_offset == 0.0
    assert result.max_abs_lane_offset == 0.0


def test_straddling_the_lane_line_is_not_compliant():
    """The case the centre-point test got wrong.

    Offset 1.6 m puts the vehicle centre inside the nearest lane's half width
    (1.75 m), so a centre-point test calls this compliant — but the body extends
    to 2.6 m, well over the line. This is exactly the geometry every scenario in
    the library used to produce, and it has to score badly.
    """
    result = ComplianceMetrics().compute(_record([_snapshot(1.6) for _ in range(50)]))
    assert result.lane_compliance_fraction == 0.0


def test_the_boundary_is_where_the_body_edge_touches_the_line():
    half_lane = LANE_WIDTH / 2.0
    just_inside = half_lane - HALF_VEHICLE - 1e-6
    just_outside = half_lane - HALF_VEHICLE + 1e-3

    assert (
        ComplianceMetrics()
        .compute(_record([_snapshot(just_inside)]))
        .lane_compliance_fraction
        == 1.0
    )
    assert (
        ComplianceMetrics()
        .compute(_record([_snapshot(just_outside)]))
        .lane_compliance_fraction
        == 0.0
    )


def test_partial_drift_gives_a_partial_fraction():
    """The acceptance criterion: drifting out of lane scores below 1.0."""
    snapshots = [_snapshot(0.0) for _ in range(30)] + [
        _snapshot(1.6) for _ in range(20)
    ]
    result = ComplianceMetrics().compute(_record(snapshots))

    assert result.lane_compliance_fraction == 0.6
    assert result.compliance_score < 1.0


def test_mean_offset_reveals_a_persistent_bias():
    """A car that sits off-centre and one that weaves score alike on the
    fraction; the mean is what separates them."""
    biased = ComplianceMetrics().compute(_record([_snapshot(0.4) for _ in range(20)]))
    weaving = ComplianceMetrics().compute(
        _record([_snapshot(0.4 if i % 2 else -0.4) for i in range(20)])
    )

    assert biased.lane_compliance_fraction == weaving.lane_compliance_fraction == 1.0
    assert biased.mean_lane_offset == 0.4
    assert abs(weaving.mean_lane_offset) < 1e-9
    assert weaving.max_abs_lane_offset == 0.4


# -- Missing data must not read as a pass ---------------------------------


def test_steps_without_lane_data_are_excluded_not_counted_compliant():
    """The stub's actual mistake: treating absent data as success."""
    snapshots = [_snapshot(0.0) for _ in range(10)] + [
        _snapshot(9.9, lane_valid=False) for _ in range(10)
    ]
    result = ComplianceMetrics().compute(_record(snapshots))
    assert result.lane_compliance_fraction == 1.0  # the 10 measured steps
    assert result.max_abs_lane_offset == 0.0  # the invalid ones ignored


def test_a_scenario_with_no_lane_geometry_cannot_fail_lane_keeping():
    snapshots = [_snapshot(5.0, lane_valid=False) for _ in range(10)]
    assert (
        ComplianceMetrics().compute(_record(snapshots)).lane_compliance_fraction == 1.0
    )


def test_off_road_termination_still_dominates():
    """Leaving the road is worse than any in-lane drift, and the run stops
    there — the unrecorded remainder counts against it."""
    snapshots = [_snapshot(0.0) for _ in range(5)]
    result = ComplianceMetrics().compute(
        _record(snapshots, termination="off_road", duration=1.0)
    )
    assert result.lane_compliance_fraction < 0.2


# -- End to end -----------------------------------------------------------


def test_a_drifting_model_scores_below_a_straight_one():
    """The metric has to discriminate on a real run, not just on fixtures."""
    from arep.execution.runner import EvaluationRunner
    from arep.models.examples.example_models import ConstantActionModel

    def compliance_of(steering):
        return (
            EvaluationRunner()
            .run_batch(
                scenario_path="scenarios/basic/straight_road_lead_vehicle.yaml",
                model=ConstantActionModel(throttle=0.3, steering=steering),
                num_runs=1,
                master_seed=42,
            )
            .per_run_results[0]
            .compliance
        )

    straight = compliance_of(0.0)
    drifting = compliance_of(0.15)

    assert straight.lane_compliance_fraction == 1.0
    assert drifting.lane_compliance_fraction < 0.5
    assert drifting.compliance_score < straight.compliance_score


def test_lane_zero_is_centred_on_the_travel_line():
    """Scenarios place ego and traffic at y=0 and mean "in my lane" by it.

    With the carriageway centred instead, y=0 was the boundary between two
    lanes and a correctly driven car straddled it for the whole run.
    """
    from arep.config import get_config
    from arep.scenario.parser import ScenarioParser
    from arep.scenario.executor import ScenarioExecutor

    scenario, _hash = ScenarioParser().parse_file(
        "scenarios/basic/straight_road_lead_vehicle.yaml"
    )
    lanes = ScenarioExecutor(get_config())._create_lanes(scenario)

    assert lanes[0].centerline_points[0].y == 0.0
    assert len(lanes) == 2
    assert lanes[1].centerline_points[0].y == LANE_WIDTH
