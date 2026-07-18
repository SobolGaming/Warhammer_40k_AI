from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Self, TypedDict, cast

from warhammer40k_core import __version__ as ENGINE_VERSION
from warhammer40k_core.adapters.contracts import AdapterGameSession
from warhammer40k_core.adapters.external_contract import (
    EXTERNAL_CONTRACT_VERSION,
    SESSION_COMMAND_RESULT_SCHEMA_VERSION,
    SESSION_METADATA_SCHEMA_VERSION,
)
from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.game_state import GameConfig
from warhammer40k_core.engine.phase import LifecycleStatus, LifecycleStatusKind

ENGINE_BUILD_ID = f"warhammer40k-core-v2:{ENGINE_VERSION}"

type OperationalClock = Callable[[], datetime]


class SessionProtocolError(ValueError):
    """Raised when server-owned session protocol state is invalid."""


class ParticipantRole(StrEnum):
    PLAYER = "player"
    SPECTATOR = "spectator"
    OBSERVER = "observer"


class SessionState(StrEnum):
    CREATED = "created"
    ACTIVE = "active"
    TERMINAL = "terminal"
    CLOSED = "closed"


class ParticipantAssignmentPayload(TypedDict):
    participant_id: str
    role: str
    player_id: str | None


class TerminalReasonPayload(TypedDict):
    code: str
    message: str


class SessionMetadataPayload(TypedDict):
    schema_version: str
    session_id: str
    game_id: str
    session_state: str
    session_revision: int
    ruleset_id: JsonValue
    catalog_id: str
    source_package_id: str
    source_hash: str
    projection_state_hash: str | None
    event_cursor: int
    lifecycle_status: JsonValue
    terminal_reason: TerminalReasonPayload | None
    created_at: str
    last_activity_at: str
    participant_assignments: list[ParticipantAssignmentPayload]
    server_contract_version: str
    engine_version: str
    engine_build_id: str


class SessionCheckpointPayload(TypedDict):
    viewer_player_id: str
    projection_state_hash: str
    event_cursor: int


class SessionEventRangePayload(TypedDict):
    from_cursor: int
    to_cursor: int


class SessionCommandResultPayload(TypedDict):
    schema_version: str
    operation: str
    accepted: bool
    session: SessionMetadataPayload
    checkpoint: SessionCheckpointPayload
    event_range: SessionEventRangePayload


@dataclass(frozen=True, slots=True)
class ParticipantAssignment:
    participant_id: str
    role: ParticipantRole
    player_id: str | None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "participant_id",
            _validate_identifier("participant_id", self.participant_id),
        )
        if type(self.role) is not ParticipantRole:
            raise SessionProtocolError("Participant assignment role is invalid.")
        if self.role is ParticipantRole.PLAYER:
            object.__setattr__(
                self,
                "player_id",
                _validate_identifier("player_id", self.player_id),
            )
        elif self.player_id is not None:
            raise SessionProtocolError(
                "Spectator and observer assignments cannot control a player."
            )

    @classmethod
    def from_payload(cls, payload: JsonValue) -> Self:
        if not isinstance(payload, dict):
            raise SessionProtocolError("Participant assignment must be an object.")
        if set(payload) != {"participant_id", "role", "player_id"}:
            raise SessionProtocolError("Participant assignment keys are invalid.")
        role_value = payload["role"]
        if type(role_value) is not str:
            raise SessionProtocolError("Participant assignment role must be a string.")
        try:
            role = ParticipantRole(role_value)
        except ValueError as exc:
            raise SessionProtocolError("Participant assignment role is unsupported.") from exc
        player_id = payload["player_id"]
        if player_id is not None and type(player_id) is not str:
            raise SessionProtocolError("Participant assignment player_id is invalid.")
        participant_id = payload["participant_id"]
        if type(participant_id) is not str:
            raise SessionProtocolError("Participant assignment participant_id is invalid.")
        return cls(
            participant_id=participant_id,
            role=role,
            player_id=player_id,
        )

    def to_payload(self) -> ParticipantAssignmentPayload:
        return {
            "participant_id": self.participant_id,
            "role": self.role.value,
            "player_id": self.player_id,
        }


