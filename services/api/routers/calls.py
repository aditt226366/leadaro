import asyncio
import io
import json
import logging
import os
import sys
from pathlib import Path

import phonenumbers
from fastapi import (
    APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Query,
    UploadFile, status,
)
from livekit import api as lk_api

import db
from auth import Principal, audit, current_user, requires
from routers.leads import normalise_phone
from schemas import BatchCallIn, OriginateCallIn

# The dialer's compliance gates (suppression/DNC among them) live in the agent
# service, not here — imported rather than reimplemented so a manual call from
# the dashboard is checked by the exact same rule as the automated loop.
_AGENT_DIR = Path(__file__).resolve().parents[2] / "agent"
if str(_AGENT_DIR) not in sys.path:
    sys.path.insert(0, str(_AGENT_DIR))
from dialer import AGENT_NAME, OUTBOUND_TRUNK, is_suppressed  # noqa: E402

log = logging.getLogger(__name__)
router = APIRouter(prefix="/calls", tags=["calls"])


@router.get("")
async def list_calls(
    campaign_id: str | None = None,
    outcome: str | None = None,
    direction: str | None = None,
    answered_by: str | None = None,
    limit: int = Query(50, le=200),
    offset: int = 0,
    user: Principal = Depends(current_user),
):
    rows = await db.fetch(
        """
        SELECT c.id, c.direction, c.status, c.answered_by, c.outcome,
               c.started_at, c.answered_at, c.ended_at, c.duration_sec,
               c.recording_url, c.to_number, c.cost_usd,
               l.first_name, l.last_name, l.company, l.phone,
               cam.name AS campaign_name, cam.mode,
               s.lead_tier, s.summary
        FROM calls c
        LEFT JOIN leads l        ON l.id = c.lead_id
        LEFT JOIN campaigns cam  ON cam.id = c.campaign_id
        LEFT JOIN call_summaries s ON s.call_id = c.id
        WHERE c.org_id = $1
          AND ($2::uuid IS NULL OR c.campaign_id = $2)
          AND ($3::call_outcome   IS NULL OR c.outcome     = $3)
          AND ($4::call_direction IS NULL OR c.direction   = $4)
          AND ($5::answered_by    IS NULL OR c.answered_by = $5)
        ORDER BY c.started_at DESC
        LIMIT $6 OFFSET $7
        """,
        user.org_id, campaign_id, outcome, direction, answered_by, limit, offset,
    )
    return [{**r, "id": str(r["id"])} for r in rows]


async def _resolve_or_create_lead(
    org_id: str, lead_id: str | None, phone: str | None, name: str | None,
) -> dict:
    """
    A dashboard call targets either an existing lead or a raw number. A raw
    number is upserted into `leads` (keyed on org+phone) so the call is tied to
    a person and appears in history exactly like a dialer call — a one-off call
    is not a second kind of record.
    """
    if lead_id:
        lead = await db.fetchrow(
            "SELECT * FROM leads WHERE id = $1 AND org_id = $2", lead_id, org_id,
        )
        if not lead:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "lead not found")
        return dict(lead)

    e164 = normalise_phone(phone or "")
    if not e164:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            f"'{phone}' is not a dialable number")
    first, last = _split_name(name)
    lead = await db.fetchrow(
        """INSERT INTO leads (org_id, first_name, last_name, phone, source)
           VALUES ($1,$2,$3,$4,'manual')
           ON CONFLICT (org_id, phone) DO UPDATE
             SET first_name = COALESCE(EXCLUDED.first_name, leads.first_name),
                 last_name  = COALESCE(EXCLUDED.last_name,  leads.last_name)
           RETURNING *""",
        org_id, first, last, e164,
    )
    return dict(lead)


def _split_name(name: str | None) -> tuple[str | None, str | None]:
    parts = (name or "").strip().split()
    if not parts:
        return None, None
    if len(parts) == 1:
        return parts[0], None
    return parts[0], " ".join(parts[1:])


