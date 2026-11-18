from fastapi import APIRouter, Depends

from confhub.api.dependencies import get_provider_registry
from confhub.providers.registry import ProviderRegistry
from confhub.schemas import ProviderCapabilitiesRead
from confhub.security import require_api_access

router = APIRouter(
    prefix="/api/v1/providers",
    tags=["providers"],
    dependencies=[Depends(require_api_access)],
)


@router.get("", response_model=list[ProviderCapabilitiesRead])
async def list_provider_capabilities(
    provider_registry: ProviderRegistry = Depends(get_provider_registry),
):
    return provider_registry.all_capabilities()
