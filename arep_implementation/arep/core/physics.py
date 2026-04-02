"""
ORION Vehicle Physics Engine.

Two modes:
  KINEMATIC - Bicycle model with Euler integration (original, fast)
  DYNAMIC   - Enhanced dynamics with Pacejka tire model, mass, friction,
              weight transfer, and aerodynamic drag (realistic)

Kinematic equations (unchanged):
  x'   = v · cos(θ)
  y'   = v · sin(θ)
  θ'   = (v / L) · tan(δ)
  v'   = a

Dynamic equations (new):
  Tire forces:  F = D·sin(C·atan(B·α - E·(B·α - atan(B·α))))  (Pacejka)
  Longitudinal: F_x = F_drive - F_brake - F_drag - F_rolling
  Lateral:      F_y = F_front_lat + F_rear_lat
  Yaw:          τ   = F_front_lat·l_f - F_rear_lat·l_r
  Motion:       a = F_x/m,  α_yaw = τ/I_z,  v' = v + a·dt
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum
from typing import Optional

from arep.core.state import VehicleState, Vector2D
from arep.core.action import Action
from arep.utils.validators import clamp


# ── Physics Mode ─────────────────────────────────────────────────────────

class PhysicsMode(Enum):
    """Physics simulation mode."""
    KINEMATIC = "kinematic"   # Original bicycle model — fast, simple
    DYNAMIC = "dynamic"       # Enhanced with tire model, mass, friction


class SurfaceType(Enum):
    """Road surface types with associated friction coefficients."""
    DRY_ASPHALT = "dry"       # μ ≈ 1.0
    WET_ASPHALT = "wet"       # μ ≈ 0.5
    ICE = "ice"               # μ ≈ 0.2
    GRAVEL = "gravel"         # μ ≈ 0.6
    CUSTOM = "custom"         # User-specified μ

    def get_friction(self) -> float:
        """Default friction coefficient for this surface."""
        return {
            SurfaceType.DRY_ASPHALT: 1.0,
            SurfaceType.WET_ASPHALT: 0.5,
            SurfaceType.ICE: 0.2,
            SurfaceType.GRAVEL: 0.6,
            SurfaceType.CUSTOM: 1.0,
        }[self]


# ── Pacejka Tire Model ──────────────────────────────────────────────────

@dataclass
class PacejkaParams:
    """
    Pacejka 'Magic Formula' tire parameters.

    F = D · sin(C · atan(B·α − E·(B·α − atan(B·α))))

    Where:
      B = stiffness factor (how quickly force builds with slip)
      C = shape factor (determines curve shape — typically 1.0-1.9)
      D = peak force (maximum grip = μ·N, where N is normal load)
      E = curvature factor (controls shape near peak)
      α = slip angle (radians) or slip ratio (dimensionless)
    """
    B: float = 10.0     # Stiffness factor
    C: float = 1.9      # Shape factor (lateral) — 1.9 for typical car tires
    D: float = 1.0      # Peak factor (normalized — multiplied by μ·N at runtime)
    E: float = 0.97     # Curvature factor

    def compute_force(self, slip: float, normal_load: float,
                      friction: float = 1.0) -> float:
        """
        Compute tire force using Pacejka Magic Formula.

        Args:
            slip: Slip angle (radians) or slip ratio (dimensionless).
            normal_load: Normal force on this tire (N).
            friction: Surface friction coefficient (0.0 to 1.0+).

        Returns:
            Lateral or longitudinal force (N).
        """
        D_scaled = self.D * friction * normal_load
        Bs = self.B * slip
        return D_scaled * math.sin(
            self.C * math.atan(Bs - self.E * (Bs - math.atan(Bs)))
        )


# ── Dynamic Vehicle Parameters ──────────────────────────────────────────

@dataclass
class DynamicVehicleParams:
    """
    Physical parameters for the dynamic model.

    These extend the basic kinematic parameters with mass, inertia,
    and aerodynamic properties.
    """
    mass: float = 1500.0             # kg
    yaw_inertia: float = 2500.0      # kg·m² (moment of inertia about Z axis)
    cg_height: float = 0.5           # m (center of gravity height)
    track_width: float = 1.6         # m (distance between left/right wheels)
    front_weight_ratio: float = 0.55 # fraction of weight on front axle
    drag_coefficient: float = 0.3    # aerodynamic Cd
    frontal_area: float = 2.2        # m² (frontal cross-section)
    rolling_resistance: float = 0.015  # rolling resistance coefficient
    air_density: float = 1.225       # kg/m³

    # Tire parameters
    front_tire: PacejkaParams = None
    rear_tire: PacejkaParams = None

    def __post_init__(self):
        if self.front_tire is None:
            # Front tires: higher stiffness, slightly less peak
            self.front_tire = PacejkaParams(B=12.0, C=1.9, D=1.0, E=0.97)
        if self.rear_tire is None:
            # Rear tires: lower stiffness, higher peak
            self.rear_tire = PacejkaParams(B=10.0, C=1.9, D=1.0, E=0.97)


# ── Main Physics Engine ─────────────────────────────────────────────────

GRAVITY = 9.81  # m/s²


class VehiclePhysics:
    """
    Deterministic vehicle physics engine.

    Supports two modes:
      - KINEMATIC: Original bicycle model (fast, ~2μs/step)
      - DYNAMIC: Enhanced with Pacejka tires, mass, friction (~20-50μs/step)

    Guarantees:
      - Fixed timestep (never derived from wall clock)
      - Deterministic integration (same inputs → same output)
      - Consistent angle wrapping via atan2(sin, cos)
      - Constraint enforcement on every update

    Usage:
        # Kinematic (default — backward compatible)
        physics = VehiclePhysics(config)

        # Dynamic (new)
        physics = VehiclePhysics(config, mode=PhysicsMode.DYNAMIC)
        physics.set_surface_friction(0.5)  # wet road
    """

    def __init__(
        self,
        config,
        mode: PhysicsMode = PhysicsMode.KINEMATIC,
        vehicle_params: Optional[DynamicVehicleParams] = None,
    ):
        self.dt = config.timestep
        self.wheelbase = config.wheelbase
        self.max_velocity = config.max_velocity
        self.max_acceleration = config.max_acceleration
        self.max_deceleration = config.max_deceleration
        self.max_steering_angle = config.max_steering_angle
        self.mode = mode

        # Dynamic mode parameters
        self.params = vehicle_params or DynamicVehicleParams()
        self.surface_friction = 1.0  # default: dry asphalt

        # Derived: axle distances from CG
        self._lf = self.wheelbase * (1.0 - self.params.front_weight_ratio)
        self._lr = self.wheelbase * self.params.front_weight_ratio

        # Internal yaw rate state for dynamic mode
        self._yaw_rate = 0.0

    def set_surface(self, surface: SurfaceType) -> None:
        """Set road surface type (affects tire grip)."""
        self.surface_friction = surface.get_friction()

    def set_surface_friction(self, friction: float) -> None:
        """Set custom friction coefficient (0.0 to 1.0+)."""
        self.surface_friction = max(0.0, friction)

    def reset_dynamic_state(self) -> None:
        """Reset internal dynamic state (call on episode reset)."""
        self._yaw_rate = 0.0

    # ── Main Update ──────────────────────────────────────────────────

    def update(self, state: VehicleState, action: Action) -> VehicleState:
        """
        Apply one physics timestep.

        Dispatches to kinematic or dynamic model based on self.mode.

        Args:
            state: Current vehicle state.
            action: Control action.

        Returns:
            New VehicleState after dt seconds.
        """
        if self.mode == PhysicsMode.KINEMATIC:
            return self._update_kinematic(state, action)
        else:
            return self._update_dynamic(state, action)

    # ── Kinematic Model (Original) ───────────────────────────────────

    def _update_kinematic(self, state: VehicleState, action: Action) -> VehicleState:
        """
        Original bicycle model — unchanged from v1.

        x_{t+1} = x_t + v_t · cos(θ_t) · dt
        y_{t+1} = y_t + v_t · sin(θ_t) · dt
        θ_{t+1} = wrap(θ_t + (v_t / L) · tan(δ) · dt)
        v_{t+1} = clamp(v_t + a · dt, 0, v_max)
        """
        new_state = state.copy()

        steering_angle = action.get_steering_angle(self.max_steering_angle)
        acceleration = action.get_acceleration(
            self.max_acceleration, self.max_deceleration
        )

        steering_angle = clamp(
            steering_angle, -self.max_steering_angle, self.max_steering_angle
        )
        acceleration = clamp(
            acceleration, -self.max_deceleration, self.max_acceleration
        )

        v = state.velocity
        theta = state.heading
        dt = self.dt

        # Position update
        new_state.position = Vector2D(
            state.position.x + v * math.cos(theta) * dt,
            state.position.y + v * math.sin(theta) * dt,
        )

        # Heading update
        if abs(v) > 1e-6:
            dtheta = (v / self.wheelbase) * math.tan(steering_angle) * dt
            new_theta = theta + dtheta
            new_state.heading = math.atan2(
                math.sin(new_theta), math.cos(new_theta)
            )

        # Velocity update
        new_v = v + acceleration * dt
        new_state.velocity = clamp(new_v, 0.0, self.max_velocity)
        new_state.acceleration = acceleration

        return new_state

    # ── Dynamic Model (New) ──────────────────────────────────────────

    def _update_dynamic(self, state: VehicleState, action: Action) -> VehicleState:
        """
        Enhanced dynamic model with Pacejka tires, mass, and friction.

        Step order (deterministic):
          1. Compute steering angle and driver-requested acceleration
          2. Compute normal loads (static + weight transfer)
          3. Compute tire slip angles
          4. Compute tire lateral forces (Pacejka)
          5. Compute longitudinal forces (drive/brake + drag + rolling)
          6. Integrate: acceleration → velocity → position → heading
          7. Apply constraints

        Returns:
            New VehicleState after dt seconds.
        """
        new_state = state.copy()
        p = self.params
        dt = self.dt
        v = max(state.velocity, 0.0)
        theta = state.heading
        omega = self._yaw_rate  # yaw rate (rad/s)

        # 1. Driver inputs
        steering_angle = action.get_steering_angle(self.max_steering_angle)
        steering_angle = clamp(
            steering_angle, -self.max_steering_angle, self.max_steering_angle
        )
        driver_accel = action.get_acceleration(
            self.max_acceleration, self.max_deceleration
        )

        # 2. Normal loads on each axle
        #    Static distribution + longitudinal weight transfer
        total_weight = p.mass * GRAVITY
        F_front_static = total_weight * p.front_weight_ratio
        F_rear_static = total_weight * (1.0 - p.front_weight_ratio)

        # Weight transfer due to acceleration (forward accel → shifts to rear)
        weight_transfer_long = (
            p.mass * state.acceleration * p.cg_height / self.wheelbase
        )
        F_front_normal = max(F_front_static - weight_transfer_long, 100.0)
        F_rear_normal = max(F_rear_static + weight_transfer_long, 100.0)

        # 3. Slip angles
        #    Front: α_f = δ − atan2(v_y + ω·l_f, v_x)
        #    Rear:  α_r = −atan2(v_y − ω·l_r, v_x)
        #    In body frame: v_x = v (longitudinal), v_y ≈ 0 for small angles
        if v > 0.5:  # Avoid division instabilities at very low speed
            alpha_front = steering_angle - math.atan2(
                omega * self._lf, v
            )
            alpha_rear = -math.atan2(
                -omega * self._lr, v
            )
        else:
            # At very low speed, use simplified geometry
            alpha_front = 0.0
            alpha_rear = 0.0

        # 4. Lateral tire forces (Pacejka Magic Formula)
        F_lat_front = p.front_tire.compute_force(
            alpha_front, F_front_normal, self.surface_friction
        )
        F_lat_rear = p.rear_tire.compute_force(
            alpha_rear, F_rear_normal, self.surface_friction
        )

        # 5. Longitudinal forces
        #    Drive/brake force (from driver input; limited by tire friction)
        max_drive_force = self.surface_friction * total_weight * 0.5  # traction limit
        drive_force = clamp(
            driver_accel * p.mass,
            -p.mass * self.max_deceleration,
            min(p.mass * self.max_acceleration, max_drive_force),
        )

        # Aerodynamic drag: F_drag = ½ρCdAv²
        F_drag = 0.5 * p.air_density * p.drag_coefficient * p.frontal_area * v * v

        # Rolling resistance: F_roll = Crr · m · g
        F_rolling = p.rolling_resistance * total_weight

        # Net longitudinal force
        F_x = drive_force - F_drag - F_rolling
        if v < 0.1 and F_x < 0:
            F_x = 0.0  # Prevent reverse from drag/rolling at standstill

        # 6. Integration
        # Longitudinal acceleration
        ax = F_x / p.mass

        # Yaw dynamics: torque = F_lat_front · l_f · cos(δ) - F_lat_rear · l_r
        yaw_torque = (
            F_lat_front * self._lf * math.cos(steering_angle)
            - F_lat_rear * self._lr
        )
        alpha_yaw = yaw_torque / p.yaw_inertia  # angular acceleration

        # Yaw damping (prevents oscillation; models tire self-aligning torque)
        yaw_damping = -0.5 * omega
        alpha_yaw += yaw_damping

        # Update yaw rate
        new_omega = omega + alpha_yaw * dt
        # Clamp yaw rate to physically reasonable range
        max_yaw_rate = 1.5  # rad/s — ~86°/s, very aggressive turning
        new_omega = clamp(new_omega, -max_yaw_rate, max_yaw_rate)
        self._yaw_rate = new_omega

        # Update velocity
        new_v = v + ax * dt
        new_v = clamp(new_v, 0.0, self.max_velocity)

        # Update heading
        new_theta = theta + new_omega * dt
        new_theta = math.atan2(math.sin(new_theta), math.cos(new_theta))

        # Update position (using average of old and new heading for better accuracy)
        avg_theta = theta + 0.5 * new_omega * dt
        avg_v = 0.5 * (v + new_v)
        new_state.position = Vector2D(
            state.position.x + avg_v * math.cos(avg_theta) * dt,
            state.position.y + avg_v * math.sin(avg_theta) * dt,
        )

        # 7. Apply final state
        new_state.heading = new_theta
        new_state.velocity = new_v
        new_state.acceleration = ax

        return new_state

    # ── Utilities (both modes) ───────────────────────────────────────

    def validate_action(self, action: Action) -> bool:
        """Check whether an action is valid."""
        return action.is_valid()

    def compute_stopping_distance(self, velocity: float) -> float:
        """
        Compute distance to stop at max deceleration.

        Dynamic mode accounts for drag and friction.
        Kinematic: d = v² / (2·a_max)
        Dynamic:   d ≈ v² / (2·(a_max + drag/m + rolling))  [approximate]
        """
        if velocity <= 0:
            return 0.0

        if self.mode == PhysicsMode.KINEMATIC:
            return (velocity * velocity) / (2.0 * self.max_deceleration)

        # Dynamic: include friction-limited braking + drag
        p = self.params
        effective_decel = (
            self.surface_friction * self.max_deceleration
            + (0.5 * p.air_density * p.drag_coefficient
               * p.frontal_area * velocity * velocity) / p.mass
            + p.rolling_resistance * GRAVITY
        )
        effective_decel = max(effective_decel, 0.1)
        return (velocity * velocity) / (2.0 * effective_decel)

    def compute_time_to_stop(self, velocity: float) -> float:
        """Compute time to stop from given velocity."""
        if velocity <= 0:
            return 0.0

        if self.mode == PhysicsMode.KINEMATIC:
            return velocity / self.max_deceleration

        # Approximate for dynamic mode
        effective_decel = self.surface_friction * self.max_deceleration
        effective_decel = max(effective_decel, 0.1)
        return velocity / effective_decel

    def predict_future_position(
        self,
        state: VehicleState,
        time_horizon: float,
    ) -> Vector2D:
        """Predict position assuming constant velocity and heading."""
        return Vector2D(
            state.position.x + state.velocity * math.cos(state.heading) * time_horizon,
            state.position.y + state.velocity * math.sin(state.heading) * time_horizon,
        )

    def get_tire_forces(
        self, state: VehicleState, action: Action
    ) -> dict:
        """
        Diagnostic: compute current tire forces without stepping.

        Returns dict with front/rear lateral forces, slip angles,
        normal loads, and traction status.
        """
        if self.mode == PhysicsMode.KINEMATIC:
            return {"mode": "kinematic", "forces_available": False}

        p = self.params
        v = max(state.velocity, 0.0)
        omega = self._yaw_rate

        steering_angle = action.get_steering_angle(self.max_steering_angle)
        steering_angle = clamp(
            steering_angle, -self.max_steering_angle, self.max_steering_angle
        )

        total_weight = p.mass * GRAVITY
        F_front_normal = total_weight * p.front_weight_ratio
        F_rear_normal = total_weight * (1.0 - p.front_weight_ratio)

        if v > 0.5:
            alpha_front = steering_angle - math.atan2(omega * self._lf, v)
            alpha_rear = -math.atan2(-omega * self._lr, v)
        else:
            alpha_front = 0.0
            alpha_rear = 0.0

        F_lat_front = p.front_tire.compute_force(
            alpha_front, F_front_normal, self.surface_friction
        )
        F_lat_rear = p.rear_tire.compute_force(
            alpha_rear, F_rear_normal, self.surface_friction
        )

        max_front_grip = self.surface_friction * F_front_normal
        max_rear_grip = self.surface_friction * F_rear_normal

        return {
            "mode": "dynamic",
            "front_slip_angle_deg": math.degrees(alpha_front),
            "rear_slip_angle_deg": math.degrees(alpha_rear),
            "front_lateral_force_N": F_lat_front,
            "rear_lateral_force_N": F_lat_rear,
            "front_normal_load_N": F_front_normal,
            "rear_normal_load_N": F_rear_normal,
            "front_grip_ratio": abs(F_lat_front) / max(max_front_grip, 1.0),
            "rear_grip_ratio": abs(F_lat_rear) / max(max_rear_grip, 1.0),
            "surface_friction": self.surface_friction,
            "yaw_rate_deg_s": math.degrees(omega),
        }
