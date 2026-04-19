"""Позиция скальпа с трейлинг-стопом."""
from __future__ import annotations

from typing import Any


class ScalpPosition:
    def __init__(
        self,
        symbol: str,
        side: str,
        entry_price: float,
        size_usdt: float,
        leverage: int,
        tp_pct: float,
        sl_pct: float,
        max_hold_candles: int,
        trailing_enabled: bool,
        trailing_activation_pct: float,
        trailing_distance_pct: float,
        entry_ts: float,
        indicators_snapshot: dict[str, Any],
    ):
        self.symbol = symbol
        self.side = side
        self.entry_price = entry_price
        self.current_price = entry_price
        self.size_usdt = size_usdt
        self.leverage = leverage
        self.notional = size_usdt * leverage

        if side == "LONG":
            self.tp_price = entry_price * (1 + tp_pct)
            self.sl_price = entry_price * (1 - sl_pct)
        else:
            self.tp_price = entry_price * (1 - tp_pct)
            self.sl_price = entry_price * (1 + sl_pct)

        self.initial_sl = self.sl_price

        self.trailing_enabled = trailing_enabled
        self.trailing_activation_pct = trailing_activation_pct
        self.trailing_distance_pct = trailing_distance_pct
        self.trailing_active = False

        self.max_hold_candles = max_hold_candles
        self.candles_held = 0
        self.entry_ts = entry_ts
        self.status = "OPEN"
        self.close_reason: str | None = None
        self.exit_price: float | None = None

        self.ema_at_entry = indicators_snapshot.get("ema_current", 0)
        self.volume_ratio_at_entry = indicators_snapshot.get("volume_ratio", 0)
        self.above_ema_at_entry = indicators_snapshot.get("above_ema_count", 0)
        self.rsi_at_entry = indicators_snapshot.get("rsi", 0)
        self.structure_at_entry = indicators_snapshot.get("structure_15m", "")
        self.trend_1h_at_entry = indicators_snapshot.get("trend_1h", "")

    @property
    def pnl_pct(self) -> float:
        if self.side == "LONG":
            return (self.current_price - self.entry_price) / self.entry_price
        return (self.entry_price - self.current_price) / self.entry_price

    @property
    def pnl_usdt(self) -> float:
        fee = self.notional * 0.0001 * 2
        return self.notional * self.pnl_pct - fee

    @property
    def progress_to_tp(self) -> float:
        if self.side == "LONG":
            total = self.tp_price - self.entry_price
            done = self.current_price - self.entry_price
        else:
            total = self.entry_price - self.tp_price
            done = self.entry_price - self.current_price
        if total <= 0:
            return 0.0
        return max(0.0, min(100.0, done / total * 100))

    def update_trailing_stop(self, current_price: float) -> None:
        if not self.trailing_enabled:
            return

        activation = self.trailing_activation_pct / 100.0
        dist = self.trailing_distance_pct / 100.0

        if self.side == "LONG":
            if (current_price - self.entry_price) / self.entry_price >= activation:
                new_sl = current_price * (1 - dist)
                if new_sl > self.sl_price:
                    self.sl_price = new_sl
                    self.trailing_active = True
        elif self.side == "SHORT":
            if (self.entry_price - current_price) / self.entry_price >= activation:
                new_sl = current_price * (1 + dist)
                if new_sl < self.sl_price:
                    self.sl_price = new_sl
                    self.trailing_active = True

    def update(self, current_price: float, *, new_candle: bool = True) -> None:
        self.current_price = current_price
        if new_candle:
            self.candles_held += 1
        self.update_trailing_stop(current_price)

    def close(self, exit_price: float, reason: str) -> None:
        self.exit_price = exit_price
        self.close_reason = reason
        self.status = "CLOSED"

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "side": self.side,
            "entry_price": self.entry_price,
            "current_price": self.current_price,
            "tp_price": self.tp_price,
            "sl_price": self.sl_price,
            "initial_sl": self.initial_sl,
            "size_usdt": self.size_usdt,
            "notional": self.notional,
            "leverage": self.leverage,
            "pnl_pct": round(self.pnl_pct * 100, 3),
            "pnl_usdt": round(self.pnl_usdt, 4),
            "candles_held": self.candles_held,
            "progress_to_tp": round(self.progress_to_tp, 1),
            "trailing_active": self.trailing_active,
            "entry_ts": self.entry_ts,
            "status": self.status,
            "close_reason": self.close_reason,
            "ema_at_entry": self.ema_at_entry,
            "volume_ratio_at_entry": self.volume_ratio_at_entry,
            "above_ema_at_entry": self.above_ema_at_entry,
            "rsi_at_entry": self.rsi_at_entry,
            "structure_at_entry": self.structure_at_entry,
            "trend_1h_at_entry": self.trend_1h_at_entry,
        }
