"""SQLite: trades, metrics, logs"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_BOT_ROOT = Path(__file__).resolve().parent.parent.parent
_DEFAULT_DB = _BOT_ROOT / "data" / "bot.sqlite3"


def get_connection(db_path: Path | None = None) -> sqlite3.Connection:
    path = db_path or _DEFAULT_DB
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    return conn


def init_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
-- trades table
CREATE TABLE IF NOT EXISTS trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT,
    pair_id TEXT,
    action TEXT,
    direction TEXT,
    symbol_a TEXT,
    symbol_b TEXT,
    side_a TEXT,
    side_b TEXT,
    qty_a REAL,
    qty_b REAL,
    entry_price_a REAL,
    entry_price_b REAL,
    exit_price_a REAL,
    exit_price_b REAL,
    pnl_usdt REAL,
    zscore_entry REAL,
    zscore_exit REAL,
    close_reason TEXT,
    dry_run INTEGER
);
-- metrics_history table (for charts)
CREATE TABLE IF NOT EXISTS metrics_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT,
    pair_id TEXT,
    zscore REAL,
    spread REAL,
    hurst REAL,
    price_a REAL,
    price_b REAL
);
CREATE TABLE IF NOT EXISTS scalp_trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp_open TEXT,
    timestamp_close TEXT,
    symbol TEXT,
    strategy TEXT DEFAULT 'ema_scalper',
    side TEXT,
    entry_price REAL,
    exit_price REAL,
    tp_price REAL,
    sl_price REAL,
    size_usdt REAL,
    notional REAL,
    leverage INTEGER,
    candles_held INTEGER,
    pnl_usdt REAL,
    pnl_pct REAL,
    fee_usdt REAL,
    close_reason TEXT,
    dry_run INTEGER DEFAULT 1,
    ema_at_entry REAL,
    volume_ratio_at_entry REAL,
    above_ema_count_at_entry INTEGER,
    entry_reason TEXT
);
CREATE INDEX IF NOT EXISTS idx_scalp_symbol ON scalp_trades(symbol);
CREATE INDEX IF NOT EXISTS idx_scalp_ts ON scalp_trades(timestamp_open);
CREATE INDEX IF NOT EXISTS idx_scalp_strategy ON scalp_trades(strategy);
-- открытые позиции EMA в dry-run (память процесса → переживают restart)
CREATE TABLE IF NOT EXISTS ema_sim_open_v2 (
    profile_id TEXT NOT NULL DEFAULT 'base',
    symbol TEXT NOT NULL,
    payload_json TEXT NOT NULL
    ,PRIMARY KEY (profile_id, symbol)
);
"""
    )
    conn.commit()
    _migrate_scalp_entry_reason(conn)


def _migrate_scalp_entry_reason(conn: sqlite3.Connection) -> None:
    """Старые БД без колонки entry_reason."""
    try:
        conn.execute("ALTER TABLE scalp_trades ADD COLUMN entry_reason TEXT")
        conn.commit()
    except sqlite3.OperationalError:
        pass


def upsert_ema_sim_open(conn: sqlite3.Connection, payload: dict[str, Any]) -> None:
    """Сохранить открытую EMA dry-run позицию (JSON полей EMAScalpPosition)."""
    import json

    sym = str(payload.get("symbol") or "")
    profile_id = str(payload.get("profile_id") or "base")
    if not sym:
        return
    conn.execute(
        """
        INSERT INTO ema_sim_open_v2 (profile_id, symbol, payload_json) VALUES (?, ?, ?)
        ON CONFLICT(profile_id, symbol) DO UPDATE SET payload_json = excluded.payload_json
        """,
        (profile_id, sym, json.dumps(payload, default=str)),
    )
    conn.commit()


def delete_ema_sim_open(conn: sqlite3.Connection, symbol: str, profile_id: str = "base") -> None:
    conn.execute(
        "DELETE FROM ema_sim_open_v2 WHERE symbol = ? AND profile_id = ?",
        (symbol, profile_id),
    )
    conn.commit()


