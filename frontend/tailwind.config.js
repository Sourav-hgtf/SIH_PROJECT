/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        canvas: "#fafaf9",
        border: "#e8e6e5",
        muted: "#d6d3d1",
        ash: "#a8a29e",
        warm: "#78716c",
        ink: "#0c0a09",
        soot: "#1c1917",
        cyan: {
          DEFAULT: "#3ba6f1",
          edge: "#3398e1",
          wash: "#c1e1f7",
        },
        risk: {
          critical: "#dc2626",
          "critical-wash": "#fee2e2",
          medium: "#d97706",
          "medium-wash": "#fef3c7",
          low: "#16a34a",
          "low-wash": "#dcfce7",
        },
      },
      fontFamily: {
        sans: ["Inter", "system-ui", "-apple-system", "Segoe UI", "Roboto", "sans-serif"],
      },
      boxShadow: {
        card: "rgba(0,0,0,0.05) 0px 4px 16px 0px",
        row: "rgba(0,0,0,0.04) 0px 1px 4px 0px",
      },
    },
  },
  plugins: [],
};
