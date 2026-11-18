"""Platform OAuth connection wizard."""

import webbrowser

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm, Prompt
from rich.rule import Rule
from rich.table import Table

console = Console()


def _show_platform_status(settings) -> None:
    table = Table(title="Platform Connection Status", border_style="bright_black", show_lines=True)
    table.add_column("Platform")
    table.add_column("Status")
    table.add_column("Action")

    checks = [
        ("Google Meet", settings.google_token_file.exists(), "confhub google-auth"),
        ("Zoom", settings.zoom_configured, "confhub zoom-auth"),
        ("Webex", settings.webex_configured, "confhub webex-auth"),
        ("Teams", settings.teams_gateway_configured, "Set TEAMS_GATEWAY_URL + TEAMS_GATEWAY_TOKEN"),
    ]
    for platform, configured, action in checks:
        status = "[green]Connected[/green]" if configured else "[yellow]Not connected[/yellow]"
        action_text = "[dim]OK[/dim]" if configured else f"[cyan]{action}[/cyan]"
        table.add_row(platform, status, action_text)

    console.print(table)


async def run_auth_wizard(settings, platform: str) -> None:
    """Guide the user through OAuth for a given platform."""
    console.print()
    console.print(Rule(f"[bold cyan]{platform.title()} Authentication[/bold cyan]", style="bright_cyan"))
    console.print()
    _show_platform_status(settings)
    console.print()

    if platform.lower() == "zoom":
        await _zoom_auth_wizard(settings)
    elif platform.lower() == "webex":
        await _webex_auth_wizard(settings)
    elif platform.lower() in {"google", "google_meet", "googlemeet"}:
        console.print(
            "[dim]Google auth is handled by the Google OAuth flow. Run:[/dim]\n"
            "  [cyan]confhub google-auth[/cyan]"
        )
    elif platform.lower() == "teams":
        console.print(
            "[dim]Teams auth requires a deployed .NET gateway. See docs/teams-gateway-contract.md.[/dim]"
        )


async def _zoom_auth_wizard(settings) -> None:
    from confhub.providers.zoom import ZoomProvider
    provider = ZoomProvider(settings)

    if not settings.zoom_oauth_client_id or not settings.zoom_oauth_client_secret:
        console.print(Panel(
            "Before connecting Zoom you need an OAuth app:\n\n"
            "1. Go to [link=https://marketplace.zoom.us]marketplace.zoom.us[/link]\n"
            "2. Click 'Develop' > 'Build App' > choose 'OAuth'\n"
            "3. Set the redirect URI to: [bold]" + settings.zoom_oauth_redirect_uri + "[/bold]\n"
            "4. Copy the Client ID and Secret into your .env file:\n"
            "   [cyan]ZOOM_OAUTH_CLIENT_ID=...[/cyan]\n"
            "   [cyan]ZOOM_OAUTH_CLIENT_SECRET=...[/cyan]\n"
            "5. Re-run this command.",
            title="Zoom OAuth Setup",
            border_style="yellow",
        ))
        return

    auth_url = provider.build_oauth_authorization_url()
    console.print(f"[bold]Authorization URL:[/bold]\n{auth_url}\n")

    if Confirm.ask("Open this URL in your browser now?", default=True):
        webbrowser.open(auth_url)

    console.print(
        "\n[dim]After authorizing, Zoom will redirect you to your redirect URI with a ?code= parameter.[/dim]"
    )
    code = Prompt.ask("Paste the authorization code from the redirect URL")
    if not code.strip():
        console.print("[red]No code provided. Cancelled.[/red]")
        return

    try:
        await provider.exchange_code_for_token(code.strip())
        console.print(f"[green]Zoom connected successfully. Token saved to {settings.zoom_token_file}[/green]")
    except Exception as exc:
        console.print(f"[red]Failed to exchange code: {exc}[/red]")


async def _webex_auth_wizard(settings) -> None:
    from confhub.providers.webex import WebexProvider
    provider = WebexProvider(settings)

    if not settings.webex_oauth_client_id or not settings.webex_oauth_client_secret:
        console.print(Panel(
            "Before connecting Webex you need an OAuth integration:\n\n"
            "1. Go to [link=https://developer.webex.com]developer.webex.com[/link]\n"
            "2. Click 'Start Building Apps' > 'Create an Integration'\n"
            "3. Set the redirect URI to: [bold]" + settings.webex_oauth_redirect_uri + "[/bold]\n"
            "4. Copy the Client ID and Secret into your .env file:\n"
            "   [cyan]WEBEX_OAUTH_CLIENT_ID=...[/cyan]\n"
            "   [cyan]WEBEX_OAUTH_CLIENT_SECRET=...[/cyan]\n"
            "5. Re-run this command.",
            title="Webex OAuth Setup",
            border_style="yellow",
        ))
        return

    auth_url = provider.build_oauth_authorization_url()
    console.print(f"[bold]Authorization URL:[/bold]\n{auth_url}\n")

    if Confirm.ask("Open this URL in your browser now?", default=True):
        webbrowser.open(auth_url)

    console.print(
        "\n[dim]After authorizing, Webex will redirect you to your redirect URI with a ?code= parameter.[/dim]"
    )
    code = Prompt.ask("Paste the authorization code from the redirect URL")
    if not code.strip():
        console.print("[red]No code provided. Cancelled.[/red]")
        return

    try:
        await provider.exchange_code_for_token(code.strip())
        console.print(f"[green]Webex connected successfully. Token saved to {settings.webex_token_file}[/green]")
    except Exception as exc:
        console.print(f"[red]Failed to exchange code: {exc}[/red]")
