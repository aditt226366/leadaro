"""
DTMF keypad menu for inbound calls.

Runs *before* the conversational agent. A caller who presses a key gets routed
immediately; a caller who says nothing and presses nothing falls through to the
AI agent, which is the better experience for anyone calling from a mobile who
never listens to menus anyway.

`sip_dtmf_received` is a first-class LiveKit room event, so no audio-level
tone detection is needed.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field

log = logging.getLogger(__name__)

VALID_DIGITS = frozenset("0123456789*#")


@dataclass
class MenuOption:
    digit: str
    label: str
    action: str            # ai_agent | transfer | voicemail | hangup | submenu
    target: str | None = None
    message: str | None = None


@dataclass
class IvrMenu:
    enabled: bool = False
    greeting: str = ""
    timeout_seconds: int = 6
    invalid_message: str = ""
    repeat_limit: int = 2
    options: list[MenuOption] = field(default_factory=list)

    @classmethod
    def from_json(cls, raw: dict | None) -> "IvrMenu":
        raw = raw or {}
        return cls(
            enabled=bool(raw.get("enabled")),
            greeting=raw.get("greeting") or "",
            timeout_seconds=int(raw.get("timeout_seconds") or 6),
            invalid_message=raw.get("invalid_message")
                or "Sorry, I didn't get that.",
            repeat_limit=int(raw.get("repeat_limit") or 2),
            options=[
                MenuOption(
                    digit=str(o.get("digit", "")),
                    label=o.get("label") or "",
                    action=o.get("action") or "ai_agent",
                    target=o.get("target"),
                    message=o.get("message"),
                )
                for o in (raw.get("options") or [])
                if str(o.get("digit", "")) in VALID_DIGITS
            ],
        )

    def find(self, digit: str) -> MenuOption | None:
        return next((o for o in self.options if o.digit == digit), None)

    def spoken_prompt(self) -> str:
        """Greeting plus the options, as one utterance."""
        parts = [self.greeting] if self.greeting else []
        parts += [f"Press {o.digit} {o.label}." for o in self.options if o.label]
        return " ".join(parts)


async def run_menu(session, room, menu: IvrMenu) -> MenuOption | None:
    """
    Play the menu and wait for a keypress.

    Returns the chosen option, or None if the caller pressed nothing — in which
    case the caller should be handed to the AI agent rather than dropped.
    """
    if not menu.enabled or not menu.options:
        return None

    pressed: asyncio.Queue[str] = asyncio.Queue()

    def on_dtmf(ev) -> None:
        digit = getattr(ev, "digit", None) or str(getattr(ev, "code", ""))
        if digit:
            pressed.put_nowait(digit)

    room.on("sip_dtmf_received", on_dtmf)
    try:
        for attempt in range(menu.repeat_limit + 1):
            # Interruptible: pressing a key mid-prompt should act at once, which
            # is exactly how callers who know the menu expect it to behave.
            await session.say(
                menu.spoken_prompt() if attempt == 0
                else f"{menu.invalid_message} {menu.spoken_prompt()}",
                allow_interruptions=True,
            )
            try:
                digit = await asyncio.wait_for(
                    pressed.get(), timeout=menu.timeout_seconds
                )
            except asyncio.TimeoutError:
                continue

            if option := menu.find(digit):
                log.info("ivr: caller pressed %s -> %s", digit, option.action)
                if option.message:
                    await session.say(option.message, allow_interruptions=False)
                return option

            log.info("ivr: caller pressed %s (unassigned)", digit)

        # Out of attempts. Fall through to the agent rather than hanging up —
        # a caller stuck in a menu loop is worse than one who gets a person.
        log.info("ivr: no valid selection, handing to the AI agent")
        return None
    finally:
        room.off("sip_dtmf_received", on_dtmf)
