import { useMemo, useState } from "react";
import type { EmaTradeByDayPayload } from "../../hooks/useWebSocket";
import { emaEntryReasonHasMappedLabel, formatEmaEntryReason } from "./emaEntryReason";

type Row = Record<string, unknown>;

const reasonClass: Record<string, string> = {
  TP: "bg-[#378ADD] text-white",
  SL: "bg-rose-700 text-white",
  EMA_CROSS: "bg-gray-600 text-white",
  TIME: "bg-violet-700 text-white",
  MANUAL: "bg-amber-700 text-white",
};

function fmtCloseUtc(ts: unknown): string {
  const s = String(ts ?? "");
  if (s.length >= 19) return s.slice(0, 19).replace("T", " ");
  return s;
}

function csvEscape(cell: string): string {
  if (/[",\n\r]/.test(cell)) return `"${cell.replace(/"/g, '""')}"`;
  return cell;
}

function tradesToCsv(rows: Row[]): string {
  const headers = [
    "Время закрытия UTC",
    "Пара",
    "Сторона",
    "Номинал",
    "Плечо",
    "Маржа USDT",
    "Цена входа",
    "Цена выхода",
    "Свечей",
    "Причина входа",
    "Закрытие",
    "P&L USDT",
    "P&L %",
    "Комиссия",
    "Стратегия",
  ];
  const lines = [headers.join(";")];
  for (const t of rows) {
    const lev = Math.max(1, Number(t.leverage ?? 1));
    const margin = Number(t.size_usdt ?? 0);
    let notion = Number(t.notional ?? 0);
    if (!(notion > 0) && margin > 0) notion = margin * lev;
    const er = String(t.entry_reason ?? "").trim();
    const line = [
      fmtCloseUtc(t.timestamp_close),
      String(t.symbol ?? ""),
      String(t.side ?? ""),
      notion.toFixed(4),
      String(lev),
      margin.toFixed(4),
      Number(t.entry_price ?? 0).toFixed(6),
      Number(t.exit_price ?? 0).toFixed(6),
      String(t.candles_held ?? ""),
      er,
      String(t.close_reason ?? ""),
      Number(t.pnl_usdt ?? 0).toFixed(6),
      Number(t.pnl_pct ?? 0).toFixed(4),
      Number(t.fee_usdt ?? 0).toFixed(6),
      String(t.strategy ?? ""),
    ].map((x) => csvEscape(String(x)));
    lines.push(line.join(";"));
  }
  return "\uFEFF" + lines.join("\r\n");
}

function downloadCsv(filename: string, content: string) {
  const blob = new Blob([content], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

export default function EMATradeLog({
  trades,
  emaTradeByDay,
  requestEmaTradeDay,
  clearEmaTradeDay,
}: {
  trades: Row[];
  emaTradeByDay: EmaTradeByDayPayload | null;
  requestEmaTradeDay: (date: string) => void;
  clearEmaTradeDay: () => void;
}) {
  const defaultDay = useMemo(() => {
    const d = new Date();
    d.setUTCDate(d.getUTCDate() - 1);
    return d.toISOString().slice(0, 10);
  }, []);
  const [dayInput, setDayInput] = useState(defaultDay);
  const [pendingDay, setPendingDay] = useState<string | null>(null);

  const loadingDay =
    pendingDay != null && (!emaTradeByDay || emaTradeByDay.date !== pendingDay);
  const dayReady =
    pendingDay != null && emaTradeByDay?.date === pendingDay && !emaTradeByDay.error;
  const dayErr =
    pendingDay != null && emaTradeByDay?.date === pendingDay && emaTradeByDay.error;

  const displayRows: Row[] = dayReady ? (emaTradeByDay?.trades ?? []) : trades;
  const modeLabel = dayReady && pendingDay ? `день UTC ${pendingDay}` : "последние (с сервера)";

  const wins = displayRows.filter((t) => Number(t.pnl_usdt ?? 0) > 0).length;
  const totalPnl = displayRows.reduce((s, t) => s + Number(t.pnl_usdt ?? 0), 0);

  const loadDay = () => {
    const d = dayInput.trim();
    if (!/^\d{4}-\d{2}-\d{2}$/.test(d)) return;
    setPendingDay(d);
    requestEmaTradeDay(d);
  };

  const backToLive = () => {
    setPendingDay(null);
    clearEmaTradeDay();
  };

  const exportExcel = () => {
    const stamp = dayReady && pendingDay ? pendingDay : "live";
    downloadCsv(`ema_scalper_${stamp}.csv`, tradesToCsv(displayRows));
  };

  return (
    <div className="flex flex-col gap-2">
      <div className="flex flex-wrap items-center gap-2 text-[10px]">
        <span className="text-gray-500">История:</span>
        <label className="flex items-center gap-1 text-gray-400">
          День (UTC)
          <input
            type="date"
            className="bg-black/40 border border-gray-700 rounded px-1 py-0.5 text-gray-200"
            value={dayInput}
            onChange={(e) => setDayInput(e.target.value)}
          />
        </label>
        <button
          type="button"
          className="px-2 py-0.5 rounded bg-emerald-900/60 border border-emerald-700/50 text-emerald-100 hover:bg-emerald-800/60 disabled:opacity-40"
          onClick={loadDay}
          disabled={!dayInput.trim()}
        >
          Показать за день
        </button>
        {pendingDay != null ? (
          <button
            type="button"
            className="px-2 py-0.5 rounded bg-gray-800 border border-gray-600 text-gray-300 hover:bg-gray-700"
            onClick={backToLive}
          >
            К ленте (последние)
          </button>
        ) : null}
        <button
          type="button"
          className="px-2 py-0.5 rounded bg-slate-800 border border-slate-600 text-slate-200 hover:bg-slate-700"
          onClick={exportExcel}
          disabled={!displayRows.length}
        >
          Скачать Excel (CSV)
        </button>
        <span className="text-gray-600">· {modeLabel}</span>
      </div>
      {loadingDay ? (
        <div className="text-amber-400/90 text-xs">Загрузка сделок за выбранный день…</div>
      ) : null}
      {dayErr ? (
        <div className="text-rose-400/90 text-xs">
          Ошибка: {emaTradeByDay?.error}. Проверьте, что бот с БД запущен.
        </div>
      ) : null}
      {!displayRows.length && !loadingDay ? (
        <div className="text-gray-500 text-xs p-2">
          Нет сделок за выбранный период (scalp_trades / EMA).
        </div>
      ) : displayRows.length ? (
        <div className="flex flex-col max-h-[280px] border border-gray-800 rounded">
          <div className="overflow-auto flex-1">
            <table className="w-full text-[10px] text-left">
              <thead className="sticky top-0 bg-terminal-bg text-gray-500 border-b border-gray-800">
                <tr>
                  <th className="p-1">Время (UTC)</th>
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
                {displayRows.map((t) => {
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
                        {fmtCloseUtc(t.timestamp_close)}
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
                        title={
                          entryReasonRaw
                            ? `${entryReasonLabel}${showEntryCode ? ` · ${entryReasonRaw}` : ""}`
                            : "—"
                        }
                      >
                        <span className="font-medium text-emerald-200/90">{entryReasonLabel}</span>
                        {showEntryCode ? (
                          <span className="block text-[9px] text-gray-500 font-mono truncate">
                            {entryReasonRaw}
                          </span>
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
            <span>Всего: {displayRows.length}</span>
            <span>Win: {displayRows.length ? ((wins / displayRows.length) * 100).toFixed(0) : 0}%</span>
            <span>P&amp;L: ${totalPnl.toFixed(2)}</span>
          </div>
        </div>
      ) : null}
    </div>
  );
}
