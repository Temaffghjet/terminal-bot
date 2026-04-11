"""Spread calculation, z-score, cointegration"""
from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd
from statsmodels.regression.linear_model import OLS
from statsmodels.tsa.stattools import coint


def calculate_spread(prices_a: pd.Series, prices_b: pd.Series, hedge_ratio: float) -> pd.Series:
    spread = np.log(prices_a) - hedge_ratio * np.log(prices_b)
    return pd.Series(spread, index=prices_a.index)


def calculate_zscore(spread: pd.Series, window: int) -> float:
    if len(spread) < window:
        return float("nan")
    roll = spread.iloc[-window:]
    mu = roll.mean()
    sigma = roll.std()
    if sigma == 0 or math.isnan(sigma):
        return float("nan")
    current = spread.iloc[-1]
    z = (current - mu) / sigma
    return float(z)


def calculate_hurst(series: pd.Series) -> float:
    """Hurst exponent via R/S analysis. H < 0.5 = mean-reverting."""
    vals = series.dropna().values.astype(float)
    n = len(vals)
    if n < 30:
        return 0.5
    max_k = min(n // 2, 100)
    if max_k < 4:
        return 0.5
    rs_vals: list[tuple[float, float]] = []
    for k in range(4, max_k + 1):
        n_segments = n // k
        if n_segments < 2:
            continue
        rs_list: list[float] = []
        for seg in range(n_segments):
            sub = vals[seg * k : (seg + 1) * k]
            mean_s = np.mean(sub)
            dev = sub - mean_s
            cum = np.cumsum(dev)
            r = np.max(cum) - np.min(cum)
            s = np.std(sub, ddof=1)
            if s > 1e-12:
                rs_list.append(r / s)
        if rs_list:
            rs_vals.append((math.log(k), math.log(np.mean(rs_list))))
    if len(rs_vals) < 2:
        return 0.5
    x = np.array([a[0] for a in rs_vals])
    y = np.array([a[1] for a in rs_vals])
    slope, _ = np.polyfit(x, y, 1)
    h = float(np.clip(slope, 0.0, 1.0))
    return h


def check_cointegration(prices_a: pd.Series, prices_b: pd.Series) -> dict[str, Any]:
    la = np.log(prices_a.values.astype(float))
    lb = np.log(prices_b.values.astype(float))
    ols = OLS(la, lb).fit()
    hedge_ratio_ols = float(ols.params[0])
    _, pvalue, _ = coint(la, lb)
    cointegrated = bool(pvalue < 0.05)
    return {
        "cointegrated": cointegrated,
        "p_value": float(pvalue),
        "hedge_ratio": hedge_ratio_ols,
    }


def get_all_metrics(
    prices_a: pd.Series,
    prices_b: pd.Series,
    config: dict,
) -> dict[str, Any]:
    strat = config.get("strategy") or {}
    window = int(strat.get("lookback_periods", 60))

    ci = check_cointegration(prices_a, prices_b)
    hedge_ratio = ci["hedge_ratio"]
    spread = calculate_spread(prices_a, prices_b, hedge_ratio)
    zscore = calculate_zscore(spread, window)
    hurst = calculate_hurst(spread)
    spread_tail = spread.iloc[-min(100, len(spread)) :].tolist()
    return {
        "zscore": zscore,
        "spread": float(spread.iloc[-1]) if len(spread) else float("nan"),
        "hurst": hurst,
        "cointegrated": ci["cointegrated"],
        "p_value": ci["p_value"],
        "hedge_ratio": hedge_ratio,
        "spread_history": [float(x) for x in spread_tail],
    }
