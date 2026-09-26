#!/bin/sh
# ORION CI entrypoint — shared by the GitHub Action and the GitLab component.
#
# Both integrations are "run the suite, publish the numbers, set the exit
# code". Writing that twice guarantees the two drift, and a CI integration
# drifts silently: nobody runs the other platform's pipeline. So one script,
# configured by environment variables, baked into the CLI image.
#
# It must not use `set -e`. The whole point is the exit code from run_suite —
# 1 (the model failed) and 2 (ORION could not answer) mean different things and
# both have to survive to the caller. Aborting on the first non-zero command
# would lose the outputs and flatten the distinction.
set -u

MODEL="${ORION_MODEL_PATH:-}"
if [ -z "$MODEL" ]; then
  echo "error: ORION_MODEL_PATH is required (import path to your ModelInterface class)" >&2
  exit 2
fi

SCENARIOS="${ORION_SCENARIOS:-all}"
RUNS="${ORION_RUNS_PER_SCENARIO:-10}"
THRESHOLD="${ORION_PASS_THRESHOLD:-0.80}"
SEED="${ORION_SEED:-42}"
# Relative by default so the report lands in the checkout on both platforms and
# can be collected as an artifact. An absolute /tmp path is invisible to both.
OUTPUT_DIR="${ORION_OUTPUT_DIR:-orion-results}"
BASELINE="${ORION_BASELINE_REPORT:-}"
FAIL_ON_REGRESSION="${ORION_FAIL_ON_REGRESSION:-true}"

set -- --model "$MODEL" \
  --scenarios "$SCENARIOS" \
  --runs-per-scenario "$RUNS" \
  --pass-threshold "$THRESHOLD" \
  --seed "$SEED" \
  --output-dir "$OUTPUT_DIR" \
  --format json

if [ -n "$BASELINE" ]; then
  set -- "$@" --baseline "$BASELINE"
  if [ "$FAIL_ON_REGRESSION" != "true" ]; then
    set -- "$@" --no-fail-on-regression
  fi
fi

python -m arep.cli.run_suite "$@"
STATUS=$?

REPORT="$OUTPUT_DIR/orion_suite_report.json"
if [ ! -f "$REPORT" ]; then
  # Exit 2 territory: the suite never got far enough to write anything. Say so
  # rather than reporting a composite of 0, which reads like a model that
  # crashes everywhere.
  echo "error: no report at $REPORT — the suite did not complete" >&2
  exit 2
fi

# Written as key=value so it serves as a GitLab dotenv report unchanged. Keys
# come from the report itself; a missing key prints empty rather than crashing
# the summary step after a run that actually happened.
python - "$REPORT" "$STATUS" <<'PY' > "$OUTPUT_DIR/orion.env"
import json, sys

report = json.load(open(sys.argv[1], encoding="utf-8"))
# The verdict is the exit code, not a second opinion derived from the numbers.
# A regression against the baseline fails the build while every scenario is
# still under the collision limit, so a recomputed "passed" would contradict
# the code the pipeline acted on.
status = sys.argv[2]
pairs = {
    "composite_score": report.get("composite_mean", ""),
    "safety_score": report.get("safety_mean", ""),
    "collision_rate": report.get("collision_rate", ""),
    "pass_rate": report.get("pass_rate", ""),
    "scenarios_passed": report.get("scenarios_passed", ""),
    "scenario_count": report.get("scenario_count", ""),
    "passed": "true" if status == "0" else "false",
}
for key, value in pairs.items():
    print(f"{key}={value}")
PY

# GitHub reads step outputs from a file it points at; GitLab reads the dotenv
# artifact above. Same content, two delivery mechanisms.
if [ -n "${GITHUB_OUTPUT:-}" ]; then
  cat "$OUTPUT_DIR/orion.env" >> "$GITHUB_OUTPUT"
fi

cat "$OUTPUT_DIR/orion.env"
exit $STATUS
