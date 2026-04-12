"""EMA scalper entry/exit."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from backend.strategy.ema_scalper.position import EMAScalpPosition


class EMAScalpSignalEngine:
    def __init__(self, config: dict) -> None:
        self.cfg = config.get("ema_scalper") or {}
        ent = self.cfg.get("entry") or {}
        ex = self.cfg.get("exit") or {}
        rk = self.cfg.get("risk") or {}
        self.ema_period = int(ent.get("ema_period", 9))
        self.vol_mult = float(ent.get("volume_multiplier", 1.5))
        self.min_streak = int(ent.get("min_candles_above_below", 3))
        self.no_trade_hours = list(ent.get("no_trade_hours_utc") or [])
        self.min_quote_vol = float(ent.get("min_volume_usdt", 0))
        self.cooldown_candles = int(ent.get("cooldown_candles", 4))
        self.tp_pct = float(ex.get("take_profit_pct", 1.5))
        self.sl_pct = float(ex.get("stop_loss_pct", 0.5))
        self.max_hold = int(ex.get("max_hold_candles", 8))
        self.ema_cross_exit = bool(ex.get("ema_cross_exit", False))
        self.tf_sec = self._tf_seconds(self.cfg.get("timeframe", "5m"))
        self.max_open = int(rk.get("max_open_positions", 2))
        self.cooldown_ms = self.cooldown_candles * self.tf_sec * 1000

    def _tf_seconds(self, tf: str) -> int:
        if tf.endswith("m"):
            return int(tf[:-1] or "5") * 60
        if tf.endswith("h"):
            return int(tf[:-1] or "1") * 3600
        return 300

    def check_entry(
        self,
        ind: dict[str, Any],
        symbol: str,
        open_count: int,
        last_entry_ts_ms: int | None,
        current_bar_ts_ms: int,
        risk_ok: bool,
    ) -> dict[str, Any]:
        if ind.get("warming_up"):
            return {"action": "HOLD", "reason": "warmup", "indicators": ind}
        if open_count >= self.max_open:
            return {"action": "HOLD", "reason": "max_positions", "indicators": ind}
        if not risk_ok:
            return {"action": "HOLD", "reason": "daily_loss_limit", "indicators": ind}
        h = datetime.now(timezone.utc).hour
        if h in self.no_trade_hours:
            return {"action": "HOLD", "reason": "no_trade_hour", "indicators": ind}
        qv = float(ind.get("quote_volume_usdt", 0))
        if self.min_quote_vol > 0 and qv < self.min_quote_vol:
            return {"action": "HOLD", "reason": "low_liquidity", "indicators": ind}
        vr = float(ind.get("volume_ratio", 0))
        if vr < self.vol_mult:
            return {"action": "HOLD", "reason": "volume_filter", "indicators": ind}
        if last_entry_ts_ms is not None:
            if current_bar_ts_ms - last_entry_ts_ms < self.cooldown_ms:
                return {"action": "HOLD", "reason": "cooldown", "indicators": ind}

        ema = float(ind["ema_current"])
        close = float(ind["close"])
        mom_long = bool(ind.get("momentum_long"))
        mom_short = bool(ind.get("momentum_short"))
        if (
            close > ema
            and int(ind["above_ema_count"]) >= self.min_streak
            and ind.get("is_green")
            and mom_long
        ):
            return {"action": "OPEN_LONG", "reason": "ema_long", "indicators": ind}
        if (
            close < ema
            and int(ind["below_ema_count"]) >= self.min_streak
            and ind.get("is_red")
            and mom_short
        ):
            return {"action": "OPEN_SHORT", "reason": "ema_short", "indicators": ind}
        return {"action": "HOLD", "reason": "no_setup", "indicators": ind}

    def check_exit(
        self, pos: EMAScalpPosition, ind: dict[str, Any], current_bar_ts_ms: int
    ) -> dict[str, Any]:
        if ind.get("warming_up"):
            return {"should_exit": False, "reason": None, "pnl_pct": 0.0}
        pnl = pos.pnl_pct()
        if pnl >= self.tp_pct:
            return {"should_exit": True, "reason": "TP", "pnl_pct": pnl}
        if pnl <= -self.sl_pct:
            return {"should_exit": True, "reason": "SL", "pnl_pct": pnl}
        bars = pos.bars_held(current_bar_ts_ms)
        if bars >= self.max_hold:
            return {"should_exit": True, "reason": "TIME", "pnl_pct": pnl}
        if self.ema_cross_exit:
            ema = float(ind["ema_current"])
            close = float(ind["close"])
            if pos.side == "LONG" and close < ema:
                return {"should_exit": True, "reason": "EMA_CROSS", "pnl_pct": pnl}
            if pos.side == "SHORT" and close > ema:
                return {"should_exit": True, "reason": "EMA_CROSS", "pnl_pct": pnl}
        return {"should_exit": False, "reason": None, "pnl_pct": pnl}

    def preview_panel_status(self, ind: dict[str, Any]) -> dict[str, Any]:
        """Для UI: готовность к входу без проверки позиции/риска/кулдауна."""
        if ind.get("warming_up"):
            return {"signal_ready": False, "side_ready": None, "reason": "warmup"}
        h = datetime.now(timezone.utc).hour
        if h in self.no_trade_hours:
            return {"signal_ready": False, "side_ready": None, "reason": "no_trade_hour"}
        qv = float(ind.get("quote_volume_usdt", 0))
        if self.min_quote_vol > 0 and qv < self.min_quote_vol:
            return {"signal_ready": False, "side_ready": None, "reason": "low_liquidity"}
        vr = float(ind.get("volume_ratio", 0))
        if vr < self.vol_mult:
            return {"signal_ready": False, "side_ready": None, "reason": "volume_filter"}
        ema = float(ind["ema_current"])
        close = float(ind["close"])
        if (
            close > ema
            and int(ind["above_ema_count"]) >= self.min_streak
            and ind.get("is_green")
            and ind.get("momentum_long")
        ):
            return {"signal_ready": True, "side_ready": "LONG", "reason": "long_setup"}
        if (
            close < ema
            and int(ind["below_ema_count"]) >= self.min_streak
            and ind.get("is_red")
            and ind.get("momentum_short")
        ):
            return {"signal_ready": True, "side_ready": "SHORT", "reason": "short_setup"}
        return {"signal_ready": False, "side_ready": None, "reason": "no_setup"}
