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

function baseLabel(sym: string): string {
  const base = sym.split("/")[0] ?? sym;
  return base.replace(/^XYZ-/, "");
}

export default function EMAStatusBar({
  indicators,
  watchlist = [],
}: {
  indicators: Record<string, IndRow>;
  /** Все пары из config; для отсутствующих в indicators — строка «прогрев» */
  watchlist?: string[];
}) {
  const order =
    watchlist.length > 0
      ? watchlist
      : Object.keys(indicators).sort();
  const seen = new Set<string>();
  const rows: { sym: string; ind?: IndRow }[] = [];
  for (const sym of order) {
    if (seen.has(sym)) continue;
    seen.add(sym);
    rows.push({ sym, ind: indicators[sym] });
  }
  for (const sym of Object.keys(indicators)) {
    if (seen.has(sym)) continue;
    seen.add(sym);
    rows.push({ sym, ind: indicators[sym] });
  }
  if (!rows.length) {
    return <div className="text-gray-500 text-xs py-1">EMA: нет пар в config</div>;
  }
  return (
    <div className="flex flex-col gap-1 text-xs">
      {rows.map(({ sym, ind }) => {
        if (!ind) {
          return (
            <div
              key={sym}
              className="flex flex-wrap items-center gap-x-3 gap-y-1 border-b border-gray-900 pb-1 font-mono text-gray-500"
            >
              <span className="text-amber-400/80">{baseLabel(sym)}</span>
              <span className="text-gray-500">|</span>
              <span>прогрев данных…</span>
            </div>
          );
        }
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
            <span className="text-amber-400">{baseLabel(sym)}</span>
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
