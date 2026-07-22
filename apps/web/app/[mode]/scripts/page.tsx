"use client";
import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import {
  FileText, Sparkles, Loader2, ArrowRight, Wand2, Scissors, Save, Check,
} from "lucide-react";
import { PageHeader } from "@/components/shell/TopBar";
import { Card } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Chip } from "@/components/ui/Chip";
import { Field, Input, Select, Textarea } from "@/components/ui/Form";
import { api, type Campaign, type Mode } from "@/lib/api";

const SECTIONS: [string, string][] = [
  ["greeting", "Greeting"], ["introduction", "Introduction"],
  ["pain_point", "Pain point"], ["offer", "Offer"], ["cta", "Call to action"],
  ["objection_handling", "Objection handling"],
  ["closing_statement", "Closing"], ["thank_you", "Thank you"],
  ["voicemail_message", "Voicemail"], ["fallback_script", "Fallback"],
  ["transfer_script", "Transfer"], ["knowledge_base", "Knowledge base"],
];

const GOALS = [
  ["book_meeting", "Book a meeting"], ["qualify_lead", "Qualify lead"],
  ["follow_up", "Follow up"], ["collect_payment", "Payment reminder"],
  ["survey", "Survey / feedback"], ["reengage", "Re-engage cold lead"],
  ["confirm_verify", "Confirm / verify"],
];

const TONES = ["friendly", "professional", "confident", "energetic",
               "calm", "urgent", "happy", "empathetic"];

