import { useMemo, useState } from "react";

type TradeRow = {
  id?: number;
  timestamp?: string;
  pair_id?: string;
  action?: string;
  direction?: string;
  zscore_entry?: number | null;
  zscore_exit?: number | null;
  entry_price_a?: number | null;
  exit_price_a?: number | null;
  pnl_usdt?: number | null;
  close_reason?: string | null;
  dry_run?: number | null;
};

type FilterMode = "all" | "open" | "closed" | "dry";

type Props = { trades: TradeRow[] };

export default function TradeLog({ trades }: Props) {
  const [filter, setFilter] = useState<FilterMode>("all");
  const [sortDesc, setSortDesc] = useState(true);

  const filtered = useMemo(() => {
    let rows = [...trades];
    if (filter === "open") rows = rows.filter((t) => t.action === "OPEN");
    if (filter === "closed") rows = rows.filter((t) => t.action === "CLOSE");
    if (filter === "dry") rows = rows.filter((t) => t.dry_run === 1);
    rows.sort((a, b) => {
      const ta = Date.parse(a.timestamp ?? "") || 0;
      const tb = Date.parse(b.timestamp ?? "") || 0;
      return sortDesc ? tb - ta : ta - tb;
    });
    return rows;
  }, [trades, filter, sortDesc]);

  const totals = useMemo(() => {
    const closed = trades.filter((t) => t.action === "CLOSE" && t.pnl_usdt != null);
    const wins = closed.filter((t) => (t.pnl_usdt ?? 0) > 0).length;
    const totalPnl = closed.reduce((s, t) => s + (t.pnl_usdt ?? 0), 0);
    const winRate = closed.length ? (wins / closed.length) * 100 : 0;
    return { count: trades.length, winRate, totalPnl };
  }, [trades]);

  return (
    <div className="border border-gray-800 bg-[#0a0a0f] flex flex-col min-h-[200px]">
      <div className="flex flex-wrap items-center gap-2 px-2 py-1 border-b border-gray-800">
        <span className="text-xs text-gray-500 uppercase">Trade log</span>
        <div className="flex gap-1 text-[10px]">
          {(["all", "open", "closed", "dry"] as const).map((f) => (
            <button
              key={f}
              type="button"
              className={`px-2 py-0.5 border ${filter === f ? "border-terminal-warn text-terminal-warn" : "border-gray-700 text-gray-500"}`}
              onClick={() => setFilter(f)}
            >
              {f === "all" ? "All" : f === "open" ? "Open" : f === "closed" ? "Closed" : "Dry Run"}
            </button>
          ))}
        </div>
        <button
          type="button"
          className="text-[10px] text-gray-500 ml-auto"
          onClick={() => setSortDesc((s) => !s)}
        >
          Time {sortDesc ? "↓" : "↑"}
        </button>
      </div>
      <div className="overflow-auto max-h-[280px]">
        <table className="w-full text-[10px] font-mono">
          <thead className="sticky top-0 bg-[#0d0d14] text-gray-500">
            <tr>
              <th className="text-left p-1">Time</th>
              <th className="text-left p-1">Pair</th>
              <th className="text-left p-1">Action</th>
              <th className="text-left p-1">Direction</th>
              <th className="text-left p-1">Z in → out / цена</th>
              <th className="text-right p-1">P&amp;L</th>
              <th className="text-left p-1">Reason</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((t, i) => (
              <tr key={`${t.timestamp}-${i}`} className="border-t border-gray-900">
                <td className="p-1 text-gray-400 whitespace-nowrap">{t.timestamp}</td>
                <td className="p-1">{t.pair_id}</td>
                <td
                  className={`p-1 ${t.action === "OPEN" ? "text-terminal-profit" : "text-terminal-loss"}`}
                >
                  {t.action}
                </td>
                <td className="p-1">{t.direction}</td>
                <td className="p-1">
                  {(() => {
                    const scalp =
                      (t.pair_id?.startsWith("scalp:") ?? false) ||
                      String(t.direction ?? "").includes("SCALP");
                    if (scalp) {
                      const a =
                        t.entry_price_a != null && t.entry_price_a !== undefined
                          ? Number(t.entry_price_a).toFixed(2)
                          : "—";
                      const b =
                        t.exit_price_a != null && t.exit_price_a !== undefined
                          ? Number(t.exit_price_a).toFixed(2)
                          : "—";
                      return (
                        <>
                          {a} → {b}
                        </>
                      );
                    }
                    const ze =
                      t.zscore_entry != null && t.zscore_entry !== undefined && !Number.isNaN(t.zscore_entry)
                        ? t.zscore_entry.toFixed(2)
                        : "—";
                    const zx =
                      t.zscore_exit != null && t.zscore_exit !== undefined && !Number.isNaN(t.zscore_exit)
                        ? t.zscore_exit.toFixed(2)
                        : "—";
                    return (
                      <>
                        {ze} → {zx}
                      </>
                    );
                  })()}
                </td>
                <td
                  className={`p-1 text-right ${(t.pnl_usdt ?? 0) >= 0 ? "text-terminal-profit" : "text-terminal-loss"}`}
                >
                  {(t.pnl_usdt ?? 0) >= 0 ? "+" : ""}
                  {(t.pnl_usdt ?? 0).toFixed(2)}
                </td>
                <td className="p-1 flex items-center gap-1">
                  {t.close_reason}
                  {t.dry_run === 1 && (
                    <span className="border border-terminal-warn text-terminal-warn px-0.5 text-[9px]">DRY RUN</span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="border-t border-gray-800 px-2 py-1 text-[10px] flex gap-6 text-gray-400">
        <span>
          Total trades: <span className="text-white">{totals.count}</span>
        </span>
        <span>
          Win rate: <span className="text-white">{totals.winRate.toFixed(0)}%</span>
        </span>
        <span>
          Total P&amp;L:{" "}
          <span className={totals.totalPnl >= 0 ? "text-terminal-profit" : "text-terminal-loss"}>
            {totals.totalPnl >= 0 ? "+" : ""}
            {totals.totalPnl.toFixed(2)}
          </span>
        </span>
      </div>
    </div>
  );
}
