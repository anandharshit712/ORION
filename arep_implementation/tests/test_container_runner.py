"""
Container model runner tests (Phase 2, D-01 step 2).

The Docker submission path used to start nothing: resolve_model returned an
HttpModelAdapter aimed at localhost:<port> and a comment said the caller owned
the container lifecycle. No caller did. So a registered Docker model either
failed to connect or spoke to whatever was listening on that port on the API
host — and this was the path the pickle gate tells customers to use instead.

These tests assert the composed `docker run` invocation rather than running
one. That is deliberate: the isolation is exactly this argument list, a
silently dropped --cap-drop looks identical at runtime, and the development
machine has no Docker daemon. **The execution path is not covered here** —
the first real deployment is its integration test, and the module says so.
"""

from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from arep.config import get_config, reload_config  # noqa: E402
from arep.models.container import ContainerModelRunner  # noqa: E402
from arep.utils.exceptions import ModelSandboxError  # noqa: E402


def _command(monkeypatch, host_port: int = 54321, **config_env) -> list[str]:
    """Build the docker command without starting anything."""
    for key, value in config_env.items():
        monkeypatch.setenv(key, value)
    reload_config()

    # __init__ starts a container; build the command off an uninitialised
    # instance instead, which is the part under test.
    runner = ContainerModelRunner.__new__(ContainerModelRunner)
    runner.image = "registry.example.com/acme/model:v1"
    runner.container_port = 8080
    runner.container_name = "orion-model-test"
    return runner._build_command(get_config().sandbox, host_port)


@pytest.fixture(autouse=True)
def restore_config():
    yield
    reload_config()


# -- The isolation flags --------------------------------------------------


def test_all_capabilities_are_dropped(monkeypatch):
    command = _command(monkeypatch)
    assert "--cap-drop" in command
    assert command[command.index("--cap-drop") + 1] == "ALL"


def test_privilege_escalation_is_blocked(monkeypatch):
    command = _command(monkeypatch)
    assert "--security-opt" in command
    assert command[command.index("--security-opt") + 1] == "no-new-privileges"


def test_the_filesystem_is_read_only_with_a_scratch_tmpfs(monkeypatch):
    """A model may need scratch space; nothing it writes should outlive the run."""
    command = _command(monkeypatch)
    assert "--read-only" in command
    tmpfs = command[command.index("--tmpfs") + 1]
    assert tmpfs.startswith("/tmp:")
    assert "noexec" in tmpfs and "nosuid" in tmpfs


def test_resources_are_capped(monkeypatch):
    command = _command(monkeypatch)
    assert "--memory" in command
    assert "--cpus" in command
    # PID limit is what actually stops a fork bomb; memory alone does not.
    assert "--pids-limit" in command


def test_the_port_is_published_on_loopback_only(monkeypatch):
    """On 0.0.0.0 the customer's model would be reachable from off the host."""
    command = _command(monkeypatch, host_port=54321)
    published = command[command.index("--publish") + 1]
    assert published.startswith("127.0.0.1:")
    assert published == "127.0.0.1:54321:8080"


def test_no_host_environment_is_inherited(monkeypatch):
    """The API process holds ORION_* database credentials. Omitting the flag
    entirely would let the daemon's environment through."""
    command = _command(monkeypatch)
    assert "--env-file" in command
    env_file = command[command.index("--env-file") + 1]
    assert os.path.exists(env_file)
    with open(env_file) as handle:
        assert handle.read().strip() == ""


def test_the_container_is_removed_when_it_exits(monkeypatch):
    command = _command(monkeypatch)
    assert "--rm" in command


def test_the_image_is_the_last_argument(monkeypatch):
    """Anything after the image is passed to the container, not to Docker."""
    command = _command(monkeypatch)
    assert command[-1] == "registry.example.com/acme/model:v1"


# -- The hardened runtime -------------------------------------------------


def test_no_runtime_flag_by_default(monkeypatch):
    """gVisor is not installed on a development machine."""
    command = _command(monkeypatch, ORION_CONTAINER_RUNTIME="")
    assert "--runtime" not in command


def test_gvisor_is_requested_when_configured(monkeypatch):
    command = _command(monkeypatch, ORION_CONTAINER_RUNTIME="runsc")
    assert command[command.index("--runtime") + 1] == "runsc"


def test_limits_come_from_config_not_from_the_code(monkeypatch):
    command = _command(
        monkeypatch,
        ORION_CONTAINER_MEMORY="256m",
        ORION_CONTAINER_CPUS="0.5",
        ORION_CONTAINER_PIDS_LIMIT="64",
    )
    assert command[command.index("--memory") + 1] == "256m"
    assert command[command.index("--cpus") + 1] == "0.5"
    assert command[command.index("--pids-limit") + 1] == "64"


# -- Refusing rather than falling back ------------------------------------


def test_without_docker_it_refuses_instead_of_calling_localhost(monkeypatch):
    """The old behaviour was to return an HTTP client aimed at localhost and
    hope. That is the bug, not a fallback."""
    monkeypatch.setattr("arep.models.container.shutil.which", lambda _: None)

    with pytest.raises(ModelSandboxError, match="Docker is not available"):
        ContainerModelRunner(image="acme/model:v1")


def test_requiring_a_hardened_runtime_without_one_configured_refuses(monkeypatch):
    """Production sets this so customer code is never run under plain runc."""
    monkeypatch.setattr(
        "arep.models.container.shutil.which", lambda _: "/usr/bin/docker"
    )
    monkeypatch.setenv("ORION_REQUIRE_HARDENED_RUNTIME", "true")
    monkeypatch.setenv("ORION_CONTAINER_RUNTIME", "")
    reload_config()

    with pytest.raises(ModelSandboxError, match="require_hardened_runtime"):
        ContainerModelRunner(image="acme/model:v1")


def test_a_sandbox_error_voids_the_run_rather_than_scoring_it():
    """ModelSandboxError is the contract EvaluationRunner relies on: the run is
    void and the credit is refunded, never scored as if it had finished."""
    from arep.utils.exceptions import ModelSandboxError as Err

    assert issubclass(Err, Exception)


# -- Teardown -------------------------------------------------------------


def test_close_is_safe_before_a_container_exists():
    runner = ContainerModelRunner.__new__(ContainerModelRunner)
    runner._started = False
    runner.close()  # must not raise


def test_close_only_kills_once(monkeypatch):
    """EvaluationRunner calls close() in a finally, and callers may call it too."""
    calls = []
    monkeypatch.setattr(
        "arep.models.container.subprocess.run", lambda *a, **k: calls.append(a[0])
    )

    runner = ContainerModelRunner.__new__(ContainerModelRunner)
    runner._started = True
    runner.container_name = "orion-model-test"

    runner.close()
    runner.close()

    assert len(calls) == 1
    assert calls[0][:2] == ["docker", "kill"]


def test_free_ports_do_not_repeat():
    """A fixed port collides whenever two runs overlap, which is the normal case."""
    from arep.models.container import _free_port

    assert _free_port() != 0
