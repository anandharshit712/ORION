"""
ORION WebSocket streaming endpoint (P1.1).

Serves ``WS /ws/simulation/{run_id}`` — a live stream of per-tick JSON
frames produced by the SimulationEngine.

Auth is a single-use ticket from ``POST /api/runs/{run_id}/ws-ticket``, passed
as ``?ticket=...`` (Phase 0.4, D-04). A browser cannot set an Authorization
header on a WebSocket handshake, so the credential must travel in the URL —
and URLs end up in access logs, proxy logs and browser history. This used to be
the session JWT, which meant one log export handed over a credential good until
expiry. A ticket is worth sixty seconds and one connection.

Auth failures close with 4401 (application range) rather than 1008, so a client
can tell "your ticket was no good, go get another" apart from a policy close.

Each client gets its own bounded ``asyncio.Queue``; slow consumers drop
old frames rather than backpressuring the simulation loop.
"""

from __future__ import annotations

import time

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect, status

from arep.api.sim_registry import get_registry
from arep.api.ws_tickets import redeem_ticket
from arep.utils.logging_config import get_logger

logger = get_logger("api.ws")

ws_router = APIRouter()

# Application close code for "your credential was not accepted". 1008 is the
# generic policy violation and gives a client nothing to act on; 4401 mirrors
# HTTP 401 so the frontend knows to fetch a fresh ticket rather than retry.
WS_AUTH_FAILED = 4401


@ws_router.websocket("/ws/simulation/{run_id}")
async def simulation_ws(
    websocket: WebSocket,
    run_id: str,
    ticket: str = Query(..., description="Single-use ticket from POST /api/runs/{run_id}/ws-ticket"),
) -> None:
    # Redeeming consumes the ticket, so a replay of the same URL fails here even
    # if it is still inside its sixty seconds.
    redeemed = redeem_ticket(ticket, run_id)
    if redeemed is None:
        await websocket.close(code=WS_AUTH_FAILED, reason="invalid or expired ticket")
        logger.warning("WS ticket rejected for run_id=%s", run_id)
        return
    user_id, org_id = redeemed

    registry = get_registry()
    run = await registry.get(run_id)
    if run is None or (run.org_id is not None and run.org_id != org_id):
        await websocket.close(
            code=status.WS_1008_POLICY_VIOLATION,
            reason="run not found",
        )
        return

    await websocket.accept()
    queue = run.subscribe()
    logger.info(
        "WS attached: run_id=%s user_id=%s subscribers=%d",
        run_id, user_id, len(run.subscribers),
    )

    try:
        while True:
            frame = await queue.get()
            if frame is None:  # end-of-stream sentinel
                await websocket.send_json({
                    "event": "stream_end",
                    "status": run.status,
                    "error": run.error,
                    # Published once the run is over, so a client can check the
                    # determinism digest of what it just watched (D-06).
                    "frame_hash": run.frame_hash,
                })
                break
            # emit_ts_ms is stamped here, not in get_tick_frame (D-06). It is a
            # transport concern for the client's latency HUD; inside the frame
            # it broke the no-wall-clock rule and made every run's hash unique.
            # A copy, because subscribers share the published dict and the
            # canonical frame has already been hashed.
            await websocket.send_json({
                **frame,
                "emit_ts_ms": round(time.time() * 1000.0, 2),
            })
    except WebSocketDisconnect:
        logger.info("WS disconnected: run_id=%s user_id=%s", run_id, user_id)
    except Exception:
        logger.exception("WS error for run_id=%s", run_id)
    finally:
        run.unsubscribe(queue)
