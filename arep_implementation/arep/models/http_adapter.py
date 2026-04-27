"""
ORION HTTP Model Adapter.  [Phase 1]

Wraps an externally-running model server (Docker container) behind
the standard ModelInterface, so it can be used anywhere in the
simulation pipeline without special casing.

The model server must expose:
  POST /predict   body: Observation JSON → returns Action JSON
  POST /reset     body: {}              → returns {}

This adapter is used when submission_type == "docker".
"""

from __future__ import annotations

import json
from typing import Optional

import urllib.request
import urllib.error

from arep.models.interface import ModelInterface
from arep.core.observation import Observation
from arep.core.action import Action
from arep.utils.logging_config import get_logger

logger = get_logger("models.http_adapter")


class HttpModelAdapter(ModelInterface):
    """
    ModelInterface implementation that delegates to an HTTP model server.

    The server is expected to be running before this adapter is used.
    Caller is responsible for container lifecycle (start/stop).

    Args:
        base_url: Base URL of the model server, e.g. "http://localhost:8080"
        timeout: Request timeout in seconds.
    """

    def __init__(self, base_url: str, timeout: float = 5.0):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        logger.info(f"HttpModelAdapter initialised → {self.base_url}")

    def predict(self, observation: Observation) -> Action:
        """
        Call POST /predict on the model server.

        Serialises the Observation to JSON, sends it, and deserialises
        the Action response.
        """
        payload = json.dumps(observation.to_dict()).encode("utf-8")
        try:
            req = urllib.request.Request(
                f"{self.base_url}/predict",
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                body = json.loads(resp.read().decode("utf-8"))
                return Action.from_dict(body)
        except urllib.error.URLError as e:
            logger.error(f"HttpModelAdapter.predict failed: {e}")
            return Action.emergency_brake()

    def reset(self) -> None:
        """Call POST /reset on the model server."""
        try:
            req = urllib.request.Request(
                f"{self.base_url}/reset",
                data=b"{}",
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=self.timeout):
                pass
        except urllib.error.URLError as e:
            logger.warning(f"HttpModelAdapter.reset failed (non-fatal): {e}")

    def health_check(self) -> bool:
        """
        Return True if the model server is reachable.

        Used by the worker to verify the container is ready before
        starting a simulation run.
        """
        try:
            req = urllib.request.Request(
                f"{self.base_url}/health",
                method="GET",
            )
            with urllib.request.urlopen(req, timeout=2.0) as resp:
                return resp.status == 200
        except Exception:
            return False
