from sqlalchemy.ext.asyncio import AsyncSession

from meetbridge.config import Settings
from meetbridge.integrations.llm import LocalLLMClient
from meetbridge.models import Meeting, MeetingNote
from meetbridge.services.audit_service import write_audit_event


async def summarise_meeting_transcript(
    session: AsyncSession,
    settings: Settings,
    meeting: Meeting,
    transcript: str,
    transcript_consent_confirmed: bool,
) -> MeetingNote:
    if not transcript_consent_confirmed:
        raise PermissionError(
            "Transcript processing is blocked until the requester confirms that processing is authorised"
        )

    summary = await LocalLLMClient(settings).summarise_transcript(meeting.title, transcript)
    meeting.transcript_consent_confirmed = True
    note = MeetingNote(
        meeting_id=meeting.meeting_id,
        note_type="summary",
        content=summary,
    )
    session.add(note)
    await write_audit_event(
        session,
        meeting,
        "transcript_summarised",
        actor="user",
        details="Transcript processing consent confirmed by requester; raw transcript was not persisted.",
    )
    await session.commit()
    await session.refresh(note)
    return note
