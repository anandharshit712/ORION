"""
ORION Scenario YAML Parser.

Parses YAML scenario files into ScenarioDefinition objects.
Includes validation and SHA256 hashing for versioning.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional, Tuple, Union

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

        scenario = self._parse_dict(data, filepath.parent)
        errors = self.validator.validate(scenario)
        if errors:
            raise ScenarioValidationError(
                "Validation failed:\n" + "\n".join(f"  - {e}" for e in errors)
            )

        # A map is part of the scenario: an edited .xodr must not reuse the
        # content hash (and so the stored results) of the map it replaced.
        if scenario.road.file_sha256:
            yaml_content += f"\n# xodr sha256: {scenario.road.file_sha256}"
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
                "Validation failed:\n" + "\n".join(f"  - {e}" for e in errors)
            )

        return scenario, hash_string(yaml_string)

    # ── Private parsing ──────────────────────────────────────────────

    def _parse_dict(
        self, data: dict, base_dir: Optional[Path] = None
    ) -> ScenarioDefinition:
        """Parse a raw YAML dictionary into a ScenarioDefinition.

        ``base_dir`` is the scenario file's directory. Only a `source: xodr`
        road needs it, to resolve its map; a string has none and is refused.
        """
        try:
            meta = data["scenario"]
            ego_data = data["ego"]
            env_data = data["environment"]

            if env_data["road"].get("source") is not None:
                road, (x, y, heading) = _xodr_road(
                    env_data["road"], ego_data["initial"], base_dir
                )
                # These move the ego in world x/y, which on a map road is
                # partly sideways: out of the lane it was placed in.
                world_shift = {"ego_x", "ego_y", "ego_x_jitter"} & set(
                    data.get("parameterization") or {}
                )
                if world_shift:
                    raise ScenarioParseError(
                        f"parameterization {sorted(world_shift)} moves the ego in "
                        f"world coordinates, off its map lane; not supported "
                        f"with source: xodr"
                    )
            else:
                road = RoadConfiguration(
                    road_type=env_data["road"]["type"],
                    lanes=int(env_data["road"]["lanes"]),
                    lane_width=float(env_data["road"]["lane_width"]),
                    speed_limit=float(env_data["road"]["speed_limit"]),
                    # Optional (Phase 1.5): omitted means the flat straight road.
                    template=env_data["road"].get("template"),
                    template_params=dict(env_data["road"].get("template_params", {})),
                )
                x = float(ego_data["initial"]["x"])
                y = float(ego_data["initial"]["y"])
                heading = float(ego_data["initial"]["heading"])

            ego_initial = VehicleInitialCondition(
                x=x,
                y=y,
                heading=heading,
                velocity=float(ego_data["initial"]["velocity"]),
            )

            ego_constraints = VehicleConstraints(
                max_velocity=float(ego_data["constraints"]["max_velocity"]),
                max_acceleration=float(ego_data["constraints"]["max_acceleration"]),
                max_deceleration=float(ego_data["constraints"]["max_deceleration"]),
                max_steering=float(ego_data["constraints"]["max_steering"]),
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
                traffic_objects.append(
                    TrafficObjectDefinition(
                        id=obj_data["id"],
                        type=obj_data["type"],
                        initial=obj_initial,
                        behavior=obj_behavior,
                    )
                )

            # Events
            events = []
            for ev_data in data.get("events", []):
                events.append(
                    ScenarioEvent(
                        type=ev_data["type"],
                        trigger_time=float(ev_data["trigger_time"]),
                        parameters=ev_data.get("parameters", {}),
                    )
                )

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
                # Optional (Phase 4.5): documentation, never read by the engine.
                behavioral_requirement=_text(meta.get("behavioral_requirement")),
                hazard=_text(meta.get("hazard")),
                verification_gap=_text(meta.get("verification_gap")),
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


def _xodr_road(
    road_data: dict, ego_initial: dict, base_dir: Optional[Path]
) -> Tuple[RoadConfiguration, Tuple[float, float, float]]:
    """A `source: xodr` road block -> (RoadConfiguration, ego x/y/heading).

    Every failure is a ScenarioParseError naming what is wrong. Nothing falls
    back to the flat road: a scenario scored on geometry it does not declare is
    exactly what this refuses.
    """
    from arep.maps.xodr_parser import file_sha256, load_map

    if road_data["source"] != "xodr":
        raise ScenarioParseError(
            f"Unknown road source {road_data['source']!r}; supported: 'xodr'"
        )
    # The map is the one source of these. Stating them as well would let the
    # YAML and the map disagree, and one of them would silently lose.
    stated = sorted(
        {"lanes", "lane_width", "speed_limit", "template", "template_params"}
        & set(road_data)
    ) + [f"ego.initial.{k}" for k in ("x", "y", "heading") if k in ego_initial]
    if stated:
        raise ScenarioParseError(
            f"source: xodr takes {stated} from the map; remove them from the scenario"
        )
    missing = [
        k
        for k in ("file", "ego_start_road_id", "ego_start_s", "ego_start_lane_id")
        if k not in road_data
    ]
    if missing:
        raise ScenarioParseError(f"source: xodr requires {missing}")
    if base_dir is None:
        raise ScenarioParseError(
            "source: xodr needs a scenario loaded from a file: its map is "
            "resolved relative to the scenario"
        )

    # The library root is the directory holding the scenario's category
    # directory (scenarios/ for scenarios/int/X.yaml). A map path may not leave
    # it, by `..` or by symlink -- resolve() follows both.
    root = base_dir.resolve().parent
    path = (base_dir / str(road_data["file"])).resolve()
    if not path.is_relative_to(root):
        raise ScenarioParseError(
            f"map file {road_data['file']!r} resolves outside the scenario "
            f"library root {root}"
        )
    if not path.is_file():
        raise ScenarioParseError(f"map file not found: {road_data['file']!r}")

    road_id = str(road_data["ego_start_road_id"])
    lane_id = str(road_data["ego_start_lane_id"])
    start_s = float(road_data["ego_start_s"])
    sha = file_sha256(str(path))
    try:
        xmap = load_map(str(path), sha)
        pose = xmap.lane_pose(road_id, start_s, lane_id)
    except ValueError as exc:
        raise ScenarioParseError(f"{road_data['file']}: {exc}") from exc

    segment = xmap.graph.segments[f"road_{road_id}"]
    road = RoadConfiguration(
        road_type=road_data["type"],
        lanes=segment.lane_count,
        lane_width=segment.lane_width,
        speed_limit=segment.speed_limit,
        source="xodr",
        file=str(path),
        file_sha256=sha,
        ego_start_road_id=road_id,
        ego_start_s=start_s,
        ego_start_lane_id=lane_id,
    )
    return road, pose


def _text(value: object) -> str:
    """A free-text metadata field as one line: absent is "", YAML folding undone."""
    return " ".join(str(value).split()) if value is not None else ""
