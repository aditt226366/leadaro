"""
    python services/agent/test_ivr.py

Covers menu parsing and selection. The async playback loop needs a live room,
so it is exercised by the smoke call rather than here.
"""
from ivr import IvrMenu, MenuOption, VALID_DIGITS

RAW = {
    "enabled": True,
    "greeting": "Thanks for calling Leadaro.",
    "timeout_seconds": 5,
    "invalid_message": "Sorry, I didn't get that.",
    "repeat_limit": 2,
    "options": [
        {"digit": "1", "label": "for sales", "action": "ai_agent"},
        {"digit": "2", "label": "for support", "action": "transfer",
         "target": "+14155550123", "message": "Connecting you now."},
        {"digit": "9", "label": "to leave a message", "action": "voicemail"},
    ],
}


def test_parses_options():
    m = IvrMenu.from_json(RAW)
    assert m.enabled is True
    assert len(m.options) == 3
    assert m.find("2").action == "transfer"
    assert m.find("2").target == "+14155550123"
    assert m.find("9").action == "voicemail"


def test_unknown_digit_returns_none():
    m = IvrMenu.from_json(RAW)
    assert m.find("5") is None
    assert m.find("") is None


def test_non_keypad_digits_are_dropped():
    """A stray 'A' in config must not become an unreachable option."""
    m = IvrMenu.from_json({**RAW, "options": [
        {"digit": "1", "label": "ok"},
        {"digit": "A", "label": "not a keypad key"},
        {"digit": "#", "label": "hash is valid"},
    ]})
    assert [o.digit for o in m.options] == ["1", "#"]


def test_star_and_hash_are_valid():
    assert "*" in VALID_DIGITS and "#" in VALID_DIGITS
    m = IvrMenu.from_json({**RAW, "options": [{"digit": "*", "label": "to repeat"}]})
    assert m.find("*").label == "to repeat"


def test_spoken_prompt_reads_naturally():
    m = IvrMenu.from_json(RAW)
    p = m.spoken_prompt()
    assert p.startswith("Thanks for calling Leadaro.")
    assert "Press 1 for sales." in p
    assert "Press 2 for support." in p
    # No markdown, no list syntax — this gets read aloud.
    assert "*" not in p and "-" not in p


def test_empty_menu_is_disabled_by_default():
    m = IvrMenu.from_json({})
    assert m.enabled is False
    assert m.options == []
    m2 = IvrMenu.from_json(None)
    assert m2.enabled is False


def test_defaults_fill_in_when_absent():
    m = IvrMenu.from_json({"enabled": True, "options": [{"digit": "1", "label": "x"}]})
    assert m.timeout_seconds == 6
    assert m.repeat_limit == 2
    assert m.invalid_message                     # never blank — it gets spoken
    assert m.options[0].action == "ai_agent"     # safe default


def test_options_without_labels_are_kept_but_not_announced():
    """A digit with no label still routes; it just isn't read out."""
    m = IvrMenu.from_json({**RAW, "options": [
        {"digit": "1", "label": "for sales"},
        {"digit": "0", "label": "", "action": "transfer"},
    ]})
    assert m.find("0") is not None
    assert "Press 0" not in m.spoken_prompt()


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print(f"  ok  {t.__name__}")
    print(f"\n{len(tests)} passed")
