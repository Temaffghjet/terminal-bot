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


def calc_momentum(candles: list[dict[str, Any]], ema: list[float]) -> dict[str, Any]:
    """
    Проверяет, что последняя свеча удаляется от EMA, а не приближается к ней.

    momentum_long: close выше EMA, расстояние до EMA растёт, последняя свеча выше предыдущей.
    momentum_short: зеркально для шорта.
    """
    if len(candles) < 2 or len(ema) < 2:
        return {
            "momentum_long": False,
            "momentum_short": False,
            "distance_from_ema": 0.0,
            "distance_change": 0.0,
        }
    c1 = float(candles[-1]["close"])
    c2 = float(candles[-2]["close"])
    e1 = float(ema[-1])
    e2 = float(ema[-2])

    momentum_long = (c1 > e1) and ((c1 - e1) > (c2 - e2)) and (c1 > c2)
    momentum_short = (c1 < e1) and ((e1 - c1) > (e2 - c2)) and (c1 < c2)

    return {
        "momentum_long": momentum_long,
        "momentum_short": momentum_short,
        "distance_from_ema": abs(c1 - e1),
        "distance_change": (c1 - e1) - (c2 - e2),
    }


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
    momentum = calc_momentum(candles, ema)
    result: dict[str, Any] = {
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
    result.update(momentum)
    return result
