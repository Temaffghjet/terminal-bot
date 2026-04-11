"""Momentum scalping: EMA/RSI/объём, одна нога, TP/SL/трейлинг."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd


def rsi_series(close: pd.Series, period: int = 14) -> pd.Series:
    d = close.diff()
    up = d.clip(lower=0.0)
    down = (-d).clip(lower=0.0)
    ma_u = up.rolling(period, min_periods=period).mean()
    ma_d = down.rolling(period, min_periods=period).mean()
    rs = ma_u / ma_d.replace(0, np.nan)
    return 100.0 - (100.0 / (1.0 + rs))


def build_ohlcv_df(ohlcv: list) -> pd.DataFrame:
    df = pd.DataFrame(ohlcv, columns=["ts", "o", "h", "l", "c", "v"])
    return df


def enrich_indicators(df: pd.DataFrame, sc: dict) -> pd.DataFrame:
    out = df.copy()
    ef = int(sc.get("ema_fast", 10))
    es = int(sc.get("ema_slow", 20))
    vl = int(sc.get("volume_lookback", 20))
    rp = int(sc.get("rsi_period", 14))
    out["ema_fast"] = out["c"].ewm(span=ef, adjust=False).mean()
    out["ema_slow"] = out["c"].ewm(span=es, adjust=False).mean()
    out["vol_ma"] = out["v"].rolling(vl, min_periods=1).mean()
    out["rsi"] = rsi_series(out["c"], rp)
    swing = int(sc.get("swing_lookback", 14))
    out["past_high"] = out["h"].shift(1).rolling(swing, min_periods=1).max()
    out["past_low"] = out["l"].shift(1).rolling(swing, min_periods=1).min()
    return out


def long_entry_row(df: pd.DataFrame, i: int, sc: dict) -> bool:
    if i < 2 or i >= len(df):
        return False
    row = df.iloc[i]
    if any(pd.isna(x) for x in (row["ema_slow"], row["rsi"], row["vol_ma"], row.get("past_high", np.nan))):
        return False
    rsi_min = float(sc.get("rsi_entry_min", 50))
    rsi_max = float(sc.get("rsi_entry_max", 70))
    vol_mult = float(sc.get("volume_mult", 1.05))
    if row["c"] <= row["ema_slow"]:
        return False
    if not (rsi_min <= row["rsi"] <= rsi_max):
        return False
    if row["v"] <= row["vol_ma"] * vol_mult:
        return False
    ph = row["past_high"]
    if pd.isna(ph) or row["c"] <= ph:
        return False
    if sc.get("require_pullback", False):
        if i < 3:
            return False
        ema_prev = df["ema_slow"].iloc[i - 1]
        low_prev = df["l"].iloc[i - 1]
        if not (low_prev < ema_prev):
            return False
    return True


def short_entry_row(df: pd.DataFrame, i: int, sc: dict) -> bool:
    if i < 2 or i >= len(df):
        return False
    row = df.iloc[i]
    if any(pd.isna(x) for x in (row["ema_slow"], row["rsi"], row["vol_ma"], row.get("past_low", np.nan))):
        return False
    rsi_min_s = float(sc.get("rsi_short_min", 30))
    rsi_max_s = float(sc.get("rsi_short_max", 50))
    vol_mult = float(sc.get("volume_mult", 1.05))
    if row["c"] >= row["ema_slow"]:
        return False
    if not (rsi_min_s <= row["rsi"] <= rsi_max_s):
        return False
    if row["v"] <= row["vol_ma"] * vol_mult:
        return False
    pl = row["past_low"]
    if pd.isna(pl) or row["c"] >= pl:
        return False
    return True


@dataclass
class ExitResult:
    exit_price: float
    reason: str


def _long_exit_intrabar(
    entry: float,
    high: float,
    low: float,
    tp: float,
    sl: float,
) -> ExitResult | None:
    hit_sl = low <= sl
    hit_tp = high >= tp
    if hit_sl and hit_tp:
        return ExitResult(sl, "stop_loss")
    if hit_sl:
        return ExitResult(sl, "stop_loss")
    if hit_tp:
        return ExitResult(tp, "take_profit")
    return None


def _short_exit_intrabar(entry: float, high: float, low: float, tp: float, sl: float) -> ExitResult | None:
    hit_sl = high >= sl
    hit_tp = low <= tp
    if hit_sl and hit_tp:
        return ExitResult(sl, "stop_loss")
    if hit_sl:
        return ExitResult(sl, "stop_loss")
    if hit_tp:
        return ExitResult(tp, "take_profit")
    return None


def update_trailing_long(
    entry: float,
    peak: float,
    high: float,
    sl: float,
    tp_pct: float,
    trail_act_pct: float,
    trailing_on: bool,
) -> tuple[float, float, bool]:
    peak = max(peak, high)
    tp_frac = tp_pct / 100.0
    act_frac = trail_act_pct / 100.0
    if not trailing_on and peak >= entry * (1.0 + act_frac):
        trailing_on = True
    if trailing_on:
        trail_sl = peak * (1.0 - tp_frac)
        sl = max(sl, trail_sl)
    return peak, sl, trailing_on


def update_trailing_short(
    entry: float,
    trough: float,
    low: float,
    sl: float,
    tp_pct: float,
    trail_act_pct: float,
    trailing_on: bool,
) -> tuple[float, float, bool]:
    trough = min(trough, low)
    tp_frac = tp_pct / 100.0
    act_frac = trail_act_pct / 100.0
    if not trailing_on and trough <= entry * (1.0 - act_frac):
        trailing_on = True
    if trailing_on:
        trail_sl = trough * (1.0 + tp_frac)
        sl = min(sl, trail_sl)
    return trough, sl, trailing_on


def position_notional_usdt(deposit: float, sc: dict) -> float:
    pct = float(sc.get("position_size_pct", 20)) / 100.0
    raw = deposit * pct
    lo = float(sc.get("min_position_usdt", 5))
    hi = float(sc.get("max_position_usdt", 10))
    return float(max(lo, min(hi, raw)))
