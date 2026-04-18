"""EMA scalper entry/exit."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from backend.strategy.ema_scalper.indicators import is_active_session
from backend.strategy.ema_scalper.position import EMAScalpPosition

ALLOWED_SYMBOLS = {
    "ETH/USDC:USDC",
    "BTC/USDC:USDC",
    "SOL/USDC:USDC",
}


class EMAScalpSignalEngine:
    def __init__(self, config: dict) -> None:
        self.cfg = config.get("ema_scalper") or {}
        ent = self.cfg.get("entry") or {}
        ex = self.cfg.get("exit") or {}
        rk = self.cfg.get("risk") or {}
        self.ema_period = int(ent.get("ema_period", 9))
        self.vol_mult = float(ent.get("volume_multiplier", 1.5))
        self.min_streak = int(ent.get("min_candles_above_below", 3))
        self.max_streak = int(ent.get("max_candles_above_below", 8))
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
        self.min_candle_body_pct = float(ent.get("min_candle_body_pct", 0.05))
        self.rsi_long_max = float(ent.get("rsi_long_max", 65))
        self.rsi_short_min = float(ent.get("rsi_short_min", 35))
        self.adx_enabled = bool(ent.get("adx_filter_enabled", True))
        self.adx_threshold = float(ent.get("adx_threshold", 20.0))
        self.vwap_max_dist_pct = float(ent.get("vwap_max_distance_pct", 0.9))
        self.macd_enabled = bool(ent.get("macd_filter_enabled", True))
        self.macd_need_hist_rising = bool(ent.get("macd_hist_rising_required", True))
        self.min_volume_pct_rank = float(ent.get("min_volume_percentile", 60.0))
        self.volume_percentile_lb = int(ent.get("volume_percentile_lookback", 40))
        self.higher_tf_min_volume_ratio = float(ent.get("higher_tf_min_volume_ratio", 1.0))
        self.anti_flat_enabled = bool(ent.get("anti_flat_enabled", True))
        self.anti_flat_min_atr_pct = float(ent.get("anti_flat_min_atr_pct", 0.15))
        # strict = расширение дистанции до EMA (агрессивно, часто поздно); loose = тело+направление
        self.momentum_mode = str(ent.get("momentum_mode", "strict")).strip().lower()
        # 0 = выкл.; иначе не входить, если цена слишком далеко от EMA на 5m (% от цены)
        self.entry_max_dist_ema_pct = float(ent.get("entry_max_distance_from_ema_pct", 0) or 0)
        # OTE / Order Block (старший ТФ, см. enrich_indicators_htf_ote_ob в main)
        self.ob_filter_enabled = bool(ent.get("ob_filter_enabled", False))
        self.ote_filter_enabled = bool(ent.get("ote_filter_enabled", False))
        self.min_confidence_score = float(ent.get("min_confidence_score", 60))
        # Если true: при higher_tf_trend == FLAT всё равно смотреть только 5m-сетап (лонг/шорт по своим правилам)
        self.allow_trading_when_higher_tf_flat = bool(ent.get("allow_trading_when_higher_tf_flat", False))
        self.market_structure_enabled = bool(ent.get("market_structure_enabled", False))
        self.trade_sessions_utc: list[Any] = list(ent.get("trade_sessions_utc") or [])
        self.trailing_stop_enabled = bool(ex.get("trailing_stop_enabled", False))
        self.trailing_activation_pct = float(ex.get("trailing_activation_pct", 0.3))
        self.trailing_distance_pct = float(ex.get("trailing_distance_pct", 0.2))

    def _trade_session_ok(self) -> bool:
        if not self.trade_sessions_utc:
            return True
        h = datetime.now(timezone.utc).hour
        return is_active_session(h, self.trade_sessions_utc)

    def _ht_allows_long(self, ht: Any) -> bool:
        if self.market_structure_enabled:
            return True
        if ht == "UP":
            return True
        return bool(self.allow_trading_when_higher_tf_flat and ht == "FLAT")

    def _ht_allows_short(self, ht: Any) -> bool:
        if self.market_structure_enabled:
            return True
        if ht == "DOWN":
            return True
        return bool(self.allow_trading_when_higher_tf_flat and ht == "FLAT")

    def _confluence_eval(self, side: str, ind: dict[str, Any]) -> tuple[bool, str]:
        """Бонус к уверенности: база 40 + OB + OTE + RSI; порог min_confidence_score."""
        if not self.ob_filter_enabled and not self.ote_filter_enabled:
            return True, ""
        if ind.get("ote_ob_unavailable"):
            return False, "ote_ob_unavailable"
        ob_ok = bool(ind.get("price_in_bullish_ob")) if side == "LONG" else bool(ind.get("price_in_bearish_ob"))
        ote_ok = bool(ind.get("in_ote_long")) if side == "LONG" else bool(ind.get("in_ote_short"))
        score = 40
        if self.ob_filter_enabled and ob_ok:
            score += 30
        if self.ote_filter_enabled and ote_ok:
            score += 20
        rsi = float(ind.get("rsi", 50.0))
        if side == "LONG" and rsi < 50:
            score += 10
        if side == "SHORT" and rsi > 50:
            score += 10
        ind["entry_confidence_score"] = float(score)
        if score < self.min_confidence_score:
            return False, f"low_confidence_{score}"
        return True, ""

    def _momentum_long_ok(self, ind: dict[str, Any]) -> bool:
        if self.momentum_mode in ("off", "false", "0", "none"):
            return True
        if self.momentum_mode == "loose":
            return bool(ind.get("momentum_long_loose"))
        return bool(ind.get("momentum_long"))

    def _momentum_short_ok(self, ind: dict[str, Any]) -> bool:
        if self.momentum_mode in ("off", "false", "0", "none"):
            return True
        if self.momentum_mode == "loose":
            return bool(ind.get("momentum_short_loose"))
        return bool(ind.get("momentum_short"))

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
        if symbol not in ALLOWED_SYMBOLS:
            return {"action": "HOLD", "reason": "symbol_not_whitelisted", "indicators": ind}
        qv = float(ind.get("quote_volume_usdt", 0))
        if self.min_quote_vol > 0 and qv < self.min_quote_vol:
            return {"action": "HOLD", "reason": "low_liquidity", "indicators": ind}
        adx = float(ind.get("adx", 0.0))
        if self.adx_enabled and adx < self.adx_threshold:
            return {"action": "HOLD", "reason": "adx_chop", "indicators": ind}
        dvwap = float(ind.get("distance_from_vwap_pct", 0.0))
        if self.vwap_max_dist_pct > 0 and dvwap > self.vwap_max_dist_pct:
            return {"action": "HOLD", "reason": "vwap_stretched", "indicators": ind}
        atr_pct = float(ind.get("atr_pct", 0.0))
        if self.anti_flat_enabled and atr_pct < self.anti_flat_min_atr_pct:
            return {"action": "HOLD", "reason": "flat_market", "indicators": ind}
        ht = ind.get("higher_tf_trend")
        if ht is None:
            return {"action": "HOLD", "reason": "higher_tf_unavailable", "indicators": ind}
        if ht == "FLAT" and not self.allow_trading_when_higher_tf_flat and not self.market_structure_enabled:
            return {"action": "HOLD", "reason": "higher_tf_flat", "indicators": ind}
        if open_count >= self.max_open:
            return {"action": "HOLD", "reason": "max_positions", "indicators": ind}
        if not risk_ok:
            return {"action": "HOLD", "reason": "daily_loss_limit", "indicators": ind}
        if not self._trade_session_ok():
            return {"action": "HOLD", "reason": "outside_session", "indicators": ind}
        h = datetime.now(timezone.utc).hour
        if h in self.no_trade_hours:
            return {"action": "HOLD", "reason": "no_trade_hour", "indicators": ind}
        vr = float(ind.get("volume_ratio", 0))
        if vr < self.vol_mult:
            return {"action": "HOLD", "reason": "volume_filter", "indicators": ind}
        v_rank = float(ind.get("volume_percentile", 0.0))
        if self.min_volume_pct_rank > 0 and v_rank < self.min_volume_pct_rank:
            return {"action": "HOLD", "reason": "low_volume_percentile", "indicators": ind}
        htf_vr = float(ind.get("higher_tf_volume_ratio", 0.0))
        if self.higher_tf_min_volume_ratio > 0 and htf_vr < self.higher_tf_min_volume_ratio:
            return {"action": "HOLD", "reason": "thin_higher_tf_volume", "indicators": ind}
        if last_entry_ts_ms is not None:
            if current_bar_ts_ms - last_entry_ts_ms < self.cooldown_ms:
                return {"action": "HOLD", "reason": "cooldown", "indicators": ind}

        if self.market_structure_enabled:
            ms = str(ind.get("market_structure", "RANGING"))
            if ms == "RANGING":
                return {"action": "HOLD", "reason": "ranging_market", "indicators": ind}

        ema = float(ind["ema_current"])
        close = float(ind["close"])
        ae = int(ind["above_ema_count"])
        be = int(ind["below_ema_count"])
        rsi = float(ind.get("rsi", 50.0))
        body_pct = float(ind.get("candle_body_pct", 0.0))
        macd = float(ind.get("macd", 0.0))
        macd_signal = float(ind.get("macd_signal", 0.0))
        macd_hist = float(ind.get("macd_hist", 0.0))
        macd_hist_prev = float(ind.get("macd_hist_prev", 0.0))

        # Перегрев: слишком долго подряд у EMA — не догонять
        if close > ema and ae > self.max_streak:
            return {"action": "HOLD", "reason": "ema_overextended", "indicators": ind}
        if close < ema and be > self.max_streak:
            return {"action": "HOLD", "reason": "ema_overextended", "indicators": ind}

        if self.entry_max_dist_ema_pct > 0:
            if close > ema:
                dist_pct = (close - ema) / max(ema, 1e-12) * 100.0
                if dist_pct > self.entry_max_dist_ema_pct:
                    return {"action": "HOLD", "reason": "ema_stretched", "indicators": ind}
            elif close < ema:
                dist_pct = (ema - close) / max(ema, 1e-12) * 100.0
                if dist_pct > self.entry_max_dist_ema_pct:
                    return {"action": "HOLD", "reason": "ema_stretched", "indicators": ind}

        long_setup = (
            close > ema
            and ae >= self.min_streak
            and ind.get("is_green")
            and self._momentum_long_ok(ind)
        )
        short_setup = (
            close < ema
            and be >= self.min_streak
            and ind.get("is_red")
            and self._momentum_short_ok(ind)
        )

        if long_setup:
            if not self._ht_allows_long(ht):
                return {"action": "HOLD", "reason": "against_higher_tf", "indicators": ind}
            if self.macd_enabled:
                if not (macd > macd_signal and macd_hist > 0):
                    return {"action": "HOLD", "reason": "macd_not_confirmed", "indicators": ind}
                if self.macd_need_hist_rising and macd_hist < macd_hist_prev:
                    return {"action": "HOLD", "reason": "macd_hist_fading", "indicators": ind}
            if rsi > self.rsi_long_max:
                return {"action": "HOLD", "reason": "rsi_overbought", "indicators": ind}
            if body_pct < self.min_candle_body_pct:
                return {"action": "HOLD", "reason": "doji_candle", "indicators": ind}
            if self.market_structure_enabled and ind.get("market_structure") != "BULLISH":
                return {"action": "HOLD", "reason": "structure_bearish", "indicators": ind}
            ok_c, reason_c = self._confluence_eval("LONG", ind)
            if not ok_c:
                return {"action": "HOLD", "reason": reason_c, "indicators": ind}
            return {"action": "OPEN_LONG", "reason": "ema_long", "indicators": ind}

        if short_setup:
            if not self._ht_allows_short(ht):
                return {"action": "HOLD", "reason": "against_higher_tf", "indicators": ind}
            if self.macd_enabled:
                if not (macd < macd_signal and macd_hist < 0):
                    return {"action": "HOLD", "reason": "macd_not_confirmed", "indicators": ind}
                if self.macd_need_hist_rising and macd_hist > macd_hist_prev:
                    return {"action": "HOLD", "reason": "macd_hist_fading", "indicators": ind}
            if rsi < self.rsi_short_min:
                return {"action": "HOLD", "reason": "rsi_oversold", "indicators": ind}
            if body_pct < self.min_candle_body_pct:
                return {"action": "HOLD", "reason": "doji_candle", "indicators": ind}
            if self.market_structure_enabled and ind.get("market_structure") != "BEARISH":
                return {"action": "HOLD", "reason": "structure_bullish", "indicators": ind}
            ok_c, reason_c = self._confluence_eval("SHORT", ind)
            if not ok_c:
                return {"action": "HOLD", "reason": reason_c, "indicators": ind}
            return {"action": "OPEN_SHORT", "reason": "ema_short", "indicators": ind}

        return {"action": "HOLD", "reason": "no_setup", "indicators": ind}

    def check_exit(
        self, pos: EMAScalpPosition, ind: dict[str, Any], current_bar_ts_ms: int
    ) -> dict[str, Any]:
        if ind.get("warming_up"):
            return {"should_exit": False, "reason": None, "pnl_pct": 0.0}
        px = float(pos.current_price)
        if self.trailing_stop_enabled:
            pos.update_trailing_stop(px, self.trailing_activation_pct, self.trailing_distance_pct)
        if pos.side == "LONG":
            if px >= float(pos.tp_price):
                return {"should_exit": True, "reason": "TP", "pnl_pct": pos.pnl_pct()}
            if px <= float(pos.sl_price):
                return {"should_exit": True, "reason": "SL", "pnl_pct": pos.pnl_pct()}
        else:
            if px <= float(pos.tp_price):
                return {"should_exit": True, "reason": "TP", "pnl_pct": pos.pnl_pct()}
            if px >= float(pos.sl_price):
                return {"should_exit": True, "reason": "SL", "pnl_pct": pos.pnl_pct()}
        pnl = pos.pnl_pct()
        if pnl >= self.tp_pct:
            return {"should_exit": True, "reason": "TP", "pnl_pct": pnl}
        if pnl <= -self.sl_pct:
            return {"should_exit": True, "reason": "SL", "pnl_pct": pnl}
        bars = pos.bars_held(current_bar_ts_ms)
        hold_limit = int(getattr(pos, "max_hold_candles", self.max_hold) or self.max_hold)
        if bars >= hold_limit:
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
        ht = ind.get("higher_tf_trend")
        if ht is None:
            return {"signal_ready": False, "side_ready": None, "reason": "higher_tf_unavailable"}
        if ht == "FLAT" and not self.allow_trading_when_higher_tf_flat and not self.market_structure_enabled:
            return {"signal_ready": False, "side_ready": None, "reason": "higher_tf_flat"}
        if not self._trade_session_ok():
            return {"signal_ready": False, "side_ready": None, "reason": "outside_session"}
        qv = float(ind.get("quote_volume_usdt", 0))
        if self.min_quote_vol > 0 and qv < self.min_quote_vol:
            return {"signal_ready": False, "side_ready": None, "reason": "low_liquidity"}
        adx = float(ind.get("adx", 0.0))
        if self.adx_enabled and adx < self.adx_threshold:
            return {"signal_ready": False, "side_ready": None, "reason": "adx_chop"}
        dvwap = float(ind.get("distance_from_vwap_pct", 0.0))
        if self.vwap_max_dist_pct > 0 and dvwap > self.vwap_max_dist_pct:
            return {"signal_ready": False, "side_ready": None, "reason": "vwap_stretched"}
        atr_pct = float(ind.get("atr_pct", 0.0))
        if self.anti_flat_enabled and atr_pct < self.anti_flat_min_atr_pct:
            return {"signal_ready": False, "side_ready": None, "reason": "flat_market"}
        h = datetime.now(timezone.utc).hour
        if h in self.no_trade_hours:
            return {"signal_ready": False, "side_ready": None, "reason": "no_trade_hour"}
        vr = float(ind.get("volume_ratio", 0))
        if vr < self.vol_mult:
            return {"signal_ready": False, "side_ready": None, "reason": "volume_filter"}
        v_rank = float(ind.get("volume_percentile", 0.0))
        if self.min_volume_pct_rank > 0 and v_rank < self.min_volume_pct_rank:
            return {"signal_ready": False, "side_ready": None, "reason": "low_volume_percentile"}
        htf_vr = float(ind.get("higher_tf_volume_ratio", 0.0))
        if self.higher_tf_min_volume_ratio > 0 and htf_vr < self.higher_tf_min_volume_ratio:
            return {"signal_ready": False, "side_ready": None, "reason": "thin_higher_tf_volume"}
        if self.market_structure_enabled:
            ms = str(ind.get("market_structure", "RANGING"))
            if ms == "RANGING":
                return {"signal_ready": False, "side_ready": None, "reason": "ranging_market"}
        ema = float(ind["ema_current"])
        close = float(ind["close"])
        ae = int(ind["above_ema_count"])
        be = int(ind["below_ema_count"])
        rsi = float(ind.get("rsi", 50.0))
        body_pct = float(ind.get("candle_body_pct", 0.0))
        macd = float(ind.get("macd", 0.0))
        macd_signal = float(ind.get("macd_signal", 0.0))
        macd_hist = float(ind.get("macd_hist", 0.0))
        macd_hist_prev = float(ind.get("macd_hist_prev", 0.0))
        if close > ema and ae > self.max_streak:
            return {"signal_ready": False, "side_ready": None, "reason": "ema_overextended"}
        if close < ema and be > self.max_streak:
            return {"signal_ready": False, "side_ready": None, "reason": "ema_overextended"}

        if self.entry_max_dist_ema_pct > 0:
            if close > ema:
                dist_pct = (close - ema) / max(ema, 1e-12) * 100.0
                if dist_pct > self.entry_max_dist_ema_pct:
                    return {"signal_ready": False, "side_ready": None, "reason": "ema_stretched"}
            elif close < ema:
                dist_pct = (ema - close) / max(ema, 1e-12) * 100.0
                if dist_pct > self.entry_max_dist_ema_pct:
                    return {"signal_ready": False, "side_ready": None, "reason": "ema_stretched"}

        long_setup = (
            close > ema
            and ae >= self.min_streak
            and ind.get("is_green")
            and self._momentum_long_ok(ind)
        )
        short_setup = (
            close < ema
            and be >= self.min_streak
            and ind.get("is_red")
            and self._momentum_short_ok(ind)
        )

        if long_setup:
            if not self._ht_allows_long(ht):
                return {"signal_ready": False, "side_ready": None, "reason": "against_higher_tf"}
            if self.macd_enabled:
                if not (macd > macd_signal and macd_hist > 0):
                    return {"signal_ready": False, "side_ready": None, "reason": "macd_not_confirmed"}
                if self.macd_need_hist_rising and macd_hist < macd_hist_prev:
                    return {"signal_ready": False, "side_ready": None, "reason": "macd_hist_fading"}
            if rsi > self.rsi_long_max:
                return {"signal_ready": False, "side_ready": None, "reason": "rsi_overbought"}
            if body_pct < self.min_candle_body_pct:
                return {"signal_ready": False, "side_ready": None, "reason": "doji_candle"}
            if self.market_structure_enabled and ind.get("market_structure") != "BULLISH":
                return {"signal_ready": False, "side_ready": None, "reason": "structure_bearish"}
            ok_c, reason_c = self._confluence_eval("LONG", ind)
            if not ok_c:
                return {"signal_ready": False, "side_ready": None, "reason": reason_c}
            return {"signal_ready": True, "side_ready": "LONG", "reason": "long_setup"}

        if short_setup:
            if not self._ht_allows_short(ht):
                return {"signal_ready": False, "side_ready": None, "reason": "against_higher_tf"}
            if self.macd_enabled:
                if not (macd < macd_signal and macd_hist < 0):
                    return {"signal_ready": False, "side_ready": None, "reason": "macd_not_confirmed"}
                if self.macd_need_hist_rising and macd_hist > macd_hist_prev:
                    return {"signal_ready": False, "side_ready": None, "reason": "macd_hist_fading"}
            if rsi < self.rsi_short_min:
                return {"signal_ready": False, "side_ready": None, "reason": "rsi_oversold"}
            if body_pct < self.min_candle_body_pct:
                return {"signal_ready": False, "side_ready": None, "reason": "doji_candle"}
            if self.market_structure_enabled and ind.get("market_structure") != "BEARISH":
                return {"signal_ready": False, "side_ready": None, "reason": "structure_bullish"}
            ok_c, reason_c = self._confluence_eval("SHORT", ind)
            if not ok_c:
                return {"signal_ready": False, "side_ready": None, "reason": reason_c}
            return {"signal_ready": True, "side_ready": "SHORT", "reason": "short_setup"}

        return {"signal_ready": False, "side_ready": None, "reason": "no_setup"}
