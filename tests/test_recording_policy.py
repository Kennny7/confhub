"""Tests for recording policy evaluation."""

import pytest
from unittest.mock import MagicMock
from pathlib import Path

from confhub.enums import MeetingPlatform, RecordingStatus
from confhub.providers.base import ProviderCapabilities
from confhub.services.recording_service import evaluate_recording_eligibility


def _make_capabilities(can_record_live: bool = True) -> ProviderCapabilities:
    return ProviderCapabilities(
        platform=MeetingPlatform.TEAMS,
        available=True,
        can_join_live=True,
        can_fetch_attendance=False,
        can_fetch_transcripts=False,
        can_fetch_recordings=False,
        can_record_live=can_record_live,
        explanation="test",
    )


def _make_settings(recording_enabled: bool = True):
    settings = MagicMock()
    settings.recording_enabled = recording_enabled
    return settings


def _make_meeting(**kwargs):
    meeting = MagicMock()
    meeting.recording_requested = kwargs.get("recording_requested", True)
    meeting.organizer_recording_authorized = kwargs.get("organizer_recording_authorized", True)
    meeting.participant_consent_state = kwargs.get("participant_consent_state", "granted")
    return meeting


def test_recording_blocked_when_globally_disabled():
    result = evaluate_recording_eligibility(
        _make_meeting(),
        _make_capabilities(),
        _make_settings(recording_enabled=False),
    )
    assert result["eligible"] is False
    assert any("disabled" in r for r in result["blocking_reasons"])


def test_recording_blocked_without_participant_consent():
    result = evaluate_recording_eligibility(
        _make_meeting(participant_consent_state="pending"),
        _make_capabilities(),
        _make_settings(),
    )
    assert result["eligible"] is False
    assert any("consent" in r.lower() for r in result["blocking_reasons"])


def test_recording_blocked_when_provider_cannot_record():
    result = evaluate_recording_eligibility(
        _make_meeting(),
        _make_capabilities(can_record_live=False),
        _make_settings(),
    )
    assert result["eligible"] is False


def test_recording_eligible_when_all_conditions_met():
    result = evaluate_recording_eligibility(
        _make_meeting(
            recording_requested=True,
            organizer_recording_authorized=True,
            participant_consent_state="granted",
        ),
        _make_capabilities(can_record_live=True),
        _make_settings(recording_enabled=True),
    )
    assert result["eligible"] is True
    assert result["blocking_reasons"] == []
    # Service does not start recording; can_start_recording stays False.
    assert result["can_start_recording"] is False
