"""Zoom OAuth2 provider adapter.

Zoom does not provide a programmatic API for joining a meeting as a live
participant on behalf of a user (only the Zoom Meeting SDK for native apps
does this). What this adapter does:

1. Manage OAuth2 tokens for the user's Zoom account.
2. Resolve meeting IDs / join codes to full join URLs.
3. Retrieve post-meeting reports (attendance, cloud recordings) via the Zoom API.
4. Return the constructed join URL as the JoinResult so the user can open it.

Live audio/video media is NOT captured by this adapter; the user must
open the returned URL in their Zoom client or browser.
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

ZOOM_API_ROOT = "https://api.zoom.us/v2"
ZOOM_OAUTH_TOKEN_URL = "https://zoom.us/oauth/token"


class ZoomProvider:
    """Zoom adapter: OAuth token management, meeting URL resolution, post-meeting reports."""

    platform = MeetingPlatform.ZOOM

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def capabilities(self) -> ProviderCapabilities:
        configured = self.settings.zoom_configured
        return ProviderCapabilities(
            platform=self.platform,
            available=configured,
            can_join_live=configured,
            can_fetch_attendance=configured,
            can_fetch_transcripts=False,
            can_fetch_recordings=configured,
            can_record_live=False,
            explanation=(
                "Zoom OAuth is configured. The adapter resolves meeting IDs to join URLs and "
                "can retrieve post-meeting attendance and cloud recording reports."
                if configured
                else (
                    "Run `confhub zoom-auth` to connect your Zoom account. "
                    "Set ZOOM_OAUTH_CLIENT_ID and ZOOM_OAUTH_CLIENT_SECRET first."
                )
            ),
        )

    def _load_token(self) -> dict[str, Any]:
        token_path: Path = self.settings.zoom_token_file
        if not token_path.exists():
            raise ProviderConfigurationError(
                f"Zoom token file not found: {token_path}. Run `confhub zoom-auth`."
            )
        return json.loads(token_path.read_text(encoding="utf-8"))

    def _save_token(self, token_data: dict[str, Any]) -> None:
        token_path: Path = self.settings.zoom_token_file
        token_path.parent.mkdir(parents=True, exist_ok=True)
        token_path.write_text(json.dumps(token_data), encoding="utf-8")
        try:
            token_path.chmod(0o600)
        except Exception:
            pass

    async def _get_access_token(self) -> str:
        token_data = self._load_token()
        # Refresh if expired (Zoom tokens expire in 3600 seconds).
        if token_data.get("expires_at", 0) < time.time() + 60:
            if not token_data.get("refresh_token"):
                raise ProviderConfigurationError(
                    "Zoom access token expired and no refresh token is available. "
                    "Re-run `confhub zoom-auth`."
                )
            token_data = await self._refresh_token(token_data["refresh_token"])
        return str(token_data["access_token"])

    async def _refresh_token(self, refresh_token: str) -> dict[str, Any]:
        if not self.settings.zoom_oauth_client_id or not self.settings.zoom_oauth_client_secret:
            raise ProviderConfigurationError(
                "ZOOM_OAUTH_CLIENT_ID and ZOOM_OAUTH_CLIENT_SECRET are required to refresh tokens."
            )
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    ZOOM_OAUTH_TOKEN_URL,
                    data={"grant_type": "refresh_token", "refresh_token": refresh_token},
                    auth=(self.settings.zoom_oauth_client_id, self.settings.zoom_oauth_client_secret),
                )
                response.raise_for_status()
                new_token = response.json()
                new_token["expires_at"] = time.time() + int(new_token.get("expires_in", 3600))
                self._save_token(new_token)
                return new_token
        except httpx.HTTPError as error:
            raise ProviderError(f"Zoom token refresh failed: {error}") from error

    async def _api_get(self, path: str, params: dict[str, str] | None = None) -> dict[str, Any]:
        access_token = await self._get_access_token()
        url = f"{ZOOM_API_ROOT}/{path.lstrip('/')}"
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
            raise ProviderError(f"Zoom API request failed: {error}") from error

    def _build_join_url(self, meeting: Meeting) -> str:
        """Construct a Zoom join URL from the stored join_code / join_url."""
        if meeting.join_url:
            return meeting.join_url
        if meeting.join_code:
            # Normalize: Zoom meeting IDs are numeric; passcodes are appended via query param.
            meeting_id = meeting.join_code.replace(" ", "").replace("-", "")
            base = f"https://zoom.us/j/{meeting_id}"
            if meeting.join_passcode:
                return f"{base}?pwd={meeting.join_passcode}"
            return base
        raise ProviderConfigurationError(
            "Meeting has neither a join_url nor a join_code. Set one before joining."
        )

    async def join(self, meeting: Meeting, *, display_name: str = "") -> JoinResult:
        """Return a JoinResult with the constructed Zoom join URL.

        The user must open the URL in their Zoom desktop client or browser.
        This adapter does not capture live media.
        """
        join_url = self._build_join_url(meeting)
        effective_name = display_name or meeting.display_name_override or "Participant"
        return JoinResult(
            provider_call_id=meeting.join_code or meeting.join_url,
            state="url_ready",
            display_name=effective_name,
            details={"join_url": join_url, "note": "Open this URL in Zoom to join as yourself."},
        )

    async def fetch_meeting_report(self, zoom_meeting_id: str) -> dict[str, Any]:
        """Fetch post-meeting participant report from Zoom API."""
        return await self._api_get(f"report/meetings/{zoom_meeting_id}/participants")

    async def fetch_cloud_recordings(self, zoom_meeting_id: str) -> dict[str, Any]:
        """Fetch cloud recording metadata for a meeting."""
        return await self._api_get(f"meetings/{zoom_meeting_id}/recordings")

    def build_oauth_authorization_url(self) -> str:
        """Build the Zoom OAuth authorization URL for the user to visit."""
        if not self.settings.zoom_oauth_client_id:
            raise ProviderConfigurationError(
                "ZOOM_OAUTH_CLIENT_ID is required to initiate the OAuth flow."
            )
        params = {
            "response_type": "code",
            "client_id": self.settings.zoom_oauth_client_id,
            "redirect_uri": self.settings.zoom_oauth_redirect_uri,
        }
        return f"https://zoom.us/oauth/authorize?{urlencode(params)}"

    async def exchange_code_for_token(self, code: str) -> dict[str, Any]:
        """Exchange an authorization code for an access token and save it."""
        if not self.settings.zoom_oauth_client_id or not self.settings.zoom_oauth_client_secret:
            raise ProviderConfigurationError(
                "ZOOM_OAUTH_CLIENT_ID and ZOOM_OAUTH_CLIENT_SECRET are required."
            )
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    ZOOM_OAUTH_TOKEN_URL,
                    data={
                        "grant_type": "authorization_code",
                        "code": code,
                        "redirect_uri": self.settings.zoom_oauth_redirect_uri,
                    },
                    auth=(self.settings.zoom_oauth_client_id, self.settings.zoom_oauth_client_secret),
                )
                response.raise_for_status()
                token_data = response.json()
                token_data["expires_at"] = time.time() + int(token_data.get("expires_in", 3600))
                self._save_token(token_data)
                return token_data
        except httpx.HTTPError as error:
            raise ProviderError(f"Zoom token exchange failed: {error}") from error
