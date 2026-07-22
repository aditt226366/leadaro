"""Routing rules, automation rules, follow-ups and notifications (FRD §7, §12, §19)."""
from fastapi import APIRouter, Depends, HTTPException, Query, status

import db
from auth import Principal, audit, current_user, requires

router = APIRouter(tags=["automation"])

# ── smart routing (FRD §7, call mode) ───────────────────────────────────────

@router.get("/routing-rules")
async def list_routing(
    campaign_id: str | None = None, user: Principal = Depends(current_user),
):
    rows = await db.fetch(
        """SELECT * FROM routing_rules
           WHERE org_id = $1 AND ($2::uuid IS NULL OR campaign_id = $2 OR campaign_id IS NULL)
           ORDER BY position, created_at""",
        user.org_id, campaign_id,
    )
    return [{**r, "id": str(r["id"]),
             "campaign_id": str(r["campaign_id"]) if r["campaign_id"] else None}
            for r in rows]


@router.post("/routing-rules", status_code=status.HTTP_201_CREATED)
async def create_routing(
    body: dict, user: Principal = Depends(requires("create_campaign")),
):
    row = await db.fetchrow(
        """INSERT INTO routing_rules (org_id, campaign_id, name, position,
                                      conditions, destination, is_active)
           VALUES ($1,$2,$3,$4,$5,$6,$7) RETURNING *""",
        user.org_id, body.get("campaign_id"), body.get("name", "Untitled rule"),
        body.get("position", 0), body.get("conditions", []),
        body.get("destination", {}), body.get("is_active", True),
    )
    await audit(user.org_id, user.user_id, "routing.create", "routing_rule", str(row["id"]))
    return {**row, "id": str(row["id"]),
            "campaign_id": str(row["campaign_id"]) if row["campaign_id"] else None}


@router.patch("/routing-rules/{rule_id}")
async def update_routing(
    rule_id: str, body: dict, user: Principal = Depends(requires("create_campaign")),
):
    row = await db.fetchrow(
        """UPDATE routing_rules
           SET name = COALESCE($3, name), position = COALESCE($4, position),
               conditions = COALESCE($5, conditions),
               destination = COALESCE($6, destination),
               is_active = COALESCE($7, is_active)
           WHERE id = $1 AND org_id = $2 RETURNING *""",
        rule_id, user.org_id, body.get("name"), body.get("position"),
        body.get("conditions"), body.get("destination"), body.get("is_active"),
    )
    if not row:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "rule not found")
    return {**row, "id": str(row["id"]),
            "campaign_id": str(row["campaign_id"]) if row["campaign_id"] else None}


@router.delete("/routing-rules/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_routing(
    rule_id: str, user: Principal = Depends(requires("create_campaign")),
):
    await db.execute(
        "DELETE FROM routing_rules WHERE id = $1 AND org_id = $2", rule_id, user.org_id
    )


# ── automation rules (FRD §12) ──────────────────────────────────────────────

@router.get("/automation-rules")
async def list_automation(
    campaign_id: str | None = None, user: Principal = Depends(current_user),
):
    rows = await db.fetch(
        """SELECT * FROM automation_rules
           WHERE org_id = $1 AND ($2::uuid IS NULL OR campaign_id = $2 OR campaign_id IS NULL)
           ORDER BY created_at""",
        user.org_id, campaign_id,
    )
    return [{**r, "id": str(r["id"]),
             "campaign_id": str(r["campaign_id"]) if r["campaign_id"] else None}
            for r in rows]


@router.post("/automation-rules", status_code=status.HTTP_201_CREATED)
async def create_automation(
    body: dict, user: Principal = Depends(requires("create_campaign")),
):
    row = await db.fetchrow(
        """INSERT INTO automation_rules (org_id, campaign_id, name, trigger,
                                         actions, is_active)
           VALUES ($1,$2,$3,$4,$5,$6) RETURNING *""",
        user.org_id, body.get("campaign_id"), body.get("name", "Untitled"),
        body.get("trigger", "outcome:interested"), body.get("actions", []),
        body.get("is_active", True),
    )
    await audit(user.org_id, user.user_id, "automation.create", "automation_rule",
                str(row["id"]))
    return {**row, "id": str(row["id"]),
            "campaign_id": str(row["campaign_id"]) if row["campaign_id"] else None}


