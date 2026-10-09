"""
ORION side of the ROS2 bridge (Phase 4.1), against a fake bridge.

The fake speaks the same ZeroMQ protocol as `ros2_bridge_node.py` without
needing ROS2, so the contract the node depends on -- handshake, one tick per
step, latest-control-wins, coast on silence -- is checked on every platform.
The node itself is exercised in a real ROS2 Humble environment by
`tests/test_ros2_integration.py`.
"""

from __future__ import annotations

import socket
import threading
import time
from pathlib import Path

import pytest

zmq = pytest.importorskip("zmq")

from arep.bridges.ros2_bridge import Ros2BridgeModel, control_to_action  # noqa: E402
from arep.config import SimulationConfig  # noqa: E402
from arep.execution.runner import EvaluationRunner  # noqa: E402

EMPTY_ROAD = str(
    Path(__file__).parent.parent / "scenarios/basic/straight_road_empty.yaml"
)
SIM = SimulationConfig()


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class FakeBridge(threading.Thread):
    """Heartbeats, records every tick, and optionally sends a fixed command."""

    def __init__(self, tick_ep, control_ep, command=None, heartbeat=True):
        super().__init__(daemon=True)
        self.tick_ep, self.control_ep = tick_ep, control_ep
        self.command, self.heartbeat = command, heartbeat
        self.ticks: list = []
        self.ended = threading.Event()
        self.stop = threading.Event()

    def run(self):
        ctx = zmq.Context.instance()
        push = ctx.socket(zmq.PUSH)
        push.setsockopt(zmq.LINGER, 0)
        push.connect(self.control_ep)
        sub = ctx.socket(zmq.SUB)
        sub.setsockopt(zmq.LINGER, 0)
        sub.setsockopt(zmq.SUBSCRIBE, b"")
        sub.connect(self.tick_ep)
        last_beat = 0.0
        while not self.stop.is_set():
            now = time.monotonic()
            if self.heartbeat and now - last_beat > 0.05:
                push.send_json({"type": "hello"})
                last_beat = now
            if self.command is not None:
                push.send_json({"type": "control", **self.command})
            if sub.poll(2):
                msg = sub.recv_json()
                if msg["type"] == "tick":
                    self.ticks.append(msg)
                elif msg["type"] == "end":
                    self.ended.set()
        push.close()
        sub.close()


def _run(command=None, heartbeat=True, connect_timeout=5.0):
    tick_ep = f"tcp://127.0.0.1:{_free_port()}"
    control_ep = f"tcp://127.0.0.1:{_free_port()}"
    bridge = FakeBridge(tick_ep, control_ep, command, heartbeat)
    bridge.start()
    model = Ros2BridgeModel(
        tick_ep, control_ep, connect_timeout=connect_timeout, tick_interval=0.0
    )
    try:
        result = EvaluationRunner().run_single(EMPTY_ROAD, model, master_seed=42)
        bridge.ended.wait(2.0)
        return result, model, bridge
    finally:
        model.close()
        bridge.stop.set()
        bridge.join(2.0)


# ── control mapping ─────────────────────────────────────────────────


def test_steering_angle_maps_to_normalised_steering_with_the_same_sign():
    # ROS steering is positive counter-clockwise; so is ORION's heading.
    a = control_to_action({"steering_angle": 0.25}, 0.0, SIM)
    assert a.steering == pytest.approx(0.25 / SIM.max_steering_angle)
    assert control_to_action({"steering_angle": -9.0}, 0.0, SIM).steering == -1.0


def test_speed_below_target_throttles_above_target_brakes():
    up = control_to_action({"speed": 10.0}, 9.0, SIM)
    assert up.throttle == pytest.approx(1.0 / SIM.max_acceleration) and up.brake == 0.0
    down = control_to_action({"speed": 0.0}, 4.0, SIM)
    assert (
        down.brake == pytest.approx(4.0 / SIM.max_deceleration) and down.throttle == 0.0
    )


def test_acceleration_caps_the_response_and_zero_means_the_vehicle_limit():
    capped = control_to_action({"speed": 30.0, "acceleration": 1.5}, 0.0, SIM)
    assert capped.throttle == pytest.approx(1.5 / SIM.max_acceleration)
    assert control_to_action({"speed": 30.0}, 0.0, SIM).throttle == 1.0


def test_negative_speed_is_a_stop_not_reverse():
    a = control_to_action({"speed": -5.0}, 3.0, SIM)
    assert a.throttle == 0.0 and a.brake > 0.0


# ── the run, end to end through EvaluationRunner ────────────────────


def test_a_constant_command_drives_the_ego_and_every_tick_is_published():
    result, model, bridge = _run(command={"speed": 8.0, "steering_angle": 0.0})
    speeds = [t["obs"]["ego"]["velocity"] for t in bridge.ticks]
    assert len(bridge.ticks) > 100
    assert max(speeds) > 6.0  # it got going towards 8 m/s
    seqs = [t["seq"] for t in bridge.ticks]
    assert seqs == sorted(seqs)  # in order (a full-speed test run may drop some)
    assert bridge.ended.is_set()  # the bridge is told the run is over
    assert 0.0 <= result.composite_score <= 1.0  # scored like any model
    assert model.coasted_ticks < 5  # only before the first command lands


def test_positive_steering_angle_turns_counter_clockwise():
    _, _, bridge = _run(command={"speed": 5.0, "steering_angle": 0.05})
    headings = [t["obs"]["ego"]["heading"] for t in bridge.ticks]
    assert headings[-1] > headings[0]


def test_a_silent_stack_coasts_rather_than_crashing():
    # Connected (heartbeats) but never commands: every tick is a coast.
    result, model, bridge = _run(command=None)
    speeds = [t["obs"]["ego"]["velocity"] for t in bridge.ticks]
    assert model.coasted_ticks == len(bridge.ticks)
    assert all(b <= a + 1e-9 for a, b in zip(speeds, speeds[1:]))  # never speeds up
    assert result.termination_reason != "model_error"


def test_ticks_are_paced_to_the_simulation_clock():
    # 50 ticks at the real 20 ms timestep is one second of wall clock.
    tick_ep = f"tcp://127.0.0.1:{_free_port()}"
    control_ep = f"tcp://127.0.0.1:{_free_port()}"
    bridge = FakeBridge(tick_ep, control_ep)
    bridge.start()
    model = Ros2BridgeModel(tick_ep, control_ep, connect_timeout=5.0)
    try:
        model.reset()
        from arep.core.observation import Observation

        t0 = time.monotonic()
        for _ in range(50):
            model.predict(Observation())
        elapsed = time.monotonic() - t0
    finally:
        model.close()
        bridge.stop.set()
        bridge.join(2.0)
    assert elapsed == pytest.approx(1.0, abs=0.1)


def test_no_bridge_is_a_clear_error_not_a_hang():
    t0 = time.monotonic()
    with pytest.raises(ConnectionError, match="ros2_bridge_node"):
        _run(heartbeat=False, connect_timeout=0.5)
    assert time.monotonic() - t0 < 5.0


def test_cli_refuses_an_ambiguous_or_unknown_scenario(capsys):
    from arep.bridges.ros2_bridge import main

    assert main(["--scenario-id", "NOPE-999"]) == 2
    assert main(["--scenario-id", "LON"]) == 2  # a category, not one scenario
