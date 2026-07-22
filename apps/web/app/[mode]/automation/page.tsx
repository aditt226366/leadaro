"use client";
import { useCallback, useEffect, useState } from "react";
import { useParams } from "next/navigation";
import {
  Plus, Trash2, GitBranch, Workflow, Loader2, Clock, Mail,
  MessageSquare, PhoneForwarded, Database, Bell,
} from "lucide-react";
import { PageHeader } from "@/components/shell/TopBar";
import { Card } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Chip } from "@/components/ui/Chip";
import { Field, Input, Select, Toggle } from "@/components/ui/Form";
import { api, type Mode } from "@/lib/api";
import { num } from "@/lib/cn";

type RoutingRule = {
  id: string; name: string; position: number; is_active: boolean;
  conditions: { signal: string; op: string; value: string }[];
  destination: { type?: string; phone?: string; target?: string };
};

type AutomationRule = {
  id: string; name: string; trigger: string; is_active: boolean;
  actions: { type: string; config?: Record<string, string> }[];
};

type Followup = {
  id: string; channel: string; due_at: string; status: string;
  reason?: string | null; first_name?: string | null;
  last_name?: string | null; company?: string | null;
};

const SIGNALS = [
  "lead_score", "industry", "language", "region", "intent",
  "buying_signals", "crm_status", "meeting_probability", "availability",
  "past_interactions",
];
const OPS = [["gt", ">"], ["lt", "<"], ["eq", "="], ["contains", "contains"]];
const DESTINATIONS = [
  "ai_voice", "sales_rep", "support", "recruiter", "manager",
  "regional_team", "partner", "custom_queue",
];

const TRIGGERS = [
  "outcome:interested", "outcome:not_interested", "outcome:busy",
  "outcome:voicemail", "outcome:no_answer", "outcome:wrong_number",
  "outcome:callback", "outcome:meeting_scheduled", "outcome:transferred",
];

const ACTIONS = [
  ["send_email", "Send email", Mail],
  ["send_sms", "Send SMS", MessageSquare],
  ["send_whatsapp", "Send WhatsApp", MessageSquare],
  ["notify_sales", "Notify sales", Bell],
  ["crm_update", "Update CRM", Database],
  ["assign_owner", "Assign owner", PhoneForwarded],
  ["retry_call", "Retry the call", Clock],
  ["mark_invalid", "Mark number invalid", Trash2],
  ["suppress", "Add to suppression list", Trash2],
] as const;

