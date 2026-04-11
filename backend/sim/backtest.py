"""
Симуляция на исторических OHLCV: та же логика spread / z-score / SignalEngine, что в основном цикле.
Быстрый прогон ~4 месяцев, нога 100 USDT:
  python -m backend.sim.backtest --preset 2026_4m --deposit 100 --relax
При exchange.name: hyperliquid в config — свечи Hyperliquid (mainnet), ключи из .env.
Дашборд localhost — реальное время, не «ускоренная» симуляция.
"""
from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.config import get_env, load_config
from backend.exchange.connector import create_exchange_for_backtest
from backend.strategy.signals import SignalEngine
from backend.strategy.spread import get_all_metrics

# Micro scalping (одна нога, см. также `python -m backend.sim.scalping_backtest`):
from backend.sim.scalping_backtest import run_scalping_backtest  # noqa: F401


def _day_start_utc_ms(day: str) -> int:
    dt = datetime.strptime(day, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    return int(dt.timestamp() * 1000)


def _day_end_utc_ms(day: str) -> int:
    dt = datetime.strptime(day, "%Y-%m-%d").replace(
        tzinfo=timezone.utc, hour=23, minute=59, second=59, microsecond=999000
    )
    return int(dt.timestamp() * 1000)


def fetch_ohlcv_range(
    exchange,
    symbol: str,
    timeframe: str,
    since_ms: int,
    until_ms: int,
    batch_limit: int = 1000,
) -> list:
    """Постраничная загрузка OHLCV между since_ms и until_ms (включительно)."""
    out: list = []
    seen: set[int] = set()
    cursor = since_ms
    while cursor <= until_ms:
        batch = exchange.fetch_ohlcv(
            symbol, timeframe=timeframe, since=cursor, limit=batch_limit
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
        if last_ts >= until_ms or len(batch) < batch_limit:
            break
        cursor = last_ts + 1
    out.sort(key=lambda x: x[0])
    return out


def align_ohlcv_closes(
    oa: list,
    ob: list,
) -> tuple[list[int], list[float], list[float]]:
    """Внутреннее объединение по timestamp, closes A/B."""
    if not oa or not ob:
        return [], [], []
    dfa = pd.DataFrame(oa, columns=["ts", "o", "h", "l", "c", "v"])
    dfb = pd.DataFrame(ob, columns=["ts", "o", "h", "l", "c", "v"])
    m = pd.merge(dfa[["ts", "c"]], dfb[["ts", "c"]], on="ts", suffixes=("_a", "_b"))
    m = m.sort_values("ts").reset_index(drop=True)
    ts = m["ts"].astype(int).tolist()
    ca = m["c_a"].astype(float).tolist()
    cb = m["c_b"].astype(float).tolist()
    return ts, ca, cb


def qty_b_from_a(qty_a: float, price_a: float, price_b: float, hedge_ratio: float) -> float:
    return qty_a * hedge_ratio / (price_b / price_a)


def pnl_at_close(
    direction: str,
    entry_a: float,
    entry_b: float,
    exit_a: float,
    exit_b: float,
    qty_a: float,
    qty_b: float,
) -> float:
    """LONG_A_SHORT_B или SHORT_A_LONG_B — знаки как в order_manager (USDT PnL)."""
    if direction == "LONG_A_SHORT_B":
        return (exit_a - entry_a) * qty_a + (entry_b - exit_b) * qty_b
    if direction == "SHORT_A_LONG_B":
        return (entry_a - exit_a) * qty_a + (exit_b - entry_b) * qty_b
    return 0.0


@dataclass
class SimState:
    has_position: bool = False
    direction: str = ""
    entry_a: float = 0.0
    entry_b: float = 0.0
    qty_a: float = 0.0
    qty_b: float = 0.0
    entry_z: float = 0.0
    entry_idx: int = 0


@dataclass
class SimResult:
    trades: list[dict[str, Any]] = field(default_factory=list)
    total_pnl: float = 0.0
    wins: int = 0
    losses: int = 0


def run_pair_backtest(
    cfg: dict,
    pair: dict,
    ts: list[int],
    closes_a: list[float],
    closes_b: list[float],
    notional_usdt: float,
    relax_filters: bool = False,
) -> SimResult:
    strat = cfg.get("strategy") or {}
    lookback = int(strat.get("lookback_periods", 60))
    n = len(closes_a)
    if n < lookback:
        return SimResult()

    signals = SignalEngine(cfg)
    st = SimState()
    out = SimResult()

    for t in range(lookback - 1, n):
        pa = pd.Series(closes_a[t - lookback + 1 : t + 1])
        pb = pd.Series(closes_b[t - lookback + 1 : t + 1])
        metrics = get_all_metrics(pa, pb, cfg)
        z = metrics.get("zscore")
        if z is None or z != z:
            continue

        metrics["has_open_position"] = st.has_position
        metrics["position_direction"] = st.direction if st.has_position else None
        sig_in = dict(metrics)
        if relax_filters:
            sig_in["hurst"] = 0.4
            sig_in["cointegrated"] = True
            sig_in["p_value"] = 0.01
        sig = signals.get_signal(sig_in)

        price_a = closes_a[t]
        price_b = closes_b[t]

        if sig["action"] == "CLOSE" and st.has_position:
            pnl = pnl_at_close(
                st.direction,
                st.entry_a,
                st.entry_b,
                price_a,
                price_b,
                st.qty_a,
                st.qty_b,
            )
            out.total_pnl += pnl
            if pnl > 0:
                out.wins += 1
            elif pnl < 0:
                out.losses += 1
            reason = "stop_zscore" if "emergency" in sig.get("reason", "") else "zscore_revert"
            out.trades.append(
                {
                    "exit_ts": ts[t],
                    "action": "CLOSE",
                    "pnl_usdt": pnl,
                    "z_entry": st.entry_z,
                    "z_exit": float(z),
                    "reason": reason,
                }
            )
            st = SimState()

        elif sig["action"].startswith("OPEN") and not st.has_position:
            hedge = float(metrics.get("hedge_ratio") or pair.get("hedge_ratio", 1.0))
            qa = notional_usdt / price_a if price_a else 0.0
            qb = qty_b_from_a(qa, price_a, price_b, hedge)
            if sig["action"] == "OPEN_SHORT_A_LONG_B":
                direction = "SHORT_A_LONG_B"
            else:
                direction = "LONG_A_SHORT_B"
            st = SimState(
                has_position=True,
                direction=direction,
                entry_a=price_a,
                entry_b=price_b,
                qty_a=qa,
                qty_b=qb,
                entry_z=float(z),
                entry_idx=t,
            )
            out.trades.append(
                {
                    "entry_ts": ts[t],
                    "action": "OPEN",
                    "direction": direction,
                    "z": float(z),
                }
            )

    return out


PRESET_RANGES = {
    # Четыре календарных месяца: янв — апр 2026
    "2026_4m": ("2026-01-01", "2026-04-30"),
}


def main() -> None:
    import time

    parser = argparse.ArgumentParser(description="Backtest on historical OHLCV (public API).")
    parser.add_argument("--bars", type=int, default=3000, help="Свечей на символ (если не задан диапазон дат).")
    parser.add_argument("--since", type=str, default="", help="Начало периода UTC, YYYY-MM-DD (включительно).")
    parser.add_argument(
        "--until",
        type=str,
        default="",
        help="Конец периода UTC, YYYY-MM-DD (включительно, конец дня).",
    )
    parser.add_argument(
        "--preset",
        type=str,
        default=None,
        choices=list(PRESET_RANGES.keys()),
        help="Готовый диапазон: 2026_4m → 2026-01-01..2026-04-30 (~4 мес.). Перекрывает --since/--until.",
    )
    parser.add_argument(
        "--deposit",
        type=float,
        default=None,
        metavar="USDT",
        help="Размер ноги A в USDT (как max_position_usdt). Например 100 при «депозите 100$» на ногу.",
    )
    parser.add_argument("--pair-index", type=int, default=0, help="Индекс пары в config pairs (только enabled).")
    parser.add_argument(
        "--relax",
        action="store_true",
        help="Упростить симуляцию: считать Hurst mean-reverting и коинтеграцию выполненными (остаётся логика z-score). "
        "Иначе на короткой истории часто 0 сделок из-за фильтров.",
    )
    args = parser.parse_args()

    since_s = args.since
    until_s = args.until
    if args.preset is not None:
        since_s, until_s = PRESET_RANGES[args.preset]

    cfg = load_config()
    env = get_env()
    ex = create_exchange_for_backtest(cfg, env)
    ex.load_markets()

    enabled = [p for p in (cfg.get("pairs") or []) if p.get("enabled")]
    if not enabled:
        print("Нет enabled пар в config.yaml")
        sys.exit(1)
    if args.pair_index < 0 or args.pair_index >= len(enabled):
        print(f"pair-index вне диапазона 0..{len(enabled)-1}")
        sys.exit(1)

    pair = enabled[args.pair_index]
    sym_a = pair["symbol_a"]
    sym_b = pair["symbol_b"]
    tf = (cfg.get("strategy") or {}).get("timeframe", "15m")
    rk = cfg.get("risk") or {}
    notional = (
        float(args.deposit)
        if args.deposit is not None
        else float(rk.get("max_position_usdt", 500))
    )

    use_range = bool(since_s and until_s)
    t0 = time.perf_counter()
    ex_name = (cfg.get("exchange") or {}).get("name", "")
    if ex_name == "hyperliquid" and env.get("HYPERLIQUID_WALLET_ADDRESS"):
        print("Hyperliquid: используются ключи из .env (свечи mainnet).")
    elif ex_name == "hyperliquid":
        print("Hyperliquid: в .env нет HYPERLIQUID_* — ccxt всё равно тянет публичные OHLCV.")

    if use_range:
        since_ms = _day_start_utc_ms(since_s)
        until_ms = _day_end_utc_ms(until_s)
        if until_ms < since_ms:
            print("--until раньше --since")
            sys.exit(1)
        print(
            f"Биржа (данные, mainnet): {ex_name}  TF={tf}  "
            f"период: {since_s} .. {until_s} UTC"
        )
    else:
        print(f"Биржа (данные, mainnet): {ex_name}  TF={tf}  свечей: {args.bars}")

    print(f"Пара: {sym_a} / {sym_b}  notional/нога A: {notional} USDT")
    if args.relax:
        print("Режим: --relax (фильтры Hurst/коинтеграции отключены для сигнала)")
    print("Загрузка OHLCV...")

    if use_range:
        oa = fetch_ohlcv_range(ex, sym_a, tf, since_ms, until_ms)
        ob = fetch_ohlcv_range(ex, sym_b, tf, since_ms, until_ms)
    else:
        oa = ex.fetch_ohlcv(sym_a, timeframe=tf, limit=args.bars)
        ob = ex.fetch_ohlcv(sym_b, timeframe=tf, limit=args.bars)
    ts, ca, cb = align_ohlcv_closes(oa, ob)
    print(f"После выравнивания по времени: {len(ts)} баров")

    if len(ts) < int((cfg.get("strategy") or {}).get("lookback_periods", 60)):
        print("Слишком мало общих баров для lookback.")
        sys.exit(1)

    t_after_load = time.perf_counter()
    res = run_pair_backtest(cfg, pair, ts, ca, cb, notional, relax_filters=args.relax)
    t_done = time.perf_counter()

    closed = [x for x in res.trades if x.get("action") == "CLOSE"]
    n_open = len([x for x in res.trades if x.get("action") == "OPEN"])
    print()
    print("--- Результат симуляции ---")
    print(
        f"Время: загрузка+merge {t_after_load - t0:.1f}s, прогон {t_done - t_after_load:.1f}s, всего {t_done - t0:.1f}s"
    )
    print(f"Сделок OPEN: {n_open}  CLOSE: {len(closed)}")
    print(f"Суммарный PnL (USDT, упрощённая модель): {res.total_pnl:.4f}")
    print(f"(нога A = {notional} USDT; ориентир «депозит на ногу», не весь счёт)")
    print(f"Прибыльных закрытий: {res.wins}  Убыточных: {res.losses}")
    if closed:
        rets = [c["pnl_usdt"] for c in closed]
        avg = sum(rets) / len(rets)
        print(f"Средний PnL на закрытие: {avg:.4f} USDT")
    print()
    print("Последние 10 записей (OPEN/CLOSE):")
    for row in res.trades[-10:]:
        print(row)


if __name__ == "__main__":
    main()
