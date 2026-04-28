"""
ORION SDK — OrionClient.

High-level client for the ORION REST API. Wraps all HTTP calls and
provides a clean Python interface for:
  - Submitting models (SDK or Docker)
  - Listing/managing models + API keys
  - Running batch evaluations (Phase 1.3)
  - Fetching results
"""

from __future__ import annotations

import time
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
        composite = (
            f"{self.composite_mean:.3f}"
            if self.composite_mean is not None else "pending"
        )
        pass_rate = (
            f"{self.pass_rate:.1%}"
            if self.pass_rate is not None else "pending"
        )
        return (
            f"BatchResult(id={self.batch_id}, status={self.status}, "
            f"composite={composite}, pass_rate={pass_rate})"
        )


@dataclass
class ApiKey:
    id: str
    label: str
    key_prefix: str
    created_at: str
    revoked_at: Optional[str]


class OrionClient:
    """Python client for the ORION evaluation platform API.

    Args:
        api_key:  Your ORION API key (sk-orion-...).
        base_url: API base URL (default: https://api.orion.run).
        timeout:  Request timeout in seconds (default: 60).
    """

    def __init__(
        self,
        api_key: str,
        base_url: str = DEFAULT_BASE_URL,
        timeout: float = 60.0,
    ):
        if not api_key:
            raise ValueError("api_key is required")
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._session = requests.Session()
        self._session.headers.update({
            "Authorization": f"Bearer {api_key}",
            "User-Agent": "orion-sdk/0.1.0",
        })

    # ── Models ───────────────────────────────────────────────────────

    def submit_model(
        self,
        model: ModelInterface,
        name: str,
        version: str = "v1.0",
    ) -> str:
        """Serialise and upload a Python ModelInterface. Returns model_id."""
        return _upload_model(
            model=model, name=name, version=version,
            base_url=self.base_url, session=self._session,
            timeout=self.timeout,
        )

    def register_docker_model(
        self,
        image: str,
        port: int,
        name: str,
        version: str = "v1.0",
    ) -> str:
        """Register a Docker container image as a model. Returns model_id."""
        body = {"name": name, "version": version, "image": image, "port": port}
        return self._post("/api/models/register", body)["id"]

    def list_models(self) -> list[dict]:
        return self._get("/api/models/")

    def delete_model(self, model_id: str) -> None:
        self._delete(f"/api/models/{model_id}")

    # ── API keys ─────────────────────────────────────────────────────

    def list_keys(self) -> list[dict]:
        return self._get("/api/keys/")

    def create_key(self, label: str) -> dict:
        return self._post("/api/keys/", {"label": label})

    def revoke_key(self, key_id: str) -> None:
        self._delete(f"/api/keys/{key_id}")

    # ── Batch evaluation ─────────────────────────────────────────────

    def run_batch(
        self,
        model_id: str,
        scenario_path: str,
        num_runs: int = 10,
        seed: int = 42,
    ) -> BatchResult:
        """Submit a synchronous batch evaluation.

        Note: P1.3 (Celery + async batch) will replace this with a polling
        flow. For now, hits the synchronous /evaluate/batch endpoint.
        """
        body = {
            "scenario_path": scenario_path,
            "model_name": model_id,
            "num_runs": num_runs,
            "master_seed": seed,
        }
        resp = self._post("/evaluate/batch", body)
        agg = resp.get("aggregated", {})
        return BatchResult(
            batch_id=resp.get("scenario_name", ""),
            scenario_ids=[scenario_path],
            model_id=model_id,
            status="completed",
            composite_mean=agg.get("composite_mean"),
            safety_mean=agg.get("safety_mean"),
            collision_rate=agg.get("collision_rate"),
        )

    def get_run_status(self, run_id: str) -> dict:
        """Fetch status of a single live run."""
        return self._get(f"/api/runs/{run_id}")

    def wait_for_run(
        self,
        run_id: str,
        poll_interval: float = 1.0,
        timeout: float = 600.0,
    ) -> dict:
        """Block until a live run completes (or timeout expires)."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            run = self.get_run_status(run_id)
            if run.get("status") in ("complete", "completed", "failed", "cancelled"):
                return run
            time.sleep(poll_interval)
        raise TimeoutError(f"Run {run_id} did not finish within {timeout}s")

    # ── Internal HTTP helpers ────────────────────────────────────────

    def _get(self, path: str) -> dict:
        resp = self._session.get(f"{self.base_url}{path}", timeout=self.timeout)
        resp.raise_for_status()
        return resp.json()

    def _post(self, path: str, body: dict) -> dict:
        resp = self._session.post(
            f"{self.base_url}{path}", json=body, timeout=self.timeout,
        )
        resp.raise_for_status()
        return resp.json()

    def _delete(self, path: str) -> None:
        resp = self._session.delete(f"{self.base_url}{path}", timeout=self.timeout)
        resp.raise_for_status()
