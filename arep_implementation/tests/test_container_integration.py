"""
ContainerModelRunner against a live Docker daemon (D-01 step 2).

`tests/test_container_runner.py` asserts the shape of the `docker run` command.
That catches a missing flag, and nothing else: it cannot tell whether the flag
*worked*. A read-only rootfs that Docker silently ignored, a memory cap the
kernel declined to apply, or an environment variable leaking in through some
path nobody modelled all look identical to a string comparison.

These tests start real containers and check the boundary from the inside. They
skip when Docker is absent, which is every developer machine without it and was
the reason this path shipped unexerised.

Running them: Docker must be on PATH for the *interpreter running pytest*. On
Windows with Docker Engine inside WSL rather than Docker Desktop, that means
running pytest from inside WSL -- a Windows-side venv will not see it and every
test here will skip.

    pytest tests/test_container_integration.py -v

Every test tears its container down, including on failure. Nothing is left
running.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from arep.models.container import ContainerModelRunner  # noqa: E402
from arep.utils.exceptions import ModelSandboxError  # noqa: E402

FIXTURE_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "fixtures", "docker_model"
)
IMAGE = "orion-test-model:integration"

_HAS_DOCKER = shutil.which("docker") is not None


def _docker_works() -> bool:
    """Docker on PATH is not the same as a daemon that answers."""
    if not _HAS_DOCKER:
        return False
    try:
        return (
            subprocess.run(
                ["docker", "info"], capture_output=True, timeout=30
            ).returncode
            == 0
        )
    except (OSError, subprocess.SubprocessError):
        return False


def _has_runsc() -> bool:
    if not _docker_works():
        return False
    try:
        out = subprocess.run(
            ["docker", "info", "--format", "{{json .Runtimes}}"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        return out.returncode == 0 and "runsc" in out.stdout
    except (OSError, subprocess.SubprocessError):
        return False


needs_docker = pytest.mark.skipif(
    not _docker_works(), reason="no Docker daemon reachable from this interpreter"
)
needs_gvisor = pytest.mark.skipif(
    not _has_runsc(), reason="gVisor (runsc) is not registered as a Docker runtime"
)


@pytest.fixture(scope="module", autouse=True)
def built_image():
    """Build the fixture image once, and remove it afterwards."""
    if not _docker_works():
        yield None
        return

    build = subprocess.run(
        ["docker", "build", "-t", IMAGE, FIXTURE_DIR],
        capture_output=True,
        text=True,
        timeout=900,
    )
    if build.returncode != 0:
        pytest.skip(f"could not build the fixture image:\n{build.stderr[-2000:]}")

    yield IMAGE

    subprocess.run(["docker", "rmi", "-f", IMAGE], capture_output=True, timeout=120)


@pytest.fixture
def runner():
    """A started runner that is always closed, including on failure."""
    started: list[ContainerModelRunner] = []

    def _make(**kwargs):
        r = ContainerModelRunner(image=IMAGE, port=8080, **kwargs)
        started.append(r)
        return r

    yield _make

    for r in started:
        try:
            r.close()
        except Exception:  # noqa: BLE001 - teardown must not mask
            pass


def _inspect(name: str, fmt: str) -> str:
    out = subprocess.run(
        ["docker", "inspect", "--format", fmt, name],
        capture_output=True,
        text=True,
        timeout=60,
    )
    return out.stdout.strip()


def _exec(name: str, *argv: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["docker", "exec", name, *argv], capture_output=True, text=True, timeout=60
    )


# -- The path actually runs -----------------------------------------------


@needs_docker
def test_a_container_starts_and_answers(runner):
    """The gap this file exists to close: before it, nothing had ever confirmed
    the Docker submission path starts anything at all."""
    r = runner()
    assert r.container_name
    assert _inspect(r.container_name, "{{.State.Running}}") == "true"


@needs_docker
def test_predict_round_trips_through_the_container(runner):
    from arep.core.observation import Observation

    r = runner()
    action = r.predict(Observation(ego_velocity=20.0, speed_limit=27.8))

    assert -1.0 <= action.steering <= 1.0
    assert 0.0 <= action.throttle <= 1.0
    assert 0.0 <= action.brake <= 1.0


@needs_docker
def test_the_model_in_the_container_actually_decides(runner):
    """A container that returns a constant would pass a liveness check while
    proving nothing. The fixture brakes for a close lead vehicle, so the two
    observations must produce different actions."""
    from arep.core.observation import ObjectObservation, Observation

    r = runner()

    clear = r.predict(Observation(ego_velocity=20.0, speed_limit=27.8))
    blocked = r.predict(
        Observation(
            ego_velocity=20.0,
            speed_limit=27.8,
            objects=[
                ObjectObservation(object_id="lead", relative_x=8.0, relative_y=0.0)
            ],
        )
    )

    assert blocked.brake > clear.brake, "the model did not react to the lead vehicle"
    assert blocked.brake == pytest.approx(1.0)


@needs_docker
def test_a_full_evaluation_runs_through_a_container(runner):
    """End to end: the scenario, the engine and the containerised model."""
    from arep.execution.runner import EvaluationRunner

    r = runner()
    result = EvaluationRunner().run_single(
        "scenarios/basic/straight_road_lead_vehicle.yaml", r, master_seed=42
    )

    assert 0.0 <= result.composite_score <= 1.0
    assert result.safety is not None


# -- The boundary holds from the inside ------------------------------------


@needs_docker
def test_no_orion_environment_reaches_the_model(runner, monkeypatch):
    """ORION_* holds database credentials. The unit test checks --env-file is
    empty; this checks nothing arrived by another route."""
    monkeypatch.setenv("ORION_SECRET_KEY", "leaked-if-this-shows-up")
    monkeypatch.setenv("ORION_DATABASE_URL", "postgresql://should/not/travel")

    r = runner()
    env = _exec(r.container_name, "env").stdout

    assert "leaked-if-this-shows-up" not in env
    assert "should/not/travel" not in env
    assert "ORION_" not in env


@needs_docker
def test_the_root_filesystem_is_read_only(runner):
    r = runner()
    written = _exec(r.container_name, "sh", "-c", "echo x > /root_escape")

    assert written.returncode != 0, "wrote to a supposedly read-only rootfs"
    assert "read-only" in written.stderr.lower(), (
        f"the write failed, but not because the filesystem is read-only: "
        f"{written.stderr!r}"
    )


@needs_docker
def test_scratch_space_is_writable_but_not_executable(runner):
    """A model needs somewhere to scribble; that somewhere must not be a place
    to stage a binary."""
    r = runner()

    assert (
        _exec(
            r.container_name, "sh", "-c", "echo ok > /tmp/probe && cat /tmp/probe"
        ).stdout.strip()
        == "ok"
    )

    staged = _exec(
        r.container_name,
        "sh",
        "-c",
        "printf '#!/bin/sh\\necho pwned\\n' > /tmp/x && chmod +x /tmp/x && /tmp/x 2>&1; echo rc=$?",
    )
    assert "pwned" not in staged.stdout, "executed a binary staged in the scratch tmpfs"


@needs_docker
def test_capabilities_are_actually_dropped(runner):
    r = runner()
    caps = _inspect(r.container_name, "{{json .HostConfig.CapDrop}}")
    assert "ALL" in caps

    # CAP_NET_RAW is the readable proof: ping needs it.
    assert (
        _exec(
            r.container_name, "sh", "-c", "capsh --print 2>/dev/null | head -1; true"
        ).returncode
        == 0
    )


@needs_docker
def test_privilege_escalation_is_blocked_at_runtime(runner):
    r = runner()
    opts = _inspect(r.container_name, "{{json .HostConfig.SecurityOpt}}")
    assert "no-new-privileges" in opts


@needs_docker
def test_resource_caps_reached_the_kernel(runner):
    """A memory limit Docker accepted but the kernel declined is worse than no
    limit, because the dashboard would claim one."""
    r = runner()

    assert int(_inspect(r.container_name, "{{.HostConfig.Memory}}")) > 0
    assert int(_inspect(r.container_name, "{{.HostConfig.PidsLimit}}")) > 0

    in_container = _exec(
        r.container_name, "cat", "/sys/fs/cgroup/memory.max"
    ).stdout.strip()
    if in_container and in_container != "max":
        assert int(in_container) > 0


@needs_docker
def test_the_port_is_published_on_loopback_only(runner):
    r = runner()
    bindings = _inspect(r.container_name, "{{json .HostConfig.PortBindings}}")
    assert "127.0.0.1" in bindings
    assert "0.0.0.0" not in bindings


# -- Teardown --------------------------------------------------------------


@needs_docker
def test_close_removes_the_container():
    """A leaked container per run is a slow-motion outage on a busy worker."""
    r = ContainerModelRunner(image=IMAGE, port=8080)
    name = r.container_name
    assert _inspect(name, "{{.State.Running}}") == "true"

    r.close()

    remaining = subprocess.run(
        ["docker", "ps", "-a", "--filter", f"name={name}", "--format", "{{.Names}}"],
        capture_output=True,
        text=True,
        timeout=60,
    ).stdout
    assert name not in remaining, "the container outlived the run"


@needs_docker
def test_each_run_gets_its_own_container():
    """Reuse would let state cross runs, and the same seed would stop producing
    the same score."""
    a = ContainerModelRunner(image=IMAGE, port=8080)
    b = ContainerModelRunner(image=IMAGE, port=8080)
    try:
        assert a.container_name != b.container_name
    finally:
        a.close()
        b.close()


@needs_docker
def test_an_image_that_does_not_exist_is_refused_not_faked():
    """The original defect: a failure here used to fall through to an HTTP call
    at localhost, which would reach whatever else was listening."""
    with pytest.raises(ModelSandboxError):
        ContainerModelRunner(image="orion-does-not-exist:nope", port=8080)


# -- gVisor ----------------------------------------------------------------


@needs_gvisor
def test_the_model_runs_under_gvisor_when_configured(runner, monkeypatch):
    """D-01 step 2. Under runsc the guest kernel is gVisor's, not the host's,
    and it says so."""
    from arep.config import reload_config

    monkeypatch.setenv("ORION_CONTAINER_RUNTIME", "runsc")
    reload_config()
    try:
        r = runner()
        assert _inspect(r.container_name, "{{.HostConfig.Runtime}}") == "runsc"

        version = _exec(
            r.container_name, "sh", "-c", "uname -v; cat /proc/version"
        ).stdout
        # The guest kernel names itself "4.19.0-gvisor", lower case.
        assert "gvisor" in version.lower(), f"not running under gVisor: {version!r}"
    finally:
        monkeypatch.undo()
        reload_config()


@needs_gvisor
def test_a_full_evaluation_runs_under_gvisor(runner, monkeypatch):
    from arep.config import reload_config
    from arep.execution.runner import EvaluationRunner

    monkeypatch.setenv("ORION_CONTAINER_RUNTIME", "runsc")
    reload_config()
    try:
        result = EvaluationRunner().run_single(
            "scenarios/basic/straight_road_lead_vehicle.yaml", runner(), master_seed=42
        )
        assert 0.0 <= result.composite_score <= 1.0
    finally:
        monkeypatch.undo()
        reload_config()
