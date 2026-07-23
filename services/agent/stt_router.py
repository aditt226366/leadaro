"""
Language-keyed STT routing.

No single STT vendor covers every language well. Deepgram Nova-3
(``language="multi"``) is production-grade for English and Hindi (measured 1.00
and 0.99 confidence) but cannot do Tamil (0.31 — it romanises it into garbage),
so Tamil and other Indic languages route to Sarvam Saaras instead.

Adding a language is a one-line edit to ``STT_PROVIDER_BY_LANG``. Adding a whole
provider is: implement it, put one warm instance in the prewarm pool under its
name, and point the languages at it here. Nothing else changes.
"""
from __future__ import annotations

# Provider name per ISO language code. Anything not listed uses DEFAULT_PROVIDER.
STT_PROVIDER_BY_LANG: dict[str, str] = {
    # Deepgram Nova-3 multilingual — verified strong on these.
    "en": "deepgram",
    "hi": "deepgram",
    # Sarvam Saaras — Indic languages Deepgram mistranscribes. The adapter is
    # wired separately; until it is, these languages fail loud rather than
    # silently falling back to Deepgram (a guaranteed mistranscription).
    "ta": "sarvam",
    "te": "sarvam",
    "ml": "sarvam",
    "kn": "sarvam",
}

DEFAULT_PROVIDER = "deepgram"

# Sarvam wants BCP-47 codes with a region; we store ISO-639-1 internally. Unlike
# Deepgram's "multi", a Sarvam STT instance is bound to one language, so each
# Sarvam-routed language gets its own warmed instance keyed by its code.
SARVAM_LANGUAGE = {
    "ta": "ta-IN", "te": "te-IN", "ml": "ml-IN", "kn": "kn-IN",
    "hi": "hi-IN", "en": "en-IN",
}


def provider_for(language: str | None) -> str:
    """The STT provider a call in `language` should use."""
    return STT_PROVIDER_BY_LANG.get((language or "en"), DEFAULT_PROVIDER)


def sarvam_languages() -> list[str]:
    """Internal codes that route to Sarvam — one warm instance is built per code."""
    return [code for code, prov in STT_PROVIDER_BY_LANG.items() if prov == "sarvam"]
