from dataclasses import dataclass
from typing import Any, Protocol

from meetbridge.enums import MeetingPlatform
from meetbridge.models import Meeting


class ProviderError(RuntimeError):
    """Base exception for provider failures."""


class UnsupportedCapabilityError(ProviderError):
    """Raised when a provider does not expose a requested operation."""


class ProviderConfigurationError(ProviderError):
    """Raised when required credentials or a provider gateway are missing."""


@dataclass(frozen=True, slots=True)
class ProviderCapabilities:
    platform: MeetingPlatform
    available: bool
    can_join_live: bool
    can_fetch_attendance: bool
    can_fetch_transcripts: bool
    can_fetch_recordings: bool
    can_record_live: bool
    explanation: str


@dataclass(frozen=True, slots=True)
class JoinResult:
    provider_call_id: str
    state: str
    bot_display_name: str
    details: dict[str, Any]


class MeetingProvider(Protocol):
    platform: MeetingPlatform

    def capabilities(self) -> ProviderCapabilities: ...

    async def join(self, meeting: Meeting) -> JoinResult: ...
