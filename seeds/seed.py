"""
Development seed: one org, users for every role, stock voices, a couple of
campaigns with leads, and enough call history for the dashboard to look real.

    python seeds/seed.py
"""
import asyncio
import random
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "services" / "api"))

import db  # noqa: E402
from auth import hash_password  # noqa: E402

ORG = "11111111-1111-1111-1111-111111111111"

USERS = [
    ("admin@leadaro.io",     "Alex Morgan",   "admin"),
    ("manager@leadaro.io",   "Priya Nair",    "manager"),
    ("rep@leadaro.io",       "Sam Okafor",    "sales_rep"),
    ("recruiter@leadaro.io", "Dana Whitfield", "recruiter"),
    ("ops@leadaro.io",       "Iris Chen",     "campaign_operator"),
    ("analyst@leadaro.io",   "Tom Bexley",    "analyst"),
    ("viewer@leadaro.io",    "Jo Ruiz",       "viewer"),
]

# Cartesia stock voice ids are placeholders — replace with real ones from the
# provider console. The gallery still renders and filters without them.
VOICES = [
    ("Emma",   "female", "American", "en", "professional", "sales"),
    ("James",  "male",   "British",  "en", "sales",        "sales"),
    ("Sophia", "female", "American", "en", "friendly",     "support"),
    ("Arjun",  "male",   "Indian",   "en", "professional", "finance"),
    ("Mei",    "female", "Neutral",  "en", "calm",         "healthcare"),
    ("Diego",  "male",   "Spanish",  "es", "energetic",    "sales"),
]

FIRST = ["Raj", "Sarah", "Wei", "Amara", "Tom", "Lucia", "Kenji", "Nina",
         "Omar", "Elena", "Marcus", "Priya", "Ivan", "Chloe", "Dev", "Hana"]
LAST = ["Patel", "Chen", "Okafor", "Rossi", "Nguyen", "Silva", "Kim", "Haddad",
        "Novak", "Dubois", "Adeyemi", "Larsen"]
COMPANIES = ["Globex", "Initech", "Umbrella", "Stark Industries", "Wayne Foods",
             "Acme Retail", "Northwind", "Contoso", "Fabrikam", "Soylent"]
INDUSTRIES = ["SaaS", "Insurance", "Real Estate", "Healthcare", "Fintech",
              "Logistics", "Education"]
CITIES = [("Austin", "US"), ("London", "GB"), ("Bengaluru", "IN"),
          ("Berlin", "DE"), ("Toronto", "CA"), ("Singapore", "SG")]

# Real, dialable-shaped area codes. The 555-01XX range is reserved for fiction
# and is rejected by number validation, which made every seeded lead look
# unreachable in the audience preview.
AREA_CODES = ["415", "512", "212", "312", "617", "206", "305", "646"]


def fake_us_number() -> str:
    return (f"+1{random.choice(AREA_CODES)}"
            f"{random.randint(2, 9)}{random.randint(0, 99):02d}"
            f"{random.randint(0, 9999):04d}")

OUTCOMES = ["interested", "not_interested", "voicemail", "callback",
            "meeting_scheduled", "no_answer", "wrong_number", "busy"]
OUTCOME_W = [22, 26, 15, 13, 9, 10, 3, 2]


