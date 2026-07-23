"""
LiveKit agent worker — the live call runtime.

    python services/agent/worker.py dev      # local
    python services/agent/worker.py start    # production

Job flow: a job arrives carrying a call_id (outbound, placed by the dialer) or
a SIP participant (inbound). We load the campaign and lead, build a Brain, hand
it to AgentSession as the LLM, and let the session own the audio pipeline.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
import time
from datetime import datetime, timezone
from enum import StrEnum
from pathlib import Path

from dotenv import load_dotenv
from livekit import agents, api, rtc
from livekit.agents import (
    Agent, AgentSession, JobContext, JobProcess, RoomInputOptions,
)
from livekit.plugins import cartesia, deepgram, sarvam, silero

# db.py is shared with the API service — one definition of the pool and codecs.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "api"))
import db  # noqa: E402

import prompts
from brain import Brain
from ivr import IvrMenu, run_menu
from lk_llm import SPEED_SCALE, BrainLLM
from rules import Directive, TERMINAL_DIRECTIVES
from stt_router import SARVAM_LANGUAGE, provider_for, sarvam_languages

load_dotenv()
logging.basicConfig(level=logging.INFO)
log = logging.getLogger("worker")

# The dispatched agent name. MUST match the SIP dispatch rule (infra/setup_sip.py)
# and the outbound dialer (dialer.py) — a mismatch means inbound calls ring with
# no agent to route to ("didn't pick up at all").
AGENT_NAME = "leadaro-voice"

# Cartesia's stock voice, used when a campaign carries no voice (e.g. the
# safe-default inbound path below) so TTS never fails on an empty voice id.
DEFAULT_VOICE_ID = "f786b574-daa5-4673-aa0c-cbe3e8534c02"  # Cartesia "Katie"

# Language used for inbound calls whose DID has no campaign (and therefore no
# language) bound. English is the safe universal default; a warning is logged so
# the number gets configured.
DEFAULT_INBOUND_LANGUAGE = "en"


def _default_inbound_campaign() -> dict:
    """
    A minimal campaign for an inbound DID with no `inbound_campaign_id` bound.

    Without this the worker used to `return` on a missing campaign — after it had
    already answered the SIP leg — so the caller heard the line pick up and then
    cut to dead air. This keeps the agent greeting and conversing in a safe
    default language instead. `id` is None so the call row's campaign_id is NULL.
    """
    return {
        "id": None,
        "language": DEFAULT_INBOUND_LANGUAGE,
        "org_name": "our team",
        "voice_config": {},
        "settings": {},
        "script": {},
    }


# ── data loading ─────────────────────────────────────────────────────────────

async def load_call(call_id: str) -> dict | None:
    """
    Load everything the session needs in one round trip.

    `provider_voice_id` is resolved here: campaigns store our internal voice
    UUID, but Cartesia needs *its* id. Passing the internal one produces a
    "voice ID must be a valid UUID"-shaped failure at synthesis time, i.e.
    after the callee has already picked up.
    """
    return await db.fetchrow(
        """
        SELECT c.id AS call_id, c.org_id, c.campaign_id, c.lead_id, c.direction,
               c.to_number, c.from_number,
               row_to_json(cam) AS campaign, row_to_json(l) AS lead,
               o.name  AS org_name,
               v.provider_id AS provider_voice_id,
               v.language    AS voice_language
        FROM calls c
        JOIN campaigns cam    ON cam.id = c.campaign_id
        LEFT JOIN leads l     ON l.id   = c.lead_id
        LEFT JOIN voices v    ON v.id   = cam.voice_id
        JOIN organizations o  ON o.id   = c.org_id
        WHERE c.id = $1
        """,
        call_id,
    )


async def lead_by_phone(org_id: str, phone: str) -> dict | None:
    """Inbound: match the caller to a known lead so we can resume context."""
    return await db.fetchrow(
        "SELECT * FROM leads WHERE org_id = $1 AND phone = $2", org_id, phone
    )


async def prior_call_context(lead_id: str) -> dict | None:
    row = await db.fetchrow(
        """
        SELECT c.outcome::text, c.started_at, s.summary
        FROM calls c LEFT JOIN call_summaries s ON s.call_id = c.id
        WHERE c.lead_id = $1 AND c.ended_at IS NOT NULL
        ORDER BY c.started_at DESC LIMIT 1
        """,
        lead_id,
    )
    if not row:
        return None
    days = (datetime.now(timezone.utc) - row["started_at"]).days
    return {
        "when": "today" if days == 0 else f"{days} day{'s' if days > 1 else ''} ago",
        "summary": row["summary"],
        "outcome": row["outcome"],
    }


# ── persistence ──────────────────────────────────────────────────────────────

# Turn/transcript writes run OFF the turn/audio path. asyncpg is async and does
# not block the event loop, but an awaited write still sits in the sequence
# between the model finishing and the next thing the caller hears (local
# Postgres measured ~44ms per round trip). Fire-and-forget removes even that,
# and future-proofs against a slower DB. Drained before finish_call so the
# transcript is complete before the post-call job reads it.
_write_tasks: set = set()


def _persist(coro) -> None:
    task = asyncio.create_task(coro)
    _write_tasks.add(task)

    def _done(t) -> None:
        _write_tasks.discard(t)
        if not t.cancelled() and (exc := t.exception()) is not None:
            log.error("background DB write failed: %r", exc)

    task.add_done_callback(_done)


async def _drain_writes() -> None:
    """Wait for all fire-and-forget writes to land — called at hangup, off the
    hot path, so the transcript is complete before post-call reads it."""
    if _write_tasks:
        await asyncio.gather(*list(_write_tasks), return_exceptions=True)


async def save_turn(call_id: str | None, org_id: str, seq: int, role: str,
                    text: str, result=None, stt_ms: int | None = None,
                    tts_ms: int | None = None, lang: str | None = None) -> None:
    # An inbound call on an unknown DID (no org) runs without persistence — see
    # the inbound branch in entrypoint(). Nothing to save.
    if call_id is None:
        return
    o = result.output if result else None
    # Fire-and-forget: never let the turn/audio path wait on the database.
    _persist(db.execute(
        """INSERT INTO turns (call_id, org_id, seq, role, text, intent, sentiment,
                              emotion, speed, pitch, action, stt_ms, llm_ms,
                              tts_ms, total_ms, cache_read_tokens, lang)
           VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17)
           ON CONFLICT (call_id, seq) DO NOTHING""",
        call_id, org_id, seq, role, text,
        o.intent if o else None,
        o.sentiment if o else None,
        o.emotion if o else None,
        o.speed if o else None,
        o.pitch if o else None,
        result.directive.value if result else None,
        stt_ms,
        result.llm_ms if result else None,
        tts_ms,
        (stt_ms or 0) + (result.llm_ms if result else 0) + (tts_ms or 0) or None,
        result.cache_read_tokens if result else None,
        lang,
    ))


async def finish_call(call_id: str | None, outcome: str, answered_by: str,
                      started: float, transferred_to: str | None = None) -> None:
    # Unknown-DID inbound call ran without persistence; nothing to finalise and
    # no transcript to post-process.
    if call_id is None:
        return
    dur = int(time.time() - started)
    await db.execute(
        """UPDATE calls
           SET status='completed', ended_at=now(), duration_sec=$2,
               outcome=$3::call_outcome, answered_by=$4::answered_by,
               transferred_to=$5
           WHERE id=$1""",
        call_id, dur, outcome, answered_by, transferred_to,
    )
    # Post-call work runs out of band (post_call.py drains the queue) so hangup
    # is never delayed by it, and the after-call features read the persisted
    # transcript from the turns table.
    await db.execute(
        "INSERT INTO jobs (kind, payload) VALUES ('post_call', $1)",
        {"call_id": call_id},
    )


# ── entrypoint ───────────────────────────────────────────────────────────────

async def entrypoint(ctx: JobContext) -> None:
    await db.init_pool()
    await ctx.connect()
    t_connect = time.perf_counter()   # BUG 1: anchor for the first-audio timeline

    meta = json.loads(ctx.job.metadata or "{}")
    call_id = meta.get("call_id")

    ivr_menu = IvrMenu()          # outbound calls never present a menu

    if call_id:
        record = await load_call(call_id)
        if not record:
            log.error("call %s not found; dropping job", call_id)
            return
        campaign, lead = dict(record["campaign"]), record["lead"] or {}
        org_id, direction = str(record["org_id"]), record["direction"]
        # The remote party on THIS call — the number we dialed. Used to honor an
        # in-call opt-out (write it to the DNC suppression list).
        contact_phone = (lead.get("phone") or record["to_number"] or "").strip()
        # Carry the provider-side voice id into the config the TTS reads.
        campaign.setdefault("voice_config", {})
        campaign["voice_config"] = {
            **(campaign.get("voice_config") or {}),
            "provider_voice_id": record["provider_voice_id"],
        }
        # The chosen voice's language is the source of truth for the call.
        # campaigns.language was left at its 'en' default by the wizard, so
        # relying on it made a Hindi campaign dial in English — STT transcribed
        # against the wrong language and TTS spoke English words. A voice is
        # inseparable from the language it was trained on, so follow the voice.
        if record["voice_language"]:
            campaign["language"] = record["voice_language"]

        # Fail LOUDLY rather than silently conducting a call in the wrong
        # language. In practice the campaign or voice always carries one; an
        # empty value here is a real misconfiguration worth a visible error.
        if not campaign.get("language"):
            log.error(
                "call %s has NO language set on campaign or voice — STT/TTS/LLM "
                "will fall back to English. Fix the campaign or voice config.",
                call_id,
            )
    else:
        # Inbound: identify the caller from the SIP participant.
        participant = await ctx.wait_for_participant()
        phone = (participant.attributes or {}).get("sip.phoneNumber", "")
        to_number = meta.get("to_number", "")
        org_id = meta.get("org_id") or await db.fetchval(
            "SELECT org_id FROM phone_numbers WHERE e164 = $1", to_number
        )
        number_row = await db.fetchrow(
            """SELECT p.ivr_menu, row_to_json(cam) AS campaign
               FROM phone_numbers p
               LEFT JOIN campaigns cam ON cam.id = p.inbound_campaign_id
               WHERE p.e164 = $1""",
            to_number,
        )
        ivr_menu = IvrMenu.from_json((number_row or {}).get("ivr_menu"))
        campaign = (number_row or {}).get("campaign")
        if campaign:
            campaign = dict(campaign)
        else:
            # No inbound campaign bound to this DID. NEVER join-and-cut or sit
            # silent: serve a safe default so the agent still greets and holds a
            # conversation. Warn loudly so the number gets configured.
            log.warning(
                "no inbound campaign bound to %s — serving the safe default "
                "greeting in %r. Bind an inbound_campaign_id to customise it.",
                to_number or "(unknown DID)", DEFAULT_INBOUND_LANGUAGE,
            )
            campaign = _default_inbound_campaign()
        lead = (await lead_by_phone(org_id, phone) if org_id else None) or {}
        direction = "inbound"
        # The remote party on THIS call — the caller's own number (falls back to
        # the matched lead's). Used to honor an in-call opt-out (DNC write).
        contact_phone = (phone or lead.get("phone") or "").strip()
        if org_id:
            call_id = await db.fetchval(
                """INSERT INTO calls (org_id, campaign_id, lead_id, direction,
                                      room_name, from_number, status)
                   VALUES ($1,$2,$3,'inbound',$4,$5,'connected') RETURNING id""",
                org_id, campaign.get("id"), lead.get("id"), ctx.room.name, phone,
            )
        else:
            # DID has no phone_numbers row at all — no tenant to attach the call
            # to. We still greet and converse rather than drop the caller;
            # persistence is skipped (save_turn/finish_call no-op on None).
            log.error(
                "inbound DID %r resolves to no org — running WITHOUT persistence",
                to_number or "(unknown)",
            )
            call_id = None

    campaign = dict(campaign)
    campaign["org_name"] = campaign.get("org_name") or "our team"
    brain = Brain(campaign, dict(lead))
    # The number to suppress if the caller opts out mid-call (set per direction
    # above). _end_call reads it off the brain on an OPT_OUT end.
    brain.contact_phone = contact_phone
    # Give the model the concrete values behind the script's {{placeholders}}
    # (as a per-call message, not the cached system prompt) so it substitutes
    # names/company/etc. naturally.
    brain.seed_lead_context()
    # The call's language, stamped on every transcript row so the after-call
    # worker reads (speaker, text, timestamp, language) per turn.
    lang = campaign.get("language")

    # Inbound from a known lead: seed the prior conversation so the agent opens
    # with context instead of a cold greeting.
    if direction == "inbound" and lead.get("id"):
        if prior := await prior_call_context(str(lead["id"])):
            brain.seed_inbound_context(prior)

    started = time.time()
    seq = {"n": 0}
    final_outcome = {"value": "no_answer", "answered_by": "unknown",
                     "transferred_to": None}

    # Populated from the session's own metrics events, then attached to the next
    # saved turn. Without these, total_ms is just llm_ms and understates what the
    # callee actually waited through.
    timing = {"stt_ms": None, "tts_ms": None}

    async def on_turn(heard: str, result) -> None:
        seq["n"] += 1
        await save_turn(call_id, org_id, seq["n"], "lead", heard, lang=lang)
        seq["n"] += 1
        await save_turn(call_id, org_id, seq["n"], "agent", result.output.reply,
                        result=result, stt_ms=timing["stt_ms"],
                        tts_ms=timing["tts_ms"], lang=lang)
        # Per-turn latency breakdown — which stage owns the wall-clock. e2e is
        # to FIRST audio (what the caller waits through). llm_ttft is the LLM's
        # time-to-first-sentence; llm_total is its full-object time. A healthy
        # call reads cache (cache_read > 0) from turn 2 on.
        stt, tts = timing["stt_ms"] or 0, timing["tts_ms"] or 0
        log.info(
            "turn %d latency: stt=%dms llm_ttft=%dms llm_total=%dms tts=%dms "
            "e2e=%dms | cache_read=%d in=%d out=%d",
            brain.state.turn_count, stt, result.llm_ms, result.full_ms, tts,
            stt + result.llm_ms + tts, result.cache_read_tokens,
            result.input_tokens, result.output_tokens,
        )
        timing["stt_ms"] = timing["tts_ms"] = None
        final_outcome["answered_by"] = "human"
        final_outcome["value"] = _outcome_for(result)

    # Reuse the VAD and STT built in prewarm() so the first turn isn't blocked
    # on a model load or a fresh connection. STT is routed by language.
    vad = ctx.proc.userdata.get("vad") or silero.VAD.load(min_silence_duration=0.4)
    stt = _resolve_stt(campaign.get("language"), ctx.proc.userdata)
    # Voicemail/answering-machine detection is an OUTBOUND concern only. On an
    # inbound call a human dialled us, so a false ivr_detected must never fire
    # _leave_voicemail and cut the caller off.
    session = _build_session(campaign, brain, on_turn, vad, stt,
                             ivr_detection=(direction == "outbound"))

    @session.on("metrics_collected")
    def _on_metrics(ev) -> None:
        m = ev.metrics
        # Transcription delay is the part of STT the caller actually waits on;
        # ttfb is the equivalent for TTS. Both are seconds.
        if (d := getattr(m, "transcription_delay", None)) is not None:
            timing["stt_ms"] = int(d * 1000)
        elif (t := getattr(m, "ttfb", None)) is not None and type(m).__name__.startswith("TTS"):
            timing["tts_ms"] = int(t * 1000)

    # Voicemail/IVR detection is native in livekit-agents 1.6 — no bespoke
    # beep-detection heuristic to maintain.
    @session.on("ivr_detected")
    def _on_ivr(_ev) -> None:
        asyncio.create_task(_leave_voicemail(session, campaign, lead, call_id,
                                             org_id, started, final_outcome))

    # BUG 1: start GENERATING the first line now, so its text (a live LLM
    # translation on a non-English call) is ready by the time the audio pipeline
    # is up — the two overlap instead of running back to back. English openings
    # are instant, so this costs nothing there.
    first_line_task = None
    if direction == "outbound":
        first_line_task = asyncio.create_task(brain.opening_localized())
    elif not ivr_menu.enabled:
        first_line_task = asyncio.create_task(brain.inbound_greeting_localized())

    t_pre_start = time.perf_counter()
    await session.start(
        room=ctx.room,
        agent=Agent(instructions=brain.system),
        room_input_options=RoomInputOptions(close_on_disconnect=True),
    )
    t_started = time.perf_counter()

    def _log_first_audio(kind: str, ready_at: float) -> None:
        log.info(
            "first-audio timeline [%s]: connect->build=%dms session.start=%dms "
            "%s_ready=%dms | connect->speaking=%dms (call %s)",
            kind, int((t_pre_start - t_connect) * 1000),
            int((t_started - t_pre_start) * 1000),
            kind, int((ready_at - t_started) * 1000),
            int((time.perf_counter() - t_connect) * 1000), call_id,
        )

    if direction == "outbound":
        # In the call's language, not hardcoded English — a Tamil campaign must
        # open in Tamil. English campaigns pay no extra latency for this.
        opening = await first_line_task
        # Record it before speaking. The opening carries the AI disclosure, so a
        # transcript without it is an incomplete compliance record. It also has
        # to enter the model's history — otherwise the first real turn starts
        # from an empty context and the agent introduces itself a second time.
        seq["n"] += 1
        await save_turn(call_id, org_id, seq["n"], "agent", opening, lang=lang)
        brain.note_spoken(opening)
        _log_first_audio("opening", time.perf_counter())
        await session.say(opening, allow_interruptions=True)
    elif ivr_menu.enabled:
        # Keypad menu first. Pressing nothing falls through to the AI agent
        # rather than dropping the caller.
        choice = await run_menu(session, ctx.room, ivr_menu)
        if choice:
            await save_turn(call_id, org_id, 1, "lead",
                            f"[keypad] pressed {choice.digit} — {choice.label}")
            seq["n"] = 1

            if choice.action == "hangup":
                final_outcome["value"] = "not_interested"
                await session.aclose()
                return
            if choice.action == "voicemail":
                final_outcome["value"] = "voicemail"
                await session.say(
                    (campaign.get("script") or {}).get("voicemail_message")
                    or "Please leave a message after the tone.",
                )
                await session.aclose()
                return
            if choice.action == "transfer" and choice.target:
                final_outcome["value"] = "transferred"
                await _sip_transfer(ctx, choice.target)
                await session.aclose()
                return
            # ai_agent — carry on into the normal conversation.
    else:
        # Inbound with no keypad menu — the agent must speak first, in the
        # number's language, then enter the same turn loop. Without this the
        # agent sat silent and the inbound caller heard dead air.
        greeting = await first_line_task
        seq["n"] += 1
        await save_turn(call_id, org_id, seq["n"], "agent", greeting, lang=lang)
        brain.note_spoken(greeting)
        _log_first_audio("greeting", time.perf_counter())
        await session.say(greeting, allow_interruptions=True)

    try:
        await _run_until_done(session, brain, ctx, call_id, org_id,
                              started, final_outcome, seq, lang)
    finally:
        # Ensure every fire-and-forget transcript write has landed BEFORE we
        # finalise the call + enqueue post-call (which reads the turns table).
        await _drain_writes()
        await finish_call(call_id, final_outcome["value"],
                          final_outcome["answered_by"], started,
                          final_outcome["transferred_to"])
        await db.close_pool()


def _resolve_stt(language: str | None, userdata: dict):
    """
    Pick the STT for this call's language from the prewarmed pool.

    Refuses to fall back to Deepgram for a Sarvam-routed language — Deepgram
    mistranscribes Tamil into garbage, so a call in that language fails loudly
    here rather than running with an STT that cannot understand the caller.
    """
    provider = provider_for(language)
    pool = userdata.get("stt_pool") or {}

    if provider == "deepgram":
        # One shared multilingual instance (en, hi); build fresh if prewarm
        # didn't run.
        return pool.get("deepgram") or deepgram.STT(
            model="nova-3", language="multi",
            api_key=os.environ.get("DEEPGRAM_API_KEY"),
        )

    if provider == "sarvam":
        if stt := pool.get(f"sarvam:{language}"):
            return stt
        # Prewarm didn't build it (missing key, or a dev path). A Sarvam
        # language with no key cannot be transcribed — fail loud rather than
        # send it to Deepgram, which mistranscribes these languages.
        sarvam_key = os.environ.get("SARVAM_API_KEY")
        if not sarvam_key:
            raise RuntimeError(
                f"language {language!r} routes to Sarvam, but SARVAM_API_KEY is "
                f"not set. Add it to .env to transcribe {language!r} calls."
            )
        return sarvam.STT(
            model="saaras:v3",
            language=SARVAM_LANGUAGE.get(language, "ta-IN"),
            mode="transcribe", api_key=sarvam_key, high_vad_sensitivity=True,
        )

    raise RuntimeError(
        f"language {language!r} routes to unknown STT provider '{provider}'."
    )


def _prosody_from_config(cfg: dict) -> tuple[float | None, str]:
    """
    Map the campaign's prosody controls onto REAL Cartesia sonic-3 parameters.

    Cartesia sonic-3 exposes only speed, a single categorical emotion, and
    volume — there is NO pitch, energy, or emotion-intensity parameter. So of the
    dashboard's five controls, only two map to a real parameter and are wired
    here; the rest are intentionally not invented (see the plan/notes):

      - Speech Intensity  -> Cartesia `volume` (0.5-2.0 on sonic-3).
      - Natural Pause     -> inline `<break time="Nms"/>` markup in the reply
                             text (NOT a TTS parameter). Integer ms only: a
                             decimal in the value is split by the tokenizer.
      - Emotion Level     -> unsupported (emotion is categorical, no level).
      - Energy Level      -> unsupported (no Cartesia parameter).
      - Pitch             -> unsupported (Cartesia has no pitch control).

    Returns (volume, pause_tag). volume is None when unset (Cartesia default).
    """
    volume: float | None = None
    raw = cfg.get("speech_intensity", cfg.get("volume"))
    if raw is not None:
        try:
            volume = min(2.0, max(0.5, float(raw)))
        except (TypeError, ValueError):
            volume = None

    pause_tag = ""
    if cfg.get("natural_pause") or cfg.get("pause_controls"):
        try:
            ms = int(cfg.get("pause_ms", 350))
        except (TypeError, ValueError):
            ms = 350
        ms = max(0, ms)
        if ms:
            pause_tag = f'<break time="{ms}ms"/>'
    return volume, pause_tag


def _build_session(campaign: dict, brain: Brain, on_turn, vad, stt, *,
                   ivr_detection: bool = True) -> AgentSession:
    cfg = campaign.get("voice_config") or {}
    settings = campaign.get("settings") or {}
    volume, pause_tag = _prosody_from_config(cfg)

    # STT is Deepgram Nova-3 multilingual (passed in, prewarmed and shared —
    # see prewarm()). Cartesia ink-whisper transcribed multilingual phone audio
    # poorly — a Tamil caller came back as a repeated stray word. TTS stays on
    # Cartesia sonic-3, which does render Tamil correctly and is per-call because
    # the voice and language vary; STT does not, thanks to language="multi".
    #
    # Keys are passed explicitly rather than relying on each plugin's env
    # lookup, so a rename in .env can never silently break a live call.
    tts = cartesia.TTS(
        api_key=os.environ.get("CARTESIA_API_KEY"),
        model="sonic-3",
        voice=cfg.get("provider_voice_id") or cfg.get("voice_id") or DEFAULT_VOICE_ID,
        # Base speed -> sonic-3 scale (0.6-2.0); per-turn delivery overrides it.
        speed=SPEED_SCALE.get(cfg.get("speed", "normal"), 1.0),
        # Speech Intensity control -> Cartesia volume (sonic-3: 0.5-2.0).
        volume=volume,
        language=campaign.get("language", "en"),
    )

    # Natural Pause control -> <break> markup appended to each spoken sentence.
    brain_llm = BrainLLM(brain, on_turn=on_turn, tts=tts, pause_tag=pause_tag)

    session = AgentSession(
        stt=stt,
        tts=tts,
        vad=vad,
        # tts is handed over so each turn's emotion and speed can retune the
        # voice mid-call instead of speaking the whole call in one register.
        llm=brain_llm,
        # Start generating on the partial transcript instead of waiting for the
        # endpointer to confirm the turn. The reply is already part-written by
        # the time the caller actually stops, which removes endpointing and STT
        # finalisation from the critical path. If the caller keeps talking the
        # speculative generation is discarded and re-run.
        preemptive_generation=bool(settings.get("preemptive_generation", True)),
        # Barge-in: the caller talking over the agent stops TTS immediately.
        allow_interruptions=True,
        min_interruption_duration=0.4,
        # Endpointing. Lower = snappier but more false turns on a noisy line.
        # 0.4s was a straight 400ms added to every single turn before the model
        # even saw the words. 0.3 is still comfortably above a normal
        # mid-sentence pause without clipping people mid-thought.
        min_endpointing_delay=float(settings.get("min_endpointing_delay", 0.3)),
        max_endpointing_delay=float(settings.get("max_endpointing_delay", 4.0)),
        # Only on outbound (see caller): an inbound human must never be treated
        # as an answering machine and cut off.
        ivr_detection=ivr_detection and bool(settings.get("voicemail_detection", True)),
    )

    return session


def _outcome_for(result) -> str:
    """Map the resolved directive onto a call disposition."""
    return {
        Directive.BOOK_MEETING: "meeting_scheduled",
        Directive.PUSH_FOR_MEETING: "interested",
        Directive.TRANSFER_HUMAN: "transferred",
        Directive.OFFER_CALLBACK: "callback",
        Directive.EXIT_APOLOGETIC: "not_interested",
        Directive.EXPLAIN_DETAIL: "interested",
        Directive.HANDLE_OBJECTION: "interested",
        Directive.OPT_OUT: "do_not_call",
    }.get(result.directive, "interested"
          if result.output.sentiment > 0.2 else "not_interested")


async def _leave_voicemail(session, campaign, lead, call_id, org_id, started,
                           final) -> None:
    """Machine answered: leave the campaign's voicemail message and hang up."""
    script = campaign.get("script") or {}
    msg = prompts.render(
        script.get("voicemail_message")
        or "Sorry we missed you. We'll try again soon.",
        dict(lead),
    )
    if (campaign.get("settings") or {}).get("leave_voicemail", True):
        await session.say(msg, allow_interruptions=False)
        await save_turn(call_id, org_id, 1, "agent", msg)
    final["value"] = "voicemail"
    final["answered_by"] = "machine"
    await asyncio.sleep(1)
    await session.aclose()


