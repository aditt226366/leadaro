from fastapi import APIRouter, Depends, Query

import db
from auth import Principal, current_user, requires

router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.get("/summary")
async def summary(
    mode: str | None = Query(None, pattern="^(voice|call)$"),
    days: int = Query(30, le=365),
    user: Principal = Depends(requires("access_analytics")),
):
    """Dashboard KPI cards + the secondary metric strip, in one round trip."""
    row = await db.fetchrow(
        """
        SELECT
          count(*)                                                      AS total_calls,
          count(*) FILTER (WHERE answered_by = 'human')                 AS answered,
          count(*) FILTER (WHERE answered_by = 'machine')               AS voicemail,
          count(*) FILTER (WHERE outcome IN ('interested','very_interested')) AS interested,
          count(*) FILTER (WHERE outcome = 'not_interested')            AS not_interested,
          count(*) FILTER (WHERE outcome = 'transferred')               AS transferred,
          count(*) FILTER (WHERE outcome = 'callback')                  AS callbacks,
          count(*) FILTER (WHERE outcome IN ('meeting_scheduled','booked_demo')) AS meetings,
          COALESCE(avg(duration_sec) FILTER (WHERE duration_sec > 0), 0) AS avg_duration,
          COALESCE(sum(ai_speaking_sec), 0)                             AS ai_speaking_sec,
          COALESCE(sum(cost_usd), 0)                                    AS cost_usd
        FROM calls c
        WHERE c.org_id = $1
          AND c.started_at > now() - ($2 || ' days')::interval
          AND ($3::campaign_mode IS NULL OR EXISTS (
                SELECT 1 FROM campaigns m WHERE m.id = c.campaign_id AND m.mode = $3))
        """,
        user.org_id, str(days), mode,
    )

    total = row["total_calls"] or 0
    answered = row["answered"] or 0
    campaigns = await db.fetchval(
        """SELECT count(*) FROM campaigns
           WHERE org_id = $1 AND archived_at IS NULL
             AND ($2::campaign_mode IS NULL OR mode = $2)""",
        user.org_id, mode,
    )

    return {
        "total_campaigns": campaigns,
        "total_calls": total,
        "answered": answered,
        "answer_rate": round(answered / total, 4) if total else 0,
        "voicemail": row["voicemail"],
        "interested": row["interested"],
        "not_interested": row["not_interested"],
        "transferred": row["transferred"],
        "callbacks": row["callbacks"],
        "meetings": row["meetings"],
        "avg_duration_sec": round(float(row["avg_duration"]), 1),
        "ai_speaking_sec": row["ai_speaking_sec"],
        "conversion_rate": round((row["meetings"] or 0) / total, 4) if total else 0,
        "cost_usd": round(float(row["cost_usd"]), 2),
    }


@router.get("/trend")
async def trend(
    days: int = Query(30, le=365),
    mode: str | None = Query(None, pattern="^(voice|call)$"),
    user: Principal = Depends(requires("access_analytics")),
):
    """Calls / answered / interested per day — the main dashboard area chart."""
    rows = await db.fetch(
        """
        SELECT date_trunc('day', started_at)::date AS d,
               count(*)                                   AS calls,
               count(*) FILTER (WHERE answered_by='human') AS answered,
               count(*) FILTER (WHERE outcome IN ('interested','very_interested')) AS interested
        FROM calls c
        WHERE c.org_id = $1
          AND c.started_at > now() - ($2 || ' days')::interval
          AND ($3::campaign_mode IS NULL OR EXISTS (
                SELECT 1 FROM campaigns m WHERE m.id = c.campaign_id AND m.mode = $3))
        GROUP BY 1 ORDER BY 1
        """,
        user.org_id, str(days), mode,
    )
    return [{"d": r["d"].isoformat(), "calls": r["calls"],
             "answered": r["answered"], "interested": r["interested"]} for r in rows]


@router.get("/outcomes")
async def outcomes(
    days: int = Query(30, le=365),
    user: Principal = Depends(requires("access_analytics")),
):
    rows = await db.fetch(
        """SELECT outcome::text AS name, count(*) AS value
           FROM calls
           WHERE org_id = $1 AND outcome IS NOT NULL
             AND started_at > now() - ($2 || ' days')::interval
           GROUP BY 1 ORDER BY 2 DESC""",
        user.org_id, str(days),
    )
    return rows


