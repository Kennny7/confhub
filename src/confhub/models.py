from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.types import TypeDecorator


def utc_now() -> datetime:
    return datetime.now(UTC)


class UTCDateTime(TypeDecorator[datetime]):
    """Store UTC-normalised datetimes and restore timezone information on SQLite."""

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Datetime values must be timezone-aware")
        return value.astimezone(UTC).replace(tzinfo=None)

    def process_result_value(self, value: datetime | None, dialect) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)


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

    credentials: Mapped[list["PlatformCredential"]] = relationship(
        back_populates="user_profile", cascade="all, delete-orphan", lazy="selectin"
    )


class PlatformCredential(Base):
    """Stores per-platform OAuth tokens for real-user authentication."""

    __tablename__ = "platform_credentials"

    credential_id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid4())
    )
    user_id: Mapped[str] = mapped_column(
        ForeignKey("user_profiles.user_id", ondelete="CASCADE"), index=True
    )
    platform: Mapped[str] = mapped_column(String(40), index=True)
    # JSON-encoded token blob. Store secrets backend encryption in production.
    token_data: Mapped[str] = mapped_column(Text, default="")
    scopes: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now, onupdate=utc_now)

    user_profile: Mapped[UserProfile] = relationship(back_populates="credentials")


class Meeting(Base):
    __tablename__ = "meetings"

    meeting_id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid4())
    )
    owner_email: Mapped[str] = mapped_column(String(320), default="", index=True)
    title: Mapped[str] = mapped_column(String(300))
    platform: Mapped[str] = mapped_column(String(40), index=True)
    join_url: Mapped[str] = mapped_column(Text, default="")
    # Raw meeting code / ID (e.g. Zoom meeting ID, Teams code). Resolved to a URL at join time.
    join_code: Mapped[str] = mapped_column(String(200), default="")
    # Passcode associated with join_code (e.g. Zoom passcode).
    join_passcode: Mapped[str] = mapped_column(String(100), default="")
    conference_record_name: Mapped[str] = mapped_column(String(300), default="")
    scheduled_start_at: Mapped[datetime] = mapped_column(UTCDateTime(), index=True)
    scheduled_end_at: Mapped[datetime] = mapped_column(UTCDateTime(), index=True)
    status: Mapped[str] = mapped_column(String(32), default="scheduled", index=True)
    description: Mapped[str] = mapped_column(Text, default="")
    agenda: Mapped[str] = mapped_column(Text, default="")
    # Join mode: "as_user" uses the owner's real name; "as_bot" uses a labelled bot identity.
    join_mode: Mapped[str] = mapped_column(String(20), default="as_user")
    # Display name override. When empty and join_mode=as_user, the profile display_name is used.
    display_name_override: Mapped[str] = mapped_column(String(160), default="")
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

    note_id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid4())
    )
    meeting_id: Mapped[str] = mapped_column(
        ForeignKey("meetings.meeting_id", ondelete="CASCADE"), index=True
    )
    note_type: Mapped[str] = mapped_column(String(32), default="manual")
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now)

    meeting: Mapped[Meeting] = relationship(back_populates="notes")


class AuditEvent(Base):
    __tablename__ = "audit_events"

    event_id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid4())
    )
    meeting_id: Mapped[str] = mapped_column(
        ForeignKey("meetings.meeting_id", ondelete="CASCADE"), index=True
    )
    event_type: Mapped[str] = mapped_column(String(80), index=True)
    actor: Mapped[str] = mapped_column(String(160), default="system")
    details: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now)

    meeting: Mapped[Meeting] = relationship(back_populates="audit_events")
