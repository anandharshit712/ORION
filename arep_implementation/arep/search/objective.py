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

        The optimizer maximises this, so a higher value means a worse outcome
        for the ego. Weights are collision-heavy on purpose: the search exists
        to find crashes, not mildly uncomfortable drives.

        Every evaluation is recorded, because the search itself is the
        deliverable — a customer wants the parameter set that broke their
        model, not just the knowledge that one exists.
        """
        import copy

        from arep.core.random_manager import RandomManager
        from arep.execution.runner import EvaluationRunner
        from arep.scenario.parameterizer import ScenarioParameterizer

        params = self._space.to_params_dict(np.asarray(x, dtype=float))

        # Replace the ranges with the concrete point under test, then run the
        # ordinary path. Applying the parameterizer to a block that already
        # holds scalars is a no-op for those keys, so the scenario reaching the
        # engine is exactly the point the optimizer asked for.
        scenario = copy.deepcopy(self._scenario)
        scenario.parameterization = params
        ScenarioParameterizer().apply(scenario, RandomManager(seed))

        runner = EvaluationRunner()
        result = runner.run_scenario_definition(scenario, self._model, seed)

        fitness = self.compute_fitness(
            collision_occurred=result.safety.collision_occurred,
            min_ttc=result.safety.min_ttc,
            safety_score=result.safety.safety_score,
            compliance_score=result.compliance.compliance_score,
        )

        self._history.append(
            EvaluationRecord(
                params=params,
                fitness=fitness,
                seed=seed,
                collision_occurred=result.safety.collision_occurred,
                min_ttc=result.safety.min_ttc,
                safety_score=result.safety.safety_score,
                compliance_score=result.compliance.compliance_score,
                composite_score=result.composite_score,
            )
        )
        return fitness

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

    @property
    def falsification_records(self) -> List[EvaluationRecord]:
        """Every collision-producing record, worst first.

        One counter-example proves the model can fail. Several show *how many
        different ways* it fails, which is the more useful answer: two failures
        from opposite corners of the parameter space are two bugs, not one.

        Ordered by fitness so the worst case is first — that is the one a
        reviewer reproduces before the others.
        """
        return sorted(
            (r for r in self._history if r.collision_occurred),
            key=lambda r: r.fitness,
            reverse=True,
        )

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
