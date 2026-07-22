"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import {
  Play, Square, Sparkles, Star, Upload, Loader2, Mic, RefreshCw, Gauge, Smile,
} from "lucide-react";
import { PageHeader } from "@/components/shell/TopBar";
import { Card } from "@/components/ui/Card";
import { Button, PillSelect } from "@/components/ui/Button";
import { Chip } from "@/components/ui/Chip";
import { Field, Input, Select } from "@/components/ui/Form";
import { api, getToken, type Voice } from "@/lib/api";
import { cn, num } from "@/lib/cn";

import { RTL, sampleLine } from "@/lib/sampleLines";

// FRD §5 step 3 — the 8 emotions and 3 speeds the campaign can request.
const EMOTIONS = [
  "friendly", "professional", "confident", "energetic",
  "calm", "urgent", "happy", "empathetic",
];
const SPEEDS = ["slow", "normal", "fast"];

type Facets = {
  gender: string[];
  accent: string[];
  tone: string[];
  language: { code: string; label: string; voices: number }[];
};

export default function VoiceLibrary() {
  const [voices, setVoices] = useState<Voice[]>([]);
  const [facets, setFacets] = useState<Facets | null>(null);
  const [filter, setFilter] = useState<Record<string, string>>({});
  const [playing, setPlaying] = useState<string | null>(null);
  const [text, setText] = useState(sampleLine("en"));
  // Tracks whether the user has typed their own line. Once they have, changing
  // the language filter must not silently overwrite their words.
  const [edited, setEdited] = useState(false);
  const [emotion, setEmotion] = useState("friendly");
  const [speed, setSpeed] = useState("normal");
  const [error, setError] = useState("");
  const [msg, setMsg] = useState("");
  const [syncing, setSyncing] = useState(false);
  const [cloning, setCloning] = useState(false);
  const [cloneName, setCloneName] = useState("");
  const audioRef = useRef<HTMLAudioElement | null>(null);

  const load = useCallback(async () => {
    const q = new URLSearchParams();
    Object.entries(filter).forEach(([k, v]) => v && q.set(k, v));
    try {
      const [v, f] = await Promise.all([
        api.get<Voice[]>(`/voices?${q}`),
        api.get<Facets>("/voices/facets"),
      ]);
      setVoices(v);
      setFacets(f);
      setError("");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not load voices");
    }
  }, [filter]);

  useEffect(() => { void load(); }, [load]);
  useEffect(() => () => { audioRef.current?.pause(); }, []);

  // Swap the preview line into the selected language. Without this the text
  // stays English and every voice reads English words — the language parameter
  // controls pronunciation, not translation.
  useEffect(() => {
    if (!edited) setText(sampleLine(filter.language || "en"));
  }, [filter.language, edited]);

  async function sync() {
    setSyncing(true);
    setError("");
    setMsg("");
    try {
      const r = await api.post<{ imported: number; languages: string[] }>("/voices/sync");
      setMsg(`${num(r.imported)} voices synced across ${r.languages.length} languages`);
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Sync failed");
    } finally {
      setSyncing(false);
    }
  }

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
          // Emotion and speed are applied server-side, so what you hear here is
          // exactly what the campaign will sound like.
          body: JSON.stringify({
            voice_id: v.id, text, emotion, speed, language: v.language,
          }),
        },
      );
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.detail ?? `Preview failed (${res.status})`);
      }
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

  async function clone(file: File) {
    if (!cloneName.trim()) { setError("Give the cloned voice a name first."); return; }
    setCloning(true);
    setError("");
    try {
      const fd = new FormData();
      fd.append("name", cloneName);
      fd.append("sample", file);
      await api.upload("/voices/clone", fd);
      setCloneName("");
      setMsg("Voice cloned and added to your library.");
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Cloning failed");
    } finally {
      setCloning(false);
    }
  }

  const opt = (any: string, vals: string[]) => [
    { value: "", label: any },
    ...vals.map((v) => ({ value: v, label: v })),
  ];

  return (
    <>
      <PageHeader
        title="Voice Library"
        subtitle={
          facets
            ? `${num(voices.length)} voices shown · ${facets.language.length} languages available`
            : "Preview any voice reading your own line."
        }
      >
        <PillSelect
          value={filter.language ?? ""}
          onChange={(v) => setFilter({ ...filter, language: v })}
          options={[
            { value: "", label: "Any language" },
            ...(facets?.language ?? []).map((l) => ({
              value: l.code, label: `${l.label} (${l.voices})`,
            })),
          ]}
        />
        <PillSelect
          value={filter.gender ?? ""}
          onChange={(v) => setFilter({ ...filter, gender: v })}
          options={opt("Any gender", facets?.gender ?? [])}
        />
        <PillSelect
          value={filter.accent ?? ""}
          onChange={(v) => setFilter({ ...filter, accent: v })}
          options={opt("Any accent", facets?.accent ?? [])}
        />
        <PillSelect
          value={filter.tone ?? ""}
          onChange={(v) => setFilter({ ...filter, tone: v })}
          options={opt("Any tone", facets?.tone ?? [])}
        />
        <Button onClick={sync} disabled={syncing}>
          {syncing ? <Loader2 size={13} className="animate-spin" /> : <RefreshCw size={13} />}
          Sync
        </Button>
      </PageHeader>

      {error && (
        <p className="mb-card rounded-card bg-neg-wash px-4 py-2.5 text-base text-neg">{error}</p>
      )}
      {msg && (
        <p className="mb-card rounded-card bg-pos-wash px-4 py-2.5 text-base text-pos">{msg}</p>
      )}

      <div className="grid gap-card lg:grid-cols-[1fr_290px]">
        <div>
          {/* Preview controls — these are applied to the synthesis request, so
              the card previews match what the campaign will actually sound like. */}
          <Card className="mb-card">
            <Field
              label="Preview line"
              hint={
                edited
                  ? "Your own line — it stays put when you change language."
                  : "Switches with the language filter. Edit it to keep your own."
              }
            >
              <Input
                value={text}
                dir={RTL.has(filter.language ?? "") ? "rtl" : "ltr"}
                onChange={(e) => { setText(e.target.value); setEdited(true); }}
              />
            </Field>
            {edited && (
              <button
                type="button"
                onClick={() => { setEdited(false); setText(sampleLine(filter.language || "en")); }}
                className="mt-1 text-tiny font-medium text-primary-ink hover:underline"
              >
                Reset to the sample line for this language
              </button>
            )}
            <div className="mt-3 grid gap-3 sm:grid-cols-2">
              <Field label="Emotion">
                <Select
                  value={emotion}
                  onChange={(e) => setEmotion(e.target.value)}
                  options={EMOTIONS.map((v) => ({
                    value: v, label: v[0].toUpperCase() + v.slice(1),
                  }))}
                />
              </Field>
              <Field label="Speaking speed">
                <Select
                  value={speed}
                  onChange={(e) => setSpeed(e.target.value)}
                  options={SPEEDS.map((v) => ({
                    value: v, label: v[0].toUpperCase() + v.slice(1),
                  }))}
                />
              </Field>
            </div>
            <p className="mt-2 flex items-center gap-1.5 text-tiny text-muted">
              <Smile size={11} /> Emotion and speed are applied by the synthesiser —
              what you hear is what the caller hears.
            </p>
          </Card>

          <div className="grid gap-card sm:grid-cols-2 xl:grid-cols-3">
            {voices.map((v) => (
              <Card key={v.id}>
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0">
                    <p className="flex items-center gap-1.5 truncate text-base font-semibold text-ink">
                      {v.name}
                      {v.is_clone && <Sparkles size={11} className="shrink-0 text-primary" />}
                    </p>
                    <p className="truncate text-sm text-muted">
                      {[v.gender?.replace("_", " "), v.accent, v.tone]
                        .filter(Boolean).join(" · ")}
                    </p>
                  </div>
                  <button
                    onClick={() => preview(v)}
                    aria-label={`Preview ${v.name}`}
                    className="grid size-8 shrink-0 place-items-center rounded-full bg-primary-wash text-primary-ink hover:bg-primary hover:text-white"
                  >
                    {playing === v.id ? <Square size={13} /> : <Play size={13} />}
                  </button>
                </div>

                <div className="mt-3 flex h-6 items-center gap-[2px]">
                  {Array.from({ length: 34 }).map((_, i) => (
                    <span
                      key={i}
                      className={cn(
                        "w-[2px] rounded-full transition-colors",
                        playing === v.id ? "bg-primary" : "bg-line-strong",
                      )}
                      style={{ height: `${20 + Math.abs(Math.sin(i * 1.4)) * 70}%` }}
                    />
                  ))}
                </div>

                <div className="mt-2.5 flex items-center justify-between">
                  <div className="flex gap-1">
                    <Chip>{v.language}</Chip>
                    {v.tone && <Chip>{v.tone}</Chip>}
                  </div>
                  {v.rating != null && (
                    <span className="flex items-center gap-1 text-tiny text-muted">
                      <Star size={10} className="fill-warn text-warn" />
                      {v.rating.toFixed(1)}
                    </span>
                  )}
                </div>
              </Card>
            ))}
            {voices.length === 0 && (
              <Card className="col-span-full py-12 text-center">
                <Gauge size={20} className="mx-auto text-faint" />
                <p className="mt-2 font-medium text-ink">No voices match those filters</p>
                <p className="mt-1 text-base text-muted">
                  Clear a filter, or press Sync to pull the latest catalogue.
                </p>
              </Card>
            )}
          </div>
        </div>

        <Card className="h-fit">
          <h3 className="mb-1 flex items-center gap-1.5 text-base font-semibold text-ink">
            <Mic size={14} className="text-primary" /> Clone a voice
          </h3>
          <p className="mb-3 text-sm leading-snug text-muted">
            Upload a clean recording of one speaker. Thirty seconds is enough.
          </p>
          <Field label="Voice name">
            <Input
              value={cloneName}
              onChange={(e) => setCloneName(e.target.value)}
              placeholder="e.g. Priya — Sales"
            />
          </Field>
          <label className="mt-3 block">
            <input
              type="file"
              accept="audio/*"
              className="hidden"
              onChange={(e) => e.target.files?.[0] && clone(e.target.files[0])}
            />
            <span className="inline-flex h-9 w-full cursor-pointer items-center justify-center gap-2 rounded-pill bg-primary text-sm font-medium text-white hover:bg-primary-deep">
              {cloning
                ? <><Loader2 size={13} className="animate-spin" /> Cloning…</>
                : <><Upload size={13} /> Upload sample</>}
            </span>
          </label>
          <p className="mt-3 border-t border-line pt-3 text-tiny leading-snug text-muted">
            You are responsible for having the speaker's permission. The upload is
            recorded against your account with who uploaded it and when.
          </p>
        </Card>
      </div>
    </>
  );
}
