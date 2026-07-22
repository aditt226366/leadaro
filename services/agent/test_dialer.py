"""
    python services/agent/test_dialer.py

Covers the calling-window gate. This is the logic that stops the system phoning
someone at 3am because the server happens to be in another timezone — worth a
test even though it looks trivial.
"""
from datetime import datetime, timezone

from dialer import _parse_hhmm, within_business_hours

# 2026-05-18 is a Monday, 2026-05-23 a Saturday.
def utc(y, mo, d, h, mi=0):
    return datetime(y, mo, d, h, mi, tzinfo=timezone.utc)


BASE = {
    "timezone": "America/New_York",
    "business_hours": {"start": "09:00", "end": "18:00"},
    "weekdays_only": True,
    "weekends_only": False,
    "holiday_rules": {},
}


def test_inside_window_local_time():
    # 15:00 UTC = 11:00 EDT on a Monday.
    assert within_business_hours(BASE, utc(2026, 5, 18, 15)) is True


def test_before_open_local_time():
    # 12:00 UTC = 08:00 EDT — an hour before open.
    assert within_business_hours(BASE, utc(2026, 5, 18, 12)) is False


def test_after_close_local_time():
    # 23:00 UTC = 19:00 EDT — an hour after close.
    assert within_business_hours(BASE, utc(2026, 5, 18, 23)) is False


def test_timezone_is_the_campaigns_not_the_servers():
    """
    The bug this guards: 03:00 UTC is inside 09:00-18:00 in Asia/Kolkata but
    is the middle of the night in New York. Same instant, opposite answers.
    """
    at_0300_utc = utc(2026, 5, 18, 3)
    ny = {**BASE, "timezone": "America/New_York"}
    kolkata = {**BASE, "timezone": "Asia/Kolkata"}   # 08:30 IST
    assert within_business_hours(ny, at_0300_utc) is False
    # 03:00 UTC = 08:30 IST, still before a 09:00 open.
    assert within_business_hours(kolkata, at_0300_utc) is False
    # 05:00 UTC = 10:30 IST — open.
    assert within_business_hours(kolkata, utc(2026, 5, 18, 5)) is True


def test_weekdays_only_blocks_saturday():
    saturday = utc(2026, 5, 23, 15)   # 11:00 EDT Saturday
    assert within_business_hours(BASE, saturday) is False


def test_weekends_only_blocks_monday():
    cfg = {**BASE, "weekdays_only": False, "weekends_only": True}
    assert within_business_hours(cfg, utc(2026, 5, 18, 15)) is False   # Mon
    assert within_business_hours(cfg, utc(2026, 5, 23, 15)) is True    # Sat


def test_holiday_dates_block_calling():
    cfg = {**BASE, "holiday_rules": {"dates": ["2026-05-18"]}}
    assert within_business_hours(cfg, utc(2026, 5, 18, 15)) is False
    assert within_business_hours(cfg, utc(2026, 5, 19, 15)) is True


def test_malformed_hours_fall_back_to_nine_am():
    assert _parse_hhmm("garbage") == _parse_hhmm("09:00")
    assert _parse_hhmm(None) == _parse_hhmm("09:00")
    # A broken config must not silently open a 24h window.
    cfg = {**BASE, "business_hours": {"start": "garbage", "end": "18:00"}}
    assert within_business_hours(cfg, utc(2026, 5, 18, 12)) is False   # 08:00 EDT


def test_missing_timezone_defaults_to_utc():
    cfg = {k: v for k, v in BASE.items() if k != "timezone"}
    assert within_business_hours(cfg, utc(2026, 5, 18, 12)) is True    # 12:00 UTC
    assert within_business_hours(cfg, utc(2026, 5, 18, 3)) is False


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print(f"  ok  {t.__name__}")
    print(f"\n{len(tests)} passed")
