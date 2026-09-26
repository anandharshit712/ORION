"""
The CI integration files are consumed by other people's pipelines (Phase 3.2).

They are never executed by our own test suite, which is exactly why they broke
without anyone noticing. Two defects shipped at once:

  - `action.yml` was not valid YAML. A value began with a quote and continued
    unquoted (`description: "true" if all scenarios...`), which GitHub rejects
    outright — the action could not load at all.
  - It ran `docker://ghcr.io/orioneval/cli:latest`, an image nobody built or
    pushed. `docker-build.yml` tagged the CLI locally inside the runner and the
    tag evaporated when the job ended, so the build looked green while
    publishing nothing.

Both failures land in a customer's pipeline rather than ours, and the roadmap
recorded the action as shipped. These tests parse the files the way GitHub
would and check the two halves agree.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

yaml = pytest.importorskip("yaml")

REPO = Path(__file__).resolve().parent.parent.parent
ACTION = REPO / ".github" / "actions" / "evaluate-model" / "action.yml"
DOCKER_BUILD = REPO / ".github" / "workflows" / "docker-build.yml"
COMPONENT = REPO / "ci" / "gitlab" / "templates" / "evaluate-model.yml"
ENTRYPOINT = REPO / "ci" / "orion-ci.sh"
DOCKERFILE = REPO / "infrastructure" / "docker" / "Dockerfile.cli"


def _load(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def test_the_action_is_valid_yaml():
    """It was not, for its whole existence. GitHub parses this before running
    anything, so a syntax error here is a total failure, not a warning."""
    assert ACTION.exists(), f"{ACTION} is missing"
    assert _load(ACTION), "action.yml parsed to nothing"


def test_the_docker_build_workflow_is_valid_yaml():
    assert _load(DOCKER_BUILD), "docker-build.yml parsed to nothing"


def test_the_action_runs_an_image_the_workflow_actually_publishes():
    """The defect that made the action unusable.

    GitHub does not allow expressions in a Docker action's `image`, so the
    owner cannot be templated and the two files have to agree by hand. A test
    is the only thing that keeps them in step.
    """
    action = _load(ACTION)
    image = action["runs"]["image"]
    assert image.startswith("docker://"), f"unexpected image reference {image!r}"

    repository = image.replace("docker://", "").rsplit(":", 1)[0]
    workflow_text = DOCKER_BUILD.read_text(encoding="utf-8")

    name = repository.rsplit("/", 1)[-1]
    assert name in workflow_text, (
        f"the action runs {repository!r} but docker-build.yml never builds an "
        f"image called {name!r}"
    )
    assert "docker push" in workflow_text, (
        "docker-build.yml builds images but never pushes one, so the action's "
        "image will not exist when a customer pulls it"
    )


def test_the_cli_image_is_pushed_not_just_built():
    """Tagging inside the runner and ending the job publishes nothing, while
    still showing a green build."""
    workflow = _load(DOCKER_BUILD)
    steps = workflow["jobs"]["build"]["steps"]
    pushes = [s for s in steps if "docker push" in str(s.get("run", ""))]

    assert pushes, "no step pushes an image"
    assert any(
        "orion-cli" in str(s.get("run", "")) for s in pushes
    ), "the CLI image is the one the action consumes, and it is not pushed"


def test_the_published_image_is_smoke_tested_before_it_is_pushed():
    """A published image that cannot start fails inside a customer's pipeline
    rather than ours."""
    workflow = _load(DOCKER_BUILD)
    steps = workflow["jobs"]["build"]["steps"]
    names = [str(s.get("name", "")) for s in steps]

    smoke = next((i for i, n in enumerate(names) if "Smoke-test" in n), None)
    push = next((i for i, n in enumerate(names) if n.startswith("Push")), None)

    assert smoke is not None, "the CLI image is pushed without being started once"
    assert push is not None, "no push step found"
    assert smoke < push, "the smoke test must run before the push, not after"


def test_pushing_requires_the_packages_permission():
    """Without it the login succeeds and the push fails with a 403 that reads
    like a credentials problem."""
    workflow = _load(DOCKER_BUILD)
    assert workflow.get("permissions", {}).get("packages") == "write"


def test_the_action_declares_the_inputs_the_roadmap_specifies():
    action = _load(ACTION)
    expected = {
        "api_key",
        "model_path",
        "scenarios",
        "runs_per_scenario",
        "pass_threshold",
        "fail_on_regression",
    }
    assert expected <= set(action["inputs"])


def test_only_the_model_path_is_required():
    """Every other input has a default, so the smallest usable step is three
    lines. A CI integration nobody can adopt in three lines does not get
    adopted.

    `api_key` used to be required and is not used by anything: the action runs
    the suite locally inside its own container. Requiring a secret to run code
    that never makes a request is a barrier for nothing.
    """
    action = _load(ACTION)
    required = {n for n, spec in action["inputs"].items() if spec.get("required")}
    assert required == {"model_path"}


# -- The entrypoint --------------------------------------------------------
#
# The third defect in the same feature, and the one that survived the first
# two fixes: the action configured itself entirely through ORION_* environment
# variables that nothing in the image read.


def test_the_action_overrides_the_image_entrypoint():
    """The image's own ENTRYPOINT is run_suite, which ignores those variables
    and runs with defaults. Without an override the action evaluated the wrong
    model, against every scenario, and produced no outputs."""
    action = _load(ACTION)
    assert action["runs"].get("entrypoint"), (
        "the action does not override the image entrypoint, so its env vars "
        "are read by nobody"
    )


def test_the_entrypoint_the_action_names_is_installed_in_the_image():
    """A script beside action.yml is not in a prebuilt image — GitHub mounts
    the workspace, not the action directory. It has to be COPYed in."""
    action = _load(ACTION)
    installed = action["runs"]["entrypoint"]

    dockerfile = DOCKERFILE.read_text(encoding="utf-8")
    assert (
        installed in dockerfile
    ), f"the action runs {installed} but Dockerfile.cli never installs it there"
    assert ENTRYPOINT.exists(), f"{ENTRYPOINT} is missing"


def test_the_entrypoint_does_not_abort_on_the_first_failure():
    """`set -e` would end the script the moment run_suite exits non-zero,
    losing the outputs and flattening exit 1 (model failed) into the same
    shape as any other error."""
    code = [
        line
        for line in ENTRYPOINT.read_text(encoding="utf-8").splitlines()
        if not line.lstrip().startswith("#")
    ]
    assert not any(line.strip().startswith("set -e") for line in code)
    assert any(
        "exit $STATUS" in line for line in code
    ), "the run_suite exit code must reach the caller"


def test_the_entrypoint_has_unix_line_endings():
    """A CRLF shell script does not fail as a shell script. The kernel reads
    the shebang as `/bin/sh\r`, finds no such interpreter, and the container
    dies with "no such file or directory" naming a file that plainly exists.

    `.gitattributes` pins `*.sh` to LF on checkout, which covers git. It does
    not cover a script writing the file through Python's default newline
    translation on Windows, which is how this one got CRLF'd between being
    written and being built into the image.
    """
    assert (
        b"\r\n" not in ENTRYPOINT.read_bytes()
    ), f"{ENTRYPOINT.name} has CRLF line endings and will not execute in the image"


def test_the_entrypoint_reads_every_variable_the_action_sets():
    """A variable the action sets and the script ignores is a silently
    ignored input — the customer's `runs_per_scenario: 50` does nothing and
    nothing says so."""
    action = _load(ACTION)
    script = ENTRYPOINT.read_text(encoding="utf-8")

    for name in action["runs"]["env"]:
        if name == "ORION_API_KEY":
            continue  # declared for the hosted path, deliberately unused
        assert name in script, f"the action sets {name} and the entrypoint ignores it"


def test_the_entrypoint_publishes_the_keys_the_action_declares_as_outputs():
    action = _load(ACTION)
    script = ENTRYPOINT.read_text(encoding="utf-8")

    for name in action["outputs"]:
        assert f'"{name}"' in script, f"output {name} is declared but never written"


# -- GitLab (3.3) ----------------------------------------------------------


def test_the_gitlab_component_is_valid_yaml_with_a_spec_header():
    """A component without a `spec:` document cannot declare inputs, and
    GitLab will not accept it into the catalogue."""
    docs = list(yaml.safe_load_all(COMPONENT.read_text(encoding="utf-8")))
    assert len(docs) == 2, "a component is a spec document then the job document"
    assert "inputs" in docs[0]["spec"]


def test_the_component_requires_only_the_model_path():
    """Same bar as the action: an input without a default is one the customer
    must supply."""
    spec = list(yaml.safe_load_all(COMPONENT.read_text(encoding="utf-8")))[0]
    required = {n for n, v in spec["spec"]["inputs"].items() if "default" not in v}
    assert required == {"model_path"}


def test_the_component_runs_the_same_image_as_the_action():
    """Two integrations of the same product scoring differently because one
    pinned an older image is a support case nobody can reproduce."""
    action_image = _load(ACTION)["runs"]["image"].replace("docker://", "")
    spec = list(yaml.safe_load_all(COMPONENT.read_text(encoding="utf-8")))[0]
    assert spec["spec"]["inputs"]["image"]["default"] == action_image


def test_the_component_clears_the_entrypoint_before_running_script():
    """GitLab runs `script:` inside the container. With run_suite still as the
    entrypoint, every line is handed to it as arguments and the job dies on
    the first one."""
    job = list(yaml.safe_load_all(COMPONENT.read_text(encoding="utf-8")))[1]
    settings = next(iter(job.values()))
    assert settings["image"]["entrypoint"] == [""]
    assert any("orion-ci" in line for line in settings["script"])


def test_the_component_collects_the_report_even_when_the_job_fails():
    """The report is most useful precisely when the job went red."""
    job = list(yaml.safe_load_all(COMPONENT.read_text(encoding="utf-8")))[1]
    settings = next(iter(job.values()))
    assert settings["artifacts"]["when"] == "always"


def test_the_dotenv_path_matches_what_the_entrypoint_writes():
    """GitLab reads job outputs from this exact file. A mismatch means the
    variables silently never appear downstream."""
    job = list(yaml.safe_load_all(COMPONENT.read_text(encoding="utf-8")))[1]
    settings = next(iter(job.values()))
    dotenv = settings["artifacts"]["reports"]["dotenv"]

    output_dir = settings["variables"]["ORION_OUTPUT_DIR"]
    assert dotenv == f"{output_dir}/orion.env"
    assert "orion.env" in ENTRYPOINT.read_text(encoding="utf-8")


def test_the_baseline_is_only_promoted_on_the_default_branch():
    """Letting a merge request overwrite the baseline lets a regression
    ratchet in one commit at a time — each pipeline compares against the
    slightly-worse one before it and never fires."""
    job = list(yaml.safe_load_all(COMPONENT.read_text(encoding="utf-8")))[1]
    script = " ".join(next(iter(job.values()))["script"])
    assert "CI_DEFAULT_BRANCH" in script


def test_the_roadmap_verifier_is_importable():
    """`scripts/verify_roadmap.py` is how a roadmap box gets ticked, and it is
    not part of any test run — a syntax error in it sits there until someone
    runs it by hand, at which point the thing that verifies claims is itself
    broken."""
    import ast

    script = REPO / "arep_implementation" / "scripts" / "verify_roadmap.py"
    ast.parse(script.read_text(encoding="utf-8"), filename=str(script))