export default function ScriptsPage() {
  const { mode } = useParams<{ mode: Mode }>();
  const router = useRouter();
  const [campaigns, setCampaigns] = useState<Campaign[]>([]);
  const [active, setActive] = useState<Campaign | null>(null);
  const [script, setScript] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [saved, setSaved] = useState(false);
  const [focused, setFocused] = useState("greeting");
  const [gen, setGen] = useState({
    company_website: "", goal: "book_meeting", offer: "",
    audience: "", tone: "professional", cta: "", length: "short", prompt: "",
  });

  useEffect(() => {
    api.get<Campaign[]>(`/campaigns?mode=${mode}`)
      .then((c) => {
        setCampaigns(c);
        const first = c[0] ?? null;
        setActive(first);
        setScript((first?.script as Record<string, string>) ?? {});
      })
      .catch((e) => setError(e instanceof Error ? e.message : "Could not load campaigns"))
      .finally(() => setLoading(false));
  }, [mode]);

  function pick(c: Campaign) {
    setActive(c);
    setScript((c.script as Record<string, string>) ?? {});
    setSaved(false);
    setError("");
  }

  async function generate() {
    if (!gen.offer.trim()) {
      setError("Describe what you're offering — the generator needs it.");
      return;
    }
    setBusy("generate");
    setError("");
    try {
      const r = await api.post<Record<string, string | number>>("/scripts/generate", {
        ...gen, language: active?.language ?? "en",
      });
      const { estimated_duration_seconds, ...sections } = r;
      setScript((s) => ({ ...s, ...(sections as Record<string, string>) }));
      setSaved(false);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Generation failed");
    } finally {
      setBusy("");
    }
  }

  async function improve(action: string) {
    const text = script[focused];
    if (!text?.trim()) {
      setError(`"${SECTIONS.find(([k]) => k === focused)?.[1]}" is empty.`);
      return;
    }
    setBusy(action);
    setError("");
    try {
      const r = await api.post<{ text: string }>("/scripts/improve", { text, action });
      setScript((s) => ({ ...s, [focused]: r.text }));
      setSaved(false);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Rewrite failed");
    } finally {
      setBusy("");
    }
  }

  async function save() {
    if (!active) return;
    setBusy("save");
    setError("");
    try {
      await api.patch(`/campaigns/${active.id}`, { script });
      setSaved(true);
      setCampaigns((cs) =>
        cs.map((c) => (c.id === active.id ? { ...c, script } : c)));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not save");
    } finally {
      setBusy("");
    }
  }

  if (loading) {
    return (
      <div className="grid place-items-center py-24 text-muted">
        <Loader2 size={20} className="animate-spin" />
      </div>
    );
  }

  const filled = SECTIONS.filter(([k]) => script[k]?.trim()).length;
  const words = Object.values(script).join(" ").trim().split(/\s+/).filter(Boolean).length;

  return (
    <>
      <PageHeader
        title="Scripts"
        subtitle="Write, generate and refine what your agents say."
      >
        {active && (
          <Button variant="primary" onClick={save} disabled={busy === "save"}>
            {busy === "save" ? <Loader2 size={13} className="animate-spin" />
              : saved ? <Check size={13} /> : <Save size={13} />}
            {saved ? "Saved" : "Save script"}
          </Button>
        )}
      </PageHeader>

      {error && (
        <p className="mb-card rounded-card bg-neg-wash px-4 py-2.5 text-base text-neg">{error}</p>
      )}

      <div className="grid gap-card lg:grid-cols-[240px_1fr_270px]">
        {/* campaign picker */}
        <Card pad={false} className="h-fit">
          <div className="border-b border-line px-4 py-3">
            <h3 className="text-base font-semibold text-ink">Campaigns</h3>
          </div>
          <ul className="divide-y divide-line">
            {campaigns.map((c) => {
              const n = SECTIONS.filter(
                ([k]) => (c.script as Record<string, string>)?.[k]?.trim()).length;
              return (
                <li
                  key={c.id}
                  onClick={() => pick(c)}
                  className={`cursor-pointer px-4 py-2.5 transition-colors ${
                    active?.id === c.id ? "bg-primary-wash/50" : "hover:bg-sunk"
                  }`}
                >
                  <p className="truncate text-base font-medium text-ink">{c.name}</p>
                  <p className="text-sm text-muted">{n} of {SECTIONS.length} written</p>
                </li>
              );
            })}
            {campaigns.length === 0 && (
              <li className="px-4 py-10 text-center text-sm text-muted">
                No campaigns yet.
              </li>
            )}
          </ul>
        </Card>

        {active ? (
          <div className="min-w-0 space-y-card">
            {/* generator */}
            <Card>
              <h3 className="mb-1 flex items-center gap-1.5 text-base font-semibold text-ink">
                <Sparkles size={14} className="text-primary" /> Generate with AI
              </h3>
              <p className="mb-3 text-sm text-muted">
                Fills every section below. Existing text is overwritten.
              </p>
              <div className="grid gap-3 sm:grid-cols-2">
                <Field label="Goal" required>
                  <Select
                    value={gen.goal}
                    onChange={(e) => setGen({ ...gen, goal: e.target.value })}
                    options={GOALS.map(([v, l]) => ({ value: v, label: l }))}
                  />
                </Field>
                <Field label="Tone">
                  <Select
                    value={gen.tone}
                    onChange={(e) => setGen({ ...gen, tone: e.target.value })}
                    options={TONES.map((t) => ({
                      value: t, label: t[0].toUpperCase() + t.slice(1),
                    }))}
                  />
                </Field>
                <Field label="What you offer" required className="sm:col-span-2">
                  <Textarea
                    value={gen.offer}
                    onChange={(e) => setGen({ ...gen, offer: e.target.value })}
                    placeholder="e.g. AI outbound calling that books meetings automatically"
                    className="min-h-[60px]"
                  />
                </Field>
                <Field label="Company website">
                  <Input
                    value={gen.company_website}
                    onChange={(e) => setGen({ ...gen, company_website: e.target.value })}
                    placeholder="https://example.com"
                  />
                </Field>
                <Field label="Target audience">
                  <Input
                    value={gen.audience}
                    onChange={(e) => setGen({ ...gen, audience: e.target.value })}
                    placeholder="e.g. VP Sales at SaaS companies"
                  />
                </Field>
                <Field label="Call to action">
                  <Input
                    value={gen.cta}
                    onChange={(e) => setGen({ ...gen, cta: e.target.value })}
                    placeholder="e.g. agree to a 20-minute demo"
                  />
                </Field>
                <Field label="Length">
                  <Select
                    value={gen.length}
                    onChange={(e) => setGen({ ...gen, length: e.target.value })}
                    options={[
                      { value: "short", label: "Short (~2 min)" },
                      { value: "medium", label: "Medium (~3 min)" },
                      { value: "long", label: "Long (~5 min)" },
                    ]}
                  />
                </Field>
              </div>
              <Button
                variant="primary"
                size="md"
                className="mt-3"
                onClick={generate}
                disabled={busy === "generate"}
              >
                {busy === "generate"
                  ? <><Loader2 size={14} className="animate-spin" /> Writing…</>
                  : <><Sparkles size={14} /> Generate script</>}
              </Button>
            </Card>

            {SECTIONS.map(([key, label]) => (
              <Card key={key}>
                <div className="mb-1.5 flex items-center justify-between">
                  <h3 className="text-sm font-semibold uppercase tracking-wide text-faint">
                    {label}
                  </h3>
                  {script[key]?.trim() && <Chip tone="pos">written</Chip>}
                </div>
                <Textarea
                  value={script[key] ?? ""}
                  onFocus={() => setFocused(key)}
                  onChange={(e) => {
                    setScript({ ...script, [key]: e.target.value });
                    setSaved(false);
                  }}
                  placeholder={`Write the ${label.toLowerCase()}…`}
                  className={focused === key ? "border-primary/40 ring-2 ring-primary/15" : ""}
                />
              </Card>
            ))}
          </div>
        ) : (
          <Card className="grid place-items-center py-20 text-muted">
            <div className="text-center">
              <FileText size={22} className="mx-auto text-faint" />
              <p className="mt-2 font-medium text-ink">No campaign selected</p>
              <Button
                variant="primary"
                className="mt-3"
                onClick={() => router.push(`/${mode}/campaigns/new`)}
              >
                Create a campaign <ArrowRight size={13} />
              </Button>
            </div>
          </Card>
        )}

        {/* right rail */}
        {active && (
          <div className="space-y-card">
            <Card>
              <h3 className="mb-2 text-base font-semibold text-ink">AI improvements</h3>
              <p className="mb-2 text-sm text-muted">
                Applies to <span className="font-medium text-ink">
                  {SECTIONS.find(([k]) => k === focused)?.[1]}
                </span>.
              </p>
              <div className="grid grid-cols-2 gap-1.5">
                {([["rewrite", "Rewrite", Wand2], ["shorten", "Shorten", Scissors],
                   ["professional", "Formal", Wand2], ["friendly", "Warmer", Wand2],
                   ["urgent", "Urgent", Wand2], ["sales", "Stronger", Wand2]] as const)
                  .map(([action, label, Icon]) => (
                    <Button
                      key={action}
                      onClick={() => improve(action)}
                      disabled={!!busy}
                      className="justify-start"
                    >
                      {busy === action
                        ? <Loader2 size={12} className="animate-spin" />
                        : <Icon size={12} />}
                      {label}
                    </Button>
                  ))}
              </div>
            </Card>

            <Card>
              <dl className="space-y-1.5 text-sm">
                <div className="flex justify-between">
                  <dt className="text-muted">Sections written</dt>
                  <dd className="tnum font-semibold text-ink">{filled}/{SECTIONS.length}</dd>
                </div>
                <div className="flex justify-between">
                  <dt className="text-muted">Word count</dt>
                  <dd className="tnum font-semibold text-ink">{words}</dd>
                </div>
                <div className="flex justify-between">
                  <dt className="text-muted">Est. speaking time</dt>
                  <dd className="tnum font-semibold text-ink">
                    {Math.floor(words / 150)}:
                    {String(Math.round(((words / 150) % 1) * 60)).padStart(2, "0")}
                  </dd>
                </div>
              </dl>
              <p className="mt-2 border-t border-line pt-2 text-tiny leading-snug text-muted">
                Only the sections the AI reaches get spoken — a longer script is a
                deeper well, not a longer call.
              </p>
            </Card>
          </div>
        )}
      </div>
    </>
  );
}
