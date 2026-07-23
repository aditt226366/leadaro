"""
Copy the STOCK (reference) voices from the local Postgres into Neon.

    python infra/copy_voices.py

- Neon target  : DATABASE_URL from .env (where the app now points).
- Local source : LOCAL_DATABASE_URL, default the local container
                 postgresql://leadaro:leadaro@localhost:5433/leadaro

Copies only stock voices (org_id IS NULL) — the provider catalogue, which has no
tenant foreign key. Org-scoped / cloned voices are tenant data and are NOT copied
(they'd reference an org that doesn't exist on Neon). Rows already present are
skipped (matched on the provider/provider_id unique index), so it's safe to
re-run.

Uses its own direct asyncpg connections with statement_cache_size=0 so it works
against Neon's pooled (PgBouncer) endpoint without prepared-statement clashes.
"""
import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "services" / "api"))
import db  # noqa: E402  — only for db.DATABASE_URL (Neon, loaded from .env)

import asyncpg  # noqa: E402

LOCAL_URL = os.environ.get(
    "LOCAL_DATABASE_URL", "postgresql://leadaro:leadaro@localhost:5433/leadaro"
)
NEON_URL = db.DATABASE_URL

COLS = ["id", "org_id", "name", "provider", "provider_id", "gender", "accent",
        "language", "age", "tone", "vertical", "is_clone", "sample_url",
        "rating", "created_at"]

# ON CONFLICT target must match the voices_provider_uniq expression index exactly.
CONFLICT = ("(provider, provider_id, "
            "COALESCE(org_id, '00000000-0000-0000-0000-000000000000'::uuid))")


async def main() -> None:
    local = await asyncpg.connect(LOCAL_URL, statement_cache_size=0)
    try:
        rows = await local.fetch(
            f"SELECT {', '.join(COLS)} FROM voices WHERE org_id IS NULL ORDER BY name")
    finally:
        await local.close()
    print(f"local  : {len(rows)} stock voice(s) found")
    if not rows:
        print("nothing to copy."); return

    placeholders = ", ".join(f"${i + 1}" for i in range(len(COLS)))
    insert = (f"INSERT INTO voices ({', '.join(COLS)}) VALUES ({placeholders}) "
              f"ON CONFLICT {CONFLICT} DO NOTHING")

    neon = await asyncpg.connect(NEON_URL, statement_cache_size=0)
    try:
        inserted = 0
        for r in rows:
            status = await neon.execute(insert, *[r[c] for c in COLS])
            if status.split()[-1] == "1":   # "INSERT 0 1" vs "INSERT 0 0"
                inserted += 1
        total = await neon.fetchval("SELECT count(*) FROM voices WHERE org_id IS NULL")
        print(f"neon   : inserted {inserted} new, {len(rows) - inserted} already present "
              f"-> {total} stock voice(s) on Neon")
    finally:
        await neon.close()


if __name__ == "__main__":
    asyncio.run(main())
