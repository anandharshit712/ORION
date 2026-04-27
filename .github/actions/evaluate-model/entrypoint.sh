#!/bin/bash
# ORION GitHub Action entrypoint
# Called by the Docker container when the action runs.
set -e

python -m arep.cli.run_suite \
  --model "$ORION_MODEL_PATH" \
  --scenarios "$ORION_SCENARIOS" \
  --runs-per-scenario "$ORION_RUNS_PER_SCENARIO" \
  --pass-threshold "$ORION_PASS_THRESHOLD" \
  --output-dir /tmp/orion_results \
  --format json

# Write outputs for GitHub Actions
COMPOSITE=$(python -c "import json; d=json.load(open('/tmp/orion_results/report.json')); print(d.get('composite_mean', 0))")
PASSED=$(python -c "import json; d=json.load(open('/tmp/orion_results/report.json')); print('true' if d.get('passed') else 'false')")

echo "composite_score=$COMPOSITE" >> "$GITHUB_OUTPUT"
echo "passed=$PASSED" >> "$GITHUB_OUTPUT"
