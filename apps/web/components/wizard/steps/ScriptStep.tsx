"use client";
import { useState } from "react";
import {
  PencilLine, Sparkles, FileUp, Loader2, Wand2, Scissors, Briefcase,
  Smile, Zap, Copy,
} from "lucide-react";
import { Card } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Field, Input, OptionCards, Select, Textarea } from "@/components/ui/Form";
import { SectionTitle, StepSplit } from "../WizardShell";
import { api, type Campaign } from "@/lib/api";
import { cn } from "@/lib/cn";

// FRD §5 step 4 — the script sections, in the order they're spoken.
const SECTIONS: [key: string, label: string, hint: string][] = [
  ["greeting", "Greeting", "First line. Must include the AI disclosure."],
  ["introduction", "Introduction", "Who you are and why you're calling."],
  ["pain_point", "Pain point", "The problem you're addressing."],
  ["offer", "Offer", "What you're actually offering."],
  ["cta", "Call to action", "The ask."],
  ["objection_handling", "Objection handling", "How to respond to pushback."],
  ["closing_statement", "Closing statement", "How to end a good call."],
  ["thank_you", "Thank you", "Sign-off."],
  ["voicemail_message", "Voicemail message", "Left when a machine answers."],
  ["fallback_script", "Fallback", "When the AI can't understand the caller."],
  ["transfer_script", "Transfer", "Said just before handing to a human."],
  ["knowledge_base", "Knowledge base", "Facts the AI may cite. Not read aloud."],
];

const VARIABLES = [
  "first_name", "last_name", "company", "industry", "designation",
  "city", "website", "meeting_link", "discount", "campaign_name", "product",
];

const IMPROVEMENTS = [
  ["rewrite", "Rewrite", Wand2], ["shorten", "Shorten", Scissors],
  ["professional", "Professional", Briefcase], ["friendly", "Friendly", Smile],
  ["urgent", "Urgent", Zap],
] as const;

