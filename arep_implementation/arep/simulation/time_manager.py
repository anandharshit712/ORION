"""
ORION Deterministic Time Management.

CRITICAL RULES:
  1. Simulation time is NEVER derived from the wall clock
  2. Timestep is FIXED at initialization
  3. Time advances by exactly dt each step
  4. Wall clock is used ONLY for performance metrics
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Optional


@dataclass
class TimeMetrics:
    """Performance metrics about simulation timing."""
    sim_time: float          # Simulation time elapsed (seconds)
    wall_time: float         # Wall clock time elapsed (seconds)
    timesteps: int           # Number of timesteps executed
    real_time_factor: float  # sim_time / wall_time  (>1 = faster than real)


class TimeManager:
    """
    Strictly deterministic time management.

    Simulation time advances by exactly dt per step, regardless of
    how long the step takes in wall-clock time.
    """

    def __init__(self, dt: float):
        """
        Initialize time manager.

        Args:
            dt: Fixed timestep in seconds.
        """
        self.dt = dt
        self.sim_time: float = 0.0
        self.timesteps: int = 0
        self._start_wall_time: Optional[float] = None

    def start(self) -> None:
        """Start wall clock timer (for performance measurement only)."""
        self._start_wall_time = time.perf_counter()

    def step(self) -> None:
        """Advance simulation time by exactly one timestep."""
        self.sim_time += self.dt
        self.timesteps += 1

    def reset(self) -> None:
        """Reset time to zero."""
        self.sim_time = 0.0
        self.timesteps = 0
        self._start_wall_time = None

    def get_metrics(self) -> TimeMetrics:
        """
        Compute timing metrics.

        Returns:
            TimeMetrics with sim/wall times and real-time factor.
        """
        wall_time = 0.0
        if self._start_wall_time is not None:
            wall_time = time.perf_counter() - self._start_wall_time

        rtf = self.sim_time / wall_time if wall_time > 0 else 0.0

        return TimeMetrics(
            sim_time=self.sim_time,
            wall_time=wall_time,
            timesteps=self.timesteps,
            real_time_factor=rtf,
        )
