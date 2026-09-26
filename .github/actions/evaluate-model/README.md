# ORION Safety Evaluation — GitHub Action

Runs the ORION scenario suite against your model and fails the check when it
regresses or drops below threshold. The evaluation happens inside the action's
own container: no ORION account, no API key, nothing leaves the runner.

```yaml
- uses: anandharshit712/ORION/.github/actions/evaluate-model@main
  id: orion
  with:
    model_path: myproject.model.MyModel

- run: echo "composite ${{ steps.orion.outputs.composite_score }}"
```

Your model has to be importable inside the container, so install your package
into it first, or publish it and add a step that `pip install`s it. The action
mounts the workspace, so a `pip install -e .` in a prior step is not enough —
the container is a different Python environment.

## Exit codes

`0` passed, `1` the model failed, `2` ORION could not answer. Keep the last two
apart in any pipeline logic: a failing model and a broken harness call for
different responses.

## Failing on regressions

The regression check needs a previous report. Restore one from the last run on
your default branch and point the action at it:

```yaml
- uses: actions/cache/restore@v4
  with:
    path: orion-baseline
    key: orion-baseline-${{ github.event.repository.default_branch }}

- uses: anandharshit712/ORION/.github/actions/evaluate-model@main
  with:
    model_path: myproject.model.MyModel
    baseline_report: orion-baseline/orion_suite_report.json

- if: github.ref_name == github.event.repository.default_branch
  run: mkdir -p orion-baseline && cp orion-results/orion_suite_report.json orion-baseline/
- if: github.ref_name == github.event.repository.default_branch
  uses: actions/cache/save@v4
  with:
    path: orion-baseline
    key: orion-baseline-${{ github.event.repository.default_branch }}
```

A missing baseline is the normal first run and is skipped, not an error.
Saving the baseline only on the default branch is deliberate — letting a pull
request overwrite it means a regression can ratchet in one commit at a time.

Thresholds are the platform-wide ones in `arep/analysis/regression_detector.py`
(composite −5%, safety −10%, collision rate +1pp), compared per scenario rather
than on the mean: a model that gains a little on four scenarios and loses a lot
on the fifth has a flat mean and a new way to crash.

## Inputs and outputs

See `action.yml`. Everything except `model_path` has a default. `api_key` is
declared for the future hosted path and is unused by this action.

The GitLab equivalent lives in [`ci/gitlab/`](../../../ci/gitlab/) and shares
the same image and entrypoint.
