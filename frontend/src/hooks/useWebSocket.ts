import { useCallback, useEffect, useRef, useState } from "react";

export type BotState = Record<string, unknown> | null;

/** Полный URL WebSocket (для Vercel / удалённого бэкенда), например wss://api.example.com/ws */
const WS_URL =
  import.meta.env.VITE_WS_URL?.trim() ||
  `ws://localhost:${import.meta.env.VITE_WS_PORT ?? "8765"}`;

export function useWebSocket() {
  const [state, setState] = useState<BotState>(null);
  const [isConnected, setIsConnected] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);
  const backoffRef = useRef(1000);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const connect = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) return;
    const ws = new WebSocket(WS_URL);
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

  return { state, isConnected, sendMessage };
}
