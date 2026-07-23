"""
Clean production-tenant seed — ONE org, ONE admin user (real bcrypt hash), ONE
campaign. No demo leads, no fake calls, no stock voices.

    python seeds/seed_prod.py

Set your values via environment variables (recommended, keeps the password out of
the file) or edit the constants below. At minimum, set a real admin password:

    PowerShell:
      $env:SEED_ORG_NAME="Cebos"
      $env:SEED_ADMIN_EMAIL="you@cebos.io"
      $env:SEED_ADMIN_PASSWORD="a-strong-password"
      .venv\\Scripts\\python.exe seeds\\seed_prod.py

Idempotent: re-running updates the admin password + campaign in place (keyed on
org name + admin email), never duplicates.
"""
import asyncio
import os
import sys
from pathlib import Path

# db.py + auth.py live in services/api; reuse them so the password hash is the
# EXACT one the login route verifies against (bcrypt via auth.hash_password).
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "services" / "api"))

import db  # noqa: E402
from auth import hash_password  # noqa: E402

ORG_NAME       = os.environ.get("SEED_ORG_NAME",       "Cebos")
TIMEZONE       = os.environ.get("SEED_TIMEZONE",       "Asia/Kolkata")
ADMIN_EMAIL    = os.environ.get("SEED_ADMIN_EMAIL",    "admin@cebos.io")
ADMIN_NAME     = os.environ.get("SEED_ADMIN_NAME",     "Admin")
ADMIN_PASSWORD = os.environ.get("SEED_ADMIN_PASSWORD", "change-me-now")
CAMPAIGN_NAME  = os.environ.get("SEED_CAMPAIGN_NAME",  "Inbound Line")
LANGUAGE       = os.environ.get("SEED_LANGUAGE",       "en")   # en/hi/ta/te/ml/kn/...


async def main() -> None:
    await db.init_pool()
    try:
        async with db.tx() as c:
            # ── org (create once, reuse by name) ──────────────────────────────
            org_id = await c.fetchval(
                "SELECT id FROM organizations WHERE name = $1", ORG_NAME)
            if org_id is None:
                org_id = await c.fetchval(
                    "INSERT INTO organizations (name, timezone) VALUES ($1,$2) RETURNING id",
                    ORG_NAME, TIMEZONE)

            # ── admin user (real bcrypt hash) ─────────────────────────────────
            pw = hash_password(ADMIN_PASSWORD)
            uid = await c.fetchval(
                "SELECT id FROM users WHERE org_id=$1 AND lower(email)=lower($2)",
                org_id, ADMIN_EMAIL)
            if uid is None:
                await c.execute(
                    """INSERT INTO users (org_id, email, name, password_hash, role, is_active)
                       VALUES ($1,$2,$3,$4,'admin',true)""",
                    org_id, ADMIN_EMAIL, ADMIN_NAME, pw)
            else:
                await c.execute(
                    """UPDATE users SET name=$2, password_hash=$3, role='admin',
                                        is_active=true WHERE id=$1""",
                    uid, ADMIN_NAME, pw)

            # ── one campaign (voice mode; no voice picked -> agent falls back to
            #    the Cartesia default voice; select/sync a real voice in the UI) ─
            campaign_id = await c.fetchval(
                "SELECT id FROM campaigns WHERE org_id=$1 AND name=$2",
                org_id, CAMPAIGN_NAME)
            if campaign_id is None:
                campaign_id = await c.fetchval(
                    """INSERT INTO campaigns (org_id, mode, name, type, goal, status,
                                              voice_type, language, timezone, script)
                       VALUES ($1,'voice',$2,'cold_calling','book_meeting','draft',
                               'ai',$3,$4,$5) RETURNING id""",
                    org_id, CAMPAIGN_NAME, LANGUAGE, TIMEZONE,
                    {
                        "greeting": "Hi, thanks for calling. This is an AI assistant. "
                                    "How can I help you today?",
                        "offer": "We help teams automate their outbound calling.",
                        "cta": "Would a short demo be useful?",
                    })

        print("clean tenant ready:")
        print(f"  org_id      : {org_id}   ({ORG_NAME}, tz={TIMEZONE})")
        print(f"  campaign_id : {campaign_id}   ({CAMPAIGN_NAME!r}, voice, lang={LANGUAGE}, status=draft)")
        print(f"  login       : {ADMIN_EMAIL}  /  {ADMIN_PASSWORD}")
        if ADMIN_PASSWORD == "change-me-now":
            print("  WARNING     : you used the default password — set SEED_ADMIN_PASSWORD and re-run.")
        print()
        print("next — register your Plivo number, bound to this campaign for inbound:")
        print("  INSERT INTO phone_numbers (org_id, e164, label, provider, country,")
        print("                             inbound_campaign_id, is_active)")
        print(f"  VALUES ('{org_id}', '+918035017512', 'Plivo India', 'plivo', 'IN',")
        print(f"          '{campaign_id}', true)")
        print("  ON CONFLICT (org_id, e164) DO UPDATE SET is_active=true,")
        print("    inbound_campaign_id=EXCLUDED.inbound_campaign_id;")
        print("  -- outbound caller id:")
        print(f"  UPDATE campaigns SET caller_number_id=(SELECT id FROM phone_numbers")
        print(f"    WHERE org_id='{org_id}' AND e164='+918035017512') WHERE id='{campaign_id}';")
    finally:
        await db.close_pool()


if __name__ == "__main__":
    asyncio.run(main())
