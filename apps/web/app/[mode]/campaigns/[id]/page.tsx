"use client";
import { useCallback, useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import {
  Play, Pause, Copy, Archive, PhoneOutgoing, Target, CalendarCheck,
  Voicemail, Loader2, Settings2, ChevronRight, Radio,
} from "lucide-react";
import { PageHeader } from "@/components/shell/TopBar";
import { Card, StatCard, ChartCard } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Chip, StatusChip } from "@/components/ui/Chip";
import { DataTable, IconCell, type Column } from "@/components/ui/DataTable";
import { TrendArea, Donut, LegendList } from "@/components/ui/Charts";
import { LiveDot } from "@/components/ui/Waveform";
import { CallLauncher } from "@/components/calls/CallLauncher";
import { useLiveCalls } from "@/lib/useLiveCalls";
import { api, type Campaign, type Mode } from "@/lib/api";
import { dur, num, usd } from "@/lib/cn";

type CallRow = {
  id: string;
  outcome?: string | null;
  answered_by: string;
  started_at: string;
  duration_sec?: number | null;
  first_name?: string | null;
  last_name?: string | null;
  company?: string | null;
  phone?: string | null;
  lead_tier?: string | null;
  summary?: string | null;
};

export default function CampaignDetail() {
  const { mode, id } = useParams<{ mode: Mode; id: string }>();
  const router = useRouter();

  const [campaign, setCampaign] = useState<Campaign | null>(null);
  const [calls, setCalls] = useState<CallRow[]>([]);
  const [trend, setTrend] = useState<Record<string, number | string>[]>([]);
  const [outcomes, setOutcomes] = useState<{ name: string; value: number }[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const { calls: live, connected } = useLiveCalls(id);

  const load = useCallback(async () => {
    try {
      const [c, cl, t, o] = await Promise.all([
        api.get<Campaign>(`/campaigns/${id}`),
        api.get<CallRow[]>(`/calls?campaign_id=${id}&limit=25`),
        api.get<Record<string, number | string>[]>(`/analytics/trend?days=30&mode=${mode}`),
        api.get<{ name: string; value: number }[]>("/analytics/outcomes?days=30"),
      ]);
      setCampaign(c);
      setCalls(cl);
      setTrend(t);
      setOutcomes(o);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not load campaign");
    }
  }, [id, mode]);

  useEffect(() => { void load(); }, [load]);

  async function act(action: "pause" | "resume" | "clone" | "archive") {
    setBusy(true);
    setError("");
    try {
      if (action === "clone") {
        const c = await api.post<Campaign>(`/campaigns/${id}/clone`);
        router.push(`/${mode}/campaigns/${c.id}`);
        return;
      }
      if (action === "archive") {
        await api.del(`/campaigns/${id}`);
        router.push(`/${mode}/campaigns`);
        return;
      }
      await api.patch(`/campaigns/${id}`, {
        status: action === "pause" ? "paused" : "active",
      });
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Action failed");
    } finally {
      setBusy(false);
    }
  }

  if (!campaign) {
    return (
      <div className="grid place-items-center py-24 text-muted">
        {error ? (
          <p className="text-neg">{error}</p>
        ) : (
          <Loader2 size={20} className="animate-spin" />
        )}
      </div>
    );
  }

  const answered = calls.filter((c) => c.answered_by === "human").length;
  const meetings = calls.filter(
    (c) => c.outcome === "meeting_scheduled" || c.outcome === "booked_demo",
  ).length;
  const voicemail = calls.filter((c) => c.outcome === "voicemail").length;
  const totalOutcomes = outcomes.reduce((s, o) => s + o.value, 0);

  const columns: Column<CallRow>[] = [
    {
      key: "lead",
      header: "Lead",
      cell: (r) => (
        <IconCell
          icon={([r.first_name, r.last_name].filter(Boolean).join(" ") || r.phone || "?")
            .slice(0, 2).toUpperCase()}
          title={[r.first_name, r.last_name].filter(Boolean).join(" ") || r.phone || "Unknown"}
          subtitle={r.company ?? r.phone ?? "—"}
        />
      ),
    },
    {
      key: "outcome",
      header: "Outcome",
      cell: (r) => (
        <Chip
          tone={
            ["interested", "meeting_scheduled", "booked_demo", "qualified"].includes(r.outcome ?? "")
              ? "pos"
              : ["not_interested", "wrong_number", "do_not_call", "spam"].includes(r.outcome ?? "")
                ? "neg"
                : "neutral"
          }
        >
          {(r.outcome ?? "—").replace(/_/g, " ")}
        </Chip>
      ),
    },
    {
      key: "lead_tier",
      header: "Tier",
      cell: (r) =>
        r.lead_tier ? (
          <Chip tone={r.lead_tier === "hot" ? "neg" : r.lead_tier === "warm" ? "warn" : "neutral"}>
            {r.lead_tier}
          </Chip>
        ) : <span className="text-muted">—</span>,
    },
    {
      key: "duration_sec",
      header: "Duration",
      align: "right",
      cell: (r) => (r.duration_sec ? dur(r.duration_sec) : "—"),
    },
    {
      key: "started_at",
      header: "When",
      align: "right",
      cell: (r) => new Date(r.started_at).toLocaleString([], {
        month: "short", day: "numeric", hour: "2-digit", minute: "2-digit",
      }),
    },
  ];

  return (
    <>
      <PageHeader title={campaign.name} subtitle={campaign.description ?? undefined}>
        <StatusChip status={campaign.status} />
        {live.length > 0 && (
          <span className="flex items-center gap-1.5 rounded-pill border border-line-strong bg-surface px-2.5 py-1 text-sm">
            <LiveDot on={connected} />
            {num(live.length)} live
          </span>
        )}
        {campaign.status === "active" ? (
          <Button onClick={() => act("pause")} disabled={busy}>
            <Pause size={13} /> Pause
          </Button>
        ) : (
          <Button
            onClick={() => act("resume")}
            disabled={busy || campaign.status === "completed"}
          >
            <Play size={13} /> Resume
          </Button>
        )}
        <Button onClick={() => act("clone")} disabled={busy}><Copy size={13} /> Duplicate</Button>
        <Button onClick={() => act("archive")} disabled={busy}><Archive size={13} /> Archive</Button>
        <CallLauncher mode={mode} campaignId={id} onPlaced={load} />
        <Button variant="primary" onClick={() => router.push(`/${mode}/monitor`)}>
          <Radio size={13} /> Live Monitor
        </Button>
      </PageHeader>

      {error && (
        <p className="mb-card rounded-card bg-neg-wash px-4 py-2.5 text-base text-neg">{error}</p>
      )}

      <div className="grid grid-cols-2 gap-card lg:grid-cols-4">
        <StatCard icon={PhoneOutgoing} label="Calls placed" value={num(calls.length)} />
        <StatCard icon={Target} label="Answered" value={num(answered)} />
        <StatCard icon={CalendarCheck} label="Meetings booked" value={num(meetings)} />
        <StatCard icon={Voicemail} label="Voicemails" value={num(voicemail)} />
      </div>

      <div className="mt-card grid gap-card lg:grid-cols-3">
        <ChartCard className="lg:col-span-2" title="Performance over time">
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

        <ChartCard title="Outcomes">
          <Donut
            data={outcomes.slice(0, 5)}
            centerValue={num(totalOutcomes)}
            centerLabel="Calls"
          />
          <div className="mt-4 border-t border-line pt-4">
            <LegendList
              items={outcomes.slice(0, 5).map((o) => ({
                name: o.name.replace(/_/g, " "),
                value: num(o.value),
              }))}
            />
          </div>
        </ChartCard>
      </div>

      <div className="mt-card grid gap-card lg:grid-cols-3">
        <Card className="lg:col-span-2" pad={false}>
          <div className="flex items-center justify-between border-b border-line px-card py-3">
            <h3 className="text-base font-semibold text-ink">Recent calls</h3>
            <a
              href={`/${mode}/calls?campaign_id=${id}`}
              className="text-sm font-semibold text-primary-ink hover:underline"
            >
              View all
            </a>
          </div>
          <div className="px-card py-2">
            <DataTable
              columns={columns}
              rows={calls}
              onRowClick={(r) => router.push(`/${mode}/calls/${r.id}`)}
              empty="No calls placed yet."
            />
          </div>
        </Card>

        <Card>
          <div className="mb-3 flex items-center justify-between">
            <h3 className="text-base font-semibold text-ink">Configuration</h3>
            <Settings2 size={14} className="text-muted" />
          </div>
          <dl className="space-y-2 text-sm">
            {[
              ["Type", campaign.type?.replace(/_/g, " ") ?? "—"],
              ["Goal", campaign.goal?.replace(/_/g, " ") ?? "—"],
              ["Voice type", campaign.voice_type],
              ["Language", campaign.language],
              ["Timezone", campaign.timezone],
              ["Calling hours",
                `${campaign.business_hours?.start ?? "09:00"} – ${campaign.business_hours?.end ?? "18:00"}`],
              ["Concurrency", String(campaign.concurrent_calls)],
              ["Calls / minute", String(campaign.calls_per_minute)],
              ["Daily cap", campaign.max_daily_calls ? num(campaign.max_daily_calls) : "None"],
              ["Warm-up", campaign.warmup_mode ? "On" : "Off"],
              ["Schedule", campaign.schedule_mode.replace(/_/g, " ")],
            ].map(([k, v]) => (
              <div key={k} className="flex justify-between gap-3">
                <dt className="text-muted">{k}</dt>
                <dd className="truncate font-medium capitalize text-ink">{v}</dd>
              </div>
            ))}
          </dl>

          {campaign.tags.length > 0 && (
            <div className="mt-3 flex flex-wrap gap-1.5 border-t border-line pt-3">
              {campaign.tags.map((t) => <Chip key={t}>{t}</Chip>)}
            </div>
          )}
        </Card>
      </div>
    </>
  );
}
