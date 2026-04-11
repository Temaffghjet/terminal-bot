type Pos = {
  pair_id: string;
  is_scalp?: boolean;
  minutes_in_trade?: number;
  leg_a: {
    symbol: string;
    side: string;
    entry_price: number;
    current_price: number;
    pnl_usdt: number;
  };
};

type Props = { positions: Pos[] };

export default function ActivePositionsTable({ positions }: Props) {
  const scalp = positions.filter((p) => p.is_scalp);
  if (!scalp.length) {
    return (
      <div className="border border-gray-800 rounded p-2 bg-[#0a0a0f] text-[11px] text-gray-600">
        Нет открытых micro-scalp позиций
      </div>
    );
  }
  return (
    <div className="border border-gray-800 rounded p-2 bg-[#0a0a0f] text-[11px]">
      <div className="text-gray-500 uppercase tracking-wider text-[10px] mb-2">Активные позиции</div>
      <table className="w-full text-left">
        <thead>
          <tr className="text-gray-500 border-b border-gray-800">
            <th className="pb-1">Символ</th>
            <th>Сторона</th>
            <th>В сделке</th>
            <th>PnL</th>
          </tr>
        </thead>
        <tbody>
          {scalp.map((p) => (
            <tr key={p.pair_id} className="border-b border-gray-900">
              <td className="py-1 font-mono">{p.leg_a.symbol}</td>
              <td>{p.leg_a.side}</td>
              <td>{p.minutes_in_trade != null ? `${p.minutes_in_trade.toFixed(1)} мин` : "—"}</td>
              <td className={p.leg_a.pnl_usdt >= 0 ? "text-terminal-profit" : "text-terminal-loss"}>
                {p.leg_a.pnl_usdt >= 0 ? "+" : ""}
                {p.leg_a.pnl_usdt.toFixed(4)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
