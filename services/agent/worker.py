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
from pathlib import Path

from dotenv import load_dotenv
from livekit import agents, api, rtc
from livekit.agents import Agent, AgentSession, JobContext, RoomInputOptions
from livekit.plugins import cartesia, silero

# db.py is shared with the API service — one definition of the pool and codecs.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "api"))
import db  # noqa: E402

import prompts
from brain import Brain
from ivr import IvrMenu, run_menu
from lk_llm import BrainLLM
from rules import Directive

load_dotenv()
logging.basicConfig(level=logging.INFO)
log = logging.getLogger("worker")

# Cartesia exposes emotion/speed; we map the model's per-turn choice onto it.
SPEED_MAP = {"slow": -0.3, "normal": 0.0, "fast": 0.3}


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

async def save_turn(call_id: str, org_id: str, seq: int, role: str, text: str,
                    result=None, stt_ms: int | None = None,
                    tts_ms: int | None = None) -> None:
    o = result.output if result else None
    await db.execute(
        """INSERT INTO turns (call_id, org_id, seq, role, text, intent, sentiment,
                              emotion, speed, pitch, action, stt_ms, llm_ms,
                              tts_ms, total_ms, cache_read_tokens)
           VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16)
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
    )


async def finish_call(call_id: str, outcome: str, answered_by: str,
                      started: float, transferred_to: str | None = None) -> None:
    dur = int(time.time() - started)
    await db.execute(
        """UPDATE calls
           SET status='completed', ended_at=now(), duration_sec=$2,
               outcome=$3::call_outcome, answered_by=$4::answered_by,
               transferred_to=$5
           WHERE id=$1""",
        call_id, dur, outcome, answered_by, transferred_to,
    )
    # Post-call work runs out of band so hangup is never delayed by it.
    await db.execute(
        "INSERT INTO jobs (kind, payload) VALUES ('post_call', $1)",
        {"call_id": call_id},
    )


# ── entrypoint ───────────────────────────────────────────────────────────────

async def entrypoint(ctx: JobContext) -> None:
    await db.init_pool()
    await ctx.connect()

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
    else:
        # Inbound: identify the caller from the SIP participant.
        participant = await ctx.wait_for_participant()
        phone = (participant.attributes or {}).get("sip.phoneNumber", "")
        org_id = meta.get("org_id") or await db.fetchval(
            "SELECT org_id FROM phone_numbers WHERE e164 = $1", meta.get("to_number", "")
        )
        number_row = await db.fetchrow(
            """SELECT p.ivr_menu, row_to_json(cam) AS campaign
               FROM phone_numbers p
               LEFT JOIN campaigns cam ON cam.id = p.inbound_campaign_id
               WHERE p.e164 = $1""",
            meta.get("to_number", ""),
        )
        campaign = (number_row or {}).get("campaign")
        ivr_menu = IvrMenu.from_json((number_row or {}).get("ivr_menu"))
        if not campaign:
            log.error("no inbound campaign bound to %s", meta.get("to_number"))
            return
        lead = await lead_by_phone(org_id, phone) or {}
        direction = "inbound"
        call_id = await db.fetchval(
            """INSERT INTO calls (org_id, campaign_id, lead_id, direction,
                                  room_name, from_number, status)
               VALUES ($1,$2,$3,'inbound',$4,$5,'connected') RETURNING id""",
            org_id, campaign["id"], lead.get("id"), ctx.room.name, phone,
        )
        campaign = dict(campaign)

    campaign = dict(campaign)
    campaign["org_name"] = campaign.get("org_name") or "our team"
    brain = Brain(campaign, dict(lead))

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
        await save_turn(call_id, org_id, seq["n"], "lead", heard)
        seq["n"] += 1
        await save_turn(call_id, org_id, seq["n"], "agent", result.output.reply,
                        result=result, stt_ms=timing["stt_ms"],
                        tts_ms=timing["tts_ms"])
        timing["stt_ms"] = timing["tts_ms"] = None
        final_outcome["answered_by"] = "human"
        final_outcome["value"] = _outcome_for(result)

    session = _build_session(campaign, brain, on_turn)

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

    await session.start(
        room=ctx.room,
        agent=Agent(instructions=brain.system),
        room_input_options=RoomInputOptions(close_on_disconnect=True),
    )

    if direction == "outbound":
        opening = brain.opening()
        # Record it before speaking. The opening carries the AI disclosure, so a
        # transcript without it is an incomplete compliance record. It also has
        # to enter the model's history — otherwise the first real turn starts
        # from an empty context and the agent introduces itself a second time.
        seq["n"] += 1
        await save_turn(call_id, org_id, seq["n"], "agent", opening)
        brain.note_spoken(opening)
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

    try:
        await _run_until_done(session, brain, ctx, call_id, org_id,
                              started, final_outcome)
    finally:
        await finish_call(call_id, final_outcome["value"],
                          final_outcome["answered_by"], started,
                          final_outcome["transferred_to"])
        await db.close_pool()


def _build_session(campaign: dict, brain: Brain, on_turn) -> AgentSession:
    cfg = campaign.get("voice_config") or {}
    settings = campaign.get("settings") or {}

    # STT and TTS both run on Cartesia. The original plan used ElevenLabs for
    # transcription, but that meant a second vendor, a second key, and a second
    # failure mode on the call path — and its key reads from a differently
    # named env var, which crashed session construction after pickup. One
    # provider for both halves of the audio path is simply less to break.
    #
    # Keys are passed explicitly rather than relying on each plugin's env
    # lookup, so a rename in .env can never silently break a live call.
    tts = cartesia.TTS(
        api_key=os.environ.get("CARTESIA_API_KEY"),
        model="sonic-3",
        voice=cfg.get("provider_voice_id") or cfg.get("voice_id") or "",
        speed=SPEED_MAP.get(cfg.get("speed", "normal"), 0.0),
        language=campaign.get("language", "en"),
    )

    brain_llm = BrainLLM(brain, on_turn=on_turn, tts=tts)

    session = AgentSession(
        stt=cartesia.STT(
            api_key=os.environ.get("CARTESIA_API_KEY"),
            model="ink-whisper",
            language=campaign.get("language", "en"),
        ),
        tts=tts,
        vad=silero.VAD.load(),
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
        ivr_detection=bool(settings.get("voicemail_detection", True)),
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


async def _run_until_done(session, brain, ctx, call_id, org_id, started,
                          final) -> None:
    """
    Watch for terminal directives and close the call when one lands.

    The session handles the conversation itself; this only decides when to stop
    and whether to transfer.
    """
    terminal = {Directive.EXIT_POLITE, Directive.EXIT_APOLOGETIC}

    while True:
        await asyncio.sleep(0.25)
        directive = session.llm._pending_directive  # type: ignore[attr-defined]

        if directive == Directive.TRANSFER_HUMAN:
            agent_number = await _route_to_human(brain.campaign, org_id)
            if agent_number:
                final["value"] = "transferred"
                await _sip_transfer(ctx, agent_number)
            else:
                # Nobody available — degrade to a callback rather than dead air.
                await session.say(
                    "My colleagues are all busy right now. Can I arrange a call back?"
                )
                final["value"] = "callback"
            break

        if directive in terminal:
            # Let the closing line finish playing before tearing down.
            await asyncio.sleep(2.0)
            break

        if ctx.room.connection_state == rtc.ConnectionState.CONN_DISCONNECTED:
            break

    await session.aclose()


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


if __name__ == "__main__":
    agents.cli.run_app(
        agents.WorkerOptions(
            entrypoint_fnc=entrypoint,
            agent_name="leadaro-voice",
        )
    )