async def _prepare_call(org_id: str, lead: dict, campaign: dict | None) -> str:
    """Create the `calls` row for a lead, linking it to a campaign if given.
    Raises 422 if the number is suppressed — the one gate no screen may skip."""
    if kind := await is_suppressed(org_id, lead["phone"]):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"{lead['phone']} is on the {kind} suppression list and cannot be called",
        )

    cl_id = None
    if campaign:
        # Enrol the lead so a manual call is a first-class member of the
        # campaign, then link the call to that membership like a dialer call.
        cl_id = await db.fetchval(
            """INSERT INTO campaign_leads (campaign_id, lead_id)
               VALUES ($1,$2) ON CONFLICT (campaign_id, lead_id) DO UPDATE
                 SET lead_id = EXCLUDED.lead_id
               RETURNING id""",
            campaign["id"], lead["id"],
        )

    from_number = await _resolve_caller_id(campaign)
    return await db.fetchval(
        """INSERT INTO calls (org_id, campaign_id, campaign_lead_id, lead_id,
                              direction, to_number, from_number, status)
           VALUES ($1,$2,$3,$4,'outbound',$5,$6,'initiated') RETURNING id""",
        org_id, campaign["id"] if campaign else None, cl_id, lead["id"],
        lead["phone"], from_number,
    )


async def _load_campaign(org_id: str, campaign_id: str | None) -> dict | None:
    if not campaign_id:
        return None
    campaign = await db.fetchrow(
        "SELECT * FROM campaigns WHERE id = $1 AND org_id = $2", campaign_id, org_id,
    )
    if not campaign:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "campaign not found")
    return dict(campaign)


@router.post("/originate", status_code=status.HTTP_201_CREATED)
async def originate_call(
    body: OriginateCallIn,
    background_tasks: BackgroundTasks,
    user: Principal = Depends(current_user),
):
    """
    Dashboard 'Call now' — the manual counterpart to the dialer's tick().

    Targets an existing `lead_id` or a raw `phone` (+ optional `name`). Creates
    the `calls` row and returns immediately; the SIP leg (which blocks ~8s for
    pickup) runs in the background so the request isn't held open. The UI then
    watches progress over the same SSE feed as an automated call.
    """
    if not body.lead_id and not body.phone:
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            "either lead_id or phone is required")

    campaign = await _load_campaign(user.org_id, body.campaign_id)
    lead = await _resolve_or_create_lead(
        user.org_id, body.lead_id, body.phone, body.name)
    call_id = await _prepare_call(user.org_id, lead, campaign)

    await audit(user.org_id, user.user_id, "call.originate", "call", str(call_id),
                {"lead_id": str(lead["id"]), "campaign_id": body.campaign_id})

    background_tasks.add_task(_dial, str(call_id), dict(lead))
    return {"call_id": str(call_id), "status": "initiated", "room_name": f"call-{call_id}"}


@router.post("/parse-contacts")
async def parse_contacts(
    file: UploadFile = File(...),
    default_region: str = Form("US"),
    user: Principal = Depends(current_user),
):
    """
    Pull name + phone pairs out of an uploaded .csv or .pdf, so the user can
    see who is in the sheet and pick who to call. Nothing is dialed here — this
    is the preview step. Every row is returned with its validity and whether the
    number is suppressed, so uncallable rows are shown rather than silently cut.
    """
    raw = await file.read()
    fname = (file.filename or "").lower()
    if fname.endswith(".pdf") or (file.content_type or "").endswith("pdf"):
        pairs = _extract_from_pdf(raw, default_region)
    else:
        pairs = _extract_from_csv(raw, default_region)

    # De-dupe on the normalised number, keeping the first name seen for it.
    seen: dict[str, dict] = {}
    invalid = 0
    for name, e164 in pairs:
        if not e164:
            invalid += 1
            continue
        seen.setdefault(e164, {"name": name, "phone": e164})

    contacts = list(seen.values())
    if contacts:
        supp = await db.fetch(
            """SELECT phone, kind FROM suppression_list
               WHERE org_id = $1 AND phone = ANY($2::text[])""",
            user.org_id, [c["phone"] for c in contacts],
        )
        supp_map = {r["phone"]: r["kind"] for r in supp}
        for c in contacts:
            c["suppressed"] = supp_map.get(c["phone"])

    return {
        "contacts": contacts,
        "invalid": invalid,
        "total_rows": len(pairs),
    }


