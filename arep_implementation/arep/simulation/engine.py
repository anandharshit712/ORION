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

from typing import TYPE_CHECKING

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
