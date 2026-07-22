"""
Integrations (FRD §16) and meeting booking (§11).

Credentials live in `integrations.secrets` and are never returned by the API —
the list endpoint reports only whether a provider is connected.
"""
import os
from datetime import datetime, timedelta, timezone

import httpx
from fastapi import APIRouter, Depends, HTTPException, status

import db
from auth import Principal, audit, current_user, requires

router = APIRouter(tags=["integrations"])

# Everything the FRD lists, with what's actually wired marked honestly. The UI
# renders `status` so a user is never left guessing why a toggle does nothing.
CATALOG = [
    ("google_calendar", "Google Calendar", "meetings", "available"),
    ("outlook",        "Outlook Calendar", "meetings", "planned"),
    ("calendly",       "Calendly",         "meetings", "planned"),
    ("hubspot",        "HubSpot",          "crm",      "available"),
    ("salesforce",     "Salesforce",       "crm",      "planned"),
    ("zoho",           "Zoho CRM",         "crm",      "planned"),
    ("pipedrive",      "Pipedrive",        "crm",      "planned"),
    ("slack",          "Slack",            "comms",    "available"),
    ("teams",          "Microsoft Teams",  "comms",    "planned"),
    ("webhook",        "Webhook",          "comms",    "available"),
    ("zapier",         "Zapier",           "comms",    "planned"),
    ("plivo",          "Plivo",            "telephony", "available"),
    ("twilio",         "Twilio",           "telephony", "planned"),
    ("elevenlabs",     "ElevenLabs",       "voice",    "available"),
    ("cartesia",       "Cartesia",         "voice",    "available"),
]


@router.get("/integrations")
async def list_integrations(user: Principal = Depends(current_user)):
    rows = await db.fetch(
        "SELECT provider, config, is_active, created_at FROM integrations WHERE org_id = $1",
        user.org_id,
    )
    connected = {r["provider"]: r for r in rows}

    return [
        {
            "provider": key,
            "name": name,
            "category": category,
            "status": status_,
            "connected": key in connected and connected[key]["is_active"],
            "config": connected.get(key, {}).get("config", {}),
            "connected_at": connected.get(key, {}).get("created_at"),
        }
        for key, name, category, status_ in CATALOG
    ]


@router.post("/integrations/{provider}")
async def connect(
    provider: str, body: dict, user: Principal = Depends(requires("manage_numbers")),
):
    known = {c[0] for c in CATALOG}
    if provider not in known:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"unknown provider: {provider}")

    await db.execute(
        """INSERT INTO integrations (org_id, provider, config, secrets, is_active)
           VALUES ($1,$2,$3,$4,true)
           ON CONFLICT (org_id, provider) DO UPDATE
             SET config = EXCLUDED.config,
                 secrets = CASE WHEN EXCLUDED.secrets = '{}'::jsonb
                                THEN integrations.secrets ELSE EXCLUDED.secrets END,
                 is_active = true""",
        user.org_id, provider, body.get("config", {}), body.get("secrets", {}),
    )
    await audit(user.org_id, user.user_id, "integration.connect", "integration",
                provider)
    return {"provider": provider, "connected": True}


@router.delete("/integrations/{provider}", status_code=status.HTTP_204_NO_CONTENT)
async def disconnect(
    provider: str, user: Principal = Depends(requires("manage_numbers")),
):
    await db.execute(
        "UPDATE integrations SET is_active = false WHERE org_id = $1 AND provider = $2",
        user.org_id, provider,
    )
    await audit(user.org_id, user.user_id, "integration.disconnect", "integration",
                provider)


# ── meetings (FRD §11) ──────────────────────────────────────────────────────

