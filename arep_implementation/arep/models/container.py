"""
Container lifecycle for Docker-submitted customer models (Phase 2, D-01 step 2).

Before this existed, the "Docker submission path" started nothing. `resolve_model`
returned an `HttpModelAdapter` pointed at ``http://localhost:<port>`` with a comment
saying the caller owned the container lifecycle — and no caller did. So a registered
Docker model either failed to connect, or connected to whatever happened to be
listening on that port on the API host. The path the pickle gate tells customers to
use instead ("use the Docker submission path") was the one with no boundary at all.

What this adds, per run:

  - a container started from the customer's image and torn down afterwards
  - ``--cap-drop=ALL`` and ``--security-opt=no-new-privileges`` so the image cannot
    acquire privileges it was not given
  - ``--read-only`` with a small tmpfs, so a model can scribble but not persist
  - memory, CPU and PID limits, the last of which is what stops a fork bomb
  - the port published on 127.0.0.1 only, never 0.0.0.0
  - no environment inherited from the API process — the same rule the subprocess
    sandbox already follows, because ORION_* holds database credentials

and, when configured, ``--runtime=runsc`` (gVisor): a user-space kernel between the
model and the host. That is the isolation D-01 step 2 was waiting for. It is opt-in
because gVisor is not installed on a development machine, and
``require_hardened_runtime`` makes production refuse to run customer code without it.

**Untested against a live Docker daemon.** The command construction is covered by
unit tests; the execution path has not been exercised on this machine, which has no
Docker. Treat the first real deployment as the integration test.
"""

from __future__ import annotations

import shutil
import subprocess
import time
import uuid
from typing import List, Optional

from arep.config import get_config
from arep.core.action import Action
from arep.core.observation import Observation
from arep.models.http_adapter import HttpModelAdapter
from arep.models.interface import ModelInterface
from arep.utils.exceptions import ModelSandboxError
from arep.utils.logging_config import get_logger

logger = get_logger("models.container")


