import { AlertTriangle } from "lucide-react";
import { useState } from "react";

export type ExchangeUsdtSlice = {
  /** USDT (Binance и др.) или USDC (Hyperliquid) — с бэкенда из ccxt. */
  currency?: string;
  free: number;
  used: number;
  total: number;
} | null;

export type TradingCapitalPayload = {
  config: {
    scalping_deposit_usdt: number;
    stat_arb_max_leg_usdt: number;
    stat_arb_max_total_exposure_usdt: number;
    breakout_balance_usdt: number;
    ema_balance_usdt: number;
    /** доля депозита EMA на одну сделку, % */
    ema_position_size_pct?: number;
    ema_leverage?: number;
    ema_use_exchange_balance?: boolean;
  };
  exchange_usdt: {
    main: ExchangeUsdtSlice;
    breakout: ExchangeUsdtSlice;
    ema: ExchangeUsdtSlice;
  };
  exchange_errors?: Record<string, string>;
};

/** Слоты EMA: открыто / max одновременных позиций (из config бэкенда). */
export type EmaSlotDisplay = {
  label: string;
  open: number;
  max: number;
};

type Props = {
  botStatus: string;
  isConnected: boolean;
  openPairs: number;
  totalPairs: number;
  /** Если задано — вместо «Open pairs» (stat-arb) показываем слоты EMA */
  emaSlotDisplay?: EmaSlotDisplay | null;
  /** Короткие имена базовых активов для подсказки в шапке */
  emaWatchlistShort?: string[] | null;
  todayPnl: number;
  unrealized: number;
  winRate: number;
  dryRun: boolean;
  testnet: boolean;
  tradingCapital?: TradingCapitalPayload | null;
  strategyMode?: string;
  onPause: () => void;
  onResume: () => void;
  onEmergency: () => void;
  /** Пауза после убытка — то же, что PAUSE (ручной стоп торговли) */
  onPauseAfterLoss?: () => void;
};

