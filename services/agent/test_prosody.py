"""
    python services/agent/test_prosody.py

FIX 4 — the campaign prosody controls that map to REAL Cartesia sonic-3 params.
Only Speech Intensity (-> volume) and Natural Pause (-> <break> markup) are
wired; Emotion Level / Energy Level / pitch have no sonic-3 parameter and are
intentionally not invented.
"""
from lk_llm import SPEED_SCALE
from worker import _prosody_from_config


def test_speed_scale_is_within_sonic3_range():
    # sonic-3 `speed` is valid between 0.6 and 2.0. The old -1..1 scale silently
    # sent invalid values (normal=0.0 dropped, slow/fast out of range).
    assert set(SPEED_SCALE) == {"slow", "normal", "fast"}
    for label, value in SPEED_SCALE.items():
        assert isinstance(value, float)
        assert 0.6 <= value <= 2.0, f"{label}={value} outside sonic-3 range"
    # Ordered slow < normal < fast, with the agreed values.
    assert SPEED_SCALE["slow"] == 0.8
    assert SPEED_SCALE["normal"] == 1.0
    assert SPEED_SCALE["fast"] == 1.3
    assert SPEED_SCALE["slow"] < SPEED_SCALE["normal"] < SPEED_SCALE["fast"]


def test_unset_config_sends_nothing():
    volume, pause = _prosody_from_config({})
    assert volume is None      # -> Cartesia default volume
    assert pause == ""


def test_speech_intensity_maps_to_volume_and_clamps_to_sonic3_range():
    assert _prosody_from_config({"speech_intensity": 1.5})[0] == 1.5
    # sonic-3 volume is 0.5-2.0; out-of-range values clamp rather than error.
    assert _prosody_from_config({"speech_intensity": 5.0})[0] == 2.0
    assert _prosody_from_config({"speech_intensity": 0.1})[0] == 0.5
    # a plain `volume` key is accepted too.
    assert _prosody_from_config({"volume": 0.8})[0] == 0.8
    # garbage is ignored, never crashes the session build.
    assert _prosody_from_config({"speech_intensity": "loud"})[0] is None


def test_natural_pause_emits_integer_ms_break_tag():
    _, pause = _prosody_from_config({"natural_pause": True, "pause_ms": 500})
    assert pause == '<break time="500ms"/>'
    # No decimals in the value — that is the tokenizer tag-split bug we dodge.
    assert "." not in pause
    # enabled without an explicit value -> a sensible default.
    assert _prosody_from_config({"pause_controls": True})[1] == '<break time="350ms"/>'
    # a zero pause disables the tag rather than emitting <break time="0ms"/>.
    assert _prosody_from_config({"natural_pause": True, "pause_ms": 0})[1] == ""


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print(f"  ok  {t.__name__}")
    print(f"\n{len(tests)} passed")
