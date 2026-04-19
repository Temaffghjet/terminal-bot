"""Логика входа/выхода EMA Scalper v3."""
from __future__ import annotations

import logging
import time
from typing import Any

from backend.strategy.ema_scalper.indicators import get_1h_trend, get_market_structure
from backend.strategy.ema_scalper.position import ScalpPosition

logger = logging.getLogger(__name__)


class EMAScalpSignalEngine:
    def __init__(self, config: dict):
        self.config = config

    def _es(self) -> dict:
        return self.config.get("ema_scalper") or {}

    def check_entry(
        self,
        *,
        indicators: dict[str, Any],
        symbol: str,
        last_entry_ts: float,
        daily_loss_exceeded: bool,
        balance: float,
        has_position: bool,
        open_positions_count: int,
        candles_15m: list[dict],
        candles_1h: list[dict],
    ) -> dict[str, Any]:
        es = self._es()
        entry = es.get("entry") or {}
        risk = es.get("risk") or {}
        cooldown_candles = int(entry.get("cooldown_candles", 2))
        tf_sec = 300  # 5m

        if indicators.get("warming_up"):
            return {"action": "HOLD", "reason": "warmup"}

        if has_position:
            return {"action": "HOLD", "reason": "position_exists"}

        max_pos = int(risk.get("max_open_positions", 2))
        if open_positions_count >= max_pos:
            return {"action": "HOLD", "reason": "max_positions"}

        if daily_loss_exceeded:
            return {"action": "HOLD", "reason": "daily_loss_limit"}

        now = time.time()
        if now - last_entry_ts < cooldown_candles * tf_sec:
            return {"action": "HOLD", "reason": "cooldown"}

        vol_ratio = float(indicators.get("volume_ratio", 0))
        vol_mult = float(entry.get("volume_multiplier", 1.2))
        if vol_ratio < vol_mult:
            return {"action": "HOLD", "reason": "volume_filter"}

        body_pct = float(indicators.get("candle_body_pct", 0))
        min_body = float(entry.get("min_candle_body_pct", 0.03))
        if body_pct < min_body:
            return {"action": "HOLD", "reason": "doji_candle"}

        close = float(indicators["close"])
        ema = float(indicators["ema_current"])
        above = int(indicators.get("above_ema_count", 0))
        below = int(indicators.get("below_ema_count", 0))
        mn = int(entry.get("min_candles_above_below", 3))
        mx = int(entry.get("max_candles_above_below", 8))
        is_green = bool(indicators.get("is_green"))
        is_red = bool(indicators.get("is_red"))

        potential_long = (
            close > ema and mn <= above <= mx and is_green
        )
        potential_short = (
            close < ema and mn <= below <= mx and is_red
        )

        if not (potential_long or potential_short):
            return {"action": "HOLD", "reason": "no_ema_setup"}

        rsi = float(indicators.get("rsi", 50))
        rsi_long_max = float(entry.get("rsi_long_max", 70))
        rsi_short_min = float(entry.get("rsi_short_min", 30))
        if potential_long and rsi > rsi_long_max:
            return {"action": "HOLD", "reason": "rsi_overbought"}
        if potential_short and rsi < rsi_short_min:
            return {"action": "HOLD", "reason": "rsi_oversold"}

        structure = indicators.get("structure_15m") or get_market_structure(
            candles_15m, int(entry.get("market_structure_lookback", 6))
        )
        require_both = bool(entry.get("require_both_tf_confirm", True))
        ms_enabled = bool(entry.get("market_structure_enabled", True))

        if ms_enabled and require_both:
            if structure == "RANGING":
                return {"action": "HOLD", "reason": "ranging_market"}
            if potential_long and structure != "BULLISH":
                return {"action": "HOLD", "reason": "structure_conflict"}
            if potential_short and structure != "BEARISH":
                return {"action": "HOLD", "reason": "structure_conflict"}
        elif ms_enabled and not require_both:
            if potential_long and structure == "BEARISH":
                return {"action": "HOLD", "reason": "structure_conflict"}
            if potential_short and structure == "BULLISH":
                return {"action": "HOLD", "reason": "structure_conflict"}

        # --- 1H ТРЕНД ФИЛЬТР ---
        if entry.get("higher_tf_trend_enabled", False):
            candles_1h_f = indicators.get("candles_1h", []) or candles_1h
            trend_1h = get_1h_trend(
                candles_1h_f,
                entry.get("higher_tf_ema_fast", 9),
                entry.get("higher_tf_ema_slow", 21),
            )
            indicators["trend_1h_data"] = trend_1h
            indicators["trend_1h"] = trend_1h["trend"]

            if potential_long and not trend_1h["bullish"]:
                return {"action": "HOLD", "reason": f"1h_trend_{trend_1h['trend']}"}
            if potential_short and not trend_1h["bearish"]:
                return {"action": "HOLD", "reason": f"1h_trend_{trend_1h['trend']}"}

        trend_1h = indicators.get("trend_1h_data") or get_1h_trend(
            indicators.get("candles_1h", []) or candles_1h,
            int(entry.get("higher_tf_ema_fast", 9)),
            int(entry.get("higher_tf_ema_slow", 21)),
        )

        if potential_long:
            logger.info(
                "EMA_TRADE ENTRY %s LONG entry=%s above_ema=%s vol_ratio=%.2f rsi=%.1f "
                "15m_structure=%s 1h_trend=%s",
                symbol,
                close,
                above,
                vol_ratio,
                rsi,
                structure,
                trend_1h.get("trend"),
            )
            return {"action": "OPEN_LONG", "reason": "entry", "price": close}

        logger.info(
            "EMA_TRADE ENTRY %s SHORT entry=%s below_ema=%s vol_ratio=%.2f rsi=%.1f "
            "15m_structure=%s 1h_trend=%s",
            symbol,
            close,
            below,
            vol_ratio,
            rsi,
            structure,
            trend_1h.get("trend"),
        )
        return {"action": "OPEN_SHORT", "reason": "entry", "price": close}

    def check_exit(
        self,
        pos: ScalpPosition,
        indicators: dict[str, Any],
    ) -> dict[str, Any]:
        es = self._es()
        ex = es.get("exit") or {}
        max_hold = int(ex.get("max_hold_candles", 10))
        ema_cross = bool(ex.get("ema_cross_exit", False))

        price = float(indicators.get("close", pos.current_price))

        if pos.side == "LONG":
            if price >= pos.tp_price:
                return {"should_exit": True, "reason": "TP"}
            if price <= pos.sl_price:
                return {"should_exit": True, "reason": "SL"}
        else:
            if price <= pos.tp_price:
                return {"should_exit": True, "reason": "TP"}
            if price >= pos.sl_price:
                return {"should_exit": True, "reason": "SL"}

        if pos.candles_held >= max_hold:
            return {"should_exit": True, "reason": "TIME"}

        if ema_cross:
            ema = float(indicators.get("ema_current", 0))
            if pos.side == "LONG" and price < ema:
                return {"should_exit": True, "reason": "EMA_CROSS"}
            if pos.side == "SHORT" and price > ema:
                return {"should_exit": True, "reason": "EMA_CROSS"}

        return {"should_exit": False, "reason": ""}

    def signal_status_for_ui(
        self,
        indicators: dict[str, Any],
        candles_15m: list[dict],
        candles_1h: list[dict],
        has_position: bool,
        *,
        last_entry_ts: float = 0.0,
        daily_loss_exceeded: bool = False,
        open_positions_count: int = 0,
        balance: float = 500.0,
    ) -> dict[str, Any]:
        """Статус строки таблицы сигналов (без открытия сделки)."""
        if indicators.get("warming_up"):
            return {
                "status": "FILTER",
                "reason": "warmup",
                "structure_15m": "—",
                "trend_1h": "NEUTRAL",
                "ema": 0.0,
                "price": 0.0,
                "above_count": 0,
                "below_count": 0,
                "volume_ratio": 0.0,
                "rsi": 0.0,
                "ema_1h_fast": 0.0,
                "ema_1h_slow": 0.0,
                "atr": 0.0,
            }

        entry = (self._es().get("entry")) or {}
        structure = indicators.get("structure_15m") or get_market_structure(
            candles_15m, int(entry.get("market_structure_lookback", 6))
        )

        r = self.check_entry(
            indicators=indicators,
            symbol="",
            last_entry_ts=last_entry_ts,
            daily_loss_exceeded=daily_loss_exceeded,
            balance=balance,
            has_position=has_position,
            open_positions_count=open_positions_count,
            candles_15m=candles_15m,
            candles_1h=candles_1h,
        )

        ch1 = indicators.get("candles_1h") or candles_1h
        t1h = indicators.get("trend_1h_data") or get_1h_trend(
            ch1,
            int(entry.get("higher_tf_ema_fast", 9)),
            int(entry.get("higher_tf_ema_slow", 21)),
        )

        action = r["action"]
        reason = r.get("reason", "")
        if has_position:
            st = "IN_POSITION"
        elif action == "OPEN_LONG":
            st = "READY_LONG"
        elif action == "OPEN_SHORT":
            st = "READY_SHORT"
        else:
            st = "FILTER"

        return {
            "status": st,
            "reason": reason,
            "structure_15m": structure,
            "trend_1h": t1h.get("trend", "NEUTRAL"),
            "ema": float(indicators.get("ema_current", 0)),
            "price": float(indicators.get("close", 0)),
            "above_count": int(indicators.get("above_ema_count", 0)),
            "below_count": int(indicators.get("below_ema_count", 0)),
            "volume_ratio": float(indicators.get("volume_ratio", 0)),
            "rsi": float(indicators.get("rsi", 0)),
            "ema_1h_fast": float(t1h.get("ema_fast", 0)),
            "ema_1h_slow": float(t1h.get("ema_slow", 0)),
            "atr": float(indicators.get("atr", 0)),
        }
