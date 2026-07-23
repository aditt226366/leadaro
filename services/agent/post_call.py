"""
Post-call worker — the SIX after-call features, all off the live turn loop.

    python services/agent/post_call.py

Drains the `jobs` table. Runs off the call path entirely (triggered by the
`post_call` job that finish_call() enqueues), so a slow analysis never delays
hangup and a failure never loses the call record.

Every feature reads the saved TRANSCRIPT (the turns table) as its input — text,
not audio, not the live session. The transcript is loaded ONCE and one Sonnet
4.6 pass produces:

  4  AI Sentiment Detection       → overall_sentiment + sentiment_trajectory
  5  AI Intent Recognition        → the caller's final intent(s)
  6  AI Call Summary              → summary + key points + pain points
  8  AI Lead Qualification        → HOT/WARM/SCRAP from transcript signals
  9  AI Next Best Action          → from the analyzed transcript
  7  AI Follow-up Recommendation  → from summary + sentiment + outcome
                                     (rule-driven suppression on rejection)

None of the six run inside the live turn loop — the live turn only replies,
handles an inline objection, and captures a booking (see brain.py / lk_llm.py).
"""
from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv
from pydantic import BaseModel, Field

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "api"))
import db  # noqa: E402
import llm as api_llm  # noqa: E402

from rules import (  # noqa: E402
    BUYING_INTENTS, ConversationState, qualify, should_follow_up,
)

load_dotenv()
logging.basicConfig(level=logging.INFO)
log = logging.getLogger("post_call")

POLL_SECONDS = 3
MAX_ATTEMPTS = 3

# Warmer leads get chased sooner. Keyed by the transcript-derived tier below.
FOLLOWUP_DELAY_DAYS = {"hot": 1, "warm": 2, "scrap": 5}

SUMMARY_SYSTEM = """You analyse completed sales call transcripts. Everything you \
return is derived from the transcript text and nothing else.

Work in this order:
  1. Read the whole transcript, then write the summary, key points and pain \
points, and the caller's overall sentiment (a number from -1.0 hostile to 1.0 \
enthusiastic) with a one-line trajectory of how it moved.
  2. Classify the caller's final intent(s) and qualify the lead as hot, warm or \
scrap FROM WHAT THEY SAID and asked for — not from how many turns it took. A \
short call where they ask to book is hot; a long call that goes nowhere is not.
  3. Only then, from that analysis plus the recorded outcome, write the \
follow-up recommendation and the single next best action.

Be strictly factual. Every field must be supported by something actually said \
on the call. If the caller never mentioned budget, leave budget empty — do not \
infer it from tone, and never invent a commitment they did not make. An \
optimistic summary that misrepresents the call is worse than a sparse one, \
because a rep will act on it."""


class Summary(BaseModel):
    """One structured pass over the transcript that carries all six features."""
    # AI Call Summary (feature 6) — read straight from the transcript.
    summary: str = Field(description="2-3 sentences on what happened.")
    key_points: list[str] = Field(default_factory=list, max_length=6)
    action_items: list[str] = Field(default_factory=list, max_length=6)
    pain_points: list[str] = Field(default_factory=list, max_length=6)
    next_steps: str = ""
    budget: str = ""
    timeline: str = ""
    # AI Sentiment Detection (feature 4) — from the transcript, not per-turn.
    overall_sentiment: float = Field(ge=-1.0, le=1.0, default=0.0)
    sentiment_trajectory: str = ""
    # AI Intent Recognition (feature 5) — the caller's final intent(s).
    intents: list[str] = Field(default_factory=list, max_length=6)
    # AI Lead Qualification (feature 8) — HOT/WARM/SCRAP from transcript signals.
    qualification_tier: Literal["hot", "warm", "scrap"] = "scrap"
    qualification_score: int = Field(ge=0, le=100, default=0)
    # AI Follow-up (feature 7) + Next Best Action (feature 9) — derived last.
    followup_recommendation: str = ""
    next_best_action: str = ""
    meeting_requested: bool = False
    meeting_time_hint: str = ""


def _resolve_tier(parsed: "Summary | None", state: ConversationState) -> str:
    """
    Feature 8 — lead tier from transcript signals (the model's read), floored by
    an explicit buying intent: asking to book is never scrap, however short the
    call. Falls back to engagement-depth tiering when the LLM pass didn't run.
    """
    if not parsed:
        return qualify(state)
    if any(i in BUYING_INTENTS for i in (parsed.intents or [])) or \
       any(i in BUYING_INTENTS for i in state.intents):
        return "hot"
    return parsed.qualification_tier