@router.patch("/automation-rules/{rule_id}")
async def update_automation(
    rule_id: str, body: dict, user: Principal = Depends(requires("create_campaign")),
):
    row = await db.fetchrow(
        """UPDATE automation_rules
           SET name = COALESCE($3,name), trigger = COALESCE($4,trigger),
               actions = COALESCE($5,actions), is_active = COALESCE($6,is_active)
           WHERE id = $1 AND org_id = $2 RETURNING *""",
        rule_id, user.org_id, body.get("name"), body.get("trigger"),
        body.get("actions"), body.get("is_active"),
    )
    if not row:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "rule not found")
    return {**row, "id": str(row["id"]),
            "campaign_id": str(row["campaign_id"]) if row["campaign_id"] else None}


@router.delete("/automation-rules/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_automation(
    rule_id: str, user: Principal = Depends(requires("create_campaign")),
):
    await db.execute(
        "DELETE FROM automation_rules WHERE id = $1 AND org_id = $2", rule_id, user.org_id
    )


# ── follow-ups ──────────────────────────────────────────────────────────────

@router.get("/followups")
async def list_followups(
    pending_only: bool = True,
    limit: int = Query(100, le=500),
    user: Principal = Depends(current_user),
):
    rows = await db.fetch(
        """SELECT f.*, l.first_name, l.last_name, l.company, l.phone
           FROM followups f LEFT JOIN leads l ON l.id = f.lead_id
           WHERE f.org_id = $1 AND ($2 = false OR f.status = 'pending')
           ORDER BY f.due_at LIMIT $3""",
        user.org_id, pending_only, limit,
    )
    return [{**r, "id": str(r["id"]), "lead_id": str(r["lead_id"]),
             "call_id": str(r["call_id"]) if r["call_id"] else None} for r in rows]


@router.patch("/followups/{fid}")
async def update_followup(
    fid: str, body: dict, user: Principal = Depends(current_user),
):
    row = await db.fetchrow(
        """UPDATE followups SET status = COALESCE($3, status)
           WHERE id = $1 AND org_id = $2 RETURNING *""",
        fid, user.org_id, body.get("status"),
    )
    if not row:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "follow-up not found")
    return {**row, "id": str(row["id"]), "lead_id": str(row["lead_id"]),
            "call_id": str(row["call_id"]) if row["call_id"] else None}


# ── notifications (FRD §19) ─────────────────────────────────────────────────

@router.get("/notifications")
async def list_notifications(
    unread_only: bool = False,
    limit: int = Query(50, le=200),
    user: Principal = Depends(current_user),
):
    rows = await db.fetch(
        """SELECT * FROM notifications
           WHERE org_id = $1 AND (user_id = $2 OR user_id IS NULL)
             AND ($3 = false OR read_at IS NULL)
           ORDER BY created_at DESC LIMIT $4""",
        user.org_id, user.user_id, unread_only, limit,
    )
    return [{**r, "user_id": str(r["user_id"]) if r["user_id"] else None} for r in rows]


@router.post("/notifications/read")
async def mark_read(body: dict, user: Principal = Depends(current_user)):
    ids = body.get("ids")
    if ids:
        await db.execute(
            """UPDATE notifications SET read_at = now()
               WHERE org_id = $1 AND id = ANY($2::bigint[])""",
            user.org_id, ids,
        )
    else:
        await db.execute(
            """UPDATE notifications SET read_at = now()
               WHERE org_id = $1 AND (user_id = $2 OR user_id IS NULL)
                 AND read_at IS NULL""",
            user.org_id, user.user_id,
        )
    return {"ok": True}
