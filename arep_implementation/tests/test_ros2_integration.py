"""
ROS2 bridge against a real ROS2 Humble graph (Phase 4.1 acceptance criteria).

`tests/test_ros2_bridge.py` checks ORION's half of the protocol with a fake
bridge. This checks the other half -- that `ros2_bridge_node.py` really puts
messages on ROS2 topics and really takes commands off one -- which nothing short
of a ROS2 environment can show. It skips wherever `rclpy` is not importable,
which is every machine without a sourced ROS2 install.

Running it (from the repo root in WSL, Docker Engine installed). The image
carries no tests or fixtures, so mount them:

    docker build -f infrastructure/docker/Dockerfile.ros2 -t orion-ros2 .
    docker run --rm \\
        -v "$PWD/arep_implementation/tests:/orion/arep_implementation/tests:ro" \\
        -v "$PWD/arep_implementation/scenarios:/orion/arep_implementation/scenarios:ro" \\
        --entrypoint /ros_entrypoint.sh orion-ros2 \\
        bash -c "pip install -q pytest && python3 -m pytest tests/test_ros2_integration.py -v"

Every test runs in real time, so this file takes about a minute.
"""

from __future__ import annotations

import json
import math
import os
import signal
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

rclpy = pytest.importorskip("rclpy")

from ackermann_msgs.msg import AckermannDriveStamped  # noqa: E402
from nav_msgs.msg import Odometry  # noqa: E402
from rclpy.executors import SingleThreadedExecutor  # noqa: E402
from visualization_msgs.msg import MarkerArray  # noqa: E402

HERE = Path(__file__).resolve().parent.parent  # arep_implementation/
EMPTY_ROAD = str(HERE / "scenarios/basic/straight_road_empty.yaml")


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module", autouse=True)
def ros():
    rclpy.init()
    yield
    rclpy.shutdown()


class Stack:
    """Stands in for an AV stack: records odom/objects, can publish commands."""

    def __init__(self):
        self.node = rclpy.create_node(f"fake_stack_{os.getpid()}_{time.monotonic_ns()}")
        self.odom: list = []  # (wall time, speed, yaw)
        self.objects: list = []
        self.node.create_subscription(Odometry, "/orion/ego/odom", self._on_odom, 50)
        self.node.create_subscription(
            MarkerArray, "/orion/objects", self.objects.append, 50
        )
        self.cmd = self.node.create_publisher(AckermannDriveStamped, "/orion/cmd", 10)
        self._command = None
        self.node.create_timer(0.05, self._send)  # a 20 Hz stack
        self.executor = SingleThreadedExecutor()
        self.executor.add_node(self.node)
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._spin, daemon=True)
        self._thread.start()

    def _on_odom(self, msg):
        q = msg.pose.pose.orientation
        yaw = 2.0 * math.atan2(q.z, q.w)
        self.odom.append((time.monotonic(), msg.twist.twist.linear.x, yaw))

    def _send(self):
        if self._command is not None:
            msg = AckermannDriveStamped()
            msg.drive.speed, msg.drive.steering_angle = self._command
            self.cmd.publish(msg)

    def _spin(self):
        while not self._stop.is_set():
            self.executor.spin_once(timeout_sec=0.05)

    def command(self, speed, steering_angle=0.0):
        self._command = (float(speed), float(steering_angle))

    def silence(self):
        self._command = None

    def wait_for_odom(self, timeout=40.0):
        deadline = time.monotonic() + timeout
        while not self.odom and time.monotonic() < deadline:
            time.sleep(0.05)
        assert self.odom, "no /orion/ego/odom message arrived"

    def since(self, t0):
        return [o for o in self.odom if o[0] >= t0]

    def close(self):
        self._stop.set()
        self._thread.join(2.0)
        self.executor.shutdown()
        self.node.destroy_node()


