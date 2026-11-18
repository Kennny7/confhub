from fastapi import Depends

from meetbridge.config import Settings, get_settings
from meetbridge.providers.registry import ProviderRegistry


def get_provider_registry(settings: Settings = Depends(get_settings)) -> ProviderRegistry:
    return ProviderRegistry(settings)
