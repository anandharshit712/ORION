"""
ORION OpenSCENARIO 2.0 Importer.  [Phase 4]

Reads OpenSCENARIO 2.0 DSL (.osc) files and converts them to
AREP ScenarioDefinition objects, enabling teams to import their
existing scenario libraries without rewriting them.

A line-oriented reader for the subset ORION models, not a conforming OSC2
parser. That is a deliberate limit rather than a shortcut: the full DSL has a
type system, modifiers and composition that this engine has no way to execute,
and a parser that accepted them would produce scenarios that silently do not
test what the file describes.

Supported OSC2 constructs:
  scenario NAME:                         → name
  NAME: float|int|<unit type>            → parameter declaration
  keep(NAME in [a .. b]) / NAME: T = v   → parameterization range / scalar
  NAME: Vehicle|Car|Truck|Bicycle|
        Pedestrian|Person (any case)     → traffic NPC entry (ego / ego_vehicle
                                           is the ego)
  do parallel|serial(duration: Ns)       → duration
  X.assign_position(position_3d(x:, y:)) → initial x / y
  X.assign_orientation(orientation_3d(yaw:)) → initial heading
  X.assign_speed(v) / speed(v) modifier  → initial velocity
  wait elapsed / time_to_collision /
       distance_to condition             → time / ttc / proximity trigger
  drive / brake / walk action            → constant_velocity / hesitant_brake /
                                           pedestrian
  deceleration(a) modifier               → final_decel
  #@orion annotation lines               → ORION fields with no OSC2 equivalent
                                           (written by OpenSCENARIOExporter)

Units: m, s, mps, mpsps, rad as given; kph and deg converted. Anything else —
paths, lanes, relative positions, lane changes, other actions, unknown
parameter names — is skipped *and reported*: logged, and returned by `read()`
so an API caller sees exactly what was lost. A scenario missing its hazard
still runs and still produces a score, which is the dangerous failure.

Reference: ASAM OpenSCENARIO 2.0 DSL specification
"""

from __future__ import annotations

import dataclasses
import json
import math
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from arep.scenario.osc_exporter import ANNOTATION, PARAM_SEPARATOR
from arep.scenario.schema import (
    ScenarioDefinition,
    ScenarioEvent,
    ScenarioTermination,
    TrafficObjectBehavior,
    TrafficObjectDefinition,
)
from arep.utils.logging_config import get_logger

logger = get_logger("scenario.osc_importer")

EGO_NAMES = ("ego", "ego_vehicle")

# OSC2 actor type (lower-cased) → ORION object type.
ACTOR_TYPES = {
    "vehicle": "car",
    "car": "car",
    "truck": "truck",
    "bicycle": "bicycle",
    "pedestrian": "pedestrian",
    "person": "pedestrian",
}

# OSC2 action → (behaviour type, bt_type). Mirrors the exporter's table.
VERBS = {
    "drive": ("constant_velocity", None),
    "brake": ("reactive_vehicle", "hesitant_brake"),
    "walk": ("pedestrian", None),
}

# The parameterization keys ScenarioParameterizer reads. Anything else would
# load and never be sampled — a range that looks applied and is not.
EGO_PARAMS = frozenset({"ego_velocity", "ego_x_jitter", "ego_x", "ego_y"})
NPC_PARAMS = frozenset({"initial_velocity", "initial_x", "initial_y"})

_NUM = r"[-+]?\d+(?:\.\d*)?(?:[eE][-+]?\d+)?"
_UNITS = {
    "": 1.0,
    "m": 1.0,
    "s": 1.0,
    "mps": 1.0,
    "mpsps": 1.0,
    "rad": 1.0,
    "kph": 1 / 3.6,
    "deg": math.pi / 180.0,
}
_QUANTITY_RE = re.compile(rf"^\s*({_NUM})\s*([a-z]*)\s*$")

_SCENARIO_RE = re.compile(r"^scenario\s+([A-Za-z_]\w*)\s*:$")
_DECL_RE = re.compile(r"^([A-Za-z_]\w*)\s*:\s*([A-Za-z_]\w*)\s*(?:=\s*(.+))?$")
_KEEP_RE = re.compile(r"^keep\(\s*(\w+)\s+in\s+\[\s*(.+?)\s*\.\.\s*(.+?)\s*\]\s*\)$")
_BLOCK_RE = re.compile(
    rf"^(?:do\s+)?(?:parallel|serial)(?:\(\s*duration:\s*({_NUM}\s*[a-z]*)\s*\))?:$"
)
_WAIT_RE = re.compile(r"^wait\s+(.+?):?$")
_CALL_RE = re.compile(r"^([A-Za-z_]\w*)\.(\w+)\((.*)\)(\s+with:)?$")
_MODIFIER_RE = re.compile(r"^(\w+)\((.*)\)$")
_POSITION_RE = re.compile(r"^position_3d\(\s*x:\s*([^,]+),\s*y:\s*([^,)]+)")
_ORIENTATION_RE = re.compile(r"^orientation_3d\(\s*yaw:\s*([^,)]+)")


