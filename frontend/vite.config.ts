import path from "node:path";
import { fileURLToPath } from "node:url";

import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Каталог с index.html — не зависит от cwd; защита от случайного `vite build —` (тире «—» вместо «.»).
const frontendRoot = path.dirname(fileURLToPath(import.meta.url));

export default defineConfig({
  root: frontendRoot,
  plugins: [react()],
  server: { port: 5173 },
});
