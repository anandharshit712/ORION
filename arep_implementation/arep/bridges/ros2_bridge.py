"""
ORION side of the ROS2 bridge.  [Phase 4.1]

    ORION simulation (this module)  <-- ZeroMQ -->  ros2_bridge_node.py  <-- topics -->  AV stack

A ROS2 stack is evaluated as a model like any other: `Ros2BridgeModel` is a
`ModelInterface`, so a run goes through `EvaluationRunner`, `ModelWrapper` and
`CompositeEvaluator` exactly as a built-in model's does. Nothing about scoring
is bridge-specific.

Each tick the model publishes the `Observation` -- the same wire format the
sandbox and HTTP adapters use, so a ROS2 stack sees exactly what every other
model sees -- and returns the most recent control the stack has sent.

**A run through this bridge is not reproducible from its seed.** The stack runs
on its own clock, so which control lands on which tick depends on wall-clock
timing. The scenario draw is still seeded and identical; the trajectory is not,
and the frame hash will differ between two runs. That is the cost of driving a
real-time stack in real time, and the reason this model paces itself to the
simulation timestep instead of running as fast as it can.

Control semantics (`ackermann_msgs/AckermannDrive`): `steering_angle` is the
front-wheel angle, positive counter-clockwise -- the same sense as ORION's
heading, so it maps straight across. `speed` is the target speed and
`acceleration` caps how hard to get there, 0 meaning "the vehicle's limit".

No fresh control within `stale_after` seconds means the ego **coasts**
(`Action.zero()`): no throttle, no brake, wheels straight. That is what a real
car does when its driving stack goes silent, so a dead stack is scored as one
rather than crashing the run or freezing the last command forever.

Run one scenario against a connected bridge:

    python -m arep.bridges.ros2_bridge --scenario-id LON-003 --seed 42
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import time
from typing import Any, Dict, Optional

from arep.bridges.zmq_transport import (
    DEFAULT_CONTROL_ENDPOINT,
    DEFAULT_TICK_ENDPOINT,
    ControlSubscriber,
    SimPublisher,
)
from arep.config import SimulationConfig, get_config
from arep.core.action import Action
from arep.core.observation import Observation
from arep.models.interface import ModelInterface
from arep.utils.logging_config import get_logger

logger = get_logger("bridges.ros2")

# ponytail: proportional speed tracking, 1/s. A stack that wants finer
# longitudinal control sends `acceleration` and a reachable `speed`.
SPEED_GAIN = 1.0


def control_to_action(
    control: Dict[str, Any], ego_velocity: float, sim: SimulationConfig
) -> Action:
    """Turn an AckermannDrive-shaped dict into a normalised ORION Action."""
    steering = float(control.get("steering_angle", 0.0)) / sim.max_steering_angle
    target = max(0.0, float(control.get("speed", 0.0)))  # ORION has no reverse
    limit = abs(float(control.get("acceleration", 0.0)))

    accel = SPEED_GAIN * (target - ego_velocity)
    if limit > 0.0:
        accel = max(-limit, min(limit, accel))

    throttle = accel / sim.max_acceleration if accel > 0 else 0.0
    brake = -accel / sim.max_deceleration if accel < 0 else 0.0
    return Action(
        steering=max(-1.0, min(1.0, steering)),
        throttle=min(1.0, throttle),
        brake=min(1.0, brake),
    )


class Ros2BridgeModel(ModelInterface):
    """A ROS2 stack, reached over ZeroMQ through `ros2_bridge_node.py`."""

    def __init__(
        self,
        tick_endpoint: str = DEFAULT_TICK_ENDPOINT,
        control_endpoint: str = DEFAULT_CONTROL_ENDPOINT,
        stale_after: float = 0.5,
        connect_timeout: float = 30.0,
        sim_config: Optional[SimulationConfig] = None,
        tick_interval: Optional[float] = None,
    ):
        self.tick_endpoint = tick_endpoint
        self.control_endpoint = control_endpoint
        self.stale_after = stale_after
        self.connect_timeout = connect_timeout
        self.sim = sim_config or get_config().simulation
        # Wall-clock seconds per tick. Real time by default; tests shorten it.
        self.tick_interval = (
            self.sim.timestep if tick_interval is None else tick_interval
        )

        self._pub: Optional[SimPublisher] = None
        self._sub: Optional[ControlSubscriber] = None
        self._control: Optional[Dict[str, Any]] = None
        self._control_at = 0.0
        self._next_tick = 0.0
        self._seq = 0
        self.coasted_ticks = 0

    @property
    def name(self) -> str:
        return "ROS2Bridge"

    # ── ModelInterface ──────────────────────────────────────────────

    def reset(self) -> None:
        """Bind the sockets and wait for the bridge -- the run starts paused."""
        if self._pub is None:
            self._pub = SimPublisher(self.tick_endpoint)
            self._sub = ControlSubscriber(self.control_endpoint)
        self._control = None
        self._seq = 0
        self.coasted_ticks = 0

        # The bridge heartbeats once a second; any message means it is there.
        # Waiting here is what keeps tick 0 from being published to nobody.
        deadline = time.monotonic() + self.connect_timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise ConnectionError(
                    f"No ROS2 bridge on {self.control_endpoint} after "
                    f"{self.connect_timeout:.0f}s -- is ros2_bridge_node.py running?"
                )
            if self._absorb(int(min(remaining, 0.25) * 1000)):
                break
        # PUB has a slow-joiner window: the bridge's subscription can reach us
        # just after its first heartbeat. Ticks lost in it would be harmless,
        # but there is no reason to lose them.
        time.sleep(0.2)
        self._control = None  # a heartbeat is not a command
        self._next_tick = time.monotonic()
        logger.info("ROS2 bridge connected on %s", self.control_endpoint)

    def predict(self, observation: Observation) -> Action:
        self.publish_tick(observation)
        # Pace to the simulation clock: a real-time stack needs real time.
        self._next_tick += self.tick_interval
        # The deadline is absolute, so a poll that oversleeps is made up on the
        # next tick and the average rate stays exact.
        if self._next_tick <= time.monotonic():
            self._next_tick = time.monotonic()  # behind: don't try to catch up
            self._absorb(0)
        while (remaining := self._next_tick - time.monotonic()) > 0:
            self._absorb(math.ceil(remaining * 1000))
        return self.get_latest_control(observation.ego_velocity)

    def close(self) -> None:
        """Tell the bridge the run is over and release the sockets."""
        if self._pub is not None:
            try:
                self._pub.send({"type": "end", "seq": self._seq})
            finally:
                self._pub.close()
                self._sub.close()  # type: ignore[union-attr]
                self._pub = self._sub = None

    # ── Bridge API ──────────────────────────────────────────────────

    def publish_tick(self, observation: Observation) -> None:
        assert self._pub is not None, "reset() binds the sockets"
        self._pub.send({"type": "tick", "seq": self._seq, "obs": observation.to_dict()})
        self._seq += 1

    def get_latest_control(self, ego_velocity: float) -> Action:
        """The stack's latest command, or a coast if it has gone quiet."""
        if (
            self._control is None
            or time.monotonic() - self._control_at > self.stale_after
        ):
            self.coasted_ticks += 1
            return Action.zero()
        return control_to_action(self._control, ego_velocity, self.sim)

    def _absorb(self, timeout_ms: int) -> bool:
        """Read everything waiting; keep the newest control. True if anything came."""
        assert self._sub is not None
        messages = self._sub.drain(timeout_ms)
        for msg in messages:
            if msg.get("type") == "control":
                self._control = msg
                self._control_at = time.monotonic()
        return bool(messages)


