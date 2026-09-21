"""
ORION CLI — Run Suite.  [Phase 3]

Entry point for the Docker-based CI/CD evaluation image.
Runs the full scenario suite against a model and returns a structured report.

Usage:
    python -m arep.cli.run_suite \\
        --scenarios all \\
        --runs-per-scenario 10 \\
        --pass-threshold 0.80 \\
        --model emergency_brake \\
        --output-dir ./results/ \\
        --format json

Exit codes:
    0  All scenarios passed (pass_rate >= pass_threshold)
    1  One or more scenarios failed
    2  Fatal error (could not load model, scenario not found, etc.)
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import List, Optional

from arep.utils.logging_config import get_logger

logger = get_logger("cli.run_suite")

# Exit codes are the contract with CI. 1 and 2 must stay distinct: a failing
# model and a broken harness call for different responses.
EXIT_PASS = 0
EXIT_FAIL = 1
EXIT_ERROR = 2

# A scenario passes on collision rate rather than composite score — a model can
# be uncomfortable and safe, but not comfortable and crashing. Matches the
# platform-wide criterion in CLAUDE.md section 7.
COLLISION_RATE_LIMIT = 0.01

# ── Built-in model name → class mapping ──────────────────────────────────
BUILTIN_MODELS = {
    "emergency_brake": "arep.models.examples.example_models.EmergencyBrakeModel",
    "constant":        "arep.models.examples.example_models.ConstantActionModel",
    "lane_keep":       "arep.models.examples.example_models.SimpleLaneKeepModel",
    "random":          "arep.models.examples.example_models.RandomModel",
}

# ── Scenario category → file pattern ─────────────────────────────────────
CATEGORY_PATTERNS = {
    "LON": "scenarios/lon/LON-*.yaml",
    "LAT": "scenarios/lat/LAT-*.yaml",
    "INT": "scenarios/int/INT-*.yaml",
    "VRU": "scenarios/vru/VRU-*.yaml",
    "EMG": "scenarios/emg/EMG-*.yaml",
    "MLT": "scenarios/mlt/MLT-*.yaml",
}


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m arep.cli.run_suite",
        description="ORION Scenario Suite Runner — CI/CD entrypoint",
    )
    p.add_argument(
        "--scenarios",
        default="all",
        help="Scenarios to run: 'all', a category (LON/LAT/INT/VRU/EMG/MLT), or a scenario ID",
    )
    p.add_argument(
        "--runs-per-scenario",
        type=int,
        default=10,
        metavar="N",
        help="Number of seeded runs per scenario (default: 10)",
    )
    p.add_argument(
        "--pass-threshold",
        type=float,
        default=0.80,
        metavar="T",
        help="Minimum pass_rate required to exit 0 (default: 0.80)",
    )
    p.add_argument(
        "--model",
        required=True,
        help="Model to evaluate: built-in name or Python import path (module.ClassName)",
    )
    p.add_argument(
        "--output-dir",
        type=Path,
        default=Path("./results"),
        metavar="DIR",
        help="Directory to write report files (default: ./results/)",
    )
    p.add_argument(
        "--format",
        choices=["json", "html"],
        default="json",
        help="Output report format (default: json)",
    )
    p.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Master seed for all runs (default: 42)",
    )
    return p


def resolve_scenarios(selector: str, root: Path) -> List[Path]:
    """Turn --scenarios into a concrete, ordered list of files.

    Ordered because a CI report that lists scenarios in filesystem order
    changes between machines, and a diffable report is worth more than a fast
    one. An unknown selector raises rather than silently running nothing —
    exit 0 on "ran no scenarios" is the worst possible CI outcome.
    """
    if selector.lower() == "all":
        paths = sorted(root.glob("scenarios/*/*.yaml"))
        if not paths:
            raise FileNotFoundError(f"No scenarios found under {root / 'scenarios'}")
        return paths

    category = selector.upper()
    if category in CATEGORY_PATTERNS:
        paths = sorted(root.glob(CATEGORY_PATTERNS[category]))
        if not paths:
            raise FileNotFoundError(f"No scenarios in category {category}")
        return paths

    # A specific scenario, by id or by path.
    direct = Path(selector)
    if direct.is_file():
        return [direct]
    matches = sorted(root.glob(f"scenarios/*/{selector}*.yaml"))
    if matches:
        return matches

    raise FileNotFoundError(
        f"Unknown scenario selector {selector!r}. Use 'all', a category "
        f"({'/'.join(CATEGORY_PATTERNS)}), a scenario id, or a path."
    )


def load_model(spec: str):
    """Instantiate a model from a built-in name or an import path.

    The import path form is what makes this usable in CI: a customer points it
    at their own class without registering anything here first.
    """
    import importlib

    target = BUILTIN_MODELS.get(spec, spec)
    if "." not in target:
        raise ValueError(
            f"Unknown model {spec!r}. Use a built-in "
            f"({', '.join(sorted(BUILTIN_MODELS))}) or a module.ClassName path."
        )

    module_name, _, class_name = target.rpartition(".")
    try:
        module = importlib.import_module(module_name)
        model_class = getattr(module, class_name)
    except (ImportError, AttributeError) as exc:
        raise ValueError(f"Could not load model {spec!r}: {exc}") from exc

    return model_class()


def run_suite(
    scenario_paths: List[Path],
    model,
    runs_per_scenario: int,
    seed: int,
) -> dict:
    """Run every scenario and collect one report structure."""
    from arep.execution.runner import EvaluationRunner

    runner = EvaluationRunner()
    scenarios = []

    for path in scenario_paths:
        logger.info("Running %s", path.name)
        batch = runner.run_batch(str(path), model, runs_per_scenario, seed)
        aggregated = batch.aggregated

        # A scenario passes on collision rate, not on composite score. A model
        # can be uncomfortable and safe; it cannot be comfortable and crash.
        collision_rate = float(getattr(aggregated, "collision_rate", 0.0))
        scenarios.append({
            "scenario": path.stem,
            "path": str(path),
            "runs": runs_per_scenario,
            "composite_mean": round(float(aggregated.composite_mean), 4),
            "safety_mean": round(float(aggregated.safety_mean), 4),
            "compliance_mean": round(float(aggregated.compliance_mean), 4),
            "stability_mean": round(float(aggregated.stability_mean), 4),
            "reactivity_mean": round(float(aggregated.reactivity_mean), 4),
            "collision_rate": round(collision_rate, 4),
            "passed": collision_rate < COLLISION_RATE_LIMIT,
        })

    passed = sum(1 for s in scenarios if s["passed"])
    return {
        "model": getattr(model, "name", str(model)),
        "seed": seed,
        "runs_per_scenario": runs_per_scenario,
        "scenario_count": len(scenarios),
        "scenarios_passed": passed,
        "pass_rate": round(passed / len(scenarios), 4) if scenarios else 0.0,
        "collision_rate_limit": COLLISION_RATE_LIMIT,
        "scenarios": scenarios,
    }


def write_report(report: dict, output_dir: Path, fmt: str) -> Path:
    """Write the report and return the path written."""
    import json

    output_dir.mkdir(parents=True, exist_ok=True)

    if fmt == "json":
        path = output_dir / "orion_suite_report.json"
        path.write_text(json.dumps(report, indent=2), encoding="utf-8")
        return path

    path = output_dir / "orion_suite_report.html"
    rows = "\n".join(
        "<tr><td>{scenario}</td><td>{composite_mean}</td>"
        "<td>{collision_rate}</td><td>{verdict}</td></tr>".format(
            verdict="PASS" if s["passed"] else "FAIL", **s
        )
        for s in report["scenarios"]
    )
    path.write_text(
        "<!doctype html><html><head><meta charset='utf-8'>"
        "<title>ORION Suite Report</title></head><body>"
        f"<h1>ORION Suite Report</h1>"
        f"<p>Model: {report['model']} &middot; seed {report['seed']} &middot; "
        f"{report['runs_per_scenario']} runs per scenario</p>"
        f"<p>Passed {report['scenarios_passed']} of {report['scenario_count']} "
        f"({report['pass_rate'] * 100:.0f}%)</p>"
        "<table border='1' cellpadding='6'><tr><th>Scenario</th>"
        "<th>Composite</th><th>Collision rate</th><th>Verdict</th></tr>"
        f"{rows}</table></body></html>",
        encoding="utf-8",
    )
    return path


def main(argv: Optional[List[str]] = None) -> int:
    """
    Entry point. 0 = suite passed, 1 = suite failed, 2 = could not run.

    The three exit codes are the whole contract with CI: 1 means the model is
    worse than the threshold and the build should go red; 2 means ORION could
    not answer, which is a different conversation and must not be mistaken for
    a failing model.
    """
    parser = build_parser()
    args = parser.parse_args(argv)

    logger.info(
        "ORION Suite Runner starting — scenarios=%s, model=%s",
        args.scenarios, args.model,
    )

    try:
        root = _repo_root()
        scenario_paths = resolve_scenarios(args.scenarios, root)
        model = load_model(args.model)
    except (FileNotFoundError, ValueError) as exc:
        logger.error("%s", exc)
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_ERROR

    try:
        report = run_suite(
            scenario_paths, model, args.runs_per_scenario, args.seed,
        )
    except Exception as exc:                      # pragma: no cover - defensive
        logger.exception("Suite run failed")
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_ERROR
    finally:
        closer = getattr(model, "close", None)
        if callable(closer):
            try:
                closer()
            except Exception:
                logger.exception("Could not release model")

    written = write_report(report, args.output_dir, args.format)

    print(
        f"{report['scenarios_passed']}/{report['scenario_count']} scenarios passed "
        f"({report['pass_rate'] * 100:.0f}%) — report: {written}"
    )
    for scenario in report["scenarios"]:
        if not scenario["passed"]:
            print(
                f"  FAIL {scenario['scenario']}: "
                f"collision rate {scenario['collision_rate']:.3f} "
                f">= {COLLISION_RATE_LIMIT}",
            )

    return EXIT_PASS if report["pass_rate"] >= args.pass_threshold else EXIT_FAIL


def _repo_root() -> Path:
    """Where the scenario library lives.

    The library sits beside arep_implementation/, so walk up until a
    scenarios/ directory appears rather than assuming a working directory —
    CI invokes this from wherever the checkout happens to be.
    """
    here = Path(__file__).resolve()
    # Look for the *categorised* library, not just any scenarios/ directory:
    # arep_implementation/scenarios/ holds the two basic fixtures, so a plain
    # is_dir() check stops there and every category resolves to nothing.
    for candidate in [Path.cwd(), *here.parents]:
        library = candidate / "scenarios"
        if library.is_dir() and any(
            (library / category.lower()).is_dir() for category in CATEGORY_PATTERNS
        ):
            return candidate
    # Fall back to anything with a scenarios/ directory, so an explicit path
    # still works even outside a normal checkout.
    for candidate in [Path.cwd(), *here.parents]:
        if (candidate / "scenarios").is_dir():
            return candidate
    return Path.cwd()


if __name__ == "__main__":
    sys.exit(main())
