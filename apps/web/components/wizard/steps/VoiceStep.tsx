"use client";
import { useEffect, useRef, useState } from "react";
import {
  Bot, UserRound, Users, Play, Square, Loader2, Star, Sparkles, Upload,
} from "lucide-react";
import { Card } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Field, OptionCards, Select, Toggle } from "@/components/ui/Form";
import { SectionTitle, StepSplit } from "../WizardShell";
import { api, getToken, type Campaign, type Mode, type Voice } from "@/lib/api";
import { sampleLine } from "@/lib/sampleLines";
import { cn } from "@/lib/cn";

const EMOTIONS = ["friendly", "professional", "confident", "energetic",
                  "calm", "urgent", "happy", "empathetic"];

export function VoiceStep({
  draft, patch, mode,
}: {
  draft: Partial<Campaign>;
  patch: (p: Partial<Campaign>) => void;
  mode: Mode;
}) {
  const [voices, setVoices] = useState<Voice[]>([]);
  const [facets, setFacets] = useState<{
    gender: string[]; accent: string[]; tone: string[];
    language: { code: string; label: string; voices: number }[];
  } | null>(null);
  const [filter, setFilter] = useState<Record<string, string>>({});
  const [playing, setPlaying] = useState<string | null>(null);
  const [error, setError] = useState("");
  const audioRef = useRef<HTMLAudioElement | null>(null);

  const cfg = (draft.voice_config ?? {}) as Record<string, string | boolean | number>;
  const setCfg = (p: Record<string, unknown>) =>
    patch({ voice_config: { ...cfg, ...p } });

  useEffect(() => {
    const q = new URLSearchParams();
    Object.entries(filter).forEach(([k, v]) => v && q.set(k, v));
    api.get<Voice[]>(`/voices?${q}`).then(setVoices).catch(() => setVoices([]));
  }, [filter]);

  useEffect(() => {
    api.get<NonNullable<typeof facets>>("/voices/facets")
      .then(setFacets)
      .catch(() => setFacets(null));
  }, []);

  // Stop any playing sample when the step unmounts — otherwise audio keeps
  // going after the user has navigated away.
  useEffect(() => () => { audioRef.current?.pause(); }, []);

  async function preview(v: Voice) {
    if (playing === v.id) {
      audioRef.current?.pause();
      setPlaying(null);
      return;
    }
    setError("");
    setPlaying(v.id);
    try {
      const res = await fetch(
        `${process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"}/voices/preview`,
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            Authorization: `Bearer ${getToken()}`,
          },
          body: JSON.stringify({
            voice_id: v.id,
            // Read a line already written in the voice's own language. Cartesia's
            // language parameter sets pronunciation, not translation, so English
            // text made every voice read English words in a foreign accent. This
            // is why a Hindi voice sounded English in the preview.
            text: sampleLine(v.language),
            language: v.language,
            speed: cfg.speed ?? "normal",
            emotion: cfg.emotion,
          }),
        },
      );
      if (!res.ok) throw new Error((await res.text()).slice(0, 120));
      const url = URL.createObjectURL(await res.blob());
      audioRef.current?.pause();
      const a = new Audio(url);
      audioRef.current = a;
      a.onended = () => { setPlaying(null); URL.revokeObjectURL(url); };
      await a.play();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Preview failed");
      setPlaying(null);
    }
  }

  const chosen = voices.find((v) => v.id === draft.voice_id);

  return (
    <StepSplit
      aside={
        <>
          <Card>
            <SectionTitle>Selected voice</SectionTitle>
            {chosen ? (
              <>
                <p className="text-lg font-semibold text-ink">{chosen.name}</p>
                <p className="text-sm text-muted">
                  {[chosen.gender, chosen.accent, chosen.tone].filter(Boolean).join(" · ")}
                </p>
                <Button
                  className="mt-3 w-full"
                  onClick={() => preview(chosen)}
                >
                  {playing === chosen.id
                    ? <><Square size={12} /> Stop</>
                    : <><Play size={12} /> Preview</>}
                </Button>
              </>
            ) : (
              <p className="text-sm text-muted">No voice chosen yet.</p>
            )}
          </Card>

          <Card>
            <SectionTitle hint="Applied as the call's baseline. The AI still adjusts per turn.">
              Delivery
            </SectionTitle>
            <Field label="Speaking speed">
              <Select
                value={String(cfg.speed ?? "normal")}
                onChange={(e) => setCfg({ speed: e.target.value })}
                options={[
                  { value: "slow", label: "Slow" },
                  { value: "normal", label: "Normal" },
                  { value: "fast", label: "Fast" },
                ]}
              />
            </Field>
            <Field label="Pitch" className="mt-3">
              <Select
                value={String(cfg.pitch ?? "medium")}
                onChange={(e) => setCfg({ pitch: e.target.value })}
                options={[
                  { value: "low", label: "Low" },
                  { value: "medium", label: "Medium" },
                  { value: "high", label: "High" },
                ]}
              />
            </Field>
            <Field label="Base emotion" className="mt-3">
              <Select
                value={String(cfg.emotion ?? "friendly")}
                onChange={(e) => setCfg({ emotion: e.target.value })}
                options={EMOTIONS.map((e) => ({
                  value: e, label: e[0].toUpperCase() + e.slice(1),
                }))}
              />
            </Field>
            <div className="mt-2 border-t border-line pt-1">
              <Toggle
                label="Noise reduction"
                hint="Filters line noise before transcription."
                checked={cfg.noise_reduction !== false}
                onChange={(v) => setCfg({ noise_reduction: v })}
              />
              <Toggle
                label="Natural pauses"
                hint="Adds breathing room between sentences."
                checked={cfg.natural_pause !== false}
                onChange={(v) => setCfg({ natural_pause: v })}
              />
            </div>
          </Card>
        </>
      }
    >
      {mode === "call" && (
        <>
          <SectionTitle hint="Who actually speaks to the lead.">
            Campaign voice type
          </SectionTitle>
          <OptionCards
            value={draft.voice_type ?? "ai"}
            onChange={(v) => patch({ voice_type: v })}
            options={[
              { value: "ai", label: "AI Voice", description: "AI handles the whole call", icon: Bot },
              { value: "human", label: "Human Agent", description: "Routed straight to your team", icon: UserRound },
              { value: "hybrid", label: "Hybrid", description: "AI qualifies, then transfers", icon: Users },
            ]}
          />
        </>
      )}

      {(mode === "voice" || draft.voice_type !== "human") && (
        <>
          <div className="mt-5 flex items-end justify-between gap-3">
            <SectionTitle hint="Click any card to hear it speak in its own language.">
              Voice library
            </SectionTitle>
            <Button><Upload size={12} /> Clone a voice</Button>
          </div>

          {/* Filter values come from the synced catalogue, not a hardcoded list —
              hardcoding is what limited this to five accents and six languages. */}
          <div className="mb-3 grid gap-2 sm:grid-cols-4">
            <Select
              value={filter.language ?? ""}
              onChange={(e) => setFilter({ ...filter, language: e.target.value })}
              options={[
                { value: "", label: "Any language" },
                ...(facets?.language ?? []).map((l) => ({
                  value: l.code, label: `${l.label} (${l.voices})`,
                })),
              ]}
            />
            {(["gender", "accent", "tone"] as const).map((key) => (
              <Select
                key={key}
                value={filter[key] ?? ""}
                onChange={(e) => setFilter({ ...filter, [key]: e.target.value })}
                options={[
                  { value: "", label: `Any ${key}` },
                  ...(facets?.[key] ?? []).map((o) => ({ value: o, label: o })),
                ]}
              />
            ))}
          </div>

          {error && (
            <p className="mb-3 rounded-md bg-neg-wash px-3 py-2 text-sm text-neg">{error}</p>
          )}

          <div className="grid gap-2.5 sm:grid-cols-2 lg:grid-cols-3">
            {voices.map((v) => {
              const active = v.id === draft.voice_id;
              return (
                <div
                  key={v.id}
                  // Persist the voice's language onto the campaign. The call
                  // runtime follows the voice, but saving it here keeps the
                  // campaign record and analytics consistent with what plays.
                  onClick={() => patch({ voice_id: v.id, language: v.language })}
                  className={cn(
                    "cursor-pointer rounded-card border p-3 transition-colors",
                    active
                      ? "border-primary bg-primary-wash"
                      : "border-line-strong bg-surface hover:border-primary/40",
                  )}
                >
                  <div className="flex items-start justify-between">
                    <div className="min-w-0">
                      <p className="flex items-center gap-1.5 font-semibold text-ink">
                        {v.name}
                        {v.is_clone && (
                          <Sparkles size={11} className="text-primary" aria-label="Cloned voice" />
                        )}
                      </p>
                      <p className="truncate text-sm text-muted">
                        {[v.gender, v.accent, v.tone].filter(Boolean).join(" · ") || v.language}
                      </p>
                    </div>
                    <button
                      onClick={(e) => { e.stopPropagation(); preview(v); }}
                      aria-label={`Preview ${v.name}`}
                      className="grid size-7 shrink-0 place-items-center rounded-full bg-surface text-primary-ink shadow-card hover:bg-primary hover:text-white"
                    >
                      {playing === v.id
                        ? <Loader2 size={12} className="animate-spin" />
                        : <Play size={12} />}
                    </button>
                  </div>

                  {/* static waveform — a visual cue, not a real analysis */}
                  <div className="mt-2.5 flex h-5 items-center gap-[2px]">
                    {Array.from({ length: 28 }).map((_, i) => (
                      <span
                        key={i}
                        className={cn(
                          "w-[2px] rounded-full",
                          active ? "bg-primary/50" : "bg-line-strong",
                        )}
                        style={{ height: `${18 + Math.sin(i * 1.7) * 12 + (i % 3) * 5}%` }}
                      />
                    ))}
                  </div>

                  {v.rating != null && (
                    <p className="mt-2 flex items-center gap-1 text-tiny text-muted">
                      <Star size={10} className="fill-warn text-warn" /> {v.rating.toFixed(1)}
                    </p>
                  )}
                </div>
              );
            })}
            {voices.length === 0 && (
              <p className="col-span-full py-8 text-center text-base text-muted">
                No voices match those filters.
              </p>
            )}
          </div>
        </>
      )}
    </StepSplit>
  );
}
