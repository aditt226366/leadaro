from fastapi import APIRouter, Depends, HTTPException, status

import db
from auth import Principal, audit, current_user, requires

router = APIRouter(prefix="/phone-numbers", tags=["numbers"])


def _out(r: dict) -> dict:
    return {
        **r,
        "id": str(r["id"]),
        "inbound_campaign_id": str(r["inbound_campaign_id"])
        if r.get("inbound_campaign_id") else None,
    }


@router.get("")
async def list_numbers(user: Principal = Depends(current_user)):
    rows = await db.fetch(
        """SELECT id, e164, label, provider, country, is_active,
                  inbound_campaign_id, ivr_menu
           FROM phone_numbers WHERE org_id = $1 AND is_active
           ORDER BY created_at""",
        user.org_id,
    )
    return [_out(r) for r in rows]


@router.put("/{number_id}/ivr")
async def set_ivr_menu(
    number_id: str, body: dict,
    user: Principal = Depends(requires("manage_numbers")),
):
    """
    Save the DTMF keypad menu for a number.

    Digits are validated and de-duplicated here rather than in the UI — two
    options bound to "1" would make the second unreachable, and a caller would
    never find out why.
    """
    options = body.get("options") or []
    seen: set[str] = set()
    clean = []
    for o in options:
        digit = str(o.get("digit", "")).strip()
        if digit not in {*"0123456789", "*", "#"}:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                f"'{digit}' is not a keypad digit (0-9, * or #)",
            )
        if digit in seen:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                f"digit {digit} is assigned twice — the second would be unreachable",
            )
        seen.add(digit)
        clean.append({
            "digit": digit,
            "label": (o.get("label") or "").strip(),
            "action": o.get("action") or "ai_agent",
            "target": o.get("target") or None,
            "message": (o.get("message") or "").strip() or None,
        })

    menu = {
        "enabled": bool(body.get("enabled")),
        "greeting": (body.get("greeting") or "").strip(),
        "timeout_seconds": int(body.get("timeout_seconds") or 6),
        "invalid_message": (body.get("invalid_message") or "").strip(),
        "repeat_limit": int(body.get("repeat_limit") or 2),
        "options": clean,
    }

    row = await db.fetchrow(
        """UPDATE phone_numbers SET ivr_menu = $3
           WHERE id = $1 AND org_id = $2
           RETURNING id, e164, label, provider, country, is_active,
                     inbound_campaign_id, ivr_menu""",
        number_id, user.org_id, menu,
    )
    if not row:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "number not found")

    await audit(user.org_id, user.user_id, "ivr.update", "phone_number", number_id,
                {"enabled": menu["enabled"], "options": len(clean)})
    return _out(row)


@router.post("", status_code=status.HTTP_201_CREATED)
async def add_number(
    body: dict, user: Principal = Depends(requires("manage_numbers")),
):
    e164 = (body.get("e164") or "").strip()
    if not e164.startswith("+"):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "number must be in E.164 format, e.g. +14155550100",
        )
    row = await db.fetchrow(
        """INSERT INTO phone_numbers (org_id, e164, label, provider, country)
           VALUES ($1,$2,$3,$4,$5)
           ON CONFLICT (org_id, e164) DO UPDATE SET label = EXCLUDED.label,
                                                    is_active = true
           RETURNING *""",
        user.org_id, e164, body.get("label"),
        body.get("provider", "plivo"), body.get("country"),
    )
    await audit(user.org_id, user.user_id, "number.add", "phone_number",
                str(row["id"]), {"e164": e164})
    return _out(row)


@router.patch("/{number_id}")
async def update_number(
    number_id: str, body: dict,
    user: Principal = Depends(requires("manage_numbers")),
):
    """Bind an inbound campaign, relabel, or deactivate."""
    row = await db.fetchrow(
        """UPDATE phone_numbers
           SET label = COALESCE($3, label),
               inbound_campaign_id = COALESCE($4::uuid, inbound_campaign_id),
               is_active = COALESCE($5, is_active)
           WHERE id = $1 AND org_id = $2
           RETURNING *""",
        number_id, user.org_id, body.get("label"),
        body.get("inbound_campaign_id"), body.get("is_active"),
    )
    if not row:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "number not found")
    return _out(row)
