"""Tests for consent, authorization, and service-layer flows."""

import asyncio
import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

from confhub.enums import JoinMode, MeetingPlatform, MeetingStatus, RecordingStatus
from confhub.models import Meeting
from confhub.services.meeting_service import (
    AuthorizationRequiredError,
    MeetingNotFoundError,
    cancel_meeting,
    join_meeting,
)
from confhub.providers.base import JoinResult, ProviderCapabilities


def _make_meeting(**kwargs):
    """Return a MagicMock that looks like a Meeting ORM instance.

    We use MagicMock rather than Meeting.__new__ because SQLAlchemy's
    instrumented attributes require a fully initialized mapper state which
    is only available inside a live session/engine context.
    """
    now = datetime.now(timezone.utc)
    defaults = dict(
        meeting_id="test-id-001",
        owner_email="user@example.com",
        title="Test Meeting",
        platform=MeetingPlatform.TEAMS.value,
        join_url="https://teams.microsoft.com/l/meetup-join/test",
        join_code="",
        join_passcode="",
        scheduled_start_at=now - timedelta(minutes=5),
        scheduled_end_at=now + timedelta(hours=1),
        status=MeetingStatus.SCHEDULED.value,
        join_mode=JoinMode.AS_USER.value,
        display_name_override="",
        join_authorized=False,
        auto_join=False,
        recording_requested=False,
        recording_status=RecordingStatus.NOT_REQUESTED.value,
        organizer_recording_authorized=False,
        participant_consent_state="pending",
        transcript_consent_confirmed=False,
        provider_call_id="",
        failure_reason="",
        note_taking_enabled=True,
        microphone_enabled=False,
        camera_enabled=False,
        notes=[],
        audit_events=[],
    )
    defaults.update(kwargs)
    meeting = MagicMock(spec=Meeting)
    for k, v in defaults.items():
        setattr(meeting, k, v)
    return meeting


@pytest.mark.asyncio
async def test_cancel_meeting_sets_status():
    session = AsyncMock()
    session.commit = AsyncMock()
    session.refresh = AsyncMock()
    meeting = _make_meeting()

    with patch("confhub.services.meeting_service.write_audit_event", new=AsyncMock()):
        result = await cancel_meeting(session, meeting, actor="test-user")

    assert result.status == MeetingStatus.CANCELLED.value
    assert result.auto_join is False


@pytest.mark.asyncio
async def test_cancel_already_cancelled_is_idempotent():
    session = AsyncMock()
    meeting = _make_meeting(status=MeetingStatus.CANCELLED.value)
    result = await cancel_meeting(session, meeting, actor="test-user")
    assert result.status == MeetingStatus.CANCELLED.value


@pytest.mark.asyncio
async def test_join_requires_confirm_flag():
    session = AsyncMock()
    settings = MagicMock()
    registry = MagicMock()
    meeting = _make_meeting(join_authorized=True)

    with pytest.raises(AuthorizationRequiredError):
        await join_meeting(session, settings, registry, meeting, confirm_join=False, actor="test")


@pytest.mark.asyncio
async def test_join_cannot_join_cancelled_meeting():
    session = AsyncMock()
    settings = MagicMock()
    registry = MagicMock()
    meeting = _make_meeting(status=MeetingStatus.CANCELLED.value, join_authorized=True)

    with pytest.raises(ValueError, match="Cannot join"):
        await join_meeting(session, settings, registry, meeting, confirm_join=True, actor="test")


@pytest.mark.asyncio
async def test_join_as_user_uses_profile_name():
    """When join_mode=as_user, the profile display_name should be used."""
    session = AsyncMock()
    profile_mock = MagicMock()
    profile_mock.display_name = "Jane Smith"
    session.get = AsyncMock(return_value=profile_mock)
    session.commit = AsyncMock()
    session.refresh = AsyncMock()

    settings = MagicMock()
    settings.default_display_name = "ConfHub Assistant (Bot)"
    settings.default_user_name = ""

    capabilities = ProviderCapabilities(
        platform=MeetingPlatform.TEAMS,
        available=True,
        can_join_live=True,
        can_fetch_attendance=False,
        can_fetch_transcripts=False,
        can_fetch_recordings=False,
        can_record_live=False,
        explanation="ok",
    )
    provider_mock = MagicMock()
    provider_mock.capabilities.return_value = capabilities
    provider_mock.join = AsyncMock(return_value=JoinResult(
        provider_call_id="call-123",
        state="joined",
        display_name="Jane Smith",
        details={},
    ))

    registry = MagicMock()
    registry.get.return_value = provider_mock

    meeting = _make_meeting(join_authorized=True, join_mode=JoinMode.AS_USER.value)

    with patch("confhub.services.meeting_service.write_audit_event", new=AsyncMock()):
        result = await join_meeting(
            session, settings, registry, meeting, confirm_join=True, actor="test"
        )

    provider_mock.join.assert_called_once()
    call_kwargs = provider_mock.join.call_args
    assert call_kwargs.kwargs.get("display_name") == "Jane Smith"
