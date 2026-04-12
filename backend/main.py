"""Entry point, starts bot loop + WS server"""
from __future__ import annotations

import asyncio
import logging
import signal
import sys
import time
from collections import deque
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.config import get_env, load_config
from backend.data import db as dbmod
from backend.data.market_data import fetch_ohlcv_pair
from backend.exchange.connector import (
    create_exchange,
    create_exchange_for_strategy,
    verify_fetch_one_candle,
)
from backend.exchange.order_manager import OrderManager
from backend.strategy.breakout import (
    BreakoutDetector,
    BreakoutPositionTracker,
    BreakoutSignalEngine,
)
from backend.strategy.ema_scalper import EMAScalpPosition, EMAScalpSignalEngine, get_indicators
from backend.strategy.ema_scalper.indicators import calc_ema
from backend.strategy.micro_signals import MicroSignalEngine
from backend.strategy.position_manager import LegState, PairPosition, PositionManager, ScalpPosition
from backend.strategy.risk import RiskManager
from backend.strategy.signals import SignalEngine
from backend.strategy.spread import get_all_metrics
from backend.ws_server import WsHub, run_ws_server

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")


def pair_id_from(syma: str, symb: str) -> str:
    ba = syma.split("/")[0]
    bb = symb.split("/")[0]
    return f"{ba}-{bb}"


def direction_from_signal(action: str) -> str:
    if action == "OPEN_SHORT_A_LONG_B":
        return "SHORT_A_LONG_B"
    if action == "OPEN_LONG_A_SHORT_B":
        return "LONG_A_SHORT_B"
    return ""


def scalp_id(symbol: str) -> str:
    return f"scalp:{symbol}"


