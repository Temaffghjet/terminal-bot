type Ind = {
  volume_ratio?: number;
  above_ema_count?: number;
  below_ema_count?: number;
  rsi?: number;
  distance_from_ema_pct?: number;
  distance_from_vwap_pct?: number;
  adx?: number;
  atr_pct?: number;
  auto_trade_score?: number;
  auto_min_score_dynamic?: number;
  auto_allow_trade?: boolean;
  higher_tf_trend?: string | null;
  signal_ready?: boolean;
  side_ready?: string | null;
};

function baseLabel(sym: string): string {
  const base = sym.split("/")[0] ?? sym;
  return base.replace(/^XYZ-/, "");
}

function clamp01(x: number): number {
  if (x < 0) return 0;
  if (x > 1) return 1;
  return x;
}

function qualityScore(ind: Ind): number {
  const trend = String(ind.higher_tf_trend ?? "");
  const vol = Number(ind.volume_ratio ?? 0);
  const streak = Math.max(Number(ind.above_ema_count ?? 0), Number(ind.below_ema_count ?? 0));
  const rsi = Number(ind.rsi ?? 50);
  const dist = Number(ind.distance_from_ema_pct ?? 0);
  const adx = Number(ind.adx ?? 0);
  const dvwap = Number(ind.distance_from_vwap_pct ?? 0);

  // Весовые блоки: trend + ADX + volume + streak + RSI + anti-FOMO.
  const trendScore = trend === "UP" || trend === "DOWN" ? 30 : 0;
  const adxScore = adx >= 25 ? 18 : adx >= 20 ? 12 : 0;
  const volScore = clamp01(vol / 2.0) * 25;
  const streakScore = clamp01(streak / 6.0) * 12;
  const rsiScore = rsi >= 35 && rsi <= 65 ? 15 : rsi >= 30 && rsi <= 70 ? 10 : 3;
  // Анти-fomo: слишком далеко от EMA (на импульсе) снижает score
  const distScore = dist <= 0.7 ? 6 : dist <= 1.0 ? 4 : 1;
  const vwapScore = dvwap <= 0.9 ? 12 : dvwap <= 1.2 ? 7 : 2;

  return Math.round(trendScore + adxScore + volScore + streakScore + rsiScore + distScore + vwapScore);
}

function grade(score: number): { label: string; cls: string } {
  if (score >= 75) return { label: "A / strong", cls: "text-emerald-400" };
  if (score >= 60) return { label: "B / tradable", cls: "text-lime-400" };
  if (score >= 45) return { label: "C / weak", cls: "text-amber-400" };
  return { label: "D / skip", cls: "text-rose-400" };
}

export default function EMAEntryAnalytics({
  indicators,
  watchlist = [],
}: {
  indicators: Record<string, Ind>;
  watchlist?: string[];
}) {
  const ordered = watchlist.length ? watchlist : Object.keys(indicators).sort();
  if (!ordered.length) {
    return <div className="text-gray-500 text-xs">Нет пар для аналитики входа.</div>;
  }
  const scored = ordered
    .map((sym) => {
      const ind = indicators[sym];
      const modelScore = Number(ind?.auto_trade_score ?? 0);
      const score = modelScore > 0 ? modelScore : ind ? qualityScore(ind) : 0;
      return { sym, ind, score };
    })
    .sort((a, b) => b.score - a.score);
  const dynMin = Number(scored.find((x) => x.ind?.auto_min_score_dynamic != null)?.ind?.auto_min_score_dynamic ?? 60);
  const tradable = scored.filter((x) => x.ind && x.score >= dynMin).length;
  const avg = scored.length ? scored.reduce((s, x) => s + x.score, 0) / scored.length : 0;

  return (
    <div className="border border-emerald-900/60 rounded-lg p-3 bg-gradient-to-b from-emerald-950/20 to-transparent space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="text-[11px] text-emerald-300 uppercase tracking-wider">
          Alpha Radar: ADX + ATR + VWAP + Trend
        </div>
        <div className="text-[11px] text-gray-400">
          tradable <span className="text-white">{tradable}</span> / {scored.length} · avg score{" "}
          <span className="text-white">{avg.toFixed(1)}</span> · min <span className="text-white">{dynMin.toFixed(0)}</span>
        </div>
      </div>
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-2">
        <div className="border border-gray-800 rounded p-2">
          <div className="text-[10px] text-gray-500 uppercase mb-1">Top Candidate</div>
          {scored[0]?.ind ? (
            <div className="text-xs">
              <div className="text-amber-300">{baseLabel(scored[0].sym)}</div>
              <div className={grade(scored[0].score).cls}>score {scored[0].score}</div>
              <div className="text-gray-400">
                adx {Number(scored[0].ind.adx ?? 0).toFixed(1)} · dvwap{" "}
                {Number(scored[0].ind.distance_from_vwap_pct ?? 0).toFixed(2)}%
              </div>
            </div>
          ) : (
            <div className="text-xs text-gray-500">нет прогретых данных</div>
          )}
        </div>
        <div className="border border-gray-800 rounded p-2">
          <div className="text-[10px] text-gray-500 uppercase mb-1">Filters Health</div>
          <div className="text-xs text-gray-300">ADX anti-chop active</div>
          <div className="text-xs text-gray-300">VWAP anti-FOMO active</div>
          <div className="text-xs text-gray-300">ATR adaptive TP/SL active</div>
        </div>
        <div className="border border-gray-800 rounded p-2">
          <div className="text-[10px] text-gray-500 uppercase mb-1">Action Hint</div>
          <div className="text-xs text-gray-300">
            {tradable > 0 ? "Есть пары с валидным контекстом для входа." : "Рынок шумный: лучше ждать."}
          </div>
          <div className="text-[10px] text-gray-500 mt-1">Сначала смотри пары с A/B grade.</div>
        </div>
      </div>
      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-2">
        {scored.map(({ sym, ind, score }) => {
          if (!ind) {
            return (
              <div key={sym} className="border border-gray-800 rounded px-2 py-1 text-xs text-gray-500">
                {baseLabel(sym)}: прогрев...
              </div>
            );
          }
          const g = grade(score);
          const trend = String(ind.higher_tf_trend ?? "—");
          const vol = Number(ind.volume_ratio ?? 0).toFixed(2);
          const dist = Number(ind.distance_from_ema_pct ?? 0).toFixed(2);
          const dvwap = Number(ind.distance_from_vwap_pct ?? 0).toFixed(2);
          const rsi = Number(ind.rsi ?? 50).toFixed(1);
          const adx = Number(ind.adx ?? 0).toFixed(1);
          const atrp = Number(ind.atr_pct ?? 0).toFixed(2);
          const allow = ind.auto_allow_trade;
          return (
            <div key={sym} className="border border-gray-800 rounded px-2 py-1 text-xs">
              <div className="flex items-center justify-between">
                <span className="text-amber-400">{baseLabel(sym)}</span>
                <span className={g.cls}>{g.label}</span>
              </div>
              <div className="text-gray-300">
                score <span className="text-white">{score}</span> · trend {trend} · vol {vol}x · adx {adx}
              </div>
              <div className="text-gray-500">
                RSI {rsi} · dEMA {dist}% · dVWAP {dvwap}% · ATR {atrp}% · ready {String(!!ind.signal_ready)} · auto{" "}
                {allow == null ? "?" : allow ? "yes" : "no"}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
