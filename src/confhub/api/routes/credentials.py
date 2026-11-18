"""Platform credential management endpoints."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from confhub.database import get_session
from confhub.enums import MeetingPlatform
from confhub.schemas import PlatformCredentialRead, PlatformCredentialUpsert
from confhub.security import require_api_access
from confhub.services.credential_service import (
    delete_credential,
    get_credential,
    list_credentials,
    upsert_credential,
)

router = APIRouter(
    prefix="/api/v1/credentials",
    tags=["credentials"],
    dependencies=[Depends(require_api_access)],
)

_DEFAULT_USER_ID = "default"


@router.get("", response_model=list[PlatformCredentialRead])
async def list_credentials_endpoint(
    session: AsyncSession = Depends(get_session),
):
    """List all stored platform credentials (token data is not returned)."""
    credentials = await list_credentials(session, _DEFAULT_USER_ID)
    return credentials


@router.put("/{platform}", response_model=PlatformCredentialRead, status_code=status.HTTP_200_OK)
async def upsert_credential_endpoint(
    platform: MeetingPlatform,
    data: PlatformCredentialUpsert,
    session: AsyncSession = Depends(get_session),
):
    """Store or update the OAuth token for a platform."""
    return await upsert_credential(
        session,
        _DEFAULT_USER_ID,
        platform,
        data.token_data,
        data.scopes,
    )


@router.get("/{platform}", response_model=PlatformCredentialRead)
async def get_credential_endpoint(
    platform: MeetingPlatform,
    session: AsyncSession = Depends(get_session),
):
    """Check if a credential is stored for a platform."""
    credential = await get_credential(session, _DEFAULT_USER_ID, platform)
    if credential is None:
        raise HTTPException(status_code=404, detail=f"No credential stored for {platform.value}")
    return credential


@router.delete("/{platform}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_credential_endpoint(
    platform: MeetingPlatform,
    session: AsyncSession = Depends(get_session),
):
    """Remove a stored platform credential."""
    deleted = await delete_credential(session, _DEFAULT_USER_ID, platform)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"No credential found for {platform.value}")
