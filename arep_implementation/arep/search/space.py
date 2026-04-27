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

    def _build(self) -> None:
        """
        Walk the scenario's parameterization block and extract all {min, max} pairs.

        TODO [P2]: Recursively walk ScenarioDefinition.parameterization dict.
        TODO [P2]: For each leaf that is a dict with "min" and "max" keys,
                   create a SearchDimension with dotted path as name.
        TODO [P2]: Append to self._dimensions.
        """
        raise NotImplementedError("SearchSpace._build not yet implemented [P2]")

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
        Convert an optimizer vector x to a parameterizer-compatible override dict.

        The override dict has the same nested structure as the scenario's
        parameterization block, with each {min, max} replaced by the
        corresponding value from x.

        TODO [P2]: Reconstruct nested dict from self._dimensions and x.
        """
        raise NotImplementedError("SearchSpace.to_params_dict not yet implemented [P2]")

    def midpoint(self) -> np.ndarray:
        """Return the midpoint of the search space (good CMA-ES starting point)."""
        return np.array([(d.low + d.high) / 2.0 for d in self._dimensions])

    def random_point(self, rng: np.random.Generator) -> np.ndarray:
        """Sample a uniformly random point in the search space."""
        lows, highs = self.bounds
        return rng.uniform(lows, highs)

    def __repr__(self) -> str:
        return f"SearchSpace({self.n_dims} dims: {[d.name for d in self._dimensions]})"
