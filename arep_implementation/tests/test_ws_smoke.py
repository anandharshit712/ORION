"""
Smoke tests for P1.1 live-streaming core.

Covers the streaming primitives (SimulationEngine.run_async +
get_tick_frame + SimulationRegistry pub/sub) directly. The HTTP/WS
layer is verified manually via ``scripts/ws_smoke.py`` against a live
uvicorn server — Starlette's TestClient does not reliably cooperate
with long-lived background tasks in the same event loop.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from arep.api.sim_registry import get_registry, start_run


SCENARIO = str(
    Path(__file__).parent.parent
    / "scenarios" / "basic" / "straight_road_lead_vehicle.yaml"
)


def _run(coro):
    return asyncio.run(coro)


async def _live_run_streams_frames():
    run = await start_run(
        scenario_path=SCENARIO,
        model_name="EmergencyBrake",
        master_seed=42,
        tick_interval=0.0,  # run as fast as possible
    )
    assert run.status == "running"
    assert run.run_id
    assert run.scenario_name

    q = run.subscribe()
    frames = []
    for _ in range(10):
        frame = await q.get()
        if frame is None:
            break
        frames.append(frame)

    run.unsubscribe(q)

    assert len(frames) >= 5

    first = frames[0]
    for key in ("tick", "t_ms", "ego", "npcs", "env", "monitor", "events"):
        assert key in first, f"missing top-level key: {key}"
    for key in ("id", "x", "y", "heading", "speed", "accel_x", "accel_y"):
        assert key in first["ego"], f"missing ego key: {key}"
    assert "metrics_current" in first["monitor"]
    assert "verdict_so_far" in first["monitor"]

    ticks = [f["tick"] for f in frames]
    assert all(b >= a for a, b in zip(ticks, ticks[1:])), ticks

    if run.producer_task is not None:
        run.producer_task.cancel()
    await get_registry().remove(run.run_id)


async def _determinism_same_seed():
    run_a = await start_run(SCENARIO, "EmergencyBrake", 42, tick_interval=0.0)
    run_b = await start_run(SCENARIO, "EmergencyBrake", 42, tick_interval=0.0)

    qa = run_a.subscribe()
    qb = run_b.subscribe()
    frames_a = [await qa.get() for _ in range(5)]
    frames_b = [await qb.get() for _ in range(5)]

    for fa, fb in zip(frames_a, frames_b):
        assert fa["ego"]["x"] == fb["ego"]["x"]
        assert fa["ego"]["y"] == fb["ego"]["y"]
        assert fa["ego"]["speed"] == fb["ego"]["speed"]

    for r in (run_a, run_b):
        if r.producer_task is not None:
            r.producer_task.cancel()
        await get_registry().remove(r.run_id)


async def _registry_lookup():
    run = await start_run(SCENARIO, "ConstantAction", 7, tick_interval=0.0)
    registry = get_registry()
    assert await registry.get(run.run_id) is run
    await registry.remove(run.run_id)
    assert await registry.get(run.run_id) is None
    if run.producer_task is not None:
        run.producer_task.cancel()


# ── pytest entrypoints ───────────────────────────────────────────────────

def test_live_run_streams_frames():
    _run(_live_run_streams_frames())


def test_determinism_same_seed():
    _run(_determinism_same_seed())


def test_registry_lookup():
    _run(_registry_lookup())
