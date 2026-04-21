"""
ORION Scenario YAML Parser.

Parses YAML scenario files into ScenarioDefinition objects.
Includes validation and SHA256 hashing for versioning.
"""

from __future__ import annotations

from pathlib import Path
from typing import Tuple, Union

import yaml

from arep.scenario.schema import (
    ScenarioDefinition,
    VehicleInitialCondition,
    VehicleConstraints,
    RoadConfiguration,
    WeatherConfiguration,
    TrafficObjectDefinition,
    TrafficObjectBehavior,
    ScenarioEvent,
    ScenarioTermination,
)
from arep.scenario.validator import ScenarioValidator
from arep.utils.exceptions import ScenarioParseError, ScenarioValidationError
from arep.utils.hashing import hash_string


class ScenarioParser:
    """
    Parse scenario YAML files into ScenarioDefinition objects.

    Includes schema validation and SHA256 content hashing.
    """

    def __init__(self) -> None:
        self.validator = ScenarioValidator()

    def parse_file(
        self,
        filepath: Union[str, Path],
    ) -> Tuple[ScenarioDefinition, str]:
        """
        Parse scenario from a YAML file.

        Args:
            filepath: Path to YAML file.

        Returns:
            (ScenarioDefinition, content_hash) tuple.

        Raises:
            ScenarioParseError: If YAML parsing fails.
            ScenarioValidationError: If validation fails.
        """
        filepath = Path(filepath)

        if not filepath.exists():
            raise ScenarioParseError(f"File not found: {filepath}")

        try:
            yaml_content = filepath.read_text(encoding="utf-8")
            data = yaml.safe_load(yaml_content)
        except yaml.YAMLError as e:
            raise ScenarioParseError(f"YAML parsing error: {e}")

        scenario = self._parse_dict(data)
        errors = self.validator.validate(scenario)
        if errors:
            raise ScenarioValidationError(
                f"Validation failed:\n" + "\n".join(f"  - {e}" for e in errors)
            )

        return scenario, hash_string(yaml_content)

    def parse_string(
        self,
        yaml_string: str,
    ) -> Tuple[ScenarioDefinition, str]:
        """
        Parse scenario from a YAML string.

        Args:
            yaml_string: YAML content.

        Returns:
            (ScenarioDefinition, content_hash) tuple.
        """
        try:
            data = yaml.safe_load(yaml_string)
        except yaml.YAMLError as e:
            raise ScenarioParseError(f"YAML parsing error: {e}")

        scenario = self._parse_dict(data)
        errors = self.validator.validate(scenario)
        if errors:
            raise ScenarioValidationError(
                f"Validation failed:\n" + "\n".join(f"  - {e}" for e in errors)
            )

        return scenario, hash_string(yaml_string)

    # ── Private parsing ──────────────────────────────────────────────

    def _parse_dict(self, data: dict) -> ScenarioDefinition:
        """Parse a raw YAML dictionary into a ScenarioDefinition."""
        try:
            meta = data["scenario"]
            ego_data = data["ego"]
            env_data = data["environment"]

            ego_initial = VehicleInitialCondition(
                x=float(ego_data["initial"]["x"]),
                y=float(ego_data["initial"]["y"]),
                heading=float(ego_data["initial"]["heading"]),
                velocity=float(ego_data["initial"]["velocity"]),
            )

            ego_constraints = VehicleConstraints(
                max_velocity=float(ego_data["constraints"]["max_velocity"]),
                max_acceleration=float(ego_data["constraints"]["max_acceleration"]),
                max_deceleration=float(ego_data["constraints"]["max_deceleration"]),
                max_steering=float(ego_data["constraints"]["max_steering"]),
            )

            road = RoadConfiguration(
                road_type=env_data["road"]["type"],
                lanes=int(env_data["road"]["lanes"]),
                lane_width=float(env_data["road"]["lane_width"]),
                speed_limit=float(env_data["road"]["speed_limit"]),
            )

            weather = WeatherConfiguration(
                condition=env_data["weather"]["condition"],
                visibility=float(env_data["weather"]["visibility"]),
            )

            # Traffic objects
            traffic_objects = []
            for obj_data in data.get("traffic", []):
                obj_initial = VehicleInitialCondition(
                    x=float(obj_data["initial"]["x"]),
                    y=float(obj_data["initial"]["y"]),
                    heading=float(obj_data["initial"]["heading"]),
                    velocity=float(obj_data["initial"]["velocity"]),
                )
                obj_behavior = TrafficObjectBehavior(
                    type=obj_data["behavior"]["type"],
                    parameters=obj_data["behavior"].get("parameters", {}),
                )
                traffic_objects.append(TrafficObjectDefinition(
                    id=obj_data["id"],
                    type=obj_data["type"],
                    initial=obj_initial,
                    behavior=obj_behavior,
                ))

            # Events
            events = []
            for ev_data in data.get("events", []):
                events.append(ScenarioEvent(
                    type=ev_data["type"],
                    trigger_time=float(ev_data["trigger_time"]),
                    parameters=ev_data.get("parameters", {}),
                ))

            # Termination
            term_data = data["termination"]
            termination = ScenarioTermination(
                conditions=term_data["conditions"],
                timeout=float(term_data["timeout"]),
            )

            return ScenarioDefinition(
                name=meta["name"],
                version=str(meta["version"]),
                description=meta.get("description", ""),
                duration=float(meta["duration"]),
                ego_initial=ego_initial,
                ego_constraints=ego_constraints,
                road=road,
                weather=weather,
                traffic_objects=traffic_objects,
                events=events,
                termination=termination,
                master_seed=data.get("master_seed"),
                parameterization=data.get("parameterization", {}),
            )

        except (KeyError, TypeError, ValueError) as e:
            raise ScenarioParseError(f"Schema parsing error: {e}")
