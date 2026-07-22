"use client";
import { useEffect, useRef, useState } from "react";
import {
  PhoneOutgoing, ChevronDown, FileUp, Hash, X, Loader2, Check,
  PhoneCall, AlertTriangle, Ban,
} from "lucide-react";
import { Button } from "@/components/ui/Button";
import { Field, Input, Select } from "@/components/ui/Form";
import { api, getToken, type Campaign, type Mode } from "@/lib/api";
import { cn } from "@/lib/cn";

type Contact = { name: string | null; phone: string; suppressed?: string | null };
type RowState = "idle" | "calling" | "placed" | "failed";

/**
 * "Call" launcher for the campaign header and the IVR screen.
 *
 * Two ways in, both ending in a real outbound call that inherits the campaign's
 * voice, script, caller ID and compliance:
 *   • from a file — upload a .csv or .pdf, see everyone in it, then call.
 *   • manual — type one number and dial it.
 *
 * The call it places is the same record a campaign dial produces, so it lands in
 * the campaign's call history automatically; `onPlaced` just refreshes the view.
 */
export function CallLauncher({
  mode,
  campaignId,
  campaigns,
  onPlaced,
}: {
  mode: Mode;
  campaignId?: string;
  campaigns?: Campaign[];
  onPlaced?: () => void;
}) {
  const [menuOpen, setMenuOpen] = useState(false);
  const [panel, setPanel] = useState<null | "file" | "manual">(null);
  const wrap = useRef<HTMLDivElement>(null);

  // When there is no fixed campaign (the IVR screen), the user picks which one
  // the calls go out as — the call needs a voice and a script from somewhere.
  const [pickedCampaign, setPickedCampaign] = useState(campaignId ?? "");
  const effectiveCampaign = campaignId ?? pickedCampaign;
  const needsPick = !campaignId && (campaigns?.length ?? 0) > 0;

  useEffect(() => {
    if (!menuOpen) return;
    const onDoc = (e: MouseEvent) => {
      if (wrap.current && !wrap.current.contains(e.target as Node)) setMenuOpen(false);
    };
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, [menuOpen]);

  function openPanel(which: "file" | "manual") {
    setMenuOpen(false);
    setPanel(which);
  }

  return (
    <div className="relative" ref={wrap}>
      <Button variant="primary" onClick={() => setMenuOpen((o) => !o)}>
        <PhoneOutgoing size={13} /> Call <ChevronDown size={12} className="opacity-70" />
      </Button>

      {menuOpen && (
        <div className="absolute right-0 z-30 mt-1.5 w-60 overflow-hidden rounded-card border border-line-strong bg-surface py-1 shadow-pop">
          <MenuItem icon={FileUp} title="From file" sub=".csv or .pdf"
            onClick={() => openPanel("file")} />
          <MenuItem icon={Hash} title="Enter number manually" sub="Dial one number"
            onClick={() => openPanel("manual")} />
        </div>
      )}

      {panel && (
        <Modal
          title={panel === "file" ? "Call from a file" : "Call a number"}
          onClose={() => setPanel(null)}
        >
          {needsPick && (
            <Field label="Call as campaign" className="mb-4"
              hint="The call uses this campaign's voice, script and caller ID.">
              <Select
                value={pickedCampaign}
                onChange={(e) => setPickedCampaign(e.target.value)}
                options={[
                  { value: "", label: "Select a campaign…" },
                  ...(campaigns ?? []).map((c) => ({ value: c.id, label: c.name })),
                ]}
              />
            </Field>
          )}

          {panel === "file" ? (
            <FilePanel
              campaignId={effectiveCampaign}
              blocked={needsPick && !pickedCampaign}
              onPlaced={onPlaced}
            />
          ) : (
            <ManualPanel
              campaignId={effectiveCampaign}
              blocked={needsPick && !pickedCampaign}
              onPlaced={onPlaced}
            />
          )}
        </Modal>
      )}
    </div>
  );
}

function MenuItem({
  icon: Icon, title, sub, onClick,
}: {
  icon: typeof FileUp; title: string; sub: string; onClick: () => void;
}) {
  return (
    <button
      onClick={onClick}
      className="flex w-full items-center gap-3 px-3 py-2 text-left hover:bg-sunk"
    >
      <span className="grid size-8 shrink-0 place-items-center rounded-full bg-primary-wash text-primary-ink">
        <Icon size={15} />
      </span>
      <span className="min-w-0">
        <span className="block text-sm font-semibold text-ink">{title}</span>
        <span className="block text-tiny text-muted">{sub}</span>
      </span>
    </button>
  );
}

function Modal({
  title, onClose, children,
}: {
  title: string; onClose: () => void; children: React.ReactNode;
}) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <div
      className="fixed inset-0 z-40 grid place-items-start justify-center overflow-y-auto bg-ink/30 p-4 pt-[8vh]"
      onMouseDown={onClose}
    >
      <div
        className="w-full max-w-xl rounded-card border border-line-strong bg-surface shadow-pop"
        onMouseDown={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between border-b border-line px-card py-3">
          <h3 className="text-base font-semibold text-ink">{title}</h3>
          <button
            onClick={onClose}
            aria-label="Close"
            className="grid size-7 place-items-center rounded-full text-muted hover:bg-sunk hover:text-ink"
          >
            <X size={15} />
          </button>
        </div>
        <div className="px-card py-4">{children}</div>
      </div>
    </div>
  );
}

