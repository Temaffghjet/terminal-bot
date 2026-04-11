"""Load config.yaml + .env"""
from __future__ import annotations

import os
from pathlib import Path

import yaml
from dotenv import load_dotenv

_BOT_ROOT = Path(__file__).resolve().parent.parent
_CONFIG_PATH = _BOT_ROOT / "config.yaml"


def load_config() -> dict:
    load_dotenv(_BOT_ROOT / ".env")
    with open(_CONFIG_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f)


def get_env() -> dict:
    load_dotenv(_BOT_ROOT / ".env")
    return {
        "BINANCE_API_KEY": os.getenv("BINANCE_API_KEY", ""),
        "BINANCE_API_SECRET": os.getenv("BINANCE_API_SECRET", ""),
        "BYBIT_API_KEY": os.getenv("BYBIT_API_KEY", ""),
        "BYBIT_API_SECRET": os.getenv("BYBIT_API_SECRET", ""),
        "HYPERLIQUID_WALLET_ADDRESS": os.getenv("HYPERLIQUID_WALLET_ADDRESS", ""),
        "HYPERLIQUID_PRIVATE_KEY": os.getenv("HYPERLIQUID_PRIVATE_KEY", ""),
        "WS_PORT": int(os.getenv("WS_PORT", "8765")),
    }
