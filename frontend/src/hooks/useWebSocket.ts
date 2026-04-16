import { useCallback, useEffect, useRef, useState } from "react";

export type BotState = Record<string, unknown> | null;

const DEFAULT_PORT = import.meta.env.VITE_WS_PORT ?? "8765";

/** ws:// / wss:// только; http(s) → ws(s) чтобы не падал new WebSocket при ошибке в Vercel env */
function resolveWsUrl(): string {
  const raw = import.meta.env.VITE_WS_URL?.trim();
  if (!raw) {
    return `ws://localhost:${DEFAULT_PORT}`;
  }
  if (raw.startsWith("ws://") || raw.startsWith("wss://")) {
    return raw;
  }
  if (raw.startsWith("https://")) {
    return `wss://${raw.slice("https://".length)}`;
  }
  if (raw.startsWith("http://")) {
    return `ws://${raw.slice("http://".length)}`;
  }
  return raw;
}

export type EmaTradeByDayPayload = {
  date: string;
  trades: Record<string, unknown>[];
  error: string | null;
};

export function useWebSocket() {
  const [state, setState] = useState<BotState>(null);
  const [emaTradeByDay, setEmaTradeByDay] = useState<EmaTradeByDayPayload | null>(null);
  const [isConnected, setIsConnected] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);
  const backoffRef = useRef(1000);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const connect = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) return;
    const url = resolveWsUrl();
    let ws: WebSocket;
    try {
      ws = new WebSocket(url);
    } catch {
      console.error(
        "[WS] Неверный VITE_WS_URL. Нужен ws:// или wss:// на бота (порт",
        DEFAULT_PORT,
        "), не http://localhost:5173"
      );
      return;
    }
    wsRef.current = ws;

    ws.onopen = () => {
      setIsConnected(true);
      backoffRef.current = 1000;
    };

    ws.onclose = () => {
      setIsConnected(false);
      const delay = Math.min(backoffRef.current, 60_000);
      backoffRef.current = Math.min(backoffRef.current * 2, 60_000);
      timerRef.current = setTimeout(connect, delay);
    };

    ws.onerror = () => {
      ws.close();
    };

    ws.onmessage = (ev) => {
      try {
        const msg = JSON.parse(ev.data as string) as Record<string, unknown>;
        if (msg.type === "state_update") {
          setState(msg);
        } else if (msg.type === "ema_trade_history") {
          setEmaTradeByDay({
            date: String(msg.date ?? ""),
            trades: Array.isArray(msg.trades)
              ? (msg.trades as Record<string, unknown>[])
              : [],
            error: msg.error != null ? String(msg.error) : null,
          });
        }
      } catch {
        /* ignore */
      }
    };
  }, []);

  useEffect(() => {
    connect();
    return () => {
      if (timerRef.current) clearTimeout(timerRef.current);
      wsRef.current?.close();
    };
  }, [connect]);

  const sendMessage = useCallback((payload: Record<string, unknown>) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(payload));
    }
  }, []);

  const requestEmaTradeDay = useCallback((date: string) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ action: "ema_trade_day", date }));
    }
  }, []);

  const clearEmaTradeDay = useCallback(() => setEmaTradeByDay(null), []);

  return { state, isConnected, sendMessage, emaTradeByDay, requestEmaTradeDay, clearEmaTradeDay };
}
