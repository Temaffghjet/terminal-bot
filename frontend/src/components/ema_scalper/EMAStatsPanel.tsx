type Stats = {
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

export default function EMAStatsPanel({ stats }: { stats: Stats }) {
  const t = stats.today_trades ?? 0;
  const tw = stats.today_wins ?? 0;
  const wrToday = t ? (tw / t) * 100 : 0;
  return (
    <div className="grid grid-cols-2 gap-3 text-xs">
      <div>
        <div className="text-gray-500 mb-1">Сегодня</div>
        <div className="border border-gray-800 rounded p-2 space-y-1 bg-black/30">
          <div>Сделок: {t}</div>
          <div>Win rate: {wrToday.toFixed(0)}%</div>
          <div className={(stats.today_pnl ?? 0) >= 0 ? "text-emerald-400" : "text-rose-400"}>
            P&amp;L: ${(stats.today_pnl ?? 0).toFixed(2)}
          </div>
          <div>SL: {stats.today_losses ?? 0}</div>
          <div className="text-amber-400">Fees: ${(stats.today_fees ?? 0).toFixed(4)}</div>
        </div>
      </div>
      <div>
        <div className="text-gray-500 mb-1">All time</div>
        <div className="border border-gray-800 rounded p-2 space-y-1 bg-black/30">
          <div>Сделок: {stats.all_trades ?? 0}</div>
          <div>Win rate: {(stats.win_rate_all ?? 0).toFixed(0)}%</div>
          <div>P&amp;L: ${(stats.all_pnl ?? 0).toFixed(2)}</div>
          <div>PF: {stats.profit_factor ?? 0}</div>
        </div>
      </div>
      <div className="col-span-2 text-gray-500 border-t border-gray-800 pt-2">
        Avg удержание: {(stats.avg_hold_candles ?? 0).toFixed(1)} свечей
      </div>
    </div>
  );
}
