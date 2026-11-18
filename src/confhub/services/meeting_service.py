from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from confhub.config import Settings
from confhub.enums import JoinMode, MeetingPlatform, MeetingStatus, RecordingStatus
from confhub.models import Meeting, MeetingNote, UserProfile
from confhub.providers.base import ProviderError, UnsupportedCapabilityError
from confhub.providers.registry import ProviderRegistry
from confhub.schemas import MeetingCreate, NoteCreate
from confhub.services.audit_service import write_audit_event


class MeetingNotFoundError(LookupError):
    pass


class AuthorizationRequiredError(PermissionError):
    pass


async def _resolve_display_name(
    session: AsyncSession,
    meeting: Meeting,
    settings: Settings,
) -> str:
    """Return the name that should appear in the conference for this meeting."""
    if meeting.display_name_override:
        return meeting.display_name_override
    if meeting.join_mode == JoinMode.AS_USER.value:
        profile = await session.get(UserProfile, "default")
        if profile and profile.display_name.strip():
            return profile.display_name
        return settings.default_user_name or "Participant"
    # Bot mode fallback
    return settings.default_display_name


async def create_meeting(
    session: AsyncSession,
    settings: Settings,
    meeting_data: MeetingCreate,
) -> Meeting:
    provider_registry = ProviderRegistry(settings)

    # Only validate provider capability for auto_join; manual joins are always accepted.
    if meeting_data.auto_join and meeting_data.platform not in {
        MeetingPlatform.UNKNOWN,
    }:
        try:
            provider = provider_registry.get(meeting_data.platform)
            provider_capabilities = provider.capabilities()
            if not provider_capabilities.can_join_live:
                raise UnsupportedCapabilityError(
                    f"{meeting_data.platform.value} does not currently support live auto-join. "
                    "Create the meeting without auto_join or configure the provider first."
                )
        except ValueError:
            pass  # Provider not registered; will fail at join time.

    owner_email = meeting_data.owner_email or settings.default_user_email
    if not owner_email:
        saved_profile = await session.get(UserProfile, "default")
        if saved_profile is not None:
            owner_email = saved_profile.email

    meeting = Meeting(
        owner_email=owner_email,
        title=meeting_data.title,
        platform=meeting_data.platform.value,
        join_url=meeting_data.join_url,
        join_code=meeting_data.join_code,
        join_passcode=meeting_data.join_passcode,
        conference_record_name=meeting_data.conference_record_name,
        scheduled_start_at=meeting_data.scheduled_start_at,
        scheduled_end_at=meeting_data.scheduled_end_at,
        description=meeting_data.description,
        agenda=meeting_data.agenda,
        join_mode=meeting_data.join_mode.value,
        display_name_override=meeting_data.display_name_override,
        microphone_enabled=False,
        camera_enabled=False,
        note_taking_enabled=meeting_data.note_taking_enabled,
        auto_join=meeting_data.auto_join,
        join_authorized=meeting_data.join_authorized,
        recording_requested=meeting_data.recording_requested,
        recording_status=(
            RecordingStatus.PENDING_AUTHORIZATION.value
            if meeting_data.recording_requested
            else RecordingStatus.NOT_REQUESTED.value
        ),
    )
    session.add(meeting)
    await session.flush()
    await write_audit_event(
        session,
        meeting,
        "meeting_created",
        actor=owner_email or "local-user",
        details=(
            f"platform={meeting.platform}; join_mode={meeting.join_mode}; "
            f"auto_join={meeting.auto_join}; notes={meeting.note_taking_enabled}; "
            f"recording_requested={meeting.recording_requested}"
        ),
    )
    await session.commit()
    await session.refresh(meeting)
    return meeting


async def get_meeting(session: AsyncSession, meeting_id: str) -> Meeting:
    meeting = await session.get(Meeting, meeting_id)
    if meeting is None:
        raise MeetingNotFoundError(meeting_id)
    return meeting


async def list_meetings(
    session: AsyncSession,
    status: MeetingStatus | None = None,
    platform: MeetingPlatform | None = None,
    limit: int = 100,
    search: str | None = None,
) -> list[Meeting]:
    statement = select(Meeting).order_by(Meeting.scheduled_start_at.asc()).limit(limit)
    if status:
        statement = statement.where(Meeting.status == status.value)
    if platform:
        statement = statement.where(Meeting.platform == platform.value)
    result = await session.scalars(statement)
    meetings = list(result.all())
    if search:
        query = search.lower()
        meetings = [
            m for m in meetings
            if query in m.title.lower()
            or query in m.description.lower()
            or query in m.owner_email.lower()
        ]
    return meetings


async def cancel_meeting(session: AsyncSession, meeting: Meeting, actor: str) -> Meeting:
    if meeting.status in {MeetingStatus.COMPLETED.value, MeetingStatus.CANCELLED.value}:
        return meeting
    meeting.status = MeetingStatus.CANCELLED.value
    meeting.auto_join = False
    await write_audit_event(session, meeting, "meeting_cancelled", actor=actor)
    await session.commit()
    await session.refresh(meeting)
    return meeting


