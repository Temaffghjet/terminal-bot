import {
  Cell,
  Line,
  LineChart,
  Scatter,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

type AutoTuner = {
  enabled?: boolean;
  self_tune_enabled?: boolean;
  lookback?: number;
  min_samples?: number;
  samples?: number;
  winrate?: number;
  profit_factor?: number;
  base_min_score?: number;
  dynamic_min_score?: number;
  decision?: string;
};

type TunerPoint = {
  ts?: string;
  dynamic_min_score?: number;
  base_min_score?: number;
  winrate?: number;
  profit_factor?: number;
  samples?: number;
  decision?: string;
};

function decisionLabel(v?: string): string {
  if (v === "raise_threshold") return "Порог повышен (рынок слабее)";
  if (v === "lower_threshold") return "Порог понижен (рынок сильнее)";
  if (v === "keep_threshold") return "Порог без изменений";
  return "Недостаточно данных";
}

export default function EMAAutoTunerPanel({
  tuner,
  history = [],
}: {
  tuner?: AutoTuner | null;
  history?: TunerPoint[];
}) {
  if (!tuner?.enabled) {
    return <div className="text-xs text-gray-500">Auto tuner выключен.</div>;
  }
  const samples = Number(tuner.samples ?? 0);
  const minSamples = Number(tuner.min_samples ?? 0);
  const rows = history.slice(-20).map((p, i) => ({
    i: i + 1,
    dyn: Number(p.dynamic_min_score ?? 0),
    base: Number(p.base_min_score ?? 0),
    win: Number(p.winrate ?? 0),
    pf: Number(p.profit_factor ?? 0),
    decision: String(p.decision ?? "keep_threshold"),
  }));
  const colorByDecision = (d: string): string => {
    if (d === "raise_threshold") return "#f59e0b";
    if (d === "lower_threshold") return "#22c55e";
    return "#94a3b8";
  };
  return (
    <div className="border border-sky-900/60 rounded-lg p-3 bg-sky-950/10">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="text-[11px] uppercase tracking-wider text-sky-300">Auto Tuner State</div>
        <div className="text-xs text-gray-400">{decisionLabel(tuner.decision)}</div>
      </div>
      <div className="mt-2 grid grid-cols-1 md:grid-cols-3 gap-2 text-xs">
        <div className="border border-gray-800 rounded p-2">
          <div className="text-gray-500">Winrate / PF</div>
          <div className="text-white">
            {Number(tuner.winrate ?? 0).toFixed(2)}% / {Number(tuner.profit_factor ?? 0).toFixed(3)}
          </div>
        </div>
        <div className="border border-gray-800 rounded p-2">
          <div className="text-gray-500">Samples</div>
          <div className="text-white">
            {samples}/{minSamples} (lookback {Number(tuner.lookback ?? 0)})
          </div>
        </div>
        <div className="border border-gray-800 rounded p-2">
          <div className="text-gray-500">Min Score</div>
          <div className="text-white">
            base {Number(tuner.base_min_score ?? 0).toFixed(0)} → dyn{" "}
            {Number(tuner.dynamic_min_score ?? 0).toFixed(0)}
          </div>
        </div>
      </div>
      <div className="mt-2 border border-gray-800 rounded p-2">
        <div className="flex items-center justify-between gap-2 mb-1">
          <div className="text-[10px] text-gray-500 uppercase">
            История dynamic min score (последние {rows.length})
          </div>
          <div className="text-[10px] text-gray-500 flex items-center gap-2">
            <span className="inline-flex items-center gap-1">
              <span className="inline-block w-2 h-2 rounded-full bg-amber-500" /> raise
            </span>
            <span className="inline-flex items-center gap-1">
              <span className="inline-block w-2 h-2 rounded-full bg-green-500" /> lower
            </span>
            <span className="inline-flex items-center gap-1">
              <span className="inline-block w-2 h-2 rounded-full bg-slate-400" /> keep
            </span>
          </div>
        </div>
        <div className="text-[10px] text-gray-600 mb-1">
          Цвет точки = решение тюнера на этом шаге
        </div>
        <div className="h-[110px] w-full">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={rows}>
              <XAxis dataKey="i" hide />
              <YAxis hide domain={["dataMin - 2", "dataMax + 2"]} />
              <Tooltip
                formatter={(v: number, name: string, ctx: { payload?: { decision?: string } }) =>
                  name === "decision"
                    ? [String(ctx?.payload?.decision ?? "keep_threshold"), "decision"]
                    : [Number(v).toFixed(2), name]
                }
                labelFormatter={(i: number) => `point ${i}`}
              />
              <Line type="monotone" dataKey="dyn" stroke="#38bdf8" strokeWidth={2} dot={false} name="dyn" />
              <Line
                type="monotone"
                dataKey="base"
                stroke="#64748b"
                strokeWidth={1}
                strokeDasharray="4 4"
                dot={false}
                name="base"
              />
              <Scatter dataKey="dyn" name="decision">
                {rows.map((r, idx) => (
                  <Cell key={`cell-${r.i}-${idx}`} fill={colorByDecision(r.decision)} />
                ))}
              </Scatter>
            </LineChart>
          </ResponsiveContainer>
        </div>
      </div>
    </div>
  );
}
