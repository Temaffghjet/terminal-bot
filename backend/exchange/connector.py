"""ccxt unified connector (Binance / Bybit / Hyperliquid)"""
from __future__ import annotations

import ccxt


def create_exchange(config: dict, env: dict) -> ccxt.Exchange:
    ex_name = (config.get("exchange") or {}).get("name", "binance")
    testnet = bool((config.get("exchange") or {}).get("testnet", True))

    if ex_name == "binance":
        exchange = ccxt.binance(
            {
                "apiKey": env.get("BINANCE_API_KEY", ""),
                "secret": env.get("BINANCE_API_SECRET", ""),
                "options": {"defaultType": "future"},
            }
        )
        if testnet:
            exchange.set_sandbox_mode(True)
    elif ex_name == "bybit":
        exchange = ccxt.bybit(
            {
                "apiKey": env.get("BYBIT_API_KEY", ""),
                "secret": env.get("BYBIT_API_SECRET", ""),
                "options": {"defaultType": "swap"},
            }
        )
        if testnet:
            exchange.set_sandbox_mode(True)
    elif ex_name == "hyperliquid":
        exchange = ccxt.hyperliquid(
            {
                "walletAddress": env.get("HYPERLIQUID_WALLET_ADDRESS", ""),
                "privateKey": env.get("HYPERLIQUID_PRIVATE_KEY", ""),
                "options": {"defaultType": "swap"},
            }
        )
        if testnet:
            exchange.set_sandbox_mode(True)
    else:
        raise ValueError(f"Unsupported exchange: {ex_name}")

    exchange.timeout = 60000
    return exchange


def create_exchange_for_strategy(exchange_name: str, testnet: bool, env: dict) -> ccxt.Exchange:
    """Отдельное подключение (breakout / ema_scalper на другой бирже)."""
    return create_exchange({"exchange": {"name": exchange_name, "testnet": testnet}}, env)


def create_public_data_exchange(config: dict) -> ccxt.Exchange:
    """
    Только публичные рынки (OHLCV) без testnet — mainnet стабильнее, чем testnet.binance.vision.
    Используется в бэктесте по датам.
    """
    ex_name = (config.get("exchange") or {}).get("name", "binance")
    if ex_name == "binance":
        ex = ccxt.binance({"enableRateLimit": True, "options": {"defaultType": "future"}})
    elif ex_name == "bybit":
        ex = ccxt.bybit({"enableRateLimit": True, "options": {"defaultType": "swap"}})
    elif ex_name == "hyperliquid":
        ex = ccxt.hyperliquid({"enableRateLimit": True, "options": {"defaultType": "swap"}})
    else:
        raise ValueError(f"Unsupported exchange: {ex_name}")
    ex.set_sandbox_mode(False)
    ex.timeout = 60000
    return ex


def create_exchange_for_backtest(config: dict, env: dict) -> ccxt.Exchange:
    """
    Историческая симуляция: всегда mainnet для свечей.
    Hyperliquid — через create_exchange (кошелёк из .env); Binance/Bybit — публичный API без ключей.
    """
    name = (config.get("exchange") or {}).get("name", "binance")
    if name == "hyperliquid":
        ex = create_exchange(config, env)
        ex.set_sandbox_mode(False)
        return ex
    return create_public_data_exchange(config)


def verify_fetch_one_candle(exchange: ccxt.Exchange, symbol: str, timeframe: str) -> list:
    """Fetch a single OHLCV candle (Step 1 verification)."""
    ohlcv = exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=1)
    return ohlcv


def _fetch_ohlcv_range_hyperliquid(
    exchange: ccxt.Exchange,
    symbol: str,
    timeframe: str,
    since_ms: int,
    until_ms: int,
    batch_limit: int,
) -> list:
    """
    Hyperliquid требует endTime: иначе ccxt подставляет «сейчас» и при limit отдаёт хвост диапазона.
    Пагинация вперёд с фиксированным params['until'] = конец окна бэктеста.
    """
    tf_ms = int(exchange.parse_timeframe(timeframe) * 1000)
    out: list = []
    seen: set[int] = set()
    cursor = since_ms
    while cursor <= until_ms:
        batch = exchange.fetch_ohlcv(
            symbol,
            timeframe=timeframe,
            since=cursor,
            limit=batch_limit,
            params={"until": until_ms},
        )
        if not batch:
            break
        for row in batch:
            ts = int(row[0])
            if ts < since_ms or ts > until_ms:
                continue
            if ts not in seen:
                seen.add(ts)
                out.append(row)
        last_ts = int(batch[-1][0])
        if last_ts >= until_ms - tf_ms or len(batch) < batch_limit:
            break
        nxt = last_ts + tf_ms
        if nxt <= cursor:
            break
        cursor = nxt
    out.sort(key=lambda x: x[0])
    return out


def _fetch_ohlcv_range_default(
    exchange: ccxt.Exchange,
    symbol: str,
    timeframe: str,
    since_ms: int,
    until_ms: int,
    batch_limit: int,
) -> list:
    out: list = []
    seen: set[int] = set()
    cursor = since_ms
    while cursor <= until_ms:
        batch = exchange.fetch_ohlcv(symbol, timeframe=timeframe, since=cursor, limit=batch_limit)
        if not batch:
            break
        for row in batch:
            ts = int(row[0])
            if ts < since_ms or ts > until_ms:
                continue
            if ts not in seen:
                seen.add(ts)
                out.append(row)
        last_ts = int(batch[-1][0])
        if last_ts >= until_ms or len(batch) < batch_limit:
            break
        cursor = last_ts + 1
    out.sort(key=lambda x: x[0])
    return out


def fetch_ohlcv_range_historical(
    exchange: ccxt.Exchange,
    symbol: str,
    timeframe: str,
    since_ms: int,
    until_ms: int,
    batch_limit: int = 1000,
) -> list:
    """Исторические свечи [since_ms, until_ms] для бэктеста (HL — с params.until)."""
    if exchange.id == "hyperliquid":
        return _fetch_ohlcv_range_hyperliquid(
            exchange, symbol, timeframe, since_ms, until_ms, batch_limit
        )
    return _fetch_ohlcv_range_default(exchange, symbol, timeframe, since_ms, until_ms, batch_limit)