def _endpoints():
    return [
        "--tick-endpoint",
        f"tcp://127.0.0.1:{_free_port()}",
        "--control-endpoint",
        f"tcp://127.0.0.1:{_free_port()}",
    ]


def _spawn(*args, **kw):
    return subprocess.Popen([sys.executable, *args], cwd=HERE, text=True, **kw)


def _stop(proc):
    if proc.poll() is None:
        proc.send_signal(signal.SIGINT)
        try:
            proc.wait(10)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()


@pytest.fixture
def stack():
    s = Stack()
    yield s
    s.close()


def test_lon003_starts_and_publishes_odom_at_50hz_with_objects(stack):
    """Criteria 1 and 2: the literal launch command, and the topic rate."""
    node = _spawn(
        "ros2_bridge_node.py", "--scenario-id", "LON-003", "--seed", "42", *_endpoints()
    )
    try:
        stack.wait_for_odom()
        t0 = time.monotonic()
        time.sleep(4.0)
        window = stack.since(t0)
        rate = len(window) / (window[-1][0] - window[0][0])
        assert 45.0 <= rate <= 55.0, f"odom at {rate:.1f} Hz"
        # LON-003's lead vehicle is on /orion/objects as a cube after the clear.
        assert any(len(m.markers) >= 2 for m in stack.objects)
        assert node.poll() is None, "the bridge exited mid-run"
    finally:
        _stop(node)


def test_a_constant_command_drives_the_ego_and_silence_coasts(stack):
    """Criterion 3, plus the stack-side half of criterion 4."""
    node = _spawn(
        "ros2_bridge_node.py",
        "--scenario-id",
        EMPTY_ROAD,
        "--seed",
        "42",
        *_endpoints(),
    )
    try:
        stack.wait_for_odom()
        start_speed = stack.odom[-1][1]  # the scenario starts the ego at 15 m/s

        stack.command(speed=25.0, steering_angle=0.001)  # gentle: stays on the road
        t0 = time.monotonic()
        time.sleep(3.0)
        driven = stack.since(t0)
        assert (
            driven[-1][1] > start_speed + 4.0
        ), "the command did not accelerate the ego"
        assert driven[-1][2] > driven[0][2], "positive steering_angle did not turn left"

        stack.silence()
        time.sleep(0.7)  # past the 0.5 s staleness window
        t1 = time.monotonic()
        time.sleep(1.5)
        coasting = [o[1] for o in stack.since(t1)]
        assert coasting and all(b <= a + 1e-6 for a, b in zip(coasting, coasting[1:]))
        assert node.poll() is None, "a silent stack crashed the run"
    finally:
        _stop(node)


def test_killing_the_bridge_node_coasts_the_run_and_a_new_node_reconnects(stack):
    """Criterion 4: the bridge itself disappears mid-run."""
    ends = _endpoints()
    orion = _spawn(
        "-m",
        "arep.bridges.ros2_bridge",
        "--scenario-id",
        EMPTY_ROAD,
        "--seed",
        "42",
        *ends,
        stdout=subprocess.PIPE,
    )
    node = _spawn("ros2_bridge_node.py", *ends)
    try:
        stack.wait_for_odom()
        stack.command(speed=25.0)
        time.sleep(1.0)

        node.kill()  # no goodbye: the process is simply gone
        node.wait()
        time.sleep(2.0)
        assert orion.poll() is None, "ORION died with the bridge"

        t0 = time.monotonic()
        node = _spawn("ros2_bridge_node.py", *ends)
        time.sleep(3.0)
        assert stack.since(t0), "a restarted bridge did not resume the topics"

        out, _ = orion.communicate(timeout=60)
        assert orion.returncode == 0
        out = "\n" + out  # logs share stdout; the report is the last "{" block
        report = json.loads(out[out.rindex("\n{\n") + 1 :])
        assert report["coasted_ticks"] > 50  # the gap was coasted, not crashed
        assert report["termination_reason"] != "model_error"
    finally:
        _stop(node)
        _stop(orion)
