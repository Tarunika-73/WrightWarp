import pytest

from app.core.lead_time import (
    LEAD_TIME_DAYS,
    LEAD_TIME_WINDOWS,
    get_lead_time_window,
    is_supported_lead_day,
)


def test_lead_time_windows_match_spec():
    assert LEAD_TIME_DAYS == (1, 7, 15, 30, 45)
    assert [w.name for w in LEAD_TIME_WINDOWS] == ["T+1", "T+7", "T+15", "T+30", "T+45"]


@pytest.mark.parametrize("days", [1, 7, 15, 30, 45])
def test_supported_lead_days_are_recognized(days):
    assert is_supported_lead_day(days)


@pytest.mark.parametrize("days", [0, 2, 3, 14, 60, -1])
def test_unsupported_lead_days_are_rejected(days):
    assert not is_supported_lead_day(days)


def test_get_lead_time_window_by_days():
    window = get_lead_time_window(days=15)
    assert window.name == "T+15"


def test_get_lead_time_window_by_name():
    window = get_lead_time_window(name="T+30")
    assert window.days == 30


def test_get_lead_time_window_invalid_raises():
    with pytest.raises(ValueError):
        get_lead_time_window(days=99)
