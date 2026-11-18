import asyncio
import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from confhub.config import get_settings
from confhub.database import AsyncSessionFactory, create_database_schema, dispose_database
from confhub.providers.registry import ProviderRegistry
from confhub.services.meeting_service import get_due_auto_join_meetings, join_meeting

logger = logging.getLogger(__name__)


async def dispatch_due_meetings() -> None:
    settings = get_settings()
    provider_registry = ProviderRegistry(settings)
    async with AsyncSessionFactory() as session:
        due_meetings = await get_due_auto_join_meetings(session)
        for meeting in due_meetings:
            try:
                await join_meeting(
                    session,
                    settings,
                    provider_registry,
                    meeting,
                    confirm_join=True,
                    actor="scheduler-explicitly-authorized",
                )
                logger.info(
                    "Dispatched meeting %s through %s",
                    meeting.meeting_id,
                    meeting.platform,
                )
            except Exception:
                logger.exception("Could not dispatch scheduled meeting %s", meeting.meeting_id)


async def run_scheduler() -> None:
    settings = get_settings()
    await create_database_schema()
    scheduler = AsyncIOScheduler(timezone=settings.default_user_timezone)
    scheduler.add_job(
        dispatch_due_meetings,
        trigger="interval",
        seconds=20,
        id="dispatch_due_meetings",
        max_instances=1,
        coalesce=True,
    )
    scheduler.start()
    logger.info("ConfHub scheduler started; polling every 20 seconds")
    try:
        while True:
            await asyncio.sleep(3600)
    finally:
        scheduler.shutdown(wait=False)
        await dispose_database()
