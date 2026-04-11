"""Position object for EMA 5m scalper."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class EMAScalpPosition:
    symbol: str
    side: str
    entry_price: float
    size_usdt: float
    qty: float
    leverage: int
    tp_price: float
    sl_price: float
    max_hold_candles: int
    entry_ts_ms: int
    tf_ms: int
    ema_at_entry: float = 0.0
    volume_ratio_at_entry: float = 0.0
    above_ema_count_at_entry: int = 0
    timestamp_open_iso: str = ""
    candles_held: int = 0
    current_price: float = 0.0
    status: str = "OPEN"
    close_reason: str | None = None
    exit_price: float | None = None

    def __post_init__(self) -> None:
        if self.current_price <= 0:
            self.current_price = self.entry_price

    def bars_held(self, current_bar_ts_ms: int) -> int:
        if self.tf_ms <= 0:
            return max(1, self.candles_held)
        return max(1, int((current_bar_ts_ms - self.entry_ts_ms) // self.tf_ms) + 1)

    @property
    def notional(self) -> float:
        return self.size_usdt * self.leverage

    def position_qty(self) -> float:
        return self.qty if self.qty > 0 else self.notional / max(self.entry_price, 1e-12)

    def pnl_pct(self) -> float:
        if self.side == "LONG":
            return (self.current_price - self.entry_price) / self.entry_price * 100.0
        return (self.entry_price - self.current_price) / self.entry_price * 100.0

    def update(self, price: float) -> None:
        self.current_price = price

    def to_dict(self, current_bar_ts_ms: int | None = None) -> dict:
        tp_dist = abs(self.tp_price - self.entry_price)
        prog = 0.0
        if tp_dist > 1e-12:
            if self.side == "LONG":
                prog = max(0.0, min(100.0, (self.current_price - self.entry_price) / tp_dist * 100.0))
            else:
                prog = max(0.0, min(100.0, (self.entry_price - self.current_price) / tp_dist * 100.0))
        bars = self.bars_held(current_bar_ts_ms) if current_bar_ts_ms is not None else self.candles_held
        sign = 1.0 if self.side == "LONG" else -1.0
        gross_usdt = sign * (self.current_price - self.entry_price) * self.position_qty()
        fee_est = self.notional * 0.0001 * 2.0
        return {
            "symbol": self.symbol,
            "side": self.side,
            "entry_price": self.entry_price,
            "current_price": self.current_price,
            "tp_price": self.tp_price,
            "sl_price": self.sl_price,
            "pnl_pct": round(self.pnl_pct(), 3),
            "pnl_usdt": round(gross_usdt - fee_est, 4),
            "candles_held": bars,
            "max_hold_candles": self.max_hold_candles,
            "entry_ts_ms": self.entry_ts_ms,
            "leverage": self.leverage,
            "progress_to_tp": round(prog, 1),
            "status": self.status,
        }
