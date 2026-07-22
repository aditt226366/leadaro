"""
Measures the real per-turn latency — the project's primary success metric.

    ANTHROPIC_API_KEY=sk-... python services/agent/bench_turn.py

Runs a scripted conversation against the live model and reports the latency
distribution plus the prompt-cache hit rate. Run this before wiring telephony:
if p50 is already above ~700ms here, no amount of STT/TTS tuning will save the
call, streaming into TTS is the lever - not a smaller model.
"""
import asyncio
import os
import statistics
import sys

from brain import Brain

CAMPAIGN = {
    "org_name": "Leadaro",
    "goal": "Book a 20 minute product demo",
    "language": "en",
    "voice_config": {"persona": "a friendly SDR named Emma"},
    "script": {
        "greeting": "Hi {{first_name}}, this is Emma from Leadaro. I'm an AI "
                    "assistant — do you have thirty seconds?",
        "introduction": "We work with {{industry}} teams on outbound calling.",
        "pain_point": "Most teams lose hours a day to manual dialling.",
        "offer": "Leadaro runs the calls with AI and books meetings automatically.",
        "cta": "Would a short demo this week be useful?",
        "objection_handling": "Plenty of people say that before they see it work.",
        "knowledge_base": "Pricing starts at $499/month for 5,000 minutes. "
                          "Integrates with HubSpot, Salesforce and Zoho.",
    },
}

LEAD = {"first_name": "Raj", "company": "Globex", "industry": "SaaS",
        "designation": "VP Sales", "city": "Austin"}

# A realistic arc: curious -> probing -> objection -> warming -> close.
TURNS = [
    "Uh, sure, who is this again?",
    "What exactly does it do?",
    "How much is it?",
    "That's more than we budgeted honestly.",
    "Hmm. Does it work with HubSpot?",
    "Okay, that's interesting.",
    "Yeah, go on.",
    "Alright, what would a demo look like?",
    "Tuesday could work.",
    "Sure, send me the invite.",
]


async def main() -> int:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("ANTHROPIC_API_KEY is not set — cannot measure live latency.")
        return 2

    brain = Brain(CAMPAIGN, LEAD)
    print(f"model     : {os.environ.get('LLM_MODEL', 'claude-sonnet-4-6')}")
    print(f"opening   : {brain.opening()}\n")

    lat: list[int] = []
    cached = 0
    directive = None

    for i, heard in enumerate(TURNS, 1):
        try:
            r = await brain.turn(heard, directive_hint=directive)
        except Exception as e:
            print(f"turn {i} failed: {type(e).__name__}: {e}")
            return 1

        lat.append(r.llm_ms)
        if r.cache_read_tokens > 0:
            cached += 1
        directive = r.directive

        print(f"[{i:2}] caller : {heard}")
        print(f"     agent  : {r.output.reply}")
        print(f"     labels : intent={r.output.intent} "
              f"sentiment={r.output.sentiment:+.2f} "
              f"emotion={r.output.emotion} speed={r.output.speed}")
        print(f"     next   : model={r.output.next_action} -> applied={r.directive}")
        print(f"     timing : {r.llm_ms}ms  cache_read={r.cache_read_tokens} tok\n")

    lat_sorted = sorted(lat)
    p50 = statistics.median(lat_sorted)
    p95 = lat_sorted[max(0, int(len(lat_sorted) * 0.95) - 1)]

    print("-" * 62)
    print(f"turns            : {len(lat)}")
    print(f"llm p50          : {p50:.0f} ms")
    print(f"llm p95          : {p95:.0f} ms")
    print(f"llm min / max    : {min(lat)} / {max(lat)} ms")
    print(f"cache hit rate   : {cached}/{len(lat)} turns")
    print(f"lead tier        : {brain.state.turn_count} turns -> "
          f"{__import__('rules').qualify(brain.state)}")

    # Budget from the plan: ~100ms VAD + ~150ms STT + ~150ms TTS around the model.
    est = p50 + 400
    print(f"\nestimated first-audio latency: ~{est:.0f} ms  "
          f"(llm p50 + ~400ms for VAD/STT/TTS)")
    if est > 1400:
        print("  ABOVE TARGET. Escalation ladder:")
        print("   1. confirm thinking={'type':'disabled'} is set (biggest single win)")
        print("   2. confirm cache hit rate is ~100% after turn 1")
        print("   3. lower max_tokens in brain.py")
        print("   4. stream partial output into TTS (see worker.py)")
    else:
        print("  Within the conversational range.")

    if cached < len(lat) - 1:
        print("\n  WARNING: prompt cache is not being hit on every turn after the")
        print("  first. Something per-call is in the system prompt — run")
        print("  test_prompts.py and check prompts.build_system().")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
