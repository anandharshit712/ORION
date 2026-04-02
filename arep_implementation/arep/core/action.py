"""
AREP Control Action Representations.

Defines:
  - Action: normalized steering/throttle/brake controls
  - ActionAlternative: steering/acceleration controls (simpler API)

Both support validation, clamping, and bidirectional conversion.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Dict

import numpy as np

from arep.utils.validators import clamp


# ── Action ───────────────────────────────────────────────────────────────

@dataclass
class Action:
    """
    Control action from the model.

    All values are normalized to standard ranges:
      steering:  [-1, 1]  (left to right)
      throttle:  [0, 1]   (no throttle to full throttle)
      brake:     [0, 1]   (no brake to full brake)

    Brake takes precedence over throttle when both are nonzero.
    """
    steering: float = 0.0
    throttle: float = 0.0
    brake: float = 0.0

    def __post_init__(self):
        self._validate()

    def _validate(self):
        """Clamp values to valid ranges."""
        self.steering = clamp(self.steering, -1.0, 1.0)
        self.throttle = clamp(self.throttle, 0.0, 1.0)
        self.brake = clamp(self.brake, 0.0, 1.0)

    # ── Conversion to physical values ────────────────────────────────

    def get_acceleration(
        self,
        max_acceleration: float = 3.0,
        max_deceleration: float = 8.0,
    ) -> float:
        """
        Convert throttle/brake to net acceleration.

        Brake takes precedence: if brake > 0, result is negative.

        Args:
            max_acceleration: Maximum forward acceleration (m/s²).
            max_deceleration: Maximum braking deceleration (m/s²).

        Returns:
            Net acceleration (m/s²). Positive = accelerate, negative = brake.
        """
        if self.brake > 0.0:
            return -self.brake * max_deceleration
        return self.throttle * max_acceleration

    def get_steering_angle(self, max_steering: float = 0.5) -> float:
        """
        Convert normalized steering to physical steering angle.

        Args:
            max_steering: Maximum steering angle (radians).

        Returns:
            Steering angle (radians).
        """
        return self.steering * max_steering

    # ── Constructors ─────────────────────────────────────────────────

    @staticmethod
    def zero() -> Action:
        """No-op action: no steering, no throttle, no brake."""
        return Action(0.0, 0.0, 0.0)

    @staticmethod
    def emergency_brake() -> Action:
        """Full emergency brake with no steering."""
        return Action(0.0, 0.0, 1.0)

    # ── Serialization ────────────────────────────────────────────────

    def to_dict(self) -> Dict[str, float]:
        return {
            "steering": self.steering,
            "throttle": self.throttle,
            "brake": self.brake,
        }

    @staticmethod
    def from_dict(d: Dict[str, float]) -> Action:
        return Action(
            steering=d.get("steering", 0.0),
            throttle=d.get("throttle", 0.0),
            brake=d.get("brake", 0.0),
        )

    def to_array(self) -> np.ndarray:
        """Convert to numpy array [steering, throttle, brake]."""
        return np.array(
            [self.steering, self.throttle, self.brake], dtype=np.float64
        )

    @staticmethod
    def from_array(arr: np.ndarray) -> Action:
        """Create from numpy array."""
        return Action(float(arr[0]), float(arr[1]), float(arr[2]))

    def copy(self) -> Action:
        return Action(self.steering, self.throttle, self.brake)

    def is_valid(self) -> bool:
        """Check if values are in valid ranges."""
        return (
            -1.0 <= self.steering <= 1.0
            and 0.0 <= self.throttle <= 1.0
            and 0.0 <= self.brake <= 1.0
        )

    def __repr__(self) -> str:
        return (
            f"Action(steer={self.steering:.3f}, "
            f"throttle={self.throttle:.3f}, "
            f"brake={self.brake:.3f})"
        )


# ── ActionAlternative ────────────────────────────────────────────────────

@dataclass
class ActionAlternative:
    """
    Alternative action format using steering + acceleration.

    Simpler for models that prefer to output a single acceleration value
    instead of separate throttle/brake.
    """
    steering: float = 0.0        # [-1, 1]
    acceleration: float = 0.0    # m/s² (positive = accel, negative = brake)

    def __post_init__(self):
        self.steering = clamp(self.steering, -1.0, 1.0)

    def to_action(
        self,
        max_acceleration: float = 3.0,
        max_deceleration: float = 8.0,
    ) -> Action:
        """
        Convert to standard Action.

        Positive acceleration → throttle, negative → brake.
        """
        if self.acceleration >= 0:
            throttle = min(self.acceleration / max_acceleration, 1.0)
            brake = 0.0
        else:
            throttle = 0.0
            brake = min(abs(self.acceleration) / max_deceleration, 1.0)
        return Action(self.steering, throttle, brake)

    @staticmethod
    def from_action(
        action: Action,
        max_acceleration: float = 3.0,
        max_deceleration: float = 8.0,
    ) -> ActionAlternative:
        """Create from a standard Action."""
        accel = action.get_acceleration(max_acceleration, max_deceleration)
        return ActionAlternative(action.steering, accel)

    def to_dict(self) -> Dict[str, float]:
        return {"steering": self.steering, "acceleration": self.acceleration}

    def copy(self) -> ActionAlternative:
        return ActionAlternative(self.steering, self.acceleration)
