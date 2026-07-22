"use client";
import { Search, Bell, Gift, History, ChevronDown } from "lucide-react";
import { cn } from "@/lib/cn";

export function TopBar({
  user = { name: "Alex Morgan", role: "Admin" },
  unread = 0,
}: {
  user?: { name: string; role: string };
  unread?: number;
}) {
  return (
    <header className="sticky top-0 z-20 flex h-14 items-center gap-4 border-b border-line bg-page/85 px-6 backdrop-blur">
      {/* search */}
      <label className="relative flex h-8 w-full max-w-[300px] items-center">
        <Search size={14} className="absolute left-2.5 text-faint" />
        <input
          placeholder="Search campaigns, leads, calls…"
          className={cn(
            "h-full w-full rounded-pill border border-line-strong bg-surface",
            "pl-8 pr-14 text-base text-ink placeholder:text-faint",
            "outline-none focus:border-primary/40 focus:ring-2 focus:ring-primary/15",
          )}
        />
        <kbd className="absolute right-2 rounded border border-line-strong bg-sunk px-1.5 py-0.5 text-[10px] font-medium text-faint">
          ⌘+F
        </kbd>
      </label>

      <div className="ml-auto flex items-center gap-1">
        <IconButton label="What's new"><Gift size={16} /></IconButton>
        <IconButton label="Notifications" badge={unread}><Bell size={16} /></IconButton>
        <IconButton label="Recent activity"><History size={16} /></IconButton>

        <div className="ml-2 flex items-center gap-2 border-l border-line pl-3">
          <span className="grid size-7 place-items-center rounded-full bg-gradient-to-br from-c2 to-c5 text-tiny font-semibold text-white">
            {user.name.split(" ").map((s) => s[0]).slice(0, 2).join("")}
          </span>
          <span className="leading-tight">
            <span className="block text-sm font-semibold text-ink">{user.name}</span>
            <span className="block text-tiny text-muted">{user.role}</span>
          </span>
          <ChevronDown size={13} className="text-faint" />
        </div>
      </div>
    </header>
  );
}

function IconButton({
  children,
  label,
  badge = 0,
}: {
  children: React.ReactNode;
  label: string;
  badge?: number;
}) {
  return (
    <button
      aria-label={label}
      className="relative grid size-8 place-items-center rounded-pill text-muted hover:bg-sunk hover:text-ink"
    >
      {children}
      {badge > 0 && (
        <span className="absolute right-1 top-1 grid size-3.5 place-items-center rounded-full bg-neg text-[9px] font-bold text-white">
          {badge > 9 ? "9+" : badge}
        </span>
      )}
    </button>
  );
}

/** Page title row: title left, control cluster right. */
export function PageHeader({
  title,
  subtitle,
  children,
}: {
  title: string;
  subtitle?: string;
  children?: React.ReactNode;
}) {
  return (
    <div className="mb-5 flex flex-wrap items-center justify-between gap-3">
      <div>
        <h1 className="text-xl font-semibold tracking-tight text-ink">{title}</h1>
        {subtitle && <p className="mt-0.5 text-base text-muted">{subtitle}</p>}
      </div>
      {children && <div className="flex flex-wrap items-center gap-2">{children}</div>}
    </div>
  );
}
