"""
ORION CLI — standards-alignment artefacts.  [Phase 4.5]

Two artefacts per suite, both generated from the scenario YAML so they cannot
drift from the library:

    traceability   scenario <-> hazard <-> behavioural requirement <-> latest
                   result, as CSV and HTML (plus PDF where WeasyPrint loads)
    odd            the operational design domain the suite exercises -- road
                   types, speed ranges, actor types -- and, stated as plainly,
                   what it does not, as JSON and HTML (plus PDF)

Usage:
    python -m arep.cli.standards traceability --suite core \\
        --report results/orion_suite_report.json --output-dir ./standards
    python -m arep.cli.standards odd --suite full --output-dir ./standards

The latest result comes only from a run_suite report passed with --report. A
scenario that report does not cover reads "not run": a result is never
inferred, defaulted or carried over from anywhere else.

This is alignment documentation, not certification. See docs/STANDARDS.md.

Exit codes: 0 written, 2 could not build (unknown suite, unreadable report).
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

EXIT_OK = 0
EXIT_ERROR = 2

NOT_RUN = "not run"

CATEGORY_NAMES = {
    "LON": "Longitudinal",
    "LAT": "Lateral",
    "INT": "Intersection",
    "VRU": "Vulnerable road user",
    "EMG": "Emergency",
    "MLT": "Multi-agent",
}

# Spawn events add actors that are absent from `traffic:`; counting only the
# traffic block would leave LON-007's revealed obstacle out of the ODD.
SPAWNED_ACTOR_TYPES = {"spawn_vehicle": "car", "spawn_pedestrian": "pedestrian"}

CSV_COLUMNS = [
    "scenario",
    "name",
    "category",
    "hazard",
    "behavioral_requirement",
    "verification_gap",
    "result",
    "collision_rate",
    "off_road_rate",
    "composite_mean",
    "runs",
    "model",
    "seed",
]


def _engine_limits() -> List[Dict[str, str]]:
    """What no suite covers, because the engine does not model it.

    ponytail: hand-written on purpose -- these are facts about the code, not the
    YAML, so there is no scenario data to derive them from. Each names the code
    or document that shows it; when one of them is built, delete its entry.
    """
    from arep.core.observation import MAX_OBJECTS

    return [
        {
            "topic": "Weather, visibility and surface friction",
            "statement": "Scenario weather and visibility are labels that neither "
            "the physics nor the Observation reads. Friction is one global "
            "configuration value, and the default kinematic physics ignores it.",
            "evidence": "docs/DISCUSSIONS.md DI-01; arep/scenario/parameterizer.py",
        },
        {
            "topic": "Sensors and perception",
            "statement": f"The Observation is ground truth for the {MAX_OBJECTS} "
            "nearest objects: no camera, LiDAR, radar, GPS or IMU model, no noise, "
            "no field of view and no occlusion. Planned as Phase 6.",
            "evidence": "arep/core/observation.py; docs/METHODOLOGY.md section 8",
        },
        {
            "topic": "Lighting and time of day",
            "statement": "Not modelled. No night or low-sun scenario exists.",
            "evidence": "docs/ROADMAP.md 4.3, substituted themes",
        },
        {
            "topic": "Road grade and elevation",
            "statement": "The world is a flat plane: no grade, crest, banking or "
            "speed bump.",
            "evidence": "arep/core/state.py (Vector2D positions)",
        },
        {
            "topic": "Routes, goals and lane assignment",
            "statement": "The Observation carries no route and no assigned lane, and "
            "no scenario has a goal condition. Turns and merges cannot be required, "
            "so junction results measure reaction inside a junction, not "
            "negotiation of one.",
            "evidence": "docs/PENDING.md, 'No lane assignment reaches the model'",
        },
        {
            "topic": "Progress",
            "statement": "Nothing in the composite or the pass criterion rewards "
            "making progress: a vehicle that stops early passes most scenarios.",
            "evidence": "docs/METHODOLOGY.md section 8; tests/test_reference_model.py",
        },
        {
            "topic": "Traffic-rule compliance",
            "statement": "Only speed-limit and lane-position compliance are scored, "
            "and only in the composite. Signals, stop lines, give-way and right of "
            "way are not checked: a violation fails a run only if it causes contact.",
            "evidence": "arep/evaluation/compliance.py; arep/cli/run_suite.py",
        },
        {
            "topic": "Ego manoeuvres",
            "statement": "The ego cannot reverse: the physics clamps its speed at zero.",
            "evidence": "arep/core/physics.py",
        },
    ]


def _text(value: Any) -> str:
    return " ".join(str(value).split()) if value is not None else ""


def load_scenarios(selector: str, root: Path) -> List[Dict[str, Any]]:
    """Every scenario the selector names, with its metadata and loadability.

    Read from the raw YAML rather than through the parser alone, because a
    scenario refused at load still belongs in the matrix: a requirement the
    engine cannot execute is exactly the row a reviewer most needs to see.
    """
    from arep.cli.run_suite import resolve_scenarios
    from arep.scenario.parser import ScenarioParser
    from arep.utils.exceptions import ScenarioParseError, ScenarioValidationError

    parser = ScenarioParser()
    scenarios = []
    for path in resolve_scenarios(selector, root):
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        try:
            parser.parse_file(path)
            refused = ""
        except (ScenarioParseError, ScenarioValidationError) as exc:
            refused = str(exc).strip().splitlines()[-1].strip(" -")
        meta = data["scenario"]
        scenario_id = path.stem.split("_")[0]
        scenarios.append(
            {
                "id": scenario_id,
                "stem": path.stem,
                "name": _text(meta.get("name")),
                "category": CATEGORY_NAMES.get(scenario_id.split("-")[0], ""),
                "behavioral_requirement": _text(meta.get("behavioral_requirement")),
                "hazard": _text(meta.get("hazard")),
                "verification_gap": _text(meta.get("verification_gap")),
                "refused": refused,
                "data": data,
            }
        )
    return scenarios


def traceability_rows(
    scenarios: List[Dict[str, Any]], report: Optional[dict] = None
) -> List[Dict[str, Any]]:
    """One row per scenario. The result is the report's, or "not run"."""
    report = report or {}
    results = {s["scenario"]: s for s in report.get("scenarios", [])}
    unloadable = {u["scenario"] for u in report.get("unloadable", [])}

    rows = []
    for sc in scenarios:
        run = results.get(sc["stem"])
        if run is not None:
            result = "PASS" if run.get("passed") else "FAIL"
        elif sc["stem"] in unloadable:
            result = "NOT RUN: refused at load"
        else:
            result = NOT_RUN
        rows.append(
            {
                "scenario": sc["id"],
                "name": sc["name"],
                "category": sc["category"],
                "hazard": sc["hazard"],
                "behavioral_requirement": sc["behavioral_requirement"],
                "verification_gap": sc["verification_gap"],
                "result": result,
                "collision_rate": run.get("collision_rate", "") if run else "",
                "off_road_rate": run.get("off_road_rate", "") if run else "",
                "composite_mean": run.get("composite_mean", "") if run else "",
                "runs": run.get("runs", "") if run else "",
                "model": report.get("model", "") if run else "",
                "seed": report.get("seed", "") if run else "",
            }
        )
    return rows


