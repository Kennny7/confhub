# ConfHub

ConfHub is a platform-neutral conference management and real-user participation assistant built with FastAPI, SQLAlchemy, Typer, Rich, APScheduler, and `uv`.

It lets you register conference links or meeting codes across Microsoft Teams, Google Meet, Zoom, and Cisco Webex, then manage and join those conferences as yourself using your real account credentials and your real display name. It also supports a scheduled auto-join window, an interactive terminal dashboard, manual notes, AI-assisted transcript summarisation, audit logging, and post-meeting artifact retrieval.

> **Platform reality:** ConfHub is a Python management layer. Live audio/video media is handled by the platform client the user opens. For Teams, live joining requires a separately deployed .NET calling-bot gateway (see `docs/teams-gateway-contract.md`). For Google Meet, the REST API is used for post-meeting artifacts only. For Zoom and Webex, the adapter constructs a join URL and can open it in the user's browser or client.

## Capabilities

- **Interactive terminal dashboard** (`confhub ui`) with live meeting list, join/cancel/note/export actions.
- **Step-by-step meeting creation wizard** (`confhub meeting wizard`) supporting both full URLs and meeting codes.
- **Four platform providers**: Teams (gateway), Google Meet (REST/artifacts), Zoom (OAuth2 + URL), Webex (OAuth2 + URL).
- **Real-user join mode** (default): join using your own display name from your profile. Bot-labelled mode retained as an opt-in.
- **Meeting codes and passcodes**: create meetings with Zoom IDs, Webex meeting numbers, etc.
- **Platform OAuth flows**: `confhub zoom-auth`, `confhub webex-auth`, `confhub google-auth`.
- **Per-platform credential storage** in the local database.
- **Search and filter** in `confhub meeting list` by title, description, platform, status.
- **Markdown export** (`confhub meeting export`) of notes and audit log.
- **FastAPI service** with API-key protection, full CRUD for meetings, notes, profiles, platform capabilities, and credentials.
- **Webhook handlers** for Teams call events and Zoom event callbacks.
- **Scheduled auto-join** with a start/end window and explicit authorization gate.
- **LLM transcript summarisation** (OpenAI-compatible, local model) with consent gate.
- **Consent-aware recording model**: policy checks, organizer authorization tracking, participant consent state.
- **SQLite** for local development; PostgreSQL-compatible for production.
- **Alembic migrations**, Dockerfile, Compose, Ruff, mypy, and pytest.

## Explicit limits in this release

| Platform / feature | Current status |
|---|---|
| Microsoft Teams live join | Python adapter implemented; requires the external .NET calling-bot gateway described in `docs/teams-gateway-contract.md`. |
| Teams application-hosted media | Not implemented in Python. Microsoft documents this as a C#/.NET and Windows Server/Azure workload. |
| Google Meet live join | Not supported by this adapter. The Google Meet REST API does not expose general live media joining. |
| Google Meet attendance / artifacts | Implemented through the Meet REST API when the user has authorised OAuth access. |
| Zoom live join | Adapter constructs the join URL from meeting ID and passcode. The user opens it in their Zoom client or browser. Post-meeting attendance and cloud recordings retrieved via API. |
| Webex live join | Same as Zoom: adapter constructs the join URL; the user opens it in Webex. Post-meeting participant and recording reports available via API. |
| Local audio/video recording | Intentionally not implemented. Recording metadata and authorization state are tracked; the platform handles recording. |
| Live automatic speech recognition | Not implemented. Notes and transcript summarisation are user-supplied. |

## Project tree

