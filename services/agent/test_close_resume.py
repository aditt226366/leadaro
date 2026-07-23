"""
    python services/agent/test_close_resume.py

Regression for the bug where the agent said "I'll schedule a meeting" and went
silent: a model close on a scheduling turn must NOT hang up while the customer is
still talking. The loop keeps listening and resumes; it ends only once the
customer is genuinely done.
"""
import asyncio

from livekit import rtc

import worker
from rules import Directive


class _FakeLLM:
    def __init__(self, directive):
        self._pending_directive = directive


class _FakeState:
    def __init__(self, turn_count=6, booking_engaged=False, intents=None):
        self.turn_count = turn_count
        self.booking_engaged = booking_engaged
        self.intents = intents or []


class _FakeHandle:
    def __init__(self):
        self.played = False

    async def wait_for_playout(self):
        self.played = True


class _FakeBrain:
    def __init__(self, state, ending="Thanks, have a great day!",
                 closing="", thank_you="",
                 opt_out="Understood, I'll remove you from our list. "
                         "You won't be contacted again.",
                 contact_phone=""):
        self.state = state
        self.campaign = {}
        self._ending = ending
        self._closing = closing
        self._thank_you = thank_you
        self._opt_out = opt_out
        self.contact_phone = contact_phone
        self.ending_spoken = None

    async def ending_message_localized(self):
        return self._ending

    async def closing_statement_localized(self):
        return self._closing

    async def thank_you_localized(self):
        return self._thank_you

    async def callback_offer_localized(self):
        return "My colleagues are all busy right now. Can I arrange a call back?"

    async def opt_out_confirmation_localized(self):
        return self._opt_out


class _FakeRoom:
    def __init__(self):
        self.connection_state = "connected"      # never == CONN_DISCONNECTED


class _FakeCtx:
    def __init__(self, room):
        self.room = room


class _FakeSession:
    def __init__(self, llm, state):
        self.llm = llm
        self._state = state
        self.closed_at = None                    # turn_count when aclose ran
        self.said = []                           # everything spoken via say()
        self.handle = _FakeHandle()

    async def aclose(self):
        self.closed_at = self._state.turn_count

    async def say(self, text, **k):
        self.said.append(text)
        return self.handle


def _fast_timing():
    worker._POLL_INTERVAL = 0.02
    worker._CLOSE_CONFIRM_WINDOW = 0.5


def test_resume_when_customer_replies_after_close():
    async def run():
        _fast_timing()
        state = _FakeState(6)
        llm = _FakeLLM(Directive.EXIT_POLITE)
        brain, ctx = _FakeBrain(state), _FakeCtx(_FakeRoom())
        session = _FakeSession(llm, state)

        async def driver():
            await asyncio.sleep(0.1)             # customer keeps talking
            state.turn_count = 7
            llm._pending_directive = Directive.CONTINUE

        asyncio.create_task(driver())
        return await worker._customer_resumed(session, brain, ctx)

    assert asyncio.run(run()) is True


def test_no_resume_when_customer_is_silent():
    async def run():
        _fast_timing()
        worker._CLOSE_CONFIRM_WINDOW = 0.15      # short — nobody speaks
        state = _FakeState(6)
        session = _FakeSession(_FakeLLM(Directive.EXIT_POLITE), state)
        return await worker._customer_resumed(session, _FakeBrain(state), _FakeCtx(_FakeRoom()))

    assert asyncio.run(run()) is False


def test_no_resume_when_reply_is_also_a_decline():
    async def run():
        _fast_timing()
        state = _FakeState(6)
        llm = _FakeLLM(Directive.EXIT_POLITE)
        session = _FakeSession(llm, state)

        async def driver():
            await asyncio.sleep(0.1)
            state.turn_count = 7                  # they replied...
            llm._pending_directive = Directive.EXIT_APOLOGETIC   # ...but declined

        asyncio.create_task(driver())
        return await worker._customer_resumed(session, _FakeBrain(state), _FakeCtx(_FakeRoom()))

    assert asyncio.run(run()) is False


def test_no_resume_when_line_drops():
    async def run():
        _fast_timing()
        state = _FakeState(6)
        room = _FakeRoom()
        session = _FakeSession(_FakeLLM(Directive.EXIT_POLITE), state)

        async def driver():
            await asyncio.sleep(0.1)
            room.connection_state = rtc.ConnectionState.CONN_DISCONNECTED

        asyncio.create_task(driver())
        return await worker._customer_resumed(session, _FakeBrain(state), _FakeCtx(room))

    assert asyncio.run(run()) is False


