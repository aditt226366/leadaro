"""
The one runnable check for the conversation logic.

    python services/agent/test_rules.py

No pytest, no fixtures — asserts and a __main__. Every row in the FRD threshold
table has a case here, plus the precedence ordering between them.
"""
from rules import (
    ConversationState, Directive, decide, followup_delay_days, qualify,
    should_follow_up,
)


def state(sentiments=(), intents=(), silence=0, unclear=0) -> ConversationState:
    s = ConversationState()
    for i, sent in enumerate(sentiments):
        s.record(sent, intents[i] if i < len(intents) else "neutral")
    s.silence_strikes = silence
    s.unclear_strikes = unclear
    return s


def test_positive_streak_pushes_for_meeting():
    # FRD: positive 8+ turns → trigger next best action → book meeting now
    s = state([0.7] * 8)
    assert s.positive_turns == 8
    assert decide(s, "interested", "continue") is Directive.PUSH_FOR_MEETING
    # 7 is not yet enough
    assert decide(state([0.7] * 7), "interested", "continue") is Directive.CONTINUE


def test_neutral_flatline_shortens_pitch():
    # FRD: neutral flatline 5+ turns → caller disengaged → go straight to the ask
    s = state([0.05] * 5)
    assert s.neutral_turns == 5
    assert decide(s, "neutral", "continue") is Directive.SHORTEN_AND_ASK
    assert decide(state([0.05] * 4), "neutral", "continue") is Directive.CONTINUE


def test_negative_streak_exits():
    # FRD: negative 3+ turns → stop pitch → offer graceful exit
    s = state([-0.6] * 3)
    assert s.negative_turns == 3
    assert decide(s, "objection", "continue") is Directive.EXIT_POLITE
    assert decide(state([-0.6] * 2), "objection", "continue") is Directive.CONTINUE


def test_silence_then_unclear_strikes():
    # FRD flow: silence ×2 → close;  unclear audio ×2 → offer callback
    assert decide(state(silence=2), "neutral", "continue") is Directive.EXIT_POLITE
    assert decide(state(silence=1), "neutral", "continue") is Directive.CONTINUE
    assert decide(state(unclear=2), "neutral", "continue") is Directive.OFFER_CALLBACK
    assert decide(state(unclear=1), "neutral", "continue") is Directive.CONTINUE


def test_exit_intents_take_precedence_over_everything():
    # A warm caller who then says "not interested" must still exit, not be pushed.
    hot = state([0.9] * 9)
    assert decide(hot, "not_interested", "book_meeting") is Directive.EXIT_APOLOGETIC
    assert decide(hot, "wrong_number", "book_meeting") is Directive.EXIT_APOLOGETIC
    assert decide(hot, "spam", "continue") is Directive.EXIT_APOLOGETIC


def test_transfer_intents_beat_sentiment_rules():
    # "Speak to a human" must win even mid negative streak.
    angry = state([-0.7] * 3)
    assert decide(angry, "speak_to_human", "continue") is Directive.TRANSFER_HUMAN
    assert decide(state(), "complaint", "continue") is Directive.TRANSFER_HUMAN
    assert decide(state(), "book_demo", "continue") is Directive.TRANSFER_HUMAN


def test_deep_dive_intents():
    # FRD feature 9: pricing / product questions → explain in detail
    assert decide(state(), "price_inquiry", "continue") is Directive.EXPLAIN_DETAIL
    assert decide(state(), "more_info", "continue") is Directive.EXPLAIN_DETAIL


def test_model_action_used_only_when_no_rule_fires():
    quiet = state([0.1, 0.15])   # 2 neutral turns — below every threshold
    assert decide(quiet, "neutral", "handle_objection") is Directive.HANDLE_OBJECTION
    assert decide(quiet, "neutral", "book_meeting") is Directive.BOOK_MEETING
    assert decide(quiet, "neutral", "garbage_value") is Directive.CONTINUE


def test_lead_tiering():
    # FRD feature 8: 10+ hot, 5–9 warm, 1–4 scrap. Intents kept neutral here so
    # the turn-count baseline is what is under test.
    assert qualify(state([0.5] * 10)) == "hot"
    assert qualify(state([0.5] * 14)) == "hot"
    assert qualify(state([0.5] * 9)) == "warm"
    assert qualify(state([0.5] * 5)) == "warm"
    assert qualify(state([0.5] * 4)) == "scrap"
    assert qualify(state([0.5])) == "scrap"
    assert qualify(state()) == "scrap"


def test_buying_intent_outranks_a_short_call():
    """
    Regression from a live call: the caller asked "when can I book a demo" on
    turn four, and pure turn-count tiering filed them as scrap with a five-day
    follow-up. Asking to book is the strongest signal there is; a brief call is
    not a cold one.
    """
    short_but_buying = state([0.7, 0.3, 0.6, 0.7],
                             ["interested", "more_info", "interested", "book_demo"])
    assert short_but_buying.turn_count == 4        # scrap by turn count alone
    assert qualify(short_but_buying) == "hot"
    assert followup_delay_days(short_but_buying) == 1   # chased tomorrow, not in 5 days

    assert qualify(state([0.6], ["book_meeting"])) == "hot"


def test_soft_interest_lifts_a_short_call_to_warm_not_hot():
    assert qualify(state([0.4, 0.3], ["interested", "price_inquiry"])) == "warm"
    assert qualify(state([0.2], ["more_info"])) == "warm"


def test_rejection_still_tiers_down_however_it_is_phrased():
    """An intent floor must never rescue someone who said no."""
    assert qualify(state([-0.5, -0.6], ["not_interested", "not_interested"])) == "scrap"
    assert qualify(state([0.0], ["wrong_number"])) == "scrap"
    assert qualify(state([0.0], ["spam"])) == "scrap"


def test_followup_suppression():
    # Scrap lead that simply didn't engage → still worth a follow-up.
    assert should_follow_up(state([0.1] * 3, ["neutral"] * 3)) is True
    # Explicit rejection → no follow-up, whatever the tier.
    assert should_follow_up(state([0.1] * 3, ["neutral", "not_interested", "neutral"])) is False
    assert should_follow_up(state([0.1] * 2, ["wrong_number", "neutral"])) is False
    assert should_follow_up(state([0.1] * 2, ["spam", "neutral"])) is False
    # Even a hot lead who said "not interested" late is suppressed.
    assert should_follow_up(state([0.9] * 12, ["interested"] * 11 + ["not_interested"])) is False


def test_followup_delay_scales_with_tier():
    assert followup_delay_days(state([0.9] * 10)) == 1   # hot
    assert followup_delay_days(state([0.5] * 6)) == 2    # warm — FRD's 2-day default
    assert followup_delay_days(state([0.5] * 2)) == 5    # scrap


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print(f"  ok  {t.__name__}")
    print(f"\n{len(tests)} passed")