async def _suppress_contact(org_id, phone, reason="in-call opt-out") -> bool:
    """
    Write the caller to the DNC suppression list — the SAME table the dialer
    checks before every outbound call (dialer.is_suppressed), so the number can
    never be dialed again from any campaign in this org.

    This is a compliance write, so it is AWAITED and durable, not fire-and-forget
    like the transcript writes: the caller is promised removal in the very next
    breath, and that promise must already be true. It never raises into the call
    path — a failure is logged LOUDLY (the caller asked to be removed but was
    not) so it can be reconciled, and the call still ends cleanly.
    """
    if not (org_id and phone):
        log.error("opt-out with no org/phone (org=%r phone=%r) — caller NOT "
                  "written to DNC; reconcile manually", org_id, phone)
        return False
    try:
        await db.execute(
            """INSERT INTO suppression_list (org_id, phone, kind, reason)
               VALUES ($1, $2, 'dnc', $3)
               ON CONFLICT (org_id, phone, kind)
               DO UPDATE SET reason = EXCLUDED.reason""",
            org_id, phone, reason,
        )
        log.info("opt-out: suppressed %s for org %s (%s)", phone, org_id, reason)
        return True
    except Exception:
        log.exception("opt-out DNC write FAILED for %s org %s — caller asked to "
                      "be removed but was NOT suppressed; reconcile NOW",
                      phone, org_id)
        return False