class BotRuntime:
    def __init__(self) -> None:
        self.config: dict = {}
        self.env: dict = {}
        self.exchange = None
        self.conn = None
        self.pm = PositionManager()
        self.risk: RiskManager | None = None
        self.orders: OrderManager | None = None
        self.orders_breakout: OrderManager | None = None
        self.orders_ema: OrderManager | None = None
        self.stat_signals: SignalEngine | None = None
        self.micro_signals: MicroSignalEngine | None = None
        self.hub: WsHub | None = None
        self.bot_status: str = "running"
        self.warming_up: bool = True
        self.zscore_hist: dict[str, deque[float]] = {}
        self.scalp_last_entry_bar_ts: dict[str, int] = {}
        self.mark_prices: dict[str, float] = {}
        self.scalp_signal_by_symbol: dict[str, dict] = {}
        self.ema_hist: dict[str, deque[float]] = {}
        self.ws_metrics: dict = {}
        self.broadcast_lock: asyncio.Lock | None = None
        self.breakout_exchange = None
        self.breakout_tracker: BreakoutPositionTracker | None = None
        self.breakout_engine: BreakoutSignalEngine | None = None
        self.breakout_detector: BreakoutDetector | None = None
        self.breakout_last_signals: dict = {}
        self.ema_scalper_exchange = None
        self.ema_scalper_engine: EMAScalpSignalEngine | None = None
        self.ema_positions: dict[str, EMAScalpPosition] = {}
        self.ema_last_entry_ts: dict[str, int] = {}
        self.ema_last_bar_ts: dict[str, int] = {}
        self.ema_current_bar_ts: dict[str, int] = {}
        self.ema_indicators: dict[str, dict] = {}
        self.ema_chart_history: dict[str, list[dict]] = {}
        self._shutdown = False
        self._shutdown_event: asyncio.Event | None = None
        self.ws_task: asyncio.Task | None = None
        self._bal_fetch_ts: float = 0.0
        self._bal_fetch_data: dict | None = None

    def set_pause(self, paused: bool) -> None:
        if self.risk:
            self.risk.set_pause(paused)
        self.bot_status = "paused" if paused else "running"

    async def emergency_stop_all(self) -> None:
        if not self.orders:
            return
        for sym, pos in list(self.pm.scalp_all().items()):
            await self._close_scalp(sym, pos, "emergency")
        ex_ema = self.ema_scalper_exchange or self.exchange
        for sym, pos in list(self.ema_positions.items()):
            t = await asyncio.to_thread(ex_ema.fetch_ticker, sym) if ex_ema else None
            px = float(t["last"] or t["close"] or pos.entry_price) if t else pos.entry_price
            await self._close_ema_scalp(sym, pos, px, "MANUAL", bar_ts_ms=int(time.time() * 1000))
        if self.breakout_tracker:
            br_dry = bool(
                (self.config.get("breakout") or {}).get(
                    "dry_run", (self.config.get("bot") or {}).get("dry_run", True)
                )
            )
            om_br = self.orders_breakout or self.orders
            for sym in list(self.breakout_tracker.symbols()):
                p = self.breakout_tracker.get_position(sym)
                if not p or not om_br:
                    continue
                if p.status == "PENDING" and p.pending_order_id:
                    try:
                        await om_br.cancel_breakout_order(sym, p.pending_order_id, br_dry)
                    except Exception as e:
                        logger.warning("emergency cancel breakout pending %s: %s", sym, e)
                    self.breakout_tracker.remove(sym)
                    continue
                if p.status == "OPEN":
                    await om_br.close_breakout_market(sym, p.side == "LONG", p.qty)
                    ex = self.breakout_exchange or self.exchange
                    t = await asyncio.to_thread(ex.fetch_ticker, sym) if ex else None
                    px = float(t["last"] or t["close"] or p.entry_price) if t else p.entry_price
                    rec = self.breakout_tracker.close_position(sym, px, "MANUAL")
                    self._log_breakout_scalp_trade(rec, "MANUAL")
        for pid, pos in list(self.pm._positions.items()):
            await self._close_one(pid, pos, "manual")

    async def emergency_close_pair(self, pair_id: str) -> None:
        if pair_id.startswith("scalp:"):
            sym = pair_id.split(":", 1)[1]
            pos = self.pm.scalp_get(sym)
            if pos and self.orders:
                await self._close_scalp(sym, pos, "manual")
            return
        pos = self.pm.get(pair_id)
        if pos and self.orders:
            await self._close_one(pair_id, pos, "manual")

    async def close_ema_manual(self, symbol: str) -> None:
        pos = self.ema_positions.get(symbol)
        if not pos or not (self.orders_ema or self.orders):
            return
        ex = self.ema_scalper_exchange or self.exchange
        t = await asyncio.to_thread(ex.fetch_ticker, symbol) if ex else None
        px = float(t["last"] or t["close"] or pos.entry_price) if t else pos.entry_price
        await self._close_ema_scalp(symbol, pos, px, "MANUAL", bar_ts_ms=None)

    async def close_breakout_manual(self, symbol: str) -> None:
        tr = self.breakout_tracker
        om = self.orders_breakout or self.orders
        if not tr or not om:
            return
        p = tr.get_position(symbol)
        if not p:
            return
        br_dry = bool(
            (self.config.get("breakout") or {}).get(
                "dry_run", (self.config.get("bot") or {}).get("dry_run", True)
            )
        )
        if p.status == "PENDING":
            if p.pending_order_id:
                try:
                    await om.cancel_breakout_order(symbol, p.pending_order_id, br_dry)
                except Exception as e:
                    logger.warning("cancel pending breakout %s: %s", symbol, e)
            tr.remove(symbol)
            return
        if p.status != "OPEN":
            return
        ex = self.breakout_exchange or self.exchange
        t = await asyncio.to_thread(ex.fetch_ticker, symbol) if ex else None
        px = float(t["last"] or t["close"] or p.entry_price) if t else p.entry_price
        await om.close_breakout_market(symbol, p.side == "LONG", p.qty)
        rec = tr.close_position(symbol, px, "MANUAL")
        self._log_breakout_scalp_trade(rec, "MANUAL")

    async def _close_scalp(self, symbol: str, pos: ScalpPosition, reason: str) -> None:
        if not self.orders or not self.conn:
            return
        rk = (self.config.get("risk") or {})
        comm_side = float(rk.get("commission_pct", 0.1)) / 100.0
        res = await self.orders.close_scalp_market(symbol, pos.side == "LONG", pos.size)
        exit_px = float(res.get("exit_price") or self.mark_prices.get(symbol) or pos.entry_price)
        entry = pos.entry_price
        if pos.side == "LONG":
            gross = (exit_px - entry) * pos.size
        else:
            gross = (entry - exit_px) * pos.size
        notional = abs(pos.size * entry)
        fee = notional * comm_side * 2.0
        if self.risk:
            self.risk.add_commission(fee)
        net = gross - fee
        self.pm.add_realized_today(net)
        self.pm.scalp_remove(symbol)
        ts = datetime.now(timezone.utc).isoformat()
        pid = scalp_id(symbol)
        dbmod.insert_trade(
            self.conn,
            {
                "timestamp": ts,
                "pair_id": pid,
                "action": "CLOSE",
                "direction": f"SCALP_{pos.side}",
                "symbol_a": symbol,
                "symbol_b": "",
                "side_a": pos.side,
                "side_b": "",
                "qty_a": pos.size,
                "qty_b": None,
                "entry_price_a": entry,
                "entry_price_b": None,
                "exit_price_a": exit_px,
                "exit_price_b": None,
                "pnl_usdt": net,
                # z-score только для stat-arb; для скальпа смотри entry/exit price в колонке лога
                "zscore_entry": None,
                "zscore_exit": None,
                "close_reason": reason,
                "dry_run": 1 if (self.config.get("bot") or {}).get("dry_run") else 0,
            },
        )
        logger.info(
            "SCALP CLOSE %s %s entry=%.4f exit=%.4f net=%.4f USDT gross=%.4f fee=%.4f reason=%s",
            symbol,
            pos.side,
            entry,
            exit_px,
            net,
            gross,
            fee,
            reason,
        )

    async def _close_ema_scalp(
        self,
        symbol: str,
        pos: EMAScalpPosition,
        exit_px: float,
        reason: str,
        bar_ts_ms: int | None = None,
    ) -> None:
        om = self.orders_ema or self.orders
        if not om or not self.conn:
            return
        es_cfg = self.config.get("ema_scalper") or {}
        dry_e = bool(es_cfg.get("dry_run", (self.config.get("bot") or {}).get("dry_run", True)))
        rk = (self.config.get("risk") or {})
        comm_side = float(rk.get("commission_pct", 0.1)) / 100.0
        amt = pos.position_qty()
        res = await om.close_scalp_market(
            symbol, pos.side == "LONG", amt, dry_run_override=dry_e
        )
        exit_px = float(res.get("exit_price") or exit_px)
        entry = pos.entry_price
        if pos.side == "LONG":
            gross = (exit_px - entry) * amt
        else:
            gross = (entry - exit_px) * amt
        notional_abs = abs(amt * entry)
        fee = notional_abs * comm_side * 2.0
        if self.risk:
            self.risk.add_commission(fee)
        net = gross - fee
        self.pm.add_realized_today(net)
        self.ema_positions.pop(symbol, None)
        ts_close = datetime.now(timezone.utc).isoformat()
        bms = bar_ts_ms if bar_ts_ms is not None else int(time.time() * 1000)
        bars = pos.bars_held(bms)
        pnl_pct_row = (net / max(pos.notional, 1e-12)) * 100.0
        dbmod.insert_scalp_trade(
            self.conn,
            {
                "timestamp_open": pos.timestamp_open_iso or ts_close,
                "timestamp_close": ts_close,
                "symbol": symbol,
                "strategy": "ema_scalper",
                "side": pos.side,
                "entry_price": entry,
                "exit_price": exit_px,
                "tp_price": pos.tp_price,
                "sl_price": pos.sl_price,
                "size_usdt": pos.size_usdt,
                "notional": pos.notional,
                "leverage": pos.leverage,
                "candles_held": bars,
                "pnl_usdt": net,
                "pnl_pct": pnl_pct_row,
                "fee_usdt": fee,
                "close_reason": reason,
                "dry_run": 1 if dry_e else 0,
                "ema_at_entry": pos.ema_at_entry,
                "volume_ratio_at_entry": pos.volume_ratio_at_entry,
                "above_ema_count_at_entry": pos.above_ema_count_at_entry,
            },
        )
        logger.info(
            "EMA_SCALP CLOSE %s %s net=%.4f USDT reason=%s (scalp_trades)",
            symbol,
            pos.side,
            net,
            reason,
        )

    def _log_breakout_scalp_trade(self, rec: dict, reason: str) -> None:
        """Запись закрытия breakout в scalp_trades (не stat-arb trades)."""
        if not self.conn or not rec:
            return
        br = self.config.get("breakout") or {}
        dry_br = bool(br.get("dry_run", (self.config.get("bot") or {}).get("dry_run", True)))
        rk = self.config.get("risk") or {}
        comm_side = float(rk.get("commission_pct", 0.1)) / 100.0
        lev = int((br.get("risk") or {}).get("leverage", 3))
        entry = float(rec.get("entry_price") or 0)
        exit_px = float(rec.get("exit_price") or 0)
        qty = float(rec.get("qty") or 0)
        gross = float(rec.get("pnl_usdt") or 0)
        notional_abs = abs(qty * entry)
        fee = notional_abs * comm_side * 2.0
        net = gross - fee
        if self.risk:
            self.risk.add_commission(fee)
        self.pm.add_realized_today(net)
        ts_close = datetime.now(timezone.utc).isoformat()
        ts_open = str(rec.get("open_time") or ts_close)
        size_usdt = float(rec.get("size_usdt") or 0)
        pnl_pct_row = (net / max(size_usdt * lev, 1e-12)) * 100.0 if lev else 0.0
        dbmod.insert_scalp_trade(
            self.conn,
            {
                "timestamp_open": ts_open,
                "timestamp_close": ts_close,
                "symbol": str(rec.get("symbol") or ""),
                "strategy": "breakout",
                "side": str(rec.get("side") or ""),
                "entry_price": entry,
                "exit_price": exit_px,
                "tp_price": float(rec.get("tp_price") or 0),
                "sl_price": float(rec.get("sl_price") or 0),
                "size_usdt": size_usdt,
                "notional": size_usdt * lev,
                "leverage": lev,
                "candles_held": 0,
                "pnl_usdt": net,
                "pnl_pct": pnl_pct_row,
                "fee_usdt": fee,
                "close_reason": reason,
                "dry_run": 1 if dry_br else 0,
                "ema_at_entry": 0.0,
                "volume_ratio_at_entry": 0.0,
                "above_ema_count_at_entry": 0,
            },
        )

    async def _close_one(self, pair_id: str, pos: PairPosition, reason: str) -> None:
        if not self.orders or not self.conn:
            return
        res = await self.orders.close_pair_trade(pos, reason)
        # PnL simplified for dry_run
        pa = float(res.get("exit_price_a") or pos.leg_a.current_price or pos.leg_a.entry_price)
        pb = float(res.get("exit_price_b") or pos.leg_b.current_price or pos.leg_b.entry_price)
        sign_a = 1.0 if pos.leg_a.side == "LONG" else -1.0
        sign_b = 1.0 if pos.leg_b.side == "LONG" else -1.0
        pnl = (
            sign_a * (pa - pos.leg_a.entry_price) * pos.leg_a.size
            + sign_b * (pb - pos.leg_b.entry_price) * pos.leg_b.size
        )
        self.pm.add_realized_today(pnl)
        self.pm.remove_position(pair_id)
        sym_a = None
        sym_b = None
        for p in self.config.get("pairs") or []:
            if pair_id_from(p["symbol_a"], p["symbol_b"]) == pair_id:
                sym_a, sym_b = p["symbol_a"], p["symbol_b"]
                break
        dbmod.insert_trade(
            self.conn,
            {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "pair_id": pair_id,
                "action": "CLOSE",
                "direction": pos.direction,
                "symbol_a": sym_a or "",
                "symbol_b": sym_b or "",
                "side_a": pos.leg_a.side,
                "side_b": pos.leg_b.side,
                "qty_a": pos.leg_a.size,
                "qty_b": pos.leg_b.size,
                "entry_price_a": pos.leg_a.entry_price,
                "entry_price_b": pos.leg_b.entry_price,
                "exit_price_a": pa,
                "exit_price_b": pb,
                "pnl_usdt": pnl,
                "zscore_entry": pos.zscore_at_entry,
                "zscore_exit": pos.current_zscore,
                "close_reason": reason,
                "dry_run": 1 if (self.config.get("bot") or {}).get("dry_run") else 0,
            },
        )


RT = BotRuntime()