def main(argv: Optional[list] = None) -> int:
    from arep.cli.run_suite import _repo_root, resolve_scenarios
    from arep.execution.runner import EvaluationRunner

    parser = argparse.ArgumentParser(
        description="Evaluate a ROS2 stack on one scenario"
    )
    parser.add_argument("--scenario-id", required=True, help="e.g. LON-003, or a path")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--tick-endpoint", default=DEFAULT_TICK_ENDPOINT)
    parser.add_argument("--control-endpoint", default=DEFAULT_CONTROL_ENDPOINT)
    parser.add_argument("--stale-after", type=float, default=0.5)
    parser.add_argument("--connect-timeout", type=float, default=30.0)
    args = parser.parse_args(argv)

    try:
        paths = resolve_scenarios(args.scenario_id, _repo_root())
    except FileNotFoundError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    if len(paths) != 1:
        print(
            f"{args.scenario_id!r} matches {len(paths)} scenarios; name one",
            file=sys.stderr,
        )
        return 2

    model = Ros2BridgeModel(
        args.tick_endpoint,
        args.control_endpoint,
        args.stale_after,
        args.connect_timeout,
    )
    try:
        result = EvaluationRunner().run_single(str(paths[0]), model, args.seed)
    except ConnectionError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    finally:
        model.close()

    report = result.to_dict()
    report["seed"] = args.seed
    report["coasted_ticks"] = model.coasted_ticks
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
