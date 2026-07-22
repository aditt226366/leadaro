"""
    python services/agent/test_partial_json.py

Feeds JSON in one character at a time — the way it actually arrives from the
stream — and asserts the extracted prefix is never wrong, never contains a
broken escape, and never speaks a half sentence.
"""
import json

from partial_json import (complete_sentences, extract_complete_string,
                          extract_string_prefix, flush_remainder)

FULL = json.dumps({
    "reply": 'Pricing starts at $499 a month. Would a demo help?',
    "emotion": "friendly",
    "sentiment": 0.4,
})


def test_extracts_progressively_and_never_lies():
    """Every prefix of the stream must yield a prefix of the true value."""
    truth = json.loads(FULL)["reply"]
    for n in range(len(FULL) + 1):
        got = extract_string_prefix(FULL[:n], "reply")
        assert truth.startswith(got), f"at n={n}: {got!r} is not a prefix of the value"
    assert extract_string_prefix(FULL, "reply") == truth


def test_missing_key_returns_empty():
    assert extract_string_prefix("", "reply") == ""
    assert extract_string_prefix('{"emo', "reply") == ""
    assert extract_string_prefix('{"reply"', "reply") == ""
    assert extract_string_prefix('{"reply":', "reply") == ""
    assert extract_string_prefix('{"reply": ', "reply") == ""
    # Opening quote present but no content yet.
    assert extract_string_prefix('{"reply": "', "reply") == ""


def test_escapes_decode():
    raw = r'{"reply": "She said \"yes\" \\ then left.\nNew line."}'
    assert extract_string_prefix(raw, "reply") == 'She said "yes" \\ then left.\nNew line.'


def test_partial_escape_is_withheld_not_mangled():
    # ONE trailing backslash = an escape whose second char hasn't arrived yet.
    # It must be withheld, not emitted as a literal backslash.
    assert extract_string_prefix('{"reply": "a' + "\\", "reply") == "a"
    # TWO backslashes = a complete escape for one literal backslash.
    assert extract_string_prefix('{"reply": "a' + "\\\\", "reply") == "a\\"
    # A truncated \uXXXX must not emit garbage.
    assert extract_string_prefix(r'{"reply": "hi \u26', "reply") == "hi "
    # …and the complete form decodes.
    assert extract_string_prefix(r'{"reply": "hi ☀', "reply") == "hi ☀"
    assert extract_string_prefix('{"reply": "hi ☀"', "reply") == "hi ☀"


def test_whitespace_variants_between_key_and_value():
    assert extract_string_prefix('{"reply"  :   "ok"}', "reply") == "ok"
    assert extract_string_prefix('{\n  "reply": "ok"\n}', "reply") == "ok"


def test_sentences_emit_only_when_complete():
    text = "Pricing starts at $499 a month"
    got, off = complete_sentences(text, 0)
    assert got == [] and off == 0, "no terminator yet — nothing should be spoken"

    text += ". Would a demo help?"
    got, off = complete_sentences(text, 0)
    assert got == ["Pricing starts at $499 a month.", "Would a demo help?"]
    assert off == len(text)


def test_sentences_resume_from_offset():
    text = "One. Two. Three."
    first, off = complete_sentences(text, 0)
    assert first == ["One.", "Two.", "Three."]
    more, off2 = complete_sentences(text, off)
    assert more == [] and off2 == off, "already-emitted text must not repeat"


def test_decimal_and_abbreviation_do_not_split():
    got, _ = complete_sentences("It costs $4.99 today.", 0)
    assert got == ["It costs $4.99 today."], f"split inside a decimal: {got}"

    got, _ = complete_sentences("Works with e.g. HubSpot fine.", 0)
    assert got == ["Works with e.g. HubSpot fine."], f"split on abbreviation: {got}"


def test_question_and_exclamation_terminate():
    got, _ = complete_sentences("Really? Yes! Ok.", 0)
    assert got == ["Really?", "Yes!", "Ok."]


def test_flush_remainder_picks_up_unterminated_tail():
    text = "All done. And a trailing thought"
    got, off = complete_sentences(text, 0)
    assert got == ["All done."]
    assert flush_remainder(text, off) == "And a trailing thought"
    assert flush_remainder("All done.", len("All done.")) == ""


def test_end_to_end_streaming_simulation():
    """Char-by-char delivery: assert the spoken output equals the true reply."""
    truth = json.loads(FULL)["reply"]
    spoken: list[str] = []
    emitted = 0
    buf = ""
    for ch in FULL:
        buf += ch
        prefix = extract_string_prefix(buf, "reply")
        sentences, emitted = complete_sentences(prefix, emitted)
        spoken.extend(sentences)
    prefix = extract_string_prefix(buf, "reply")
    if tail := flush_remainder(prefix, emitted):
        spoken.append(tail)

    assert " ".join(spoken) == truth, f"spoke {' '.join(spoken)!r}, expected {truth!r}"
    assert len(spoken) == 2, f"expected 2 sentences, got {spoken}"


def test_complete_string_withholds_until_terminated():
    """
    The delivery fields drive TTS settings, so a prefix is worse than nothing:
    acting on "emp" would set an emotion that does not exist.
    """
    partial = '{"emotion": "empath'
    assert extract_complete_string(partial, "emotion") is None

    done = '{"emotion": "empathetic", "speed": "slow"'
    assert extract_complete_string(done, "emotion") == "empathetic"
    assert extract_complete_string(done, "speed") == "slow"


def test_complete_string_absent_key_is_none():
    assert extract_complete_string('{"reply": "hi"}', "emotion") is None
    assert extract_complete_string("", "emotion") is None


def test_complete_string_ignores_value_before_colon():
    """A key that has arrived but whose value has not must not read ahead."""
    assert extract_complete_string('{"emotion"', "emotion") is None
    assert extract_complete_string('{"emotion":', "emotion") is None
    assert extract_complete_string('{"emotion": ', "emotion") is None


def test_complete_string_survives_reply_arriving_first():
    """
    Field order is a schema decision, not a parser guarantee. Extraction must not
    depend on emotion preceding reply.
    """
    buf = '{"reply": "Sure thing.", "emotion": "friendly"}'
    assert extract_complete_string(buf, "emotion") == "friendly"


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print(f"  ok  {t.__name__}")
    print(f"\n{len(tests)} passed")
