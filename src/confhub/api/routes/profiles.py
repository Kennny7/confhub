from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from confhub.config import Settings, get_settings
from confhub.database import get_session
from confhub.schemas import ProfileRead, ProfileUpdate
from confhub.security import require_api_access
from confhub.services.profile_service import get_default_profile, update_default_profile

router = APIRouter(
    prefix="/api/v1/profile",
    tags=["profile"],
    dependencies=[Depends(require_api_access)],
)


@router.get("", response_model=ProfileRead)
async def get_profile_endpoint(
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
):
    return await get_default_profile(session, settings)


@router.put("", response_model=ProfileRead)
async def update_profile_endpoint(
    update_data: ProfileUpdate,
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
):
    return await update_default_profile(session, settings, update_data)
