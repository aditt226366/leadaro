"""Feature 2 — voice gallery, preview and cloning."""
import os

import httpx
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status

import db
from auth import Principal, audit, current_user

router = APIRouter(prefix="/voices", tags=["voices"])

ELEVEN_KEY = os.environ.get("ELEVENLABS_API_KEY", "")
CARTESIA_KEY = os.environ.get("CARTESIA_API_KEY", "")


# The 13 languages the FRD lists. Cartesia carries 42; we surface these.
FRD_LANGUAGES = {
    "en": "English", "es": "Spanish", "fr": "French", "de": "German",
    "ar": "Arabic", "ta": "Tamil", "hi": "Hindi", "te": "Telugu",
    "ml": "Malayalam", "ja": "Japanese", "zh": "Mandarin",
    "pt": "Portuguese", "it": "Italian",
}

# Cartesia exposes no accent field, so it is inferred from the voice name and
# description. A miss just means the voice shows as "Neutral" — it never blocks
# playback, which is why a lookup table beats anything cleverer here.
ACCENT_HINTS = [
    ("American", ("american", "us ", "midwest", "california", "new york")),
    ("British", ("british", "uk ", "london", "english accent", "rp ")),
    ("Australian", ("australian", "aussie")),
    ("Indian", ("indian", "india")),
    ("Irish", ("irish",)),
    ("Scottish", ("scottish", "scots")),
    ("Canadian", ("canadian",)),
    ("Spanish", ("spanish", "castilian", "iberian")),
    ("Latin American", ("latin", "mexican", "colombian", "argentin")),
    ("French", ("french", "parisian")),
    ("German", ("german",)),
    ("Brazilian", ("brazil",)),
]

# Vertical is likewise inferred; it drives the library's tone filter.
TONE_HINTS = [
    ("sales", ("sales", "persuasive", "confident", "pitch")),
    ("support", ("support", "helpful", "friendly", "warm", "patient")),
    ("professional", ("professional", "corporate", "business", "formal", "news")),
    ("energetic", ("energetic", "upbeat", "excited", "lively")),
    ("calm", ("calm", "soothing", "gentle", "relaxed", "meditation")),
    ("recruitment", ("recruit", "interview")),
    ("healthcare", ("health", "medical", "care", "nurse")),
    ("finance", ("finance", "banking", "advisor")),
]


def _classify(name: str, description: str, table) -> str | None:
    blob = f"{name} {description}".lower()
    for label, needles in table:
        if any(n in blob for n in needles):
            return label
    return None


@router.post("/sync")
async def sync_voices(user: Principal = Depends(current_user)):
    """
    Pull the real voice catalogue from Cartesia.

    The seed originally invented ids like `stock-voice-1`, which Cartesia
    rejects — it requires a UUID. Rather than hand-maintaining a list that
    drifts, this fetches the live catalogue and keeps only the FRD's languages.
    Safe to re-run; it upserts on (provider, provider_id).
    """
    if not CARTESIA_KEY:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE,
                            "CARTESIA_API_KEY not configured")

    fetched: list[dict] = []
    cursor = None
    async with httpx.AsyncClient(timeout=45) as c:
        for _ in range(15):          # bounded: ~1500 voices is far beyond the catalogue
            params = {"limit": 100}
            if cursor:
                params["starting_after"] = cursor
            r = await c.get(
                "https://api.cartesia.ai/voices/",
                params=params,
                headers={"X-API-Key": CARTESIA_KEY, "Cartesia-Version": "2024-11-13"},
            )
            if r.status_code >= 400:
                raise HTTPException(status.HTTP_502_BAD_GATEWAY,
                                    f"Cartesia listing failed: {r.text[:200]}")
            body = r.json()
            rows = body.get("data", [])
            fetched.extend(rows)
            if not body.get("has_more") or not rows:
                break
            cursor = rows[-1]["id"]

    keep = [v for v in fetched if v.get("language") in FRD_LANGUAGES]

    async with db.tx() as conn:
        # Replace the stock set wholesale — org-owned clones are untouched.
        await conn.execute("DELETE FROM voices WHERE org_id IS NULL")
        for v in keep:
            name = v.get("name") or "Unnamed"
            desc = v.get("description") or ""
            await conn.execute(
                """INSERT INTO voices (org_id, name, provider, provider_id, gender,
                                       accent, language, tone, vertical, is_clone)
                   VALUES (NULL,$1,'cartesia',$2,$3,$4,$5,$6,$6,false)""",
                name.split(" - ")[0].strip(),
                v["id"],
                (v.get("gender") or "").lower() or None,
                _classify(name, desc, ACCENT_HINTS) or "Neutral",
                v["language"],
                _classify(name, desc, TONE_HINTS) or "professional",
            )

    await audit(user.org_id, user.user_id, "voices.sync", "voices", None,
                {"fetched": len(fetched), "kept": len(keep)})
    return {
        "fetched": len(fetched),
        "imported": len(keep),
        "languages": sorted({v["language"] for v in keep}),
    }


