import { useEffect, useMemo, useState } from "react";

type SignalRow = {
  status: string;
  reason: string;
  structure_15m: string;
  trend_1h: string;
  ema: number;
  price: number;
};

type OpenPosition = {
  symbol: string;
  side: string;
  entry_price: number;
  current_price: number;
  size_usdt: number;
  notional: number;
  leverage: number;
  pnl_pct: number;
  pnl_usdt: number;
  candles_held: number;
  trailing_active: boolean;
  structure_at_entry?: string;
  trend_1h_at_entry?: string;
};

type ClosedTrade = {
  id: number;
  timestamp_open: string;
  timestamp_close: string;
  symbol: string;
  side: string;
  entry_price: number;
  exit_price: number;
  size_usdt: number;
  notional: number;
  leverage: number;
  pnl_usdt: number;
  close_reason: string;
  candles_held: number;
  trailing_active: number;
  structure_15m_at_entry?: string;
  trend_1h_at_entry?: string;
};

type Payload = {
  ts: string;
  bot_status: string;
  dry_run: boolean;
  pnl_today: number;
  ema_scalper: {
    positions: OpenPosition[];
    signals: Record<string, SignalRow>;
    recent_trades: ClosedTrade[];
    stats: Record<string, number>;
  };
};

const WS_URL = import.meta.env.VITE_WS_URL || "ws://127.0.0.1:8765";

function fmt(n: unknown, d = 2): string {
  const x = Number(n || 0);
  if (!Number.isFinite(x)) return "0";
  return x.toFixed(d);
}

function entryReasonFromTrade(t: ClosedTrade | OpenPosition): string {
  const s15 = String((t as any).structure_15m_at_entry || (t as any).structure_at_entry || "—");
  const t1h = String((t as any).trend_1h_at_entry || "—");
  return `EMA + ${s15} + ${t1h}`;
}

