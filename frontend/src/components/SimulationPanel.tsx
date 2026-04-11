export type SimulationSnapshot = {
  data_source?: string;
  ohlcv_backtest?: string;
  period?: { since?: string; until?: string };
  timeframe?: string;
  symbols?: string[];
  trades_closed?: number;
  win_rate_pct?: number;
  total_net_usdt?: number;
  total_gross_usdt?: number;
  total_fees_usdt?: number;
  cost_rate_pct?: number;
  expectancy_usdt?: number;
  avg_trade_min?: number;
  compute_sec?: number;
  exchange_config?: string;
};

type Props = {
  simulation: SimulationSnapshot | null | undefined;
  source: "websocket" | "file" | "none";
};

export default function SimulationPanel({ simulation, source }: Props) {
  if (!simulation) {
    return (
      <div className="mx-3 mb-2 border border-dashed border-gray-700 rounded-lg p-4 bg-[#0a0a12] text-gray-500 text-xs">
        <p className="font-semibold text-gray-400 mb-1">Симуляция (бэктест)</p>
        <p>
          Положите файл <code className="text-terminal-warn">simulation.json</code> в{" "}
          <code className="text-gray-400">frontend/public/</code> (скопируйте из{" "}
          <code className="text-gray-400">bot/data/last_scalping_sim.json</code> после прогона) или запустите бота —
          данные придут по WebSocket.
        </p>
      </div>
    );
  }

  const s = simulation;
  const sym = (s.symbols ?? []).join(", ") || "—";
  const net = s.total_net_usdt ?? 0;

  return (
    <div className="mx-3 mb-2 border border-terminal-warn/30 rounded-lg overflow-hidden bg-[#0a0a12]">
      <div className="px-3 py-2 border-b border-gray-800 flex flex-wrap items-center justify-between gap-2">
        <span className="text-xs font-semibold text-terminal-warn uppercase tracking-wider">
          Последняя симуляция (бэктест)
        </span>
        <span className="text-[10px] text-gray-500">
          источник:{" "}
          {source === "websocket" ? (
            <span className="text-terminal-profit">бот (WS)</span>
          ) : source === "file" ? (
            <span className="text-gray-300">simulation.json</span>
          ) : (
            "—"
          )}
        </span>
      </div>
      <div className="p-3 grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3 text-xs">
        <div className="space-y-1">
          <div className="text-gray-500">Период</div>
          <div className="text-gray-200">
            {s.period?.since ?? "—"} → {s.period?.until ?? "—"}
          </div>
          <div className="text-gray-500 mt-2">Таймфрейм / OHLCV</div>
          <div>
            {s.timeframe ?? "—"} · <span className="text-terminal-warn">{s.data_source ?? s.ohlcv_backtest}</span>
          </div>
          <div className="text-gray-500 mt-2">Символы</div>
          <div className="text-gray-300 break-all">{sym}</div>
        </div>
        <div className="space-y-1">
          <div className="text-gray-500">Сделок (закрытий)</div>
          <div className="text-xl font-mono text-white">{s.trades_closed ?? "—"}</div>
          <div className="text-gray-500 mt-2">Win rate</div>
          <div className="font-mono">{(s.win_rate_pct ?? 0).toFixed(2)}%</div>
          <div className="text-gray-500 mt-2">Издержки (оценка)</div>
          <div className="font-mono text-gray-300">
            {(s.cost_rate_pct ?? 0).toFixed(3)}% от номинала / раунд
          </div>
        </div>
        <div className="space-y-1">
          <div className="text-gray-500">Net PnL</div>
          <div className={`text-xl font-mono ${net >= 0 ? "text-terminal-profit" : "text-terminal-loss"}`}>
            {net >= 0 ? "+" : ""}
            {net.toFixed(4)} USDT
          </div>
          <div className="text-gray-500 mt-2">Gross / комиссии+slip (симв.)</div>
          <div className="font-mono text-gray-300">
            {(s.total_gross_usdt ?? 0).toFixed(4)} / {(s.total_fees_usdt ?? 0).toFixed(4)} USDT
          </div>
          <div className="text-gray-500 mt-2">Expectancy · t̄ в сделке · расчёт</div>
          <div className="font-mono text-gray-300">
            {(s.expectancy_usdt ?? 0).toFixed(4)} USDT · {(s.avg_trade_min ?? 0).toFixed(2)} мин ·{" "}
            {s.compute_sec ?? "—"}s
          </div>
        </div>
      </div>
    </div>
  );
}
