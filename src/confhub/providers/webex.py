"""Cisco Webex provider adapter.

Webex does not expose a programmatic join API for live call participation
as a user (only the Webex Meetings SDK for native apps supports that).
This adapter:

1. Manages OAuth2 tokens for the user's Webex account.
2. Resolves meeting keys / SIP addresses to Webex join URLs.
3. Retrieves post-meeting participant reports via the Webex API.
4. Returns the constructed join URL so the user can open it.

Live audio/video media is NOT captured by this adapter.
"""

import json
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

import httpx

from confhub.config import Settings
from confhub.enums import MeetingPlatform
from confhub.models import Meeting
from confhub.providers.base import (
    JoinResult,
    ProviderCapabilities,
    ProviderConfigurationError,
    ProviderError,
)

WEBEX_API_ROOT = "https://webexapis.com/v1"
WEBEX_OAUTH_TOKEN_URL = "https://webexapis.com/v1/access_token"


class WebexProvider:
    """Webex adapter: OAuth token management, meeting URL resolution, post-meeting reports."""

    platform = MeetingPlatform.WEBEX

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def capabilities(self) -> ProviderCapabilities:
        configured = self.settings.webex_configured
        return ProviderCapabilities(
            platform=self.platform,
            available=configured,
            can_join_live=configured,
            can_fetch_attendance=configured,
            can_fetch_transcripts=False,
            can_fetch_recordings=configured,
            can_record_live=False,
            explanation=(
                "Webex OAuth is configured. The adapter resolves meeting keys to join URLs and "
                "can retrieve post-meeting attendance and recording reports."
                if configured
                else (
                    "Run `confhub webex-auth` to connect your Webex account. "
                    "Set WEBEX_OAUTH_CLIENT_ID and WEBEX_OAUTH_CLIENT_SECRET first."
                )
            ),
        )

    def _load_token(self) -> dict[str, Any]:
        token_path: Path = self.settings.webex_token_file
        if not token_path.exists():
            raise ProviderConfigurationError(
                f"Webex token file not found: {token_path}. Run `confhub webex-auth`."
            )
        return json.loads(token_path.read_text(encoding="utf-8"))

    def _save_token(self, token_data: dict[str, Any]) -> None:
        token_path: Path = self.settings.webex_token_file
        token_path.parent.mkdir(parents=True, exist_ok=True)
        token_path.write_text(json.dumps(token_data), encoding="utf-8")
        try:
            token_path.chmod(0o600)
        except Exception:
            pass

    async def _get_access_token(self) -> str:
        token_data = self._load_token()
        if token_data.get("expires_at", 0) < time.time() + 60:
            if not token_data.get("refresh_token"):
                raise ProviderConfigurationError(
                    "Webex access token expired and no refresh token is available. "
                    "Re-run `confhub webex-auth`."
                )
            token_data = await self._refresh_token(token_data["refresh_token"])
        return str(token_data["access_token"])

    async def _refresh_token(self, refresh_token: str) -> dict[str, Any]:
        if not self.settings.webex_oauth_client_id or not self.settings.webex_oauth_client_secret:
            raise ProviderConfigurationError(
                "WEBEX_OAUTH_CLIENT_ID and WEBEX_OAUTH_CLIENT_SECRET are required to refresh tokens."
            )
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    WEBEX_OAUTH_TOKEN_URL,
                    data={
                        "grant_type": "refresh_token",
                        "client_id": self.settings.webex_oauth_client_id,
                        "client_secret": self.settings.webex_oauth_client_secret,
                        "refresh_token": refresh_token,
                    },
                )
                response.raise_for_status()
                new_token = response.json()
                new_token["expires_at"] = time.time() + int(new_token.get("expires_in", 3600))
                self._save_token(new_token)
                return new_token
        except httpx.HTTPError as error:
            raise ProviderError(f"Webex token refresh failed: {error}") from error

    async def _api_get(self, path: str, params: dict[str, str] | None = None) -> dict[str, Any]:
        access_token = await self._get_access_token()
        url = f"{WEBEX_API_ROOT}/{path.lstrip('/')}"
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(
                    url,
                    params=params,
                    headers={"Authorization": f"Bearer {access_token}"},
                )
                response.raise_for_status()
                return response.json()
        except httpx.HTTPError as error:
            raise ProviderError(f"Webex API request failed: {error}") from error

    def _build_join_url(self, meeting: Meeting) -> str:
        if meeting.join_url:
            return meeting.join_url
        if meeting.join_code:
            # Webex meeting numbers can be used as: https://webex.com/j/MEETING_NUMBER
            meeting_key = meeting.join_code.replace(" ", "")
            return f"https://webex.com/j/{meeting_key}"
        raise ProviderConfigurationError(
            "Meeting has neither a join_url nor a join_code. Set one before joining."
        )

    async def join(self, meeting: Meeting, *, display_name: str = "") -> JoinResult:
        """Return a JoinResult with the Webex join URL.

        The user must open the URL in their Webex app or browser.
        """
        join_url = self._build_join_url(meeting)
        effective_name = display_name or meeting.display_name_override or "Participant"
        return JoinResult(
            provider_call_id=meeting.join_code or meeting.join_url,
            state="url_ready",
            display_name=effective_name,
            details={"join_url": join_url, "note": "Open this URL in Webex to join as yourself."},
        )

    async def fetch_meeting_participants(self, meeting_id: str) -> dict[str, Any]:
        """Fetch participant list for a Webex meeting."""
        return await self._api_get("meetingParticipants", params={"meetingId": meeting_id})

    async def fetch_meeting_recordings(self, meeting_id: str) -> dict[str, Any]:
        """Fetch recording list for a Webex meeting."""
        return await self._api_get("recordings", params={"meetingId": meeting_id})

    def build_oauth_authorization_url(self, state: str = "") -> str:
        if not self.settings.webex_oauth_client_id:
            raise ProviderConfigurationError(
                "WEBEX_OAUTH_CLIENT_ID is required to initiate the OAuth flow."
            )
        params: dict[str, str] = {
            "response_type": "code",
            "client_id": self.settings.webex_oauth_client_id,
            "redirect_uri": self.settings.webex_oauth_redirect_uri,
            "scope": "meeting:schedules_read meeting:participants_read spark:kms",
        }
        if state:
            params["state"] = state
        return f"https://webexapis.com/v1/authorize?{urlencode(params)}"

    async def exchange_code_for_token(self, code: str) -> dict[str, Any]:
        if not self.settings.webex_oauth_client_id or not self.settings.webex_oauth_client_secret:
            raise ProviderConfigurationError(
                "WEBEX_OAUTH_CLIENT_ID and WEBEX_OAUTH_CLIENT_SECRET are required."
            )
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    WEBEX_OAUTH_TOKEN_URL,
                    data={
                        "grant_type": "authorization_code",
                        "client_id": self.settings.webex_oauth_client_id,
                        "client_secret": self.settings.webex_oauth_client_secret,
                        "code": code,
                        "redirect_uri": self.settings.webex_oauth_redirect_uri,
                    },
                )
                response.raise_for_status()
                token_data = response.json()
                token_data["expires_at"] = time.time() + int(token_data.get("expires_in", 3600))
                self._save_token(token_data)
                return token_data
        except httpx.HTTPError as error:
            raise ProviderError(f"Webex token exchange failed: {error}") from error
