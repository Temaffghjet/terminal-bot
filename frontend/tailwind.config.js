/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,tsx}"],
  theme: {
    extend: {
      fontFamily: {
        sans: ["Inter", "system-ui", "-apple-system", "Segoe UI", "Roboto", "sans-serif"],
        mono: ["JetBrains Mono", "ui-monospace", "SFMono-Regular", "Menlo", "monospace"],
      },
      colors: {
        ex: {
          bg: "#0d0d0d",
          surface: "#161616",
          surface2: "#1c1c1c",
          raised: "#222222",
          border: "#2b2b2b",
          line: "#3e3e42",
          text: "#eaecef",
          muted: "#848e9c",
          dim: "#5e6673",
          up: "#00b897",
          down: "#f6465d",
          warn: "#f0b90b",
          accent: "#3861fb",
        },
      },
      boxShadow: {
        ex: "0 1px 0 rgba(255,255,255,0.04) inset",
      },
    },
  },
  plugins: [],
};