# How the loop-ender behaves once a terminal directive lands.
_POLL_INTERVAL = 0.25
# After a close, keep listening this long for the customer to carry on. Long
# enough to catch a reply to "I'll schedule a meeting"; short enough that a real
# goodbye is not followed by awkward dead air.
_CLOSE_CONFIRM_WINDOW = 5.0


# ── the single termination path ──────────────────────────────────────────────
#
# THE INVARIANT: no directive, intent or action ends the call directly. When an
# end condition is reached the loop maps it to an EndReason and calls _end_call()
# — the ONLY place a call is torn down — which speaks every sign-off stage
# configured for that reason IN FULL before it hangs up. This is what stops the
# "closed too early" class of bug: a new sign-off stage can never be skipped,
# because the hangup only happens after the whole sequence has played.

class EndReason(StrEnum):
    BOOKED = "booked"        # engaged positive close, a booking happened
    POLITE = "polite"        # engaged positive close, no booking
    DECLINE = "decline"      # polite "not interested"
    REJECT = "reject"        # spam / wrong number — the model already apologised
    TRANSFER = "transfer"    # hand off to a human (no sign-off; a human takes over)
    CALLBACK = "callback"    # offer a callback then end
    DROPPED = "dropped"      # customer hung up / line dropped — nothing to say
    OPT_OUT = "opt_out"      # compliance removal — DNC write + bare confirmation only