```text
meetbridge/           <- repository root (rename folder to confhub if desired)
├── .env.example
├── .dockerignore
├── .gitignore
├── .python-version
├── Makefile
├── Dockerfile
├── compose.yaml
├── pyproject.toml
├── alembic.ini
├── README.md
├── docs/
│   ├── architecture.md
│   ├── platform-support.md
│   ├── security-and-consent.md
│   └── teams-gateway-contract.md
├── migrations/
│   ├── env.py
│   ├── script.py.mako
│   └── versions/
│       ├── 0001_initial_schema.py
│       └── 0002_confhub_rename_and_extend.py
├── src/
│   └── confhub/
│       ├── __init__.py
│       ├── cli.py
│       ├── config.py
│       ├── database.py
│       ├── enums.py
│       ├── logging_config.py
│       ├── models.py
│       ├── scheduler.py
│       ├── schemas.py
│       ├── security.py
│       ├── api/
│       │   ├── main.py
│       │   ├── dependencies.py
│       │   └── routes/
│       │       ├── credentials.py
│       │       ├── health.py
│       │       ├── meetings.py
│       │       ├── profiles.py
│       │       ├── providers.py
│       │       └── webhooks.py
│       ├── integrations/
│       │   └── llm.py
│       ├── providers/
│       │   ├── base.py
│       │   ├── google_meet.py
│       │   ├── registry.py
│       │   ├── teams.py
│       │   ├── webex.py
│       │   └── zoom.py
│       ├── services/
│       │   ├── audit_service.py
│       │   ├── credential_service.py
│       │   ├── meeting_service.py
│       │   ├── notes_service.py
│       │   ├── profile_service.py
│       │   └── recording_service.py
│       └── tui/
│           ├── auth_wizard.py
│           ├── dashboard.py
│           ├── profile_wizard.py
│           └── wizard.py
└── tests/
    ├── test_consent_and_service.py
    ├── test_provider_capabilities.py
    ├── test_recording_policy.py
    └── test_schemas.py
```

## Requirements

