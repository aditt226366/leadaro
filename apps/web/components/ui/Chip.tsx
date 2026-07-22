import { ArrowUpRight, ArrowDownRight } from "lucide-react";
import { cn } from "@/lib/cn";

type Tone = "pos" | "neg" | "warn" | "info" | "neutral" | "primary";

const TONE: Record<Tone, string> = {
  pos:     "bg-pos-wash text-pos",
  neg:     "bg-neg-wash text-neg",
  warn:    "bg-warn-wash text-warn",
  info:    "bg-info-wash text-info",
  primary: "bg-primary-wash text-primary-ink",
  neutral: "bg-sunk text-muted",
};

export function Chip({
  children,
  tone = "neutral",
  className,
}: {
  children: React.ReactNode;
  tone?: Tone;
  className?: string;
}) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-md px-1.5 py-0.5 text-tiny font-semibold",
        TONE[tone],
        className,
      )}
    >
      {children}
    </span>
  );
}

/**
 * The delta chip from the reference: "15.8% ↗" green / "34.0% ↘" red.
 * Direction is derived from sign, but `goodWhenDown` flips the colour for
 * metrics where falling is good (bounce rate, cost per conversion, callback rate).
 */
export function Delta({
  value,
  goodWhenDown = false,
}: {
  value: number;
  goodWhenDown?: boolean;
}) {
  const up = value >= 0;
  const good = goodWhenDown ? !up : up;
  const Icon = up ? ArrowUpRight : ArrowDownRight;
  return (
    <Chip tone={good ? "pos" : "neg"}>
      <span className="tnum">{Math.abs(value).toFixed(1)}%</span>
      <Icon size={11} strokeWidth={2.5} />
    </Chip>
  );
}

const DOT: Record<string, string> = {
  active: "bg-pos", scheduled: "bg-info", draft: "bg-faint",
  paused: "bg-warn", completed: "bg-primary", archived: "bg-faint",
};

export function StatusChip({ status }: { status: string }) {
  return (
    <span className="inline-flex items-center gap-1.5 text-sm font-medium capitalize text-ink">
      <span className={cn("size-1.5 rounded-full", DOT[status] ?? "bg-faint")} />
      {status}
    </span>
  );
}
