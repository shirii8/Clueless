import type { Config } from "tailwindcss";

const token = (name: string) => `rgb(var(--${name}) / <alpha-value>)`;

const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        page: token("page"), surface: token("surface"), subtle: token("subtle"), line: token("line"),
        ink: token("ink"), muted: token("muted"),
        brand: token("brand"), "brand-strong": token("brand-strong"), "brand-soft": token("brand-soft"),
        good: token("good"), "good-soft": token("good-soft"),
        warn: token("warn"), "warn-soft": token("warn-soft"),
        bad: token("bad"), "bad-soft": token("bad-soft"),
      },
    },
  },
  plugins: [],
};

export default config;
