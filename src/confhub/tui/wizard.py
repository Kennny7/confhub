"""Step-by-step meeting creation wizard using Rich prompts."""

from datetime import datetime

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm, Prompt
from rich.rule import Rule
from rich.table import Table

from confhub.enums import JoinMode, MeetingPlatform
from confhub.schemas import MeetingCreate
from confhub.services.meeting_service import create_meeting

console = Console()

PLATFORMS = {
    "1": ("teams", "Microsoft Teams"),
    "2": ("google_meet", "Google Meet"),
    "3": ("zoom", "Zoom"),
    "4": ("webex", "Cisco Webex"),
}


def _parse_dt(value: str) -> datetime:
    try:
        dt = datetime.fromisoformat(value)
    except ValueError as err:
        raise ValueError("Use ISO-8601 with offset, e.g. 2026-11-18T14:30:00+05:30") from err
    if dt.tzinfo is None:
        raise ValueError("Must include a timezone offset such as +05:30") from None
    return dt


async def run_meeting_wizard(session_factory, settings, profile) -> object | None:
    """Interactive multi-step meeting creation wizard."""
    console.print()
    console.print(Rule("[bold cyan]New Conference Wizard[/bold cyan]", style="bright_cyan"))
    console.print()

    # Step 1: Title
    title = Prompt.ask("[bold]Step 1 of 7[/bold]  Meeting title")
    if not title.strip():
        console.print("[red]Title cannot be empty. Wizard cancelled.[/red]")
        return None

    # Step 2: Platform selection
    console.print()
    console.print("[bold]Step 2 of 7[/bold]  Select platform")
    for key, (_, label) in PLATFORMS.items():
        console.print(f"  [{key}] {label}")
    platform_choice = Prompt.ask("Enter number", choices=list(PLATFORMS.keys()))
    platform_value, platform_label = PLATFORMS[platform_choice]

    # Step 3: Join URL or code
    console.print()
    console.print("[bold]Step 3 of 7[/bold]  How do you want to specify the meeting?")
    console.print("  [1] Full join URL  (e.g. https://zoom.us/j/123456)")
    console.print("  [2] Meeting code / ID  (e.g. 123 456 789 for Zoom)")
    link_type = Prompt.ask("Enter number", choices=["1", "2"])

    join_url = ""
    join_code = ""
    join_passcode = ""

    if link_type == "1":
        join_url = Prompt.ask("Join URL (must start with https://)")
    else:
        join_code = Prompt.ask("Meeting code / ID")
        join_passcode = Prompt.ask("Passcode (leave blank if none)", default="")

    # Step 4: Schedule
    console.print()
    console.print("[bold]Step 4 of 7[/bold]  Schedule")
    console.print("[dim]Format: YYYY-MM-DDTHH:MM:SS+HH:MM  (e.g. 2026-11-18T14:30:00+05:30)[/dim]")
    while True:
        try:
            start_at = _parse_dt(Prompt.ask("Start time"))
            break
        except ValueError as exc:
            console.print(f"[red]{exc}[/red]")
    while True:
        try:
            end_at = _parse_dt(Prompt.ask("End time"))
            if end_at <= start_at:
                console.print("[red]End time must be after start time.[/red]")
                continue
            break
        except ValueError as exc:
            console.print(f"[red]{exc}[/red]")

    # Step 5: Description and agenda
    console.print()
    console.print("[bold]Step 5 of 7[/bold]  Details (optional)")
    description = Prompt.ask("Description", default="")
    agenda = Prompt.ask("Agenda", default="")

    # Step 6: Join mode
    console.print()
    console.print("[bold]Step 6 of 7[/bold]  How should this meeting be joined?")
    console.print(f"  [1] As yourself  (display name: [green]{profile.display_name or 'Your name from profile'}[/green])")
    console.print("  [2] As assistant  (requires a labelled bot/assistant identity)")
    mode_choice = Prompt.ask("Enter number", choices=["1", "2"], default="1")
    join_mode = JoinMode.AS_USER if mode_choice == "1" else JoinMode.AS_BOT
    display_name_override = ""
    if join_mode == JoinMode.AS_BOT:
        display_name_override = Prompt.ask(
            "Bot display name (must include 'bot' or 'assistant')",
            default="ConfHub Assistant (Bot)",
        )

    # Step 7: Options
    console.print()
    console.print("[bold]Step 7 of 7[/bold]  Options")
    note_taking = Confirm.ask("Enable note taking?", default=True)
    auto_join = Confirm.ask("Enable automatic join when window opens?", default=False)
    join_authorized = False
    if auto_join:
        console.print("[yellow]Auto-join will submit the join request automatically at start time.[/yellow]")
        join_authorized = Confirm.ask("Authorize this automatic join?", default=False)
        if not join_authorized:
            console.print("[dim]Auto-join disabled.[/dim]")
            auto_join = False

    # Preview
    console.print()
    console.print(Rule("[dim]Preview[/dim]", style="bright_black"))
    preview_table = Table(show_header=False, border_style="bright_black", padding=(0, 2))
    preview_table.add_column("Field", style="dim")
    preview_table.add_column("Value")
    preview_table.add_row("Title", title)
    preview_table.add_row("Platform", platform_label)
    preview_table.add_row("Join URL", join_url or "(none)")
    preview_table.add_row("Join code", join_code or "(none)")
    preview_table.add_row("Passcode", join_passcode or "(none)")
    preview_table.add_row("Start", start_at.isoformat())
    preview_table.add_row("End", end_at.isoformat())
    preview_table.add_row("Join mode", join_mode.value)
    preview_table.add_row("Display name", display_name_override or profile.display_name or "(from profile)")
    preview_table.add_row("Note taking", "yes" if note_taking else "no")
    preview_table.add_row("Auto join", "yes" if auto_join else "no")
    console.print(Panel(preview_table, border_style="bright_cyan"))

    if not Confirm.ask("Save this meeting?", default=True):
        console.print("[dim]Cancelled.[/dim]")
        return None

    try:
        meeting_create = MeetingCreate(
            title=title,
            platform=MeetingPlatform(platform_value),
            join_url=join_url,
            join_code=join_code,
            join_passcode=join_passcode,
            owner_email=profile.email,
            scheduled_start_at=start_at,
            scheduled_end_at=end_at,
            description=description,
            agenda=agenda,
            join_mode=join_mode,
            display_name_override=display_name_override,
            note_taking_enabled=note_taking,
            auto_join=auto_join,
            join_authorized=join_authorized,
        )
        async with session_factory() as session:
            meeting = await create_meeting(session, settings, meeting_create)
        console.print(f"[green]Meeting saved. ID: [bold]{meeting.meeting_id}[/bold][/green]")
        return meeting
    except Exception as exc:
        console.print(f"[red]Failed to save meeting: {exc}[/red]")
        return None
