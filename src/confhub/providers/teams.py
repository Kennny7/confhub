from typing import Any

import httpx

from confhub.config import Settings
from confhub.enums import MeetingPlatform
from confhub.models import Meeting
from confhub.providers.base import (
    JoinResult,
    ProviderCapabilities,
    ProviderConfigurationError,
    ProviderError,
    UnsupportedCapabilityError,
)


class TeamsGatewayProvider:
    """Python orchestration adapter for a separately hosted Teams calling-bot gateway.

    Microsoft application-hosted real-time media uses Microsoft's .NET media library.
    This adapter delegates to a configured .NET gateway service.
    """

    platform = MeetingPlatform.TEAMS

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def capabilities(self) -> ProviderCapabilities:
        configured = self.settings.teams_gateway_configured
        recording_enabled = configured and self.settings.teams_recording_gateway_enabled
        return ProviderCapabilities(
            platform=self.platform,
            available=configured,
            can_join_live=configured,
            can_fetch_attendance=False,
            can_fetch_transcripts=False,
            can_fetch_recordings=False,
            can_record_live=recording_enabled,
            explanation=(
                "Configured Teams .NET calling-bot gateway is available."
                if configured
                else "Set TEAMS_GATEWAY_URL and TEAMS_GATEWAY_TOKEN after deploying the Teams .NET bot gateway."
            ),
        )

    async def join(self, meeting: Meeting, *, display_name: str = "") -> JoinResult:
        if not self.settings.teams_gateway_configured:
            raise ProviderConfigurationError(
                "Teams live join is not configured. Deploy the Teams .NET bot gateway and set "
                "TEAMS_GATEWAY_URL and TEAMS_GATEWAY_TOKEN."
            )

        effective_name = display_name or meeting.display_name_override or self.settings.default_display_name
        request_payload: dict[str, Any] = {
            "meeting_id": meeting.meeting_id,
            "meeting_url": meeting.join_url,
            "join_code": meeting.join_code,
            "subject": meeting.title,
            "display_name": effective_name,
            "join_mode": meeting.join_mode,
            "microphone_enabled": False,
            "camera_enabled": False,
            "note_taking_enabled": meeting.note_taking_enabled,
            "recording_requested": False,
        }

        gateway_url = self.settings.teams_gateway_url.rstrip("/") + "/v1/calls/join"
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(30.0)) as client:
                response = await client.post(
                    gateway_url,
                    json=request_payload,
                    headers={"Authorization": f"Bearer {self.settings.teams_gateway_token}"},
                )
                response.raise_for_status()
                gateway_response = response.json()
        except httpx.HTTPError as error:
            raise ProviderError(f"Teams gateway request failed: {error}") from error

        call_identifier = str(gateway_response.get("call_id", ""))
        if not call_identifier:
            raise RuntimeError("Teams gateway response did not include call_id")

        returned_name = str(gateway_response.get("display_name", effective_name))
        return JoinResult(
            provider_call_id=call_identifier,
            state=str(gateway_response.get("state", "joining")),
            display_name=returned_name,
            details=gateway_response,
        )

    async def start_recording(self, meeting: Meeting) -> dict[str, Any]:
        if not self.settings.teams_recording_gateway_enabled:
            raise UnsupportedCapabilityError("Teams gateway recording has not been enabled")
        raise UnsupportedCapabilityError(
            "Recording activation must be implemented in the deployed gateway after it has "
            "received platform recording-status acknowledgement and participant consent."
        )
