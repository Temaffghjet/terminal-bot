import {
  ComposedChart,
  Line,
  ReferenceLine,
  ResponsiveContainer,
  Scatter,
  XAxis,
  YAxis,
} from "recharts";

type Candle = {
  ts: number;
  close: number;
  ema: number;
};

type Pos = {
  entry_price: number;
  tp_price: number;
  sl_price: number;
  side: string;
};

export default function EMAMiniChart({
  candles,
  position,
}: {
  candles: Candle[];
  position: Pos | null;
}) {
  const data = candles.map((c, i) => ({
    i,
    close: c.close,
    ema: c.ema,
    ts: c.ts,
  }));
  if (!data.length) {
    return (
      <div className="h-[160px] flex items-center justify-center text-gray-600 text-xs border border-gray-800 rounded">
        Нет candle_history
      </div>
    );
  }
  const last = data[data.length - 1]?.close ?? 0;
  return (
    <div className="h-[160px] border border-gray-800 rounded overflow-hidden bg-black/40 relative">
      <ResponsiveContainer width="100%" height="100%">
        <ComposedChart data={data} margin={{ top: 4, right: 8, left: 0, bottom: 0 }}>
          <XAxis dataKey="i" hide />
          <YAxis domain={["auto", "auto"]} width={0} hide />
          <Line type="monotone" dataKey="close" stroke="#60a5fa" strokeWidth={1} dot={false} />
          <Line
            type="monotone"
            dataKey="ema"
            stroke="#9ca3af"
            strokeWidth={1}
            strokeDasharray="4 2"
            dot={false}
          />
          {position && (
            <>
              <ReferenceLine y={position.entry_price} stroke="#e5e7eb" strokeWidth={1} />
              <ReferenceLine
                y={position.tp_price}
                stroke="#34d399"
                strokeDasharray="3 3"
              />
              <ReferenceLine
                y={position.sl_price}
                stroke="#fb7185"
                strokeDasharray="3 3"
              />
            </>
          )}
          <Scatter dataKey="close" fill="transparent" />
        </ComposedChart>
      </ResponsiveContainer>
      <div className="absolute right-2 top-2 text-[10px] text-gray-400 font-mono">{last.toFixed(2)}</div>
    </div>
  );
}
