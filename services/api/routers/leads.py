import csv
import io

import phonenumbers
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status

import db
from auth import Principal, audit, current_user
from schemas import AudiencePreview, LeadIn

router = APIRouter(prefix="/leads", tags=["leads"])

# Per-minute rate a campaign is billed at. Used for the wizard's cost estimate.
COST_PER_MINUTE_USD = 0.065
AVG_CALL_MINUTES = 2.5


def normalise_phone(raw: str, default_region: str = "US") -> str | None:
    """
    E.164 or None. Everything downstream assumes E.164 — normalise once, here.

    Eligibility is `is_possible_number`, not `is_valid_number`. Strict validity
    requires the exact number block to be present in the library's metadata,
    which lags real carrier allocations — so a freshly-allocated, perfectly
    dialable number would be silently discarded as "invalid". Length-and-shape
    correctness for the region is the bar carriers actually enforce; anything
    truly dead surfaces as an unreachable outcome on the first attempt.
    """
    if not raw:
        return None
    try:
        p = phonenumbers.parse(raw.strip(), default_region)
    except phonenumbers.NumberParseException:
        return None
    if not phonenumbers.is_possible_number(p):
        return None
    return phonenumbers.format_number(p, phonenumbers.PhoneNumberFormat.E164)


@router.get("")
async def list_leads(
    q: str | None = None,
    industry: str | None = None,
    country: str | None = None,
    city: str | None = None,
    company: str | None = None,
    designation: str | None = None,
    min_score: int | None = None,
    tag: str | None = None,
    limit: int = Query(100, le=500),
    offset: int = 0,
    user: Principal = Depends(current_user),
):
    rows = await db.fetch(
        """
        SELECT * FROM leads
        WHERE org_id = $1
          AND ($2::text IS NULL OR
               (coalesce(first_name,'')||' '||coalesce(last_name,'')||' '||
                coalesce(company,'')||' '||phone) ILIKE '%'||$2||'%')
          AND ($3::text IS NULL OR industry    = $3)
          AND ($4::text IS NULL OR country     = $4)
          AND ($5::text IS NULL OR city        = $5)
          AND ($6::text IS NULL OR company     = $6)
          AND ($7::text IS NULL OR designation = $7)
          AND ($8::int  IS NULL OR lead_score >= $8)
          AND ($9::text IS NULL OR $9 = ANY(tags))
        ORDER BY lead_score DESC, created_at DESC
        LIMIT $10 OFFSET $11
        """,
        user.org_id, q, industry, country, city, company, designation,
        min_score, tag, limit, offset,
    )
    return [{**r, "id": str(r["id"]), "org_id": str(r["org_id"])} for r in rows]


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_lead(body: LeadIn, user: Principal = Depends(current_user)):
    e164 = normalise_phone(body.phone)
    if not e164:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "invalid phone number")

    row = await db.fetchrow(
        """
        INSERT INTO leads (org_id, first_name, last_name, phone, email, company,
                           designation, industry, city, country, website, source,
                           lead_score, tags, custom_fields)
        VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15)
        ON CONFLICT (org_id, phone) DO UPDATE
          SET first_name  = COALESCE(EXCLUDED.first_name, leads.first_name),
              last_name   = COALESCE(EXCLUDED.last_name,  leads.last_name),
              company     = COALESCE(EXCLUDED.company,    leads.company),
              email       = COALESCE(EXCLUDED.email,      leads.email)
        RETURNING *
        """,
        user.org_id, body.first_name, body.last_name, e164, body.email, body.company,
        body.designation, body.industry, body.city, body.country, body.website,
        body.source, body.lead_score, body.tags, body.custom_fields,
    )
    return {**row, "id": str(row["id"]), "org_id": str(row["org_id"])}


@router.post("/import")
async def import_csv(
    file: UploadFile = File(...),
    default_region: str = "US",
    user: Principal = Depends(current_user),
):
    """
    CSV ingest with the four validation classes from FRD §5 step 2.
    Rows are classified, not silently dropped — the caller sees every rejection.
    """
    raw = (await file.read()).decode("utf-8-sig", errors="replace")
    reader = csv.DictReader(io.StringIO(raw))

    seen: set[str] = set()
    ok: list[tuple] = []
    invalid = duplicates = 0

    for row in reader:
        low = {(k or "").strip().lower(): (v or "").strip() for k, v in row.items()}
        e164 = normalise_phone(
            low.get("phone") or low.get("mobile") or low.get("number") or "",
            default_region,
        )
        if not e164:
            invalid += 1
            continue
        if e164 in seen:
            duplicates += 1
            continue
        seen.add(e164)
        ok.append((
            user.org_id,
            low.get("first_name") or low.get("firstname") or low.get("name"),
            low.get("last_name") or low.get("lastname"),
            e164,
            low.get("email"),
            low.get("company"),
            low.get("designation") or low.get("title") or low.get("job_title"),
            low.get("industry"),
            low.get("city"),
            low.get("country"),
            low.get("website"),
            "csv",
        ))

    inserted = 0
    if ok:
        async with db.tx() as c:
            # Existing phones are updated, not duplicated — the unique index on
            # (org_id, phone) is what makes re-importing a list safe.
            result = await c.executemany(
                """
                INSERT INTO leads (org_id, first_name, last_name, phone, email,
                                   company, designation, industry, city, country,
                                   website, source)
                VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12)
                ON CONFLICT (org_id, phone) DO UPDATE
                  SET company = COALESCE(EXCLUDED.company, leads.company),
                      email   = COALESCE(EXCLUDED.email,   leads.email)
                """,
                ok,
            )
            inserted = len(ok)

    await audit(user.org_id, user.user_id, "leads.import", "leads", None,
                {"accepted": inserted, "invalid": invalid, "duplicates": duplicates})
    return {
        "accepted": inserted,
        "invalid": invalid,
        "duplicates": duplicates,
        "total_rows": inserted + invalid + duplicates,
    }


