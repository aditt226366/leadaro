"use client";
import { cn } from "@/lib/cn";

type Variant = "primary" | "ghost" | "outline" | "danger";
type Size = "sm" | "md";

const V: Record<Variant, string> = {
  primary: "bg-primary text-white hover:bg-primary-deep",
  outline: "border border-line-strong bg-surface text-ink hover:bg-sunk",
  ghost:   "text-muted hover:bg-sunk hover:text-ink",
  danger:  "bg-neg text-white hover:brightness-95",
};
const S: Record<Size, string> = {
  sm: "h-7 gap-1.5 px-2.5 text-sm",
  md: "h-9 gap-2 px-3.5 text-base",
};

export function Button({
  variant = "outline",
  size = "sm",
  className,
  ...rest
}: React.ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: Variant;
  size?: Size;
}) {
  return (
    <button
      className={cn(
        "inline-flex items-center justify-center rounded-pill font-medium",
        "transition-colors disabled:pointer-events-none disabled:opacity-45",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/30",
        V[variant],
        S[size],
        className,
      )}
      {...rest}
    />
  );
}

/** Bordered pill used for the date-range and period controls in the page header. */
export function PillSelect({
  value,
  onChange,
  options,
  icon: Icon,
  className,
}: {
  value: string;
  onChange: (v: string) => void;
  options: { value: string; label: string }[];
  icon?: React.ComponentType<{ size?: number; className?: string }>;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "relative inline-flex h-7 items-center gap-1.5 rounded-pill",
        "border border-line-strong bg-surface pl-2.5 pr-1.5 text-sm text-ink",
        className,
      )}
    >
      {Icon && <Icon size={13} className="text-muted" />}
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="cursor-pointer appearance-none bg-transparent pr-4 font-medium outline-none"
      >
        {options.map((o) => (
          <option key={o.value} value={o.value}>{o.label}</option>
        ))}
      </select>
      <svg
        className="pointer-events-none absolute right-2 text-muted"
        width="9" height="9" viewBox="0 0 10 10" fill="none"
      >
        <path d="M2 4l3 3 3-3" stroke="currentColor" strokeWidth="1.6"
              strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    </div>
  );
}
