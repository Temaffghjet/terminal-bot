"""EMA + volume indicators for closed-candle scalper."""
from __future__ import annotations

from typing import Any


def calc_ema(closes: list[float], period: int) -> list[float]:
    if not closes:
        return []
    k = 2.0 / (period + 1)
    ema = [closes[0]]
    for price in closes[1:]:
        ema.append(price * k + ema[-1] * (1.0 - k))
    return ema


def get_indicators(candles: list[dict[str, Any]], entry_cfg: dict[str, Any]) -> dict[str, Any]:
    ema_period = int(entry_cfg.get("ema_period", 9))
    vol_lb = int(entry_cfg.get("volume_lookback", 10))
    min_required = ema_period + vol_lb + 2
    if len(candles) < min_required:
        return {"warming_up": True}

    closes = [float(c["close"]) for c in candles]
    ema = calc_ema(closes, ema_period)
    vols = [float(c["volume"]) for c in candles]
    lb = min(vol_lb, len(vols) - 1)
    if lb < 1:
        return {"warming_up": True}
    vol_avg = sum(vols[-lb - 1 : -1]) / float(lb)
    vol_c = vols[-1]
    vol_ratio = vol_c / vol_avg if vol_avg > 1e-12 else 0.0

    def count_above() -> int:
        cnt = 0
        for i in range(len(candles) - 1, -1, -1):
            if closes[i] > ema[i]:
                cnt += 1
            else:
                break
        return cnt

    def count_below() -> int:
        cnt = 0
        for i in range(len(candles) - 1, -1, -1):
            if closes[i] < ema[i]:
                cnt += 1
            else:
                break
        return cnt

    last = candles[-1]
    close = float(last["close"])
    open_ = float(last["open"])
    return {
        "warming_up": False,
        "ema_current": float(ema[-1]),
        "close": close,
        "open": open_,
        "volume_current": vol_c,
        "volume_avg": vol_avg,
        "volume_ratio": vol_ratio,
        "above_ema_count": count_above(),
        "below_ema_count": count_below(),
        "is_green": close > open_,
        "is_red": close < open_,
        "quote_volume_usdt": close * vol_c,
    }