export default function StableTradeApp() {
  const [data, setData] = useState<Payload | null>(null);
  const [wsLive, setWsLive] = useState(false);
  const [selectedDate, setSelectedDate] = useState("ALL");

  useEffect(() => {
    let ws: WebSocket | null = null;
    let stop = false;
    let retry = 0;

    const connect = () => {
      if (stop) return;
      ws = new WebSocket(WS_URL);

      ws.onopen = () => {
        retry = 0;
        if (!stop) setWsLive(true);
      };

      ws.onmessage = (ev) => {
        try {
          setData(JSON.parse(String(ev.data)));
        } catch {
          // ignore bad frame
        }
      };

      ws.onerror = () => {
        if (!stop) setWsLive(false);
      };

      ws.onclose = () => {
        if (stop) return;
        setWsLive(false);
        const delay = Math.min(10000, 1000 * (2 ** retry));
        retry += 1;
        setTimeout(connect, delay);
      };
    };

    connect();
    return () => {
      stop = true;
      try {
        ws?.close();
      } catch {
        // ignore
      }
    };
  }, []);

  const es = data?.ema_scalper;
  const openPositions = es?.positions || [];
  const closedTrades = es?.recent_trades || [];
  const stats = es?.stats || {};

  const tradeDates = useMemo(() => {
    const uniq = new Set<string>();
    for (const t of closedTrades) {
      const ts = String(t.timestamp_close || "");
      if (ts.length >= 10) uniq.add(ts.slice(0, 10));
    }
    return Array.from(uniq).sort((a, b) => b.localeCompare(a));
  }, [closedTrades]);

  const filteredClosed = useMemo(() => {
    if (selectedDate === "ALL") return closedTrades;
    if (selectedDate === "WEEK") {
      const now = new Date();
      const start = new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate() - 6));
      return closedTrades.filter((t) => {
        const ds = String(t.timestamp_close || "").slice(0, 10);
        if (ds.length !== 10) return false;
        return new Date(`${ds}T00:00:00Z`) >= start;
      });
    }
    return closedTrades.filter((t) => String(t.timestamp_close || "").startsWith(selectedDate));
  }, [closedTrades, selectedDate]);

  const lastClosed = filteredClosed.slice(0, 8);

  return (
    <div className="min-h-screen bg-[#060b16] text-[#d9dde4]">
      <header className="flex flex-wrap items-center justify-between gap-3 border-b border-[#1d2736] px-5 py-4">
        <div className="flex items-center gap-3">
          <h1 className="font-mono text-xl font-semibold">EMA SCALPER</h1>
          <span className={`rounded px-2 py-0.5 font-mono text-xs ${data?.dry_run ? "bg-[#f0b90b22] text-[#f0b90b]" : "bg-[#f6465d22] text-[#f6465d]"}`}>
            {data?.dry_run ? "DRY RUN" : "LIVE"}
          </span>
          <span className={`font-mono text-xs ${wsLive ? "text-[#0ecb81]" : "text-[#f6465d]"}`}>
            {wsLive ? "live" : "offline"}
          </span>
        </div>
        <div className="font-mono text-sm text-[#9aa4b2]">
          PnL today: <span className={(data?.pnl_today || 0) >= 0 ? "text-[#0ecb81]" : "text-[#f6465d]"}>${fmt(data?.pnl_today, 2)}</span>
        </div>
      </header>

      <div className="grid gap-4 p-4 lg:grid-cols-2">
        <section className="rounded border border-[#1d2736] bg-[#0b1322] p-3">
          <h2 className="mb-2 font-mono text-xs uppercase text-[#8f99a8]">Открытые позиции</h2>
          {openPositions.length === 0 ? (
            <p className="font-mono text-xs text-[#7e8795]">Сейчас открытых сделок нет</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full border-collapse font-mono text-xs">
                <thead>
                  <tr className="border-b border-[#1d2736] text-left text-[#8f99a8]">
                    <th className="py-1 pr-2">Пара</th>
                    <th className="py-1 pr-2">Маржа</th>
                    <th className="py-1 pr-2">Плечо</th>
                    <th className="py-1 pr-2">Вход</th>
                    <th className="py-1 pr-2">Текущая</th>
                    <th className="py-1 pr-2">Причина входа</th>
                    <th className="py-1">PnL</th>
                  </tr>
                </thead>
                <tbody>
                  {openPositions.map((p, i) => (
                    <tr key={`${p.symbol}-${i}`} className="border-b border-[#1d273655]">
                      <td className="py-1.5 pr-2">{p.side === "LONG" ? "▲" : "▼"} {p.symbol}</td>
                      <td className="py-1.5 pr-2">${fmt(p.size_usdt, 2)}</td>
                      <td className="py-1.5 pr-2">x{p.leverage}</td>
                      <td className="py-1.5 pr-2">{fmt(p.entry_price, 4)}</td>
                      <td className="py-1.5 pr-2">{fmt(p.current_price, 4)}</td>
                      <td className="py-1.5 pr-2 text-[#9aa4b2]">{entryReasonFromTrade(p)}</td>
                      <td className={`py-1.5 ${(p.pnl_usdt || 0) >= 0 ? "text-[#0ecb81]" : "text-[#f6465d]"}`}>
                        ${fmt(p.pnl_usdt, 4)} ({fmt(p.pnl_pct, 2)}%)
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>

        <section className="rounded border border-[#1d2736] bg-[#0b1322] p-3">
          <h2 className="mb-2 font-mono text-xs uppercase text-[#8f99a8]">Последние закрытые</h2>
          <div className="overflow-x-auto">
            <table className="w-full border-collapse font-mono text-xs">
              <thead>
                <tr className="border-b border-[#1d2736] text-left text-[#8f99a8]">
                  <th className="py-1 pr-2">Время</th>
                  <th className="py-1 pr-2">Пара</th>
                  <th className="py-1 pr-2">Маржа</th>
                  <th className="py-1 pr-2">Плечо</th>
                  <th className="py-1 pr-2">Причина входа</th>
                  <th className="py-1 pr-2">Причина выхода</th>
                  <th className="py-1">PnL</th>
                </tr>
              </thead>
              <tbody>
                {lastClosed.map((t) => (
                  <tr key={t.id} className="border-b border-[#1d273655]">
                    <td className="py-1.5 pr-2 text-[#9aa4b2]">{String(t.timestamp_close || "").slice(0, 19)}</td>
                    <td className="py-1.5 pr-2">{t.side === "LONG" ? "▲" : "▼"} {t.symbol}</td>
                    <td className="py-1.5 pr-2">${fmt(t.size_usdt, 2)}</td>
                    <td className="py-1.5 pr-2">x{t.leverage}</td>
                    <td className="py-1.5 pr-2 text-[#9aa4b2]">{entryReasonFromTrade(t)}</td>
                    <td className="py-1.5 pr-2">{t.close_reason || "—"}</td>
                    <td className={`py-1.5 ${(t.pnl_usdt || 0) >= 0 ? "text-[#0ecb81]" : "text-[#f6465d]"}`}>${fmt(t.pnl_usdt, 4)}</td>
                  </tr>
                ))}
                {lastClosed.length === 0 ? (
                  <tr>
                    <td className="py-2 text-[#7e8795]" colSpan={7}>Нет закрытых сделок за выбранный период</td>
                  </tr>
                ) : null}
              </tbody>
            </table>
          </div>
        </section>
      </div>

      <section className="mx-4 mb-4 rounded border border-[#1d2736] bg-[#0b1322] p-3">
        <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
          <h2 className="font-mono text-xs uppercase text-[#8f99a8]">История сделок</h2>
          <div className="flex flex-wrap items-center gap-2 font-mono text-xs text-[#8f99a8]">
            <span>Дата:</span>
            <select
              value={selectedDate}
              onChange={(e) => setSelectedDate(e.target.value)}
              className="rounded border border-[#2a3648] bg-[#0a111e] px-2 py-1 text-[#d9dde4]"
            >
              <option value="ALL">Все даты</option>
              <option value="WEEK">Последние 7 дней</option>
              {tradeDates.map((d) => (
                <option key={d} value={d}>{d}</option>
              ))}
            </select>
            <input
              type="date"
              value={selectedDate === "ALL" || selectedDate === "WEEK" ? "" : selectedDate}
              onChange={(e) => setSelectedDate(e.target.value || "ALL")}
              className="rounded border border-[#2a3648] bg-[#0a111e] px-2 py-1 text-[#d9dde4]"
            />
          </div>
        </div>
        <p className="mb-2 font-mono text-[11px] text-[#7e8795]">
          Показано: {filteredClosed.length} | Сегодня: {fmt(stats.trades_today, 0)} сделок | WinRate: {fmt(stats.win_rate_today, 0)}%
        </p>
        <div className="overflow-x-auto">
          <table className="w-full border-collapse font-mono text-xs">
            <thead>
              <tr className="border-b border-[#1d2736] text-left text-[#8f99a8]">
                <th className="py-1 pr-2">Open UTC</th>
                <th className="py-1 pr-2">Close UTC</th>
                <th className="py-1 pr-2">Пара</th>
                <th className="py-1 pr-2">Сторона</th>
                <th className="py-1 pr-2">Маржа</th>
                <th className="py-1 pr-2">Плечо</th>
                <th className="py-1 pr-2">Вход</th>
                <th className="py-1 pr-2">Выход</th>
                <th className="py-1 pr-2">Причина входа</th>
                <th className="py-1 pr-2">Причина выхода</th>
                <th className="py-1">PnL</th>
              </tr>
            </thead>
            <tbody>
              {filteredClosed.map((t) => (
                <tr key={t.id} className="border-b border-[#1d273655]">
                  <td className="py-1.5 pr-2 text-[#9aa4b2]">{String(t.timestamp_open || "").slice(0, 19)}</td>
                  <td className="py-1.5 pr-2 text-[#9aa4b2]">{String(t.timestamp_close || "").slice(0, 19)}</td>
                  <td className="py-1.5 pr-2">{t.symbol}</td>
                  <td className="py-1.5 pr-2">{t.side}</td>
                  <td className="py-1.5 pr-2">${fmt(t.size_usdt, 2)}</td>
                  <td className="py-1.5 pr-2">x{t.leverage}</td>
                  <td className="py-1.5 pr-2">{fmt(t.entry_price, 4)}</td>
                  <td className="py-1.5 pr-2">{fmt(t.exit_price, 4)}</td>
                  <td className="py-1.5 pr-2 text-[#9aa4b2]">{entryReasonFromTrade(t)}</td>
                  <td className="py-1.5 pr-2">{t.close_reason || "—"}</td>
                  <td className={`py-1.5 ${(t.pnl_usdt || 0) >= 0 ? "text-[#0ecb81]" : "text-[#f6465d]"}`}>${fmt(t.pnl_usdt, 4)}</td>
                </tr>
              ))}
              {filteredClosed.length === 0 ? (
                <tr>
                  <td className="py-2 text-[#7e8795]" colSpan={11}>Сделок за выбранный период нет</td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}
