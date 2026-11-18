import hmac

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from confhub.config import Settings, get_settings
from confhub.database import get_session
from confhub.enums import MeetingStatus
from confhub.models import Meeting
from confhub.services.audit_service import write_audit_event

router = APIRouter(prefix="/api/v1/webhooks", tags=["webhooks"])


class TeamsCallEvent(BaseModel):
    meeting_id: str = Field(min_length=1, max_length=36)
    call_id: str = Field(min_length=1, max_length=200)
    event: str = Field(min_length=1, max_length=80)
    details: str = Field(default="", max_length=5000)


@router.post("/teams/call-event")
async def receive_teams_call_event(
    event_data: TeamsCallEvent,
    x_teams_webhook_secret: str = Header(default=""),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
):
    if not settings.teams_webhook_secret or not hmac.compare_digest(
        x_teams_webhook_secret, settings.teams_webhook_secret
    ):
        raise HTTPException(status_code=401, detail="Invalid Teams webhook secret")

    meeting = await session.get(Meeting, event_data.meeting_id)
    if meeting is None or meeting.provider_call_id != event_data.call_id:
        raise HTTPException(status_code=404, detail="Meeting or call identifier not found")

    event_name = event_data.event.lower()
    if event_name == "call_established":
        meeting.status = MeetingStatus.JOINED.value
    elif event_name == "call_ended":
        meeting.status = MeetingStatus.COMPLETED.value
    elif event_name == "call_failed":
        meeting.status = MeetingStatus.FAILED.value
        meeting.failure_reason = "Teams gateway reported call_failed"
    else:
        raise HTTPException(status_code=422, detail="Unsupported call event")

    await write_audit_event(
        session,
        meeting,
        f"teams_{event_name}",
        actor="teams-gateway",
        details=event_data.details,
    )
    await session.commit()
    return {"accepted": True, "meeting_id": meeting.meeting_id, "status": meeting.status}


class TeamsConsentEvent(BaseModel):
    meeting_id: str = Field(min_length=1, max_length=36)
    call_id: str = Field(min_length=1, max_length=200)
    consent_state: str = Field(pattern="^(pending|granted|denied|partial)$")
    details: str = Field(default="", max_length=5000)


@router.post("/teams/participant-consent")
async def receive_teams_consent_event(
    event_data: TeamsConsentEvent,
    x_teams_webhook_secret: str = Header(default=""),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
):
    if not settings.teams_webhook_secret or not hmac.compare_digest(
        x_teams_webhook_secret, settings.teams_webhook_secret
    ):
        raise HTTPException(status_code=401, detail="Invalid Teams webhook secret")

    meeting = await session.get(Meeting, event_data.meeting_id)
    if meeting is None or meeting.provider_call_id != event_data.call_id:
        raise HTTPException(status_code=404, detail="Meeting or call identifier not found")

    meeting.participant_consent_state = event_data.consent_state
    await write_audit_event(
        session,
        meeting,
        "teams_participant_consent_updated",
        actor="teams-gateway",
        details=event_data.details,
    )
    await session.commit()
    return {
        "accepted": True,
        "meeting_id": meeting.meeting_id,
        "participant_consent_state": meeting.participant_consent_state,
    }


class ZoomWebhookEvent(BaseModel):
    """Generic Zoom webhook event envelope."""
    event: str = Field(min_length=1, max_length=80)
    payload: dict = Field(default_factory=dict)


@router.post("/zoom/event")
async def receive_zoom_event(
    event_data: ZoomWebhookEvent,
    x_zoom_signature: str = Header(default=""),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
):
    """Receive Zoom webhook event callbacks (meeting.ended, participant.joined, etc.)."""
    # Zoom signature validation would use HMAC-SHA256 against the webhook secret.
    # Set up webhook secret validation here when deploying to production.
    event_name = event_data.event
    payload = event_data.payload
    meeting_id_raw = str(payload.get("object", {}).get("uuid", "") or payload.get("meeting_id", ""))

    if not meeting_id_raw:
        return {"accepted": True, "note": "No meeting_id in payload; event acknowledged."}

    # Look up the meeting by provider_call_id (Zoom UUID).
    from sqlalchemy import select

    from confhub.models import Meeting as MeetingModel

    stmt = select(MeetingModel).where(MeetingModel.provider_call_id == meeting_id_raw)
    result = await session.scalars(stmt)
    meeting = result.first()

    if meeting is None:
        return {"accepted": True, "note": "No matching meeting found; event acknowledged."}

    if event_name == "meeting.ended":
        meeting.status = MeetingStatus.COMPLETED.value
    elif event_name == "meeting.started":
        if meeting.status == MeetingStatus.SCHEDULED.value:
            meeting.status = MeetingStatus.JOINING.value

    await write_audit_event(
        session,
        meeting,
        f"zoom_{event_name.replace('.', '_')}",
        actor="zoom-webhook",
        details=str(payload)[:5000],
    )
    await session.commit()
    return {"accepted": True, "meeting_id": meeting.meeting_id, "status": meeting.status}
