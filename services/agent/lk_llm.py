"""
Adapts Brain to LiveKit's LLM plugin interface.

This is what lets AgentSession own the hard real-time parts — VAD, endpointing,
barge-in, turn detection, TTS scheduling — while Brain owns what to say and the
six per-turn features. Writing our own turn loop would mean reimplementing all
of that, badly.

Text is pushed out sentence by sentence as it streams, so TTS starts on
sentence one rather than waiting for the whole JSON object. Measured saving:
~550ms per turn.
"""
from __future__ import annotations

import logging

from livekit.agents import llm

from brain import Brain, TurnResult

log = logging.getLogger(__name__)

# NOTE ON BACKCHANNEL — do not re-attempt this the obvious ways.
#
# Speaking a short "mm-hm" the instant the caller stops would mask the model's
# thinking time, which is the thing callers actually notice. Three approaches
# were built and measured, and all three fail:
#
#   1. Emit a ChatChunk here before calling the model. The chunk leaves at +0ms
#      (logged and confirmed) but the TTS node buffers it and the caller hears
#      nothing until the rest of the reply is ready. Perceived latency: 4.7s.
#   2. session.say() from inside _run. The generation for this turn is already
#      scheduled, so the filler queues BEHIND it and plays after. No gain.
#   3. livekit's own _AgentBackchannelOpportunityEvent. Documented as internal,
#      "not surfaced as a public AgentSession event yet" — depending on it means
#      depending on private internals.
#
# The correct hook is a turn-end event that fires before generation is queued.
# When LiveKit makes that public, this becomes a few lines. Until then the real
# latency work is preemptive_generation (measured: 860ms) and co-location.

# Speech rate -> Cartesia sonic-3 `speed` (valid range 0.6-2.0; 1.0 is neutral).
# The model and the campaign both speak in words; this is the SINGLE source that
# maps those onto the sonic-3 float, so the two call sites — per-turn delivery
# here and the base speed in worker._build_session — can never drift out of
# range again. (The old -1..1 scale was for sonic-2 and silently sent invalid
# values on sonic-3: normal=0.0 was dropped, slow/fast fell below/near 0.6.)
SPEED_SCALE = {"slow": 0.8, "normal": 1.0, "fast": 1.3}


class BrainLLM(llm.LLM):
    """LiveKit LLM plugin backed by one Brain instance (one per call)."""

    def __init__(self, brain: Brain, on_turn=None, tts=None, pause_tag=""):
        super().__init__()
        self.brain = brain
        # Called with the completed TurnResult after each turn — the worker uses
        # it to persist the transcript row and act on the directive.
        self.on_turn = on_turn
        # Needed to apply per-turn emotion and speed; without it the whole call
        # is spoken in one static register.
        self.tts = tts
        # Natural-pause markup appended after each spoken sentence (the campaign's
        # "Pause Controls" -> Cartesia `<break time="Nms"/>`). Empty when off.
        # Integer ms only, to dodge the tokenizer's tag-split-on-decimal bug.
        self.pause_tag = pause_tag
        self._pending_directive = None

    def chat(self, *, chat_ctx: llm.ChatContext, tools=None, conn_options=None,
             **kwargs) -> llm.LLMStream:
        return BrainStream(
            self, chat_ctx=chat_ctx, tools=tools or [], conn_options=conn_options
        )


class BrainStream(llm.LLMStream):
    def __init__(self, parent: BrainLLM, *, chat_ctx, tools, conn_options):
        super().__init__(parent, chat_ctx=chat_ctx, tools=tools,
                         conn_options=conn_options)
        self._parent = parent

    async def _run(self) -> None:
        brain = self._parent.brain

        heard = _last_user_text(self._chat_ctx)
        if not heard:
            # Endpointer fired on noise. Count it as silence so the two-strike
            # rule can eventually close the call, and say nothing.
            self._parent._pending_directive = brain.note_silence()
            return

        async def emit(sentence: str) -> None:
            # Each sentence goes downstream the moment it is complete; the TTS
            # node starts synthesising while the model is still writing. When the
            # campaign enables Natural Pause, a <break> tag is appended so Cartesia
            # inserts a short pause between sentences.
            spoken = f"{sentence} {self._parent.pause_tag}" if self._parent.pause_tag else sentence
            self._event_ch.send_nowait(
                llm.ChatChunk(
                    id=f"turn-{brain.state.turn_count}",
                    delta=llm.ChoiceDelta(role="assistant", content=spoken + " "),
                )
            )

        async def apply_delivery(emotion: str, speed: str) -> None:
            """Retune the voice before it speaks this turn's words."""
            if not self._parent.tts:
                return
            try:
                self._parent.tts.update_options(
                    emotion=emotion, speed=SPEED_SCALE[speed])
            except Exception:
                # A rejected emotion must never take the call down; speaking in
                # the previous turn's register is a perfectly survivable outcome.
                log.warning("could not apply delivery %s/%s", emotion, speed,
                            exc_info=True)

        try:
            result: TurnResult = await brain.turn_streaming(
                heard,
                on_sentence=emit,
                directive_hint=self._parent._pending_directive,
                on_delivery=apply_delivery,
            )
        except Exception:
            log.exception("turn failed; falling back to a holding line")
            self._event_ch.send_nowait(
                llm.ChatChunk(
                    id="fallback",
                    delta=llm.ChoiceDelta(
                        role="assistant",
                        content="Sorry, I didn't catch that. Could you say it again?",
                    ),
                )
            )
            self._parent._pending_directive = brain.note_unclear()
            return

        self._parent._pending_directive = result.directive
        if self._parent.on_turn:
            await self._parent.on_turn(heard, result)


def _last_user_text(chat_ctx: llm.ChatContext) -> str:
    """Pull the most recent user utterance out of LiveKit's chat context."""
    for item in reversed(chat_ctx.items):
        if getattr(item, "role", None) != "user":
            continue
        content = getattr(item, "content", None)
        if isinstance(content, str):
            return content.strip()
        if isinstance(content, list):
            parts = [c for c in content if isinstance(c, str)]
            if parts:
                return " ".join(parts).strip()
    return ""
