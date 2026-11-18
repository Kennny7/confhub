"""Tests for provider capability reporting."""

import pytest
from unittest.mock import MagicMock, patch
from pathlib import Path

from confhub.enums import MeetingPlatform
from confhub.providers.base import ProviderCapabilities
from confhub.providers.google_meet import GoogleMeetProvider
from confhub.providers.teams import TeamsGatewayProvider
from confhub.providers.zoom import ZoomProvider
from confhub.providers.webex import WebexProvider
from confhub.providers.registry import ProviderRegistry


def _make_settings(**kwargs):
    settings = MagicMock()
    settings.teams_gateway_configured = False
    settings.teams_recording_gateway_enabled = False
    settings.google_token_file = Path("/nonexistent/token.json")
    settings.google_scopes = ["https://www.googleapis.com/auth/meetings.space.readonly"]
    settings.zoom_token_file = Path("/nonexistent/zoom-token.json")
    settings.zoom_oauth_client_id = ""
    settings.zoom_oauth_client_secret = ""
    settings.webex_token_file = Path("/nonexistent/webex-token.json")
    settings.webex_oauth_client_id = ""
    settings.webex_oauth_client_secret = ""
    for k, v in kwargs.items():
        setattr(settings, k, v)
    return settings


def test_teams_unavailable_when_not_configured():
    settings = _make_settings(teams_gateway_configured=False)
    provider = TeamsGatewayProvider(settings)
    caps = provider.capabilities()
    assert caps.available is False
    assert caps.can_join_live is False


def test_teams_available_when_configured():
    settings = _make_settings(teams_gateway_configured=True)
    provider = TeamsGatewayProvider(settings)
    caps = provider.capabilities()
    assert caps.available is True
    assert caps.can_join_live is True


def test_google_meet_unavailable_without_token():
    settings = _make_settings()
    provider = GoogleMeetProvider(settings)
    caps = provider.capabilities()
    assert caps.available is False
    assert caps.can_join_live is False
    assert caps.can_fetch_attendance is False


def test_zoom_unavailable_without_credentials():
    settings = _make_settings()
    provider = ZoomProvider(settings)
    # zoom_configured returns False when no token file and no client credentials
    settings.zoom_configured = False
    caps = provider.capabilities()
    assert caps.platform == MeetingPlatform.ZOOM


def test_webex_unavailable_without_credentials():
    settings = _make_settings()
    settings.webex_configured = False
    provider = WebexProvider(settings)
    caps = provider.capabilities()
    assert caps.platform == MeetingPlatform.WEBEX


def test_registry_has_all_four_platforms():
    settings = _make_settings()
    registry = ProviderRegistry(settings)
    caps = registry.all_capabilities()
    platforms = {c.platform for c in caps}
    assert MeetingPlatform.TEAMS in platforms
    assert MeetingPlatform.GOOGLE_MEET in platforms
    assert MeetingPlatform.ZOOM in platforms
    assert MeetingPlatform.WEBEX in platforms


def test_registry_get_raises_for_unknown():
    settings = _make_settings()
    registry = ProviderRegistry(settings)
    with pytest.raises(ValueError):
        registry.get(MeetingPlatform.UNKNOWN)
