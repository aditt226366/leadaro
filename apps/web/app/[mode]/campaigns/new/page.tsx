"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { PageHeader } from "@/components/shell/TopBar";
import { WizardShell, type Step } from "@/components/wizard/WizardShell";
import { DetailsStep } from "@/components/wizard/steps/Details";
import { AudienceStep } from "@/components/wizard/steps/Audience";
import { VoiceStep } from "@/components/wizard/steps/VoiceStep";
import { ScriptStep } from "@/components/wizard/steps/ScriptStep";
import { SettingsStep } from "@/components/wizard/steps/SettingsStep";
import { ScheduleStep } from "@/components/wizard/steps/ScheduleStep";
import { FlowStep } from "@/components/wizard/steps/FlowStep";
import { api, type Campaign, type Mode, type Voice } from "@/lib/api";

// Voice Outreach is AI-only; Call Outreach adds the conversation-flow builder.
// This is the only structural difference between the two wizards.
const VOICE_STEPS: Step[] = [
  { key: "details", label: "Details" },
  { key: "audience", label: "Leads" },
  { key: "voice", label: "Voice" },
  { key: "script", label: "Script" },
  { key: "settings", label: "Settings" },
  { key: "schedule", label: "Schedule" },
];

const CALL_STEPS: Step[] = [
  { key: "details", label: "Details" },
  { key: "audience", label: "Audience" },
  { key: "voice", label: "Voice" },
  { key: "script", label: "Script" },
  { key: "flow", label: "Flow" },
  { key: "settings", label: "Settings" },
  { key: "schedule", label: "Schedule" },
];

export default function NewCampaign() {
  const { mode } = useParams<{ mode: Mode }>();
  const router = useRouter();
  const steps = mode === "call" ? CALL_STEPS : VOICE_STEPS;

  const [step, setStep] = useState(0);
  const [draft, setDraft] = useState<Partial<Campaign>>({
    mode,
    language: "en",
    timezone: "America/New_York",
    priority: "normal",
    tags: [],
    voice_type: "ai",
    voice_config: { speed: "normal", pitch: "medium", emotion: "friendly" },
    script: {},
    settings: {},
    compliance: { dnd_check: true, tcpa: true, recording_notice: true },
    business_hours: { start: "09:00", end: "18:00" },
    weekdays_only: true,
    concurrent_calls: 5,
    calls_per_minute: 10,
    schedule_mode: "immediate",
  });
  const [campaignId, setCampaignId] = useState<string | null>(null);
  const [leadCount, setLeadCount] = useState(0);
  const [voices, setVoices] = useState<Voice[]>([]);
  const [numbers, setNumbers] = useState<{ id: string; e164: string; label?: string | null }[]>([]);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  const dirty = useRef(false);
  const patch = useCallback((p: Partial<Campaign>) => {
    dirty.current = true;
    setDraft((d) => ({ ...d, ...p }));
  }, []);

  useEffect(() => {
    api.get<Voice[]>("/voices").then(setVoices).catch(() => {});
    api.get<{ id: string; e164: string; label?: string }[]>("/phone-numbers")
      .then(setNumbers)
      .catch(() => setNumbers([]));   // endpoint optional until numbers are provisioned
  }, []);

  /** Persist the draft. Creates on first save, patches thereafter. */
  const save = useCallback(async (): Promise<string | null> => {
    if (!draft.name?.trim()) {
      setError("Give the campaign a name before continuing.");
      return null;
    }
    setSaving(true);
    setError("");
    try {
      if (!campaignId) {
        const created = await api.post<Campaign>("/campaigns", { ...draft, mode });
        setCampaignId(created.id);
        dirty.current = false;
        return created.id;
      }
      if (dirty.current) {
        // `mode` is immutable after creation and the API rejects unknown keys.
        const { mode: _m, id: _i, ...patchable } = draft as Record<string, unknown>;
        await api.patch(`/campaigns/${campaignId}`, patchable);
        dirty.current = false;
      }
      return campaignId;
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not save the campaign");
      return null;
    } finally {
      setSaving(false);
    }
  }, [draft, campaignId, mode]);

  async function next() {
    if (await save()) setStep((s) => Math.min(s + 1, steps.length - 1));
  }

  async function launch() {
    const id = await save();
    if (!id) return;
    setSaving(true);
    try {
      // Immediate campaigns go live; anything dated waits for the dialer.
      await api.patch(`/campaigns/${id}`, {
        status: draft.schedule_mode === "immediate" ? "active" : "scheduled",
      });
      router.push(`/${mode}/campaigns/${id}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Launch failed");
      setSaving(false);
    }
  }

  const key = steps[step].key;

  return (
    <>
      <PageHeader
        title={mode === "voice" ? "Create Voice Campaign" : "Create Call Campaign"}
        subtitle={
          campaignId
            ? "Draft saved — you can leave and come back."
            : "Your progress is saved as you move through the steps."
        }
      />

      <WizardShell
        steps={steps}
        current={step}
        onStep={setStep}
        onBack={() => setStep((s) => Math.max(s - 1, 0))}
        onNext={next}
        onLaunch={launch}
        saving={saving}
        canAdvance={!!draft.name?.trim()}
        error={error}
      >
        {key === "details" && (
          <DetailsStep draft={draft} patch={patch} mode={mode} numbers={numbers} />
        )}
        {key === "audience" && (
          <AudienceStep campaignId={campaignId} onCount={setLeadCount} />
        )}
        {key === "voice" && <VoiceStep draft={draft} patch={patch} mode={mode} />}
        {key === "script" && <ScriptStep draft={draft} patch={patch} />}
        {key === "flow" && <FlowStep draft={draft} patch={patch} />}
        {key === "settings" && <SettingsStep draft={draft} patch={patch} />}
        {key === "schedule" && (
          <ScheduleStep
            draft={draft}
            patch={patch}
            mode={mode}
            leadCount={leadCount}
            voiceName={voices.find((v) => v.id === draft.voice_id)?.name}
          />
        )}
      </WizardShell>
    </>
  );
}