class ContainerModelRunner(ModelInterface):
    """Runs a customer's Docker image for the lifetime of one run.

    One container per run, never reused: a model that carries state across runs
    would make the same seed produce different scores, which is the one thing
    the platform promises it will not do.
    """

    def __init__(self, image: str, port: int = 8080, org_id: Optional[str] = None):
        self.image = image
        self.container_port = port
        self.org_id = org_id
        self.container_name = f"orion-model-{uuid.uuid4().hex[:12]}"
        self._adapter: Optional[HttpModelAdapter] = None
        self._started = False

        self._start()

    # ── Lifecycle ────────────────────────────────────────────────────

    def _start(self) -> None:
        cfg = get_config().sandbox

        if shutil.which("docker") is None:
            raise ModelSandboxError(
                "Docker is not available on this host, so a Docker-submitted "
                "model cannot be run. Refusing rather than falling back to an "
                "unsandboxed HTTP call."
            )

        if cfg.require_hardened_runtime and not cfg.container_runtime:
            raise ModelSandboxError(
                "require_hardened_runtime is set but no container_runtime is "
                "configured. Set ORION_CONTAINER_RUNTIME=runsc (gVisor), or "
                "clear the requirement — customer code will not be run under "
                "the default runtime while this is on."
            )

        host_port = _free_port()
        command = self._build_command(cfg, host_port)

        logger.info(
            "Starting model container %s from %s", self.container_name, self.image
        )
        try:
            subprocess.run(command, check=True, capture_output=True, timeout=60)
        except subprocess.CalledProcessError as exc:
            stderr = (exc.stderr or b"").decode(errors="replace")[:500]
            raise ModelSandboxError(
                f"Could not start the model container: {stderr}"
            ) from exc
        except subprocess.TimeoutExpired as exc:
            raise ModelSandboxError("Timed out starting the model container") from exc

        self._started = True
        self._await_ready(host_port, cfg.container_start_timeout_s)
        self._adapter = HttpModelAdapter(base_url=f"http://127.0.0.1:{host_port}")

    def _build_command(self, cfg, host_port: int) -> List[str]:
        """Compose the docker run invocation.

        Split out so the flags can be asserted in a test without a daemon — the
        isolation here is only as good as this argument list, and a silently
        dropped --cap-drop is invisible at runtime.
        """
        command = [
            "docker",
            "run",
            "--detach",
            "--rm",
            "--name",
            self.container_name,
            # Bind to loopback only. Published on 0.0.0.0 the customer's model
            # would be reachable from outside the host.
            "--publish",
            f"127.0.0.1:{host_port}:{self.container_port}",
            "--memory",
            cfg.container_memory,
            "--cpus",
            cfg.container_cpus,
            "--pids-limit",
            str(cfg.container_pids_limit),
            "--cap-drop",
            "ALL",
            "--security-opt",
            "no-new-privileges",
            # Writable only in a small tmpfs: a model may need scratch space,
            # and nothing it writes should outlive the run.
            "--read-only",
            "--tmpfs",
            "/tmp:rw,noexec,nosuid,size=64m",
            # No inherited environment. The API process holds ORION_* database
            # credentials, and the subprocess sandbox already refuses to pass
            # them on for the same reason.
            "--env-file",
            _empty_env_file(),
        ]

        if cfg.container_runtime:
            command += ["--runtime", cfg.container_runtime]

        command.append(self.image)
        return command

    def _await_ready(self, host_port: int, timeout: float) -> None:
        """Poll until the model answers, then hand over.

        A container that starts and never serves is a hang, and a hang during a
        batch is indistinguishable from a slow model unless it is bounded here.
        """
        import urllib.error
        import urllib.request

        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                with urllib.request.urlopen(
                    f"http://127.0.0.1:{host_port}/health", timeout=2.0
                ) as response:
                    if response.status == 200:
                        return
            except (urllib.error.URLError, OSError):
                time.sleep(0.25)

        self.close()
        raise ModelSandboxError(
            f"Model container did not become ready within {timeout:g}s. "
            f"The image must serve GET /health on port {self.container_port}."
        )

    def close(self) -> None:
        """Stop and remove the container. Safe to call more than once.

        EvaluationRunner._release_model calls this in a finally; without it
        every run would leak a container.
        """
        if not self._started:
            return
        self._started = False
        try:
            subprocess.run(
                ["docker", "kill", self.container_name],
                check=False,
                capture_output=True,
                timeout=30,
            )
        except Exception:
            logger.exception("Could not stop container %s", self.container_name)

    # ── ModelInterface ───────────────────────────────────────────────

    def predict(self, observation: Observation) -> Action:
        if self._adapter is None:
            raise ModelSandboxError("Model container is not running")
        return self._adapter.predict(observation)

    def reset(self) -> None:
        if self._adapter is not None:
            self._adapter.reset()

    @property
    def name(self) -> str:
        return f"Container({self.image})"


def _free_port() -> int:
    """Ask the OS for an unused port.

    Racy in principle — the port is free when asked and bound a moment later by
    Docker — but the alternative is a fixed port, which collides whenever two
    runs overlap on one host, and overlapping runs are the normal case.
    """
    import socket

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


_EMPTY_ENV_FILE: Optional[str] = None


def _empty_env_file() -> str:
    """Path to an empty env file, created once per process.

    `--env-file` with an empty file is how you tell Docker to pass nothing;
    omitting the flag would let the daemon's own environment through.
    """
    global _EMPTY_ENV_FILE
    if _EMPTY_ENV_FILE is None:
        import tempfile

        handle = tempfile.NamedTemporaryFile(
            prefix="orion-empty-env-", suffix=".env", delete=False, mode="w"
        )
        handle.close()
        _EMPTY_ENV_FILE = handle.name
    return _EMPTY_ENV_FILE