# Sign-off stages spoken, IN ORDER, per end reason — the SINGLE source of truth.
# To add a stage, add its producer here; _end_call() speaks the whole list before
# hanging up, so it can never be skipped by a termination path.
async def _sf_closing(b):   return await b.closing_statement_localized()
async def _sf_thank_you(b): return await b.thank_you_localized()
async def _sf_ending(b):    return await b.ending_message_localized()
async def _sf_callback(b):  return await b.callback_offer_localized()
async def _sf_optout(b):    return await b.opt_out_confirmation_localized()

_SIGN_OFF: dict = {
    EndReason.BOOKED:   (_sf_closing, _sf_thank_you, _sf_ending),
    EndReason.POLITE:   (_sf_closing, _sf_thank_you),
    EndReason.DECLINE:  (_sf_closing, _sf_thank_you),
    EndReason.REJECT:   (),
    EndReason.CALLBACK: (_sf_callback,),
    EndReason.DROPPED:  (),
    # Compliance: ONLY the removal confirmation. No closing, no thank-you, no
    # sales sign-off — an opt-out is not a warm goodbye.
    EndReason.OPT_OUT:  (_sf_optout,),
}


def _end_reason_for_close(directive, brain) -> EndReason:
    """Map a terminal close directive to its end reason."""
    if directive == Directive.EXIT_POLITE:
        return EndReason.BOOKED if brain.state.booking_engaged else EndReason.POLITE
    # EXIT_APOLOGETIC — a decline. A polite "not interested" still gets the warm
    # closing + thank-you; spam / wrong number does not (the model apologised and
    # a sales sign-off would be wrong).
    last = brain.state.intents[-1] if brain.state.intents else None
    return EndReason.REJECT if last in ("spam", "wrong_number") else EndReason.DECLINE