async def scalping_bot_loop() -> None:
    """Micro scalping: EMA + объём, TP/SL/время/EMA-cross, лимит позиций."""
    cfg = RT.config
    sc = cfg.get("scalping") or {}
    bot_cfg = cfg.get("bot") or {}
    if not sc.get("enabled", True):
        logger.warning("scalping.enabled=false — цикл не запущен")
        return
    loop_sec = float(bot_cfg.get("loop_interval_sec", 10))
    tf = sc.get("timeframe", "1m")
    symbols = [p["symbol"] for p in sc.get("pairs", []) if p.get("enabled")]
    deposit = float(sc.get("deposit_usdt", 50))
    risk_pct = float(sc.get("risk_per_trade_pct", 20))
    notional = deposit * risk_pct / 100.0
    max_pos = int(sc.get("max_positions", 2))
    ex_cfg = sc.get("exit") or {}
    tp_pct = float(ex_cfg.get("take_profit_pct", 0.6))
    sl_pct = float(ex_cfg.get("stop_loss_pct", 0.5))
    max_hold = float(ex_cfg.get("max_hold_minutes", 3))
    dry = bool(bot_cfg.get("dry_run", True))
    candle_limit = 30

    def ts_iso() -> str:
        return datetime.now(timezone.utc).isoformat()

    while not RT._shutdown:
        try:
            metrics_scalp: dict = {}
            any_warming = False
            exp = sum(abs(p.size * p.entry_price) for p in RT.pm.scalp_all().values())
            if RT.risk:
                RT.risk.set_open_notional(exp)
    
            for symbol in symbols:
                await asyncio.sleep(0.1)
                try:
                    ohlcv = await asyncio.to_thread(
                        RT.exchange.fetch_ohlcv, symbol, tf, None, candle_limit
                    )
                except Exception as e:
                    logger.warning("OHLCV %s: %s", symbol, e)
                    any_warming = True
                    continue
                if len(ohlcv) < 12:
                    any_warming = True
                    continue
    
                ind = RT.micro_signals.calculate_indicators(ohlcv) if RT.micro_signals else {}
                RT.scalp_signal_by_symbol[symbol] = ind
                if symbol not in RT.ema_hist:
                    RT.ema_hist[symbol] = deque(maxlen=100)
                if ind.get("ema") is not None:
                    RT.ema_hist[symbol].append(float(ind["ema"]))
                ema_hist = list(RT.ema_hist[symbol])
                metrics_scalp[symbol] = {
                    "zscore": float(ind["ema"]) if ind.get("ema") is not None else None,
                    "zscore_history": ema_hist,
                    "spread_history": [0.0] * len(ema_hist),
                    "scalp_mode": True,
                    "has_open_position": RT.pm.scalp_get(symbol) is not None,
                    "indicators": ind,
                }
    
                ticker = await asyncio.to_thread(RT.exchange.fetch_ticker, symbol)
                last = float(ticker["last"] or ticker["close"] or (ohlcv[-1][4] if ohlcv else 0))
                RT.mark_prices[symbol] = last
    
                pos = RT.pm.scalp_get(symbol)
                now = datetime.now(timezone.utc)
                ema_now = float(ind["ema"]) if ind.get("ema") is not None else last
    
                if pos:
                    should, reason = pos.should_exit(
                        last, ema_now, now, tp_pct, sl_pct, int(max_hold)
                    )
                    if should:
                        await RT._close_scalp(symbol, pos, reason)
                    continue
    
                bar_ts = int(ohlcv[-1][0])
                if RT.scalp_last_entry_bar_ts.get(symbol) == bar_ts:
                    continue
    
                sig = (
                    RT.micro_signals.check_entry(symbol, ohlcv, has_position=False)
                    if RT.micro_signals
                    else {"action": "HOLD"}
                )
                if sig.get("action") not in ("OPEN_LONG", "OPEN_SHORT"):
                    continue
                if RT.pm.scalp_count() >= max_pos:
                    continue
                ok, _ = RT.risk.check_can_open(scalp_id(symbol), notional, legs=1) if RT.risk else (True, "")
                if not ok:
                    continue
    
                side_buy = sig["action"] == "OPEN_LONG"
                res = await RT.orders.open_scalp_market(symbol, "buy" if side_buy else "sell", notional)
                entry = float(res.get("price") or float(ohlcv[-1][4]))
                size = notional / entry if entry else 0.0
                side = "LONG" if side_buy else "SHORT"
                if side == "LONG":
                    tp_price = entry * (1.0 + tp_pct / 100.0)
                    sl_price = entry * (1.0 - sl_pct / 100.0)
                else:
                    tp_price = entry * (1.0 - tp_pct / 100.0)
                    sl_price = entry * (1.0 + sl_pct / 100.0)
                ts_open = ts_iso()
                sp = ScalpPosition(
                    symbol=symbol,
                    side=side,
                    size=size,
                    entry_price=entry,
                    entry_time=ts_open,
                    take_profit=tp_price,
                    stop_loss=sl_price,
                    current_price=entry,
                    entry_ts_ms=bar_ts,
                )
                RT.pm.scalp_set(symbol, sp)
                RT.scalp_last_entry_bar_ts[symbol] = bar_ts
                if RT.conn:
                    dbmod.insert_trade(
                        RT.conn,
                        {
                            "timestamp": ts_open,
                            "pair_id": scalp_id(symbol),
                            "action": "OPEN",
                            "direction": f"SCALP_{side}",
                            "symbol_a": symbol,
                            "symbol_b": "",
                            "side_a": side,
                            "side_b": "",
                            "qty_a": size,
                            "qty_b": None,
                            "entry_price_a": entry,
                            "entry_price_b": None,
                            "exit_price_a": None,
                            "exit_price_b": None,
                            "pnl_usdt": None,
                            "zscore_entry": None,
                            "zscore_exit": None,
                            "close_reason": None,
                            "dry_run": 1 if dry else 0,
                        },
                    )
                logger.info(
                    "SCALP OPEN %s %s size=%.6f entry=%.4f notional≈%.2f USDT TP=%.4f SL=%.4f",
                    symbol,
                    side,
                    size,
                    entry,
                    notional,
                    tp_price,
                    sl_price,
                )
    
            RT.warming_up = any_warming
            RT.ws_metrics.update(metrics_scalp)
            await safe_broadcast()
            await asyncio.sleep(loop_sec)

        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("scalping_bot_loop: итерация — продолжаем")
            await asyncio.sleep(loop_sec)


def _quote_balance_from_ccxt(bal: dict) -> dict | None:
    """USDT (Binance/Bybit) или USDC (Hyperliquid и др.) из unified fetch_balance ccxt."""
    if not bal:
        return None
    best: dict | None = None
    best_score = -1.0
    for code in ("USDT", "USDC"):
        u = bal.get(code)
        if not isinstance(u, dict):
            continue
        total = float(u.get("total") or 0)
        free = float(u.get("free") or 0)
        score = max(total, free)
        if score > best_score or best is None:
            best_score = score
            best = {
                "currency": code,
                "free": free,
                "used": float(u.get("used") or 0),
                "total": total,
            }
    if best:
        return best
    tot = bal.get("total")
    if isinstance(tot, dict):
        for code in ("USDT", "USDC"):
            if code in tot:
                t = float(tot[code] or 0)
                return {"currency": code, "free": 0.0, "used": 0.0, "total": t}
    return None


async def build_trading_capital_payload(rt: BotRuntime) -> dict:
    """Бюджеты из config + фактический USDT с биржи (кэш ~30 с)."""
    cfg = rt.config or {}
    rk = cfg.get("risk") or {}
    sc_cfg = cfg.get("scalping") or {}
    br_cfg = cfg.get("breakout") or {}
    es_cfg = cfg.get("ema_scalper") or {}
    es_risk = es_cfg.get("risk") or {}
    out: dict = {
        "config": {
            "scalping_deposit_usdt": float(sc_cfg.get("deposit_usdt", 50)),
            "stat_arb_max_leg_usdt": float(rk.get("max_position_usdt", 500)),
            "stat_arb_max_total_exposure_usdt": float(rk.get("max_total_exposure", 2000)),
            "breakout_balance_usdt": float((br_cfg.get("risk") or {}).get("balance_usdt", 1000)),
            "ema_balance_usdt": float(es_risk.get("balance_usdt", 50)),
            "ema_position_size_pct": float(es_risk.get("position_size_pct", 25)),
            "ema_leverage": int(es_risk.get("leverage", 5)),
        },
        "exchange_usdt": {"main": None, "breakout": None, "ema": None},
        "exchange_errors": {},
    }
    now = time.time()
    if rt._bal_fetch_data is not None and now - rt._bal_fetch_ts < 30.0:
        out["exchange_usdt"] = dict(rt._bal_fetch_data.get("exchange_usdt", {}))
        out["exchange_errors"] = dict(rt._bal_fetch_data.get("exchange_errors", {}))
        return out

    errors: dict[str, str] = {}
    main_u = br_u = ema_u = None

    async def grab(ex: object | None, key: str) -> tuple[str, dict | None, str | None]:
        if ex is None:
            return key, None, None
        try:
            bal = await asyncio.to_thread(ex.fetch_balance)  # type: ignore[attr-defined]
            u = _quote_balance_from_ccxt(bal) if isinstance(bal, dict) else None
            return key, u, None
        except Exception as e:
            return key, None, str(e)

    r1, r2, r3 = await asyncio.gather(
        grab(rt.exchange, "main"),
        grab(rt.breakout_exchange, "breakout"),
        grab(rt.ema_scalper_exchange, "ema"),
    )
    for key, u, err in (r1, r2, r3):
        if key == "main":
            main_u = u
        elif key == "breakout":
            br_u = u
        else:
            ema_u = u
        if err:
            errors[key] = err

    if rt.breakout_exchange and rt.exchange and id(rt.breakout_exchange) == id(rt.exchange):
        br_u = main_u
    if rt.ema_scalper_exchange and rt.exchange and id(rt.ema_scalper_exchange) == id(rt.exchange):
        ema_u = main_u
    elif (
        rt.ema_scalper_exchange
        and rt.breakout_exchange
        and id(rt.ema_scalper_exchange) == id(rt.breakout_exchange)
    ):
        ema_u = br_u

    out["exchange_usdt"] = {"main": main_u, "breakout": br_u, "ema": ema_u}
    out["exchange_errors"] = errors
    rt._bal_fetch_ts = now
    rt._bal_fetch_data = {
        "exchange_usdt": out["exchange_usdt"],
        "exchange_errors": errors,
    }
    return out


