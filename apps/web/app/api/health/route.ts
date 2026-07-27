// Health endpoint for the WEB container's platform probe (Teploy hardcodes a
// GET /api/health check for Next.js apps; without a matching route the deploy
// hangs at "deploying"). App-router filesystem routes are matched BEFORE the
// afterFiles `/api/:path*` proxy rewrite in next.config.js, so this handles
// /api/health locally while every other /api/* still proxies to the backend.
// It intentionally reports only that the web server itself is up — it does NOT
// call the backend, so a cold/booting API can't make the web app look down.
export const dynamic = "force-dynamic";

export function GET() {
  return Response.json({ ok: true });
}
