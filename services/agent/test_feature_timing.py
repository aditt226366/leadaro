"""
    python services/agent/test_feature_timing.py

Feature timing is split: the LIVE turn only converses — reply + prosody + the
compact control signals the rules engine needs to steer the call (objection,
booking, close, transfer). The SIX analytics features are computed AFTER the
call from the saved transcript (the turns table, read by post_call.py).

This encodes that boundary as an invariant on the schemas, so a future change
that tries to sneak an after-call feature back onto the live turn fails here.
"""
from brain import TurnOutput
from post_call import Summary

# Outputs that belong ONLY to the post-call transcript pass, never the live turn.
AFTER_CALL_ONLY = {
    "summary", "key_points", "action_items", "pain_points",
    "qualification_tier", "qualification_score", "sentiment_trajectory",
    "next_best_action", "followup_recommendation",
}


def test_live_turn_output_carries_no_after_call_feature():
    leaked = set(TurnOutput.model_fields) & AFTER_CALL_ONLY
    assert not leaked, f"after-call features leaked onto the live turn: {leaked}"


def test_live_turn_keeps_only_reply_prosody_and_control_signals():
    # reply + prosody (for TTS) + the compact control signals rules.decide uses.
    assert set(TurnOutput.model_fields) == {
        "emotion", "speed", "reply", "pitch",
        "intent", "sentiment", "next_action",
    }


def test_all_six_features_live_on_the_post_call_analysis():
    fields = set(Summary.model_fields)
    for f in ("summary", "overall_sentiment", "intents", "qualification_tier",
              "next_best_action", "followup_recommendation"):
        assert f in fields, f"post-call analysis missing {f}"


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print(f"  ok  {t.__name__}")
    print(f"\n{len(tests)} passed")