async def safe_broadcast() -> None:
    """Ошибки трансляции не завершают торговые циклы."""
    if not RT.hub:
        return
    if RT.broadcast_lock is None:
        RT.broadcast_lock = asyncio.Lock()
    try:
        async with RT.broadcast_lock:
            payload = await build_state_payload(RT)
            await RT.hub.broadcast_json(payload)
    except asyncio.CancelledError:
        raise
    except Exception:
        logger.exception("safe_broadcast: пропуск итерации")


async def build_state_payload(rt: BotRuntime, metrics_by_pair: dict | None = None) -> dict:
    st = rt.pm.get_state()
    mode = (rt.config.get("strategy") or {}).get("mode", "pairs")
    merged_metrics = metrics_by_pair if metrics_by_pair is not None else rt.ws_metrics
    positions_out = list(st["positions"])
    unreal = st["total_pnl_unrealized"]
    if mode == "scalping":
        positions_out = []
        unreal = 0.0
        for sym, p in rt.pm.scalp_all().items():
            px = float(rt.mark_prices.get(sym) or p.entry_price)
            sign = 1.0 if p.side == "LONG" else -1.0
            ur = sign * (px - p.entry_price) * p.size
            unreal += ur
            ema_v = float((rt.scalp_signal_by_symbol.get(sym) or {}).get("ema") or 0.0)
            try:
                et = datetime.fromisoformat(p.entry_time.replace("Z", "+00:00"))
                if et.tzinfo is None:
                    et = et.replace(tzinfo=timezone.utc)
                mins_in = (datetime.now(timezone.utc) - et).total_seconds() / 60.0
            except Exception:
                mins_in = 0.0
            positions_out.append(
                {
                    "pair_id": scalp_id(sym),
                    "is_scalp": True,
                    "minutes_in_trade": round(mins_in, 2),
                    "leg_a": {
                        "symbol": sym,
                        "side": p.side,
                        "size": p.size,
                        "entry_price": p.entry_price,
                        "current_price": px,
                        "pnl_usdt": ur,
                    },
                    "leg_b": {
                        "symbol": "",
                        "side": "",
                        "size": 0.0,
                        "entry_price": 0.0,
                        "current_price": 0.0,
                        "pnl_usdt": 0.0,
                    },
                    "total_pnl_usdt": ur,
                    "open_time": p.entry_time,
                    "zscore_at_entry": 0.0,
                    "current_zscore": ema_v,
                }
            )
    pnl = {
        "total_today": st["total_pnl_today"],
        "unrealized": unreal,
        "realized_today": st["total_pnl_today"],
    }
    ex = (rt.config.get("exchange") or {}) if rt.config else {}
    bot = (rt.config.get("bot") or {}) if rt.config else {}
    sc_cfg = (rt.config.get("scalping") or {}) if rt.config else {}
    deposit = float(sc_cfg.get("deposit_usdt", 50))
    rk = (rt.config.get("risk") or {}) if rt.config else {}
    daily_pct = RT.risk.daily_pnl_pct_vs_deposit() if RT.risk else 0.0
    comm_today = RT.risk.commission_today_usdt if RT.risk else 0.0
    br_cfg = (rt.config.get("breakout") or {}) if rt.config else {}
    br_dep = float((br_cfg.get("risk") or {}).get("balance_usdt", 1000))
    es_cfg_rt = (rt.config.get("ema_scalper") or {}) if rt.config else {}
    es_dep = float((es_cfg_rt.get("risk") or {}).get("balance_usdt", 50))
    breakout_equity: list[float] = []
    ema_equity: list[float] = []
    br_st: dict = {}
    ema_st: dict = {}
    recent_ema_trades: list = []
    if rt.conn:
        breakout_equity = dbmod.get_equity_history(rt.conn, "breakout", br_dep, 100)
        ema_equity = dbmod.get_equity_history(rt.conn, "ema_scalper", es_dep, 100)
        br_st = dbmod.fetch_scalp_strategy_stats(rt.conn, "breakout")
        ema_st = dbmod.fetch_scalp_strategy_stats(rt.conn, "ema_scalper")
        recent_ema_trades = dbmod.get_recent_scalp_trades(rt.conn, 50, strategy="ema_scalper")
    today_stats = (
        dbmod.fetch_scalp_today_stats(rt.conn)
        if rt.conn and mode == "scalping"
        else {}
    )
    scalping_metrics = {
        "activePositions": positions_out if mode == "scalping" else [],
        "todayStats": {
            "trades": today_stats.get("trades", 0),
            "wins": today_stats.get("wins", 0),
            "losses": today_stats.get("losses", 0),
            "totalPnL": today_stats.get("totalPnL", 0),
            "commissionPaid": comm_today,
            "avgTradeTime": 0,
            "winRate": today_stats.get("winRate", 0),
        },
        "currentSignal": dict(rt.scalp_signal_by_symbol) if mode == "scalping" else {},
        "dailyProgress": {
            "target_pct": 5.0,
            "current_pct": round(daily_pct, 3),
            "max_loss_pct": float(rk.get("max_daily_loss_pct", 10)),
        },
        "riskMonitor": {
            "daily_pnl_pct": round(daily_pct, 3),
            "limit_reached": daily_pct <= -float(rk.get("max_daily_loss_pct", 10)),
            "deposit_usdt": deposit,
        },
    }
    return {
        "type": "state_update",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "bot_status": rt.bot_status,
        "warming_up": rt.warming_up,
        "strategy_mode": mode,
        "exchange_name": str(ex.get("name", "") or ""),
        "scalping_metrics": scalping_metrics,
        "positions": positions_out,
        "metrics": merged_metrics,
        "breakout": {
            "status": rt.bot_status,
            "positions": rt.breakout_tracker.get_all_positions() if rt.breakout_tracker else [],
            "stats_today": {
                "trades": int(br_st.get("today_trades", 0)),
                "wins": int(br_st.get("today_wins", 0)),
                "losses": int(br_st.get("today_losses", 0)),
                "pnl_today": float(br_st.get("today_pnl", 0.0)),
            },
            "stats": br_st,
            "last_signals": dict(rt.breakout_last_signals),
            "equity_history": breakout_equity,
        },
        "ema_scalper": {
            "status": rt.bot_status,
            "positions": [
                p.to_dict(current_bar_ts_ms=rt.ema_current_bar_ts.get(sym))
                for sym, p in rt.ema_positions.items()
            ],
            "indicators": dict(rt.ema_indicators),
            "stats": ema_st,
            "candle_history": dict(rt.ema_chart_history),
            "recent_trades": recent_ema_trades,
            "equity_history": ema_equity,
        },
        "pnl": pnl,
        "trades_recent": dbmod.fetch_trades_last_n(rt.conn, 20) if rt.conn else [],
        "config_flags": {
            "dry_run": bool(bot.get("dry_run", True)),
            "testnet": bool(ex.get("testnet", True)),
            "risk_leverage": int(rk.get("leverage", 5)),
        },
        "trading_capital": await build_trading_capital_payload(rt),
    }