@router.post("/preview", response_model=AudiencePreview)
async def audience_preview(
    filters: dict, user: Principal = Depends(current_user),
):
    """
    FRD §5 step 2 preview panel. Counts are computed against the live
    suppression list, so a number that went DNC since import is caught here
    rather than at dial time.
    """
    rows = await db.fetch(
        """
        SELECT l.phone,
               EXISTS (SELECT 1 FROM suppression_list s
                       WHERE s.org_id = l.org_id AND s.phone = l.phone
                         AND s.kind IN ('dnc','opt_out'))       AS is_dnc,
               EXISTS (SELECT 1 FROM suppression_list s
                       WHERE s.org_id = l.org_id AND s.phone = l.phone
                         AND s.kind = 'blacklist')              AS is_black
        FROM leads l
        WHERE l.org_id = $1
          AND ($2::text IS NULL OR l.industry = $2)
          AND ($3::text IS NULL OR l.country  = $3)
          AND ($4::text IS NULL OR l.city     = $4)
          AND ($5::int  IS NULL OR l.lead_score >= $5)
        """,
        user.org_id,
        filters.get("industry"), filters.get("country"),
        filters.get("city"), filters.get("min_score"),
    )

    total = len(rows)
    dnc = sum(1 for r in rows if r["is_dnc"])
    black = sum(1 for r in rows if r["is_black"])
    invalid = sum(1 for r in rows if not normalise_phone(r["phone"]))
    reachable = max(0, total - dnc - black - invalid)

    return AudiencePreview(
        total=total,
        reachable=reachable,
        duplicates=0,           # unique index guarantees none persisted
        invalid=invalid,
        dnc=dnc,
        blacklisted=black,
        estimated_cost_usd=round(reachable * AVG_CALL_MINUTES * COST_PER_MINUTE_USD, 2),
        # Historical connect rate for this org, defaulted before there's data.
        predicted_success_rate=await _predicted_rate(user.org_id),
    )


async def _predicted_rate(org_id: str) -> float:
    v = await db.fetchval(
        """SELECT COALESCE(
             AVG(CASE WHEN answered_by = 'human' THEN 1.0 ELSE 0.0 END), 0.32)
           FROM calls WHERE org_id = $1 AND started_at > now() - interval '30 days'""",
        org_id,
    )
    return round(float(v), 4)


@router.post("/attach/{campaign_id}")
async def attach_to_campaign(
    campaign_id: str, body: dict, user: Principal = Depends(current_user),
):
    """Enrol leads into a campaign, skipping anything on the suppression list."""
    lead_ids: list[str] = body.get("lead_ids") or []
    if not lead_ids:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "lead_ids required")

    owned = await db.fetchval(
        "SELECT 1 FROM campaigns WHERE id = $1 AND org_id = $2",
        campaign_id, user.org_id,
    )
    if not owned:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "campaign not found")

    n = await db.fetchval(
        """
        WITH eligible AS (
          SELECT l.id FROM leads l
          WHERE l.org_id = $2 AND l.id = ANY($3::uuid[])
            AND NOT EXISTS (
              SELECT 1 FROM suppression_list s
              WHERE s.org_id = l.org_id AND s.phone = l.phone
            )
        )
        INSERT INTO campaign_leads (campaign_id, lead_id)
        SELECT $1, id FROM eligible
        ON CONFLICT (campaign_id, lead_id) DO NOTHING
        RETURNING 1
        """,
        campaign_id, user.org_id, lead_ids,
    )
    attached = n or 0
    await audit(user.org_id, user.user_id, "leads.attach", "campaign", campaign_id,
                {"requested": len(lead_ids), "attached": attached})
    return {"requested": len(lead_ids), "attached": attached,
            "skipped_suppressed": len(lead_ids) - attached}
