"""
ORION Failure Clustering.  [Phase 2.2]

Post-run analysis that clusters failed simulation runs by the parameters that
produced them, to identify root-cause fault conditions.

A batch of 500 runs reporting "12% collision rate" tells a customer they have a
problem. It does not tell them *when* — and "when" is the only part they can
act on. This answers that: which region of the parameter space the failures
came from, and what the complement of those regions looks like.

Algorithm:
  1. Pull every run for a batch from the DB
  2. Reconstruct each failed run's parameter vector from its seed
  3. Normalise to [0, 1] over the observed range and run DBSCAN
  4. For each cluster: mean parameters, regional failure rate, dominant event
  5. Return human-readable FaultCondition descriptions

Parameters are reconstructed rather than stored: applying the parameterizer to
a fresh copy of the scenario with ``RandomManager(seed)`` reproduces exactly
what that run used, because the whole platform rests on that being true. If it
ever stops being true this analysis is wrong in the same way every score is,
and the per-run frame hash catches it first.

Requires: scikit-learn>=1.3.0 (install with: pip install arep[search])
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Tuple

from arep.utils.logging_config import get_logger

logger = get_logger("analysis.failure_clustering")


@dataclass
class FaultCondition:
    """A cluster of failed runs sharing similar parameter values."""

    description: str  # Human-readable e.g. "NPC initial_x < 28m AND ego_speed > 14 m/s"
    failure_rate: float  # Fraction of runs in this region that FAILed (0.0–1.0)
    run_count: int  # Total runs in this cluster
    dominant_event: str  # "collision" | "off_road" | "timeout" | ...
    example_run_id: str  # The worst (lowest composite score) run_id in this cluster
    parameter_means: dict = field(
        default_factory=dict
    )  # param_name → mean value in cluster


@dataclass
class FailureReport:
    """Complete failure analysis for a batch run."""

    batch_id: str
    total_runs: int
    fail_runs: int
    pass_runs: int
    fault_conditions: List[FaultCondition]  # Ordered by failure_rate desc
    safe_region_description: str  # e.g. "Model is safe when NPC initial_x > 35m"
    analysis_method: str = "dbscan"

    @property
    def overall_pass_rate(self) -> float:
        if self.total_runs == 0:
            return 0.0
        return self.pass_runs / self.total_runs


class FailureClusterer:
    """
    Clusters failed runs by parameter configuration to find fault conditions.

    Args:
        eps:      DBSCAN neighbourhood radius in normalised parameter space.
        min_samples: DBSCAN minimum cluster size.
    """

    def __init__(self, eps: float = 0.3, min_samples: int = 3):
        self.eps = eps
        self.min_samples = min_samples

    def analyse(self, batch_id) -> FailureReport:
        """Cluster a completed batch's failures by the parameters behind them."""
        from arep.database.connection import session_scope
        from arep.database.repository import BatchJobRepository, RunRepository

        with session_scope() as session:
            job = BatchJobRepository(session).get_by_id(int(batch_id), org_id=None)
            if job is None:
                raise ValueError(f"No batch job with id {batch_id!r}")
            scenario_path = job.scenario_path
            runs = [
                {
                    "master_seed": r.master_seed,
                    "composite_score": r.composite_score,
                    "collision": bool(r.collision_occurred),
                    "termination_reason": r.termination_reason or "timeout",
                    "run_id": str(r.id),
                }
                for r in RunRepository(session).get_runs_for_batch(int(batch_id))
            ]

        if not runs:
            return FailureReport(
                batch_id=str(batch_id),
                total_runs=0,
                fail_runs=0,
                pass_runs=0,
                fault_conditions=[],
                safe_region_description="No runs recorded for this batch.",
            )

        failures = [r for r in runs if _is_failure(r)]
        report = FailureReport(
            batch_id=str(batch_id),
            total_runs=len(runs),
            fail_runs=len(failures),
            pass_runs=len(runs) - len(failures),
            fault_conditions=[],
            safe_region_description="",
        )

        if not failures:
            report.safe_region_description = (
                "No failures in this batch; the model held across the whole "
                "sampled parameter space."
            )
            return report

        if not scenario_path:
            # Batches recorded before the path was stored cannot have their
            # parameters reproduced. Say so, rather than clustering nothing and
            # implying the failures had no pattern.
            report.safe_region_description = (
                "This batch has no scenario path recorded, so its parameters "
                "cannot be reconstructed. Re-run the batch to analyse it."
            )
            return report

        vectors, names = self._parameter_vectors(scenario_path, failures)
        if not names:
            report.safe_region_description = (
                "This scenario declares no parameterisation, so every run used "
                "identical inputs and there is no parameter space to cluster. "
                "The failures share a cause that is not a parameter."
            )
            return report

        report.fault_conditions = self._cluster(vectors, names, failures, runs)
        report.safe_region_description = self._build_safe_region(
            report.fault_conditions
        )
        return report

    # ── Internals ────────────────────────────────────────────────────

    def _parameter_vectors(
        self,
        scenario_path: str,
        failures: List[dict],
    ) -> Tuple[List[List[float]], List[str]]:
        """Reconstruct each failed run's concrete parameter values from its seed."""
        import copy

        from arep.core.random_manager import RandomManager
        from arep.scenario.parameterizer import ScenarioParameterizer
        from arep.scenario.parser import ScenarioParser

        template, _ = ScenarioParser().parse_file(scenario_path)
        if not template.parameterization:
            return [], []

        parameterizer = ScenarioParameterizer()
        rows = []
        for run in failures:
            scenario = copy.deepcopy(template)
            parameterizer.apply(scenario, RandomManager(run["master_seed"]))
            rows.append(_flatten_parameters(scenario))

        names = sorted(rows[0]) if rows else []
        vectors = [[row.get(name, 0.0) for name in names] for row in rows]
        return vectors, names

    def _cluster(
        self,
        vectors: List[List[float]],
        names: List[str],
        failures: List[dict],
        all_runs: List[dict],
    ) -> List[FaultCondition]:
        """DBSCAN over normalised parameter vectors.

        DBSCAN rather than k-means because the number of fault regions is the
        answer, not an input — and because a model usually fails in one or two
        corners of the space with everything else scattered, which is the shape
        DBSCAN handles and k-means does not.
        """
        import numpy as np
        from sklearn.cluster import DBSCAN

        raw = np.asarray(vectors, dtype=float)
        spans = raw.max(axis=0) - raw.min(axis=0)
        # A parameter that never varied carries no information, and dividing by
        # its zero span produces NaNs that poison every distance in the matrix.
        spans[spans < 1e-12] = 1.0
        normalised = (raw - raw.min(axis=0)) / spans

        labels = DBSCAN(eps=self.eps, min_samples=self.min_samples).fit_predict(
            normalised
        )
        ranges = _observed_ranges(raw, names)

        conditions: List[FaultCondition] = []
        for label in sorted(set(labels)):
            if label == -1:
                continue  # DBSCAN noise: failures with no shared pattern
            members = [i for i, value in enumerate(labels) if value == label]
            cluster_rows = raw[members]
            means = {
                name: float(cluster_rows[:, j].mean()) for j, name in enumerate(names)
            }
            worst = min(members, key=lambda i: failures[i]["composite_score"])

            conditions.append(
                FaultCondition(
                    description=self._build_description(means, ranges),
                    failure_rate=_regional_failure_rate(len(members), all_runs),
                    run_count=len(members),
                    dominant_event=_dominant_event([failures[i] for i in members]),
                    example_run_id=failures[worst]["run_id"],
                    parameter_means=means,
                )
            )

        conditions.sort(key=lambda c: (c.failure_rate, c.run_count), reverse=True)
        return conditions

    def _build_description(
        self,
        cluster_params: dict,
        scenario_param_ranges: dict,
    ) -> str:
        """Human-readable fault condition.

        Mentions only parameters where the cluster sits in the bottom or top
        quarter of the observed range. A description listing every parameter
        says nothing; the useful part is the two or three that characterise
        the region.
        """
        clauses = []
        for name, mean in sorted(cluster_params.items()):
            low, high = scenario_param_ranges.get(name, (mean, mean))
            span = high - low
            if span < 1e-12:
                continue
            position = (mean - low) / span
            if position <= 0.25:
                clauses.append(f"{name} < {_fmt(low + span * 0.25)}")
            elif position >= 0.75:
                clauses.append(f"{name} > {_fmt(high - span * 0.25)}")

        if not clauses:
            return "failures spread across the sampled range with no dominant parameter"
        return " AND ".join(clauses)

    def _build_safe_region(self, fault_conditions: List[FaultCondition]) -> str:
        """The complement of the fault conditions, stated as guidance.

        Deliberately hedged: "not observed to fail here" is a different claim
        from "safe". Only the sampled space was explored, and DBSCAN noise is
        excluded from the clusters entirely.
        """
        if not fault_conditions:
            return "No consistent failure patterns detected across the parameter space."

        inverted = []
        for condition in fault_conditions:
            parts = []
            for clause in condition.description.split(" AND "):
                if " < " in clause:
                    parts.append(clause.replace(" < ", " >= "))
                elif " > " in clause:
                    parts.append(clause.replace(" > ", " <= "))
            if parts:
                inverted.append(" OR ".join(parts))

        if not inverted:
            return (
                "Failures did not concentrate in any region of the sampled "
                "parameter space."
            )
        return (
            "No failures were observed when "
            + "; and ".join(inverted)
            + ". This describes the sampled space only, not a safety guarantee."
        )


