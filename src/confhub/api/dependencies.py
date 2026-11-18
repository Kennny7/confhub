from fastapi import Depends

from confhub.config import Settings, get_settings
from confhub.providers.registry import ProviderRegistry


def get_provider_registry(settings: Settings = Depends(get_settings)) -> ProviderRegistry:
    return ProviderRegistry(settings)
