import type { Config } from "tailwindcss";

export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        base: {
          950: "#0a0a0c",
          900: "#111114",
          850: "#16161a",
          800: "#1c1c21",
          700: "#26262c",
          600: "#3a3a42",
          400: "#8a8a93",
          200: "#d4d4d8",
          50: "#f5f5f7"
        },
        accent: {
          DEFAULT: "#0a84ff",
          soft: "#0a84ff33"
        },
        risk: {
          low: "#30d158",
          mid: "#ffd60a",
          high: "#ff453a"
        }
      },
      fontFamily: {
        sans: [
          "-apple-system",
          "BlinkMacSystemFont",
          "SF Pro Text",
          "Inter",
          "system-ui",
          "sans-serif"
        ]
      },
      borderRadius: {
        xl2: "1.25rem"
      },
      boxShadow: {
        panel: "0 1px 0 0 rgba(255,255,255,0.04) inset, 0 8px 24px -8px rgba(0,0,0,0.5)"
      },
      backdropBlur: {
        xs: "2px"
      }
    }
  },
  plugins: []
} satisfies Config;
