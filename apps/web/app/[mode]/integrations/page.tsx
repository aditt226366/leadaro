"use client";
import { useCallback, useEffect, useState } from "react";
import {
  Calendar, Database, MessageSquare, Phone, AudioLines, Check, Plug,
  Loader2, ExternalLink,
} from "lucide-react";
import { PageHeader } from "@/components/shell/TopBar";
import { Card } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Chip } from "@/components/ui/Chip";
import { Field, Input } from "@/components/ui/Form";
import { api } from "@/lib/api";
import { cn } from "@/lib/cn";

type Integration = {
  provider: string; name: string; category: string;
  status: "available" | "planned";
  connected: boolean; config: Record<string, string>;
};

const CATEGORY = {
  meetings: { label: "Calendars & meetings", icon: Calendar },
  crm: { label: "CRM", icon: Database },
  comms: { label: "Communication", icon: MessageSquare },
  telephony: { label: "Telephony", icon: Phone },
  voice: { label: "Speech", icon: AudioLines },
} as const;

export default function Integrations() {
  const [items, setItems] = useState<Integration[]>([]);
  const [busy, setBusy] = useState<string | null>(null);
  const [open, setOpen] = useState<string | null>(null);
  const [form, setForm] = useState<Record<string, string>>({});
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    try {
      setItems(await api.get<Integration[]>("/integrations"));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not load integrations");
    }
  }, []);

  useEffect(() => { void load(); }, [load]);

  async function connect(provider: string) {
    setBusy(provider);
    setError("");
    try {
      await api.post(`/integrations/${provider}`, {
        config: { label: form.label ?? "" },
        secrets: form.token ? { access_token: form.token } : {},
      });
      setOpen(null);
      setForm({});
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Connect failed");
    } finally {
      setBusy(null);
    }
  }

  async function disconnect(provider: string) {
    setBusy(provider);
    try {
      await api.del(`/integrations/${provider}`);
      await load();
    } finally {
      setBusy(null);
    }
  }

  const grouped = Object.keys(CATEGORY).map((cat) => ({
    cat: cat as keyof typeof CATEGORY,
    items: items.filter((i) => i.category === cat),
  })).filter((g) => g.items.length);

  return (
    <>
      <PageHeader
        title="Integrations"
        subtitle="Connect the tools your outreach writes into."
      />

      {error && (
        <p className="mb-card rounded-card bg-neg-wash px-4 py-2.5 text-base text-neg">{error}</p>
      )}

      {items.length === 0 ? (
        <div className="grid place-items-center py-20 text-muted">
          <Loader2 size={20} className="animate-spin" />
        </div>
      ) : (
        <div className="space-y-card">
          {grouped.map(({ cat, items: group }) => {
            const Icon = CATEGORY[cat].icon;
            return (
              <div key={cat}>
                <h3 className="mb-2.5 flex items-center gap-1.5 text-base font-semibold text-ink">
                  <Icon size={14} className="text-muted" /> {CATEGORY[cat].label}
                </h3>
                <div className="grid gap-card sm:grid-cols-2 lg:grid-cols-3">
                  {group.map((i) => (
                    <Card
                      key={i.provider}
                      className={cn(i.status === "planned" && "opacity-70")}
                    >
                      <div className="flex items-start justify-between gap-2">
                        <div className="min-w-0">
                          <p className="font-semibold text-ink">{i.name}</p>
                          <p className="mt-0.5 text-sm text-muted">
                            {i.status === "planned"
                              ? "Adapter not wired yet"
                              : i.connected ? "Connected" : "Available"}
                          </p>
                        </div>
                        {i.connected ? (
                          <Chip tone="pos"><Check size={10} /> On</Chip>
                        ) : i.status === "planned" ? (
                          <Chip tone="neutral">Planned</Chip>
                        ) : (
                          <Chip tone="info">Ready</Chip>
                        )}
                      </div>

                      {open === i.provider && (
                        <div className="mt-3 space-y-2 border-t border-line pt-3">
                          <Field label="Access token / API key">
                            <Input
                              type="password"
                              value={form.token ?? ""}
                              onChange={(e) => setForm({ ...form, token: e.target.value })}
                              placeholder="Paste the credential"
                              className="h-8"
                            />
                          </Field>
                          <div className="flex gap-2">
                            <Button
                              variant="primary"
                              onClick={() => connect(i.provider)}
                              disabled={busy === i.provider}
                            >
                              {busy === i.provider
                                ? <Loader2 size={12} className="animate-spin" />
                                : <Plug size={12} />}
                              Save
                            </Button>
                            <Button onClick={() => { setOpen(null); setForm({}); }}>
                              Cancel
                            </Button>
                          </div>
                        </div>
                      )}

                      {open !== i.provider && (
                        <div className="mt-3">
                          {i.connected ? (
                            <Button
                              onClick={() => disconnect(i.provider)}
                              disabled={busy === i.provider}
                              className="w-full"
                            >
                              Disconnect
                            </Button>
                          ) : (
                            <Button
                              variant={i.status === "available" ? "primary" : "outline"}
                              disabled={i.status !== "available"}
                              onClick={() => setOpen(i.provider)}
                              className="w-full"
                            >
                              {i.status === "available"
                                ? <><Plug size={12} /> Connect</>
                                : "Not available yet"}
                            </Button>
                          )}
                        </div>
                      )}
                    </Card>
                  ))}
                </div>
              </div>
            );
          })}
        </div>
      )}

      <Card className="mt-card">
        <h3 className="mb-1 flex items-center gap-1.5 text-base font-semibold text-ink">
          <ExternalLink size={14} className="text-muted" /> Why some show as planned
        </h3>
        <p className="text-base leading-relaxed text-muted">
          Each provider sits behind a common adapter interface. The ones marked
          available are wired and tested; the rest are one adapter file away, and
          are shown here so the gap is visible rather than implied. Adding one
          does not require touching the campaign, dialer or agent code.
        </p>
      </Card>
    </>
  );
}