async def _end_call(session, brain, ctx, reason: EndReason, call_id, org_id,
                    seq, lang, final) -> None:
    """
    The SINGLE place a call is torn down. Speaks every sign-off stage configured
    for `reason` — in full, uninterruptible, variables substituted and localized
    — and only then hangs up. Nothing else may aclose the session.
    """
    if reason is EndReason.TRANSFER:
        agent_number = await _route_to_human(brain.campaign, org_id)
        if agent_number:
            final["value"] = "transferred"
            await _sip_transfer(ctx, agent_number)
            return   # handed to a human — the agent's involvement ends here
        reason = EndReason.CALLBACK        # nobody free -> degrade to a callback
        final["value"] = "callback"

    if reason is EndReason.OPT_OUT:
        # Remove the caller BEFORE we speak the confirmation — the promise we're
        # about to make ("you won't be contacted again") must already be true.
        # Awaited and durable; a failure is logged, never raised into the call.
        await _suppress_contact(org_id, getattr(brain, "contact_phone", ""))
        final["value"] = "do_not_call"      # matches the call_outcome enum

    for produce in _SIGN_OFF.get(reason, ()):
        line = await produce(brain)
        if not line:                       # stage left blank / empty render — skip
            continue
        seq["n"] += 1
        await save_turn(call_id, org_id, seq["n"], "agent", line, lang=lang)
        handle = await session.say(line, allow_interruptions=False)
        await handle.wait_for_playout()    # spoken IN FULL before the next line

    await session.aclose()


