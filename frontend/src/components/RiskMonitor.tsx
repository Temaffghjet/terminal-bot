type Risk = {
  daily_pnl_pct?: number;
  limit_reached?: boolean;
  deposit_usdt?: number;
};

type Daily = {
  target_pct?: number;
  current_pct?: number;
  max_loss_pct?: number;
};

type Props = {
  riskMonitor: Risk | undefined;
  dailyProgress: Daily | undefined;
};

export default function RiskMonitor({ riskMonitor, dailyProgress }: Props) {
  const cur = dailyProgress?.current_pct ?? riskMonitor?.daily_pnl_pct ?? 0;
  const maxLoss = dailyProgress?.max_loss_pct ?? 10;
  const tgt = dailyProgress?.target_pct ?? 5;
  const lim = riskMonitor?.limit_reached ?? false;
  const widthPct = Math.min(100, Math.max(0, 50 + (cur / maxLoss) * 25));

  return (
    <div className="border border-gray-800 rounded p-2 bg-[#0a0a0f] text-[11px] space-y-2">
      <div className="text-gray-500 uppercase tracking-wider text-[10px]">Риск дня</div>
      <div className="flex justify-between">
        <span className="text-gray-400">PnL vs депозит</span>
        <span className={cur >= 0 ? "text-terminal-profit" : "text-terminal-loss"}>
          {cur >= 0 ? "+" : ""}
          {cur.toFixed(2)}%
        </span>
      </div>
      <div className="flex justify-between text-gray-500">
        <span>Цель дня ~{tgt}%</span>
        <span>Стоп −{maxLoss}%</span>
      </div>
      <div className="h-2 bg-gray-900 rounded overflow-hidden">
        <div
          className={`h-full transition-all ${lim ? "bg-terminal-loss" : cur >= 0 ? "bg-terminal-profit" : "bg-terminal-warn"}`}
          style={{ width: `${widthPct}%` }}
        />
      </div>
      {lim && <div className="text-terminal-loss text-[10px]">Достигнут дневной лимит убытка — бот должен стопориться</div>}
    </div>
  );
}
