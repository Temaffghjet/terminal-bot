"""EMA Scalper Bot — главный цикл."""
from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timezone
from typing import Any

from ccxt.base.errors import DDoSProtection, RateLimitExceeded

from backend.config import get_env, load_config
from backend.data import db as dbmod
from backend.exchange.connector import create_exchange_for_strategy
from backend.exchange.order_manager import OrderManager
from backend.strategy.ema_scalper.indicators import (
    calc_ema,
    get_htf_data_cached,
    get_indicators,
    get_1h_trend,
    get_market_structure,
)
from backend.strategy.ema_scalper.position import ScalpPosition
from backend.strategy.ema_scalper.signals import EMAScalpSignalEngine
from backend import ws_server

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("ema_bot")


def _is_rate_limited(e: BaseException) -> bool:
    if isinstance(e, (RateLimitExceeded, DDoSProtection)):
        return True
    t = f"{e}"
    return "429" in t or "Too Many Requests" in t or "RateLimit" in t


async def _hyperliquid_warmup(ex: Any) -> None:
    """Прогрев load_markets — иначе каждый fetch_ticker тянет fetch_markets и бьёт 429 на /info."""
    for i in range(5):
        try:
            await asyncio.to_thread(ex.load_markets, False)
            logger.info("Hyperliquid: рынки загружены (кэш ccxt), лимит запросов меньше.")
            return
        except Exception as e:  # noqa: BLE001
            if not _is_rate_limited(e):
                logger.warning("load_markets: %s", e)
            wait = min(2 ** (i + 1), 45)
            logger.warning("load_markets: лимит/ошибка, ждём %s с", wait)
            await asyncio.sleep(float(wait))
    await asyncio.to_thread(ex.load_markets, False)


class RT:
    config: dict = {}
    env: dict = {}
    exchange: Any = None
    conn: Any = None
    orders: OrderManager | None = None
    engine: EMAScalpSignalEngine | None = None
    positions: dict[str, ScalpPosition] = {}
    last_entry_ts: dict[str, float] = {}
    last_processed_ts: dict[str, int] = {}
    signal_rows: dict[str, dict] = {}
    chart_snapshots: dict[str, dict[str, Any]] = {}
    paused: bool = False


def _balance() -> float:
    es = (RT.config.get("ema_scalper") or {}).get("risk") or {}
    if es.get("use_exchange_balance"):
        return float(es.get("balance_usdt", 500))
    return float(es.get("balance_usdt", 500))


def _chart_rows_for_ws(
    candles: list[dict],
    *,
    ema_period: int | None = None,
    ema_period_2: int | None = None,
    limit: int = 48,
) -> list[dict[str, Any]]:
    """Сжатые точки для Recharts: t (ms), c, ema, ema2."""
    if not candles:
        return []
    slice_ = candles[-limit:]
    closes = [float(c["close"]) for c in slice_]
    e1: list[float] = []
    e2: list[float] = []
    if ema_period and len(closes) >= ema_period:
        e1 = calc_ema(closes, ema_period)
    if ema_period_2 and len(closes) >= ema_period_2:
        e2 = calc_ema(closes, ema_period_2)
    out: list[dict[str, Any]] = []
    for i, c in enumerate(slice_):
        t = int(c.get("t", 0))
        row: dict[str, Any] = {
            "t": t,
            "c": round(float(c["close"]), 8),
        }
        if e1 and i < len(e1):
            row["ema"] = round(float(e1[i]), 8)
        if e2 and i < len(e2):
            row["ema2"] = round(float(e2[i]), 8)
        out.append(row)
    return out


