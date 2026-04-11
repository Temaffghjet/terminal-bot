"""Micro scalping: EMA + объём + зелёная/красная свеча (MicroSignalEngine)."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def _ema_array(closes: list[float], period: int) -> list[float]:
    if not closes:
        return []
    k = 2.0 / (period + 1)
    out = [closes[0]]
    for i in range(1, len(closes)):
        out.append(closes[i] * k + out[i - 1] * (1.0 - k))
    return out


def _consecutive_above_ema(closes: list[float], ema: list[float]) -> int:
    n = min(len(closes), len(ema))
    if n < 2:
        return 0
    cnt = 0
    for j in range(1, n + 1):
        i = -j
        if closes[i] > ema[i]:
            cnt += 1
        else:
            break
    return cnt


def _consecutive_below_ema(closes: list[float], ema: list[float]) -> int:
    n = min(len(closes), len(ema))
    if n < 2:
        return 0
    cnt = 0
    for j in range(1, n + 1):
        i = -j
        if closes[i] < ema[i]:
            cnt += 1
        else:
            break
    return cnt


class MicroSignalEngine:
    def __init__(self, config: dict) -> None:
        self.cfg = config.get("scalping") or {}
        ent = self.cfg.get("entry") or {}
        ex = self.cfg.get("exit") or {}
        fl = self.cfg.get("filters") or {}
        self.ema_period = int(ent.get("ema_period", 9))
        self.vol_mult = float(ent.get("volume_multiplier", 1.2))
        self.min_candles = int(ent.get("min_candles", 2))
        self.volume_lookback = int(ent.get("volume_lookback", 10))
        self.tp = float(ex.get("take_profit_pct", 0.6))
        self.sl = float(ex.get("stop_loss_pct", 0.5))
        self.max_hold = float(ex.get("max_hold_minutes", 3))
        self.no_trade_hours = list(fl.get("no_trade_hours") or [])
        self.min_volume_usdt = float(fl.get("min_volume_usdt", 0))

    def calculate_indicators(self, ohlcv: list) -> dict[str, Any]:
        if len(ohlcv) < self.ema_period + 2:
            return {
                "ema": None,
                "volume_avg": None,
                "volume_current": None,
                "above_ema_count": 0,
                "below_ema_count": 0,
                "last_close": None,
                "is_green": False,
                "quote_volume_est": None,
            }
        opens = [float(x[1]) for x in ohlcv]
        closes = [float(x[4]) for x in ohlcv]
        vols = [float(x[5]) for x in ohlcv]
        ema = _ema_array(closes, self.ema_period)
        lb = min(self.volume_lookback, len(vols))
        vol_avg = sum(vols[-lb:]) / float(lb) if lb else 0.0
        above = _consecutive_above_ema(closes, ema)
        below = _consecutive_below_ema(closes, ema)
        last_o, last_c, last_v = opens[-1], closes[-1], vols[-1]
        qv_est = last_c * last_v
        return {
            "ema": float(ema[-1]),
            "volume_avg": float(vol_avg),
            "volume_current": float(last_v),
            "above_ema_count": int(above),
            "below_ema_count": int(below),
            "last_close": float(last_c),
            "is_green": last_c > last_o,
            "quote_volume_est": float(qv_est),
        }

    def _hour_blocked_utc(self, when: datetime | None = None) -> bool:
        dt = when or datetime.now(timezone.utc)
        return dt.hour in self.no_trade_hours

    def check_entry(self, symbol: str, ohlcv: list, has_position: bool) -> dict[str, Any]:
        if has_position:
            return {"action": "HOLD", "reason": "has_position", "confidence": 0.0, "symbol": symbol}
        ind = self.calculate_indicators(ohlcv)
        if ind["ema"] is None:
            return {"action": "HOLD", "reason": "warmup", "confidence": 0.0, "symbol": symbol}
        if self._hour_blocked_utc():
            return {"action": "HOLD", "reason": "no_trade_hour_utc", "confidence": 0.0, "symbol": symbol}
        ema = float(ind["ema"])
        close = float(ind["last_close"])
        vol_c = float(ind["volume_current"])
        vol_a = float(ind["volume_avg"] or 0)
        qv = float(ind["quote_volume_est"] or 0)
        if self.min_volume_usdt > 0 and qv < self.min_volume_usdt:
            return {"action": "HOLD", "reason": "low_liquidity", "confidence": 0.0, "symbol": symbol}
        if vol_a <= 0 or vol_c <= vol_a * self.vol_mult:
            return {"action": "HOLD", "reason": "volume_filter", "confidence": 0.0, "symbol": symbol}

        if close > ema and ind["above_ema_count"] >= self.min_candles and ind["is_green"]:
            return {
                "action": "OPEN_LONG",
                "reason": "ema_volume_green",
                "confidence": 0.85,
                "symbol": symbol,
                "indicators": ind,
            }
        is_red = not ind["is_green"]
        if close < ema and ind["below_ema_count"] >= self.min_candles and is_red:
            return {
                "action": "OPEN_SHORT",
                "reason": "ema_volume_red",
                "confidence": 0.85,
                "symbol": symbol,
                "indicators": ind,
            }
        return {"action": "HOLD", "reason": "no_setup", "confidence": 0.2, "symbol": symbol, "indicators": ind}

    def check_exit(
        self,
        position: dict[str, Any],
        current_price: float,
        entry_time: str,
        ema: float,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        now = now or datetime.now(timezone.utc)
        side = str(position.get("side", "LONG"))
        entry = float(position.get("entry_price", 0))
        if entry <= 0:
            return {"action": "HOLD", "reason": "bad_entry"}
        if side == "LONG":
            pnl_pct = (current_price - entry) / entry * 100.0
        else:
            pnl_pct = (entry - current_price) / entry * 100.0
        if pnl_pct >= self.tp:
            return {"action": "EXIT", "reason": "TAKE_PROFIT", "pnl_pct": pnl_pct}
        if pnl_pct <= -self.sl:
            return {"action": "EXIT", "reason": "STOP_LOSS", "pnl_pct": pnl_pct}
        try:
            et = datetime.fromisoformat(entry_time.replace("Z", "+00:00"))
            if et.tzinfo is None:
                et = et.replace(tzinfo=timezone.utc)
            if (now - et).total_seconds() / 60.0 >= self.max_hold:
                return {"action": "EXIT", "reason": "TIME_EXIT", "pnl_pct": pnl_pct}
        except Exception:
            pass
        if side == "LONG" and current_price < ema:
            return {"action": "EXIT", "reason": "EMA_CROSS_EXIT", "pnl_pct": pnl_pct}
        if side == "SHORT" and current_price > ema:
            return {"action": "EXIT", "reason": "EMA_CROSS_EXIT", "pnl_pct": pnl_pct}
        return {"action": "HOLD", "reason": "in_trade", "pnl_pct": pnl_pct}


__all__ = ["MicroSignalEngine"]