def _range(values: List[float]) -> Dict[str, float]:
    lo, hi = min(values), max(values)
    return {
        "min_ms": round(lo, 2),
        "max_ms": round(hi, 2),
        "min_kmh": round(lo * 3.6, 1),
        "max_kmh": round(hi * 3.6, 1),
    }


def odd_statement(scenarios: List[Dict[str, Any]], suite: str) -> Dict[str, Any]:
    """The ODD the suite exercises, derived from the scenario YAML.

    Coverage counts only scenarios that load: a refused scenario exercises
    nothing, so it is listed under not-covered instead of widening a range.
    """
    executable = [s for s in scenarios if not s["refused"]]

    road_types: Counter = Counter()
    templates: Counter = Counter()
    lanes: set = set()
    lane_widths: set = set()
    speed_limits: List[float] = []
    ego_speeds: List[float] = []
    by_road: Dict[str, Dict[str, List[float]]] = {}
    actor_types: Counter = Counter()
    behaviours: Counter = Counter()

    for sc in executable:
        data = sc["data"]
        road = data["environment"]["road"]
        road_types[road["type"]] += 1
        templates[road.get("template") or "flat straight road"] += 1
        lanes.add(int(road["lanes"]))
        lane_widths.add(float(road["lane_width"]))

        ego_range = (data.get("parameterization") or {}).get("ego_velocity")
        if ego_range:
            ego = [float(ego_range["min"]), float(ego_range["max"])]
        else:
            ego = [float(data["ego"]["initial"]["velocity"])]
        limit = float(road["speed_limit"])
        speed_limits.append(limit)
        ego_speeds.extend(ego)
        bucket = by_road.setdefault(road["type"], {"limits": [], "ego": []})
        bucket["limits"].append(limit)
        bucket["ego"].extend(ego)

        for obj in data.get("traffic") or []:
            actor_types[obj["type"]] += 1
            behaviour = obj["behavior"]
            behaviours[
                (behaviour.get("parameters") or {}).get("bt_type") or behaviour["type"]
            ] += 1
        for event in data.get("events") or []:
            spawned = SPAWNED_ACTOR_TYPES.get(event.get("type"))
            if spawned:
                actor_types[spawned] += 1
                behaviours[f"{event['type']} (appears mid-run)"] += 1

    weather_labels = Counter(
        str(s["data"]["environment"]["weather"]["condition"]) for s in scenarios
    )

    return {
        "suite": suite,
        "scenarios": len(scenarios),
        "executable": len(executable),
        "road": {
            "types": dict(sorted(road_types.items())),
            "templates": dict(sorted(templates.items())),
            "lanes": sorted(lanes),
            "lane_widths_m": sorted(lane_widths),
        },
        "speeds": {
            "speed_limit": _range(speed_limits) if speed_limits else {},
            "ego_initial_speed": _range(ego_speeds) if ego_speeds else {},
            "by_road_type": {
                road_type: {
                    "speed_limit": _range(v["limits"]),
                    "ego_initial_speed": _range(v["ego"]),
                }
                for road_type, v in sorted(by_road.items())
            },
        },
        "actors": {
            "types": dict(sorted(actor_types.items())),
            "behaviours": dict(sorted(behaviours.items())),
        },
        "weather_labels_declared": dict(sorted(weather_labels.items())),
        "not_covered": _engine_limits(),
        "refused_at_load": [
            {"scenario": s["id"], "reason": s["refused"]}
            for s in scenarios
            if s["refused"]
        ],
        "scenario_specific_gaps": [
            {"scenario": s["id"], "gap": s["verification_gap"]}
            for s in scenarios
            if s["verification_gap"]
        ],
    }


