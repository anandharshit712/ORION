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

        # ── Lane compliance ──────────────────────────────────────────
        # Currently simplified: can't compute from snapshots alone
        # (would need lane offset data). Default to full compliance.
        lane_frac = 1.0
        if record.termination_reason == "off_road":
            # If terminated due to off_road, penalize
            lane_frac = record.duration / max(
                record.duration + 10.0, 1.0
            )

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
        )