export default function ControlPanel({
  botStatus,
  isConnected,
  openPairs,
  totalPairs,
  todayPnl,
  unrealized,
  winRate,
  dryRun,
  testnet,
  tradingCapital,
  emaSlotDisplay = null,
  emaWatchlistShort = null,
  strategyMode = "pairs",
  onPause,
  onResume,
  onEmergency,
  onPauseAfterLoss,
}: Props) {
  const [modal, setModal] = useState(false);

  const showLiveWarning = !dryRun || !testnet;

  const statusColor =
    botStatus === "running"
      ? "bg-terminal-profit"
      : botStatus === "paused"
        ? "bg-terminal-warn"
        : "bg-terminal-loss";

  const pulse = botStatus === "stopped" ? "" : "animate-pulse-dot";

  return (
    <div className="border-b border-gray-800 px-3 py-2 flex flex-wrap items-center gap-4 justify-between bg-[#0d0d14]">
      {showLiveWarning && (
        <div className="w-full flex items-center gap-2 text-terminal-warn text-sm font-semibold border border-terminal-warn/40 rounded px-2 py-1 bg-terminal-warn/10">
          <AlertTriangle className="w-4 h-4 shrink-0" />
          <span>
            WARNING: live trading and/or mainnet may be enabled (dry_run={String(dryRun)}, testnet=
            {String(testnet)})
          </span>
        </div>
      )}

      <div className="flex items-center gap-3 min-w-[200px]">
        <span
          className={`inline-block w-2.5 h-2.5 rounded-full ${statusColor} ${pulse}`}
          title={isConnected ? "WS connected" : "WS disconnected"}
        />
        <span className="uppercase tracking-wide text-xs text-gray-400">Bot status</span>
        <span className="text-terminal-profit font-semibold">[{botStatus.toUpperCase()}]</span>
      </div>

      <div className="flex flex-wrap gap-6 text-xs font-mono text-gray-300 items-center">
        {tradingCapital && (
          <span
            className="border border-emerald-600/50 rounded px-2 py-0.5 bg-emerald-950/30 text-emerald-300 max-w-[min(100vw,520px)]"
            title="Баланс USDT/USDC с биржи (кэш ~30 с) + лимиты из config.yaml"
          >
            Сумма для торговли:{" "}
            <strong className="text-white">
              {tradingCapital.exchange_errors?.main
                ? `API: ${String(tradingCapital.exchange_errors.main).slice(0, 40)}`
                : tradingCapital.exchange_usdt?.main
                  ? `${tradingCapital.exchange_usdt.main.free.toFixed(2)} free / ${tradingCapital.exchange_usdt.main.total.toFixed(2)} ${tradingCapital.exchange_usdt.main.currency ?? "USDT"}`
                  : "—"}
            </strong>
            <span className="text-gray-500 mx-1">|</span>
            <span className="text-gray-400">
              {strategyMode === "scalping" ? (
                <>скальп ${tradingCapital.config.scalping_deposit_usdt.toFixed(0)} · </>
              ) : (
                <>
                  stat-arb нога ≤${tradingCapital.config.stat_arb_max_leg_usdt.toFixed(0)} · Σ≤$
                  {tradingCapital.config.stat_arb_max_total_exposure_usdt.toFixed(0)} ·{" "}
                </>
              )}
              br ${tradingCapital.config.breakout_balance_usdt.toFixed(0)} · EMA $
              {tradingCapital.config.ema_balance_usdt.toFixed(0)}
              {tradingCapital.config.ema_position_size_pct != null &&
                tradingCapital.config.ema_leverage != null && (
                  <span className="text-gray-500">
                    {" "}
                    ({tradingCapital.config.ema_position_size_pct.toFixed(0)}% маржи ·{" "}
                    {tradingCapital.config.ema_leverage}x)
                  </span>
                )}
              {tradingCapital.config.ema_use_exchange_balance ? (
                <span className="text-gray-500"> · баланс с HL</span>
              ) : null}
            </span>
          </span>
        )}
        {emaWatchlistShort != null && emaWatchlistShort.length > 0 ? (
          <span
            className="text-[10px] text-gray-500 max-w-[min(100vw,640px)] leading-snug"
            title={emaWatchlistShort.join(", ")}
          >
            Пары EMA:{" "}
            <span className="text-gray-300">{emaWatchlistShort.join(" · ")}</span>
          </span>
        ) : null}
        <span>
          {emaSlotDisplay ? (
            <>
              {emaSlotDisplay.label}:{" "}
              <span className="text-white">
                {emaSlotDisplay.open}/{emaSlotDisplay.max}
              </span>
            </>
          ) : (
            <>
              Open pairs:{" "}
              <span className="text-white">
                {openPairs}/{totalPairs}
              </span>
            </>
          )}
        </span>
        <span>
          Today P&amp;L:{" "}
          <span className={todayPnl >= 0 ? "text-terminal-profit" : "text-terminal-loss"}>
            {todayPnl >= 0 ? "+" : ""}
            {todayPnl.toFixed(2)} USDT
          </span>
        </span>
        <span>
          Unrealized:{" "}
          <span className={unrealized >= 0 ? "text-terminal-profit" : "text-terminal-loss"}>
            {unrealized >= 0 ? "+" : ""}
            {unrealized.toFixed(2)} USDT
          </span>
        </span>
        <span>
          Win rate: <span className="text-white">{winRate.toFixed(0)}%</span>
        </span>
      </div>

      <div className="flex gap-2">
        <button
          type="button"
          className="px-3 py-1 text-xs border border-terminal-warn text-terminal-warn hover:bg-terminal-warn/10"
          onClick={onPause}
        >
          PAUSE
        </button>
        {onPauseAfterLoss && (
          <button
            type="button"
            className="px-3 py-1 text-xs border border-gray-600 text-gray-300 hover:bg-gray-800"
            onClick={onPauseAfterLoss}
            title="Остановить торговлю после убыточной серии"
          >
            Пауза (убыток)
          </button>
        )}
        <button
          type="button"
          className="px-3 py-1 text-xs border border-terminal-profit text-terminal-profit hover:bg-terminal-profit/10"
          onClick={onResume}
        >
          ▶ RESUME
        </button>
        <button
          type="button"
          className="px-3 py-1 text-xs border border-terminal-loss text-terminal-loss hover:bg-terminal-loss/10"
          onClick={() => setModal(true)}
        >
          EMERGENCY STOP
        </button>
      </div>

      {modal && (
        <div className="fixed inset-0 bg-black/70 flex items-center justify-center z-50">
          <div className="bg-[#12121a] border border-terminal-loss p-6 max-w-md w-full shadow-xl">
            <p className="text-sm mb-4">
              This will close ALL open positions at market price immediately. Are you sure?
            </p>
            <div className="flex justify-end gap-3">
              <button
                type="button"
                className="px-4 py-2 text-xs border border-gray-600"
                onClick={() => setModal(false)}
              >
                Cancel
              </button>
              <button
                type="button"
                className="px-4 py-2 text-xs bg-terminal-loss text-black font-bold"
                onClick={() => {
                  setModal(false);
                  onEmergency();
                }}
              >
                CONFIRM STOP
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
