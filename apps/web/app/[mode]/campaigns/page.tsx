"use client";
import { useCallback, useEffect, useMemo, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import {
  Plus, Search, SlidersHorizontal, Download, Copy, Pause, Play,
  Archive, MoreHorizontal, Loader2,
} from "lucide-react";
import { PageHeader } from "@/components/shell/TopBar";
import { Card } from "@/components/ui/Card";
import { Button, PillSelect } from "@/components/ui/Button";
import { Chip, StatusChip } from "@/components/ui/Chip";
import { DataTable, IconCell, MiniBar, type Column } from "@/components/ui/DataTable";
import { api, type Campaign, type Mode } from "@/lib/api";
import { num } from "@/lib/cn";

const STATUSES = [
  { value: "", label: "All statuses" },
  { value: "draft", label: "Draft" },
  { value: "scheduled", label: "Scheduled" },
  { value: "active", label: "Active" },
  { value: "paused", label: "Paused" },
  { value: "completed", label: "Completed" },
];

export default function CampaignsPage() {
  const { mode } = useParams<{ mode: Mode }>();
  const router = useRouter();

  const [rows, setRows] = useState<Campaign[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [q, setQ] = useState("");
  const [status, setStatus] = useState("");
  const [sort, setSort] = useState("recent");
  const [busyId, setBusyId] = useState<string | null>(null);
  const [selected, setSelected] = useState<Set<string>>(new Set());

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const p = new URLSearchParams({ mode });
      if (status) p.set("status", status);
      if (q) p.set("q", q);
      setRows(await api.get<Campaign[]>(`/campaigns?${p}`));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load campaigns");
    } finally {
      setLoading(false);
    }
  }, [mode, status, q]);

  useEffect(() => {
    // Debounce so typing in the search box doesn't fire a request per keystroke.
    const t = setTimeout(load, q ? 300 : 0);
    return () => clearTimeout(t);
  }, [load, q]);

  const sorted = useMemo(() => {
    const c = [...rows];
    if (sort === "name") c.sort((a, b) => a.name.localeCompare(b.name));
    if (sort === "leads") c.sort((a, b) => (b.lead_count ?? 0) - (a.lead_count ?? 0));
    return c;
  }, [rows, sort]);

  async function act(id: string, action: "clone" | "pause" | "resume" | "archive") {
    setBusyId(id);
    try {
      if (action === "clone") await api.post(`/campaigns/${id}/clone`);
      else if (action === "archive") await api.del(`/campaigns/${id}`);
      else await api.patch(`/campaigns/${id}`, {
        status: action === "pause" ? "paused" : "active",
      });
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Action failed");
    } finally {
      setBusyId(null);
    }
  }

  const columns: Column<Campaign>[] = [
    {
      key: "name",
      header: "Campaign",
      cell: (r) => (
        <IconCell
          icon={r.name.slice(0, 2).toUpperCase()}
          title={r.name}
          subtitle={r.type?.replace(/_/g, " ") ?? "—"}
        />
      ),
    },
    { key: "status", header: "Status", cell: (r) => <StatusChip status={r.status} /> },
    {
      key: "priority",
      header: "Priority",
      cell: (r) => (
        <Chip tone={r.priority === "urgent" ? "neg" : r.priority === "high" ? "warn" : "neutral"}>
          {r.priority}
        </Chip>
      ),
    },
    {
      key: "lead_count",
      header: "Leads",
      align: "right",
      cell: (r) => num(r.lead_count ?? 0),
    },
    {
      key: "progress",
      header: "Progress",
      cell: (r) => {
        const total = r.lead_count ?? 0;
        const done = (r as Campaign & { done_count?: number }).done_count ?? 0;
        return <MiniBar value={total ? (done / total) * 100 : 0} />;
      },
    },
    { key: "timezone", header: "Timezone", cell: (r) => r.timezone },
    {
      key: "actions",
      header: "",
      align: "right",
      width: "150px",
      cell: (r) => (
        <div className="flex items-center justify-end gap-1" onClick={(e) => e.stopPropagation()}>
          {busyId === r.id ? (
            <Loader2 size={14} className="animate-spin text-muted" />
          ) : (
            <>
              {r.status === "active" ? (
                <Button variant="ghost" onClick={() => act(r.id, "pause")} title="Pause">
                  <Pause size={13} />
                </Button>
              ) : (
                <Button
                  variant="ghost"
                  onClick={() => act(r.id, "resume")}
                  title="Resume"
                  disabled={r.status === "completed"}
                >
                  <Play size={13} />
                </Button>
              )}
              <Button variant="ghost" onClick={() => act(r.id, "clone")} title="Duplicate">
                <Copy size={13} />
              </Button>
              <Button variant="ghost" onClick={() => act(r.id, "archive")} title="Archive">
                <Archive size={13} />
              </Button>
            </>
          )}
        </div>
      ),
    },
  ];

  return (
    <>
      <PageHeader
        title="Campaigns"
        subtitle={
          mode === "voice"
            ? "AI voice campaigns — every call handled by an AI agent."
            : "Call campaigns — AI, human agents, or a hybrid of both."
        }
      >
        <PillSelect
          value={status}
          onChange={setStatus}
          options={STATUSES}
        />
        <PillSelect
          value={sort}
          onChange={setSort}
          options={[
            { value: "recent", label: "Most recent" },
            { value: "name", label: "Name" },
            { value: "leads", label: "Lead count" },
          ]}
        />
        <Button><Download size={13} /> Export</Button>
        <Button
          variant="primary"
          onClick={() => router.push(`/${mode}/campaigns/new`)}
        >
          <Plus size={13} /> Create Campaign
        </Button>
      </PageHeader>

      <Card pad={false}>
        <div className="flex items-center gap-3 border-b border-line px-card py-3">
          <label className="relative flex h-8 flex-1 items-center">
            <Search size={14} className="absolute left-2.5 text-faint" />
            <input
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder="Search campaigns by name…"
              className="h-full w-full rounded-pill border border-line-strong bg-surface pl-8 pr-3 text-base outline-none focus:border-primary/40 focus:ring-2 focus:ring-primary/15"
            />
          </label>
          {selected.size > 0 && (
            <Chip tone="primary">{selected.size} selected</Chip>
          )}
          <Button><SlidersHorizontal size={13} /> Filter</Button>
        </div>

        {error && (
          <p className="border-b border-line bg-neg-wash px-card py-2 text-sm text-neg">
            {error}
          </p>
        )}

        <div className="px-card py-2">
          {loading ? (
            <div className="grid place-items-center py-16 text-muted">
              <Loader2 size={18} className="animate-spin" />
            </div>
          ) : (
            <DataTable
              columns={columns}
              rows={sorted}
              selectable
              selected={selected}
              onSelect={setSelected}
              onRowClick={(r) => router.push(`/${mode}/campaigns/${r.id}`)}
              empty={
                <div className="py-6">
                  <p className="font-medium text-ink">No campaigns yet</p>
                  <p className="mt-1 text-muted">
                    Create your first {mode === "voice" ? "voice" : "call"} campaign to start reaching leads.
                  </p>
                  <Button
                    variant="primary"
                    className="mt-3"
                    onClick={() => router.push(`/${mode}/campaigns/new`)}
                  >
                    <Plus size={13} /> Create Campaign
                  </Button>
                </div>
              }
            />
          )}
        </div>
      </Card>
    </>
  );
}
