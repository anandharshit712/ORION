"""
ORION Scenario Validator.

Validates parsed ScenarioDefinition objects for correctness:
  - Required fields present
  - Value ranges valid
  - Unique object IDs
  - Event ordering
  - Physical constraint consistency
"""

from __future__ import annotations

from typing import List

from arep.scenario.schema import ScenarioDefinition


class ScenarioValidator:
    """Validate ScenarioDefinition objects."""

    def validate(self, scenario: ScenarioDefinition) -> List[str]:
        """
        Run all validation checks.

        Args:
            scenario: Parsed scenario.

        Returns:
            List of error strings (empty = valid).
        """
        errors: List[str] = []

        errors.extend(self._check_metadata(scenario))
        errors.extend(self._check_ego(scenario))
        errors.extend(self._check_road(scenario))
        errors.extend(self._check_traffic_ids(scenario))
        errors.extend(self._check_events(scenario))
        errors.extend(self._check_constraints(scenario))

        return errors

    @staticmethod
    def _check_metadata(s: ScenarioDefinition) -> List[str]:
        errors = []
        if not s.name or not s.name.strip():
            errors.append("Scenario name is required")
        if s.duration <= 0:
            errors.append(f"Duration must be positive, got {s.duration}")
        return errors

    @staticmethod
    def _check_ego(s: ScenarioDefinition) -> List[str]:
        errors = []
        if s.ego_initial.velocity < 0:
            errors.append(f"Ego initial velocity cannot be negative: {s.ego_initial.velocity}")
        return errors

    @staticmethod
    def _check_road(s: ScenarioDefinition) -> List[str]:
        errors = []
        if s.road.lanes < 1:
            errors.append(f"Road must have at least 1 lane, got {s.road.lanes}")
        if s.road.lane_width <= 0:
            errors.append(f"Lane width must be positive, got {s.road.lane_width}")
        if s.road.speed_limit <= 0:
            errors.append(f"Speed limit must be positive, got {s.road.speed_limit}")
        return errors

    @staticmethod
    def _check_traffic_ids(s: ScenarioDefinition) -> List[str]:
        errors = []
        ids = [obj.id for obj in s.traffic_objects]
        seen = set()
        for obj_id in ids:
            if not obj_id:
                errors.append("Traffic object has empty ID")
            elif obj_id in seen:
                errors.append(f"Duplicate traffic object ID: {obj_id!r}")
            seen.add(obj_id)
        return errors

    @staticmethod
    def _check_events(s: ScenarioDefinition) -> List[str]:
        errors = []
        for i, event in enumerate(s.events):
            if event.trigger_time < 0:
                errors.append(
                    f"Event {i} trigger_time cannot be negative: {event.trigger_time}"
                )
            if event.trigger_time > s.duration:
                errors.append(
                    f"Event {i} trigger_time ({event.trigger_time}) "
                    f"exceeds scenario duration ({s.duration})"
                )
        return errors

    @staticmethod
    def _check_constraints(s: ScenarioDefinition) -> List[str]:
        errors = []
        c = s.ego_constraints
        if c.max_velocity <= 0:
            errors.append(f"max_velocity must be positive: {c.max_velocity}")
        if c.max_acceleration <= 0:
            errors.append(f"max_acceleration must be positive: {c.max_acceleration}")
        if c.max_deceleration <= 0:
            errors.append(f"max_deceleration must be positive: {c.max_deceleration}")
        if c.max_steering <= 0:
            errors.append(f"max_steering must be positive: {c.max_steering}")
        return errors
