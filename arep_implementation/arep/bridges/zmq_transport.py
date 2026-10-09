"""
ORION ZeroMQ transport for out-of-process bridges.  [Phase 4.1]

Two sockets, both bound by ORION so the bridge can come and go:

  SimPublisher      PUB   ORION -> bridge   one JSON message per tick
  ControlSubscriber PULL  bridge -> ORION   control messages, read non-blocking

PUB/PULL rather than REQ/REP on purpose. A REQ socket whose peer vanishes
blocks forever, and "the ROS2 stack died" has to end in a coasting car, not a
hung simulation.

Messages are plain JSON dicts with a "type" key. The bridge side needs only
pyzmq, never `arep`, so it can run in a ROS2 Python environment that has
nothing of ORION installed.
"""

from __future__ import annotations

from typing import Any, Dict, List

import zmq

# Defaults for a bridge on the same host. Loopback only: the control socket
# drives the ego vehicle, so it is not something to expose on 0.0.0.0.
DEFAULT_TICK_ENDPOINT = "tcp://127.0.0.1:5555"
DEFAULT_CONTROL_ENDPOINT = "tcp://127.0.0.1:5556"


class SimPublisher:
    """PUB socket ORION publishes each tick on."""

    def __init__(self, endpoint: str = DEFAULT_TICK_ENDPOINT, context=None):
        self._ctx = context or zmq.Context.instance()
        self._sock = self._ctx.socket(zmq.PUB)
        self._sock.setsockopt(zmq.LINGER, 0)
        # A slow bridge must not grow ORION's memory: drop ticks it cannot keep
        # up with rather than queue them. A stale tick is worthless anyway.
        self._sock.setsockopt(zmq.SNDHWM, 10)
        self._sock.bind(endpoint)

    def send(self, message: Dict[str, Any]) -> None:
        self._sock.send_json(message)

    def close(self) -> None:
        # Brief linger so a final "end" message still leaves the socket.
        self._sock.close(linger=500)


class ControlSubscriber:
    """PULL socket ORION reads control messages from."""

    def __init__(self, endpoint: str = DEFAULT_CONTROL_ENDPOINT, context=None):
        self._ctx = context or zmq.Context.instance()
        self._sock = self._ctx.socket(zmq.PULL)
        self._sock.setsockopt(zmq.LINGER, 0)
        self._sock.bind(endpoint)

    def drain(self, timeout_ms: int = 0) -> List[Dict[str, Any]]:
        """Every message waiting, waiting up to `timeout_ms` for the first."""
        messages: List[Dict[str, Any]] = []
        if not self._sock.poll(timeout_ms):
            return messages
        while True:
            try:
                raw = self._sock.recv_json(flags=zmq.NOBLOCK)
            except zmq.Again:
                return messages
            except ValueError:
                continue  # not JSON: a misbehaving peer is skipped, not fatal
            if isinstance(raw, dict):
                messages.append(raw)

    def close(self) -> None:
        self._sock.close()
