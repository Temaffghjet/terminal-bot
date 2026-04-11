"""Track pair legs + одиночные micro-scalp позиции"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any


@dataclass
class LegState:
    symbol: str
    side: str
    size: float
    entry_price: float
    current_price: float = 0.0

    def pnl_usdt(self) -> float:
        sign = 1.0 if self.side == "LONG" else -1.0
        return sign * (self.current_price - self.entry_price) * self.size


@dataclass
class PairPosition:
    pair_id: str
    leg_a: LegState
    leg_b: LegState
    open_time: str
    zscore_at_entry: float
    current_zscore: float = 0.0
    direction: str = ""

    def total_pnl_usdt(self) -> float:
        return self.leg_a.pnl_usdt() + self.leg_b.pnl_usdt()


@dataclass
class ScalpPosition:
    """Одна нога micro scalping."""
    symbol: str
    side: str
    size: float
    entry_price: float
    entry_time: str
    take_profit: float
    stop_loss: float
    current_price: float = 0.0
    entry_ts_ms: int = 0

    def pnl_pct(self) -> float:
        if self.side == "LONG":
            return (self.current_price - self.entry_price) / self.entry_price * 100.0
        return (self.entry_price - self.current_price) / self.entry_price * 100.0

    def should_exit(
        self,
        current_price: float,
        ema: float,
        now: datetime,
        tp_pct: float,
        sl_pct: float,
        max_hold_minutes: int,
    ) -> tuple[bool, str]:
        self.current_price = current_price
        pnl = self.pnl_pct()
        if pnl >= tp_pct:
            return True, "TAKE_PROFIT"
        if pnl <= -sl_pct:
            return True, "STOP_LOSS"
        try:
            et = datetime.fromisoformat(self.entry_time.replace("Z", "+00:00"))
            if et.tzinfo is None:
                et = et.replace(tzinfo=timezone.utc)
            mins = (now - et).total_seconds() / 60.0
            if mins >= max_hold_minutes:
                return True, "TIME_EXIT"
        except Exception:
            pass
        if self.side == "LONG" and current_price < ema:
            return True, "EMA_CROSS_EXIT"
        if self.side == "SHORT" and current_price > ema:
            return True, "EMA_CROSS_EXIT"
        return False, ""


class PositionManager:
    def __init__(self) -> None:
        self._positions: dict[str, PairPosition] = {}
        self._scalp: dict[str, ScalpPosition] = {}
        self._total_pnl_today: float = 0.0

    def add_realized_today(self, pnl: float) -> None:
        self._total_pnl_today += pnl

    def set_position(self, pair_id: str, pos: PairPosition) -> None:
        self._positions[pair_id] = pos

    def remove_position(self, pair_id: str) -> None:
        self._positions.pop(pair_id, None)

    def get(self, pair_id: str) -> PairPosition | None:
        return self._positions.get(pair_id)

    def has(self, pair_id: str) -> bool:
        return pair_id in self._positions

    def update_mark(self, pair_id: str, price_a: float, price_b: float, z: float) -> None:
        p = self._positions.get(pair_id)
        if not p:
            return
        p.leg_a.current_price = price_a
        p.leg_b.current_price = price_b
        p.current_zscore = z

    # --- Micro scalping (одна нога) ---
    def scalp_get(self, symbol: str) -> ScalpPosition | None:
        return self._scalp.get(symbol)

    def scalp_set(self, symbol: str, pos: ScalpPosition) -> None:
        self._scalp[symbol] = pos

    def scalp_remove(self, symbol: str) -> None:
        self._scalp.pop(symbol, None)

    def scalp_count(self) -> int:
        return len(self._scalp)

    def scalp_all(self) -> dict[str, ScalpPosition]:
        return dict(self._scalp)

    def scalp_update_price(self, symbol: str, price: float) -> None:
        p = self._scalp.get(symbol)
        if p:
            p.current_price = price

    def get_state(self) -> dict[str, Any]:
        positions: list[dict[str, Any]] = []
        total_unreal = 0.0
        for pid, p in self._positions.items():
            total_unreal += p.total_pnl_usdt()
            positions.append(
                {
                    "pair_id": pid,
                    "leg_a": {
                        "symbol": p.leg_a.symbol,
                        "side": p.leg_a.side,
                        "size": p.leg_a.size,
                        "entry_price": p.leg_a.entry_price,
                        "current_price": p.leg_a.current_price,
                        "pnl_usdt": p.leg_a.pnl_usdt(),
                    },
                    "leg_b": {
                        "symbol": p.leg_b.symbol,
                        "side": p.leg_b.side,
                        "size": p.leg_b.size,
                        "entry_price": p.leg_b.entry_price,
                        "current_price": p.leg_b.current_price,
                        "pnl_usdt": p.leg_b.pnl_usdt(),
                    },
                    "total_pnl_usdt": p.total_pnl_usdt(),
                    "open_time": p.open_time,
                    "zscore_at_entry": p.zscore_at_entry,
                    "current_zscore": p.current_zscore,
                }
            )
        return {
            "positions": positions,
            "total_pnl_today": self._total_pnl_today,
            "total_pnl_unrealized": total_unreal,
        }
