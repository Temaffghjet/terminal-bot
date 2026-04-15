import { useMemo, useState } from "react";
import { emaEntryReasonHasMappedLabel, formatEmaEntryReason } from "./emaEntryReason";

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
  const [selectedDate, setSelectedDate] = useState<string>("all");
  const tradesWithDate = useMemo(
    () =>
      trades.map((t) => {
        const ts = String(t.timestamp_close ?? t.timestamp_open ?? "");
        return { row: t, date: ts.slice(0, 10) };
      }),
    [trades],
  );
  const dailyStats = useMemo(() => {
    const m = new Map<string, { count: number; wins: number; pnl: number }>();
    for (const x of tradesWithDate) {
      if (!x.date) continue;
      const pnl = Number(x.row.pnl_usdt ?? 0);
      const cur = m.get(x.date) ?? { count: 0, wins: 0, pnl: 0 };
      cur.count += 1;
      if (pnl > 0) cur.wins += 1;
      cur.pnl += pnl;
      m.set(x.date, cur);
    }
    return [...m.entries()]
      .sort((a, b) => b[0].localeCompare(a[0]))
      .map(([date, v]) => ({
        date,
        count: v.count,
        winRate: v.count ? (v.wins / v.count) * 100 : 0,
        pnl: v.pnl,
      }));
  }, [tradesWithDate]);
  const filteredTrades = useMemo(
    () => (selectedDate === "all" ? trades : tradesWithDate.filter((x) => x.date === selectedDate).map((x) => x.row)),
    [selectedDate, trades, tradesWithDate],
  );
  const wins = filteredTrades.filter((t) => Number(t.pnl_usdt ?? 0) > 0).length;
  const totalPnl = filteredTrades.reduce((s, t) => s + Number(t.pnl_usdt ?? 0), 0);
  const exportCsv = () => {
    const headers = [
      "timestamp_close",
      "symbol",
      "side",
      "entry_reason",
      "close_reason",
      "leverage",
      "size_usdt",
      "notional",
      "entry_price",
      "exit_price",
      "candles_held",
      "pnl_usdt",
      "pnl_pct",
    ];
    const rows = filteredTrades.map((t) =>
      headers.map((k) => {
        const raw = String((t as Record<string, unknown>)[k] ?? "");
        const safe = raw.replace(/"/g, '""');
        return `"${safe}"`;
      }),
    );
    const csv = [headers.join(","), ...rows.map((r) => r.join(","))].join("\n");
    const blob = new Blob(["\uFEFF" + csv], { type: "text/csv;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    const d = selectedDate === "all" ? "all" : selectedDate;
    a.href = url;
    a.download = `ema_trades_${d}.csv`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };
  return (
    <div className="flex flex-col max-h-[220px] border border-gray-800 rounded">
      <div className="px-2 py-1 border-b border-gray-800 bg-terminal-bg text-[10px] flex flex-wrap items-center gap-2">
        <span className="text-gray-500">Дата:</span>
        <select
          className="bg-gray-900 border border-gray-700 rounded px-1 py-0.5"
          value={selectedDate}
          onChange={(e) => setSelectedDate(e.target.value)}
        >
          <option value="all">Все</option>
          {dailyStats.map((d) => (
            <option key={d.date} value={d.date}>
              {d.date}
            </option>
          ))}
        </select>
        <button
          type="button"
          onClick={exportCsv}
          className="ml-auto border border-gray-700 hover:border-emerald-600 rounded px-2 py-0.5 text-emerald-300"
        >
          Экспорт CSV (Excel)
        </button>
      </div>
      <div className="overflow-auto flex-1">
        <table className="w-full text-[10px] text-left">
          <thead className="sticky top-0 bg-terminal-bg text-gray-500 border-b border-gray-800">
            <tr>
              <th className="p-1">Время</th>
              <th className="p-1">Пара</th>
              <th className="p-1">Сторона</th>
              <th className="p-1 text-right" title="Номинал позиции (с плечом)">
                Номинал
              </th>
              <th className="p-1 text-right" title="Маржа (реальные деньги на счёте)">
                Маржа
              </th>
              <th className="p-1" title="Цена входа">
                Цена вх.
              </th>
              <th className="p-1" title="Цена выхода">
                Цена вых.
              </th>
              <th className="p-1">Свечей</th>
              <th className="p-1 min-w-[6rem]" title="Сигнал стратегии (код из бота)">
                Причина входа
              </th>
              <th className="p-1" title="Причина закрытия">
                Закрытие
              </th>
              <th className="p-1">P&amp;L $</th>
              <th className="p-1">P&amp;L %</th>
            </tr>
          </thead>
          <tbody>
            {filteredTrades.map((t) => {
              const closeReason = String(t.close_reason ?? "");
              const rc = reasonClass[closeReason] ?? "bg-gray-800 text-gray-300";
              const entryReasonRaw = String(t.entry_reason ?? "").trim();
              const entryReasonLabel = formatEmaEntryReason(entryReasonRaw);
              const showEntryCode = entryReasonRaw && emaEntryReasonHasMappedLabel(entryReasonRaw);
              const lev = Math.max(1, Number(t.leverage ?? 1));
              const margin = Number(t.size_usdt ?? 0);
              let notion = Number(t.notional ?? 0);
              if (!(notion > 0) && margin > 0) {
                notion = margin * lev;
              }
              return (
                <tr key={String(t.id)} className="border-b border-gray-900">
                  <td className="p-1 font-mono whitespace-nowrap">
                    {String(t.timestamp_close ?? "").slice(11, 19)}
                  </td>
                  <td className="p-1">{String(t.symbol ?? "")}</td>
                  <td className="p-1">{String(t.side ?? "")}</td>
                  <td className="p-1 text-right text-gray-300 whitespace-nowrap">
                    ${notion.toFixed(2)}
                    <span className="text-gray-600"> x{lev}</span>
                  </td>
                  <td className="p-1 text-right text-amber-200/90 whitespace-nowrap">
                    ${margin.toFixed(2)}
                  </td>
                  <td className="p-1">{Number(t.entry_price ?? 0).toFixed(2)}</td>
                  <td className="p-1">{Number(t.exit_price ?? 0).toFixed(2)}</td>
                  <td className="p-1">{String(t.candles_held ?? "")}</td>
                  <td
                    className="p-1 text-gray-200 max-w-[9rem]"
                    title={entryReasonRaw ? `${entryReasonLabel}${showEntryCode ? ` · ${entryReasonRaw}` : ""}` : "—"}
                  >
                    <span className="font-medium text-emerald-200/90">{entryReasonLabel}</span>
                    {showEntryCode ? (
                      <span className="block text-[9px] text-gray-500 font-mono truncate">{entryReasonRaw}</span>
                    ) : null}
                  </td>
                  <td className="p-1">
                    <span className={`px-1 rounded ${rc}`}>{closeReason}</span>
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
        <span>Всего: {filteredTrades.length}</span>
        <span>Win: {filteredTrades.length ? ((wins / filteredTrades.length) * 100).toFixed(0) : 0}%</span>
        <span>P&amp;L: ${totalPnl.toFixed(2)}</span>
      </div>
      <div className="border-t border-gray-800 bg-[#0a0a12] px-2 py-1 text-[10px] text-gray-400">
        <div className="mb-1 text-gray-500">Статистика по дням:</div>
        <div className="flex flex-wrap gap-x-3 gap-y-1">
          {dailyStats.slice(0, 8).map((d) => (
            <span key={d.date}>
              {d.date}: {d.count} сделок, Win {d.winRate.toFixed(0)}%, P&amp;L {d.pnl >= 0 ? "+" : ""}
              {d.pnl.toFixed(2)}
            </span>
          ))}
        </div>
      </div>
    </div>
  );
}
