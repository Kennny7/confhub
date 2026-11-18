from sqlalchemy.ext.asyncio import AsyncSession

from confhub.config import Settings
from confhub.models import UserProfile


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
    session: AsyncSession,
    settings: Settings,
    update_data,
) -> UserProfile:
    profile = await get_default_profile(session, settings)
    profile.display_name = update_data.display_name
    profile.email = update_data.email
    profile.location = update_data.location
    profile.timezone_name = update_data.timezone_name
    await session.commit()
    await session.refresh(profile)
    return profile
