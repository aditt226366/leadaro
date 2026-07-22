"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { api, eventStream } from "@/lib/api";

export type LiveCall = {
  id: string;
  status: string;
  answered_by: string;
  started_at: string;
  to_number: string;
  first_name?: string | null;
  last_name?: string | null;
  company?: string | null;
  country?: string | null;
  campaign_name?: string | null;
  last_line?: string | null;
  turn_count: number;
};

export type FeedItem = {
  id: string;
  at: number;
  kind: "call" | "turn";
  text: string;
  callId: string;
};

/**
 * Live call state, driven by the server's SSE stream.
 *
 * The stream carries change *notifications*, not full rows — a NOTIFY payload
 * is capped at 8KB and we don't want transcripts flowing through it. So an
 * event triggers a refetch of the snapshot rather than patching local state.
 * That also means a dropped event self-heals on the next one.
 */
export function useLiveCalls(campaignId?: string) {
  const [calls, setCalls] = useState<LiveCall[]>([]);
  const [feed, setFeed] = useState<FeedItem[]>([]);
  const [connected, setConnected] = useState(false);
  const [error, setError] = useState("");

  // Coalesce bursts: 20 turns landing at once should cause one refetch.
  const pending = useRef<ReturnType<typeof setTimeout> | null>(null);

  const refresh = useCallback(async () => {
    try {
      const q = campaignId ? `?campaign_id=${campaignId}` : "";
      setCalls(await api.get<LiveCall[]>(`/calls/live/active${q}`));
      setError("");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not load active calls");
    }
  }, [campaignId]);

  const scheduleRefresh = useCallback(() => {
    if (pending.current) return;
    pending.current = setTimeout(() => {
      pending.current = null;
      void refresh();
    }, 400);
  }, [refresh]);

  useEffect(() => {
    void refresh();

    const es = eventStream(campaignId);
    if (!es) {
      setError("Not signed in");
      return;
    }

    es.onopen = () => setConnected(true);
    es.onerror = () => {
      // EventSource reconnects on its own; surface the gap without tearing down.
      setConnected(false);
    };

    const onEvent = (kind: "call" | "turn") => (e: MessageEvent) => {
      let data: Record<string, string> = {};
      try {
        data = JSON.parse(e.data);
      } catch {
        return;
      }
      setFeed((f) =>
        [
          {
            id: `${kind}-${data.id}-${Date.now()}`,
            at: Date.now(),
            kind,
            callId: data.call_id || data.id,
            text:
              kind === "call"
                ? `Call ${data.status ?? "updated"}${data.outcome ? ` — ${data.outcome}` : ""}`
                : "New turn",
          },
          ...f,
        ].slice(0, 60),   // the feed is a tail, not a log
      );
      scheduleRefresh();
    };

    es.addEventListener("calls", onEvent("call") as EventListener);
    es.addEventListener("turns", onEvent("turn") as EventListener);

    // Safety net: if the stream silently dies behind a proxy, this keeps the
    // board roughly current rather than frozen.
    const poll = setInterval(refresh, 15000);

    return () => {
      es.close();
      clearInterval(poll);
      if (pending.current) clearTimeout(pending.current);
    };
  }, [campaignId, refresh, scheduleRefresh]);

  return { calls, feed, connected, error, refresh };
}
