"use client";

/**
 * API client. One place that knows about the token, the base URL, and how
 * errors come back — so no screen hand-rolls a fetch.
 */

const BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
const TOKEN_KEY = "leadaro_token";

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(TOKEN_KEY);
}

export function setToken(t: string) {
  window.localStorage.setItem(TOKEN_KEY, t);
}

export function clearToken() {
  window.localStorage.removeItem(TOKEN_KEY);
}

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const token = getToken();
  const isForm = init.body instanceof FormData;

  const res = await fetch(`${BASE}${path}`, {
    ...init,
    headers: {
      ...(isForm ? {} : { "Content-Type": "application/json" }),
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...init.headers,
    },
  });

  if (res.status === 401 && typeof window !== "undefined") {
    clearToken();
    window.location.href = "/login";
    throw new ApiError(401, "session expired");
  }

  if (!res.ok) {
    // FastAPI puts the message on `detail`; fall back to the status text.
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
    } catch {
      /* non-JSON error body */
    }
    throw new ApiError(res.status, detail);
  }

  if (res.status === 204) return undefined as T;
  return res.json();
}

export const api = {
  get:   <T>(p: string) => request<T>(p),
  post:  <T>(p: string, body?: unknown) =>
    request<T>(p, { method: "POST", body: body === undefined ? undefined : JSON.stringify(body) }),
  patch: <T>(p: string, body: unknown) =>
    request<T>(p, { method: "PATCH", body: JSON.stringify(body) }),
  put:   <T>(p: string, body: unknown) =>
    request<T>(p, { method: "PUT", body: JSON.stringify(body) }),
  del:   <T>(p: string) => request<T>(p, { method: "DELETE" }),
  upload: <T>(p: string, form: FormData) =>
    request<T>(p, { method: "POST", body: form }),
};

/** EventSource cannot set headers, so the SSE stream takes the token by query. */
export function eventStream(campaignId?: string): EventSource | null {
  const token = getToken();
  if (!token) return null;
  const q = new URLSearchParams({ token });
  if (campaignId) q.set("campaign_id", campaignId);
  return new EventSource(`${BASE}/events/stream?${q}`);
}

// ── shared types (mirror services/api/schemas.py) ───────────────────────────

export type Mode = "voice" | "call";

export type Campaign = {
  id: string;
  mode: Mode;
  name: string;
  description?: string | null;
  type?: string | null;
  goal?: string | null;
  status: "draft" | "scheduled" | "active" | "paused" | "completed" | "archived";
  priority: "low" | "normal" | "high" | "urgent";
  tags: string[];
  timezone: string;
  language: string;
  country?: string | null;
  department?: string | null;
  caller_id?: string | null;
  caller_number_id?: string | null;
  voice_type: "ai" | "human" | "hybrid";
  voice_id?: string | null;
  voice_config: Record<string, unknown>;
  script: Record<string, string>;
  flow: Record<string, unknown>;
  settings: Record<string, unknown>;
  compliance: Record<string, unknown>;
  schedule_mode: string;
  start_date?: string | null;
  end_date?: string | null;
  recurrence: Record<string, unknown>;
  holiday_rules: Record<string, unknown>;
  business_hours: { start?: string; end?: string };
  weekdays_only: boolean;
  weekends_only: boolean;
  max_daily_calls?: number | null;
  concurrent_calls: number;
  calls_per_minute: number;
  queue_size?: number | null;
  warmup_mode: boolean;
  /** Aggregates returned by the list endpoint, not stored columns. */
  lead_count?: number;
  done_count?: number;
};

export type Voice = {
  id: string;
  name: string;
  provider: string;
  gender?: string | null;
  accent?: string | null;
  language: string;
  tone?: string | null;
  vertical?: string | null;
  is_clone: boolean;
  rating?: number | null;
};

export type Lead = {
  id: string;
  first_name?: string | null;
  last_name?: string | null;
  phone: string;
  email?: string | null;
  company?: string | null;
  designation?: string | null;
  industry?: string | null;
  city?: string | null;
  country?: string | null;
  lead_score: number;
  tier?: "hot" | "warm" | "scrap" | null;
  tags: string[];
};

export type AudiencePreview = {
  total: number;
  reachable: number;
  duplicates: number;
  invalid: number;
  dnc: number;
  blacklisted: number;
  estimated_cost_usd: number;
  predicted_success_rate: number;
};
