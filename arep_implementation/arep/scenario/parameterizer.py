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
"""

from __future__ import annotations

from typing import Any

from arep.core.random_manager import RandomManager
from arep.scenario.schema import ScenarioDefinition


def _sample(spec: Any, gen) -> float:
    """Return spec directly if scalar, or sample uniform(min, max) if range dict."""
    if isinstance(spec, dict) and "min" in spec and "max" in spec:
        return float(gen.uniform(spec["min"], spec["max"]))
    return float(spec)


class ScenarioParameterizer:
    """
    Apply the scenario's parameterization spec to produce a concrete instance.

    Mutates the ScenarioDefinition in-place; the caller should pass a copy
    if the original template must be preserved.

    Usage:
        param = ScenarioParameterizer()
        param.apply(scenario, rng)   # scenario is now fully instantiated
    """

    def apply(self, scenario: ScenarioDefinition, rng: RandomManager) -> None:
        """
        Sample all parameterization ranges and write concrete values into scenario.

        Args:
            scenario: Parsed scenario (mutated in-place).
            rng:      Seeded random manager.
        """
        spec = scenario.parameterization
        if not spec:
            return

        gen = rng.get("scenario")

        # ── Ego vehicle ────────────────────────────────────────────────
        if "ego_velocity" in spec:
            scenario.ego_initial.velocity = _sample(spec["ego_velocity"], gen)

        if "ego_x_jitter" in spec:
            jitter = _sample(spec["ego_x_jitter"], gen)
            scenario.ego_initial.x = scenario.ego_initial.x + jitter

        if "ego_x" in spec:
            scenario.ego_initial.x = _sample(spec["ego_x"], gen)

        if "ego_y" in spec:
            scenario.ego_initial.y = _sample(spec["ego_y"], gen)

        # ── NPC overrides ──────────────────────────────────────────────
        npc_overrides = spec.get("npc_overrides", {})
        if not npc_overrides:
            return

        for obj_def in scenario.traffic_objects:
            override = npc_overrides.get(obj_def.id)
            if not override:
                continue

            if "initial_velocity" in override:
                obj_def.initial.velocity = _sample(override["initial_velocity"], gen)

            if "initial_x" in override:
                obj_def.initial.x = _sample(override["initial_x"], gen)

            if "initial_y" in override:
                obj_def.initial.y = _sample(override["initial_y"], gen)

            # Apply parameter-level overrides (e.g., trigger_value, initial_decel)
            param_overrides = override.get("parameters", {})
            if param_overrides and hasattr(obj_def.behavior, "parameters"):
                for key, value_spec in param_overrides.items():
                    obj_def.behavior.parameters[key] = _sample(value_spec, gen)
