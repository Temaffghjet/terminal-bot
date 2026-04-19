import {
  ComposedChart,
  Line,
  ReferenceDot,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

export type ChartPoint = {
  t: number;
  c: number;
  ema?: number;
  ema2?: number;
};

export type ChartSnap = {
  tf_5m: string;
  tf_15m: string;
  tf_1h: string;
  series_5m: ChartPoint[];
  series_15m: ChartPoint[];
  series_1h: ChartPoint[];
  structure_15m: string;
  trend_1h: string;
  signal_status: string;
  signal_reason: string;
};

type SignalLite = {
  status?: string;
  reason?: string;
  structure_15m?: string;
  trend_1h?: string;
  rsi?: number;
  volume_ratio?: number;
};

const SLOTS = [
  { base: "BTC", label: "Bitcoin" },
  { base: "ETH", label: "Ethereum" },
  { base: "SOL", label: "Solana" },
] as const;

function findHlSymbol(
  base: string,
  charts?: Record<string, ChartSnap>,
  signals?: Record<string, SignalLite>,
): string | null {
  const keys = new Set([
    ...Object.keys(charts || {}),
    ...Object.keys(signals || {}),
  ]);
  for (const k of keys) {
    if (k.split("/")[0]?.toUpperCase() === base) return k;
  }
  return null;
}

function tfClass(s: string): string {
  if (s === "STRONG_UP" || s === "BULLISH") return "text-okx-profit";
  if (s === "STRONG_DOWN" || s === "BEARISH") return "text-okx-loss";
  return "text-okx-muted";
}

function OneEntryChart({
  assetLabel,
  hlSymbol,
  snap,
  signal,
}: {
  assetLabel: string;
  hlSymbol: string | null;
  snap: ChartSnap | undefined;
  signal: SignalLite | undefined;
}) {
  const rows = snap?.series_5m ?? [];
  const tf = snap?.tf_5m ?? "5m";
  const status = snap?.signal_status ?? signal?.status ?? "—";
  const reason = snap?.signal_reason ?? signal?.reason ?? "";
  const s15 = snap?.structure_15m ?? signal?.structure_15m ?? "—";
  const t1h = snap?.trend_1h ?? signal?.trend_1h ?? "—";
  const last = rows.length ? rows[rows.length - 1] : null;
  const lastEma = last && typeof last.ema === "number" ? last.ema : null;

  const readyLong = status === "READY_LONG";
  const readyShort = status === "READY_SHORT";
  const scanning = !readyLong && !readyShort;

  if (!hlSymbol) {
    return (
      <div className="flex min-h-[200px] flex-col rounded border border-okx-border/50 bg-okx-bg/40 p-2">
        <div className="mb-1 font-mono text-[11px] font-semibold text-okx-text">
          {assetLabel}
        </div>
        <p className="font-mono text-[10px] text-okx-muted">
          Нет пары в конфиге (ожидался {assetLabel.split(" ")[0]}/USDC на Hyperliquid).
        </p>
      </div>
    );
  }

  if (!rows.length) {
    return (
      <div className="flex min-h-[200px] flex-col rounded border border-okx-border/50 bg-okx-bg/40 p-2">
        <div className="mb-1 flex flex-wrap items-baseline justify-between gap-1">
          <span className="font-mono text-[11px] font-semibold text-okx-text">
            {assetLabel}
          </span>
          <span className="font-mono text-[9px] text-okx-muted">{hlSymbol}</span>
        </div>
        <p className="font-mono text-[10px] text-okx-muted">Загрузка свечей…</p>
      </div>
    );
  }

  return (
    <div className="flex min-h-[200px] flex-col rounded border border-okx-border/60 bg-okx-bg/30 p-2">
      <div className="mb-1 flex flex-wrap items-baseline justify-between gap-1">
        <span className="font-mono text-[11px] font-semibold text-okx-text">
          {assetLabel}
        </span>
        <span className="font-mono text-[9px] text-okx-muted">{hlSymbol}</span>
      </div>
      <div className="mb-1 font-mono text-[9px] leading-tight text-okx-muted">
        <span className={tfClass(s15)}>{s15}</span>
        <span className="text-okx-border"> · </span>
        <span className={tfClass(t1h)}>{t1h}</span>
        <span className="text-okx-border"> · </span>
        <span className="text-okx-text">{status}</span>
        {reason ? <span className="text-okx-muted"> — {reason}</span> : null}
      </div>
      <div className="relative flex-1 min-h-[168px] w-full">
        {scanning ? (
          <div
            className="pointer-events-none absolute right-1 top-0 z-10 rounded bg-okx-border/30 px-1.5 py-0.5 font-mono text-[8px] text-okx-muted"
            title="Бот проверяет фильтры к следующей сделке"
          >
            поиск входа
          </div>
        ) : null}
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart
            data={rows}
            margin={{ top: 8, right: 4, left: 0, bottom: 4 }}
          >
            <XAxis
              dataKey="t"
              type="number"
              scale="time"
              domain={["dataMin", "dataMax"]}
              tickFormatter={(v) =>
                new Date(v).toLocaleTimeString("ru-RU", {
                  hour: "2-digit",
                  minute: "2-digit",
                  timeZone: "UTC",
                }) + "Z"
              }
              tick={{ fontSize: 8, fill: "#848e9c" }}
              height={20}
            />
            <YAxis
              domain={["auto", "auto"]}
              tick={{ fontSize: 8, fill: "#848e9c" }}
              width={46}
            />
            <Tooltip
              contentStyle={{
                background: "#141720",
                border: "1px solid #2a2d36",
                fontSize: 10,
              }}
              labelFormatter={(v) =>
                new Date(Number(v)).toISOString().slice(0, 19) + "Z"
              }
            />
            {lastEma != null ? (
              <ReferenceLine
                y={lastEma}
                stroke="#f0b90b"
                strokeOpacity={0.35}
                strokeDasharray="4 4"
                ifOverflow="extendDomain"
              />
            ) : null}
            <Line
              type="monotone"
              dataKey="c"
              name="close"
              stroke="#aeb4bc"
              dot={false}
              strokeWidth={1.1}
              isAnimationActive={false}
            />
            <Line
              type="monotone"
              dataKey="ema"
              name="EMA вход"
              stroke="#f0b90b"
              dot={false}
              strokeWidth={1.4}
              connectNulls
              isAnimationActive={false}
            />
            {last && readyLong ? (
              <ReferenceDot
                x={last.t}
                y={last.c}
                r={7}
                fill="#0ecb81"
                stroke="#fff"
                strokeWidth={1.5}
                isFront
              />
            ) : null}
            {last && readyShort ? (
              <ReferenceDot
                x={last.t}
                y={last.c}
                r={7}
                fill="#f6465d"
                stroke="#fff"
                strokeWidth={1.5}
                isFront
              />
            ) : null}
            {last && scanning ? (
              <ReferenceDot
                x={last.t}
                y={last.c}
                r={3}
                fill="#848e9c"
                stroke="#2a2d36"
                strokeWidth={1}
                isFront
              />
            ) : null}
          </ComposedChart>
        </ResponsiveContainer>
      </div>
      <div className="mt-1 font-mono text-[8px] text-okx-muted">
        {tf}: цена vs EMA — как на скальпе; большая точка = бот видит{" "}
        <span className="text-okx-profit">READY_LONG</span> /{" "}
        <span className="text-okx-loss">READY_SHORT</span>
        {signal?.rsi != null ? (
          <>
            {" "}
            · RSI {Number(signal.rsi).toFixed(0)}
          </>
        ) : null}
        {signal?.volume_ratio != null ? (
          <>
            {" "}
            · Vol×{Number(signal.volume_ratio).toFixed(2)}
          </>
        ) : null}
      </div>
    </div>
  );
}

export function EntrySearchChartsPanel({
  charts,
  signals,
}: {
  charts?: Record<string, ChartSnap>;
  signals?: Record<string, SignalLite>;
}) {
  return (
    <div>
      <p className="mb-3 font-mono text-[10px] leading-snug text-okx-muted">
        Три актива: на каждом графике тот же таймфрейм, что у бота для входа (
        <span className="text-okx-text">close + EMA</span>
        ), плюс фильтры 15m структура и 1H тренд. Яркая точка на последней цене — момент,
        когда статус уже <span className="text-okx-profit">READY_LONG</span> или{" "}
        <span className="text-okx-loss">READY_SHORT</span>; серая маленькая — ещё идёт
        проверка условий.
      </p>
      <div className="grid gap-3 lg:grid-cols-3">
        {SLOTS.map(({ base, label }) => {
          const hl = findHlSymbol(base, charts, signals);
          const snap = hl ? charts?.[hl] : undefined;
          const sig = hl ? signals?.[hl] : undefined;
          return (
            <OneEntryChart
              key={base}
              assetLabel={label}
              hlSymbol={hl}
              snap={snap}
              signal={sig}
            />
          );
        })}
      </div>
    </div>
  );
}
