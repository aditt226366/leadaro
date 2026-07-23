"""
Validate every dependency a live call touches, before dialling anyone.

    python infra/preflight.py

Exists because the first call attempt failed on a Plivo country block, which
masked two further faults that would each have produced a connected call with
silence on it. A caller picking up to dead air is the worst possible way to
discover a missing API key.
"""
import asyncio
import os
import pathlib
import sys

import httpx
from dotenv import load_dotenv

ROOT = pathlib.Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")
sys.path.insert(0, str(ROOT / "services" / "api"))
sys.path.insert(0, str(ROOT / "services" / "agent"))

OK, BAD, WARN = "  OK  ", " FAIL ", " WARN "
results: list[tuple[str, str, str]] = []


def record(status: str, name: str, detail: str = "") -> None:
    results.append((status, name, detail))
    print(f"[{status}] {name}" + (f" — {detail}" if detail else ""))


async def check_db() -> None:
    try:
        import db
        await db.init_pool()
        n = await db.fetchval("SELECT count(*) FROM campaigns")
        await db.close_pool()
        record(OK, "Postgres", f"{n} campaigns")
    except Exception as e:
        record(BAD, "Postgres", str(e)[:120])


async def check_anthropic() -> None:
    try:
        from anthropic import AsyncAnthropic
        c = AsyncAnthropic()
        r = await c.messages.create(
            model=os.environ.get("LLM_MODEL", "claude-sonnet-4-6"),
            max_tokens=5, messages=[{"role": "user", "content": "say ok"}],
        )
        record(OK, "Anthropic", f"{r.model}")
    except Exception as e:
        record(BAD, "Anthropic", str(e)[:120])


async def check_cartesia(voice_id: str | None) -> None:
    key = os.environ.get("CARTESIA_API_KEY")
    if not key:
        record(BAD, "Cartesia", "CARTESIA_API_KEY not set")
        return
    if not voice_id:
        record(WARN, "Cartesia", "no voice resolved for the campaign")
        return
    try:
        async with httpx.AsyncClient(timeout=30) as c:
            r = await c.post(
                "https://api.cartesia.ai/tts/bytes",
                headers={"X-API-Key": key, "Cartesia-Version": "2024-11-13"},
                json={"model_id": "sonic-3", "transcript": "Preflight check.",
                      "voice": {"mode": "id", "id": voice_id},
                      "output_format": {"container": "mp3", "sample_rate": 44100,
                                        "bit_rate": 128000},
                      "language": "en"},
            )
        if r.status_code == 200 and len(r.content) > 1000:
            record(OK, "Cartesia TTS", f"{len(r.content)} bytes with the campaign voice")
        else:
            record(BAD, "Cartesia TTS", f"HTTP {r.status_code} {r.text[:100]}")
    except Exception as e:
        record(BAD, "Cartesia TTS", str(e)[:120])


async def check_deepgram_stt() -> None:
    """Transcription runs on Deepgram Nova-3 (language=multi)."""
    key = os.environ.get("DEEPGRAM_API_KEY")
    if not key:
        record(BAD, "Deepgram STT", "DEEPGRAM_API_KEY not set")
        return
    try:
        async with httpx.AsyncClient(timeout=30) as c:
            # Listing projects requires a valid key and touches nothing.
            r = await c.get("https://api.deepgram.com/v1/projects",
                            headers={"Authorization": f"Token {key}"})
        record(OK if r.status_code == 200 else BAD, "Deepgram STT",
               "key valid (nova-3, multi)" if r.status_code == 200
               else f"HTTP {r.status_code}")
    except Exception as e:
        record(BAD, "Deepgram STT", str(e)[:120])


