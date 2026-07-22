"use client";
import { cn } from "@/lib/cn";

export type Column<T> = {
  key: string;
  header: string;
  /** Cell renderer. Omit to render `row[key]` as text. */
  cell?: (row: T) => React.ReactNode;
  align?: "left" | "right" | "center";
  width?: string;
};

/**
 * The table style from the reference's "List of Integration" panel:
 * sunk uppercase header, optional checkbox column, hairline row dividers.
 */
export function DataTable<T extends { id: string }>({
  columns,
  rows,
  selectable = false,
  selected,
  onSelect,
  empty = "Nothing here yet.",
  onRowClick,
  className,
}: {
  columns: Column<T>[];
  rows: T[];
  selectable?: boolean;
  selected?: Set<string>;
  onSelect?: (next: Set<string>) => void;
  empty?: React.ReactNode;
  onRowClick?: (row: T) => void;
  className?: string;
}) {
  const allChecked = rows.length > 0 && rows.every((r) => selected?.has(r.id));

  const toggleAll = () => {
    if (!onSelect) return;
    onSelect(allChecked ? new Set() : new Set(rows.map((r) => r.id)));
  };

  const toggleOne = (id: string) => {
    if (!onSelect) return;
    const next = new Set(selected);
    next.has(id) ? next.delete(id) : next.add(id);
    onSelect(next);
  };

  return (
    <div className={cn("overflow-x-auto", className)}>
      <table className="w-full border-collapse text-base">
        <thead>
          <tr className="bg-sunk">
            {selectable && (
              <th className="w-9 rounded-l-md px-3 py-2">
                <Checkbox checked={allChecked} onChange={toggleAll} />
              </th>
            )}
            {columns.map((c, i) => (
              <th
                key={c.key}
                style={{ width: c.width }}
                className={cn(
                  "px-3 py-2 text-micro font-semibold uppercase tracking-wider text-faint",
                  c.align === "right" && "text-right",
                  c.align === "center" && "text-center",
                  !c.align && "text-left",
                  !selectable && i === 0 && "rounded-l-md",
                  i === columns.length - 1 && "rounded-r-md",
                )}
              >
                {c.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.length === 0 && (
            <tr>
              <td
                colSpan={columns.length + (selectable ? 1 : 0)}
                className="px-3 py-10 text-center text-base text-muted"
              >
                {empty}
              </td>
            </tr>
          )}
          {rows.map((row) => (
            <tr
              key={row.id}
              onClick={() => onRowClick?.(row)}
              className={cn(
                "border-b border-line last:border-0",
                onRowClick && "cursor-pointer hover:bg-sunk",
              )}
            >
              {selectable && (
                <td className="px-3 py-2.5" onClick={(e) => e.stopPropagation()}>
                  <Checkbox
                    checked={!!selected?.has(row.id)}
                    onChange={() => toggleOne(row.id)}
                  />
                </td>
              )}
              {columns.map((c) => (
                <td
                  key={c.key}
                  className={cn(
                    "px-3 py-2.5 text-ink",
                    c.align === "right" && "text-right tnum",
                    c.align === "center" && "text-center",
                  )}
                >
                  {c.cell ? c.cell(row) : String((row as never)[c.key] ?? "—")}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function Checkbox({
  checked,
  onChange,
}: {
  checked: boolean;
  onChange: () => void;
}) {
  return (
    <input
      type="checkbox"
      checked={checked}
      onChange={onChange}
      className={cn(
        "size-3.5 cursor-pointer appearance-none rounded-[4px] border border-line-strong",
        "bg-surface transition-colors checked:border-primary checked:bg-primary",
        "checked:bg-[url('data:image/svg+xml;utf8,<svg xmlns=%22http://www.w3.org/2000/svg%22 viewBox=%220 0 12 12%22><path d=%22M2.5 6.2l2.2 2.2 4.3-4.6%22 fill=%22none%22 stroke=%22white%22 stroke-width=%222%22 stroke-linecap=%22round%22 stroke-linejoin=%22round%22/></svg>')]",
        "bg-center bg-no-repeat",
      )}
    />
  );
}

/**
 * The thin rate bar in the reference's integration table.
 * Colour comes through an inline CSS var, not `bg-${tone}` — Tailwind only
 * generates classes it can see as literal strings, so a runtime-built class
 * name silently produces no colour at all.
 */
export function MiniBar({ value, tone = "var(--c1)" }: { value: number; tone?: string }) {
  const w = Math.min(100, Math.max(0, value));
  return (
    <div className="flex items-center gap-2">
      <div className="h-1 w-14 overflow-hidden rounded-full bg-line">
        <div className="h-full rounded-full" style={{ width: `${w}%`, background: tone }} />
      </div>
      <span className="tnum text-sm text-muted">{value.toFixed(1)}%</span>
    </div>
  );
}

/** Icon-tile + primary/secondary label cell, as used for app rows and lead rows. */
export function IconCell({
  icon,
  title,
  subtitle,
  tint = "bg-primary-wash text-primary-ink",
}: {
  icon: React.ReactNode;
  title: string;
  subtitle?: string;
  tint?: string;
}) {
  return (
    <div className="flex items-center gap-2.5">
      <span
        className={cn(
          "grid size-7 shrink-0 place-items-center rounded-md text-tiny font-bold",
          tint,
        )}
      >
        {icon}
      </span>
      <span className="min-w-0">
        <span className="block truncate font-medium text-ink">{title}</span>
        {subtitle && (
          <span className="block truncate text-sm text-muted">{subtitle}</span>
        )}
      </span>
    </div>
  );
}
