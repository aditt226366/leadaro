import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

import db
from routers import (
    analytics, auth_routes, automation, calls, campaigns, compliance, events,
    integrations, leads, numbers, scripts, voices,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await db.init_pool()
    yield
    await db.close_pool()


app = FastAPI(title="Leadaro Outreach API", version="0.1.0", lifespan=lifespan)

# Allowed browser origins for the dashboard. CORSMiddleware matches origins by
# EXACT string, so a single WEB_BASE_URL with a stray trailing slash silently
# breaks every dashboard call. To make that far less fragile:
#   - accept a comma-separated WEB_BASE_URL (prod + any custom domain),
#   - strip trailing slashes so "https://x/" and "https://x" both work,
#   - always keep the local dev origin so `run.ps1` still works,
#   - and allow our own leadaro-*.fly.dev hosts via regex so a re-launched Fly
#     app (which gets a new random name, e.g. leadaro-web -> leadaro-onjwyg)
#     doesn't require a code/secret change to log in. Scoped to leadaro-* so it
#     is not "any site on fly.dev". (Auth is a Bearer token in localStorage, not
#     a cookie, so a foreign origin can't read it regardless — this is defense
#     in depth, not the only guard.)
_origins = {
    o.strip().rstrip("/")
    for o in os.environ.get("WEB_BASE_URL", "http://localhost:3001").split(",")
    if o.strip()
}
_origins.add("http://localhost:3001")

app.add_middleware(
    CORSMiddleware,
    allow_origins=sorted(_origins),
    allow_origin_regex=r"https://leadaro-[a-z0-9-]+\.fly\.dev",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

for r in (
    auth_routes.router, campaigns.router, leads.router, voices.router,
    scripts.router, calls.router, analytics.router, events.router,
    numbers.router, automation.router, compliance.router, integrations.router,
):
    app.include_router(r)


@app.get("/health")
async def health():
    return {"ok": await db.fetchval("SELECT 1") == 1}


# Alias: Teploy's health probe hardcodes /api/health regardless of the "Health
# check URL" field's value (it never actually hit /health — see the deploy log
# note about probing /api/health "instead of /"). Same handler, no /api prefix
# on any other route, so this is purely to satisfy that platform convention.
app.add_api_route("/api/health", health, methods=["GET"])
