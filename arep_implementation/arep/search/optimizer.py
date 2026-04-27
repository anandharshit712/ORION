"""
ORION Adversarial Search — Optimizers.  [Phase 2]

Two optimizers are provided:
  CMAESOptimizer     — primary; uses CMA-ES for efficient search
  RandomSearchOptimizer — baseline; uniform random sampling

CMA-ES (Covariance Matrix Adaptation Evolution Strategy) is well-suited
for this problem:
  - Black-box optimization (no gradients needed)
  - Handles non-convex, multimodal fitness landscapes
  - Scales well to ~50 dimensions
  - Converges faster than random search in practice

Requires: cma>=3.3.0 (install with: pip install arep[search])
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from arep.search.space import SearchSpace
from arep.search.objective import ObjectiveFunction, EvaluationRecord
from arep.utils.logging_config import get_logger

logger = get_logger("search.optimizer")


@dataclass
class SearchResult:
    """Complete result of an adversarial search run."""
    best_params: Dict[str, Any]
    best_fitness: float
    n_evals: int
    falsification_found: bool
    falsification_params: Optional[Dict[str, Any]]
    all_evaluations: List[EvaluationRecord] = field(default_factory=list)
    optimizer_used: str = "unknown"
    converged: bool = False


class CMAESOptimizer:
    """
    CMA-ES based adversarial scenario search.

    Maximises the ObjectiveFunction by minimising -f(x) internally.
    Stops early if a falsification (collision) is found.

    Args:
        space:       SearchSpace for the scenario.
        sigma0:      Initial step size (fraction of search range). Default: 0.3.
        popsize:     CMA-ES population size. Default: 10.
        max_evals:   Maximum number of fitness evaluations. Default: 200.
        seed:        Random seed for CMA-ES. Default: 0.
    """

    def __init__(
        self,
        space: SearchSpace,
        sigma0: float = 0.3,
        popsize: int = 10,
        max_evals: int = 200,
        seed: int = 0,
    ):
        self.space = space
        self.sigma0 = sigma0
        self.popsize = popsize
        self.max_evals = max_evals
        self.seed = seed

    def run(self, objective: ObjectiveFunction) -> SearchResult:
        """
        Run CMA-ES optimisation and return the best-found parameters.

        TODO [P2]: Import cma library (raise ImportError with install hint if missing).
        TODO [P2]: Initialise CMAEvolutionStrategy at space.midpoint() with sigma0.
        TODO [P2]: Set options: popsize, seed, maxfevals=max_evals, verbose=-9.
        TODO [P2]: Main loop: es.ask() → evaluate each solution → es.tell(solutions, -fitnesses).
        TODO [P2]: Break early if falsification found.
        TODO [P2]: Return SearchResult.
        """
        raise NotImplementedError("CMAESOptimizer.run not yet implemented [P2]")


class RandomSearchOptimizer:
    """
    Baseline optimizer: uniform random sampling over the search space.

    Used for:
      - Comparison against CMA-ES to verify the adversarial search adds value
      - Warm-starting CMA-ES with a good initial point
      - Scenarios with very few dimensions where CMA-ES offers little benefit

    Args:
        space:      SearchSpace for the scenario.
        n_samples:  Number of random samples. Default: 50.
        seed:       Random seed. Default: 0.
    """

    def __init__(
        self,
        space: SearchSpace,
        n_samples: int = 50,
        seed: int = 0,
    ):
        self.space = space
        self.n_samples = n_samples
        self.seed = seed

    def run(self, objective: ObjectiveFunction) -> SearchResult:
        """
        Sample n_samples random points and return the best-found parameters.

        TODO [P2]: Use np.random.default_rng(self.seed) for reproducibility.
        TODO [P2]: Sample self.n_samples points via space.random_point(rng).
        TODO [P2]: Evaluate each with objective(x, seed=i).
        TODO [P2]: Return SearchResult with the best-found params.
        """
        raise NotImplementedError("RandomSearchOptimizer.run not yet implemented [P2]")
