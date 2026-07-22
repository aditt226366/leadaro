"use client";
import { useState } from "react";
import {
  Plus, Trash2, Save, Loader2, Check, Hash, Volume2, AlertTriangle,
} from "lucide-react";
import { Card } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Chip } from "@/components/ui/Chip";
import { Field, Input, Select, Textarea, Toggle } from "@/components/ui/Form";
import { api, type Campaign } from "@/lib/api";

export type MenuOption = {
  digit: string;
  label: string;
  action: "ai_agent" | "transfer" | "voicemail" | "hangup";
  target?: string | null;
  message?: string | null;
};

export type IvrMenu = {
  enabled: boolean;
  greeting: string;
  timeout_seconds: number;
  invalid_message: string;
  repeat_limit: number;
  options: MenuOption[];
};

const ACTIONS = [
  { value: "ai_agent", label: "Hand to the AI agent" },
  { value: "transfer", label: "Transfer to a number" },
  { value: "voicemail", label: "Take a voicemail" },
  { value: "hangup", label: "End the call" },
];

const DIGITS = [..."0123456789", "*", "#"];

const EMPTY: IvrMenu = {
  enabled: false,
  greeting: "Thanks for calling. ",
  timeout_seconds: 6,
  invalid_message: "Sorry, I didn't get that.",
  repeat_limit: 2,
  options: [],
};

