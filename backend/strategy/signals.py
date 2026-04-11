"""Stat-Arb: z-score spread signals (SignalEngine.get_signal)."""
from __future__ import annotations

import math
from typing import Any


class SignalEngine:
    def __init__(self, config: dict) -> None:
        st = config.get("strategy") or {}
        self.entry_z = float(st.get("entry_zscore", 1.5))
        self.exit_z = float(st.get("exit_zscore", 0.3))
        self.stop_z = float(st.get("stop_zscore", 3.0))

    def get_signal(self, metrics: dict[str, Any]) -> dict[str, Any]:
        z_raw = metrics.get("zscore")
        if z_raw is None or isinstance(z_raw, float) and (math.isnan(z_raw) or z_raw != z_raw):
            return {
                "action": "HOLD",
                "reason": "no z-score",
                "zscore": float("nan"),
                "confidence": 0.0,
            }
        z = float(z_raw)
        hurst = float(metrics.get("hurst", 0.5))
        coint = bool(metrics.get("cointegrated", False))
        p_val = float(metrics.get("p_value", 1.0))
        has_pos = bool(metrics.get("has_open_position", False))

        if has_pos:
            az = abs(z)
            if az < self.exit_z:
                return {
                    "action": "CLOSE",
                    "reason": f"|z|={az:.3f} < exit {self.exit_z} (revert)",
                    "zscore": z,
                    "confidence": 0.85,
                }
            if az > self.stop_z:
                return {
                    "action": "CLOSE",
                    "reason": f"emergency |z|={az:.3f} > stop {self.stop_z}",
                    "zscore": z,
                    "confidence": 1.0,
                }
            return {
                "action": "HOLD",
                "reason": "position open, within bands",
                "zscore": z,
                "confidence": 0.35,
            }

        conf = 0.25
        if hurst < 0.5:
            conf += 0.2
        if coint and p_val < 0.05:
            conf += 0.25
        else:
            return {
                "action": "HOLD",
                "reason": f"filters: hurst={hurst:.3f} coint={coint} p={p_val:.4f}",
                "zscore": z,
                "confidence": min(conf, 0.5),
            }
        if hurst >= 0.5:
            return {
                "action": "HOLD",
                "reason": f"hurst={hurst:.3f} >= 0.5 (trending)",
                "zscore": z,
                "confidence": 0.2,
            }

        if z > self.entry_z:
            return {
                "action": "OPEN_SHORT_A_LONG_B",
                "reason": f"z={z:.3f} > +entry {self.entry_z} (short spread)",
                "zscore": z,
                "confidence": min(0.65 + (abs(z) - self.entry_z) * 0.05, 0.95),
            }
        if z < -self.entry_z:
            return {
                "action": "OPEN_LONG_A_SHORT_B",
                "reason": f"z={z:.3f} < -entry {self.entry_z} (long spread)",
                "zscore": z,
                "confidence": min(0.65 + (abs(z) - self.entry_z) * 0.05, 0.95),
            }
        return {
            "action": "HOLD",
            "reason": f"|z|={abs(z):.3f} inside entry band",
            "zscore": z,
            "confidence": 0.3,
        }


__all__ = ["SignalEngine"]
