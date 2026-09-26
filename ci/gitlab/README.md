# ORION GitLab CI component

The component source for `evaluate-model`. It runs the same image, the same
entrypoint and the same suite as the GitHub Action — the only difference is how
each platform collects outputs.

## Using it without publishing anything

A component is a convenience, not a requirement. Any GitLab project can run the
suite today with a job that pulls the public image:

```yaml
orion-evaluate:
  stage: test
  image:
    name: ghcr.io/anandharshit712/orion-cli:latest
    entrypoint: [""]
  variables:
    ORION_MODEL_PATH: myproject.model.MyModel
    ORION_SCENARIOS: all
    ORION_RUNS_PER_SCENARIO: "10"
    ORION_PASS_THRESHOLD: "0.80"
  script:
    - /usr/local/bin/orion-ci
  artifacts:
    when: always
    paths:
      - orion-results/
    reports:
      dotenv: orion-results/orion.env
```

The job exits `0` when the suite passed, `1` when the model failed, and `2`
when ORION could not answer. Keep `1` and `2` apart in any pipeline logic: a
failing model and a broken harness are different conversations.

To fail on regressions as well, restore the previous report and point
`ORION_BASELINE_REPORT` at it. `templates/evaluate-model.yml` does this with a
cache keyed on the default branch, which is worth copying — comparing a feature
branch against its own previous pipeline lets a regression ratchet in one
commit at a time.

## Publishing the component

**Not done, and not doable from this repository.** A GitLab CI/CD component is
published from a GitLab project, and ORION is hosted on GitHub. The artefact
here is complete; only the hosting is missing.

When the `gitlab.com/orioneval` namespace exists:

1. Create the project `orioneval/evaluate-model`.
2. Push the contents of this directory as the project root, so the file lands
   at `templates/evaluate-model.yml`. The path is fixed: GitLab resolves
   `<project>/<component>` to `templates/<component>.yml`.
3. Add a `.gitlab-ci.yml` to that project that runs the component against a
   built-in model — a component with no pipeline of its own cannot be released.
4. Tag a semantic version (`1.0.0`) and create a release. GitLab only lists a
   component in the catalogue once it has a release.
5. Set the project to **public** and tick *CI/CD Catalog resource* in settings.

After that, `@1` resolves to the latest 1.x and the snippet above becomes:

```yaml
include:
  - component: $CI_SERVER_FQDN/orioneval/evaluate-model/evaluate-model@1
    inputs:
      model_path: myproject.model.MyModel
```

## Why the image reference is written out in full

GitLab allows the image to be overridden through the `image` input, so a mirror
or a pinned digest needs no fork. The default has to match what
`.github/workflows/docker-build.yml` pushes; `tests/test_ci_integration_files.py`
asserts that it still does, because nothing else would notice it drifting.
