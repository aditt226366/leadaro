"""
The single per-turn LLM call.

Six FRD features come out of one round trip:
  3  conversation agent   → reply
  4  sentiment detection  → sentiment
  5  intent recognition   → intent
  9  next best action     → next_action
  10 objection handling   → next_action == handle_objection
  11 meeting booking      → next_action == book_meeting

Adding any of them as a separate call would add its full latency to every turn,
on a live phone line, where a second of silence is audible.
"""
from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass
from typing import Literal

from anthropic import AsyncAnthropic
from pydantic import BaseModel, Field

import partial_json
import prompts
from rules import ConversationState, Directive, decide

log = logging.getLogger(__name__)

MODEL = os.environ.get("LLM_MODEL", "claude-sonnet-4-6")

# A phone reply is one or two sentences. This cap is a latency control as much
# as a cost one: generation time scales with tokens produced.
MAX_TOKENS = 200

client = AsyncAnthropic()


class TurnOutput(BaseModel):
    """
    Structured output for one agent turn.

    Field order is load-bearing, because the object is streamed and consumed as
    it arrives.

    `emotion` and `speed` come first: they configure the TTS voice for the reply
    they describe, so they have to land BEFORE the words do. They are short
    enums — three or four tokens — so putting them ahead of `reply` delays first
    audio only marginally, and without them the agent speaks the entire call in
    one flat register, which is most of what makes it sound robotic.

    `reply` comes next so TTS can start on sentence one instead of waiting for
    the closing brace. The analysis fields trail it; nothing is spoken while
    they arrive.
    """
    emotion: Literal[
        "friendly", "professional", "confident", "energetic",
        "calm", "urgent", "happy", "empathetic",
    ]
    speed: Literal["slow", "normal", "fast"]
    reply: str = Field(description="Exactly what to say. One or two sentences.")
    pitch: Literal["low", "medium", "high"]
    intent: Literal[
        "interested", "price_inquiry", "more_info", "book_demo", "book_meeting",
        "support", "complaint", "objection", "not_interested", "wrong_number",
        "spam", "call_later", "busy", "speak_to_human", "language_switch",
        "voicemail", "neutral", "unclear",
    ]
    sentiment: float = Field(ge=-1.0, le=1.0)
    next_action: Literal[
        "continue", "handle_objection", "explain_detail", "book_meeting",
        "transfer_human", "schedule_callback", "close_positive",
        "close_negative", "leave_voicemail",
    ]


# Validation keywords structured outputs rejects. `messages.parse()` strips
# these for you and enforces them client-side instead; a schema passed by hand
# to output_config.format gets no such help, so we strip them here. Pydantic
# still applies every one of them in model_validate_json() — dropping them from
# the wire schema loses no validation, only the server-side hint.
_UNSUPPORTED = frozenset({
    "minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum", "multipleOf",
    "minLength", "maxLength", "pattern", "format",
    "minItems", "maxItems", "uniqueItems",
})


def _strict_schema(model: type[BaseModel]) -> dict:
    """
    Pydantic's JSON schema, adjusted for structured outputs: every object gets
    `additionalProperties: false`, and unsupported constraints are removed.
    Computed once at import.
    """
    def clean(node):
        if isinstance(node, dict):
            out = {k: clean(v) for k, v in node.items() if k not in _UNSUPPORTED}
            if out.get("type") == "object":
                out["additionalProperties"] = False
            return out
        if isinstance(node, list):
            return [clean(v) for v in node]
        return node

    return clean(model.model_json_schema())


TURN_SCHEMA = _strict_schema(TurnOutput)


@dataclass
class TurnResult:
    output: TurnOutput
    directive: Directive
    llm_ms: int
    cache_read_tokens: int
    input_tokens: int
    output_tokens: int


