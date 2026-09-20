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
    # Phase 0.5 / D-05: signed lateral offset from the lane centerline, and the
    # width of the lane it was measured against. Recorded per step because lane
    # compliance cannot be reconstructed from (x, y) afterwards — that needs the
    # road geometry the run was driving on.
    # Negative is left of the direction of travel, positive is right.
    lane_offset: float = 0.0
    lane_width: float = 0.0
    # Half the ego body width, recorded with the offset so the in-lane test can
    # ask whether the *body* crossed the line rather than the centre point.
    vehicle_half_width: float = 0.0
    # False when the world had no lane under the ego (off the road, or a
    # scenario with no lane geometry). Such steps are excluded from the in-lane
    # fraction rather than counted as compliant.
    lane_valid: bool = False


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

        # Lane geometry (D-05). get_current_lane() is the same lookup the
        # observation builder uses, so the score and what the model saw agree.
        lane = world.get_current_lane()
        if lane is not None:
            lane_offset = lane.get_signed_lateral_offset(ego.position)
            lane_width = lane.width
            lane_valid = True
        else:
            lane_offset = 0.0
            lane_width = 0.0
            lane_valid = False

        self._snapshots.append(EgoSnapshot(
            sim_time=world.sim_time,
            x=ego.position.x,
            y=ego.position.y,
            heading=ego.heading,
            velocity=ego.velocity,
            acceleration=ego.acceleration,
            heading_rate=heading_rate,
            lane_offset=lane_offset,
            lane_width=lane_width,
            vehicle_half_width=ego.width / 2.0,
            lane_valid=lane_valid,
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