@router.post("/batch", status_code=status.HTTP_202_ACCEPTED)
async def batch_call(
    body: BatchCallIn,
    background_tasks: BackgroundTasks,
    user: Principal = Depends(current_user),
):
    """
    Dial a whole list from a parsed sheet. Suppressed and invalid numbers are
    reported, not dialed. The SIP legs run in the background throttled to the
    campaign's own concurrency limit, so a big list respects the same ceiling
    an automated run would.
    """
    campaign = await _load_campaign(user.org_id, body.campaign_id)

    queued: list[tuple[str, dict]] = []
    skipped_suppressed: list[str] = []
    skipped_invalid: list[str] = []

    for contact in body.contacts:
        e164 = normalise_phone(contact.phone or "")
        if not e164:
            skipped_invalid.append(contact.phone)
            continue
        if await is_suppressed(user.org_id, e164):
            skipped_suppressed.append(e164)
            continue
        lead = await _resolve_or_create_lead(user.org_id, None, e164, contact.name)
        # _prepare_call re-checks suppression; harmless and keeps one code path.
        call_id = await _prepare_call(user.org_id, lead, campaign)
        queued.append((str(call_id), dict(lead)))

    if queued:
        limit = int((campaign or {}).get("concurrent_calls") or 5)
        await audit(user.org_id, user.user_id, "call.batch", "campaign",
                    body.campaign_id, {"queued": len(queued),
                                       "suppressed": len(skipped_suppressed),
                                       "invalid": len(skipped_invalid)})
        background_tasks.add_task(_dial_batch, queued, limit)

    return {
        "queued": len(queued),
        "call_ids": [cid for cid, _ in queued],
        "skipped_suppressed": skipped_suppressed,
        "skipped_invalid": skipped_invalid,
    }


async def _resolve_caller_id(campaign: dict | None) -> str:
    """Campaign's configured number if it has one and it's dialed in that
    context; otherwise the org's default outbound caller ID."""
    if campaign:
        from_number = await db.fetchval(
            "SELECT e164 FROM phone_numbers WHERE id = $1", campaign.get("caller_number_id"),
        ) or campaign.get("caller_id")
        if from_number:
            return from_number
    return os.environ.get("PLIVO_NUMBER", "")


async def _dial(call_id: str, lead: dict) -> None:
    """
    Background SIP leg for a manually-originated call — dispatch the agent
    into the room, then dial out. Mirrors dialer.place_call()'s two update
    points, except `wait_until_answered=True` here: nothing else is blocked
    on this coroutine, so it's fine (and simpler) to wait for pickup before
    flipping the row to 'connected'.
    """
    room = f"call-{call_id}"
    lkapi = lk_api.LiveKitAPI()
    try:
        await lkapi.agent_dispatch.create_dispatch(
            lk_api.CreateAgentDispatchRequest(
                agent_name=AGENT_NAME, room=room,
                metadata=json.dumps({"call_id": call_id}),
            )
        )
        await db.execute(
            "UPDATE calls SET room_name=$2, status='ringing' WHERE id=$1", call_id, room,
        )

        await lkapi.sip.create_sip_participant(
            lk_api.CreateSIPParticipantRequest(
                sip_trunk_id=OUTBOUND_TRUNK,
                sip_call_to=lead["phone"],
                room_name=room,
                participant_identity=f"lead-{lead['id']}",
                participant_name=f"{lead.get('first_name') or ''} {lead.get('last_name') or ''}".strip(),
                wait_until_answered=True,
            )
        )
        await db.execute(
            "UPDATE calls SET status='connected', answered_at=now() WHERE id=$1", call_id,
        )
    except Exception as e:
        log.exception("manual dial failed for call %s", call_id)
        await db.execute(
            "UPDATE calls SET status='failed', ended_at=now(), error=$2 WHERE id=$1",
            call_id, str(e)[:500],
        )
    finally:
        await lkapi.aclose()


async def _dial_batch(queued: list[tuple[str, dict]], limit: int) -> None:
    """Dial a batch of prepared calls, no more than `limit` ringing at once."""
    sem = asyncio.Semaphore(max(1, limit))

    async def one(call_id: str, lead: dict) -> None:
        async with sem:
            await _dial(call_id, lead)

    await asyncio.gather(*(one(cid, lead) for cid, lead in queued))


# ── contact-file parsing ─────────────────────────────────────────────────────

def _extract_from_csv(raw: bytes, region: str) -> list[tuple[str | None, str | None]]:
    """(name, e164) per row. Column names are matched loosely, same vocabulary
    as the leads importer, so a sheet exported from anywhere tends to just work."""
    import csv

    text = raw.decode("utf-8-sig", errors="replace")
    reader = csv.DictReader(io.StringIO(text))
    out: list[tuple[str | None, str | None]] = []
    for row in reader:
        low = {(k or "").strip().lower(): (v or "").strip() for k, v in row.items()}
        phone = (low.get("phone") or low.get("mobile") or low.get("number")
                 or low.get("phone_number") or "")
        name = (low.get("name") or low.get("full_name")
                or " ".join(p for p in (low.get("first_name"), low.get("last_name")) if p)
                or None)
        out.append((name or None, normalise_phone(phone, region)))
    return out


