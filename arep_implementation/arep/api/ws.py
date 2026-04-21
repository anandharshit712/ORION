"""
ORION WebSocket streaming endpoint (P1.1).

Serves ``WS /ws/simulation/{run_id}`` — a live stream of per-tick JSON
frames produced by the SimulationEngine. Auth is a JWT passed as the
``?token=<jwt>`` query parameter (matching the roadmap schema; browsers
cannot set Authorization headers on WebSocket handshakes).

Each client gets its own bounded ``asyncio.Queue``; slow consumers drop
old frames rather than backpressuring the simulation loop.
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect, status
from jose import JWTError, jwt

from arep.api.auth import ALGORITHM, SECRET_KEY
from arep.api.sim_registry import get_registry
from arep.utils.logging_config import get_logger

logger = get_logger("api.ws")

ws_router = APIRouter()


def _verify_token(token: str) -> Optional[int]:
    """Decode a JWT access token; return user id on success, else None."""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        return None
    sub = payload.get("sub")
    if sub is None:
        return None
    try:
        return int(str(sub))
    except ValueError:
        return None


@ws_router.websocket("/ws/simulation/{run_id}")
async def simulation_ws(
    websocket: WebSocket,
    run_id: str,
    token: str = Query(..., description="JWT access token"),
) -> None:
    user_id = _verify_token(token)
    if user_id is None:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        logger.warning("WS auth rejected for run_id=%s", run_id)
        return

    registry = get_registry()
    run = await registry.get(run_id)
    if run is None:
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
                })
                break
            await websocket.send_json(frame)
    except WebSocketDisconnect:
        logger.info("WS disconnected: run_id=%s user_id=%s", run_id, user_id)
    except Exception:
        logger.exception("WS error for run_id=%s", run_id)
    finally:
        run.unsubscribe(queue)
