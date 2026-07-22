from fastapi import APIRouter, Depends, HTTPException, Query, status

import db
from auth import Principal, audit, current_user, requires
from schemas import CampaignIn, CampaignPatch

router = APIRouter(prefix="/campaigns", tags=["campaigns"])

# Columns the wizard writes. Kept in one place so PATCH can't be used to set
# something the schema didn't intend (e.g. org_id).
PATCHABLE = (
    "name", "description", "type", "goal", "status", "priority", "tags",
    "timezone", "country", "language", "department", "caller_number_id",
    "caller_id", "voice_type", "voice_id", "voice_config", "script", "flow",
    "settings", "compliance", "schedule_mode", "start_date", "end_date",
    "business_hours", "weekdays_only", "weekends_only", "holiday_rules",
    "recurrence", "max_daily_calls", "concurrent_calls", "calls_per_minute",
    "queue_size", "warmup_mode",
)


def _out(r: dict) -> dict:
    return {k: (str(v) if k.endswith("_id") or k == "id" else v) for k, v in r.items()}


@router.get("")
async def list_campaigns(
    mode: str | None = Query(None, pattern="^(voice|call)$"),
    status_filter: str | None = Query(None, alias="status"),
    q: str | None = None,
    limit: int = Query(50, le=200),
    offset: int = 0,
    user: Principal = Depends(current_user),
):
    rows = await db.fetch(
        """
        SELECT c.*,
               COUNT(cl.id)                              AS lead_count,
               COUNT(cl.id) FILTER (WHERE cl.state='completed') AS done_count
        FROM campaigns c
        LEFT JOIN campaign_leads cl ON cl.campaign_id = c.id
        WHERE c.org_id = $1
          AND c.archived_at IS NULL
          AND ($2::campaign_mode   IS NULL OR c.mode   = $2)
          AND ($3::campaign_status IS NULL OR c.status = $3)
          AND ($4::text IS NULL OR c.name ILIKE '%'||$4||'%')
        GROUP BY c.id
        ORDER BY c.updated_at DESC
        LIMIT $5 OFFSET $6
        """,
        user.org_id, mode, status_filter, q, limit, offset,
    )
    return [_out(r) for r in rows]


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_campaign(
    body: CampaignIn, user: Principal = Depends(requires("create_campaign")),
):
    row = await db.fetchrow(
        """
        INSERT INTO campaigns (
          org_id, mode, name, description, type, goal, owner_id, department,
          priority, tags, timezone, country, language, caller_number_id, caller_id,
          voice_type, voice_id, voice_config, script, flow, settings, compliance,
          schedule_mode, start_date, end_date, business_hours, weekdays_only,
          weekends_only, holiday_rules, recurrence, max_daily_calls,
          concurrent_calls, calls_per_minute, queue_size, warmup_mode
        ) VALUES (
          $1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18,$19,
          $20,$21,$22,$23,$24,$25,$26,$27,$28,$29,$30,$31,$32,$33,$34,$35
        ) RETURNING *
        """,
        user.org_id, body.mode, body.name, body.description, body.type, body.goal,
        user.user_id, body.department, body.priority, body.tags, body.timezone,
        body.country, body.language, body.caller_number_id, body.caller_id,
        body.voice_type, body.voice_id, body.voice_config, body.script, body.flow,
        body.settings, body.compliance, body.schedule_mode, body.start_date,
        body.end_date, body.business_hours, body.weekdays_only, body.weekends_only,
        body.holiday_rules, body.recurrence, body.max_daily_calls,
        body.concurrent_calls, body.calls_per_minute, body.queue_size,
        body.warmup_mode,
    )
    await audit(user.org_id, user.user_id, "campaign.create", "campaign", str(row["id"]))
    return _out(row)


@router.get("/{cid}")
async def get_campaign(cid: str, user: Principal = Depends(current_user)):
    row = await db.fetchrow(
        "SELECT * FROM campaigns WHERE id = $1 AND org_id = $2", cid, user.org_id
    )
    if not row:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "campaign not found")
    return _out(row)


@router.patch("/{cid}")
async def patch_campaign(
    cid: str, body: CampaignPatch, user: Principal = Depends(current_user),
):
    changes = body.model_dump(exclude_unset=True)
    if not changes:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "no fields to update")

    # Status transitions are a permission boundary, not just a field write.
    if "status" in changes:
        needed = (
            "delete_campaign" if changes["status"] == "archived"
            else "pause_campaign" if changes["status"] in ("paused", "active")
            else "create_campaign"
        )
        if not user.can(needed):
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                f"role '{user.role}' lacks permission '{needed}'",
            )
    elif not user.can("create_campaign") and not user.can("modify_scripts"):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "not allowed to edit campaigns")

    cols = [c for c in changes if c in PATCHABLE]
    if not cols:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "no writable fields")

    sets = ", ".join(f"{c} = ${i + 3}" for i, c in enumerate(cols))
    row = await db.fetchrow(
        f"""UPDATE campaigns SET {sets}, updated_at = now()
            WHERE id = $1 AND org_id = $2 RETURNING *""",
        cid, user.org_id, *[changes[c] for c in cols],
    )
    if not row:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "campaign not found")
    await audit(user.org_id, user.user_id, "campaign.update", "campaign", cid,
                {"fields": cols})
    return _out(row)


@router.post("/{cid}/clone", status_code=status.HTTP_201_CREATED)
async def clone_campaign(
    cid: str, user: Principal = Depends(requires("create_campaign")),
):
    """Duplicate config only — leads, calls and history stay with the original."""
    row = await db.fetchrow(
        """
        INSERT INTO campaigns (
          org_id, mode, name, description, type, goal, owner_id, department,
          priority, tags, timezone, country, language, caller_number_id, caller_id,
          voice_type, voice_id, voice_config, script, flow, settings, compliance,
          schedule_mode, business_hours, weekdays_only, weekends_only,
          holiday_rules, recurrence, max_daily_calls, concurrent_calls,
          calls_per_minute, queue_size, warmup_mode, status
        )
        SELECT org_id, mode, name || ' (copy)', description, type, goal, $3,
               department, priority, tags, timezone, country, language,
               caller_number_id, caller_id, voice_type, voice_id, voice_config,
               script, flow, settings, compliance, schedule_mode, business_hours,
               weekdays_only, weekends_only, holiday_rules, recurrence,
               max_daily_calls, concurrent_calls, calls_per_minute, queue_size,
               warmup_mode, 'draft'
        FROM campaigns WHERE id = $1 AND org_id = $2
        RETURNING *
        """,
        cid, user.org_id, user.user_id,
    )
    if not row:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "campaign not found")
    await audit(user.org_id, user.user_id, "campaign.clone", "campaign", str(row["id"]),
                {"source": cid})
    return _out(row)


@router.delete("/{cid}", status_code=status.HTTP_204_NO_CONTENT)
async def archive_campaign(
    cid: str, user: Principal = Depends(requires("delete_campaign")),
):
    """Archive, not delete — call history and recordings are audit evidence."""
    n = await db.execute(
        """UPDATE campaigns SET status='archived', archived_at = now()
           WHERE id = $1 AND org_id = $2 AND archived_at IS NULL""",
        cid, user.org_id,
    )
    if n.endswith("0"):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "campaign not found")
    await audit(user.org_id, user.user_id, "campaign.archive", "campaign", cid)