function ManualPanel({
  campaignId, blocked, onPlaced,
}: {
  campaignId: string; blocked: boolean; onPlaced?: () => void;
}) {
  const [name, setName] = useState("");
  const [phone, setPhone] = useState("");
  const [state, setState] = useState<RowState>("idle");
  const [error, setError] = useState("");

  async function call() {
    if (!phone.trim()) return;
    setState("calling");
    setError("");
    try {
      await api.post("/calls/originate", {
        phone: phone.trim(),
        name: name.trim() || null,
        campaign_id: campaignId || null,
      });
      setState("placed");
      onPlaced?.();
    } catch (e) {
      setState("failed");
      setError(e instanceof Error ? e.message : "Call failed");
    }
  }

  return (
    <>
      <div className="flex items-end gap-2">
        <Field label="Name" className="w-40">
          <Input value={name} onChange={(e) => setName(e.target.value)}
            placeholder="Optional" />
        </Field>
        <Field label="Phone number" className="flex-1">
          <Input value={phone} onChange={(e) => setPhone(e.target.value)}
            placeholder="+91 98765 43210" inputMode="tel"
            onKeyDown={(e) => e.key === "Enter" && !blocked && call()} />
        </Field>
        <Button variant="primary" onClick={call}
          disabled={blocked || !phone.trim() || state === "calling"}>
          {state === "calling"
            ? <><Loader2 size={13} className="animate-spin" /> Calling</>
            : <><PhoneCall size={13} /> Call</>}
        </Button>
      </div>

      {blocked && (
        <p className="mt-3 text-sm text-muted">Pick a campaign above first.</p>
      )}
      {state === "placed" && (
        <p className="mt-3 flex items-center gap-1.5 rounded-card bg-pos-wash px-3 py-2 text-sm text-pos">
          <Check size={14} /> Calling {phone}. It will appear in the call history.
        </p>
      )}
      {error && (
        <p className="mt-3 flex items-center gap-1.5 rounded-card bg-neg-wash px-3 py-2 text-sm text-neg">
          <AlertTriangle size={14} /> {error}
        </p>
      )}
    </>
  );
}

