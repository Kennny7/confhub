from sqlalchemy.ext.asyncio import AsyncSession

from confhub.models import AuditEvent, Meeting


async def write_audit_event(
    session: AsyncSession,
    meeting: Meeting,
    event_type: str,
    actor: str = "system",
    details: str = "",
) -> None:
    session.add(
        AuditEvent(
            meeting_id=meeting.meeting_id,
            event_type=event_type,
            actor=actor,
            details=details[:10000],
        )
    )