async def handle_post_call(payload: dict) -> None:
    call_id = payload["call_id"]

    call = await db.fetchrow(
        """SELECT c.*, cam.name AS campaign_name, cam.goal, cam.mode::text,
                  l.first_name, l.last_name, l.company, l.email
           FROM calls c
           LEFT JOIN campaigns cam ON cam.id = c.campaign_id
           LEFT JOIN leads l       ON l.id   = c.lead_id
           WHERE c.id = $1""",
        call_id,
    )
    if not call:
        log.warning("call %s vanished before post-processing", call_id)
        return

    turns = await db.fetch(
        "SELECT seq, role, text, intent, sentiment FROM turns WHERE call_id=$1 ORDER BY seq",
        call_id,
    )

    # Rebuild the rule state from what was persisted, so the fallback tiering and
    # follow-up suppression run off the same counters the live call used.
    #
    # Read the AGENT rows, not the lead rows. intent and sentiment are the
    # model's reading OF the caller's last utterance, written on the agent turn
    # that responds to it — the lead row stores only the raw transcript, both
    # columns NULL. Reading lead rows would score every replayed call sentiment
    # 0.0 / intent "neutral" and stop should_follow_up() ever seeing
    # "not_interested". The greeting is an agent turn with no intent, so filter
    # on intent rather than role alone.
    state = ConversationState()
    for t in turns:
        if t["role"] == "agent" and t["intent"]:
            state.record(t["sentiment"] or 0.0, t["intent"])

    if not turns:
        # Voicemail / no-answer: tier from engagement depth, skip the LLM, still
        # allow follow-up.
        tier = qualify(state)
        await _write_summary(call_id, None, tier, state)
        await _maybe_schedule_followup(call, state, tier)
        await _update_lead(call, tier)
        return

    # The transcript is the single source of truth for all six features. Loaded
    # once, analysed once — sentiment/intent/summary/qualification come from the
    # raw transcript; follow-up + next-best-action are derived from that analysis
    # in the same structured pass (see SUMMARY_SYSTEM ordering).
    transcript = "\n".join(
        f"{'AGENT' if t['role'] == 'agent' else 'CALLER'}: {t['text']}" for t in turns
    )
    try:
        parsed = await api_llm.complete(
            SUMMARY_SYSTEM,
            f"Campaign goal: {call['goal'] or 'n/a'}\n"
            f"Outcome recorded: {call['outcome'] or 'unknown'}\n"
            f"Duration: {call['duration_sec'] or 0}s over {len(turns)} turns\n\n"
            f"Transcript:\n{transcript}",
            max_tokens=1400,
            output_format=Summary,
        )
    except Exception:
        # A failed analysis must not lose the tiering or the follow-up.
        log.exception("transcript analysis failed for %s", call_id)
        parsed = None

    tier = _resolve_tier(parsed, state)
    await _write_summary(call_id, parsed, tier, state)
    await _maybe_schedule_followup(call, state, tier, parsed)
    await _update_lead(call, tier)

    if parsed and parsed.meeting_requested:
        await db.execute(
            "INSERT INTO jobs (kind, payload) VALUES ('book_meeting', $1)",
            {"call_id": str(call_id), "hint": parsed.meeting_time_hint},
        )

    await _run_automations(call, tier)


async def _write_summary(call_id, parsed: Summary | None, tier: str,
                         state: ConversationState) -> None:
    # Sentiment is the transcript-derived reading when we have it; otherwise the
    # average of the per-turn live scores (voicemail / analysis-failed paths).
    if parsed:
        sentiment_avg = parsed.overall_sentiment
        trajectory = parsed.sentiment_trajectory
        intents = parsed.intents
        next_best = parsed.next_best_action
    else:
        sentiment_avg = (sum(state.sentiments) / len(state.sentiments)) if state.sentiments else None
        trajectory, intents, next_best = "", [], ""
    await db.execute(
        """INSERT INTO call_summaries (call_id, summary, key_points, action_items,
               next_steps, pain_points, budget, timeline, sentiment_avg,
               lead_tier, qualification_score, followup_recommendation,
               intents, next_best_action, sentiment_trajectory)
           VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15)
           ON CONFLICT (call_id) DO UPDATE SET
             summary=EXCLUDED.summary, key_points=EXCLUDED.key_points,
             action_items=EXCLUDED.action_items, next_steps=EXCLUDED.next_steps,
             pain_points=EXCLUDED.pain_points, budget=EXCLUDED.budget,
             timeline=EXCLUDED.timeline, sentiment_avg=EXCLUDED.sentiment_avg,
             lead_tier=EXCLUDED.lead_tier,
             qualification_score=EXCLUDED.qualification_score,
             followup_recommendation=EXCLUDED.followup_recommendation,
             intents=EXCLUDED.intents,
             next_best_action=EXCLUDED.next_best_action,
             sentiment_trajectory=EXCLUDED.sentiment_trajectory""",
        call_id,
        parsed.summary if parsed else "No conversation took place.",
        parsed.key_points if parsed else [],
        parsed.action_items if parsed else [],
        parsed.next_steps if parsed else "",
        parsed.pain_points if parsed else [],
        parsed.budget if parsed else "",
        parsed.timeline if parsed else "",
        sentiment_avg,
        tier,
        parsed.qualification_score if parsed else 0,
        parsed.followup_recommendation if parsed else "",
        intents,
        next_best,
        trajectory,
    )