export default function AutomationPage() {
  const { mode } = useParams<{ mode: Mode }>();
  const [tab, setTab] = useState<"automation" | "routing" | "followups">("automation");
  const [routing, setRouting] = useState<RoutingRule[]>([]);
  const [rules, setRules] = useState<AutomationRule[]>([]);
  const [followups, setFollowups] = useState<Followup[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [r, a, f] = await Promise.all([
        api.get<RoutingRule[]>("/routing-rules"),
        api.get<AutomationRule[]>("/automation-rules"),
        api.get<Followup[]>("/followups?pending_only=true"),
      ]);
      setRouting(r); setRules(a); setFollowups(f);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not load automation");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void load(); }, [load]);

  async function addRule() {
    await api.post("/automation-rules", {
      name: "New rule", trigger: "outcome:interested",
      actions: [{ type: "send_email" }],
    });
    await load();
  }

  async function addRouting() {
    await api.post("/routing-rules", {
      name: "New routing rule", position: routing.length,
      conditions: [{ signal: "lead_score", op: "gt", value: "80" }],
      destination: { type: "sales_rep" },
    });
    await load();
  }

  const tabs = [
    ["automation", "Automation rules", rules.length],
    ...(mode === "call" ? [["routing", "Smart routing", routing.length] as const] : []),
    ["followups", "Scheduled follow-ups", followups.length],
  ] as const;

  return (
    <>
      <PageHeader
        title="Automation"
        subtitle="What happens after a call ends, and who picks it up."
      >
        {tab === "automation" && (
          <Button variant="primary" onClick={addRule}><Plus size={13} /> New rule</Button>
        )}
        {tab === "routing" && (
          <Button variant="primary" onClick={addRouting}><Plus size={13} /> New routing rule</Button>
        )}
      </PageHeader>

      <div className="mb-card flex gap-1 rounded-pill border border-line bg-surface p-1">
        {tabs.map(([key, label, count]) => (
          <button
            key={key}
            onClick={() => setTab(key as typeof tab)}
            className={`flex-1 rounded-[6px] py-1.5 text-sm font-medium transition-colors ${
              tab === key ? "bg-primary-wash text-primary-ink" : "text-muted hover:text-ink"
            }`}
          >
            {label} <span className="tnum text-faint">({num(count)})</span>
          </button>
        ))}
      </div>

      {error && (
        <p className="mb-card rounded-card bg-neg-wash px-4 py-2.5 text-base text-neg">{error}</p>
      )}

      {loading ? (
        <div className="grid place-items-center py-20 text-muted">
          <Loader2 size={20} className="animate-spin" />
        </div>
      ) : tab === "automation" ? (
        <div className="space-y-card">
          {rules.map((r) => (
            <RuleCard key={r.id} rule={r} onChange={load} />
          ))}
          {rules.length === 0 && (
            <Empty
              icon={Workflow}
              title="No automation rules"
              body="Rules fire after a call ends — send a follow-up email when someone's interested, retry when they're busy, suppress a wrong number."
              action={<Button variant="primary" onClick={addRule}><Plus size={13} /> Create a rule</Button>}
            />
          )}
        </div>
      ) : tab === "routing" ? (
        <div className="space-y-card">
          <p className="rounded-card bg-info-wash px-4 py-2.5 text-sm text-info">
            Rules are evaluated top to bottom. The first match wins, so put the
            most specific conditions first.
          </p>
          {routing.map((r) => (
            <RoutingCard key={r.id} rule={r} onChange={load} />
          ))}
          {routing.length === 0 && (
            <Empty
              icon={GitBranch}
              title="No routing rules"
              body="Decide who a live transfer reaches — by lead score, language, intent or region."
              action={<Button variant="primary" onClick={addRouting}><Plus size={13} /> Create a rule</Button>}
            />
          )}
        </div>
      ) : (
        <Card pad={false}>
          <div className="border-b border-line px-card py-3">
            <h3 className="text-base font-semibold text-ink">Scheduled follow-ups</h3>
            <p className="text-sm text-muted">
              Created automatically after each call, unless the lead explicitly declined.
            </p>
          </div>
          <ul className="divide-y divide-line">
            {followups.map((f) => (
              <li key={f.id} className="flex items-center gap-3 px-card py-3">
                <span className="grid size-7 shrink-0 place-items-center rounded-full bg-primary-wash text-primary-ink">
                  {f.channel === "email" ? <Mail size={13} /> : <PhoneForwarded size={13} />}
                </span>
                <span className="min-w-0 flex-1">
                  <span className="block truncate font-medium text-ink">
                    {[f.first_name, f.last_name].filter(Boolean).join(" ") || "Lead"}
                    {f.company ? ` · ${f.company}` : ""}
                  </span>
                  <span className="block text-sm text-muted">{f.reason ?? f.channel}</span>
                </span>
                <Chip tone="neutral">{f.channel}</Chip>
                <span className="tnum w-24 shrink-0 text-right text-sm text-muted">
                  {new Date(f.due_at).toLocaleDateString([], { month: "short", day: "numeric" })}
                </span>
              </li>
            ))}
            {followups.length === 0 && (
              <li className="px-card py-12 text-center text-base text-muted">
                Nothing scheduled. Follow-ups appear here after calls complete.
              </li>
            )}
          </ul>
        </Card>
      )}
    </>
  );
}

function RuleCard({ rule, onChange }: { rule: AutomationRule; onChange: () => void }) {
  const [local, setLocal] = useState(rule);
  const save = async (p: Partial<AutomationRule>) => {
    const next = { ...local, ...p };
    setLocal(next);
    await api.patch(`/automation-rules/${rule.id}`, p);
  };

  return (
    <Card>
      <div className="flex flex-wrap items-center gap-3">
        <Input
          value={local.name}
          onChange={(e) => setLocal({ ...local, name: e.target.value })}
          onBlur={() => save({ name: local.name })}
          className="h-8 max-w-[240px] font-medium"
        />
        <span className="text-sm text-muted">when</span>
        <Select
          value={local.trigger}
          onChange={(e) => save({ trigger: e.target.value })}
          className="h-8 max-w-[220px]"
          options={TRIGGERS.map((t) => ({
            value: t, label: t.replace("outcome:", "").replace(/_/g, " "),
          }))}
        />
        <div className="ml-auto flex items-center gap-2">
          <Toggle
            label=""
            checked={local.is_active}
            onChange={(v) => save({ is_active: v })}
          />
          <Button
            variant="ghost"
            onClick={async () => {
              await api.del(`/automation-rules/${rule.id}`);
              onChange();
            }}
            aria-label="Delete rule"
          >
            <Trash2 size={13} />
          </Button>
        </div>
      </div>

      <div className="mt-3 border-t border-line pt-3">
        <p className="mb-2 text-sm text-muted">Then do all of the following:</p>
        <div className="flex flex-wrap gap-1.5">
          {ACTIONS.map(([value, label, Icon]) => {
            const on = local.actions.some((a) => a.type === value);
            return (
              <button
                key={value}
                onClick={() => {
                  const actions = on
                    ? local.actions.filter((a) => a.type !== value)
                    : [...local.actions, { type: value }];
                  save({ actions });
                }}
                className={`inline-flex items-center gap-1.5 rounded-pill border px-2.5 py-1 text-sm transition-colors ${
                  on
                    ? "border-primary bg-primary-wash font-medium text-primary-ink"
                    : "border-line-strong bg-surface text-muted hover:border-primary/40"
                }`}
              >
                <Icon size={12} /> {label}
              </button>
            );
          })}
        </div>
      </div>
    </Card>
  );
}

function RoutingCard({ rule, onChange }: { rule: RoutingRule; onChange: () => void }) {
  const [local, setLocal] = useState(rule);
  const cond = local.conditions[0] ?? { signal: "lead_score", op: "gt", value: "" };
  const save = async (p: Partial<RoutingRule>) => {
    const next = { ...local, ...p };
    setLocal(next);
    await api.patch(`/routing-rules/${rule.id}`, p);
  };

  return (
    <Card>
      <div className="flex flex-wrap items-center gap-2">
        <Chip tone="primary">#{local.position + 1}</Chip>
        <Input
          value={local.name}
          onChange={(e) => setLocal({ ...local, name: e.target.value })}
          onBlur={() => save({ name: local.name })}
          className="h-8 max-w-[200px] font-medium"
        />
        <span className="text-sm text-muted">if</span>
        <Select
          value={cond.signal}
          onChange={(e) => save({ conditions: [{ ...cond, signal: e.target.value }] })}
          className="h-8 max-w-[170px]"
          options={SIGNALS.map((s) => ({ value: s, label: s.replace(/_/g, " ") }))}
        />
        <Select
          value={cond.op}
          onChange={(e) => save({ conditions: [{ ...cond, op: e.target.value }] })}
          className="h-8 w-[90px]"
          options={OPS.map(([v, l]) => ({ value: v, label: l }))}
        />
        <Input
          value={cond.value}
          onChange={(e) => setLocal({ ...local, conditions: [{ ...cond, value: e.target.value }] })}
          onBlur={() => save({ conditions: local.conditions })}
          className="h-8 w-[110px]"
          placeholder="value"
        />
        <span className="text-sm text-muted">route to</span>
        <Select
          value={local.destination?.type ?? "sales_rep"}
          onChange={(e) => save({ destination: { ...local.destination, type: e.target.value } })}
          className="h-8 max-w-[170px]"
          options={DESTINATIONS.map((d) => ({ value: d, label: d.replace(/_/g, " ") }))}
        />
        <div className="ml-auto flex items-center gap-2">
          <Toggle label="" checked={local.is_active} onChange={(v) => save({ is_active: v })} />
          <Button
            variant="ghost"
            onClick={async () => {
              await api.del(`/routing-rules/${rule.id}`);
              onChange();
            }}
            aria-label="Delete rule"
          >
            <Trash2 size={13} />
          </Button>
        </div>
      </div>
      <Field label="Destination number" hint="Where the SIP transfer lands." className="mt-3 max-w-xs">
        <Input
          value={local.destination?.phone ?? ""}
          onChange={(e) => setLocal({
            ...local, destination: { ...local.destination, phone: e.target.value },
          })}
          onBlur={() => save({ destination: local.destination })}
          placeholder="+14155550123"
          className="h-8"
        />
      </Field>
    </Card>
  );
}

function Empty({
  icon: Icon, title, body, action,
}: {
  icon: React.ComponentType<{ size?: number; className?: string }>;
  title: string; body: string; action: React.ReactNode;
}) {
  return (
    <Card className="py-12 text-center">
      <Icon size={22} className="mx-auto text-faint" />
      <p className="mt-2 font-medium text-ink">{title}</p>
      <p className="mx-auto mt-1 max-w-md text-base text-muted">{body}</p>
      <div className="mt-3">{action}</div>
    </Card>
  );
}
