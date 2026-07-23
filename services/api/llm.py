"""
Anthropic client shared by the API's pre/post-call features.

The live per-turn call does NOT live here — it is in services/agent/brain.py,
where latency is the binding constraint. These calls are user-initiated and
off the critical path, so they run at normal effort with thinking enabled.

Both the live turn (services/agent/brain.py, LLM_MODEL) and these calls
(SUMMARY_MODEL) run Claude Sonnet 4.6. Latency does not matter here; quality
does, so these run at normal effort with thinking enabled.
"""
import os

from anthropic import AsyncAnthropic

MODEL = os.environ.get("SUMMARY_MODEL", "claude-sonnet-4-6")

client = AsyncAnthropic()  # reads ANTHROPIC_API_KEY / ant profile


async def complete(
    system: str,
    prompt: str,
    max_tokens: int = 2000,
    output_format=None,
):
    """One-shot completion. Pass a pydantic model as output_format for JSON."""
    kwargs = dict(model=MODEL, max_tokens=max_tokens, system=system,
                  messages=[{"role": "user", "content": prompt}])
    if output_format is not None:
        r = await client.messages.parse(**kwargs, output_format=output_format)
        return r.parsed_output
    r = await client.messages.create(**kwargs)
    return next((b.text for b in r.content if b.type == "text"), "")
