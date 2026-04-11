import React, { useEffect, useMemo, useState } from "react";
import ControlPanel, { type TradingCapitalPayload } from "./components/ControlPanel";
import PnLPanel from "./components/PnLPanel";
import ActivePositionsTable from "./components/ActivePositionsTable";
import RiskMonitor from "./components/RiskMonitor";
import ScalpingStats from "./components/ScalpingStats";
import SignalIndicator, { type ScalpIndicatorSnapshot } from "./components/SignalIndicator";
import SimulationPanel, { type SimulationSnapshot } from "./components/SimulationPanel";
import ModeBanner from "./components/ModeBanner";
import SimulationStrip from "./components/SimulationStrip";
import SpreadChart from "./components/SpreadChart";
import TradeLog from "./components/TradeLog";
import BreakoutPositions from "./components/breakout/BreakoutPositions";
import BreakoutSignalMonitor from "./components/breakout/BreakoutSignalMonitor";
import BreakoutStats from "./components/breakout/BreakoutStats";
import EMAStatusBar from "./components/ema_scalper/EMAStatusBar";
import EMAPositionCard from "./components/ema_scalper/EMAPositionCard";
import EMAStatsPanel from "./components/ema_scalper/EMAStatsPanel";
import EMAMiniChart from "./components/ema_scalper/EMAMiniChart";
import EMATradeLog from "./components/ema_scalper/EMATradeLog";
import { useWebSocket } from "./hooks/useWebSocket";

const ENTRY_Z = 1.5;
const STOP_Z = 3.0;

