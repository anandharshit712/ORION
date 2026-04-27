"""
ORION Failure Clustering.  [Phase 2]

Post-run analysis that clusters failed simulation runs by their
parameter configurations to identify root-cause fault conditions.

Algorithm:
  1. Pull all FAIL runs for a batch from the DB
  2. Reconstruct the parameter vector for each run from its seed
  3. Run DBSCAN over the parameter vectors
  4. For each cluster: compute mean parameters, failure rate, dominant event
  5. Return human-readable FaultCondition descriptions

Requires: scikit-learn>=1.3.0 (install with: pip install arep[search])
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from arep.utils.logging_config import get_logger

logger = get_logger("analysis.failure_clustering")


@dataclass
class FaultCondition:
    """A cluster of failed runs sharing similar parameter values."""
    description: str            # Human-readable e.g. "NPC initial_x < 28m AND ego_speed > 14 m/s"
    failure_rate: float         # Fraction of runs in this cluster that FAILed (0.0–1.0)
    run_count: int              # Total runs in this cluster
    dominant_event: str         # "collision" | "speed_violation" | "off_road" | "timeout"
    example_run_id: str         # The worst (lowest composite score) run_id in this cluster
    parameter_means: dict = field(default_factory=dict)  # param_name → mean value in cluster


@dataclass
class FailureReport:
    """Complete failure analysis for a batch run."""
    batch_id: str
    total_runs: int
    fail_runs: int
    pass_runs: int
    fault_conditions: List[FaultCondition]    # Ordered by failure_rate desc
    safe_region_description: str             # e.g. "Model is safe when NPC initial_x > 35m"
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

    def analyse(self, batch_id: str) -> FailureReport:
        """
        Run clustering analysis for a completed batch.

        TODO [P2]: Load all runs for batch_id from DB (RunRepository).
        TODO [P2]: For each FAIL run, reconstruct parameter vector from seed + ScenarioParameterizer.
        TODO [P2]: Normalise parameter vectors to [0, 1] range using their min/max bounds.
        TODO [P2]: Run DBSCAN(eps=self.eps, min_samples=self.min_samples) on normalised vectors.
        TODO [P2]: For each cluster: compute FaultCondition with human-readable description.
        TODO [P2]: Identify the safe region as the complement of all fault conditions.
        TODO [P2]: Return FailureReport.
        """
        raise NotImplementedError("FailureClusterer.analyse not yet implemented [P2]")

    def _build_description(
        self,
        cluster_params: dict,
        scenario_param_ranges: dict,
    ) -> str:
        """
        Build a human-readable fault condition description.

        TODO [P2]: For each parameter where cluster mean is in bottom/top 25% of range,
                   generate a comparison string e.g. "NPC initial_x < 28m".
        TODO [P2]: Join multiple conditions with " AND ".
        """
        raise NotImplementedError

    def _build_safe_region(self, fault_conditions: List[FaultCondition]) -> str:
        """
        Describe the safe operating region as the complement of all fault conditions.

        TODO [P2]: Invert each fault condition's comparison direction.
        """
        if not fault_conditions:
            return "No consistent failure patterns detected across the parameter space."
        raise NotImplementedError
