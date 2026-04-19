import { useEffect, useMemo, useState } from "react";
import {
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  YAxis,
} from "recharts";
import { EntrySearchChartsPanel, type ChartSnap } from "./EntrySearchCharts";

type SignalRow = {
  status: string;
  reason: string;
  structure_15m: string;
  trend_1h: string;
  ema: number;
  price: number;
  above_count: number;
  below_count: number;
  volume_ratio: number;
  rsi: number;
  ema_1h_fast: number;
  ema_1h_slow: number;
  atr: number;
};

type Payload = {
  ts: string;
  bot_status: string;
  dry_run: boolean;
  pnl_today: number;
  trades_today: number;
  ema_scalper: {
    positions: Record<string, unknown>[];
    signals: Record<string, SignalRow>;
    stats: Record<string, number>;
    recent_trades: Record<string, unknown>[];
    charts?: Record<string, ChartSnap>;
  };
};

const WS_URL = import.meta.env.VITE_WS_URL || "ws://127.0.0.1:8765";

function reasonBadgeClass(reason: string): string {
  const r = (reason || "").toUpperCase();
  if (r === "TP") return "bg-[#1677ff]/20 text-[#1677ff]";
  if (r === "SL") return "bg-okx-loss/20 text-okx-loss";
  if (r.includes("TRAIL") || r === "SL")
    return "bg-gradient-to-r from-[#1677ff]/30 to-okx-profit/30 text-okx-text";
  if (r === "TIME") return "bg-okx-muted/30 text-okx-muted";
  if (r === "MANUAL") return "bg-okx-accent/20 text-okx-accent";
  return "bg-okx-border/40 text-okx-muted";
}

function structColor(s: string): string {
  if (s === "BULLISH" || s === "STRONG_UP") return "text-okx-profit";
  if (s === "BEARISH" || s === "STRONG_DOWN") return "text-okx-loss";
  return "text-okx-muted";
}

function Trend1HCell({ trend }: { trend: string }) {
  const t = (trend || "NEUTRAL").trim();
  if (t === "STRONG_UP") {
    return (
      <span className="text-okx-profit">
        ▲▲ <span className="hidden sm:inline">STRONG_UP</span>
      </span>
    );
  }
  if (t === "STRONG_DOWN") {
    return (
      <span className="text-okx-loss">
        ▼▼ <span className="hidden sm:inline">STRONG_DOWN</span>
      </span>
    );
  }
  if (t === "WEAK_UP") {
    return (
      <span className="text-emerald-400/90">
        ▲ <span className="hidden sm:inline">WEAK_UP</span>
      </span>
    );
  }
  if (t === "WEAK_DOWN") {
    return (
      <span className="text-rose-400/90">
        ▼ <span className="hidden sm:inline">WEAK_DOWN</span>
      </span>
    );
  }
  return <span className="text-okx-muted">—</span>;
}

