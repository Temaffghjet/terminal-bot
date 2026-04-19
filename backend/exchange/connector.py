"""ccxt unified connector (Hyperliquid)"""
from __future__ import annotations

import ccxt


def create_exchange(config: dict, env: dict) -> ccxt.Exchange:
    ex_name = (config.get("exchange") or {}).get("name", "hyperliquid")
    testnet = bool((config.get("exchange") or {}).get("testnet", False))

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
        # ~20 req/s max на /info; поднимаем паузу между вызовами, чтобы не ловить 429
        exchange.enableRateLimit = True
        exchange.rateLimit = 150
        if testnet:
            exchange.set_sandbox_mode(True)
    else:
        raise ValueError(f"Unsupported exchange: {ex_name}")

    exchange.timeout = 60000
    return exchange


def create_exchange_for_strategy(exchange_name: str, testnet: bool, env: dict) -> ccxt.Exchange:
    return create_exchange({"exchange": {"name": exchange_name, "testnet": testnet}}, env)
