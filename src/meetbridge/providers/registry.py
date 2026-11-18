from meetbridge.config import Settings
from meetbridge.enums import MeetingPlatform
from meetbridge.providers.base import MeetingProvider
from meetbridge.providers.google_meet import GoogleMeetProvider
from meetbridge.providers.teams import TeamsGatewayProvider


class ProviderRegistry:
    def __init__(self, settings: Settings) -> None:
        self._providers: dict[MeetingPlatform, MeetingProvider] = {
            MeetingPlatform.TEAMS: TeamsGatewayProvider(settings),
            MeetingPlatform.GOOGLE_MEET: GoogleMeetProvider(settings),
        }

    def get(self, platform: MeetingPlatform | str) -> MeetingProvider:
        resolved_platform = MeetingPlatform(platform)
        try:
            return self._providers[resolved_platform]
        except KeyError as error:
            raise ValueError(f"No provider is registered for {resolved_platform.value}") from error

    def all_capabilities(self) -> list[object]:
        return [provider.capabilities() for provider in self._providers.values()]
