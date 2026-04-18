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
    return { text: "Offline", className: "bg-ex-surface2 text-ex-muted border border-ex-border" };
  }
  const s = (status ?? "").toLowerCase();
  if (s === "running") {
    return { text: "Running", className: "bg-ex-up/15 text-ex-up border border-ex-up/30" };
  }
  if (s === "paused") {
    return { text: "Paused", className: "bg-ex-warn/10 text-ex-warn border border-ex-warn/25" };
  }
  if (s === "stopped") {
    return { text: "Stopped", className: "bg-ex-surface2 text-ex-muted border border-ex-border" };
  }
  return { text: status || "—", className: "bg-ex-surface2 text-ex-text border border-ex-border" };
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
        const rawConf = ind.entry_confidence_score;
        const conf =
          rawConf !== undefined && rawConf !== null && String(rawConf) !== ""
            ? Number(rawConf)
            : null;
        const confOk = conf !== null && Number.isFinite(conf);
        return {
          symbol,
          ready,
          side,
          reason,
          score,
          allow,
          close,
          emaNow,
          conf: confOk ? conf : null,
          oteL: Boolean(ind.in_ote_long),
          oteS: Boolean(ind.in_ote_short),
          obB: Boolean(ind.price_in_bullish_ob),
          obBe: Boolean(ind.price_in_bearish_ob),
        };
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
    <div className="min-h-screen flex flex-col bg-ex-bg">
      {!isConnected ? (
        <div className="border-b border-ex-warn/30 bg-ex-warn/5 px-4 py-2.5 text-[12px] text-ex-warn leading-relaxed">
          <span className="font-semibold">Нет подключения к боту.</span>{" "}
          <span className="text-ex-muted">WS:</span>{" "}
          <code className="ex-num rounded bg-ex-surface px-1 py-0.5 text-ex-text border border-ex-border">{wsUrl}</code>
          {isLocalWs ? (
            <>
              {" "}
              Запустите бота и проверьте <code className="ex-num text-ex-text">WS_PORT</code> в{" "}
              <code className="ex-num text-ex-text">.env</code>.
            </>
          ) : (
            <>
              {" "}
              В <code className="ex-num text-ex-text">frontend/.env</code> задайте{" "}
              <code className="ex-num text-ex-text">VITE_WS_URL</code>.
            </>
          )}
        </div>
      ) : null}

      {/* Верхняя панель — как у бирж: бренд + статус + метрики */}
      <header className="shrink-0 border-b border-ex-border bg-ex-surface">
        <div className="flex flex-wrap items-center justify-between gap-4 px-4 py-3">
          <div className="flex flex-wrap items-center gap-4">
            <div>
              <div className="text-[15px] font-semibold tracking-tight text-ex-text">EMA Scalper</div>
              <div className="text-[11px] text-ex-muted">Hyperliquid · 5m · симуляция / мониторинг</div>
            </div>
            <span
              className={`inline-flex items-center rounded px-2 py-0.5 text-[11px] font-medium ${statusUi.className}`}
            >
              {statusUi.text}
            </span>
            <div className="flex items-center gap-2">
              <button
                type="button"
                disabled={!isConnected || !isRunning}
                onClick={() => sendMessage({ action: "pause" })}
                className="ex-btn-secondary text-[12px]"
              >
                Пауза
              </button>
              <button
                type="button"
                disabled={!isConnected || isRunning}
                onClick={() => sendMessage({ action: "resume" })}
                className="ex-btn-primary text-[12px]"
              >
                Старт
              </button>
            </div>
          </div>
          <div className="flex flex-wrap items-end gap-x-8 gap-y-2 text-[12px]">
            <div>
              <div className="text-[11px] text-ex-muted mb-0.5">Маржа в позициях</div>
              <div className="ex-num font-medium text-ex-text">
                {openMargin.toFixed(2)} <span className="text-ex-muted font-sans font-normal">USDT</span>
              </div>
            </div>
            <div>
              <div className="text-[11px] text-ex-muted mb-0.5">Нереализ. P&amp;L</div>
              <div className={`ex-num font-medium ${openUnrealized >= 0 ? "ex-pnl-up" : "ex-pnl-down"}`}>
                {openUnrealized >= 0 ? "+" : ""}
                {openUnrealized.toFixed(4)} USDT
              </div>
            </div>
            <div>
              <div className="text-[11px] text-ex-muted mb-0.5">Связь</div>
              <div className={`ex-num font-medium ${isConnected ? "text-ex-up" : "ex-pnl-down"}`}>
                {isConnected ? "Live" : "—"}
              </div>
            </div>
          </div>
        </div>
      </header>

      {/* Сводка дня — отдельная полоса */}
      <div className="shrink-0 border-b border-ex-border bg-ex-surface2 px-4 py-2.5">
        <div className="flex flex-wrap items-center gap-8 text-[12px]">
          <span className="text-ex-muted text-[11px] uppercase tracking-wide">Сегодня (UTC)</span>
          <span>
            <span className="text-ex-muted">PnL </span>
            <span className={`ex-num font-semibold ${todayPnl >= 0 ? "ex-pnl-up" : "ex-pnl-down"}`}>
              {todayPnl >= 0 ? "+" : ""}
              {todayPnl.toFixed(4)} USDT
            </span>
          </span>
          <span className="text-ex-muted">
            Сделок: <span className="ex-num text-ex-text">{todayTrades}</span>
          </span>
        </div>
      </div>

      {/* Таблица сигналов */}
      <section className="shrink-0 ex-panel border-b border-ex-border">
        <div className="ex-section-title flex items-center justify-between">
          <span>Сигналы входа</span>
          <span className="normal-case font-normal text-ex-dim">обновление по WS</span>
        </div>
        <div className="overflow-auto max-h-[200px]">
          {!entryWatchRows.length ? (
            <p className="p-3 text-[12px] text-ex-muted">Нет данных индикаторов (прогрев или нет связи).</p>
          ) : (
            <table className="w-full text-[12px]">
              <thead className="sticky top-0 ex-table-head">
                <tr>
                  <th className="px-3 py-2 text-left font-medium">Рынок</th>
                  <th className="px-3 py-2 text-left font-medium">Статус</th>
                  <th className="px-3 py-2 text-left font-medium">Комментарий</th>
                  <th className="px-3 py-2 text-right font-medium ex-num">Auto</th>
                  <th className="px-3 py-2 text-right font-medium ex-num">Conf</th>
                  <th className="px-3 py-2 text-center font-medium">OTE</th>
                  <th className="px-3 py-2 text-center font-medium">OB</th>
                  <th className="px-3 py-2 text-right font-medium ex-num">Цена / EMA</th>
                </tr>
              </thead>
              <tbody>
                {entryWatchRows.map((r) => (
                  <tr
                    key={r.symbol}
                    className="border-b border-ex-border/80 hover:bg-ex-raised/50 transition-colors"
                  >
                    <td className="px-3 py-2 font-medium text-ex-text">{r.symbol}</td>
                    <td className="px-3 py-2">
                      {r.ready ? (
                        <span className="text-ex-up font-medium">
                          Готов {r.side === "LONG" ? "Long" : r.side === "SHORT" ? "Short" : r.side}
                        </span>
                      ) : (
                        <span className={r.allow ? "text-ex-warn" : "text-ex-muted"}>
                          {r.allow ? "Ожидание" : "Фильтр"}
                        </span>
                      )}
                    </td>
                    <td className="px-3 py-2 text-ex-muted max-w-[min(280px,40vw)] truncate" title={r.reason}>
                      {r.reason}
                    </td>
                    <td className="px-3 py-2 text-right ex-num text-ex-text">
                      {Number.isFinite(r.score) ? r.score.toFixed(1) : "0.0"}
                    </td>
                    <td className="px-3 py-2 text-right ex-num text-ex-text">{r.conf !== null ? r.conf.toFixed(0) : "—"}</td>
                    <td className="px-3 py-2 text-center text-[11px] ex-num">
                      {r.oteL || r.oteS ? (
                        <>
                          {r.oteL ? <span className="text-ex-up">L</span> : null}
                          {r.oteS ? <span className="text-ex-down ml-0.5">S</span> : null}
                        </>
                      ) : (
                        "—"
                      )}
                    </td>
                    <td className="px-3 py-2 text-center text-[11px]">
                      {r.obB ? <span className="text-ex-up">↑</span> : null}
                      {r.obBe ? <span className="text-ex-down">↓</span> : null}
                      {!r.obB && !r.obBe ? <span className="text-ex-dim">—</span> : null}
                    </td>
                    <td className="px-3 py-2 text-right ex-num text-ex-muted">
                      {r.close.toFixed(3)} / {r.emaNow.toFixed(3)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </section>

      <section className="flex-1 min-h-0 grid grid-cols-1 lg:grid-cols-2 border-b border-ex-border">
        <div className="flex flex-col min-h-[200px] max-h-[44vh] border-b lg:border-b-0 lg:border-r border-ex-border">
          <div className="ex-section-title">Открытые позиции</div>
          <div className="overflow-auto flex-1 p-3 space-y-2 bg-ex-bg">
            {!positions.length ? (
              <p className="text-[12px] text-ex-muted py-2">Нет открытых позиций</p>
            ) : (
              positions.map((p, i) => (
                <div
                  key={`${p.symbol}-${i}`}
                  className="ex-panel rounded-sm p-3 text-[12px]"
                >
                  <div className="flex justify-between items-start gap-2 mb-2">
                    <span className="font-semibold text-ex-text">{String(p.symbol ?? "")}</span>
                    <span
                      className={`text-[11px] font-semibold px-1.5 py-0.5 rounded ${
                        p.side === "LONG" ? "bg-ex-up/15 text-ex-up" : "bg-ex-down/15 text-ex-down"
                      }`}
                    >
                      {p.side}
                    </span>
                  </div>
                  <div className="grid grid-cols-2 gap-x-4 gap-y-1.5 text-ex-muted text-[11px]">
                    <span>Вход</span>
                    <span className="ex-num text-right text-ex-text">{Number(p.entry_price ?? 0).toFixed(2)}</span>
                    <span>Марк</span>
                    <span className="ex-num text-right text-ex-text">{Number(p.current_price ?? 0).toFixed(2)}</span>
                    <span>Маржа</span>
                    <span className="ex-num text-right text-ex-warn">${Number(p.size_usdt ?? 0).toFixed(2)}</span>
                    <span>Номинал × плечо</span>
                    <span className="ex-num text-right text-ex-text">
                      ${Number(p.notional_usdt ?? 0).toFixed(2)} ×{p.leverage ?? 1}
                    </span>
                    <span>P&amp;L (u)</span>
                    <span
                      className={`ex-num text-right font-medium ${
                        Number(p.pnl_usdt ?? 0) >= 0 ? "ex-pnl-up" : "ex-pnl-down"
                      }`}
                    >
                      {Number(p.pnl_usdt ?? 0) >= 0 ? "+" : ""}
                      ${Number(p.pnl_usdt ?? 0).toFixed(4)}
                    </span>
                  </div>
                  {p.entry_reason ? (
                    <div className="mt-2 pt-2 border-t border-ex-border text-[10px] text-ex-dim truncate" title={String(p.entry_reason)}>
                      {String(p.entry_reason)}
                    </div>
                  ) : null}
                </div>
              ))
            )}
          </div>
        </div>

        <div className="flex flex-col min-h-[200px] max-h-[44vh]">
          <div className="ex-section-title">
            История закрытий {closedToday.length ? `· UTC ${todayUtc}` : "· лента"}
          </div>
          <div className="overflow-auto flex-1 p-3 space-y-2 bg-ex-bg">
            {!fixedList.length ? (
              <p className="text-[12px] text-ex-muted py-2">Нет записей</p>
            ) : (
              fixedList.map((t) => {
                const { d, t: tm } = fmtDt(t.timestamp_close);
                const pnl = Number(t.pnl_usdt ?? 0);
                return (
                  <div key={String(t.id)} className="ex-panel rounded-sm p-3 text-[12px]">
                    <div className="flex justify-between items-center">
                      <span className="font-medium text-ex-text">{String(t.symbol ?? "")}</span>
                      <span className={`ex-num font-semibold ${pnl >= 0 ? "ex-pnl-up" : "ex-pnl-down"}`}>
                        {pnl >= 0 ? "+" : ""}
                        {pnl.toFixed(4)}
                      </span>
                    </div>
                    <div className="text-[11px] text-ex-muted mt-1 ex-num">
                      {d} {tm}
                    </div>
                    <div className="text-[11px] text-ex-dim mt-1">
                      {String(t.close_reason ?? "")} · маржа ${Number(t.size_usdt ?? 0).toFixed(2)}
                    </div>
                  </div>
                );
              })
            )}
          </div>
        </div>
      </section>

      <section className="flex flex-col min-h-[260px] flex-1">
        <div className="flex flex-wrap items-center gap-2 px-3 py-2 border-b border-ex-border bg-ex-surface2">
          <span className="text-[11px] font-medium uppercase tracking-wide text-ex-muted">Все сделки</span>
          <input
            type="date"
            className="rounded border border-ex-border bg-ex-surface px-2 py-1 text-[12px] text-ex-text ex-num focus:border-ex-line focus:outline-none"
            value={dayPick}
            onChange={(e) => setDayPick(e.target.value)}
          />
          <button type="button" className="ex-btn-primary text-[12px] py-1" onClick={loadDayHistory}>
            Загрузить день
          </button>
          {historyMode === "day" ? (
            <button type="button" className="ex-btn-secondary text-[12px] py-1" onClick={backToFeedHistory}>
              Лента WS
            </button>
          ) : null}
          {historyMode === "day" && emaTradeByDay?.error ? (
            <span className="text-[12px] text-ex-down">{emaTradeByDay.error}</span>
          ) : null}
        </div>
        <div className="overflow-auto flex-1 bg-ex-bg">
          <table className="w-full text-left text-[12px] border-collapse">
            <thead className="sticky top-0 ex-table-head z-10">
              <tr>
                <th className="px-3 py-2 font-medium">Дата</th>
                <th className="px-3 py-2 font-medium">Время</th>
                <th className="px-3 py-2 font-medium">Рынок</th>
                <th className="px-3 py-2 font-medium text-right ex-num">Вход</th>
                <th className="px-3 py-2 font-medium text-right ex-num">Выход</th>
                <th className="px-3 py-2 font-medium text-right ex-num">Маржа</th>
                <th className="px-3 py-2 font-medium text-right ex-num">Номинал</th>
                <th className="px-3 py-2 font-medium max-w-[120px]">Вход (reason)</th>
                <th className="px-3 py-2 font-medium">Выход</th>
                <th className="px-3 py-2 font-medium text-right ex-num">P&amp;L</th>
              </tr>
            </thead>
            <tbody>
              {historyRows.map((t) => {
                const { d, t: tm } = fmtDt(t.timestamp_close);
                const pnl = Number(t.pnl_usdt ?? 0);
                const n = notionWithLev(t);
                const lev = Math.max(1, Number(t.leverage ?? 1));
                return (
                  <tr key={String(t.id)} className="border-b border-ex-border hover:bg-ex-surface/80">
                    <td className="px-3 py-2 text-ex-muted ex-num">{d}</td>
                    <td className="px-3 py-2 text-ex-muted ex-num">{tm}</td>
                    <td className="px-3 py-2 font-medium text-ex-text">{String(t.symbol ?? "")}</td>
                    <td className="px-3 py-2 text-right ex-num text-ex-text">{Number(t.entry_price ?? 0).toFixed(4)}</td>
                    <td className="px-3 py-2 text-right ex-num text-ex-text">{Number(t.exit_price ?? 0).toFixed(4)}</td>
                    <td className="px-3 py-2 text-right ex-num text-ex-warn">${Number(t.size_usdt ?? 0).toFixed(2)}</td>
                    <td className="px-3 py-2 text-right ex-num text-ex-text">
                      ${n.toFixed(2)} <span className="text-ex-muted">×{lev}</span>
                    </td>
                    <td className="px-3 py-2 text-ex-muted max-w-[140px] truncate text-[11px]" title={String(t.entry_reason ?? "")}>
                      {String(t.entry_reason ?? "—")}
                    </td>
                    <td className="px-3 py-2 text-ex-muted text-[11px]">{String(t.close_reason ?? "—")}</td>
                    <td className={`px-3 py-2 text-right ex-num font-medium ${pnl >= 0 ? "ex-pnl-up" : "ex-pnl-down"}`}>
                      {pnl >= 0 ? "+" : ""}
                      {pnl.toFixed(4)}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          {!historyRows.length ? (
            <p className="p-6 text-center text-[12px] text-ex-muted">Нет сделок. Подключите бота или загрузите день из БД.</p>
          ) : null}
        </div>
      </section>
    </div>
  );
}
