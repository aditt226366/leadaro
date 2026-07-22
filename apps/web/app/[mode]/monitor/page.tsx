"use client";
import { Suspense, useEffect, useMemo, useState } from "react";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import {
  PhoneCall, Radio, PhoneForwarded, Voicemail, XCircle, RotateCw,
  Globe2, Activity, ChevronRight,
} from "lucide-react";
import { PageHeader } from "@/components/shell/TopBar";
import { Card, StatCard } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Chip } from "@/components/ui/Chip";
import { Waveform, LiveDot } from "@/components/ui/Waveform";
import { useLiveCalls, type LiveCall } from "@/lib/useLiveCalls";
import type { Mode } from "@/lib/api";
import { cn, dur, num } from "@/lib/cn";

export default function MonitorPage() {
  // useSearchParams() opts the tree below it into client rendering, which
  // Next requires a Suspense boundary for — the rest of the page has no
  // reason to wait on it, so the boundary sits right at the query read.
  return (
    <Suspense fallback={null}>
      <MonitorPageInner />
    </Suspense>
  );
}

function MonitorPageInner() {
  const { mode } = useParams<{ mode: Mode }>();
  const router = useRouter();
  const searchParams = useSearchParams();
  const { calls, feed, connected, error, refresh } = useLiveCalls();
  // A call just placed from the leads list arrives here as ?call=<id> so it's
  // the one shown in the console the moment it appears in the live feed.
  const [focus, setFocus] = useState<string | null>(searchParams.get("call"));

  const stats = useMemo(() => {
    const running = calls.filter((c) => c.status === "connected").length;
    const ringing = calls.filter((c) => c.status === "ringing").length;
    const byCountry = calls.reduce<Record<string, number>>((acc, c) => {
      const k = c.country || "Unknown";
      acc[k] = (acc[k] ?? 0) + 1;
      return acc;
    }, {});
    return {
      running, ringing,
      total: calls.length,
      countries: Object.entries(byCountry).sort((a, b) => b[1] - a[1]),
    };
  }, [calls]);

  const selected = calls.find((c) => c.id === focus) ?? calls[0];

  return (
    <>
      <PageHeader
        title="Live Monitor"
        subtitle="Calls in flight right now, streamed as they change."
      >
        <span className="flex items-center gap-2 rounded-pill border border-line-strong bg-surface px-2.5 py-1 text-sm">
          <LiveDot on={connected} />
          <span className={connected ? "text-ink" : "text-muted"}>
            {connected ? "Stream connected" : "Reconnecting…"}
          </span>
        </span>
        <Button onClick={refresh}><RotateCw size={13} /> Refresh</Button>
      </PageHeader>

      {error && (
        <p className="mb-card rounded-card bg-neg-wash px-4 py-2.5 text-base text-neg">
          {error}
        </p>
      )}

      <div className="grid grid-cols-2 gap-card lg:grid-cols-4">
        <StatCard icon={PhoneCall} label="Calls running" value={num(stats.running)} />
        <StatCard icon={Radio} label="Ringing" value={num(stats.ringing)} />
        <StatCard icon={PhoneForwarded} label="Total in flight" value={num(stats.total)} />
        <StatCard
          icon={Globe2}
          label="Countries"
          value={num(stats.countries.length)}
        />
      </div>

      <div className="mt-card grid gap-card lg:grid-cols-3">
        {/* ── live call board ─────────────────────────────────────────── */}
        <Card className="lg:col-span-2" pad={false}>
          <div className="flex items-center justify-between border-b border-line px-card py-3">
            <h3 className="text-base font-semibold text-ink">Active calls</h3>
            <Chip tone={stats.total ? "primary" : "neutral"}>
              {num(stats.total)} live
            </Chip>
          </div>

          {calls.length === 0 ? (
            <div className="px-card py-14 text-center">
              <Radio size={22} className="mx-auto text-faint" />
              <p className="mt-2 font-medium text-ink">No calls in flight</p>
              <p className="mt-1 text-base text-muted">
                Launch an active campaign and calls will appear here as they connect.
              </p>
              <Button
                variant="primary"
                className="mt-3"
                onClick={() => router.push(`/${mode}/campaigns`)}
              >
                Go to campaigns <ChevronRight size={13} />
              </Button>
            </div>
          ) : (
            <ul className="divide-y divide-line">
              {calls.map((c) => (
                <CallRow
                  key={c.id}
                  call={c}
                  selected={c.id === selected?.id}
                  onClick={() => setFocus(c.id)}
                  onOpen={() => router.push(`/${mode}/calls/${c.id}`)}
                />
              ))}
            </ul>
          )}
        </Card>

        {/* ── right rail: console + feed + geography ──────────────────── */}
        <div className="space-y-card">
          <Card>
            <h3 className="mb-2 text-base font-semibold text-ink">Call console</h3>
            {selected ? (
              <>
                <p className="font-medium text-ink">
                  {[selected.first_name, selected.last_name].filter(Boolean).join(" ") ||
                    selected.to_number}
                </p>
                <p className="text-sm text-muted">
                  {selected.company ?? "—"} · {selected.campaign_name ?? "—"}
                </p>
                <Waveform
                  active={selected.status === "connected"}
                  className="mt-3"
                />
                <p className="mt-2 min-h-[38px] rounded-md bg-sunk px-2.5 py-2 text-sm leading-snug text-ink">
                  {selected.last_line ?? (
                    <span className="text-muted">Waiting for the first turn…</span>
                  )}
                </p>
                <dl className="mt-3 space-y-1.5 text-sm">
                  <div className="flex justify-between">
                    <dt className="text-muted">Turns</dt>
                    <dd className="tnum font-semibold text-ink">{selected.turn_count}</dd>
                  </div>
                  <div className="flex justify-between">
                    <dt className="text-muted">Answered by</dt>
                    <dd className="font-semibold capitalize text-ink">
                      {selected.answered_by}
                    </dd>
                  </div>
                  <div className="flex justify-between">
                    <dt className="text-muted">Elapsed</dt>
                    <dd className="tnum font-semibold text-ink">
                      <Elapsed since={selected.started_at} />
                    </dd>
                  </div>
                </dl>
              </>
            ) : (
              <p className="py-6 text-center text-sm text-muted">
                Select a call to inspect it.
              </p>
            )}
          </Card>

          <Card pad={false}>
            <div className="flex items-center justify-between border-b border-line px-card py-2.5">
              <h3 className="flex items-center gap-1.5 text-base font-semibold text-ink">
                <Activity size={14} className="text-muted" /> Live feed
              </h3>
              <LiveDot on={connected} />
            </div>
            <ul className="max-h-[240px] divide-y divide-line overflow-y-auto">
              {feed.length === 0 && (
                <li className="px-card py-6 text-center text-sm text-muted">
                  Events appear here as calls progress.
                </li>
              )}
              {feed.map((f) => (
                <li key={f.id} className="flex items-center gap-2 px-card py-2 text-sm">
                  <span
                    className={cn(
                      "size-1.5 shrink-0 rounded-full",
                      f.kind === "call" ? "bg-primary" : "bg-c5",
                    )}
                  />
                  <span className="flex-1 truncate text-ink">{f.text}</span>
                  <span className="tnum shrink-0 text-tiny text-faint">
                    {new Date(f.at).toLocaleTimeString([], {
                      hour: "2-digit", minute: "2-digit", second: "2-digit",
                    })}
                  </span>
                </li>
              ))}
            </ul>
          </Card>

          <Card>
            <h3 className="mb-2 flex items-center gap-1.5 text-base font-semibold text-ink">
              <Globe2 size={14} className="text-muted" /> Calls by country
            </h3>
            {stats.countries.length === 0 ? (
              <p className="py-3 text-center text-sm text-muted">No active calls.</p>
            ) : (
              <ul className="space-y-2">
                {stats.countries.map(([country, n]) => (
                  <li key={country} className="flex items-center gap-2 text-base">
                    <span className="w-10 shrink-0 font-mono text-sm text-muted">
                      {country}
                    </span>
                    <span className="h-1.5 flex-1 overflow-hidden rounded-full bg-line">
                      <span
                        className="block h-full rounded-full bg-primary"
                        style={{ width: `${(n / stats.total) * 100}%` }}
                      />
                    </span>
                    <span className="tnum w-6 text-right font-semibold text-ink">{n}</span>
                  </li>
                ))}
              </ul>
            )}
          </Card>
        </div>
      </div>
    </>
  );
}

