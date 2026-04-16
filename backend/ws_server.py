"""WebSocket server → pushes state to UI"""
from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Awaitable, Callable
from typing import Any

import websockets
from websockets.exceptions import ConnectionClosed

logger = logging.getLogger(__name__)


class WsHub:
    def __init__(
        self,
        on_pause: Callable[[], Awaitable[None] | None],
        on_resume: Callable[[], Awaitable[None] | None],
        on_emergency_stop: Callable[[], Awaitable[None] | None],
        on_close_pair: Callable[[str], Awaitable[None] | None],
        on_close_breakout: Callable[[str], Awaitable[None] | None] | None = None,
        on_close_ema_scalp: Callable[[str], Awaitable[None] | None] | None = None,
        on_ema_trade_day: Callable[[str, Any], Awaitable[None]] | None = None,
    ) -> None:
        self._clients: set[Any] = set()
        self._on_pause = on_pause
        self._on_resume = on_resume
        self._on_emergency_stop = on_emergency_stop
        self._on_close_pair = on_close_pair
        self._on_close_breakout = on_close_breakout
        self._on_close_ema_scalp = on_close_ema_scalp
        self._on_ema_trade_day = on_ema_trade_day
        self._lock = asyncio.Lock()

    async def register(self, ws: Any) -> None:
        async with self._lock:
            self._clients.add(ws)

    async def unregister(self, ws: Any) -> None:
        async with self._lock:
            self._clients.discard(ws)

    async def broadcast_json(self, payload: dict[str, Any]) -> None:
        raw = json.dumps(payload, default=str)
        async with self._lock:
            if not self._clients:
                return
            dead: list[Any] = []
            for ws in self._clients.copy():
                try:
                    await ws.send(raw)
                except (ConnectionClosed, OSError):
                    dead.append(ws)
                except Exception as e:
                    logger.error("[WS] broadcast error: %s", e)
                    dead.append(ws)
            for ws in dead:
                self._clients.discard(ws)

    async def handle_message(self, raw: str, ws: Any) -> None:
        try:
            msg = json.loads(raw)
        except json.JSONDecodeError:
            return
        action = msg.get("action")
        if action == "pause":
            await self._maybe_await(self._on_pause())
        elif action == "resume":
            await self._maybe_await(self._on_resume())
        elif action == "emergency_stop":
            await self._maybe_await(self._on_emergency_stop())
        elif action == "close_pair":
            pid = msg.get("pair_id") or ""
            await self._maybe_await(self._on_close_pair(pid))
        elif action == "close_breakout":
            sym = str(msg.get("symbol") or "")
            if sym and self._on_close_breakout:
                await self._maybe_await(self._on_close_breakout(sym))
        elif action == "close_ema_scalp":
            sym = str(msg.get("symbol") or "")
            if sym and self._on_close_ema_scalp:
                await self._maybe_await(self._on_close_ema_scalp(sym))
        elif action == "ema_trade_day":
            if self._on_ema_trade_day:
                ds = str(msg.get("date") or "").strip()
                await self._on_ema_trade_day(ds, ws)

    @staticmethod
    async def _maybe_await(x: Any) -> None:
        if asyncio.iscoroutine(x):
            await x


async def run_ws_server(
    port: int,
    hub: WsHub,
    shutdown_event: asyncio.Event,
) -> None:
    async def handler(ws: Any) -> None:
        await hub.register(ws)
        try:
            try:
                async for message in ws:
                    if isinstance(message, bytes):
                        message = message.decode("utf-8")
                    await hub.handle_message(message, ws)
            except ConnectionClosed:
                pass  # обрыв без close frame / reconnect — не ошибка
            except OSError:
                pass  # broken pipe / reset
            except Exception as e:
                logger.error("[WS] handler error: %s", e)
        finally:
            await hub.unregister(ws)

    async with websockets.serve(handler, "0.0.0.0", port):
        # SIGTERM выставляет event → быстрый выход из serve (не asyncio.Future()).
        await shutdown_event.wait()
