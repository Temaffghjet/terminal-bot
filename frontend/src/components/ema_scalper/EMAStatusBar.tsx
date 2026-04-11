type IndRow = {
  ema_current?: number;
  close?: number;
  volume_ratio?: number;
  above_ema_count?: number;
  below_ema_count?: number;
  signal_ready?: boolean;
  side_ready?: string | null;
  reason?: string;
};

export default function EMAStatusBar({ indicators }: { indicators: Record<string, IndRow> }) {
  const rows = Object.entries(indicators);
  if (!rows.length) {
    return <div className="text-gray-500 text-xs py-1">EMA: нет индикаторов (warmup)</div>;
  }
  return (
    <div className="flex flex-col gap-1 text-xs">
      {rows.map(([sym, ind]) => {
        const ema = ind.ema_current ?? 0;
        const close = ind.close ?? 0;
        const up = close >= ema;
        const vol = ind.volume_ratio ?? 0;
        const streakUp = ind.above_ema_count ?? 0;
        const streakDn = ind.below_ema_count ?? 0;
        const ready = ind.signal_ready && ind.side_ready === "LONG";
        const readyS = ind.signal_ready && ind.side_ready === "SHORT";
        let badge = (
          <span className="text-gray-600 border border-gray-700 px-1 rounded">○ ОЖИДАНИЕ</span>
        );
        if (ready) {
          badge = (
            <span className="text-emerald-400 border border-emerald-700 px-1 rounded animate-pulse">
              ● LONG READY
            </span>
          );
        } else if (readyS) {
          badge = (
            <span className="text-rose-400 border border-rose-700 px-1 rounded animate-pulse">
              ● SHORT READY
            </span>
          );
        }
        return (
          <div
            key={sym}
            className="flex flex-wrap items-center gap-x-3 gap-y-1 border-b border-gray-900 pb-1 font-mono"
          >
            <span className="text-amber-400">{sym.split("/")[0]}</span>
            <span className="text-gray-500">|</span>
            <span>EMA ${ema.toFixed(2)}</span>
            <span className="text-gray-500">|</span>
            <span>
              Цена ${close.toFixed(2)} {up ? "▲" : "▼"}
            </span>
            <span className="text-gray-500">|</span>
            <span>
              Vol {vol.toFixed(2)}x {vol >= 1.2 ? "✓" : ""}
            </span>
            <span className="text-gray-500">|</span>
            <span>
              Стрик {streakUp ? `${streakUp}↑` : `${streakDn}↓`}
            </span>
            <span className="text-gray-500">|</span>
            {badge}
          </div>
        );
      })}
    </div>
  );
}