async def stat_arb_bot_loop() -> None:
    cfg = RT.config
    ex = RT.exchange
    conn = RT.conn
    strat = cfg.get("strategy") or {}
    bot_cfg = cfg.get("bot") or {}
    rk = cfg.get("risk") or {}
    loop_sec = float(bot_cfg.get("loop_interval_sec", 30))
    lookback = int(strat.get("lookback_periods", 60))
    tf = strat.get("timeframe", "15m")
    max_leg = float(rk.get("max_position_usdt", 500))

    enabled = [p for p in (cfg.get("pairs") or []) if p.get("enabled")]
    for p in enabled:
        pid = pair_id_from(p["symbol_a"], p["symbol_b"])
        RT.zscore_hist[pid] = deque(maxlen=100)

    while not RT._shutdown:
        try:
            metrics_by_pair: dict = {}
            any_warming = False
            if RT.risk and RT.pm:
                st0 = RT.pm.get_state()
                exp = sum(
                    abs(x["leg_a"]["size"]) * x["leg_a"]["entry_price"]
                    + abs(x["leg_b"]["size"]) * x["leg_b"]["entry_price"]
                    for x in st0["positions"]
                )
                RT.risk.set_open_notional(exp)
    
            for pair in enabled:
                await asyncio.sleep(0.2)
                pid = pair_id_from(pair["symbol_a"], pair["symbol_b"])
                oa, ob = await asyncio.to_thread(
                    fetch_ohlcv_pair,
                    ex,
                    pair["symbol_a"],
                    pair["symbol_b"],
                    tf,
                    lookback + 5,
                )
                if len(oa) < lookback or len(ob) < lookback:
                    any_warming = True
                    metrics_by_pair[pid] = {
                        "zscore": None,
                        "spread": None,
                        "hurst": None,
                        "cointegrated": False,
                        "spread_history": [],
                        "zscore_history": list(RT.zscore_hist.get(pid, [])),
                    }
                    continue
    
                closes_a = [x[4] for x in oa[-lookback:]]
                closes_b = [x[4] for x in ob[-lookback:]]
                idx = pd.RangeIndex(start=0, stop=len(closes_a))
                pa = pd.Series(closes_a, index=idx)
                pb = pd.Series(closes_b, index=idx)
    
                metrics = get_all_metrics(pa, pb, cfg)
                cfg_h = float(pair.get("hedge_ratio", 1.0))
                ols_h = float(metrics.get("hedge_ratio", cfg_h))
                if abs(ols_h - cfg_h) / max(cfg_h, 1e-9) > 0.1:
                    logger.info(
                        "hedge_ratio deviates from config: ols=%.4f config=%.4f pair=%s",
                        ols_h,
                        cfg_h,
                        pid,
                    )
    
                z = metrics.get("zscore")
                if z is not None and z == z:
                    RT.zscore_hist[pid].append(float(z))
                metrics["zscore_history"] = list(RT.zscore_hist.get(pid, []))
    
                pos = RT.pm.get(pid)
                metrics["has_open_position"] = pos is not None
                metrics["position_direction"] = pos.direction if pos else None
    
                sig = RT.stat_signals.get_signal(metrics) if RT.stat_signals else {"action": "HOLD"}
    
                ticker_a = await asyncio.to_thread(ex.fetch_ticker, pair["symbol_a"])
                ticker_b = await asyncio.to_thread(ex.fetch_ticker, pair["symbol_b"])
                price_a = float(ticker_a["last"] or ticker_a["close"] or 0)
                price_b = float(ticker_b["last"] or ticker_b["close"] or 0)
                if pos:
                    RT.pm.update_mark(pid, price_a, price_b, float(z or 0))
    
                metrics_by_pair[pid] = {
                    "zscore": metrics.get("zscore"),
                    "spread": metrics.get("spread"),
                    "hurst": metrics.get("hurst"),
                    "cointegrated": metrics.get("cointegrated"),
                    "spread_history": metrics.get("spread_history", [])[-100:],
                    "zscore_history": metrics.get("zscore_history", [])[-100:],
                }
    
                ts = datetime.now(timezone.utc).isoformat()
                if conn and z == z:
                    dbmod.insert_metrics_snapshot(
                        conn,
                        ts,
                        pid,
                        float(z),
                        float(metrics.get("spread") or 0),
                        float(metrics.get("hurst") or 0),
                        price_a,
                        price_b,
                    )
    
                if z != z:
                    continue
    
                if sig["action"].startswith("OPEN") and not RT.pm.has(pid):
                    ok, reason = RT.risk.check_can_open(pid, max_leg) if RT.risk else (True, "")
                    if ok:
                        res = await RT.orders.open_pair_trade(pair, sig, max_leg)
                        if res.get("error"):
                            logger.error("open_pair_trade error: %s", res["error"])
                        else:
                            la = res["leg_a"]
                            lb = res["leg_b"]
                            side_a = "LONG" if la["side"] == "buy" else "SHORT"
                            side_b = "LONG" if lb["side"] == "buy" else "SHORT"
                            ppos = PairPosition(
                                pair_id=pid,
                                leg_a=LegState(
                                    pair["symbol_a"],
                                    side_a,
                                    float(la["amount"]),
                                    float(la["price"]),
                                    float(la["price"]),
                                ),
                                leg_b=LegState(
                                    pair["symbol_b"],
                                    side_b,
                                    float(lb["amount"]),
                                    float(lb["price"]),
                                    float(lb["price"]),
                                ),
                                open_time=datetime.now(timezone.utc).isoformat(),
                                zscore_at_entry=float(z or 0),
                                current_zscore=float(z or 0),
                                direction=direction_from_signal(sig["action"]),
                            )
                            RT.pm.set_position(pid, ppos)
                            dbmod.insert_trade(
                                conn,
                                {
                                    "timestamp": ts,
                                    "pair_id": pid,
                                    "action": "OPEN",
                                    "direction": ppos.direction,
                                    "symbol_a": pair["symbol_a"],
                                    "symbol_b": pair["symbol_b"],
                                    "side_a": side_a,
                                    "side_b": side_b,
                                    "qty_a": ppos.leg_a.size,
                                    "qty_b": ppos.leg_b.size,
                                    "entry_price_a": ppos.leg_a.entry_price,
                                    "entry_price_b": ppos.leg_b.entry_price,
                                    "exit_price_a": None,
                                    "exit_price_b": None,
                                    "pnl_usdt": None,
                                    "zscore_entry": float(z or 0),
                                    "zscore_exit": None,
                                    "close_reason": None,
                                    "dry_run": 1 if bot_cfg.get("dry_run") else 0,
                                },
                            )
                    else:
                        logger.info("skip open %s: %s", pid, reason)
    
                elif sig["action"] == "CLOSE" and RT.pm.has(pid):
                    pos = RT.pm.get(pid)
                    reason = "zscore_revert" if "revert" in sig.get("reason", "") else "stop_zscore"
                    await RT._close_one(pid, pos, reason)
    
            RT.warming_up = any_warming
            RT.ws_metrics.update(metrics_by_pair)
            await safe_broadcast()
            await asyncio.sleep(loop_sec)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("stat_arb_bot_loop: итерация — продолжаем")
            await asyncio.sleep(loop_sec)