- Python 3.12 or newer.
- `uv` (install from [astral.sh/uv](https://astral.sh/uv)).
- SQLite for local use, or PostgreSQL for multi-instance deployment.
- For Teams live calling: Azure app registration, admin consent, and a registered Teams calling bot. Application-hosted real-time media additionally requires the Microsoft-supported C#/.NET and Windows Server/Azure stack.
- For Google Meet artifacts: a Google Cloud OAuth desktop application with the required Meet scopes.
- For Zoom: a Zoom OAuth app created at marketplace.zoom.us with the required scopes.
- For Webex: a Webex OAuth integration created at developer.webex.com.
- Optional: an OpenAI-compatible local LLM endpoint for transcript summarisation.

## Install and run locally

```bash
# From the repository root
uv sync --all-extras

# Copy and configure environment
cp .env.example .env
# Edit .env: set DEFAULT_USER_NAME, DEFAULT_USER_EMAIL, DATABASE_URL, etc.

# Generate a strong API key (required for non-loopback API access)
python -c "import secrets; print(secrets.token_urlsafe(48))"

# Initialise the database and seed the default profile
uv run confhub init

# Apply migrations for a deployment-managed database
uv run alembic upgrade head

# Start the API
uv run confhub serve

# Launch the interactive terminal dashboard
uv run confhub ui
```

API documentation is available at `http://127.0.0.1:8090/docs`.

Run the scheduler in a separate process:

```bash
uv run confhub worker
```

## Set up your profile

Your display name in the profile is used as your join display name when `join_mode=as_user` (the default).

```bash
# Interactive wizard
uv run confhub profile wizard

# Or set directly
uv run confhub profile set
uv run confhub profile show
```

Or configure via `.env` before `confhub init`:

```dotenv
DEFAULT_USER_NAME=Jane Smith
DEFAULT_USER_EMAIL=jane@example.com
DEFAULT_USER_LOCATION=Mumbai, India
DEFAULT_USER_TIMEZONE=Asia/Kolkata
```

## Connect platforms

### Google Meet

```bash
# Create an OAuth desktop client in Google Cloud Console, download JSON to secrets/
uv run confhub google-auth
```

### Zoom

```bash
# Set ZOOM_OAUTH_CLIENT_ID and ZOOM_OAUTH_CLIENT_SECRET in .env first
uv run confhub zoom-auth
```

### Webex

```bash
# Set WEBEX_OAUTH_CLIENT_ID and WEBEX_OAUTH_CLIENT_SECRET in .env first
uv run confhub webex-auth
```

### Teams

Configure `TEAMS_GATEWAY_URL` and `TEAMS_GATEWAY_TOKEN` after deploying the Teams .NET bot gateway described in `docs/teams-gateway-contract.md`.

## Check configuration

```bash
uv run confhub doctor
uv run confhub platforms
```

## Schedule a conference

Using the interactive wizard:

```bash
uv run confhub meeting wizard
```

Using direct options with a full URL:

```bash
uv run confhub meeting add \
  --title "Project planning" \
  --platform zoom \
  --join-url "https://zoom.us/j/123456789?pwd=abc" \
  --start-at "2026-11-18T14:00:00+05:30" \
  --end-at "2026-11-18T15:00:00+05:30"
```

Using a Zoom meeting code and passcode instead of a full URL:

```bash
uv run confhub meeting add \
  --title "Weekly sync" \
  --platform zoom \
  --join-code "123 456 789" \
  --join-passcode "secret" \
  --start-at "2026-11-18T10:00:00+05:30" \
  --end-at "2026-11-18T11:00:00+05:30"
```

```bash
uv run confhub meeting list
uv run confhub meeting list --platform zoom --status scheduled
uv run confhub meeting list --search "planning"
uv run confhub meeting show MEETING_ID
uv run confhub meeting join MEETING_ID
uv run confhub meeting cancel MEETING_ID
uv run confhub meeting note MEETING_ID
uv run confhub meeting export MEETING_ID --output notes.md
```

## Join modes

| Mode | Behaviour |
|------|-----------|
| `as_user` (default) | Your real display name from the profile is shown in the conference. The adapter constructs or returns the join URL for you to open. |
| `as_bot` | A labelled assistant identity (e.g. "ConfHub Assistant (Bot)") is used. For Teams, this goes through the .NET gateway. |

## Configure the optional local LLM

```dotenv
LLM_PROVIDER=openai-compatible
LLM_BASE_URL=http://127.0.0.1:8000/v1
LLM_MODEL=your-served-model-name
LLM_API_KEY=not-required-for-local-server
```

After submitting a transcript via the API, the summary is stored as a meeting note. The raw transcript is never persisted.

## Recording and consent model

Recording is disabled by default. ConfHub tracks whether recording was requested, whether the organizer supplied an authorization reference, and what the participant consent state is. It does not capture audio or video. The platform must handle recording, announce it, obtain participant consent, and report the state back via webhook.

## API examples

Create a meeting with a Zoom join code:

```bash
curl -X POST http://127.0.0.1:8090/api/v1/meetings \
  -H "X-API-Key: $CONFHUB_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Weekly sync",
    "platform": "zoom",
    "join_code": "123456789",
    "join_passcode": "secret",
    "scheduled_start_at": "2026-11-18T10:00:00+05:30",
    "scheduled_end_at": "2026-11-18T11:00:00+05:30",
    "join_mode": "as_user",
    "note_taking_enabled": true
  }'
```

Join a meeting:

```bash
curl -X POST http://127.0.0.1:8090/api/v1/meetings/MEETING_ID/join \
  -H "X-API-Key: $CONFHUB_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"confirm_join": true}'
```

Export a meeting as Markdown:

```bash
curl http://127.0.0.1:8090/api/v1/meetings/MEETING_ID/export \
  -H "X-API-Key: $CONFHUB_API_KEY" > meeting.md
```

## Tests and quality checks

```bash
uv run pytest -q
uv run ruff check .
uv run ruff format --check .
```

## Docker

Set `API_KEY` in `.env` before using Compose.

```bash
docker compose build
docker compose up -d
```

## Operational checklist

- Rotate any credentials that have been pasted into terminals, tickets, chat, or source code.
- Keep `.env`, `secrets/`, OAuth token files, and recordings out of Git.
- Set `API_KEY` before any non-loopback deployment.
- Use HTTPS and restrict network access to the API and webhook endpoints.
- Configure platform OAuth and admin consent with the minimum required permissions.
- Apply data-retention and deletion controls to transcripts and notes.

## Official platform references

- [Microsoft Graph create call](https://learn.microsoft.com/en-us/graph/api/application-post-calls?view=graph-rest-1.0)
- [Register a Teams calls and meetings bot](https://learn.microsoft.com/en-us/microsoftteams/platform/bots/calls-and-meetings/registering-calling-bot)
- [Google Meet REST API overview](https://developers.google.com/workspace/meet/api/guides/overview)
- [Zoom OAuth documentation](https://developers.zoom.us/docs/integrations/oauth/)
- [Zoom Meeting REST API](https://developers.zoom.us/docs/api/rest/reference/zoom-api/methods/)
- [Webex developer documentation](https://developer.webex.com/docs/getting-started)
- [Webex Meetings API](https://developer.webex.com/docs/api/v1/meetings)
