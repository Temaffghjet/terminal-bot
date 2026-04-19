"""Load config.yaml + .env"""
from __future__ import annotations

import logging
import os
import re
from pathlib import Path

import yaml
from dotenv import load_dotenv

_BOT_ROOT = Path(__file__).resolve().parent.parent
_CONFIG_PATH = _BOT_ROOT / "config.yaml"


def _strip_secrets(s: str | None) -> str:
    if not s:
        return ""
    t = s.strip().strip("'\"")
    t = t.replace("\ufeff", "")
    t = t.replace("\r", "").split("\n", 1)[0].strip()
    return t


def normalize_hl_address(addr: str) -> str:
    """0x + 40 hex, без мусора из .env (иначе 422 / deserialization)."""
    t = _strip_secrets(addr)
    if t.lower().startswith("0x"):
        body = t[2:]
    else:
        body = t
    if not re.fullmatch(r"[0-9a-fA-F]{40}", body):
        return ""
    return "0x" + body.lower()


def normalize_hl_private_key(key: str) -> str:
    """
    0x + 64 hex. Иначе ссылки на 'Non-base16 digit' в ccxt (подпись L1).
    """
    t = _strip_secrets(key)
    if t.lower().startswith("0x"):
        body = t[2:]
    else:
        body = t
    if not re.fullmatch(r"[0-9a-fA-F]{64}", body):
        return ""
    return "0x" + body.lower()


def load_config() -> dict:
    load_dotenv(_BOT_ROOT / ".env")
    with open(_CONFIG_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def get_env() -> dict:
    _log = logging.getLogger(__name__)
    load_dotenv(_BOT_ROOT / ".env")
    raw_addr = os.getenv("HYPERLIQUID_WALLET_ADDRESS", "")
    raw_key = os.getenv("HYPERLIQUID_PRIVATE_KEY", "")
    addr = normalize_hl_address(raw_addr)
    if raw_addr.strip() and not addr:
        _log.warning(
            "HYPERLIQUID_WALLET_ADDRESS не похож на 0x + 40 hex — проверьте .env (без пробелов/кавычек)."
        )
    key = normalize_hl_private_key(raw_key)
    if raw_key.strip() and not key:
        _log.warning(
            "HYPERLIQUID_PRIVATE_KEY не похож на 0x + 64 hex — set_leverage/подпись будут падать."
        )
    return {
        "BINANCE_API_KEY": os.getenv("BINANCE_API_KEY", ""),
        "BINANCE_API_SECRET": os.getenv("BINANCE_API_SECRET", ""),
        "BYBIT_API_KEY": os.getenv("BYBIT_API_KEY", ""),
        "BYBIT_API_SECRET": os.getenv("BYBIT_API_SECRET", ""),
        "HYPERLIQUID_WALLET_ADDRESS": addr,
        "HYPERLIQUID_PRIVATE_KEY": key,
        "WS_PORT": int(os.getenv("WS_PORT", "8765")),
    }
