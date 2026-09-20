"""
Standalone smoke test for the P1.1 WebSocket streaming endpoint.

Starts uvicorn in-process, signs up and verifies an account, launches a live
run, mints a single-use WebSocket ticket and streams the first ~20 frames.
Intended for manual validation end-to-end; it does not need a frontend.

The signup/verify dance is not ceremony: POST /api/runs/ requires a verified
account (D-04) and the socket requires a ticket rather than a JWT (D-04), so
this is the shortest path a real client can take.

Usage (from arep_implementation/):
    python scripts/ws_smoke.py
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import sys
import threading
import time
from pathlib import Path

import httpx
import uvicorn
import websockets

# A throwaway database, set before anything imports arep.config.env (which loads
# .env and would otherwise point this at the real dev Postgres). A smoke script
# that signs up users must not write to a database anyone cares about.
import os
import tempfile

_fd, _db = tempfile.mkstemp(suffix=".db")
os.close(_fd)
os.unlink(_db)
os.environ["ORION_DATABASE_URL"] = "sqlite:///" + _db.replace("\\", "/")

HOST = "127.0.0.1"
PORT = 8765
SCENARIO = str(
    Path(__file__).resolve().parent.parent
    / "scenarios" / "basic" / "straight_road_lead_vehicle.yaml"
)


def _start_server() -> uvicorn.Server:
    from arep.api.app import create_app

    config = uvicorn.Config(
        create_app(), host=HOST, port=PORT, log_level="warning",
    )
    server = uvicorn.Server(config)

    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    # Wait for readiness
    deadline = time.monotonic() + 15.0
    while time.monotonic() < deadline:
        try:
            r = httpx.get(f"http://{HOST}:{PORT}/health", timeout=1.0)
            if r.status_code == 200:
                return server
        except Exception:
            time.sleep(0.1)
    raise RuntimeError("uvicorn did not become ready")


async def run_smoke() -> int:
    server = _start_server()
    print(f"[ws_smoke] uvicorn up on http://{HOST}:{PORT}")
    try:
        async with httpx.AsyncClient(base_url=f"http://{HOST}:{PORT}") as http:
            email = f"ws-smoke-{int(time.time())}@example.com"
            resp = await http.post("/api/auth/signup", json={
                "email": email,
                "username": email.split("@")[0],
                "password": "ws-smoke-password",
                "org_name": "WS Smoke Org",
            })
            resp.raise_for_status()

            # Starting a run needs a verified address. Flipping the flag
            # directly is the local stand-in for clicking the emailed link.
            from arep.database.connection import session_scope
            from arep.database.models import UserRecord
            with session_scope() as session:
                user = session.query(UserRecord).filter_by(email=email).first()
                user.email_verified = True

            resp = await http.post("/api/auth/login", json={
                "identifier": email, "password": "ws-smoke-password",
            })
            resp.raise_for_status()
            auth = {"Authorization": f"Bearer {resp.json()['access_token']}"}

            resp = await http.post("/api/runs/", headers=auth, json={
                "scenario_path": SCENARIO,
                "model_name": "EmergencyBrake",
                "master_seed": 42,
                "tick_interval": 0.02,
            })
            resp.raise_for_status()
            body = resp.json()
            print(f"[ws_smoke] run started: {body['run_id']} "
                  f"scenario={body['scenario_name']}")
            run_id = body["run_id"]

            resp = await http.post(f"/api/runs/{run_id}/ws-ticket", headers=auth)
            resp.raise_for_status()
            ticket = resp.json()["ticket"]
            print(f"[ws_smoke] ticket minted (expires in "
                  f"{resp.json()['expires_in']}s)")

        ws_url = f"ws://{HOST}:{PORT}/ws/simulation/{run_id}?ticket={ticket}"
        print(f"[ws_smoke] connecting to {ws_url}")
        async with websockets.connect(ws_url) as ws:
            t0 = time.monotonic()
            received = 0
            while received < 20:
                try:
                    raw = await asyncio.wait_for(ws.recv(), timeout=5.0)
                except asyncio.TimeoutError:
                    print("[ws_smoke] timeout waiting for frame")
                    return 1
                msg = json.loads(raw)
                # D-06: the canonical frame has no wall-clock; the send site
                # stamps emit_ts_ms for the client's latency HUD. If this stops
                # arriving, the HUD silently reports nothing.
                if msg.get("event") != "stream_end" and "emit_ts_ms" not in msg:
                    print("[ws_smoke] FAIL: emit_ts_ms missing from a streamed frame")
                    return 1
                if msg.get("event") == "stream_end":
                    print(f"[ws_smoke] stream_end: {msg}")
                    break
                received += 1
                if received <= 3 or received % 10 == 0:
                    ego = msg.get("ego", {})
                    print(
                        f"  tick={msg.get('tick'):>4} "
                        f"t_ms={msg.get('t_ms'):>7} "
                        f"ego=({ego.get('x'):.2f}, {ego.get('y'):.2f}) "
                        f"v={ego.get('speed'):.2f} "
                        f"verdict={msg['monitor']['verdict_so_far']}"
                    )
            elapsed = time.monotonic() - t0
            print(f"[ws_smoke] received {received} frames in {elapsed:.2f}s "
                  f"(~{received/elapsed:.1f} Hz)")
        return 0
    finally:
        server.should_exit = True


def main() -> int:
    return asyncio.run(run_smoke())


if __name__ == "__main__":
    sys.exit(main())
