"""
Deterministic conversation rules from the FRD.

The model classifies each turn; this module applies the thresholds. Keeping
them out of the prompt makes them cheap (no tokens), consistent (same input →
same decision every time), and testable without an API key. test_rules.py
covers every row below.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

# ── thresholds (FRD §4, §8 and the flow spec) ────────────────────────────────

POSITIVE_SENTIMENT = 0.3       # above this a turn counts as positive
NEGATIVE_SENTIMENT = -0.3      # below this a turn counts as negative
NEUTRAL_BAND = 0.2             # |sentiment| under this is "flat"

POSITIVE_TURNS_TO_CLOSE = 8    # 8+ positive turns → go for the meeting now
NEUTRAL_TURNS_TO_SHORTEN = 5   # 5+ flat turns → caller disengaged, cut to the ask
NEGATIVE_TURNS_TO_SOFTEN = 3   # 3+ negative turns → de-escalate (NOT exit)
# The model may not end the call before this many turns — a "close" in the
# opening exchange is a misfire that cuts the caller off mid-question.
MIN_TURNS_BEFORE_MODEL_CLOSE = 3

HOT_LEAD_TURNS = 10            # 10+ turns → hot
WARM_LEAD_TURNS = 5            # 5–9 turns → warm; 1–4 → scrap

MAX_SILENCE_STRIKES = 2        # 2 silent turns → close the call
MAX_UNCLEAR_STRIKES = 2        # 2 unintelligible turns → offer a callback

# Intents that suppress any follow-up, however the call went (FRD feature 8).
NO_FOLLOWUP_INTENTS = frozenset({"not_interested", "wrong_number", "spam"})

# Intents that floor the tier regardless of how many turns the call took.
#
# The FRD tiers purely on turn count (10+/5-9/1-4). Taken literally that files a
# caller who says "when can I book a demo" in four turns as scrap, and chases
# them in five days instead of one. Observed on a live call: a lead asked to
# book a demo, scored 62, and was written to the database as scrap.
#
# A short call is not a cold one. Efficiency is not disinterest, and asking to
# book is the strongest buying signal there is.
BUYING_INTENTS = frozenset({"book_meeting", "book_demo"})
WARM_INTENTS = frozenset({"interested", "price_inquiry", "more_info", "call_later"})

# Intents that hand off to a human immediately (FRD feature 5 / 9).
#
# book_demo is NOT here: it is a BUYING signal (see BUYING_INTENTS above), an
# in-conversation booking step — not a transfer. Routing it to a human made a
# booking terminate the call via the transfer path before the script's closing
# and thank-you could play. The agent books the demo itself; only an explicit
# "speak to a human" / support / complaint hands off.
TRANSFER_INTENTS = frozenset({"speak_to_human", "support", "complaint"})

# Intents that end the call politely with an apology (FRD feature 5).
EXIT_INTENTS = frozenset({"not_interested", "spam", "wrong_number"})

# COMPLIANCE — the caller asked to be removed / not called again ("stop calling",
# "take me off your list", "do not call me", in ANY language). This is NOT a soft
# "not interested": it is a legal opt-out that must HARD-INTERRUPT the call, be
# recorded to the DNC suppression list, and end with a bare confirmation — no
# closing, no thank-you, no sales sign-off. It outranks every other rule below,
# including booking and objection handling, so it is checked FIRST in decide().
OPT_OUT_INTENTS = frozenset({"do_not_call", "opt_out"})

# Intents that mean "explain in depth and mark as hot" (FRD feature 9).
DEEP_DIVE_INTENTS = frozenset({"price_inquiry", "more_info"})


class Directive(StrEnum):
    """What the runtime should do after this turn."""
    CONTINUE = "continue"
    SHORTEN_AND_ASK = "shorten_and_ask"
    PUSH_FOR_MEETING = "push_for_meeting"
    HANDLE_OBJECTION = "handle_objection"
    EXPLAIN_DETAIL = "explain_detail"
    BOOK_MEETING = "book_meeting"
    TRANSFER_HUMAN = "transfer_human"
    OFFER_CALLBACK = "offer_callback"
    EXIT_POLITE = "exit_polite"
    EXIT_APOLOGETIC = "exit_apologetic"
    OPT_OUT = "opt_out"          # compliance removal — hard interrupt, DNC + bare bye


# The directives that actually hang up the call. The worker watches for these
# to tear the session down; decide() guards them so the model can't trigger one
# in the opening turns.
#
# OPT_OUT is terminal too but is DELIBERATELY not in this set: these go through
# the "is the customer still talking?" resume-confirmation path, whereas an
# opt-out is a HARD INTERRUPT that must never be second-guessed or resumed. The
# worker handles OPT_OUT on its own branch, ahead of these. (This also means an
# opt-out spoken DURING a close-confirmation window is treated as a fresh,
# non-terminal turn there and re-evaluated, so it still ends via the opt-out
# path — with a bare confirmation — rather than the sales sign-off.)
TERMINAL_DIRECTIVES = frozenset({Directive.EXIT_POLITE, Directive.EXIT_APOLOGETIC})


@dataclass
class ConversationState:
    """Rolling counters for one call. Cheap to keep in memory per session."""
    sentiments: list[float] = field(default_factory=list)
    intents: list[str] = field(default_factory=list)
    silence_strikes: int = 0
    unclear_strikes: int = 0
    # True once the agent has moved to book a meeting. Drives the dedicated
    # closing message so a booked call ends warmly, not with an abrupt cut.
    booking_engaged: bool = False

    # ── counters ─────────────────────────────────────────────────────────────

    @property
    def turn_count(self) -> int:
        return len(self.sentiments)

    @property
    def positive_turns(self) -> int:
        return sum(1 for s in self.sentiments if s > POSITIVE_SENTIMENT)

    @property
    def negative_turns(self) -> int:
        return sum(1 for s in self.sentiments if s < NEGATIVE_SENTIMENT)

    @property
    def neutral_turns(self) -> int:
        return sum(1 for s in self.sentiments if abs(s) < NEUTRAL_BAND)

    def record(self, sentiment: float, intent: str) -> None:
        self.sentiments.append(sentiment)
        self.intents.append(intent)

    def record_silence(self) -> None:
        self.silence_strikes += 1

    def record_unclear(self) -> None:
        self.unclear_strikes += 1


def decide(state: ConversationState, intent: str, model_action: str) -> Directive:
    """
    Resolve the next move. Ordered by precedence: things that must end or
    redirect the call outrank anything the model suggested.

    `model_action` is the LLM's own next_action for this turn — used only when
    no deterministic rule fires, so the model can steer within the guardrails
    rather than around them.
    """
    # 0. COMPLIANCE — "remove me / stop calling / do not call again". Outranks
    #    EVERYTHING, including booking and objection handling: a legal opt-out is
    #    not negotiable and is never worth a spurious upsell. The worker turns
    #    this into an immediate DNC write + a bare confirmation, then hangs up.
    if intent in OPT_OUT_INTENTS:
        return Directive.OPT_OUT

    # 1. Hard exits — caller said no, wrong number, or flagged us as spam.
    if intent in EXIT_INTENTS:
        return Directive.EXIT_APOLOGETIC

    # 2. Explicit escalation to a human.
    if intent in TRANSFER_INTENTS:
        return Directive.TRANSFER_HUMAN

    # 3. Non-responsive caller. Silence closes; garbled audio offers a callback.
    #    These are the ONLY threshold-driven ends allowed — two strikes each.
    if state.silence_strikes >= MAX_SILENCE_STRIKES:
        return Directive.EXIT_POLITE
    if state.unclear_strikes >= MAX_UNCLEAR_STRIKES:
        return Directive.OFFER_CALLBACK

    # 4. Sustained negativity does NOT end the call. Auto-hanging-up on a few
    #    negative-scored turns was cutting callers off mid-conversation. A call
    #    ends on an explicit decline (rule 1), silence/unclear (rule 3), or the
    #    caller hanging up — never because sentiment dipped. Redirect instead:
    #    address the concern once and let the caller decide.
    if state.negative_turns >= NEGATIVE_TURNS_TO_SOFTEN:
        return Directive.HANDLE_OBJECTION

    # 5. Sustained warmth — stop selling and ask for the meeting.
    if state.positive_turns >= POSITIVE_TURNS_TO_CLOSE:
        return Directive.PUSH_FOR_MEETING

    # 6. Flatlined — they are not engaging. Compress and get to the ask.
    if state.neutral_turns >= NEUTRAL_TURNS_TO_SHORTEN:
        return Directive.SHORTEN_AND_ASK

    # 7. Wants depth on price or product.
    if intent in DEEP_DIVE_INTENTS:
        return Directive.EXPLAIN_DETAIL

    # 8. Nothing deterministic fired — follow the model, with one guard: the
    #    model may not END the call in the opening turns. A "close" on turn one
    #    is a misfire, and cutting off a caller who just asked a question is
    #    exactly the reported bug. Genuine end conditions (decline intent,
    #    silence, unclear) are handled above and are unaffected by this guard.
    mapped = {
        "book_meeting": Directive.BOOK_MEETING,
        "handle_objection": Directive.HANDLE_OBJECTION,
        "transfer_human": Directive.TRANSFER_HUMAN,
        "schedule_callback": Directive.OFFER_CALLBACK,
        "close_positive": Directive.EXIT_POLITE,
        "close_negative": Directive.EXIT_POLITE,
        "explain_detail": Directive.EXPLAIN_DETAIL,
    }.get(model_action, Directive.CONTINUE)
    if mapped in TERMINAL_DIRECTIVES and state.turn_count < MIN_TURNS_BEFORE_MODEL_CLOSE:
        return Directive.CONTINUE
    return mapped


def qualify(state: ConversationState) -> str:
    """
    Feature 8 — lead tier. Engagement depth, floored by stated intent.

    Turn count is the FRD's measure and stays the baseline, but it is a proxy
    for interest, not interest itself. What the caller actually asked for
    outranks how long they took to ask it, so an explicit buying signal cannot
    be tiered down to scrap by a short call.
    """
    n = state.turn_count
    if n >= HOT_LEAD_TURNS:
        by_turns = "hot"
    elif n >= WARM_LEAD_TURNS:
        by_turns = "warm"
    else:
        by_turns = "scrap"

    # A caller who asked to book is never scrap, however brief the call.
    if any(i in BUYING_INTENTS for i in state.intents):
        return "hot"
    if by_turns == "scrap" and any(i in WARM_INTENTS for i in state.intents):
        return "warm"
    return by_turns


def should_follow_up(state: ConversationState) -> bool:
    """
    Feature 7 — schedule a follow-up unless the caller told us not to.

    A scrap lead still gets a follow-up if they simply didn't engage; it is the
    explicit rejection intents that suppress it. Following up on someone who
    said "not interested" is the fastest way to a complaint.
    """
    return not any(i in NO_FOLLOWUP_INTENTS for i in state.intents)


def followup_delay_days(state: ConversationState) -> int:
    """Warmer leads get chased sooner."""
    tier = qualify(state)
    return {"hot": 1, "warm": 2, "scrap": 5}[tier]
