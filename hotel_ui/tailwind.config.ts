import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        brand: {
          red: "#E62020",
          orange: "#F7941D",
        },
        cream: {
          DEFAULT: "#FFF8EE",
          light: "#FFFDF8",
          warm: "#FFE4A8",
        },
        tier: {
          platinum: "#8B6914",
          gold: "#B8860B",
          silver: "#708090",
        },
      },
      fontFamily: {
        sans: ["Inter", "system-ui", "sans-serif"],
      },
    },
  },
  plugins: [],
};

export default config;
