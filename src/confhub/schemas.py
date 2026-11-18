from datetime import datetime
from typing import Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from confhub.enums import JoinMode, MeetingPlatform, MeetingStatus


class ProfileRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    user_id: str
    display_name: str
    email: str
    location: str
    timezone_name: str


class ProfileUpdate(BaseModel):
    display_name: str = Field(min_length=1, max_length=160)
    email: str = Field(default="", max_length=320)
    location: str = Field(default="", max_length=160)
    timezone_name: str = Field(default="Asia/Kolkata", max_length=80)


class PlatformCredentialRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    credential_id: str
    platform: str
    scopes: str
    created_at: datetime
    updated_at: datetime


class PlatformCredentialUpsert(BaseModel):
    platform: MeetingPlatform
    token_data: str = Field(min_length=1, max_length=50000)
    scopes: str = Field(default="", max_length=2000)


class MeetingCreate(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    platform: MeetingPlatform
    # Either join_url (full HTTPS link) or join_code (meeting ID / code) must be provided.
    join_url: str = Field(default="", max_length=2000)
    join_code: str = Field(default="", max_length=200)
    join_passcode: str = Field(default="", max_length=100)
    owner_email: str = Field(default="", max_length=320)
    conference_record_name: str = Field(default="", max_length=300)
    scheduled_start_at: datetime
    scheduled_end_at: datetime
    description: str = Field(default="", max_length=10000)
    agenda: str = Field(default="", max_length=10000)
    join_mode: JoinMode = JoinMode.AS_USER
    # Optional display name override. When empty and join_mode=as_user, profile name is used.
    display_name_override: str = Field(default="", max_length=160)
    note_taking_enabled: bool = True
    auto_join: bool = False
    join_authorized: bool = False
    recording_requested: bool = False

    @field_validator("join_url")
    @classmethod
    def validate_join_url(cls, value: str) -> str:
        if not value:
            return value
        parsed_url = urlsplit(value)
        if parsed_url.scheme != "https" or not parsed_url.hostname:
            raise ValueError("Meeting links must use HTTPS and include a hostname")
        if parsed_url.username or parsed_url.password:
            raise ValueError("Meeting links must not contain embedded credentials")
        return value

    @field_validator("scheduled_start_at", "scheduled_end_at")
    @classmethod
    def require_timezone_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Date/time values must include a UTC offset or timezone")
        return value

    @model_validator(mode="after")
    def validate_all(self) -> "MeetingCreate":
        if not self.join_url and not self.join_code:
            raise ValueError("Provide either join_url (full HTTPS link) or join_code (meeting code/ID)")
        if self.scheduled_end_at <= self.scheduled_start_at:
            raise ValueError("scheduled_end_at must be after scheduled_start_at")
        if self.auto_join and not self.join_authorized:
            raise ValueError("auto_join requires explicit join_authorized=true")

        if self.join_url:
            meeting_host = (urlsplit(self.join_url).hostname or "").lower().rstrip(".")
            allowed_hosts: dict[MeetingPlatform, set[str]] = {
                MeetingPlatform.TEAMS: {
                    "teams.microsoft.com",
                    "teams.live.com",
                    "teams.cloud.microsoft",
                },
                MeetingPlatform.GOOGLE_MEET: {"meet.google.com"},
                MeetingPlatform.ZOOM: {
                    "zoom.us",
                    "us02web.zoom.us",
                    "us04web.zoom.us",
                    "us06web.zoom.us",
                },
                MeetingPlatform.WEBEX: {
                    "webex.com",
                    "cisco.webex.com",
                },
            }
            if self.platform in allowed_hosts:
                if meeting_host not in allowed_hosts[self.platform]:
                    raise ValueError(
                        f"The meeting URL host does not match the selected platform: {self.platform.value}"
                    )
        return self


class MeetingRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    meeting_id: str
    owner_email: str
    title: str
    platform: str
    join_url: str
    join_code: str
    join_passcode: str
    conference_record_name: str
    scheduled_start_at: datetime
    scheduled_end_at: datetime
    status: MeetingStatus
    description: str
    agenda: str
    join_mode: str
    display_name_override: str
    microphone_enabled: bool
    camera_enabled: bool
    note_taking_enabled: bool
    auto_join: bool
    join_authorized: bool
    recording_requested: bool
    recording_status: str
    organizer_recording_authorized: bool
    participant_consent_state: str
    transcript_consent_confirmed: bool
    provider_call_id: str
    failure_reason: str
    created_at: datetime
    updated_at: datetime


class JoinRequest(BaseModel):
    confirm_join: bool = False


class RecordingAuthorizationRequest(BaseModel):
    organizer_authorized: bool
    authorization_reference: str = Field(min_length=4, max_length=500)


class NoteCreate(BaseModel):
    content: str = Field(min_length=1, max_length=50000)
    note_type: Literal["manual", "summary", "action_items", "transcript_excerpt"] = "manual"


class NoteRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    note_id: str
    meeting_id: str
    note_type: str
    content: str
    created_at: datetime


class SummarizeRequest(BaseModel):
    transcript: str = Field(min_length=30, max_length=200000)
    transcript_consent_confirmed: bool = False


class ProviderCapabilitiesRead(BaseModel):
    platform: str
    available: bool
    can_join_live: bool
    can_fetch_attendance: bool
    can_fetch_transcripts: bool
    can_fetch_recordings: bool
    can_record_live: bool
    explanation: str
