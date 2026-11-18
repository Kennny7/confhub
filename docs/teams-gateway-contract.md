# Teams .NET calling-bot gateway contract

The Python service intentionally separates meeting orchestration from the Teams calling runtime. A Teams gateway may use Microsoft Graph call-control APIs with service-hosted media when its features fit that model. If it needs direct access to live media streams, Microsoft documents application-hosted media bots as C#/.NET applications using `Microsoft.Graph.Communications.Calls.Media` and a supported Windows Server/Azure host.

This repository contains the Python HTTP client and the contract below. It does **not** contain or claim to implement the actual Teams calling bot. The gateway must be registered as a Teams calling bot, configured with the required Graph permissions, and reviewed by the tenant administrator.

## Configuration

```dotenv
TEAMS_GATEWAY_URL=https://teams-gateway.internal.example
TEAMS_GATEWAY_TOKEN=<strong-secret>
TEAMS_WEBHOOK_SECRET=<different-strong-secret>
TEAMS_RECORDING_GATEWAY_ENABLED=false
```

## Join request

`POST {TEAMS_GATEWAY_URL}/v1/calls/join`

Headers:

```http
Authorization: Bearer <TEAMS_GATEWAY_TOKEN>
Content-Type: application/json
```

Request body:

```json
{
  "meeting_id": "meetingbridge-meeting-uuid",
  "meeting_url": "https://teams.microsoft.com/l/meetup-join/...",
  "subject": "Project planning",
  "bot_display_name": "MeetBridge Assistant (Bot)",
  "microphone_enabled": false,
  "camera_enabled": false,
  "note_taking_enabled": true,
  "recording_requested": false
}
```

Successful response:

```json
{
  "call_id": "provider-call-id",
  "state": "joining",
  "bot_display_name": "MeetBridge Assistant (Bot)"
}
```

The `bot_display_name` response must remain explicitly bot-labelled. The gateway must reject attempts to enable the microphone or camera for this service.

## Lifecycle callbacks

The gateway posts a lifecycle event to:

`POST {MEETBRIDGE_API_BASE_URL}/api/v1/webhooks/teams/call-event`

Headers:

```http
X-Teams-Webhook-Secret: <TEAMS_WEBHOOK_SECRET>
Content-Type: application/json
```

Body:

```json
{
  "meeting_id": "meetingbridge-meeting-uuid",
  "call_id": "provider-call-id",
  "event": "call_established",
  "details": "The Teams call is established."
}
```

Supported event values: `call_established`, `call_ended`, `call_failed`.

## Recording extension requirements

The current Python adapter always sends `recording_requested=false`. Do not change that until the gateway implements all of the following:

1. Verify that recording is enabled by tenant policy and by the meeting organiser.
2. Notify meeting participants and capture the platform's participant-consent state.
3. Use the required Microsoft Graph recording-status lifecycle and wait for successful acknowledgement before persisting media.
4. Stop recording before reporting the recording-stopped state to Microsoft Graph.
5. Store media in an access-controlled location with retention and deletion controls.
6. Emit auditable `recording_started`, `recording_stopped`, and consent events back to MeetBridge.

The adapter's `TEAMS_RECORDING_GATEWAY_ENABLED` flag alone does not implement or authorise recording.

## Participant-consent callback

After the gateway has collected the platform's consent result for the entire meeting, it may post the aggregate state to:

`POST {MEETBRIDGE_API_BASE_URL}/api/v1/webhooks/teams/participant-consent`

Use the same `X-Teams-Webhook-Secret` header and body:

```json
{
  "meeting_id": "meetingbridge-meeting-uuid",
  "call_id": "provider-call-id",
  "consent_state": "granted",
  "details": "The gateway observed the platform consent state for all required participants."
}
```

Allowed states are `pending`, `granted`, `denied`, and `partial`. The gateway must not report `granted` merely because the organiser approved recording; it must reflect the platform's participant-level consent outcome.