@router.get("/meetings")
async def list_meetings(user: Principal = Depends(current_user)):
    rows = await db.fetch(
        """SELECT m.*, l.first_name, l.last_name, l.company, l.email,
                  u.name AS assigned_name
           FROM meetings m
           LEFT JOIN leads l ON l.id = m.lead_id
           LEFT JOIN users u ON u.id = m.assigned_to
           WHERE m.org_id = $1 ORDER BY m.starts_at DESC LIMIT 100""",
        user.org_id,
    )
    return [
        {**r, "id": str(r["id"]),
         "lead_id": str(r["lead_id"]) if r["lead_id"] else None,
         "call_id": str(r["call_id"]) if r["call_id"] else None,
         "assigned_to": str(r["assigned_to"]) if r["assigned_to"] else None}
        for r in rows
    ]


@router.post("/meetings", status_code=status.HTTP_201_CREATED)
async def create_meeting(body: dict, user: Principal = Depends(current_user)):
    """
    Book a meeting. Writes locally first, then attempts the calendar push —
    a calendar outage must not lose the booking the AI already promised.
    """
    starts = datetime.fromisoformat(body["starts_at"].replace("Z", "+00:00"))
    ends = starts + timedelta(minutes=int(body.get("duration_minutes", 20)))

    row = await db.fetchrow(
        """INSERT INTO meetings (org_id, lead_id, call_id, assigned_to, provider,
                                 starts_at, ends_at, timezone, status)
           VALUES ($1,$2,$3,$4,$5,$6,$7,$8,'scheduled') RETURNING *""",
        user.org_id, body.get("lead_id"), body.get("call_id"),
        body.get("assigned_to") or user.user_id, body.get("provider", "google"),
        starts, ends, body.get("timezone", "UTC"),
    )

    external_id, join_url, warning = None, None, None
    try:
        external_id, join_url = await _push_to_google(user.org_id, row, body)
    except Exception as e:
        # Surfaced to the caller rather than swallowed — the meeting exists but
        # the invite didn't send, and someone needs to know that.
        warning = f"calendar sync failed: {str(e)[:160]}"

    if external_id:
        await db.execute(
            "UPDATE meetings SET external_id = $2, join_url = $3 WHERE id = $1",
            row["id"], external_id, join_url,
        )

    await audit(user.org_id, user.user_id, "meeting.create", "meeting", str(row["id"]))
    return {
        **row, "id": str(row["id"]),
        "lead_id": str(row["lead_id"]) if row["lead_id"] else None,
        "call_id": str(row["call_id"]) if row["call_id"] else None,
        "assigned_to": str(row["assigned_to"]) if row["assigned_to"] else None,
        "external_id": external_id, "join_url": join_url, "warning": warning,
    }


async def _push_to_google(org_id: str, meeting: dict, body: dict):
    """Create the event on Google Calendar. Returns (event_id, join_url)."""
    integ = await db.fetchrow(
        """SELECT secrets FROM integrations
           WHERE org_id = $1 AND provider = 'google_calendar' AND is_active""",
        org_id,
    )
    token = (integ or {}).get("secrets", {}).get("access_token")
    if not token:
        raise RuntimeError("Google Calendar not connected")

    attendees = [{"email": e} for e in ([body["attendee_email"]]
                                        if body.get("attendee_email") else [])]
    async with httpx.AsyncClient(timeout=20) as c:
        r = await c.post(
            "https://www.googleapis.com/calendar/v3/calendars/primary/events",
            params={"conferenceDataVersion": 1, "sendUpdates": "all"},
            headers={"Authorization": f"Bearer {token}"},
            json={
                "summary": body.get("title", "Leadaro — intro call"),
                "description": body.get("description", "Booked by your AI voice agent."),
                "start": {"dateTime": meeting["starts_at"].isoformat(),
                          "timeZone": meeting["timezone"]},
                "end": {"dateTime": meeting["ends_at"].isoformat(),
                        "timeZone": meeting["timezone"]},
                "attendees": attendees,
                "conferenceData": {
                    "createRequest": {"requestId": str(meeting["id"])[:32]}
                },
            },
        )
    if r.status_code >= 400:
        raise RuntimeError(r.text[:200])
    data = r.json()
    return data.get("id"), data.get("hangoutLink")
