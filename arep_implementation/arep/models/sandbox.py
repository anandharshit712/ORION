"""
ORION Subprocess Model Sandbox.  [Phase 0.2 — defect D-01]

Runs a cloudpickle-serialised ``ModelInterface`` in an isolated subprocess.

A customer artefact is hostile input: unpickling it executes arbitrary Python.
The containment here is the *interim* lockdown specified in docs/ROADMAP.md
section 0.2, and it is what stands between one malicious upload and every org's
data:

  - **Environment stripped** to an explicit whitelist. No ``ORION_*`` variables
    reach the child, so the database URL, JWT secret and broker URL are not
    readable from inside a model.
  - **Network blocked.** On Linux with user namespaces available the child runs
    in its own empty network namespace (kernel-enforced). Everywhere else a
    Python-level block is installed *before* the artefact is unpickled. The
    in-process block is a speed bump, not a boundary — see SECURITY below.
  - **Filesystem**: the child's working directory is a fresh empty temp dir,
    which is also its ``TMPDIR`` and ``HOME``. The artefact is read once at
    startup and the file is removed immediately after.
  - **Resource limits** (POSIX): CPU seconds, address space, file size, open
    files, all applied via ``setrlimit`` in ``preexec_fn``.
  - **Hard wall-clock kill**: every ``predict()``/``reset()`` round trip has a
    deadline, and the run as a whole has a budget. A model that hangs is
    SIGKILLed (whole process group) and the run fails loudly — callers refund
    the credit. There is no silent "model was slow" path.

SECURITY — known ceiling of this layer:
    A determined attacker with arbitrary code execution can still read files
    this process can read (the source tree is on ``PYTHONPATH``), and on
    non-Linux hosts can bypass the Python-level network block via ``ctypes`` or
    a subprocess. Closing that requires an OS-level jail, which is Step 2 of
    0.2: gVisor (``runsc``) or a Firecracker microVM, container-per-run, before
    open self-serve signup. Until then the cloudpickle path is gated per-org
    (``organisations.allow_pickle_models``, default False) and the Docker path
    is the default for untrusted tenants.
"""

from __future__ import annotations

import json
import os
import queue
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path
from typing import Optional

import arep
from arep.config import SandboxConfig, get_config
from arep.core.action import Action
from arep.core.observation import Observation
from arep.models.interface import ModelInterface
from arep.utils.exceptions import ModelSandboxError
from arep.utils.logging_config import get_logger

logger = get_logger("models.sandbox")

__all__ = ["SubprocessModelRunner", "ModelSandboxError"]




# Environment variables the child is allowed to inherit. Everything else —
# above all ORION_* — is dropped. Keep this list minimal; each entry is a
# decision that the value is not sensitive and the interpreter needs it.
_ENV_WHITELIST = (
    "PATH",
    "SYSTEMROOT",   # Windows: python.exe will not start without it
    "COMSPEC",      # Windows
    "WINDIR",       # Windows
    "LANG",
    "LC_ALL",
    "TZ",
)

_SECRET_PREFIXES = ("ORION_", "AREP_", "STRIPE_", "AWS_", "POSTGRES_", "REDIS_")


# ── Subprocess worker script ──────────────────────────────────────────────
# Runs inside the sandbox. Order matters: the network block is installed
# BEFORE the artefact is unpickled, because unpickling runs customer code.
_WORKER_SCRIPT = r'''
import json
import sys


def _block_network():
    """Make socket construction fail. Defence in depth behind the netns."""
    import socket

    class _Blocked(OSError):
        pass

    def _refuse(*_args, **_kwargs):
        raise _Blocked("network access is not permitted inside the ORION model sandbox")

    socket.socket = _refuse
    socket.create_connection = _refuse
    socket.socketpair = _refuse
    socket.create_server = _refuse
    for _name in ("gethostbyname", "getaddrinfo"):
        if hasattr(socket, _name):
            setattr(socket, _name, _refuse)


_block_network()

import pickle  # noqa: E402

artefact_path = sys.argv[1]
with open(artefact_path, "rb") as fh:
    _blob = fh.read()
model = pickle.loads(_blob)
del _blob

from arep.core.observation import Observation  # noqa: E402

sys.stderr.write("READY\n")
sys.stderr.flush()

for line in sys.stdin:
    line = line.strip()
    if not line:
        continue
    if line == "RESET":
        try:
            model.reset()
            print(json.dumps({"ok": True}), flush=True)
        except Exception as exc:
            print(json.dumps({"error": f"{type(exc).__name__}: {exc}"}), flush=True)
        continue
    try:
        obs = Observation.from_dict(json.loads(line))
        action = model.predict(obs)
        print(json.dumps(action.to_dict()), flush=True)
    except Exception as exc:
        print(json.dumps({"error": f"{type(exc).__name__}: {exc}"}), flush=True)
'''


