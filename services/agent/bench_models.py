"""
Head-to-head per-turn latency across candidate models and settings.

    python services/agent/bench_models.py

Answers the only question that matters before wiring telephony: which model can
hold a phone conversation without an audible gap. Runs the same three turns
through each config so the numbers are comparable.
"""
import asyncio
import os
import statistics
import sys
import time

from anthropic import AsyncAnthropic

from brain import TurnOutput
import prompts

CAMPAIGN = {
    "org_name": "Leadaro",
    "goal": "Book a 20 minute product demo",
    "language": "en",
    "voice_config": {"persona": "a friendly SDR named Emma"},
    "script": {
        "greeting": "Hi {{first_name}}, this is Emma from Leadaro.",
        "offer": "Leadaro runs outbound calls with AI and books meetings.",
        "cta": "Would a short demo this week be useful?",
        "knowledge_base": "Pricing starts at $499/month for 5,000 minutes. "
                          "Integrates with HubSpot, Salesforce and Zoho.",
    },
}

TURNS = ["Who is this?", "What does it do?", "How much does it cost?"]

CONFIGS = [
    ("sonnet-4-6  structured", "claude-sonnet-4-6", True),
    ("sonnet-4-6  plain text", "claude-sonnet-4-6", False),
]

client = AsyncAnthropic()
SYSTEM = prompts.build_system(CAMPAIGN)


async def run(model: str, structured: bool) -> tuple[list[int], int, str]:
    history: list[dict] = []
    lat: list[int] = []
    cached = 0
    sample = ""

    for heard in TURNS:
        history.append({"role": "user", "content": heard})
        kwargs = dict(
            model=model,
            max_tokens=200,
            thinking={"type": "disabled"},
            system=[{"type": "text", "text": SYSTEM,
                     "cache_control": {"type": "ephemeral"}}],
            messages=list(history),
        )
        t0 = time.perf_counter()
        if structured:
            r = await client.messages.parse(**kwargs, output_format=TurnOutput)
            reply = r.parsed_output.reply
        else:
            r = await client.messages.create(**kwargs)
            reply = next((b.text for b in r.content if b.type == "text"), "")
        lat.append(int((time.perf_counter() - t0) * 1000))

        if (getattr(r.usage, "cache_read_input_tokens", 0) or 0) > 0:
            cached += 1
        history.append({"role": "assistant", "content": reply})
        sample = reply

    return lat, cached, sample


async def main() -> int:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("ANTHROPIC_API_KEY not set")
        return 2

    print(f"system prompt: {len(SYSTEM)} chars\n")
    print(f"{'config':<24} {'p50':>7} {'min':>7} {'max':>7}  {'cache':>6}")
    print("-" * 60)

    results = []
    for label, model, structured in CONFIGS:
        try:
            lat, cached, sample = await run(model, structured)
        except Exception as e:
            print(f"{label:<24} FAILED: {type(e).__name__}: {str(e)[:60]}")
            continue
        p50 = statistics.median(lat)
        results.append((label, p50, sample))
        print(f"{label:<24} {p50:>6.0f}ms {min(lat):>6}ms {max(lat):>6}ms  "
              f"{cached}/{len(lat):>4}")

    if results:
        best = min(results, key=lambda r: r[1])
        print(f"\nfastest: {best[0]} at {best[1]:.0f}ms")
        print(f"  sample reply: {best[2][:120]}")
        print(f"\nwith ~400ms for VAD+STT+TTS around it, first audio lands at "
              f"~{best[1] + 400:.0f}ms")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
