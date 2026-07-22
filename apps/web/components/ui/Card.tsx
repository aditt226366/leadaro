import { Info } from "lucide-react";
import { cn } from "@/lib/cn";
import { Delta } from "./Chip";

/** Base surface. Every panel on every screen is this. */
export function Card({
  children,
  className,
  pad = true,
}: {
  children: React.ReactNode;
  className?: string;
  pad?: boolean;
}) {
  return (
    <div
      className={cn(
        "rounded-card border border-line bg-surface shadow-card",
        pad && "p-card",
        className,
      )}
    >
      {children}
    </div>
  );
}

/**
 * KPI tile — the three cards across the top of the reference dashboard.
 * icon + label on the left, info affordance on the right, big figure, delta chip.
 */
export function StatCard({
  icon: Icon,
  label,
  value,
  delta,
  goodWhenDown,
  hint,
  className,
}: {
  icon: React.ComponentType<{ size?: number; strokeWidth?: number; className?: string }>;
  label: string;
  value: string;
  delta?: number;
  goodWhenDown?: boolean;
  hint?: string;
  className?: string;
}) {
  return (
    <Card className={className}>
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2 text-muted">
          <Icon size={15} strokeWidth={2} />
          <span className="text-base font-medium">{label}</span>
        </div>
        {hint && <Info size={14} className="text-faint" aria-label={hint} />}
      </div>
      <div className="mt-3 flex items-baseline gap-2.5">
        <span className="tnum text-stat font-semibold text-ink">{value}</span>
        {delta !== undefined && <Delta value={delta} goodWhenDown={goodWhenDown} />}
      </div>
    </Card>
  );
}

/**
 * Chart panel — title row with optional right-hand controls, then the chart.
 * `lead` renders the big figure + delta + caption block seen in Sales Overview.
 */
export function ChartCard({
  title,
  icon: Icon,
  actions,
  lead,
  children,
  className,
}: {
  title: string;
  icon?: React.ComponentType<{ size?: number; strokeWidth?: number; className?: string }>;
  actions?: React.ReactNode;
  lead?: { value: string; delta?: number; caption?: string };
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <Card className={cn("flex flex-col", className)}>
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          {Icon && <Icon size={15} strokeWidth={2} className="text-muted" />}
          <h3 className="text-base font-semibold text-ink">{title}</h3>
        </div>
        {actions && <div className="flex items-center gap-1.5">{actions}</div>}
      </div>

      {lead && (
        <div className="mt-3">
          <div className="flex items-center gap-2.5">
            <span className="tnum text-stat font-semibold text-ink">{lead.value}</span>
            {lead.delta !== undefined && <Delta value={lead.delta} />}
          </div>
          {lead.caption && (
            <p className="mt-1 text-sm text-muted">{lead.caption}</p>
          )}
        </div>
      )}

      <div className="mt-4 flex-1">{children}</div>
    </Card>
  );
}
