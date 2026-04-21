"""
ORION NPC Behavior Tree Engine.

Each BT type implements a reactive state machine that reads world state
(ego position, velocity, TTC) and uses the seeded RNG for probabilistic
decisions — keeping everything deterministic while producing varied,
unpredictable behavior that challenges the AV model.

BT state is persisted in world.npc_behaviors[id]['_bt_state'] and
world.npc_behaviors[id]['_bt_data'], both deep-copied each tick by
WorldState.copy(), so state carries forward correctly.

Available BT types
------------------
Vehicles:
  hesitant_brake     — staged emergency brake with optional hesitation window
  hesitant_cut_in    — lane change that may abort if ego responds
  adaptive_tailgate  — tight follower that adjusts gap dynamically

Pedestrians / VRU:
  cautious_pedestrian — steps out, hesitates or retreats based on ego speed
  erratic_pedestrian  — random speed changes, pauses, and direction reversals
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

from arep.core.state import VehicleState, Vector2D

if TYPE_CHECKING:
    from arep.core.state import WorldState
    from arep.core.random_manager import RandomManager


# ── Module-level helpers ─────────────────────────────────────────────────────

def _sample(spec, gen) -> float:
    """Return a scalar or sample a {min, max} range uniformly."""
    if isinstance(spec, dict) and "min" in spec and "max" in spec:
        return float(gen.uniform(spec["min"], spec["max"]))
    return float(spec)


def _apply_accel(
    obj: VehicleState,
    accel: float,
    min_v: float,
    max_v: float,
    dt: float,
) -> VehicleState:
    """Clamp velocity and advance position longitudinally."""
    new_v = max(min_v, min(max_v, obj.velocity + accel * dt))
    new_obj = obj.copy()
    new_obj.velocity = new_v
    new_obj.acceleration = accel
    new_obj.position = Vector2D(
        obj.position.x + new_v * math.cos(obj.heading) * dt,
        obj.position.y + new_v * math.sin(obj.heading) * dt,
    )
    return new_obj


def _const_vel(obj: VehicleState, dt: float) -> VehicleState:
    """Advance position at constant velocity along heading."""
    new_obj = obj.copy()
    new_obj.position = Vector2D(
        obj.position.x + obj.velocity * math.cos(obj.heading) * dt,
        obj.position.y + obj.velocity * math.sin(obj.heading) * dt,
    )
    return new_obj


def _move_along_heading(obj: VehicleState, speed: float, dt: float) -> VehicleState:
    """
    Move obj at `speed` along its current heading.
    Negative speed reverses direction (heading flipped by pi).
    """
    actual_heading = obj.heading if speed >= 0 else (obj.heading + math.pi) % (2 * math.pi)
    act_speed = abs(speed)
    new_obj = obj.copy()
    new_obj.velocity = act_speed
    new_obj.position = Vector2D(
        obj.position.x + act_speed * math.cos(actual_heading) * dt,
        obj.position.y + act_speed * math.sin(actual_heading) * dt,
    )
    return new_obj


def _check_trigger(behavior: dict, obj: VehicleState, world: "WorldState") -> bool:
    """Shared trigger evaluation for all BT types."""
    if behavior["_triggered"]:
        return True
    params = behavior["parameters"]
    trigger_type = params.get("trigger_type", "time")
    trigger_value = params.get("trigger_value", 0.0)

    # trigger_value may itself be a sampled range stored at init time
    if isinstance(trigger_value, dict):
        return False  # not yet resolved — parameterizer should have resolved this

    fired = False
    if trigger_type == "time":
        fired = world.sim_time >= float(trigger_value)
    elif trigger_type == "proximity":
        dist = obj.position.distance_to(world.ego_vehicle.position)
        fired = dist <= float(trigger_value)
    elif trigger_type == "ttc":
        ttc = _compute_ttc(obj, world.ego_vehicle)
        fired = ttc is not None and ttc <= float(trigger_value)

    if fired:
        behavior["_triggered"] = True
        behavior["_trigger_time"] = world.sim_time
    return fired


def _compute_ttc(obj: VehicleState, ego: VehicleState) -> float | None:
    """1-D time-to-collision estimate; None if diverging."""
    dx = obj.position.x - ego.position.x
    dy = obj.position.y - ego.position.y
    gap = math.sqrt(dx * dx + dy * dy) - (obj.length / 2.0 + ego.length / 2.0)
    if gap <= 0.0:
        return 0.0
    rel_vx = ego.velocity * math.cos(ego.heading) - obj.velocity * math.cos(obj.heading)
    rel_vy = ego.velocity * math.sin(ego.heading) - obj.velocity * math.sin(obj.heading)
    rel_v = math.sqrt(rel_vx ** 2 + rel_vy ** 2)
    if rel_v < 1e-6:
        return None
    return gap / rel_v


# ── Base class ────────────────────────────────────────────────────────────────

class BaseBT:
    def tick(
        self,
        obj: VehicleState,
        behavior: dict,
        world: "WorldState",
        rng: "RandomManager",
        dt: float,
    ) -> VehicleState:
        raise NotImplementedError


# ── Vehicle BTs ───────────────────────────────────────────────────────────────

class HesitantBrakeBT(BaseBT):
    """
    Staged emergency brake with randomised hesitation phase.

    State machine:
      cruising ──trigger──→ initial_brake ──maybe──→ hesitation ──→ full_stop
                                          └──────────────────────→ full_stop

    Key parameters (all support {min, max} range syntax):
      initial_decel          m/s²  (negative)  e.g. -4.0 or {min:-6,max:-3}
      initial_brake_duration s                  e.g. {min:0.3,max:1.0}
      hesitation_prob        0–1               probability of a hesitation phase
      hesitation_duration    s                  e.g. {min:0.2,max:0.8}
      hesitation_accel       m/s²              slight release accel during hesitation
      final_decel            m/s²  (negative)  e.g. {min:-9.81,max:-7.0}
      min_velocity           m/s               floor velocity (default 0)
    """

    def tick(self, obj, behavior, world, rng, dt):
        params = behavior["parameters"]
        state = behavior.setdefault("_bt_state", "cruising")
        data = behavior.setdefault("_bt_data", {})
        gen = rng.get("traffic")

        if state == "cruising":
            if _check_trigger(behavior, obj, world):
                behavior["_bt_state"] = "initial_brake"
                data["initial_decel"] = _sample(params.get("initial_decel", -4.0), gen)
                data["hesitation_prob"] = float(params.get("hesitation_prob", 0.3))
                data["elapsed"] = 0.0
                data["phase_duration"] = _sample(
                    params.get("initial_brake_duration", {"min": 0.3, "max": 1.0}), gen
                )
                data["final_decel"] = _sample(
                    params.get("final_decel", {"min": -9.81, "max": -7.0}), gen
                )
            return _const_vel(obj, dt)

        elif state == "initial_brake":
            data["elapsed"] = data.get("elapsed", 0.0) + dt
            new_obj = _apply_accel(
                obj, data["initial_decel"], float(params.get("min_velocity", 0.0)), 50.0, dt
            )
            if data["elapsed"] >= data["phase_duration"]:
                if gen.random() < data["hesitation_prob"]:
                    behavior["_bt_state"] = "hesitation"
                    data["elapsed"] = 0.0
                    data["phase_duration"] = _sample(
                        params.get("hesitation_duration", {"min": 0.2, "max": 0.8}), gen
                    )
                    data["hesitation_accel"] = _sample(
                        params.get("hesitation_accel", {"min": 1.0, "max": 3.0}), gen
                    )
                else:
                    behavior["_bt_state"] = "full_stop"
                    data["elapsed"] = 0.0
            return new_obj

        elif state == "hesitation":
            data["elapsed"] = data.get("elapsed", 0.0) + dt
            # Release brakes momentarily — creates the "near-miss" pattern
            new_obj = _apply_accel(
                obj, data.get("hesitation_accel", 1.5),
                0.0, float(params.get("max_velocity", 30.0)), dt
            )
            if data["elapsed"] >= data["phase_duration"]:
                behavior["_bt_state"] = "full_stop"
                data["elapsed"] = 0.0
            return new_obj

        elif state == "full_stop":
            return _apply_accel(
                obj, data.get("final_decel", -9.0),
                float(params.get("min_velocity", 0.0)), 50.0, dt
            )

        return _const_vel(obj, dt)


class HesitantCutInBT(BaseBT):
    """
    Lane-change NPC that may abort mid-manoeuvre if the ego vehicle responds.

    State machine:
      cruising ──trigger──→ signaling ──→ cutting ──ego brakes & prob──→ aborting ──→ cruising
                                                  └──────────────────→ committed

    Key parameters:
      signal_duration    s       {min:0.3, max:1.2}
      lateral_target_y   m       target lane center y
      lateral_speed      m/s     {min:1.0, max:2.5}
      abort_prob         0–1     probability of aborting when ego responds
    """

    def tick(self, obj, behavior, world, rng, dt):
        params = behavior["parameters"]
        state = behavior.setdefault("_bt_state", "cruising")
        data = behavior.setdefault("_bt_data", {})
        gen = rng.get("traffic")

        if state == "cruising":
            if _check_trigger(behavior, obj, world):
                behavior["_bt_state"] = "signaling"
                data["elapsed"] = 0.0
                data["phase_duration"] = _sample(
                    params.get("signal_duration", {"min": 0.3, "max": 1.2}), gen
                )
                data["abort_prob"] = float(params.get("abort_prob", 0.35))
                data["lateral_target_y"] = float(params.get("lateral_target_y", 0.0))
                data["lateral_speed"] = _sample(
                    params.get("lateral_speed", {"min": 1.0, "max": 2.5}), gen
                )
                data["original_y"] = obj.position.y
            return _const_vel(obj, dt)

        elif state == "signaling":
            data["elapsed"] = data.get("elapsed", 0.0) + dt
            # Tiny drift toward target lane during signaling
            drift = math.copysign(0.2 * dt, data["lateral_target_y"] - obj.position.y)
            new_obj = obj.copy()
            new_obj.position = Vector2D(
                obj.position.x + obj.velocity * math.cos(obj.heading) * dt,
                obj.position.y + drift,
            )
            if data["elapsed"] >= data["phase_duration"]:
                behavior["_bt_state"] = "cutting"
            return new_obj

        elif state == "cutting":
            # Abort if ego has meaningfully braked or slowed down
            ego_braking = (
                world.ego_vehicle.acceleration < -1.5
                or world.ego_vehicle.velocity < obj.velocity - 2.5
            )
            if ego_braking and not data.get("committed") and gen.random() < data["abort_prob"]:
                behavior["_bt_state"] = "aborting"
                return _const_vel(obj, dt)

            target_y = data["lateral_target_y"]
            dy = target_y - obj.position.y
            if abs(dy) < 0.05:
                behavior["_bt_state"] = "committed"
                data["committed"] = True
                new_obj = obj.copy()
                new_obj.heading = 0.0 if math.cos(obj.heading) > 0 else math.pi
                new_obj.position = Vector2D(
                    obj.position.x + obj.velocity * dt, target_y
                )
                return new_obj

            lat_delta = math.copysign(min(data["lateral_speed"] * dt, abs(dy)), dy)
            lon_delta = obj.velocity * dt
            new_obj = obj.copy()
            new_obj.position = Vector2D(
                obj.position.x + lon_delta * math.cos(obj.heading),
                obj.position.y + lat_delta,
            )
            new_obj.heading = math.atan2(lat_delta, max(abs(lon_delta), 1e-6))
            # Keep heading in the same hemisphere as original
            if math.cos(obj.heading) < 0:
                new_obj.heading = math.pi - new_obj.heading
            return new_obj

        elif state == "committed":
            return _const_vel(obj, dt)

        elif state == "aborting":
            orig_y = data.get("original_y", obj.position.y)
            dy = orig_y - obj.position.y
            if abs(dy) < 0.05:
                # Reset so another cut-in attempt can happen later
                behavior["_bt_state"] = "cruising"
                behavior["_triggered"] = False
                return _const_vel(obj, dt)
            lat_delta = math.copysign(min(1.2 * dt, abs(dy)), dy)
            new_obj = obj.copy()
            new_obj.position = Vector2D(
                obj.position.x + obj.velocity * math.cos(obj.heading) * dt,
                obj.position.y + lat_delta,
            )
            return new_obj

        return _const_vel(obj, dt)


class AdaptiveTailgateBT(BaseBT):
    """
    Aggressive follower that maintains a randomised target TTC behind the ego.
    Accelerates when gap widens, brakes when gap closes.
    Small Gaussian noise each tick creates organic, non-robotic behaviour.

    Key parameters:
      target_ttc   {min:0.5, max:1.2}  desired time-headway in seconds
    """

    def tick(self, obj, behavior, world, rng, dt):
        params = behavior["parameters"]
        data = behavior.setdefault("_bt_data", {})
        gen = rng.get("traffic")

        # Initialise target TTC once
        if "target_ttc" not in data:
            data["target_ttc"] = _sample(
                params.get("target_ttc", {"min": 0.5, "max": 1.2}), gen
            )

        ego = world.ego_vehicle
        dist = obj.position.distance_to(ego.position)
        gap = dist - (obj.length / 2.0 + ego.length / 2.0)
        target_gap = data["target_ttc"] * max(obj.velocity, 1.0)
        gap_error = gap - target_gap

        # Proportional controller + noise
        accel = -2.0 * gap_error + float(gen.normal(0.0, 0.4))
        accel = max(-8.0, min(3.0, accel))

        return _apply_accel(obj, accel, 0.0, 45.0, dt)


# ── Pedestrian / VRU BTs ─────────────────────────────────────────────────────

class CautiousPedestrianBT(BaseBT):
    """
    Pedestrian crosses cautiously.  Reacts to ego speed and proximity:
      - Hesitates mid-crossing if ego is fast and close
      - Retreats to kerb if ego is very close and not braking
      - Resumes or re-tries after a pause

    State machine:
      waiting → stepping_out → crossing ──hesitation──→ hesitating → crossing
                                        └───────────────────────────→ retreating → waiting

    Key parameters:
      walk_speed          {min:0.7, max:1.4}  m/s
      start_y             float  y-coordinate of waiting position (for retreat check)
      mid_hesitation_prob 0–1   chance of hesitating once while crossing
    """

    def tick(self, obj, behavior, world, rng, dt):
        params = behavior["parameters"]
        state = behavior.setdefault("_bt_state", "waiting")
        data = behavior.setdefault("_bt_data", {})
        gen = rng.get("pedestrian")

        # Initialise walk speed once
        if "walk_speed" not in data:
            data["walk_speed"] = _sample(
                params.get("walk_speed", {"min": 0.7, "max": 1.4}), gen
            )
            data["start_y"] = obj.position.y

        ego = world.ego_vehicle

        if state == "waiting":
            if _check_trigger(behavior, obj, world):
                behavior["_bt_state"] = "stepping_out"
                data["step_speed"] = data["walk_speed"] * 0.5
            return obj.copy()

        elif state == "stepping_out":
            ego_dist = obj.position.distance_to(ego.position)

            if ego_dist < 7.0 and ego.velocity > 5.0:
                behavior["_bt_state"] = "retreating"
                return _move_along_heading(obj, -data["step_speed"], dt)

            if ego_dist < 14.0 and ego.velocity > 7.0 and gen.random() < 0.5:
                behavior["_bt_state"] = "hesitating"
                data["hesitation_elapsed"] = 0.0
                data["hesitation_duration"] = float(gen.uniform(0.5, 1.8))
                return obj.copy()

            new_obj = _move_along_heading(obj, data["step_speed"], dt)
            # After stepping ~0.5 m out, switch to full-speed crossing
            if abs(new_obj.position.y - data["start_y"]) > 0.5:
                behavior["_bt_state"] = "crossing"
                data["cross_speed"] = data["walk_speed"] * float(gen.uniform(0.9, 1.2))
            return new_obj

        elif state == "crossing":
            ego_dist = obj.position.distance_to(ego.position)

            if (
                ego_dist < 11.0
                and ego.velocity > 5.5
                and not data.get("hesitated_once")
                and gen.random() < float(params.get("mid_hesitation_prob", 0.3))
            ):
                behavior["_bt_state"] = "hesitating"
                data["hesitation_elapsed"] = 0.0
                data["hesitation_duration"] = float(gen.uniform(0.3, 1.0))
                data["hesitated_once"] = True
                return obj.copy()

            # Organic speed variation
            jitter = float(gen.normal(0.0, 0.08))
            speed = max(0.3, data.get("cross_speed", data["walk_speed"]) + jitter)
            return _move_along_heading(obj, speed, dt)

        elif state == "hesitating":
            data["hesitation_elapsed"] = data.get("hesitation_elapsed", 0.0) + dt
            ego_dist = obj.position.distance_to(ego.position)

            if data["hesitation_elapsed"] >= data.get("hesitation_duration", 0.8):
                if ego_dist < 5.5 and ego.velocity > 3.0:
                    behavior["_bt_state"] = "retreating"
                else:
                    behavior["_bt_state"] = "crossing"
                    data["cross_speed"] = data["walk_speed"] * float(gen.uniform(1.0, 1.3))
            return obj.copy()  # stationary while hesitating

        elif state == "retreating":
            new_obj = _move_along_heading(obj, -data["walk_speed"], dt)
            # Back near start → reset and wait to cross again
            if abs(new_obj.position.y - data["start_y"]) < 0.4:
                behavior["_bt_state"] = "waiting"
                behavior["_triggered"] = False
            return new_obj

        return obj.copy()


class ErraticPedestrianBT(BaseBT):
    """
    Maximally unpredictable pedestrian.  Random speed changes, pauses, and
    direction reversals on short, randomised decision intervals.
    Designed for VRU-008 to defeat any pattern-matching by the AV model.

    Key parameters:
      walk_speed_range   {min:0.4, max:1.6}   m/s
      decision_interval  {min:0.2, max:1.4}   s between state changes
    """

    def tick(self, obj, behavior, world, rng, dt):
        params = behavior["parameters"]
        state = behavior.setdefault("_bt_state", "waiting")
        data = behavior.setdefault("_bt_data", {})
        gen = rng.get("pedestrian")

        if state == "waiting":
            if _check_trigger(behavior, obj, world):
                behavior["_bt_state"] = "moving"
                data["current_speed"] = _sample(
                    params.get("walk_speed_range", {"min": 0.6, "max": 1.4}), gen
                )
                data["direction"] = 1.0
                data["next_decision_t"] = world.sim_time + _sample(
                    params.get("decision_interval", {"min": 0.3, "max": 1.2}), gen
                )
            return obj.copy()

        # Random decision at each interval
        if world.sim_time >= data.get("next_decision_t", float("inf")):
            roll = gen.random()
            if roll < 0.20:
                data["direction"] = -data.get("direction", 1.0)          # reverse
            elif roll < 0.45:
                data["current_speed"] = _sample(                           # change speed
                    params.get("walk_speed_range", {"min": 0.4, "max": 1.6}), gen
                )
            elif roll < 0.60:
                data["current_speed"] = 0.0                               # freeze
            elif roll < 0.65:
                # Brief sprint
                data["current_speed"] = _sample({"min": 1.8, "max": 2.5}, gen)
            # else: keep current behaviour

            data["next_decision_t"] = world.sim_time + _sample(
                params.get("decision_interval", {"min": 0.2, "max": 1.4}), gen
            )

        speed = data.get("current_speed", 1.0) * data.get("direction", 1.0)
        return _move_along_heading(obj, speed, dt)


# ── Registry ──────────────────────────────────────────────────────────────────

_BT_REGISTRY: dict[str, BaseBT] = {
    "hesitant_brake":       HesitantBrakeBT(),
    "hesitant_cut_in":      HesitantCutInBT(),
    "adaptive_tailgate":    AdaptiveTailgateBT(),
    "cautious_pedestrian":  CautiousPedestrianBT(),
    "erratic_pedestrian":   ErraticPedestrianBT(),
}


def get_bt(bt_type: str) -> BaseBT:
    """Return the BT instance for the given type string."""
    bt = _BT_REGISTRY.get(bt_type)
    if bt is None:
        raise ValueError(f"Unknown BT type: {bt_type!r}. Available: {list(_BT_REGISTRY)}")
    return bt
