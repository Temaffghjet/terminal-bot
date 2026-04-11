import { Line, LineChart, ResponsiveContainer } from "recharts";

type StatsToday = {
  trades?: number;
  wins?: number;
  losses?: number;
  pnl_today?: number;
};

type StatsBlock = {
  today_trades?: number;
  today_wins?: number;
  today_losses?: number;
  today_pnl?: number;
  today_fees?: number;
  avg_hold_candles?: number;
  all_trades?: number;
  win_rate_all?: number;
  profit_factor?: number;
  all_pnl?: number;
};

export default function BreakoutStats({
  statsToday,
  stats,
  equityHistory,
}: {
  statsToday: StatsToday;
  stats: StatsBlock;
  equityHistory: number[];
}) {
  const chartData = equityHistory.map((y, i) => ({ i, y }));
  return (
    <div className="space-y-3">
      <div className="grid grid-cols-2 sm:grid-cols-3 gap-2 text-xs">
        <div className="border border-gray-800 rounded p-2 bg-black/30">
          <div className="text-gray-500">Сделок сегодня</div>
          <div className="text-emerald-400 font-mono">{statsToday.trades ?? stats.today_trades ?? 0}</div>
        </div>
        <div className="border border-gray-800 rounded p-2 bg-black/30">
          <div className="text-gray-500">Win rate</div>
          <div className="font-mono">
            {stats.all_trades
              ? `${(((stats.today_wins ?? 0) / Math.max(statsToday.trades ?? 1, 1)) * 100).toFixed(0)}%`
              : "—"}
          </div>
        </div>
        <div className="border border-gray-800 rounded p-2 bg-black/30">
          <div className="text-gray-500">P&amp;L сегодня</div>
          <div
            className={`font-mono ${
              (statsToday.pnl_today ?? stats.today_pnl ?? 0) >= 0 ? "text-emerald-400" : "text-rose-400"
            }`}
          >
            ${(statsToday.pnl_today ?? stats.today_pnl ?? 0).toFixed(2)}
          </div>
        </div>
        <div className="border border-gray-800 rounded p-2 bg-black/30">
          <div className="text-gray-500">TP / SL</div>
          <div className="font-mono">
            {stats.today_wins ?? 0} / {stats.today_losses ?? 0}
          </div>
        </div>
        <div className="border border-gray-800 rounded p-2 bg-black/30">
          <div className="text-gray-500">Avg hold</div>
          <div className="font-mono">{(stats.avg_hold_candles ?? 0).toFixed(1)}</div>
        </div>
        <div className="border border-gray-800 rounded p-2 bg-black/30">
          <div className="text-gray-500">Комиссии</div>
          <div className="font-mono text-amber-400">
            ${(stats.today_fees ?? 0).toFixed(4)}
          </div>
        </div>
      </div>
      <div className="h-[100px] border border-gray-800 rounded overflow-hidden bg-black/40">
        {chartData.length > 0 ? (
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={chartData}>
              <Line type="monotone" dataKey="y" stroke="#00ff88" strokeWidth={1} dot={false} />
            </LineChart>
          </ResponsiveContainer>
        ) : (
          <div className="h-full flex items-center justify-center text-gray-600 text-xs">
            Нет equity_history
          </div>
        )}
      </div>
    </div>
  );
}