def _extract_from_pdf(raw: bytes, region: str) -> list[tuple[str | None, str | None]]:
    """
    Pull numbers out of a PDF's text. PhoneNumberMatcher finds dialable numbers
    inside free text far more reliably than a regex, and the words on the line
    before the match are taken as the name — which is how these sheets read.
    """
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(raw))
    text = "\n".join(page.extract_text() or "" for page in reader.pages)

    out: list[tuple[str | None, str | None]] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        for m in phonenumbers.PhoneNumberMatcher(line, region):
            e164 = phonenumbers.format_number(
                m.number, phonenumbers.PhoneNumberFormat.E164)
            # The name is whatever text sits before the number on the line,
            # stripped of separators a table might leave behind.
            name = line[:m.start].strip(" \t|,:-").strip() or None
            out.append((name, e164))
    return out


@router.get("/{call_id}")
async def get_call(call_id: str, user: Principal = Depends(current_user)):
    """Lead Conversation screen: header, full transcript, AI summary."""
    call = await db.fetchrow(
        """
        SELECT c.*, l.first_name, l.last_name, l.company, l.phone, l.email,
               l.designation, l.industry, l.city, l.lead_score,
               cam.name AS campaign_name, cam.mode
        FROM calls c
        LEFT JOIN leads l       ON l.id = c.lead_id
        LEFT JOIN campaigns cam ON cam.id = c.campaign_id
        WHERE c.id = $1 AND c.org_id = $2
        """,
        call_id, user.org_id,
    )
    if not call:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "call not found")

    turns = await db.fetch(
        """SELECT seq, role, text, intent, sentiment, emotion, action,
                  stt_ms, llm_ms, tts_ms, total_ms, created_at
           FROM turns WHERE call_id = $1 ORDER BY seq""",
        call_id,
    )
    summary = await db.fetchrow(
        "SELECT * FROM call_summaries WHERE call_id = $1", call_id
    )

    return {
        "call": {k: (str(v) if k.endswith("_id") or k == "id" else v)
                 for k, v in call.items()},
        "turns": turns,
        "summary": {**summary, "call_id": str(summary["call_id"])} if summary else None,
    }


@router.get("/{call_id}/transcript.txt")
async def download_transcript(call_id: str, user: Principal = Depends(current_user)):
    """Plain-text transcript download (FRD: searchable + downloadable)."""
    from fastapi import Response

    owned = await db.fetchval(
        "SELECT 1 FROM calls WHERE id = $1 AND org_id = $2", call_id, user.org_id
    )
    if not owned:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "call not found")

    turns = await db.fetch(
        "SELECT seq, role, text FROM turns WHERE call_id = $1 ORDER BY seq", call_id
    )
    body = "\n".join(f"[{t['role'].upper()}] {t['text']}" for t in turns)
    return Response(
        content=body or "(no transcript)",
        media_type="text/plain",
        headers={"Content-Disposition": f'attachment; filename="transcript-{call_id}.txt"'},
    )


@router.get("/{call_id}/recording")
async def get_recording(
    call_id: str, user: Principal = Depends(requires("download_recordings")),
):
    row = await db.fetchrow(
        "SELECT recording_url FROM calls WHERE id = $1 AND org_id = $2",
        call_id, user.org_id,
    )
    if not row or not row["recording_url"]:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no recording for this call")
    return {"url": row["recording_url"]}


@router.get("/live/active")
async def active_calls(
    campaign_id: str | None = None, user: Principal = Depends(current_user),
):
    """Live monitor snapshot. The SSE stream sends deltas; this is the baseline."""
    rows = await db.fetch(
        """
        SELECT c.id, c.status, c.answered_by, c.started_at, c.to_number,
               l.first_name, l.last_name, l.company, l.country,
               cam.name AS campaign_name,
               (SELECT text FROM turns t WHERE t.call_id = c.id
                ORDER BY seq DESC LIMIT 1) AS last_line,
               (SELECT count(*) FROM turns t WHERE t.call_id = c.id) AS turn_count
        FROM calls c
        LEFT JOIN leads l       ON l.id = c.lead_id
        LEFT JOIN campaigns cam ON cam.id = c.campaign_id
        WHERE c.org_id = $1
          AND c.ended_at IS NULL
          AND ($2::uuid IS NULL OR c.campaign_id = $2)
        ORDER BY c.started_at DESC
        """,
        user.org_id, campaign_id,
    )
    return [{**r, "id": str(r["id"])} for r in rows]
