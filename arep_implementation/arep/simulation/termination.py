"""
ORION Termination Condition Handler.

Checks for simulation-ending conditions:
  - Timeout (sim_time >= max_duration)
  - Off-road (lateral offset exceeds lane boundary)
  - Goal reached (scenario-specific, placeholder)

Collision termination is handled separately in the engine after
collision detection.
"""

from __future__ import annotations

from typing import Optional

from arep.config import SimulationConfig
from arep.core.state import WorldState, TerminationReason
from arep.core.collision import CollisionDetector


class TerminationChecker:
    """Check for simulation termination conditions."""

    def __init__(self, config: SimulationConfig):
        self.config = config
        self.collision_detector = CollisionDetector(config)
        self.max_simulation_time = config.max_duration

    def check(self, world: WorldState) -> Optional[TerminationReason]:
        """
        Check all termination conditions.

        Called each timestep AFTER collision detection.

        Args:
            world: Current world state.

        Returns:
            TerminationReason if should terminate, None otherwise.
        """
        # Timeout
        if world.sim_time >= self.max_simulation_time:
            return TerminationReason.TIMEOUT

        # Off-road
        if self.collision_detector.check_off_road(world.ego_vehicle, world):
            return TerminationReason.OFF_ROAD

        # Goal reached (scenario-specific — not yet implemented)
        # if self._check_goal_reached(world):
        #     return TerminationReason.SUCCESS

        return None
