"""Interactive meeting dashboard using Rich live display."""

import asyncio
from datetime import UTC, datetime

from rich.console import Console
from rich.layout import Layout
from rich.panel import Panel
from rich.prompt import Confirm, Prompt
from rich.table import Table
from rich.text import Text

console = Console()

PLATFORM_LABELS = {
    "teams": "Teams",
    "google_meet": "Google Meet",
    "zoom": "Zoom",
    "webex": "Webex",
    "unknown": "Unknown",
}

STATUS_STYLES = {
    "scheduled": "cyan",
    "joining": "yellow",
    "joined": "green bold",
    "completed": "dim",
    "failed": "red bold",
    "cancelled": "dim red",
}


def _status_text(status: str) -> Text:
    style = STATUS_STYLES.get(status, "white")
    return Text(status.upper(), style=style)


def _time_until(dt: datetime) -> str:
    now = datetime.now(UTC)
    diff = dt - now
    total_seconds = int(diff.total_seconds())
    if total_seconds < 0:
        mins = abs(total_seconds) // 60
        return f"Started {mins}m ago"
    if total_seconds < 3600:
        return f"In {total_seconds // 60}m"
    if total_seconds < 86400:
        return f"In {total_seconds // 3600}h {(total_seconds % 3600) // 60}m"
    return f"In {total_seconds // 86400}d"


def _build_meetings_table(meetings: list) -> Table:
    table = Table(
        title="Scheduled Conferences",
        border_style="bright_black",
        header_style="bold white",
        show_lines=True,
        expand=True,
    )
    table.add_column("ID", style="dim", max_width=9, no_wrap=True)
    table.add_column("Title", overflow="fold", min_width=20)
    table.add_column("Platform", min_width=12)
    table.add_column("Start", min_width=20)
    table.add_column("When", min_width=12)
    table.add_column("Mode", min_width=8)
    table.add_column("Status", min_width=10)

    if not meetings:
        table.add_row(
            "-", "No meetings scheduled", "-", "-", "-", "-", "-"
        )
        return table

    for m in meetings:
        start_local = m.scheduled_start_at.strftime("%Y-%m-%d  %H:%M")
        table.add_row(
            m.meeting_id[:8],
            m.title,
            PLATFORM_LABELS.get(m.platform, m.platform),
            start_local,
            _time_until(m.scheduled_start_at),
            m.join_mode,
            _status_text(m.status),
        )
    return table


def _build_header(profile_name: str) -> Panel:
    text = Text(justify="center")
    text.append("ConfHub", style="bold bright_cyan")
    text.append("  |  Conference Hub", style="dim")
    text.append("  |  Signed in as: ", style="dim")
    text.append(profile_name or "Unknown", style="bold white")
    return Panel(text, border_style="bright_cyan", padding=(0, 2))


def _build_help_panel() -> Panel:
    lines = [
        "[bold white]Commands[/bold white]",
        "",
        "[cyan]j[/cyan]  Join a meeting by ID",
        "[cyan]a[/cyan]  Add a new meeting (wizard)",
        "[cyan]n[/cyan]  Add a note to a meeting",
        "[cyan]x[/cyan]  Cancel a meeting",
        "[cyan]e[/cyan]  Export meeting to Markdown",
        "[cyan]r[/cyan]  Refresh the list",
        "[cyan]q[/cyan]  Quit",
    ]
    return Panel("\n".join(lines), title="Actions", border_style="bright_black", padding=(0, 2))


def _build_profile_panel(profile) -> Panel:
    lines = [
        f"[bold]Name:[/bold]     {profile.display_name or '[dim]Not set[/dim]'}",
        f"[bold]Email:[/bold]    {profile.email or '[dim]Not set[/dim]'}",
        f"[bold]Location:[/bold] {profile.location or '[dim]Not set[/dim]'}",
        f"[bold]Timezone:[/bold] {profile.timezone_name}",
    ]
    return Panel("\n".join(lines), title="Your Profile", border_style="bright_black", padding=(0, 2))


