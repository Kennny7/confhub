"""Tests for Pydantic schemas: validation, join code/URL rules, join mode."""

import pytest
from datetime import datetime, timezone, timedelta

from confhub.enums import JoinMode, MeetingPlatform
from confhub.schemas import MeetingCreate, ProfileUpdate


def _future_window():
    start = datetime.now(timezone.utc) + timedelta(hours=1)
    end = start + timedelta(hours=1)
    return start, end


# ---------------------------------------------------------------------------
# ProfileUpdate
# ---------------------------------------------------------------------------

def test_profile_update_requires_display_name():
    with pytest.raises(Exception):
        ProfileUpdate(display_name="", email="x@x.com", timezone_name="UTC")


def test_profile_update_valid():
    p = ProfileUpdate(display_name="Alice", email="alice@example.com", timezone_name="Asia/Kolkata")
    assert p.display_name == "Alice"


# ---------------------------------------------------------------------------
# MeetingCreate - URL path
# ---------------------------------------------------------------------------

def test_meeting_create_requires_url_or_code():
    start, end = _future_window()
    with pytest.raises(Exception, match="join_url.*join_code"):
        MeetingCreate(
            title="Test",
            platform=MeetingPlatform.TEAMS,
            join_url="",
            join_code="",
            scheduled_start_at=start,
            scheduled_end_at=end,
        )


def test_meeting_create_valid_with_url():
    start, end = _future_window()
    m = MeetingCreate(
        title="Project sync",
        platform=MeetingPlatform.TEAMS,
        join_url="https://teams.microsoft.com/l/meetup-join/example",
        scheduled_start_at=start,
        scheduled_end_at=end,
    )
    assert m.join_mode == JoinMode.AS_USER


def test_meeting_create_valid_with_code_zoom():
    start, end = _future_window()
    m = MeetingCreate(
        title="Zoom call",
        platform=MeetingPlatform.ZOOM,
        join_code="123 456 789",
        join_passcode="secret",
        scheduled_start_at=start,
        scheduled_end_at=end,
    )
    assert m.join_code == "123 456 789"
    assert m.join_passcode == "secret"


def test_meeting_create_url_host_mismatch_raises():
    start, end = _future_window()
    with pytest.raises(Exception):
        MeetingCreate(
            title="Bad URL",
            platform=MeetingPlatform.TEAMS,
            join_url="https://meet.google.com/abc-def-ghi",
            scheduled_start_at=start,
            scheduled_end_at=end,
        )


def test_meeting_create_end_before_start_raises():
    start, end = _future_window()
    with pytest.raises(Exception, match="after"):
        MeetingCreate(
            title="Bad time",
            platform=MeetingPlatform.ZOOM,
            join_code="123456789",
            scheduled_start_at=end,
            scheduled_end_at=start,
        )


def test_meeting_create_auto_join_requires_authorized():
    start, end = _future_window()
    with pytest.raises(Exception, match="join_authorized"):
        MeetingCreate(
            title="Auto join without auth",
            platform=MeetingPlatform.TEAMS,
            join_url="https://teams.microsoft.com/l/meetup-join/example",
            scheduled_start_at=start,
            scheduled_end_at=end,
            auto_join=True,
            join_authorized=False,
        )


def test_meeting_create_no_embedded_credentials_in_url():
    start, end = _future_window()
    with pytest.raises(Exception, match="credentials"):
        MeetingCreate(
            title="Cred URL",
            platform=MeetingPlatform.TEAMS,
            join_url="https://user:pass@teams.microsoft.com/l/meetup-join/example",
            scheduled_start_at=start,
            scheduled_end_at=end,
        )


def test_meeting_create_webex_url():
    start, end = _future_window()
    m = MeetingCreate(
        title="Webex call",
        platform=MeetingPlatform.WEBEX,
        join_url="https://webex.com/join/someroom",
        scheduled_start_at=start,
        scheduled_end_at=end,
    )
    assert m.platform == MeetingPlatform.WEBEX


def test_meeting_create_as_bot_mode():
    start, end = _future_window()
    m = MeetingCreate(
        title="Bot mode",
        platform=MeetingPlatform.TEAMS,
        join_url="https://teams.microsoft.com/l/meetup-join/example",
        scheduled_start_at=start,
        scheduled_end_at=end,
        join_mode=JoinMode.AS_BOT,
        display_name_override="ConfHub Assistant (Bot)",
    )
    assert m.join_mode == JoinMode.AS_BOT