async def _maybe_schedule_followup(call, state: ConversationState, tier: str,
                                   parsed: Summary | None = None) -> None:
    """Feature 7. The suppression check is the important half."""
    if not call.get("lead_id"):
        return
    if not should_follow_up(state):
        log.info("follow-up suppressed for call %s (explicit rejection)", call["id"])
        return

    # Cadence follows the transcript-derived tier, not raw turn count.
    days = FOLLOWUP_DELAY_DAYS.get(tier, 5)
    await db.execute(
        """INSERT INTO followups (org_id, lead_id, call_id, channel, due_at,
                                  payload, reason)
           VALUES ($1,$2,$3,$4, now() + ($5 || ' days')::interval, $6, $7)""",
        call["org_id"], call["lead_id"], call["id"],
        "email" if call.get("email") else "call",
        str(days),
        {"tier": tier,
         "recommendation": parsed.followup_recommendation if parsed else ""},
        f"{tier} lead, {state.turn_count} turns",
    )


async def _update_lead(call, tier: str) -> None:
    if not call.get("lead_id"):
        return
    await db.execute(
        "UPDATE leads SET tier=$2::lead_tier, last_contacted_at=now() WHERE id=$1",
        call["lead_id"], tier,
    )


async def _run_automations(call, tier: str) -> None:
    """Fire automation rules bound to this outcome (FRD §12)."""
    rules = await db.fetch(
        """SELECT actions FROM automation_rules
           WHERE org_id = $1 AND is_active
             AND (campaign_id = $2 OR campaign_id IS NULL)
             AND trigger = $3""",
        call["org_id"], call["campaign_id"], f"outcome:{call['outcome']}",
    )
    for rule in rules:
        for action in rule["actions"] or []:
            await db.execute(
                "INSERT INTO jobs (kind, payload) VALUES ($1, $2)",
                f"action_{action.get('type', 'noop')}",
                {"call_id": str(call["id"]), "lead_id": str(call["lead_id"]),
                 "config": action, "tier": tier},
            )


# ── queue loop ───────────────────────────────────────────────────────────────

HANDLERS = {"post_call": handle_post_call}


async def drain_once() -> int:
    """
    Claim and run one batch. SKIP LOCKED lets several workers share the queue
    without double-processing a job.
    """
    jobs = await db.fetch(
        """UPDATE jobs SET status='running', locked_at=now(),
                           attempts = attempts + 1
           WHERE id IN (
             SELECT id FROM jobs
             WHERE status='pending' AND run_at <= now()
             ORDER BY run_at
             FOR UPDATE SKIP LOCKED
             LIMIT 10
           )
           RETURNING id, kind, payload, attempts"""
    )

    for job in jobs:
        handler = HANDLERS.get(job["kind"])
        if handler is None:
            await db.execute(
                "UPDATE jobs SET status='done', last_error='no handler' WHERE id=$1",
                job["id"],
            )
            continue
        try:
            await handler(job["payload"])
            await db.execute("UPDATE jobs SET status='done' WHERE id=$1", job["id"])
        except Exception as e:
            log.exception("job %s (%s) failed", job["id"], job["kind"])
            failed = job["attempts"] >= MAX_ATTEMPTS
            await db.execute(
                """UPDATE jobs
                   SET status = $2::job_status, last_error = $3,
                       run_at = now() + ($4 || ' seconds')::interval
                   WHERE id = $1""",
                job["id"],
                "failed" if failed else "pending",
                str(e)[:500],
                str(60 * job["attempts"]),   # linear backoff
            )
    return len(jobs)


async def main() -> None:
    await db.init_pool()
    log.info("post-call worker started")
    try:
        while True:
            try:
                if n := await drain_once():
                    log.info("processed %d job(s)", n)
            except Exception:
                log.exception("drain failed; continuing")
            await asyncio.sleep(POLL_SECONDS)
    finally:
        await db.close_pool()


if __name__ == "__main__":
    asyncio.run(main())