export default function App() {
  const { state, isConnected, sendMessage } = useWebSocket();
  const [fileSimulation, setFileSimulation] = useState<SimulationSnapshot | null>(null);

  useEffect(() => {
    fetch("/simulation.json")
      .then((r) => (r.ok ? r.json() : null))
      .then((data) => setFileSimulation(data))
      .catch(() => setFileSimulation(null));
  }, []);

  const botStatus = (state?.bot_status as string) ?? "stopped";
  const strategyMode = (state?.strategy_mode as string) ?? "pairs";
  const exchangeName = (state?.exchange_name as string) ?? "";
  const simulationWs = state?.simulation as SimulationSnapshot | undefined;
  const simulation = simulationWs ?? fileSimulation;
  const simSource: "websocket" | "file" | "none" = simulationWs
    ? "websocket"
    : fileSimulation
      ? "file"
      : "none";
  const positions = (state?.positions as React.ComponentProps<typeof PnLPanel>["positions"]) ?? [];
  const metrics =
    (state?.metrics as Record<string, { zscore?: number | null; spread_history?: number[]; zscore_history?: number[] }>) ??
    {};
  const pnl = (state?.pnl as { total_today?: number; unrealized?: number; realized_today?: number }) ?? {};
  const trades = (state?.trades_recent as React.ComponentProps<typeof TradeLog>["trades"]) ?? [];
  const flags = (state?.config_flags as { dry_run?: boolean; testnet?: boolean }) ?? {
    dry_run: true,
    testnet: true,
  };
  const tradingCapital = (state?.trading_capital as TradingCapitalPayload | undefined) ?? null;

  const sm = state?.scalping_metrics as
    | {
        todayStats?: React.ComponentProps<typeof ScalpingStats>["today"];
        currentSignal?: Record<string, Record<string, unknown>>;
        dailyProgress?: React.ComponentProps<typeof RiskMonitor>["dailyProgress"];
        riskMonitor?: React.ComponentProps<typeof RiskMonitor>["riskMonitor"];
      }
    | undefined;

  const totalPairs = Object.keys(metrics).length || 1;
  const openPairs = positions.length;
  const todayPnl = Number(pnl.total_today ?? pnl.realized_today ?? 0);
  const unrealized = Number(pnl.unrealized ?? 0);

  const closed = trades.filter((t) => t.action === "CLOSE" && t.pnl_usdt != null);
  const wins = closed.filter((t) => (t.pnl_usdt ?? 0) > 0).length;
  const winRate = closed.length ? (wins / closed.length) * 100 : 0;

  const breakoutState = state?.breakout as
    | {
        positions?: React.ComponentProps<typeof BreakoutPositions>["positions"];
        last_signals?: Record<string, { signal?: string; volume_ratio?: number; breakout_level?: number }>;
        stats_today?: React.ComponentProps<typeof BreakoutStats>["statsToday"];
        stats?: Record<string, unknown>;
        equity_history?: number[];
      }
    | undefined;

  const emaState = state?.ema_scalper as
    | {
        positions?: React.ComponentProps<typeof EMAPositionCard>["positions"];
        indicators?: Record<string, Record<string, unknown>>;
        stats?: Record<string, unknown>;
        candle_history?: Record<string, { ts: number; close: number; ema: number }[]>;
        recent_trades?: Record<string, unknown>[];
      }
    | undefined;

  const breakoutOpenSyms = useMemo(() => {
    const s = new Set<string>();
    for (const p of breakoutState?.positions ?? []) {
      if (p.status === "OPEN") s.add(p.symbol);
    }
    return s;
  }, [breakoutState?.positions]);

  const emaChartSym = useMemo(() => {
    const ch = emaState?.candle_history ?? {};
    const keys = Object.keys(ch);
    if (keys.length) return keys[0];
    const ind = emaState?.indicators ?? {};
    return Object.keys(ind)[0] ?? "";
  }, [emaState?.candle_history, emaState?.indicators]);

  const emaChartCandles = emaChartSym ? emaState?.candle_history?.[emaChartSym] ?? [] : [];
  const emaOpenPos = emaState?.positions?.[0];
  const emaPosForChart =
    emaOpenPos && emaChartSym && emaOpenPos.symbol === emaChartSym
      ? {
          entry_price: emaOpenPos.entry_price,
          tp_price: emaOpenPos.tp_price,
          sl_price: emaOpenPos.sl_price,
          side: emaOpenPos.side,
        }
      : null;

  return (
    <div className="min-h-screen flex flex-col bg-terminal-bg text-gray-100 font-mono text-sm">
      <ModeBanner testnet={flags.testnet !== false} dryRun={flags.dry_run !== false} />
      <SimulationStrip exchangeName={exchangeName} simulation={simulation} strategyMode={strategyMode} />

      <SimulationPanel simulation={simulation} source={simSource} />

      <ControlPanel
        botStatus={isConnected ? botStatus : "stopped"}
        isConnected={isConnected}
        openPairs={openPairs}
        totalPairs={totalPairs}
        todayPnl={todayPnl}
        unrealized={unrealized}
        winRate={winRate}
        dryRun={flags.dry_run !== false}
        testnet={flags.testnet !== false}
        tradingCapital={tradingCapital}
        strategyMode={strategyMode}
        onPause={() => sendMessage({ action: "pause" })}
        onResume={() => sendMessage({ action: "resume" })}
        onEmergency={() => sendMessage({ action: "emergency_stop" })}
        onPauseAfterLoss={
          strategyMode === "scalping" ? () => sendMessage({ action: "pause" }) : undefined
        }
      />

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-0 flex-1 min-h-0">
        <div className="min-h-[320px] lg:min-h-0 border-b lg:border-b-0 lg:border-r border-gray-800 flex flex-col min-h-0">
          <PnLPanel
            positions={positions}
            totalUnrealized={unrealized}
            totalRealized={todayPnl}
            onClosePair={(pairId) => sendMessage({ action: "close_pair", pair_id: pairId })}
          />
          {strategyMode === "scalping" && (
            <div className="p-2 border-t border-gray-800 grid grid-cols-1 sm:grid-cols-2 gap-2 overflow-auto max-h-[280px]">
              <ScalpingStats today={sm?.todayStats ?? {}} />
              <RiskMonitor dailyProgress={sm?.dailyProgress} riskMonitor={sm?.riskMonitor} />
              <ActivePositionsTable positions={positions} />
              <SignalIndicator signals={(sm?.currentSignal ?? {}) as Record<string, ScalpIndicatorSnapshot>} />
            </div>
          )}
        </div>
        <div className="min-h-[420px] lg:min-h-0">
          <SpreadChart
            metricsByPair={metrics}
            entryZ={ENTRY_Z}
            stopZ={STOP_Z}
            scalpMode={strategyMode === "scalping"}
          />
        </div>
      </div>

      {state?.breakout != null &&
      ((breakoutState?.last_signals && Object.keys(breakoutState.last_signals).length > 0) ||
        (breakoutState?.positions && breakoutState.positions.length > 0)) ? (
        <div className="border-t border-gray-800 p-3 space-y-3 bg-black/20">
          <h2 className="text-amber-500/90 text-xs uppercase tracking-wider">Breakout (1H)</h2>
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-3">
            <BreakoutSignalMonitor
              lastSignals={breakoutState?.last_signals ?? {}}
              openSymbols={breakoutOpenSyms}
            />
            <BreakoutPositions
              positions={breakoutState?.positions ?? []}
              sendMessage={sendMessage}
            />
            <BreakoutStats
              statsToday={breakoutState?.stats_today ?? {}}
              stats={(breakoutState?.stats ?? {}) as React.ComponentProps<typeof BreakoutStats>["stats"]}
              equityHistory={breakoutState?.equity_history ?? []}
            />
          </div>
        </div>
      ) : null}

      {state?.ema_scalper != null ? (
        <div className="border-t border-gray-800 p-3 space-y-3 bg-black/20">
          <h2 className="text-emerald-500/90 text-xs uppercase tracking-wider">EMA Scalper (5m)</h2>
          {Object.keys(emaState?.indicators ?? {}).length === 0 &&
          !(emaState?.positions?.length ?? 0) &&
          !(emaState?.recent_trades?.length ?? 0) ? (
            <p className="text-gray-600 text-xs">EMA: прогрев данных или стратегия без активных пар</p>
          ) : (
            <>
              <EMAStatusBar indicators={(emaState?.indicators ?? {}) as Record<string, Record<string, unknown>>} />
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
                <EMAPositionCard positions={emaState?.positions ?? []} sendMessage={sendMessage} />
                <div className="space-y-2">
                  <div className="text-[10px] text-gray-500">Мини-график: {emaChartSym || "—"}</div>
                  <EMAMiniChart candles={emaChartCandles} position={emaPosForChart} />
                </div>
              </div>
              <EMAStatsPanel stats={(emaState?.stats ?? {}) as React.ComponentProps<typeof EMAStatsPanel>["stats"]} />
              <EMATradeLog trades={emaState?.recent_trades ?? []} />
            </>
          )}
        </div>
      ) : null}

      <TradeLog trades={trades} />
    </div>
  );
}