async def _run_until_done(session, brain, ctx, call_id, org_id, started,
                          final, seq, lang=None) -> None:
    """
    Watch for an end condition and hand off to _end_call() when one lands.

    NO directive ends the call here. Booking is an in-conversation step, never a
    terminal state; a close is a REQUEST to end that we confirm the customer
    means. When an end condition is genuine, it is mapped to an EndReason and
    _end_call() runs the full sign-off before the single hangup.
    """
    while True:
        await asyncio.sleep(_POLL_INTERVAL)
        directive = session.llm._pending_directive  # type: ignore[attr-defined]

        if directive == Directive.OPT_OUT:
            # COMPLIANCE — HARD INTERRUPT. Checked FIRST, ahead of every other
            # end condition, and deliberately WITHOUT the _customer_resumed
            # confirmation the ordinary closes use: a removal request is never
            # second-guessed, re-pitched, or waited out. Straight to _end_call,
            # which suppresses the number then speaks only the confirmation.
            reason = EndReason.OPT_OUT
        elif directive == Directive.TRANSFER_HUMAN:
            reason = EndReason.TRANSFER
        elif directive in TERMINAL_DIRECTIVES:
            # A close is a REQUEST to end, not an instant hangup. The model
            # sometimes tags a booking/scheduling line as a positive close while
            # the customer is still talking. Keep listening; if they reply with a
            # non-close turn the close was premature — resume. This is also what
            # lets the customer respond AFTER a booking before the sign-off runs.
            if await _customer_resumed(session, brain, ctx):
                continue
            reason = _end_reason_for_close(directive, brain)
        elif ctx.room.connection_state == rtc.ConnectionState.CONN_DISCONNECTED:
            reason = EndReason.DROPPED
        else:
            continue

        await _end_call(session, brain, ctx, reason, call_id, org_id, seq, lang, final)
        return