class Brain:
    """One instance per call. Holds the history and the rolling rule state."""

    def __init__(self, campaign: dict, lead: dict):
        self.campaign = campaign
        self.lead = lead
        # Built once. Must stay byte-identical across turns — see prompts.py.
        self.system = prompts.build_system(campaign)
        self.history: list[dict] = []
        self.state = ConversationState()

    def seed_inbound_context(self, prior: dict) -> None:
        """Inbound from a known lead: prior-call context as the first user turn."""
        self.history.append(
            {"role": "user", "content": prompts.resumption_context(prior)}
        )

    def note_spoken(self, text: str) -> None:
        """
        Record something the session spoke outside the turn loop — the outbound
        opening, a voicemail message, a transfer whisper.

        Anthropic rejects a leading assistant message, so an empty history gets a
        minimal user turn standing in for the callee picking up.
        """
        if not self.history:
            self.history.append({"role": "user", "content": "[call answered]"})
        self.history.append({"role": "assistant", "content": text})

    async def turn(self, heard: str, directive_hint: Directive | None = None) -> TurnResult:
        """
        One conversational turn: caller's words in, agent's reply + labels out.

        `directive_hint` carries a deterministic rule decision from the previous
        turn so this turn's generation already obeys it.
        """
        # The coaching nudge rides along with the caller's words rather than as
        # a mid-conversation system message: `role: "system"` inside messages[]
        # is Opus 4.8-only and 400s on every other model. Appending to the user
        # turn works everywhere and still leaves the cached prefix untouched.
        content = heard
        if directive_hint and (nudge := prompts.DIRECTIVE_NUDGE.get(directive_hint)):
            content = f"{heard}\n\n[Direction for your next line: {nudge}]"

        self.history.append({"role": "user", "content": content})
        messages = list(self.history)

        t0 = time.perf_counter()
        resp = await client.messages.parse(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            # Sonnet 5 runs ADAPTIVE thinking when this field is omitted, which
            # silently adds seconds per turn. On a live call that is fatal.
            thinking={"type": "disabled"},
            output_config={"effort": "low"},
            system=[{
                "type": "text",
                "text": self.system,
                "cache_control": {"type": "ephemeral"},
            }],
            messages=messages,
            output_format=TurnOutput,
        )
        llm_ms = int((time.perf_counter() - t0) * 1000)

        out: TurnOutput = resp.parsed_output
        self.history.append({"role": "assistant", "content": out.reply})

        self.state.record(out.sentiment, out.intent)
        directive = decide(self.state, out.intent, out.next_action)

        usage = resp.usage
        cache_read = getattr(usage, "cache_read_input_tokens", 0) or 0

        # Turn 2 onward should be reading cache. Zero means something variable
        # crept into the system prompt.
        if len(self.history) > 3 and cache_read == 0:
            log.warning(
                "prompt cache miss on turn %d — system prompt is not stable",
                self.state.turn_count,
            )

        return TurnResult(
            output=out,
            directive=directive,
            llm_ms=llm_ms,
            cache_read_tokens=cache_read,
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
        )

    async def turn_streaming(
        self,
        heard: str,
        on_sentence,
        directive_hint: Directive | None = None,
        on_delivery=None,
    ) -> TurnResult:
        """
        Same single call as `turn`, but hands each finished sentence to
        `on_sentence` the moment it is complete instead of waiting for the whole
        object.

        This is the difference between speaking at ~1.5s and ~2.7s. `reply` is
        the first field in the schema, so it finishes well before `sentiment`
        and `next_action` — TTS gets to work while the labels are still arriving.

        `on_sentence` is awaited, so a slow TTS backs up the loop rather than
        queueing unbounded audio.
        """
        content = heard
        if directive_hint and (nudge := prompts.DIRECTIVE_NUDGE.get(directive_hint)):
            content = f"{heard}\n\n[Direction for your next line: {nudge}]"

        self.history.append({"role": "user", "content": content})

        t0 = time.perf_counter()
        first_audio_ms: int | None = None
        buf = ""
        emitted = 0
        delivery_sent = False

        async with client.messages.stream(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            thinking={"type": "disabled"},
            output_config={
                "effort": "low",
                "format": {"type": "json_schema", "schema": TURN_SCHEMA},
            },
            system=[{
                "type": "text",
                "text": self.system,
                "cache_control": {"type": "ephemeral"},
            }],
            messages=list(self.history),
        ) as stream:
            async for chunk in stream.text_stream:
                buf += chunk

                # Delivery first — emotion and speed precede `reply` in the
                # schema so the voice is configured before it speaks. Fires once.
                if on_delivery and not delivery_sent:
                    emo = partial_json.extract_complete_string(buf, "emotion")
                    spd = partial_json.extract_complete_string(buf, "speed")
                    if emo and spd:
                        delivery_sent = True
                        await on_delivery(emo, spd)

                reply_so_far = partial_json.extract_string_prefix(buf, "reply")
                sentences, emitted = partial_json.complete_sentences(
                    reply_so_far, emitted
                )
                for s in sentences:
                    if first_audio_ms is None:
                        first_audio_ms = int((time.perf_counter() - t0) * 1000)
                    await on_sentence(s)

            final = await stream.get_final_message()

        llm_ms = int((time.perf_counter() - t0) * 1000)

        text = next((b.text for b in final.content if b.type == "text"), buf)
        out = TurnOutput.model_validate_json(text)

        # Anything after the last terminator (or a reply with no terminator at all).
        if tail := partial_json.flush_remainder(out.reply, emitted):
            if first_audio_ms is None:
                first_audio_ms = int((time.perf_counter() - t0) * 1000)
            await on_sentence(tail)

        self.history.append({"role": "assistant", "content": out.reply})
        self.state.record(out.sentiment, out.intent)
        directive = decide(self.state, out.intent, out.next_action)

        cache_read = getattr(final.usage, "cache_read_input_tokens", 0) or 0
        return TurnResult(
            output=out,
            directive=directive,
            # The number that matters on a call is when audio started, not when
            # the object finished.
            llm_ms=first_audio_ms if first_audio_ms is not None else llm_ms,
            cache_read_tokens=cache_read,
            input_tokens=final.usage.input_tokens,
            output_tokens=final.usage.output_tokens,
        )

    def note_silence(self) -> Directive:
        self.state.record_silence()
        return decide(self.state, "neutral", "continue")

    def note_unclear(self) -> Directive:
        self.state.record_unclear()
        return decide(self.state, "unclear", "continue")

    def opening(self) -> str:
        return prompts.opening_line(self.campaign.get("script") or {}, self.lead)
