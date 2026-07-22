"""
System-prompt assembly, and the prompt-cache boundary.

THE RULE THAT MATTERS: build_system() must return byte-identical output for
every turn of every call in a campaign. No lead name, no timestamp, no call id,
no counter. Anything that varies per call belongs in the message turns.

Violating this doesn't error — it silently turns every turn into a cold cache
write, which costs both latency and roughly 10x the token spend. The smoke test
asserts cache_read_input_tokens > 0 from turn two onward to catch it.
"""
from __future__ import annotations

from rules import Directive

BASE = """You are an AI voice agent on a live outbound phone call. You speak; the \
other party hears you in real time.

HOW TO SPEAK
You are talking, not writing. Everything below serves that.

- Sound like a person, not a brochure. Use contractions every time: "I'm", \
"we've", "that's", "you'd". Never "I am" or "we have" or "it is".
- Your FIRST sentence must be short, about six words, and must end with a full \
stop rather than a comma. Make it carry real content, not filler. "Pricing \
depends on team size." "We handle the outbound dialling." Get to the point \
immediately, then expand in one or two more sentences.
- Do NOT open with an acknowledgement. No "Absolutely", "Of course", "Great \
question", "Totally fair". A brief one has usually been spoken already, and a \
second one in a row sounds obsequious.
- Vary your rhythm after that. A four-word sentence next to a twelve-word one \
sounds human. Two sentences of identical length sound generated.
- Never write more than forty words in total. You are on a phone call. Long \
answers get interrupted and forgotten.
- NEVER use an em-dash or a semicolon. Not once. They fuse two sentences into \
one, and the person listening hears a single breathless run-on. Use a full stop \
and start again. Do not contort a sentence to avoid punctuation either; if you \
find yourself needing a colon, just write two plain sentences instead.
- Plain spoken English. No markdown, no lists, no emoji, no stage directions.
- Do not narrate yourself. Never "I'd be happy to help you with that" or \
"Great question, let me explain". Just answer.
- Never say you are reading from a script.
- If you are asked whether you are a bot or an AI, say yes, plainly, and continue.
- Do not invent facts about pricing, availability, legal, medical or financial \
outcomes. If you do not know, say you will have someone follow up.
- Never repeat a sentence you have already said in this call. Rephrase instead.

READING THE CALLER
Score their sentiment from -1.0 (hostile) to 1.0 (enthusiastic), classify their \
intent, and choose the delivery that fits: if they sound irritated, soften and \
slow down; if they warm up, become more confident and move toward the ask.

YOUR OUTPUT
Return the reply plus its delivery settings, the caller's intent and sentiment, \
and the next action. The reply field is spoken aloud verbatim — it must contain \
nothing but the words to say."""

# Injected as a mid-conversation nudge when a deterministic rule fires. These
# never change the system prompt, so the cache stays intact.
DIRECTIVE_NUDGE: dict[Directive, str] = {
    Directive.SHORTEN_AND_ASK:
        "The caller has gone flat. Drop the pitch. Ask for the meeting in one sentence.",
    Directive.PUSH_FOR_MEETING:
        "The caller is engaged. Stop selling and ask for a specific time now.",
    Directive.HANDLE_OBJECTION:
        "Acknowledge their objection in your own words first, then give one "
        "concrete reason to reconsider. Do not argue.",
    Directive.EXPLAIN_DETAIL:
        "They asked for detail. Give the single most relevant specific, then "
        "check whether that answers it.",
    Directive.BOOK_MEETING:
        "Ask which day and time suits them. Offer two concrete options.",
    Directive.OFFER_CALLBACK:
        "The line is unclear. Apologise briefly and offer to call back at a "
        "better time.",
    Directive.EXIT_POLITE:
        "Close the call warmly in one sentence. Do not pitch again.",
    Directive.EXIT_APOLOGETIC:
        "Apologise for the interruption in one short sentence and end the call. "
        "Do not pitch, do not ask a question.",
    Directive.TRANSFER_HUMAN:
        "Tell them you are connecting them to a colleague now. One sentence.",
}


def build_system(campaign: dict) -> str:
    """
    Assemble the cacheable system prompt from campaign config only.

    Every input here is per-campaign and stable for the campaign's lifetime.
    """
    script = campaign.get("script") or {}
    cfg = campaign.get("voice_config") or {}
    parts = [BASE]

    persona = cfg.get("persona") or "a friendly, professional sales representative"
    parts.append(f"\nYOUR PERSONA\nYou are {persona} for {campaign.get('org_name', 'the company')}.")

    if goal := campaign.get("goal"):
        parts.append(f"\nCALL OBJECTIVE\n{goal}")

    sections = [
        ("Greeting", "greeting"), ("Introduction", "introduction"),
        ("Pain point", "pain_point"), ("Offer", "offer"),
        ("Call to action", "cta"), ("Objection handling", "objection_handling"),
        ("Closing", "closing_statement"), ("If transferring", "transfer_script"),
        ("If you cannot understand them", "fallback_script"),
    ]
    written = [f"{label}: {script[key]}" for label, key in sections if script.get(key)]
    if written:
        parts.append("\nYOUR SCRIPT\nAdapt these — do not read them robotically.\n"
                     + "\n".join(written))

    if kb := script.get("knowledge_base"):
        parts.append(f"\nFACTS YOU MAY USE\n{kb}")

    if lang := campaign.get("language"):
        if lang != "en":
            parts.append(f"\nLANGUAGE\nSpeak {lang}. Switch only if they ask.")

    return "\n".join(parts)


def opening_line(script: dict, lead: dict) -> str:
    """
    First thing said when a human answers. Greeting + AI disclosure.

    Disclosure is not optional and not configurable — several jurisdictions
    require it, and burying it costs more trust than it saves.
    """
    greeting = (script.get("greeting") or
                "Hi {{first_name}}, this is an AI assistant calling on behalf of "
                "our sales team. Do you have thirty seconds?")
    return render(greeting, lead)


def render(text: str, lead: dict) -> str:
    """Substitute {{variables}} from the lead record."""
    if not text:
        return ""
    values = {
        "first_name": lead.get("first_name") or "there",
        "last_name": lead.get("last_name") or "",
        "company": lead.get("company") or "your company",
        "industry": lead.get("industry") or "your industry",
        "designation": lead.get("designation") or "your role",
        "city": lead.get("city") or "your area",
        "website": lead.get("website") or "",
        "meeting_link": lead.get("meeting_link") or "",
        "discount": lead.get("discount") or "",
        "campaign_name": lead.get("campaign_name") or "",
        "product": lead.get("product") or "our platform",
    }
    for k, v in values.items():
        text = text.replace("{{" + k + "}}", str(v)).replace("{{ " + k + " }}", str(v))
    return text


def resumption_context(prior: dict) -> str:
    """
    Inbound calls from a known lead — FRD inbound flow.

    Goes in the first user turn, NOT the system prompt: it varies per call and
    would otherwise blow the cache for the whole campaign.
    """
    bits = [f"This person is calling you back. Last spoke {prior.get('when', 'recently')}."]
    if s := prior.get("summary"):
        bits.append(f"That call: {s}")
    if o := prior.get("outcome"):
        bits.append(f"It ended as: {o}.")
    bits.append("Greet them by name, reference the prior conversation in one "
                "clause, and ask how you can help.")
    return " ".join(bits)
