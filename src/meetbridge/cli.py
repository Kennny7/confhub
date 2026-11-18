import asyncio
from datetime import datetime

import typer
from google_auth_oauthlib.flow import InstalledAppFlow
from rich.console import Console
from rich.table import Table

from meetbridge.config import get_settings
from meetbridge.database import AsyncSessionFactory, create_database_schema, dispose_database
from meetbridge.enums import MeetingPlatform, MeetingStatus
from meetbridge.logging_config import configure_logging
from meetbridge.providers.registry import ProviderRegistry
from meetbridge.schemas import MeetingCreate, NoteCreate, ProfileUpdate
from meetbridge.services.meeting_service import (
    MeetingNotFoundError,
    add_meeting_note,
    cancel_meeting,
    create_meeting,
    get_meeting,
    join_meeting,
    list_meetings,
)
from meetbridge.services.profile_service import get_default_profile, update_default_profile
from meetbridge.scheduler import run_scheduler

console = Console()
app = typer.Typer(help="MeetBridge meeting assistant service", no_args_is_help=True)
meeting_app = typer.Typer(help="Manage scheduled meetings", no_args_is_help=True)
profile_app = typer.Typer(help="Manage the default user profile", no_args_is_help=True)
app.add_typer(meeting_app, name="meeting")
app.add_typer(profile_app, name="profile")


async def initialise_database() -> None:
    await create_database_schema()
    settings = get_settings()
    async with AsyncSessionFactory() as session:
        await get_default_profile(session, settings)
    await dispose_database()


def parse_datetime(value: str) -> datetime:
    try:
        parsed_datetime = datetime.fromisoformat(value)
    except ValueError as error:
        raise typer.BadParameter(
            "Use ISO-8601 with a timezone, e.g. 2026-11-18T14:30:00+05:30"
        ) from error
    if parsed_datetime.tzinfo is None or parsed_datetime.utcoffset() is None:
        raise typer.BadParameter("Date/time must include a timezone offset, such as +05:30")
    return parsed_datetime


async def ensure_profile_ready() -> str:
    settings = get_settings()
    async with AsyncSessionFactory() as session:
        profile = await get_default_profile(session, settings)
        if not profile.display_name.strip():
            profile.display_name = typer.prompt("Your display name")
        if not profile.email.strip():
            profile.email = typer.prompt("Your email address")
        if not profile.timezone_name.strip():
            profile.timezone_name = typer.prompt("Your IANA timezone", default="Asia/Kolkata")
        await session.commit()
        return profile.email


@app.command("init")
def initialise_command() -> None:
    """Create database tables and seed the default profile from environment settings."""
    asyncio.run(initialise_database())
    console.print("[green]Database initialised.[/green]")


@app.command("serve")
def serve_command(
    host: str = typer.Option("127.0.0.1", help="Bind address; use 0.0.0.0 only with API_KEY set."),
    port: int = typer.Option(8090, min=1, max=65535),
    reload: bool = typer.Option(False, help="Enable development reload."),
) -> None:
    """Start the FastAPI service."""
    import uvicorn

    settings = get_settings()
    if host not in {"127.0.0.1", "localhost", "::1"} and not settings.api_key:
        raise typer.BadParameter("Set API_KEY before binding the API to a non-loopback interface")
    configure_logging(settings.log_level)
    uvicorn.run("meetbridge.api.main:app", host=host, port=port, reload=reload)


@app.command("worker")
def worker_command() -> None:
    """Run the opt-in scheduled meeting dispatcher."""
    configure_logging(get_settings().log_level)
    asyncio.run(run_scheduler())


@app.command("platforms")
def platforms_command() -> None:
    """Show actual configured capabilities for each provider."""
    registry = ProviderRegistry(get_settings())
    table = Table(title="Platform capabilities")
    table.add_column("Platform")
    table.add_column("Configured")
    table.add_column("Live join")
    table.add_column("Attendance / artifacts")
    table.add_column("Details", overflow="fold")
    for capability in registry.all_capabilities():
        table.add_row(
            capability.platform.value,
            "yes" if capability.available else "no",
            "yes" if capability.can_join_live else "no",
            "yes" if any(
                [
                    capability.can_fetch_attendance,
                    capability.can_fetch_transcripts,
                    capability.can_fetch_recordings,
                ]
            )
            else "no",
            capability.explanation,
        )
    console.print(table)


