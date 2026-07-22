"""
Realtime fan-out for the live monitor.

Postgres LISTEN/NOTIFY → in-process queues → SSE. One dedicated connection
listens; each subscriber gets a bounded queue filtered to their org. No Redis,
no WebSocket server — the live monitor is a read-only feed, so SSE is the whole
requirement.
"""
import asyncio
import contextlib
import json
import logging

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import StreamingResponse
from jose import JWTError, jwt

import db
from auth import JWT_ALG, JWT_SECRET, Principal, current_user

log = logging.getLogger(__name__)
router = APIRouter(prefix="/events", tags=["events"])

# org_id -> set of subscriber queues
_subs: dict[str, set[asyncio.Queue]] = {}
_listener_task: asyncio.Task | None = None
_listen_conn = None

# Bounded so one stalled browser tab cannot grow memory without limit.
QUEUE_MAX = 200
HEARTBEAT_SECONDS = 20


async def _ensure_listener() -> None:
    """Start the single LISTEN connection on first subscriber."""
    global _listener_task, _listen_conn
    if _listener_task and not _listener_task.done():
        return

    _listen_conn = await db.pool().acquire()

    def on_notify(_conn, _pid, _channel, payload: str) -> None:
        try:
            evt = json.loads(payload)
        except json.JSONDecodeError:
            return
        org = evt.get("org_id")
        if not org:
            return
        for q in list(_subs.get(org, ())):
            try:
                q.put_nowait(evt)
            except asyncio.QueueFull:
                # Slow consumer: drop the event rather than block the listener.
                # The client re-syncs from /calls/live/active on reconnect.
                pass

    await _listen_conn.add_listener("leadaro_events", on_notify)
    _listener_task = asyncio.current_task()


@router.get("/stream")
async def stream(
    request: Request,
    token: str = Query(..., description="JWT — EventSource cannot set headers"),
    campaign_id: str | None = None,
):
    """
    SSE stream of call and turn changes for the caller's org.

    The token comes as a query param because the browser EventSource API has no
    way to set an Authorization header. It is verified exactly as a bearer
    token would be.
    """
    try:
        claims = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALG])
    except JWTError:
        return StreamingResponse(
            iter([b"event: error\ndata: invalid token\n\n"]),
            media_type="text/event-stream", status_code=401,
        )

    org_id = claims["org"]
    q: asyncio.Queue = asyncio.Queue(maxsize=QUEUE_MAX)
    _subs.setdefault(org_id, set()).add(q)
    await _ensure_listener()

    async def gen():
        try:
            yield b": connected\n\n"
            while True:
                if await request.is_disconnected():
                    break
                try:
                    evt = await asyncio.wait_for(q.get(), timeout=HEARTBEAT_SECONDS)
                except asyncio.TimeoutError:
                    # Keeps proxies from closing an idle connection.
                    yield b": ping\n\n"
                    continue

                if campaign_id and evt.get("campaign_id") not in (campaign_id, None):
                    continue
                yield f"event: {evt['table']}\ndata: {json.dumps(evt)}\n\n".encode()
        finally:
            _subs.get(org_id, set()).discard(q)
            if not _subs.get(org_id):
                _subs.pop(org_id, None)

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",   # nginx: don't buffer the stream
        },
    )


@router.get("/subscribers")
async def subscriber_count(user: Principal = Depends(current_user)):
    """Operational visibility — how many live-monitor tabs are attached."""
    return {"org": len(_subs.get(user.org_id, ())),
            "total": sum(len(s) for s in _subs.values())}
