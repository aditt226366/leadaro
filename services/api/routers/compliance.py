"""Suppression lists, consent, audit log (FRD §14) and report exports (§18)."""
import csv
import io

from fastapi import APIRouter, Depends, File, Query, Response, UploadFile, status

import db
from auth import Principal, audit, current_user, requires
from routers.leads import normalise_phone

router = APIRouter(tags=["compliance"])


# ── suppression / DNC ───────────────────────────────────────────────────────

@router.get("/suppression")
async def list_suppression(
    kind: str | None = None,
    q: str | None = None,
    limit: int = Query(200, le=1000),
    user: Principal = Depends(current_user),
):
    rows = await db.fetch(
        """SELECT * FROM suppression_list
           WHERE org_id = $1
             AND ($2::text IS NULL OR kind = $2)
             AND ($3::text IS NULL OR phone ILIKE '%'||$3||'%')
           ORDER BY created_at DESC LIMIT $4""",
        user.org_id, kind, q, limit,
    )
    return [{**r, "id": str(r["id"])} for r in rows]


@router.post("/suppression", status_code=status.HTTP_201_CREATED)
async def add_suppression(body: dict, user: Principal = Depends(current_user)):
    phone = normalise_phone(body.get("phone", "")) or body.get("phone", "").strip()
    row = await db.fetchrow(
        """INSERT INTO suppression_list (org_id, phone, kind, reason)
           VALUES ($1,$2,$3,$4)
           ON CONFLICT (org_id, phone, kind) DO UPDATE SET reason = EXCLUDED.reason
           RETURNING *""",
        user.org_id, phone, body.get("kind", "dnc"), body.get("reason"),
    )
    await audit(user.org_id, user.user_id, "suppression.add", "suppression",
                str(row["id"]), {"phone": phone, "kind": row["kind"]})
    return {**row, "id": str(row["id"])}


@router.post("/suppression/import")
async def import_suppression(
    file: UploadFile = File(...),
    kind: str = "dnc",
    user: Principal = Depends(current_user),
):
    """Bulk DNC upload. One phone per line, or a CSV with a `phone` column."""
    text = (await file.read()).decode("utf-8-sig", errors="replace")
    phones: set[str] = set()

    if "," in text.splitlines()[0] if text.strip() else False:
        for row in csv.DictReader(io.StringIO(text)):
            low = {(k or "").strip().lower(): v for k, v in row.items()}
            if p := normalise_phone(low.get("phone") or low.get("number") or ""):
                phones.add(p)
    else:
        for line in text.splitlines():
            if p := normalise_phone(line.strip()):
                phones.add(p)

    if phones:
        async with db.tx() as c:
            await c.executemany(
                """INSERT INTO suppression_list (org_id, phone, kind, reason)
                   VALUES ($1,$2,$3,'bulk import')
                   ON CONFLICT (org_id, phone, kind) DO NOTHING""",
                [(user.org_id, p, kind) for p in phones],
            )
    await audit(user.org_id, user.user_id, "suppression.import", "suppression",
                None, {"count": len(phones), "kind": kind})
    return {"imported": len(phones), "kind": kind}


