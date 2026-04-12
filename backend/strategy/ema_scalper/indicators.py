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


def calc_rsi(closes: list[float], period: int = 14) -> float:
    """RSI по простым средним дельг (как в ТЗ). Значение 0–100."""
    if len(closes) < 2:
        return 50.0
    gains: list[float] = []
    losses: list[float] = []
    for i in range(1, len(closes)):
        diff = closes[i] - closes[i - 1]
        gains.append(max(diff, 0.0))
        losses.append(max(-diff, 0.0))
    if len(gains) < period:
        return 50.0
    avg_gain = sum(gains[-period:]) / float(period)
    avg_loss = sum(losses[-period:]) / float(period)
    if avg_loss <= 1e-12:
        return 100.0
    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))


def calc_candle_body_pct(candle: dict[str, Any]) -> float:
    """Тело свечи в % от open — отсев «копеечных» доджи."""
    o = float(candle.get("open") or 0.0)
    c = float(candle.get("close") or 0.0)
    if abs(o) < 1e-12:
        return 0.0
    return abs(c - o) / abs(o) * 100.0


def higher_tf_trend_from_closes(closes: list[float], ema_period: int = 9) -> str | None:
    """
    Тренд старшего ТФ: close последней закрытой свечи vs EMA(ema_period).
    Возвращает UP / DOWN / None если мало данных.
    """
    if len(closes) < ema_period + 1:
        return None
    ema = calc_ema(closes, ema_period)
    if not ema:
        return None
    last = closes[-1]
    e = ema[-1]
    if last > e:
        return "UP"
    if last < e:
        return "DOWN"
    return "NEUTRAL"


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
    rsi_period = int(entry_cfg.get("rsi_period", 14))
    min_required = max(ema_period + vol_lb + 2, rsi_period + 5)
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
    rsi = calc_rsi(closes, period=rsi_period)
    body_pct = calc_candle_body_pct(last)
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
        "rsi": rsi,
        "candle_body_pct": body_pct,
    }
    result.update(momentum)
    return result
