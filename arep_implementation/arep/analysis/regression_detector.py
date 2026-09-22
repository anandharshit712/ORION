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
from typing import List

from arep.utils.logging_config import get_logger

logger = get_logger("analysis.regression_detector")

# Regression thresholds (never change without updating baselines)
REGRESSION_COMPOSITE_THRESHOLD = 0.05  # 5% drop in composite score
REGRESSION_SAFETY_THRESHOLD = 0.10  # 10% drop in safety score
REGRESSION_COLLISION_THRESHOLD = 0.01  # 1pp increase in collision rate


@dataclass
class MetricDelta:
    """Change in a single metric between two model versions."""

    metric: str
    value_a: float  # baseline (vN-1) value
    value_b: float  # candidate (vN) value
    delta: float  # value_b - value_a (positive = improved)
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
    winner: str = "tie"  # "a" | "b" | "tie"
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
    recommendation: str = ""  # "Safe to deploy" | "Regression detected — do not deploy"


class RegressionDetector:
    """
    Detects performance regressions between two model versions.

    Compares batches with identical scenario IDs and run counts.
    """

    # Per-metric thresholds. Composite, safety and the component scores are
    # "higher is better"; collision rate is not, and is handled separately.
    _SCORE_METRICS = (
        ("composite_score", "composite_mean", REGRESSION_COMPOSITE_THRESHOLD),
        ("safety_score", "safety_mean", REGRESSION_SAFETY_THRESHOLD),
        ("compliance_score", "compliance_mean", REGRESSION_COMPOSITE_THRESHOLD),
        ("stability_score", "stability_mean", REGRESSION_COMPOSITE_THRESHOLD),
        ("reactivity_score", "reactivity_mean", REGRESSION_COMPOSITE_THRESHOLD),
    )

    # A candidate has to be meaningfully better to "win" a scenario, not merely
    # different. Without this, every comparison resolves to a winner on noise.
    WIN_MARGIN = 0.02

    def compare(
        self,
        model_a_id: str,
        model_b_id: str,
        scenario_ids: List[str],
        runs_per_scenario: int,
        seed: int,
    ) -> ComparisonReport:
        """
        Run both models across every scenario and compare them.

        Both models get the **same seed** on the same scenario, so they face
        identical parameter draws. Comparing one model on one sample of the
        space against another model on a different sample measures the sampler,
        not the models.
        """
        from arep.api.routes import AVAILABLE_MODELS
        from arep.execution.runner import EvaluationRunner
        from arep.models.resolver import resolve_model

        runner = EvaluationRunner()
        model_a = resolve_model(model_a_id, AVAILABLE_MODELS)
        model_b = resolve_model(model_b_id, AVAILABLE_MODELS)

        report = ComparisonReport(
            model_a_id=model_a_id,
            model_a_name=model_a.name,
            model_b_id=model_b_id,
            model_b_name=model_b.name,
        )

        try:
            for scenario_id in scenario_ids:
                batch_a = runner.run_batch(
                    scenario_id, model_a, runs_per_scenario, seed
                )
                batch_b = runner.run_batch(
                    scenario_id, model_b, runs_per_scenario, seed
                )
                report.scenario_comparisons.append(
                    self._compare_aggregates(
                        scenario_id,
                        model_a.name,
                        model_b.name,
                        batch_a.aggregated,
                        batch_b.aggregated,
                        runs_per_scenario,
                    )
                )
        finally:
            # Out-of-process models hold a child process or a container.
            for model in (model_a, model_b):
                closer = getattr(model, "close", None)
                if callable(closer):
                    try:
                        closer()
                    except Exception:
                        logger.exception("Could not release model %s", model)

        return self._finalise(report)

    def compare_from_db(
        self,
        batch_id_a: str,
        batch_id_b: str,
    ) -> ComparisonReport:
        """
        Compare two batches that have already run.

        The usual path in CI: the baseline batch ran when the previous model
        was released, and re-running it would both cost the customer credits
        and risk a different answer if anything about the platform has moved
        since.
        """
        from arep.database.connection import session_scope
        from arep.database.repository import BatchJobRepository, RunRepository

        with session_scope() as session:
            jobs = BatchJobRepository(session)
            runs = RunRepository(session)

            job_a = jobs.get_by_id(int(batch_id_a), org_id=None)
            job_b = jobs.get_by_id(int(batch_id_b), org_id=None)
            if job_a is None or job_b is None:
                missing = batch_id_a if job_a is None else batch_id_b
                raise ValueError(f"No batch job with id {missing!r}")

            if job_a.scenario_name != job_b.scenario_name:
                # Comparing different scenarios yields a confident number about
                # nothing.
                raise ValueError(
                    f"Batches ran different scenarios "
                    f"({job_a.scenario_name!r} vs {job_b.scenario_name!r}); "
                    f"there is nothing to compare."
                )

            summary_a = _summarise(runs.get_runs_for_batch(int(batch_id_a)))
            summary_b = _summarise(runs.get_runs_for_batch(int(batch_id_b)))
            names = (job_a.model_name, job_b.model_name, job_a.scenario_name)

        if summary_a.num_runs == 0 or summary_b.num_runs == 0:
            raise ValueError("One of the batches has no recorded runs.")

        model_a_name, model_b_name, scenario_name = names
        report = ComparisonReport(
            model_a_id=str(batch_id_a),
            model_a_name=model_a_name,
            model_b_id=str(batch_id_b),
            model_b_name=model_b_name,
        )
        report.scenario_comparisons.append(
            self._compare_aggregates(
                scenario_name,
                model_a_name,
                model_b_name,
                summary_a,
                summary_b,
                min(summary_a.num_runs, summary_b.num_runs),
            )
        )
        return self._finalise(report)

    # ── Internals ────────────────────────────────────────────────────

    def _compare_aggregates(
        self,
        scenario_id,
        model_a_name,
        model_b_name,
        agg_a,
        agg_b,
        runs,
    ) -> ScenarioComparison:
        comparison = ScenarioComparison(
            scenario_id=scenario_id,
            model_a_name=model_a_name,
            model_b_name=model_b_name,
            runs_per_model=runs,
        )

        for metric, attribute, threshold in self._SCORE_METRICS:
            value_a = float(getattr(agg_a, attribute))
            value_b = float(getattr(agg_b, attribute))
            delta = value_b - value_a
            comparison.metric_deltas.append(
                MetricDelta(
                    metric=metric,
                    value_a=value_a,
                    value_b=value_b,
                    delta=delta,
                    is_regression=delta < -threshold,
                    threshold_used=threshold,
                )
            )

        # Collision rate is inverted: a rise is the regression. The delta is
        # negated so "positive means improved" holds for every metric here.
        rate_a = float(agg_a.collision_rate)
        rate_b = float(agg_b.collision_rate)
        comparison.metric_deltas.append(
            MetricDelta(
                metric="collision_rate",
                value_a=rate_a,
                value_b=rate_b,
                delta=-(rate_b - rate_a),
                is_regression=(rate_b - rate_a) > REGRESSION_COLLISION_THRESHOLD,
                threshold_used=REGRESSION_COLLISION_THRESHOLD,
            )
        )

        comparison.has_regression = any(
            d.is_regression for d in comparison.metric_deltas
        )

        composite_delta = next(
            d.delta for d in comparison.metric_deltas if d.metric == "composite_score"
        )
        if composite_delta > self.WIN_MARGIN:
            comparison.winner = "b"
        elif composite_delta < -self.WIN_MARGIN:
            comparison.winner = "a"
        else:
            comparison.winner = "tie"

        return comparison

    def _finalise(self, report: ComparisonReport) -> ComparisonReport:
        report.regressions = [
            delta
            for comparison in report.scenario_comparisons
            for delta in comparison.metric_deltas
            if delta.is_regression
        ]

        wins_b = sum(1 for c in report.scenario_comparisons if c.winner == "b")
        wins_a = sum(1 for c in report.scenario_comparisons if c.winner == "a")

        if report.regressions:
            # A regression outranks the win count. A candidate that is better
            # on four scenarios and dangerous on the fifth does not ship.
            report.overall_winner = "a"
            worst = min(report.regressions, key=lambda d: d.delta)
            report.recommendation = (
                f"Regression detected — do not deploy. "
                f"{len(report.regressions)} metric(s) regressed, worst: "
                f"{worst.metric} {worst.value_a:.3f} to {worst.value_b:.3f} "
                f"against a threshold of {worst.threshold_used:.2f}."
            )
            return report

        if wins_b > wins_a:
            report.overall_winner = "b"
            report.recommendation = (
                f"Safe to deploy. No regressions, and the candidate wins "
                f"{wins_b} of {len(report.scenario_comparisons)} scenarios."
            )
        elif wins_a > wins_b:
            report.overall_winner = "a"
            report.recommendation = (
                f"Safe to deploy, but no improvement: the baseline wins "
                f"{wins_a} of {len(report.scenario_comparisons)} scenarios."
            )
        else:
            report.overall_winner = "tie"
            report.recommendation = (
                "Safe to deploy. No regressions and no measurable difference."
            )
        return report


def _summarise(runs):
    """Aggregate stored RunRecords the way StatisticalAggregator would.

    Recomputed from the rows rather than read off the batch job, because the
    stored aggregate was written by whatever version of the scoring code was
    current at the time — and comparing across a scoring change is exactly
    what this tool must not do silently.
    """
    from arep.statistics.aggregator import AggregatedMetrics

    if not runs:
        return AggregatedMetrics(num_runs=0)

    def mean(attribute):
        return sum(float(getattr(r, attribute)) for r in runs) / len(runs)

    return AggregatedMetrics(
        num_runs=len(runs),
        composite_mean=mean("composite_score"),
        safety_mean=mean("safety_score"),
        compliance_mean=mean("compliance_score"),
        stability_mean=mean("stability_score"),
        reactivity_mean=mean("reactivity_score"),
        collision_rate=sum(1 for r in runs if r.collision_occurred) / len(runs),
    )
