"""
ORION Example Model Implementations.

Provides simple models for testing and CI:
  - ConstantActionModel: always returns the same action
  - EmergencyBrakeModel: always brakes
  - SimpleLaneKeepModel: basic PD-controller lane keeping
  - RandomModel: uniform random actions (deterministic with seed)
"""

from __future__ import annotations


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
            self.kp * observation.lane_offset + self.kd * observation.lane_heading_error
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


class ReferenceDriverModel(ModelInterface):
    """A competent baseline: IDM car-following, PD lane keeping, evasion.

    Every other model in this module is degenerate on purpose -- one fixed
    action, maximum braking always, steering with no longitudinal sense, or
    noise. That is fine for testing the harness and useless for testing the
    library: when `EmergencyBrake` fails a scenario, nothing distinguishes "the
    scenario correctly demands a behaviour this model lacks" from "the scenario
    is impossible". The claim that ORION's failures are the model's fault and
    not the scenario's needs a model that can actually pass, and this is it.

    It is a **reference, not a good driver.** The point is a defensible upper
    bound for scenario review, not a controller anyone would ship:

    - Longitudinal is the Intelligent Driver Model (Treiber, Hennecke & Helbing
      2000), which is the standard published baseline for exactly this. Its
      parameters here are conventional values, not fitted to anything.
    - Lateral is the same PD on lane offset that `SimpleLaneKeepModel` uses.
    - Evasion is a heuristic and is bounded to roughly one lane width of lateral
      travel, because `Observation` carries the ego's offset within its lane but
      not how many lanes exist or which are free. It steers away from an
      obstacle it cannot stop for, and it will not steer off a two-lane road.

    Deterministic: a pure function of the observation and `_prev_steering`.
    """

    # IDM parameters. Conventional values from the literature, deliberately not
    # tuned against this library -- a reference tuned to pass is not a reference.
    DESIRED_HEADWAY = 1.6  # s, time gap to the lead
    MIN_GAP = 5.0  # m, bumper-to-bumper at a standstill
    MAX_ACCEL = 2.0  # m/s^2, comfortable
    COMFORT_DECEL = 2.5  # m/s^2, comfortable
    DELTA = 4.0  # free-road acceleration exponent

    # Action normalisation. The Action fields are fractions of whatever the
    # scenario declares, so these are the nominal limits used to turn a
    # commanded acceleration into a pedal position.
    NOMINAL_ACCEL = 3.0
    NOMINAL_DECEL = 8.0

    # Threat handling
    EMERGENCY_TTC = 1.8  # s, below this the brake goes to the floor
    IN_PATH_HALF_WIDTH = 2.2  # m, lateral band counted as "in my lane"
    APPROACHING_HALF_WIDTH = 3.6  # m, wider band for something moving inward
    MAX_EVASION_OFFSET = 3.5  # m, roughly one lane; see the class docstring

    def __init__(
        self,
        desired_headway: float | None = None,
        kp: float = 0.35,
        kd: float = 0.15,
    ):
        self.desired_headway = (
            self.DESIRED_HEADWAY if desired_headway is None else desired_headway
        )
        self.kp = kp
        self.kd = kd
        self._prev_steering = 0.0

    # ── Perception helpers ────────────────────────────────────────────

    def _relevant_objects(self, obs: Observation) -> list:
        """Objects ahead that are in the ego path, or heading into it.

        The second half matters more than the first. A cut-in vehicle is not in
        the lane when the decision has to be made, and a model that waits for it
        to arrive before reacting has already spent the room -- so an object
        outside the lane but closing laterally counts.
        """
        out = []
        for obj in obs.objects:
            if obj.relative_x <= 0.0:
                continue
            lateral = abs(obj.relative_y)
            if lateral <= self.IN_PATH_HALF_WIDTH:
                out.append(obj)
            elif lateral <= self.APPROACHING_HALF_WIDTH and (
                obj.relative_y * obj.relative_vy < 0.0
            ):
                out.append(obj)
        return out

    @staticmethod
    def _gap(obj) -> float:
        """Bumper-to-bumper gap, not centre-to-centre.

        Centre distance overstates the room available by half of both vehicles,
        which at highway speed is most of a car length of imaginary margin.
        """
        return max(0.0, obj.relative_x - obj.length / 2.0 - 2.25)

    # ── Control ───────────────────────────────────────────────────────

    def _idm_acceleration(self, obs: Observation, lead) -> float:
        v = max(0.0, obs.ego_velocity)
        v0 = obs.speed_limit if obs.speed_limit > 0.0 else 25.0

        free_road = self.MAX_ACCEL * (1.0 - (v / v0) ** self.DELTA)
        if lead is None:
            return free_road

        gap = max(0.5, self._gap(lead))
        closing = -lead.relative_vx  # positive when the gap is shrinking
        desired_gap = self.MIN_GAP + max(
            0.0,
            v * self.desired_headway
            + (v * closing) / (2.0 * (self.MAX_ACCEL * self.COMFORT_DECEL) ** 0.5),
        )
        return free_road - self.MAX_ACCEL * (desired_gap / gap) ** 2

    def _time_to_collision(self, obs: Observation, lead) -> float:
        closing = -lead.relative_vx
        if closing <= 0.1:
            return float("inf")
        return self._gap(lead) / closing

    def _stopping_distance(self, obs: Observation) -> float:
        return obs.ego_velocity**2 / (2.0 * self.NOMINAL_DECEL)

    def predict(self, observation: Observation) -> Action:
        objects = self._relevant_objects(observation)
        lead = min(objects, key=self._gap) if objects else None

        # ── Longitudinal ──────────────────────────────────────────────
        accel = self._idm_acceleration(observation, lead)

        emergency = False
        if lead is not None:
            ttc = self._time_to_collision(observation, lead)
            if ttc < self.EMERGENCY_TTC or self._gap(lead) < self.MIN_GAP:
                emergency = True

        # A red or amber light is a stationary obstacle at the stop line. Amber
        # is treated as stop rather than go: this is a reference for reviewing
        # scenarios, and the conservative reading is the defensible one.
        light = observation.traffic_light_state
        if getattr(light, "name", str(light)).upper() in {"RED", "YELLOW", "AMBER"}:
            distance = max(1.0, observation.traffic_light_distance)
            if distance < self._stopping_distance(observation) + self.MIN_GAP:
                accel = min(accel, -observation.ego_velocity**2 / (2.0 * distance))

        if emergency:
            throttle, brake = 0.0, 1.0
        elif accel >= 0.0:
            throttle = clamp(accel / self.NOMINAL_ACCEL, 0.0, 1.0)
            brake = 0.0
        else:
            throttle = 0.0
            brake = clamp(-accel / self.NOMINAL_DECEL, 0.0, 1.0)

        # ── Lateral ───────────────────────────────────────────────────
        steering = -(
            self.kp * observation.lane_offset + self.kd * observation.lane_heading_error
        )

        # Evasion, only when braking alone cannot solve it. Bounded so the car
        # stays on a two-lane road: Observation says where the ego sits in its
        # lane, not how many lanes there are or which are free, so anything more
        # ambitious than "move away, about one lane's worth" would be guessing.
        if (
            emergency
            and lead is not None
            and self._gap(lead) < self._stopping_distance(observation)
        ):
            away = -1.0 if lead.relative_y >= 0.0 else 1.0
            if abs(observation.lane_offset) < self.MAX_EVASION_OFFSET:
                steering += away * 0.45

        steering = clamp(steering, -1.0, 1.0)
        # Rate limit: a reference that snaps the wheel scores itself badly on
        # stability and stops being a useful upper bound.
        steering = clamp(
            steering, self._prev_steering - 0.08, self._prev_steering + 0.08
        )
        self._prev_steering = steering

        return Action(steering, throttle, brake)

    def reset(self) -> None:
        self._prev_steering = 0.0

    @property
    def name(self) -> str:
        return "ReferenceDriver"


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