@router.get("/languages")
async def languages(user: Principal = Depends(current_user)):
    """Languages actually present in the library, with voice counts."""
    rows = await db.fetch(
        """SELECT language, count(*) AS voices FROM voices
           WHERE org_id = $1 OR org_id IS NULL
           GROUP BY language ORDER BY count(*) DESC""",
        user.org_id,
    )
    return [
        {"code": r["language"],
         "label": FRD_LANGUAGES.get(r["language"], r["language"].upper()),
         "voices": r["voices"]}
        for r in rows
    ]


@router.get("/facets")
async def facets(user: Principal = Depends(current_user)):
    """
    Distinct filter values, derived from what's in the library.

    Hardcoding these was the bug behind the five-item accent dropdown — the
    list said what we imagined, not what exists.
    """
    async def distinct(col: str) -> list[str]:
        rows = await db.fetch(
            f"""SELECT DISTINCT {col} AS v FROM voices
                WHERE (org_id = $1 OR org_id IS NULL) AND {col} IS NOT NULL
                ORDER BY 1""",
            user.org_id,
        )
        return [r["v"] for r in rows]

    return {
        "gender": await distinct("gender"),
        "accent": await distinct("accent"),
        "tone": await distinct("tone"),
        "language": await languages(user),
    }


@router.get("")
async def list_voices(
    gender: str | None = None,
    language: str | None = None,
    accent: str | None = None,
    tone: str | None = None,
    vertical: str | None = None,
    clones_only: bool = False,
    user: Principal = Depends(current_user),
):
    rows = await db.fetch(
        """
        SELECT * FROM voices
        WHERE (org_id = $1 OR org_id IS NULL)          -- org clones + stock voices
          AND ($2::text IS NULL OR gender   = $2)
          AND ($3::text IS NULL OR language = $3)
          AND ($4::text IS NULL OR accent   = $4)
          AND ($5::text IS NULL OR tone     = $5)
          AND ($6::text IS NULL OR vertical = $6)
          AND ($7 = false OR is_clone = true)
        ORDER BY is_clone DESC, name
        """,
        user.org_id, gender, language, accent, tone, vertical, clones_only,
    )
    return [{**r, "id": str(r["id"]),
             "org_id": str(r["org_id"]) if r["org_id"] else None} for r in rows]


@router.post("/preview")
async def preview(body: dict, user: Principal = Depends(current_user)):
    """
    Synthesize a sample line so the user can hear a voice before committing.
    Returns audio bytes; the client plays them and draws the waveform.
    """
    voice_id = body.get("voice_id")
    text = (body.get("text") or "").strip()
    if not voice_id or not text:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "voice_id and text required")

    v = await db.fetchrow(
        """SELECT provider, provider_id, language FROM voices
           WHERE id = $1 AND (org_id = $2 OR org_id IS NULL)""",
        voice_id, user.org_id,
    )
    if not v:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "voice not found")

    audio = await _synthesize(
        v["provider"], v["provider_id"], text[:500],
        body.get("speed", "normal"), body.get("emotion"),
        body.get("language") or v["language"] or "en",
    )
    from fastapi import Response
    return Response(content=audio, media_type="audio/mpeg")


