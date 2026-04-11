type Pos = {
  symbol: string;
  side: string;
  entry_price: number;
  current_price: number;
  tp_price: number;
  sl_price: number;
  unrealized_pnl?: number;
  unrealized_pnl_pct?: number;
  open_minutes?: number;
  status?: string;
};

function progressToTp(p: Pos): number {
  const e = p.entry_price;
  const c = p.current_price;
  const tp = p.tp_price;
  const sl = p.sl_price;
  if (p.side === "LONG") {
    const num = c - e;
    const den = tp - e;
    if (Math.abs(den) < 1e-12) return 0;
    return Math.max(0, Math.min(100, (num / den) * 100));
  }
  const num = e - c;
  const den = e - sl;
  if (Math.abs(den) < 1e-12) return 0;
  return Math.max(0, Math.min(100, (num / den) * 100));
}

export default function BreakoutPositions({
  positions,
  sendMessage,
}: {
  positions: Pos[];
  sendMessage: (msg: Record<string, unknown>) => void;
}) {
  const open = positions.filter((x) => x.status === "OPEN");
  if (!open.length) {
    return (
      <div className="text-gray-500 text-xs p-2 border border-gray-800 rounded">
        Breakout: нет открытых позиций
      </div>
    );
  }
  return (
    <div className="grid gap-2">
      {open.map((p) => {
        const prog = progressToTp(p);
        const pnl = p.unrealized_pnl ?? 0;
        const pnlOk = pnl >= 0;
        const mins = p.open_minutes ?? 0;
        const h = Math.floor(mins / 60);
        const m = mins % 60;
        return (
          <div
            key={p.symbol}
            className="border border-gray-800 rounded p-3 bg-terminal-bg/80 text-xs"
          >
            <div className="flex justify-between items-start mb-2">
              <span>
                {p.side === "LONG" ? "▲ LONG" : "▼ SHORT"} {p.symbol}
              </span>
              <span className="text-gray-500">open</span>
            </div>
            <div className="mb-2">
              Вход ${p.entry_price.toFixed(2)} → Сейчас ${p.current_price.toFixed(2)}
            </div>
            <div className="text-[10px] text-gray-500 mb-1">
              TP ${p.tp_price.toFixed(2)}
            </div>
            <div className="h-2 bg-gray-900 rounded overflow-hidden mb-1">
              <div
                className={`h-full ${pnlOk ? "bg-emerald-500/80" : "bg-rose-500/80"}`}
                style={{ width: `${prog}%` }}
              />
            </div>
            <div className="flex justify-between text-[10px] text-gray-500">
              <span>SL ${p.sl_price.toFixed(2)}</span>
              <span className={pnlOk ? "text-emerald-400" : "text-rose-400"}>
                {(p.unrealized_pnl_pct ?? 0).toFixed(2)}%
              </span>
            </div>
            <div className="flex justify-between items-center mt-2">
              <span className="text-gray-500">
                {h}ч {m}м
              </span>
              <button
                type="button"
                className="px-2 py-1 border border-rose-700 text-rose-400 rounded hover:bg-rose-950"
                onClick={() => sendMessage({ action: "close_breakout", symbol: p.symbol })}
              >
                ✕ Закрыть
              </button>
            </div>
          </div>
        );
      })}
    </div>
  );
}
