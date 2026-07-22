"use client";
import {
  Area, AreaChart, Bar, BarChart, CartesianGrid, Cell, Legend, Pie, PieChart,
  ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";

export const SERIES = ["#4F46E5", "#7C6CF0", "#3B82F6", "#7DC4FB", "#22C7C7", "#A5B4FC"];

const AXIS = { tickLine: false, axisLine: false, dy: 6 } as const;

/*
 * Animations are off across every chart. Two reasons, both practical:
 * headless/print capture never runs the rAF loop so animated paths render
 * empty, and on a live dashboard the charts re-animate on every filter change,
 * which reads as flicker rather than polish.
 */
const NO_ANIM = { isAnimationActive: false } as const;

/*
 * ResponsiveContainer normally paints nothing until its ResizeObserver fires,
 * which costs a visible empty frame on load and makes the chart miss entirely
 * in headless capture. Seeding a plausible width lets the first paint draw
 * real geometry; the observer corrects it on the next tick.
 */
const INITIAL = { width: 680, height: 210 } as const;

/** Shared tooltip so every chart in the product reads identically. */
function Tip({ active, payload, label, fmt }: any) {
  if (!active || !payload?.length) return null;
  return (
    <div className="rounded-lg border border-line bg-surface px-2.5 py-2 shadow-pop">
      {label !== undefined && (
        <p className="mb-1 text-tiny font-semibold text-ink">{label}</p>
      )}
      {payload.map((p: any) => (
        <p key={p.dataKey ?? p.name} className="flex items-center gap-1.5 text-tiny text-muted">
          <span className="size-1.5 rounded-full" style={{ background: p.color ?? p.fill }} />
          <span>{p.name}</span>
          <span className="tnum ml-auto pl-3 font-semibold text-ink">
            {fmt ? fmt(p.value) : p.value?.toLocaleString?.() ?? p.value}
          </span>
        </p>
      ))}
    </div>
  );
}

/** Trend area — the "Call Performance Overview" panel. */
export function TrendArea({
  data, x, series, height = 210, fmt,
}: {
  data: Record<string, unknown>[];
  x: string;
  series: { key: string; label: string }[];
  height?: number;
  fmt?: (v: number) => string;
}) {
  return (
    <ResponsiveContainer width="100%" height={height} debounce={0} initialDimension={INITIAL}>
      <AreaChart data={data} margin={{ top: 4, right: 4, left: 0, bottom: 0 }}>
        <defs>
          {series.map((s, i) => (
            <linearGradient key={s.key} id={`g-${s.key}`} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={SERIES[i % SERIES.length]} stopOpacity={0.28} />
              <stop offset="100%" stopColor={SERIES[i % SERIES.length]} stopOpacity={0.02} />
            </linearGradient>
          ))}
        </defs>
        <CartesianGrid strokeDasharray="3 3" vertical={false} />
        <XAxis dataKey={x} {...AXIS} />
        <YAxis
          {...AXIS}
          width={44}
          tickFormatter={(v: number) => (v >= 1000 ? `${v / 1000}k` : String(v))}
        />
        <Tooltip content={<Tip fmt={fmt} />} cursor={{ stroke: "#D9D9E3" }} />
        {series.map((s, i) => (
          <Area
            key={s.key}
            {...NO_ANIM}
            type="monotone"
            dataKey={s.key}
            name={s.label}
            stroke={SERIES[i % SERIES.length]}
            strokeWidth={2}
            fill={`url(#g-${s.key})`}
          />
        ))}
      </AreaChart>
    </ResponsiveContainer>
  );
}

/**
 * Bar chart with a single emphasised column — the "Total Subscriber" panel,
 * where Tuesday is highlighted and the rest are washed out.
 */
export function HighlightBars({
  data, x, y, height = 190, highlight,
}: {
  data: Record<string, any>[];
  x: string;
  y: string;
  height?: number;
  /** Index of the bar to emphasise. Defaults to the max value. */
  highlight?: number;
}) {
  const peak =
    highlight ?? data.reduce((best, d, i, a) => (d[y] > a[best][y] ? i : best), 0);

  return (
    <ResponsiveContainer width="100%" height={height} debounce={0} initialDimension={INITIAL}>
      <BarChart data={data} margin={{ top: 18, right: 4, left: 4, bottom: 0 }} barCategoryGap="24%">
        <XAxis dataKey={x} {...AXIS} interval={0} />
        <YAxis hide />
        <Tooltip content={<Tip />} cursor={{ fill: "transparent" }} />
        <Bar dataKey={y} name={y} radius={[6, 6, 6, 6]} {...NO_ANIM}>
          {data.map((_, i) => (
            <Cell key={i} fill={i === peak ? "#5B5BD6" : "#E9E9F5"} />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}

/** Stacked composition bars — regional / outcome breakdown by period. */
export function StackedBars({
  data, x, series, height = 210,
}: {
  data: Record<string, unknown>[];
  x: string;
  series: { key: string; label: string }[];
  height?: number;
}) {
  return (
    <ResponsiveContainer width="100%" height={height} debounce={0} initialDimension={INITIAL}>
      <BarChart data={data} margin={{ top: 4, right: 4, left: -20, bottom: 0 }} barCategoryGap="36%">
        <CartesianGrid strokeDasharray="3 3" vertical={false} />
        <XAxis dataKey={x} {...AXIS} />
        <YAxis {...AXIS} width={48} />
        <Tooltip content={<Tip />} cursor={{ fill: "rgba(0,0,0,.02)" }} />
        <Legend
          iconType="circle"
          iconSize={7}
          wrapperStyle={{ fontSize: 11, color: "#8B90A0", paddingTop: 8 }}
        />
        {series.map((s, i) => (
          <Bar
            key={s.key}
            {...NO_ANIM}
            dataKey={s.key}
            name={s.label}
            stackId="a"
            fill={SERIES[i % SERIES.length]}
            radius={i === series.length - 1 ? [5, 5, 0, 0] : 0}
            maxBarSize={38}
          />
        ))}
      </BarChart>
    </ResponsiveContainer>
  );
}

/** Donut — the "Sales Distribution" / "Call Outcomes" panel. */
export function Donut({
  data, height = 190, centerLabel, centerValue,
}: {
  data: { name: string; value: number }[];
  height?: number;
  centerLabel?: string;
  centerValue?: string;
}) {
  return (
    <div className="relative">
      <ResponsiveContainer width="100%" height={height} debounce={0} initialDimension={INITIAL}>
        <PieChart>
          <Pie
            {...NO_ANIM}
            data={data}
            dataKey="value"
            nameKey="name"
            innerRadius="62%"
            outerRadius="92%"
            paddingAngle={2}
            stroke="none"
          >
            {data.map((_, i) => (
              <Cell key={i} fill={SERIES[i % SERIES.length]} />
            ))}
          </Pie>
          <Tooltip content={<Tip />} />
        </PieChart>
      </ResponsiveContainer>
      {centerValue && (
        <div className="pointer-events-none absolute inset-0 grid place-items-center">
          <div className="text-center">
            <p className="tnum text-lg font-semibold text-ink">{centerValue}</p>
            {centerLabel && <p className="text-tiny text-muted">{centerLabel}</p>}
          </div>
        </div>
      )}
    </div>
  );
}

/** Legend row used beneath donuts and distribution splits. */
export function LegendList({
  items,
}: {
  items: { name: string; value: string; hint?: string }[];
}) {
  return (
    <ul className="space-y-2">
      {items.map((it, i) => (
        <li key={it.name} className="flex items-center gap-2 text-base">
          <span
            className="size-2 shrink-0 rounded-full"
            style={{ background: SERIES[i % SERIES.length] }}
          />
          <span className="text-muted">{it.name}</span>
          <span className="tnum ml-auto font-semibold text-ink">{it.value}</span>
        </li>
      ))}
    </ul>
  );
}