def build_ws_payload() -> dict[str, Any]:
    es = RT.config.get("ema_scalper") or {}
    dry = bool(es.get("dry_run", (RT.config.get("bot") or {}).get("dry_run", True)))
    stats = dbmod.get_stats(RT.conn) if RT.conn else {}
    pnl_today = float(stats.get("pnl_today", 0))
    recent = dbmod.get_recent_trades(RT.conn, 50) if RT.conn else []

    return {
        "ts": datetime.now(timezone.utc).isoformat(),
        "bot_status": "paused" if RT.paused else "running",
        "dry_run": dry,
        "pnl_today": pnl_today,
        "trades_today": int(stats.get("trades_today", 0)),
        "ema_scalper": {
            "positions": [p.to_dict() for p in RT.positions.values()],
            "signals": RT.signal_rows,
            "charts": RT.chart_snapshots,
            "stats": stats,
            "recent_trades": recent,
        },
    }


async def ema_scalper_loop() -> None:
    es = RT.config.get("ema_scalper") or {}
    if not es.get("enabled"):
        while True:
            await asyncio.sleep(60)
            await ws_server.broadcast_state()

    entry_cfg = es.get("entry") or {}
    exit_cfg = es.get("exit") or {}
    risk = es.get("risk") or {}
    loop_sec = float((es.get("bot") or {}).get("loop_interval_sec", 10))
    max_loss_pct = float(risk.get("max_daily_loss_pct", 3.0))

    while True:
        if RT.paused:
            await asyncio.sleep(loop_sec)
            await ws_server.broadcast_state()
            continue

        pairs = [p for p in (es.get("pairs") or []) if p.get("enabled")]
        daily_loss = False
        if RT.conn:
            daily_loss = dbmod.get_daily_loss_exceeded(RT.conn, _balance(), max_loss_pct)

        for pair in pairs:
            symbol = pair["symbol"]
            await asyncio.sleep(0.85)
            try:
                raw_5m = await asyncio.wait_for(
                    asyncio.to_thread(
                        RT.exchange.fetch_ohlcv, symbol, "5m", None, 40
                    ),
                    timeout=15.0,
                )
            except asyncio.TimeoutError:
                logger.warning("[EMA] timeout fetching %s", symbol)
                continue
            except Exception as e:  # noqa: BLE001
                if _is_rate_limited(e):
                    w = 12.0
                    logger.warning("[EMA] 429/лимит, пауза %.0f с: %s", w, e)
                    await asyncio.sleep(w)
                else:
                    logger.error("[EMA] fetch_ohlcv %s: %s", symbol, e)
                continue

            if not raw_5m or len(raw_5m) < 3:
                continue

            last_ts = int(raw_5m[-2][0])
            new_bar = last_ts != RT.last_processed_ts.get(symbol)
            if not new_bar and symbol not in RT.positions:
                continue
            if new_bar:
                RT.last_processed_ts[symbol] = last_ts

            candles_5m = [
                {
                    "t": int(x[0]),
                    "open": x[1],
                    "high": x[2],
                    "low": x[3],
                    "close": x[4],
                    "volume": x[5],
                }
                for x in raw_5m[:-1]
            ]

            try:
                ms_tf = str(entry_cfg.get("market_structure_tf", "15m"))
                htf_tf = str(entry_cfg.get("higher_tf", "1h"))
                candles_15m = await asyncio.to_thread(
                    get_htf_data_cached, RT.exchange, symbol, ms_tf, 60.0
                )
                candles_1h = await asyncio.to_thread(
                    get_htf_data_cached, RT.exchange, symbol, htf_tf, 120.0
                )
            except Exception as e:  # noqa: BLE001
                if _is_rate_limited(e):
                    await asyncio.sleep(8.0)
                logger.error("[EMA] HTF %s: %s", symbol, e)
                continue

            indicators = get_indicators(candles_5m, entry_cfg)
            indicators["candles_1h"] = candles_1h
            if not new_bar and symbol in RT.positions:
                try:
                    tk = await asyncio.to_thread(RT.exchange.fetch_ticker, symbol)
                    live = float(tk.get("last") or tk.get("close") or candles_5m[-1]["close"])
                    indicators["close"] = live
                except Exception as e:  # noqa: BLE001
                    if _is_rate_limited(e):
                        await asyncio.sleep(10.0)
                    logger.warning("[EMA] ticker %s: %s", symbol, e)
            if indicators.get("warming_up"):
                if RT.engine:
                    RT.signal_rows[symbol] = RT.engine.signal_status_for_ui(
                        indicators,
                        [],
                        [],
                        symbol in RT.positions,
                        last_entry_ts=RT.last_entry_ts.get(symbol, 0.0),
                        daily_loss_exceeded=daily_loss,
                        open_positions_count=len(RT.positions),
                        balance=_balance(),
                    )
                ema_pw = int(entry_cfg.get("ema_period", 9))
                RT.chart_snapshots[symbol] = {
                    "tf_5m": str(es.get("timeframe", "5m")),
                    "tf_15m": str(entry_cfg.get("market_structure_tf", "15m")),
                    "tf_1h": str(entry_cfg.get("higher_tf", "1h")),
                    "series_5m": _chart_rows_for_ws(
                        candles_5m,
                        ema_period=ema_pw if len(candles_5m) >= ema_pw else None,
                        limit=48,
                    ),
                    "series_15m": [],
                    "series_1h": [],
                    "structure_15m": "warmup",
                    "trend_1h": "—",
                    "signal_status": "FILTER",
                    "signal_reason": "warmup",
                }
                continue

            lookback = int(entry_cfg.get("market_structure_lookback", 6))
            structure = get_market_structure(candles_15m, lookback)
            trend_1h = get_1h_trend(
                candles_1h,
                int(entry_cfg.get("higher_tf_ema_fast", 9)),
                int(entry_cfg.get("higher_tf_ema_slow", 21)),
            )

            indicators["structure_15m"] = structure
            indicators["trend_1h"] = trend_1h["trend"]
            indicators["trend_1h_data"] = trend_1h

            current_price = float(indicators.get("close", candles_5m[-1]["close"]))
            has_pos = symbol in RT.positions
            open_n = len(RT.positions)

            if RT.engine and new_bar:
                RT.signal_rows[symbol] = RT.engine.signal_status_for_ui(
                    indicators,
                    candles_15m,
                    candles_1h,
                    has_pos,
                    last_entry_ts=RT.last_entry_ts.get(symbol, 0.0),
                    daily_loss_exceeded=daily_loss,
                    open_positions_count=open_n,
                    balance=_balance(),
                )

            ema_p = int(entry_cfg.get("ema_period", 9))
            ema_f = int(entry_cfg.get("higher_tf_ema_fast", 9))
            ema_s = int(entry_cfg.get("higher_tf_ema_slow", 21))
            sig_row = RT.signal_rows.get(symbol) or {}
            RT.chart_snapshots[symbol] = {
                "tf_5m": str(es.get("timeframe", "5m")),
                "tf_15m": str(entry_cfg.get("market_structure_tf", "15m")),
                "tf_1h": str(entry_cfg.get("higher_tf", "1h")),
                "series_5m": _chart_rows_for_ws(
                    candles_5m, ema_period=ema_p, limit=48
                ),
                "series_15m": _chart_rows_for_ws(
                    candles_15m, ema_period=9, limit=36
                ),
                "series_1h": _chart_rows_for_ws(
                    candles_1h, ema_period=ema_f, ema_period_2=ema_s, limit=36
                ),
                "structure_15m": structure,
                "trend_1h": trend_1h.get("trend", "NEUTRAL"),
                "signal_status": sig_row.get("status", "—"),
                "signal_reason": sig_row.get("reason", ""),
            }

            if symbol in RT.positions:
                pos = RT.positions[symbol]
                pos.update(current_price, new_candle=new_bar)
                if RT.engine:
                    ex_sig = RT.engine.check_exit(pos, indicators)
                    if ex_sig["should_exit"]:
                        dry = bool(es.get("dry_run", True))
                        if not dry and RT.orders:
                            try:
                                await asyncio.to_thread(
                                    RT.orders.close_scalp, symbol, pos.side
                                )
                            except Exception as e:
                                logger.error("close_scalp %s: %s", symbol, e)
                        exit_px = current_price
                        pos.close(exit_px, ex_sig["reason"])
                        if RT.conn:
                            dbmod.log_scalp_trade(RT.conn, pos, dry)
                        logger.info(
                            "EMA_TRADE CLOSE %s %s net=%.4f USDT reason=%s trailing=%s",
                            symbol,
                            pos.side,
                            pos.pnl_usdt,
                            ex_sig["reason"],
                            pos.trailing_active,
                        )
                        del RT.positions[symbol]

            if new_bar and symbol not in RT.positions and RT.engine:
                sig = RT.engine.check_entry(
                    indicators=indicators,
                    symbol=symbol,
                    last_entry_ts=RT.last_entry_ts.get(symbol, 0.0),
                    daily_loss_exceeded=daily_loss,
                    balance=_balance(),
                    has_position=False,
                    open_positions_count=open_n,
                    candles_15m=candles_15m,
                    candles_1h=candles_1h,
                )
                if sig["action"] in ("OPEN_LONG", "OPEN_SHORT"):
                    margin = _balance() * float(risk.get("position_size_pct", 25)) / 100.0
                    lev = int(risk.get("leverage", 5))
                    dry = bool(es.get("dry_run", True))
                    fill_price = current_price
                    if not dry and RT.orders:
                        try:
                            od = await asyncio.to_thread(
                                RT.orders.open_scalp,
                                symbol,
                                sig["action"],
                                margin,
                                lev,
                            )
                            fill_price = float(od.get("fill_price") or current_price)
                        except Exception as e:
                            logger.error("open_scalp %s: %s", symbol, e)
                            continue

                    snap = dict(indicators)
                    snap["structure_15m"] = structure
                    snap["trend_1h"] = trend_1h["trend"]

                    pos = ScalpPosition(
                        symbol=symbol,
                        side="LONG" if "LONG" in sig["action"] else "SHORT",
                        entry_price=fill_price,
                        size_usdt=margin,
                        leverage=lev,
                        tp_pct=float(exit_cfg.get("take_profit_pct", 1.2)) / 100.0,
                        sl_pct=float(exit_cfg.get("stop_loss_pct", 0.4)) / 100.0,
                        max_hold_candles=int(exit_cfg.get("max_hold_candles", 10)),
                        trailing_enabled=bool(exit_cfg.get("trailing_stop_enabled", True)),
                        trailing_activation_pct=float(
                            exit_cfg.get("trailing_activation_pct", 0.3)
                        ),
                        trailing_distance_pct=float(
                            exit_cfg.get("trailing_distance_pct", 0.2)
                        ),
                        entry_ts=time.time(),
                        indicators_snapshot=snap,
                    )
                    RT.positions[symbol] = pos
                    RT.last_entry_ts[symbol] = time.time()

        await ws_server.broadcast_state()
        await asyncio.sleep(loop_sec)


async def main_async() -> None:
    RT.config = load_config()
    RT.env = get_env()
    een = str((RT.config.get("ema_scalper") or {}).get("exchange", "hyperliquid"))
    testn = bool((RT.config.get("ema_scalper") or {}).get("testnet", False))
    RT.exchange = create_exchange_for_strategy(een, testn, RT.env)
    if een == "hyperliquid":
        await _hyperliquid_warmup(RT.exchange)
    RT.conn = dbmod.get_connection()
    dbmod.init_schema(RT.conn)
    RT.orders = OrderManager(RT.exchange, RT.config)
    RT.engine = EMAScalpSignalEngine(RT.config)

    ws_server.set_state_provider(build_ws_payload)
    ws_port = int(RT.env.get("WS_PORT", 8765))
    asyncio.create_task(ws_server.run_ws_server(ws_port))
    logger.info("WebSocket на 0.0.0.0:%s", ws_port)

    await ema_scalper_loop()


def main() -> None:
    asyncio.run(main_async())


if __name__ == "__main__":
    main()
