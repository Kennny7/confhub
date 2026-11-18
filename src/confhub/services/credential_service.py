from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from confhub.enums import MeetingPlatform
from confhub.models import PlatformCredential


async def upsert_credential(
    session: AsyncSession,
    user_id: str,
    platform: MeetingPlatform,
    token_data: str,
    scopes: str = "",
) -> PlatformCredential:
    """Create or replace the stored credential for a platform."""
    statement = select(PlatformCredential).where(
        PlatformCredential.user_id == user_id,
        PlatformCredential.platform == platform.value,
    )
    result = await session.scalars(statement)
    credential = result.first()
    if credential is None:
        credential = PlatformCredential(
            user_id=user_id,
            platform=platform.value,
            token_data=token_data,
            scopes=scopes,
        )
        session.add(credential)
    else:
        credential.token_data = token_data
        credential.scopes = scopes
        credential.updated_at = datetime.now(UTC)
    await session.commit()
    await session.refresh(credential)
    return credential


async def get_credential(
    session: AsyncSession,
    user_id: str,
    platform: MeetingPlatform,
) -> PlatformCredential | None:
    statement = select(PlatformCredential).where(
        PlatformCredential.user_id == user_id,
        PlatformCredential.platform == platform.value,
    )
    result = await session.scalars(statement)
    return result.first()


async def list_credentials(
    session: AsyncSession,
    user_id: str,
) -> list[PlatformCredential]:
    statement = select(PlatformCredential).where(PlatformCredential.user_id == user_id)
    result = await session.scalars(statement)
    return list(result.all())


async def delete_credential(
    session: AsyncSession,
    user_id: str,
    platform: MeetingPlatform,
) -> bool:
    """Returns True if a credential was deleted."""
    credential = await get_credential(session, user_id, platform)
    if credential is None:
        return False
    await session.delete(credential)
    await session.commit()
    return True
