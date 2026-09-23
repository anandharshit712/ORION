"""
Stored tick frames for scrubbable playback (Phase 2.5).

Seed replay already reproduces any run exactly and stores nothing, so this
exists for one reason: not paying the CPU again while someone drags a scrub bar
through a failure.

Which means it is deliberately selective. At 50 Hz a 30-second run is 1,500
frames; storing every run of a 500-run batch would be three quarters of a
million frames per batch, growing with every customer. Frames are kept for the
runs worth scrubbing instantly — the ones that collided, plus anything a
customer pins — which at a 2% collision rate is ten runs a batch.
"""

from __future__ import annotations

import gzip
import json
from typing import Any, Dict, List, Optional

from arep.utils.logging_config import get_logger

logger = get_logger("execution.frame_store")

# Refuse to store a run whose frame list is implausible. A scenario that somehow
# produced a million frames is a bug somewhere upstream, and writing it to the
# database turns that bug into an outage.
MAX_FRAMES = 20_000

# Compressed payloads above this are refused rather than truncated. A truncated
# replay that looks complete is worse than no replay: the scrub bar would end
# early and read as "the run stopped here".
MAX_COMPRESSED_BYTES = 8 * 1024 * 1024


class FrameStoreError(RuntimeError):
    """Frames could not be stored or read back."""


def compress(frames: List[Dict[str, Any]]) -> bytes:
    """Gzip a frame list to bytes.

    Frames repeat the same keys every tick, so gzip takes roughly an order of
    magnitude off. Stored as bytes rather than text because a text column would
    hold the base64 of the gzip, which is bigger than the JSON it replaced.
    """
    if len(frames) > MAX_FRAMES:
        raise FrameStoreError(
            f"refusing to store {len(frames)} frames (limit {MAX_FRAMES}); "
            f"a run this long is a bug upstream, not a playback candidate"
        )

    payload = gzip.compress(
        json.dumps(frames, separators=(",", ":"), sort_keys=True).encode("utf-8")
    )
    if len(payload) > MAX_COMPRESSED_BYTES:
        raise FrameStoreError(
            f"compressed frames are {len(payload)} bytes, over the "
            f"{MAX_COMPRESSED_BYTES} limit"
        )
    return payload


def decompress(payload: bytes) -> List[Dict[str, Any]]:
    """Inverse of `compress`."""
    try:
        return json.loads(gzip.decompress(payload).decode("utf-8"))
    except (OSError, ValueError, UnicodeDecodeError) as exc:
        raise FrameStoreError(f"stored frames are unreadable: {exc}") from exc


def should_store(collision_occurred: bool, termination_reason: Optional[str]) -> bool:
    """Whether this run's frames are worth keeping.

    A collision is the case worth scrubbing — it is the finding. `off_road` is
    kept for the same reason: something went wrong and someone will want to
    watch it. A run that merely timed out is reproducible from its seed in the
    time it takes to ask for it.
    """
    return bool(collision_occurred) or termination_reason == "off_road"


def store_frames(
    session,
    run_id: int,
    frames: List[Dict[str, Any]],
    reason: str = "collision",
) -> Optional[int]:
    """Persist frames for one run. Returns the count stored, or None if skipped.

    Never raises on a storage failure. Losing playback for one run is a degraded
    experience; failing the run that produced it — after the simulation has
    already been paid for and scored — is worse.
    """
    from arep.database.models import RunFrameRecord

    if not frames:
        return None

    try:
        payload = compress(frames)
    except FrameStoreError as exc:
        logger.warning("Not storing frames for run %s: %s", run_id, exc)
        return None

    try:
        existing = session.get(RunFrameRecord, run_id)
        if existing is not None:
            existing.frames_gzip = payload
            existing.frame_count = len(frames)
            existing.reason = reason
        else:
            session.add(
                RunFrameRecord(
                    run_id=run_id,
                    frame_count=len(frames),
                    frames_gzip=payload,
                    reason=reason,
                )
            )
        session.flush()
    except Exception as exc:  # noqa: BLE001 - see docstring
        logger.warning("Failed to store frames for run %s: %s", run_id, exc)
        return None

    logger.info(
        "Stored %d frames for run %s (%s, %d compressed bytes)",
        len(frames),
        run_id,
        reason,
        len(payload),
    )
    return len(frames)


def load_frames(session, run_id: int) -> Optional[List[Dict[str, Any]]]:
    """Read frames back, or None when this run has none stored."""
    from arep.database.models import RunFrameRecord

    record = session.get(RunFrameRecord, run_id)
    if record is None:
        return None
    return decompress(record.frames_gzip)


def event_markers(frames: List[Dict[str, Any]]) -> Dict[str, Optional[int]]:
    """Frame indices worth jumping to, computed server-side.

    Every client then agrees where the events are, and the viewer does not have
    to scan the whole array to place a marker.

    Derived from what the frame actually carries. There is no collision flag and
    no TTC in the tick frame: the collision shows up as
    `monitor.metrics_current.safety_score` dropping to 0 on the colliding tick
    (`engine.get_tick_frame` sets it to 0.0 when `world.has_collision`), and the
    run's end shows up as `termination_reason`.

    A "first critical TTC" marker would be the more useful one — it is where the
    situation became unrecoverable, usually a second or two before impact — but
    TTC is not in the frame schema, so it cannot be recovered from stored frames.
    Adding it means extending `get_tick_frame`, which changes every stored
    digest, so it is not worth doing for a scrub marker.
    """
    collision: Optional[int] = None
    off_road: Optional[int] = None
    terminated: Optional[int] = None

    for i, frame in enumerate(frames):
        if collision is None:
            metrics = (frame.get("monitor") or {}).get("metrics_current") or {}
            if metrics.get("safety_score") == 0.0:
                collision = i

        reason = frame.get("termination_reason")
        if off_road is None and reason == "off_road":
            off_road = i
        if terminated is None and frame.get("is_terminated"):
            terminated = i

    return {
        "collision": collision,
        "off_road": off_road,
        "terminated": terminated,
    }
