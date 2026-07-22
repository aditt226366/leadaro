"use client";
import { cn } from "@/lib/cn";

export function Field({
  label, hint, required, children, className,
}: {
  label: string;
  hint?: string;
  required?: boolean;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <label className={cn("block", className)}>
      <span className="flex items-center gap-1 text-sm font-medium text-ink">
        {label}
        {required && <span className="text-neg">*</span>}
      </span>
      <div className="mt-1">{children}</div>
      {hint && <p className="mt-1 text-tiny text-muted">{hint}</p>}
    </label>
  );
}

const INPUT =
  "h-9 w-full rounded-pill border border-line-strong bg-surface px-3 text-base " +
  "text-ink placeholder:text-faint outline-none transition-colors " +
  "focus:border-primary/40 focus:ring-2 focus:ring-primary/15 " +
  "disabled:bg-sunk disabled:text-muted";

export function Input(props: React.InputHTMLAttributes<HTMLInputElement>) {
  return <input {...props} className={cn(INPUT, props.className)} />;
}

export function Textarea(props: React.TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return (
    <textarea
      {...props}
      className={cn(INPUT, "h-auto min-h-[84px] resize-y py-2 leading-relaxed", props.className)}
    />
  );
}

export function Select({
  options, ...rest
}: React.SelectHTMLAttributes<HTMLSelectElement> & {
  options: { value: string; label: string }[];
}) {
  return (
    <div className="relative">
      <select {...rest} className={cn(INPUT, "cursor-pointer appearance-none pr-8", rest.className)}>
        {options.map((o) => (
          <option key={o.value} value={o.value}>{o.label}</option>
        ))}
      </select>
      <svg
        className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-muted"
        width="10" height="10" viewBox="0 0 10 10" fill="none"
      >
        <path d="M2 4l3 3 3-3" stroke="currentColor" strokeWidth="1.6"
              strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    </div>
  );
}

/** Card-style radio group — the wizard's channel / voice-type / source pickers. */
export function OptionCards<T extends string>({
  value, onChange, options, columns = 3,
}: {
  value: T;
  onChange: (v: T) => void;
  options: {
    value: T;
    label: string;
    description?: string;
    icon?: React.ComponentType<{ size?: number; strokeWidth?: number }>;
    disabled?: boolean;
  }[];
  columns?: number;
}) {
  return (
    <div
      className="grid gap-2.5"
      style={{ gridTemplateColumns: `repeat(${columns}, minmax(0,1fr))` }}
    >
      {options.map((o) => {
        const active = o.value === value;
        return (
          <button
            key={o.value}
            type="button"
            disabled={o.disabled}
            onClick={() => onChange(o.value)}
            aria-pressed={active}
            className={cn(
              "rounded-card border p-3 text-left transition-colors",
              active
                ? "border-primary bg-primary-wash"
                : "border-line-strong bg-surface hover:border-primary/40 hover:bg-sunk",
              o.disabled && "cursor-not-allowed opacity-45 hover:border-line-strong hover:bg-surface",
            )}
          >
            <span className="flex items-center gap-2">
              {o.icon && (
                <o.icon size={15} strokeWidth={active ? 2.4 : 2} />
              )}
              <span className={cn("text-base font-semibold",
                                  active ? "text-primary-ink" : "text-ink")}>
                {o.label}
              </span>
            </span>
            {o.description && (
              <span className="mt-1 block text-sm leading-snug text-muted">
                {o.description}
              </span>
            )}
          </button>
        );
      })}
    </div>
  );
}

export function Toggle({
  checked, onChange, label, hint,
}: {
  checked: boolean;
  onChange: (v: boolean) => void;
  label: string;
  hint?: string;
}) {
  return (
    <div className="flex items-start justify-between gap-4 py-2">
      <span className="min-w-0">
        <span className="block text-base font-medium text-ink">{label}</span>
        {hint && <span className="mt-0.5 block text-sm text-muted">{hint}</span>}
      </span>
      <button
        type="button"
        role="switch"
        aria-checked={checked}
        aria-label={label}
        onClick={() => onChange(!checked)}
        className={cn(
          "relative mt-0.5 h-5 w-9 shrink-0 rounded-full transition-colors",
          checked ? "bg-primary" : "bg-line-strong",
        )}
      >
        <span
          className={cn(
            "absolute top-0.5 size-4 rounded-full bg-white shadow transition-all",
            checked ? "left-[18px]" : "left-0.5",
          )}
        />
      </button>
    </div>
  );
}

export function TagInput({
  value, onChange, placeholder = "Add a tag and press Enter",
}: {
  value: string[];
  onChange: (v: string[]) => void;
  placeholder?: string;
}) {
  return (
    <div className="flex min-h-9 flex-wrap items-center gap-1.5 rounded-pill border border-line-strong bg-surface px-2 py-1">
      {value.map((t) => (
        <span
          key={t}
          className="inline-flex items-center gap-1 rounded-md bg-primary-wash px-1.5 py-0.5 text-tiny font-medium text-primary-ink"
        >
          {t}
          <button
            type="button"
            onClick={() => onChange(value.filter((x) => x !== t))}
            aria-label={`Remove ${t}`}
            className="text-primary-ink/60 hover:text-primary-ink"
          >
            ×
          </button>
        </span>
      ))}
      <input
        placeholder={value.length ? "" : placeholder}
        onKeyDown={(e) => {
          const t = e.currentTarget.value.trim();
          if (e.key === "Enter" && t) {
            e.preventDefault();
            if (!value.includes(t)) onChange([...value, t]);
            e.currentTarget.value = "";
          }
          if (e.key === "Backspace" && !e.currentTarget.value && value.length) {
            onChange(value.slice(0, -1));
          }
        }}
        className="min-w-[120px] flex-1 bg-transparent px-1 text-base outline-none placeholder:text-faint"
      />
    </div>
  );
}
