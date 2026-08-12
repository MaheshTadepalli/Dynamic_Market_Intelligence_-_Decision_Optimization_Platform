import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./src/pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/components/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        ink: {
          50: "#f3f6f8",
          100: "#e4ebf0",
          200: "#c7d5e0",
          300: "#9ab3c6",
          400: "#6a8aa4",
          500: "#4d6f8c",
          600: "#3c5872",
          700: "#32485d",
          800: "#2c3d4f",
          900: "#1a2633",
          950: "#0f1720",
        },
        signal: {
          up: "#0f8a5f",
          down: "#c43c3c",
          warn: "#c9851a",
          accent: "#1f7a6c",
        },
      },
      fontFamily: {
        display: ["var(--font-display)", "serif"],
        sans: ["var(--font-sans)", "sans-serif"],
        mono: ["var(--font-mono)", "monospace"],
      },
      boxShadow: {
        panel: "0 1px 0 rgba(26,38,51,0.06), 0 18px 40px rgba(15,23,32,0.08)",
      },
      backgroundImage: {
        mesh: "radial-gradient(ellipse at 20% 0%, rgba(31,122,108,0.12), transparent 50%), radial-gradient(ellipse at 90% 10%, rgba(201,133,26,0.10), transparent 45%), linear-gradient(180deg, #f3f6f8 0%, #e8eef3 100%)",
      },
    },
  },
  plugins: [],
};

export default config;
