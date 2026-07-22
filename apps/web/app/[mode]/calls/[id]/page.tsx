"use client";
import { useEffect, useMemo, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import {
  Download, Search, Play, Share2, Loader2, ArrowLeft, Clock, Bot, User,
  Sparkles, Target, Wallet, ListChecks, AlertTriangle,
} from "lucide-react";
import { PageHeader } from "@/components/shell/TopBar";
import { Card } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Chip } from "@/components/ui/Chip";
import { Input } from "@/components/ui/Form";
import { api, getToken, type Mode } from "@/lib/api";
import { cn, dur } from "@/lib/cn";

type Turn = {
  seq: number;
  role: "agent" | "lead";
  text: string;
  intent?: string | null;
  sentiment?: number | null;
  emotion?: string | null;
  action?: string | null;
  total_ms?: number | null;
  llm_ms?: number | null;
  created_at: string;
};

type Detail = {
  call: Record<string, string | number | null>;
  turns: Turn[];
  summary: {
    summary?: string; key_points: string[]; action_items: string[];
    pain_points: string[]; next_steps?: string; budget?: string;
    timeline?: string; lead_tier?: string; qualification_score?: number;
    sentiment_avg?: number; followup_recommendation?: string;
  } | null;
};

export default function CallDetail() {
  const { mode, id } = useParams<{ mode: Mode; id: string }>();
  const router = useRouter();
  const [data, setData] = useState<Detail | null>(null);
  const [error, setError] = useState("");
  const [q, setQ] = useState("");

  useEffect(() => {
    api.get<Detail>(`/calls/${id}`)
      .then(setData)
      .catch((e) => setError(e instanceof Error ? e.message : "Could not load call"));
  }, [id]);

  const filtered = useMemo(() => {
    if (!data) return [];
    if (!q.trim()) return data.turns;
    const needle = q.toLowerCase();
    return data.turns.filter((t) => t.text.toLowerCase().includes(needle));
  }, [data, q]);

  if (!data) {
    return (
      <div className="grid place-items-center py-24 text-muted">
        {error ? <p className="text-neg">{error}</p> : <Loader2 size={20} className="animate-spin" />}
      </div>
    );
  }

  const { call, summary, turns } = data;
  const name =
    [call.first_name, call.last_name].filter(Boolean).join(" ") ||
    String(call.to_number ?? "Unknown");

  // Median agent-turn latency — the per-call view of the success metric.
  const latencies = turns.filter((t) => t.total_ms).map((t) => t.total_ms as number).sort((a, b) => a - b);
  const p50 = latencies.length ? latencies[Math.floor(latencies.length / 2)] : null;

  async function download() {
    const res = await fetch(
      `${process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"}/calls/${id}/transcript.txt`,
      { headers: { Authorization: `Bearer ${getToken()}` } },
    );
    const blob = await res.blob();
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `transcript-${id}.txt`;
    a.click();
    URL.revokeObjectURL(a.href);
  }

  return (
    <>
      <PageHeader title={name} subtitle={String(call.company ?? call.to_number ?? "")}>
        <Button onClick={() => router.back()}><ArrowLeft size={13} /> Back</Button>
        <Button onClick={download}><Download size={13} /> Transcript</Button>
        {call.recording_url && (
          <>
            <Button><Play size={13} /> Play recording</Button>
            <Button><Share2 size={13} /> Share</Button>
          </>
        )}
      </PageHeader>

      <div className="grid gap-card lg:grid-cols-3">
        {/* ── transcript ─────────────────────────────────────────────── */}
        <Card className="lg:col-span-2" pad={false}>
          <div className="flex items-center gap-3 border-b border-line px-card py-3">
            <h3 className="text-base font-semibold text-ink">Conversation</h3>
            <Chip tone="neutral">{turns.length} turns</Chip>
            <label className="relative ml-auto flex h-8 w-[220px] items-center">
              <Search size={13} className="absolute left-2.5 text-faint" />
              <Input
                value={q}
                onChange={(e) => setQ(e.target.value)}
                placeholder="Search transcript…"
                className="h-8 pl-8 text-sm"
              />
            </label>
          </div>

          <ul className="max-h-[620px] space-y-3 overflow-y-auto p-card">
            {filtered.length === 0 && (
              <li className="py-10 text-center text-base text-muted">
                {turns.length === 0
                  ? "No conversation recorded — the call did not connect to a person."
                  : "No turns match that search."}
              </li>
            )}
            {filtered.map((t) => {
              const agent = t.role === "agent";
              return (
                <li key={t.seq} className={cn("flex gap-2.5", agent ? "" : "flex-row-reverse")}>
                  <span
                    className={cn(
                      "grid size-7 shrink-0 place-items-center rounded-full",
                      agent ? "bg-primary-wash text-primary-ink" : "bg-sunk text-muted",
                    )}
                  >
                    {agent ? <Bot size={13} /> : <User size={13} />}
                  </span>
                  <div className={cn("max-w-[78%]", agent ? "" : "text-right")}>
                    <div
                      className={cn(
                        "rounded-card px-3 py-2 text-base leading-relaxed",
                        agent
                          ? "bg-surface border border-line text-ink"
                          : "bg-primary text-white",
                      )}
                    >
                      {t.text}
                    </div>
                    <div
                      className={cn(
                        "mt-1 flex flex-wrap items-center gap-1.5 text-tiny text-muted",
                        agent ? "" : "justify-end",
                      )}
                    >
                      {t.intent && <span className="capitalize">{t.intent.replace(/_/g, " ")}</span>}
                      {t.sentiment != null && (
                        <span
                          className={cn(
                            "tnum font-medium",
                            t.sentiment > 0.2 ? "text-pos"
                              : t.sentiment < -0.2 ? "text-neg" : "text-muted",
                          )}
                        >
                          {t.sentiment > 0 ? "+" : ""}{t.sentiment.toFixed(2)}
                        </span>
                      )}
                      {t.emotion && <span>· {t.emotion}</span>}
                      {t.total_ms && (
                        <span className="tnum">· {t.total_ms}ms</span>
                      )}
                    </div>
                  </div>
                </li>
              );
            })}
          </ul>
        </Card>

        {/* ── right rail ─────────────────────────────────────────────── */}
        <div className="space-y-card">
          <Card>
            <h3 className="mb-3 text-base font-semibold text-ink">Call details</h3>
            <dl className="space-y-2 text-sm">
              {[
                ["Outcome", String(call.outcome ?? "—").replace(/_/g, " ")],
                ["Direction", String(call.direction ?? "—")],
                ["Answered by", String(call.answered_by ?? "—")],
                ["Duration", call.duration_sec ? dur(Number(call.duration_sec)) : "—"],
                ["Campaign", String(call.campaign_name ?? "—")],
                ["Number", String(call.to_number ?? call.phone ?? "—")],
                ["Started", call.started_at
                  ? new Date(String(call.started_at)).toLocaleString()
                  : "—"],
                ...(p50 ? [["Median turn latency", `${p50}ms`]] : []),
              ].map(([k, v]) => (
                <div key={k} className="flex justify-between gap-3">
                  <dt className="text-muted">{k}</dt>
                  <dd className="truncate font-medium capitalize text-ink">{v}</dd>
                </div>
              ))}
            </dl>
          </Card>

          {summary ? (
            <>
              <Card>
                <h3 className="mb-2 flex items-center gap-1.5 text-base font-semibold text-ink">
                  <Sparkles size={14} className="text-primary" /> AI summary
                </h3>
                <p className="text-base leading-relaxed text-ink">{summary.summary}</p>

                <div className="mt-3 flex flex-wrap gap-1.5">
                  {summary.lead_tier && (
                    <Chip tone={summary.lead_tier === "hot" ? "neg"
                      : summary.lead_tier === "warm" ? "warn" : "neutral"}>
                      {summary.lead_tier} lead
                    </Chip>
                  )}
                  {summary.qualification_score != null && (
                    <Chip tone="primary">score {summary.qualification_score}</Chip>
                  )}
                  {summary.sentiment_avg != null && (
                    <Chip tone={summary.sentiment_avg > 0 ? "pos" : "neg"}>
                      sentiment {summary.sentiment_avg > 0 ? "+" : ""}
                      {summary.sentiment_avg.toFixed(2)}
                    </Chip>
                  )}
                </div>
              </Card>

              {(summary.budget || summary.timeline) && (
                <Card>
                  <h3 className="mb-2 text-base font-semibold text-ink">Qualification</h3>
                  {summary.budget && (
                    <p className="flex items-start gap-2 text-sm">
                      <Wallet size={13} className="mt-0.5 shrink-0 text-muted" />
                      <span><span className="text-muted">Budget: </span>{summary.budget}</span>
                    </p>
                  )}
                  {summary.timeline && (
                    <p className="mt-1.5 flex items-start gap-2 text-sm">
                      <Clock size={13} className="mt-0.5 shrink-0 text-muted" />
                      <span><span className="text-muted">Timeline: </span>{summary.timeline}</span>
                    </p>
                  )}
                </Card>
              )}

              <ListCard icon={Target} title="Key points" items={summary.key_points} />
              <ListCard icon={AlertTriangle} title="Pain points" items={summary.pain_points} />
              <ListCard icon={ListChecks} title="Action items" items={summary.action_items} />

              {summary.followup_recommendation && (
                <Card>
                  <h3 className="mb-1.5 text-base font-semibold text-ink">
                    Recommended follow-up
                  </h3>
                  <p className="text-base leading-relaxed text-muted">
                    {summary.followup_recommendation}
                  </p>
                </Card>
              )}
            </>
          ) : (
            <Card>
              <p className="text-base text-muted">
                No AI summary yet — it is generated by the post-call worker shortly
                after the call ends.
              </p>
            </Card>
          )}
        </div>
      </div>
    </>
  );
}

function ListCard({
  icon: Icon, title, items,
}: {
  icon: React.ComponentType<{ size?: number; className?: string }>;
  title: string;
  items: string[];
}) {
  if (!items?.length) return null;
  return (
    <Card>
      <h3 className="mb-2 flex items-center gap-1.5 text-base font-semibold text-ink">
        <Icon size={14} className="text-muted" /> {title}
      </h3>
      <ul className="space-y-1.5">
        {items.map((it, i) => (
          <li key={i} className="flex gap-2 text-base leading-snug text-ink">
            <span className="mt-1.5 size-1 shrink-0 rounded-full bg-primary" />
            {it}
          </li>
        ))}
      </ul>
    </Card>
  );
}
