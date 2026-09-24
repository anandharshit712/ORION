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


# Two failures whose parameters differ by less than this fraction of each
# dimension's declared range are treated as the same failure.
#
# Needed because CMA-ES converges: once it finds a failing region it samples
# that region repeatedly, so a search that keeps going returns forty variations
# of one bug. Reporting them as forty findings would be worse than reporting
# one, because it buries the *other* failure modes in noise.
DISTINCT_FAILURE_TOLERANCE = 0.10

# Cap on how many counter-examples are returned. A customer reproduces the worst
# few; the rest is what `failure_rate` and `analysis/failure_clustering.py` are
# for.
MAX_REPORTED_FAILURES = 10

# CMA-ES needs roughly 10 evaluations per search dimension before it beats
# random sampling — it spends the early evaluations learning the shape of the
# space. Measured on LON-003 (8 dimensions): at 50 evaluations random search
# won (13.5 vs 1.6); at 100 CMA-ES won (14.9 vs 13.5) and found a *worse*
# failure. Verified 3/3 across scenarios, models and seeds.
#
# Scaled per scenario rather than a flat floor, because the library runs from 1
# to 11 dimensions: a flat 150 would overcharge a one-dimensional scenario
# fifteen-fold for a search that converged at evaluation ten.
EVALS_PER_DIMENSION = 10

# Even a one-dimensional space needs enough draws for the result to mean
# anything; 10 evaluations is a sampling accident, not a search.
MIN_EVALS = 30


def recommended_evals(n_dims: int) -> int:
    """Smallest evaluation budget at which a search is worth trusting.

    Below this CMA-ES is still exploring, so it underperforms random sampling
    and the result understates how bad the model is — which is the dangerous
    direction for a safety tool to be wrong in.
    """
    return max(MIN_EVALS, EVALS_PER_DIMENSION * max(n_dims, 1))


def distinct_failures(
    records, space=None, tolerance: float = DISTINCT_FAILURE_TOLERANCE
):
    """Collapse near-identical failures, keeping the worst of each group.

    Records are expected worst-first, so the representative kept for each group
    is the most severe example of that failure mode — the one to reproduce.

    Closeness is measured as a fraction of each dimension's **declared range**,
    not of its value. Those are very different tests: 10% of a velocity of 25
    is 2.5 m/s, but if the declared range is [24, 26] then 2.5 spans the whole
    space and every sample collapses into one group. Passing `space` is what
    makes the comparison meaningful; without it this falls back to a
    relative-to-value test, which over eight dimensions collapses almost
    nothing.

    Deliberately a greedy pass rather than real clustering: it runs on a few
    hundred records at most, and `analysis/failure_clustering.py` already exists
    for the case where a customer wants fault *conditions* rather than a
    de-duplicated list.
    """
    ranges = _dimension_ranges(space) if space is not None else None
    kept: list = []
    for record in records:
        if not any(_near(record.params, k.params, tolerance, ranges) for k in kept):
            kept.append(record)
    return kept


def _dimension_ranges(space) -> dict:
    """Declared width of each search dimension, by flattened name."""
    return {
        dim.name: max(float(dim.high) - float(dim.low), 1e-9)
        for dim in space.dimensions
    }


def _near(a: dict, b: dict, tolerance: float, ranges=None) -> bool:
    """Whether two parameter sets represent the same failure.

    A key present in one set and not the other makes them different: they are
    not comparable, so they are not the same finding.
    """
    flat_a, flat_b = _flatten(a), _flatten(b)
    if flat_a.keys() != flat_b.keys():
        return False

    for key, value_a in flat_a.items():
        value_b = flat_b[key]
        if ranges is not None and key in ranges:
            scale = ranges[key]
        else:
            scale = max(abs(value_a), abs(value_b), 1e-9)
        if abs(value_a - value_b) / scale > tolerance:
            return False
    return True


