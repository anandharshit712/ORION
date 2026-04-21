"""
ORION Simulation Engine.

The main orchestrator that runs the deterministic simulation loop.

Step execution order (CRITICAL for determinism):
  1. Validate action
  2. Apply physics to ego vehicle
  3. Update dynamic objects
  4. Update traffic lights
  5. Check collisions
  6. Check other termination conditions
  7. Increment time
"""

from __future__ import annotations

import asyncio
import math
import time
from typing import Any, Awaitable, Callable, Dict, List, Optional, TYPE_CHECKING

from arep.config import SimulationConfig
from arep.core.state import WorldState, TerminationReason
from arep.core.action import Action
from arep.core.physics import VehiclePhysics
from arep.core.collision import CollisionDetector
from arep.core.observation import Observation
from arep.core.random_manager import RandomManager
from arep.simulation.world import WorldManager
from arep.simulation.termination import TerminationChecker
from arep.utils.logging_config import get_logger

if TYPE_CHECKING:
    from arep.models.interface import ModelInterface

logger = get_logger("simulation.engine")


class SimulationEngine:
    """
    Core simulation engine.

    Usage:
        engine = SimulationEngine(config)
        world = engine.step(world, action, rng)
        # or
        final = engine.run_simulation(world, model, rng)
    """

    def __init__(self, config: SimulationConfig):
        self.config = config
        self.dt = config.timestep

        # Initialize subsystems
        self.physics = VehiclePhysics(config)
        self.collision_detector = CollisionDetector(config)
        self.world_manager = WorldManager(config)
        self.termination_checker = TerminationChecker(config)

    def step(
        self,
        world: WorldState,
        action: Action,
        rng: RandomManager,
    ) -> WorldState:
        """
        Execute one simulation timestep.

        This is the MAIN simulation step function.
        Same inputs always produce the same output.

        Args:
            world: Current world state.
            action: Control action from model.
            rng: Random manager.

        Returns:
            New world state after dt seconds.
        """
        # 0. Already terminated?
        if world.is_terminated:
            return world

        # 1. Validate action
        if not self.physics.validate_action(action):
            new_world = world.copy()
            new_world.is_terminated = True
            new_world.termination_reason = TerminationReason.INVALID_ACTION
            return new_world

        # 2. Apply physics to ego vehicle
        new_ego = self.physics.update(world.ego_vehicle, action)

        # 3–4. Update dynamic objects and traffic lights
        new_world = world.copy()
        new_world.ego_vehicle = new_ego
        new_world = self.world_manager.update_dynamic_objects(
            new_world, self.dt, rng
        )
        new_world = self.world_manager.update_traffic_lights(new_world, rng)

        # 5. Check collisions
        collisions = self.collision_detector.detect_all_collisions(new_world)
        if collisions:
            new_world.has_collision = True
            new_world.collision_object_id = collisions[0].object_id
            new_world.collision_time = new_world.sim_time
            new_world.is_terminated = True
            new_world.termination_reason = TerminationReason.COLLISION

        # 6. Check other termination conditions
        if not new_world.is_terminated:
            termination = self.termination_checker.check(new_world)
            if termination is not None:
                new_world.is_terminated = True
                new_world.termination_reason = termination

        # 7. Increment time
        new_world.sim_time += self.dt
        new_world.timestep_count += 1
        new_world.last_action = action.copy()

        return new_world

    def run_simulation(
        self,
        initial_world: WorldState,
        model: ModelInterface,
        rng: RandomManager,
        max_steps: int = 3000,
    ) -> WorldState:
        """
        Run a complete simulation until termination or max_steps.

        Args:
            initial_world: Starting world state.
            model: Model controlling the ego vehicle.
            rng: Random manager.
            max_steps: Maximum number of timesteps (default: 60s at 50Hz).

        Returns:
            Final world state.
        """
        world = initial_world.copy()
        previous_world = None

        model.reset()

        logger.info(
            "Starting simulation (max_steps=%d, dt=%.4f)",
            max_steps, self.dt,
        )

        for step in range(max_steps):
            # Generate observation
            observation = Observation.from_world_state(world, previous_world)

            # Get action from model
            try:
                action = model.predict(observation)
            except Exception as e:
                logger.error("Model error at step %d: %s", step, e)
                world.is_terminated = True
                world.termination_reason = TerminationReason.MODEL_ERROR
                break

            # Execute timestep
            previous_world = world
            world = self.step(world, action, rng)

            # Check termination
            if world.is_terminated:
                break

        # If max_steps reached without other termination
        if not world.is_terminated:
            world.is_terminated = True
            world.termination_reason = TerminationReason.TIMEOUT

        logger.info(
            "Simulation complete: reason=%s, time=%.2fs, steps=%d",
            world.termination_reason.value if world.termination_reason else "unknown",
            world.sim_time,
            world.timestep_count,
        )

        return world

    # ── Async / streaming interface (P1.1) ───────────────────────────

    async def run_async(
        self,
        initial_world: WorldState,
        model: ModelInterface,
        rng: RandomManager,
        on_tick: Callable[[WorldState, Action], Awaitable[None]],
        max_steps: int = 3000,
        tick_interval: float = 0.02,
    ) -> WorldState:
        """
        Run a complete simulation in an async context, invoking ``on_tick``
        after each step. Paces to ``tick_interval`` seconds of wall clock
        per step (default 50 Hz). Pass ``tick_interval <= 0`` to run as
        fast as possible (used for batch/headless mode).

        Determinism is preserved: same seed → same world trajectory. Wall-
        clock pacing affects delivery latency, not simulation outputs.
        """
        world = initial_world.copy()
        previous_world: Optional[WorldState] = None

        model.reset()
        logger.info(
            "Starting async simulation (max_steps=%d, dt=%.4f, pace=%.4fs)",
            max_steps, self.dt, tick_interval,
        )

        next_deadline = time.monotonic() if tick_interval > 0 else 0.0

        for step in range(max_steps):
            observation = Observation.from_world_state(world, previous_world)

            try:
                action = model.predict(observation)
            except Exception as e:
                logger.error("Model error at step %d: %s", step, e)
                world.is_terminated = True
                world.termination_reason = TerminationReason.MODEL_ERROR
                await on_tick(world, Action.zero())
                break

            previous_world = world
            world = self.step(world, action, rng)

            await on_tick(world, action)

            if world.is_terminated:
                break

            if tick_interval > 0:
                next_deadline += tick_interval
                delay = next_deadline - time.monotonic()
                if delay > 0:
                    await asyncio.sleep(delay)
                else:
                    # Behind schedule — don't try to catch up, just yield.
                    next_deadline = time.monotonic()
                    await asyncio.sleep(0)
            else:
                await asyncio.sleep(0)

        if not world.is_terminated:
            world.is_terminated = True
            world.termination_reason = TerminationReason.TIMEOUT

        logger.info(
            "Async simulation complete: reason=%s, time=%.2fs, steps=%d",
            world.termination_reason.value if world.termination_reason else "unknown",
            world.sim_time,
            world.timestep_count,
        )
        return world

    def get_tick_frame(
        self,
        world: WorldState,
        action: Optional[Action] = None,
        scenario_name: str = "",
        speed_limit: float = 0.0,
    ) -> Dict[str, Any]:
        """
        Serialize the current world to the P1.1 WebSocket JSON frame schema.

        This frame is intended for live visualisation only. Authoritative
        metric values come from the offline ``CompositeEvaluator`` after
        the run ends; the ``monitor.metrics_current`` block here is a
        cheap per-tick proxy (collision + speed-limit compliance).
        """
        ego = world.ego_vehicle
        cos_h = math.cos(ego.heading)
        sin_h = math.sin(ego.heading)

        collision = world.has_collision
        speed_ok = speed_limit <= 0.0 or ego.velocity <= speed_limit * 1.10

        safety_score = 0.0 if collision else 1.0
        compliance_score = 1.0 if speed_ok else 0.7
        stability_score = 1.0
        reactivity_score = 1.0

        if collision or world.termination_reason == TerminationReason.OFF_ROAD:
            verdict = "FAIL"
        elif not world.is_terminated and world.sim_time < 0.5:
            verdict = "INCONCLUSIVE"
        else:
            verdict = "PASS"

        npcs: List[Dict[str, Any]] = []
        for obj in world.dynamic_objects:
            bt_state = ""
            behavior = world.npc_behaviors.get(obj.object_id)
            if isinstance(behavior, dict):
                bt_state = str(
                    behavior.get("current_state")
                    or behavior.get("state")
                    or behavior.get("type", "")
                )
            npcs.append({
                "id": obj.object_id,
                "x": round(obj.position.x, 4),
                "y": round(obj.position.y, 4),
                "z": 0.0,
                "heading": round(obj.heading, 4),
                "speed": round(obj.velocity, 4),
                "type": obj.object_type.value,
                "bt_state": bt_state,
            })

        frame: Dict[str, Any] = {
            "tick": world.timestep_count,
            "t_ms": round(world.sim_time * 1000.0, 2),
            "emit_ts_ms": round(time.time() * 1000.0, 2),
            "scenario_name": scenario_name,
            "ego": {
                "id": ego.object_id,
                "x": round(ego.position.x, 4),
                "y": round(ego.position.y, 4),
                "z": 0.0,
                "heading": round(ego.heading, 4),
                "speed": round(ego.velocity, 4),
                "accel_x": round(ego.acceleration * cos_h, 4),
                "accel_y": round(ego.acceleration * sin_h, 4),
                "active_sensors": [],
            },
            "npcs": npcs,
            "env": {
                "weather_type": world.weather_condition,
                "friction_mu": 1.0,
                "visibility_m": world.visibility,
                "time_of_day": "day",
            },
            "monitor": {
                "active_criteria": ["no_collision", "speed_compliance"],
                "metrics_current": {
                    "safety_score": round(safety_score, 4),
                    "compliance_score": round(compliance_score, 4),
                    "stability_score": round(stability_score, 4),
                    "reactivity_score": round(reactivity_score, 4),
                },
                "verdict_so_far": verdict,
            },
            "events": [],
            "is_terminated": world.is_terminated,
            "termination_reason": (
                world.termination_reason.value if world.termination_reason else None
            ),
        }

        if action is not None:
            frame["ego"]["last_action"] = {
                "steering": round(action.steering, 4),
                "throttle": round(action.throttle, 4),
                "brake": round(action.brake, 4),
            }

        return frame