async def _customer_resumed(session, brain, ctx) -> bool:
    """
    After a terminal directive, wait briefly to see whether the customer keeps
    talking.

    Returns True if a fresh, non-terminal turn arrived (the close was premature —
    resume the call) and False if the customer is done, replied with another
    close, or the line dropped (proceed to hang up). This is what stops the agent
    going silent after it says it will schedule a meeting.
    """
    turns_at_close = brain.state.turn_count
    waited = 0.0
    while waited < _CLOSE_CONFIRM_WINDOW:
        await asyncio.sleep(_POLL_INTERVAL)
        waited += _POLL_INTERVAL
        if ctx.room.connection_state == rtc.ConnectionState.CONN_DISCONNECTED:
            return False
        if brain.state.turn_count > turns_at_close:
            # A new turn was processed after the closing line. Resume only if it
            # is not itself a close — a genuine decline still ends the call.
            return session.llm._pending_directive not in TERMINAL_DIRECTIVES
    return False


async def _route_to_human(campaign: dict, org_id: str) -> str | None:
    """Smart routing (call mode): first matching rule wins, by priority."""
    rules = await db.fetch(
        """SELECT destination FROM routing_rules
           WHERE org_id = $1 AND is_active
             AND (campaign_id = $2 OR campaign_id IS NULL)
           ORDER BY position LIMIT 5""",
        org_id, campaign.get("id"),
    )
    for r in rules:
        if number := (r["destination"] or {}).get("phone"):
            return number
    return await db.fetchval(
        """SELECT phone FROM users
           WHERE org_id = $1 AND is_active AND phone IS NOT NULL
             AND role IN ('sales_rep','manager','recruiter')
           LIMIT 1""",
        org_id,
    )