export function ScriptStep({
  draft, patch,
}: {
  draft: Partial<Campaign>;
  patch: (p: Partial<Campaign>) => void;
}) {
  const [tab, setTab] = useState<"write" | "generate" | "import">("write");
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [focused, setFocused] = useState("greeting");
  const [gen, setGen] = useState({
    company_website: "", goal: "book_meeting", offer: "",
    audience: "", tone: "professional", cta: "", length: "short", prompt: "",
  });

  const script = (draft.script ?? {}) as Record<string, string>;
  const setScript = (p: Record<string, string>) =>
    patch({ script: { ...script, ...p } });

  async function generate() {
    if (!gen.offer.trim()) {
      setError("Describe what you're offering — the generator needs it.");
      return;
    }
    setBusy("generate");
    setError("");
    try {
      const r = await api.post<Record<string, string | number>>("/scripts/generate", {
        ...gen,
        language: draft.language ?? "en",
      });
      const { estimated_duration_seconds, ...sections } = r;
      setScript(sections as Record<string, string>);
      setTab("write");
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
      setScript({ [focused]: r.text });
    } catch (e) {
      setError(e instanceof Error ? e.message : "Rewrite failed");
    } finally {
      setBusy("");
    }
  }

  async function importFile(file: File) {
    setBusy("import");
    setError("");
    try {
      const fd = new FormData();
      fd.append("file", file);
      const r = await api.upload<{ text: string }>("/scripts/import", fd);
      setScript({ introduction: r.text });
      setTab("write");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Import failed");
    } finally {
      setBusy("");
    }
  }

  const words = Object.values(script).join(" ").trim().split(/\s+/).filter(Boolean).length;

  return (
    <StepSplit
      aside={
        <>
          <Card>
            <SectionTitle hint="Click to insert into the focused section.">
              Variables
            </SectionTitle>
            <div className="flex flex-wrap gap-1.5">
              {VARIABLES.map((v) => (
                <button
                  key={v}
                  type="button"
                  onClick={() =>
                    setScript({ [focused]: `${script[focused] ?? ""}{{${v}}}` })
                  }
                  className="rounded-md bg-sunk px-1.5 py-1 font-mono text-tiny text-primary-ink hover:bg-primary-wash"
                >
                  {`{{${v}}}`}
                </button>
              ))}
            </div>
          </Card>

          <Card>
            <SectionTitle>AI improvements</SectionTitle>
            <p className="mb-2 text-sm text-muted">
              Applies to <span className="font-medium text-ink">
                {SECTIONS.find(([k]) => k === focused)?.[1]}
              </span>.
            </p>
            <div className="grid grid-cols-2 gap-1.5">
              {IMPROVEMENTS.map(([action, label, Icon]) => (
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
            <div className="flex items-center justify-between text-sm">
              <span className="text-muted">Word count</span>
              <span className="tnum font-semibold text-ink">{words}</span>
            </div>
            <div className="mt-1 flex items-center justify-between text-sm">
              <span className="text-muted">Est. speaking time</span>
              <span className="tnum font-semibold text-ink">
                {Math.floor(words / 150)}:{String(Math.round((words / 150 % 1) * 60)).padStart(2, "0")}
              </span>
            </div>
            <p className="mt-2 text-tiny leading-snug text-muted">
              Only the sections the AI reaches get spoken — a longer script is a
              deeper well, not a longer call.
            </p>
          </Card>
        </>
      }
    >
      <SectionTitle hint="Write it, generate it, or import an existing one.">
        Campaign script
      </SectionTitle>
      <OptionCards
        value={tab}
        onChange={setTab}
        columns={3}
        options={[
          { value: "write", label: "Write yourself", description: "Full manual control", icon: PencilLine },
          { value: "generate", label: "Generate with AI", description: "From your goal and offer", icon: Sparkles },
          { value: "import", label: "Import", description: ".txt, .md, .docx or .pdf", icon: FileUp },
        ]}
      />

      {error && (
        <p className="mt-3 rounded-md bg-neg-wash px-3 py-2 text-sm text-neg">{error}</p>
      )}

      {tab === "generate" && (
        <Card className="mt-4">
          <div className="grid gap-3 sm:grid-cols-2">
            <Field label="Company website" hint="Used for context.">
              <Input
                value={gen.company_website}
                onChange={(e) => setGen({ ...gen, company_website: e.target.value })}
                placeholder="https://example.com"
              />
            </Field>
            <Field label="Goal" required>
              <Select
                value={gen.goal}
                onChange={(e) => setGen({ ...gen, goal: e.target.value })}
                options={[
                  { value: "book_meeting", label: "Book a meeting" },
                  { value: "qualify_lead", label: "Qualify lead" },
                  { value: "follow_up", label: "Follow up" },
                  { value: "collect_payment", label: "Payment reminder" },
                  { value: "survey", label: "Survey / feedback" },
                  { value: "reengage", label: "Re-engage cold lead" },
                  { value: "confirm_verify", label: "Confirm / verify" },
                ]}
              />
            </Field>
            <Field label="What you offer" required className="sm:col-span-2">
              <Textarea
                value={gen.offer}
                onChange={(e) => setGen({ ...gen, offer: e.target.value })}
                placeholder="e.g. AI outbound calling that books meetings automatically"
              />
            </Field>
            <Field label="Target audience">
              <Input
                value={gen.audience}
                onChange={(e) => setGen({ ...gen, audience: e.target.value })}
                placeholder="e.g. VP Sales at 50-500 person SaaS companies"
              />
            </Field>
            <Field label="Tone">
              <Select
                value={gen.tone}
                onChange={(e) => setGen({ ...gen, tone: e.target.value })}
                options={["friendly", "professional", "confident", "energetic",
                          "calm", "urgent", "happy", "empathetic"].map((t) => ({
                  value: t, label: t[0].toUpperCase() + t.slice(1),
                }))}
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
                  { value: "short", label: "Short (~2 min call)" },
                  { value: "medium", label: "Medium (~3 min)" },
                  { value: "long", label: "Long (~5 min)" },
                ]}
              />
            </Field>
            <Field label="Extra instructions" className="sm:col-span-2">
              <Textarea
                value={gen.prompt}
                onChange={(e) => setGen({ ...gen, prompt: e.target.value })}
                placeholder="Anything else the script should mention or avoid."
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
              ? <><Loader2 size={14} className="animate-spin" /> Writing the script…</>
              : <><Sparkles size={14} /> Generate script</>}
          </Button>
        </Card>
      )}

      {tab === "import" && (
        <Card className="mt-4 border-dashed text-center">
          <FileUp size={20} className="mx-auto text-muted" />
          <p className="mt-2 text-base font-medium text-ink">Import an existing script</p>
          <p className="mt-0.5 text-sm text-muted">.txt, .md, .docx or .pdf</p>
          <label className="mt-3 inline-block">
            <input
              type="file"
              accept=".txt,.md,.docx,.pdf"
              className="hidden"
              onChange={(e) => e.target.files?.[0] && importFile(e.target.files[0])}
            />
            <span className="inline-flex h-8 cursor-pointer items-center gap-2 rounded-pill bg-primary px-3.5 text-sm font-medium text-white hover:bg-primary-deep">
              {busy === "import"
                ? <Loader2 size={13} className="animate-spin" />
                : <FileUp size={13} />}
              Choose file
            </span>
          </label>
        </Card>
      )}

      <div className="mt-5 space-y-3">
        {SECTIONS.map(([key, label, hint]) => (
          <Field key={key} label={label} hint={hint}>
            <Textarea
              value={script[key] ?? ""}
              onFocus={() => setFocused(key)}
              onChange={(e) => setScript({ [key]: e.target.value })}
              placeholder={hint}
              className={cn(
                "min-h-[64px]",
                focused === key && "border-primary/40 ring-2 ring-primary/15",
              )}
            />
          </Field>
        ))}
      </div>
    </StepSplit>
  );
}
