"""
ORION Data Collector.

Records per-timestep data during simulation for post-run metrics.

Tracks:
  - EgoSnapshot: position, velocity, acceleration, heading_rate
  - CollisionEvents: from collision detector
  - Actions: model outputs
  - TTC values: minimum TTC per step
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from arep.core.state import WorldState, TerminationReason
from arep.core.action import Action
from arep.core.ttc import TTCCalculator


@dataclass
class EgoSnapshot:
    """Ego vehicle state at a single timestep."""
    sim_time: float
    x: float
    y: float
    heading: float
    velocity: float
    acceleration: float
    heading_rate: float = 0.0


@dataclass
class SimulationRecord:
    """Complete record of a single simulation run."""
    # Per-timestep data
    ego_snapshots: List[EgoSnapshot] = field(default_factory=list)
    actions: List[Action] = field(default_factory=list)
    ttc_values: List[float] = field(default_factory=list)

    # Summary data
    duration: float = 0.0
    num_timesteps: int = 0
    termination_reason: Optional[str] = None
    has_collision: bool = False
    collision_time: Optional[float] = None
    collision_object_id: Optional[str] = None
    min_ttc_overall: float = 30.0
    speed_limit: float = 0.0

    # Metadata
    scenario_name: str = ""
    model_name: str = ""
    master_seed: int = 0


class DataCollector:
    """
    Collects per-timestep data during simulation.

    Usage:
        collector = DataCollector()
        # During simulation loop:
        collector.record_step(world, action, previous_world)
        # After simulation:
        record = collector.finalize(world)
    """

    def __init__(self, scenario_name: str = "", model_name: str = ""):
        self.scenario_name = scenario_name
        self.model_name = model_name
        self._snapshots: List[EgoSnapshot] = []
        self._actions: List[Action] = []
        self._ttc_values: List[float] = []
        self._ttc_calculator = TTCCalculator()
        self._prev_heading: Optional[float] = None

    def record_step(
        self,
        world: WorldState,
        action: Action,
        previous_world: Optional[WorldState] = None,
    ) -> None:
        """
        Record one timestep's data.

        Args:
            world: Current world state.
            action: Action taken this step.
            previous_world: Previous world state (for heading rate).
        """
        ego = world.ego_vehicle

        # Heading rate
        heading_rate = 0.0
        if previous_world is not None:
            import math
            dh = ego.heading - previous_world.ego_vehicle.heading
            dh = math.atan2(math.sin(dh), math.cos(dh))
            dt = world.sim_time - previous_world.sim_time
            if abs(dt) > 1e-9:
                heading_rate = dh / dt

        self._snapshots.append(EgoSnapshot(
            sim_time=world.sim_time,
            x=ego.position.x,
            y=ego.position.y,
            heading=ego.heading,
            velocity=ego.velocity,
            acceleration=ego.acceleration,
            heading_rate=heading_rate,
        ))
        self._actions.append(action.copy())

        # TTC
        min_ttc = self._ttc_calculator.compute_min_ttc(
            ego, world.dynamic_objects,
        )
        self._ttc_values.append(min_ttc)

    def finalize(self, final_world: WorldState) -> SimulationRecord:
        """
        Create completed SimulationRecord from collected data.

        Args:
            final_world: Final world state.

        Returns:
            Complete SimulationRecord for metrics computation.
        """
        return SimulationRecord(
            ego_snapshots=self._snapshots,
            actions=self._actions,
            ttc_values=self._ttc_values,
            duration=final_world.sim_time,
            num_timesteps=final_world.timestep_count,
            termination_reason=(
                final_world.termination_reason.value
                if final_world.termination_reason else None
            ),
            has_collision=final_world.has_collision,
            collision_time=final_world.collision_time,
            collision_object_id=final_world.collision_object_id,
            min_ttc_overall=(
                min(self._ttc_values) if self._ttc_values else 30.0
            ),
            speed_limit=final_world.get_speed_limit(),
            scenario_name=self.scenario_name,
            model_name=self.model_name,
        )

    def reset(self) -> None:
        """Clear all collected data."""
        self._snapshots.clear()
        self._actions.clear()
        self._ttc_values.clear()
        self._prev_heading = None