@dataclass(slots=True)
class AuthoritativeSession:
    session_id: str
    game_id: str
    adapter_session: AdapterGameSession
    player_ids: tuple[str, ...]
    participant_assignments: tuple[ParticipantAssignment, ...]
    ruleset_id: JsonValue
    catalog_id: str
    source_package_id: str
    source_hash: str
    lifecycle_status: LifecycleStatus
    created_at: str
    last_activity_at: str
    session_revision: int = 0
    started: bool = False
    closed: bool = False

    def __post_init__(self) -> None:
        self.session_id = _validate_identifier("session_id", self.session_id)
        self.game_id = _validate_identifier("game_id", self.game_id)
        self.player_ids = _validated_player_ids(self.player_ids)
        self.participant_assignments = validate_participant_assignments(
            self.participant_assignments,
            player_ids=self.player_ids,
        )
        self.ruleset_id = validate_json_value(self.ruleset_id)
        self.catalog_id = _validate_identifier("catalog_id", self.catalog_id)
        self.source_package_id = _validate_identifier(
            "source_package_id",
            self.source_package_id,
        )
        self.source_hash = _validate_sha256("source_hash", self.source_hash)
        if type(self.lifecycle_status) is not LifecycleStatus:
            raise SessionProtocolError("Session lifecycle status is invalid.")
        self.created_at = _validate_timestamp("created_at", self.created_at)
        self.last_activity_at = _validate_timestamp("last_activity_at", self.last_activity_at)
        if _parse_timestamp(self.last_activity_at) < _parse_timestamp(self.created_at):
            raise SessionProtocolError("Session activity timestamp predates creation.")
        if type(self.session_revision) is not int or self.session_revision < 0:
            raise SessionProtocolError("Session revision must be non-negative.")
        if type(self.started) is not bool or type(self.closed) is not bool:
            raise SessionProtocolError("Session state flags must be bool values.")

    @classmethod
    def create(
        cls,
        *,
        session_id: str,
        adapter_session: AdapterGameSession,
        config: GameConfig,
        participant_assignments: tuple[ParticipantAssignment, ...],
        lifecycle_status: LifecycleStatus,
        created_at: str,
    ) -> Self:
        if type(config) is not GameConfig:
            raise SessionProtocolError("Session creation requires GameConfig.")
        catalog_view = adapter_session.rules_catalog_view()
        if catalog_view["catalog_id"] != config.army_catalog.catalog_id:
            raise SessionProtocolError("Session catalog identity drifted during creation.")
        if catalog_view["source_package_id"] != config.army_catalog.source_package_id:
            raise SessionProtocolError("Session source package drifted during creation.")
        return cls(
            session_id=session_id,
            game_id=config.game_id,
            adapter_session=adapter_session,
            player_ids=config.player_ids,
            participant_assignments=participant_assignments,
            ruleset_id=validate_json_value(config.ruleset_descriptor.ruleset_id.to_payload()),
            catalog_id=catalog_view["catalog_id"],
            source_package_id=catalog_view["source_package_id"],
            source_hash=catalog_view["source_hash"],
            lifecycle_status=lifecycle_status,
            created_at=created_at,
            last_activity_at=created_at,
        )

    @property
    def state(self) -> SessionState:
        if self.closed:
            return SessionState.CLOSED
        if self.lifecycle_status.status_kind is LifecycleStatusKind.TERMINAL:
            return SessionState.TERMINAL
        if self.started:
            return SessionState.ACTIVE
        return SessionState.CREATED

    def touch(self, timestamp: str) -> None:
        activity = _validate_timestamp("last_activity_at", timestamp)
        if _parse_timestamp(activity) < _parse_timestamp(self.last_activity_at):
            raise SessionProtocolError("Session activity timestamp cannot move backwards.")
        self.last_activity_at = activity

    def accept_status(self, status: LifecycleStatus, *, timestamp: str) -> None:
        if type(status) is not LifecycleStatus:
            raise SessionProtocolError("Accepted session status is invalid.")
        self.lifecycle_status = status
        self.session_revision += 1
        self.touch(timestamp)

    def reject_status(self, status: LifecycleStatus, *, timestamp: str) -> None:
        if type(status) is not LifecycleStatus:
            raise SessionProtocolError("Rejected session status is invalid.")
        self.lifecycle_status = status
        self.touch(timestamp)

    def close(self, *, timestamp: str) -> None:
        self.closed = True
        self.session_revision += 1
        self.touch(timestamp)

    def metadata_payload(
        self,
        *,
        lifecycle_status: JsonValue,
        projection_state_hash: str | None,
        event_cursor: int,
    ) -> SessionMetadataPayload:
        if projection_state_hash is not None:
            projection_state_hash = _validate_sha256(
                "projection_state_hash",
                projection_state_hash,
            )
        if type(event_cursor) is not int or event_cursor < 0:
            raise SessionProtocolError("Session event cursor must be non-negative.")
        payload: SessionMetadataPayload = {
            "schema_version": SESSION_METADATA_SCHEMA_VERSION,
            "session_id": self.session_id,
            "game_id": self.game_id,
            "session_state": self.state.value,
            "session_revision": self.session_revision,
            "ruleset_id": self.ruleset_id,
            "catalog_id": self.catalog_id,
            "source_package_id": self.source_package_id,
            "source_hash": self.source_hash,
            "projection_state_hash": projection_state_hash,
            "event_cursor": event_cursor,
            "lifecycle_status": validate_json_value(lifecycle_status),
            "terminal_reason": self._terminal_reason(),
            "created_at": self.created_at,
            "last_activity_at": self.last_activity_at,
            "participant_assignments": [
                assignment.to_payload() for assignment in self.participant_assignments
            ],
            "server_contract_version": EXTERNAL_CONTRACT_VERSION,
            "engine_version": ENGINE_VERSION,
            "engine_build_id": ENGINE_BUILD_ID,
        }
        validate_json_value(cast(JsonValue, payload))
        return payload

    def _terminal_reason(self) -> TerminalReasonPayload | None:
        if self.closed:
            return {"code": "session_closed", "message": "Session was closed."}
        if self.lifecycle_status.status_kind is LifecycleStatusKind.TERMINAL:
            message = self.lifecycle_status.message
            if message is None:
                raise SessionProtocolError("Terminal lifecycle status requires a message.")
            return {"code": "game_complete", "message": message}
        return None


