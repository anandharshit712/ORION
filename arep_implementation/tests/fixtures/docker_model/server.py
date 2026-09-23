"""Minimal ORION model server for the container integration test.

Deliberately stdlib-only. The SDK example under orion-sdk/examples/docker_model
uses FastAPI, which means a pip install on every build; this one builds in
seconds from python:3.11-slim with no network, so the integration test stays
runnable on a laptop and in CI.

Implements the contract ContainerModelRunner speaks:
    POST /predict  Observation JSON -> Action JSON
    POST /reset    {} -> {}
    GET  /health   -> {"status": "ok"}

The behaviour is an emergency braker, so a run against a lead-vehicle scenario
produces a score that is recognisably *not* the default-zero action. A test that
cannot tell "the model ran" from "the model returned nothing" proves nothing.
"""

from __future__ import annotations

import json
import os
from http.server import BaseHTTPRequestHandler, HTTPServer

# Distance at which this model slams the brakes, in metres.
BRAKE_DISTANCE = 30.0
# Anything further off the travel line than this is treated as another lane.
LANE_HALF_WIDTH = 2.0


class Handler(BaseHTTPRequestHandler):
    def _send(self, payload: dict, status: int = 200) -> None:
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802  (BaseHTTPRequestHandler's spelling)
        if self.path == "/health":
            self._send({"status": "ok"})
        else:
            self._send({"detail": "not found"}, status=404)

    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length) if length else b"{}"

        if self.path == "/reset":
            self._send({})
            return

        if self.path != "/predict":
            self._send({"detail": "not found"}, status=404)
            return

        try:
            observation = json.loads(raw or b"{}")
        except json.JSONDecodeError:
            self._send({"detail": "bad observation"}, status=400)
            return

        self._send(self._act(observation))

    def _act(self, observation: dict) -> dict:
        """Brake hard when something is close ahead, otherwise hold speed.

        Reads the fields DetectedObject.to_dict actually ships -- relative_x and
        relative_y, in the ego frame. There is no distance field on the wire.
        """
        nearest = None
        for obj in observation.get("objects", []) or []:
            dx = obj.get("relative_x") or 0.0
            dy = obj.get("relative_y") or 0.0
            if dx <= 0:
                continue  # behind the ego
            if abs(dy) > LANE_HALF_WIDTH:
                continue  # another lane
            nearest = dx if nearest is None else min(nearest, dx)

        if nearest is not None and nearest < BRAKE_DISTANCE:
            return {"steering": 0.0, "throttle": 0.0, "brake": 1.0}
        return {"steering": 0.0, "throttle": 0.2, "brake": 0.0}

    def log_message(self, *args) -> None:
        """Silence per-request logging; the test reads stdout on failure."""
        return


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8080"))
    HTTPServer(("0.0.0.0", port), Handler).serve_forever()
