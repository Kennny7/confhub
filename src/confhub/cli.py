import asyncio
from datetime import datetime
from pathlib import Path

import typer
from google_auth_oauthlib.flow import InstalledAppFlow
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm, Prompt
from rich.rule import Rule
from rich.table import Table

from confhub.config import get_settings
from confhub.database import AsyncSessionFactory, create_database_schema, dispose_database
from confhub.enums import JoinMode, MeetingPlatform, MeetingStatus
from confhub.logging_config import configure_logging
from confhub.providers.registry import ProviderRegistry
from confhub.scheduler import run_scheduler
from confhub.schemas import MeetingCreate, NoteCreate, ProfileUpdate
from confhub.services.meeting_service import (
    MeetingNotFoundError,
    add_meeting_note,
    cancel_meeting,
    create_meeting,
    export_meeting_to_markdown,
    get_meeting,
    join_meeting,
    list_meetings,
)
from confhub.services.profile_service import get_default_profile, update_default_profile

console = Console()
app = typer.Typer(
    help="ConfHub - platform-neutral conference management and participation assistant.",
    no_args_is_help=True,
)
meeting_app = typer.Typer(help="Manage scheduled conferences", no_args_is_help=True)
profile_app = typer.Typer(help="Manage your user profile", no_args_is_help=True)
app.add_typer(meeting_app, name="meeting")
app.add_typer(profile_app, name="profile")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

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
        changed = False
        if not profile.display_name.strip():
            profile.display_name = Prompt.ask("Your full name")
            changed = True
        if not profile.email.strip():
            profile.email = Prompt.ask("Your email address")
            changed = True
        if not profile.timezone_name.strip():
            profile.timezone_name = Prompt.ask("Your IANA timezone", default="Asia/Kolkata")
            changed = True
        if changed:
            await session.commit()
        return profile.email


# ---------------------------------------------------------------------------
# Top-level commands
# ---------------------------------------------------------------------------

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
    uvicorn.run("confhub.api.main:app", host=host, port=port, reload=reload)


@app.command("worker")
def worker_command() -> None:
    """Run the scheduled conference dispatcher."""
    configure_logging(get_settings().log_level)
    asyncio.run(run_scheduler())


@app.command("ui")
def ui_command() -> None:
    """Launch the interactive ConfHub terminal dashboard."""
    async def _run():
        await create_database_schema()
        from confhub.tui.dashboard import run_dashboard
        await run_dashboard(AsyncSessionFactory, get_settings())
        await dispose_database()

    asyncio.run(_run())


@app.command("platforms")
def platforms_command() -> None:
    """Show configured capabilities for each platform provider."""
    registry = ProviderRegistry(get_settings())
    table = Table(title="Platform capabilities", border_style="bright_black", show_lines=True)
    table.add_column("Platform")
    table.add_column("Configured")
    table.add_column("Live join")
    table.add_column("Post-meeting artifacts")
    table.add_column("Details", overflow="fold")
    for capability in registry.all_capabilities():
        table.add_row(
            capability.platform.value,
            "[green]yes[/green]" if capability.available else "[yellow]no[/yellow]",
            "[green]yes[/green]" if capability.can_join_live else "no",
            "[green]yes[/green]" if any([
                capability.can_fetch_attendance,
                capability.can_fetch_transcripts,
                capability.can_fetch_recordings,
            ]) else "no",
            capability.explanation,
        )
    console.print(table)


@app.command("doctor")
def doctor_command() -> None:
    """Check local configuration without printing secrets."""
    settings = get_settings()
    checks = [
        ("Database URL", bool(settings.database_url)),
        ("API key configured", bool(settings.api_key)),
        ("Teams gateway", settings.teams_gateway_configured),
        ("Google OAuth token", settings.google_token_file.exists()),
        ("Zoom OAuth token", settings.zoom_token_file.exists()),
        ("Webex OAuth token", settings.webex_token_file.exists()),
        ("Local LLM endpoint", bool(settings.llm_base_url and settings.llm_model)),
        ("Recording globally enabled", settings.recording_enabled),
    ]
    table = Table(title="ConfHub diagnostics", border_style="bright_black", show_lines=True)
    table.add_column("Check")
    table.add_column("Status")
    for label, succeeded in checks:
        status = "[green]configured[/green]" if succeeded else "[yellow]not configured[/yellow]"
        table.add_row(label, status)
    console.print(table)