# ── Helpers ──────────────────────────────────────────────────────────────


def _is_failure(run: dict) -> bool:
    """A run failed if it hit something or left the road.

    Deliberately not a composite-score threshold: a low score can mean an
    uncomfortable but safe drive, and calling that a "failure" would cluster
    ride quality together with crashes.
    """
    return run["collision"] or run["termination_reason"] == "off_road"


def _flatten_parameters(scenario) -> Dict[str, float]:
    """The concrete numeric inputs one run actually used.

    Only values the parameterizer can vary are included — a constant is the
    same in every run and would contribute a zero-span column.
    """
    values: Dict[str, float] = {
        "ego_velocity": float(scenario.ego_initial.velocity),
        "ego_x": float(scenario.ego_initial.x),
        "ego_y": float(scenario.ego_initial.y),
    }
    for obj in scenario.traffic_objects:
        values[f"{obj.id}.initial_x"] = float(obj.initial.x)
        values[f"{obj.id}.initial_y"] = float(obj.initial.y)
        values[f"{obj.id}.initial_velocity"] = float(obj.initial.velocity)
        for key, value in (obj.behavior.parameters or {}).items():
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                values[f"{obj.id}.{key}"] = float(value)
    return values


def _observed_ranges(raw, names: List[str]) -> Dict[str, Tuple[float, float]]:
    return {
        name: (float(raw[:, j].min()), float(raw[:, j].max()))
        for j, name in enumerate(names)
    }


def _regional_failure_rate(cluster_size: int, all_runs: List[dict]) -> float:
    """Share of the batch that this fault region accounts for.

    Not the share of runs *within* the region that failed: only failures are
    clustered, so that number would be 1.0 by construction and would tell a
    customer nothing.
    """
    if not all_runs:
        return 0.0
    return cluster_size / len(all_runs)


def _dominant_event(cluster: List[dict]) -> str:
    counts: Dict[str, int] = {}
    for run in cluster:
        key = "collision" if run["collision"] else run["termination_reason"]
        counts[key] = counts.get(key, 0) + 1
    return max(counts, key=lambda k: counts[k]) if counts else "unknown"


def _fmt(value: float) -> str:
    return f"{value:.2f}".rstrip("0").rstrip(".")
