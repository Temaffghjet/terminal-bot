type Today = {
  trades?: number;
  wins?: number;
  losses?: number;
  totalPnL?: number;
  commissionPaid?: number;
  avgTradeTime?: number;
  winRate?: number;
};

type Props = { today: Today };

export default function ScalpingStats({ today }: Props) {
  const t = today?.trades ?? 0;
  const wr = today?.winRate ?? 0;
  return (
    <div className="border border-gray-800 rounded p-2 bg-[#0a0a0f] text-[11px] space-y-1">
      <div className="text-gray-500 uppercase tracking-wider text-[10px]">Сегодня (scalp)</div>
      <div className="grid grid-cols-2 gap-x-4 gap-y-1">
        <span className="text-gray-400">Сделок</span>
        <span>{t}</span>
        <span className="text-gray-400">Win rate</span>
        <span>{wr.toFixed(1)}%</span>
        <span className="text-gray-400">PnL</span>
        <span className={(today?.totalPnL ?? 0) >= 0 ? "text-terminal-profit" : "text-terminal-loss"}>
          {(today?.totalPnL ?? 0) >= 0 ? "+" : ""}
          {(today?.totalPnL ?? 0).toFixed(4)} USDT
        </span>
        <span className="text-gray-400">Комиссии</span>
        <span className="text-gray-300">{(today?.commissionPaid ?? 0).toFixed(4)} USDT</span>
      </div>
    </div>
  );
}