async def join_meeting(
    session: AsyncSession,
    settings: Settings,
    provider_registry: ProviderRegistry,
    meeting: Meeting,
    confirm_join: bool,
    actor: str,
) -> Meeting:
    if not confirm_join:
        raise AuthorizationRequiredError("Confirm that you want to join before the request is submitted.")
    if not meeting.join_authorized:
        if actor == "scheduler-explicitly-authorized":
            raise AuthorizationRequiredError(
                "The scheduled join was not authorised when the meeting was created."
            )
        meeting.join_authorized = True
        await write_audit_event(
            session,
            meeting,
            "join_authorized",
            actor=actor,
            details="User explicitly confirmed join immediately before submitting.",
        )
    if meeting.status in {MeetingStatus.CANCELLED.value, MeetingStatus.COMPLETED.value}:
        raise ValueError(f"Cannot join a meeting with status={meeting.status}")

    provider = provider_registry.get(meeting.platform)
    capabilities = provider.capabilities()
    if not capabilities.can_join_live:
        raise UnsupportedCapabilityError(capabilities.explanation)

    display_name = await _resolve_display_name(session, meeting, settings)

    meeting.status = MeetingStatus.JOINING.value
    await write_audit_event(
        session,
        meeting,
        "join_requested",
        actor=actor,
        details=(
            f"join_mode={meeting.join_mode}; display_name={display_name}; "
            f"microphone=off; camera=off"
        ),
    )
    await session.commit()

    try:
        join_result = await provider.join(meeting, display_name=display_name)
    except ProviderError:
        meeting.status = MeetingStatus.FAILED.value
        meeting.failure_reason = "Provider rejected or could not process the join request"
        await write_audit_event(session, meeting, "join_failed", actor="provider")
        await session.commit()
        raise
    except Exception:
        meeting.status = MeetingStatus.FAILED.value
        meeting.failure_reason = "Unexpected provider error; inspect service logs"
        await write_audit_event(session, meeting, "join_failed", actor="provider")
        await session.commit()
        raise

    meeting.provider_call_id = join_result.provider_call_id
    meeting.display_name_override = join_result.display_name
    meeting.status = (
        MeetingStatus.JOINED.value
        if join_result.state.lower() in {"joined", "connected", "established"}
        else MeetingStatus.JOINING.value
    )
    await write_audit_event(
        session,
        meeting,
        "provider_join_accepted",
        actor="provider",
        details=f"call_id={join_result.provider_call_id}; state={join_result.state}",
    )
    await session.commit()
    await session.refresh(meeting)
    return meeting


async def add_meeting_note(
    session: AsyncSession,
    meeting: Meeting,
    note_data: NoteCreate,
) -> MeetingNote:
    note = MeetingNote(
        meeting_id=meeting.meeting_id,
        note_type=note_data.note_type,
        content=note_data.content,
    )
    session.add(note)
    await write_audit_event(
        session,
        meeting,
        "note_added",
        actor="user",
        details=f"note_type={note_data.note_type}",
    )
    await session.commit()
    await session.refresh(note)
    return note


async def authorize_recording(
    session: AsyncSession,
    meeting: Meeting,
    authorization_reference: str,
    organizer_authorized: bool,
    actor: str,
) -> Meeting:
    if not meeting.recording_requested:
        raise ValueError("Recording was not requested for this meeting")
    meeting.organizer_recording_authorized = organizer_authorized
    if organizer_authorized:
        meeting.recording_status = RecordingStatus.PENDING_AUTHORIZATION.value
    else:
        meeting.recording_status = RecordingStatus.BLOCKED.value
    await write_audit_event(
        session,
        meeting,
        "recording_authorization_recorded",
        actor=actor,
        details=(
            f"organizer_authorized={organizer_authorized}; "
            f"reference={authorization_reference[:450]}"
        ),
    )
    await session.commit()
    await session.refresh(meeting)
    return meeting


async def get_due_auto_join_meetings(session: AsyncSession) -> list[Meeting]:
    current_time = datetime.now(UTC)
    statement = select(Meeting).where(
        Meeting.status == MeetingStatus.SCHEDULED.value,
        Meeting.auto_join.is_(True),
        Meeting.join_authorized.is_(True),
        Meeting.scheduled_start_at <= current_time,
        Meeting.scheduled_end_at >= current_time,
    )
    result = await session.scalars(statement)
    return list(result.all())


async def mark_meeting_completed(
    session: AsyncSession, meeting: Meeting, details: dict[str, Any]
) -> None:
    meeting.status = MeetingStatus.COMPLETED.value
    await write_audit_event(
        session,
        meeting,
        "meeting_completed",
        actor="provider",
        details=str(details)[:9000],
    )
    await session.commit()


async def export_meeting_to_markdown(
    session: AsyncSession,
    meeting: Meeting,
) -> str:
    """Generate a markdown export of a meeting including notes and audit log."""
    lines: list[str] = [
        f"# {meeting.title}",
        "",
        f"**Platform:** {meeting.platform}",
        f"**Status:** {meeting.status}",
        f"**Owner:** {meeting.owner_email}",
        f"**Start:** {meeting.scheduled_start_at.isoformat()}",
        f"**End:** {meeting.scheduled_end_at.isoformat()}",
        f"**Join mode:** {meeting.join_mode}",
    ]
    if meeting.join_url:
        lines.append(f"**Join URL:** {meeting.join_url}")
    if meeting.join_code:
        lines.append(f"**Join code:** {meeting.join_code}")
    if meeting.description:
        lines += ["", "## Description", "", meeting.description]
    if meeting.agenda:
        lines += ["", "## Agenda", "", meeting.agenda]
    if meeting.notes:
        lines += ["", "## Notes", ""]
        for note in meeting.notes:
            lines += [
                f"### {note.note_type} ({note.created_at.strftime('%Y-%m-%d %H:%M')} UTC)",
                "",
                note.content,
                "",
            ]
    if meeting.audit_events:
        lines += ["", "## Audit Log", ""]
        lines.append("| Time | Event | Actor | Details |")
        lines.append("|------|-------|-------|---------|")
        for event in sorted(meeting.audit_events, key=lambda e: e.created_at):
            ts = event.created_at.strftime("%Y-%m-%d %H:%M")
            detail_short = event.details[:80].replace("|", "/") if event.details else ""
            lines.append(f"| {ts} | {event.event_type} | {event.actor} | {detail_short} |")
    return "\n".join(lines)
