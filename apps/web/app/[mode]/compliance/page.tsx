"use client";
import { useCallback, useEffect, useState } from "react";
import {
  ShieldBan, Upload, Plus, Trash2, ScrollText, Loader2, Search, ShieldCheck,
} from "lucide-react";
import { PageHeader } from "@/components/shell/TopBar";
import { Card } from "@/components/ui/Card";
import { Button, PillSelect } from "@/components/ui/Button";
import { Chip } from "@/components/ui/Chip";
import { Input } from "@/components/ui/Form";
import { api } from "@/lib/api";
import { num } from "@/lib/cn";

type Suppression = {
  id: string; phone: string; kind: string;
  reason?: string | null; created_at: string;
};

type AuditRow = {
  id: number; action: string; entity?: string | null;
  entity_id?: string | null; detail: Record<string, unknown>;
  created_at: string; actor_name?: string | null; actor_email?: string | null;
};

export default function Compliance() {
  const [tab, setTab] = useState<"suppression" | "audit">("suppression");
  const [rows, setRows] = useState<Suppression[]>([]);
  const [audit, setAudit] = useState<AuditRow[]>([]);
  const [kind, setKind] = useState("");
  const [q, setQ] = useState("");
  const [phone, setPhone] = useState("");
  const [loading, setLoading] = useState(true);
  const [msg, setMsg] = useState("");
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const p = new URLSearchParams();
      if (kind) p.set("kind", kind);
      if (q) p.set("q", q);
      const [s, a] = await Promise.all([
        api.get<Suppression[]>(`/suppression?${p}`),
        api.get<AuditRow[]>("/audit?limit=150"),
      ]);
      setRows(s);
      setAudit(a);
      setError("");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not load compliance data");
    } finally {
      setLoading(false);
    }
  }, [kind, q]);

  useEffect(() => {
    const t = setTimeout(load, q ? 300 : 0);
    return () => clearTimeout(t);
  }, [load, q]);

  async function add() {
    if (!phone.trim()) return;
    try {
      await api.post("/suppression", { phone, kind: "dnc", reason: "added manually" });
      setPhone("");
      setMsg("Number suppressed. It cannot be dialled by any campaign.");
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not add number");
    }
  }

  async function bulk(file: File) {
    try {
      const fd = new FormData();
      fd.append("file", file);
      const r = await api.upload<{ imported: number }>("/suppression/import", fd);
      setMsg(`${num(r.imported)} numbers added to the suppression list`);
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Import failed");
    }
  }

  return (
    <>
      <PageHeader
        title="Compliance"
        subtitle="Suppression lists and the audit trail. Enforced before every dial."
      >
        <PillSelect
          value={kind}
          onChange={setKind}
          options={[
            { value: "", label: "All kinds" },
            { value: "dnc", label: "Do Not Call" },
            { value: "opt_out", label: "Opted out" },
            { value: "blacklist", label: "Blacklisted" },
          ]}
        />
        <label>
          <input
            type="file"
            accept=".csv,.txt"
            className="hidden"
            onChange={(e) => e.target.files?.[0] && bulk(e.target.files[0])}
          />
          <span className="inline-flex h-7 cursor-pointer items-center gap-1.5 rounded-pill border border-line-strong bg-surface px-2.5 text-sm font-medium text-ink hover:bg-sunk">
            <Upload size={13} /> Bulk import
          </span>
        </label>
      </PageHeader>

      <div className="mb-card flex gap-1 rounded-pill border border-line bg-surface p-1">
        {([["suppression", "Suppression list", rows.length],
           ["audit", "Audit log", audit.length]] as const).map(([k, label, n]) => (
          <button
            key={k}
            onClick={() => setTab(k)}
            className={`flex-1 rounded-[6px] py-1.5 text-sm font-medium transition-colors ${
              tab === k ? "bg-primary-wash text-primary-ink" : "text-muted hover:text-ink"
            }`}
          >
            {label} <span className="tnum text-faint">({num(n)})</span>
          </button>
        ))}
      </div>

      {msg && <p className="mb-card rounded-card bg-pos-wash px-4 py-2.5 text-base text-pos">{msg}</p>}
      {error && <p className="mb-card rounded-card bg-neg-wash px-4 py-2.5 text-base text-neg">{error}</p>}

      {tab === "suppression" ? (
        <div className="grid gap-card lg:grid-cols-[1fr_300px]">
          <Card pad={false}>
            <div className="flex items-center gap-3 border-b border-line px-card py-3">
              <label className="relative flex h-8 flex-1 items-center">
                <Search size={14} className="absolute left-2.5 text-faint" />
                <Input
                  value={q}
                  onChange={(e) => setQ(e.target.value)}
                  placeholder="Search numbers…"
                  className="h-8 pl-8"
                />
              </label>
              <span className="text-sm text-muted">{num(rows.length)} suppressed</span>
            </div>

            {loading ? (
              <div className="grid place-items-center py-16 text-muted">
                <Loader2 size={18} className="animate-spin" />
              </div>
            ) : (
              <ul className="divide-y divide-line">
                {rows.map((r) => (
                  <li key={r.id} className="flex items-center gap-3 px-card py-2.5">
                    <ShieldBan size={14} className="shrink-0 text-neg" />
                    <span className="tnum min-w-0 flex-1 font-medium text-ink">{r.phone}</span>
                    <Chip tone={r.kind === "blacklist" ? "neg" : "warn"}>
                      {r.kind.replace("_", " ")}
                    </Chip>
                    <span className="hidden w-40 truncate text-sm text-muted sm:block">
                      {r.reason ?? "—"}
                    </span>
                    <Button
                      variant="ghost"
                      aria-label="Remove suppression"
                      onClick={async () => {
                        await api.del(`/suppression/${r.id}`);
                        setMsg("Suppression removed — this number is callable again.");
                        await load();
                      }}
                    >
                      <Trash2 size={13} />
                    </Button>
                  </li>
                ))}
                {rows.length === 0 && (
                  <li className="px-card py-12 text-center text-base text-muted">
                    Nothing suppressed yet.
                  </li>
                )}
              </ul>
            )}
          </Card>

          <div className="space-y-card">
            <Card>
              <h3 className="mb-2 text-base font-semibold text-ink">Add a number</h3>
              <Input
                value={phone}
                onChange={(e) => setPhone(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && add()}
                placeholder="+14155550123"
              />
              <Button variant="primary" className="mt-2 w-full" onClick={add}>
                <Plus size={13} /> Suppress
              </Button>
            </Card>

            <Card>
              <h3 className="mb-1.5 flex items-center gap-1.5 text-base font-semibold text-ink">
                <ShieldCheck size={14} className="text-pos" /> How this is enforced
              </h3>
              <p className="text-sm leading-relaxed text-muted">
                The dialer re-checks this list immediately before placing each
                call, not when the audience was built. A number added here is
                unreachable from that moment, even for a campaign already
                running. Every skip and every removal is written to the audit log.
              </p>
            </Card>
          </div>
        </div>
      ) : (
        <Card pad={false}>
          <div className="flex items-center gap-2 border-b border-line px-card py-3">
            <ScrollText size={14} className="text-muted" />
            <h3 className="text-base font-semibold text-ink">Audit log</h3>
            <span className="ml-auto text-sm text-muted">{num(audit.length)} entries</span>
          </div>
          <ul className="divide-y divide-line">
            {audit.map((a) => (
              <li key={a.id} className="flex items-start gap-3 px-card py-2.5">
                <Chip tone={a.action.includes("remove") || a.action.includes("archive")
                  ? "warn" : "neutral"}>
                  {a.action}
                </Chip>
                <span className="min-w-0 flex-1">
                  <span className="block text-base text-ink">
                    {a.actor_name ?? "System"}
                    {a.entity ? ` · ${a.entity}` : ""}
                  </span>
                  {Object.keys(a.detail ?? {}).length > 0 && (
                    <span className="block truncate font-mono text-tiny text-muted">
                      {JSON.stringify(a.detail)}
                    </span>
                  )}
                </span>
                <span className="tnum shrink-0 text-sm text-muted">
                  {new Date(a.created_at).toLocaleString([], {
                    month: "short", day: "numeric", hour: "2-digit", minute: "2-digit",
                  })}
                </span>
              </li>
            ))}
            {audit.length === 0 && (
              <li className="px-card py-12 text-center text-base text-muted">
                No audit entries yet.
              </li>
            )}
          </ul>
        </Card>
      )}
    </>
  );
}
