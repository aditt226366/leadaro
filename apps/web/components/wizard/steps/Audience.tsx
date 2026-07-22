"use client";
import { useCallback, useEffect, useState } from "react";
import {
  Upload, Database, Users, Globe, Linkedin, PencilLine, Plug, Loader2,
  AlertTriangle, ShieldBan, CircleSlash, CheckCircle2,
} from "lucide-react";
import { Card } from "@/components/ui/Card";
import { Field, Input, OptionCards, Select } from "@/components/ui/Form";
import { Button } from "@/components/ui/Button";
import { SectionTitle, StepSplit } from "../WizardShell";
import { api, type AudiencePreview, type Lead } from "@/lib/api";
import { num, usd } from "@/lib/cn";

type Source = "csv" | "crm" | "leadaro" | "apollo" | "linkedin" | "website" | "manual" | "api";

const SOURCES = [
  { value: "csv" as const, label: "Upload CSV", description: "Import a file of leads", icon: Upload },
  { value: "leadaro" as const, label: "Existing Leads", description: "Reuse your lead database", icon: Database },
  { value: "crm" as const, label: "CRM Contacts", description: "HubSpot, Salesforce, Zoho", icon: Users },
  { value: "apollo" as const, label: "Apollo", description: "Pull from Apollo lists", icon: Globe },
  { value: "linkedin" as const, label: "LinkedIn", description: "LinkedIn Sales Navigator", icon: Linkedin },
  { value: "website" as const, label: "Website Leads", description: "Inbound form captures", icon: Globe },
  { value: "manual" as const, label: "Manual Entry", description: "Add numbers by hand", icon: PencilLine },
  { value: "api" as const, label: "API", description: "Push leads programmatically", icon: Plug },
];