class OpenSCENARIOImporter:
    """
    Converts OpenSCENARIO 2.0 .osc files to ScenarioDefinition.

    Constructs with no ORION equivalent are skipped and reported, never
    approximated into a behaviour the file did not describe.
    """

    def import_file(self, osc_path: str) -> ScenarioDefinition:
        """Parse an .osc file and return an AREP ScenarioDefinition."""
        path = Path(osc_path)
        if not path.exists():
            raise FileNotFoundError(f"OpenSCENARIO file not found: {osc_path}")
        return self.import_string(path.read_text(encoding="utf-8"), source=path.name)

    def import_string(
        self, osc_text: str, source: str = "<string>"
    ) -> ScenarioDefinition:
        """Convert OSC2 DSL text into a ScenarioDefinition (see `read`)."""
        return self.read(osc_text, source)[0]

    def read(
        self, osc_text: str, source: str = "<string>"
    ) -> Tuple[ScenarioDefinition, List[str]]:
        """
        Convert OSC2 DSL text into a ScenarioDefinition.

        Returns:
            (scenario, skipped) — `skipped` names every line that was not
            imported, so the caller can see what the scenario lost.

        Raises:
            ValueError: the text declares no scenario.
        """
        return _Reader(source).run(osc_text)


class _Reader:
    """One pass over one file. Holds the state a line reader needs."""

    def __init__(self, source: str) -> None:
        self.source = source
        self.scenario = ScenarioDefinition(name="", version="2.0")
        self.actors: Dict[str, Dict[str, Any]] = {}
        self.param_types: Dict[str, str] = {}
        self.params: Dict[str, Any] = {}
        self.events: List[ScenarioEvent] = []
        self.pending_trigger: Optional[Tuple[str, float]] = None
        self.current: Optional[str] = None  # actor whose `with:` block is open
        self.current_indent = -1
        self.actor_annotations: List[Tuple[str, Any, str]] = []
        self.has_termination = False
        self.skipped: List[str] = []

    # ── Driver ───────────────────────────────────────────────────────

    def run(self, osc_text: str) -> Tuple[ScenarioDefinition, List[str]]:
        for raw_line in osc_text.splitlines():
            stripped = raw_line.strip()
            if stripped.startswith(ANNOTATION + " "):
                self._annotation(stripped[len(ANNOTATION) :].strip())
                continue
            line = raw_line.split("#", 1)[0].strip()
            if not line:
                continue
            indent = len(raw_line) - len(raw_line.lstrip())
            if self.current is not None and indent <= self.current_indent:
                self.current = None
            if not self._line(line, indent):
                self.skipped.append(line)
        if self.pending_trigger is not None:
            self.skipped.append(f"{self.pending_trigger[0]} trigger with no action")

        if not self.scenario.name:
            raise ValueError(
                f"{self.source} declares no scenario. Expected a line of the "
                f"form 'scenario my_name:'."
            )
        return self._build(), self.skipped

    def _line(self, line: str, indent: int) -> bool:
        """Handle one line. False means it was not understood."""
        if line.startswith("import "):
            return True

        match = _SCENARIO_RE.match(line)
        if match:
            if not self.scenario.name:
                self.scenario.name = match.group(1)
            return True

        match = _BLOCK_RE.match(line)
        if match:
            if match.group(1) is not None:
                duration = _quantity(match.group(1))
                if duration is None:
                    return False
                self.scenario.duration = duration
            return True

        match = _KEEP_RE.match(line)
        if match:
            return self._keep(*match.groups())

        match = _DECL_RE.match(line)
        if match:
            return self._declaration(*match.groups())

        match = _WAIT_RE.match(line)
        if match:
            # Consumed by the next action whatever it is, so a trigger meant
            # for an unsupported action is lost with it, not moved elsewhere.
            self.pending_trigger = _condition(match.group(1))
            return self.pending_trigger is not None

        match = _CALL_RE.match(line)
        if match:
            name, method, args, with_block = match.groups()
            return self._call(name, method, args, with_block, indent)

        match = _MODIFIER_RE.match(line)
        if match and self.current is not None:
            return self._modifier(self.current, *match.groups())
        return False

    # ── Declarations ─────────────────────────────────────────────────

    def _declaration(self, name: str, kind: str, default: Optional[str]) -> bool:
        actor_type = ACTOR_TYPES.get(kind.lower())
        if actor_type is not None and default is None:
            if name not in EGO_NAMES:
                self.actors[name] = {
                    "id": name,
                    "type": actor_type,
                    "x": 0.0,
                    "y": 0.0,
                    "heading": 0.0,
                    "speed": 0.0,
                    "behaviour": "constant_velocity",
                    "params": {},
                }
            return True
        if actor_type is not None:
            return False
        # Anything else declared with a type is a parameter.
        self.param_types[name] = kind
        if default is None:
            return True
        value = _quantity(default)
        if value is None:
            return False
        self.params[name] = int(value) if kind == "int" else value
        return True

    def _keep(self, name: str, low_text: str, high_text: str) -> bool:
        low, high = _quantity(low_text), _quantity(high_text)
        if low is None or high is None:
            return False
        if self.param_types.get(name) == "int":
            self.params[name] = {"min": int(low), "max": int(high)}
        else:
            self.params[name] = {"min": low, "max": high}
        return True

    # ── Actions ──────────────────────────────────────────────────────

    def _call(
        self, name: str, method: str, args: str, with_block: Optional[str], indent: int
    ) -> bool:
        is_ego = name in EGO_NAMES
        actor = None if is_ego else self.actors.get(name)
        trigger, self.pending_trigger = self.pending_trigger, None
        trigger_used = False

        if not is_ego and actor is None:
            supported = False
        elif method.startswith("assign_"):
            supported = self._assign(name, method, args)
        elif is_ego:
            # The ego is the model under test; driving is all it can be told.
            supported = method == "drive"
        elif method in VERBS:
            assert actor is not None
            behaviour, bt_type = VERBS[method]
            actor["behaviour"] = behaviour
            if bt_type is not None:
                actor["params"]["bt_type"] = bt_type
            if trigger is not None:
                actor["params"]["trigger_type"] = trigger[0]
                actor["params"]["trigger_value"] = trigger[1]
                trigger_used = True
            supported = True
        else:
            supported = False

        if trigger is not None and not trigger_used:
            self.skipped.append(
                f"{trigger[0]} trigger {trigger[1]} (the action after it, "
                f"{name}.{method}, cannot take an ORION trigger)"
            )
        if method.startswith("assign_"):
            return supported
        if supported and args.strip():
            # drive(path) and the like: the action is read, its arguments
            # (a route, a target) are not, and the caller should know.
            self.skipped.append(f"{name}.{method}({args}): arguments not imported")
        if with_block and supported:
            self.current, self.current_indent = name, indent
        return supported

    def _assign(self, name: str, method: str, args: str) -> bool:
        args = args.strip()
        values: Dict[str, Optional[float]] = {}
        if method == "assign_position":
            match = _POSITION_RE.match(args)
            if not match:
                return False
            values = {"x": _quantity(match.group(1)), "y": _quantity(match.group(2))}
        elif method == "assign_orientation":
            match = _ORIENTATION_RE.match(args)
            if not match:
                return False
            values = {"heading": _quantity(match.group(1))}
        elif method == "assign_speed":
            values = {"speed": _quantity(args)}
        else:
            return False
        if any(v is None for v in values.values()):
            return False
        for key, value in values.items():
            self._set_initial(name, key, value)
        return True

    def _modifier(self, name: str, modifier: str, args: str) -> bool:
        value = _quantity(args)
        if value is None:
            return False
        if modifier == "speed":
            self._set_initial(name, "speed", value)
            return True
        if modifier == "deceleration" and name not in EGO_NAMES:
            # OSC2 states deceleration as a magnitude; ORION signs it.
            self.actors[name]["params"]["final_decel"] = -abs(value)
            return True
        return False

    def _set_initial(self, name: str, key: str, value: Any) -> None:
        if name in EGO_NAMES:
            ego = self.scenario.ego_initial
            setattr(ego, "velocity" if key == "speed" else key, value)
        else:
            self.actors[name][key] = value

    # ── ORION annotations ────────────────────────────────────────────

    def _annotation(self, body: str) -> None:
        kind, _, rest = body.partition(" ")
        try:
            if kind == "scenario":
                self._scenario_annotation(json.loads(rest))
                return
            if kind == "event":
                self.events.append(ScenarioEvent(**json.loads(rest)))
                return
            if kind == "actor":
                # Applied in _build, after every OSC2 line: the annotation
                # refines what the action said, whatever order they came in.
                name, _, payload = rest.partition(" ")
                self.actor_annotations.append((name, json.loads(payload), body))
                return
        except (ValueError, TypeError):
            pass
        self.skipped.append(f"{ANNOTATION} {body}")

    def _scenario_annotation(self, data: Dict[str, Any]) -> None:
        defaults = ScenarioDefinition()
        known = {f.name for f in dataclasses.fields(defaults)}
        for key, value in data.items():
            if key not in known:
                self.skipped.append(f"{ANNOTATION} scenario field {key!r}")
                continue
            current: Any = getattr(defaults, key)
            if dataclasses.is_dataclass(current) and not isinstance(current, type):
                value = type(current)(**value)
            setattr(self.scenario, key, value)
            self.has_termination |= key == "termination"

    def _actor_annotation(self, name: str, data: Any, body: str) -> None:
        actor = self.actors.get(name)
        if (
            actor is None
            or not isinstance(data, dict)
            or set(data) - {"id", "type", "behavior", "parameters"}
        ):
            self.skipped.append(f"{ANNOTATION} {body}")
            return
        actor["id"] = data.get("id", actor["id"])
        actor["type"] = data.get("type", actor["type"])
        actor["behaviour"] = data.get("behavior", actor["behaviour"])
        actor["params"].update(data.get("parameters", {}))

    # ── Assembly ─────────────────────────────────────────────────────

    def _build(self) -> ScenarioDefinition:
        scenario = self.scenario
        for name, data, body in self.actor_annotations:
            self._actor_annotation(name, data, body)
        for actor in self.actors.values():
            obj = TrafficObjectDefinition(id=actor["id"], type=actor["type"])
            obj.initial.x = actor["x"]
            obj.initial.y = actor["y"]
            obj.initial.heading = actor["heading"]
            obj.initial.velocity = actor["speed"]
            obj.behavior = TrafficObjectBehavior(
                type=actor["behaviour"], parameters=actor["params"]
            )
            scenario.traffic_objects.append(obj)
        scenario.events = self.events
        scenario.parameterization = self._parameterization()

        if not self.has_termination:
            scenario.termination = ScenarioTermination(
                conditions=["collision", "off_road", "timeout"],
                timeout=scenario.duration,
            )

        if self.skipped:
            # Logged individually: a reviewer needs to know *what* was lost,
            # not merely that something was.
            logger.warning(
                "%s: %d construct(s) not imported", self.source, len(self.skipped)
            )
            for line in self.skipped[:20]:
                logger.warning("  skipped: %s", line)

        logger.info(
            "Imported %s: %d traffic actor(s)",
            self.source,
            len(scenario.traffic_objects),
        )
        return scenario

    def _parameterization(self) -> Dict[str, Any]:
        """Nest the flat OSC2 parameters back into ORION's block.

        Only names ScenarioParameterizer reads are kept; a third-party
        parameter that would load and never be sampled is reported instead.
        """
        for name, kind in self.param_types.items():
            if name not in self.params:
                self.skipped.append(f"{name}: {kind} (declared with no value)")
        npc_ids = {name: actor["id"] for name, actor in self.actors.items()}
        out: Dict[str, Any] = {}
        for name, spec in self.params.items():
            path = name.split(PARAM_SEPARATOR)
            known = (len(path) == 1 and path[0] in EGO_PARAMS) or (
                len(path) >= 3
                and path[0] == "npc_overrides"
                and path[1] in npc_ids
                and (
                    (len(path) == 3 and path[2] in NPC_PARAMS)
                    or (len(path) == 4 and path[2] == "parameters")
                )
            )
            if not known:
                self.skipped.append(f"parameter {name} (not a parameter ORION samples)")
                continue
            if len(path) > 1:
                path[1] = npc_ids[path[1]]
            node = out
            for part in path[:-1]:
                node = node.setdefault(part, {})
            node[path[-1]] = spec
        return out


def _quantity(text: str) -> Optional[float]:
    """A number with an optional unit, in SI. None if it is not one."""
    match = _QUANTITY_RE.match(text)
    if not match or match.group(2) not in _UNITS:
        return None
    value = float(match.group(1))
    scale = _UNITS[match.group(2)]
    return value if scale == 1.0 else value * scale


def _condition(text: str) -> Optional[Tuple[str, float]]:
    """Map an OSC2 wait condition onto an ORION trigger.

    ORION's ttc and proximity triggers measure against the ego, so a condition
    measured against any other actor is not one of them and is refused.
    """
    text = text.strip()
    ego = r"\(\s*(?:" + "|".join(EGO_NAMES) + r")\s*\)"
    for pattern, trigger_type in (
        (r"^elapsed\((.+)\)$", "time"),
        (rf"^time_to_collision{ego}\s*<\s*(.+)$", "ttc"),
        (rf"^distance_to{ego}\s*<\s*(.+)$", "proximity"),
    ):
        match = re.match(pattern, text)
        if match:
            value = _quantity(match.group(1))
            return None if value is None else (trigger_type, value)
    return None
