from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from confhub.api.dependencies import get_provider_registry
from confhub.config import Settings, get_settings
from confhub.database import get_session
from confhub.enums import MeetingPlatform, MeetingStatus
from confhub.providers.base import ProviderError, UnsupportedCapabilityError
from confhub.providers.google_meet import GoogleMeetProvider
from confhub.providers.registry import ProviderRegistry
from confhub.schemas import (
    JoinRequest,
    MeetingCreate,
    MeetingRead,
    NoteCreate,
    NoteRead,
    RecordingAuthorizationRequest,
    SummarizeRequest,
)
from confhub.security import require_api_access
from confhub.services.meeting_service import (
    AuthorizationRequiredError,
    MeetingNotFoundError,
    add_meeting_note,
    authorize_recording,
    cancel_meeting,
    create_meeting,
    export_meeting_to_markdown,
    get_meeting,
    join_meeting,
    list_meetings,
)
from confhub.services.notes_service import summarise_meeting_transcript
from confhub.services.recording_service import evaluate_recording_eligibility

router = APIRouter(
    prefix="/api/v1/meetings",
    tags=["meetings"],
    dependencies=[Depends(require_api_access)],
)


@router.post("", response_model=MeetingRead, status_code=status.HTTP_201_CREATED)
async def create_meeting_endpoint(
    meeting_data: MeetingCreate,
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
):
    try:
        return await create_meeting(session, settings, meeting_data)
    except UnsupportedCapabilityError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@router.get("", response_model=list[MeetingRead])
async def list_meetings_endpoint(
    meeting_status: MeetingStatus | None = Query(default=None, alias="status"),
    platform: MeetingPlatform | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    search: str | None = Query(default=None, description="Filter by title/description/email"),
    session: AsyncSession = Depends(get_session),
):
    return await list_meetings(session, meeting_status, platform, limit, search)


@router.get("/{meeting_id}", response_model=MeetingRead)
async def get_meeting_endpoint(
    meeting_id: str,
    session: AsyncSession = Depends(get_session),
):
    try:
        return await get_meeting(session, meeting_id)
    except MeetingNotFoundError as error:
        raise HTTPException(status_code=404, detail="Meeting not found") from error


@router.post("/{meeting_id}/join", response_model=MeetingRead)
async def join_meeting_endpoint(
    meeting_id: str,
    request_data: JoinRequest,
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
    provider_registry: ProviderRegistry = Depends(get_provider_registry),
):
    try:
        meeting = await get_meeting(session, meeting_id)
        return await join_meeting(
            session,
            settings,
            provider_registry,
            meeting,
            request_data.confirm_join,
            actor="api-user",
        )
    except MeetingNotFoundError as error:
        raise HTTPException(status_code=404, detail="Meeting not found") from error
    except AuthorizationRequiredError as error:
        raise HTTPException(status_code=403, detail=str(error)) from error
    except UnsupportedCapabilityError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except ProviderError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error


@router.post("/{meeting_id}/cancel", response_model=MeetingRead)
async def cancel_meeting_endpoint(
    meeting_id: str,
    session: AsyncSession = Depends(get_session),
):
    try:
        meeting = await get_meeting(session, meeting_id)
        return await cancel_meeting(session, meeting, actor="api-user")
    except MeetingNotFoundError as error:
        raise HTTPException(status_code=404, detail="Meeting not found") from error


@router.post("/{meeting_id}/recording-authorization", response_model=MeetingRead)
async def recording_authorization_endpoint(
    meeting_id: str,
    request_data: RecordingAuthorizationRequest,
    session: AsyncSession = Depends(get_session),
):
    try:
        meeting = await get_meeting(session, meeting_id)
        return await authorize_recording(
            session,
            meeting,
            request_data.authorization_reference,
            request_data.organizer_authorized,
            actor="api-user",
        )
    except MeetingNotFoundError as error:
        raise HTTPException(status_code=404, detail="Meeting not found") from error
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.post("/{meeting_id}/notes", response_model=NoteRead, status_code=status.HTTP_201_CREATED)
async def add_note_endpoint(
    meeting_id: str,
    note_data: NoteCreate,
    session: AsyncSession = Depends(get_session),
):
    try:
        meeting = await get_meeting(session, meeting_id)
        return await add_meeting_note(session, meeting, note_data)
    except MeetingNotFoundError as error:
        raise HTTPException(status_code=404, detail="Meeting not found") from error


@router.get("/{meeting_id}/notes", response_model=list[NoteRead])
async def list_notes_endpoint(
    meeting_id: str,
    session: AsyncSession = Depends(get_session),
):
    try:
        meeting = await get_meeting(session, meeting_id)
        return meeting.notes
    except MeetingNotFoundError as error:
        raise HTTPException(status_code=404, detail="Meeting not found") from error


@router.post("/{meeting_id}/summarise", response_model=NoteRead, status_code=status.HTTP_201_CREATED)
async def summarise_transcript_endpoint(
    meeting_id: str,
    request_data: SummarizeRequest,
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
):
    try:
        meeting = await get_meeting(session, meeting_id)
        return await summarise_meeting_transcript(
            session,
            settings,
            meeting,
            request_data.transcript,
            request_data.transcript_consent_confirmed,
        )
    except MeetingNotFoundError as error:
        raise HTTPException(status_code=404, detail="Meeting not found") from error
    except PermissionError as error:
        raise HTTPException(status_code=403, detail=str(error)) from error
    except RuntimeError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error


@router.get("/{meeting_id}/export")
async def export_meeting_endpoint(
    meeting_id: str,
    session: AsyncSession = Depends(get_session),
):
    """Export meeting details, notes, and audit log as Markdown."""
    try:
        meeting = await get_meeting(session, meeting_id)
        content = await export_meeting_to_markdown(session, meeting)
        from fastapi.responses import PlainTextResponse
        return PlainTextResponse(content=content, media_type="text/markdown")
    except MeetingNotFoundError as error:
        raise HTTPException(status_code=404, detail="Meeting not found") from error


@router.get("/{meeting_id}/google-artifacts")
async def fetch_google_meet_artifacts_endpoint(
    meeting_id: str,
    session: AsyncSession = Depends(get_session),
    provider_registry: ProviderRegistry = Depends(get_provider_registry),
):
    try:
        meeting = await get_meeting(session, meeting_id)
        if meeting.platform != MeetingPlatform.GOOGLE_MEET.value:
            raise HTTPException(status_code=409, detail="Meeting is not a Google Meet meeting")
        if not meeting.conference_record_name:
            raise HTTPException(
                status_code=422,
                detail="Set conference_record_name before requesting Google Meet artifacts",
            )
        provider = provider_registry.get(MeetingPlatform.GOOGLE_MEET)
        if not isinstance(provider, GoogleMeetProvider):
            raise HTTPException(status_code=500, detail="Google Meet provider is unavailable")
        return await provider.fetch_artifact_bundle(meeting.conference_record_name)
    except MeetingNotFoundError as error:
        raise HTTPException(status_code=404, detail="Meeting not found") from error
    except ProviderError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error


@router.get("/{meeting_id}/recording-eligibility")
async def recording_eligibility_endpoint(
    meeting_id: str,
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
    provider_registry: ProviderRegistry = Depends(get_provider_registry),
):
    try:
        meeting = await get_meeting(session, meeting_id)
        provider = provider_registry.get(meeting.platform)
        return evaluate_recording_eligibility(meeting, provider.capabilities(), settings)
    except MeetingNotFoundError as error:
        raise HTTPException(status_code=404, detail="Meeting not found") from error
