type LastSig = {
  signal?: string;
  volume_ratio?: number;
  breakout_level?: number;
};

const VOL_OK = 1.2;

export default function BreakoutSignalMonitor({
  lastSignals,
  openSymbols,
}: {
  lastSignals: Record<string, LastSig>;
  openSymbols: Set<string>;
}) {
  const rows = Object.entries(lastSignals);
  if (!rows.length) {
    return <div className="text-gray-500 text-xs">Нет данных сигналов breakout</div>;
  }
  return (
    <div className="overflow-x-auto border border-gray-800 rounded">
      <table className="w-full text-xs text-left">
        <thead className="text-gray-500 border-b border-gray-800">
          <tr>
            <th className="p-2">Пара</th>
            <th className="p-2">Сигнал</th>
            <th className="p-2">Vol ratio</th>
            <th className="p-2">Уровень</th>
            <th className="p-2">Статус</th>
          </tr>
        </thead>
        <tbody>
          {rows.map(([sym, s]) => {
            const vol = s.volume_ratio ?? 0;
            const volClass = vol >= VOL_OK ? "text-emerald-400" : "text-gray-500";
            const inPos = openSymbols.has(sym);
            let status = "○ NO SIGNAL";
            let statusClass = "text-gray-500";
            if (inPos) {
              status = "● IN POSITION";
              statusClass = "text-sky-400 animate-pulse";
            } else if (s.signal === "LONG") {
              status = "● LONG READY";
              statusClass = "text-emerald-400 animate-pulse";
            } else if (s.signal === "SHORT") {
              status = "● SHORT READY";
              statusClass = "text-rose-400 animate-pulse";
            } else {
              status = "● WATCHING";
              statusClass = "text-gray-400";
            }
            return (
              <tr key={sym} className="border-b border-gray-900">
                <td className="p-2 font-mono">{sym}</td>
                <td className="p-2">{s.signal ?? "—"}</td>
                <td className={`p-2 ${volClass}`}>
                  {vol.toFixed(2)}x {vol >= VOL_OK ? "✓" : "✗"}
                </td>
                <td className="p-2">${(s.breakout_level ?? 0).toLocaleString()}</td>
                <td className={`p-2 ${statusClass}`}>{status}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
