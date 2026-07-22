"use client";
import {
  Zap, CalendarClock, Repeat, Droplets, MousePointerClick, Workflow,
  CheckCircle2, AlertTriangle,
} from "lucide-react";
import { Card } from "@/components/ui/Card";
import { Field, Input, OptionCards, Select, Toggle } from "@/components/ui/Form";
import { SectionTitle, StepSplit } from "../WizardShell";
import { Chip } from "@/components/ui/Chip";
import type { Campaign, Mode } from "@/lib/api";
import { num, usd } from "@/lib/cn";

const MODES = [
  { value: "immediate" as const, label: "Immediately", description: "Start as soon as you launch", icon: Zap },
  { value: "one_time" as const, label: "One time", description: "Run once at a set date", icon: CalendarClock },
  { value: "recurring" as const, label: "Recurring", description: "Repeat on a schedule", icon: Repeat },
  { value: "drip" as const, label: "Drip sequence", description: "Spread over days", icon: Droplets },
  { value: "behavior" as const, label: "Behaviour triggered", description: "Fires on lead activity", icon: MousePointerClick },
  { value: "workflow" as const, label: "Workflow triggered", description: "Called by an automation", icon: Workflow },
];

export function ScheduleStep({
  draft, patch, mode, leadCount, voiceName,
}: {
  draft: Partial<Campaign>;
  patch: (p: Partial<Campaign>) => void;
  mode: Mode;
  leadCount: number;
  voiceName?: string;
}) {
  const hours = draft.business_hours ?? { start: "09:00", end: "18:00" };
  const script = (draft.script ?? {}) as Record<string, string>;

  // Everything that must be true before launching. Shown as a checklist rather
  // than a single "invalid" error, so the gap is obvious.
  const checks = [
    { ok: !!draft.name?.trim(), label: "Campaign has a name" },
    { ok: !!draft.type, label: "Campaign type selected" },
    { ok: leadCount > 0, label: "Audience has reachable leads" },
    {
      ok: mode === "call" && draft.voice_type === "human" ? true : !!draft.voice_id,
      label: "Voice selected",
    },
    { ok: !!script.greeting?.trim(), label: "Greeting written" },
    { ok: !!draft.caller_number_id, label: "Caller number assigned" },
  ];
  const ready = checks.every((c) => c.ok);
  const estCost = leadCount * 2.5 * 0.065;

  return (
    <StepSplit
      aside={
        <>
          <Card>
            <SectionTitle>Pre-launch checklist</SectionTitle>
            <ul className="space-y-1.5">
              {checks.map((c) => (
                <li key={c.label} className="flex items-start gap-2 text-sm">
                  {c.ok ? (
                    <CheckCircle2 size={13} className="mt-0.5 shrink-0 text-pos" />
                  ) : (
                    <AlertTriangle size={13} className="mt-0.5 shrink-0 text-warn" />
                  )}
                  <span className={c.ok ? "text-muted" : "font-medium text-ink"}>
                    {c.label}
                  </span>
                </li>
              ))}
            </ul>
            {!ready && (
              <p className="mt-3 rounded-md bg-warn-wash px-2.5 py-2 text-tiny text-warn">
                Finish the outstanding items before launching.
              </p>
            )}
          </Card>

          <Card>
            <SectionTitle>Review</SectionTitle>
            <dl className="space-y-2 text-sm">
              {[
                ["Surface", mode === "voice" ? "Voice Outreach" : "Call Outreach"],
                ["Leads", num(leadCount)],
                ["Voice", voiceName ?? "—"],
                ["Timezone", draft.timezone ?? "UTC"],
                ["Calling hours", `${hours.start ?? "09:00"} – ${hours.end ?? "18:00"}`],
                ["Concurrency", String(draft.concurrent_calls ?? 5)],
                ["Est. cost", usd(estCost)],
                ["Est. duration", `${Math.ceil(leadCount / Math.max(draft.calls_per_minute ?? 10, 1) / 60)}h`],
              ].map(([k, v]) => (
                <div key={k} className="flex justify-between gap-3">
                  <dt className="text-muted">{k}</dt>
                  <dd className="truncate font-medium text-ink">{v}</dd>
                </div>
              ))}
            </dl>
          </Card>
        </>
      }
    >
      <SectionTitle hint="When the dialer should start working through the audience.">
        Scheduling mode
      </SectionTitle>
      <OptionCards
        value={(draft.schedule_mode ?? "immediate") as typeof MODES[number]["value"]}
        onChange={(v) => patch({ schedule_mode: v })}
        options={MODES}
        columns={3}
      />

      {draft.schedule_mode !== "immediate" && (
        <div className="mt-4 grid gap-4 sm:grid-cols-2">
          <Field label="Start date">
            <Input
              type="datetime-local"
              onChange={(e) =>
                patch({ start_date: e.target.value ? new Date(e.target.value).toISOString() : null } as Partial<Campaign>)
              }
            />
          </Field>
          <Field label="End date" hint="Leave blank to run until the audience is exhausted.">
            <Input
              type="datetime-local"
              onChange={(e) =>
                patch({ end_date: e.target.value ? new Date(e.target.value).toISOString() : null } as Partial<Campaign>)
              }
            />
          </Field>
        </div>
      )}

      {draft.schedule_mode === "recurring" && (
        <Field label="Repeat" className="mt-4 max-w-xs">
          <Select
            value={String((draft.recurrence as Record<string, string>)?.pattern ?? "weekly")}
            onChange={(e) => patch({ recurrence: { pattern: e.target.value } })}
            options={[
              { value: "daily", label: "Daily" },
              { value: "weekly", label: "Weekly" },
              { value: "monthly", label: "Monthly" },
              { value: "custom", label: "Custom pattern" },
            ]}
          />
        </Field>
      )}

      <div className="mt-5">
        <SectionTitle hint="Enforced in the campaign's timezone, not the server's.">
          Calling window
        </SectionTitle>
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Earliest call">
            <Input
              type="time"
              value={hours.start ?? "09:00"}
              onChange={(e) => patch({ business_hours: { ...hours, start: e.target.value } })}
            />
          </Field>
          <Field label="Latest call">
            <Input
              type="time"
              value={hours.end ?? "18:00"}
              onChange={(e) => patch({ business_hours: { ...hours, end: e.target.value } })}
            />
          </Field>
        </div>
        <div className="mt-1">
          <Toggle
            label="Weekdays only"
            hint="No calls on Saturday or Sunday."
            checked={draft.weekdays_only !== false}
            onChange={(v) => patch({ weekdays_only: v, weekends_only: v ? false : draft.weekends_only })}
          />
          <Toggle
            label="Weekends only"
            hint="Only Saturday and Sunday."
            checked={!!draft.weekends_only}
            onChange={(v) => patch({ weekends_only: v, weekdays_only: v ? false : draft.weekdays_only })}
          />
        </div>
        <p className="mt-2 flex items-start gap-2 rounded-md bg-info-wash px-3 py-2 text-sm text-info">
          <AlertTriangle size={13} className="mt-0.5 shrink-0" />
          Calls outside this window are skipped, not queued. A campaign in
          {" "}{draft.timezone ?? "UTC"} will pause overnight and resume in the morning.
        </p>
      </div>

      {ready && (
        <div className="mt-5 rounded-card border border-pos/30 bg-pos-wash p-4">
          <p className="flex items-center gap-2 font-semibold text-pos">
            <CheckCircle2 size={15} /> Ready to launch
          </p>
          <p className="mt-1 text-sm text-pos/80">
            {num(leadCount)} leads · {draft.concurrent_calls ?? 5} concurrent ·
            {" "}{draft.calls_per_minute ?? 10} calls/min · approx. {usd(estCost)}
          </p>
          <div className="mt-2 flex flex-wrap gap-1.5">
            <Chip tone="pos">{draft.type?.replace(/_/g, " ") ?? "campaign"}</Chip>
            <Chip tone="pos">{draft.language ?? "en"}</Chip>
            <Chip tone="pos">{draft.schedule_mode ?? "immediate"}</Chip>
          </div>
        </div>
      )}
    </StepSplit>
  );
}
