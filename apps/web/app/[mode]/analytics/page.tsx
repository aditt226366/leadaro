"use client";
import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import {
  PhoneOutgoing, Target, CalendarCheck, Voicemail, Download, Gauge,
  TrendingUp, Clock, Loader2, Zap,
} from "lucide-react";
import { PageHeader } from "@/components/shell/TopBar";
import { Card, StatCard, ChartCard } from "@/components/ui/Card";
import { Button, PillSelect } from "@/components/ui/Button";
import { Chip } from "@/components/ui/Chip";
import { TrendArea, HighlightBars, Donut, LegendList } from "@/components/ui/Charts";
import { api, getToken, type Mode } from "@/lib/api";
import { dur, num, pct, usd } from "@/lib/cn";

type Summary = {
  total_campaigns: number; total_calls: number; answered: number;
  answer_rate: number; voicemail: number; interested: number;
  not_interested: number; transferred: number; callbacks: number;
  meetings: number; avg_duration_sec: number; ai_speaking_sec: number;
  conversion_rate: number; cost_usd: number;
};

type Latency = {
  turns: number; p50_ms: number; p95_ms: number;
  stt_p50_ms: number; llm_p50_ms: number; tts_p50_ms: number;
  cache_hit_rate: number;
};

type CampaignRow = {
  id: string; name: string; type: string; status: string;
  leads: number; calls: number; answered: number;
  interested: number; meetings: number; conversion: number;
};

