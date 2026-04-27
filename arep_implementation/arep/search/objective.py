"""
ORION Adversarial Search — Objective Function.  [Phase 2]

The objective function runs one simulation with a given parameter
configuration and returns a scalar fitness value. Higher fitness = worse
for the ego model (the optimizer maximises this).

Fitness function:
  f(params) = w_collision · collision_indicator
            + w_ttc · (1 / max(min_ttc, 0.1))
            + w_safety · (1 - safety_score)
            + w_compliance · (1 - compliance_score)

Weights are intentionally collision-heavy — we want the search to
find scenarios that cause collisions, not just score degradations.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import numpy as np

from arep.scenario.schema import ScenarioDefinition
from arep.search.space import SearchSpace
from arep.utils.logging_config import get_logger

logger = get_logger("search.objective")

# Fitness weights — do not change without updating documentation
W_COLLISION = 10.0
W_TTC = 2.0
W_SAFETY = 1.0
W_COMPLIANCE = 0.5


@dataclass
class EvaluationRecord:
    """Result of one fitness evaluation."""
    params: Dict[str, Any]
    fitness: float
    seed: int
    collision_occurred: bool
    min_ttc: float
    safety_score: float
    compliance_score: float
    composite_score: float


class ObjectiveFunction:
    """
    Callable that maps a parameter vector to a scalar fitness value.

    Args:
        scenario:      The base ScenarioDefinition to perturb.
        model:         ModelInterface instance to evaluate.
        space:         SearchSpace for this scenario.
        physics_mode:  "kinematic" or "dynamic".
    """

    def __init__(
        self,
        scenario: ScenarioDefinition,
        model,
        space: SearchSpace,
        physics_mode: str = "kinematic",
    ):
        self._scenario = scenario
        self._model = model
        self._space = space
        self._physics_mode = physics_mode
        self._history: List[EvaluationRecord] = []

    def __call__(self, x: np.ndarray, seed: int = 0) -> float:
        """
        Run one simulation with parameters derived from x and return fitness.

        Args:
            x:    Parameter vector in the search space.
            seed: Deterministic seed for this evaluation.

        Returns:
            Scalar fitness (higher = worse for ego).

        TODO [P2]: Convert x to params_dict via self._space.to_params_dict(x).
        TODO [P2]: Apply params_dict overrides to a copy of self._scenario via ScenarioParameterizer.
        TODO [P2]: Run one simulation with the perturbed scenario and self._model.
        TODO [P2]: Compute fitness from result metrics using the weights above.
        TODO [P2]: Append EvaluationRecord to self._history.
        TODO [P2]: Return fitness scalar.
        """
        raise NotImplementedError("ObjectiveFunction.__call__ not yet implemented [P2]")

    @property
    def history(self) -> List[EvaluationRecord]:
        """All evaluations so far, in order."""
        return list(self._history)

    @property
    def best_record(self) -> Optional[EvaluationRecord]:
        """The evaluation with the highest fitness (worst for ego)."""
        if not self._history:
            return None
        return max(self._history, key=lambda r: r.fitness)

    @property
    def falsification_found(self) -> bool:
        """True if any evaluation produced a collision."""
        return any(r.collision_occurred for r in self._history)

    @property
    def falsification_record(self) -> Optional[EvaluationRecord]:
        """The first collision-producing record, or None."""
        for r in self._history:
            if r.collision_occurred:
                return r
        return None

    @staticmethod
    def compute_fitness(
        collision_occurred: bool,
        min_ttc: float,
        safety_score: float,
        compliance_score: float,
    ) -> float:
        """
        Compute fitness scalar from simulation result metrics.

        This is a pure function — easy to unit test independently.
        """
        return (
            W_COLLISION * float(collision_occurred)
            + W_TTC * (1.0 / max(min_ttc, 0.1))
            + W_SAFETY * (1.0 - safety_score)
            + W_COMPLIANCE * (1.0 - compliance_score)
        )