async def run_dashboard(session_factory, settings) -> None:
    """Launch the interactive ConfHub meeting dashboard."""
    from confhub.providers.registry import ProviderRegistry
    from confhub.schemas import NoteCreate
    from confhub.services.meeting_service import (
        MeetingNotFoundError,
        add_meeting_note,
        cancel_meeting,
        export_meeting_to_markdown,
        get_meeting,
        join_meeting,
        list_meetings,
    )
    from confhub.services.profile_service import get_default_profile

    console.clear()
    console.print(_build_header("Loading..."))

    async with session_factory() as session:
        profile = await get_default_profile(session, settings)
        meetings = await list_meetings(session, limit=50)

    while True:
        console.clear()

        # Build layout
        layout = Layout()
        layout.split_column(
            Layout(name="header", size=3),
            Layout(name="main"),
            Layout(name="sidebar", size=12),
        )
        layout["header"].update(_build_header(profile.display_name))
        layout["main"].update(Panel(_build_meetings_table(meetings), border_style="bright_cyan"))
        layout["sidebar"].split_row(
            Layout(_build_profile_panel(profile)),
            Layout(_build_help_panel()),
        )

        console.print(layout)
        console.print()

        action = Prompt.ask(
            "[bold cyan]Action[/bold cyan]",
            choices=["j", "a", "n", "x", "e", "r", "q"],
            default="r",
            show_choices=True,
        )

        if action == "q":
            console.print("\nGoodbye.\n")
            break

        elif action == "r":
            async with session_factory() as session:
                meetings = await list_meetings(session, limit=50)
                profile = await get_default_profile(session, settings)
            console.print("[dim]Refreshed.[/dim]")
            await asyncio.sleep(0.3)

        elif action == "j":
            meeting_id = Prompt.ask("Meeting ID (first 8+ chars)")
            try:
                async with session_factory() as session:
                    meeting = await get_meeting(session, meeting_id)
                    console.print(Panel(
                        f"[bold]{meeting.title}[/bold]\n"
                        f"Platform: {meeting.platform}  |  Mode: [cyan]{meeting.join_mode}[/cyan]\n"
                        f"Join URL: {meeting.join_url or '(code: ' + meeting.join_code + ')'}\n"
                        f"Display name: [green]{meeting.display_name_override or profile.display_name}[/green]",
                        title="Joining",
                        border_style="green",
                    ))
                    confirmed = Confirm.ask("Confirm and submit join request?", default=False)
                    if confirmed:
                        updated = await join_meeting(
                            session,
                            settings,
                            ProviderRegistry(settings),
                            meeting,
                            confirm_join=True,
                            actor="tui-user",
                        )
                        console.print(f"[green]Join request sent. Status: {updated.status}[/green]")
                        if updated.platform in {"zoom", "webex"}:
                            join_url = updated.join_url or (
                                f"https://zoom.us/j/{updated.join_code}"
                                if updated.platform == "zoom"
                                else f"https://webex.com/j/{updated.join_code}"
                            )
                            if Confirm.ask("Open join URL in browser?"):
                                import webbrowser
                                webbrowser.open(join_url)
                    await list_meetings(session, limit=50)
                    meetings = await list_meetings(session, limit=50)
            except MeetingNotFoundError:
                console.print("[red]Meeting ID not found.[/red]")
            except Exception as exc:
                console.print(f"[red]Error: {exc}[/red]")
            Prompt.ask("\nPress Enter to continue", default="")

        elif action == "x":
            meeting_id = Prompt.ask("Meeting ID to cancel")
            try:
                async with session_factory() as session:
                    meeting = await get_meeting(session, meeting_id)
                    confirmed = Confirm.ask(f"Cancel '{meeting.title}'?", default=False)
                    if confirmed:
                        await cancel_meeting(session, meeting, actor="tui-user")
                        console.print("[yellow]Meeting cancelled.[/yellow]")
                        meetings = await list_meetings(session, limit=50)
            except MeetingNotFoundError:
                console.print("[red]Meeting ID not found.[/red]")
            Prompt.ask("\nPress Enter to continue", default="")

        elif action == "n":
            meeting_id = Prompt.ask("Meeting ID")
            content = Prompt.ask("Note content")
            note_type = Prompt.ask(
                "Note type",
                choices=["manual", "summary", "action_items", "transcript_excerpt"],
                default="manual",
            )
            try:
                async with session_factory() as session:
                    meeting = await get_meeting(session, meeting_id)
                    await add_meeting_note(session, meeting, NoteCreate(content=content, note_type=note_type))
                    console.print("[green]Note saved.[/green]")
            except MeetingNotFoundError:
                console.print("[red]Meeting ID not found.[/red]")
            Prompt.ask("\nPress Enter to continue", default="")

        elif action == "e":
            meeting_id = Prompt.ask("Meeting ID to export")
            output_path = Prompt.ask("Output file path", default=f"meeting-{meeting_id[:8]}.md")
            try:
                async with session_factory() as session:
                    meeting = await get_meeting(session, meeting_id)
                    markdown = await export_meeting_to_markdown(session, meeting)
                from pathlib import Path
                Path(output_path).write_text(markdown, encoding="utf-8")
                console.print(f"[green]Exported to {output_path}[/green]")
            except MeetingNotFoundError:
                console.print("[red]Meeting ID not found.[/red]")
            Prompt.ask("\nPress Enter to continue", default="")

        elif action == "a":
            from confhub.tui.wizard import run_meeting_wizard
            new_meeting = await run_meeting_wizard(session_factory, settings, profile)
            if new_meeting:
                async with session_factory() as session:
                    meetings = await list_meetings(session, limit=50)