def utc_operational_clock() -> datetime:
    return datetime.now(UTC)


def operational_timestamp(clock: OperationalClock) -> str:
    if not callable(clock):
        raise SessionProtocolError("Operational clock must be callable.")
    value = clock()
    if type(value) is not datetime or value.tzinfo is None or value.utcoffset() is None:
        raise SessionProtocolError("Operational clock must return an aware datetime.")
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def participant_assignments_from_payload(
    payload: JsonValue,
    *,
    player_ids: tuple[str, ...],
) -> tuple[ParticipantAssignment, ...]:
    if not isinstance(payload, list):
        raise SessionProtocolError("Participant assignments must be an array.")
    return validate_participant_assignments(
        tuple(ParticipantAssignment.from_payload(value) for value in payload),
        player_ids=player_ids,
    )


def default_participant_assignments(
    player_ids: tuple[str, ...],
) -> tuple[ParticipantAssignment, ...]:
    players = _validated_player_ids(player_ids)
    return tuple(
        ParticipantAssignment(
            participant_id=player_id,
            role=ParticipantRole.PLAYER,
            player_id=player_id,
        )
        for player_id in players
    )


def validate_participant_assignments(
    assignments: tuple[ParticipantAssignment, ...],
    *,
    player_ids: tuple[str, ...],
) -> tuple[ParticipantAssignment, ...]:
    if type(assignments) is not tuple or not assignments:
        raise SessionProtocolError("Participant assignments must be a non-empty tuple.")
    players = _validated_player_ids(player_ids)
    seen_participants: set[str] = set()
    controlled_players: list[str] = []
    validated: list[ParticipantAssignment] = []
    for assignment in assignments:
        if type(assignment) is not ParticipantAssignment:
            raise SessionProtocolError(
                "Participant assignments must contain ParticipantAssignment values."
            )
        if assignment.participant_id in seen_participants:
            raise SessionProtocolError("Participant IDs must be unique within a session.")
        seen_participants.add(assignment.participant_id)
        if assignment.role is ParticipantRole.PLAYER:
            player_id = assignment.player_id
            if player_id is None:
                raise SessionProtocolError("Player assignment requires player_id.")
            controlled_players.append(player_id)
        validated.append(assignment)
    if len(controlled_players) != len(set(controlled_players)):
        raise SessionProtocolError("Each player may have only one controlling participant.")
    if set(controlled_players) != set(players):
        raise SessionProtocolError("Participant assignments must control every game player.")
    return tuple(validated)


def session_command_result_payload(
    *,
    operation: str,
    accepted: bool,
    session: SessionMetadataPayload,
    checkpoint: SessionCheckpointPayload,
    from_cursor: int,
) -> SessionCommandResultPayload:
    operation_id = _validate_identifier("operation", operation)
    if type(accepted) is not bool:
        raise SessionProtocolError("Session command accepted flag must be bool.")
    to_cursor = checkpoint["event_cursor"]
    if type(from_cursor) is not int or from_cursor < 0 or from_cursor > to_cursor:
        raise SessionProtocolError("Session command event range is invalid.")
    payload: SessionCommandResultPayload = {
        "schema_version": SESSION_COMMAND_RESULT_SCHEMA_VERSION,
        "operation": operation_id,
        "accepted": accepted,
        "session": session,
        "checkpoint": checkpoint,
        "event_range": {
            "from_cursor": from_cursor,
            "to_cursor": to_cursor,
        },
    }
    validate_json_value(cast(JsonValue, payload))
    return payload


def _validated_player_ids(values: tuple[str, ...]) -> tuple[str, ...]:
    if type(values) is not tuple or not values:
        raise SessionProtocolError("Session player IDs must be a non-empty tuple.")
    validated = tuple(_validate_identifier("player_id", value) for value in values)
    if len(validated) != len(set(validated)):
        raise SessionProtocolError("Session player IDs must be unique.")
    return validated


def _validate_sha256(field_name: str, value: object) -> str:
    identifier = _validate_identifier(field_name, value)
    if len(identifier) != 64 or any(
        character not in "0123456789abcdef" for character in identifier
    ):
        raise SessionProtocolError(f"{field_name} must be a lowercase SHA-256 digest.")
    return identifier


def _validate_timestamp(field_name: str, value: object) -> str:
    if type(value) is not str or not value.endswith("Z"):
        raise SessionProtocolError(f"{field_name} must be a UTC timestamp.")
    _parse_timestamp(value)
    return value


def _parse_timestamp(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise SessionProtocolError("Session timestamp is invalid.") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise SessionProtocolError("Session timestamp must be timezone-aware.")
    return parsed.astimezone(UTC)


_validate_identifier = IdentifierValidator(SessionProtocolError)
