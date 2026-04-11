type Row = Record<string, unknown>;

const reasonClass: Record<string, string> = {
  TP: "bg-[#378ADD] text-white",
  SL: "bg-rose-700 text-white",
  EMA_CROSS: "bg-gray-600 text-white",
  TIME: "bg-violet-700 text-white",
  MANUAL: "bg-amber-700 text-white",
};

export default function EMATradeLog({ trades }: { trades: Row[] }) {
  if (!trades.length) {
    return <div className="text-gray-500 text-xs p-2">Нет сделок в scalp_trades (ema)</div>;
  }
  const wins = trades.filter((t) => Number(t.pnl_usdt ?? 0) > 0).length;
  const totalPnl = trades.reduce((s, t) => s + Number(t.pnl_usdt ?? 0), 0);
  return (
    <div className="flex flex-col max-h-[220px] border border-gray-800 rounded">
      <div className="overflow-auto flex-1">
        <table className="w-full text-[10px] text-left">
          <thead className="sticky top-0 bg-terminal-bg text-gray-500 border-b border-gray-800">
            <tr>
              <th className="p-1">Время</th>
              <th className="p-1">Пара</th>
              <th className="p-1">Сторона</th>
              <th className="p-1">Вход</th>
              <th className="p-1">Выход</th>
              <th className="p-1">Свечей</th>
              <th className="p-1">Причина</th>
              <th className="p-1">P&amp;L $</th>
              <th className="p-1">P&amp;L %</th>
            </tr>
          </thead>
          <tbody>
            {trades.map((t) => {
              const reason = String(t.close_reason ?? "");
              const rc = reasonClass[reason] ?? "bg-gray-800 text-gray-300";
              return (
                <tr key={String(t.id)} className="border-b border-gray-900">
                  <td className="p-1 font-mono whitespace-nowrap">
                    {String(t.timestamp_close ?? "").slice(11, 19)}
                  </td>
                  <td className="p-1">{String(t.symbol ?? "")}</td>
                  <td className="p-1">{String(t.side ?? "")}</td>
                  <td className="p-1">{Number(t.entry_price ?? 0).toFixed(2)}</td>
                  <td className="p-1">{Number(t.exit_price ?? 0).toFixed(2)}</td>
                  <td className="p-1">{String(t.candles_held ?? "")}</td>
                  <td className="p-1">
                    <span className={`px-1 rounded ${rc}`}>{reason}</span>
                  </td>
                  <td
                    className={`p-1 ${
                      Number(t.pnl_usdt ?? 0) >= 0 ? "text-emerald-400" : "text-rose-400"
                    }`}
                  >
                    {Number(t.pnl_usdt ?? 0).toFixed(4)}
                  </td>
                  <td className="p-1">{Number(t.pnl_pct ?? 0).toFixed(2)}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <div className="sticky bottom-0 border-t border-gray-800 bg-terminal-bg px-2 py-1 text-[10px] text-gray-400 flex flex-wrap gap-2">
        <span>Всего: {trades.length}</span>
        <span>Win: {trades.length ? ((wins / trades.length) * 100).toFixed(0) : 0}%</span>
        <span>P&amp;L: ${totalPnl.toFixed(2)}</span>
      </div>
    </div>
  );
}
