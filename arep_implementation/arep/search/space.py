"""
ORION Adversarial Search — Search Space.  [Phase 2]

Extracts the bounded search space from a scenario's parameterization block.
Each {min, max} range in the YAML becomes one SearchDimension.

The optimizer works with a flat numpy vector x ∈ R^n where each element
corresponds to one SearchDimension. SearchSpace handles the conversion
between the optimizer's vector and the parameterizer-compatible override dict.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List

import numpy as np

from arep.scenario.schema import ScenarioDefinition
from arep.utils.logging_config import get_logger

logger = get_logger("search.space")


@dataclass
class SearchDimension:
    """One bounded dimension in the search space."""
    name: str             # e.g. "lead_vehicle.initial_x"
    low: float            # minimum value (inclusive)
    high: float           # maximum value (inclusive)
    unit: str = ""        # e.g. "m", "m/s", "s" — for display only

    @property
    def range(self) -> float:
        return self.high - self.low

    def normalise(self, value: float) -> float:
        """Map value from [low, high] to [0, 1]."""
        if self.range < 1e-12:
            return 0.0
        return (value - self.low) / self.range

    def denormalise(self, normalised: float) -> float:
        """Map value from [0, 1] to [low, high]."""
        return self.low + normalised * self.range


class SearchSpace:
    """
    Extracts and manages the parameterisation search space for a scenario.

    Reads all {min, max} pairs from the scenario's parameterization block
    and exposes them as a flat vector space for CMA-ES optimisation.
    """

    def __init__(self, scenario: ScenarioDefinition):
        self._scenario = scenario
        self._dimensions: List[SearchDimension] = []
        self._build()

    # Dimensions are ordered by dotted path so the vector layout is stable.
    # An optimizer resumed from a saved state would otherwise apply x[0] to a
    # different parameter than the run that produced it.
    def _build(self) -> None:
        """Extract every {min, max} pair from the parameterization block."""
        self._dimensions = []
        for path, leaf in sorted(_walk(self._scenario.parameterization)):
            self._dimensions.append(SearchDimension(
                name=path,
                low=float(leaf["min"]),
                high=float(leaf["max"]),
                unit=str(leaf.get("unit", "")),
            ))
        logger.debug("Search space: %d dimensions", len(self._dimensions))

    @property
    def dimensions(self) -> List[SearchDimension]:
        return list(self._dimensions)

    @property
    def n_dims(self) -> int:
        return len(self._dimensions)

    @property
    def bounds(self) -> tuple[np.ndarray, np.ndarray]:
        """Return (lower_bounds, upper_bounds) arrays for the optimizer."""
        lows = np.array([d.low for d in self._dimensions])
        highs = np.array([d.high for d in self._dimensions])
        return lows, highs

    def to_params_dict(self, x: np.ndarray) -> Dict[str, Any]:
        """
        Convert an optimizer vector into a parameterization block.

        Each {min, max} becomes a concrete number, keeping the nested shape the
        parameterizer already understands — so the search feeds the ordinary
        run path rather than a second one that could drift away from it.

        Values are clipped to their bounds. CMA-ES proposes points outside the
        box routinely; letting one through would run a scenario the customer
        never declared and score the model on it.
        """
        if len(x) != len(self._dimensions):
            raise ValueError(
                f"Expected {len(self._dimensions)} values, got {len(x)}"
            )

        params: Dict[str, Any] = {}
        for value, dimension in zip(x, self._dimensions):
            clipped = float(min(max(float(value), dimension.low), dimension.high))
            _set_nested(params, dimension.name.split("."), clipped)
        return params

    def midpoint(self) -> np.ndarray:
        """Return the midpoint of the search space (good CMA-ES starting point)."""
        return np.array([(d.low + d.high) / 2.0 for d in self._dimensions])

    def random_point(self, rng: np.random.Generator) -> np.ndarray:
        """Sample a uniformly random point in the search space."""
        lows, highs = self.bounds
        return rng.uniform(lows, highs)

    def __repr__(self) -> str:
        return f"SearchSpace({self.n_dims} dims: {[d.name for d in self._dimensions]})"


# ── Helpers ──────────────────────────────────────────────────────────────

def _walk(node, prefix: str = ""):
    """Yield (dotted path, {min, max} dict) for every range in the block.

    A leaf is a dict carrying both "min" and "max"; anything else is a nesting
    level. That is the same shape the parameterizer reads, so the search space
    and the runtime cannot disagree about what is tunable.
    """
    if not isinstance(node, dict):
        return
    if "min" in node and "max" in node:
        yield prefix, node
        return
    for key, value in node.items():
        child = f"{prefix}.{key}" if prefix else str(key)
        yield from _walk(value, child)


def _set_nested(target: Dict[str, Any], path: List[str], value: float) -> None:
    for key in path[:-1]:
        target = target.setdefault(key, {})
    target[path[-1]] = value
