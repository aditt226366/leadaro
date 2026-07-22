"use client";
import { Check, ChevronLeft, ChevronRight, Loader2, Rocket } from "lucide-react";
import { cn } from "@/lib/cn";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";

export type Step = { key: string; label: string };

/**
 * Six-step wizard chrome. Steps come from the caller because the two modes
 * differ: Call Outreach has a conversation-flow step that Voice Outreach
 * doesn't. Everything else is shared.
 */
export function WizardShell({
  steps, current, onStep, onBack, onNext, onLaunch,
  saving, canAdvance = true, error, children,
}: {
  steps: Step[];
  current: number;
  onStep: (i: number) => void;
  onBack: () => void;
  onNext: () => void;
  onLaunch: () => void;
  saving?: boolean;
  canAdvance?: boolean;
  error?: string;
  children: React.ReactNode;
}) {
  const last = current === steps.length - 1;

  return (
    <Card pad={false} className="overflow-hidden">
      {/* step rail */}
      <ol className="flex items-center gap-1 overflow-x-auto border-b border-line bg-sunk px-card py-3">
        {steps.map((s, i) => {
          const done = i < current;
          const active = i === current;
          return (
            <li key={s.key} className="flex shrink-0 items-center">
              <button
                type="button"
                // Only backwards — jumping ahead would skip required fields.
                onClick={() => i < current && onStep(i)}
                disabled={i > current}
                className={cn(
                  "flex items-center gap-2 rounded-pill px-2.5 py-1.5 text-sm transition-colors",
                  active && "bg-surface font-semibold text-primary-ink shadow-card",
                  done && "text-ink hover:bg-surface",
                  i > current && "cursor-default text-faint",
                )}
              >
                <span
                  className={cn(
                    "grid size-[18px] place-items-center rounded-full text-[10px] font-bold",
                    active && "bg-primary text-white",
                    done && "bg-pos text-white",
                    i > current && "border border-line-strong text-faint",
                  )}
                >
                  {done ? <Check size={11} strokeWidth={3} /> : i + 1}
                </span>
                {s.label}
              </button>
              {i < steps.length - 1 && (
                <ChevronRight size={13} className="mx-0.5 text-faint" />
              )}
            </li>
          );
        })}
      </ol>

      <div className="p-card">{children}</div>

      {error && (
        <p className="mx-card mb-3 rounded-md bg-neg-wash px-3 py-2 text-sm text-neg">
          {error}
        </p>
      )}

      <div className="flex items-center justify-between border-t border-line bg-sunk px-card py-3">
        <Button onClick={onBack} disabled={current === 0 || saving}>
          <ChevronLeft size={13} /> Back
        </Button>

        <span className="text-sm text-muted">
          {saving ? "Saving…" : `Step ${current + 1} of ${steps.length}`}
        </span>

        {last ? (
          <Button variant="primary" size="md" onClick={onLaunch} disabled={saving}>
            {saving ? <Loader2 size={14} className="animate-spin" /> : <Rocket size={14} />}
            Launch Campaign
          </Button>
        ) : (
          <Button variant="primary" onClick={onNext} disabled={saving || !canAdvance}>
            Next <ChevronRight size={13} />
          </Button>
        )}
      </div>
    </Card>
  );
}

/** Two-column layout used inside most steps: form left, live preview right. */
export function StepSplit({
  children, aside,
}: {
  children: React.ReactNode;
  aside: React.ReactNode;
}) {
  return (
    <div className="grid gap-card lg:grid-cols-[1fr_300px]">
      <div className="min-w-0 space-y-4">{children}</div>
      <aside className="space-y-3">{aside}</aside>
    </div>
  );
}

export function SectionTitle({ children, hint }: { children: React.ReactNode; hint?: string }) {
  return (
    <div className="mb-3">
      <h3 className="text-base font-semibold text-ink">{children}</h3>
      {hint && <p className="mt-0.5 text-sm text-muted">{hint}</p>}
    </div>
  );
}
