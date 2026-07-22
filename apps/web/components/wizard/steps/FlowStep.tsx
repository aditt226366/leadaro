"use client";
import { useState } from "react";
import {
  PhoneCall, MessageSquare, GitBranch, CalendarCheck, PhoneForwarded,
  Clock, Voicemail, XCircle, ArrowDown, Info,
} from "lucide-react";
import { Card } from "@/components/ui/Card";
import { Field, Select, Textarea } from "@/components/ui/Form";
import { SectionTitle, StepSplit } from "../WizardShell";
import { Chip } from "@/components/ui/Chip";
import type { Campaign } from "@/lib/api";
import { cn } from "@/lib/cn";

/**
 * Conversation flow (Call Outreach only).
 *
 * This edits the *branch outcomes* — what happens after each decision — rather
 * than being a free-form node canvas. The AI already decides what to say turn
 * by turn; a drag-and-drop graph would imply a scripted tree it doesn't
 * actually follow. What genuinely needs configuring is where each branch ends up.
 */

const BRANCHES = [
  { key: "interested", label: "Interested", icon: CalendarCheck, tone: "pos" as const,
    hint: "Caller is engaged and wants to proceed." },
  { key: "not_interested", label: "Not interested", icon: XCircle, tone: "neg" as const,
    hint: "Caller declined." },
  { key: "more_info", label: "Needs more information", icon: MessageSquare, tone: "info" as const,
    hint: "Caller has questions before deciding." },
  { key: "call_later", label: "Call back later", icon: Clock, tone: "warn" as const,
    hint: "Caller asked to be reached another time." },
  { key: "busy", label: "Busy", icon: Clock, tone: "warn" as const,
    hint: "Caller can't talk right now." },
  { key: "voicemail", label: "Voicemail", icon: Voicemail, tone: "neutral" as const,
    hint: "A machine answered." },
  { key: "wrong_number", label: "Wrong number", icon: XCircle, tone: "neg" as const,
    hint: "This isn't the right person." },
  { key: "speak_to_human", label: "Asked for a human", icon: PhoneForwarded, tone: "primary" as const,
    hint: "Caller explicitly wants a person." },
];

const ACTIONS = [
  { value: "book_meeting", label: "Book a meeting" },
  { value: "transfer_human", label: "Transfer to a human" },
  { value: "schedule_callback", label: "Schedule a callback" },
  { value: "send_followup", label: "Send follow-up (email/SMS)" },
  { value: "leave_voicemail", label: "Leave voicemail" },
  { value: "mark_invalid", label: "Mark number invalid" },
  { value: "suppress", label: "Add to suppression list" },
  { value: "end_call", label: "End the call politely" },
  { value: "continue", label: "Keep talking" },
];

const DEFAULTS: Record<string, string> = {
  interested: "book_meeting",
  not_interested: "end_call",
  more_info: "continue",
  call_later: "schedule_callback",
  busy: "schedule_callback",
  voicemail: "leave_voicemail",
  wrong_number: "mark_invalid",
  speak_to_human: "transfer_human",
};

export function FlowStep({
  draft, patch,
}: {
  draft: Partial<Campaign>;
  patch: (p: Partial<Campaign>) => void;
}) {
  const flow = (draft.flow ?? {}) as Record<string, { action?: string; note?: string }>;
  const [open, setOpen] = useState<string | null>("interested");

  const set = (key: string, v: { action?: string; note?: string }) =>
    patch({ flow: { ...flow, [key]: { ...flow[key], ...v } } });

  return (
    <StepSplit
      aside={
        <Card>
          <SectionTitle>Call spine</SectionTitle>
          <ol className="space-y-1 text-sm">
            {["Start call", "Greeting + AI disclosure", "Qualify", "Interest question",
              "Decision", "Branch action", "Close"].map((s, i, a) => (
              <li key={s}>
                <span className="flex items-center gap-2">
                  <span className="grid size-[18px] place-items-center rounded-full bg-primary-wash text-[10px] font-bold text-primary-ink">
                    {i + 1}
                  </span>
                  <span className="text-ink">{s}</span>
                </span>
                {i < a.length - 1 && (
                  <ArrowDown size={11} className="ml-[8px] my-0.5 text-faint" />
                )}
              </li>
            ))}
          </ol>
          <p className="mt-3 flex items-start gap-1.5 border-t border-line pt-3 text-tiny leading-snug text-muted">
            <Info size={12} className="mt-0.5 shrink-0" />
            The AI decides wording turn by turn. You're configuring where each
            branch <em>ends</em>, not the exact words.
          </p>
        </Card>
      }
    >
      <SectionTitle hint="What should happen when the AI detects each outcome.">
        Decision branches
      </SectionTitle>

      <div className="space-y-2">
        {BRANCHES.map((b) => {
          const cfg = flow[b.key] ?? {};
          const action = cfg.action ?? DEFAULTS[b.key];
          const expanded = open === b.key;
          return (
            <Card
              key={b.key}
              pad={false}
              className={cn(
                "overflow-hidden transition-colors",
                expanded && "border-primary/40",
              )}
            >
              <button
                type="button"
                onClick={() => setOpen(expanded ? null : b.key)}
                className="flex w-full items-center gap-3 px-card py-3 text-left hover:bg-sunk"
              >
                <b.icon size={15} className="shrink-0 text-muted" />
                <span className="min-w-0 flex-1">
                  <span className="block text-base font-semibold text-ink">{b.label}</span>
                  <span className="block text-sm text-muted">{b.hint}</span>
                </span>
                <Chip tone={b.tone}>
                  {ACTIONS.find((a) => a.value === action)?.label ?? action}
                </Chip>
              </button>

              {expanded && (
                <div className="grid gap-3 border-t border-line px-card py-3 sm:grid-cols-2">
                  <Field label="Then do this">
                    <Select
                      value={action}
                      onChange={(e) => set(b.key, { action: e.target.value })}
                      options={ACTIONS}
                    />
                  </Field>
                  <Field
                    label="Guidance for the AI"
                    hint="Optional. Steers tone and wording on this branch."
                  >
                    <Textarea
                      value={cfg.note ?? ""}
                      onChange={(e) => set(b.key, { note: e.target.value })}
                      placeholder={
                        b.key === "not_interested"
                          ? "e.g. Apologise briefly and end. Do not pitch again."
                          : "e.g. Offer two concrete time slots."
                      }
                      className="min-h-[60px]"
                    />
                  </Field>
                </div>
              )}
            </Card>
          );
        })}
      </div>

      <p className="mt-4 flex items-start gap-2 rounded-md bg-info-wash px-3 py-2 text-sm text-info">
        <GitBranch size={13} className="mt-0.5 shrink-0" />
        Rejection branches always win over engagement rules — a caller who says
        "not interested" after ten warm turns still exits politely rather than
        being pushed toward a meeting.
      </p>
    </StepSplit>
  );
}
