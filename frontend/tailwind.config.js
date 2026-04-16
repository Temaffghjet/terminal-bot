/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,tsx}"],
  theme: {
    extend: {
      fontFamily: {
        mono: ["ui-monospace", "SFMono-Regular", "Menlo", "Consolas", "monospace"],
        display: ["ui-monospace", "SFMono-Regular", "Menlo", "monospace"],
      },
      colors: {
        cp: {
          void: "#050608",
          bg: "#0a0c10",
          panel: "#0f1218",
          panel2: "#141820",
          border: "#1e2533",
          line: "#2a3344",
          muted: "#6b7f94",
          dim: "#4a5568",
          yellow: "#fcee0a",
          cyan: "#00e5ff",
          magenta: "#ff2a6d",
          green: "#39ff14",
          red: "#ff3355",
          amber: "#ffb800",
        },
      },
      boxShadow: {
        "cp-glow": "0 0 20px rgba(0, 229, 255, 0.12)",
        "cp-yellow": "0 0 14px rgba(252, 238, 10, 0.25)",
        "cp-inset": "inset 0 1px 0 rgba(255,255,255,0.04)",
      },
      backgroundImage: {
        "cp-grid":
          "linear-gradient(rgba(0,229,255,0.03) 1px, transparent 1px), linear-gradient(90deg, rgba(0,229,255,0.03) 1px, transparent 1px)",
      },
      backgroundSize: {
        "cp-grid": "24px 24px",
      },
    },
  },
  plugins: [],
};