@router.delete("/suppression/{sid}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_suppression(sid: str, user: Principal = Depends(current_user)):
    """
    Removing a suppression is a consequential act — someone becomes callable
    again — so it is always audited with the actor.
    """
    row = await db.fetchrow(
        "DELETE FROM suppression_list WHERE id = $1 AND org_id = $2 RETURNING phone, kind",
        sid, user.org_id,
    )
    if row:
        await audit(user.org_id, user.user_id, "suppression.remove", "suppression",
                    sid, {"phone": row["phone"], "kind": row["kind"]})


# ── consent ─────────────────────────────────────────────────────────────────

@router.get("/consents")
async def list_consents(
    lead_id: str | None = None,
    limit: int = Query(200, le=1000),
    user: Principal = Depends(current_user),
):
    rows = await db.fetch(
        """SELECT c.*, l.first_name, l.last_name, l.phone
           FROM consents c JOIN leads l ON l.id = c.lead_id
           WHERE c.org_id = $1 AND ($2::uuid IS NULL OR c.lead_id = $2)
           ORDER BY c.created_at DESC LIMIT $3""",
        user.org_id, lead_id, limit,
    )
    return [{**r, "id": str(r["id"]), "lead_id": str(r["lead_id"])} for r in rows]


@router.post("/consents", status_code=status.HTTP_201_CREATED)
async def record_consent(body: dict, user: Principal = Depends(current_user)):
    row = await db.fetchrow(
        """INSERT INTO consents (org_id, lead_id, kind, granted, source)
           VALUES ($1,$2,$3,$4,$5) RETURNING *""",
        user.org_id, body["lead_id"], body.get("kind", "calling"),
        bool(body.get("granted", True)), body.get("source", "manual"),
    )
    await audit(user.org_id, user.user_id, "consent.record", "consent", str(row["id"]),
                {"granted": row["granted"], "kind": row["kind"]})
    return {**row, "id": str(row["id"]), "lead_id": str(row["lead_id"])}


# ── audit log ───────────────────────────────────────────────────────────────

@router.get("/audit")
async def list_audit(
    action: str | None = None,
    entity: str | None = None,
    limit: int = Query(200, le=1000),
    offset: int = 0,
    user: Principal = Depends(requires("access_analytics")),
):
    rows = await db.fetch(
        """SELECT a.*, u.name AS actor_name, u.email AS actor_email
           FROM audit_log a LEFT JOIN users u ON u.id = a.actor_id
           WHERE a.org_id = $1
             AND ($2::text IS NULL OR a.action ILIKE $2||'%')
             AND ($3::text IS NULL OR a.entity = $3)
           ORDER BY a.created_at DESC LIMIT $4 OFFSET $5""",
        user.org_id, action, entity, limit, offset,
    )
    return [{**r, "actor_id": str(r["actor_id"]) if r["actor_id"] else None}
            for r in rows]


# ── exports (FRD §18) ───────────────────────────────────────────────────────

@router.get("/exports/calls.csv")
async def export_calls(
    days: int = Query(30, le=365),
    campaign_id: str | None = None,
    user: Principal = Depends(requires("export_reports")),
):
    rows = await db.fetch(
        """
        SELECT c.started_at, cam.name AS campaign, cam.mode::text,
               l.first_name, l.last_name, l.company, l.phone,
               c.direction::text, c.answered_by::text, c.outcome::text,
               c.duration_sec, c.cost_usd, s.lead_tier::text,
               s.qualification_score, s.summary
        FROM calls c
        LEFT JOIN campaigns cam    ON cam.id = c.campaign_id
        LEFT JOIN leads l          ON l.id = c.lead_id
        LEFT JOIN call_summaries s ON s.call_id = c.id
        WHERE c.org_id = $1
          AND c.started_at > now() - ($2 || ' days')::interval
          AND ($3::uuid IS NULL OR c.campaign_id = $3)
        ORDER BY c.started_at DESC
        """,
        user.org_id, str(days), campaign_id,
    )

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([
        "Started", "Campaign", "Mode", "First name", "Last name", "Company",
        "Phone", "Direction", "Answered by", "Outcome", "Duration (s)",
        "Cost (USD)", "Lead tier", "Score", "Summary",
    ])
    for r in rows:
        writer.writerow([
            r["started_at"].isoformat() if r["started_at"] else "",
            r["campaign"], r["mode"], r["first_name"], r["last_name"],
            r["company"], r["phone"], r["direction"], r["answered_by"],
            r["outcome"], r["duration_sec"], r["cost_usd"], r["lead_tier"],
            r["qualification_score"], (r["summary"] or "").replace("\n", " "),
        ])

    await audit(user.org_id, user.user_id, "export.calls", "calls", None,
                {"rows": len(rows), "days": days})
    return Response(
        content=buf.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="calls.csv"'},
    )


@router.get("/exports/leads.csv")
async def export_leads(user: Principal = Depends(requires("export_reports"))):
    rows = await db.fetch(
        """SELECT first_name, last_name, phone, email, company, designation,
                  industry, city, country, lead_score, tier::text, source,
                  last_contacted_at
           FROM leads WHERE org_id = $1 ORDER BY lead_score DESC""",
        user.org_id,
    )
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["First name", "Last name", "Phone", "Email", "Company", "Title",
                "Industry", "City", "Country", "Score", "Tier", "Source",
                "Last contacted"])
    for r in rows:
        w.writerow([r[k] for k in (
            "first_name", "last_name", "phone", "email", "company", "designation",
            "industry", "city", "country", "lead_score", "tier", "source",
            "last_contacted_at")])

    await audit(user.org_id, user.user_id, "export.leads", "leads", None,
                {"rows": len(rows)})
    return Response(
        content=buf.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="leads.csv"'},
    )
