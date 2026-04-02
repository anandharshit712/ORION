"""
ORION Example Model Implementations.

Provides simple models for testing and CI:
  - ConstantActionModel: always returns the same action
  - EmergencyBrakeModel: always brakes
  - SimpleLaneKeepModel: basic PD-controller lane keeping
  - RandomModel: uniform random actions (deterministic with seed)
"""

from __future__ import annotations

import math
from typing import Optional

import numpy as np

from arep.core.observation import Observation
from arep.core.action import Action
from arep.models.interface import ModelInterface
from arep.utils.validators import clamp


class ConstantActionModel(ModelInterface):
    """Always returns the same pre-configured action."""

    def __init__(
        self,
        steering: float = 0.0,
        throttle: float = 0.3,
        brake: float = 0.0,
    ):
        self.action = Action(steering, throttle, brake)

    def predict(self, observation: Observation) -> Action:
        return self.action.copy()

    def reset(self) -> None:
        pass

    @property
    def name(self) -> str:
        return "ConstantAction"


class EmergencyBrakeModel(ModelInterface):
    """Always applies full emergency braking."""

    def predict(self, observation: Observation) -> Action:
        return Action.emergency_brake()

    def reset(self) -> None:
        pass

    @property
    def name(self) -> str:
        return "EmergencyBrake"


class SimpleLaneKeepModel(ModelInterface):
    """
    Basic lane-keeping model using a PD controller.

    Steering = -(Kp × lane_offset + Kd × heading_error)
    Throttle is set to maintain target velocity.
    """

    def __init__(
        self,
        target_velocity: float = 20.0,
        kp: float = 0.3,
        kd: float = 0.1,
    ):
        self.target_velocity = target_velocity
        self.kp = kp
        self.kd = kd

    def predict(self, observation: Observation) -> Action:
        # Steering: PD control on lane offset
        steering = -(
            self.kp * observation.lane_offset
            + self.kd * observation.lane_heading_error
        )
        steering = clamp(steering, -1.0, 1.0)

        # Throttle/brake: simple velocity control
        speed_error = self.target_velocity - observation.ego_velocity

        if speed_error > 0:
            throttle = clamp(speed_error / 5.0, 0.0, 1.0)
            brake = 0.0
        else:
            throttle = 0.0
            brake = clamp(-speed_error / 5.0, 0.0, 1.0)

        return Action(steering, throttle, brake)

    def reset(self) -> None:
        pass

    @property
    def name(self) -> str:
        return "SimpleLaneKeep"


class RandomModel(ModelInterface):
    """
    Random action model (deterministic with seed).

    Useful for baseline comparisons: a random agent should
    perform poorly across all metrics.
    """

    def __init__(self, seed: int = 0):
        self.seed = seed
        self._rng = np.random.Generator(np.random.PCG64(seed))

    def predict(self, observation: Observation) -> Action:
        return Action(
            steering=float(self._rng.uniform(-1, 1)),
            throttle=float(self._rng.uniform(0, 1)),
            brake=float(self._rng.uniform(0, 0.3)),
        )

    def reset(self) -> None:
        self._rng = np.random.Generator(np.random.PCG64(self.seed))

    @property
    def name(self) -> str:
        return f"Random(seed={self.seed})"
