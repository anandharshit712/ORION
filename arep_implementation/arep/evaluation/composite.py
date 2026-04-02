"""
ORION Composite Evaluator.

Combines all four metric categories into a single evaluation result.

Composite Score = weighted average of:
  Safety      (35%)
  Compliance  (25%)
  Stability   (20%)
  Reactivity  (20%)
"""

from __future__ import annotations

from dataclasses import dataclass

from arep.evaluation.collector import SimulationRecord
from arep.evaluation.safety import SafetyMetrics, SafetyResult
from arep.evaluation.compliance import ComplianceMetrics, ComplianceResult
from arep.evaluation.stability import StabilityMetrics, StabilityResult
from arep.evaluation.reactivity import ReactivityMetrics, ReactivityResult


@dataclass
class EvaluationResult:
    """Complete evaluation result for one simulation run."""
    safety: SafetyResult
    compliance: ComplianceResult
    stability: StabilityResult
    reactivity: ReactivityResult
    composite_score: float            # Weighted average [0, 1]

    # Metadata
    scenario_name: str = ""
    model_name: str = ""
    duration: float = 0.0
    termination_reason: str = ""
    master_seed: int = 0

    def to_dict(self) -> dict:
        return {
            "composite_score": round(self.composite_score, 4),
            "safety_score": round(self.safety.safety_score, 4),
            "compliance_score": round(self.compliance.compliance_score, 4),
            "stability_score": round(self.stability.stability_score, 4),
            "reactivity_score": round(self.reactivity.reactivity_score, 4),
            "collision_occurred": self.safety.collision_occurred,
            "min_ttc": round(self.safety.min_ttc, 2),
            "duration": round(self.duration, 2),
            "termination_reason": self.termination_reason,
            "scenario_name": self.scenario_name,
            "model_name": self.model_name,
        }


class CompositeEvaluator:
    """
    Run all four evaluators and combine into a composite score.

    Weights:
      - Safety:    35%
      - Compliance: 25%
      - Stability: 20%
      - Reactivity: 20%
    """

    SAFETY_WEIGHT = 0.35
    COMPLIANCE_WEIGHT = 0.25
    STABILITY_WEIGHT = 0.20
    REACTIVITY_WEIGHT = 0.20

    def __init__(self):
        self.safety = SafetyMetrics()
        self.compliance = ComplianceMetrics()
        self.stability = StabilityMetrics()
        self.reactivity = ReactivityMetrics()

    def evaluate(self, record: SimulationRecord) -> EvaluationResult:
        """
        Compute all metrics and composite score.

        Args:
            record: Completed simulation record.

        Returns:
            Complete EvaluationResult.
        """
        safety_result = self.safety.compute(record)
        compliance_result = self.compliance.compute(record)
        stability_result = self.stability.compute(record)
        reactivity_result = self.reactivity.compute(record)

        composite = (
            self.SAFETY_WEIGHT * safety_result.safety_score
            + self.COMPLIANCE_WEIGHT * compliance_result.compliance_score
            + self.STABILITY_WEIGHT * stability_result.stability_score
            + self.REACTIVITY_WEIGHT * reactivity_result.reactivity_score
        )

        return EvaluationResult(
            safety=safety_result,
            compliance=compliance_result,
            stability=stability_result,
            reactivity=reactivity_result,
            composite_score=composite,
            scenario_name=record.scenario_name,
            model_name=record.model_name,
            duration=record.duration,
            termination_reason=record.termination_reason or "",
            master_seed=record.master_seed,
        )