export function AudienceStep({
  campaignId, onCount,
}: {
  campaignId: string | null;
  onCount: (n: number) => void;
}) {
  const [source, setSource] = useState<Source>("leadaro");
  const [filters, setFilters] = useState<Record<string, string>>({});
  const [preview, setPreview] = useState<AudiencePreview | null>(null);
  const [leads, setLeads] = useState<Lead[]>([]);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");
  const [error, setError] = useState("");

  const refresh = useCallback(async () => {
    setBusy(true);
    setError("");
    try {
      const body: Record<string, unknown> = {};
      if (filters.industry) body.industry = filters.industry;
      if (filters.country) body.country = filters.country;
      if (filters.city) body.city = filters.city;
      if (filters.min_score) body.min_score = Number(filters.min_score);

      const [p, l] = await Promise.all([
        api.post<AudiencePreview>("/leads/preview", body),
        api.get<Lead[]>(`/leads?limit=8${filters.industry ? `&industry=${filters.industry}` : ""}`),
      ]);
      setPreview(p);
      setLeads(l);
      onCount(p.reachable);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Preview failed");
    } finally {
      setBusy(false);
    }
  }, [filters, onCount]);

  useEffect(() => { void refresh(); }, [refresh]);

  async function upload(file: File) {
    setBusy(true);
    setMsg("");
    setError("");
    try {
      const fd = new FormData();
      fd.append("file", file);
      const r = await api.upload<{
        accepted: number; invalid: number; duplicates: number; total_rows: number;
      }>("/leads/import", fd);
      setMsg(
        `${num(r.accepted)} imported · ${num(r.duplicates)} duplicates skipped · ` +
        `${num(r.invalid)} invalid numbers rejected`,
      );
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Import failed");
    } finally {
      setBusy(false);
    }
  }

  async function attach() {
    if (!campaignId) return;
    setBusy(true);
    try {
      const all = await api.get<Lead[]>("/leads?limit=500");
      const r = await api.post<{ attached: number; skipped_suppressed: number }>(
        `/leads/attach/${campaignId}`,
        { lead_ids: all.map((l) => l.id) },
      );
      setMsg(`${num(r.attached)} leads attached · ${num(r.skipped_suppressed)} skipped (suppressed)`);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Attach failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <StepSplit
      aside={
        <>
          <Card>
            <SectionTitle hint="Recomputed against the live suppression list.">
              Audience preview
            </SectionTitle>
            {busy && !preview ? (
              <div className="grid place-items-center py-8 text-muted">
                <Loader2 size={16} className="animate-spin" />
              </div>
            ) : preview ? (
              <>
                <div className="mb-3 rounded-card bg-primary-wash p-3 text-center">
                  <p className="tnum text-stat font-semibold text-primary-ink">
                    {num(preview.reachable)}
                  </p>
                  <p className="text-sm text-primary-ink/70">reachable leads</p>
                </div>
                <dl className="space-y-1.5 text-sm">
                  <Row icon={CheckCircle2} label="Total matched" value={num(preview.total)} />
                  <Row icon={AlertTriangle} label="Invalid numbers" value={num(preview.invalid)} tone={preview.invalid ? "warn" : undefined} />
                  <Row icon={CircleSlash} label="On DNC list" value={num(preview.dnc)} tone={preview.dnc ? "neg" : undefined} />
                  <Row icon={ShieldBan} label="Blacklisted" value={num(preview.blacklisted)} tone={preview.blacklisted ? "neg" : undefined} />
                </dl>
                <div className="mt-3 space-y-1.5 border-t border-line pt-3 text-sm">
                  <Row label="Estimated cost" value={usd(preview.estimated_cost_usd)} />
                  <Row
                    label="Predicted connect rate"
                    value={`${(preview.predicted_success_rate * 100).toFixed(1)}%`}
                  />
                </div>
              </>
            ) : null}
          </Card>

          {campaignId && (
            <Button variant="primary" size="md" className="w-full" onClick={attach} disabled={busy}>
              {busy ? <Loader2 size={13} className="animate-spin" /> : null}
              Attach audience to campaign
            </Button>
          )}
        </>
      }
    >
      <SectionTitle hint="Pick where the leads come from.">Choose source</SectionTitle>
      <OptionCards value={source} onChange={setSource} options={SOURCES} columns={4} />

      {source === "csv" && (
        <Card className="mt-4 border-dashed">
          <div className="text-center">
            <Upload size={20} className="mx-auto text-muted" />
            <p className="mt-2 text-base font-medium text-ink">Upload a CSV of leads</p>
            <p className="mt-0.5 text-sm text-muted">
              Needs a <code className="rounded bg-sunk px-1">phone</code> column. Also reads
              first_name, last_name, email, company, designation, industry, city, country.
            </p>
            <label className="mt-3 inline-block">
              <input
                type="file"
                accept=".csv"
                className="hidden"
                onChange={(e) => e.target.files?.[0] && upload(e.target.files[0])}
              />
              <span className="inline-flex h-8 cursor-pointer items-center gap-2 rounded-pill bg-primary px-3.5 text-sm font-medium text-white hover:bg-primary-deep">
                <Upload size={13} /> Choose file
              </span>
            </label>
          </div>
        </Card>
      )}

      {source !== "csv" && source !== "manual" && (
        <p className="mt-3 rounded-md bg-info-wash px-3 py-2 text-sm text-info">
          {SOURCES.find((s) => s.value === source)?.label} sync is configured under
          Integrations. Leads already synced are filterable below.
        </p>
      )}

      <div className="mt-5">
        <SectionTitle hint="Narrow the audience before you commit to calling it.">
          Filters
        </SectionTitle>
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <Field label="Industry">
            <Input
              value={filters.industry ?? ""}
              onChange={(e) => setFilters({ ...filters, industry: e.target.value })}
              placeholder="e.g. SaaS"
            />
          </Field>
          <Field label="Country">
            <Input
              value={filters.country ?? ""}
              onChange={(e) => setFilters({ ...filters, country: e.target.value })}
              placeholder="e.g. US"
            />
          </Field>
          <Field label="City">
            <Input
              value={filters.city ?? ""}
              onChange={(e) => setFilters({ ...filters, city: e.target.value })}
              placeholder="e.g. Austin"
            />
          </Field>
          <Field label="Minimum lead score">
            <Select
              value={filters.min_score ?? ""}
              onChange={(e) => setFilters({ ...filters, min_score: e.target.value })}
              options={[
                { value: "", label: "Any score" },
                { value: "40", label: "40+" },
                { value: "60", label: "60+" },
                { value: "80", label: "80+ (hot)" },
              ]}
            />
          </Field>
        </div>
      </div>

      {msg && (
        <p className="mt-3 rounded-md bg-pos-wash px-3 py-2 text-sm text-pos">{msg}</p>
      )}
      {error && (
        <p className="mt-3 rounded-md bg-neg-wash px-3 py-2 text-sm text-neg">{error}</p>
      )}

      {leads.length > 0 && (
        <div className="mt-5">
          <SectionTitle>Sample of matching leads</SectionTitle>
          <div className="overflow-hidden rounded-card border border-line">
            <table className="w-full text-base">
              <thead className="bg-sunk">
                <tr>
                  {["Name", "Phone", "Company", "Industry", "Score"].map((h) => (
                    <th key={h} className="px-3 py-2 text-left text-micro font-semibold uppercase tracking-wider text-faint">
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {leads.map((l) => (
                  <tr key={l.id} className="border-t border-line">
                    <td className="px-3 py-2 font-medium text-ink">
                      {[l.first_name, l.last_name].filter(Boolean).join(" ") || "—"}
                    </td>
                    <td className="tnum px-3 py-2 text-muted">{l.phone}</td>
                    <td className="px-3 py-2 text-muted">{l.company ?? "—"}</td>
                    <td className="px-3 py-2 text-muted">{l.industry ?? "—"}</td>
                    <td className="tnum px-3 py-2 text-right font-medium text-ink">{l.lead_score}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </StepSplit>
  );
}

function Row({
  icon: Icon, label, value, tone,
}: {
  icon?: React.ComponentType<{ size?: number; className?: string }>;
  label: string;
  value: string;
  tone?: "warn" | "neg";
}) {
  return (
    <div className="flex items-center justify-between gap-2">
      <span className="flex items-center gap-1.5 text-muted">
        {Icon && <Icon size={12} className={tone === "neg" ? "text-neg" : tone === "warn" ? "text-warn" : "text-faint"} />}
        {label}
      </span>
      <span className={`tnum font-semibold ${tone === "neg" ? "text-neg" : tone === "warn" ? "text-warn" : "text-ink"}`}>
        {value}
      </span>
    </div>
  );
}
