"use client";
import { useEffect, useState } from "react";
import { Phone, Users, Shield, Plus, Loader2, LogOut } from "lucide-react";
import { PageHeader } from "@/components/shell/TopBar";
import { Card } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Chip } from "@/components/ui/Chip";
import { Field, Input } from "@/components/ui/Form";
import { api, clearToken } from "@/lib/api";

type Me = { id: string; name: string; email: string; role: string; permissions: string[] };
type Number_ = { id: string; e164: string; label?: string | null; provider: string; country?: string | null };

// FRD §15 — the permission matrix, shown so a user can see why a control is
// missing rather than assuming the app is broken.
const ALL_PERMISSIONS = [
  ["create_campaign", "Create campaigns"],
  ["delete_campaign", "Delete / archive campaigns"],
  ["pause_campaign", "Pause and resume"],
  ["export_reports", "Export reports"],
  ["download_recordings", "Download recordings"],
  ["modify_scripts", "Modify scripts"],
  ["access_analytics", "Access analytics"],
  ["manage_numbers", "Manage phone numbers"],
  ["approve_campaigns", "Approve campaigns"],
];

export default function Settings() {
  const [me, setMe] = useState<Me | null>(null);
  const [numbers, setNumbers] = useState<Number_[]>([]);
  const [adding, setAdding] = useState({ e164: "", label: "" });
  const [error, setError] = useState("");

  async function load() {
    try {
      const [m, n] = await Promise.all([
        api.get<Me>("/auth/me"),
        api.get<Number_[]>("/phone-numbers"),
      ]);
      setMe(m);
      setNumbers(n);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not load settings");
    }
  }

  useEffect(() => { void load(); }, []);

  async function addNumber() {
    if (!adding.e164.trim()) return;
    try {
      await api.post("/phone-numbers", adding);
      setAdding({ e164: "", label: "" });
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not add number");
    }
  }

  if (!me) {
    return (
      <div className="grid place-items-center py-24 text-muted">
        {error ? <p className="text-neg">{error}</p> : <Loader2 size={20} className="animate-spin" />}
      </div>
    );
  }

  return (
    <>
      <PageHeader title="Settings" subtitle="Your account, numbers and permissions.">
        <Button
          onClick={() => { clearToken(); window.location.href = "/login"; }}
        >
          <LogOut size={13} /> Sign out
        </Button>
      </PageHeader>

      {error && (
        <p className="mb-card rounded-card bg-neg-wash px-4 py-2.5 text-base text-neg">{error}</p>
      )}

      <div className="grid gap-card lg:grid-cols-2">
        <Card>
          <h3 className="mb-3 flex items-center gap-1.5 text-base font-semibold text-ink">
            <Users size={14} className="text-muted" /> Your account
          </h3>
          <dl className="space-y-2 text-base">
            {[["Name", me.name], ["Email", me.email], ["Role", me.role.replace(/_/g, " ")]]
              .map(([k, v]) => (
                <div key={k} className="flex justify-between gap-3">
                  <dt className="text-muted">{k}</dt>
                  <dd className="font-medium capitalize text-ink">{v}</dd>
                </div>
              ))}
          </dl>
        </Card>

        <Card>
          <h3 className="mb-3 flex items-center gap-1.5 text-base font-semibold text-ink">
            <Shield size={14} className="text-muted" /> Your permissions
          </h3>
          <ul className="space-y-1.5">
            {ALL_PERMISSIONS.map(([key, label]) => {
              const has = me.permissions.includes(key);
              return (
                <li key={key} className="flex items-center justify-between gap-3 text-base">
                  <span className={has ? "text-ink" : "text-faint"}>{label}</span>
                  <Chip tone={has ? "pos" : "neutral"}>{has ? "allowed" : "denied"}</Chip>
                </li>
              );
            })}
          </ul>
          <p className="mt-3 border-t border-line pt-3 text-tiny leading-snug text-muted">
            Enforced by the API, not just hidden in the interface — a denied
            action fails even if called directly.
          </p>
        </Card>

        <Card className="lg:col-span-2">
          <h3 className="mb-3 flex items-center gap-1.5 text-base font-semibold text-ink">
            <Phone size={14} className="text-muted" /> Phone numbers
          </h3>

          <ul className="divide-y divide-line rounded-card border border-line">
            {numbers.map((n) => (
              <li key={n.id} className="flex items-center gap-3 px-3 py-2.5">
                <span className="tnum font-medium text-ink">{n.e164}</span>
                <span className="text-sm text-muted">{n.label ?? "—"}</span>
                <Chip className="ml-auto">{n.provider}</Chip>
                {n.country && <Chip>{n.country}</Chip>}
              </li>
            ))}
            {numbers.length === 0 && (
              <li className="px-3 py-8 text-center text-base text-muted">
                No numbers yet. Add the caller ID your campaigns will dial from.
              </li>
            )}
          </ul>

          {me.permissions.includes("manage_numbers") && (
            <div className="mt-3 flex flex-wrap items-end gap-3">
              <Field label="Number (E.164)" className="w-[200px]">
                <Input
                  value={adding.e164}
                  onChange={(e) => setAdding({ ...adding, e164: e.target.value })}
                  placeholder="+14155550100"
                />
              </Field>
              <Field label="Label" className="w-[200px]">
                <Input
                  value={adding.label}
                  onChange={(e) => setAdding({ ...adding, label: e.target.value })}
                  placeholder="Sales line"
                />
              </Field>
              <Button variant="primary" size="md" onClick={addNumber}>
                <Plus size={13} /> Add number
              </Button>
            </div>
          )}
        </Card>
      </div>
    </>
  );
}
