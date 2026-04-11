"""Risk checks, max drawdown, комиссии за день"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone


class RiskManager:
    def __init__(self, config: dict, conn: sqlite3.Connection) -> None:
        self._config = config
        self._conn = conn
        self._paused = False
        rk = config.get("risk") or {}
        self._max_total = float(rk.get("max_total_exposure", 2000))
        self._max_daily_loss_pct = float(rk.get("max_daily_loss_pct", 10.0))
        self._commission_pct_side = float(rk.get("commission_pct", 0.1))
        self._open_notional: float = 0.0
        self._commission_today_usdt: float = 0.0

    def set_pause(self, paused: bool) -> None:
        self._paused = paused

    def is_paused(self) -> bool:
        return self._paused

    def set_open_notional(self, usdt: float) -> None:
        self._open_notional = usdt

    def add_commission(self, usdt: float) -> None:
        self._commission_today_usdt += float(usdt)

    @property
    def commission_today_usdt(self) -> float:
        return self._commission_today_usdt

    def round_trip_fee_rate(self) -> float:
        """Доля от номинала: 2 стороны × commission_pct (проценты)."""
        return 2.0 * (self._commission_pct_side / 100.0)

    def _deposit_usdt(self) -> float:
        for key in ("ema_scalper", "breakout", "scalping"):
            sec = self._config.get(key) or {}
            rk = sec.get("risk") or {}
            if rk.get("balance_usdt") is not None:
                return float(rk["balance_usdt"])
        sc = self._config.get("scalping") or {}
        return float(sc.get("deposit_usdt", 50))

    def _daily_realized_pnl_usdt(self) -> float:
        start = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        cur = self._conn.execute(
            "SELECT COALESCE(SUM(pnl_usdt), 0) FROM trades WHERE timestamp >= ? AND action = 'CLOSE'",
            (start,),
        )
        row = cur.fetchone()
        return float(row[0] or 0)

    def daily_pnl_pct_vs_deposit(self) -> float:
        d = self._deposit_usdt()
        base = max(d, 1.0)
        return self._daily_realized_pnl_usdt() / base * 100.0

    def check_can_open(self, pair_id: str, notional: float, legs: int = 2) -> tuple[bool, str]:
        if self._paused:
            return False, "bot is paused"
        if self._open_notional + notional * legs > self._max_total:
            return False, "max_total_exposure exceeded"
        daily = self._daily_realized_pnl_usdt()
        base = max(self._deposit_usdt(), 1.0)
        daily_pct = daily / base * 100.0
        if daily_pct <= -self._max_daily_loss_pct:
            return False, "daily loss limit"
        return True, ""

    def check_emergency_stop(self, positions: list) -> bool:
        st = self._config.get("strategy") or {}
        stop_z = float(st.get("stop_zscore", 3.0))
        for p in positions:
            z = float(p.get("current_zscore", 0.0))
            if abs(z) > stop_z:
                return True
        return False