export default function Analytics() {
  const { mode } = useParams<{ mode: Mode }>();
  const [days, setDays] = useState("30");
  const [summary, setSummary] = useState<Summary | null>(null);
  const [trend, setTrend] = useState<Record<string, number | string>[]>([]);
  const [outcomes, setOutcomes] = useState<{ name: string; value: number }[]>([]);
  const [hourly, setHourly] = useState<{ hour: number; rate: number; calls: number }[]>([]);
  const [latency, setLatency] = useState<Latency | null>(null);
  const [campaigns, setCampaigns] = useState<CampaignRow[]>([]);

  const [error, setError] = useState("");

  useEffect(() => {
    const q = `days=${days}&mode=${mode}`;
    setError("");
    Promise.all([
      api.get<Summary>(`/analytics/summary?${q}`),
      api.get<Record<string, number | string>[]>(`/analytics/trend?${q}`),
      api.get<{ name: string; value: number }[]>(`/analytics/outcomes?days=${days}`),
      api.get<{ hour: number; rate: number; calls: number }[]>(`/analytics/hourly?days=${days}`),
      api.get<Latency>(`/analytics/latency?days=${days}`),
      api.get<CampaignRow[]>(`/analytics/campaigns?mode=${mode}`),
    ]).then(([s, t, o, h, l, c]) => {
      setSummary(s); setTrend(t); setOutcomes(o);
      setHourly(h); setLatency(l); setCampaigns(c);
    }).catch((e) => {
      // Swallowing this left a permanent spinner with no explanation — the
      // failure has to reach the screen, not just the console.
      setError(e instanceof Error ? e.message : "Could not load analytics");
    });
  }, [days, mode]);

  function exportCsv() {
    fetch(`${process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"}/exports/calls.csv?days=${days}`,
          { headers: { Authorization: `Bearer ${getToken()}` } })
      .then((r) => r.blob())
      .then((b) => {
        const a = document.createElement("a");
        a.href = URL.createObjectURL(b);
        a.download = `calls-${days}d.csv`;
        a.click();
        URL.revokeObjectURL(a.href);
      });
  }

  if (error) {
    return (
      <Card className="mx-auto mt-12 max-w-md text-center">
        <p className="font-medium text-neg">Could not load analytics</p>
        <p className="mt-1 text-base text-muted">{error}</p>
        <Button className="mt-3" onClick={() => location.reload()}>Retry</Button>
      </Card>
    );
  }

  if (!summary) {
    return (
      <div className="grid place-items-center py-24 text-muted">
        <Loader2 size={20} className="animate-spin" />
      </div>
    );
  }

  const totalOutcomes = outcomes.reduce((s, o) => s + o.value, 0);
  const peak = hourly.reduce((b, h, i, a) => (h.rate > a[b].rate ? i : b), 0);

  return (
    <>
      <PageHeader title="Analytics" subtitle="Campaign performance and call quality.">
        <PillSelect
          value={days}
          onChange={setDays}
          options={[
            { value: "7", label: "Last 7 days" },
            { value: "30", label: "Last 30 days" },
            { value: "90", label: "Last 90 days" },
          ]}
        />
        <Button onClick={exportCsv}><Download size={13} /> Export CSV</Button>
      </PageHeader>

      <div className="grid grid-cols-2 gap-card lg:grid-cols-4">
        <StatCard icon={PhoneOutgoing} label="Total calls" value={num(summary.total_calls)} />
        <StatCard icon={Target} label="Answer rate" value={pct(summary.answer_rate)} />
        <StatCard icon={CalendarCheck} label="Meetings booked" value={num(summary.meetings)} />
        <StatCard icon={Gauge} label="Conversion" value={pct(summary.conversion_rate)} />
      </div>

      <Card className="mt-card" pad={false}>
        <dl className="grid grid-cols-2 divide-line sm:grid-cols-3 lg:grid-cols-6 lg:divide-x">
          {[
            ["Campaigns", num(summary.total_campaigns)],
            ["Answered", num(summary.answered)],
            ["Interested", num(summary.interested)],
            ["Voicemails", num(summary.voicemail)],
            ["Avg duration", dur(summary.avg_duration_sec)],
            ["Spend", usd(summary.cost_usd)],
          ].map(([k, v]) => (
            <div key={k} className="px-card py-3.5">
              <dt className="text-sm text-muted">{k}</dt>
              <dd className="tnum mt-0.5 text-lg font-semibold text-ink">{v}</dd>
            </div>
          ))}
        </dl>
      </Card>

      {/* Latency — the project's stated success metric, given its own panel. */}
      {latency && latency.turns > 0 && (
        <Card className="mt-card">
          <div className="mb-3 flex items-center justify-between">
            <div>
              <h3 className="flex items-center gap-1.5 text-base font-semibold text-ink">
                <Zap size={14} className="text-primary" /> Conversation latency
              </h3>
              <p className="text-sm text-muted">
                Time from the caller finishing to the agent speaking, over {num(latency.turns)} turns.
              </p>
            </div>
            <Chip tone={latency.p50_ms < 1200 ? "pos" : latency.p50_ms < 2000 ? "warn" : "neg"}>
              p50 {latency.p50_ms}ms
            </Chip>
          </div>

          <div className="grid grid-cols-2 gap-3 sm:grid-cols-5">
            {[
              ["p50", `${latency.p50_ms}ms`, "median"],
              ["p95", `${latency.p95_ms}ms`, "worst 5%"],
              ["Speech-to-text", `${latency.stt_p50_ms}ms`, "transcription"],
              ["Model", `${latency.llm_p50_ms}ms`, "reply + labels"],
              ["Text-to-speech", `${latency.tts_p50_ms}ms`, "synthesis"],
            ].map(([k, v, hint]) => (
              <div key={k} className="rounded-card bg-sunk px-3 py-2.5">
                <p className="text-sm text-muted">{k}</p>
                <p className="tnum text-lg font-semibold text-ink">{v}</p>
                <p className="text-tiny text-faint">{hint}</p>
              </div>
            ))}
          </div>

          <div className="mt-3 flex items-center justify-between border-t border-line pt-3">
            <span className="text-sm text-muted">Prompt cache hit rate</span>
            <Chip tone={latency.cache_hit_rate > 0.8 ? "pos" : "warn"}>
              {pct(latency.cache_hit_rate)}
            </Chip>
          </div>
          {latency.cache_hit_rate < 0.8 && (
            <p className="mt-2 rounded-md bg-warn-wash px-3 py-2 text-sm text-warn">
              Cache hits are low. Something per-call has probably entered the system
              prompt, which costs both latency and roughly ten times the tokens.
            </p>
          )}
        </Card>
      )}

      <div className="mt-card grid gap-card lg:grid-cols-3">
        <ChartCard className="lg:col-span-2" title="Calls over time" icon={TrendingUp}>
          <TrendArea
            data={trend}
            x="d"
            series={[
              { key: "calls", label: "Calls" },
              { key: "answered", label: "Answered" },
              { key: "interested", label: "Interested" },
            ]}
          />
        </ChartCard>

        <ChartCard title="Outcome split">
          <Donut data={outcomes.slice(0, 6)} centerValue={num(totalOutcomes)} centerLabel="Calls" />
          <div className="mt-4 border-t border-line pt-4">
            <LegendList
              items={outcomes.slice(0, 6).map((o) => ({
                name: o.name.replace(/_/g, " "),
                value: `${num(o.value)} · ${((o.value / totalOutcomes) * 100).toFixed(1)}%`,
              }))}
            />
          </div>
        </ChartCard>
      </div>

      <div className="mt-card grid gap-card lg:grid-cols-3">
        <ChartCard
          title="Best time to call"
          icon={Clock}
          lead={hourly.length ? {
            value: `${hourly[peak].hour}:00`,
            caption: `${pct(hourly[peak].rate)} answer rate — your strongest hour`,
          } : undefined}
        >
          <HighlightBars
            data={hourly.map((h) => ({ h: `${h.hour}:00`, answered: Math.round(h.rate * 100) }))}
            x="h"
            y="answered"
            highlight={peak}
          />
        </ChartCard>

        <Card className="lg:col-span-2" pad={false}>
          <div className="border-b border-line px-card py-3">
            <h3 className="text-base font-semibold text-ink">Campaign comparison</h3>
          </div>
          <div className="overflow-x-auto px-card py-2">
            <table className="w-full text-base">
              <thead className="bg-sunk">
                <tr>
                  {["Campaign", "Leads", "Calls", "Answered", "Meetings", "Conv."].map((h, i) => (
                    <th
                      key={h}
                      className={`px-3 py-2 text-micro font-semibold uppercase tracking-wider text-faint ${i ? "text-right" : "text-left"}`}
                    >
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {campaigns.map((c) => (
                  <tr key={c.id} className="border-b border-line last:border-0">
                    <td className="px-3 py-2.5">
                      <span className="block font-medium text-ink">{c.name}</span>
                      <span className="block text-sm text-muted">
                        {c.type?.replace(/_/g, " ")}
                      </span>
                    </td>
                    <td className="tnum px-3 py-2.5 text-right">{num(c.leads)}</td>
                    <td className="tnum px-3 py-2.5 text-right">{num(c.calls)}</td>
                    <td className="tnum px-3 py-2.5 text-right">{num(c.answered)}</td>
                    <td className="tnum px-3 py-2.5 text-right">{num(c.meetings)}</td>
                    <td className="px-3 py-2.5 text-right">
                      <Chip tone={c.conversion > 20 ? "pos" : c.conversion > 8 ? "warn" : "neutral"}>
                        {c.conversion.toFixed(1)}%
                      </Chip>
                    </td>
                  </tr>
                ))}
                {campaigns.length === 0 && (
                  <tr>
                    <td colSpan={6} className="px-3 py-10 text-center text-muted">
                      No campaigns to compare yet.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </Card>
      </div>
    </>
  );
}