@app.command("doctor")
def doctor_command() -> None:
    """Check basic local configuration without printing secrets."""
    settings = get_settings()
    checks = [
        ("Database URL", bool(settings.database_url)),
        ("API key configured", bool(settings.api_key)),
        ("Teams gateway", settings.teams_gateway_configured),
        ("Google OAuth token", settings.google_token_file.exists()),
        ("Local LLM endpoint", bool(settings.llm_base_url and settings.llm_model)),
        ("Recording globally enabled", settings.recording_enabled),
    ]
    table = Table(title="MeetBridge diagnostics")
    table.add_column("Check")
    table.add_column("Status")
    for label, succeeded in checks:
        table.add_row(label, "[green]configured[/green]" if succeeded else "[yellow]not configured[/yellow]")
    console.print(table)


@profile_app.command("show")
def profile_show_command() -> None:
    async def show_profile() -> None:
        settings = get_settings()
        await create_database_schema()
        async with AsyncSessionFactory() as session:
            profile = await get_default_profile(session, settings)
            table = Table(title="Default user profile")
            table.add_column("Field")
            table.add_column("Value")
            table.add_row("Display name", profile.display_name or "Not set")
            table.add_row("Email", profile.email or "Not set")
            table.add_row("Location", profile.location or "Not set")
            table.add_row("Timezone", profile.timezone_name)
            console.print(table)
        await dispose_database()

    asyncio.run(show_profile())


@profile_app.command("set")
def profile_set_command(
    display_name: str = typer.Option(..., prompt=True),
    email: str = typer.Option("", prompt=True),
    location: str = typer.Option("", prompt=True),
    timezone_name: str = typer.Option("Asia/Kolkata", prompt=True),
) -> None:
    async def save_profile() -> None:
        settings = get_settings()
        await create_database_schema()
        async with AsyncSessionFactory() as session:
            profile = await update_default_profile(
                session,
                settings,
                ProfileUpdate(
                    display_name=display_name,
                    email=email,
                    location=location,
                    timezone_name=timezone_name,
                ),
            )
            console.print(f"Saved profile for [bold]{profile.display_name}[/bold].")
        await dispose_database()

    asyncio.run(save_profile())


@meeting_app.command("add")
def meeting_add_command(
    title: str = typer.Option(..., prompt=True),
    platform: MeetingPlatform = typer.Option(..., case_sensitive=False),
    join_url: str = typer.Option(..., prompt=True),
    conference_record_name: str = typer.Option("", help="Google Meet resource, e.g. conferenceRecords/ID"),
    start_at: str = typer.Option(..., prompt=True, help="ISO-8601 date/time with timezone offset."),
    end_at: str = typer.Option(..., prompt=True, help="ISO-8601 date/time with timezone offset."),
    description: str = typer.Option(""),
    agenda: str = typer.Option(""),
    note_taking: bool = typer.Option(True, "--notes/--no-notes"),
    auto_join: bool = typer.Option(False, "--auto-join/--manual-join"),
    recording_requested: bool = typer.Option(False, "--recording/--no-recording"),
    bot_display_name: str | None = typer.Option(None),
) -> None:
    async def save_meeting() -> None:
        settings = get_settings()
        await create_database_schema()
        owner_email = await ensure_profile_ready()
        join_authorized = False
        if auto_join:
            console.print(
                "The service will join as a separately named bot. It will not impersonate your identity."
            )
            join_authorized = typer.confirm("Authorize this bot to join automatically in the scheduled window?")
            if not join_authorized:
                raise typer.Abort()
        if recording_requested:
            console.print(
                "Recording is not started by this Python service. Platform recording requires "
                "organizer authorization and participant consent."
            )
        async with AsyncSessionFactory() as session:
            meeting = await create_meeting(
                session,
                settings,
                MeetingCreate(
                    title=title,
                    platform=platform,
                    join_url=join_url,
                    owner_email=owner_email,
                    conference_record_name=conference_record_name,
                    scheduled_start_at=parse_datetime(start_at),
                    scheduled_end_at=parse_datetime(end_at),
                    description=description,
                    agenda=agenda,
                    bot_display_name=bot_display_name or settings.default_bot_display_name,
                    note_taking_enabled=note_taking,
                    auto_join=auto_join,
                    join_authorized=join_authorized,
                    recording_requested=recording_requested,
                ),
            )
            console.print(f"Created meeting [bold]{meeting.meeting_id}[/bold].")
        await dispose_database()

    asyncio.run(save_meeting())


