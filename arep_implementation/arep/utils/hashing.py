"""
Deterministic hashing utilities for ORION.

SHA256-based hashing for state snapshots, scenario versioning, and seed derivation.
All functions are pure and deterministic.
"""

import hashlib
import json
from typing import Any, Dict


def hash_string(s: str) -> str:
    """
    Compute SHA256 hex digest of a string.

    Args:
        s: Input string.

    Returns:
        64-character hex digest.
    """
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def hash_bytes(data: bytes) -> str:
    """
    Compute SHA256 hex digest of raw bytes.

    Args:
        data: Input bytes.

    Returns:
        64-character hex digest.
    """
    return hashlib.sha256(data).hexdigest()


def hash_dict(d: Dict[str, Any]) -> str:
    """
    Compute SHA256 hash of a dictionary.

    Uses sorted-key JSON serialization for deterministic ordering.

    Args:
        d: Dictionary to hash (must be JSON-serializable).

    Returns:
        64-character hex digest.
    """
    canonical = json.dumps(d, sort_keys=True, separators=(",", ":"))
    return hash_string(canonical)


def derive_seed(master_seed: int, subsystem: str) -> int:
    """
    Derive a deterministic subsystem seed from master seed via SHA256.

    Uses the first 4 bytes of SHA256(master_seed || subsystem_name) as a
    32-bit unsigned integer seed. This ensures:
      - Deterministic: same inputs always produce the same seed
      - Independent: changing one subsystem doesn't affect others
      - Unpredictable: no trivial correlation between subsystem seeds

    Args:
        master_seed: Master seed integer.
        subsystem: Subsystem identifier (e.g. "scenario", "traffic").

    Returns:
        Derived seed as a non-negative 32-bit integer.
    """
    key = f"{master_seed}:{subsystem}"
    digest = hashlib.sha256(key.encode("utf-8")).digest()
    # First 4 bytes → unsigned 32-bit int (big-endian)
    return int.from_bytes(digest[:4], byteorder="big")
