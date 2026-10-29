"""
ORION Scenario Parameterizer.

Implements L2 of the 4-layer architecture: takes a parsed ScenarioDefinition
(the template) and applies randomised concrete values sampled from the
parameterization ranges defined in the YAML, producing a unique ScenarioInstance
per run while remaining fully reproducible given the same seed.

YAML parameterization block format
-----------------------------------
parameterization:
  ego_velocity:   {min: 16.67, max: 27.78}   # overrides ego initial velocity (m/s)
  ego_x_jitter:   {min: -5.0,  max: 5.0}     # ± shift on ego initial x (m)

  npc_overrides:
    <npc_id>:
      initial_velocity:  {min: 11.11, max: 19.44}
      initial_x:         {min: 40.0,  max: 70.0}
      initial_y:         {min: -2.0,  max: -1.5}    # optional
      parameters:                                    # overrides behavior.parameters
        trigger_value:      {min: 2.5, max: 5.0}
        post_acceleration:  {min: -9.81, max: -5.0}
        initial_decel:      {min: -6.0, max: -3.5}
        final_decel:        {min: -9.81, max: -7.0}
        hesitation_prob:    {min: 0.2, max: 0.6}
        hesitation_duration:{min: 0.2, max: 0.8}
        lateral_speed:      {min: 1.0, max: 2.5}
        walk_speed:         {min: 0.7, max: 1.4}

Any value can be either a scalar (kept as-is) or a {min, max} dict (sampled).

Sampling is uniform by default. Passing an `ImportanceRegion` biases the draw
toward a sub-region of the declared space and returns the weight that converts
the result back to a population estimate -- see `arep/scenario/importance.py`.
"""

from __future__ import annotations

from typing import Any

from arep.core.random_manager import RandomManager
from arep.scenario.importance import ImportanceRegion
from arep.scenario.schema import ScenarioDefinition


def _range_of(spec: Any) -> tuple[float, float] | None:
    """(min, max) if spec is a range dict, else None."""
    if isinstance(spec, dict) and "min" in spec and "max" in spec:
        return float(spec["min"]), float(spec["max"])
    return None


class ScenarioParameterizer:
    """
    Apply the scenario's parameterization spec to produce a concrete instance.

    Mutates the ScenarioDefinition in-place; the caller should pass a copy
    if the original template must be preserved.

    Usage:
        param = ScenarioParameterizer()
        param.apply(scenario, rng)   # scenario is now fully instantiated
    """

    def apply(
        self,
        scenario: ScenarioDefinition,
        rng: RandomManager,
        region: ImportanceRegion | None = None,
    ) -> float:
        """
        Sample all parameterization ranges and write concrete values into scenario.

        Args:
            scenario: Parsed scenario (mutated in-place).
            rng:      Seeded random manager.
            region:   Optional sub-region to oversample.

        Returns:
            The importance weight of this instance: 1.0 for an ordinary uniform
            draw, and the likelihood ratio when `region` is given. A caller
            averaging over a batch must weight by it or the reported rates
            describe the biased draw rather than the scenario.

        Determinism: a given seed maps to exactly one instance per
        (scenario, region). The in/out coin is drawn only when a region is
        supplied, so an ordinary uniform batch consumes the same RNG stream it
        always has -- every stored score, baseline and frame hash is keyed to
        that sequence, and an unconditional extra draw would silently move all
        of them. A biased batch is a different batch and gets its own stream.
        """
        spec = scenario.parameterization
        if not spec:
            return 1.0

        gen = rng.get("scenario")

        # Decided before anything is sampled, so the coin sits at a fixed
        # position in the stream and the draw below it does not depend on
        # which branch was taken.
        in_region = (
            region is not None and float(gen.uniform(0.0, 1.0)) < region.fraction
        )

        # Declared ranges and the values actually drawn, by the names
        # failure_clustering._flatten_parameters uses, so a FaultCondition can
        # be fed straight back in.
        declared: dict[str, tuple[float, float]] = {}
        drawn: dict[str, float] = {}

        def sample(name: str, value_spec: Any) -> float:
            """Draw one value, narrowed to the region when this run is inside it."""
            bounds = _range_of(value_spec)
            if bounds is None:
                return float(value_spec)
            low, high = bounds
            declared[name] = (low, high)
            if in_region and region is not None:
                low, high = region.clip(name, low, high)
            value = float(gen.uniform(low, high))
            drawn[name] = value
            return value

        # ── Ego vehicle ────────────────────────────────────────────────
        if "ego_velocity" in spec:
            scenario.ego_initial.velocity = sample("ego_velocity", spec["ego_velocity"])

        if "ego_x_jitter" in spec:
            # The region names the resulting x, not the jitter, because that is
            # what the clusterer reports. Shift the bound into jitter space.
            base_x = scenario.ego_initial.x
            jitter_spec = spec["ego_x_jitter"]
            jitter_region = None
            if region is not None and "ego_x" in region.bounds:
                lo, hi = region.bounds["ego_x"]
                jitter_region = ImportanceRegion(
                    bounds={"ego_x_jitter": (lo - base_x, hi - base_x)},
                    fraction=region.fraction,
                )
            bounds = _range_of(jitter_spec)
            if bounds is None:
                jitter = float(jitter_spec)
            else:
                low, high = bounds
                declared["ego_x"] = (base_x + low, base_x + high)
                if in_region and jitter_region is not None:
                    low, high = jitter_region.clip("ego_x_jitter", low, high)
                jitter = float(gen.uniform(low, high))
                drawn["ego_x"] = base_x + jitter
            scenario.ego_initial.x = base_x + jitter

        if "ego_x" in spec:
            scenario.ego_initial.x = sample("ego_x", spec["ego_x"])

        if "ego_y" in spec:
            scenario.ego_initial.y = sample("ego_y", spec["ego_y"])

        # ── NPC overrides ──────────────────────────────────────────────
        npc_overrides = spec.get("npc_overrides", {})

        for obj_def in scenario.traffic_objects:
            override = npc_overrides.get(obj_def.id)
            if not override:
                continue

            if "initial_velocity" in override:
                obj_def.initial.velocity = sample(
                    f"{obj_def.id}.initial_velocity", override["initial_velocity"]
                )

            if "initial_x" in override:
                obj_def.initial.x = sample(
                    f"{obj_def.id}.initial_x", override["initial_x"]
                )

            if "initial_y" in override:
                obj_def.initial.y = sample(
                    f"{obj_def.id}.initial_y", override["initial_y"]
                )

            # Apply parameter-level overrides (e.g., trigger_value, initial_decel)
            param_overrides = override.get("parameters", {})
            if param_overrides and hasattr(obj_def.behavior, "parameters"):
                for key, value_spec in param_overrides.items():
                    obj_def.behavior.parameters[key] = sample(
                        f"{obj_def.id}.{key}", value_spec
                    )

        if region is None:
            return 1.0
        # Membership of the point, not the branch that produced it: the
        # "outside" branch draws from the whole space and can land inside the
        # region. See ImportanceRegion.contains.
        return region.weight(region.contains(drawn, declared), region.volume(declared))
