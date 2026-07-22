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

app.add_middleware(
    CORSMiddleware,
    allow_origins=[os.environ.get("WEB_BASE_URL", "http://localhost:3001")],
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
