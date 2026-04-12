"""Place, cancel, track orders"""
from __future__ import annotations

import asyncio
from typing import Any

import ccxt


class OrderManager:
    def __init__(self, exchange: ccxt.Exchange, config: dict) -> None:
        self._ex = exchange
        self._config = config
        self._dry = bool((config.get("bot") or {}).get("dry_run", True))
        rk = config.get("risk") or {}
        self._leverage = int(rk.get("leverage", 5))

    async def set_leverage(self, symbol: str, leverage: int) -> None:
        await asyncio.to_thread(self._ex.set_leverage, leverage, symbol)

    def _qty_b_from_a(
        self, qty_a: float, price_a: float, price_b: float, hedge_ratio: float
    ) -> float:
        return qty_a * hedge_ratio / (price_b / price_a)

    async def open_pair_trade(
        self, pair_config: dict, signal: dict, position_size_usdt: float
    ) -> dict[str, Any]:
        sym_a = pair_config["symbol_a"]
        sym_b = pair_config["symbol_b"]
        hedge_ratio = float(pair_config.get("hedge_ratio", 1.0))
        action = signal["action"]

        ticker_a = await asyncio.to_thread(self._ex.fetch_ticker, sym_a)
        ticker_b = await asyncio.to_thread(self._ex.fetch_ticker, sym_b)
        price_a = float(ticker_a["last"] or ticker_a["close"] or 0)
        price_b = float(ticker_b["last"] or ticker_b["close"] or 0)

        qty_a = position_size_usdt / price_a if price_a else 0.0
        qty_b = self._qty_b_from_a(qty_a, price_a, price_b, hedge_ratio)

        qty_a = float(self._ex.amount_to_precision(sym_a, qty_a))
        qty_b = float(self._ex.amount_to_precision(sym_b, qty_b))

        if action == "OPEN_SHORT_A_LONG_B":
            side_a, side_b = "sell", "buy"
        elif action == "OPEN_LONG_A_SHORT_B":
            side_a, side_b = "buy", "sell"
        else:
            return {"error": "invalid open signal", "leg_a": None, "leg_b": None}

        if self._dry:
            return {
                "dry_run": True,
                "leg_a": {"symbol": sym_a, "side": side_a, "amount": qty_a, "price": price_a},
                "leg_b": {"symbol": sym_b, "side": side_b, "amount": qty_b, "price": price_b},
            }

        async def place(sym: str, side: str, amt: float):
            return await asyncio.to_thread(
                self._ex.create_market_order, sym, side, amt
            )

        oa, ob = await asyncio.gather(
            place(sym_a, side_a, qty_a),
            place(sym_b, side_b, qty_b),
            return_exceptions=True,
        )
        err = None
        if isinstance(oa, Exception) or isinstance(ob, Exception):
            err = f"leg failures: {oa!r} / {ob!r}"
        return {
            "error": err,
            "leg_a": oa if not isinstance(oa, Exception) else str(oa),
            "leg_b": ob if not isinstance(ob, Exception) else str(ob),
            "dry_run": False,
        }

    async def close_pair_trade(self, position: Any, reason: str) -> dict[str, Any]:
        leg_a = position.leg_a
        leg_b = position.leg_b
        sym_a, sym_b = leg_a.symbol, leg_b.symbol

        close_side_a = "sell" if leg_a.side == "LONG" else "buy"
        close_side_b = "sell" if leg_b.side == "LONG" else "buy"

        if self._dry:
            ticker_a = await asyncio.to_thread(self._ex.fetch_ticker, sym_a)
            ticker_b = await asyncio.to_thread(self._ex.fetch_ticker, sym_b)
            pa = float(ticker_a["last"] or ticker_a["close"] or 0)
            pb = float(ticker_b["last"] or ticker_b["close"] or 0)
            return {
                "reason": reason,
                "dry_run": True,
                "exit_price_a": pa,
                "exit_price_b": pb,
            }

        async def place(sym: str, side: str, amt: float):
            return await asyncio.to_thread(
                self._ex.create_market_order, sym, side, amt
            )

        oa, ob = await asyncio.gather(
            place(sym_a, close_side_a, leg_a.size),
            place(sym_b, close_side_b, leg_b.size),
            return_exceptions=True,
        )
        err = None
        if isinstance(oa, Exception) or isinstance(ob, Exception):
            err = f"naked leg risk: {oa!r} / {ob!r}"
        return {
            "reason": reason,
            "error": err,
            "leg_a": oa if not isinstance(oa, Exception) else str(oa),
            "leg_b": ob if not isinstance(ob, Exception) else str(ob),
            "dry_run": False,
        }

    async def open_scalp_market(
        self,
        symbol: str,
        side: str,
        notional_usdt: float,
        dry_run_override: bool | None = None,
    ) -> dict[str, Any]:
        """Одна нога: side = 'buy' (LONG) или 'sell' (SHORT), размер по USDT."""
        dry = self._dry if dry_run_override is None else bool(dry_run_override)
        ticker = await asyncio.to_thread(self._ex.fetch_ticker, symbol)
        price = float(ticker["last"] or ticker["close"] or 0)
        amt = notional_usdt / price if price else 0.0
        amt = float(self._ex.amount_to_precision(symbol, amt))
        if dry:
            return {
                "dry_run": True,
                "symbol": symbol,
                "side": side,
                "amount": amt,
                "price": price,
            }
        o = await asyncio.to_thread(self._ex.create_market_order, symbol, side, amt)
        return {"dry_run": False, "symbol": symbol, "side": side, "order": o}

    async def open_breakout_market(
        self,
        symbol: str,
        side: str,
        notional_usdt: float,
        prefer_price: float | None = None,
        dry_run_override: bool | None = None,
    ) -> dict[str, Any]:
        """Вход в breakout: рыночный ордер (dry_run — имитация у prefer_price или last)."""
        dry = self._dry if dry_run_override is None else bool(dry_run_override)
        ticker = await asyncio.to_thread(self._ex.fetch_ticker, symbol)
        price = float(prefer_price or ticker["last"] or ticker["close"] or 0)
        if price <= 0:
            return {"error": "no price", "amount": 0.0, "price": 0.0}
        amt = notional_usdt / price
        amt = float(self._ex.amount_to_precision(symbol, amt))
        if dry:
            return {"dry_run": True, "symbol": symbol, "side": side, "amount": amt, "price": price}
        o = await asyncio.to_thread(self._ex.create_market_order, symbol, side, amt)
        return {"dry_run": False, "order": o, "symbol": symbol, "side": side, "amount": amt, "price": price}

    async def close_breakout_market(self, symbol: str, side_was_long: bool, amount: float) -> dict[str, Any]:
        return await self.close_scalp_market(symbol, side_was_long, amount)

    async def close_scalp_market(
        self,
        symbol: str,
        side_was_long: bool,
        amount: float,
        dry_run_override: bool | None = None,
    ) -> dict[str, Any]:
        close_side = "sell" if side_was_long else "buy"
        amount = float(self._ex.amount_to_precision(symbol, amount))
        dry = self._dry if dry_run_override is None else bool(dry_run_override)
        if dry:
            ticker = await asyncio.to_thread(self._ex.fetch_ticker, symbol)
            px = float(ticker["last"] or ticker["close"] or 0)
            return {"dry_run": True, "exit_price": px, "side": close_side, "amount": amount}
        o = await asyncio.to_thread(self._ex.create_market_order, symbol, close_side, amount)
        exit_px = float(o.get("average") or o.get("price") or 0) if isinstance(o, dict) else 0.0
        if exit_px <= 0:
            ticker = await asyncio.to_thread(self._ex.fetch_ticker, symbol)
            exit_px = float(ticker["last"] or ticker["close"] or 0)
        return {"dry_run": False, "order": o, "exit_price": exit_px}

    async def open_breakout_limit(
        self,
        symbol: str,
        side: str,
        position_size_usdt: float,
        limit_price: float,
        dry_run_override: bool | None = None,
    ) -> dict[str, Any]:
        """
        Лимитный вход GTC (§13.3). dry_run: мгновенное исполнение по limit_price.
        position_size_usdt — номинал позиции в USDT (как в open_breakout_market).
        """
        dry = self._dry if dry_run_override is None else bool(dry_run_override)
        if limit_price <= 0:
            return {"error": "bad limit price", "pending": False}
        amt = position_size_usdt / limit_price
        amt = float(self._ex.amount_to_precision(symbol, amt))
        lp = float(self._ex.price_to_precision(symbol, limit_price))
        if dry:
            return {
                "dry_run": True,
                "pending": False,
                "filled": True,
                "price": lp,
                "amount": amt,
                "order_id": None,
            }
        o = await asyncio.to_thread(
            self._ex.create_order,
            symbol,
            "limit",
            side,
            amt,
            lp,
            {"timeInForce": "GTC"},
        )
        oid = o.get("id") if isinstance(o, dict) else None
        return {
            "dry_run": False,
            "pending": True,
            "filled": False,
            "price": lp,
            "amount": amt,
            "order_id": str(oid) if oid is not None else "",
            "order": o,
        }

    async def poll_breakout_limit(
        self, symbol: str, order_id: str | None, dry_run_override: bool | None = None
    ) -> dict[str, Any]:
        """Статус лимитного breakout-ордера: исполнен / отменён / ждём."""
        dry = self._dry if dry_run_override is None else bool(dry_run_override)
        if dry or not order_id:
            return {"done": False, "cancelled": False, "reason": "dry_or_no_id"}
        o = await asyncio.to_thread(self._ex.fetch_order, order_id, symbol)
        if not isinstance(o, dict):
            return {"done": False, "cancelled": False, "reason": "bad_response"}
        status = str(o.get("status") or "").lower()
        filled = float(o.get("filled") or 0)
        remaining = float(o.get("remaining") or 0)
        avg = float(o.get("average") or 0) or float(o.get("price") or 0)
        if filled > 0 and remaining <= 1e-12:
            return {
                "done": True,
                "filled": True,
                "avg": avg,
                "filled_qty": filled,
                "cancelled": False,
                "raw": o,
            }
        if status in ("canceled", "cancelled", "expired", "rejected", "failed"):
            return {
                "done": filled > 0,
                "filled": filled > 0,
                "avg": avg,
                "filled_qty": filled,
                "cancelled": True,
                "partial_before_cancel": filled > 0,
                "raw": o,
            }
        return {"done": False, "cancelled": False, "filled": False, "raw": o}

    async def check_pending_breakout_orders(
        self,
        pending_orders: list[dict[str, Any]],
        current_bar_ts_ms: int,
        tf_ms: int,
        dry_run_override: bool | None = None,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        """
        §13.3: обход списка pending — исполненные отдельно, неисполненные после 2 свечей отменить.
        pending_orders: {symbol, order_id, placed_bar_ts, ...}
        """
        filled_out: list[dict[str, Any]] = []
        still_pending: list[dict[str, Any]] = []
        for po in pending_orders:
            sym = str(po.get("symbol") or "")
            oid = po.get("order_id")
            placed = int(po.get("placed_bar_ts") or 0)
            poll = await self.poll_breakout_limit(sym, str(oid) if oid else None, dry_run_override)
            if poll.get("done") and poll.get("filled"):
                filled_out.append({**po, **poll})
                continue
            if (
                tf_ms > 0
                and placed
                and current_bar_ts_ms - placed >= 2 * tf_ms
            ):
                await self.cancel_breakout_order(sym, str(oid) if oid else None, dry_run_override)
                continue
            still_pending.append(po)
        return filled_out, still_pending

    async def cancel_breakout_order(
        self, symbol: str, order_id: str | None, dry_run_override: bool | None = None
    ) -> None:
        dry = self._dry if dry_run_override is None else bool(dry_run_override)
        if dry or not order_id:
            return
        await asyncio.to_thread(self._ex.cancel_order, order_id, symbol)