@router.get("/hourly")
async def hourly(
    days: int = Query(30, le=365),
    user: Principal = Depends(requires("access_analytics")),
):
    """Hourly connect rate — drives the best-time-to-call heatmap."""
    rows = await db.fetch(
        """
        SELECT extract(hour FROM started_at)::int AS hour,
               count(*) AS calls,
               count(*) FILTER (WHERE answered_by='human') AS answered
        FROM calls
        WHERE org_id = $1 AND started_at > now() - ($2 || ' days')::interval
        GROUP BY 1 ORDER BY 1
        """,
        user.org_id, str(days),
    )
    return [{"hour": r["hour"], "calls": r["calls"], "answered": r["answered"],
             "rate": round(r["answered"] / r["calls"], 4) if r["calls"] else 0}
            for r in rows]


@router.get("/latency")
async def latency(
    days: int = Query(7, le=90),
    campaign_id: str | None = None,
    user: Principal = Depends(requires("access_analytics")),
):
    """
    The primary success metric. p50/p95 of turn latency, split by stage, so a
    regression can be attributed to STT, the model, or TTS rather than guessed at.
    """
    row = await db.fetchrow(
        """
        SELECT
          count(*)                                                          AS turns,
          percentile_cont(0.5) WITHIN GROUP (ORDER BY total_ms)            AS p50,
          percentile_cont(0.95) WITHIN GROUP (ORDER BY total_ms)           AS p95,
          percentile_cont(0.5) WITHIN GROUP (ORDER BY stt_ms)              AS stt_p50,
          percentile_cont(0.5) WITHIN GROUP (ORDER BY llm_ms)              AS llm_p50,
          percentile_cont(0.5) WITHIN GROUP (ORDER BY tts_ms)              AS tts_p50,
          count(*) FILTER (WHERE cache_read_tokens > 0)                    AS cached_turns
        FROM turns t
        JOIN calls c ON c.id = t.call_id
        WHERE c.org_id = $1
          AND t.role = 'agent' AND t.total_ms IS NOT NULL
          AND t.created_at > now() - ($2 || ' days')::interval
          AND ($3::uuid IS NULL OR c.campaign_id = $3)
        """,
        user.org_id, str(days), campaign_id,
    )
    turns = row["turns"] or 0
    return {
        "turns": turns,
        "p50_ms": int(row["p50"] or 0),
        "p95_ms": int(row["p95"] or 0),
        "stt_p50_ms": int(row["stt_p50"] or 0),
        "llm_p50_ms": int(row["llm_p50"] or 0),
        "tts_p50_ms": int(row["tts_p50"] or 0),
        # If this drifts below ~1.0 the system prompt has a variable in it and
        # every turn is paying a cold cache write. See the plan's cache rule.
        "cache_hit_rate": round((row["cached_turns"] or 0) / turns, 3) if turns else 0,
    }


@router.get("/campaigns")
async def per_campaign(
    mode: str | None = Query(None, pattern="^(voice|call)$"),
    user: Principal = Depends(requires("access_analytics")),
):
    # Aggregated in separate scalar subqueries, NOT by joining campaign_leads
    # and calls together. Two one-to-many joins in one GROUP BY multiply each
    # other — every call gets counted once per enrolled lead, which inflated
    # 80 leads into 28,560 calls.
    rows = await db.fetch(
        """
        SELECT cam.id, cam.name, cam.type, cam.status::text, cam.mode::text,
               (SELECT count(*) FROM campaign_leads cl
                 WHERE cl.campaign_id = cam.id)                        AS leads,
               (SELECT count(*) FROM calls c
                 WHERE c.campaign_id = cam.id)                         AS calls,
               (SELECT count(*) FROM calls c
                 WHERE c.campaign_id = cam.id
                   AND c.answered_by = 'human')                        AS answered,
               (SELECT count(*) FROM calls c
                 WHERE c.campaign_id = cam.id
                   AND c.outcome IN ('interested','very_interested'))  AS interested,
               (SELECT count(*) FROM calls c
                 WHERE c.campaign_id = cam.id
                   AND c.outcome IN ('meeting_scheduled','booked_demo')) AS meetings
        FROM campaigns cam
        WHERE cam.org_id = $1 AND cam.archived_at IS NULL
          AND ($2::campaign_mode IS NULL OR cam.mode = $2)
        ORDER BY cam.updated_at DESC
        """,
        user.org_id, mode,
    )
    return [{**r, "id": str(r["id"]),
             "conversion": round(r["meetings"] / r["calls"] * 100, 1) if r["calls"] else 0.0}
            for r in rows]
