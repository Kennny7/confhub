from sqlalchemy.ext.asyncio import AsyncSession

from meetbridge.config import Settings
from meetbridge.models import UserProfile
from meetbridge.schemas import ProfileUpdate


async def get_default_profile(session: AsyncSession, settings: Settings) -> UserProfile:
    profile = await session.get(UserProfile, "default")
    if profile is None:
        profile = UserProfile(
            user_id="default",
            display_name=settings.default_user_name,
            email=settings.default_user_email,
            location=settings.default_user_location,
            timezone_name=settings.default_user_timezone,
        )
        session.add(profile)
        await session.commit()
        await session.refresh(profile)
    return profile


async def update_default_profile(
    session: AsyncSession, settings: Settings, profile_update: ProfileUpdate
) -> UserProfile:
    profile = await get_default_profile(session, settings)
    profile.display_name = profile_update.display_name
    profile.email = profile_update.email
    profile.location = profile_update.location
    profile.timezone_name = profile_update.timezone_name
    await session.commit()
    await session.refresh(profile)
    return profile
