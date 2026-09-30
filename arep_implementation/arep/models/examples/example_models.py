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
    - Yielding to crossing traffic is a separate rule, because IDM has nothing
      to say about a perpendicular path. It gives way whenever a conflict exists
      rather than working out who has priority: `Observation` carries no sign,
      no stop line and no right-of-way, so the conservative reading is the only
      honest one. A real model should do better, and a scenario that rewards
      correctly *taking* priority will score this one as timid.

    What it does not do, so that nobody reads a passing score as more than it is:
    no route, no lane-change planning, no signal semantics beyond stopping for
    red and amber, and no notion of which lane it ought to be in.

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

    # Crossing traffic. IDM has nothing to say about a vehicle on a
    # perpendicular path: it is not a lead, it is never in the lane until it is
    # in the lane, and by then the decision has been made. Measured cost of not
    # handling it: the first version of this model collided on 40% of runs at a
    # four-way stop and failed every intersection scenario it met.
    CONFLICT_HORIZON = 5.0  # s, how far ahead a crossing path is considered
    CONFLICT_BAND = 9.0  # m, longitudinal half-width of the conflict zone
    CROSSING_SPEED = 0.5  # m/s, lateral speed below which it is not crossing

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

    def _crossing_conflict(self, obs: Observation):
        """The nearest object whose path crosses the ego's inside the horizon.

        Yielding is a longitudinal decision made on a lateral cue, which is why
        it cannot come out of IDM. The test is where each body will be, not
        where it is: an object is a conflict when it reaches the ego's line of
        travel at a moment when the ego is close enough to that point to matter.

        Returns the object, or None. The caller treats it as a stationary
        obstacle, which is the conservative reading -- this is a reference for
        judging whether a scenario is passable, so when in doubt it gives way.
        """
        nearest = None
        for obj in obs.objects:
            if abs(obj.relative_vy) < self.CROSSING_SPEED:
                continue
            # Opposite signs mean it is closing on the line y = 0; same signs
            # mean it is leaving, and a negative time is behind us.
            time_to_line = -obj.relative_y / obj.relative_vy
            if not 0.0 < time_to_line < self.CONFLICT_HORIZON:
                continue
            longitudinal_at_crossing = obj.relative_x + obj.relative_vx * time_to_line
            if abs(longitudinal_at_crossing) > self.CONFLICT_BAND:
                continue
            if nearest is None or time_to_line < nearest[0]:
                nearest = (time_to_line, obj)
        return nearest[1] if nearest else None

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

        # Crossing traffic is a stopping problem, not a following problem, and
        # it must not go through IDM. IDM keys its whole response off the
        # longitudinal closing speed, which for a perpendicular vehicle is
        # approximately zero -- so handing it one as a lead produces a gentle
        # response to something about to drive across the bonnet, and displaces
        # the real lead while doing it. Measured: routing crossings through IDM
        # cleared four intersection scenarios and made three others worse,
        # INT-010 going from 0.30 to 0.70 collisions.
        #
        # The requirement is to be stopped by the conflict point, so command the
        # deceleration that achieves exactly that and take whichever of the two
        # demands is harder.
        crossing = self._crossing_conflict(observation)
        if crossing is not None:
            distance = max(1.0, self._gap(crossing))
            accel = min(accel, -(observation.ego_velocity**2) / (2.0 * distance))

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
