import { useMemo, useState } from "react";
import { useWebSocket } from "./hooks/useWebSocket";

type EmaPos = {
  symbol?: string;
  side?: string;
  entry_price?: number;
  current_price?: number;
  pnl_usdt?: number;
  size_usdt?: number;
  notional_usdt?: number;
  leverage?: number;
  entry_reason?: string;
  tp_price?: number;
  sl_price?: number;
  candles_held?: number;
  max_hold_candles?: number;
};

type Row = Record<string, unknown>;

function utcYmd(ts: unknown): string {
  const s = String(ts ?? "");
  return s.length >= 10 ? s.slice(0, 10) : "";
}

function fmtDt(ts: unknown): { d: string; t: string } {
  const s = String(ts ?? "");
  if (s.length >= 19) {
    return { d: s.slice(0, 10), t: s.slice(11, 19) };
  }
  return { d: s.slice(0, 10), t: "" };
}

function notionWithLev(t: Row): number {
  const lev = Math.max(1, Number(t.leverage ?? 1));
  const margin = Number(t.size_usdt ?? 0);
  let n = Number(t.notional ?? 0);
  if (!(n > 0) && margin > 0) n = margin * lev;
  return n;
}

export default function App() {
  const { state, isConnected, emaTradeByDay, requestEmaTradeDay, clearEmaTradeDay } = useWebSocket();

  const ema = state?.ema_scalper as
    | {
        positions?: EmaPos[];
        stats?: Record<string, unknown>;
        recent_trades?: Row[];
      }
    | undefined;

  const positions = (ema?.positions ?? []) as EmaPos[];
  const stats = ema?.stats ?? {};
  const recent = (ema?.recent_trades ?? []) as Row[];

  const openMargin = useMemo(
    () => positions.reduce((s, p) => s + Number(p.size_usdt ?? 0), 0),
    [positions],
  );
  const openUnrealized = useMemo(
    () => positions.reduce((s, p) => s + Number(p.pnl_usdt ?? 0), 0),
    [positions],
  );

  const todayPnl = Number(stats.today_pnl ?? stats["today_pnl"] ?? 0);
  const todayTrades = Number(stats.today_trades ?? 0);

  const todayUtc = new Date().toISOString().slice(0, 10);
  const closedToday = useMemo(
    () => recent.filter((t) => utcYmd(t.timestamp_close) === todayUtc),
    [recent, todayUtc],
  );
  const fixedList = closedToday.length ? closedToday : recent.slice(0, 15);

  const [historyMode, setHistoryMode] = useState<"feed" | "day">("feed");
  const [dayPick, setDayPick] = useState(() => {
    const d = new Date();
    d.setUTCDate(d.getUTCDate() - 1);
    return d.toISOString().slice(0, 10);
  });

  const historyRows: Row[] = useMemo(() => {
    if (historyMode === "day" && emaTradeByDay?.date && !emaTradeByDay.error) {
      return emaTradeByDay.trades;
    }
    return recent;
  }, [historyMode, emaTradeByDay, recent]);

  const loadDayHistory = () => {
    setHistoryMode("day");
    requestEmaTradeDay(dayPick.trim());
  };

  const backToFeedHistory = () => {
    setHistoryMode("feed");
    clearEmaTradeDay();
  };

  return (
    <div className="min-h-screen flex flex-col bg-slate-950 text-slate-200">
      {/* Верх: баланс по открытым */}
      <header className="border-b border-slate-800 px-4 py-3 shrink-0 bg-slate-900/80">
        <div className="flex flex-wrap items-baseline justify-between gap-3">
          <h1 className="text-sm font-semibold text-emerald-400/90 tracking-wide">EMA Scalper</h1>
          <div className="flex flex-wrap gap-6 text-xs font-mono">
            <div>
              <span className="text-slate-500">Маржа в открытых </span>
              <span className="text-amber-200">${openMargin.toFixed(2)}</span>
              <span className="text-slate-600"> USDT</span>
            </div>
            <div>
              <span className="text-slate-500">Нереализ. P&amp;L </span>
              <span className={openUnrealized >= 0 ? "text-emerald-400" : "text-rose-400"}>
                ${openUnrealized.toFixed(4)}
              </span>
            </div>
            <div className="text-slate-600">
              WS: {isConnected ? <span className="text-emerald-500">online</span> : <span className="text-rose-500">offline</span>}
            </div>
          </div>
        </div>
      </header>

      {/* PnL за день */}
      <section className="border-b border-slate-800 px-4 py-2 bg-slate-900/40 shrink-0">
        <div className="text-xs font-mono flex flex-wrap gap-6">
          <span className="text-slate-500 uppercase text-[10px] tracking-wider">PnL за день (UTC)</span>
          <span>
            Сегодня:{" "}
            <span className={todayPnl >= 0 ? "text-emerald-400" : "text-rose-400"}>${todayPnl.toFixed(4)}</span>
          </span>
          <span className="text-slate-500">Сделок сегодня: {todayTrades}</span>
        </div>
      </section>

      {/* Открытые | Зафиксированные */}
      <section className="flex-1 min-h-0 grid grid-cols-1 lg:grid-cols-2 gap-0 border-b border-slate-800">
        <div className="border-b lg:border-b-0 lg:border-r border-slate-800 flex flex-col min-h-[220px] max-h-[42vh]">
          <div className="px-3 py-1.5 text-[10px] uppercase tracking-wider text-slate-500 border-b border-slate-800 shrink-0">
            Открытые позиции
          </div>
          <div className="overflow-auto flex-1 p-2 space-y-2">
            {!positions.length ? (
              <p className="text-slate-600 text-xs p-2">Нет открытых EMA-позиций</p>
            ) : (
              positions.map((p, i) => (
                <div
                  key={`${p.symbol}-${i}`}
                  className="border border-slate-800 rounded p-2 bg-slate-900/50 text-[11px] font-mono"
                >
                  <div className="flex justify-between gap-2">
                    <span className="text-emerald-300/90">{String(p.symbol ?? "")}</span>
                    <span className={p.side === "LONG" ? "text-sky-400" : "text-orange-400"}>{p.side}</span>
                  </div>
                  <div className="mt-1 grid grid-cols-2 gap-x-3 gap-y-0.5 text-slate-400">
                    <span>Вход</span>
                    <span className="text-right text-slate-200">{Number(p.entry_price ?? 0).toFixed(2)}</span>
                    <span>Сейчас</span>
                    <span className="text-right text-slate-200">{Number(p.current_price ?? 0).toFixed(2)}</span>
                    <span>Маржа</span>
                    <span className="text-right text-amber-200/90">${Number(p.size_usdt ?? 0).toFixed(2)}</span>
                    <span>С плечом</span>
                    <span className="text-right">${Number(p.notional_usdt ?? 0).toFixed(2)} ×{p.leverage ?? 1}</span>
                    <span>P&amp;L нер.</span>
                    <span
                      className={`text-right ${Number(p.pnl_usdt ?? 0) >= 0 ? "text-emerald-400" : "text-rose-400"}`}
                    >
                      ${Number(p.pnl_usdt ?? 0).toFixed(4)}
                    </span>
                  </div>
                  {p.entry_reason ? (
                    <div className="mt-1 text-[10px] text-slate-500 truncate" title={String(p.entry_reason)}>
                      Вход: {String(p.entry_reason)}
                    </div>
                  ) : null}
                </div>
              ))
            )}
          </div>
        </div>

        <div className="flex flex-col min-h-[220px] max-h-[42vh]">
          <div className="px-3 py-1.5 text-[10px] uppercase tracking-wider text-slate-500 border-b border-slate-800 shrink-0">
            Зафиксировано {closedToday.length ? `(сегодня UTC ${todayUtc})` : "(последние в ленте)"}
          </div>
          <div className="overflow-auto flex-1 p-2 space-y-2">
            {!fixedList.length ? (
              <p className="text-slate-600 text-xs p-2">Нет закрытых сделок в выборке</p>
            ) : (
              fixedList.map((t) => {
                const { d, t: tm } = fmtDt(t.timestamp_close);
                const pnl = Number(t.pnl_usdt ?? 0);
                return (
                  <div
                    key={String(t.id)}
                    className="border border-slate-800/80 rounded p-2 bg-slate-900/30 text-[11px] font-mono"
                  >
                    <div className="flex justify-between">
                      <span className="text-slate-300">{String(t.symbol ?? "")}</span>
                      <span className={pnl >= 0 ? "text-emerald-400" : "text-rose-400"}>${pnl.toFixed(4)}</span>
                    </div>
                    <div className="text-[10px] text-slate-500 mt-0.5">
                      {d} {tm}
                    </div>
                    <div className="mt-1 text-[10px] text-slate-500">
                      {String(t.close_reason ?? "")} · маржа ${Number(t.size_usdt ?? 0).toFixed(2)}
                    </div>
                  </div>
                );
              })
            )}
          </div>
        </div>
      </section>

      {/* История — полная таблица */}
      <section className="flex flex-col min-h-[280px] flex-1 border-t border-slate-800">
        <div className="flex flex-wrap items-center gap-2 px-3 py-1.5 border-b border-slate-800 bg-slate-900/30 shrink-0">
          <span className="text-[10px] uppercase tracking-wider text-slate-500">История сделок</span>
          <input
            type="date"
            className="bg-slate-900 border border-slate-700 rounded px-1 py-0.5 text-[11px]"
            value={dayPick}
            onChange={(e) => setDayPick(e.target.value)}
          />
          <button
            type="button"
            className="text-[11px] px-2 py-0.5 rounded bg-emerald-900/50 border border-emerald-800 text-emerald-100"
            onClick={loadDayHistory}
          >
            Загрузить день из БД
          </button>
          {historyMode === "day" ? (
            <button
              type="button"
              className="text-[11px] px-2 py-0.5 rounded bg-slate-800 border border-slate-600"
              onClick={backToFeedHistory}
            >
              Лента с сервера
            </button>
          ) : null}
          {historyMode === "day" && emaTradeByDay?.error ? (
            <span className="text-rose-400 text-[11px]">{emaTradeByDay.error}</span>
          ) : null}
        </div>
        <div className="overflow-auto flex-1">
          <table className="w-full text-left text-[11px] font-mono border-collapse">
            <thead className="sticky top-0 bg-slate-900 text-slate-500 border-b border-slate-800">
              <tr>
                <th className="p-1.5 font-normal">Дата</th>
                <th className="p-1.5 font-normal">Время UTC</th>
                <th className="p-1.5 font-normal">Пара</th>
                <th className="p-1.5 font-normal text-right">Вход</th>
                <th className="p-1.5 font-normal text-right">Выход</th>
                <th className="p-1.5 font-normal text-right">Маржа</th>
                <th className="p-1.5 font-normal text-right">С плечом</th>
                <th className="p-1.5 font-normal">Причина входа</th>
                <th className="p-1.5 font-normal">Выход (reason)</th>
                <th className="p-1.5 font-normal text-right">P&amp;L</th>
              </tr>
            </thead>
            <tbody>
              {historyRows.map((t) => {
                const { d, t: tm } = fmtDt(t.timestamp_close);
                const pnl = Number(t.pnl_usdt ?? 0);
                const n = notionWithLev(t);
                const lev = Math.max(1, Number(t.leverage ?? 1));
                return (
                  <tr key={String(t.id)} className="border-b border-slate-800/80 hover:bg-slate-900/50">
                    <td className="p-1.5 text-slate-400">{d}</td>
                    <td className="p-1.5 text-slate-400">{tm}</td>
                    <td className="p-1.5">{String(t.symbol ?? "")}</td>
                    <td className="p-1.5 text-right">{Number(t.entry_price ?? 0).toFixed(4)}</td>
                    <td className="p-1.5 text-right">{Number(t.exit_price ?? 0).toFixed(4)}</td>
                    <td className="p-1.5 text-right text-amber-200/80">${Number(t.size_usdt ?? 0).toFixed(2)}</td>
                    <td className="p-1.5 text-right text-slate-300">
                      ${n.toFixed(2)} <span className="text-slate-600">×{lev}</span>
                    </td>
                    <td className="p-1.5 text-slate-400 max-w-[140px] truncate" title={String(t.entry_reason ?? "")}>
                      {String(t.entry_reason ?? "—")}
                    </td>
                    <td className="p-1.5 text-slate-400">{String(t.close_reason ?? "—")}</td>
                    <td className={`p-1.5 text-right ${pnl >= 0 ? "text-emerald-400" : "text-rose-400"}`}>
                      {pnl.toFixed(4)}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          {!historyRows.length ? (
            <p className="p-4 text-slate-600 text-xs">Нет строк. Подключите бота или загрузите день из БД.</p>
          ) : null}
        </div>
      </section>
    </div>
  );
}
