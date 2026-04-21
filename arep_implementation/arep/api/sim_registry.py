"""
ORION Live Simulation Registry.

Tracks in-flight simulations that are being streamed over WebSocket.
Each ``LiveRun`` owns a producer task that steps the SimulationEngine
at wall-clock rate and publishes JSON tick frames to all attached
subscriber queues (pub/sub, non-blocking — slow consumers drop frames
rather than stalling the producer).

Designed to live entirely inside the FastAPI event loop. All methods
that touch shared state are ``async`` and guarded by ``asyncio.Lock``.
"""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from arep.utils.logging_config import get_logger

logger = get_logger("api.sim_registry")


# ── LiveRun ──────────────────────────────────────────────────────────────

@dataclass
class LiveRun:
    """
    One live, streamable simulation run.

    Subscribers attach an ``asyncio.Queue`` via ``subscribe()``; the
    producer calls ``publish(frame)`` each tick. When the run ends
    (naturally or by error) a ``None`` sentinel is pushed to each queue.
    """
    run_id: str
    scenario_path: str
    scenario_name: str
    model_name: str
    master_seed: int
    status: str                       # "running" | "complete" | "failed" | "cancelled"
    started_at: str
    completed_at: Optional[str] = None
    producer_task: Optional[asyncio.Task] = None
    subscribers: List[asyncio.Queue] = field(default_factory=list)
    last_frame: Optional[Dict[str, Any]] = None
    final_metrics: Optional[Dict[str, Any]] = None
    error: Optional[str] = None

    # Pub/sub ────────────────────────────────────────────────────────

    def subscribe(self, maxsize: int = 64) -> asyncio.Queue:
        """Attach a new subscriber queue. Seeds with the latest frame so
        late joiners render the current world immediately."""
        q: asyncio.Queue = asyncio.Queue(maxsize=maxsize)
        if self.last_frame is not None:
            try:
                q.put_nowait(self.last_frame)
            except asyncio.QueueFull:
                pass
        self.subscribers.append(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        if q in self.subscribers:
            self.subscribers.remove(q)

    def publish(self, frame: Dict[str, Any]) -> None:
        """Publish to all subscribers. Drops oldest on queue overflow."""
        self.last_frame = frame
        for q in list(self.subscribers):
            if q.full():
                try:
                    q.get_nowait()
                except asyncio.QueueEmpty:
                    pass
            try:
                q.put_nowait(frame)
            except asyncio.QueueFull:
                pass

    def signal_end(self) -> None:
        """Push the None sentinel to every subscriber."""
        for q in list(self.subscribers):
            if q.full():
                try:
                    q.get_nowait()
                except asyncio.QueueEmpty:
                    pass
            try:
                q.put_nowait(None)
            except asyncio.QueueFull:
                pass

    def to_dict(self) -> Dict[str, Any]:
        m = self.final_metrics or {}
        return {
            "run_id": self.run_id,
            "id": self.run_id,
            "scenario_path": self.scenario_path,
            "scenario_name": self.scenario_name,
            "model_name": self.model_name,
            "master_seed": self.master_seed,
            "status": self.status,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "subscribers": len(self.subscribers),
            "error": self.error,
            "composite_score": m.get("composite_score", 0.0),
            "safety_score": m.get("safety_score", 0.0),
            "compliance_score": m.get("compliance_score", 0.0),
            "stability_score": m.get("stability_score", 0.0),
            "reactivity_score": m.get("reactivity_score", 0.0),
            "collision_occurred": m.get("collision_occurred", False),
        }


# ── Registry ─────────────────────────────────────────────────────────────

class SimulationRegistry:
    """Thread-safe (asyncio-safe) registry of live runs."""

    def __init__(self) -> None:
        self._runs: Dict[str, LiveRun] = {}
        self._lock = asyncio.Lock()

    async def register(self, run: LiveRun) -> None:
        async with self._lock:
            self._runs[run.run_id] = run

    async def get(self, run_id: str) -> Optional[LiveRun]:
        async with self._lock:
            return self._runs.get(run_id)

    async def remove(self, run_id: str) -> None:
        async with self._lock:
            self._runs.pop(run_id, None)

    async def list(self) -> List[LiveRun]:
        async with self._lock:
            return list(self._runs.values())


_registry: Optional[SimulationRegistry] = None


def get_registry() -> SimulationRegistry:
    """Return the process-wide singleton registry."""
    global _registry
    if _registry is None:
        _registry = SimulationRegistry()
    return _registry


# ── Starter helper ───────────────────────────────────────────────────────

async def start_run(
    scenario_path: str,
    model_name: str,
    master_seed: int,
    tick_interval: float = 0.02,
) -> LiveRun:
    """
    Bootstrap a live simulation run and kick off its producer task.

    Returns immediately once the run is registered; the simulation
    runs in the background until completion or error. Subscribers can
    attach at any time via the WebSocket endpoint.
    """
    # Lazy imports to avoid circular dependencies with api.routes
    from arep.api.routes import _get_model
    from arep.config import get_config
    from arep.core.random_manager import RandomManager
    from arep.scenario.executor import ScenarioExecutor
    from arep.scenario.parser import ScenarioParser
    from arep.simulation.engine import SimulationEngine

    parser = ScenarioParser()
    scenario_def, _ = parser.parse_file(scenario_path)

    sim_config = get_config().simulation
    engine = SimulationEngine(sim_config)
    scenario_executor = ScenarioExecutor(sim_config)
    rng = RandomManager(master_seed)
    initial_world = scenario_executor.create_initial_world(scenario_def, rng)
    model = _get_model(model_name)

    speed_limit = initial_world.get_speed_limit()
    max_steps = int(scenario_def.duration / sim_config.timestep) or sim_config.max_steps

    run_id = uuid.uuid4().hex
    run = LiveRun(
        run_id=run_id,
        scenario_path=scenario_path,
        scenario_name=scenario_def.name,
        model_name=model_name,
        master_seed=master_seed,
        status="running",
        started_at=datetime.now(timezone.utc).isoformat(),
    )

    async def on_tick(world, action) -> None:
        frame = engine.get_tick_frame(
            world,
            action=action,
            scenario_name=scenario_def.name,
            speed_limit=speed_limit,
        )
        run.publish(frame)

    async def producer() -> None:
        try:
            await engine.run_async(
                initial_world=initial_world,
                model=model,
                rng=rng,
                on_tick=on_tick,
                max_steps=max_steps,
                tick_interval=tick_interval,
            )
            run.status = "complete"
            if run.last_frame:
                mon = run.last_frame.get("monitor", {})
                m = mon.get("metrics_current", {})
                verdict = mon.get("verdict_so_far", "INCONCLUSIVE")
                run.final_metrics = {
                    "composite_score": (
                        m.get("safety_score", 0.0) * 0.5
                        + m.get("compliance_score", 0.0) * 0.2
                        + m.get("stability_score", 0.0) * 0.15
                        + m.get("reactivity_score", 0.0) * 0.15
                    ),
                    "safety_score": m.get("safety_score", 0.0),
                    "compliance_score": m.get("compliance_score", 0.0),
                    "stability_score": m.get("stability_score", 0.0),
                    "reactivity_score": m.get("reactivity_score", 0.0),
                    "collision_occurred": verdict == "FAIL",
                }
        except asyncio.CancelledError:
            run.status = "cancelled"
            raise
        except Exception as e:  # pragma: no cover — defensive
            run.status = "failed"
            run.error = str(e)
            logger.exception("Live run %s failed", run_id)
        finally:
            run.completed_at = datetime.now(timezone.utc).isoformat()
            run.signal_end()

    registry = get_registry()
    await registry.register(run)
    run.producer_task = asyncio.create_task(producer(), name=f"sim-{run_id}")
    logger.info(
        "Live run started: run_id=%s scenario=%s model=%s seed=%s",
        run_id, scenario_def.name, model_name, master_seed,
    )
    return run
