"""
    python services/agent/test_inbound.py

Guards the two inbound failures we fixed:

  1. "Picked up then cut with nothing" — the worker used to `return` on an
     unbound DID (after answering the SIP leg), so the caller heard dead air.
     Now it serves a safe default campaign and greets.
  2. "Didn't pick up at all" — the SIP dispatch rule routes to a worker by
     agent name; if that name drifts from the worker's registration, inbound
     calls ring with nobody to answer. We assert the names stay in lockstep.

These run without a live LiveKit session or DB: they exercise the pure
session-build decision (default campaign, greeting, the no-early-hangup rule)
and the dispatch-name invariant.
"""
import asyncio
import pathlib
import sys

# infra/ is a sibling of services/, not on the path when running from here.
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "infra"))

from brain import Brain
from rules import (
    MIN_TURNS_BEFORE_MODEL_CLOSE, ConversationState, TERMINAL_DIRECTIVES, decide,
)
from worker import DEFAULT_INBOUND_LANGUAGE, _default_inbound_campaign


# ── 1. "picked up then cut": unbound DID must still produce a usable agent ────

def test_unbound_did_yields_a_usable_default_campaign():
    cam = _default_inbound_campaign()
    # A real language so STT/TTS/LLM don't fall back blindly.
    assert cam.get("language") == DEFAULT_INBOUND_LANGUAGE
    # No real campaign -> campaign_id NULL on the call row, never a KeyError.
    assert cam.get("id") is None
    # The Brain builds a non-empty system prompt from the default alone; this is
    # the object the session is handed, so "it builds" == "no join-and-cut".
    brain = Brain(cam, {})
    assert brain.system.strip()


def test_inbound_greeting_is_spoken_and_carries_the_ai_disclosure():
    # English default -> no translation round trip, so this is offline.
    brain = Brain(_default_inbound_campaign(), {})
    greeting = asyncio.run(brain.inbound_greeting_localized())
    assert greeting.strip(), "inbound greeting must never be empty (no dead air)"
    # Disclosure is legally load-bearing and must survive into the greeting.
    assert "assistant" in greeting.lower()


def test_call_stays_alive_through_the_first_two_caller_turns():
    """
    The model must not be able to hang up in the opening exchange. Two caller
    turns where the model tries to close -> the call keeps going (guarded by
    MIN_TURNS_BEFORE_MODEL_CLOSE). This is the "processes 2 turns, stays alive"
    behaviour the inbound flow needs.
    """
    assert MIN_TURNS_BEFORE_MODEL_CLOSE >= 3
    state = ConversationState()
    for _ in range(2):
        state.record(0.1, "neutral")            # engaged-ish caller turn
        directive = decide(state, "neutral", "close_positive")  # model tries to close
        assert directive not in TERMINAL_DIRECTIVES, "closed too early — caller cut off"
    assert state.turn_count == 2


# ── 2. "didn't pick up at all": dispatch name must reach a registered worker ──

def test_agent_name_is_consistent_across_worker_dialer_and_dispatch_rule():
    import dialer
    import setup_sip
    import worker
    # The dispatch rule (setup_sip) hands the call to a worker registered under
    # worker.AGENT_NAME; the dialer dispatches outbound the same way. A mismatch
    # is exactly the "call rings, no agent joins" failure.
    assert worker.AGENT_NAME == dialer.AGENT_NAME == setup_sip.AGENT_NAME


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print(f"  ok  {t.__name__}")
    print(f"\n{len(tests)} passed")
