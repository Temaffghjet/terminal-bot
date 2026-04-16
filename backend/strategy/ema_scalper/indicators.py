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


def calc_atr(candles: list[dict[str, Any]], period: int = 14) -> float:
    if len(candles) < period + 1:
        return 0.0
    trs: list[float] = []
    for i in range(1, len(candles)):
        h = float(candles[i]["high"])
        l = float(candles[i]["low"])
        pc = float(candles[i - 1]["close"])
        tr = max(h - l, abs(h - pc), abs(l - pc))
        trs.append(tr)
    if len(trs) < period:
        return 0.0
    return sum(trs[-period:]) / float(period)


def calc_vwap(candles: list[dict[str, Any]], lookback: int = 20) -> float:
    if not candles:
        return 0.0
    lb = min(len(candles), max(1, lookback))
    sl = candles[-lb:]
    pv = 0.0
    vv = 0.0
    for c in sl:
        h = float(c["high"])
        l = float(c["low"])
        cl = float(c["close"])
        v = float(c["volume"])
        typical = (h + l + cl) / 3.0
        pv += typical * v
        vv += v
    if vv <= 1e-12:
        return float(sl[-1]["close"])
    return pv / vv


def calc_adx(candles: list[dict[str, Any]], period: int = 14) -> float:
    """
    Упрощённый ADX (Wilder): сила тренда без направления.
    Для anti-chop фильтра достаточно значения ADX.
    """
    if len(candles) < period * 2 + 1:
        return 0.0
    plus_dm: list[float] = []
    minus_dm: list[float] = []
    tr: list[float] = []
    for i in range(1, len(candles)):
        cur = candles[i]
        prev = candles[i - 1]
        up = float(cur["high"]) - float(prev["high"])
        down = float(prev["low"]) - float(cur["low"])
        plus_dm.append(up if up > down and up > 0 else 0.0)
        minus_dm.append(down if down > up and down > 0 else 0.0)
        h = float(cur["high"])
        l = float(cur["low"])
        pc = float(prev["close"])
        tr.append(max(h - l, abs(h - pc), abs(l - pc)))
    if len(tr) < period:
        return 0.0
    plus_di_vals: list[float] = []
    minus_di_vals: list[float] = []
    for i in range(period, len(tr) + 1):
        tr_sum = sum(tr[i - period : i])
        if tr_sum <= 1e-12:
            plus_di_vals.append(0.0)
            minus_di_vals.append(0.0)
            continue
        p_sum = sum(plus_dm[i - period : i])
        m_sum = sum(minus_dm[i - period : i])
        plus_di_vals.append(100.0 * p_sum / tr_sum)
        minus_di_vals.append(100.0 * m_sum / tr_sum)
    if len(plus_di_vals) < period:
        return 0.0
    dx: list[float] = []
    for p, m in zip(plus_di_vals, minus_di_vals):
        den = p + m
        dx.append(0.0 if den <= 1e-12 else 100.0 * abs(p - m) / den)
    if len(dx) < period:
        return 0.0
    return sum(dx[-period:]) / float(period)


def calc_macd(
    closes: list[float],
    fast_period: int = 12,
    slow_period: int = 26,
    signal_period: int = 9,
) -> dict[str, float]:
    """Классический MACD (EMA fast - EMA slow) + signal + histogram."""
    if len(closes) < max(slow_period + signal_period, 35):
        return {"macd": 0.0, "macd_signal": 0.0, "macd_hist": 0.0, "macd_hist_prev": 0.0}
    fast = calc_ema(closes, fast_period)
    slow = calc_ema(closes, slow_period)
    macd_line = [f - s for f, s in zip(fast, slow)]
    signal_line = calc_ema(macd_line, signal_period)
    if not macd_line or not signal_line:
        return {"macd": 0.0, "macd_signal": 0.0, "macd_hist": 0.0, "macd_hist_prev": 0.0}
    macd_now = float(macd_line[-1])
    signal_now = float(signal_line[-1])
    hist_now = macd_now - signal_now
    hist_prev = float(macd_line[-2] - signal_line[-2]) if len(macd_line) >= 2 and len(signal_line) >= 2 else hist_now
    return {
        "macd": macd_now,
        "macd_signal": signal_now,
        "macd_hist": hist_now,
        "macd_hist_prev": hist_prev,
    }


