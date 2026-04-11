/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_WS_PORT?: string;
  /** Полный URL WebSocket бэкенда (Vercel → VPS / туннель), напр. wss://bot.example.com/ws */
  readonly VITE_WS_URL?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
