from confhub.config import Settings
from confhub.models import Meeting
from confhub.providers.base import ProviderCapabilities


def evaluate_recording_eligibility(
    meeting: Meeting,
    capabilities: ProviderCapabilities,
    settings: Settings,
) -> dict[str, object]:
    blocking_reasons: list[str] = []
    if not settings.recording_enabled:
        blocking_reasons.append("Recording is disabled by service configuration")
    if not meeting.recording_requested:
        blocking_reasons.append("Recording was not requested for this meeting")
    if not meeting.organizer_recording_authorized:
        blocking_reasons.append("Organizer authorisation has not been recorded")
    if meeting.participant_consent_state != "granted":
        blocking_reasons.append("Participant consent has not been confirmed by the platform gateway")
    if not capabilities.can_record_live:
        blocking_reasons.append("The configured provider does not support live recording")
    return {
        "eligible": not blocking_reasons,
        "can_start_recording": False,
        "blocking_reasons": blocking_reasons,
        "note": (
            "Eligibility is a policy check only. This release does not start or capture raw media; "
            "the platform gateway must still perform the required recording-status handshake."
        ),
    }