def calc_last_value_percentile(values: list[float], lookback: int = 40) -> float:
    """
    Перцентиль последнего значения внутри lookback окна в диапазоне [0, 100].
    100 = максимум окна, 0 = минимум.
    """
    if len(values) < 2:
        return 50.0
    lb = min(max(2, lookback), len(values))
    sl = values[-lb:]
    last = sl[-1]
    less_eq = sum(1 for v in sl if v <= last)
    return (less_eq / float(lb)) * 100.0


def compute_higher_tf_trend_from_ohlcv(ohlcv: list[Any]) -> dict[str, Any] | None:
    """
    Тренд старшего ТФ по закрытым свечам: последняя цена vs EMA(9) и EMA(21).
    Формирующая свеча отбрасывается (как fetch_ohlcv[:-1]).
    """
    if not ohlcv or len(ohlcv) < 3:
        return None
    closed = ohlcv[:-1]
    if len(closed) < 21:
        return None
    closes = [float(c[4]) for c in closed]
    ema9 = calc_ema(closes, 9)
    ema21 = calc_ema(closes, 21)
    if not ema9 or not ema21:
        return None
    close = closes[-1]
    e9 = ema9[-1]
    e21 = ema21[-1]
    trend_up = close > e9 and e9 > e21
    trend_down = close < e9 and e9 < e21
    if trend_up:
        trend = "UP"
    elif trend_down:
        trend = "DOWN"
    else:
        trend = "FLAT"
    volumes = [float(c[5]) for c in closed]
    vol_ratio = 1.0
    if len(volumes) >= 2:
        lb = min(20, len(volumes) - 1)
        vol_avg = sum(volumes[-lb - 1 : -1]) / float(lb)
        vol_ratio = (volumes[-1] / vol_avg) if vol_avg > 1e-12 else 1.0
    return {
        "trend": trend,
        "close": close,
        "ema9": e9,
        "ema21": e21,
        "volume_ratio": vol_ratio,
    }


def get_higher_tf_trend(exchange: Any, symbol: str, tf: str = "15m") -> dict[str, Any] | None:
    """Синхронно: одна выборка OHLCV и расчёт тренда (для тестов/утилит)."""
    try:
        raw = exchange.fetch_ohlcv(symbol, tf, limit=25)
    except Exception:
        return None
    return compute_higher_tf_trend_from_ohlcv(raw)


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
            "momentum_long_loose": False,
            "momentum_short_loose": False,
            "distance_from_ema": 0.0,
            "distance_change": 0.0,
        }
    c1 = float(candles[-1]["close"])
    c2 = float(candles[-2]["close"])
    o1 = float(candles[-1]["open"])
    e1 = float(ema[-1])
    e2 = float(ema[-2])

    # strict: расстояние до EMA растёт — часто поздний вход в конце импульса
    momentum_long = (c1 > e1) and ((c1 - e1) > (c2 - e2)) and (c1 > c2)
    momentum_short = (c1 < e1) and ((e1 - c1) > (e2 - c2)) and (c1 < c2)
    # loose: тренд + зелёная/красная свеча + движение в сторону сделки (раньше по времени)
    momentum_long_loose = (c1 > e1) and (c1 > c2) and (c1 > o1)
    momentum_short_loose = (c1 < e1) and (c1 < c2) and (c1 < o1)

    return {
        "momentum_long": momentum_long,
        "momentum_short": momentum_short,
        "momentum_long_loose": momentum_long_loose,
        "momentum_short_loose": momentum_short_loose,
        "distance_from_ema": abs(c1 - e1),
        "distance_change": (c1 - e1) - (c2 - e2),
    }