def test_scheduling_close_does_not_end_call_until_customer_is_done():
    """
    The reported scenario end to end: agent says it will schedule a meeting
    (model close), the customer sends TWO more replies, the agent stays live for
    both, and the call ends ONLY after the customer finally stops — never at the
    scheduling turn.
    """
    async def run():
        _fast_timing()
        worker._CLOSE_CONFIRM_WINDOW = 0.3
        state = _FakeState(6)                     # agent's scheduling turn
        llm = _FakeLLM(Directive.EXIT_POLITE)     # ...tagged a positive close
        brain, ctx = _FakeBrain(state), _FakeCtx(_FakeRoom())
        session = _FakeSession(llm, state)

        async def driver():
            await asyncio.sleep(0.1)              # reply 1: "actually, Friday?"
            state.turn_count = 7
            llm._pending_directive = Directive.CONTINUE
            await asyncio.sleep(0.1)              # reply 2: a question
            state.turn_count = 8
            llm._pending_directive = Directive.CONTINUE
            await asyncio.sleep(0.1)              # customer done; model closes again
            llm._pending_directive = Directive.EXIT_POLITE

        asyncio.create_task(driver())
        await worker._run_until_done(
            session, brain, ctx, "cid", "org", 0.0,
            {"value": "x", "answered_by": "human", "transferred_to": None},
            {"n": 8},
        )
        return session.closed_at

    # Ended only after both replies were handled (turn 8) — never at the
    # scheduling turn (6). That is the bug not reproducing.
    assert asyncio.run(run()) == 8


async def _noop_save(*a, **k):
    pass


def _with_noop_save(coro_factory):
    """Run an async test body with worker.save_turn stubbed (no DB needed)."""
    orig = worker.save_turn
    worker.save_turn = _noop_save
    try:
        return asyncio.run(coro_factory())
    finally:
        worker.save_turn = orig


def test_ending_message_is_spoken_fully_before_a_booked_call_ends():
    """After a booking, the closing message plays to completion before hangup."""
    async def run():
        _fast_timing()
        worker._CLOSE_CONFIRM_WINDOW = 0.1
        state = _FakeState(6, booking_engaged=True)
        session = _FakeSession(_FakeLLM(Directive.EXIT_POLITE), state)
        brain = _FakeBrain(state, ending="Thank you, our team will be in touch. Bye!")
        await worker._run_until_done(
            session, brain, _FakeCtx(_FakeRoom()), "cid", "org", 0.0,
            {"value": "meeting_scheduled", "answered_by": "human", "transferred_to": None},
            {"n": 6},
        )
        return session

    session = _with_noop_save(run)
    assert "Thank you, our team will be in touch. Bye!" in session.said   # spoken
    assert session.handle.played is True                                  # played FULLY
    assert session.closed_at is not None                                  # then ended


def test_no_ending_message_when_no_booking():
    """A non-booking close with an empty script must NOT speak anything extra."""
    async def run():
        _fast_timing()
        worker._CLOSE_CONFIRM_WINDOW = 0.1
        state = _FakeState(6, booking_engaged=False)
        session = _FakeSession(_FakeLLM(Directive.EXIT_POLITE), state)
        brain = _FakeBrain(state)   # empty closing/thank-you/ending path
        await worker._run_until_done(
            session, brain, _FakeCtx(_FakeRoom()), "cid", "org", 0.0,
            {"value": "x", "answered_by": "human", "transferred_to": None},
            {"n": 6},
        )
        return session

    session = _with_noop_save(run)
    assert session.said == []                     # nothing extra spoken
    assert session.closed_at is not None


def test_closing_then_thank_you_spoken_in_order_on_engaged_close():
    """FIX 1: on an engaged (EXIT_POLITE) close, the script's Closing statement
    and Thank-you are BOTH spoken in full, in order, before hangup — even with
    no booking. A booked call additionally gets the ending message after them."""
    async def run():
        _fast_timing()
        worker._CLOSE_CONFIRM_WINDOW = 0.1
        state = _FakeState(6, booking_engaged=True)
        session = _FakeSession(_FakeLLM(Directive.EXIT_POLITE), state)
        brain = _FakeBrain(
            state,
            closing="It's been great chatting.",
            thank_you="Thanks so much for your time.",
            ending="You'll get a confirmation shortly. Bye!",
        )
        await worker._run_until_done(
            session, brain, _FakeCtx(_FakeRoom()), "cid", "org", 0.0,
            {"value": "meeting_scheduled", "answered_by": "human", "transferred_to": None},
            {"n": 6},
        )
        return session

    session = _with_noop_save(run)
    # closing, then thank-you, then the booking ending — in that exact order.
    assert session.said == [
        "It's been great chatting.",
        "Thanks so much for your time.",
        "You'll get a confirmation shortly. Bye!",
    ]
    assert session.handle.played is True          # spoken to completion
    assert session.closed_at is not None          # then ended


async def _no_agent(*a, **k):
    return None


