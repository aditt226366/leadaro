import type { Config } from "tailwindcss";

// Mirrors app/globals.css. Tokens live in CSS so they can be themed at runtime;
// this file only exposes them to Tailwind's utility generator.
const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}", "./lib/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        page: "var(--page)",
        surface: "var(--surface)",
        sunk: "var(--surface-sunk)",
        line: "var(--border)",
        "line-strong": "var(--border-strong)",
        ink: "var(--text)",
        muted: "var(--text-muted)",
        faint: "var(--text-faint)",
        primary: "var(--primary)",
        "primary-ink": "var(--primary-ink)",
        "primary-wash": "var(--primary-wash)",
        "primary-deep": "var(--primary-deep)",
        c1: "var(--c1)", c2: "var(--c2)", c3: "var(--c3)",
        c4: "var(--c4)", c5: "var(--c5)", c6: "var(--c6)",
        pos: "var(--pos)", "pos-wash": "var(--pos-wash)",
        neg: "var(--neg)", "neg-wash": "var(--neg-wash)",
        warn: "var(--warn)", "warn-wash": "var(--warn-wash)",
        info: "var(--info)", "info-wash": "var(--info-wash)",
      },
      borderRadius: { card: "var(--r-card)", pill: "var(--r-pill)" },
      spacing: { card: "var(--pad-card)", sidebar: "var(--sidebar)" },
      fontSize: {
        // The reference runs small and tight. These are the only sizes used.
        micro: ["10px", { lineHeight: "14px", letterSpacing: "0.06em" }],
        tiny:  ["11px", { lineHeight: "16px" }],
        sm:    ["12px", { lineHeight: "18px" }],
        base:  ["13px", { lineHeight: "20px" }],
        md:    ["14px", { lineHeight: "21px" }],
        lg:    ["16px", { lineHeight: "24px" }],
        xl:    ["20px", { lineHeight: "28px" }],
        stat:  ["26px", { lineHeight: "32px", letterSpacing: "-0.02em" }],
        hero:  ["30px", { lineHeight: "36px", letterSpacing: "-0.02em" }],
      },
      boxShadow: {
        // Hairline, not the default Tailwind drop shadow — that reads as generated.
        card: "0 1px 2px 0 rgb(16 24 40 / 0.03)",
        pop: "0 8px 24px -6px rgb(16 24 40 / 0.10), 0 2px 6px -2px rgb(16 24 40 / 0.05)",
      },
    },
  },
  plugins: [],
};
export default config;