# ── Writers ──────────────────────────────────────────────────────────────


def write_csv(rows: List[Dict[str, Any]], path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    return path


def write_html_and_pdf(template: str, context: dict, path: Path) -> List[Path]:
    """HTML always; PDF only where WeasyPrint's native libraries load.

    The two carry identical content -- the PDF is the HTML printed -- so a
    machine without GTK (Windows, usually) loses a format, not information.
    """
    from arep.reporting.pdf_generator import PDFGenerator

    path.parent.mkdir(parents=True, exist_ok=True)
    html = PDFGenerator(require_pdf=False).render_html(template, context)
    path.write_text(html, encoding="utf-8")
    written = [path]
    try:
        pdf_path = path.with_suffix(".pdf")
        PDFGenerator().render_pdf(template, context, pdf_path)
        written.append(pdf_path)
    except (ImportError, OSError) as exc:
        print(f"note: PDF not written ({str(exc).splitlines()[0]})", file=sys.stderr)
    return written


def _slug(selector: str) -> str:
    return re.sub(r"[^A-Za-z0-9-]+", "_", selector).strip("_").lower() or "suite"


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m arep.cli.standards",
        description="ORION standards-alignment artefacts (Phase 4.5)",
    )
    p.add_argument("artefact", choices=["traceability", "odd"])
    p.add_argument(
        "--suite",
        default="full",
        help="A suite (core/intersection/vru/emergency/multi-agent/full), "
        "'all', a category or a scenario id (default: full)",
    )
    p.add_argument(
        "--report",
        type=Path,
        default=None,
        metavar="REPORT.json",
        help="run_suite JSON report supplying the latest result (traceability). "
        "Without it every result reads 'not run'.",
    )
    p.add_argument(
        "--output-dir",
        type=Path,
        default=Path("./results"),
        metavar="DIR",
        help="Directory to write into (default: ./results/)",
    )
    return p


def main(argv: Optional[List[str]] = None) -> int:
    from arep.cli.run_suite import (
        COLLISION_RATE_LIMIT,
        OFF_ROAD_RATE_LIMIT,
        _repo_root,
    )

    args = build_parser().parse_args(argv)
    try:
        scenarios = load_scenarios(args.suite, _repo_root())
        # Asked for by name, so a missing report is an error -- not the quiet
        # "not run" column it would otherwise turn into.
        report = (
            json.loads(args.report.read_text(encoding="utf-8"))
            if args.report is not None
            else None
        )
    except (OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_ERROR

    slug = _slug(args.suite)
    if args.artefact == "traceability":
        rows = traceability_rows(scenarios, report)
        counts = Counter(r["result"] for r in rows)
        written = [write_csv(rows, args.output_dir / f"traceability_{slug}.csv")]
        written += write_html_and_pdf(
            "traceability.html",
            {
                "suite": args.suite,
                "rows": rows,
                "counts": dict(sorted(counts.items())),
                "report": report,
                "collision_limit": COLLISION_RATE_LIMIT,
                "off_road_limit": OFF_ROAD_RATE_LIMIT,
            },
            args.output_dir / f"traceability_{slug}.html",
        )
        summary = ", ".join(f"{n} {k}" for k, n in sorted(counts.items()))
        print(f"{len(rows)} scenarios ({summary})")
    else:
        odd = odd_statement(scenarios, args.suite)
        json_path = args.output_dir / f"odd_{slug}.json"
        json_path.parent.mkdir(parents=True, exist_ok=True)
        json_path.write_text(json.dumps(odd, indent=2), encoding="utf-8")
        written = [json_path]
        written += write_html_and_pdf(
            "odd.html", {"odd": odd}, args.output_dir / f"odd_{slug}.html"
        )
        print(
            f"{odd['executable']} of {odd['scenarios']} scenarios executable; "
            f"{len(odd['not_covered']) + len(odd['refused_at_load'])} not-covered "
            f"items"
        )

    for path in written:
        print(f"  wrote {path}")
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
