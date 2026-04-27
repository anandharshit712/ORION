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
import json
import sys
from pathlib import Path

from arep.utils.logging_config import get_logger

logger = get_logger("cli.run_suite")

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


def main() -> int:
    """
    Main entrypoint. Returns exit code (0=pass, 1=fail, 2=error).

    TODO [P3]: Resolve scenario paths from --scenarios argument.
    TODO [P3]: Load model from --model (built-in or dynamic import).
    TODO [P3]: Run EvaluationRunner.run_batch() for each scenario.
    TODO [P3]: Aggregate results across all scenarios.
    TODO [P3]: Write report to --output-dir in specified format.
    TODO [P3]: Return 0 if overall pass_rate >= pass_threshold, else 1.
    """
    parser = build_parser()
    args = parser.parse_args()

    logger.info(f"ORION Suite Runner starting — scenarios={args.scenarios}, model={args.model}")

    # TODO [P3]: Implement main()
    raise NotImplementedError("run_suite.main() not yet implemented [P3]")


if __name__ == "__main__":
    sys.exit(main())
