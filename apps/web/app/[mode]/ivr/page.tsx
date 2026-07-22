"use client";
import { useCallback, useEffect, useState } from "react";
import { useParams } from "next/navigation";
import {
  PhoneIncoming, Loader2, Link2, Check, Info, UserSearch, History,
} from "lucide-react";
import { PageHeader } from "@/components/shell/TopBar";
import { Card } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Chip } from "@/components/ui/Chip";
import { Select } from "@/components/ui/Form";
import { MenuBuilder, type IvrMenu } from "@/components/ivr/MenuBuilder";
import { CallLauncher } from "@/components/calls/CallLauncher";
import { api, type Campaign, type Mode } from "@/lib/api";
import { num } from "@/lib/cn";

type Num = {
  id: string; e164: string; label?: string | null;
  provider: string; country?: string | null;
  inbound_campaign_id?: string | null;
  ivr_menu?: Partial<IvrMenu> | null;
};

/**
 * IVR / inbound routing.
 *
 * Each business number is bound to a campaign; a call to that number runs the
 * same agent, script and voice as the outbound campaign. There is no menu tree
 * — the agent is conversational, so "press 1 for sales" would be a step
 * backwards. Caller identification and context resumption do the routing.
 */
export default function IvrPage() {
  const { mode } = useParams<{ mode: Mode }>();
  const [numbers, setNumbers] = useState<Num[]>([]);
  const [campaigns, setCampaigns] = useState<Campaign[]>([]);
  const [inbound, setInbound] = useState<{ id: string; first_name?: string | null;
    last_name?: string | null; phone?: string | null; campaign_name?: string | null;
    started_at: string; outcome?: string | null }[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<string | null>(null);
  const [msg, setMsg] = useState("");
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [n, c, i] = await Promise.all([
        api.get<Num[]>("/phone-numbers"),
        api.get<Campaign[]>(`/campaigns?mode=${mode}`),
        api.get<typeof inbound>("/calls?direction=inbound&limit=25"),
      ]);
      setNumbers(n); setCampaigns(c); setInbound(i);
      setError("");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not load inbound settings");
    } finally {
      setLoading(false);
    }
  }, [mode]);

  useEffect(() => { void load(); }, [load]);

  async function bind(numberId: string, campaignId: string) {
    setBusy(numberId);
    setError("");
    try {
      await api.patch(`/phone-numbers/${numberId}`, {
        inbound_campaign_id: campaignId || null,
      });
      setMsg(campaignId
        ? "Inbound calls to this number will now be answered by that campaign's agent."
        : "Inbound binding cleared — calls to this number will not be answered.");
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not update binding");
    } finally {
      setBusy(null);
    }
  }

  const bound = numbers.filter((n) => n.inbound_campaign_id).length;

  return (
    <>
      <PageHeader
        title="Inbound & IVR"
        subtitle="What happens when someone calls one of your numbers back."
      >
        <Chip tone={bound ? "pos" : "neutral"}>
          {num(bound)} of {num(numbers.length)} numbers answered
        </Chip>
        <CallLauncher mode={mode} campaigns={campaigns} onPlaced={load} />
      </PageHeader>

      {msg && <p className="mb-card rounded-card bg-pos-wash px-4 py-2.5 text-base text-pos">{msg}</p>}
      {error && <p className="mb-card rounded-card bg-neg-wash px-4 py-2.5 text-base text-neg">{error}</p>}

      {loading ? (
        <div className="grid place-items-center py-20 text-muted">
          <Loader2 size={20} className="animate-spin" />
        </div>
      ) : (
        <div className="grid gap-card lg:grid-cols-[1fr_320px]">
          <div className="space-y-card">
            <Card pad={false}>
              <div className="border-b border-line px-card py-3">
                <h3 className="text-base font-semibold text-ink">Number routing</h3>
                <p className="text-sm text-muted">
                  Bind a number to a campaign to answer inbound calls with that agent.
                </p>
              </div>
              <ul className="divide-y divide-line">
                {numbers.map((n) => (
                  <li key={n.id} className="flex flex-wrap items-center gap-3 px-card py-3">
                    <PhoneIncoming
                      size={15}
                      className={n.inbound_campaign_id ? "text-pos" : "text-faint"}
                    />
                    <span className="min-w-0">
                      <span className="tnum block font-medium text-ink">{n.e164}</span>
                      <span className="block text-sm text-muted">
                        {n.label ?? "—"} · {n.provider}
                      </span>
                    </span>
                    <div className="ml-auto flex items-center gap-2">
                      {busy === n.id && <Loader2 size={13} className="animate-spin text-muted" />}
                      <Select
                        value={n.inbound_campaign_id ?? ""}
                        onChange={(e) => bind(n.id, e.target.value)}
                        className="h-8 w-[220px]"
                        options={[
                          { value: "", label: "Do not answer inbound" },
                          ...campaigns.map((c) => ({ value: c.id, label: c.name })),
                        ]}
                      />
                    </div>
                  </li>
                ))}
                {numbers.length === 0 && (
                  <li className="px-card py-12 text-center text-base text-muted">
                    No numbers yet. Add one under Settings first.
                  </li>
                )}
              </ul>
            </Card>

            {/* Keypad menu, per number. Only shown for numbers that answer. */}
            {numbers.filter((n) => n.inbound_campaign_id).map((n) => (
              <MenuBuilder
                key={n.id}
                numberId={n.id}
                e164={n.e164}
                initial={n.ivr_menu}
                campaigns={campaigns}
                onSaved={load}
              />
            ))}

            <Card pad={false}>
              <div className="flex items-center gap-2 border-b border-line px-card py-3">
                <History size={14} className="text-muted" />
                <h3 className="text-base font-semibold text-ink">Recent inbound calls</h3>
              </div>
              <ul className="divide-y divide-line">
                {inbound.map((c) => (
                  <li key={c.id} className="flex items-center gap-3 px-card py-2.5">
                    <span className="min-w-0 flex-1">
                      <span className="block truncate font-medium text-ink">
                        {[c.first_name, c.last_name].filter(Boolean).join(" ") ||
                         c.phone || "Unknown caller"}
                      </span>
                      <span className="block text-sm text-muted">
                        {c.campaign_name ?? "—"}
                      </span>
                    </span>
                    <Chip tone="neutral">{(c.outcome ?? "—").replace(/_/g, " ")}</Chip>
                    <span className="tnum shrink-0 text-sm text-muted">
                      {new Date(c.started_at).toLocaleString([], {
                        month: "short", day: "numeric", hour: "2-digit", minute: "2-digit",
                      })}
                    </span>
                  </li>
                ))}
                {inbound.length === 0 && (
                  <li className="px-card py-10 text-center text-base text-muted">
                    No inbound calls yet.
                  </li>
                )}
              </ul>
            </Card>
          </div>

          <div className="space-y-card">
            <Card>
              <h3 className="mb-2 flex items-center gap-1.5 text-base font-semibold text-ink">
                <UserSearch size={14} className="text-primary" /> How a callback is handled
              </h3>
              <ol className="space-y-2 text-sm">
                {[
                  "The caller's number is matched against your leads.",
                  "If known, the agent loads the summary and outcome of their last call.",
                  "It opens with that context — not a cold greeting.",
                  "If unknown, it qualifies them and creates a new lead.",
                ].map((s, i) => (
                  <li key={s} className="flex gap-2">
                    <span className="grid size-[18px] shrink-0 place-items-center rounded-full bg-primary-wash text-[10px] font-bold text-primary-ink">
                      {i + 1}
                    </span>
                    <span className="text-ink">{s}</span>
                  </li>
                ))}
              </ol>
            </Card>

            <Card>
              <h3 className="mb-1.5 flex items-center gap-1.5 text-base font-semibold text-ink">
                <Info size={14} className="text-muted" /> Menu or no menu
              </h3>
              <p className="text-base leading-relaxed text-muted">
                A keypad menu is optional per number. Leave it off and the agent
                simply asks what the caller needs — it understands speech, so
                most callers never need to press anything. Turn it on when you
                want deterministic routing, or callers who already know the
                menu and want to skip straight through.
              </p>
              <p className="mt-2 text-base leading-relaxed text-muted">
                Either way, a caller who presses nothing is handed to the agent
                rather than dropped.
              </p>
            </Card>

            <Card>
              <h3 className="mb-1.5 flex items-center gap-1.5 text-base font-semibold text-ink">
                <Link2 size={14} className="text-muted" /> Trunk configuration
              </h3>
              <p className="text-base leading-relaxed text-muted">
                Inbound requires <code className="rounded bg-sunk px-1 text-sm">
                SIP_INBOUND_TRUNK_ID</code> in the environment, and your carrier
                pointing the number at the LiveKit SIP endpoint. Until then,
                bindings save but no call will arrive.
              </p>
            </Card>
          </div>
        </div>
      )}
    </>
  );
}
