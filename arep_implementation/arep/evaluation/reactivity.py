"""
ORION Reactivity Metrics.

Measures how quickly the model responds to critical situations:
  - Brake response time (time from TTC drop to brake application)
  - Steering response time
  - Response adequacy (was the response sufficient?)
  - Combined reactivity score [0, 1]
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from arep.evaluation.collector import SimulationRecord


@dataclass
class ReactivityResult:
    """Reactivity metric results."""
    brake_response_time: float        # seconds (inf if no response needed)
    steering_response_time: float     # seconds
    response_adequate: bool           # did the model avoid the hazard?
    deceleration_magnitude: float     # m/s² max braking applied
    reactivity_score: float           # composite [0, 1]


class ReactivityMetrics:
    """
    Compute reactivity metrics.

    Measures how fast and effectively the model responds to
    critical situations (TTC ≤ threshold).

    Weights:
      - Brake response time: 40%
      - Steering response time: 20%
      - Response adequacy: 40%
    """

    BRAKE_WEIGHT = 0.40
    STEERING_WEIGHT = 0.20
    ADEQUACY_WEIGHT = 0.40

    TTC_TRIGGER = 5.0              # seconds — start measuring response when TTC drops below this
    IDEAL_RESPONSE_TIME = 0.3       # seconds — ideal human reaction time
    MAX_RESPONSE_TIME = 2.0         # seconds — above this → score = 0
    BRAKE_THRESHOLD = 0.1           # brake value to count as "braking"

    def compute(self, record: SimulationRecord) -> ReactivityResult:
        """
        Compute reactivity metrics.

        Args:
            record: Completed simulation record.

        Returns:
            ReactivityResult.
        """
        ttc_values = record.ttc_values
        actions = record.actions
        snapshots = record.ego_snapshots

        if not ttc_values or not actions:
            return ReactivityResult(
                brake_response_time=float("inf"),
                steering_response_time=float("inf"),
                response_adequate=True,
                deceleration_magnitude=0.0,
                reactivity_score=1.0,
            )

        # ── Find first critical TTC event ────────────────────────────
        trigger_idx = None
        for i, ttc in enumerate(ttc_values):
            if ttc <= self.TTC_TRIGGER:
                trigger_idx = i
                break

        # No critical event → perfect reactivity
        if trigger_idx is None:
            return ReactivityResult(
                brake_response_time=float("inf"),
                steering_response_time=float("inf"),
                response_adequate=True,
                deceleration_magnitude=0.0,
                reactivity_score=1.0,
            )

        # ── Brake response time ──────────────────────────────────────
        brake_response = float("inf")
        for i in range(trigger_idx, min(len(actions), len(snapshots))):
            if actions[i].brake >= self.BRAKE_THRESHOLD:
                brake_response = (
                    snapshots[i].sim_time - snapshots[trigger_idx].sim_time
                )
                break

        # ── Steering response time ───────────────────────────────────
        steering_response = float("inf")
        base_steering = actions[trigger_idx].steering if trigger_idx < len(actions) else 0.0
        for i in range(trigger_idx, len(actions)):
            if abs(actions[i].steering - base_steering) > 0.1:
                if i < len(snapshots):
                    steering_response = (
                        snapshots[i].sim_time - snapshots[trigger_idx].sim_time
                    )
                break

        # ── Max deceleration applied ─────────────────────────────────
        decel_mag = 0.0
        for i in range(trigger_idx, len(snapshots)):
            a = snapshots[i].acceleration
            if a < 0:
                decel_mag = max(decel_mag, abs(a))

        # ── Response adequacy ────────────────────────────────────────
        # If no collision after critical event → adequate
        adequate = not record.has_collision

        # ── Scores ───────────────────────────────────────────────────
        if brake_response == float("inf"):
            brake_score = 0.0
        else:
            brake_score = max(0.0, 1.0 - (brake_response / self.MAX_RESPONSE_TIME))

        if steering_response == float("inf"):
            steering_score = 0.5  # neutral if no steering response needed
        else:
            steering_score = max(
                0.0, 1.0 - (steering_response / self.MAX_RESPONSE_TIME)
            )

        adequacy_score = 1.0 if adequate else 0.0

        reactivity_score = (
            self.BRAKE_WEIGHT * brake_score
            + self.STEERING_WEIGHT * steering_score
            + self.ADEQUACY_WEIGHT * adequacy_score
        )

        return ReactivityResult(
            brake_response_time=brake_response,
            steering_response_time=steering_response,
            response_adequate=adequate,
            deceleration_magnitude=decel_mag,
            reactivity_score=reactivity_score,
        )
