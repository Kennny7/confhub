# Platform support matrix

| Capability | Microsoft Teams | Google Meet | Zoom | Cisco Webex |
|---|---|---|---|---|
| Create/store meeting record | Yes | Yes | Yes | Yes |
| Live join request | Via external .NET Teams bot gateway | No (open URL in browser) | Constructs join URL; opens in Zoom client | Constructs join URL; opens in Webex client |
| Join as real user (as_user mode) | Sent to gateway with real display name | Link opened in browser | Link opened in Zoom client | Link opened in Webex client |
| Join code / meeting ID support | Not applicable (URL only) | Not applicable (URL only) | Yes (numeric meeting ID + passcode) | Yes (meeting number) |
| Attendance retrieval | Not implemented in this adapter | Yes, with Meet REST API access | Yes, via Zoom Reports API | Yes, via Webex Meetings API |
| Transcript entries | Not implemented in this adapter | Yes, when available and authorised | Not implemented | Not implemented |
| Recording metadata | Not implemented in this adapter | Yes, via conference recording resources | Yes, via Zoom cloud recordings API | Yes, via Webex recordings API |
| Live raw-media recording | Not implemented | Not implemented | Not implemented | Not implemented |
| Webhook callbacks | call-event, participant-consent | Not implemented | meeting.ended, meeting.started | Not implemented |

## Microsoft Teams

The Python service calls the gateway contract in `teams-gateway-contract.md`. The actual calling bot must be registered in Teams and granted the required Microsoft Graph permissions and admin consent. Microsoft documents application-hosted media bots as C#/.NET workloads. The Python service is not a replacement for that media stack. The gateway callback is expected to post lifecycle events to `/api/v1/webhooks/teams/call-event` using the configured webhook secret.

## Google Meet

The adapter uses user-authorised OAuth credentials and the Google Meet REST API. It retrieves attendance, transcript entries, and recording metadata using a caller-supplied `conferenceRecords/{id}` resource name. It does not join a running meeting as a bot or through the browser. The discontinued Meet Media API preview is not used.

## Zoom

The adapter manages user OAuth2 tokens (3-legged authorization code flow). It resolves numeric meeting IDs and passcodes into standard Zoom join URLs (`https://zoom.us/j/{id}?pwd={passcode}`). The user opens the URL in their Zoom desktop client or browser. Post-meeting attendance and cloud recording metadata are retrieved via the Zoom REST API.

Connect your Zoom account with:

```bash
confhub zoom-auth
```

## Cisco Webex

The adapter manages user OAuth2 tokens (3-legged authorization code flow). It resolves Webex meeting numbers into standard Webex join URLs (`https://webex.com/j/{number}`). The user opens the URL in their Webex app or browser. Post-meeting participant lists and recording metadata are retrieved via the Webex Meetings API.

Connect your Webex account with:

```bash
confhub webex-auth
```
