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


class FrameHasher:
    """
    Rolling hash over a run's canonical tick frames (Phase 0.5, defect D-06).

    Two runs of the same (model, scenario, seed) must produce byte-identical
    frames. Folding them into one digest turns that claim into something a test
    can assert and a customer can check: the determinism guarantee stops being a
    promise in a README and becomes a number attached to the run.

    Rolling rather than "collect every frame then hash": a 30-second run at
    50 Hz is 1500 frames, and holding all of them to hash at the end would make
    memory scale with run length for no benefit.

    The chain is ``h(i) = sha256(h(i-1) || canonical_json(frame_i))``, so the
    digest depends on frame *order* as well as content — a run that emits the
    same frames in a different order is not the same run.

    Only feed it canonical frames. ``SimulationEngine.get_tick_frame()`` is
    canonical by contract; the WebSocket send site adds ``emit_ts_ms`` on the
    way out, and hashing that would make every run's digest unique and the
    whole exercise pointless.
    """

    def __init__(self) -> None:
        self._digest = hashlib.sha256()
        self._count = 0

    def update(self, frame: Dict[str, Any]) -> None:
        """Fold one frame into the rolling digest."""
        canonical = json.dumps(frame, sort_keys=True, separators=(",", ":"))
        self._digest.update(canonical.encode("utf-8"))
        self._count += 1

    @property
    def frame_count(self) -> int:
        return self._count

    def hexdigest(self) -> str:
        """Current digest. Safe to call mid-run; does not finalise anything."""
        return self._digest.hexdigest()