async def breakout_bot_loop() -> None:
    cfg = RT.config
    br = cfg.get("breakout") or {}
    ex = RT.breakout_exchange or RT.exchange
    det = RT.breakout_detector
    eng = RT.breakout_engine
    tr = RT.breakout_tracker
    om = RT.orders_breakout or RT.orders
    if not det or not eng or not tr or not om:
        return
    loop_sec = float((br.get("bot") or {}).get("loop_interval_sec", 60))
    tf = br.get("timeframe", "1h")
    lookback = int(br.get("lookback_candles", 20))
    dry_br = bool(br.get("dry_run", (cfg.get("bot") or {}).get("dry_run", True)))
    rk_br = br.get("risk") or {}
    dep = float(rk_br.get("balance_usdt", 1000))
    pos_pct = float(rk_br.get("position_size_pct", 15)) / 100.0
    pairs = [p for p in br.get("pairs", []) if p.get("enabled")]
    tf_ms = int(float(ex.parse_timeframe(tf)) * 1000)
    while not RT._shutdown:
        try:
            for pr in pairs:
                sym = pr["symbol"]
                await asyncio.sleep(0.2)
                try:
                    candles = det.get_candles(ex, sym, tf, lookback + 15)
                    if candles.empty or len(candles) < lookback + 2:
                        continue
                    bar_ts = int(candles.iloc[-1]["timestamp"])
                    close = float(candles.iloc[-1]["close"])
    
                    p0 = tr.get_position(sym)
                    if p0 and p0.status == "PENDING" and p0.pending_order_id and not dry_br:
                        poll = await om.poll_breakout_limit(sym, p0.pending_order_id, dry_br)
                        if poll.get("done") and poll.get("filled"):
                            tr.confirm_open(
                                sym,
                                float(poll.get("avg") or 0),
                                float(poll.get("filled_qty") or 0),
                            )
                            logger.info(
                                "BREAKOUT limit filled %s @ %s qty=%s",
                                sym,
                                poll.get("avg"),
                                poll.get("filled_qty"),
                            )
                        elif poll.get("cancelled"):
                            fq = float(poll.get("filled_qty") or 0)
                            if fq > 0 and float(poll.get("avg") or 0) > 0:
                                tr.confirm_open(sym, float(poll["avg"]), fq)
                                logger.warning("BREAKOUT partial fill after cancel %s", sym)
                            else:
                                tr.remove(sym)
                                logger.info("BREAKOUT limit cancelled (exchange) %s", sym)
    
                    detection = det.detect(candles)
                    RT.breakout_last_signals[sym] = {
                        "signal": detection.get("signal"),
                        "volume_ratio": detection.get("volume_ratio"),
                        "breakout_level": detection.get("breakout_level"),
                    }
                    notional_est = dep * pos_pct
                    ok, _ = (
                        RT.risk.check_can_open(f"breakout:{sym}", notional_est, legs=1)
                        if RT.risk
                        else (True, "")
                    )
                    sig = eng.get_signal(
                        detection, sym, close, ok, current_bar_ts_ms=bar_ts, tf_ms=tf_ms
                    )
                    if sig["action"] in ("OPEN_LONG", "OPEN_SHORT"):
                        side = "buy" if sig["action"] == "OPEN_LONG" else "sell"
                        res = await om.open_breakout_limit(
                            sym,
                            side,
                            sig["position_size_usdt"],
                            sig["entry_price"],
                            dry_run_override=dry_br,
                        )
                        if res.get("error"):
                            logger.warning("breakout limit %s: %s", sym, res["error"])
                            continue
                        qty_est = float(res.get("amount") or 0)
                        if dry_br or res.get("filled"):
                            fill = float(res.get("price") or 0)
                            tr.confirm_open(sym, fill, qty_est)
                            logger.info("BREAKOUT OPEN %s %s @ %s (dry/instant)", sym, sig["action"], fill)
                        else:
                            oid = str(res.get("order_id") or "")
                            tr.open_pending(
                                sym,
                                "LONG" if sig["action"] == "OPEN_LONG" else "SHORT",
                                float(sig["entry_price"]),
                                float(sig["tp_price"]),
                                float(sig["sl_price"]),
                                float(sig["position_size_usdt"]),
                                qty_est,
                                time.time() + 7 * 24 * 3600,
                                oid or None,
                                placed_bar_ts=bar_ts,
                            )
                            logger.info(
                                "BREAKOUT limit placed %s %s id=%s @ %s",
                                sym,
                                sig["action"],
                                oid,
                                sig["entry_price"],
                            )
                    elif sig["action"] in ("CLOSE_TP", "CLOSE_SL"):
                        p = tr.get_position(sym)
                        if p and p.status == "OPEN":
                            await om.close_breakout_market(sym, p.side == "LONG", p.qty)
                            cr = "TP" if "TP" in sig["action"] else "SL"
                            rec = tr.close_position(sym, close, cr)
                            RT._log_breakout_scalp_trade(rec, cr)
                    elif sig["action"] == "CANCEL_PENDING":
                        p = tr.get_position(sym)
                        if p and p.pending_order_id:
                            try:
                                await om.cancel_breakout_order(sym, p.pending_order_id, dry_br)
                            except Exception as e:
                                logger.warning("breakout cancel pending %s: %s", sym, e)
                        tr.remove(sym)
                    if tr.get_position(sym) and tr.get_position(sym).status == "OPEN":
                        tr.update_price(sym, close)
                except Exception as e:
                    logger.exception("breakout %s: %s", sym, e)
            await safe_broadcast()
            await asyncio.sleep(loop_sec)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("breakout_bot_loop: итерация — продолжаем")
            await asyncio.sleep(loop_sec)


async def ema_scalper_bot_loop() -> None:
    cfg = RT.config
    es = cfg.get("ema_scalper") or {}
    ex = RT.ema_scalper_exchange or RT.exchange
    eng = RT.ema_scalper_engine
    om = RT.orders_ema or RT.orders
    if not eng or not om:
        return
    tf = es.get("timeframe", "5m")
    loop_sec = float((es.get("bot") or {}).get("loop_interval_sec", 10))
    ent_cfg = es.get("entry") or {}
    rk_es = es.get("risk") or {}
    dry_es = bool(es.get("dry_run", (cfg.get("bot") or {}).get("dry_run", True)))
    dep = float(rk_es.get("balance_usdt", 50))
    lev = int(rk_es.get("leverage", 5))
    pos_pct = float(rk_es.get("position_size_pct", 25)) / 100.0
    ex_cfg = es.get("exit") or {}
    tp_pct = float(ex_cfg.get("take_profit_pct", 1.5))
    sl_pct = float(ex_cfg.get("stop_loss_pct", 0.5))
    max_hold = int(ex_cfg.get("max_hold_candles", 12))
    tf_ms = int(float(ex.parse_timeframe(tf)) * 1000)
    pairs = [p for p in es.get("pairs", []) if p.get("enabled")]
    while not RT._shutdown:
        try:
            for pr in pairs:
                if RT._shutdown:
                    break
                sym = pr["symbol"]
                await asyncio.sleep(0.15)
                try:
                    try:
                        raw = await asyncio.wait_for(
                            asyncio.to_thread(ex.fetch_ohlcv, sym, tf, None, 80),
                            timeout=75.0,
                        )
                    except asyncio.TimeoutError:
                        logger.warning("EMA %s: fetch_ohlcv timeout — пропуск бара", sym)
                        continue
                    if not raw or len(raw) < 2:
                        continue
                    closed = raw[:-1]
                    candles = [
                        {
                            "ts": int(x[0]),
                            "open": float(x[1]),
                            "high": float(x[2]),
                            "low": float(x[3]),
                            "close": float(x[4]),
                            "volume": float(x[5]),
                        }
                        for x in closed
                    ]
                    bar_ts = int(closed[-1][0])
                    RT.ema_current_bar_ts[sym] = bar_ts
                    ema_period = int(ent_cfg.get("ema_period", 9))
                    ind = get_indicators(
                        candles,
                        {
                            **ent_cfg,
                            "ema_period": ema_period,
                            "volume_lookback": ent_cfg.get("volume_lookback", 10),
                        },
                    )
                    closes_all = [c["close"] for c in candles]
                    ema_series = calc_ema(closes_all, ema_period) if len(closes_all) >= ema_period else []
                    slice_c = candles[-50:] if len(candles) > 50 else candles
                    off = len(candles) - len(slice_c)
                    chart_rows: list[dict] = []
                    for j, c in enumerate(slice_c):
                        idx = off + j
                        ema_v = ema_series[idx] if idx < len(ema_series) else (
                            ema_series[-1] if ema_series else c["close"]
                        )
                        chart_rows.append(
                            {
                                "ts": c["ts"],
                                "open": c["open"],
                                "high": c["high"],
                                "low": c["low"],
                                "close": c["close"],
                                "volume": c["volume"],
                                "ema": float(ema_v),
                            }
                        )
                    RT.ema_chart_history[sym] = chart_rows
                    if not ind.get("warming_up") and eng:
                        base_ind = {k: v for k, v in ind.items() if k != "warming_up"}
                        prev_ui = eng.preview_panel_status(ind)
                        RT.ema_indicators[sym] = {**base_ind, **prev_ui}
                    elif ind.get("warming_up"):
                        RT.ema_indicators[sym] = {}
                    try:
                        ticker = await asyncio.wait_for(
                            asyncio.to_thread(ex.fetch_ticker, sym),
                            timeout=35.0,
                        )
                    except asyncio.TimeoutError:
                        logger.warning("EMA %s: fetch_ticker timeout — пропуск бара", sym)
                        continue
                    last = float(ticker["last"] or ticker["close"] or candles[-1]["close"])
                    if sym in RT.ema_positions:
                        pos = RT.ema_positions[sym]
                        pos.update(last)
                        if not ind.get("warming_up"):
                            x = eng.check_exit(pos, ind, bar_ts)
                            if x["should_exit"]:
                                await RT._close_ema_scalp(
                                    sym,
                                    pos,
                                    last,
                                    str(x.get("reason", "EXIT")),
                                    bar_ts_ms=bar_ts,
                                )
                        continue
    
                    if RT.ema_last_bar_ts.get(sym) == bar_ts:
                        continue
                    RT.ema_last_bar_ts[sym] = bar_ts
                    if ind.get("warming_up"):
                        continue
                    notional = dep * pos_pct
                    ok, _ = RT.risk.check_can_open(f"ema:{sym}", notional, legs=1) if RT.risk else (True, "")
                    # Временно: диагностика win rate (убрать после анализа)
                    logger.info(
                        "[EMA DEBUG] %s | close=%.2f ema=%.2f | above=%s below=%s | "
                        "vol_ratio=%.2f is_green=%s is_red=%s",
                        sym,
                        float(ind.get("close") or 0.0),
                        float(ind.get("ema_current") or 0.0),
                        ind.get("above_ema_count"),
                        ind.get("below_ema_count"),
                        float(ind.get("volume_ratio") or 0.0),
                        ind.get("is_green"),
                        ind.get("is_red"),
                    )
                    entry_sig = eng.check_entry(
                        ind,
                        sym,
                        len(RT.ema_positions),
                        RT.ema_last_entry_ts.get(sym),
                        bar_ts,
                        ok,
                    )
                    if entry_sig["action"] not in ("OPEN_LONG", "OPEN_SHORT"):
                        continue
                    side_buy = entry_sig["action"] == "OPEN_LONG"
                    order_usdt = notional * lev
                    res = await om.open_scalp_market(
                        sym, "buy" if side_buy else "sell", order_usdt, dry_run_override=dry_es
                    )
                    if res.get("error"):
                        continue
                    entry = float(res.get("price") or last)
                    qty = float(res.get("amount") or (notional * lev / max(entry, 1e-12)))
                    side = "LONG" if side_buy else "SHORT"
                    if side == "LONG":
                        tp_p = entry * (1.0 + tp_pct / 100.0)
                        sl_p = entry * (1.0 - sl_pct / 100.0)
                    else:
                        tp_p = entry * (1.0 - tp_pct / 100.0)
                        sl_p = entry * (1.0 + sl_pct / 100.0)
                    ts_open_iso = datetime.fromtimestamp(bar_ts / 1000.0, tz=timezone.utc).isoformat()
                    RT.ema_positions[sym] = EMAScalpPosition(
                        symbol=sym,
                        side=side,
                        entry_price=entry,
                        size_usdt=notional,
                        qty=qty,
                        leverage=lev,
                        tp_price=tp_p,
                        sl_price=sl_p,
                        max_hold_candles=max_hold,
                        entry_ts_ms=bar_ts,
                        tf_ms=tf_ms,
                        ema_at_entry=float(ind.get("ema_current") or 0.0),
                        volume_ratio_at_entry=float(ind.get("volume_ratio") or 0.0),
                        above_ema_count_at_entry=int(ind.get("above_ema_count") or 0),
                        timestamp_open_iso=ts_open_iso,
                    )
                    RT.ema_last_entry_ts[sym] = bar_ts
                    _vr = float(ind.get("volume_ratio") or 0.0)
                    _aec = int(ind.get("above_ema_count") or 0)
                    _bec = int(ind.get("below_ema_count") or 0)
                    logger.info(
                        "EMA_SCALP OPEN %s %s entry=%.6f above_ema_count=%d below_ema_count=%d volume_ratio=%.4f",
                        sym,
                        side,
                        entry,
                        _aec,
                        _bec,
                        _vr,
                    )
                except Exception as e:
                    logger.exception("ema_scalper %s: %s", sym, e)
            await safe_broadcast()
            await asyncio.sleep(loop_sec)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("ema_scalper_bot_loop: итерация — продолжаем")
            await asyncio.sleep(loop_sec)


