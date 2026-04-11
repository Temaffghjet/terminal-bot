export type ScalpIndicatorSnapshot = {
  ema?: number | null;
  volume_avg?: number | null;
  volume_current?: number | null;
  last_close?: number | null;
  is_green?: boolean;
  quote_volume_est?: number | null;
};

type Props = { signals: Record<string, ScalpIndicatorSnapshot> };

export default function SignalIndicator({ signals }: Props) {
  const ids = Object.keys(signals);
  if (!ids.length) {
    return (
      <div className="border border-gray-800 rounded p-2 bg-[#0a0a0f] text-[11px] text-gray-600">
        Нет данных индикаторов (ждём WS)
      </div>
    );
  }
  return (
    <div className="border border-gray-800 rounded p-2 bg-[#0a0a0f] text-[11px] space-y-2">
      <div className="text-gray-500 uppercase tracking-wider text-[10px]">Сигнал (EMA / объём)</div>
      {ids.map((id) => {
        const s = signals[id] ?? {};
        const ema = s.ema;
        const close = s.last_close;
        const above =
          ema != null && close != null ? (close > ema ? "above EMA" : "below EMA") : "—";
        const volOk =
          s.volume_avg != null && s.volume_current != null && s.volume_avg > 0
            ? s.volume_current > s.volume_avg * 1.2
            : null;
        return (
          <div key={id} className="border-b border-gray-900 last:border-0 pb-1 last:pb-0">
            <div className="font-mono text-terminal-profit">{id}</div>
            <div className="text-gray-400 grid grid-cols-[1fr_auto] gap-1">
              <span>Цена vs EMA(9)</span>
              <span className={above.includes("above") ? "text-terminal-profit" : "text-terminal-warn"}>
                {above}
              </span>
              <span>Объём</span>
              <span className={volOk === true ? "text-terminal-profit" : volOk === false ? "text-terminal-loss" : "—"}>
                {volOk === true ? "OK" : volOk === false ? "NO" : "—"}
              </span>
              <span>Свеча</span>
              <span>{s.is_green ? "green" : "red"}</span>
            </div>
          </div>
        );
      })}
    </div>
  );
}
