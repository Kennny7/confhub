from dataclasses import asdict

from fastapi import APIRouter, Depends

from meetbridge.api.dependencies import get_provider_registry
from meetbridge.providers.registry import ProviderRegistry
from meetbridge.schemas import ProviderCapabilitiesRead
from meetbridge.security import require_api_access

router = APIRouter(prefix="/api/v1/providers", tags=["providers"], dependencies=[Depends(require_api_access)])


@router.get("", response_model=list[ProviderCapabilitiesRead])
async def list_providers(
    provider_registry: ProviderRegistry = Depends(get_provider_registry),
):
    return [asdict(capability) for capability in provider_registry.all_capabilities()]
