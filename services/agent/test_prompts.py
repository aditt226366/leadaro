"""
Guards the prompt-cache invariant.

    python services/agent/test_prompts.py

The system prompt must be byte-identical for every call in a campaign. If it
isn't, every turn pays a cold cache write — slower and ~10x the token cost —
and nothing errors to tell you. This test is the tripwire. It needs no API key.
"""
import re

import prompts

CAMPAIGN = {
    "org_name": "Leadaro",
    "goal": "Book a 20 minute product demo",
    "language": "en",
    "voice_config": {"persona": "a friendly SDR"},
    "script": {
        "greeting": "Hi {{first_name}}, this is Emma from {{company}}.",
        "offer": "We automate outbound calling.",
        "cta": "Would a demo this week help?",
        "knowledge_base": "Pricing starts at $499/month.",
    },
}

LEAD_A = {"first_name": "Raj", "company": "Globex", "industry": "SaaS"}
LEAD_B = {"first_name": "Sarah", "company": "Initech", "industry": "Fintech"}


def test_system_prompt_is_identical_across_leads():
    """The whole cache strategy rests on this."""
    a = prompts.build_system(CAMPAIGN)
    b = prompts.build_system(CAMPAIGN)
    assert a == b, "build_system is not deterministic for identical input"


def test_system_prompt_contains_no_per_call_data():
    """
    Any lead field, timestamp or id inside the system prompt breaks caching.
    Checked by construction: build_system is never given the lead at all.
    """
    system = prompts.build_system(CAMPAIGN)
    for leaked in ("Raj", "Sarah", "Globex", "Initech"):
        assert leaked not in system, f"lead data {leaked!r} leaked into system prompt"

    # Digit runs that look like a timestamp or epoch.
    assert not re.search(r"\b\d{4}-\d{2}-\d{2}\b", system), "date in system prompt"
    assert not re.search(r"\b1[6-9]\d{8}\b", system), "epoch timestamp in system prompt"
    assert not re.search(
        r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b", system
    ), "uuid in system prompt"


def test_variables_render_per_lead_not_in_system():
    """Personalisation happens in the message turns, where it costs no cache."""
    a = prompts.opening_line(CAMPAIGN["script"], LEAD_A)
    b = prompts.opening_line(CAMPAIGN["script"], LEAD_B)
    assert "Raj" in a and "Globex" in a
    assert "Sarah" in b and "Initech" in b
    assert a != b
    # …and the system prompt still didn't move.
    assert prompts.build_system(CAMPAIGN) == prompts.build_system(CAMPAIGN)


def test_unknown_variables_get_sensible_fallbacks():
    """A missing first name must never render as literal '{{first_name}}'."""
    out = prompts.render("Hi {{first_name}} at {{company}}, re {{industry}}.", {})
    assert "{{" not in out, f"unsubstituted placeholder in: {out}"
    assert "there" in out


def test_spacing_variant_of_placeholder_also_renders():
    out = prompts.render("Hello {{ first_name }}!", {"first_name": "Ivy"})
    assert out == "Hello Ivy!"


def test_opening_line_always_discloses_ai():
    """
    Disclosure is a legal requirement in several jurisdictions, so the default
    must carry it even when a campaign supplies no greeting.
    """
    out = prompts.opening_line({}, LEAD_A)
    assert "AI" in out


def test_inbound_context_is_not_in_system_prompt():
    """Prior-call context varies per call — it belongs in the turns."""
    ctx = prompts.resumption_context(
        {"when": "Tuesday", "summary": "Asked about pricing", "outcome": "callback"}
    )
    assert "Tuesday" in ctx and "pricing" in ctx
    assert ctx not in prompts.build_system(CAMPAIGN)


def test_campaign_fields_drive_the_prompt():
    """The dashboard fields must actually reach the system prompt."""
    camp = {
        "org_name": "CEBOS", "type": "cold_calling", "goal": "book_meeting",
        "department": "Sales", "language": "ta",
        "voice_config": {"persona": "an account executive", "tone": "friendly"},
        "script": {"offer": "an AI calling platform"},
    }
    s = prompts.build_system(camp)
    assert "COLD outreach" in s                     # type → mode
    assert "Book a meeting" in s                    # goal → objective
    assert "Sales team" in s                        # department
    assert "friendly tone" in s                     # tone
    assert "an AI calling platform" in s            # script.offer
    assert "ONLY in Tamil" in s                     # language

    # An unknown type/goal is used, not dropped.
    other = prompts.build_system({"type": "webinar_invite", "goal": "rsvp_confirm"})
    assert "webinar invite" in other
    assert "rsvp confirm" in other


def test_type_and_goal_maps_cover_the_wizard_values():
    # Every value the wizard writes must have an explicit mapping (no silent gaps).
    for t in ("cold_calling", "follow_up", "demo_booking", "renewal_reminder",
              "customer_success", "recruitment", "promotional_campaign",
              "nps_campaign"):
        assert t in prompts.CAMPAIGN_TYPE_MODE, t
    for g in ("book_meeting", "qualify_lead", "follow_up"):
        assert g in prompts.CAMPAIGN_GOAL_OBJECTIVE, g


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print(f"  ok  {t.__name__}")
    print(f"\n{len(tests)} passed")