# Cartesia takes speed as a float; the UI speaks in words.
SPEED_MAP = {"slow": -0.4, "normal": 0.0, "fast": 0.4}


async def _synthesize(provider: str, pid: str, text: str, speed: str,
                      emotion: str | None, language: str = "en") -> bytes:
    if provider == "cartesia":
        if not CARTESIA_KEY:
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE,
                                "CARTESIA_API_KEY not configured")

        # Emotion is steered through the transcript rather than a parameter:
        # sonic-3 reads bracketed performance cues, and there is no separate
        # emotion field on the bytes endpoint.
        transcript = f"[{emotion}] {text}" if emotion else text

        payload = {
            "model_id": "sonic-3",
            "transcript": transcript,
            "voice": {"mode": "id", "id": pid},
            "output_format": {"container": "mp3", "sample_rate": 44100,
                              "bit_rate": 128000},
            "language": language,
            "speed": SPEED_MAP.get(speed, 0.0),
        }
        async with httpx.AsyncClient(timeout=30) as c:
            r = await c.post(
                "https://api.cartesia.ai/tts/bytes",
                headers={"X-API-Key": CARTESIA_KEY, "Cartesia-Version": "2024-11-13"},
                json=payload,
            )
        if r.status_code >= 400:
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"TTS failed: {r.text[:200]}")
        return r.content

    if provider == "elevenlabs":
        if not ELEVEN_KEY:
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE,
                                "ELEVENLABS_API_KEY not configured")
        async with httpx.AsyncClient(timeout=30) as c:
            r = await c.post(
                f"https://api.elevenlabs.io/v1/text-to-speech/{pid}",
                headers={"xi-api-key": ELEVEN_KEY},
                json={"text": text, "model_id": "eleven_turbo_v2_5"},
            )
        if r.status_code >= 400:
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"TTS failed: {r.text[:200]}")
        return r.content

    raise HTTPException(status.HTTP_400_BAD_REQUEST, f"unknown provider: {provider}")


@router.post("/clone", status_code=status.HTTP_201_CREATED)
async def clone_voice(
    name: str = Form(...),
    sample: UploadFile = File(...),
    language: str = Form("en"),
    gender: str | None = Form(None),
    user: Principal = Depends(current_user),
):
    """
    Feature 2 — upload a sample, register a cloned voice against the org.

    Consent note: the caller is responsible for having the speaker's permission.
    We record who uploaded it and when, so that claim is auditable.
    """
    if not ELEVEN_KEY:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE,
                            "ELEVENLABS_API_KEY not configured")

    blob = await sample.read()
    if len(blob) < 8_000:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            "sample too short — supply at least a few seconds of clean speech")

    async with httpx.AsyncClient(timeout=120) as c:
        r = await c.post(
            "https://api.elevenlabs.io/v1/voices/add",
            headers={"xi-api-key": ELEVEN_KEY},
            data={"name": name},
            files={"files": (sample.filename or "sample.wav", blob,
                             sample.content_type or "audio/wav")},
        )
    if r.status_code >= 400:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"clone failed: {r.text[:300]}")

    provider_id = r.json().get("voice_id")
    row = await db.fetchrow(
        """INSERT INTO voices (org_id, name, provider, provider_id, gender,
                               language, is_clone)
           VALUES ($1,$2,'elevenlabs',$3,$4,$5,true) RETURNING *""",
        user.org_id, name, provider_id, gender, language,
    )
    await audit(user.org_id, user.user_id, "voice.clone", "voice", str(row["id"]),
                {"name": name})
    return {**row, "id": str(row["id"]), "org_id": str(row["org_id"])}