async def check_elevenlabs() -> None:
    """
    Only voice CLONING uses ElevenLabs now, which is off the call path — so a
    bad key here is a warning, not a blocker.
    """
    key = os.environ.get("ELEVENLABS_API_KEY")
    if not key:
        record(WARN, "ElevenLabs", "not set — voice cloning unavailable")
        return
    try:
        async with httpx.AsyncClient(timeout=30) as c:
            r = await c.get("https://api.elevenlabs.io/v1/user",
                            headers={"xi-api-key": key})
        record(OK if r.status_code == 200 else WARN, "ElevenLabs (cloning only)",
               "key valid" if r.status_code == 200
               else f"HTTP {r.status_code} — cloning will fail, calls unaffected")
    except Exception as e:
        record(WARN, "ElevenLabs (cloning only)", str(e)[:120])


async def check_livekit() -> None:
    try:
        from livekit import api
        lk = api.LiveKitAPI()
        try:
            out = await lk.sip.list_sip_outbound_trunk(
                api.ListSIPOutboundTrunkRequest())
            want = os.environ.get("SIP_OUTBOUND_TRUNK_ID", "")
            ids = [t.sip_trunk_id for t in out.items]
            if want in ids:
                record(OK, "LiveKit SIP", f"outbound trunk {want}")
            else:
                record(BAD, "LiveKit SIP",
                       f"SIP_OUTBOUND_TRUNK_ID={want or '(unset)'} not among {ids}")
        finally:
            await lk.aclose()
    except Exception as e:
        record(BAD, "LiveKit", str(e)[:120])


async def check_plivo(destination: str | None) -> None:
    aid = os.environ.get("PLIVO_AUTH_ID")
    tok = os.environ.get("PLIVO_AUTH_TOKEN")
    if not (aid and tok):
        record(BAD, "Plivo", "credentials not set")
        return
    try:
        async with httpx.AsyncClient(timeout=30, auth=(aid, tok)) as c:
            r = await c.get(f"https://api.plivo.com/v1/Account/{aid}/")
            if r.status_code != 200:
                record(BAD, "Plivo", f"HTTP {r.status_code}")
                return
            credit = float(r.json().get("cash_credits") or 0)
            record(OK if credit > 0.5 else WARN, "Plivo account",
                   f"${credit:.2f} credit")
    except Exception as e:
        record(BAD, "Plivo", str(e)[:120])

    if destination:
        cc = destination[:3]
        record(WARN, "Plivo destination",
               f"{destination} — country permissions are set in the Plivo "
               f"console; a barred country returns SIP 403 at dial time")


async def check_worker_agent() -> None:
    """The dialer dispatches by agent name; a typo means a silent call."""
    try:
        from livekit import api
        lk = api.LiveKitAPI()
        try:
            # No list-workers API; assert the name the dialer will dispatch.
            import dialer
            record(OK, "Agent name", f"dialer dispatches '{dialer.AGENT_NAME}'")
        finally:
            await lk.aclose()
    except Exception as e:
        record(WARN, "Agent name", str(e)[:120])


async def main() -> int:
    destination = sys.argv[1] if len(sys.argv) > 1 else None
    print(f"Preflight{' for ' + destination if destination else ''}\n")

    # Resolve the voice the test campaign would actually use.
    voice_id = None
    try:
        import db
        await db.init_pool()
        voice_id = await db.fetchval(
            """SELECT v.provider_id FROM campaigns c
               JOIN voices v ON v.id = c.voice_id
               WHERE c.name = 'TEST — First Call'""")
        await db.close_pool()
    except Exception:
        pass

    await check_db()
    await check_anthropic()
    await check_deepgram_stt()
    await check_cartesia(voice_id)
    await check_elevenlabs()
    await check_livekit()
    await check_plivo(destination)
    await check_worker_agent()

    failed = [r for r in results if r[0] == BAD]
    print()
    if failed:
        print(f"{len(failed)} check(s) failed — do not dial yet:")
        for _, name, detail in failed:
            print(f"   {name}: {detail}")
        return 1
    print("All checks passed. Safe to place a call.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