# ── Network namespace probe ───────────────────────────────────────────────

_netns_prefix_cache: Optional[list] = None


def _network_namespace_prefix() -> list:
    """
    Return an argv prefix that puts the child in an empty network namespace.

    Empty list when unavailable (non-Linux, no ``unshare``, or user namespaces
    disabled). Probed once per process — the probe actually runs ``unshare``,
    because its availability depends on kernel settings, not just the binary
    being on PATH.
    """
    global _netns_prefix_cache
    if _netns_prefix_cache is not None:
        return _netns_prefix_cache

    _netns_prefix_cache = []
    if sys.platform.startswith("linux") and shutil.which("unshare"):
        candidate = ["unshare", "--net", "--map-root-user"]
        try:
            probe = subprocess.run(
                candidate + ["true"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=10,
            )
            if probe.returncode == 0:
                _netns_prefix_cache = candidate
        except (OSError, subprocess.SubprocessError):
            pass

    if _netns_prefix_cache:
        logger.info("Model sandbox: kernel network isolation available (unshare --net)")
    else:
        logger.warning(
            "Model sandbox: kernel network isolation unavailable on this host; "
            "falling back to the in-process block, which is not a security boundary"
        )
    return _netns_prefix_cache


class SubprocessModelRunner(ModelInterface):
    """
    Runs a cloudpickle-serialised model in a locked-down subprocess.

    The subprocess starts on the first ``predict()``/``reset()`` call and is
    kept alive for the run. Always call ``close()`` when the run finishes;
    ``EvaluationRunner`` does this for you.

    Once the sandbox has been torn down for a violation (timeout, resource
    limit, crash) it is **not** restarted — every later call raises
    ``ModelSandboxError`` so a model cannot burn the budget in a crash loop.

    Args:
        pickle_bytes: cloudpickle-serialised ``ModelInterface`` instance.
        config:       sandbox limits; defaults to ``get_config().sandbox``.
    """

    def __init__(
        self,
        pickle_bytes: bytes,
        config: Optional[SandboxConfig] = None,
    ):
        self._pickle_bytes = pickle_bytes
        self._cfg = config or get_config().sandbox
        self._process: Optional[subprocess.Popen] = None
        self._workdir: Optional[Path] = None
        self._stdout_q: "queue.Queue[Optional[str]]" = queue.Queue()
        self._stderr_q: "queue.Queue[Optional[str]]" = queue.Queue()
        self._reader: Optional[threading.Thread] = None
        self._err_reader: Optional[threading.Thread] = None
        self._stderr_tail: list = []
        self._elapsed_s = 0.0
        self._dead_reason: Optional[str] = None

    # ── lifecycle ────────────────────────────────────────────────────────

    def _build_env(self, workdir: Path) -> dict:
        """Whitelist env for the child. Asserts no secret-bearing vars leak."""
        env = {k: os.environ[k] for k in _ENV_WHITELIST if k in os.environ}

        # The artefact unpickles into arep classes, so the package must import.
        env["PYTHONPATH"] = str(Path(arep.__file__).resolve().parent.parent)
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        env["PYTHONUNBUFFERED"] = "1"
        # Anything the model writes lands in its own jail, not /tmp or $HOME.
        for key in ("TMPDIR", "TEMP", "TMP", "HOME", "USERPROFILE"):
            env[key] = str(workdir)

        leaked = [k for k in env if k.startswith(_SECRET_PREFIXES)]
        if leaked:  # pragma: no cover — guards against a careless edit above
            raise ModelSandboxError(
                f"sandbox env whitelist leaks secret-bearing variables: {leaked}"
            )
        return env

    def _preexec(self):  # pragma: no cover — POSIX child process only
        """Apply rlimits and detach into a new session (POSIX only)."""
        import resource

        cfg = self._cfg
        resource.setrlimit(resource.RLIMIT_CPU, (cfg.cpu_seconds, cfg.cpu_seconds))
        resource.setrlimit(resource.RLIMIT_AS, (cfg.memory_bytes, cfg.memory_bytes))
        resource.setrlimit(resource.RLIMIT_FSIZE, (cfg.max_file_bytes, cfg.max_file_bytes))
        resource.setrlimit(resource.RLIMIT_NOFILE, (cfg.max_open_files, cfg.max_open_files))
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
        # Own session => the whole tree dies with one killpg on timeout.
        os.setsid()

    def _start(self) -> None:
        if self._dead_reason:
            raise ModelSandboxError(f"model sandbox is dead: {self._dead_reason}")

        workdir = Path(tempfile.mkdtemp(prefix="orion_sandbox_"))
        self._workdir = workdir

        script_path = workdir / "_worker.py"
        script_path.write_text(_WORKER_SCRIPT, encoding="utf8")
        artefact_path = workdir / "artefact.pkl"
        artefact_path.write_bytes(self._pickle_bytes)

        netns = _network_namespace_prefix()
        if self._cfg.require_network_namespace and not netns:
            self._cleanup_workdir()
            raise ModelSandboxError(
                "sandbox.require_network_namespace is set but this host cannot "
                "provide one (needs Linux + unshare + user namespaces)"
            )

        popen_kwargs = {
            "stdin": subprocess.PIPE,
            "stdout": subprocess.PIPE,
            "stderr": subprocess.PIPE,
            "text": True,
            "cwd": str(workdir),
            "env": self._build_env(workdir),
        }
        if os.name == "posix":
            popen_kwargs["preexec_fn"] = self._preexec
        else:
            # Windows is a development-only target: no setrlimit, no namespaces.
            # Only the env strip, the tmpdir jail and the wall-clock kill apply.
            logger.warning(
                "Model sandbox on %s: resource limits and network namespace are "
                "unavailable; do not run untrusted models on this platform",
                sys.platform,
            )

        # -s: no user site-packages. -B: no .pyc writes. NOT -I/-E: those drop
        # PYTHONPATH, which is how the child finds the arep package.
        argv = netns + [sys.executable, "-s", "-B", str(script_path), str(artefact_path)]
        try:
            self._process = subprocess.Popen(argv, **popen_kwargs)
        except OSError as exc:
            self._cleanup_workdir()
            raise ModelSandboxError(f"failed to start model sandbox: {exc}") from exc

        self._stdout_q = queue.Queue()
        self._stderr_q = queue.Queue()
        self._reader = threading.Thread(
            target=self._pump_stdout,
            args=(self._process.stdout, self._stdout_q),
            daemon=True,
        )
        self._reader.start()
        self._err_reader = threading.Thread(
            target=self._pump_stdout,
            args=(self._process.stderr, self._stderr_q),
            daemon=True,
        )
        self._err_reader.start()

        # The artefact is loaded once at startup; drop it from the jail so the
        # model cannot re-read (or rewrite) its own bytes mid-run.
        self._await_ready(artefact_path)
        logger.info(
            "Model sandbox started (pid=%s, netns=%s, cwd=%s)",
            self._process.pid, bool(netns), workdir,
        )

    def _await_ready(self, artefact_path: Path) -> None:
        """
        Block until the child reports READY, then delete the artefact file.

        Reads through the stderr queue rather than the pipe directly: unpickling
        runs customer code, so a model that hangs on load must hit this deadline
        rather than block the reader forever.
        """
        deadline = time.perf_counter() + self._cfg.predict_timeout_s
        while True:
            remaining = deadline - time.perf_counter()
            if remaining <= 0:
                self._kill("startup timeout")
                raise ModelSandboxError(
                    f"model did not load within {self._cfg.predict_timeout_s:.1f}s"
                )
            try:
                line = self._stderr_q.get(timeout=remaining)
            except queue.Empty:
                continue
            if line is None:       # EOF — the child died while loading
                stderr = self._drain_stderr()
                self._kill("child exited during startup")
                raise ModelSandboxError(
                    f"model failed to load: {stderr.strip() or 'no output'}"
                )
            if line.strip() == "READY":
                # Loaded. Drop the artefact so the model cannot re-read or
                # rewrite its own bytes mid-run.
                try:
                    artefact_path.unlink()
                except OSError:
                    pass
                return
            self._stderr_tail.append(line.rstrip())
            logger.debug("sandbox stderr: %s", line.rstrip())

    @staticmethod
    def _pump_stdout(stream, out_q: "queue.Queue[Optional[str]]") -> None:
        """
        Feed one of the child's output streams into a queue so reads have deadlines.

        Holds only the stream and the queue — never the runner — so a thread
        left behind by a killed child cannot keep the runner alive.
        """
        try:
            for line in stream:
                out_q.put(line)
        except (ValueError, OSError):
            pass
        finally:
            out_q.put(None)   # EOF sentinel

    def _drain_stderr(self) -> str:
        """Non-blocking: whatever the stderr pump has queued so far."""
        while True:
            try:
                line = self._stderr_q.get_nowait()
            except queue.Empty:
                break
            if line is None:
                break
            self._stderr_tail.append(line.rstrip())
        return "\n".join(self._stderr_tail[-20:])

    def _ensure_started(self) -> None:
        if self._dead_reason:
            raise ModelSandboxError(f"model sandbox is dead: {self._dead_reason}")
        if self._process is None:
            self._start()
        elif self._process.poll() is not None:
            self._kill(f"child exited with code {self._process.returncode}")
            raise ModelSandboxError(
                f"model process exited unexpectedly (code {self._process.returncode})"
            )

    # ── IPC ──────────────────────────────────────────────────────────────

    def _exchange(self, payload: str, what: str) -> dict:
        """Write one line to the child and read one line back, under deadline."""
        self._ensure_started()
        assert self._process is not None

        remaining_budget = self._cfg.total_wallclock_s - self._elapsed_s
        if remaining_budget <= 0:
            self._kill("total wall-clock budget exhausted")
            raise ModelSandboxError(
                f"model exceeded its total wall-clock budget "
                f"({self._cfg.total_wallclock_s:.0f}s)"
            )
        deadline = min(self._cfg.predict_timeout_s, remaining_budget)

        started = time.perf_counter()
        try:
            self._process.stdin.write(payload)
            self._process.stdin.flush()
        except (BrokenPipeError, ValueError, OSError) as exc:
            self._kill(f"broken pipe on {what}: {exc}")
            raise ModelSandboxError(f"model sandbox pipe broke during {what}") from exc

        try:
            line = self._stdout_q.get(timeout=deadline)
        except queue.Empty:
            self._kill(f"{what} exceeded {deadline:.1f}s wall clock")
            raise ModelSandboxError(
                f"model {what} exceeded the {deadline:.1f}s hard wall-clock limit"
            ) from None
        finally:
            self._elapsed_s += time.perf_counter() - started

        if line is None:
            stderr = self._drain_stderr()
            self._kill("child closed stdout")
            raise ModelSandboxError(
                f"model process died during {what}: {stderr.strip() or 'no output'}"
            )

        try:
            return json.loads(line)
        except json.JSONDecodeError as exc:
            self._kill(f"protocol violation on {what}")
            raise ModelSandboxError(
                f"model sandbox returned non-JSON during {what}: {line[:200]!r}"
            ) from exc

    # ── ModelInterface ───────────────────────────────────────────────────

    def predict(self, observation: Observation) -> Action:
        """
        Run one inference in the sandbox.

        A model that raises gets an emergency brake for this tick and the run
        continues. A sandbox-level failure (hang, resource limit, crash) raises
        ``ModelSandboxError`` — the run is over.
        """
        result = self._exchange(json.dumps(observation.to_dict()) + "\n", "predict()")
        if "error" in result:
            logger.error("Model raised inside sandbox: %s", result["error"])
            return Action.emergency_brake()
        return Action.from_dict(result)

    def reset(self) -> None:
        result = self._exchange("RESET\n", "reset()")
        if "error" in result:
            logger.error("Model reset() raised inside sandbox: %s", result["error"])

    # ── teardown ─────────────────────────────────────────────────────────

    def _kill(self, reason: str) -> None:
        """SIGKILL the child (and anything it spawned) and mark the sandbox dead."""
        self._dead_reason = reason
        logger.error("Model sandbox killed: %s", reason)
        self._terminate_process(force=True)
        self._cleanup_workdir()

    def _terminate_process(self, force: bool = False) -> None:
        process, self._process = self._process, None
        if process is None or process.poll() is not None:
            return
        try:
            if os.name == "posix":
                import signal

                # Kill the whole session created in _preexec, not just the head.
                os.killpg(os.getpgid(process.pid), signal.SIGKILL if force else signal.SIGTERM)
            elif force:
                process.kill()
            else:
                process.terminate()
            process.wait(timeout=5.0)
        except (ProcessLookupError, PermissionError, OSError):
            pass
        except subprocess.TimeoutExpired:
            try:
                process.kill()
            except OSError:
                pass
        finally:
            for stream in (process.stdin, process.stdout, process.stderr):
                try:
                    if stream:
                        stream.close()
                except OSError:
                    pass

    def _cleanup_workdir(self) -> None:
        if self._workdir and self._workdir.exists():
            shutil.rmtree(self._workdir, ignore_errors=True)
        self._workdir = None

    def close(self) -> None:
        """Terminate the sandbox and remove its jail. Safe to call twice."""
        if self._process is not None:
            self._terminate_process(force=False)
            logger.info("Model sandbox closed")
        self._cleanup_workdir()

    def __del__(self):
        try:
            self.close()
        except Exception:  # pragma: no cover — interpreter shutdown
            pass
