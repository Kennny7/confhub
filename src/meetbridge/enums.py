from enum import StrEnum


class MeetingPlatform(StrEnum):
    TEAMS = "teams"
    GOOGLE_MEET = "google_meet"
    ZOOM = "zoom"
    WEBEX = "webex"
    UNKNOWN = "unknown"


class MeetingStatus(StrEnum):
    SCHEDULED = "scheduled"
    JOINING = "joining"
    JOINED = "joined"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class RecordingStatus(StrEnum):
    NOT_REQUESTED = "not_requested"
    PENDING_AUTHORIZATION = "pending_authorization"
    BLOCKED = "blocked"
    PLATFORM_MANAGED = "platform_managed"
    COMPLETED = "completed"
