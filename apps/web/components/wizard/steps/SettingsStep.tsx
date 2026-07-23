"use client";
import { Card } from "@/components/ui/Card";
import { Field, Input, Select, Toggle } from "@/components/ui/Form";
import { SectionTitle, StepSplit } from "../WizardShell";
import type { Campaign } from "@/lib/api";

export function SettingsStep({
  draft, patch,
}: {
  draft: Partial<Campaign>;
  patch: (p: Partial<Campaign>) => void;
}) {
  const s = (draft.settings ?? {}) as Record<string, string | number | boolean>;
  const c = (draft.compliance ?? {}) as Record<string, boolean>;
  const setS = (p: Record<string, unknown>) => patch({ settings: { ...s, ...p } });
  const setC = (p: Record<string, unknown>) => patch({ compliance: { ...c, ...p } });

  return (
    <StepSplit
      aside={
        <Card>
          <SectionTitle hint="Enforced before the dial, not in the UI.">
            Compliance
          </SectionTitle>
          <Toggle
            label="Check DND list"
            hint="Blocks numbers on the national registry."
            checked={c.dnd_check !== false}
            onChange={(v) => setC({ dnd_check: v })}
          />
          <Toggle
            label="Require consent"
            hint="Only call leads with recorded consent."
            checked={!!c.consent}
            onChange={(v) => setC({ consent: v })}
          />
          <Toggle
            label="TCPA"
            hint="US calling-hours and disclosure rules."
            checked={c.tcpa !== false}
            onChange={(v) => setC({ tcpa: v })}
          />
          <Toggle
            label="GDPR"
            hint="EU data handling and retention."
            checked={!!c.gdpr}
            onChange={(v) => setC({ gdpr: v })}
          />
          <Toggle
            label="CCPA"
            hint="California consumer privacy."
            checked={!!c.ccpa}
            onChange={(v) => setC({ ccpa: v })}
          />
          <Toggle
            label="Recording notice"
            hint="Announces recording at call start."
            checked={c.recording_notice !== false}
            onChange={(v) => setC({ recording_notice: v })}
          />
          <p className="mt-2 border-t border-line pt-2 text-tiny leading-snug text-muted">
            Suppressed numbers are re-checked at dial time, so a lead that goes
            DNC after import is still blocked.
          </p>
        </Card>
      }
    >
      <SectionTitle hint="How the dialer behaves when a call doesn't connect.">
        Call handling
      </SectionTitle>
      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="Retry attempts" hint="Before marking the lead unreachable.">
          <Select
            value={String(s.retry_attempts ?? 3)}
            onChange={(e) => setS({ retry_attempts: Number(e.target.value) })}
            options={[0, 1, 2, 3, 4, 5].map((n) => ({
              value: String(n), label: n === 0 ? "No retries" : `${n} attempt${n > 1 ? "s" : ""}`,
            }))}
          />
        </Field>
        <Field label="Retry delay" hint="Wait before trying the same lead again.">
          <Select
            value={String(s.retry_delay_minutes ?? 60)}
            onChange={(e) => setS({ retry_delay_minutes: Number(e.target.value) })}
            options={[
              { value: "30", label: "30 minutes" },
              { value: "60", label: "1 hour" },
              { value: "240", label: "4 hours" },
              { value: "1440", label: "1 day" },
              { value: "2880", label: "2 days" },
            ]}
          />
        </Field>
        {/* No call-duration cap: a call runs as long as the conversation needs
            — until the script completes (closing + thank you), the customer
            ends it, opt-out, or a real end condition fires. There is no
            backend timer, so this control was removed rather than left to
            imply one. */}
        <Field
          label="Endpointing delay"
          hint="Silence before the AI assumes the caller finished. Lower feels snappier but cuts people off."
        >
          <Select
            value={String(s.min_endpointing_delay ?? 0.4)}
            onChange={(e) => setS({ min_endpointing_delay: Number(e.target.value) })}
            options={[
              { value: "0.2", label: "0.2s — very fast" },
              { value: "0.4", label: "0.4s — balanced" },
              { value: "0.7", label: "0.7s — patient" },
              { value: "1.0", label: "1.0s — very patient" },
            ]}
          />
        </Field>
      </div>

      <div className="mt-5">
        <SectionTitle>Recording &amp; monitoring</SectionTitle>
        <Card pad={false} className="divide-y divide-line">
          <div className="px-card py-1">
            <Toggle
              label="Voicemail detection"
              hint="Detects a machine and leaves the voicemail message instead of pitching."
              checked={s.voicemail_detection !== false}
              onChange={(v) => setS({ voicemail_detection: v })}
            />
          </div>
          <div className="px-card py-1">
            <Toggle
              label="Leave AI voicemail"
              hint="Plays your voicemail script when a machine answers."
              checked={s.leave_voicemail !== false}
              onChange={(v) => setS({ leave_voicemail: v })}
            />
          </div>
          <div className="px-card py-1">
            <Toggle
              label="Record calls"
              hint="Stores audio for review and compliance."
              checked={s.recording !== false}
              onChange={(v) => setS({ recording: v })}
            />
          </div>
          <div className="px-card py-1">
            <Toggle
              label="Live monitoring"
              hint="Lets managers listen in from the Live Monitor screen."
              checked={!!s.monitoring}
              onChange={(v) => setS({ monitoring: v })}
            />
          </div>
          <div className="px-card py-1">
            <Toggle
              label="Call whisper"
              hint="Briefs the human agent before a transferred call connects."
              checked={!!s.whisper}
              onChange={(v) => setS({ whisper: v })}
            />
          </div>
          <div className="px-card py-1">
            <Toggle
              label="Live transfer"
              hint="Allows the AI to hand the call to a human mid-conversation."
              checked={s.live_transfer !== false}
              onChange={(v) => setS({ live_transfer: v })}
            />
          </div>
        </Card>
      </div>

      <div className="mt-5">
        <SectionTitle hint="Protects your number's reputation and stays within carrier limits.">
          Throughput
        </SectionTitle>
        <div className="grid gap-4 sm:grid-cols-3">
          <Field label="Concurrent calls">
            <Input
              type="number"
              min={1}
              max={100}
              value={draft.concurrent_calls ?? 5}
              onChange={(e) => patch({ concurrent_calls: Number(e.target.value) })}
            />
          </Field>
          <Field label="Calls per minute">
            <Input
              type="number"
              min={1}
              max={120}
              value={draft.calls_per_minute ?? 10}
              onChange={(e) => patch({ calls_per_minute: Number(e.target.value) })}
            />
          </Field>
          <Field label="Max calls per day" hint="Blank for no cap.">
            <Input
              type="number"
              min={1}
              value={draft.max_daily_calls ?? ""}
              onChange={(e) =>
                patch({ max_daily_calls: e.target.value ? Number(e.target.value) : null })
              }
              placeholder="No limit"
            />
          </Field>
        </div>
        <div className="mt-1">
          <Toggle
            label="Warm-up mode"
            hint="Ramps volume gradually on a new number. Runs at a quarter of your concurrency."
            checked={!!draft.warmup_mode}
            onChange={(v) => patch({ warmup_mode: v })}
          />
        </div>
      </div>
    </StepSplit>
  );
}
