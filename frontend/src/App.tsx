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
type IndicatorRow = Record<string, unknown>;

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

function botStatusLabel(
  isConnected: boolean,
  status: string | undefined,
): { text: string; className: string } {
  if (!isConnected) {
    return { text: "Нет связи с ботом", className: "bg-slate-200 text-slate-700 border-slate-300" };
  }
  const s = (status ?? "").toLowerCase();
  if (s === "running") {
    return { text: "Бот работает", className: "bg-emerald-100 text-emerald-800 border-emerald-300" };
  }
  if (s === "paused") {
    return { text: "Пауза", className: "bg-amber-100 text-amber-900 border-amber-300" };
  }
  if (s === "stopped") {
    return { text: "Остановлен", className: "bg-slate-200 text-slate-700 border-slate-300" };
  }
  return { text: status || "—", className: "bg-slate-100 text-slate-800 border-slate-300" };
}

export default function App() {
  const { state, isConnected, wsUrl, sendMessage, emaTradeByDay, requestEmaTradeDay, clearEmaTradeDay } =
    useWebSocket();

  const botStatus = (state?.bot_status as string | undefined) ?? "";

  const ema = state?.ema_scalper as
    | {
        positions?: EmaPos[];
        stats?: Record<string, unknown>;
        recent_trades?: Row[];
        indicators?: Record<string, IndicatorRow>;
      }
    | undefined;

  const positions = (ema?.positions ?? []) as EmaPos[];
  const stats = ema?.stats ?? {};
  const recent = (ema?.recent_trades ?? []) as Row[];
  const indicators = (ema?.indicators ?? {}) as Record<string, IndicatorRow>;
  const entryWatchRows = useMemo(() => {
    return Object.entries(indicators)
      .sort(([a], [b]) => a.localeCompare(b))
      .map(([symbol, ind]) => {
        const ready = Boolean(ind.signal_ready);
        const side = String(ind.side_ready ?? "");
        const reason = String(ind.reason ?? "no_setup");
        const score = Number(ind.auto_trade_score ?? 0);
        const allow = Boolean(ind.auto_allow_trade);
        const close = Number(ind.close ?? 0);
        const emaNow = Number(ind.ema_current ?? 0);
        return { symbol, ready, side, reason, score, allow, close, emaNow };
      });
  }, [indicators]);

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

  const statusUi = botStatusLabel(isConnected, botStatus);
  const isRunning = isConnected && botStatus.toLowerCase() === "running";
  const isLocalWs = /localhost|127\.0\.0\.1/i.test(wsUrl);

  return (
    <div className="min-h-screen flex flex-col bg-white text-slate-900">
      {!isConnected ? (
        <div className="border-b border-amber-200 bg-amber-50 px-4 py-2 text-[11px] text-amber-950 leading-snug">
          <strong className="font-semibold">WS offline.</strong> Подключение к{" "}
          <code className="rounded bg-amber-100/80 px-1">{wsUrl}</code>
          {isLocalWs ? (
            <>
              . Запустите бота на этой машине (из корня проекта:{" "}
              <code className="rounded bg-amber-100/80 px-1">python -m backend.main</code> или ваш systemd) и
              проверьте <code className="rounded bg-amber-100/80 px-1">WS_PORT=8765</code> в{" "}
              <code className="rounded bg-amber-100/80 px-1">.env</code> бота.
            </>
          ) : (
            <>
              . Бот на другом сервере — в <code className="rounded bg-amber-100/80 px-1">frontend/.env</code>{" "}
              задайте <code className="rounded bg-amber-100/80 px-1">VITE_WS_URL=ws://IP:8765</code> и перезапустите{" "}
              <code className="rounded bg-amber-100/80 px-1">npm run dev</code>; на VPS откройте порт 8765.
            </>
          )}
        </div>
      ) : null}

      {/* Верх: управление + баланс */}
      <header className="border-b border-slate-200 px-4 py-3 shrink-0 bg-slate-50">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex flex-wrap items-center gap-3">
            <h1 className="text-sm font-semibold text-emerald-800 tracking-wide">EMA Scalper</h1>
            <span
              className={`inline-flex items-center rounded border px-2.5 py-1 text-xs font-medium ${statusUi.className}`}
            >
              {statusUi.text}
            </span>
            <div className="flex items-center gap-2">
              <button
                type="button"
                disabled={!isConnected || !isRunning}
                onClick={() => sendMessage({ action: "pause" })}
                className="rounded border border-slate-300 bg-white px-3 py-1.5 text-xs font-medium text-slate-800 shadow-sm hover:bg-slate-100 disabled:cursor-not-allowed disabled:opacity-40"
              >
                Пауза
              </button>
              <button
                type="button"
                disabled={!isConnected || isRunning}
                onClick={() => sendMessage({ action: "resume" })}
                className="rounded border border-emerald-600 bg-emerald-600 px-3 py-1.5 text-xs font-medium text-white shadow-sm hover:bg-emerald-700 disabled:cursor-not-allowed disabled:opacity-40"
              >
                Работает
              </button>
            </div>
          </div>
          <div className="flex flex-wrap gap-6 text-xs font-mono text-slate-700">
            <div>
              <span className="text-slate-500">Маржа в открытых </span>
              <span className="text-amber-800 font-medium">${openMargin.toFixed(2)}</span>
              <span className="text-slate-500"> USDT</span>
            </div>
            <div>
              <span className="text-slate-500">Нереализ. P&amp;L </span>
              <span className={openUnrealized >= 0 ? "text-emerald-700" : "text-rose-600"}>
                ${openUnrealized.toFixed(4)}
              </span>
            </div>
            <div className="text-slate-600">
              WS:{" "}
              {isConnected ? (
                <span className="text-emerald-700 font-medium">online</span>
              ) : (
                <span className="text-rose-600 font-medium">offline</span>
              )}
            </div>
          </div>
        </div>
      </header>

      {/* PnL за день */}
      <section className="border-b border-slate-200 px-4 py-2 bg-white shrink-0">
        <div className="text-xs font-mono flex flex-wrap gap-6">
          <span className="text-slate-500 uppercase text-[10px] tracking-wider">PnL за день (UTC)</span>
          <span>
            Сегодня:{" "}
            <span className={todayPnl >= 0 ? "text-emerald-700" : "text-rose-600"}>${todayPnl.toFixed(4)}</span>
          </span>
          <span className="text-slate-500">Сделок сегодня: {todayTrades}</span>
        </div>
      </section>

      {/* Поиск входа в реальном времени */}
      <section className="border-b border-slate-200 bg-white shrink-0">
        <div className="px-3 py-1.5 text-[10px] uppercase tracking-wider text-slate-500 bg-slate-50 border-b border-slate-200">
          Поиск входа (реальное время)
        </div>
        <div className="overflow-auto max-h-[140px]">
          {!entryWatchRows.length ? (
            <p className="p-2 text-xs text-slate-500">Нет индикаторов: бот прогревается или WS не передал данные.</p>
          ) : (
            <table className="w-full text-[11px] font-mono">
              <thead className="sticky top-0 bg-slate-100 text-slate-600 border-b border-slate-200">
                <tr>
                  <th className="p-1.5 text-left font-normal">Пара</th>
                  <th className="p-1.5 text-left font-normal">Статус</th>
                  <th className="p-1.5 text-left font-normal">Причина</th>
                  <th className="p-1.5 text-right font-normal">Score</th>
                  <th className="p-1.5 text-right font-normal">Цена / EMA</th>
                </tr>
              </thead>
              <tbody>
                {entryWatchRows.map((r) => (
                  <tr key={r.symbol} className="border-b border-slate-100">
                    <td className="p-1.5">{r.symbol}</td>
                    <td className="p-1.5">
                      {r.ready ? (
                        <span className="text-emerald-700 font-medium">READY {r.side}</span>
                      ) : (
                        <span className={r.allow ? "text-amber-700" : "text-slate-500"}>
                          {r.allow ? "ожидание триггера" : "фильтр блокирует"}
                        </span>
                      )}
                    </td>
                    <td className="p-1.5 text-slate-600 max-w-[240px] truncate" title={r.reason}>
                      {r.reason}
                    </td>
                    <td className="p-1.5 text-right">{Number.isFinite(r.score) ? r.score.toFixed(1) : "0.0"}</td>
                    <td className="p-1.5 text-right text-slate-600">
                      {r.close.toFixed(3)} / {r.emaNow.toFixed(3)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </section>

      {/* Открытые | Зафиксированные */}
      <section className="flex-1 min-h-0 grid grid-cols-1 lg:grid-cols-2 gap-0 border-b border-slate-200">
        <div className="border-b lg:border-b-0 lg:border-r border-slate-200 flex flex-col min-h-[220px] max-h-[42vh]">
          <div className="px-3 py-1.5 text-[10px] uppercase tracking-wider text-slate-500 border-b border-slate-200 shrink-0 bg-slate-50">
            Открытые позиции
          </div>
          <div className="overflow-auto flex-1 p-2 space-y-2">
            {!positions.length ? (
              <p className="text-slate-500 text-xs p-2">Нет открытых EMA-позиций</p>
            ) : (
              positions.map((p, i) => (
                <div
                  key={`${p.symbol}-${i}`}
                  className="border border-slate-200 rounded p-2 bg-slate-50 text-[11px] font-mono shadow-sm"
                >
                  <div className="flex justify-between gap-2">
                    <span className="text-emerald-800 font-medium">{String(p.symbol ?? "")}</span>
                    <span className={p.side === "LONG" ? "text-sky-700" : "text-orange-700"}>{p.side}</span>
                  </div>
                  <div className="mt-1 grid grid-cols-2 gap-x-3 gap-y-0.5 text-slate-600">
                    <span>Вход</span>
                    <span className="text-right text-slate-900">{Number(p.entry_price ?? 0).toFixed(2)}</span>
                    <span>Сейчас</span>
                    <span className="text-right text-slate-900">{Number(p.current_price ?? 0).toFixed(2)}</span>
                    <span>Маржа</span>
                    <span className="text-right text-amber-800">${Number(p.size_usdt ?? 0).toFixed(2)}</span>
                    <span>С плечом</span>
                    <span className="text-right">${Number(p.notional_usdt ?? 0).toFixed(2)} ×{p.leverage ?? 1}</span>
                    <span>P&amp;L нер.</span>
                    <span
                      className={`text-right ${Number(p.pnl_usdt ?? 0) >= 0 ? "text-emerald-700" : "text-rose-600"}`}
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
          <div className="px-3 py-1.5 text-[10px] uppercase tracking-wider text-slate-500 border-b border-slate-200 shrink-0 bg-slate-50">
            Зафиксировано {closedToday.length ? `(сегодня UTC ${todayUtc})` : "(последние в ленте)"}
          </div>
          <div className="overflow-auto flex-1 p-2 space-y-2">
            {!fixedList.length ? (
              <p className="text-slate-500 text-xs p-2">Нет закрытых сделок в выборке</p>
            ) : (
              fixedList.map((t) => {
                const { d, t: tm } = fmtDt(t.timestamp_close);
                const pnl = Number(t.pnl_usdt ?? 0);
                return (
                  <div
                    key={String(t.id)}
                    className="border border-slate-200 rounded p-2 bg-white text-[11px] font-mono shadow-sm"
                  >
                    <div className="flex justify-between">
                      <span className="text-slate-800">{String(t.symbol ?? "")}</span>
                      <span className={pnl >= 0 ? "text-emerald-700" : "text-rose-600"}>${pnl.toFixed(4)}</span>
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
      <section className="flex flex-col min-h-[280px] flex-1 border-t border-slate-200">
        <div className="flex flex-wrap items-center gap-2 px-3 py-1.5 border-b border-slate-200 bg-slate-50 shrink-0">
          <span className="text-[10px] uppercase tracking-wider text-slate-500">История сделок</span>
          <input
            type="date"
            className="bg-white border border-slate-300 rounded px-1 py-0.5 text-[11px]"
            value={dayPick}
            onChange={(e) => setDayPick(e.target.value)}
          />
          <button
            type="button"
            className="text-[11px] px-2 py-0.5 rounded border border-emerald-600 bg-emerald-600 text-white hover:bg-emerald-700"
            onClick={loadDayHistory}
          >
            Загрузить день из БД
          </button>
          {historyMode === "day" ? (
            <button
              type="button"
              className="text-[11px] px-2 py-0.5 rounded border border-slate-300 bg-white hover:bg-slate-100"
              onClick={backToFeedHistory}
            >
              Лента с сервера
            </button>
          ) : null}
          {historyMode === "day" && emaTradeByDay?.error ? (
            <span className="text-rose-600 text-[11px]">{emaTradeByDay.error}</span>
          ) : null}
        </div>
        <div className="overflow-auto flex-1 bg-white">
          <table className="w-full text-left text-[11px] font-mono border-collapse">
            <thead className="sticky top-0 bg-slate-100 text-slate-600 border-b border-slate-200">
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
                  <tr key={String(t.id)} className="border-b border-slate-100 hover:bg-slate-50">
                    <td className="p-1.5 text-slate-600">{d}</td>
                    <td className="p-1.5 text-slate-600">{tm}</td>
                    <td className="p-1.5">{String(t.symbol ?? "")}</td>
                    <td className="p-1.5 text-right">{Number(t.entry_price ?? 0).toFixed(4)}</td>
                    <td className="p-1.5 text-right">{Number(t.exit_price ?? 0).toFixed(4)}</td>
                    <td className="p-1.5 text-right text-amber-800">${Number(t.size_usdt ?? 0).toFixed(2)}</td>
                    <td className="p-1.5 text-right text-slate-800">
                      ${n.toFixed(2)} <span className="text-slate-500">×{lev}</span>
                    </td>
                    <td className="p-1.5 text-slate-700 max-w-[140px] truncate" title={String(t.entry_reason ?? "")}>
                      {String(t.entry_reason ?? "—")}
                    </td>
                    <td className="p-1.5 text-slate-700">{String(t.close_reason ?? "—")}</td>
                    <td className={`p-1.5 text-right ${pnl >= 0 ? "text-emerald-700" : "text-rose-600"}`}>
                      {pnl.toFixed(4)}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          {!historyRows.length ? (
            <p className="p-4 text-slate-500 text-xs">Нет строк. Подключите бота или загрузите день из БД.</p>
          ) : null}
        </div>
      </section>
    </div>
  );
}
