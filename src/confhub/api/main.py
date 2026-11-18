import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from confhub.api.routes import credentials, health, meetings, profiles, providers, webhooks
from confhub.config import get_settings
from confhub.database import create_database_schema, dispose_database
from confhub.logging_config import configure_logging

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
    title="ConfHub API",
    version="0.2.0",
    description=(
        "Platform-neutral conference management and participation assistant API. "
        "Supports Microsoft Teams, Google Meet, Zoom, and Cisco Webex. "
        "Users join conferences using their own account identity."
    ),
    lifespan=lifespan,
)
app.include_router(health.router)
app.include_router(profiles.router)
app.include_router(providers.router)
app.include_router(meetings.router)
app.include_router(webhooks.router)
app.include_router(credentials.router)
