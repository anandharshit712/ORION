"""
ORION Regression Detector.  [Phase 2]

Compares model vN against vN-1 across the same scenario suite to flag
safety regressions before they reach production.

A regression is flagged when ANY of the following are true:
  - composite_score drops by > 5% (REGRESSION_COMPOSITE_THRESHOLD)
  - safety_score drops by > 10% (REGRESSION_SAFETY_THRESHOLD)
  - collision_rate increases by > 1pp (REGRESSION_COLLISION_THRESHOLD)

These thresholds are intentionally strict — false positives are
preferable to missed regressions in a safety-critical system.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from arep.utils.logging_config import get_logger

logger = get_logger("analysis.regression_detector")

# Regression thresholds (never change without updating baselines)
REGRESSION_COMPOSITE_THRESHOLD = 0.05      # 5% drop in composite score
REGRESSION_SAFETY_THRESHOLD = 0.10         # 10% drop in safety score
REGRESSION_COLLISION_THRESHOLD = 0.01      # 1pp increase in collision rate


@dataclass
class MetricDelta:
    """Change in a single metric between two model versions."""
    metric: str
    value_a: float           # baseline (vN-1) value
    value_b: float           # candidate (vN) value
    delta: float             # value_b - value_a (positive = improved)
    is_regression: bool
    threshold_used: float


@dataclass
class ScenarioComparison:
    """Comparison result for one scenario between two model versions."""
    scenario_id: str
    model_a_name: str
    model_b_name: str
    metric_deltas: List[MetricDelta] = field(default_factory=list)
    has_regression: bool = False
    winner: str = "tie"      # "a" | "b" | "tie"
    runs_per_model: int = 0


@dataclass
class ComparisonReport:
    """Full comparison between two model versions across all scenarios."""
    model_a_id: str
    model_a_name: str
    model_b_id: str
    model_b_name: str
    scenario_comparisons: List[ScenarioComparison] = field(default_factory=list)
    regressions: List[MetricDelta] = field(default_factory=list)
    overall_winner: str = "tie"
    recommendation: str = ""   # "Safe to deploy" | "Regression detected — do not deploy"


class RegressionDetector:
    """
    Detects performance regressions between two model versions.

    Compares batches with identical scenario IDs and run counts.
    """

    def compare(
        self,
        model_a_id: str,
        model_b_id: str,
        scenario_ids: List[str],
        runs_per_scenario: int,
        seed: int,
    ) -> ComparisonReport:
        """
        Run both models across all scenario_ids and compare results.

        TODO [P2]: For each scenario, run batch of runs_per_scenario for model_a and model_b.
        TODO [P2]: Compute MetricDelta for composite, safety, compliance, stability, reactivity, collision_rate.
        TODO [P2]: Flag regressions using the thresholds above.
        TODO [P2]: Determine winner per scenario (b wins if composite delta > 0.02, else tie).
        TODO [P2]: Set overall_winner based on majority + no regressions.
        TODO [P2]: Set recommendation string.
        """
        raise NotImplementedError("RegressionDetector.compare not yet implemented [P2]")

    def compare_from_db(
        self,
        batch_id_a: str,
        batch_id_b: str,
    ) -> ComparisonReport:
        """
        Compare two already-completed batches from the DB without re-running.

        TODO [P2]: Load batch results from DB, compute deltas directly.
        """
        raise NotImplementedError("RegressionDetector.compare_from_db not yet implemented [P2]")

    @staticmethod
    def _check_metric(
        metric: str,
        value_a: float,
        value_b: float,
        higher_is_better: bool = True,
    ) -> MetricDelta:
        """Compute delta and determine if it constitutes a regression."""
        delta = value_b - value_a
        thresholds = {
            "composite_score": REGRESSION_COMPOSITE_THRESHOLD,
            "safety_score": REGRESSION_SAFETY_THRESHOLD,
            "collision_rate": REGRESSION_COLLISION_THRESHOLD,
        }
        threshold = thresholds.get(metric, REGRESSION_COMPOSITE_THRESHOLD)

        if higher_is_better:
            is_regression = delta < -threshold
        else:
            is_regression = delta > threshold

        return MetricDelta(
            metric=metric,
            value_a=value_a,
            value_b=value_b,
            delta=delta,
            is_regression=is_regression,
            threshold_used=threshold,
        )
