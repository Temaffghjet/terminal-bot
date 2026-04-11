type Leg = {
  symbol: string;
  side: string;
  size: number;
  entry_price: number;
  current_price: number;
  pnl_usdt: number;
};

type Pos = {
  pair_id: string;
  leg_a: Leg;
  leg_b: Leg;
  total_pnl_usdt: number;
  open_time: string;
  zscore_at_entry: number;
  current_zscore: number;
  is_scalp?: boolean;
  minutes_in_trade?: number;
};

function zColor(z: number): string {
  const a = Math.abs(z);
  if (a > 2) return "text-terminal-loss";
  if (a >= 1) return "text-terminal-warn";
  return "text-terminal-profit";
}

function formatOpen(iso: string): string {
  const t = Date.parse(iso);
  if (Number.isNaN(t)) return "?";
  const diff = Date.now() - t;
  const h = Math.floor(diff / 3600000);
  const m = Math.floor((diff % 3600000) / 60000);
  return `${h}h ${m}m`;
}

type Props = {
  positions: Pos[];
  totalUnrealized: number;
  totalRealized: number;
  onClosePair: (pairId: string) => void;
};

export default function PnLPanel({ positions, totalUnrealized, totalRealized, onClosePair }: Props) {
  return (
    <div className="flex flex-col h-full min-h-0 border border-gray-800 bg-[#0a0a0f]">
      <div className="px-2 py-1 border-b border-gray-800 text-xs text-gray-500 uppercase tracking-wider">
        Open positions
      </div>
      <div className="p-2 space-y-2 overflow-auto flex-1">
        <div className="text-xs flex justify-between border-b border-gray-800 pb-2 mb-2">
          <span className="text-gray-400">Total unrealized</span>
          <span className={totalUnrealized >= 0 ? "text-terminal-profit" : "text-terminal-loss"}>
            {totalUnrealized >= 0 ? "+" : ""}
            {totalUnrealized.toFixed(2)} USDT
          </span>
        </div>
        <div className="text-xs flex justify-between pb-2">
          <span className="text-gray-400">Realized today</span>
          <span className={totalRealized >= 0 ? "text-terminal-profit" : "text-terminal-loss"}>
            {totalRealized >= 0 ? "+" : ""}
            {totalRealized.toFixed(2)} USDT
          </span>
        </div>

        {positions.length === 0 && (
          <div className="text-gray-600 text-xs py-4 text-center">No open positions</div>
        )}

        {positions.map((p) => {
          const isScalp = p.is_scalp === true;
          const [ba, bb] = p.pair_id.replace(/^scalp:/, "").split("-");
          const arrowA = p.leg_a.side === "LONG" ? "↑" : "↓";
          const arrowB = p.leg_b.side === "LONG" ? "↑" : "↓";
          return (
            <div key={p.pair_id} className="border border-gray-800 p-2 text-xs space-y-1">
              <div className="flex justify-between items-start">
                <span className="font-semibold text-white">
                  {isScalp ? (
                    <>
                      {p.leg_a.symbol} {arrowA}{" "}
                      <span className="text-gray-500 font-normal">scalp</span>
                    </>
                  ) : (
                    <>
                      {ba} {arrowA} / {bb} {arrowB}
                    </>
                  )}
                </span>
                <span className={p.total_pnl_usdt >= 0 ? "text-terminal-profit" : "text-terminal-loss"}>
                  Σ {p.total_pnl_usdt >= 0 ? "+" : ""}
                  {p.total_pnl_usdt.toFixed(2)} USDT
                </span>
              </div>
              <div
                className={`grid gap-1 text-[10px] text-gray-400 ${isScalp ? "grid-cols-1" : "grid-cols-2"}`}
              >
                <div>
                  {isScalp ? "Position" : "Leg A"} {p.leg_a.symbol}: {p.leg_a.side} {p.leg_a.size.toFixed(6)} @{" "}
                  {p.leg_a.entry_price.toFixed(2)} → {p.leg_a.current_price.toFixed(2)} P&amp;L{" "}
                  <span className={p.leg_a.pnl_usdt >= 0 ? "text-terminal-profit" : "text-terminal-loss"}>
                    {p.leg_a.pnl_usdt.toFixed(2)}
                  </span>
                </div>
                {!isScalp && (
                  <div>
                    Leg B {p.leg_b.symbol}: {p.leg_b.side} {p.leg_b.size.toFixed(6)} @ {p.leg_b.entry_price.toFixed(2)}{" "}
                    → {p.leg_b.current_price.toFixed(2)} P&amp;L{" "}
                    <span className={p.leg_b.pnl_usdt >= 0 ? "text-terminal-profit" : "text-terminal-loss"}>
                      {p.leg_b.pnl_usdt.toFixed(2)}
                    </span>
                  </div>
                )}
              </div>
              <div className="flex justify-between items-center pt-1">
                <span className={isScalp ? "text-terminal-warn" : zColor(p.current_zscore)}>
                  {isScalp ? "EMA" : "z"} = {p.current_zscore.toFixed(3)}
                  {isScalp && p.minutes_in_trade != null && (
                    <span className="text-gray-500 ml-2">({p.minutes_in_trade.toFixed(1)} мин)</span>
                  )}
                </span>
                <span className="text-gray-500">Open {formatOpen(p.open_time)}</span>
                <button
                  type="button"
                  className="border border-gray-600 px-2 py-0.5 hover:bg-gray-800"
                  onClick={() => onClosePair(p.pair_id)}
                >
                  Close manually
                </button>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