def _flatten(params: dict, prefix: str = "") -> dict:
    flat: dict = {}
    for key, value in params.items():
        name = f"{prefix}{key}"
        if isinstance(value, dict):
            flat.update(_flatten(value, prefix=f"{name}."))
        elif isinstance(value, (int, float)) and not isinstance(value, bool):
            flat[name] = float(value)
    return flat


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

    # Every distinct failure found, worst first, when the search was told to
    # keep going past the first one. `falsification_params` stays the first
    # failure so existing callers are unaffected.
    #
    # One counter-example proves the model can fail. Several show how many
    # different ways it fails, and two failures from opposite corners of the
    # parameter space are two bugs rather than one.
    falsifications: List[Dict[str, Any]] = field(default_factory=list)
    falsification_count: int = 0
    distinct_failure_count: int = 0
    # Failures as a fraction of evaluations. When most of the space fails, *that*
    # is the finding — a list of 81 settings buries it.
    failure_rate: float = 0.0


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
        stop_on_first_falsification: bool = True,
    ):
        self.space = space
        self.sigma0 = sigma0
        self.popsize = popsize
        self.max_evals = max_evals
        self.seed = seed
        # Stopping at the first collision returns one counter-example for the
        # least compute. Continuing spends the whole budget and returns every
        # failure mode it can find, which is what a customer fixing the model
        # actually wants - and makes the cost predictable, since the search then
        # always uses exactly max_evals evaluations.
        self.stop_on_first_falsification = stop_on_first_falsification

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
        except ImportError as exc:  # pragma: no cover - depends on extras
            raise ImportError(
                "Adversarial search needs the cma package: "
                "pip install 'arep[search]'"
            ) from exc

        if self.space.n_dims == 0:
            # Nothing to search. Returning an empty result beats running 200
            # identical simulations and reporting the last one.
            return SearchResult(
                best_params={},
                best_fitness=0.0,
                n_evals=0,
                falsification_found=False,
                falsification_params=None,
                optimizer_used="cma-es",
                converged=True,
            )

        if self.space.n_dims == 1:
            # CMA-ES needs at least two dimensions to build a covariance.
            # Falling back is better than raising: a one-parameter scenario is
            # a legitimate thing to search, just not with this algorithm.
            logger.info("Single-dimension space — using random search instead")
            fallback = RandomSearchOptimizer(
                self.space,
                n_samples=self.max_evals,
                seed=self.seed,
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
                "seed": self.seed + 1,  # cma rejects seed=0 as "use entropy"
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
                if objective.falsification_found and self.stop_on_first_falsification:
                    break
                if evaluations >= self.max_evals:
                    break

            if objective.falsification_found and self.stop_on_first_falsification:
                # Stop without telling CMA-ES about this generation. The inner
                # loop broke early, so `costs` is shorter than the population
                # cma proposed, and cma rejects a truncated one outright
                # ("population size 1 is too small"). Since the search ends here
                # anyway there is nothing to update the distribution for, and
                # the counter-example is already recorded on the objective.
                #
                # This fired exactly on success, which is the worst place for it:
                # the tests exercised CMA-ES with a model that never collides,
                # so the crash only appeared once the search actually worked.
                logger.info("Falsification found after %d evaluations", evaluations)
                break

            if len(costs) == len(candidates):
                strategy.tell(candidates, costs)

        return self._result(
            objective,
            evaluations,
            "cma-es",
            converged=bool(strategy.stop()),
            space=self.space,
        )

    def strategy_bounds(self):
        """Box bounds as arrays, so a proposal cannot leave the declared space."""
        return self.space.bounds

    @staticmethod
    def _result(
        objective, evaluations, optimizer_used, converged, space=None
    ) -> SearchResult:
        best = objective.best_record
        falsifier = objective.falsification_record
        failures = objective.falsification_records
        distinct = distinct_failures(failures, space=space)
        return SearchResult(
            best_params=best.params if best else {},
            best_fitness=best.fitness if best else 0.0,
            n_evals=evaluations,
            falsification_found=objective.falsification_found,
            falsification_params=falsifier.params if falsifier else None,
            all_evaluations=objective.history,
            optimizer_used=optimizer_used,
            converged=converged,
            falsifications=[
                {"params": r.params, "seed": r.seed, "fitness": r.fitness}
                for r in distinct[:MAX_REPORTED_FAILURES]
            ],
            falsification_count=len(failures),
            distinct_failure_count=len(distinct),
            failure_rate=(len(failures) / evaluations) if evaluations else 0.0,
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
        stop_on_first_falsification: bool = True,
    ):
        self.space = space
        self.n_samples = n_samples
        self.seed = seed
        self.stop_on_first_falsification = stop_on_first_falsification

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
            if objective.falsification_found and self.stop_on_first_falsification:
                logger.info("Falsification found after %d samples", evaluations)
                break

        return CMAESOptimizer._result(
            objective,
            evaluations,
            "random",
            converged=True,
            space=self.space,
        )