export default function App() {
  const [data, setData] = useState<Payload | null>(null);
  const [wsOk, setWsOk] = useState(false);

  useEffect(() => {
    let ws: WebSocket | null = null;
    let alive = true;
    const connect = () => {
      ws = new WebSocket(WS_URL);
      ws.onopen = () => {
        if (alive) setWsOk(true);
      };
      ws.onclose = () => {
        if (alive) setWsOk(false);
        setTimeout(connect, 2000);
      };
      ws.onerror = () => setWsOk(false);
      ws.onmessage = (ev) => {
        try {
          setData(JSON.parse(ev.data as string));
        } catch {
          /* ignore */
        }
      };
    };
    connect();
    return () => {
      alive = false;
      ws?.close();
    };
  }, []);

  const equityPoints = useMemo(() => {
    const rows = (data?.ema_scalper?.recent_trades || [])
      .slice()
      .reverse()
      .slice(-30);
    let acc = 0;
    return rows.map((t, i) => {
      acc += Number(t.pnl_usdt || 0);
      return { i, eq: acc };
    });
  }, [data]);

  const es = data?.ema_scalper;
  const stats = es?.stats || {};

  return (
    <div className="min-h-screen font-sans text-sm">
      <header className="flex flex-wrap items-center justify-between gap-4 border-b border-okx-border bg-okx-bg px-6 py-4">
        <div className="flex items-center gap-6">
          <h1 className="font-mono text-xl font-semibold tracking-tight text-okx-text">
            EMA SCALPER
          </h1>
          <span
            className={`inline-flex items-center gap-2 rounded px-2 py-0.5 font-mono text-xs ${
              data?.dry_run
                ? "bg-okx-accent/15 text-okx-accent"
                : "bg-okx-loss/15 text-okx-loss"
            }`}
          >
            <span
              className={`h-2 w-2 rounded-full ${
                data?.dry_run ? "bg-okx-accent" : "bg-okx-loss animate-pulse-dot"
              }`}
            />
            {data?.dry_run ? "DRY RUN" : "LIVE"}
          </span>
          <span
            className={`font-mono text-xs ${wsOk ? "text-okx-profit" : "text-okx-loss"}`}
          >
            <span className="mr-1 inline-block h-2 w-2 rounded-full bg-current animate-pulse-dot" />
            {wsOk ? "live" : "offline"}
          </span>
        </div>
        <div className="font-mono text-lg text-okx-accent">
          PnL:{" "}
          <span
            className={
              (data?.pnl_today || 0) >= 0 ? "text-okx-profit" : "text-okx-loss"
            }
          >
            {data != null ? `$${data.pnl_today.toFixed(2)}` : "—"}
          </span>
        </div>
      </header>

      <div className="grid gap-4 p-4 lg:grid-cols-2">
        <section className="rounded border border-okx-border bg-okx-card p-4">
          <h2 className="mb-3 font-mono text-xs uppercase tracking-wider text-okx-muted">
            Сигналы входа
          </h2>
          <div className="overflow-x-auto">
            <table className="w-full border-collapse font-mono text-xs">
              <thead>
                <tr className="border-b border-okx-border text-left text-okx-muted">
                  <th className="pb-2 pr-2">Рынок</th>
                  <th className="pb-2 pr-2">СТРУКТ. 15m</th>
                  <th className="pb-2 pr-2">ТРЕНД 1H</th>
                  <th className="pb-2 pr-2">Статус</th>
                  <th className="pb-2">Цена / EMA</th>
                </tr>
              </thead>
              <tbody>
                {Object.entries(es?.signals || {}).map(([sym, row]) => (
                  <tr key={sym} className="border-b border-okx-border/60">
                    <td className="py-2 pr-2 text-okx-text">{sym}</td>
                    <td className={`py-2 pr-2 ${structColor(row.structure_15m)}`}>
                      {row.structure_15m}
                    </td>
                    <td className="py-2 pr-2 font-mono">
                      <Trend1HCell trend={row.trend_1h} />
                    </td>
                    <td className="py-2 pr-2">
                      <span className="flex items-center gap-1">
                        {(row.status === "READY_LONG" ||
                          row.status === "READY_SHORT") && (
                          <span className="h-2 w-2 animate-pulse-dot rounded-full bg-okx-profit" />
                        )}
                        <span className="text-okx-text">{row.status}</span>
                      </span>
                      <span className="block text-[10px] text-okx-muted">
                        {row.reason}
                      </span>
                    </td>
                    <td className="py-2 text-okx-text">
                      {row.price?.toFixed(2) ?? "—"} /{" "}
                      {row.ema?.toFixed(2) ?? "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>

        <section className="rounded border border-okx-border bg-okx-card p-4">
          <h2 className="mb-3 font-mono text-xs uppercase tracking-wider text-okx-muted">
            Открытые позиции
          </h2>
          {(es?.positions?.length || 0) === 0 ? (
            <p className="text-okx-muted">Нет позиций</p>
          ) : (
            <div className="space-y-3">
              {es!.positions.map((p, idx) => {
                const pos = p as Record<string, unknown>;
                return (
                  <div
                    key={idx}
                    className="rounded border border-okx-border p-3 font-mono text-xs"
                  >
                    <div className="mb-2 flex justify-between">
                      <span>
                        {String(pos.side) === "LONG" ? "▲" : "▼"}{" "}
                        {String(pos.symbol)}
                      </span>
                      <span className="text-okx-muted">
                        x{String(pos.leverage)}{" "}
                        {pos.trailing_active ? "🔄 TRAIL ON" : ""}
                      </span>
                    </div>
                    <div className="text-okx-text">
                      Вход ${Number(pos.entry_price).toFixed(2)} → Сейчас $
                      {Number(pos.current_price).toFixed(2)}{" "}
                      <span
                        className={
                          Number(pos.pnl_pct) >= 0
                            ? "text-okx-profit"
                            : "text-okx-loss"
                        }
                      >
                        {Number(pos.pnl_pct) >= 0 ? "+" : ""}
                        {Number(pos.pnl_pct).toFixed(2)}%
                      </span>
                    </div>
                    <div className="mt-2 h-2 w-full rounded bg-okx-border">
                      <div
                        className="h-2 rounded bg-okx-accent"
                        style={{
                          width: `${Math.min(100, Number(pos.progress_to_tp || 0))}%`,
                        }}
                      />
                    </div>
                    <div className="mt-1 flex justify-between text-[10px] text-okx-muted">
                      <span>SL {Number(pos.sl_price).toFixed(2)}</span>
                      <span>TP {Number(pos.tp_price).toFixed(2)}</span>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </section>
      </div>

      <section className="mx-4 mb-4 rounded border border-okx-border bg-okx-card p-4">
        <h2 className="mb-3 font-mono text-xs uppercase tracking-wider text-okx-muted">
          Поиск точки входа — BTC · ETH · SOL
        </h2>
        <EntrySearchChartsPanel charts={es?.charts} signals={es?.signals} />
      </section>

      <div className="grid gap-4 px-4 pb-4 lg:grid-cols-2">
        <section className="rounded border border-okx-border bg-okx-card p-4">
          <h2 className="mb-2 font-mono text-xs uppercase text-okx-muted">
            Статистика
          </h2>
          <p className="font-mono text-xs leading-relaxed text-okx-text">
            Сегодня: {Number(stats.trades_today || 0)} сделок | Win:{" "}
            {Number(stats.win_rate_today || 0).toFixed(0)}% | PnL: $
            {Number(stats.pnl_today || 0).toFixed(2)} | Fees: $
            {Number(stats.fees_today || 0).toFixed(4)}
          </p>
          <p className="mt-1 font-mono text-xs text-okx-muted">
            All time: PnL ${Number(stats.pnl_alltime || 0).toFixed(2)} | WR{" "}
            {Number(stats.win_rate_alltime || 0).toFixed(0)}% | PF{" "}
            {Number(stats.profit_factor || 0).toFixed(2)} | Avg hold{" "}
            {Number(stats.avg_hold_candles || 0).toFixed(1)} свечей
          </p>
        </section>

        <section className="rounded border border-okx-border bg-okx-card p-4">
          <h2 className="mb-2 font-mono text-xs uppercase text-okx-muted">
            Equity (30 сделок)
          </h2>
          <div className="h-[100px] w-full">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={equityPoints}>
                <YAxis hide domain={["auto", "auto"]} />
                <Tooltip
                  contentStyle={{
                    background: "#141720",
                    border: "1px solid #2a2d36",
                    fontSize: 11,
                  }}
                />
                <Line
                  type="monotone"
                  dataKey="eq"
                  stroke="#1677ff"
                  dot={false}
                  strokeWidth={1.5}
                />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </section>
      </div>

      <section className="mx-4 mb-8 rounded border border-okx-border bg-okx-card p-4">
        <h2 className="mb-3 font-mono text-xs uppercase text-okx-muted">
          История сделок
        </h2>
        <div className="overflow-x-auto">
          <table className="w-full border-collapse font-mono text-[11px]">
            <thead>
              <tr className="border-b border-okx-border text-left text-okx-muted">
                <th className="pb-2 pr-2">Время UTC</th>
                <th className="pb-2 pr-2">Пара</th>
                <th className="pb-2 pr-2">Сторона</th>
                <th className="pb-2 pr-2">Вход</th>
                <th className="pb-2 pr-2">Выход</th>
                <th className="pb-2 pr-2">Свечей</th>
                <th className="pb-2 pr-2">Причина</th>
                <th className="pb-2 pr-2">Trail</th>
                <th className="pb-2">PnL $</th>
              </tr>
            </thead>
            <tbody>
              {(es?.recent_trades || []).map((t) => {
                const tr = t as Record<string, unknown>;
                return (
                  <tr key={String(tr.id)} className="border-b border-okx-border/50">
                    <td className="py-1.5 pr-2 text-okx-muted">
                      {String(tr.timestamp_close || "").slice(0, 19)}
                    </td>
                    <td className="py-1.5 pr-2">{String(tr.symbol)}</td>
                    <td className="py-1.5 pr-2">{String(tr.side)}</td>
                    <td className="py-1.5 pr-2">
                      {Number(tr.entry_price).toFixed(2)}
                    </td>
                    <td className="py-1.5 pr-2">
                      {Number(tr.exit_price).toFixed(2)}
                    </td>
                    <td className="py-1.5 pr-2">{String(tr.candles_held)}</td>
                    <td className="py-1.5 pr-2">
                      <span
                        className={`rounded px-1.5 py-0.5 ${reasonBadgeClass(
                          String(tr.close_reason || "")
                        )}`}
                      >
                        {String(tr.close_reason)}
                      </span>
                    </td>
                    <td className="py-1.5 pr-2">
                      {Number(tr.trailing_active) ? "Y" : "—"}
                    </td>
                    <td
                      className={`py-1.5 ${
                        Number(tr.pnl_usdt) >= 0
                          ? "text-okx-profit"
                          : "text-okx-loss"
                      }`}
                    >
                      {Number(tr.pnl_usdt).toFixed(4)}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}
