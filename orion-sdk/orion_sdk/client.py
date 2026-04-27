"""
ORION SDK — OrionClient.

High-level client for the ORION REST API.
Wraps all HTTP calls and provides a clean Python interface for:
  - Submitting models (SDK or Docker)
  - Running batch evaluations
  - Fetching results
  - Comparing models
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional
import requests

from orion_sdk.interface import ModelInterface
from orion_sdk.uploader import upload_model as _upload_model

DEFAULT_BASE_URL = "https://api.orion.run"


@dataclass
class BatchResult:
    batch_id: str
    scenario_ids: List[str]
    model_id: str
    status: str
    composite_mean: Optional[float] = None
    safety_mean: Optional[float] = None
    pass_rate: Optional[float] = None
    collision_rate: Optional[float] = None

    def summary(self) -> str:
        return (
            f"BatchResult(id={self.batch_id}, status={self.status}, "
            f"composite={self.composite_mean:.3f if self.composite_mean else 'pending'}, "
            f"pass_rate={self.pass_rate:.1%} if self.pass_rate else 'pending')"
        )


class OrionClient:
    """
    Python client for the ORION evaluation platform API.

    Args:
        api_key:  Your ORION API key (from Settings → API Keys).
        base_url: API base URL (default: https://api.orion.run).
        timeout:  Request timeout in seconds (default: 30).
    """

    def __init__(
        self,
        api_key: str,
        base_url: str = DEFAULT_BASE_URL,
        timeout: float = 30.0,
    ):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._session = requests.Session()
        self._session.headers.update({
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "User-Agent": "orion-sdk/0.1.0",
        })

    # ── Model submission ──────────────────────────────────────────────

    def submit_model(
        self,
        model: ModelInterface,
        name: str,
        version: str = "v1.0",
    ) -> str:
        """
        Serialise and upload a ModelInterface instance to ORION.

        Returns the model_id (UUID string) for use in run_batch().

        TODO [P1]: Call _upload_model(model, name, version, self._session, self.base_url)
        TODO [P1]: Return model_id from response.
        """
        raise NotImplementedError("OrionClient.submit_model not yet implemented [P1]")

    def register_docker_model(
        self,
        image: str,
        port: int,
        name: str,
        version: str = "v1.0",
    ) -> str:
        """
        Register a Docker container image as a model.

        Returns the model_id.

        TODO [P1]: POST /api/models/register with image + port.
        TODO [P1]: Return model_id.
        """
        raise NotImplementedError("OrionClient.register_docker_model not yet implemented [P1]")

    # ── Batch evaluation ──────────────────────────────────────────────

    def run_batch(
        self,
        model_id: str,
        scenarios: List[str],
        runs_per_scenario: int = 10,
        seed: int = 42,
        physics_mode: str = "kinematic",
    ) -> BatchResult:
        """
        Submit a batch evaluation job.

        Returns immediately with a BatchResult (status=queued).
        Poll with get_batch_results(batch_id) until status=completed.

        TODO [P1]: POST /api/runs/batch for each scenario_id.
        TODO [P1]: Return BatchResult with batch_id.
        """
        raise NotImplementedError("OrionClient.run_batch not yet implemented [P1]")

    def get_batch_results(self, batch_id: str) -> BatchResult:
        """
        Fetch the current status and results of a batch job.

        TODO [P1]: GET /api/runs/batch/{batch_id}/results
        TODO [P1]: Return populated BatchResult.
        """
        raise NotImplementedError("OrionClient.get_batch_results not yet implemented [P1]")

    def wait_for_batch(
        self,
        batch_id: str,
        poll_interval: float = 5.0,
        timeout: float = 3600.0,
    ) -> BatchResult:
        """
        Block until a batch job completes (or timeout is reached).

        Args:
            batch_id:      Batch ID to wait for.
            poll_interval: Seconds between polls (default: 5s).
            timeout:       Maximum seconds to wait (default: 1 hour).

        TODO [P1]: Poll get_batch_results() until status=completed or timeout.
        """
        raise NotImplementedError("OrionClient.wait_for_batch not yet implemented [P1]")

    # ── Comparison ────────────────────────────────────────────────────

    def compare_models(
        self,
        model_a_id: str,
        model_b_id: str,
        scenarios: List[str],
        runs_per_scenario: int = 10,
        seed: int = 42,
    ) -> dict:
        """
        Run both models across scenarios and return a comparison report.

        TODO [P2]: POST /api/compare
        TODO [P2]: Wait for completion, return comparison dict.
        """
        raise NotImplementedError("OrionClient.compare_models not yet implemented [P2]")

    # ── Internal helpers ──────────────────────────────────────────────

    def _get(self, path: str) -> dict:
        resp = self._session.get(f"{self.base_url}{path}", timeout=self.timeout)
        resp.raise_for_status()
        return resp.json()

    def _post(self, path: str, body: dict) -> dict:
        resp = self._session.post(f"{self.base_url}{path}", json=body, timeout=self.timeout)
        resp.raise_for_status()
        return resp.json()
