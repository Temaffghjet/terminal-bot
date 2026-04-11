import { useEffect, useState } from "react";
import {
  CartesianGrid,
  ComposedChart,
  Line,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

type PairMetrics = {
  zscore?: number | null;
  spread_history?: number[];
  zscore_history?: number[];
};

type Props = {
  metricsByPair: Record<string, PairMetrics>;
  entryZ: number;
  stopZ: number;
  /** Режим скальпинга: ось и линии для RSI, не z-score */
  scalpMode?: boolean;
};

function buildChartRows(zHist: number[], spreadHist: number[]) {
  const n = Math.max(zHist.length, spreadHist.length);
  const rows: {
    t: string;
    z: number | null;
    spread: number | null;
    mean: number | null;
    p1: number | null;
    m1: number | null;
    p2: number | null;
    m2: number | null;
  }[] = [];
  for (let i = 0; i < n; i++) {
    const spread = spreadHist[i] ?? null;
    const slice = spreadHist.slice(0, i + 1).filter((x) => x === x);
    let mean: number | null = null;
    let std = 0;
    if (slice.length) {
      mean = slice.reduce((a, b) => a + b, 0) / slice.length;
      const v = slice.reduce((a, b) => a + (b - mean!) ** 2, 0) / Math.max(slice.length - 1, 1);
      std = Math.sqrt(v);
    }
    rows.push({
      t: `${i}`,
      z: zHist[i] ?? null,
      spread,
      mean,
      p1: mean !== null && spread !== null ? mean + std : null,
      m1: mean !== null && spread !== null ? mean - std : null,
      p2: mean !== null && spread !== null ? mean + 2 * std : null,
      m2: mean !== null && spread !== null ? mean - 2 * std : null,
    });
  }
  return rows;
}

export default function SpreadChart({ metricsByPair, entryZ, stopZ, scalpMode }: Props) {
  const pairIds = Object.keys(metricsByPair);
  const [tab, setTab] = useState(pairIds[0] ?? "");

  useEffect(() => {
    if (!tab && pairIds[0]) setTab(pairIds[0]);
  }, [pairIds, tab]);

  if (pairIds.length === 0) {
    return (
      <div className="flex items-center justify-center h-full min-h-[200px] border border-gray-800 bg-[#0a0a0f] text-gray-600 text-xs">
        No pair metrics yet
      </div>
    );
  }

  const m = metricsByPair[tab] ?? {};
  const zHist = (m.zscore_history ?? []).slice(-100);
  const spreadHist = (m.spread_history ?? []).slice(-100);
  const rows = buildChartRows(zHist, spreadHist);
  const curZ = typeof m.zscore === "number" && m.zscore === m.zscore ? m.zscore : null;

  const zPrev = zHist.length >= 2 ? zHist[zHist.length - 2] : null;
  const zLast = zHist.length ? zHist[zHist.length - 1] : null;
  let zLineColor = "#ffffff";
  if (zPrev !== null && zLast !== null) {
    zLineColor = Math.abs(zLast) < Math.abs(zPrev) ? "#00ff88" : "#ff3366";
  }

  return (
    <div className="flex flex-col h-full min-h-0 border border-gray-800 bg-[#0a0a0f]">
      <div className="flex gap-1 px-2 py-1 border-b border-gray-800 overflow-x-auto">
        {pairIds.map((id) => (
          <button
            key={id}
            type="button"
            className={`px-2 py-0.5 text-xs font-mono whitespace-nowrap ${tab === id ? "bg-gray-800 text-terminal-profit" : "text-gray-500"}`}
            onClick={() => setTab(id)}
          >
            {id}
          </button>
        ))}
      </div>

      <div className="flex-1 min-h-[200px] p-2 flex flex-col gap-2">
        <div className="text-[10px] text-gray-500 flex justify-between">
          <span>{scalpMode ? "EMA(9)" : "Z-Score"}</span>
          {curZ !== null && (
            <span className="font-semibold" style={{ color: zLineColor }}>
              {scalpMode ? "EMA" : "z"} = {curZ.toFixed(4)}
            </span>
          )}
        </div>
        <div className="h-[180px] w-full">
          <ResponsiveContainer width="100%" height="100%">
            <ComposedChart data={rows}>
              <CartesianGrid strokeDasharray="3 3" stroke="#222" />
              <XAxis dataKey="t" hide tick={{ fill: "#666", fontSize: 10 }} />
              <YAxis tick={{ fill: "#666", fontSize: 10 }} width={40} />
              <Tooltip contentStyle={{ background: "#111", border: "1px solid #333", fontSize: 11 }} />
              <ReferenceLine y={scalpMode ? 50 : 0} stroke="#888" strokeDasharray="4 4" />
              {!scalpMode && (
                <>
                  <ReferenceLine y={entryZ} stroke="#ffaa00" strokeDasharray="4 4" />
                  <ReferenceLine y={-entryZ} stroke="#ffaa00" strokeDasharray="4 4" />
                  <ReferenceLine y={stopZ} stroke="#ff3366" strokeDasharray="4 4" />
                  <ReferenceLine y={-stopZ} stroke="#ff3366" strokeDasharray="4 4" />
                </>
              )}
              {scalpMode && (
                <>
                  <ReferenceLine y={70} stroke="#ffaa00" strokeDasharray="4 4" />
                  <ReferenceLine y={30} stroke="#ffaa00" strokeDasharray="4 4" />
                </>
              )}
              <Line
                type="monotone"
                dataKey="z"
                stroke={zLineColor}
                dot={false}
                strokeWidth={1.5}
                isAnimationActive={false}
              />
            </ComposedChart>
          </ResponsiveContainer>
        </div>

        <div className="text-[10px] text-gray-500">Spread</div>
        <div className="h-[180px] w-full">
          <ResponsiveContainer width="100%" height="100%">
            <ComposedChart data={rows}>
              <CartesianGrid strokeDasharray="3 3" stroke="#222" />
              <XAxis dataKey="t" hide />
              <YAxis tick={{ fill: "#666", fontSize: 10 }} width={40} />
              <Tooltip contentStyle={{ background: "#111", border: "1px solid #333", fontSize: 11 }} />
              <Line type="monotone" dataKey="p2" stroke="#ffaa00" dot={false} strokeWidth={0.5} strokeDasharray="2 2" isAnimationActive={false} />
              <Line type="monotone" dataKey="m2" stroke="#ffaa00" dot={false} strokeWidth={0.5} strokeDasharray="2 2" isAnimationActive={false} />
              <Line type="monotone" dataKey="p1" stroke="#00ff88" dot={false} strokeWidth={0.6} strokeDasharray="3 3" strokeOpacity={0.5} isAnimationActive={false} />
              <Line type="monotone" dataKey="m1" stroke="#00ff88" dot={false} strokeWidth={0.6} strokeDasharray="3 3" strokeOpacity={0.5} isAnimationActive={false} />
              <Line type="monotone" dataKey="mean" stroke="#888" dot={false} strokeWidth={1} isAnimationActive={false} />
              <Line type="monotone" dataKey="spread" stroke="#00ff88" dot={false} strokeWidth={1.2} isAnimationActive={false} />
            </ComposedChart>
          </ResponsiveContainer>
        </div>
      </div>
    </div>
  );
}
