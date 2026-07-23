"""
Anthropic client shared by the API's pre/post-call features.

The live per-turn call does NOT live here — it is in services/agent/brain.py,
where latency is the binding constraint. These calls are user-initiated and
off the critical path, so they run at normal effort with thinking enabled.

Both the live turn (services/agent/brain.py, LLM_MODEL) and these calls
(SUMMARY_MODEL) run Claude Sonnet 4.6. Latency does not matter here; quality
does, so these run at normal effort with thinking enabled.
"""
import json
import logging
import os

from anthropic import AsyncAnthropic
from pydantic import BaseModel

log = logging.getLogger("api.llm")

MODEL = os.environ.get("SUMMARY_MODEL", "claude-sonnet-4-6")

client = AsyncAnthropic()  # reads ANTHROPIC_API_KEY / ant profile


# Grammar keywords that constrained decoding either rejects or that blow up
# grammar compilation on a large object — the "Schema is too complex" /
# "Grammar compilation timed out" 400s that made post-call summaries fail and
# fall back to a bogus "no conversation took place". Stripped from the WIRE
# schema; the pydantic model still validates types on the way back. Same list
# services/agent/brain.py strips for the live turn schema.
_UNSUPPORTED = frozenset({
    "minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum", "multipleOf",
    "minLength", "maxLength", "pattern", "format",
    "minItems", "maxItems", "uniqueItems",
})


def _strict_schema(model: type[BaseModel]) -> dict:
    """Pydantic JSON schema with unsupported/complex constraints removed and
    every object closed (additionalProperties: false)."""
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


def _first_text(resp) -> str:
    return next((b.text for b in resp.content if b.type == "text"), "")


def _extract_json(text: str) -> str:
    """Pull the JSON object out of a reply that may be wrapped in prose/fences."""
    a, b = text.find("{"), text.rfind("}")
    return text[a:b + 1] if a != -1 and b != -1 else text


async def complete(
    system: str,
    prompt: str,
    max_tokens: int = 2000,
    output_format=None,
    use_grammar: bool = True,
):
    """
    One-shot completion. Pass a pydantic model as output_format for JSON.

    For structured output we try constrained decoding first (with the complex
    keywords stripped so the grammar compiles), then fall back to a plain
    JSON-prompt on ANY failure — so a schema too large for the grammar compiler
    still yields a real object instead of raising. Only if BOTH paths fail does
    this raise, letting the caller retry rather than persist a wrong result.

    Set use_grammar=False for a schema KNOWN to exceed the grammar compiler
    (e.g. the post-call Summary: 16 fields with several arrays reliably 400s
    "Schema is too complex"). It then skips straight to the JSON-prompt path —
    one round trip instead of a guaranteed-to-400 attempt plus the fallback.
    """
    base = dict(model=MODEL, max_tokens=max_tokens, system=system,
                messages=[{"role": "user", "content": prompt}])
    if output_format is None:
        r = await client.messages.create(**base)
        return _first_text(r)

    schema = _strict_schema(output_format)
    if use_grammar:
        try:
            r = await client.messages.create(
                **base,
                output_config={"format": {"type": "json_schema", "schema": schema}},
            )
            return output_format.model_validate_json(_first_text(r))
        except Exception:
            log.warning("structured output failed for %s; retrying with a "
                        "plain-JSON prompt", output_format.__name__, exc_info=True)

    # JSON-prompt path: no grammar to compile. Primary when use_grammar=False,
    # otherwise the fallback after a constrained-decoding failure.
    fb = await client.messages.create(
        model=MODEL, max_tokens=max_tokens,
        system=(system + "\n\nReturn ONLY a single JSON object that matches this "
                "JSON schema. No prose, no markdown fences:\n" + json.dumps(schema)),
        messages=[{"role": "user", "content": prompt}],
    )
    return output_format.model_validate_json(_extract_json(_first_text(fb)))
