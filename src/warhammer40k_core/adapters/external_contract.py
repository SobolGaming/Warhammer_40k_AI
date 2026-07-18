from __future__ import annotations

EXTERNAL_CONTRACT_VERSION = "1.0.0"

CREATE_SESSION_SCHEMA_VERSION = "create-session-v1"
DECISION_REQUEST_VIEW_SCHEMA_VERSION = "decision-request-view-v1"
ERROR_ENVELOPE_SCHEMA_VERSION = "error-envelope-v1"
EVENT_STREAM_DELTA_SCHEMA_VERSION = "event-delta-v1"
FINITE_SUBMISSION_SCHEMA_VERSION = "finite-submission-v1"
LIFECYCLE_STATUS_SCHEMA_VERSION = "lifecycle-status-v1"
PARAMETERIZED_SUBMISSION_SCHEMA_VERSION = "parameterized-submission-v1"


def require_schema_version(*, actual: object, expected: str, payload_name: str) -> None:
    if type(actual) is not str:
        raise ValueError(f"{payload_name} schema_version must be a string.")
    if actual != expected:
        raise ValueError(
            f"{payload_name} schema_version mismatch: expected {expected}, got {actual}."
        )