@app.command("google-auth")
def google_auth_command() -> None:
    """Run Google OAuth flow for post-meeting artifacts."""
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
    console.print(f"[green]Google OAuth token saved to [bold]{settings.google_token_file}[/bold].[/green]")


@app.command("zoom-auth")
def zoom_auth_command() -> None:
    """Connect your Zoom account via OAuth."""
    async def _run():
        settings = get_settings()
        from confhub.tui.auth_wizard import run_auth_wizard
        await run_auth_wizard(settings, "zoom")

    asyncio.run(_run())


@app.command("webex-auth")
def webex_auth_command() -> None:
    """Connect your Webex account via OAuth."""
    async def _run():
        settings = get_settings()
        from confhub.tui.auth_wizard import run_auth_wizard
        await run_auth_wizard(settings, "webex")

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# Profile commands
# ---------------------------------------------------------------------------

@profile_app.command("show")
def profile_show_command() -> None:
    """Show the current user profile."""
    async def show_profile() -> None:
        settings = get_settings()
        await create_database_schema()
        async with AsyncSessionFactory() as session:
            profile = await get_default_profile(session, settings)
            table = Table(title="Your profile", border_style="bright_black")
            table.add_column("Field", style="dim")
            table.add_column("Value")
            table.add_row("Display name", profile.display_name or "[dim]Not set[/dim]")
            table.add_row("Email", profile.email or "[dim]Not set[/dim]")
            table.add_row("Location", profile.location or "[dim]Not set[/dim]")
            table.add_row("Timezone", profile.timezone_name)
            console.print(table)
        await dispose_database()

    asyncio.run(show_profile())


@profile_app.command("set")
def profile_set_command(
    display_name: str = typer.Option(..., prompt=True, help="Your full name (shown in conferences)."),
    email: str = typer.Option("", prompt=True),
    location: str = typer.Option("", prompt=True),
    timezone_name: str = typer.Option("Asia/Kolkata", prompt=True),
) -> None:
    """Update the user profile."""
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
            console.print(f"Profile saved for [bold]{profile.display_name}[/bold].")
        await dispose_database()

    asyncio.run(save_profile())


@profile_app.command("wizard")
def profile_wizard_command() -> None:
    """Interactive profile setup wizard."""
    async def _run():
        await create_database_schema()
        from confhub.tui.profile_wizard import run_profile_wizard
        await run_profile_wizard(AsyncSessionFactory, get_settings())
        await dispose_database()

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# Meeting commands
# ---------------------------------------------------------------------------

@meeting_app.command("add")
def meeting_add_command(
    title: str = typer.Option(..., prompt=True),
    platform: MeetingPlatform = typer.Option(..., case_sensitive=False),
    join_url: str = typer.Option("", help="Full HTTPS join URL (use this OR join-code)."),
    join_code: str = typer.Option("", help="Meeting code / ID (use this OR join-url)."),
    join_passcode: str = typer.Option("", help="Passcode for the meeting code (optional)."),
    conference_record_name: str = typer.Option("", help="Google Meet conference record resource name."),
    start_at: str = typer.Option(..., prompt=True, help="ISO-8601 date/time with timezone offset."),
    end_at: str = typer.Option(..., prompt=True, help="ISO-8601 date/time with timezone offset."),
    description: str = typer.Option(""),
    agenda: str = typer.Option(""),
    join_mode: JoinMode = typer.Option(JoinMode.AS_USER, help="as_user (default) or as_bot."),
    display_name_override: str = typer.Option("", help="Override the display name shown in the meeting."),
    note_taking: bool = typer.Option(True, "--notes/--no-notes"),
    auto_join: bool = typer.Option(False, "--auto-join/--manual-join"),
    recording_requested: bool = typer.Option(False, "--recording/--no-recording"),
) -> None:
    """Schedule a conference. Provide either --join-url or --join-code."""
    async def save_meeting() -> None:
        settings = get_settings()
        await create_database_schema()
        owner_email = await ensure_profile_ready()
        join_authorized = False
        if auto_join:
            console.print(
                "Auto-join will submit the join request automatically at start time."
            )
            join_authorized = Confirm.ask("Authorize this automatic join?")
            if not join_authorized:
                raise typer.Abort()
        if recording_requested:
            console.print(
                "Recording is not started by this service. Platform recording requires "
                "organizer authorization and participant consent on the platform."
            )
        async with AsyncSessionFactory() as session:
            meeting = await create_meeting(
                session,
                settings,
                MeetingCreate(
                    title=title,
                    platform=platform,
                    join_url=join_url,
                    join_code=join_code,
                    join_passcode=join_passcode,
                    owner_email=owner_email,
                    conference_record_name=conference_record_name,
                    scheduled_start_at=parse_datetime(start_at),
                    scheduled_end_at=parse_datetime(end_at),
                    description=description,
                    agenda=agenda,
                    join_mode=join_mode,
                    display_name_override=display_name_override,
                    note_taking_enabled=note_taking,
                    auto_join=auto_join,
                    join_authorized=join_authorized,
                    recording_requested=recording_requested,
                ),
            )
            console.print(f"Created conference [bold]{meeting.meeting_id}[/bold].")
        await dispose_database()

    asyncio.run(save_meeting())


