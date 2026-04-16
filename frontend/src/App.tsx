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
    return { text: "Нет связи с ботом", className: "border-cp-line bg-cp-panel2 text-cp-muted" };
  }
  const s = (status ?? "").toLowerCase();
  if (s === "running") {
    return {
      text: "Бот работает",
      className: "border-cp-green/50 bg-cp-green/10 text-cp-green shadow-[0_0_12px_rgba(57,255,20,0.25)]",
    };
  }
  if (s === "paused") {
    return { text: "Пауза", className: "border-cp-amber/60 bg-cp-amber/10 text-cp-amber" };
  }
  if (s === "stopped") {
    return { text: "Остановлен", className: "border-cp-line bg-cp-panel2 text-cp-muted" };
  }
  return { text: status || "—", className: "border-cp-line bg-cp-panel text-slate-300" };
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
    <div className="min-h-screen flex flex-col bg-cp-bg bg-cp-grid bg-[length:24px_24px] text-slate-200">
      {!isConnected ? (
        <div className="border-b border-cp-amber/40 bg-cp-amber/5 px-4 py-2 text-[11px] text-cp-amber leading-snug shadow-[inset_0_-1px_0_rgba(255,184,0,0.2)]">
          <strong className="font-semibold text-cp-yellow">WS offline.</strong> Подключение к{" "}
          <code className="rounded-sm border border-cp-line bg-cp-panel px-1 text-cp-cyan">{wsUrl}</code>
          {isLocalWs ? (
            <>
              . Запустите бота на этой машине (из корня проекта:{" "}
              <code className="rounded-sm border border-cp-line bg-cp-panel px-1 text-cp-cyan">
                python -m backend.main
              </code>{" "}
              или ваш systemd) и проверьте{" "}
              <code className="rounded-sm border border-cp-line bg-cp-panel px-1 text-cp-cyan">WS_PORT=8765</code> в{" "}
              <code className="rounded-sm border border-cp-line bg-cp-panel px-1 text-cp-cyan">.env</code> бота.
            </>
          ) : (
            <>
              . Бот на другом сервере — в <code className="rounded-sm border border-cp-line bg-cp-panel px-1">frontend/.env</code>{" "}
              задайте <code className="rounded-sm border border-cp-line bg-cp-panel px-1 text-cp-cyan">VITE_WS_URL=ws://IP:8765</code> и
              перезапустите <code className="rounded-sm border border-cp-line bg-cp-panel px-1 text-cp-cyan">npm run dev</code>; на VPS откройте
              порт 8765.
            </>
          )}
        </div>
      ) : null}

      <header className="border-b border-cp-line px-4 py-3 shrink-0 cp-panel">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex flex-wrap items-center gap-3">
            <h1 className="text-sm font-bold tracking-[0.15em] uppercase text-cp-yellow cp-glow-text">EMA Scalper</h1>
            <span
              className={`inline-flex items-center rounded-sm border px-2.5 py-1 text-xs font-medium ${statusUi.className}`}
            >
              {statusUi.text}
            </span>
            <div className="flex items-center gap-2">
              <button
                type="button"
                disabled={!isConnected || !isRunning}
                onClick={() => sendMessage({ action: "pause" })}
                className="cp-btn-ghost"
              >
                Пауза
              </button>
              <button
                type="button"
                disabled={!isConnected || isRunning}
                onClick={() => sendMessage({ action: "resume" })}
                className="cp-btn-primary"
              >
                Работает
              </button>
            </div>
          </div>
          <div className="flex flex-wrap gap-6 text-xs font-mono text-slate-300">
            <div>
              <span className="text-cp-muted">Маржа в открытых </span>
              <span className="text-cp-amber font-medium">${openMargin.toFixed(2)}</span>
              <span className="text-cp-muted"> USDT</span>
            </div>
            <div>
              <span className="text-cp-muted">Нереализ. P&amp;L </span>
              <span className={openUnrealized >= 0 ? "text-cp-green" : "text-cp-magenta"}>
                ${openUnrealized.toFixed(4)}
              </span>
            </div>
            <div className="text-slate-400">
              WS:{" "}
              {isConnected ? (
                <span className="text-cp-cyan font-medium">online</span>
              ) : (
                <span className="text-cp-magenta font-medium">offline</span>
              )}
            </div>
          </div>
        </div>
      </header>

      <section className="border-b border-cp-line px-4 py-2 shrink-0 cp-panel">
        <div className="text-xs font-mono flex flex-wrap gap-6">
          <span className="cp-hud-title">PnL за день (UTC)</span>
          <span>
            Сегодня:{" "}
            <span className={todayPnl >= 0 ? "text-cp-green" : "text-cp-magenta"}>${todayPnl.toFixed(4)}</span>
          </span>
          <span className="text-cp-muted">Сделок сегодня: {todayTrades}</span>
        </div>
      </section>

      <section className="border-b border-cp-line shrink-0 cp-panel">
        <div className="px-3 py-1.5 cp-hud-title border-b border-cp-line bg-cp-panel2/80">Поиск входа (реальное время)</div>
        <div className="overflow-auto max-h-[160px]">
          {!entryWatchRows.length ? (
            <p className="p-2 text-xs text-cp-muted">Нет индикаторов: бот прогревается или WS не передал данные.</p>
          ) : (
            <table className="w-full text-[11px] font-mono">
              <thead className="sticky top-0 cp-table-head">
                <tr>
                  <th className="p-1.5 text-left font-normal">Пара</th>
                  <th className="p-1.5 text-left font-normal">Статус</th>
                  <th className="p-1.5 text-left font-normal">Причина</th>
                  <th className="p-1.5 text-right font-normal">Auto</th>
                  <th className="p-1.5 text-right font-normal">Conf</th>
                  <th className="p-1.5 text-center font-normal">OTE</th>
                  <th className="p-1.5 text-center font-normal">OB</th>
                  <th className="p-1.5 text-right font-normal">Цена / EMA</th>
                </tr>
              </thead>
              <tbody>
                {entryWatchRows.map((r) => (
                  <tr key={r.symbol} className="border-b border-cp-border/80 hover:bg-cp-cyan/5">
                    <td className="p-1.5 text-cp-cyan">{r.symbol}</td>
                    <td className="p-1.5">
                      {r.ready ? (
                        <span className="text-cp-green font-medium cp-glow-text">READY {r.side}</span>
                      ) : (
                        <span className={r.allow ? "text-cp-amber" : "text-cp-muted"}>
                          {r.allow ? "ожидание триггера" : "фильтр блокирует"}
                        </span>
                      )}
                    </td>
                    <td className="p-1.5 text-slate-400 max-w-[200px] truncate" title={r.reason}>
                      {r.reason}
                    </td>
                    <td className="p-1.5 text-right text-slate-300">{Number.isFinite(r.score) ? r.score.toFixed(1) : "0.0"}</td>
                    <td className="p-1.5 text-right text-slate-300">{r.conf !== null ? r.conf.toFixed(0) : "—"}</td>
                    <td className="p-1.5 text-center text-[10px]">
                      {r.oteL || r.oteS ? (
                        <>
                          {r.oteL ? <span className="text-cp-green">L</span> : null}
                          {r.oteS ? <span className="text-cp-magenta ml-0.5">S</span> : null}
                        </>
                      ) : (
                        <span className="text-cp-dim">—</span>
                      )}
                    </td>
                    <td className="p-1.5 text-center text-[10px]">
                      {r.obB ? <span className="text-cp-cyan">↑</span> : null}
                      {r.obBe ? <span className="text-cp-magenta">↓</span> : null}
                      {!r.obB && !r.obBe ? <span className="text-cp-dim">—</span> : null}
                    </td>
                    <td className="p-1.5 text-right text-slate-400">
                      {r.close.toFixed(3)} / {r.emaNow.toFixed(3)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </section>

      <section className="flex-1 min-h-0 grid grid-cols-1 lg:grid-cols-2 gap-0 border-b border-cp-line">
        <div className="border-b lg:border-b-0 lg:border-r border-cp-line flex flex-col min-h-[220px] max-h-[42vh]">
          <div className="px-3 py-1.5 cp-hud-title border-b border-cp-line shrink-0 bg-cp-panel2/80">Открытые позиции</div>
          <div className="overflow-auto flex-1 p-2 space-y-2">
            {!positions.length ? (
              <p className="text-cp-muted text-xs p-2">Нет открытых EMA-позиций</p>
            ) : (
              positions.map((p, i) => (
                <div
                  key={`${p.symbol}-${i}`}
                  className="border border-cp-line rounded-sm cp-panel p-2 text-[11px] font-mono shadow-cp-glow"
                >
                  <div className="flex justify-between gap-2">
                    <span className="text-cp-yellow font-medium">{String(p.symbol ?? "")}</span>
                    <span className={p.side === "LONG" ? "text-cp-cyan" : "text-cp-magenta"}>{p.side}</span>
                  </div>
                  <div className="mt-1 grid grid-cols-2 gap-x-3 gap-y-0.5 text-slate-400">
                    <span>Вход</span>
                    <span className="text-right text-slate-200">{Number(p.entry_price ?? 0).toFixed(2)}</span>
                    <span>Сейчас</span>
                    <span className="text-right text-slate-200">{Number(p.current_price ?? 0).toFixed(2)}</span>
                    <span>Маржа</span>
                    <span className="text-right text-cp-amber">${Number(p.size_usdt ?? 0).toFixed(2)}</span>
                    <span>С плечом</span>
                    <span className="text-right text-slate-300">
                      ${Number(p.notional_usdt ?? 0).toFixed(2)} ×{p.leverage ?? 1}
                    </span>
                    <span>P&amp;L нер.</span>
                    <span
                      className={`text-right ${Number(p.pnl_usdt ?? 0) >= 0 ? "text-cp-green" : "text-cp-magenta"}`}
                    >
                      ${Number(p.pnl_usdt ?? 0).toFixed(4)}
                    </span>
                  </div>
                  {p.entry_reason ? (
                    <div className="mt-1 text-[10px] text-cp-muted truncate" title={String(p.entry_reason)}>
                      Вход: {String(p.entry_reason)}
                    </div>
                  ) : null}
                </div>
              ))
            )}
          </div>
        </div>

        <div className="flex flex-col min-h-[220px] max-h-[42vh]">
          <div className="px-3 py-1.5 cp-hud-title border-b border-cp-line shrink-0 bg-cp-panel2/80">
            Зафиксировано {closedToday.length ? `(сегодня UTC ${todayUtc})` : "(последние в ленте)"}
          </div>
          <div className="overflow-auto flex-1 p-2 space-y-2">
            {!fixedList.length ? (
              <p className="text-cp-muted text-xs p-2">Нет закрытых сделок в выборке</p>
            ) : (
              fixedList.map((t) => {
                const { d, t: tm } = fmtDt(t.timestamp_close);
                const pnl = Number(t.pnl_usdt ?? 0);
                return (
                  <div
                    key={String(t.id)}
                    className="border border-cp-line rounded-sm cp-panel p-2 text-[11px] font-mono"
                  >
                    <div className="flex justify-between">
                      <span className="text-slate-200">{String(t.symbol ?? "")}</span>
                      <span className={pnl >= 0 ? "text-cp-green" : "text-cp-magenta"}>${pnl.toFixed(4)}</span>
                    </div>
                    <div className="text-[10px] text-cp-muted mt-0.5">
                      {d} {tm}
                    </div>
                    <div className="mt-1 text-[10px] text-cp-muted">
                      {String(t.close_reason ?? "")} · маржа ${Number(t.size_usdt ?? 0).toFixed(2)}
                    </div>
                  </div>
                );
              })
            )}
          </div>
        </div>
      </section>

      <section className="flex flex-col min-h-[280px] flex-1 border-t border-cp-line">
        <div className="flex flex-wrap items-center gap-2 px-3 py-1.5 border-b border-cp-line shrink-0 cp-panel">
          <span className="cp-hud-title">История сделок</span>
          <input
            type="date"
            className="bg-cp-panel2 border border-cp-line rounded-sm px-1 py-0.5 text-[11px] text-slate-200 focus:border-cp-cyan focus:outline-none"
            value={dayPick}
            onChange={(e) => setDayPick(e.target.value)}
          />
          <button
            type="button"
            className="text-[11px] px-2 py-0.5 rounded-sm border border-cp-yellow/70 bg-cp-yellow/10 text-cp-yellow hover:bg-cp-yellow/20"
            onClick={loadDayHistory}
          >
            Загрузить день из БД
          </button>
          {historyMode === "day" ? (
            <button
              type="button"
              className="text-[11px] px-2 py-0.5 rounded-sm border border-cp-line bg-cp-panel2 text-slate-300 hover:border-cp-cyan/40"
              onClick={backToFeedHistory}
            >
              Лента с сервера
            </button>
          ) : null}
          {historyMode === "day" && emaTradeByDay?.error ? (
            <span className="text-cp-magenta text-[11px]">{emaTradeByDay.error}</span>
          ) : null}
        </div>
        <div className="overflow-auto flex-1 bg-cp-bg">
          <table className="w-full text-left text-[11px] font-mono border-collapse">
            <thead className="sticky top-0 cp-table-head">
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
                  <tr key={String(t.id)} className="border-b border-cp-border/60 hover:bg-cp-cyan/5">
                    <td className="p-1.5 text-cp-muted">{d}</td>
                    <td className="p-1.5 text-cp-muted">{tm}</td>
                    <td className="p-1.5 text-cp-cyan">{String(t.symbol ?? "")}</td>
                    <td className="p-1.5 text-right text-slate-300">{Number(t.entry_price ?? 0).toFixed(4)}</td>
                    <td className="p-1.5 text-right text-slate-300">{Number(t.exit_price ?? 0).toFixed(4)}</td>
                    <td className="p-1.5 text-right text-cp-amber">${Number(t.size_usdt ?? 0).toFixed(2)}</td>
                    <td className="p-1.5 text-right text-slate-300">
                      ${n.toFixed(2)} <span className="text-cp-muted">×{lev}</span>
                    </td>
                    <td className="p-1.5 text-slate-400 max-w-[140px] truncate" title={String(t.entry_reason ?? "")}>
                      {String(t.entry_reason ?? "—")}
                    </td>
                    <td className="p-1.5 text-slate-400">{String(t.close_reason ?? "—")}</td>
                    <td className={`p-1.5 text-right ${pnl >= 0 ? "text-cp-green" : "text-cp-magenta"}`}>
                      {pnl.toFixed(4)}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          {!historyRows.length ? (
            <p className="p-4 text-cp-muted text-xs">Нет строк. Подключите бота или загрузите день из БД.</p>
          ) : null}
        </div>
      </section>
    </div>
  );
}