def load_all_ema_sim_open(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    cur = conn.execute("SELECT profile_id, symbol, payload_json FROM ema_sim_open_v2")
    return [
        {"profile_id": str(r[0]), "symbol": str(r[1]), "payload_json": str(r[2])}
        for r in cur.fetchall()
    ]


def insert_trade(conn: sqlite3.Connection, row: dict[str, Any]) -> int:
    cols = [
        "timestamp",
        "pair_id",
        "action",
        "direction",
        "symbol_a",
        "symbol_b",
        "side_a",
        "side_b",
        "qty_a",
        "qty_b",
        "entry_price_a",
        "entry_price_b",
        "exit_price_a",
        "exit_price_b",
        "pnl_usdt",
        "zscore_entry",
        "zscore_exit",
        "close_reason",
        "dry_run",
    ]
    placeholders = ",".join("?" * len(cols))
    values = [row.get(c) for c in cols]
    cur = conn.execute(
        f"INSERT INTO trades ({','.join(cols)}) VALUES ({placeholders})",
        values,
    )
    conn.commit()
    return int(cur.lastrowid)


def insert_metrics_snapshot(
    conn: sqlite3.Connection,
    timestamp: str,
    pair_id: str,
    zscore: float,
    spread: float,
    hurst: float,
    price_a: float,
    price_b: float,
) -> None:
    conn.execute(
        """
        INSERT INTO metrics_history (timestamp, pair_id, zscore, spread, hurst, price_a, price_b)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (timestamp, pair_id, zscore, spread, hurst, price_a, price_b),
    )
    conn.commit()


def fetch_recent_trades(conn: sqlite3.Connection, limit: int = 100) -> list[dict[str, Any]]:
    cur = conn.execute(
        "SELECT * FROM trades ORDER BY timestamp DESC LIMIT ?",
        (limit,),
    )
    return [dict(r) for r in cur.fetchall()]


def fetch_trades_last_n(conn: sqlite3.Connection, n: int = 20) -> list[dict[str, Any]]:
    cur = conn.execute(
        "SELECT * FROM trades ORDER BY timestamp DESC LIMIT ?",
        (n,),
    )
    return [dict(r) for r in cur.fetchall()]


def fetch_scalp_today_stats(conn: sqlite3.Connection) -> dict[str, Any]:
    """Сделки scalp за сегодня (UTC дата в timestamp)."""
    start = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    cur = conn.execute(
        """
        SELECT COUNT(*),
               COALESCE(SUM(CASE WHEN pnl_usdt > 0 THEN 1 ELSE 0 END), 0),
               COALESCE(SUM(CASE WHEN pnl_usdt < 0 THEN 1 ELSE 0 END), 0),
               COALESCE(SUM(pnl_usdt), 0)
        FROM trades
        WHERE action = 'CLOSE' AND pair_id LIKE 'scalp:%' AND timestamp >= ?
        """,
        (start,),
    )
    row = cur.fetchone()
    n = int(row[0] or 0)
    wins = int(row[1] or 0)
    losses = int(row[2] or 0)
    total = float(row[3] or 0)
    return {
        "trades": n,
        "wins": wins,
        "losses": losses,
        "totalPnL": total,
        "winRate": (100.0 * wins / n) if n else 0.0,
    }


def insert_scalp_trade(conn: sqlite3.Connection, row: dict[str, Any]) -> int:
    cols = [
        "timestamp_open",
        "timestamp_close",
        "symbol",
        "strategy",
        "side",
        "entry_price",
        "exit_price",
        "tp_price",
        "sl_price",
        "size_usdt",
        "notional",
        "leverage",
        "candles_held",
        "pnl_usdt",
        "pnl_pct",
        "fee_usdt",
        "close_reason",
        "dry_run",
        "ema_at_entry",
        "volume_ratio_at_entry",
        "above_ema_count_at_entry",
        "entry_reason",
    ]
    placeholders = ",".join("?" * len(cols))
    values = [row.get(c) for c in cols]
    cur = conn.execute(
        f"INSERT INTO scalp_trades ({','.join(cols)}) VALUES ({placeholders})",
        values,
    )
    conn.commit()
    return int(cur.lastrowid)


def get_recent_scalp_trades(
    conn: sqlite3.Connection, limit: int = 50, strategy: str | None = None
) -> list[dict[str, Any]]:
    if strategy:
        cur = conn.execute(
            "SELECT * FROM scalp_trades WHERE strategy = ? ORDER BY id DESC LIMIT ?",
            (strategy, limit),
        )
    else:
        cur = conn.execute(
            "SELECT * FROM scalp_trades ORDER BY id DESC LIMIT ?",
            (limit,),
        )
    return [dict(r) for r in cur.fetchall()]


def get_equity_history(
    conn: sqlite3.Connection, strategy: str, deposit: float, limit: int = 100
) -> list[float]:
    """Накопительный баланс после каждой закрытой сделки (по id)."""
    cur = conn.execute(
        """
        SELECT pnl_usdt FROM scalp_trades
        WHERE strategy = ? AND pnl_usdt IS NOT NULL
        ORDER BY id ASC
        """,
        (strategy,),
    )
    rows = [float(r[0]) for r in cur.fetchall()]
    cum = float(deposit)
    out: list[float] = []
    for pnl in rows:
        cum += pnl
        out.append(round(cum, 4))
    if limit and len(out) > limit:
        out = out[-limit:]
    return out


def fetch_scalp_strategy_stats(conn: sqlite3.Connection, strategy: str) -> dict[str, Any]:
    """Агрегаты по strategy в scalp_trades (все время и сегодня UTC)."""
    start = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    cur_all = conn.execute(
        """
        SELECT COUNT(*),
               COALESCE(SUM(CASE WHEN pnl_usdt > 0 THEN 1 ELSE 0 END), 0),
               COALESCE(SUM(CASE WHEN pnl_usdt < 0 THEN 1 ELSE 0 END), 0),
               COALESCE(SUM(pnl_usdt), 0),
               COALESCE(SUM(CASE WHEN pnl_usdt < 0 THEN ABS(pnl_usdt) ELSE 0 END), 0),
               COALESCE(SUM(CASE WHEN pnl_usdt > 0 THEN pnl_usdt ELSE 0 END), 0)
        FROM scalp_trades WHERE strategy = ?
        """,
        (strategy,),
    )
    row = cur_all.fetchone()
    n = int(row[0] or 0)
    wins = int(row[1] or 0)
    losses = int(row[2] or 0)
    total_pnl = float(row[3] or 0)
    gross_loss = float(row[4] or 0)
    gross_win = float(row[5] or 0)
    pf = (gross_win / gross_loss) if gross_loss > 1e-12 else 0.0

    cur_td = conn.execute(
        """
        SELECT COUNT(*),
               COALESCE(SUM(CASE WHEN pnl_usdt > 0 THEN 1 ELSE 0 END), 0),
               COALESCE(SUM(CASE WHEN pnl_usdt < 0 THEN 1 ELSE 0 END), 0),
               COALESCE(SUM(pnl_usdt), 0),
               COALESCE(SUM(fee_usdt), 0),
               COALESCE(AVG(candles_held), 0)
        FROM scalp_trades WHERE strategy = ? AND timestamp_close >= ?
        """,
        (strategy, start),
    )
    t = cur_td.fetchone()
    return {
        "all_trades": n,
        "all_wins": wins,
        "all_losses": losses,
        "all_pnl": total_pnl,
        "win_rate_all": (100.0 * wins / n) if n else 0.0,
        "profit_factor": round(pf, 4) if pf else 0.0,
        "today_trades": int(t[0] or 0),
        "today_wins": int(t[1] or 0),
        "today_losses": int(t[2] or 0),
        "today_pnl": float(t[3] or 0),
        "today_fees": float(t[4] or 0),
        "avg_hold_candles": float(t[5] or 0),
    }