@meeting_app.command("wizard")
def meeting_wizard_command() -> None:
    """Interactive step-by-step conference creation wizard."""
    async def _run():
        settings = get_settings()
        await create_database_schema()
        async with AsyncSessionFactory() as session:
            profile = await get_default_profile(session, settings)
        from confhub.tui.wizard import run_meeting_wizard
        await run_meeting_wizard(AsyncSessionFactory, settings, profile)
        await dispose_database()

    asyncio.run(_run())


@meeting_app.command("list")
def meeting_list_command(
    meeting_status: MeetingStatus | None = typer.Option(None, "--status"),
    platform: MeetingPlatform | None = typer.Option(None, "--platform"),
    search: str | None = typer.Option(None, "--search", "-s", help="Filter by title/description/email."),
    limit: int = typer.Option(50, "--limit", "-n", min=1, max=500),
) -> None:
    """List scheduled conferences."""
    async def show_meetings() -> None:
        await create_database_schema()
        async with AsyncSessionFactory() as session:
            meetings = await list_meetings(session, meeting_status, platform, limit=limit, search=search)
            table = Table(
                title="Conferences",
                border_style="bright_black",
                show_lines=True,
            )
            table.add_column("ID", max_width=10, no_wrap=True)
            table.add_column("Start")
            table.add_column("Platform")
            table.add_column("Mode")
            table.add_column("Status")
            table.add_column("Title", overflow="fold")
            for meeting in meetings:
                table.add_row(
                    meeting.meeting_id[:8],
                    meeting.scheduled_start_at.isoformat(),
                    meeting.platform,
                    meeting.join_mode,
                    meeting.status,
                    meeting.title,
                )
            console.print(table)
        await dispose_database()

    asyncio.run(show_meetings())


@meeting_app.command("show")
def meeting_show_command(meeting_id: str) -> None:
    """Show details of a conference."""
    async def show_meeting() -> None:
        await create_database_schema()
        async with AsyncSessionFactory() as session:
            try:
                meeting = await get_meeting(session, meeting_id)
            except MeetingNotFoundError as error:
                raise typer.BadParameter("Meeting ID not found") from error
            table = Table(
                title=f"Conference {meeting.meeting_id}",
                border_style="bright_black",
            )
            table.add_column("Field", style="dim")
            table.add_column("Value", overflow="fold")
            fields = [
                "title", "platform", "status", "owner_email", "join_url",
                "join_code", "join_passcode", "scheduled_start_at", "scheduled_end_at",
                "join_mode", "display_name_override", "microphone_enabled", "camera_enabled",
                "note_taking_enabled", "auto_join", "join_authorized",
                "recording_status", "failure_reason",
            ]
            for field_name in fields:
                table.add_row(field_name, str(getattr(meeting, field_name)))
            console.print(table)
            if meeting.notes:
                console.print(Rule("[dim]Notes[/dim]", style="bright_black"))
                for note in meeting.notes:
                    console.print(Panel(
                        note.content,
                        title=f"{note.note_type} ({note.created_at.strftime('%Y-%m-%d %H:%M')} UTC)",
                        border_style="bright_black",
                    ))
        await dispose_database()

    asyncio.run(show_meeting())


