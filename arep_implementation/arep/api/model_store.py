"""
ORION Model Store.  [Phase 1]

Handles upload, storage, and retrieval of customer model artefacts.

Two artefact types are supported:
  - python_sdk : cloudpickle-serialised ModelInterface subclass
  - docker     : reference to a customer container image in a registry

Artefacts are stored in object storage (S3-compatible).
In development, the local filesystem is used as a fallback store.
"""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Optional

from arep.utils.logging_config import get_logger

logger = get_logger("api.model_store")


class SubmissionType(str, Enum):
    PYTHON_SDK = "python_sdk"
    DOCKER = "docker"


@dataclass
class ModelArtefact:
    """Metadata about a stored model artefact."""
    model_id: str
    org_id: str
    name: str
    version: str
    submission_type: SubmissionType
    artefact_uri: str          # s3://... or registry.orion.run/...
    status: str                # uploading | ready | error
    size_bytes: Optional[int] = None
    content_hash: Optional[str] = None


class ModelStore:
    """
    Manages model artefact storage and retrieval.

    In development: stores to local filesystem under ORION_MODEL_STORE_PATH.
    In production: stores to S3-compatible object storage.

    Never stores model artefacts in the database — only metadata (URI, hash, status).
    """

    def __init__(self):
        self._store_path = Path(
            os.environ.get("ORION_MODEL_STORE_PATH", "/tmp/orion_model_store")
        )
        self._store_path.mkdir(parents=True, exist_ok=True)
        logger.info(f"ModelStore initialised at {self._store_path}")

    def upload_python_sdk(
        self,
        org_id: str,
        model_id: str,
        pickle_bytes: bytes,
    ) -> str:
        """
        Store a cloudpickle-serialised model blob.

        Returns the artefact URI (local path or s3:// URL).

        TODO [P1]: Replace local file store with S3 client (boto3).
        TODO [P1]: Compute and verify SHA-256 hash of the blob.
        """
        dest = self._store_path / org_id / f"{model_id}.pkl"
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(pickle_bytes)
        uri = f"file://{dest}"
        logger.info(f"Stored SDK model artefact: {uri} ({len(pickle_bytes)} bytes)")
        return uri

    def register_docker(
        self,
        org_id: str,
        model_id: str,
        image: str,
        port: int,
    ) -> str:
        """
        Register a Docker image reference (no data stored locally).

        Returns the artefact URI (docker registry reference).
        """
        uri = f"docker://{image}:{port}"
        logger.info(f"Registered Docker model artefact: {uri}")
        return uri

    def fetch_python_sdk(self, artefact_uri: str) -> bytes:
        """
        Fetch the cloudpickle blob for a python_sdk model.

        TODO [P1]: Add S3 download path.
        TODO [P1]: Verify hash against DB record before returning.
        """
        if artefact_uri.startswith("file://"):
            path = Path(artefact_uri[7:])
            return path.read_bytes()
        raise ValueError(f"Unsupported artefact URI scheme: {artefact_uri}")

    def get_docker_image(self, artefact_uri: str) -> tuple[str, int]:
        """
        Parse a docker artefact URI into (image, port).
        """
        if artefact_uri.startswith("docker://"):
            parts = artefact_uri[9:].rsplit(":", 1)
            return parts[0], int(parts[1])
        raise ValueError(f"Not a docker artefact URI: {artefact_uri}")

    @staticmethod
    def compute_hash(data: bytes) -> str:
        """SHA-256 hex digest of a byte blob."""
        return hashlib.sha256(data).hexdigest()


# Module-level singleton — initialised once on import.
_store: Optional[ModelStore] = None


def get_model_store() -> ModelStore:
    global _store
    if _store is None:
        _store = ModelStore()
    return _store
