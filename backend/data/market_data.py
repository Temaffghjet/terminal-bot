"""OHLCV + orderbook fetcher"""
from __future__ import annotations

import ccxt


def fetch_ohlcv_pair(
    exchange: ccxt.Exchange,
    symbol_a: str,
    symbol_b: str,
    timeframe: str,
    limit: int,
) -> tuple[list, list]:
    """Fetch OHLCV for both symbols."""
    ohlcv_a = exchange.fetch_ohlcv(symbol_a, timeframe=timeframe, limit=limit)
    ohlcv_b = exchange.fetch_ohlcv(symbol_b, timeframe=timeframe, limit=limit)
    return ohlcv_a, ohlcv_b
