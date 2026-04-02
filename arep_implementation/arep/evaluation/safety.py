"""
ORION Safety Metrics.

Computes safety scores from simulation records:
  - Collision penalty (binary + speed-weighted)
  - Minimum TTC score
  - Critical TTC fraction (% of steps with TTC ≤ 2s)
  - Combined safety score [0, 1]

Scoring: 1.0 = perfectly safe, 0.0 = worst possible.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from arep.evaluation.collector import SimulationRecord


@dataclass
class SafetyResult:
    """Safety metric results."""
    collision_occurred: bool
    collision_penalty: float      # [0, 1], 0 = collision, 1 = no collision
    min_ttc: float                # seconds
    min_ttc_score: float          # [0, 1]
    critical_ttc_fraction: float  # fraction of steps with TTC ≤ 2s
    safety_score: float           # composite [0, 1]


class SafetyMetrics:
    """
    Compute safety metrics from simulation records.

    Weights:
      - Collision: 50% (binary + severity)
      - Min TTC:   30%
      - Critical TTC fraction: 20%
    """

    COLLISION_WEIGHT = 0.50
    MIN_TTC_WEIGHT = 0.30
    CRITICAL_TTC_WEIGHT = 0.20

    TTC_SAFE_THRESHOLD = 10.0   # seconds, TTC above this → score = 1.0
    TTC_CRITICAL = 2.0          # seconds

    def compute(self, record: SimulationRecord) -> SafetyResult:
        """
        Compute safety metrics.

        Args:
            record: Completed simulation record.

        Returns:
            SafetyResult with all metrics.
        """
        # ── Collision penalty ────────────────────────────────────────
        collision_penalty = 1.0  # no collision = perfect
        if record.has_collision:
            # Severity scales with impact speed
            # At 30 m/s, penalty approaches 0
            if record.ego_snapshots:
                collision_idx = self._find_collision_step(record)
                if collision_idx is not None:
                    impact_speed = record.ego_snapshots[collision_idx].velocity
                    # Linear scale: 0 m/s → 0.3 penalty, 30 m/s → 0 penalty
                    collision_penalty = max(0.0, 0.3 * (1.0 - impact_speed / 30.0))
                else:
                    collision_penalty = 0.0
            else:
                collision_penalty = 0.0

        # ── Min TTC score ────────────────────────────────────────────
        min_ttc = record.min_ttc_overall
        min_ttc_score = min(1.0, min_ttc / self.TTC_SAFE_THRESHOLD)

        # ── Critical TTC fraction ────────────────────────────────────
        critical_steps = sum(1 for t in record.ttc_values if t <= self.TTC_CRITICAL)
        total_steps = max(1, len(record.ttc_values))
        critical_frac = critical_steps / total_steps
        # Invert: 0% critical → 1.0, 100% → 0.0
        critical_score = 1.0 - critical_frac

        # ── Composite ────────────────────────────────────────────────
        safety_score = (
            self.COLLISION_WEIGHT * collision_penalty
            + self.MIN_TTC_WEIGHT * min_ttc_score
            + self.CRITICAL_TTC_WEIGHT * critical_score
        )

        return SafetyResult(
            collision_occurred=record.has_collision,
            collision_penalty=collision_penalty,
            min_ttc=min_ttc,
            min_ttc_score=min_ttc_score,
            critical_ttc_fraction=critical_frac,
            safety_score=safety_score,
        )

    @staticmethod
    def _find_collision_step(record: SimulationRecord) -> Optional[int]:
        """Find the timestep index where collision occurred."""
        if record.collision_time is None:
            return None
        for i, snap in enumerate(record.ego_snapshots):
            if snap.sim_time >= record.collision_time:
                return i
        return len(record.ego_snapshots) - 1 if record.ego_snapshots else None
