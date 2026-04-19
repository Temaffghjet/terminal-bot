"""WebSocket сервер для UI."""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

logger = logging.getLogger(__name__)

CLIENTS: set[Any] = set()
_state_fn: Any = None


def set_state_provider(fn: Any) -> None:
    global _state_fn
    _state_fn = fn


async def broadcast_state() -> None:
    if not CLIENTS or _state_fn is None:
        return
    try:
        payload = _state_fn()
        raw = json.dumps(payload, default=str)
    except Exception:
        logger.exception("broadcast build")
        return

    import websockets.exceptions

    dead: list[Any] = []
    for ws in CLIENTS:
        try:
            await ws.send(raw)
        except (
            websockets.exceptions.ConnectionClosedError,
            websockets.exceptions.ConnectionClosedOK,
        ):
            dead.append(ws)
        except Exception as e:
            logger.warning("ws send: %s", e)
            dead.append(ws)
    for ws in dead:
        CLIENTS.discard(ws)


async def _handler(ws: Any) -> None:
    CLIENTS.add(ws)
    try:
        async for _ in ws:
            pass
    except Exception:
        pass
    finally:
        CLIENTS.discard(ws)


async def run_ws_server(port: int) -> None:
    import websockets

    async with websockets.serve(_handler, "0.0.0.0", port):
        await asyncio.Future()


def start_ws_background(port: int) -> asyncio.Task:
    return asyncio.create_task(run_ws_server(port))
