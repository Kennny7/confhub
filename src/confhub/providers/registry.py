from confhub.config import Settings
from confhub.enums import MeetingPlatform
from confhub.providers.base import MeetingProvider
from confhub.providers.google_meet import GoogleMeetProvider
from confhub.providers.teams import TeamsGatewayProvider
from confhub.providers.webex import WebexProvider
from confhub.providers.zoom import ZoomProvider


class ProviderRegistry:
    def __init__(self, settings: Settings) -> None:
        self._providers: dict[MeetingPlatform, MeetingProvider] = {
            MeetingPlatform.TEAMS: TeamsGatewayProvider(settings),
            MeetingPlatform.GOOGLE_MEET: GoogleMeetProvider(settings),
            MeetingPlatform.ZOOM: ZoomProvider(settings),
            MeetingPlatform.WEBEX: WebexProvider(settings),
        }

    def get(self, platform: MeetingPlatform | str) -> MeetingProvider:
        resolved_platform = MeetingPlatform(platform)
        try:
            return self._providers[resolved_platform]
        except KeyError as error:
            raise ValueError(f"No provider is registered for {resolved_platform.value}") from error

    def all_capabilities(self) -> list[object]:
        return [provider.capabilities() for provider in self._providers.values()]
