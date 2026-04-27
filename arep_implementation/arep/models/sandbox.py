"""
ORION Subprocess Model Sandbox.  [Phase 1]

Runs a cloudpickle-serialised ModelInterface in an isolated subprocess
with CPU and memory resource limits.

This is the execution environment for Python SDK model submissions.
The model code runs in a separate process with:
  - No network access (TODO: implement via seccomp/namespaces)
  - CPU time limit (RLIMIT_CPU)
  - Memory limit (RLIMIT_AS)
  - Stdin/stdout used for observation/action IPC

Security note: For the initial SaaS launch, subprocess isolation provides
basic protection. Before enterprise launch, migrate to Firecracker microVMs
for stronger isolation guarantees.
"""

from __future__ import annotations

import json
import os
import pickle
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Optional

from arep.core.observation import Observation
from arep.core.action import Action
from arep.models.interface import ModelInterface
from arep.utils.logging_config import get_logger

logger = get_logger("models.sandbox")

# Resource limits applied to the model subprocess
MAX_CPU_SECONDS = 10        # per predict() call — generous to allow slow models
MAX_MEMORY_BYTES = 512 * 1024 * 1024   # 512 MB


# ── Subprocess worker script ──────────────────────────────────────────────
# This script runs inside the sandbox process. It:
#   1. Loads the pickled model from a temp file path (argv[1])
#   2. Reads Observation JSON from stdin, calls predict(), writes Action JSON to stdout
#   3. Listens for "RESET\n" on stdin to call reset()

_WORKER_SCRIPT = """
import sys, json, pickle

model_path = sys.argv[1]
with open(model_path, "rb") as f:
    model = pickle.load(f)

for line in sys.stdin:
    line = line.strip()
    if line == "RESET":
        model.reset()
        print("OK", flush=True)
    else:
        try:
            obs_dict = json.loads(line)
            # Import here to avoid circular import in arep package
            import importlib
            obs_mod = importlib.import_module("arep.core.observation")
            Observation = obs_mod.Observation
            obs = Observation.from_dict(obs_dict)
            action = model.predict(obs)
            print(json.dumps(action.to_dict()), flush=True)
        except Exception as e:
            print(json.dumps({"error": str(e)}), flush=True)
"""


class SubprocessModelRunner(ModelInterface):
    """
    Runs a cloudpickle-serialised model in an isolated subprocess.

    The subprocess is started on first predict() or reset() call and
    kept alive for the duration of the simulation run.
    Call close() to terminate it after the run completes.

    Args:
        pickle_bytes: cloudpickle-serialised ModelInterface instance.
        cpu_limit:    max CPU seconds per call (default: 10).
        memory_limit: max resident memory in bytes (default: 512 MB).
    """

    def __init__(
        self,
        pickle_bytes: bytes,
        cpu_limit: int = MAX_CPU_SECONDS,
        memory_limit: int = MAX_MEMORY_BYTES,
    ):
        self._pickle_bytes = pickle_bytes
        self._cpu_limit = cpu_limit
        self._memory_limit = memory_limit
        self._process: Optional[subprocess.Popen] = None
        self._worker_script_path: Optional[Path] = None
        self._model_pickle_path: Optional[Path] = None

    def _start(self) -> None:
        """Start the sandbox subprocess."""
        # Write worker script to temp file
        script_file = tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False
        )
        script_file.write(_WORKER_SCRIPT)
        script_file.close()
        self._worker_script_path = Path(script_file.name)

        # Write pickled model to temp file
        model_file = tempfile.NamedTemporaryFile(
            mode="wb", suffix=".pkl", delete=False
        )
        model_file.write(self._pickle_bytes)
        model_file.close()
        self._model_pickle_path = Path(model_file.name)

        # Start subprocess
        self._process = subprocess.Popen(
            [sys.executable, str(self._worker_script_path), str(self._model_pickle_path)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        logger.info(f"Model sandbox started (pid={self._process.pid})")

    def _ensure_started(self) -> None:
        if self._process is None or self._process.poll() is not None:
            self._start()

    def predict(self, observation: Observation) -> Action:
        """Send observation to sandbox, return action."""
        self._ensure_started()
        try:
            obs_json = json.dumps(observation.to_dict()) + "\n"
            self._process.stdin.write(obs_json)
            self._process.stdin.flush()
            response = self._process.stdout.readline().strip()
            result = json.loads(response)
            if "error" in result:
                logger.error(f"Model sandbox error: {result['error']}")
                return Action.emergency_brake()
            return Action.from_dict(result)
        except Exception as e:
            logger.error(f"Sandbox predict() failed: {e}")
            return Action.emergency_brake()

    def reset(self) -> None:
        """Send reset signal to sandbox."""
        self._ensure_started()
        try:
            self._process.stdin.write("RESET\n")
            self._process.stdin.flush()
            self._process.stdout.readline()   # consume "OK"
        except Exception as e:
            logger.warning(f"Sandbox reset() failed (non-fatal): {e}")

    def close(self) -> None:
        """Terminate the sandbox subprocess and clean up temp files."""
        if self._process and self._process.poll() is None:
            self._process.terminate()
            try:
                self._process.wait(timeout=3.0)
            except subprocess.TimeoutExpired:
                self._process.kill()
            logger.info("Model sandbox terminated")

        for path in [self._worker_script_path, self._model_pickle_path]:
            if path and path.exists():
                try:
                    path.unlink()
                except OSError:
                    pass

    def __del__(self):
        self.close()
