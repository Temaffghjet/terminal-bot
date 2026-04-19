"""Индикаторы EMA Scalper v3: 5m, структура 15m, тренд 1H."""
from __future__ import annotations

import logging
import time
from typing import Any

logger = logging.getLogger(__name__)

_htf_cache: dict[str, dict[str, Any]] = {}


def calc_ema(closes: list[float], period: int) -> list[float]:
    if not closes:
        return []
    k = 2 / (period + 1)
    ema = [closes[0]]
    for price in closes[1:]:
        ema.append(price * k + ema[-1] * (1 - k))
    return ema


def calc_rsi(closes: list[float], period: int = 14) -> float:
    gains: list[float] = []
    losses: list[float] = []
    for i in range(1, len(closes)):
        diff = closes[i] - closes[i - 1]
        gains.append(max(diff, 0))
        losses.append(max(-diff, 0))
    if len(gains) < period:
        return 50.0
    avg_gain = sum(gains[-period:]) / period
    avg_loss = sum(losses[-period:]) / period
    if avg_loss == 0:
        return 100.0
    return 100 - (100 / (1 + avg_gain / avg_loss))


def calc_atr(candles: list[dict], period: int = 14) -> float:
    trs: list[float] = []
    for i in range(1, len(candles)):
        h, l, pc = candles[i]["high"], candles[i]["low"], candles[i - 1]["close"]
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    if not trs:
        return 0.0
    return sum(trs[-period:]) / min(len(trs), period)


def calc_avg_volume(candles: list[dict], lookback: int) -> float:
    vols = [c["volume"] for c in candles[-lookback - 1 : -1]]
    return sum(vols) / len(vols) if vols else 0.0


def count_consecutive_above_ema(candles: list[dict], ema: list[float]) -> int:
    if len(candles) != len(ema):
        n = min(len(candles), len(ema))
        candles = candles[-n:]
        ema = ema[-n:]
    count = 0
    for i in range(len(candles) - 1, -1, -1):
        if candles[i]["close"] > ema[i]:
            count += 1
        else:
            break
    return count


def count_consecutive_below_ema(candles: list[dict], ema: list[float]) -> int:
    if len(candles) != len(ema):
        n = min(len(candles), len(ema))
        candles = candles[-n:]
        ema = ema[-n:]
    count = 0
    for i in range(len(candles) - 1, -1, -1):
        if candles[i]["close"] < ema[i]:
            count += 1
        else:
            break
    return count


def get_market_structure(candles_htf: list[dict], lookback: int = 6) -> str:
    if len(candles_htf) < lookback:
        return "RANGING"

    last = candles_htf[-lookback:]
    highs = [c["high"] for c in last]
    lows = [c["low"] for c in last]

    if len(highs) < 6 or len(lows) < 6:
        return "RANGING"

    hh = highs[-1] > highs[-3] > highs[-5]
    hl = lows[-1] > lows[-3] > lows[-5]
    lh = highs[-1] < highs[-3] < highs[-5]
    ll = lows[-1] < lows[-3] < lows[-5]

    if hh and hl:
        return "BULLISH"
    if lh and ll:
        return "BEARISH"
    return "RANGING"


def get_htf_data_cached(
    exchange: Any,
    symbol: str,
    tf: str,
    ttl: float = 60.0,
) -> list[dict]:
    now = time.time()
    key = f"{symbol}:{tf}"
    if key in _htf_cache and now - _htf_cache[key]["ts"] < ttl:
        return _htf_cache[key]["data"]

    try:
        raw = exchange.fetch_ohlcv(symbol, tf, limit=40)
        if not raw:
            raise RuntimeError("empty ohlcv")
        raw_closed = raw[:-1]
        candles = [
            {
                "t": int(x[0]),
                "open": x[1],
                "high": x[2],
                "low": x[3],
                "close": x[4],
                "volume": x[5],
            }
            for x in raw_closed
        ]
        _htf_cache[key] = {"data": candles, "ts": now}
        return candles
    except Exception as e:
        logger.warning("[EMA HTF] %s %s: %s — используем кэш если есть", symbol, tf, e)
        if key in _htf_cache:
            return _htf_cache[key]["data"]
        return []


def get_indicators(candles_5m: list[dict], entry_cfg: dict) -> dict[str, Any]:
    """
    Только закрытые 5m свечи. Минимум: ema_period + volume_lookback + 5.
    """
    ema_period = int(entry_cfg.get("ema_period", 9))
    volume_lookback = int(entry_cfg.get("volume_lookback", 10))
    rsi_period = int(entry_cfg.get("rsi_period", 14))
    min_need = ema_period + volume_lookback + 5

    if len(candles_5m) < min_need:
        return {"warming_up": True}

    closes = [c["close"] for c in candles_5m]
    ema_series = calc_ema(closes, ema_period)
    ema_current = ema_series[-1]
    last = candles_5m[-1]
    close = last["close"]
    open_ = last["open"]
    vol = last["volume"]
    vol_avg = calc_avg_volume(candles_5m, volume_lookback)
    vol_ratio = vol / vol_avg if vol_avg > 0 else 0.0

    body_pct = abs(close - open_) / open_ * 100 if open_ else 0.0

    return {
        "warming_up": False,
        "ema_current": ema_current,
        "close": close,
        "open": open_,
        "volume_current": vol,
        "volume_avg": vol_avg,
        "volume_ratio": vol_ratio,
        "above_ema_count": count_consecutive_above_ema(candles_5m, ema_series),
        "below_ema_count": count_consecutive_below_ema(candles_5m, ema_series),
        "is_green": close > open_,
        "is_red": close < open_,
        "candle_body_pct": body_pct,
        "rsi": calc_rsi(closes, rsi_period),
        "atr": calc_atr(candles_5m, 14),
    }


def get_1h_trend(
    candles_1h: list[dict],
    ema_fast: int = 9,
    ema_slow: int = 21,
) -> dict[str, Any]:
    if len(candles_1h) < ema_slow + 5:
        return {
            "trend": "NEUTRAL",
            "ema_fast": 0.0,
            "ema_slow": 0.0,
            "bullish": False,
            "bearish": False,
        }

    closes = [float(c["close"]) for c in candles_1h]
    ema9 = calc_ema(closes, ema_fast)
    ema21 = calc_ema(closes, ema_slow)

    close = closes[-1]
    e9 = ema9[-1]
    e21 = ema21[-1]

    if close > e9 and e9 > e21:
        trend = "STRONG_UP"
    elif close < e9 and e9 < e21:
        trend = "STRONG_DOWN"
    elif close > e21:
        trend = "WEAK_UP"
    elif close < e21:
        trend = "WEAK_DOWN"
    else:
        trend = "NEUTRAL"

    return {
        "trend": trend,
        "ema_fast": round(e9, 4),
        "ema_slow": round(e21, 4),
        "close": close,
        "bullish": trend == "STRONG_UP",
        "bearish": trend == "STRONG_DOWN",
    }
