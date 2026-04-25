"""SQLite: сделки EMA Scalper."""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_BOT_ROOT = Path(__file__).resolve().parent.parent.parent
_DB_PATH = _BOT_ROOT / "data" / "bot.sqlite3"


def get_connection() -> sqlite3.Connection:
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(_DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def init_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS scalp_trades (
            id                        INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp_open            TEXT,
            timestamp_close           TEXT,
            symbol                    TEXT,
            strategy                  TEXT DEFAULT 'ema_scalper',
            side                      TEXT,
            entry_price               REAL,
            exit_price                REAL,
            tp_price                  REAL,
            sl_price                  REAL,
            size_usdt                 REAL,
            notional                  REAL,
            leverage                  INTEGER,
            candles_held              INTEGER,
            pnl_usdt                  REAL,
            pnl_pct                   REAL,
            fee_usdt                  REAL,
            close_reason              TEXT,
            trailing_active           INTEGER DEFAULT 0,
            dry_run                   INTEGER DEFAULT 1,
            ema_at_entry              REAL,
            volume_ratio_at_entry     REAL,
            above_ema_at_entry        INTEGER,
            rsi_at_entry              REAL,
            structure_15m_at_entry    TEXT,
            trend_1h_at_entry         TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_scalp_symbol   ON scalp_trades(symbol);
        CREATE INDEX IF NOT EXISTS idx_scalp_ts       ON scalp_trades(timestamp_open);
        CREATE INDEX IF NOT EXISTS idx_scalp_strategy ON scalp_trades(strategy);
        """
    )
    conn.commit()


def log_scalp_trade(conn: sqlite3.Connection, pos: Any, dry_run: bool) -> None:
    if not hasattr(pos, "entry_ts"):
        return
    now = datetime.now(timezone.utc).isoformat()
    fee = float(pos.notional) * 0.0001 * 2
    conn.execute(
        """
        INSERT INTO scalp_trades (
            timestamp_open, timestamp_close, symbol, strategy, side,
            entry_price, exit_price, tp_price, sl_price, size_usdt, notional, leverage,
            candles_held, pnl_usdt, pnl_pct, fee_usdt, close_reason, trailing_active, dry_run,
            ema_at_entry, volume_ratio_at_entry, above_ema_at_entry, rsi_at_entry,
            structure_15m_at_entry, trend_1h_at_entry
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            datetime.fromtimestamp(pos.entry_ts, tz=timezone.utc).isoformat(),
            now,
            pos.symbol,
            "ema_scalper",
            pos.side,
            pos.entry_price,
            pos.exit_price,
            pos.tp_price,
            pos.sl_price,
            pos.size_usdt,
            pos.notional,
            pos.leverage,
            pos.candles_held,
            pos.pnl_usdt,
            pos.pnl_pct * 100,
            fee,
            pos.close_reason,
            1 if pos.trailing_active else 0,
            1 if dry_run else 0,
            pos.ema_at_entry,
            pos.volume_ratio_at_entry,
            pos.above_ema_at_entry,
            pos.rsi_at_entry,
            pos.structure_at_entry,
            pos.trend_1h_at_entry,
        ),
    )
    conn.commit()


def get_recent_trades(conn: sqlite3.Connection, limit: int = 50) -> list[dict[str, Any]]:
    cur = conn.execute(
        "SELECT * FROM scalp_trades ORDER BY id DESC LIMIT ?",
        (limit,),
    )
    return [dict(r) for r in cur.fetchall()]


def get_pnl_today(conn: sqlite3.Connection) -> float:
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    cur = conn.execute(
        "SELECT COALESCE(SUM(pnl_usdt), 0) FROM scalp_trades WHERE date(timestamp_close) = ?",
        (day,),
    )
    row = cur.fetchone()
    return float(row[0] if row else 0)


def get_daily_loss_exceeded(conn: sqlite3.Connection, balance: float, max_loss_pct: float) -> bool:
    pnl = get_pnl_today(conn)
    limit_usdt = balance * (max_loss_pct / 100.0)
    return pnl <= -limit_usdt


def get_stats(conn: sqlite3.Connection) -> dict[str, Any]:
    cur = conn.execute("SELECT COUNT(*), COALESCE(SUM(pnl_usdt),0) FROM scalp_trades")
    total_n, total_pnl = cur.fetchone()
    total_n = int(total_n or 0)
    total_pnl = float(total_pnl or 0)

    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    cur = conn.execute(
        """
        SELECT COUNT(*), COALESCE(SUM(pnl_usdt),0),
               SUM(CASE WHEN pnl_usdt > 0 THEN 1 ELSE 0 END),
               SUM(CASE WHEN pnl_usdt < 0 THEN 1 ELSE 0 END),
               COALESCE(SUM(fee_usdt), 0)
        FROM scalp_trades WHERE date(timestamp_close) = ?
        """,
        (day,),
    )
    row = cur.fetchone()
    td_n = int(row[0] or 0)
    td_pnl = float(row[1] or 0)
    wins = int(row[2] or 0)
    losses = int(row[3] or 0)
    fees_td = float(row[4] or 0)

    cur = conn.execute(
        "SELECT SUM(CASE WHEN pnl_usdt > 0 THEN pnl_usdt ELSE 0 END), "
        "SUM(CASE WHEN pnl_usdt < 0 THEN -pnl_usdt ELSE 0 END) FROM scalp_trades"
    )
    gw, gl = cur.fetchone()
    gw = float(gw or 0)
    gl = float(gl or 0)
    profit_factor = (gw / gl) if gl > 1e-12 else (gw if gw > 0 else 0.0)

    cur = conn.execute("SELECT AVG(candles_held) FROM scalp_trades")
    avg_hold = float(cur.fetchone()[0] or 0)

    win_rate_td = (wins / td_n * 100) if td_n else 0.0
    cur = conn.execute(
        "SELECT SUM(CASE WHEN pnl_usdt > 0 THEN 1 ELSE 0 END) FROM scalp_trades"
    )
    all_wins = int(cur.fetchone()[0] or 0)
    win_rate_all = (all_wins / total_n * 100) if total_n else 0.0

    return {
        "trades_today": td_n,
        "wins_today": wins,
        "losses_today": losses,
        "pnl_today": td_pnl,
        "win_rate_today": win_rate_td,
        "pnl_alltime": total_pnl,
        "win_rate_alltime": win_rate_all,
        "profit_factor": profit_factor,
        "avg_hold_candles": avg_hold,
        "fees_today": fees_td,
    }
