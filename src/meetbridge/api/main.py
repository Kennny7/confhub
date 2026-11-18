from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI

from meetbridge.config import get_settings
from meetbridge.database import create_database_schema, dispose_database
from meetbridge.logging_config import configure_logging
from meetbridge.api.routes import health, meetings, profiles, providers, webhooks

settings = get_settings()
configure_logging(settings.log_level)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(application: FastAPI):
    await create_database_schema()
    if not settings.api_key:
        logger.warning("API_KEY is not configured; requests are restricted to loopback clients")
    yield
    await dispose_database()


app = FastAPI(
    title="MeetBridge API",
    version="0.1.0",
    description=(
        "Consent-aware meeting assistant orchestration API. Bots join under an explicit bot identity; "
        "the service does not impersonate users or claim attendance credit on their behalf."
    ),
    lifespan=lifespan,
)
app.include_router(health.router)
app.include_router(profiles.router)
app.include_router(providers.router)
app.include_router(meetings.router)
app.include_router(webhooks.router)
