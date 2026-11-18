from pathlib import Path
from typing import Any

import httpx
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials

from meetbridge.config import Settings
from meetbridge.enums import MeetingPlatform
from meetbridge.providers.base import (
    ProviderCapabilities,
    ProviderConfigurationError,
    ProviderError,
    UnsupportedCapabilityError,
)

class GoogleMeetProvider:
    """Official Google Meet REST API integration for post-meeting artifacts.

    The Meet REST API exposes conference records and artifacts. It does not
    provide a general-purpose endpoint for an external bot to join an existing
    call and consume its live media, so this adapter never simulates that ability.
    """

    platform = MeetingPlatform.GOOGLE_MEET
    api_root = "https://meet.googleapis.com/v2"

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def capabilities(self) -> ProviderCapabilities:
        token_file_exists = self.settings.google_token_file.exists()
        return ProviderCapabilities(
            platform=self.platform,
            available=token_file_exists,
            can_join_live=False,
            can_fetch_attendance=token_file_exists,
            can_fetch_transcripts=token_file_exists,
            can_fetch_recordings=token_file_exists,
            can_record_live=False,
            explanation=(
                "Google Meet REST API is configured for conference attendance and post-meeting "
                "artifacts. Live bot joining and live media capture are not exposed by this adapter."
                if token_file_exists
                else "Run `meetbridge google-auth` with an OAuth client file to enable post-meeting artifacts."
            ),
        )

    def _credentials(self) -> Credentials:
        token_path: Path = self.settings.google_token_file
        if not token_path.exists():
            raise ProviderConfigurationError(
                f"Google OAuth token file was not found: {token_path}. Run `meetbridge google-auth`."
            )
        try:
            credentials = Credentials.from_authorized_user_file(
                str(token_path), self.settings.google_scopes
            )
            if credentials.expired and credentials.refresh_token:
                credentials.refresh(Request())
                token_path.parent.mkdir(parents=True, exist_ok=True)
                token_path.write_text(credentials.to_json(), encoding="utf-8")
                token_path.chmod(0o600)
        except Exception as error:
            raise ProviderConfigurationError(f"Google OAuth credential refresh failed: {error}") from error
        if not credentials.valid or not credentials.token:
            raise ProviderConfigurationError("Google OAuth credentials are invalid or expired")
        return credentials

    async def _get(self, resource_path: str, params: dict[str, str] | None = None) -> dict[str, Any]:
        credentials = self._credentials()
        url = f"{self.api_root}/{resource_path.lstrip('/')}"
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(30.0)) as client:
                response = await client.get(
                    url,
                    params=params,
                    headers={"Authorization": f"Bearer {credentials.token}"},
                )
                response.raise_for_status()
                return response.json()
        except httpx.HTTPError as error:
            raise ProviderError(f"Google Meet API request failed: {error}") from error

    async def join(self, meeting: Any) -> Any:
        raise UnsupportedCapabilityError(
            "Live Google Meet bot joining is not available through the supported Meet REST API. "
            "This provider can fetch attendance and artifacts after the conference."
        )

    async def _list_all(
        self,
        resource_path: str,
        response_field: str,
    ) -> list[dict[str, Any]]:
        all_items: list[dict[str, Any]] = []
        next_page_token = ""
        while True:
            query_parameters = {"pageSize": "100"}
            if next_page_token:
                query_parameters["pageToken"] = next_page_token
            response = await self._get(resource_path, query_parameters)
            all_items.extend(response.get(response_field, []))
            next_page_token = str(response.get("nextPageToken", ""))
            if not next_page_token:
                return all_items

    async def fetch_attendance(self, conference_record_name: str) -> list[dict[str, Any]]:
        return await self._list_all(
            f"{conference_record_name}/participants", "participants"
        )

    async def fetch_transcript_entries(self, conference_record_name: str) -> list[dict[str, Any]]:
        transcripts = await self._list_all(
            f"{conference_record_name}/transcripts", "transcripts"
        )
        transcript_entries: list[dict[str, Any]] = []
        for transcript in transcripts:
            transcript_name = str(transcript.get("name", ""))
            if transcript_name:
                transcript_entries.extend(
                    await self._list_all(
                        f"{transcript_name}/entries", "transcriptEntries"
                    )
                )
        return transcript_entries

    async def fetch_recordings(self, conference_record_name: str) -> list[dict[str, Any]]:
        return await self._list_all(
            f"{conference_record_name}/recordings", "recordings"
        )

    async def fetch_artifact_bundle(self, conference_record_name: str) -> dict[str, Any]:
        attendance, transcript_entries, recordings = await self._gather_artifacts(
            conference_record_name
        )
        return {
            "conference_record_name": conference_record_name,
            "attendance": attendance,
            "transcript_entries": transcript_entries,
            "recordings": recordings,
        }

    async def _gather_artifacts(
        self, conference_record_name: str
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
        attendance = await self.fetch_attendance(conference_record_name)
        transcript_entries = await self.fetch_transcript_entries(conference_record_name)
        recordings = await self.fetch_recordings(conference_record_name)
        return attendance, transcript_entries, recordings
