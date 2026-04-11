"""Breakout detection on closed candles."""
from __future__ import annotations

from typing import Any

import ccxt
import pandas as pd


class BreakoutDetector:
    def __init__(self, config: dict) -> None:
        self.cfg = config.get("breakout") or {}
        self.lookback = int(self.cfg.get("lookback_candles", 20))
        self.vol_mult = float(self.cfg.get("volume_multiplier", 1.2))

    def detect(self, candles: pd.DataFrame) -> dict[str, Any]:
        if len(candles) < self.lookback + 2:
            return {
                "signal": "NONE",
                "breakout_level": 0.0,
                "current_close": 0.0,
                "volume_ratio": 0.0,
                "atr": 0.0,
                "reason": "not enough candles",
            }
        prev = candles.iloc[-self.lookback - 1 : -1]
        rolling_high = float(prev["high"].max())
        rolling_low = float(prev["low"].min())
        avg_vol = float(prev["volume"].mean())
        last = candles.iloc[-1]
        close = float(last["close"])
        vol_c = float(last["volume"])
        vol_ratio = (vol_c / avg_vol) if avg_vol > 1e-12 else 0.0

        trs: list[float] = []
        h = candles["high"].astype(float)
        l = candles["low"].astype(float)
        c = candles["close"].astype(float)
        for i in range(1, len(candles)):
            tr = max(
                h.iloc[i] - l.iloc[i],
                abs(h.iloc[i] - c.iloc[i - 1]),
                abs(l.iloc[i] - c.iloc[i - 1]),
            )
            trs.append(tr)
        atr_window = trs[-14:] if len(trs) >= 14 else trs
        atr = float(sum(atr_window) / len(atr_window)) if atr_window else 0.0

        need_vol = avg_vol * self.vol_mult
        if vol_c <= need_vol:
            return {
                "signal": "NONE",
                "breakout_level": rolling_high,
                "current_close": close,
                "volume_ratio": vol_ratio,
                "atr": atr,
                "reason": f"volume {vol_ratio:.2f}x < {self.vol_mult}x filter",
            }

        if close > rolling_high:
            return {
                "signal": "LONG",
                "breakout_level": rolling_high,
                "current_close": close,
                "volume_ratio": vol_ratio,
                "atr": atr,
                "reason": f"close {close:.6f} > prior high {rolling_high:.6f}, vol {vol_ratio:.2f}x",
            }
        if close < rolling_low:
            return {
                "signal": "SHORT",
                "breakout_level": rolling_low,
                "current_close": close,
                "volume_ratio": vol_ratio,
                "atr": atr,
                "reason": f"close {close:.6f} < prior low {rolling_low:.6f}, vol {vol_ratio:.2f}x",
            }
        return {
            "signal": "NONE",
            "breakout_level": rolling_high,
            "current_close": close,
            "volume_ratio": vol_ratio,
            "atr": atr,
            "reason": "inside range",
        }

    def get_candles(
        self, exchange: ccxt.Exchange, symbol: str, timeframe: str, limit: int
    ) -> pd.DataFrame:
        ohlcv = exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
        if not ohlcv:
            return pd.DataFrame(
                columns=["timestamp", "open", "high", "low", "close", "volume"]
            )
        if len(ohlcv) > 1:
            ohlcv = ohlcv[:-1]
        rows = []
        for x in ohlcv:
            rows.append(
                {
                    "timestamp": int(x[0]),
                    "open": float(x[1]),
                    "high": float(x[2]),
                    "low": float(x[3]),
                    "close": float(x[4]),
                    "volume": float(x[5]),
                }
            )
        return pd.DataFrame(rows)
