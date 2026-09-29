"""
ORION importance sampling for scenario parameterization (Phase 4.3).

Uniform sampling spends runs evenly across the declared parameter ranges. At
suite scale that is mostly waste: a scenario whose failures live in a narrow
corner of its space will spend 95 of 100 runs confirming the safe region it
already knows about. Importance sampling biases the draw toward a named region
so the runs land where the failures are.

The bias has to be paid back. A batch that oversamples a failure region reports
a collision rate that is not the scenario's collision rate, and a number like
that is worse than no number -- it looks exactly like the honest one. Every
instance therefore carries the weight that converts it back, and the aggregator
uses the weighted estimator whenever the weights are not all 1. A weighted
batch also reports a smaller effective sample size than its run count, because
that is what it has: concentrating draws in one region buys resolution there
and pays for it in the overall estimate.

Region naming matches what `analysis.failure_clustering._flatten_parameters`
emits -- `ego_velocity`, `ego_x`, `ego_y`, `<npc_id>.initial_x`,
`<npc_id>.initial_velocity`, `<npc_id>.<behaviour_param>` -- so a
`FaultCondition` found by 2.2 or an adversarial result from 2.3 can be handed
straight back in without a translation layer.

Bounds are intersected with the scenario's declared ranges and never widen
them. A suite may concentrate runs inside what the scenario author sanctioned;
it may not score a model on parameters the author never wrote down.

Usage:

    region = ImportanceRegion(
        bounds={"lead_vehicle.initial_x": (25.0, 32.0)},
        fraction=0.6,           # 60% of runs drawn from inside the region
    )
    result = runner.run_batch(path, model, num_runs=100, importance=region)
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ImportanceRegion:
    """A sub-region of a scenario's parameter space to oversample.

    Attributes:
        bounds:   Parameter name -> (low, high). Names not present in the
                  scenario's parameterization block are ignored; a scenario
                  cannot be biased along an axis it does not vary.
        fraction: Probability that a given run is drawn from inside the region.
                  Must be in (0, 1) -- 0 disables the region and 1 would make
                  the un-sampled remainder unreachable, so neither is a
                  sampling scheme and both are refused.
    """

    bounds: dict[str, tuple[float, float]] = field(default_factory=dict)
    fraction: float = 0.5

    def __post_init__(self) -> None:
        if not 0.0 < self.fraction < 1.0:
            raise ValueError(
                f"fraction must be strictly between 0 and 1, got {self.fraction}. "
                "0 means no oversampling (pass importance=None); 1 makes the "
                "region complement unreachable and the weights undefined."
            )
        for name, bound in self.bounds.items():
            low, high = bound
            if low > high:
                raise ValueError(f"bounds[{name!r}] is inverted: {low} > {high}")

    def clip(self, name: str, low: float, high: float) -> tuple[float, float]:
        """The declared range narrowed to the region, or unchanged if disjoint.

        A region bound that does not overlap the declared range is dropped
        rather than honoured: honouring it would sample outside the scenario.
        """
        bound = self.bounds.get(name)
        if bound is None:
            return low, high
        lo = max(low, bound[0])
        hi = min(high, bound[1])
        if lo > hi:
            return low, high
        return lo, hi

    def volume(self, declared: dict[str, tuple[float, float]]) -> float:
        """Fraction of the declared space the region occupies.

        `declared` maps parameter name -> (low, high) as the scenario declares
        it, for every range the parameterizer actually sampled. Dimensions the
        region does not constrain contribute a factor of 1. A zero-width
        declared range also contributes 1 -- it is a constant in disguise and
        carries no probability mass either way.
        """
        vol = 1.0
        for name, (low, high) in declared.items():
            bound = self.bounds.get(name)
            if bound is None or high <= low:
                continue
            lo = max(low, bound[0])
            hi = min(high, bound[1])
            if lo > hi:  # disjoint; clip() left the range alone
                continue
            vol *= (hi - lo) / (high - low)
        return vol

    def contains(
        self,
        drawn: dict[str, float],
        declared: dict[str, tuple[float, float]],
    ) -> bool:
        """Whether a sampled point lies inside the region.

        Membership, not which branch produced it. The proposal is a mixture --
        with probability `fraction` it draws from the region and otherwise from
        the whole declared space -- and the "otherwise" branch can perfectly
        well land inside the region too. The likelihood ratio depends on where
        the point is, so weighting by the branch instead of by membership
        systematically under-counts the region and biases every rate the batch
        reports. Getting this wrong is silent: the estimate stays plausible and
        is simply wrong, which is the failure mode this whole module exists to
        avoid.

        Dimensions the region constrains but the scenario does not vary are
        ignored, matching `volume`.
        """
        for name, (low, high) in declared.items():
            if name not in self.bounds:
                continue
            lo, hi = self.clip(name, low, high)
            value = drawn.get(name)
            if value is None:
                continue
            if not (lo <= value <= hi):
                return False
        return True

    def weight(self, in_region: bool, volume: float) -> float:
        """Likelihood ratio p/q for one draw.

        `in_region` is membership of the sampled point -- see `contains`.

        The target p is the uniform distribution over the declared space. The
        proposal q draws from the region with probability `fraction` and from
        the whole space otherwise, so a point inside the region has proposal
        density `fraction/volume + (1 - fraction)` and one outside has
        `1 - fraction`. Both are relative to the uniform density, which is why
        p is simply 1.

        A degenerate region (volume 0, e.g. a bound pinned to a single value)
        cannot be weighted back -- the proposal has infinite density there and
        the estimator would be undefined -- so the draw is reported at weight 0
        and contributes nothing to the population estimate. It still ran, and
        its failure is still a real failure; it just cannot speak for the rest
        of the space.
        """
        if in_region:
            if volume <= 0.0:
                return 0.0
            return 1.0 / (self.fraction / volume + (1.0 - self.fraction))
        return 1.0 / (1.0 - self.fraction)
