import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

/** 12450 → "12,450" */
export const num = (n: number) => n.toLocaleString("en-US");

/** 363.95 → "$363.95" */
export const usd = (n: number) =>
  n.toLocaleString("en-US", { style: "currency", currency: "USD" });

/** 0.158 → "15.8%" */
export const pct = (n: number, digits = 1) => `${(n * 100).toFixed(digits)}%`;

/** 143 → "2:23" */
export const dur = (sec: number) =>
  `${Math.floor(sec / 60)}:${String(Math.round(sec % 60)).padStart(2, "0")}`;
