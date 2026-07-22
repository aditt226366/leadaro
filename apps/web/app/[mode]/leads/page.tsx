"use client";
import { useCallback, useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { Search, Upload, Download, Plus, Loader2, ShieldBan, Phone } from "lucide-react";
import { PageHeader } from "@/components/shell/TopBar";
import { Card } from "@/components/ui/Card";
import { Button, PillSelect } from "@/components/ui/Button";
import { Chip } from "@/components/ui/Chip";
import { DataTable, IconCell, type Column } from "@/components/ui/DataTable";
import { Input } from "@/components/ui/Form";
import { api, getToken, type Lead, type Mode } from "@/lib/api";
import { num } from "@/lib/cn";

export default function LeadsPage() {
  const { mode } = useParams<{ mode: Mode }>();
  const router = useRouter();
  const [rows, setRows] = useState<Lead[]>([]);
  const [q, setQ] = useState("");
  const [tier, setTier] = useState("");
  const [loading, setLoading] = useState(true);
  const [msg, setMsg] = useState("");
  const [error, setError] = useState("");
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [callingId, setCallingId] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const p = new URLSearchParams({ limit: "200" });
      if (q) p.set("q", q);
      const all = await api.get<Lead[]>(`/leads?${p}`);
      setRows(tier ? all.filter((l) => l.tier === tier) : all);
      setError("");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not load leads");
    } finally {
      setLoading(false);
    }
  }, [q, tier]);

  useEffect(() => {
    const t = setTimeout(load, q ? 300 : 0);
    return () => clearTimeout(t);
  }, [load, q]);

  async function upload(file: File) {
    setMsg("");
    setError("");
    try {
      const fd = new FormData();
      fd.append("file", file);
      const r = await api.upload<{
        accepted: number; invalid: number; duplicates: number;
      }>("/leads/import", fd);
      setMsg(`${num(r.accepted)} imported · ${num(r.duplicates)} duplicates · ${num(r.invalid)} invalid`);
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Import failed");
    }
  }

  async function suppress() {
    const picked = rows.filter((r) => selected.has(r.id));
    for (const l of picked) {
      await api.post("/suppression", { phone: l.phone, kind: "dnc", reason: "manual" });
    }
    setMsg(`${picked.length} number(s) added to the Do Not Call list`);
    setSelected(new Set());
  }

  async function callNow(lead: Lead) {
    setCallingId(lead.id);
    setError("");
    setMsg("");
    try {
      const r = await api.post<{ call_id: string }>("/calls/originate", { lead_id: lead.id });
      const name = [lead.first_name, lead.last_name].filter(Boolean).join(" ") || lead.phone;
      setMsg(`Calling ${name}…`);
      router.push(`/${mode}/monitor?call=${r.call_id}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not place call");
    } finally {
      setCallingId(null);
    }
  }

  function exportCsv() {
    const url = `${process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"}/exports/leads.csv`;
    fetch(url, { headers: { Authorization: `Bearer ${getToken()}` } })
      .then((r) => r.blob())
      .then((b) => {
        const a = document.createElement("a");
        a.href = URL.createObjectURL(b);
        a.download = "leads.csv";
        a.click();
        URL.revokeObjectURL(a.href);
      });
  }

  const columns: Column<Lead>[] = [
    {
      key: "name",
      header: "Lead",
      cell: (r) => (
        <IconCell
          icon={([r.first_name, r.last_name].filter(Boolean).join(" ") || r.phone)
            .slice(0, 2).toUpperCase()}
          title={[r.first_name, r.last_name].filter(Boolean).join(" ") || "—"}
          subtitle={r.phone}
        />
      ),
    },
    { key: "company", header: "Company", cell: (r) => r.company ?? "—" },
    { key: "designation", header: "Title", cell: (r) => r.designation ?? "—" },
    { key: "industry", header: "Industry", cell: (r) => r.industry ?? "—" },
    {
      key: "location",
      header: "Location",
      cell: (r) => [r.city, r.country].filter(Boolean).join(", ") || "—",
    },
    {
      key: "tier",
      header: "Tier",
      cell: (r) =>
        r.tier ? (
          <Chip tone={r.tier === "hot" ? "neg" : r.tier === "warm" ? "warn" : "neutral"}>
            {r.tier}
          </Chip>
        ) : <span className="text-muted">—</span>,
    },
    { key: "lead_score", header: "Score", align: "right", cell: (r) => String(r.lead_score) },
    {
      key: "actions",
      header: "",
      align: "right",
      cell: (r) => (
        <div className="flex items-center justify-end" onClick={(e) => e.stopPropagation()}>
          {callingId === r.id ? (
            <Loader2 size={14} className="animate-spin text-muted" />
          ) : (
            <Button variant="ghost" onClick={() => callNow(r)} title="Call now">
              <Phone size={13} /> Call
            </Button>
          )}
        </div>
      ),
    },
  ];

  return (
    <>
      <PageHeader title="Leads" subtitle="Everyone your campaigns can reach.">
        <PillSelect
          value={tier}
          onChange={setTier}
          options={[
            { value: "", label: "All tiers" },
            { value: "hot", label: "Hot" },
            { value: "warm", label: "Warm" },
            { value: "scrap", label: "Scrap" },
          ]}
        />
        <label>
          <input
            type="file"
            accept=".csv"
            className="hidden"
            onChange={(e) => e.target.files?.[0] && upload(e.target.files[0])}
          />
          <span className="inline-flex h-7 cursor-pointer items-center gap-1.5 rounded-pill border border-line-strong bg-surface px-2.5 text-sm font-medium text-ink hover:bg-sunk">
            <Upload size={13} /> Import CSV
          </span>
        </label>
        <Button onClick={exportCsv}><Download size={13} /> Export</Button>
      </PageHeader>

      <Card pad={false}>
        <div className="flex flex-wrap items-center gap-3 border-b border-line px-card py-3">
          <label className="relative flex h-8 min-w-[220px] flex-1 items-center">
            <Search size={14} className="absolute left-2.5 text-faint" />
            <Input
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder="Search by name, company or number…"
              className="h-8 pl-8"
            />
          </label>
          <span className="text-sm text-muted">{num(rows.length)} leads</span>
          {selected.size > 0 && (
            <Button variant="danger" onClick={suppress}>
              <ShieldBan size={13} /> Add {selected.size} to DNC
            </Button>
          )}
        </div>

        {msg && <p className="border-b border-line bg-pos-wash px-card py-2 text-sm text-pos">{msg}</p>}
        {error && <p className="border-b border-line bg-neg-wash px-card py-2 text-sm text-neg">{error}</p>}

        <div className="px-card py-2">
          {loading ? (
            <div className="grid place-items-center py-16 text-muted">
              <Loader2 size={18} className="animate-spin" />
            </div>
          ) : (
            <DataTable
              columns={columns}
              rows={rows}
              selectable
              selected={selected}
              onSelect={setSelected}
              empty="No leads match. Import a CSV to get started."
            />
          )}
        </div>
      </Card>
    </>
  );
}
