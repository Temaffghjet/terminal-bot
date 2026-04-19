/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        okx: {
          bg: "#0b0e11",
          card: "#141720",
          border: "#2a2d36",
          accent: "#f0b90b",
          profit: "#0ecb81",
          loss: "#f6465d",
          text: "#e8e8e8",
          muted: "#848e9c",
        },
      },
      fontFamily: {
        mono: ['"IBM Plex Mono"', "ui-monospace", "monospace"],
        sans: ['"IBM Plex Sans"', "system-ui", "sans-serif"],
      },
    },
  },
  plugins: [],
};