function FilePanel({
  campaignId, blocked, onPlaced,
}: {
  campaignId: string; blocked: boolean; onPlaced?: () => void;
}) {
  const [parsing, setParsing] = useState(false);
  const [contacts, setContacts] = useState<Contact[] | null>(null);
  const [meta, setMeta] = useState<{ invalid: number; total_rows: number } | null>(null);
  const [rowState, setRowState] = useState<Record<string, RowState>>({});
  const [callingAll, setCallingAll] = useState(false);
  const [error, setError] = useState("");
  const fileRef = useRef<HTMLInputElement>(null);

  const callable = (contacts ?? []).filter((c) => !c.suppressed);

  async function onFile(file: File) {
    setParsing(true);
    setError("");
    setContacts(null);
    setRowState({});
    try {
      const form = new FormData();
      form.append("file", file);
      const res = await api.upload<{ contacts: Contact[]; invalid: number; total_rows: number }>(
        "/calls/parse-contacts", form,
      );
      setContacts(res.contacts);
      setMeta({ invalid: res.invalid, total_rows: res.total_rows });
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not read that file");
    } finally {
      setParsing(false);
    }
  }

  async function callOne(c: Contact) {
    setRowState((s) => ({ ...s, [c.phone]: "calling" }));
    try {
      await api.post("/calls/originate", {
        phone: c.phone, name: c.name, campaign_id: campaignId || null,
      });
      setRowState((s) => ({ ...s, [c.phone]: "placed" }));
      onPlaced?.();
    } catch {
      setRowState((s) => ({ ...s, [c.phone]: "failed" }));
    }
  }

  async function callAll() {
    setCallingAll(true);
    setError("");
    const pending = callable.filter((c) => rowState[c.phone] !== "placed");
    setRowState((s) => {
      const next = { ...s };
      pending.forEach((c) => { next[c.phone] = "calling"; });
      return next;
    });
    try {
      const res = await api.post<{ queued: number; call_ids: string[] }>("/calls/batch", {
        campaign_id: campaignId || null,
        contacts: pending.map((c) => ({ phone: c.phone, name: c.name })),
      });
      setRowState((s) => {
        const next = { ...s };
        pending.forEach((c) => { next[c.phone] = "placed"; });
        return next;
      });
      onPlaced?.();
      if (!res.queued) setError("Nothing was queued — all numbers were skipped.");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Batch call failed");
      setRowState((s) => {
        const next = { ...s };
        pending.forEach((c) => { next[c.phone] = "idle"; });
        return next;
      });
    } finally {
      setCallingAll(false);
    }
  }

  return (
    <>
      {!contacts && (
        <div
          className="grid cursor-pointer place-items-center rounded-card border border-dashed border-line-strong bg-sunk/40 px-4 py-10 text-center hover:border-primary/50"
          onClick={() => fileRef.current?.click()}
        >
          {parsing ? (
            <Loader2 size={20} className="animate-spin text-muted" />
          ) : (
            <>
              <FileUp size={22} className="mb-2 text-muted" />
              <p className="text-sm font-medium text-ink">Upload a .csv or .pdf</p>
              <p className="text-tiny text-muted">
                We read the names and phone numbers out of it.
              </p>
            </>
          )}
          <input
            ref={fileRef}
            type="file"
            accept=".csv,.pdf"
            className="hidden"
            onChange={(e) => e.target.files?.[0] && onFile(e.target.files[0])}
          />
        </div>
      )}

      {error && (
        <p className="mb-3 flex items-center gap-1.5 rounded-card bg-neg-wash px-3 py-2 text-sm text-neg">
          <AlertTriangle size={14} /> {error}
        </p>
      )}

      {contacts && (
        <>
          <div className="mb-2 flex items-center justify-between">
            <p className="text-sm text-muted">
              {callable.length} callable
              {meta && meta.invalid > 0 && ` · ${meta.invalid} unreadable`}
              {contacts.length - callable.length > 0 &&
                ` · ${contacts.length - callable.length} suppressed`}
            </p>
            <button
              className="text-sm font-semibold text-primary-ink hover:underline"
              onClick={() => { setContacts(null); setMeta(null); }}
            >
              Choose another file
            </button>
          </div>

          <div className="max-h-[40vh] overflow-y-auto rounded-card border border-line">
            <table className="w-full text-sm">
              <thead className="sticky top-0 bg-sunk text-tiny uppercase tracking-wide text-muted">
                <tr>
                  <th className="px-3 py-2 text-left font-semibold">Name</th>
                  <th className="px-3 py-2 text-left font-semibold">Phone</th>
                  <th className="px-3 py-2 text-right font-semibold">Action</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-line">
                {contacts.map((c) => {
                  const st = rowState[c.phone] ?? "idle";
                  return (
                    <tr key={c.phone}>
                      <td className="px-3 py-2 text-ink">{c.name ?? "—"}</td>
                      <td className="tnum px-3 py-2 text-muted">{c.phone}</td>
                      <td className="px-3 py-2 text-right">
                        {c.suppressed ? (
                          <span className="inline-flex items-center gap-1 text-tiny text-neg">
                            <Ban size={12} /> {c.suppressed}
                          </span>
                        ) : st === "placed" ? (
                          <span className="inline-flex items-center gap-1 text-tiny text-pos">
                            <Check size={12} /> Calling
                          </span>
                        ) : st === "failed" ? (
                          <button className="text-tiny font-semibold text-neg hover:underline"
                            onClick={() => callOne(c)}>Retry</button>
                        ) : (
                          <Button size="sm" onClick={() => callOne(c)} disabled={blocked || st === "calling"}>
                            {st === "calling"
                              ? <Loader2 size={12} className="animate-spin" />
                              : <><PhoneCall size={12} /> Call</>}
                          </Button>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>

          {blocked ? (
            <p className="mt-3 text-sm text-muted">Pick a campaign above to start calling.</p>
          ) : (
            <div className="mt-3 flex justify-end">
              <Button variant="primary" onClick={callAll}
                disabled={callingAll || callable.length === 0}>
                {callingAll
                  ? <><Loader2 size={13} className="animate-spin" /> Calling all</>
                  : <><PhoneOutgoing size={13} /> Call all {callable.length}</>}
              </Button>
            </div>
          )}
        </>
      )}
    </>
  );
}
