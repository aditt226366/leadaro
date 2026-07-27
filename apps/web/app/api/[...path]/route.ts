// Runtime same-origin proxy: forwards /api/* to the real backend read from the
// API_BASE_URL env var AT REQUEST TIME. A next.config.js rewrite would bake the
// destination at build time (no good on Teploy, which can't pass build args),
// so this route handler is the mechanism instead. /api/health is a separate,
// more-specific route and is matched before this catch-all.
//
// Effect: the browser only ever talks to this web origin (no CORS), and the API
// location is a plain runtime env var. Local dev works with the default below.
import { NextRequest } from "next/server";

export const dynamic = "force-dynamic";

const apiBase = () =>
  (process.env.API_BASE_URL || "http://localhost:8000").replace(/\/+$/, "");

// Hop-by-hop / encoding headers that must NOT be blindly forwarded: fetch has
// already decompressed the body, so forwarding content-encoding/content-length
// would make the browser mis-decode it.
const STRIP = new Set(["content-encoding", "content-length", "transfer-encoding", "connection"]);

async function proxy(req: NextRequest, ctx: { params: Promise<{ path: string[] }> }) {
  const { path } = await ctx.params;
  const target = `${apiBase()}/${path.join("/")}${req.nextUrl.search}`;

  const headers = new Headers(req.headers);
  headers.delete("host");
  headers.delete("content-length"); // recomputed by fetch from the body we pass

  const hasBody = req.method !== "GET" && req.method !== "HEAD";
  const res = await fetch(target, {
    method: req.method,
    headers,
    body: hasBody ? await req.arrayBuffer() : undefined,
    redirect: "manual",
  });

  const out = new Headers(res.headers);
  for (const h of STRIP) out.delete(h);
  return new Response(res.body, { status: res.status, statusText: res.statusText, headers: out });
}

export const GET = proxy;
export const POST = proxy;
export const PUT = proxy;
export const PATCH = proxy;
export const DELETE = proxy;
export const HEAD = proxy;
export const OPTIONS = proxy;
