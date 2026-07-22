"use client";
import { useCallback, useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import {
  PhoneIncoming, Lightbulb, MessageSquareQuote, CalendarPlus, Loader2,
  User, Building2, Clock, Sparkles,
} from "lucide-react";
import { PageHeader } from "@/components/shell/TopBar";
import { Card } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Chip } from "@/components/ui/Chip";
import { Select } from "@/components/ui/Form";
import { useLiveCalls } from "@/lib/useLiveCalls";
import { api, type Mode } from "@/lib/api";
import { dur, num } from "@/lib/cn";

type Call = {
  id: string; outcome?: string | null; started_at: string;
  duration_sec?: number | null; first_name?: string | null;
  last_name?: string | null; company?: string | null; phone?: string | null;
  campaign_name?: string | null; lead_tier?: string | null;
  summary?: string | null;
};

// FRD §13 — the 12 dispositions a human agent can set.
const DISPOSITIONS = [
  "interested", "qualified", "disqualified", "callback", "meeting_scheduled",
  "not_interested", "no_budget", "wrong_contact", "do_not_call", "competitor",
  "no_answer", "voicemail",
];

const TALKING_POINTS = [
  "Open by referencing why they were called — never start cold on a transfer.",
  "Ask one qualifying question before pitching anything.",
  "If they raise price, acknowledge it before answering it.",
  "Confirm the next step out loud before ending the call.",
];

const OBJECTIONS: [string, string][] = [
  ["Too expensive", "Ask what they're comparing against, then reframe on cost per booked meeting rather than monthly licence."],
  ["Already have a vendor", "Ask what's working well first. Look for the gap rather than attacking the incumbent."],
  ["No time right now", "Offer a fixed 15-minute slot with a written agenda instead of an open-ended call."],
  ["Need to check with the team", "Offer to join that internal conversation, or send a one-page summary they can forward."],
];

