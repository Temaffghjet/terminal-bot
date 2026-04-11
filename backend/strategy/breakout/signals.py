"""Breakout: translate detector output into actions."""
from __future__ import annotations

import time
from typing import Any

from backend.strategy.breakout.position import BreakoutPositionTracker


class BreakoutSignalEngine:
    def __init__(self, config: dict, tracker: BreakoutPositionTracker) -> None:
        self.cfg = config.get("breakout") or {}
        rk = self.cfg.get("risk") or {}
        ex = self.cfg.get("exit") or {}
        self.vol_mult = float(self.cfg.get("volume_multiplier", 1.2))
        self.max_open = int(rk.get("max_open_positions", 2))
        self.tp_pct = float(ex.get("take_profit_pct", 4.0)) / 100.0
        self.sl_pct = float(ex.get("stop_loss_pct", 2.0)) / 100.0
        self._tracker = tracker
        self._deposit = float(rk.get("balance_usdt", 1000) or 1000)
        self._pos_pct = float(rk.get("position_size_pct", 15)) / 100.0

    def get_signal(
        self,
        detection: dict[str, Any],
        symbol: str,
        current_price: float,
        risk_ok: bool,
        current_bar_ts_ms: int | None = None,
        tf_ms: int | None = None,
    ) -> dict[str, Any]:
        sig = str(detection.get("signal", "NONE"))
        vol_ratio = float(detection.get("volume_ratio", 0))
        level = float(detection.get("breakout_level", 0))

        pos = self._tracker.get_position(symbol)
        if pos and pos.status == "OPEN":
            if pos.side == "LONG":
                if current_price >= pos.tp_price:
                    return {
                        "action": "CLOSE_TP",
                        "symbol": symbol,
                        "entry_price": pos.entry_price,
                        "tp_price": pos.tp_price,
                        "sl_price": pos.sl_price,
                        "position_size_usdt": pos.size_usdt,
                        "reason": "take profit",
                    }
                if current_price <= pos.sl_price:
                    return {
                        "action": "CLOSE_SL",
                        "symbol": symbol,
                        "entry_price": pos.entry_price,
                        "tp_price": pos.tp_price,
                        "sl_price": pos.sl_price,
                        "position_size_usdt": pos.size_usdt,
                        "reason": "stop loss",
                    }
            else:
                if current_price <= pos.tp_price:
                    return {
                        "action": "CLOSE_TP",
                        "symbol": symbol,
                        "entry_price": pos.entry_price,
                        "tp_price": pos.tp_price,
                        "sl_price": pos.sl_price,
                        "position_size_usdt": pos.size_usdt,
                        "reason": "take profit",
                    }
                if current_price >= pos.sl_price:
                    return {
                        "action": "CLOSE_SL",
                        "symbol": symbol,
                        "entry_price": pos.entry_price,
                        "tp_price": pos.tp_price,
                        "sl_price": pos.sl_price,
                        "position_size_usdt": pos.size_usdt,
                        "reason": "stop loss",
                    }
            return {
                "action": "HOLD",
                "symbol": symbol,
                "entry_price": 0.0,
                "tp_price": 0.0,
                "sl_price": 0.0,
                "position_size_usdt": 0.0,
                "reason": "in position",
            }

        if pos and pos.status == "PENDING":
            if (
                pos.placed_bar_ts is not None
                and current_bar_ts_ms is not None
                and tf_ms is not None
                and tf_ms > 0
                and current_bar_ts_ms - pos.placed_bar_ts >= 2 * tf_ms
            ):
                return {
                    "action": "CANCEL_PENDING",
                    "symbol": symbol,
                    "entry_price": pos.entry_price,
                    "tp_price": pos.tp_price,
                    "sl_price": pos.sl_price,
                    "position_size_usdt": pos.size_usdt,
                    "reason": "limit timeout (2 bars)",
                }
            dl = pos.pending_deadline_ts
            if dl is not None and time.time() > dl:
                return {
                    "action": "CANCEL_PENDING",
                    "symbol": symbol,
                    "entry_price": pos.entry_price,
                    "tp_price": pos.tp_price,
                    "sl_price": pos.sl_price,
                    "position_size_usdt": pos.size_usdt,
                    "reason": "limit timeout",
                }
            return {
                "action": "HOLD",
                "symbol": symbol,
                "entry_price": pos.entry_price,
                "tp_price": pos.tp_price,
                "sl_price": pos.sl_price,
                "position_size_usdt": pos.size_usdt,
                "reason": "pending fill",
            }

        if sig == "NONE" or vol_ratio < self.vol_mult:
            return {
                "action": "HOLD",
                "symbol": symbol,
                "entry_price": 0.0,
                "tp_price": 0.0,
                "sl_price": 0.0,
                "position_size_usdt": 0.0,
                "reason": detection.get("reason", "no setup"),
            }

        if self._tracker.has_open_position(symbol) or self._tracker.has_pending(symbol):
            return {
                "action": "HOLD",
                "symbol": symbol,
                "entry_price": 0.0,
                "tp_price": 0.0,
                "sl_price": 0.0,
                "position_size_usdt": 0.0,
                "reason": "already open/pending",
            }
        if self._tracker.open_count() >= self.max_open:
            return {
                "action": "HOLD",
                "symbol": symbol,
                "entry_price": 0.0,
                "tp_price": 0.0,
                "sl_price": 0.0,
                "position_size_usdt": 0.0,
                "reason": "max_open_positions",
            }
        if not risk_ok:
            return {
                "action": "HOLD",
                "symbol": symbol,
                "entry_price": 0.0,
                "tp_price": 0.0,
                "sl_price": 0.0,
                "position_size_usdt": 0.0,
                "reason": "risk blocked",
            }

        size_usdt = self._deposit * self._pos_pct
        if sig == "LONG":
            entry = level * (1.0 + 0.0005)
            tp = entry * (1.0 + self.tp_pct)
            sl = entry * (1.0 - self.sl_pct)
            return {
                "action": "OPEN_LONG",
                "symbol": symbol,
                "entry_price": entry,
                "tp_price": tp,
                "sl_price": sl,
                "position_size_usdt": size_usdt,
                "reason": detection.get("reason", "long breakout"),
            }
        if sig == "SHORT":
            entry = level * (1.0 - 0.0005)
            tp = entry * (1.0 - self.tp_pct)
            sl = entry * (1.0 + self.sl_pct)
            return {
                "action": "OPEN_SHORT",
                "symbol": symbol,
                "entry_price": entry,
                "tp_price": tp,
                "sl_price": sl,
                "position_size_usdt": size_usdt,
                "reason": detection.get("reason", "short breakout"),
            }
        return {
            "action": "HOLD",
            "symbol": symbol,
            "entry_price": 0.0,
            "tp_price": 0.0,
            "sl_price": 0.0,
            "position_size_usdt": 0.0,
            "reason": "none",
        }
