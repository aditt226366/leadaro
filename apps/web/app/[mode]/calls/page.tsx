"use client";
import { useCallback, useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { Download, Loader2, PlayCircle } from "lucide-react";
import { PageHeader } from "@/components/shell/TopBar";
import { Card } from "@/components/ui/Card";
import { Button, PillSelect } from "@/components/ui/Button";
import { Chip } from "@/components/ui/Chip";
import { DataTable, IconCell, type Column } from "@/components/ui/DataTable";
import { api, getToken, type Mode } from "@/lib/api";
import { dur, num } from "@/lib/cn";

type Row = {
  id: string;
  outcome?: string | null;
  answered_by: string;
  direction: string;
  started_at: string;
  duration_sec?: number | null;
  recording_url?: string | null;
  first_name?: string | null;
  last_name?: string | null;
  company?: string | null;
  phone?: string | null;
  campaign_name?: string | null;
  lead_tier?: string | null;
};

const POSITIVE = ["interested", "very_interested", "qualified", "meeting_scheduled", "booked_demo"];
const NEGATIVE = ["not_interested", "wrong_number", "do_not_call", "spam", "disqualified"];

export default function CallHistory() {
  const { mode } = useParams<{ mode: Mode }>();
  const router = useRouter();
  const [rows, setRows] = useState<Row[]>([]);
  const [outcome, setOutcome] = useState("");
  const [answered, setAnswered] = useState("");
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    const p = new URLSearchParams({ limit: "150" });
    if (outcome) p.set("outcome", outcome);
    if (answered) p.set("answered_by", answered);
    try {
      setRows(await api.get<Row[]>(`/calls?${p}`));
    } finally {
      setLoading(false);
    }
  }, [outcome, answered]);

  useEffect(() => { void load(); }, [load]);

  function exportCsv() {
    fetch(`${process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"}/exports/calls.csv?days=90`,
          { headers: { Authorization: `Bearer ${getToken()}` } })
      .then((r) => r.blob())
      .then((b) => {
        const a = document.createElement("a");
        a.href = URL.createObjectURL(b);
        a.download = "calls.csv";
        a.click();
        URL.revokeObjectURL(a.href);
      });
  }

  const columns: Column<Row>[] = [
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
    { key: "campaign_name", header: "Campaign", cell: (r) => r.campaign_name ?? "—" },
    {
      key: "direction",
      header: "Direction",
      cell: (r) => <Chip tone={r.direction === "inbound" ? "info" : "neutral"}>{r.direction}</Chip>,
    },
    {
      key: "outcome",
      header: "Outcome",
      cell: (r) => (
        <Chip
          tone={
            POSITIVE.includes(r.outcome ?? "") ? "pos"
            : NEGATIVE.includes(r.outcome ?? "") ? "neg" : "neutral"
          }
        >
          {(r.outcome ?? "—").replace(/_/g, " ")}
        </Chip>
      ),
    },
    {
      key: "lead_tier",
      header: "Tier",
      cell: (r) => r.lead_tier
        ? <Chip tone={r.lead_tier === "hot" ? "neg" : r.lead_tier === "warm" ? "warn" : "neutral"}>{r.lead_tier}</Chip>
        : <span className="text-muted">—</span>,
    },
    {
      key: "duration_sec",
      header: "Duration",
      align: "right",
      cell: (r) => (r.duration_sec ? dur(r.duration_sec) : "—"),
    },
    {
      key: "recording",
      header: "",
      align: "center",
      width: "44px",
      cell: (r) => r.recording_url
        ? <PlayCircle size={15} className="mx-auto text-primary-ink" />
        : <span className="text-faint">—</span>,
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
      <PageHeader title="Call History" subtitle="Every call placed and received.">
        <PillSelect
          value={outcome}
          onChange={setOutcome}
          options={[
            { value: "", label: "All outcomes" },
            ...["interested", "not_interested", "meeting_scheduled", "callback",
                "voicemail", "no_answer", "wrong_number", "transferred"]
              .map((o) => ({ value: o, label: o.replace(/_/g, " ") })),
          ]}
        />
        <PillSelect
          value={answered}
          onChange={setAnswered}
          options={[
            { value: "", label: "Anyone" },
            { value: "human", label: "Human answered" },
            { value: "machine", label: "Machine" },
            { value: "unknown", label: "No answer" },
          ]}
        />
        <Button onClick={exportCsv}><Download size={13} /> Export</Button>
      </PageHeader>

      <Card pad={false}>
        <div className="flex items-center justify-between border-b border-line px-card py-3">
          <h3 className="text-base font-semibold text-ink">Calls</h3>
          <span className="text-sm text-muted">{num(rows.length)} shown</span>
        </div>
        <div className="px-card py-2">
          {loading ? (
            <div className="grid place-items-center py-16 text-muted">
              <Loader2 size={18} className="animate-spin" />
            </div>
          ) : (
            <DataTable
              columns={columns}
              rows={rows}
              onRowClick={(r) => router.push(`/${mode}/calls/${r.id}`)}
              empty="No calls yet."
            />
          )}
        </div>
      </Card>
    </>
  );
}
