"""
Standalone smoke test for the P1.1 WebSocket streaming endpoint.

Starts uvicorn in-process, hits POST /api/runs/ to launch a live run,
then opens a WebSocket to /ws/simulation/{run_id}?token=... and prints
the first ~20 frames. Intended for manual validation end-to-end; it
does not need a frontend.

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
        # Mint a JWT directly (WS endpoint validates the token, does not
        # require a real DB user).
        from arep.api.auth import create_access_token
        token = create_access_token({"sub": "1", "email": "smoke@local"})

        async with httpx.AsyncClient(base_url=f"http://{HOST}:{PORT}") as http:
            resp = await http.post("/api/runs/", json={
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

        ws_url = f"ws://{HOST}:{PORT}/ws/simulation/{run_id}?token={token}"
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
