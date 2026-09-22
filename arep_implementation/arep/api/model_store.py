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
import io
import os
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Optional

from arep.utils.logging_config import get_logger

logger = get_logger("api.model_store")


class ModelArtefactError(RuntimeError):
    """An artefact could not be fetched, or is not the one that was uploaded."""


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
    artefact_uri: str  # s3://... or registry.orion.run/...
    status: str  # uploading | ready | error
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
    ) -> tuple[str, str, int]:
        """Store a cloudpickle-serialised model blob.

        Returns:
            (artefact_uri, sha256_hex, size_bytes)
        """
        dest = self._store_path / org_id / f"{model_id}.pkl"
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(pickle_bytes)
        uri = f"file://{dest}"
        digest = self.compute_hash(pickle_bytes)
        size = len(pickle_bytes)
        logger.info(
            "Stored SDK model artefact: %s (%d bytes, sha256=%s)", uri, size, digest[:8]
        )
        return uri, digest, size

    def delete(self, artefact_uri: str) -> None:
        """Delete a stored artefact. Best-effort; missing files ignored."""
        if artefact_uri.startswith("file://"):
            path = Path(artefact_uri[7:])
            try:
                path.unlink()
            except FileNotFoundError:
                pass
            except OSError as e:
                logger.warning("Failed to delete artefact %s: %s", artefact_uri, e)

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

    def fetch_python_sdk(
        self,
        artefact_uri: str,
        expected_hash: Optional[str] = None,
    ) -> bytes:
        """
        Fetch the cloudpickle blob for a python_sdk model.

        These bytes get unpickled, and unpickling is code execution. The
        sandbox contains what the code can do once running; the hash check is
        what notices that the bytes are not the ones the customer uploaded.
        Storage is not a trust boundary: an artefact on a shared volume or in a
        bucket can be replaced without touching the API.

        Args:
            artefact_uri: file:// or s3:// reference from the model record.
            expected_hash: the SHA-256 recorded at upload. Strongly
                recommended — callers that omit it get the old behaviour, and
                a warning, because a silent unverified read is the thing this
                argument exists to prevent.

        Raises:
            ModelArtefactError: the bytes do not match the recorded hash.
        """
        if artefact_uri.startswith("file://"):
            data = Path(artefact_uri[7:]).read_bytes()
        elif artefact_uri.startswith("s3://"):
            data = self._fetch_s3(artefact_uri)
        else:
            raise ValueError(f"Unsupported artefact URI scheme: {artefact_uri}")

        if expected_hash:
            actual = self.compute_hash(data)
            if actual != expected_hash:
                # Refuse rather than warn. A mismatch means either corruption
                # or substitution, and there is no version of "run it anyway"
                # that is safe when the payload is executable.
                raise ModelArtefactError(
                    f"Artefact hash mismatch for {artefact_uri}: recorded "
                    f"{expected_hash[:16]}..., found {actual[:16]}.... "
                    f"Refusing to load it."
                )
        else:
            logger.warning(
                "Loading %s without a hash check — the caller passed no "
                "expected_hash",
                artefact_uri,
            )

        return data

    @staticmethod
    def _fetch_s3(artefact_uri: str) -> bytes:
        """Download an artefact from S3.

        boto3 is imported here rather than at module scope: object storage is
        a deployment choice, and a local install should not need the AWS SDK
        to run a simulation.
        """
        try:
            import boto3
        except ImportError as exc:
            raise ModelArtefactError(
                "This artefact is in S3 but boto3 is not installed. "
                "Install it, or store artefacts on a local volume."
            ) from exc

        without_scheme = artefact_uri[5:]
        bucket, _, key = without_scheme.partition("/")
        if not bucket or not key:
            raise ValueError(f"Malformed S3 URI: {artefact_uri}")

        buffer = io.BytesIO()
        boto3.client("s3").download_fileobj(bucket, key, buffer)
        return buffer.getvalue()

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
