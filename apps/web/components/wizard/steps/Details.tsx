"use client";
import { Field, Input, Select, TagInput, Textarea } from "@/components/ui/Form";
import { SectionTitle, StepSplit } from "../WizardShell";
import { Card } from "@/components/ui/Card";
import type { Campaign, Mode } from "@/lib/api";

// FRD §5 — the 18 campaign types.
export const CAMPAIGN_TYPES = [
  "cold_calling", "lead_qualification", "follow_up", "demo_booking",
  "event_invitation", "renewal_reminder", "recruitment_outreach",
  "payment_reminder", "survey_campaign", "customer_success",
  "support_follow_up", "upsell_campaign", "promotional_campaign",
  "reactivation_campaign", "nps_campaign", "appointment_confirmation",
  "appointment_reminder", "webinar_outreach",
];

// FRD §5 step 3 — supported languages.
export const LANGUAGES = [
  ["en", "English"], ["es", "Spanish"], ["fr", "French"], ["de", "German"],
  ["ar", "Arabic"], ["ta", "Tamil"], ["hi", "Hindi"], ["te", "Telugu"],
  ["ml", "Malayalam"], ["ja", "Japanese"], ["zh", "Mandarin"],
  ["pt", "Portuguese"], ["it", "Italian"],
];

const TIMEZONES = [
  "UTC", "America/New_York", "America/Chicago", "America/Denver",
  "America/Los_Angeles", "Europe/London", "Europe/Berlin", "Asia/Dubai",
  "Asia/Kolkata", "Asia/Singapore", "Australia/Sydney",
];

const GOALS = [
  ["book_meeting", "Book a meeting"],
  ["qualify_lead", "Qualify lead"],
  ["follow_up", "Follow up"],
  ["collect_payment", "Payment reminder"],
  ["survey", "Survey / feedback"],
  ["reengage", "Re-engage cold lead"],
  ["confirm_verify", "Confirm / verify"],
];

const title = (s: string) =>
  s.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());

export function DetailsStep({
  draft, patch, mode, numbers,
}: {
  draft: Partial<Campaign>;
  patch: (p: Partial<Campaign>) => void;
  mode: Mode;
  numbers: { id: string; e164: string; label?: string | null }[];
}) {
  return (
    <StepSplit
      aside={
        <Card>
          <SectionTitle hint="These carry through every later step.">
            Summary
          </SectionTitle>
          <dl className="space-y-2 text-sm">
            {[
              ["Surface", mode === "voice" ? "Voice Outreach" : "Call Outreach"],
              ["Name", draft.name || "—"],
              ["Type", draft.type ? title(draft.type) : "—"],
              ["Language", LANGUAGES.find(([v]) => v === draft.language)?.[1] ?? "English"],
              ["Timezone", draft.timezone || "UTC"],
              ["Priority", draft.priority ?? "normal"],
            ].map(([k, v]) => (
              <div key={k} className="flex justify-between gap-3">
                <dt className="text-muted">{k}</dt>
                <dd className="truncate font-medium text-ink">{v}</dd>
              </div>
            ))}
          </dl>
        </Card>
      }
    >
      <SectionTitle hint="Name it something your team will recognise in reports.">
        Campaign details
      </SectionTitle>

      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="Campaign name" required className="sm:col-span-2">
          <Input
            value={draft.name ?? ""}
            onChange={(e) => patch({ name: e.target.value })}
            placeholder="e.g. SaaS Outreach — May"
          />
        </Field>

        <Field label="Description" className="sm:col-span-2">
          <Textarea
            value={draft.description ?? ""}
            onChange={(e) => patch({ description: e.target.value })}
            placeholder="What is this campaign for? Visible to your team only."
          />
        </Field>

        <Field label="Campaign type" required>
          <Select
            value={draft.type ?? ""}
            onChange={(e) => patch({ type: e.target.value })}
            options={[
              { value: "", label: "Select a type…" },
              ...CAMPAIGN_TYPES.map((t) => ({ value: t, label: title(t) })),
            ]}
          />
        </Field>

        <Field label="Campaign goal" hint="Steers what the AI drives toward on the call.">
          <Select
            value={draft.goal ?? ""}
            onChange={(e) => patch({ goal: e.target.value })}
            options={[
              { value: "", label: "Select a goal…" },
              ...GOALS.map(([v, l]) => ({ value: v, label: l })),
            ]}
          />
        </Field>

        <Field label="Language">
          <Select
            value={draft.language ?? "en"}
            onChange={(e) => patch({ language: e.target.value })}
            options={LANGUAGES.map(([v, l]) => ({ value: v, label: l }))}
          />
        </Field>

        <Field
          label="Timezone"
          required
          hint="Calling hours are enforced in this timezone, not the server's."
        >
          <Select
            value={draft.timezone ?? "UTC"}
            onChange={(e) => patch({ timezone: e.target.value })}
            options={TIMEZONES.map((t) => ({ value: t, label: t }))}
          />
        </Field>

        <Field label="Caller number" hint="The number recipients see.">
          <Select
            value={draft.caller_number_id ?? ""}
            onChange={(e) => patch({ caller_number_id: e.target.value || null })}
            options={[
              { value: "", label: numbers.length ? "Select a number…" : "No numbers configured" },
              ...numbers.map((n) => ({
                value: n.id,
                label: n.label ? `${n.e164} — ${n.label}` : n.e164,
              })),
            ]}
          />
        </Field>

        <Field label="Department">
          <Input
            value={draft.department ?? ""}
            onChange={(e) => patch({ department: e.target.value })}
            placeholder="e.g. Sales"
          />
        </Field>

        <Field label="Priority">
          <Select
            value={draft.priority ?? "normal"}
            onChange={(e) => patch({ priority: e.target.value as Campaign["priority"] })}
            options={[
              { value: "low", label: "Low" },
              { value: "normal", label: "Normal" },
              { value: "high", label: "High" },
              { value: "urgent", label: "Urgent" },
            ]}
          />
        </Field>

        <Field label="Tags" className="sm:col-span-2">
          <TagInput
            value={draft.tags ?? []}
            onChange={(tags) => patch({ tags })}
          />
        </Field>
      </div>
    </StepSplit>
  );
}