def get_indicators(candles: list[dict[str, Any]], entry_cfg: dict[str, Any]) -> dict[str, Any]:
    ema_period = int(entry_cfg.get("ema_period", 9))
    vol_lb = int(entry_cfg.get("volume_lookback", 10))
    rsi_period = int(entry_cfg.get("rsi_period", 14))
    adx_period = int(entry_cfg.get("adx_period", 14))
    atr_period = int(entry_cfg.get("atr_period", 14))
    vwap_lb = int(entry_cfg.get("vwap_lookback", 20))
    vol_pct_lb = int(entry_cfg.get("volume_percentile_lookback", 40))
    macd_fast = int(entry_cfg.get("macd_fast_period", 12))
    macd_slow = int(entry_cfg.get("macd_slow_period", 26))
    macd_signal = int(entry_cfg.get("macd_signal_period", 9))
    min_required = max(
        ema_period + vol_lb + 2,
        rsi_period + 5,
        adx_period * 2 + 1,
        atr_period + 2,
        vwap_lb + 2,
        macd_slow + macd_signal + 2,
    )
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
    vol_percentile = calc_last_value_percentile(vols, lookback=vol_pct_lb)

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
    prev_close = float(candles[-2]["close"]) if len(candles) >= 2 else close
    momentum = calc_momentum(candles, ema)
    rsi = calc_rsi(closes, period=rsi_period)
    body_pct = calc_candle_body_pct(last)
    atr = calc_atr(candles, period=atr_period)
    vwap = calc_vwap(candles, lookback=vwap_lb)
    adx = calc_adx(candles, period=adx_period)
    macd = calc_macd(closes, fast_period=macd_fast, slow_period=macd_slow, signal_period=macd_signal)
    atr_pct = atr / max(close, 1e-12) * 100.0
    dist_vwap_pct = abs(close - vwap) / max(vwap, 1e-12) * 100.0
    result: dict[str, Any] = {
        "warming_up": False,
        "ema_current": float(ema[-1]),
        "close": close,
        "open": open_,
        "volume_current": vol_c,
        "volume_avg": vol_avg,
        "volume_ratio": vol_ratio,
        "volume_percentile": vol_percentile,
        "above_ema_count": count_above(),
        "below_ema_count": count_below(),
        "is_green": close > open_,
        "is_red": close < open_,
        "quote_volume_usdt": close * vol_c,
        "rsi": rsi,
        "adx": adx,
        "atr": atr,
        "atr_pct": atr_pct,
        "vwap": vwap,
        "distance_from_vwap_pct": dist_vwap_pct,
        "candle_body_pct": body_pct,
        "prev_close": prev_close,
        "distance_from_ema_pct": abs(close - float(ema[-1])) / max(float(ema[-1]), 1e-12) * 100.0,
    }
    result.update(macd)
    result.update(momentum)
    return result


def calc_ote_zone(candles: list[dict[str, Any]], swing_lookback: int = 20) -> dict[str, Any]:
    """
    Последний swing high / swing low на окне lookback.
    OTE (61.8%–78.6% коррекции): лонг — откат от swing high к low; шорт — откат от swing low к high.
    """
    if not candles or swing_lookback < 2:
        return {}
    sl = min(swing_lookback, len(candles))
    highs = [float(c["high"]) for c in candles[-sl:]]
    lows = [float(c["low"]) for c in candles[-sl:]]
    swing_high = max(highs)
    swing_low = min(lows)
    rang = swing_high - swing_low
    current = float(candles[-1]["close"])
    if rang <= 1e-12:
        return {
            "swing_high": swing_high,
            "swing_low": swing_low,
            "ote_long_top": current,
            "ote_long_bottom": current,
            "ote_short_top": current,
            "ote_short_bottom": current,
            "in_ote_long": False,
            "in_ote_short": False,
        }
    ote_long_top = swing_high - rang * 0.618
    ote_long_bottom = swing_high - rang * 0.786
    ote_short_bottom = swing_low + rang * 0.618
    ote_short_top = swing_low + rang * 0.786
    in_ote_long = ote_long_bottom <= current <= ote_long_top
    in_ote_short = ote_short_bottom <= current <= ote_short_top
    return {
        "swing_high": swing_high,
        "swing_low": swing_low,
        "ote_long_top": ote_long_top,
        "ote_long_bottom": ote_long_bottom,
        "ote_short_top": ote_short_top,
        "ote_short_bottom": ote_short_bottom,
        "in_ote_long": in_ote_long,
        "in_ote_short": in_ote_short,
    }