@meeting_app.command("list")
def meeting_list_command(
    meeting_status: MeetingStatus | None = typer.Option(None, "--status"),
    platform: MeetingPlatform | None = typer.Option(None, "--platform"),
) -> None:
    async def show_meetings() -> None:
        await create_database_schema()
        async with AsyncSessionFactory() as session:
            meetings = await list_meetings(session, meeting_status, platform)
            table = Table(title="Meetings")
            table.add_column("ID", max_width=10)
            table.add_column("Start")
            table.add_column("Platform")
            table.add_column("Status")
            table.add_column("Title", overflow="fold")
            for meeting in meetings:
                table.add_row(
                    meeting.meeting_id[:8],
                    meeting.scheduled_start_at.isoformat(),
                    meeting.platform,
                    meeting.status,
                    meeting.title,
                )
            console.print(table)
        await dispose_database()

    asyncio.run(show_meetings())


@meeting_app.command("show")
def meeting_show_command(meeting_id: str) -> None:
    async def show_meeting() -> None:
        await create_database_schema()
        async with AsyncSessionFactory() as session:
            try:
                meeting = await get_meeting(session, meeting_id)
            except MeetingNotFoundError as error:
                raise typer.BadParameter("Meeting ID not found") from error
            table = Table(title=f"Meeting {meeting.meeting_id}")
            table.add_column("Field")
            table.add_column("Value", overflow="fold")
            for field_name in [
                "title", "platform", "status", "owner_email", "join_url",
                "scheduled_start_at", "scheduled_end_at", "bot_display_name",
                "microphone_enabled", "camera_enabled", "note_taking_enabled",
                "auto_join", "join_authorized", "recording_status", "failure_reason",
            ]:
                table.add_row(field_name, str(getattr(meeting, field_name)))
            console.print(table)
        await dispose_database()

    asyncio.run(show_meeting())


@meeting_app.command("join")
def meeting_join_command(meeting_id: str) -> None:
    async def join_now() -> None:
        settings = get_settings()
        await create_database_schema()
        await ensure_profile_ready()
        async with AsyncSessionFactory() as session:
            try:
                meeting = await get_meeting(session, meeting_id)
            except MeetingNotFoundError as error:
                raise typer.BadParameter("Meeting ID not found") from error
            console.print(
                f"The bot will enter as [bold]{meeting.bot_display_name}[/bold]. "
                "Microphone and camera stay disabled."
            )
            if not typer.confirm("Proceed with the bot join request?"):
                raise typer.Abort()
            updated_meeting = await join_meeting(
                session,
                settings,
                ProviderRegistry(settings),
                meeting,
                confirm_bot_identity=True,
                actor="cli-user",
            )
            console.print(f"Meeting state: [bold]{updated_meeting.status}[/bold]")
        await dispose_database()

    asyncio.run(join_now())


@meeting_app.command("cancel")
def meeting_cancel_command(meeting_id: str) -> None:
    async def cancel_now() -> None:
        await create_database_schema()
        async with AsyncSessionFactory() as session:
            try:
                meeting = await get_meeting(session, meeting_id)
            except MeetingNotFoundError as error:
                raise typer.BadParameter("Meeting ID not found") from error
            if not typer.confirm(f"Cancel '{meeting.title}'?"):
                raise typer.Abort()
            updated_meeting = await cancel_meeting(session, meeting, actor="cli-user")
            console.print(f"Meeting state: [bold]{updated_meeting.status}[/bold]")
        await dispose_database()

    asyncio.run(cancel_now())


@meeting_app.command("note")
def meeting_note_command(
    meeting_id: str,
    content: str = typer.Option(..., prompt=True),
    note_type: str = typer.Option("manual", help="manual, summary, action_items, transcript_excerpt"),
) -> None:
    async def save_note() -> None:
        await create_database_schema()
        async with AsyncSessionFactory() as session:
            meeting = await get_meeting(session, meeting_id)
            note = await add_meeting_note(session, meeting, NoteCreate(content=content, note_type=note_type))
            console.print(f"Saved note [bold]{note.note_id}[/bold].")
        await dispose_database()

    asyncio.run(save_note())


@app.command("google-auth")
def google_auth_command() -> None:
    """Run Google's installed-app OAuth flow for post-meeting artifacts."""
    settings = get_settings()
    if not settings.google_oauth_client_file.exists():
        raise typer.BadParameter(
            f"OAuth client JSON not found at {settings.google_oauth_client_file}. "
            "Create a Google OAuth desktop client and place its JSON at that path."
        )
    flow = InstalledAppFlow.from_client_secrets_file(
        str(settings.google_oauth_client_file), settings.google_scopes
    )
    credentials = flow.run_local_server(port=0, access_type="offline", prompt="consent")
    settings.google_token_file.parent.mkdir(parents=True, exist_ok=True)
    settings.google_token_file.write_text(credentials.to_json(), encoding="utf-8")
    settings.google_token_file.chmod(0o600)
    console.print(f"Google OAuth token saved to [bold]{settings.google_token_file}[/bold].")


if __name__ == "__main__":
    app()