def test_polite_decline_speaks_closing_and_thank_you_not_ending():
    """A polite 'not interested' still gets a warm closing + thank-you, no ending."""
    async def run():
        _fast_timing()
        worker._CLOSE_CONFIRM_WINDOW = 0.1
        state = _FakeState(6, booking_engaged=False, intents=["not_interested"])
        session = _FakeSession(_FakeLLM(Directive.EXIT_APOLOGETIC), state)
        brain = _FakeBrain(state, closing="No worries at all.",
                           thank_you="Thanks for your time.", ending="SHOULD NOT PLAY")
        await worker._run_until_done(
            session, brain, _FakeCtx(_FakeRoom()), "cid", "org", 0.0,
            {"value": "not_interested", "answered_by": "human", "transferred_to": None},
            {"n": 6})
        return session

    session = _with_noop_save(run)
    assert session.said == ["No worries at all.", "Thanks for your time."]
    assert session.closed_at is not None


def test_reject_wrong_number_speaks_no_signoff_but_still_ends():
    """Spam / wrong number: the model already apologised — no sales sign-off."""
    async def run():
        _fast_timing()
        worker._CLOSE_CONFIRM_WINDOW = 0.1
        state = _FakeState(6, intents=["wrong_number"])
        session = _FakeSession(_FakeLLM(Directive.EXIT_APOLOGETIC), state)
        brain = _FakeBrain(state, closing="X", thank_you="Y", ending="Z")
        await worker._run_until_done(
            session, brain, _FakeCtx(_FakeRoom()), "cid", "org", 0.0,
            {"value": "wrong_number", "answered_by": "human", "transferred_to": None},
            {"n": 6})
        return session

    session = _with_noop_save(run)
    assert session.said == []
    assert session.closed_at is not None


def test_transfer_with_no_agent_degrades_to_callback_not_signoff():
    """Transfer with nobody free offers a callback — never the sales closing."""
    async def run():
        _fast_timing()
        state = _FakeState(6)
        session = _FakeSession(_FakeLLM(Directive.TRANSFER_HUMAN), state)
        brain = _FakeBrain(state, closing="SHOULD NOT PLAY", thank_you="NOPE")
        orig = worker._route_to_human
        worker._route_to_human = _no_agent
        try:
            await worker._run_until_done(
                session, brain, _FakeCtx(_FakeRoom()), "cid", "org", 0.0,
                {"value": "x", "answered_by": "human", "transferred_to": None},
                {"n": 6})
        finally:
            worker._route_to_human = orig
        return session

    session = _with_noop_save(run)
    assert session.said == [
        "My colleagues are all busy right now. Can I arrange a call back?"]
    assert session.closed_at is not None


def test_opt_out_mid_call_suppresses_number_and_speaks_only_confirmation():
    """
    COMPLIANCE regression. A mid-call removal request ("stop calling me") is a
    HARD interrupt: it overrides an in-progress booking, writes the number to the
    DNC suppression list, speaks ONLY the removal confirmation — no closing, no
    thank-you, no ending, no sales sign-off — and then ends the call.
    """
    async def run():
        _fast_timing()
        worker._CLOSE_CONFIRM_WINDOW = 0.1
        # booking_engaged=True proves opt-out overrides even a booked call.
        state = _FakeState(6, booking_engaged=True, intents=["do_not_call"])
        session = _FakeSession(_FakeLLM(Directive.OPT_OUT), state)
        brain = _FakeBrain(
            state,
            closing="SHOULD NOT PLAY", thank_you="MUST NOT PLAY",
            ending="NEVER", opt_out="Understood, I'll remove you. Goodbye.",
            contact_phone="+15551234567",
        )

        suppressed = []
        orig = worker._suppress_contact

        async def fake_suppress(org_id, phone, reason="in-call opt-out"):
            suppressed.append((org_id, phone, reason))
            return True

        worker._suppress_contact = fake_suppress
        final = {"value": "x", "answered_by": "human", "transferred_to": None}
        try:
            await worker._run_until_done(
                session, brain, _FakeCtx(_FakeRoom()), "cid", "org", 0.0,
                final, {"n": 6})
        finally:
            worker._suppress_contact = orig
        return session, suppressed, final

    session, suppressed, final = _with_noop_save(run)
    # The number was written to DNC — for this org, this phone.
    assert suppressed == [("org", "+15551234567", "in-call opt-out")]
    # ONLY the confirmation was spoken. No closing / thank-you / ending leaked in.
    assert session.said == ["Understood, I'll remove you. Goodbye."]
    assert session.handle.played is True          # spoken in full
    assert session.closed_at is not None          # then the call ended
    assert final["value"] == "do_not_call"        # disposition recorded


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print(f"  ok  {t.__name__}")
    print(f"\n{len(tests)} passed")
