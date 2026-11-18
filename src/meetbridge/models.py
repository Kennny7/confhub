from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.types import TypeDecorator


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class UTCDateTime(TypeDecorator[datetime]):
    """Store UTC-normalised datetimes and restore timezone information on SQLite."""

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Datetime values must be timezone-aware")
        return value.astimezone(timezone.utc).replace(tzinfo=None)

    def process_result_value(self, value: datetime | None, dialect) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)


class Base(DeclarativeBase):
    pass


class UserProfile(Base):
    __tablename__ = "user_profiles"

    user_id: Mapped[str] = mapped_column(String(64), primary_key=True, default="default")
    display_name: Mapped[str] = mapped_column(String(160), default="")
    email: Mapped[str] = mapped_column(String(320), default="")
    location: Mapped[str] = mapped_column(String(160), default="")
    timezone_name: Mapped[str] = mapped_column(String(80), default="Asia/Kolkata")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now, onupdate=utc_now)


class Meeting(Base):
    __tablename__ = "meetings"

    meeting_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    owner_email: Mapped[str] = mapped_column(String(320), default="", index=True)
    title: Mapped[str] = mapped_column(String(300))
    platform: Mapped[str] = mapped_column(String(40), index=True)
    join_url: Mapped[str] = mapped_column(Text)
    conference_record_name: Mapped[str] = mapped_column(String(300), default="")
    scheduled_start_at: Mapped[datetime] = mapped_column(UTCDateTime(), index=True)
    scheduled_end_at: Mapped[datetime] = mapped_column(UTCDateTime(), index=True)
    status: Mapped[str] = mapped_column(String(32), default="scheduled", index=True)
    description: Mapped[str] = mapped_column(Text, default="")
    agenda: Mapped[str] = mapped_column(Text, default="")
    bot_display_name: Mapped[str] = mapped_column(String(160), default="MeetBridge Assistant (Bot)")
    microphone_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    camera_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    note_taking_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    auto_join: Mapped[bool] = mapped_column(Boolean, default=False)
    join_authorized: Mapped[bool] = mapped_column(Boolean, default=False)
    recording_requested: Mapped[bool] = mapped_column(Boolean, default=False)
    recording_status: Mapped[str] = mapped_column(String(40), default="not_requested")
    organizer_recording_authorized: Mapped[bool] = mapped_column(Boolean, default=False)
    participant_consent_state: Mapped[str] = mapped_column(String(32), default="pending")
    transcript_consent_confirmed: Mapped[bool] = mapped_column(Boolean, default=False)
    provider_call_id: Mapped[str] = mapped_column(String(200), default="")
    failure_reason: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now, onupdate=utc_now)

    notes: Mapped[list["MeetingNote"]] = relationship(
        back_populates="meeting", cascade="all, delete-orphan", lazy="selectin"
    )
    audit_events: Mapped[list["AuditEvent"]] = relationship(
        back_populates="meeting", cascade="all, delete-orphan", lazy="selectin"
    )


class MeetingNote(Base):
    __tablename__ = "meeting_notes"

    note_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    meeting_id: Mapped[str] = mapped_column(ForeignKey("meetings.meeting_id", ondelete="CASCADE"), index=True)
    note_type: Mapped[str] = mapped_column(String(32), default="manual")
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now)

    meeting: Mapped[Meeting] = relationship(back_populates="notes")


class AuditEvent(Base):
    __tablename__ = "audit_events"

    event_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    meeting_id: Mapped[str] = mapped_column(ForeignKey("meetings.meeting_id", ondelete="CASCADE"), index=True)
    event_type: Mapped[str] = mapped_column(String(80), index=True)
    actor: Mapped[str] = mapped_column(String(160), default="system")
    details: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now)

    meeting: Mapped[Meeting] = relationship(back_populates="audit_events")
