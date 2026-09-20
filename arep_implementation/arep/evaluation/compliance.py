"""
ORION Compliance Metrics.

Measures how well the model follows traffic rules:
  - Speed limit compliance (fraction of time within limit)
  - Speed violation severity (mean excess above limit)
  - Lane keeping (fraction of time within lane boundaries)
  - Combined compliance score [0, 1]
"""

from __future__ import annotations

from dataclasses import dataclass

from arep.evaluation.collector import SimulationRecord


@dataclass
class ComplianceResult:
    """Compliance metric results."""
    speed_compliance_fraction: float   # [0, 1], 1 = always ≤ limit
    mean_speed_excess: float           # m/s above limit (avg over violations)
    max_speed_excess: float            # m/s above limit (worst)
    lane_compliance_fraction: float    # [0, 1], 1 = always in-lane
    compliance_score: float            # composite [0, 1]
    # Phase 0.5 / D-05. Signed, in metres, from the lane centerline: negative is
    # left of travel. The mean shows a persistent bias, the max shows the worst
    # excursion — a model that weaves and one that hugs a line have similar
    # in-lane fractions but very different means.
    mean_lane_offset: float = 0.0
    max_abs_lane_offset: float = 0.0


class ComplianceMetrics:
    """
    Compute compliance metrics from simulation records.

    Weights:
      - Speed compliance: 60%
      - Lane keeping: 40%
    """

    SPEED_WEIGHT = 0.60
    LANE_WEIGHT = 0.40

    SPEED_TOLERANCE = 1.0  # m/s over limit before counting as violation

    def compute(self, record: SimulationRecord) -> ComplianceResult:
        """
        Compute compliance metrics.

        Args:
            record: Completed simulation record.

        Returns:
            ComplianceResult.
        """
        speed_limit = record.speed_limit
        snapshots = record.ego_snapshots

        if not snapshots or speed_limit <= 0:
            return ComplianceResult(
                speed_compliance_fraction=1.0,
                mean_speed_excess=0.0,
                max_speed_excess=0.0,
                lane_compliance_fraction=1.0,
                compliance_score=1.0,
            )

        # ── Speed compliance ─────────────────────────────────────────
        speed_compliant = 0
        speed_excesses = []
        max_speed_excess = 0.0

        for snap in snapshots:
            excess = snap.velocity - (speed_limit + self.SPEED_TOLERANCE)
            if excess <= 0:
                speed_compliant += 1
            else:
                speed_excesses.append(excess)
                max_speed_excess = max(max_speed_excess, excess)

        total = len(snapshots)
        speed_frac = speed_compliant / total
        mean_excess = (
            sum(speed_excesses) / len(speed_excesses)
            if speed_excesses else 0.0
        )

        # Speed score: compliance fraction, penalized more at high excess
        speed_score = speed_frac

        # ── Lane compliance (D-05) ───────────────────────────────────
        # Was hardcoded to 1.0, which made the lane half of this score
        # decorative: a model could weave across the centerline for the whole
        # run and still score full marks. EgoSnapshot now carries the signed
        # offset recorded against the live lane geometry.
        lane_frac, mean_offset, max_abs_offset = self._lane_compliance(snapshots)

        if record.termination_reason == "off_road":
            # Leaving the road is worse than any in-lane drift, and the run
            # stops there — so the remaining (unrecorded) time is counted
            # against it rather than simply ignored.
            off_road_frac = record.duration / max(record.duration + 10.0, 1.0)
            lane_frac = min(lane_frac, off_road_frac)

        # ── Composite ────────────────────────────────────────────────
        compliance_score = (
            self.SPEED_WEIGHT * speed_score
            + self.LANE_WEIGHT * lane_frac
        )

        return ComplianceResult(
            speed_compliance_fraction=speed_frac,
            mean_speed_excess=mean_excess,
            max_speed_excess=max_speed_excess,
            lane_compliance_fraction=lane_frac,
            compliance_score=compliance_score,
            mean_lane_offset=mean_offset,
            max_abs_lane_offset=max_abs_offset,
        )

    def _lane_compliance(self, snapshots) -> tuple[float, float, float]:
        """In-lane fraction plus mean and worst offset (D-05).

        A step counts as in-lane when the whole vehicle body is inside the lane:
        ``|offset| + vehicle_width / 2 <= lane_width / 2``. Testing the body edge
        rather than the centre point matters more than it looks. ``lane_offset``
        is measured against the *nearest* lane, so on a road of equal-width
        adjacent lanes the centre point is within half a lane width by
        construction — a centre-point test can essentially never fail, which
        would have left this metric as decorative as the stub it replaces. The
        body-edge test is also the everyday meaning of lane keeping: a car
        straddling the line is not in its lane, whatever its centre is doing.

        Steps with no lane under the vehicle are excluded rather than counted as
        compliant — the old stub's mistake was treating absent data as a pass.
        With no lane data at all the fraction is 1.0, because a scenario without
        lane geometry cannot fail a lane-keeping check.
        """
        measured = [s for s in snapshots if s.lane_valid and s.lane_width > 0.0]
        if not measured:
            return 1.0, 0.0, 0.0

        in_lane = sum(
            1 for s in measured
            if abs(s.lane_offset) + s.vehicle_half_width <= s.lane_width / 2.0
        )
        offsets = [s.lane_offset for s in measured]
        return (
            in_lane / len(measured),
            sum(offsets) / len(offsets),
            max(abs(o) for o in offsets),
        )
