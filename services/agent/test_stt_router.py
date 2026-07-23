"""
    python services/agent/test_stt_router.py

The routing that keeps Tamil off Deepgram.
"""
from stt_router import (
    DEFAULT_PROVIDER, SARVAM_LANGUAGE, provider_for, sarvam_languages,
)


def test_english_and_hindi_go_to_deepgram():
    assert provider_for("en") == "deepgram"
    assert provider_for("hi") == "deepgram"


def test_tamil_and_indic_go_to_sarvam():
    # The whole point: Tamil must NOT reach Deepgram (0.31 accuracy).
    assert provider_for("ta") == "sarvam"
    for lang in ("te", "ml", "kn"):
        assert provider_for(lang) == "sarvam", lang


def test_unknown_and_missing_default_to_deepgram():
    assert provider_for("fr") == DEFAULT_PROVIDER
    assert provider_for(None) == DEFAULT_PROVIDER
    assert provider_for("") == DEFAULT_PROVIDER


def test_sarvam_language_codes_are_bcp47():
    # Sarvam needs region-qualified codes; every Sarvam-routed language must map.
    for code in sarvam_languages():
        assert code in SARVAM_LANGUAGE, code
        assert SARVAM_LANGUAGE[code].endswith("-IN")
    assert SARVAM_LANGUAGE["ta"] == "ta-IN"


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print(f"  ok  {t.__name__}")
    print(f"\n{len(tests)} passed")