async def _sip_transfer(ctx: JobContext, number: str) -> None:
    """Warm handoff via SIP REFER."""
    lkapi = api.LiveKitAPI()
    try:
        participant = next(iter(ctx.room.remote_participants.values()), None)
        if not participant:
            return
        await lkapi.sip.transfer_sip_participant(
            api.TransferSIPParticipantRequest(
                room_name=ctx.room.name,
                participant_identity=participant.identity,
                transfer_to=f"tel:{number}",
                play_dialtone=True,
            )
        )
    except Exception:
        log.exception("SIP transfer to %s failed", number)
    finally:
        await lkapi.aclose()


def prewarm(proc: JobProcess) -> None:
    """
    Load the slow things ONCE per worker process, before any call is routed
    here — so the agent can speak the instant the callee picks up instead of
    loading a model on the first turn (the ~3s cold-start pause).

    Silero VAD is the heavy load. It is cached on the process and every call in
    this process reuses it. `min_silence_duration` is Silero's turn-end gap (its
    equivalent of "stop_secs"); 0.4s ends turns promptly without clipping the
    natural pauses in normal speech.
    """
    log.info("prewarm: loading Silero VAD + STT pool")
    proc.userdata["vad"] = silero.VAD.load(min_silence_duration=0.4)

    # One warm STT instance per provider, keyed by provider name. A call picks
    # the right one by its language (see stt_router). Deepgram Nova-3 with
    # language="multi" handles every Deepgram-routed language (en, hi) from a
    # single instance, so its config is call-independent and one shared, warm
    # object serves them all — built here at process start, not per call.
    #
    # NB: the Deepgram plugin's own .prewarm() is a no-op stub, so it can't force
    # the WebSocket open ahead of the call. Sharing the instance is what avoids a
    # per-call cold start (its connection pool is created once); the heavy load
    # (VAD, above) is off the call path entirely.
    stt_pool: dict[str, object] = {
        "deepgram": deepgram.STT(
            model="nova-3",
            language="multi",
            api_key=os.environ.get("DEEPGRAM_API_KEY"),
        ),
    }

    # Sarvam Saaras handles the Indic languages Deepgram mistranscribes (Tamil
    # et al). One instance per language — unlike Deepgram's "multi", a Sarvam STT
    # is bound to a single language. Only built if the key is present, so a
    # missing key degrades to "Tamil fails loud" rather than crashing prewarm.
    if sarvam_key := os.environ.get("SARVAM_API_KEY"):
        for lang in sarvam_languages():
            stt_pool[f"sarvam:{lang}"] = sarvam.STT(
                model="saaras:v3",
                language=SARVAM_LANGUAGE.get(lang, "ta-IN"),
                mode="transcribe",
                api_key=sarvam_key,
                high_vad_sensitivity=True,   # snappy turn/barge-in for a phone call
            )

    proc.userdata["stt_pool"] = stt_pool
    log.info("prewarm: VAD + STT pool ready (%s) — first turn won't block",
             ", ".join(stt_pool))


if __name__ == "__main__":
    agents.cli.run_app(
        agents.WorkerOptions(
            entrypoint_fnc=entrypoint,
            prewarm_fnc=prewarm,
            agent_name=AGENT_NAME,
        )
    )
