# Architecture

## Request flow

```text
CLI / Client
    |
    v
FastAPI routes ---------------------------> API-key / loopback guard
    |                                                |
    v                                                v
Application services -----------------------> SQLAlchemy async session
    |
    +--> Provider registry
    |       |
    |       +--> Teams gateway adapter -----> external .NET Teams calling bot
    |       |
    |       +--> Google Meet REST adapter --> official conference/artifact API
    |
    +--> Notes service ---------------------> optional OpenAI-compatible local LLM
    |
    +--> Audit service ---------------------> audit_events table

APScheduler worker --> due/authorised meeting query --> provider registry
```

## Main boundaries

- **API layer:** validation, HTTP status mapping, and authentication.
- **Service layer:** scheduling, authorisation checks, persistence, audit events, notes.
- **Provider layer:** platform capabilities and provider-specific calls. Unsupported capabilities fail explicitly.
- **Integration layer:** optional local LLM client and external platform clients.
- **Persistence:** SQLAlchemy models; SQLite locally, PostgreSQL in production.

## Scheduling model

A meeting has a `scheduled_start_at` and `scheduled_end_at`. The worker only dispatches meetings within that interval when both `auto_join` and `join_authorized` are true. A manual join requires a separate confirmation. Cancelled and completed meetings cannot be joined.

## Bot identity and media policy

The bot display name must contain `bot` or `assistant`. The Python Teams adapter sends `microphone_enabled=false` and `camera_enabled=false` to the gateway. No code path in this service enables either device. Raw media capture is not implemented.

## Database entities

- `user_profiles`: environment-seeded defaults and persisted user profile.
- `meetings`: meeting metadata, join window, provider state, user options, and consent state.
- `meeting_notes`: manual notes and generated summaries.
- `audit_events`: join, cancellation, recording authorisation, and note events.

## Horizontal scaling

Use PostgreSQL rather than SQLite, run multiple API workers behind a TLS reverse proxy, and run a single scheduler worker or introduce a distributed lock before running multiple schedulers. The included APScheduler worker is intentionally single-process and does not claim distributed exactly-once scheduling.
