"""
ORION Statistical Aggregation.

Aggregates evaluation results across multiple simulation runs:
  - Mean and std of composite + individual scores
  - Confidence intervals (Wilson score for proportions, t-distribution for means)
  - Collision rate with confidence interval
  - Robustness summary
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List

import numpy as np
from scipy import stats

from arep.evaluation.composite import EvaluationResult


@dataclass
class AggregatedMetrics:
    """Aggregated metrics across multiple runs."""
    num_runs: int = 0

    # Composite
    composite_mean: float = 0.0
    composite_std: float = 0.0
    composite_ci_lower: float = 0.0
    composite_ci_upper: float = 0.0

    # Per-category means
    safety_mean: float = 0.0
    compliance_mean: float = 0.0
    stability_mean: float = 0.0
    reactivity_mean: float = 0.0

    # Collision rate
    collision_rate: float = 0.0
    collision_rate_ci_lower: float = 0.0
    collision_rate_ci_upper: float = 0.0

    # Min TTC
    min_ttc_mean: float = 0.0
    min_ttc_std: float = 0.0

    # Duration
    mean_duration: float = 0.0

    def to_dict(self) -> dict:
        return {
            "num_runs": self.num_runs,
            "composite_mean": round(self.composite_mean, 4),
            "composite_std": round(self.composite_std, 4),
            "composite_95ci": [
                round(self.composite_ci_lower, 4),
                round(self.composite_ci_upper, 4),
            ],
            "safety_mean": round(self.safety_mean, 4),
            "compliance_mean": round(self.compliance_mean, 4),
            "stability_mean": round(self.stability_mean, 4),
            "reactivity_mean": round(self.reactivity_mean, 4),
            "collision_rate": round(self.collision_rate, 4),
            "collision_rate_95ci": [
                round(self.collision_rate_ci_lower, 4),
                round(self.collision_rate_ci_upper, 4),
            ],
            "min_ttc_mean": round(self.min_ttc_mean, 2),
            "mean_duration": round(self.mean_duration, 2),
        }


class StatisticalAggregator:
    """
    Aggregate evaluation results with confidence intervals.

    Usage:
        agg = StatisticalAggregator()
        agg.add_result(result1)
        agg.add_result(result2)
        summary = agg.compute()
    """

    def __init__(self, confidence_level: float = 0.95):
        self.confidence_level = confidence_level
        self.results: List[EvaluationResult] = []

    def add_result(self, result: EvaluationResult) -> None:
        self.results.append(result)

    def compute(self) -> AggregatedMetrics:
        """Compute aggregated metrics."""
        n = len(self.results)
        if n == 0:
            return AggregatedMetrics()

        composites = np.array([r.composite_score for r in self.results])
        safeties = np.array([r.safety.safety_score for r in self.results])
        compliances = np.array([r.compliance.compliance_score for r in self.results])
        stabilities = np.array([r.stability.stability_score for r in self.results])
        reactivities = np.array([r.reactivity.reactivity_score for r in self.results])
        min_ttcs = np.array([r.safety.min_ttc for r in self.results])
        durations = np.array([r.duration for r in self.results])

        collisions = sum(1 for r in self.results if r.safety.collision_occurred)

        # Confidence intervals
        comp_ci = self._mean_ci(composites)
        col_ci = self._wilson_ci(collisions, n)

        return AggregatedMetrics(
            num_runs=n,
            composite_mean=float(np.mean(composites)),
            composite_std=float(np.std(composites, ddof=1)) if n > 1 else 0.0,
            composite_ci_lower=comp_ci[0],
            composite_ci_upper=comp_ci[1],
            safety_mean=float(np.mean(safeties)),
            compliance_mean=float(np.mean(compliances)),
            stability_mean=float(np.mean(stabilities)),
            reactivity_mean=float(np.mean(reactivities)),
            collision_rate=collisions / n,
            collision_rate_ci_lower=col_ci[0],
            collision_rate_ci_upper=col_ci[1],
            min_ttc_mean=float(np.mean(min_ttcs)),
            min_ttc_std=float(np.std(min_ttcs, ddof=1)) if n > 1 else 0.0,
            mean_duration=float(np.mean(durations)),
        )

    def _mean_ci(self, values: np.ndarray) -> tuple[float, float]:
        """Compute confidence interval for mean using t-distribution."""
        n = len(values)
        if n < 2:
            m = float(np.mean(values))
            return m, m

        mean = float(np.mean(values))
        se = float(stats.sem(values))

        # If standard error is 0 (all values identical), CI = (mean, mean)
        if se < 1e-15:
            return mean, mean

        ci = stats.t.interval(
            self.confidence_level, df=n - 1, loc=mean, scale=se
        )
        return float(ci[0]), float(ci[1])

    def _wilson_ci(
        self, successes: int, total: int,
    ) -> tuple[float, float]:
        """
        Wilson score confidence interval for a proportion.

        Better than normal approximation for small samples
        or proportions near 0/1.
        """
        if total == 0:
            return 0.0, 0.0

        z = stats.norm.ppf(1 - (1 - self.confidence_level) / 2)
        p_hat = successes / total
        denominator = 1 + z**2 / total

        center = (p_hat + z**2 / (2 * total)) / denominator
        spread = (z / denominator) * np.sqrt(
            p_hat * (1 - p_hat) / total + z**2 / (4 * total**2)
        )

        return max(0.0, float(center - spread)), min(1.0, float(center + spread))

    def reset(self) -> None:
        self.results.clear()