function CallRow({
  call, selected, onClick, onOpen,
}: {
  call: LiveCall;
  selected: boolean;
  onClick: () => void;
  onOpen: () => void;
}) {
  const name =
    [call.first_name, call.last_name].filter(Boolean).join(" ") || call.to_number;
  const tone =
    call.status === "connected" ? "pos"
    : call.status === "ringing" ? "warn"
    : "neutral";

  return (
    <li
      onClick={onClick}
      className={cn(
        "flex cursor-pointer items-center gap-3 px-card py-3 transition-colors",
        selected ? "bg-primary-wash/50" : "hover:bg-sunk",
      )}
    >
      <span className="grid size-8 shrink-0 place-items-center rounded-full bg-primary-wash text-tiny font-bold text-primary-ink">
        {name.slice(0, 2).toUpperCase()}
      </span>

      <span className="min-w-0 flex-1">
        <span className="flex items-center gap-2">
          <span className="truncate font-medium text-ink">{name}</span>
          <Chip tone={tone}>{call.status}</Chip>
        </span>
        <span className="block truncate text-sm text-muted">
          {call.last_line ?? `${call.campaign_name ?? "—"} · ${call.to_number}`}
        </span>
      </span>

      <Waveform active={call.status === "connected"} bars={14} className="h-6 w-20 shrink-0" />

      <span className="tnum w-12 shrink-0 text-right text-sm text-muted">
        <Elapsed since={call.started_at} />
      </span>

      <button
        onClick={(e) => { e.stopPropagation(); onOpen(); }}
        className="shrink-0 text-faint hover:text-ink"
        aria-label="Open call detail"
      >
        <ChevronRight size={15} />
      </button>
    </li>
  );
}

/** Ticking elapsed timer. */
function Elapsed({ since }: { since: string }) {
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(t);
  }, []);

  const secs = Math.max(0, (now - new Date(since).getTime()) / 1000);
  return <>{dur(secs)}</>;
}
