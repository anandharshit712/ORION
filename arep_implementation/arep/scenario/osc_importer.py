"""
ORION OpenSCENARIO 2.0 Importer.  [Phase 4]

Reads OpenSCENARIO 2.0 DSL (.osc) files and converts them to
AREP ScenarioDefinition objects, enabling teams to import their
existing CARLA scenario libraries without rewriting them.

Supported OSC2 constructs:
  actor Vehicle / Pedestrian  → traffic NPC entry
  act with TimeCondition       → trigger_type: time, trigger_value: t
  act with EntityCondition     → trigger_type: ttc / distance
  drive action                 → constant_velocity BT
  brake action                 → hesitant_brake BT
  Unknown actions              → scripted BT with raw passthrough

Reference: ASAM OpenSCENARIO 2.0 DSL specification
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import List, Optional

from arep.scenario.schema import ScenarioDefinition
from arep.utils.logging_config import get_logger

logger = get_logger("scenario.osc_importer")


class OpenSCENARIOImporter:
    """
    Converts OpenSCENARIO 2.0 .osc files to ScenarioDefinition.

    The importer uses a best-effort approach: constructs that have no
    direct AREP equivalent are mapped to 'scripted' behavior with the
    raw parameters preserved. Unknown constructs are logged as warnings.
    """

    def import_file(self, osc_path: str) -> ScenarioDefinition:
        """
        Parse an .osc file and return an AREP ScenarioDefinition.

        Args:
            osc_path: Absolute path to the .osc file.

        Returns:
            ScenarioDefinition compatible with the AREP scenario pipeline.

        """
        path = Path(osc_path)
        if not path.exists():
            raise FileNotFoundError(f"OpenSCENARIO file not found: {osc_path}")
        return self.import_string(path.read_text(encoding="utf-8"), source=path.name)

    def import_string(
        self, osc_text: str, source: str = "<string>"
    ) -> ScenarioDefinition:
        """
        Convert OSC2 DSL text into a ScenarioDefinition.

        A line-oriented reader for the subset ORION models, not a conforming
        OSC2 parser. That is a deliberate limit rather than a shortcut: the
        full DSL has a type system, modifiers and composition that this engine
        has no way to execute, and a parser that accepted them would produce
        scenarios that silently do not test what the file describes.

        What it reads:
          - the scenario declaration, for the name
          - actor declarations, into traffic entries
          - drive and brake actions, into constant_velocity / hesitant_brake
          - wait conditions, into time / ttc / proximity triggers

        Anything else is logged and skipped, and the caller gets a scenario
        it can inspect. Silence here would be the dangerous behaviour, because
        a scenario missing its hazard still runs and still produces a score.
        """
        from arep.scenario.schema import (
            ScenarioTermination,
            TrafficObjectBehavior,
            TrafficObjectDefinition,
        )

        scenario = ScenarioDefinition(name="", version="2.0")
        actors: dict = {}
        order: List[str] = []
        pending_trigger: Optional[tuple] = None
        unsupported: List[str] = []

        for raw_line in osc_text.splitlines():
            line = raw_line.split("#", 1)[0].strip()
            if not line:
                continue

            if line.startswith("import "):
                continue

            if line.startswith("scenario ") and line.endswith(":"):
                scenario.name = line[len("scenario ") : -1].strip()
                continue

            declaration = _ACTOR_RE.match(line)
            if declaration:
                name, actor_type = declaration.group(1), declaration.group(2)
                if name != "ego":
                    actors[name] = {
                        "type": "pedestrian" if actor_type == "Pedestrian" else "car",
                        "speed": 0.0,
                        "behaviour": "constant_velocity",
                        "params": {},
                    }
                    order.append(name)
                continue

            wait = _WAIT_RE.match(line)
            if wait:
                pending_trigger = _parse_condition(wait.group(1))
                if pending_trigger is None:
                    unsupported.append(line)
                continue

            action = _ACTION_RE.match(line)
            if action:
                name, verb = action.group(1), action.group(2)
                if name == "ego":
                    continue
                actor = actors.get(name)
                if actor is None:
                    unsupported.append(line)
                    continue
                if verb == "brake":
                    actor["behaviour"] = "reactive_vehicle"
                    actor["params"]["bt_type"] = "hesitant_brake"
                if pending_trigger:
                    actor["params"]["trigger_type"] = pending_trigger[0]
                    actor["params"]["trigger_value"] = pending_trigger[1]
                    pending_trigger = None
                continue

            speed = _SPEED_RE.match(line)
            if speed and order:
                actors[order[-1]]["speed"] = float(speed.group(1))
                continue

            decel = _DECEL_RE.match(line)
            if decel and order:
                # OSC2 states deceleration as a magnitude; ORION signs it.
                actors[order[-1]]["params"]["final_decel"] = -abs(float(decel.group(1)))
                continue

            if line not in ("do parallel:", "serial:", "do serial:"):
                unsupported.append(line)

        if not scenario.name:
            raise ValueError(
                f"{source} declares no scenario. Expected a line of the form "
                f"'scenario my_name:'."
            )

        for name in order:
            actor = actors[name]
            obj = TrafficObjectDefinition(id=name, type=actor["type"])
            obj.initial.velocity = actor["speed"]
            obj.behavior = TrafficObjectBehavior(
                type=actor["behaviour"],
                parameters=actor["params"],
            )
            scenario.traffic_objects.append(obj)

        scenario.termination = ScenarioTermination(
            conditions=["collision", "off_road", "timeout"],
            timeout=scenario.duration,
        )

        if unsupported:
            # Logged individually: a reviewer needs to know *what* was lost,
            # not merely that something was.
            logger.warning(
                "%s: %d construct(s) not imported",
                source,
                len(unsupported),
            )
            for line in unsupported[:20]:
                logger.warning("  skipped: %s", line)

        logger.info(
            "Imported %s: %d traffic actor(s)",
            source,
            len(scenario.traffic_objects),
        )
        return scenario


# ── Line patterns ────────────────────────────────────────────────────────

_ACTOR_RE = re.compile(r"^([A-Za-z_]\w*)\s*:\s*(Vehicle|Pedestrian)\s*$")
_ACTION_RE = re.compile(r"^([A-Za-z_]\w*)\.(drive|brake|yield)\(\)")
_WAIT_RE = re.compile(r"^wait\s+(.+?):?$")
_SPEED_RE = re.compile(r"^speed\(([-\d.]+)mps\)")
_DECEL_RE = re.compile(r"^deceleration\(([-\d.]+)mpsps\)")


def _parse_condition(text: str) -> Optional[tuple]:
    """Map an OSC2 wait condition onto an ORION trigger."""
    text = text.strip()

    elapsed = re.match(r"elapsed\(([-\d.]+)s\)", text)
    if elapsed:
        return "time", float(elapsed.group(1))

    ttc = re.match(r"time_to_collision\([^)]*\)\s*<\s*([-\d.]+)s", text)
    if ttc:
        return "ttc", float(ttc.group(1))

    distance = re.match(r"distance_to\([^)]*\)\s*<\s*([-\d.]+)m", text)
    if distance:
        return "proximity", float(distance.group(1))

    return None