async def run_all_loops() -> None:
    cfg = RT.config
    strat = cfg.get("strategy") or {}
    sc = cfg.get("scalping") or {}
    tasks: list[asyncio.Task] = []
    if strat.get("mode") == "scalping" and sc.get("enabled", True):
        tasks.append(asyncio.create_task(scalping_bot_loop()))
    elif strat.get("mode") == "pairs":
        tasks.append(asyncio.create_task(stat_arb_bot_loop()))
    if (cfg.get("breakout") or {}).get("enabled"):
        tasks.append(asyncio.create_task(breakout_bot_loop()))
    if (cfg.get("ema_scalper") or {}).get("enabled"):
        tasks.append(asyncio.create_task(ema_scalper_bot_loop()))
    if not tasks:
        logger.warning("Нет активных стратегий — ожидание")
        while not RT._shutdown:
            await asyncio.sleep(5)
        return
    await asyncio.gather(*tasks)


async def bot_loop() -> None:
    await run_all_loops()


def _on_sig(*_a) -> None:
    RT._shutdown = True
    RT.bot_status = "stopped"
    ev = RT._shutdown_event
    if ev is not None:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        loop.call_soon_threadsafe(ev.set)


def _parse_ccxt_position_row(p: dict) -> dict | None:
    """Одна нормализованная строка из ccxt fetch_positions (не нулевая)."""
    if not p:
        return None
    sym = p.get("symbol")
    if not sym:
        return None
    contracts = p.get("contracts")
    if contracts is None:
        info = p.get("info") or {}
        if isinstance(info, dict):
            contracts = info.get("positionAmt") or info.get("positionamt")
    try:
        c = float(contracts or 0)
    except (TypeError, ValueError):
        c = 0.0
    if abs(c) < 1e-12:
        return None
    side_raw = str(p.get("side") or "").lower()
    if side_raw in ("long", "short"):
        side = "LONG" if side_raw == "long" else "SHORT"
    else:
        side = "LONG" if c > 0 else "SHORT"
    c_abs = abs(c)
    cs = float(p.get("contractSize") or 1.0)
    qty = c_abs * cs
    entry = float(p.get("entryPrice") or p.get("entry_price") or 0)
    lev = int(float(p.get("leverage") or 1))
    notional = abs(float(p.get("notional") or 0))
    if notional <= 1e-12 and entry > 0:
        notional = abs(qty * entry)
    return {
        "symbol": sym,
        "side": side,
        "qty": qty,
        "entry_price": entry,
        "notional": notional,
        "leverage": lev,
    }