async def main() -> None:
    await db.init_pool()
    print("seeding…")

    async with db.tx() as c:
        await c.execute("DELETE FROM organizations WHERE id = $1", ORG)
        # Stock voices sit outside any org, so the cascade above misses them.
        # Without this the gallery doubles on every re-seed.
        await c.execute("DELETE FROM voices WHERE org_id IS NULL")
        await c.execute(
            "INSERT INTO organizations (id, name, timezone) VALUES ($1,$2,$3)",
            ORG, "Leadaro Demo Co", "America/New_York",
        )

        pw = hash_password("leadaro123")
        for email, name, role in USERS:
            await c.execute(
                """INSERT INTO users (org_id,email,name,password_hash,role)
                   VALUES ($1,$2,$3,$4,$5)""",
                ORG, email, name, pw, role,
            )

        await c.execute(
            """INSERT INTO phone_numbers (org_id,e164,label,provider,country)
               VALUES ($1,'+14155550100','Sales line','plivo','US')""",
            ORG,
        )

        for i, (name, gender, accent, lang, tone, vertical) in enumerate(VOICES):
            await c.execute(
                """INSERT INTO voices (org_id,name,provider,provider_id,gender,
                                       accent,language,tone,vertical,rating)
                   VALUES (NULL,$1,'cartesia',$2,$3,$4,$5,$6,$7,$8)""",
                name, f"stock-voice-{i+1}", gender, accent, lang, tone, vertical,
                round(random.uniform(4.1, 4.9), 1),
            )

        voice_id = await c.fetchval("SELECT id FROM voices WHERE name='Emma'")

        campaigns = []
        for mode, name, ctype, status in [
            ("voice", "SaaS Outreach — May",  "demo_booking",     "active"),
            ("voice", "Renewal Drive Q2",     "renewal_reminder", "active"),
            ("call",  "Enterprise Follow-up", "follow_up",        "active"),
            ("call",  "Recruiter Screening",  "recruitment",      "completed"),
        ]:
            cid = await c.fetchval(
                """INSERT INTO campaigns (org_id,mode,name,type,status,voice_type,
                                          voice_id,language,timezone,script)
                   VALUES ($1,$2,$3,$4,$5,'ai',$6,'en','America/New_York',$7)
                   RETURNING id""",
                ORG, mode, name, ctype, status, voice_id,
                {
                    # No em-dash. The greeting is spoken, and an em-dash fuses
                    # two clauses into one long sentence, which delays the first
                    # sentence boundary TTS can start on and reads as breathless.
                    "greeting": "Hi {{first_name}}, this is Emma calling from Leadaro. "
                                "Quick heads up, I'm an AI assistant. Do you have a moment?",
                    "offer": "We help teams automate outbound calling and book more meetings.",
                    "cta": "Would a short demo this week be useful?",
                },
            )
            campaigns.append(cid)

        # leads
        lead_ids = []
        for i in range(240):
            city, country = random.choice(CITIES)
            lid = await c.fetchval(
                """INSERT INTO leads (org_id,first_name,last_name,phone,email,company,
                                      designation,industry,city,country,source,lead_score)
                   VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,'csv',$11)
                   ON CONFLICT (org_id, phone) DO NOTHING RETURNING id""",
                ORG, random.choice(FIRST), random.choice(LAST),
                fake_us_number(),
                f"lead{i}@example.com", random.choice(COMPANIES),
                random.choice(["CEO", "VP Sales", "Head of Ops", "Director"]),
                random.choice(INDUSTRIES), city, country, random.randint(20, 98),
            )
            if lid:
                lead_ids.append(lid)

        for cid in campaigns:
            for lid in random.sample(lead_ids, k=min(80, len(lead_ids))):
                await c.execute(
                    """INSERT INTO campaign_leads (campaign_id,lead_id)
                       VALUES ($1,$2) ON CONFLICT DO NOTHING""",
                    cid, lid,
                )

        # a couple of suppressed numbers so the audience preview shows non-zero DNC
        for lid in lead_ids[:6]:
            phone = await c.fetchval("SELECT phone FROM leads WHERE id=$1", lid)
            await c.execute(
                """INSERT INTO suppression_list (org_id,phone,kind,reason)
                   VALUES ($1,$2,'dnc','national registry')
                   ON CONFLICT DO NOTHING""",
                ORG, phone,
            )

        # call history across the last 30 days
        now = datetime.now(timezone.utc)
        made = 0
        for day in range(30):
            for _ in range(random.randint(25, 70)):
                cid = random.choice(campaigns)
                lid = random.choice(lead_ids)
                outcome = random.choices(OUTCOMES, weights=OUTCOME_W)[0]
                answered = outcome in ("interested", "not_interested", "callback",
                                       "meeting_scheduled")
                started = now - timedelta(
                    days=day, hours=random.randint(9, 17), minutes=random.randint(0, 59)
                )
                dur = random.randint(45, 260) if answered else random.randint(5, 30)

                call_id = await c.fetchval(
                    """INSERT INTO calls (org_id,campaign_id,lead_id,direction,
                          provider_call_id,to_number,status,answered_by,outcome,
                          started_at,answered_at,ended_at,duration_sec,
                          ai_speaking_sec,cost_usd)
                       VALUES ($1,$2,$3,'outbound',$4,$5,'completed',$6,$7,$8,$9,$10,
                               $11,$12,$13) RETURNING id""",
                    ORG, cid, lid, f"prov-{random.randint(10**6, 10**7)}",
                    fake_us_number(),
                    "human" if answered else ("machine" if outcome == "voicemail" else "unknown"),
                    outcome, started,
                    started + timedelta(seconds=6) if answered else None,
                    started + timedelta(seconds=dur), dur,
                    int(dur * 0.55), round(dur / 60 * 0.065, 4),
                )

                if answered:
                    n_turns = random.randint(4, 14)
                    for s in range(1, n_turns + 1):
                        is_agent = s % 2 == 1
                        await c.execute(
                            """INSERT INTO turns (call_id,org_id,seq,role,text,intent,
                                   sentiment,emotion,speed,pitch,action,
                                   stt_ms,llm_ms,tts_ms,total_ms,cache_read_tokens)
                               VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,
                                       $12,$13,$14,$15,$16)""",
                            call_id, ORG, s, "agent" if is_agent else "lead",
                            "Sure, tell me more." if not is_agent
                            else "We help teams book more meetings with AI calling.",
                            random.choice(["interested", "neutral", "price_inquiry",
                                           "more_info", "objection"]),
                            round(random.uniform(-0.6, 0.9), 2),
                            random.choice(["friendly", "professional", "confident"])
                            if is_agent else None,
                            "normal" if is_agent else None,
                            "medium" if is_agent else None,
                            random.choice(["continue", "handle_objection", "book_meeting"])
                            if is_agent else None,
                            random.randint(110, 190) if is_agent else None,
                            random.randint(380, 760) if is_agent else None,
                            random.randint(120, 210) if is_agent else None,
                            random.randint(700, 1180) if is_agent else None,
                            random.randint(1200, 3400) if is_agent and s > 1 else 0,
                        )

                    tier = ("hot" if n_turns >= 10 else
                            "warm" if n_turns >= 5 else "scrap")
                    await c.execute(
                        """INSERT INTO call_summaries (call_id,summary,key_points,
                               action_items,lead_tier,qualification_score,sentiment_avg)
                           VALUES ($1,$2,$3,$4,$5,$6,$7)""",
                        call_id,
                        "Lead engaged and asked about pricing and integration options.",
                        ["Asked about pricing", "Uses a competitor today"],
                        ["Send pricing one-pager", "Schedule technical call"],
                        tier, random.randint(30, 95), round(random.uniform(-0.2, 0.8), 2),
                    )
                made += 1

    print(f"  org       : {ORG}")
    print(f"  users     : {len(USERS)}  (password: leadaro123)")
    print(f"  voices    : {len(VOICES)}")
    print(f"  campaigns : {len(campaigns)}")
    print(f"  leads     : {len(lead_ids)}")
    print(f"  calls     : {made}")
    print("done.")
    await db.close_pool()


if __name__ == "__main__":
    asyncio.run(main())
