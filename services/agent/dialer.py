"""
Outbound dialer.

    python services/agent/dialer.py

Picks due leads, enforces every calling constraint, then creates a SIP
participant which dispatches a worker job.

Compliance is enforced HERE, before the dial — not in the UI. A number on the
suppression list must be impossible to call regardless of which screen or API
route enqueued it, and every skip is written to the audit log.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
from datetime import datetime, time as dtime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from dotenv import load_dotenv
from livekit import api

# db.py is shared with the API service — one definition of the pool and codecs.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "api"))
import db  # noqa: E402

load_dotenv()
logging.basicConfig(level=logging.INFO)
log = logging.getLogger("dialer")

OUTBOUND_TRUNK = os.environ.get("SIP_OUTBOUND_TRUNK_ID", "")
AGENT_NAME = "leadaro-voice"
POLL_SECONDS = 5


# ── gates ────────────────────────────────────────────────────────────────────

def within_business_hours(campaign: dict, now: datetime | None = None) -> bool:
    """
    Local-time window check, in the LEAD's campaign timezone.

    Calling someone at 3am because the server is in another timezone is both a
    compliance problem and the fastest way to get a number blocked.
    """
    name = campaign.get("timezone") or "UTC"
    try:
        tz = ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError):
        # Fail CLOSED. An unresolvable timezone must never fall back to "open" —
        # that is how you end up dialling someone at 3am. Needs the `tzdata`
        # package on hosts without a system IANA database (i.e. Windows).
        log.error("unknown timezone %r for campaign %s — skipping this tick",
                  name, campaign.get("name"))
        return False

    now = (now or datetime.now(timezone.utc)).astimezone(tz)

    if campaign.get("weekdays_only") and now.weekday() >= 5:
        return False
    if campaign.get("weekends_only") and now.weekday() < 5:
        return False

    hours = campaign.get("business_hours") or {}
    start = _parse_hhmm(hours.get("start", "09:00"))
    end = _parse_hhmm(hours.get("end", "18:00"))
    if not (start <= now.time() <= end):
        return False

    holidays = (campaign.get("holiday_rules") or {}).get("dates") or []
    return now.date().isoformat() not in holidays


def _parse_hhmm(s: str) -> dtime:
    try:
        h, m = s.split(":")
        return dtime(int(h), int(m))
    except (ValueError, AttributeError):
        return dtime(9, 0)


async def daily_cap_reached(campaign: dict) -> bool:
    cap = campaign.get("max_daily_calls")
    if not cap:
        return False
    used = await db.fetchval(
        """SELECT count(*) FROM calls
           WHERE campaign_id = $1 AND started_at::date = (now() AT TIME ZONE $2)::date""",
        campaign["id"], campaign.get("timezone") or "UTC",
    )
    return used >= cap


async def live_call_count(campaign_id: str) -> int:
    return await db.fetchval(
        "SELECT count(*) FROM calls WHERE campaign_id = $1 AND ended_at IS NULL",
        campaign_id,
    ) or 0


async def is_suppressed(org_id: str, phone: str) -> str | None:
    """Returns the suppression kind, or None. Checked immediately before dial."""
    return await db.fetchval(
        "SELECT kind FROM suppression_list WHERE org_id = $1 AND phone = $2 LIMIT 1",
        org_id, phone,
    )


# ── dialing ──────────────────────────────────────────────────────────────────

async def place_call(campaign: dict, lead: dict, cl_id: str) -> str | None:
    org_id = str(campaign["org_id"])

    # Re-check suppression at dial time: a number may have gone DNC since the
    # audience was built.
    if kind := await is_suppressed(org_id, lead["phone"]):
        await db.execute(
            """UPDATE campaign_leads SET state='suppressed', suppressed_reason=$2
               WHERE id=$1""",
            cl_id, kind,
        )
        await db.execute(
            """INSERT INTO audit_log (org_id, action, entity, entity_id, detail)
               VALUES ($1,'dial.skipped','campaign_lead',$2,$3)""",
            org_id, cl_id, {"reason": kind, "phone": lead["phone"]},
        )
        log.info("skipped %s (%s)", lead["phone"], kind)
        return None

    from_number = await db.fetchval(
        "SELECT e164 FROM phone_numbers WHERE id = $1", campaign.get("caller_number_id")
    ) or campaign.get("caller_id")

    call_id = await db.fetchval(
        """INSERT INTO calls (org_id, campaign_id, campaign_lead_id, lead_id,
                              direction, to_number, from_number, status)
           VALUES ($1,$2,$3,$4,'outbound',$5,$6,'initiated') RETURNING id""",
        org_id, campaign["id"], cl_id, lead["id"], lead["phone"], from_number,
    )

    room = f"call-{call_id}"
    lkapi = api.LiveKitAPI()
    try:
        # Dispatch the worker into the room first, so the agent is listening
        # before the callee can answer.
        await lkapi.agent_dispatch.create_dispatch(
            api.CreateAgentDispatchRequest(
                agent_name=AGENT_NAME,
                room=room,
                metadata=json.dumps({"call_id": str(call_id)}),
            )
        )
        await lkapi.sip.create_sip_participant(
            api.CreateSIPParticipantRequest(
                sip_trunk_id=OUTBOUND_TRUNK,
                sip_call_to=lead["phone"],
                room_name=room,
                participant_identity=f"lead-{lead['id']}",
                participant_name=f"{lead.get('first_name') or ''} {lead.get('last_name') or ''}".strip(),
                # Returning immediately keeps the dialer loop free to place the
                # next call while this one rings.
                wait_until_answered=False,
            )
        )
        await db.execute(
            "UPDATE calls SET status='ringing', room_name=$2 WHERE id=$1",
            call_id, room,
        )
        await db.execute(
            """UPDATE campaign_leads
               SET state='dialing', attempts = attempts + 1 WHERE id = $1""",
            cl_id,
        )
        log.info("dialing %s for campaign %s", lead["phone"], campaign["name"])
        return str(call_id)

    except Exception as e:
        log.exception("dial failed for %s", lead["phone"])
        await db.execute(
            "UPDATE calls SET status='failed', ended_at=now(), error=$2 WHERE id=$1",
            call_id, str(e)[:500],
        )
        await _schedule_retry(campaign, cl_id)
        return None
    finally:
        await lkapi.aclose()


async def _schedule_retry(campaign: dict, cl_id: str) -> None:
    settings = campaign.get("settings") or {}
    max_attempts = int(settings.get("retry_attempts", 3))
    delay_min = int(settings.get("retry_delay_minutes", 60))

    row = await db.fetchrow(
        "SELECT attempts FROM campaign_leads WHERE id = $1", cl_id
    )
    if row and row["attempts"] >= max_attempts:
        await db.execute(
            "UPDATE campaign_leads SET state='unreachable' WHERE id=$1", cl_id
        )
    else:
        await db.execute(
            """UPDATE campaign_leads
               SET state='pending', next_attempt_at = now() + ($2 || ' minutes')::interval
               WHERE id=$1""",
            cl_id, str(delay_min),
        )


# ── loop ─────────────────────────────────────────────────────────────────────

async def tick() -> int:
    """One pass over every active campaign. Returns calls placed."""
    campaigns = await db.fetch(
        """SELECT * FROM campaigns
           WHERE status = 'active' AND archived_at IS NULL
             AND (start_date IS NULL OR start_date <= now())
             AND (end_date   IS NULL OR end_date   >= now())"""
    )

    placed = 0
    for campaign in campaigns:
        campaign = dict(campaign)

        if not within_business_hours(campaign):
            continue
        if await daily_cap_reached(campaign):
            continue

        concurrent = int(campaign.get("concurrent_calls") or 5)
        # Warm-up mode ramps a new number gently to protect its reputation.
        if campaign.get("warmup_mode"):
            concurrent = max(1, concurrent // 4)

        free = concurrent - await live_call_count(str(campaign["id"]))
        if free <= 0:
            continue

        rows = await db.fetch(
            """SELECT cl.id AS cl_id, row_to_json(l) AS lead
               FROM campaign_leads cl
               JOIN leads l ON l.id = cl.lead_id
               WHERE cl.campaign_id = $1
                 AND cl.state IN ('pending','queued')
                 AND (cl.next_attempt_at IS NULL OR cl.next_attempt_at <= now())
               ORDER BY l.lead_score DESC, cl.created_at
               LIMIT $2""",
            campaign["id"], free,
        )

        cpm = int(campaign.get("calls_per_minute") or 10)
        gap = 60.0 / max(cpm, 1)
        for row in rows:
            if await place_call(campaign, row["lead"], row["cl_id"]):
                placed += 1
            await asyncio.sleep(gap)   # rate limit

    return placed


async def main() -> None:
    await db.init_pool()
    log.info("dialer started (poll %ss)", POLL_SECONDS)
    try:
        while True:
            try:
                if n := await tick():
                    log.info("placed %d call(s)", n)
            except Exception:
                log.exception("tick failed; continuing")
            await asyncio.sleep(POLL_SECONDS)
    finally:
        await db.close_pool()


if __name__ == "__main__":
    asyncio.run(main())