export default function AgentWorkspace() {
  const { mode } = useParams<{ mode: Mode }>();
  const router = useRouter();
  const { calls: live, connected } = useLiveCalls();
  const [recent, setRecent] = useState<Call[]>([]);
  const [selected, setSelected] = useState<Call | null>(null);
  const [disposition, setDisposition] = useState("");
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const rows = await api.get<Call[]>("/calls?answered_by=human&limit=30");
      setRecent(rows);
      setSelected((s) => s ?? rows[0] ?? null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void load(); }, [load]);

  const name = selected
    ? [selected.first_name, selected.last_name].filter(Boolean).join(" ") ||
      selected.phone || "Unknown"
    : "";

  return (
    <>
      <PageHeader
        title="Agent Workspace"
        subtitle="Everything you need on a transferred call, in one place."
      >
        {live.length > 0 && (
          <Chip tone="pos">{num(live.length)} live now</Chip>
        )}
        <Button onClick={() => router.push(`/${mode}/monitor`)}>
          <PhoneIncoming size={13} /> Live monitor
        </Button>
      </PageHeader>

      <div className="grid gap-card lg:grid-cols-[260px_1fr_300px]">
        {/* queue */}
        <Card pad={false} className="h-fit">
          <div className="border-b border-line px-4 py-3">
            <h3 className="text-base font-semibold text-ink">Recent handoffs</h3>
          </div>
          {loading ? (
            <div className="grid place-items-center py-12 text-muted">
              <Loader2 size={16} className="animate-spin" />
            </div>
          ) : (
            <ul className="max-h-[560px] divide-y divide-line overflow-y-auto">
              {recent.map((c) => {
                const n = [c.first_name, c.last_name].filter(Boolean).join(" ") || c.phone;
                return (
                  <li
                    key={c.id}
                    onClick={() => setSelected(c)}
                    className={`cursor-pointer px-4 py-2.5 transition-colors ${
                      selected?.id === c.id ? "bg-primary-wash/50" : "hover:bg-sunk"
                    }`}
                  >
                    <p className="truncate text-base font-medium text-ink">{n}</p>
                    <p className="truncate text-sm text-muted">{c.company ?? c.phone}</p>
                    <div className="mt-1 flex items-center gap-1.5">
                      {c.lead_tier && (
                        <Chip tone={c.lead_tier === "hot" ? "neg" : c.lead_tier === "warm" ? "warn" : "neutral"}>
                          {c.lead_tier}
                        </Chip>
                      )}
                      <span className="tnum text-tiny text-faint">
                        {c.duration_sec ? dur(c.duration_sec) : "—"}
                      </span>
                    </div>
                  </li>
                );
              })}
              {recent.length === 0 && (
                <li className="px-4 py-10 text-center text-sm text-muted">
                  No answered calls yet.
                </li>
              )}
            </ul>
          )}
        </Card>

        {/* lead detail */}
        {selected ? (
          <div className="space-y-card">
            <Card>
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <h2 className="text-lg font-semibold text-ink">{name}</h2>
                  <p className="flex flex-wrap items-center gap-x-3 gap-y-1 text-sm text-muted">
                    <span className="flex items-center gap-1"><Building2 size={12} /> {selected.company ?? "—"}</span>
                    <span className="flex items-center gap-1"><User size={12} /> {selected.phone ?? "—"}</span>
                    <span className="flex items-center gap-1">
                      <Clock size={12} />
                      {new Date(selected.started_at).toLocaleString()}
                    </span>
                  </p>
                </div>
                <Button
                  variant="primary"
                  onClick={() => router.push(`/${mode}/calls/${selected.id}`)}
                >
                  Full transcript
                </Button>
              </div>

              {selected.summary && (
                <div className="mt-3 rounded-card bg-sunk p-3">
                  <p className="mb-1 flex items-center gap-1.5 text-sm font-semibold text-ink">
                    <Sparkles size={12} className="text-primary" /> What the AI heard
                  </p>
                  <p className="text-base leading-relaxed text-ink">{selected.summary}</p>
                </div>
              )}
            </Card>

            <Card>
              <h3 className="mb-2 flex items-center gap-1.5 text-base font-semibold text-ink">
                <Lightbulb size={14} className="text-warn" /> Talking points
              </h3>
              <ul className="space-y-1.5">
                {TALKING_POINTS.map((t) => (
                  <li key={t} className="flex gap-2 text-base leading-snug text-ink">
                    <span className="mt-1.5 size-1 shrink-0 rounded-full bg-primary" />
                    {t}
                  </li>
                ))}
              </ul>
            </Card>

            <Card>
              <h3 className="mb-2 flex items-center gap-1.5 text-base font-semibold text-ink">
                <MessageSquareQuote size={14} className="text-muted" /> Objection handling
              </h3>
              <div className="space-y-2">
                {OBJECTIONS.map(([objection, response]) => (
                  <details key={objection} className="rounded-card border border-line">
                    <summary className="cursor-pointer px-3 py-2 text-base font-medium text-ink">
                      {objection}
                    </summary>
                    <p className="border-t border-line px-3 py-2 text-base leading-relaxed text-muted">
                      {response}
                    </p>
                  </details>
                ))}
              </div>
            </Card>
          </div>
        ) : (
          <Card className="grid place-items-center py-20 text-muted">
            Select a call to see the lead's context.
          </Card>
        )}

        {/* disposition */}
        <div className="space-y-card">
          <Card>
            <h3 className="mb-2 text-base font-semibold text-ink">Set disposition</h3>
            <Select
              value={disposition}
              onChange={(e) => setDisposition(e.target.value)}
              options={[
                { value: "", label: "Choose an outcome…" },
                ...DISPOSITIONS.map((d) => ({ value: d, label: d.replace(/_/g, " ") })),
              ]}
            />
            <Button
              variant="primary"
              className="mt-2 w-full"
              disabled={!disposition || !selected}
            >
              Save outcome
            </Button>
            <p className="mt-2 text-tiny leading-snug text-muted">
              Setting "do not call" also adds the number to the suppression list.
            </p>
          </Card>

          <Card>
            <h3 className="mb-2 flex items-center gap-1.5 text-base font-semibold text-ink">
              <CalendarPlus size={14} className="text-muted" /> Book a meeting
            </h3>
            <p className="mb-2 text-sm text-muted">
              Creates the calendar event and emails the invite.
            </p>
            <Button className="w-full" disabled={!selected}>
              Open scheduler
            </Button>
          </Card>
        </div>
      </div>
    </>
  );
}
