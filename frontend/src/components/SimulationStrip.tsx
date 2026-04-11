type Sim = {
  data_source?: string;
  ohlcv_backtest?: string;
  period?: { since?: string; until?: string };
  timeframe?: string;
  trades_closed?: number;
  win_rate_pct?: number;
  total_net_usdt?: number;
  expectancy_usdt?: number;
  avg_trade_min?: number;
  compute_sec?: number;
};

type Props = {
  exchangeName: string;
  simulation: Sim | null | undefined;
  strategyMode: string;
};

export default function SimulationStrip({ exchangeName, simulation, strategyMode }: Props) {
  const ex = exchangeName || "—";
  return (
    <div className="border-b border-gray-800 px-3 py-1.5 bg-[#080810] text-[11px] text-gray-400 flex flex-wrap gap-x-6 gap-y-1 items-center">
      <span>
        Данные терминала:{" "}
        <span className="text-terminal-profit font-semibold uppercase">{ex}</span>
        {strategyMode === "scalping" && (
          <span className="ml-2 text-gray-600">live-данные с биржи из config (exchange.name).</span>
        )}
      </span>
      {simulation ? (
        <span className="text-gray-300">
          Последняя симуляция (скальп): {simulation.period?.since} → {simulation.period?.until} · TF{" "}
          {simulation.timeframe} · источник OHLCV:{" "}
          <span className="text-terminal-warn">{simulation.data_source ?? simulation.ohlcv_backtest}</span>
          {" · "}
          сделок {simulation.trades_closed ?? "—"} · WR {simulation.win_rate_pct ?? "—"}% · net{" "}
          <span
            className={
              (simulation.total_net_usdt ?? 0) >= 0 ? "text-terminal-profit" : "text-terminal-loss"
            }
          >
            {simulation.total_net_usdt != null ? simulation.total_net_usdt.toFixed(4) : "—"} USDT
          </span>
          {" · "}E {simulation.expectancy_usdt != null ? simulation.expectancy_usdt.toFixed(4) : "—"} · t̄{" "}
          {simulation.avg_trade_min ?? "—"} мин · {simulation.compute_sec ?? "—"}s
        </span>
      ) : (
        <span className="text-gray-600">
          Симуляция: запустите{" "}
          <code className="text-gray-500">python -m backend.sim.scalping_backtest --since … --until …</code> — результат
          появится здесь.
        </span>
      )}
    </div>
  );
}
