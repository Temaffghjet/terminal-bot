import { formatEmaEntryReason } from "./emaEntryReason";

type Pos = {
  symbol: string;
  side: string;
  entry_price: number;
  current_price: number;
  tp_price: number;
  sl_price: number;
  pnl_pct?: number;
  pnl_usdt?: number;
  candles_held?: number;
  max_hold_candles?: number;
  leverage?: number;
  /** маржа (реальные деньги) */
  size_usdt?: number;
  /** номинал позиции с плечом */
  notional_usdt?: number;
  progress_to_tp?: number;
  /** код причины входа (ema_long / ema_short / …) */
  entry_reason?: string;
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

export default function EMAPositionCard({
  positions,
  sendMessage,
}: {
  positions: Pos[];
  sendMessage: (msg: Record<string, unknown>) => void;
}) {
  if (!positions.length) {
    return (
      <div className="text-gray-500 text-xs p-2 border border-gray-800 rounded">
        EMA Scalper: нет позиций
      </div>
    );
  }
  return (
    <div className="grid gap-2">
      {positions.map((p) => {
        const prog = p.progress_to_tp ?? progressToTp(p);
        const pnl = p.pnl_usdt ?? 0;
        const pnlOk = pnl >= 0;
        const held = p.candles_held ?? 0;
        const maxh = p.max_hold_candles ?? 12;
        const lev = Math.max(1, p.leverage ?? 1);
        const margin = p.size_usdt ?? 0;
        let notion = p.notional_usdt ?? 0;
        if (!(notion > 0) && margin > 0) {
          notion = margin * lev;
        }
        const er = String(p.entry_reason ?? "").trim();
        const erLabel = formatEmaEntryReason(er);
        return (
          <div
            key={p.symbol}
            className="border border-gray-800 rounded p-3 bg-terminal-bg/80 text-xs"
          >
            <div className="flex justify-between mb-2">
              <span>
                {p.side === "LONG" ? "▲ LONG" : "▼ SHORT"} {p.symbol}{" "}
                <span className="text-gray-500">x{p.leverage ?? "?"}</span>
              </span>
              <span className="text-gray-500">
                свеча {held} / {maxh}
              </span>
            </div>
            {(notion > 0 || margin > 0) && (
              <div className="mb-1 text-[10px] text-gray-400 flex flex-wrap gap-x-3 gap-y-0.5">
                <span>
                  Номинал:{" "}
                  <span className="text-gray-200">${notion > 0 ? notion.toFixed(2) : "—"}</span>
                </span>
                <span>
                  Маржа:{" "}
                  <span className="text-amber-200/90">${margin > 0 ? margin.toFixed(2) : "—"}</span>
                </span>
              </div>
            )}
            <div className="mb-2">
              Вход: ${p.entry_price.toFixed(2)} → Сейчас: ${p.current_price.toFixed(2)}
            </div>
            {er ? (
              <div
                className="mb-2 text-[10px] text-gray-400 border-l-2 border-emerald-700/60 pl-2"
                title={`Код: ${er}`}
              >
                <span className="text-gray-500">Причина входа: </span>
                <span className="text-emerald-200/90 font-medium">{erLabel}</span>
                <span className="ml-1 font-mono text-gray-500">({er})</span>
              </div>
            ) : null}
            <div className="flex justify-between text-[10px] text-gray-500 mb-1">
              <span>SL ${p.sl_price.toFixed(2)}</span>
              <span className={pnlOk ? "text-emerald-400" : "text-rose-400"}>
                {(p.pnl_pct ?? 0).toFixed(2)}%
              </span>
              <span>TP ${p.tp_price.toFixed(2)}</span>
            </div>
            <div className="h-2 bg-gray-900 rounded overflow-hidden mb-2">
              <div
                className={`h-full ${prog > 0 ? "bg-emerald-500/70" : "bg-rose-500/70"}`}
                style={{ width: `${prog}%` }}
              />
            </div>
            <div className="flex justify-between items-center">
              <span className={pnlOk ? "text-emerald-400" : "text-rose-400"}>
                P&amp;L: {pnl >= 0 ? "+" : ""}
                {pnl.toFixed(4)} USDT
              </span>
              <button
                type="button"
                className="px-2 py-1 border border-rose-700 text-rose-400 rounded text-[10px]"
                onClick={() => sendMessage({ action: "close_ema_scalp", symbol: p.symbol })}
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
