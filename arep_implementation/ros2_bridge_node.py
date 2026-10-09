"""
ORION <-> ROS2 bridge node.  [Phase 4.1]

    ORION simulation  <-- ZeroMQ -->  this node (rclpy)  <-- ROS2 topics -->  AV stack

Publishes, once per simulation tick (50 Hz):
    /orion/ego/odom   nav_msgs/Odometry              ego ground truth, frame "map"
    /orion/objects    visualization_msgs/MarkerArray nearby objects, frame "base_link"
Subscribes:
    /orion/cmd        ackermann_msgs/AckermannDriveStamped   the stack's control

Ground truth only: the observation a ROS2 stack gets is the one every ORION model
gets. Sensor topics (LaserScan, NavSatFix, Imu) arrive with Phase 6.

This file imports nothing from `arep`. It is a translator, and it runs in a
ROS2 Python environment that needs only rclpy and pyzmq.

Two ways to run it:

    # Launch mode: start ORION on one scenario and bridge it. Needs `arep`
    # importable (run from arep_implementation/ or pip install it).
    python ros2_bridge_node.py --scenario-id LON-003 --seed 42

    # Translator only, against an ORION process started separately with
    # `python -m arep.bridges.ros2_bridge --scenario-id ...`.
    python ros2_bridge_node.py

Requires a sourced ROS2 Humble environment plus ros-humble-ackermann-msgs.
"""

from __future__ import annotations

import argparse
import math
import subprocess
import sys
import threading

import rclpy
import zmq
from ackermann_msgs.msg import AckermannDriveStamped
from nav_msgs.msg import Odometry
from rclpy.node import Node
from visualization_msgs.msg import Marker, MarkerArray

DEFAULT_TICK_ENDPOINT = "tcp://127.0.0.1:5555"
DEFAULT_CONTROL_ENDPOINT = "tcp://127.0.0.1:5556"


def yaw_to_quaternion(yaw: float):
    """(x, y, z, w) for a rotation of `yaw` radians about z."""
    return 0.0, 0.0, math.sin(yaw / 2.0), math.cos(yaw / 2.0)


class OrionBridge(Node):
    def __init__(self, tick_endpoint: str, control_endpoint: str):
        super().__init__("orion_bridge")
        self.odom_pub = self.create_publisher(Odometry, "/orion/ego/odom", 10)
        self.objects_pub = self.create_publisher(MarkerArray, "/orion/objects", 10)
        self.create_subscription(AckermannDriveStamped, "/orion/cmd", self.on_cmd, 10)

        ctx = zmq.Context.instance()
        self.push = ctx.socket(zmq.PUSH)
        self.push.setsockopt(zmq.LINGER, 0)
        # Queue only to a live peer. Without this, commands sent before ORION
        # binds pile up and arrive later looking fresh.
        self.push.setsockopt(zmq.IMMEDIATE, 1)
        self.push.connect(control_endpoint)

        self.sub = ctx.socket(zmq.SUB)
        self.sub.setsockopt(zmq.LINGER, 0)
        self.sub.setsockopt(zmq.SUBSCRIBE, b"")
        self.sub.connect(tick_endpoint)

        self.ticks = 0
        self.run_ended = threading.Event()
        # ORION waits for this before tick 0, and it is how a restarted
        # bridge is noticed: the heartbeat simply resumes.
        self.create_timer(1.0, self.heartbeat)
        self._reader = threading.Thread(target=self._read_ticks, daemon=True)
        self._reader.start()
        self.get_logger().info(f"bridging {tick_endpoint} / {control_endpoint}")

    def _send(self, message: dict) -> None:
        try:
            self.push.send_json(message, flags=zmq.NOBLOCK)
        except zmq.Again:
            pass  # ORION not up yet; a heartbeat or command is not worth queueing

    def heartbeat(self) -> None:
        self._send({"type": "hello"})

    def on_cmd(self, msg: AckermannDriveStamped) -> None:
        d = msg.drive
        self._send(
            {
                "type": "control",
                "steering_angle": d.steering_angle,
                "speed": d.speed,
                "acceleration": d.acceleration,
            }
        )

    def _read_ticks(self) -> None:
        while rclpy.ok():
            if not self.sub.poll(200):
                continue
            msg = self.sub.recv_json()
            if msg.get("type") == "tick":
                self.ticks += 1
                self.publish_tick(msg["obs"])
            elif msg.get("type") == "end":
                self.get_logger().info(f"ORION run ended after {self.ticks} ticks")
                self.run_ended.set()

    def publish_tick(self, obs: dict) -> None:
        stamp = self.get_clock().now().to_msg()
        ego = obs["ego"]

        odom = Odometry()
        odom.header.stamp = stamp
        odom.header.frame_id = "map"
        odom.child_frame_id = "base_link"
        odom.pose.pose.position.x = float(ego["x"])
        odom.pose.pose.position.y = float(ego["y"])
        q = odom.pose.pose.orientation
        q.x, q.y, q.z, q.w = yaw_to_quaternion(float(ego["heading"]))
        odom.twist.twist.linear.x = float(ego["velocity"])
        odom.twist.twist.angular.z = float(ego["heading_rate"])
        self.odom_pub.publish(odom)

        markers = MarkerArray()
        clear = Marker()
        clear.header.stamp = stamp
        clear.header.frame_id = "base_link"
        clear.action = Marker.DELETEALL  # objects that left range must vanish
        markers.markers.append(clear)
        for i, obj in enumerate(obs.get("objects", [])):
            m = Marker()
            m.header.stamp = stamp
            m.header.frame_id = "base_link"
            m.ns = "orion"
            m.id = i
            m.text = str(obj.get("object_id", ""))
            m.type = Marker.CUBE
            m.action = Marker.ADD
            m.pose.position.x = float(obj["relative_x"])
            m.pose.position.y = float(obj["relative_y"])
            m.pose.position.z = 0.75
            o = m.pose.orientation
            o.x, o.y, o.z, o.w = yaw_to_quaternion(float(obj["heading"]))
            m.scale.x = max(float(obj["length"]), 0.1)
            m.scale.y = max(float(obj["width"]), 0.1)
            m.scale.z = 1.5
            m.color.r, m.color.g, m.color.b, m.color.a = 1.0, 0.6, 0.0, 0.8
            markers.markers.append(m)
        self.objects_pub.publish(markers)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--scenario-id", help="launch ORION on this scenario as well")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--tick-endpoint", default=DEFAULT_TICK_ENDPOINT)
    parser.add_argument("--control-endpoint", default=DEFAULT_CONTROL_ENDPOINT)
    args, ros_args = parser.parse_known_args()

    rclpy.init(args=ros_args)
    node = OrionBridge(args.tick_endpoint, args.control_endpoint)

    orion = None
    if args.scenario_id:
        orion = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "arep.bridges.ros2_bridge",
                "--scenario-id",
                args.scenario_id,
                "--seed",
                str(args.seed),
                "--tick-endpoint",
                args.tick_endpoint,
                "--control-endpoint",
                args.control_endpoint,
            ]
        )

    code = 0
    try:
        while rclpy.ok() and (orion is None or orion.poll() is None):
            rclpy.spin_once(node, timeout_sec=0.1)
    except KeyboardInterrupt:
        pass
    finally:
        if orion is not None:
            if orion.poll() is None:
                orion.terminate()
            code = orion.wait()
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
    return code


if __name__ == "__main__":
    sys.exit(main())
