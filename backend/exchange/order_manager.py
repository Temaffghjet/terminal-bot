"""Ордера Hyperliquid через ccxt."""
from __future__ import annotations

import logging
from typing import Any

import ccxt

logger = logging.getLogger(__name__)


class OrderManager:
    def __init__(self, exchange: ccxt.Exchange, config: dict):
        self.exchange = exchange
        self.config = config

    def _ema_dry_run(self) -> bool:
        return bool((self.config.get("ema_scalper") or {}).get("dry_run", True))

    def _fetch_positions_params(self) -> dict[str, Any]:
        w = getattr(self.exchange, "walletAddress", None) or ""
        w = str(w).strip()
        if w and w.startswith("0x") and len(w) == 42:
            return {"user": w}
        return {}

    def open_scalp(
        self,
        symbol: str,
        action: str,
        margin_usdt: float,
        leverage: int,
    ) -> dict[str, Any]:
        """Рыночный вход. margin_usdt — маржа (как в спецификации: balance * position_size_pct / 100)."""
        self.exchange.load_markets()
        side = "buy" if action == "OPEN_LONG" else "sell"
        if not self._ema_dry_run():
            try:
                self.exchange.set_leverage(leverage, symbol)
            except Exception as e:
                logger.warning("set_leverage %s: %s", symbol, e)

        ticker = self.exchange.fetch_ticker(symbol)
        price = float(ticker.get("last") or ticker.get("close") or 0)
        if price <= 0:
            raise RuntimeError(f"No price for {symbol}")
        notional = margin_usdt * leverage
        amount = notional / price
        market = self.exchange.market(symbol)
        if market.get("precision", {}).get("amount") is not None:
            amount = float(self.exchange.amount_to_precision(symbol, amount))
        amount = max(amount, 0.0)

        order = self.exchange.create_order(symbol, "market", side, amount)
        fill = float(order.get("average") or order.get("price") or price)
        return {"order": order, "fill_price": fill}

    def close_scalp(self, symbol: str, side: str) -> dict[str, Any]:
        close_side = "sell" if side == "LONG" else "buy"
        self.exchange.load_markets()
        pparams = self._fetch_positions_params()
        try:
            positions = self.exchange.fetch_positions([symbol], pparams)
        except Exception as e:
            logger.warning("fetch_positions %s: %s", symbol, e)
            positions = []

        amount = 0.0
        for p in positions:
            if p.get("symbol") != symbol:
                continue
            c = p.get("contracts")
            if c is not None:
                amount = abs(float(c))
            if amount <= 0:
                amount = abs(float(p.get("notional") or 0)) / float(
                    self.exchange.fetch_ticker(symbol).get("last") or 1
                )
            break

        if amount <= 0:
            ticker = self.exchange.fetch_ticker(symbol)
            price = float(ticker.get("last") or 1)
            rk = (self.config.get("ema_scalper") or {}).get("risk") or {}
            margin = float(rk.get("balance_usdt", 500)) * float(rk.get("position_size_pct", 25)) / 100.0
            lev = int(rk.get("leverage", 5))
            amount = (margin * lev) / price

        order = self.exchange.create_order(symbol, "market", close_side, amount)
        return {"order": order}