def detect_order_block(
    candles: list[dict[str, Any]],
    ob_lookback: int = 15,
    atr_period: int = 14,
    impulse_mult: float = 1.5,
) -> dict[str, Any]:
    """
    Order Block: последняя свеча противоположного цвета перед импульсом.
    Импульс: тело следующей свечи > ATR * impulse_mult (ATR с того же ряда).
    """
    n = len(candles)
    if n < max(atr_period + 2, ob_lookback + 3, 5):
        return {
            "bullish_ob": None,
            "bearish_ob": None,
            "price_in_bullish_ob": False,
            "price_in_bearish_ob": False,
        }
    atr = calc_atr(candles, atr_period)
    thr = max(atr * impulse_mult, float(candles[-1]["close"]) * 1e-6)

    bullish_ob = None
    bearish_ob = None
    lo = max(0, n - ob_lookback)

    for i in range(n - 3, lo - 1, -1):
        c = candles[i]
        c_next = candles[i + 1]
        o, cl = float(c["open"]), float(c["close"])
        on, cln = float(c_next["open"]), float(c_next["close"])
        body_next = abs(cln - on)
        if cl < o and cln > on and body_next > thr:
            bullish_ob = {"top": o, "bottom": cl, "index": i}
            break

    for i in range(n - 3, lo - 1, -1):
        c = candles[i]
        c_next = candles[i + 1]
        o, cl = float(c["open"]), float(c["close"])
        on, cln = float(c_next["open"]), float(c_next["close"])
        body_next = abs(cln - on)
        if cl > o and cln < on and body_next > thr:
            bearish_ob = {"top": cl, "bottom": o, "index": i}
            break

    current = float(candles[-1]["close"])
    price_in_bullish_ob = bool(
        bullish_ob and bullish_ob["bottom"] <= current <= bullish_ob["top"]
    )
    price_in_bearish_ob = bool(
        bearish_ob and bearish_ob["bottom"] <= current <= bearish_ob["top"]
    )
    return {
        "bullish_ob": bullish_ob,
        "bearish_ob": bearish_ob,
        "price_in_bullish_ob": price_in_bullish_ob,
        "price_in_bearish_ob": price_in_bearish_ob,
    }


def enrich_indicators_htf_ote_ob(
    ind: dict[str, Any],
    candles_htf: list[dict[str, Any]] | None,
    entry_cfg: dict[str, Any],
) -> None:
    """Добавляет в ind поля OTE / OB по закрытым свечам старшего ТФ (например 15m)."""
    swing_lb = int(entry_cfg.get("ote_swing_lookback", 20))
    ob_lb = int(entry_cfg.get("ob_lookback", 15))
    atr_p = int(entry_cfg.get("atr_period", 14))
    impulse_mult = float(entry_cfg.get("ob_impulse_atr_mult", 1.5))
    need = max(swing_lb + 1, atr_p + 3, ob_lb + 4, 10)
    if not candles_htf or len(candles_htf) < need:
        ind["ote_ob_unavailable"] = True
        ind["ote_swing_high"] = None
        ind["ote_swing_low"] = None
        ind["in_ote_long"] = False
        ind["in_ote_short"] = False
        ind["price_in_bullish_ob"] = False
        ind["price_in_bearish_ob"] = False
        ind["bullish_ob"] = None
        ind["bearish_ob"] = None
        return

    ind["ote_ob_unavailable"] = False
    ote = calc_ote_zone(candles_htf, swing_lookback=swing_lb)
    ob = detect_order_block(candles_htf, ob_lookback=ob_lb, atr_period=atr_p, impulse_mult=impulse_mult)

    ind["ote_swing_high"] = ote.get("swing_high")
    ind["ote_swing_low"] = ote.get("swing_low")
    ind["ote_long_top"] = ote.get("ote_long_top")
    ind["ote_long_bottom"] = ote.get("ote_long_bottom")
    ind["ote_short_top"] = ote.get("ote_short_top")
    ind["ote_short_bottom"] = ote.get("ote_short_bottom")
    ind["in_ote_long"] = bool(ote.get("in_ote_long"))
    ind["in_ote_short"] = bool(ote.get("in_ote_short"))

    ind["bullish_ob"] = ob.get("bullish_ob")
    ind["bearish_ob"] = ob.get("bearish_ob")
    ind["price_in_bullish_ob"] = bool(ob.get("price_in_bullish_ob"))
    ind["price_in_bearish_ob"] = bool(ob.get("price_in_bearish_ob"))
