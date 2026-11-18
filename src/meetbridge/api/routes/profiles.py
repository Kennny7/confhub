from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from meetbridge.config import Settings, get_settings
from meetbridge.database import get_session
from meetbridge.schemas import ProfileRead, ProfileUpdate
from meetbridge.security import require_api_access
from meetbridge.services.profile_service import get_default_profile, update_default_profile

router = APIRouter(prefix="/api/v1/profile", tags=["profile"], dependencies=[Depends(require_api_access)])


@router.get("/default", response_model=ProfileRead)
async def read_default_profile(
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
):
    return await get_default_profile(session, settings)


@router.put("/default", response_model=ProfileRead)
async def save_default_profile(
    profile_update: ProfileUpdate,
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
):
    return await update_default_profile(session, settings, profile_update)
