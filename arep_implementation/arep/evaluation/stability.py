"""
ORION Stability Metrics.

Measures smoothness and comfort of driving:
  - Acceleration smoothness (std dev of acceleration)
  - Jerk (derivative of acceleration)
  - Steering smoothness (std dev of steering changes)
  - Combined stability score [0, 1]

Lower jerk and smoother controls → higher score.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from arep.evaluation.collector import SimulationRecord


@dataclass
class StabilityResult:
    """Stability metric results."""
    acceleration_std: float       # m/s² standard deviation
    mean_jerk: float              # m/s³
    max_jerk: float               # m/s³
    steering_std: float           # steering change std dev
    stability_score: float        # composite [0, 1]


class StabilityMetrics:
    """
    Compute stability (smoothness) metrics.

    Scoring approach:
      - Acceleration smoothness: 40%
      - Jerk smoothness: 40%
      - Steering smoothness: 20%
    """

    ACCEL_WEIGHT = 0.40
    JERK_WEIGHT = 0.40
    STEERING_WEIGHT = 0.20

    # Normalization thresholds
    ACCEL_STD_THRESHOLD = 3.0  # m/s² (above this → score = 0)
    JERK_THRESHOLD = 10.0      # m/s³
    STEERING_STD_THRESHOLD = 0.5

    def compute(self, record: SimulationRecord) -> StabilityResult:
        """
        Compute stability metrics.

        Args:
            record: Completed simulation record.

        Returns:
            StabilityResult.
        """
        snapshots = record.ego_snapshots
        actions = record.actions

        if len(snapshots) < 2:
            return StabilityResult(
                acceleration_std=0.0,
                mean_jerk=0.0, max_jerk=0.0,
                steering_std=0.0,
                stability_score=1.0,
            )

        # ── Acceleration smoothness ──────────────────────────────────
        accels = np.array([s.acceleration for s in snapshots])
        accel_std = float(np.std(accels))
        accel_score = max(0.0, 1.0 - accel_std / self.ACCEL_STD_THRESHOLD)

        # ── Jerk ─────────────────────────────────────────────────────
        # Jerk = da/dt  (finite difference)
        dt = snapshots[1].sim_time - snapshots[0].sim_time
        if abs(dt) > 1e-9:
            jerks = np.diff(accels) / dt
        else:
            jerks = np.zeros(len(accels) - 1)

        mean_jerk = float(np.mean(np.abs(jerks))) if len(jerks) else 0.0
        max_jerk = float(np.max(np.abs(jerks))) if len(jerks) else 0.0
        jerk_score = max(0.0, 1.0 - mean_jerk / self.JERK_THRESHOLD)

        # ── Steering smoothness ──────────────────────────────────────
        if len(actions) >= 2:
            steerings = np.array([a.steering for a in actions])
            steering_changes = np.diff(steerings)
            steering_std = float(np.std(steering_changes))
        else:
            steering_std = 0.0
        steering_score = max(
            0.0, 1.0 - steering_std / self.STEERING_STD_THRESHOLD
        )

        # ── Composite ────────────────────────────────────────────────
        stability_score = (
            self.ACCEL_WEIGHT * accel_score
            + self.JERK_WEIGHT * jerk_score
            + self.STEERING_WEIGHT * steering_score
        )

        return StabilityResult(
            acceleration_std=accel_std,
            mean_jerk=mean_jerk,
            max_jerk=max_jerk,
            steering_std=steering_std,
            stability_score=stability_score,
        )
