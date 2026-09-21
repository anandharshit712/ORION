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
from typing import Any, Dict, List, Optional


from arep.search.space import SearchSpace
import numpy as np

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
        Search for the parameter set that breaks the model.

        CMA-ES minimises, and the objective is written so that higher is worse
        for the ego, so the sign is flipped on the way in. Getting that
        backwards would produce a confident search for the *safest* scenario,
        which is why the fitness function is unit-tested separately.

        The search stops as soon as it finds a collision. Beyond that point it
        would be refining how badly the model crashes, and a customer needs one
        reproducible counter-example, not the worst possible one.
        """
        try:
            import cma
        except ImportError as exc:      # pragma: no cover - depends on extras
            raise ImportError(
                "Adversarial search needs the cma package: "
                "pip install 'arep[search]'"
            ) from exc

        if self.space.n_dims == 0:
            # Nothing to search. Returning an empty result beats running 200
            # identical simulations and reporting the last one.
            return SearchResult(
                best_params={}, best_fitness=0.0, n_evals=0,
                falsification_found=False, falsification_params=None,
                optimizer_used="cma-es", converged=True,
            )

        if self.space.n_dims == 1:
            # CMA-ES needs at least two dimensions to build a covariance.
            # Falling back is better than raising: a one-parameter scenario is
            # a legitimate thing to search, just not with this algorithm.
            logger.info("Single-dimension space — using random search instead")
            fallback = RandomSearchOptimizer(
                self.space, n_samples=self.max_evals, seed=self.seed,
            )
            result = fallback.run(objective)
            result.optimizer_used = "random (cma-es needs >= 2 dims)"
            return result

        lows, highs = self.strategy_bounds()
        strategy = cma.CMAEvolutionStrategy(
            list(self.space.midpoint()),
            self.sigma0 * float((highs - lows).mean()),
            {
                "popsize": self.popsize,
                "seed": self.seed + 1,   # cma rejects seed=0 as "use entropy"
                "maxfevals": self.max_evals,
                "bounds": [list(lows), list(highs)],
                "verbose": -9,
            },
        )

        evaluations = 0
        while not strategy.stop() and evaluations < self.max_evals:
            candidates = strategy.ask()
            costs = []
            for candidate in candidates:
                # Seed by evaluation index so a repeat of this search replays
                # the same simulations. A fixed seed would instead let the
                # optimizer overfit one draw of the scenario randomness.
                fitness = objective(candidate, seed=self.seed + evaluations)
                evaluations += 1
                costs.append(-fitness)
                if objective.falsification_found:
                    break

            strategy.tell(candidates[:len(costs)], costs)

            if objective.falsification_found:
                logger.info("Falsification found after %d evaluations", evaluations)
                break

        return self._result(objective, evaluations, "cma-es",
                            converged=bool(strategy.stop()))

    def strategy_bounds(self):
        """Box bounds as arrays, so a proposal cannot leave the declared space."""
        return self.space.bounds

    @staticmethod
    def _result(objective, evaluations, optimizer_used, converged) -> SearchResult:
        best = objective.best_record
        falsifier = objective.falsification_record
        return SearchResult(
            best_params=best.params if best else {},
            best_fitness=best.fitness if best else 0.0,
            n_evals=evaluations,
            falsification_found=objective.falsification_found,
            falsification_params=falsifier.params if falsifier else None,
            all_evaluations=objective.history,
            optimizer_used=optimizer_used,
            converged=converged,
        )


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
        Uniform sampling over the space.

        The baseline that makes the CMA-ES number mean something: an
        adversarial search that finds no more failures than random sampling is
        not adversarial, it is just slower.
        """
        rng = np.random.default_rng(self.seed)

        evaluations = 0
        for index in range(self.n_samples):
            objective(self.space.random_point(rng), seed=self.seed + index)
            evaluations += 1
            if objective.falsification_found:
                logger.info("Falsification found after %d samples", evaluations)
                break

        return CMAESOptimizer._result(
            objective, evaluations, "random", converged=True,
        )
