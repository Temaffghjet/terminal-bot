import React, { useMemo } from "react";
import ControlPanel, { type EmaSlotDisplay, type TradingCapitalPayload } from "./components/ControlPanel";
import PnLPanel from "./components/PnLPanel";
import ActivePositionsTable from "./components/ActivePositionsTable";
import RiskMonitor from "./components/RiskMonitor";
import ScalpingStats from "./components/ScalpingStats";
import SignalIndicator, { type ScalpIndicatorSnapshot } from "./components/SignalIndicator";
import ModeBanner from "./components/ModeBanner";
import SpreadChart from "./components/SpreadChart";
import TradeLog from "./components/TradeLog";
import EMAStatusBar from "./components/ema_scalper/EMAStatusBar";
import EMAPositionCard from "./components/ema_scalper/EMAPositionCard";
import EMAStatsPanel from "./components/ema_scalper/EMAStatsPanel";
import EMAMiniChart from "./components/ema_scalper/EMAMiniChart";
import EMATradeLog from "./components/ema_scalper/EMATradeLog";
import EMAEntryAnalytics from "./components/ema_scalper/EMAEntryAnalytics";
import EMAAutoTunerPanel from "./components/ema_scalper/EMAAutoTunerPanel";
import { useWebSocket } from "./hooks/useWebSocket";

const ENTRY_Z = 1.5;
const STOP_Z = 3.0;

function emaSymbolBaseShort(symbol: string): string {
  const base = symbol.split("/")[0] ?? symbol;
  return base.replace(/^XYZ-/, "");
}