async def sync_positions_on_startup() -> None:
    """
    §13.5: восстановить EMA / Breakout из открытых позиций биржи.
    Stat-arb пары — только предупреждение по одной ноге.
    """
    cfg = RT.config
    ema_cfg = cfg.get("ema_scalper") or {}
    br_cfg = cfg.get("breakout") or {}
    ema_syms = {p["symbol"] for p in ema_cfg.get("pairs", []) if p.get("enabled")}
    br_syms = {p["symbol"] for p in br_cfg.get("pairs", []) if p.get("enabled")}
    stat_syms: set[str] = set()
    for p in cfg.get("pairs") or []:
        if p.get("enabled"):
            stat_syms.add(p["symbol_a"])
            stat_syms.add(p["symbol_b"])

    seen_ex: set[int] = set()
    all_rows: list[dict] = []

    async def grab(ex: object | None, label: str) -> None:
        if ex is None or id(ex) in seen_ex:
            return
        seen_ex.add(id(ex))
        try:
            rows = await asyncio.to_thread(ex.fetch_positions)  # type: ignore[attr-defined]
            if rows:
                all_rows.extend(rows)
        except Exception as e:
            logger.warning("[%s] fetch_positions: %s", label, e)

    await grab(RT.exchange, "main")
    await grab(RT.breakout_exchange, "breakout")
    await grab(RT.ema_scalper_exchange, "ema")

    processed_syms: set[str] = set()
    for raw in all_rows:
        info = _parse_ccxt_position_row(raw if isinstance(raw, dict) else {})
        if not info:
            continue
        sym = info["symbol"]
        if sym in processed_syms:
            continue
        processed_syms.add(sym)

        if sym in ema_syms and sym not in RT.ema_positions:
            es = ema_cfg
            rk = es.get("risk") or {}
            ex_cfg = es.get("exit") or {}
            lev = int(rk.get("leverage", 5))
            tp_pct = float(ex_cfg.get("take_profit_pct", 1.5))
            sl_pct = float(ex_cfg.get("stop_loss_pct", 0.5))
            max_hold = int(ex_cfg.get("max_hold_candles", 12))
            entry = info["entry_price"]
            qty = info["qty"]
            side = info["side"]
            notional = info["notional"]
            size_usdt = notional / max(lev, 1)
            if side == "LONG":
                tp_p = entry * (1.0 + tp_pct / 100.0)
                sl_p = entry * (1.0 - sl_pct / 100.0)
            else:
                tp_p = entry * (1.0 - tp_pct / 100.0)
                sl_p = entry * (1.0 + sl_pct / 100.0)
            ex_obj = RT.ema_scalper_exchange or RT.exchange
            tf = es.get("timeframe", "5m")
            tf_ms = int(float(ex_obj.parse_timeframe(tf)) * 1000)
            ts_ms = int(time.time() * 1000)
            ts_iso = datetime.now(timezone.utc).isoformat()
            RT.ema_positions[sym] = EMAScalpPosition(
                symbol=sym,
                side=side,
                entry_price=entry,
                size_usdt=size_usdt,
                qty=qty,
                leverage=lev,
                tp_price=tp_p,
                sl_price=sl_p,
                max_hold_candles=max_hold,
                entry_ts_ms=ts_ms,
                tf_ms=tf_ms,
                ema_at_entry=0.0,
                volume_ratio_at_entry=0.0,
                above_ema_count_at_entry=0,
                timestamp_open_iso=ts_iso,
            )
            logger.warning(
                "[STARTUP] Восстановлена EMA-позиция %s %s entry=%.4f (с биржи)",
                sym,
                side,
                entry,
            )
            continue

        if sym in br_syms and RT.breakout_tracker and not RT.breakout_tracker.get_position(sym):
            br_ex = br_cfg.get("exit") or {}
            tp_pct = float(br_ex.get("take_profit_pct", 4.0)) / 100.0
            sl_pct = float(br_ex.get("stop_loss_pct", 2.0)) / 100.0
            rk = br_cfg.get("risk") or {}
            dep = float(rk.get("balance_usdt", 1000))
            pos_pct = float(rk.get("position_size_pct", 15)) / 100.0
            side = info["side"]
            entry = info["entry_price"]
            qty = info["qty"]
            size_usdt = dep * pos_pct
            if side == "LONG":
                tp_p = entry * (1.0 + tp_pct)
                sl_p = entry * (1.0 - sl_pct)
            else:
                tp_p = entry * (1.0 - tp_pct)
                sl_p = entry * (1.0 + sl_pct)
            RT.breakout_tracker.restore_open(sym, side, entry, qty, size_usdt, tp_p, sl_p)
            logger.warning(
                "[STARTUP] Восстановлена Breakout-позиция %s %s entry=%.4f (с биржи)",
                sym,
                side,
                entry,
            )
            continue

        if sym in stat_syms:
            logger.warning(
                "[STARTUP] Открыта нога stat-arb на бирже: %s — проверьте пару вручную",
                sym,
            )
        else:
            logger.warning(
                "[STARTUP] Неизвестная открытая позиция (не в конфиге стратегий): %s",
                sym,
            )


async def main_async() -> None:
    RT.config = load_config()
    RT.env = get_env()
    RT.exchange = create_exchange(RT.config, RT.env)
    RT.conn = dbmod.get_connection()
    dbmod.init_schema(RT.conn)
    RT.risk = RiskManager(RT.config, RT.conn)
    RT.orders = OrderManager(RT.exchange, RT.config)
    RT.stat_signals = SignalEngine(RT.config)
    RT.micro_signals = MicroSignalEngine(RT.config)
    RT.orders_breakout = RT.orders
    RT.orders_ema = RT.orders

    br0 = RT.config.get("breakout") or {}
    if br0.get("enabled"):
        ben = str(br0.get("exchange", "binance"))
        RT.breakout_exchange = create_exchange_for_strategy(
            ben, bool(br0.get("testnet", True)), RT.env
        )
        RT.orders_breakout = OrderManager(RT.breakout_exchange, RT.config)
        RT.breakout_tracker = BreakoutPositionTracker()
        RT.breakout_detector = BreakoutDetector(RT.config)
        RT.breakout_engine = BreakoutSignalEngine(RT.config, RT.breakout_tracker)

    es0 = RT.config.get("ema_scalper") or {}
    if es0.get("enabled"):
        een = str(es0.get("exchange", "binance"))
        RT.ema_scalper_exchange = create_exchange_for_strategy(
            een, bool(es0.get("testnet", True)), RT.env
        )
        RT.orders_ema = OrderManager(RT.ema_scalper_exchange, RT.config)
        RT.ema_scalper_engine = EMAScalpSignalEngine(RT.config)

    strat0 = RT.config.get("strategy") or {}
    enabled = [p for p in (RT.config.get("pairs") or []) if p.get("enabled")]
    sc0 = RT.config.get("scalping") or {}
    tf0 = sc0.get("timeframe", "1m") if strat0.get("mode") == "scalping" else strat0.get("timeframe", "15m")
    if strat0.get("mode") == "scalping":
        syms = [p["symbol"] for p in sc0.get("pairs", []) if p.get("enabled")]
    else:
        syms = []
        for p in enabled:
            syms.extend([p["symbol_a"], p["symbol_b"]])
    for sym in syms:
        last_err: Exception | None = None
        for attempt in range(3):
            try:
                verify_fetch_one_candle(RT.exchange, sym, tf0)
                last_err = None
                break
            except Exception as e:
                last_err = e
                logger.warning("Проверка OHLCV %s попытка %s/3: %s", sym, attempt + 1, e)
                time.sleep(4)
        if last_err is not None:
            logger.warning(
                "Не удалось загрузить тестовую свечу для %s — запускаем бота всё равно "
                "(WS доступен). Проверьте сеть или поставьте exchange.testnet: false, "
                "если testnet недоступен.",
                sym,
            )
    lev = int((RT.config.get("risk") or {}).get("leverage", 5))
    if strat0.get("mode") == "scalping":
        for sym in syms:
            try:
                await RT.orders.set_leverage(sym, lev)
            except Exception as e:
                logger.warning("set_leverage %s: %s", sym, e)
    else:
        for p in enabled:
            try:
                await RT.orders.set_leverage(p["symbol_a"], lev)
                await RT.orders.set_leverage(p["symbol_b"], lev)
            except Exception as e:
                logger.warning("set_leverage: %s", e)

    if br0.get("enabled"):
        br_lev = int((br0.get("risk") or {}).get("leverage", 3))
        for p in br0.get("pairs", []):
            if not p.get("enabled"):
                continue
            try:
                await RT.orders_breakout.set_leverage(p["symbol"], br_lev)
            except Exception as e:
                logger.warning("breakout set_leverage %s: %s", p["symbol"], e)
    if es0.get("enabled"):
        es_lev = int((es0.get("risk") or {}).get("leverage", 5))
        for p in es0.get("pairs", []):
            if not p.get("enabled"):
                continue
            try:
                await RT.orders_ema.set_leverage(p["symbol"], es_lev)
            except Exception as e:
                logger.warning("ema_scalper set_leverage %s: %s", p["symbol"], e)

    await sync_positions_on_startup()

    async def on_pause() -> None:
        RT.set_pause(True)

    async def on_resume() -> None:
        RT.set_pause(False)

    async def on_emergency() -> None:
        await RT.emergency_stop_all()

    async def on_close_pair(pid: str) -> None:
        await RT.emergency_close_pair(pid)

    async def on_close_breakout_ws(symbol: str) -> None:
        await RT.close_breakout_manual(symbol)

    async def on_close_ema_ws(symbol: str) -> None:
        await RT.close_ema_manual(symbol)

    RT.hub = WsHub(
        on_pause,
        on_resume,
        on_emergency,
        on_close_pair,
        on_close_breakout=on_close_breakout_ws,
        on_close_ema_scalp=on_close_ema_ws,
    )
    port = int(RT.env.get("WS_PORT", 8765))

    RT._shutdown_event = asyncio.Event()
    RT.ws_task = asyncio.create_task(run_ws_server(port, RT.hub, RT._shutdown_event))
    await asyncio.sleep(0.5)

    for sig_name in (signal.SIGINT, signal.SIGTERM):
        try:
            signal.signal(sig_name, _on_sig)
        except ValueError:
            pass

    try:
        await bot_loop()
    except asyncio.CancelledError:
        raise
    except Exception:
        logger.exception("bot_loop остановлен из-за ошибки")
        raise
    finally:
        RT._shutdown = True
        if RT._shutdown_event is not None and not RT._shutdown_event.is_set():
            RT._shutdown_event.set()
        if RT.ws_task is not None and not RT.ws_task.done():
            try:
                await asyncio.wait_for(RT.ws_task, timeout=25.0)
            except asyncio.TimeoutError:
                logger.warning("WS server: ожидание завершения истекло — cancel")
                RT.ws_task.cancel()
                try:
                    await RT.ws_task
                except asyncio.CancelledError:
                    pass
            except asyncio.CancelledError:
                pass


def main() -> None:
    asyncio.run(main_async())


if __name__ == "__main__":
    main()
