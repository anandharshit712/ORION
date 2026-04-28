"""
ORION SDK — Model Uploader.

Serialises a ModelInterface instance with cloudpickle and uploads it
to the ORION API as a multipart form upload.

Standalone helper for use outside OrionClient:
    from orion_sdk import upload_model
    model_id = upload_model(MyModel(), name="my-model", api_key="sk-orion-...")
"""

from __future__ import annotations

import io
from typing import Optional

from orion_sdk.interface import ModelInterface


DEFAULT_BASE_URL = "https://api.orion.run"


def _serialise(model: ModelInterface) -> bytes:
    try:
        import cloudpickle
    except ImportError as e:
        raise ImportError(
            "cloudpickle is required for model upload. "
            "Install with: pip install cloudpickle"
        ) from e
    return cloudpickle.dumps(model)


def upload_model(
    model: ModelInterface,
    name: str,
    version: str = "v1.0",
    api_key: str = "",
    base_url: str = DEFAULT_BASE_URL,
    session: Optional[object] = None,
    timeout: float = 60.0,
) -> str:
    """Serialise and upload a model to ORION.

    Args:
        model:    ModelInterface instance to upload.
        name:     Human-readable model name (e.g. "my-ad-model").
        version:  Version string (e.g. "v2.1").
        api_key:  ORION API key (Bearer token).
        base_url: ORION API base URL.
        session:  Optional requests.Session (used by OrionClient).
        timeout:  Request timeout in seconds.

    Returns:
        model_id (UUID string) for use in batch evaluations.
    """
    if not api_key and session is None:
        raise ValueError("api_key is required when no session is supplied")

    pickle_bytes = _serialise(model)

    import requests
    sess = session if session is not None else requests.Session()
    if session is None:
        sess.headers.update({"Authorization": f"Bearer {api_key}"})

    files = {
        "artefact": (f"{name}.pkl", io.BytesIO(pickle_bytes), "application/octet-stream"),
    }
    data = {"name": name, "version": version}

    url = f"{base_url.rstrip('/')}/api/models/upload"
    # Don't send Content-Type: application/json — requests sets multipart on its own.
    resp = sess.post(url, data=data, files=files, timeout=timeout)
    resp.raise_for_status()
    body = resp.json()
    return body["id"]