export default function App() {
  const { state, isConnected, sendMessage } = useWebSocket();

  const botStatus = (state?.bot_status as string) ?? "stopped";
  const strategyMode = (state?.strategy_mode as string) ?? "pairs";
  const exchangeName = (state?.exchange_name as string) ?? "";
  const positions = (state?.positions as React.ComponentProps<typeof PnLPanel>["positions"]) ?? [];
  const metrics =
    (state?.metrics as Record<string, { zscore?: number | null; spread_history?: number[]; zscore_history?: number[] }>) ??
    {};
  const pnl = (state?.pnl as { total_today?: number; unrealized?: number; realized_today?: number }) ?? {};
  const trades = (state?.trades_recent as React.ComponentProps<typeof TradeLog>["trades"]) ?? [];
  const flags = (state?.config_flags as {
    dry_run?: boolean;
    testnet?: boolean;
    risk_leverage?: number;
  }) ?? {
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

  const emaState = state?.ema_scalper as
    | {
        positions?: React.ComponentProps<typeof EMAPositionCard>["positions"];
        indicators?: Record<string, Record<string, unknown>>;
        stats?: Record<string, unknown>;
        candle_history?: Record<string, { ts: number; close: number; ema: number }[]>;
        recent_trades?: Record<string, unknown>[];
        /** Пары из config.yaml (enabled) */
        enabled_symbols?: string[];
        max_open_positions?: number;
        auto_tuner?: Record<string, unknown>;
        auto_tuner_history?: Record<string, unknown>[];
        profiles?: Record<
          string,
          {
            id?: string;
            label?: string;
            positions?: React.ComponentProps<typeof EMAPositionCard>["positions"];
            indicators?: Record<string, Record<string, unknown>>;
            stats?: Record<string, unknown>;
            candle_history?: Record<string, { ts: number; close: number; ema: number }[]>;
            recent_trades?: Record<string, unknown>[];
            enabled_symbols?: string[];
            max_open_positions?: number;
          }
        >;
      }
    | undefined;

  const emaSlotDisplay: EmaSlotDisplay | null = useMemo(() => {
    const syms = emaState?.enabled_symbols;
    if (!syms?.length) return null;
    const open = emaState?.positions?.length ?? 0;
    const max = emaState?.max_open_positions ?? 2;
    return { label: "EMA слоты", open, max };
  }, [
    emaState?.enabled_symbols,
    emaState?.positions?.length,
    emaState?.max_open_positions,
  ]);

  const emaWatchlistShort = useMemo(
    () => (emaState?.enabled_symbols ?? []).map(emaSymbolBaseShort),
    [emaState?.enabled_symbols],
  );

  const emaUi = state?.ema_scalper != null;

  const emaPolicy = useMemo(() => {
    const c = tradingCapital?.config;
    if (c == null || c.ema_balance_usdt == null) return null;
    const pct = c.ema_position_size_pct ?? 25;
    const lev = c.ema_leverage ?? 5;
    const margin = Number(c.ema_balance_usdt) * (pct / 100);
    if (!(margin > 0)) return null;
    return { marginUsdt: margin, nominalUsdt: margin * lev, leverage: lev };
  }, [tradingCapital]);

  const emaChartSym = useMemo(() => {
    const pos0 = emaState?.positions?.[0]?.symbol;
    if (pos0) return pos0;
    const ch = emaState?.candle_history ?? {};
    const keys = Object.keys(ch);
    if (keys.length) return keys[0];
    const ind = emaState?.indicators ?? {};
    const ik = Object.keys(ind);
    if (ik.length) return ik[0];
    return (emaState?.enabled_symbols ?? [])[0] ?? "";
  }, [
    emaState?.candle_history,
    emaState?.indicators,
    emaState?.positions,
    emaState?.enabled_symbols,
  ]);

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
      {!isConnected && (
        <div className="border-b border-amber-700/50 bg-amber-950/50 px-3 py-2 text-amber-100/95 text-xs leading-snug">
          Нет WebSocket к боту — поля «Биржа» и «Сумма для торговли» пустые: данные не с сервера. На Vercel
          задайте <code className="text-amber-200">VITE_WS_URL=wss://ваш-хост:порт</code> (где крутится Python-бот)
          и пересоберите проект; локально запустите бота на порту из <code className="text-amber-200">VITE_WS_PORT</code>
          .
        </div>
      )}
      <div className="border-b border-gray-800 px-3 py-1.5 bg-[#080810] text-[11px] text-gray-400 flex flex-wrap gap-x-6 gap-y-1 items-center">
        <span>
          Биржа:{" "}
          <span className="text-terminal-profit font-semibold uppercase">{exchangeName || "—"}</span>
          {strategyMode === "scalping" && (
            <span className="ml-2 text-gray-600">live-данные с биржи из config (exchange.name).</span>
          )}
        </span>
      </div>

      <ControlPanel
        botStatus={isConnected ? botStatus : "stopped"}
        isConnected={isConnected}
        openPairs={openPairs}
        totalPairs={totalPairs}
        emaSlotDisplay={emaSlotDisplay}
        emaWatchlistShort={emaWatchlistShort.length ? emaWatchlistShort : null}
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
          {strategyMode === "scalping" && !emaUi && (
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

      {state?.ema_scalper != null ? (
        <div className="border-t border-gray-800 p-3 space-y-3 bg-black/20">
          <h2 className="text-emerald-500/90 text-xs uppercase tracking-wider">EMA Scalper (5m)</h2>
          {Object.keys(emaState?.indicators ?? {}).length === 0 &&
          !(emaState?.positions?.length ?? 0) &&
          !(emaState?.recent_trades?.length ?? 0) &&
          !(emaState?.enabled_symbols?.length ?? 0) ? (
            <p className="text-gray-600 text-xs">EMA: прогрев данных или стратегия без активных пар</p>
          ) : (
            <>
              <EMAStatusBar
                indicators={(emaState?.indicators ?? {}) as Record<string, Record<string, unknown>>}
                watchlist={emaState?.enabled_symbols ?? []}
                depositMeta={{
                  useExchangeBalance: Boolean(tradingCapital?.config?.ema_use_exchange_balance),
                  balanceUsdt: Number(tradingCapital?.config?.ema_balance_usdt ?? 0),
                }}
              />
              <EMAEntryAnalytics
                indicators={(emaState?.indicators ?? {}) as Record<string, Record<string, unknown>>}
                watchlist={emaState?.enabled_symbols ?? []}
              />
              <EMAAutoTunerPanel
                tuner={
                  (emaState?.auto_tuner ?? {}) as React.ComponentProps<typeof EMAAutoTunerPanel>["tuner"]
                }
                history={
                  (emaState?.auto_tuner_history ?? []) as React.ComponentProps<
                    typeof EMAAutoTunerPanel
                  >["history"]
                }
              />
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
                <EMAPositionCard positions={emaState?.positions ?? []} sendMessage={sendMessage} />
                <div className="space-y-2">
                  <div className="text-[10px] text-gray-500">Мини-график: {emaChartSym || "—"}</div>
                  <EMAMiniChart candles={emaChartCandles} position={emaPosForChart} />
                </div>
              </div>
              <EMAStatsPanel stats={(emaState?.stats ?? {}) as React.ComponentProps<typeof EMAStatsPanel>["stats"]} />
              <EMATradeLog trades={emaState?.recent_trades ?? []} />
              {emaState?.profiles && Object.keys(emaState.profiles).length > 1 ? (
                <div className="space-y-4 pt-2 border-t border-gray-800">
                  {Object.entries(emaState.profiles).map(([pid, prof]) => (
                    <div key={pid} className="border border-gray-800 rounded p-3 bg-[#0b0b12] space-y-3">
                      <div className="text-[11px] uppercase tracking-wider text-emerald-300">
                        Профиль: {String(prof.label ?? pid)}
                      </div>
                      <EMAStatusBar
                        indicators={(prof.indicators ?? {}) as Record<string, Record<string, unknown>>}
                        watchlist={prof.enabled_symbols ?? []}
                        depositMeta={{
                          useExchangeBalance: Boolean(tradingCapital?.config?.ema_use_exchange_balance),
                          balanceUsdt: 500,
                        }}
                      />
                      <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
                        <EMAPositionCard positions={prof.positions ?? []} sendMessage={sendMessage} />
                        <EMAStatsPanel
                          stats={(prof.stats ?? {}) as React.ComponentProps<typeof EMAStatsPanel>["stats"]}
                        />
                      </div>
                      <EMATradeLog trades={prof.recent_trades ?? []} />
                    </div>
                  ))}
                </div>
              ) : null}
            </>
          )}
        </div>
      ) : null}

      {!emaUi ? (
        <TradeLog trades={trades} scalpLeverage={flags.risk_leverage ?? 5} emaPolicy={emaPolicy} />
      ) : null}
    </div>
  );
}
