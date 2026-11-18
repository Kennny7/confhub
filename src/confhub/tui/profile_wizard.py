"""Profile setup wizard for first-run experience."""

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm, Prompt
from rich.rule import Rule
from rich.table import Table

from confhub.schemas import ProfileUpdate
from confhub.services.profile_service import update_default_profile

console = Console()

COMMON_TIMEZONES = [
    "Asia/Kolkata", "Asia/Dubai", "Asia/Singapore", "Asia/Tokyo",
    "Europe/London", "Europe/Paris", "Europe/Berlin",
    "America/New_York", "America/Chicago", "America/Los_Angeles",
    "Australia/Sydney", "Pacific/Auckland",
]


async def run_profile_wizard(session_factory, settings) -> object | None:
    """Interactive profile setup or update wizard."""
    from confhub.services.profile_service import get_default_profile

    console.print()
    console.print(Rule("[bold cyan]Profile Setup[/bold cyan]", style="bright_cyan"))
    console.print()

    async with session_factory() as session:
        profile = await get_default_profile(session, settings)

    console.print(Panel(
        f"[bold]Current profile[/bold]\n"
        f"Name:     {profile.display_name or '[dim]Not set[/dim]'}\n"
        f"Email:    {profile.email or '[dim]Not set[/dim]'}\n"
        f"Location: {profile.location or '[dim]Not set[/dim]'}\n"
        f"Timezone: {profile.timezone_name}",
        border_style="bright_black",
    ))
    console.print()

    display_name = Prompt.ask(
        "Your full name (used as your display name when joining conferences)",
        default=profile.display_name or "",
    )
    if not display_name.strip():
        console.print("[red]Name is required.[/red]")
        return None

    email = Prompt.ask("Your email address", default=profile.email or "")
    location = Prompt.ask("Your location (optional)", default=profile.location or "")

    console.print("\n[dim]Common timezones:[/dim]")
    for i, tz in enumerate(COMMON_TIMEZONES, 1):
        prefix = "[green]*[/green] " if tz == profile.timezone_name else "  "
        console.print(f"  {prefix}[dim]{i:2}.[/dim] {tz}")
    console.print()

    timezone_name = Prompt.ask(
        "IANA timezone (e.g. Asia/Kolkata)",
        default=profile.timezone_name,
    )

    # Preview
    console.print()
    preview = Table(show_header=False, border_style="bright_black", padding=(0, 2))
    preview.add_column("Field", style="dim")
    preview.add_column("Value")
    preview.add_row("Name", display_name)
    preview.add_row("Email", email or "(not set)")
    preview.add_row("Location", location or "(not set)")
    preview.add_row("Timezone", timezone_name)
    console.print(Panel(preview, title="Preview", border_style="bright_cyan"))

    if not Confirm.ask("Save profile?", default=True):
        console.print("[dim]Cancelled.[/dim]")
        return None

    async with session_factory() as session:
        updated = await update_default_profile(
            session,
            settings,
            ProfileUpdate(
                display_name=display_name,
                email=email,
                location=location,
                timezone_name=timezone_name,
            ),
        )
    console.print(f"[green]Profile saved for [bold]{updated.display_name}[/bold].[/green]")
    return updated