export function MenuBuilder({
  numberId, e164, initial, campaigns, onSaved,
}: {
  numberId: string;
  e164: string;
  initial?: Partial<IvrMenu> | null;
  campaigns: Campaign[];
  onSaved?: () => void;
}) {
  const [menu, setMenu] = useState<IvrMenu>({ ...EMPTY, ...(initial ?? {}) });
  const [busy, setBusy] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState("");

  const set = (p: Partial<IvrMenu>) => {
    setMenu((m) => ({ ...m, ...p }));
    setSaved(false);
  };

  const setOption = (i: number, p: Partial<MenuOption>) =>
    set({ options: menu.options.map((o, j) => (j === i ? { ...o, ...p } : o)) });

  const used = new Set(menu.options.map((o) => o.digit));
  const nextFree = DIGITS.find((d) => !used.has(d)) ?? "0";

  // Two options on the same digit make the second unreachable. The API rejects
  // it, but surfacing it here explains why rather than just failing.
  const duplicates = menu.options
    .map((o) => o.digit)
    .filter((d, i, a) => a.indexOf(d) !== i);

  async function save() {
    setBusy(true);
    setError("");
    try {
      await api.put(`/phone-numbers/${numberId}/ivr`, menu);
      setSaved(true);
      onSaved?.();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not save the menu");
    } finally {
      setBusy(false);
    }
  }

  const preview = [
    menu.greeting,
    ...menu.options.filter((o) => o.label).map((o) => `Press ${o.digit} ${o.label}.`),
  ].filter(Boolean).join(" ");

  return (
    <Card pad={false}>
      <div className="flex flex-wrap items-center gap-3 border-b border-line px-card py-3">
        <Hash size={15} className={menu.enabled ? "text-primary" : "text-faint"} />
        <div className="min-w-0">
          <h3 className="text-base font-semibold text-ink">Keypad menu</h3>
          <p className="tnum text-sm text-muted">{e164}</p>
        </div>
        <div className="ml-auto flex items-center gap-3">
          <Toggle
            label=""
            checked={menu.enabled}
            onChange={(v) => set({ enabled: v })}
          />
          <Button variant="primary" onClick={save} disabled={busy || !!duplicates.length}>
            {busy ? <Loader2 size={13} className="animate-spin" />
              : saved ? <Check size={13} /> : <Save size={13} />}
            {saved ? "Saved" : "Save menu"}
          </Button>
        </div>
      </div>

      {!menu.enabled && (
        <p className="border-b border-line bg-sunk px-card py-2 text-sm text-muted">
          Menu is off — inbound callers go straight to the AI agent, which asks
          what they need.
        </p>
      )}

      {error && (
        <p className="border-b border-line bg-neg-wash px-card py-2 text-sm text-neg">{error}</p>
      )}
      {duplicates.length > 0 && (
        <p className="flex items-center gap-1.5 border-b border-line bg-warn-wash px-card py-2 text-sm text-warn">
          <AlertTriangle size={13} />
          Digit {duplicates.join(", ")} is used more than once — the second
          option would never be reachable.
        </p>
      )}

      <div className="space-y-4 p-card">
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="Greeting" hint="Spoken before the options." className="sm:col-span-2">
            <Textarea
              value={menu.greeting}
              onChange={(e) => set({ greeting: e.target.value })}
              placeholder="Thanks for calling Leadaro."
              className="min-h-[56px]"
            />
          </Field>
          <Field label="Wait for a keypress" hint="Before repeating the menu.">
            <Select
              value={String(menu.timeout_seconds)}
              onChange={(e) => set({ timeout_seconds: Number(e.target.value) })}
              options={[3, 5, 6, 8, 10].map((n) => ({
                value: String(n), label: `${n} seconds`,
              }))}
            />
          </Field>
          <Field label="Repeat the menu" hint="Then hand to the AI agent.">
            <Select
              value={String(menu.repeat_limit)}
              onChange={(e) => set({ repeat_limit: Number(e.target.value) })}
              options={[0, 1, 2, 3].map((n) => ({
                value: String(n),
                label: n === 0 ? "Never repeat" : `${n} time${n > 1 ? "s" : ""}`,
              }))}
            />
          </Field>
          <Field label="If they press something unassigned" className="sm:col-span-2">
            <Input
              value={menu.invalid_message}
              onChange={(e) => set({ invalid_message: e.target.value })}
              placeholder="Sorry, I didn't get that."
            />
          </Field>
        </div>

        <div>
          <div className="mb-2 flex items-center justify-between">
            <h4 className="text-sm font-semibold uppercase tracking-wide text-faint">
              Options
            </h4>
            <Button
              onClick={() => set({
                options: [...menu.options, {
                  digit: nextFree, label: "", action: "ai_agent",
                }],
              })}
              disabled={menu.options.length >= DIGITS.length}
            >
              <Plus size={12} /> Add option
            </Button>
          </div>

          <div className="space-y-2">
            {menu.options.map((o, i) => (
              <div key={i} className="rounded-card border border-line p-3">
                <div className="flex flex-wrap items-end gap-2">
                  <Field label="Key" className="w-[74px]">
                    <Select
                      value={o.digit}
                      onChange={(e) => setOption(i, { digit: e.target.value })}
                      options={DIGITS.map((d) => ({ value: d, label: d }))}
                    />
                  </Field>
                  <Field label="Spoken as" className="min-w-[180px] flex-1">
                    <Input
                      value={o.label}
                      onChange={(e) => setOption(i, { label: e.target.value })}
                      placeholder="for sales"
                    />
                  </Field>
                  <Field label="Then" className="min-w-[190px]">
                    <Select
                      value={o.action}
                      onChange={(e) =>
                        setOption(i, { action: e.target.value as MenuOption["action"] })}
                      options={ACTIONS}
                    />
                  </Field>
                  <Button
                    variant="ghost"
                    aria-label="Remove option"
                    onClick={() => set({ options: menu.options.filter((_, j) => j !== i) })}
                  >
                    <Trash2 size={13} />
                  </Button>
                </div>

                {o.action === "transfer" && (
                  <Field label="Transfer to" className="mt-2 max-w-xs">
                    <Input
                      value={o.target ?? ""}
                      onChange={(e) => setOption(i, { target: e.target.value })}
                      placeholder="+14155550123"
                    />
                  </Field>
                )}
                <Field
                  label="Say before acting"
                  hint="Optional."
                  className="mt-2"
                >
                  <Input
                    value={o.message ?? ""}
                    onChange={(e) => setOption(i, { message: e.target.value })}
                    placeholder="One moment, connecting you now."
                  />
                </Field>
              </div>
            ))}

            {menu.options.length === 0 && (
              <p className="rounded-card border border-dashed border-line-strong px-4 py-8 text-center text-base text-muted">
                No options yet. Add one to build the menu.
              </p>
            )}
          </div>
        </div>

        {preview.trim() && (
          <div className="rounded-card bg-sunk p-3">
            <p className="mb-1 flex items-center gap-1.5 text-sm font-semibold text-ink">
              <Volume2 size={12} /> What the caller hears
            </p>
            <p className="text-base leading-relaxed text-ink">{preview}</p>
            <div className="mt-2 flex flex-wrap gap-1">
              {menu.options.map((o) => (
                <Chip key={o.digit} tone="primary">
                  {o.digit} → {o.action.replace(/_/g, " ")}
                </Chip>
              ))}
            </div>
          </div>
        )}
      </div>
    </Card>
  );
}
