"""
ORION SDK — Model Uploader.

Serialises a ModelInterface instance with cloudpickle and uploads it
to the ORION API as a multipart form upload.

Standalone function for use outside OrionClient:
    from orion_sdk import upload_model
    model_id = upload_model(MyModel(), name="my-model", api_key="sk-orion-...")
"""

from __future__ import annotations

from orion_sdk.interface import ModelInterface


def upload_model(
    model: ModelInterface,
    name: str,
    version: str = "v1.0",
    api_key: str = "",
    base_url: str = "https://api.orion.run",
) -> str:
    """
    Serialise and upload a model to ORION.

    Args:
        model:    ModelInterface instance to upload.
        name:     Human-readable model name (e.g. "my-ad-model").
        version:  Version string (e.g. "v2.1").
        api_key:  ORION API key.
        base_url: ORION API base URL.

    Returns:
        model_id (UUID string) for use in batch evaluations.

    TODO [P1]: Import cloudpickle (raise ImportError with install hint if missing).
    TODO [P1]: Serialise model with cloudpickle.dumps(model).
    TODO [P1]: POST to {base_url}/api/models/upload as multipart form.
    TODO [P1]: Return model_id from response JSON.
    """
    try:
        import cloudpickle  # noqa: F401
    except ImportError:
        raise ImportError(
            "cloudpickle is required for model upload. "
            "Install with: pip install orion-sdk[cloudpickle]"
        )
    raise NotImplementedError("upload_model not yet implemented [P1]")
