"""Single-leg breakout positions (OPEN / PENDING)."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass
class BreakoutPosition:
    symbol: str
    side: str
    entry_price: float
    current_price: float
    size_usdt: float
    qty: float
    tp_price: float
    sl_price: float
    open_time: str
    status: str
    pending_deadline_ts: float | None = None
    pending_order_id: str | None = None
    placed_bar_ts: int | None = None
    close_reason: str | None = None


class BreakoutPositionTracker:
    def __init__(self) -> None:
        self._pos: dict[str, BreakoutPosition] = {}

    def open_pending(
        self,
        symbol: str,
        side: str,
        entry_limit: float,
        tp: float,
        sl: float,
        size_usdt: float,
        qty: float,
        deadline_ts: float,
        order_id: str | None,
        placed_bar_ts: int | None = None,
    ) -> None:
        now = datetime.now(timezone.utc).isoformat()
        self._pos[symbol] = BreakoutPosition(
            symbol=symbol,
            side=side,
            entry_price=entry_limit,
            current_price=entry_limit,
            size_usdt=size_usdt,
            qty=qty,
            tp_price=tp,
            sl_price=sl,
            open_time=now,
            status="PENDING",
            pending_deadline_ts=deadline_ts,
            pending_order_id=order_id,
            placed_bar_ts=placed_bar_ts,
        )

    def confirm_open(self, symbol: str, fill_price: float, qty: float) -> None:
        p = self._pos.get(symbol)
        if not p:
            return
        p.status = "OPEN"
        p.entry_price = fill_price
        p.current_price = fill_price
        p.qty = qty
        p.pending_deadline_ts = None
        p.pending_order_id = None
        p.placed_bar_ts = None

    def restore_open(
        self,
        symbol: str,
        side: str,
        entry_price: float,
        qty: float,
        size_usdt: float,
        tp_price: float,
        sl_price: float,
    ) -> None:
        now = datetime.now(timezone.utc).isoformat()
        self._pos[symbol] = BreakoutPosition(
            symbol=symbol,
            side=side,
            entry_price=entry_price,
            current_price=entry_price,
            size_usdt=size_usdt,
            qty=qty,
            tp_price=tp_price,
            sl_price=sl_price,
            open_time=now,
            status="OPEN",
        )

    def update_price(self, symbol: str, price: float) -> None:
        p = self._pos.get(symbol)
        if p and p.status == "OPEN":
            p.current_price = price

    def close_position(self, symbol: str, close_price: float, reason: str) -> dict[str, Any]:
        p = self._pos.pop(symbol, None)
        if not p:
            return {}
        side = p.side
        if side == "LONG":
            gross = (close_price - p.entry_price) * p.qty
        else:
            gross = (p.entry_price - close_price) * p.qty
        rec = {
            "symbol": symbol,
            "side": side,
            "entry_price": p.entry_price,
            "exit_price": close_price,
            "pnl_usdt": gross,
            "close_reason": reason,
            "open_time": p.open_time,
            "tp_price": p.tp_price,
            "sl_price": p.sl_price,
            "size_usdt": p.size_usdt,
            "qty": p.qty,
        }
        return rec

    def get_position(self, symbol: str) -> BreakoutPosition | None:
        return self._pos.get(symbol)

    def has_open_position(self, symbol: str) -> bool:
        p = self._pos.get(symbol)
        return p is not None and p.status == "OPEN"

    def has_pending(self, symbol: str) -> bool:
        p = self._pos.get(symbol)
        return p is not None and p.status == "PENDING"

    def remove(self, symbol: str) -> None:
        self._pos.pop(symbol, None)

    def get_all_positions(self) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for sym, p in self._pos.items():
            ur = 0.0
            ur_pct = 0.0
            if p.status == "OPEN" and p.entry_price > 0:
                if p.side == "LONG":
                    ur = (p.current_price - p.entry_price) * p.qty
                    ur_pct = (p.current_price - p.entry_price) / p.entry_price * 100.0
                else:
                    ur = (p.entry_price - p.current_price) * p.qty
                    ur_pct = (p.entry_price - p.current_price) / p.entry_price * 100.0
            try:
                et = datetime.fromisoformat(p.open_time.replace("Z", "+00:00"))
                if et.tzinfo is None:
                    et = et.replace(tzinfo=timezone.utc)
                mins = (datetime.now(timezone.utc) - et).total_seconds() / 60.0
            except Exception:
                mins = 0.0
            out.append(
                {
                    "symbol": sym,
                    "side": p.side,
                    "entry_price": p.entry_price,
                    "current_price": p.current_price,
                    "tp_price": p.tp_price,
                    "sl_price": p.sl_price,
                    "unrealized_pnl": ur,
                    "unrealized_pnl_pct": ur_pct,
                    "open_minutes": int(mins),
                    "status": p.status,
                }
            )
        return out

    def get_total_unrealized_pnl(self) -> float:
        t = 0.0
        for p in self._pos.values():
            if p.status != "OPEN" or p.entry_price <= 0:
                continue
            if p.side == "LONG":
                t += (p.current_price - p.entry_price) * p.qty
            else:
                t += (p.entry_price - p.current_price) * p.qty
        return t

    def open_count(self) -> int:
        return sum(1 for p in self._pos.values() if p.status == "OPEN")

    def symbols(self) -> list[str]:
        return list(self._pos.keys())
