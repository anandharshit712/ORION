"""
Frame determinism tests (Phase 0.5, defect D-06).

Covers the roadmap acceptance criteria:
  - same seed → identical frame hash across two runs (CI-enforced)
  - `git grep "time.time" arep/simulation arep/core arep/evaluation` → zero hits

The frame hash is the enforceable half of the determinism guarantee. Everything
else in the pitch — "run it 500 times and the numbers mean something" — rests on
two runs of the same input producing the same frames, and until this landed
nothing checked it. It could not even be checked: every frame carried
`emit_ts_ms` from `time.time()`, so no two runs ever matched.
"""

from __future__ import annotations

import asyncio
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from arep.utils.hashing import FrameHasher          # noqa: E402

REPO = Path(__file__).resolve().parent.parent
SCENARIO = str(REPO / "scenarios" / "basic" / "straight_road_lead_vehicle.yaml")


# -- The hasher ------------------------------------------------------------

def test_identical_frames_hash_identically():
    a, b = FrameHasher(), FrameHasher()
    frames = [{"tick": i, "x": i * 1.5} for i in range(10)]
    for f in frames:
        a.update(f)
        b.update(f)
    assert a.hexdigest() == b.hexdigest()


def test_frame_order_changes_the_hash():
    """A run that emits the same frames in a different order is a different run."""
    a, b = FrameHasher(), FrameHasher()
    f1, f2 = {"tick": 1}, {"tick": 2}
    a.update(f1); a.update(f2)
    b.update(f2); b.update(f1)
    assert a.hexdigest() != b.hexdigest()


def test_a_single_changed_value_changes_the_hash():
    a, b = FrameHasher(), FrameHasher()
    a.update({"tick": 1, "x": 1.0})
    b.update({"tick": 1, "x": 1.0000001})
    assert a.hexdigest() != b.hexdigest()


def test_key_order_does_not_change_the_hash():
    """Canonical JSON: dict ordering is an implementation detail, not data."""
    a, b = FrameHasher(), FrameHasher()
    a.update({"tick": 1, "x": 2.0})
    b.update({"x": 2.0, "tick": 1})
    assert a.hexdigest() == b.hexdigest()


def test_hexdigest_is_readable_mid_run():
    hasher = FrameHasher()
    hasher.update({"tick": 1})
    partial = hasher.hexdigest()
    hasher.update({"tick": 2})
    assert hasher.hexdigest() != partial
    assert hasher.frame_count == 2


# -- The canonical frame ---------------------------------------------------

def test_tick_frame_carries_no_wall_clock():
    """emit_ts_ms in the canonical frame is what made runs unhashable."""
    from arep.config import get_config
    from arep.simulation.engine import SimulationEngine

    engine = SimulationEngine(get_config().simulation)
    frame = engine.get_tick_frame(_minimal_world(), scenario_name="t", speed_limit=30.0)
    assert "emit_ts_ms" not in frame, "wall-clock must be stamped at the send site"


def test_the_same_world_hashes_the_same_twice():
    """Two serialisations of one world must agree, or nothing downstream can."""
    from arep.config import get_config
    from arep.simulation.engine import SimulationEngine

    engine = SimulationEngine(get_config().simulation)
    world = _minimal_world()
    a = engine.get_tick_frame(world, scenario_name="t", speed_limit=30.0)
    b = engine.get_tick_frame(world, scenario_name="t", speed_limit=30.0)
    assert a == b


def _minimal_world():
    from arep.core.state import VehicleState, WorldState, Vector2D

    return WorldState(
        sim_time=0.0,
        timestep_count=0,
        ego_vehicle=VehicleState(position=Vector2D(0.0, 0.0), velocity=10.0),
    )


def test_two_runs_of_the_same_seed_produce_the_same_frames():
    """The acceptance criterion, end to end through the live-run path."""
    from arep.api.sim_registry import start_run

    async def hash_of_one_run() -> str:
        run = await start_run(
            scenario_path=SCENARIO,
            model_name="EmergencyBrake",
            master_seed=42,
            tick_interval=0.0,          # headless: pacing is a delivery concern
        )
        if run.producer_task is not None:
            await run.producer_task
        return run.frame_hash

    first = asyncio.run(hash_of_one_run())
    second = asyncio.run(hash_of_one_run())

    assert first is not None, "a completed run must publish a digest"
    assert len(first) == 64
    assert first == second, "same seed produced different frames"


def test_a_different_model_produces_a_different_hash():
    """Otherwise the digest is measuring nothing.

    Deliberately varied by model rather than by seed. On this scenario the seed
    changes nothing: the NPC is constant_velocity, and the built-in "Random"
    model is registered as RandomModel(seed=42) with its own fixed internal RNG,
    so master_seed never reaches it. Two seeds therefore produce byte-identical
    runs here — correct behaviour for a deterministic scenario, and a poor
    choice of variable for this test.
    """
    from arep.api.sim_registry import start_run

    async def hash_for(model_name: str) -> str:
        run = await start_run(
            scenario_path=SCENARIO, model_name=model_name,
            master_seed=42, tick_interval=0.0,
        )
        if run.producer_task is not None:
            await run.producer_task
        return run.frame_hash

    assert asyncio.run(hash_for("EmergencyBrake")) != asyncio.run(hash_for("Random"))


# -- The hard rule ---------------------------------------------------------

def test_no_wall_clock_in_the_simulation_packages():
    """`git grep time.time` over the deterministic packages → zero hits.

    time.monotonic() is allowed and deliberately not matched here: run_async
    uses it to pace live delivery, which changes when a frame is handed to a
    socket, never what the frame contains.
    """
    result = subprocess.run(
        ["git", "grep", "-n", r"time\.time()", "--",
         "arep/simulation", "arep/core", "arep/evaluation"],
        cwd=REPO, capture_output=True, text=True,
    )
    hits = [
        line for line in result.stdout.splitlines()
        # The prose in engine.py's docstring explains why the call is gone.
        if line.strip() and "``time.time()``" not in line
    ]
    assert not hits, "wall-clock reached a deterministic package:\n" + "\n".join(hits)


def test_no_datetime_now_in_the_simulation_packages():
    result = subprocess.run(
        ["git", "grep", "-n", r"datetime\.now()\|utcnow()", "--",
         "arep/simulation", "arep/core", "arep/evaluation"],
        cwd=REPO, capture_output=True, text=True,
    )
    assert not result.stdout.strip(), (
        "wall-clock reached a deterministic package:\n" + result.stdout
    )


def test_no_bare_random_module_in_the_simulation_packages():
    """All randomness goes through RandomManager, seeded per run."""
    result = subprocess.run(
        ["git", "grep", "-n", r"^import random\|^from random import", "--",
         "arep/simulation", "arep/core", "arep/evaluation"],
        cwd=REPO, capture_output=True, text=True,
    )
    assert not result.stdout.strip(), (
        "unseeded randomness in a deterministic package:\n" + result.stdout
    )