@meeting_app.command("join")
def meeting_join_command(meeting_id: str) -> None:
    """Join a conference by ID."""
    async def join_now() -> None:
        import webbrowser

        settings = get_settings()
        await create_database_schema()
        await ensure_profile_ready()
        async with AsyncSessionFactory() as session:
            try:
                meeting = await get_meeting(session, meeting_id)
            except MeetingNotFoundError as error:
                raise typer.BadParameter("Meeting ID not found") from error

            # Determine effective display name for the user
            profile = await get_default_profile(session, settings)
            effective_name = (
                meeting.display_name_override
                or (profile.display_name if meeting.join_mode == "as_user" else settings.default_display_name)
            )

            console.print(Panel(
                f"[bold]{meeting.title}[/bold]\n"
                f"Platform:     {meeting.platform}\n"
                f"Join mode:    [cyan]{meeting.join_mode}[/cyan]\n"
                f"Display name: [green]{effective_name}[/green]\n"
                f"Join URL:     {meeting.join_url or '(code: ' + meeting.join_code + ')'}",
                title="Conference Join",
                border_style="green",
            ))

            if not Confirm.ask("Submit join request?", default=False):
                raise typer.Abort()

            updated_meeting = await join_meeting(
                session,
                settings,
                ProviderRegistry(settings),
                meeting,
                confirm_join=True,
                actor="cli-user",
            )
            console.print(f"Status: [bold]{updated_meeting.status}[/bold]")

            # For URL-based providers, offer browser launch
            if updated_meeting.platform in {"zoom", "webex"}:
                join_url = updated_meeting.join_url
                if not join_url and updated_meeting.join_code:
                    if updated_meeting.platform == "zoom":
                        join_url = f"https://zoom.us/j/{updated_meeting.join_code}"
                        if updated_meeting.join_passcode:
                            join_url += f"?pwd={updated_meeting.join_passcode}"
                    else:
                        join_url = f"https://webex.com/j/{updated_meeting.join_code}"
                if join_url and Confirm.ask("Open join URL in browser?", default=True):
                    webbrowser.open(join_url)
            elif updated_meeting.platform == "google_meet" and updated_meeting.join_url:
                if Confirm.ask("Open Google Meet URL in browser?", default=True):
                    webbrowser.open(updated_meeting.join_url)

        await dispose_database()

    asyncio.run(join_now())


@meeting_app.command("cancel")
def meeting_cancel_command(meeting_id: str) -> None:
    """Cancel a scheduled conference."""
    async def cancel_now() -> None:
        await create_database_schema()
        async with AsyncSessionFactory() as session:
            try:
                meeting = await get_meeting(session, meeting_id)
            except MeetingNotFoundError as error:
                raise typer.BadParameter("Meeting ID not found") from error
            if not Confirm.ask(f"Cancel '{meeting.title}'?", default=False):
                raise typer.Abort()
            updated_meeting = await cancel_meeting(session, meeting, actor="cli-user")
            console.print(f"Status: [bold]{updated_meeting.status}[/bold]")
        await dispose_database()

    asyncio.run(cancel_now())


@meeting_app.command("note")
def meeting_note_command(
    meeting_id: str,
    content: str = typer.Option(..., prompt=True),
    note_type: str = typer.Option("manual", help="manual, summary, action_items, transcript_excerpt"),
) -> None:
    """Add a note to a conference."""
    async def save_note() -> None:
        await create_database_schema()
        async with AsyncSessionFactory() as session:
            meeting = await get_meeting(session, meeting_id)
            note = await add_meeting_note(session, meeting, NoteCreate(content=content, note_type=note_type))
            console.print(f"Saved note [bold]{note.note_id}[/bold].")
        await dispose_database()

    asyncio.run(save_note())


@meeting_app.command("export")
def meeting_export_command(
    meeting_id: str,
    output: str = typer.Option("", "--output", "-o", help="Output file path. Defaults to meeting-<id>.md"),
) -> None:
    """Export a conference (notes and audit log) to a Markdown file."""
    async def do_export() -> None:
        await create_database_schema()
        async with AsyncSessionFactory() as session:
            try:
                meeting = await get_meeting(session, meeting_id)
            except MeetingNotFoundError as error:
                raise typer.BadParameter("Meeting ID not found") from error
            markdown = await export_meeting_to_markdown(session, meeting)
        output_path = output or f"meeting-{meeting_id[:8]}.md"
        Path(output_path).write_text(markdown, encoding="utf-8")
        console.print(f"Exported to [bold]{output_path}[/bold].")
        await dispose_database()

    asyncio.run(do_export())


if __name__ == "__main__":
    app()
