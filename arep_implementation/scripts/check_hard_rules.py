"""
Mechanically enforce the CLAUDE.md hard rules (Phase 0.6, defect D-13).

Run:  python scripts/check_hard_rules.py

The determinism rules are the product's foundation — "run it 500 times and the
numbers mean something" is false the moment wall-clock or unseeded randomness
reaches the simulation. Rules that live only in a document get broken by people
who have not read it, and get broken again after the fix. This makes them fail
the build.

An AST walk rather than grep: grep cannot tell `time.time()` in code from
`time.time()` in a docstring explaining why it is not there, and `# noqa`-style
special cases pile up fast.

Exits non-zero on the first violation set, listing file and line.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

# Packages that must be a pure function of (seed, scenario). The API, worker and
# database layers legitimately use wall-clock and are not checked.
PURE_PACKAGES = ("arep/core", "arep/simulation", "arep/evaluation")

# Calls that make a run unreproducible.
BANNED_CALLS = {
    ("time", "time"): "time.time() — use world.sim_time",
    ("datetime", "now"): "datetime.now() — use world.sim_time",
    ("datetime", "utcnow"): "datetime.utcnow() — use world.sim_time",
}

# Modules that supply unseeded randomness. All randomness goes through
# RandomManager, which is seeded per run.
BANNED_IMPORTS = {
    "random": "import random — use RandomManager, seeded per run",
}

# time.monotonic() is deliberately absent from BANNED_CALLS. SimulationEngine
# .run_async uses it to pace live delivery: it changes *when* a frame reaches a
# socket, never what the frame contains, and removing it would mean the live
# viewer could not run at wall-clock speed.


class _Visitor(ast.NodeVisitor):
    def __init__(self, path: Path):
        self.path = path
        self.violations: list[tuple[int, str]] = []

    def visit_Call(self, node: ast.Call) -> None:
        func = node.func
        if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
            key = (func.value.id, func.attr)
            if key in BANNED_CALLS:
                self.violations.append((node.lineno, BANNED_CALLS[key]))
        self.generic_visit(node)

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            if alias.name in BANNED_IMPORTS:
                self.violations.append((node.lineno, BANNED_IMPORTS[alias.name]))
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        if node.module in BANNED_IMPORTS:
            self.violations.append((node.lineno, BANNED_IMPORTS[node.module]))
        self.generic_visit(node)


def check() -> list[str]:
    failures: list[str] = []
    checked = 0

    for package in PURE_PACKAGES:
        root = REPO / package
        if not root.is_dir():
            failures.append(f"{package}: package not found — has it moved?")
            continue

        for path in sorted(root.rglob("*.py")):
            checked += 1
            try:
                tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            except SyntaxError as exc:
                failures.append(f"{path.relative_to(REPO)}: cannot parse — {exc}")
                continue

            visitor = _Visitor(path)
            visitor.visit(tree)
            for lineno, reason in visitor.violations:
                failures.append(f"{path.relative_to(REPO)}:{lineno}: {reason}")

    # A silent zero-file walk would pass forever after a refactor moved things.
    if checked == 0:
        failures.append("no files were checked — the package paths are wrong")

    print(f"checked {checked} files across {', '.join(PURE_PACKAGES)}")
    return failures


def main() -> int:
    failures = check()
    if failures:
        print("\nHard-rule violations (see CLAUDE.md section 12):\n")
        for failure in failures:
            print(f"  {failure}")
        print(
            "\nThese rules keep a run reproducible. If a wall-clock read is "
            "genuinely needed,\nit belongs outside the simulation packages — at "
            "the transport or API layer."
        )
        return 1

    print("hard rules: clean")
    return 0


if __name__ == "__main__":
    sys.exit(main())
