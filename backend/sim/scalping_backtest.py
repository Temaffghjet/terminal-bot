"""
Micro scalping backtest: EMA+объём, TP/SL/время/EMA-cross.
Комиссия: 2×(commission_pct/100) + 2×slippage на номинал (как в ТЗ).
Запуск: python -m backend.sim.scalping_backtest --since 2026-03-01 --until 2026-04-01
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.config import get_env, load_config
from backend.exchange.connector import (
    create_exchange_for_backtest,
    create_public_data_exchange,
    fetch_ohlcv_range_historical,
)
from backend.strategy.position_manager import ScalpPosition
from backend.strategy.signals import SignalEngine

PRESET_RANGES = {"2026_4m": ("2026-01-01", "2026-04-30")}

_BACKTEST_SYMBOL_MAP = {
    "BTC/USDC:USDC": "BTC/USDT:USDT",
    "ETH/USDC:USDC": "ETH/USDT:USDT",
    "SOL/USDC:USDC": "SOL/USDT:USDT",
}


def _resolve_backtest_symbol(requested: str, use_binance_public: bool) -> str:
    if not use_binance_public:
        return requested
    return _BACKTEST_SYMBOL_MAP.get(requested, requested)


SIM_JSON_NAME = "last_scalping_sim.json"


def _day_start_utc_ms(day: str) -> int:
    dt = datetime.strptime(day, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    return int(dt.timestamp() * 1000)


def _day_end_utc_ms(day: str) -> int:
    dt = datetime.strptime(day, "%Y-%m-%d").replace(
        tzinfo=timezone.utc, hour=23, minute=59, second=59, microsecond=999000
    )
    return int(dt.timestamp() * 1000)


@dataclass
class TradeLog:
    trades: list[dict[str, Any]] = field(default_factory=list)


def run_scalping_backtest(cfg: dict, ohlcv: list) -> TradeLog:
    """
    Одна серия OHLCV, логика как в SignalEngine + ScalpPosition.should_exit.
    Учёт: gross − notional×(2×commission + 2×slippage).
    """
    engine = SignalEngine(cfg)
    sc = cfg.get("scalping") or {}
    ex = sc.get("exit") or {}
    tp_pct = float(ex.get("take_profit_pct", 0.6))
    sl_pct = float(ex.get("stop_loss_pct", 0.5))
    max_hold = int(ex.get("max_hold_minutes", 3))
    deposit = float(sc.get("deposit_usdt", 50))
    risk_pct = float(sc.get("risk_per_trade_pct", 20))
    notional = deposit * risk_pct / 100.0
    rk = cfg.get("risk") or {}
    commission = float(rk.get("commission_pct", 0.1)) / 100.0
    slippage = 0.0005
    cost_rate = 2.0 * commission + 2.0 * slippage

    log = TradeLog()
    pos: ScalpPosition | None = None
    last_entry_ts: int | None = None

    for i in range(15, len(ohlcv)):
        slice_ = ohlcv[: i + 1]
        ts = int(ohlcv[i][0])
        c = float(ohlcv[i][4])
        now = datetime.fromtimestamp(ts / 1000.0, tz=timezone.utc)
        ind = engine.calculate_indicators(slice_)
        ema = ind.get("ema")

        if pos is not None:
            if ema is None:
                continue
            should, reason = pos.should_exit(c, float(ema), now, tp_pct, sl_pct, max_hold)
            if should:
                entry = pos.entry_price
                if pos.side == "LONG":
                    gross = (c - entry) * pos.size
                else:
                    gross = (entry - c) * pos.size
                fee_cost = notional * cost_rate
                net = gross - fee_cost
                log.trades.append(
                    {
                        "ts": ts,
                        "action": "CLOSE",
                        "side": pos.side,
                        "exit": c,
                        "gross": gross,
                        "net": net,
                        "fee": fee_cost,
                        "reason": reason,
                        "dur_min": (ts - pos.entry_ts_ms) / 60000.0,
                    }
                )
                pos = None
            continue

        if last_entry_ts == ts:
            continue
        sig = engine.check_entry("sym", slice_, False)
        act = sig.get("action")
        if act not in ("OPEN_LONG", "OPEN_SHORT"):
            continue
        side = "LONG" if act == "OPEN_LONG" else "SHORT"
        entry = c
        size = notional / entry if entry else 0.0
        ts_iso = now.isoformat()
        if side == "LONG":
            tp_p = entry * (1.0 + tp_pct / 100.0)
            sl_p = entry * (1.0 - sl_pct / 100.0)
        else:
            tp_p = entry * (1.0 - tp_pct / 100.0)
            sl_p = entry * (1.0 + sl_pct / 100.0)
        pos = ScalpPosition(
            symbol="",
            side=side,
            size=size,
            entry_price=entry,
            entry_time=ts_iso,
            take_profit=tp_p,
            stop_loss=sl_p,
            current_price=entry,
            entry_ts_ms=ts,
        )
        last_entry_ts = ts
        log.trades.append({"ts": ts, "action": "OPEN", "side": side, "price": entry})

    if pos is not None and ohlcv:
        ts = int(ohlcv[-1][0])
        c = float(ohlcv[-1][4])
        now = datetime.fromtimestamp(ts / 1000.0, tz=timezone.utc)
        ind = engine.calculate_indicators(ohlcv)
        ema = float(ind.get("ema") or c)
        entry = pos.entry_price
        if pos.side == "LONG":
            gross = (c - entry) * pos.size
        else:
            gross = (entry - c) * pos.size
        fee_cost = notional * cost_rate
        net = gross - fee_cost
        log.trades.append(
            {
                "ts": ts,
                "action": "CLOSE",
                "side": pos.side,
                "exit": c,
                "gross": gross,
                "net": net,
                "fee": fee_cost,
                "reason": "END_OF_DATA",
                "dur_min": (ts - pos.entry_ts_ms) / 60000.0,
            }
        )

    return log


def _fmt_ts(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000.0, tz=timezone.utc).strftime("%Y-%m-%d %H:%M")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--preset", type=str, default=None, choices=list(PRESET_RANGES.keys()))
    parser.add_argument("--since", type=str, default="")
    parser.add_argument("--until", type=str, default="")
    parser.add_argument("--symbol", type=str, default="", help="Один символ; иначе все из scalping.pairs")
    parser.add_argument(
        "--log-trades",
        action="store_true",
        help="Вывести в консоль список закрытых сделок (см. --log-trades-limit)",
    )
    parser.add_argument(
        "--log-trades-limit",
        type=int,
        default=40,
        help="Макс. строк в логе сделок (по умолчанию 40; если меньше общего числа — первые + последние)",
    )
    args = parser.parse_args()

    cfg = load_config()
    env = get_env()
    sc = cfg.get("scalping") or {}
    if not sc:
        print("Нет секции scalping в config.yaml")
        sys.exit(1)

    since_s, until_s = args.since, args.until
    if args.preset:
        since_s, until_s = PRESET_RANGES[args.preset]
    if not since_s or not until_s:
        print("Задайте --preset или --since/--until")
        sys.exit(1)

    since_ms = _day_start_utc_ms(since_s)
    until_ms = _day_end_utc_ms(until_s)
    tf = sc.get("timeframe", "1m")

    if args.symbol:
        symbols = [args.symbol]
    else:
        symbols = [p["symbol"] for p in sc.get("pairs", []) if p.get("enabled")]
    if not symbols:
        print("scalping.pairs пуст или все disabled")
        sys.exit(1)

    ohlcv_mode = str(sc.get("ohlcv_backtest", "binance")).lower()
    use_binance = ohlcv_mode == "binance"
    use_hyperliquid = ohlcv_mode == "hyperliquid"
    if use_binance:
        ex = create_public_data_exchange({"exchange": {"name": "binance"}})
        data_source = "binance_usdtm"
    elif use_hyperliquid:
        ex = create_public_data_exchange({"exchange": {"name": "hyperliquid"}})
        data_source = "hyperliquid"
    else:
        ex = create_exchange_for_backtest(cfg, env)
        data_source = (cfg.get("exchange") or {}).get("name", "exchange")
    ex.load_markets()

    rk = cfg.get("risk") or {}
    commission = float(rk.get("commission_pct", 0.1)) / 100.0
    slippage = 0.0005
    cost_rate = 2.0 * commission + 2.0 * slippage

    t0 = time.perf_counter()
    all_closed: list[dict] = []
    total_net = 0.0
    total_gross = 0.0
    total_fees = 0.0

    for sym in symbols:
        data_sym = _resolve_backtest_symbol(sym, use_binance)
        print(f"Загрузка {sym} {tf} (OHLCV: {data_sym}, режим={ohlcv_mode})...")
        raw = fetch_ohlcv_range_historical(ex, data_sym, tf, since_ms, until_ms)
        if len(raw) < 60:
            print(f"Мало данных: {sym}")
            continue
        log = run_scalping_backtest(cfg, raw)
        closes = [t for t in log.trades if t.get("action") == "CLOSE"]
        for c in closes:
            c["symbol"] = sym
            all_closed.append(c)
        total_net += sum(x.get("net", 0) for x in closes)
        total_gross += sum(x.get("gross", 0) for x in closes)
        total_fees += sum(x.get("fee", 0) for x in closes)

    t1 = time.perf_counter()
    n = len(all_closed)
    wins = len([x for x in all_closed if x.get("net", 0) > 0])
    avg_dur = sum(x.get("dur_min", 0) for x in all_closed) / n if n else 0.0
    expectancy = total_net / n if n else 0.0

    print()
    print("=== Micro scalping backtest ===")
    print(f"Период: {since_s} .. {until_s}  TF={tf}")
    print(f"Издержки на номинал: {cost_rate * 100:.3f}% (comm 2×{commission*100:.2f}% + slip 2×{slippage*100:.2f}%)")
    print(f"Сделок (закрытий): {n}  Win rate: {100 * wins / n if n else 0:.1f}%")
    print(f"Суммарный net PnL: {total_net:.4f} USDT  (gross {total_gross:.4f}, издержки {total_fees:.4f})")
    print(f"Expectancy / сделка: {expectancy:.4f} USDT")
    print(f"Среднее время в сделке: {avg_dur:.2f} мин")
    print(f"Время расчёта: {t1 - t0:.1f}s")

    if args.log_trades and all_closed:
        lim = max(1, args.log_trades_limit)
        total_n = len(all_closed)
        if total_n <= lim:
            chunk = all_closed
            header = f"--- Все закрытия ({total_n}) ---"
        else:
            half = lim // 2
            chunk = all_closed[:half] + all_closed[-half :]
            header = f"--- Закрытия: первые {half} и последние {half} из {total_n} ---"
        print()
        print(header)
        print(f"{'время_utc':<17} {'символ':<18} {'сторона':<6} {'выход':>10} {'net':>10} {'gross':>8} {'причина'}")
        for c in chunk:
            ts = _fmt_ts(int(c.get("ts", 0)))
            sym = str(c.get("symbol", ""))[:16]
            side = str(c.get("side", ""))[:5]
            ex = float(c.get("exit", 0))
            net = float(c.get("net", 0))
            gr = float(c.get("gross", 0))
            r = str(c.get("reason", ""))[:32]
            print(f"{ts:<17} {sym:<18} {side:<6} {ex:>10.4f} {net:>10.4f} {gr:>8.4f} {r}")
        print("--- конец списка ---")

    snap = {
        "data_source": data_source,
        "ohlcv_backtest": ohlcv_mode,
        "period": {"since": since_s, "until": until_s},
        "timeframe": tf,
        "symbols": symbols,
        "trades_closed": n,
        "win_rate_pct": round(100 * wins / n, 2) if n else 0.0,
        "total_net_usdt": round(total_net, 4),
        "total_gross_usdt": round(total_gross, 4),
        "total_fees_usdt": round(total_fees, 4),
        "cost_rate_pct": round(cost_rate * 100, 4),
        "expectancy_usdt": round(expectancy, 4),
        "avg_trade_min": round(avg_dur, 2),
        "compute_sec": round(t1 - t0, 2),
        "exchange_config": (cfg.get("exchange") or {}).get("name", ""),
    }
    out_path = ROOT / "data" / SIM_JSON_NAME
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(snap, f, ensure_ascii=False, indent=2)
    print(f"Снимок симуляции записан: {out_path}")


if __name__ == "__main__":
    main()
