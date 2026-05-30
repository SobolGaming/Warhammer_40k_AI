from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Self, TypedDict, cast

from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.scoring import VictoryPointAward


class MissionActionStatus(StrEnum):
    STARTED = "started"
    COMPLETED = "completed"
    INTERRUPTED = "interrupted"


class MissionActionStatePayload(TypedDict):
    action_id: str
    player_id: str
    unit_instance_id: str
    target_id: str
    mission_id: str
    battle_round_started: int
    phase_started: str
    start_timing: str
    completion_timing: str
    eligible_unit_instance_ids: list[str]
    interruption_conditions: list[str]
    scoring_source_id: str
    victory_points: int
    status: str
    completed_battle_round: int | None
    completed_phase: str | None
    interrupted_reason: str | None
    score_transaction_id: str | None


@dataclass(frozen=True, slots=True)
class MissionActionState:
    action_id: str
    player_id: str
    unit_instance_id: str
    target_id: str
    mission_id: str
    battle_round_started: int
    phase_started: str
    start_timing: str
    completion_timing: str
    eligible_unit_instance_ids: tuple[str, ...]
    interruption_conditions: tuple[str, ...]
    scoring_source_id: str
    victory_points: int
    status: MissionActionStatus = MissionActionStatus.STARTED
    completed_battle_round: int | None = None
    completed_phase: str | None = None
    interrupted_reason: str | None = None
    score_transaction_id: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "action_id",
            _validate_identifier("MissionActionState action_id", self.action_id),
        )
        object.__setattr__(
            self,
            "player_id",
            _validate_identifier("MissionActionState player_id", self.player_id),
        )
        object.__setattr__(
            self,
            "unit_instance_id",
            _validate_identifier("MissionActionState unit_instance_id", self.unit_instance_id),
        )
        object.__setattr__(
            self,
            "target_id",
            _validate_identifier("MissionActionState target_id", self.target_id),
        )
        object.__setattr__(
            self,
            "mission_id",
            _validate_identifier("MissionActionState mission_id", self.mission_id),
        )
        object.__setattr__(
            self,
            "battle_round_started",
            _validate_positive_int(
                "MissionActionState battle_round_started",
                self.battle_round_started,
            ),
        )
        object.__setattr__(
            self,
            "phase_started",
            _validate_identifier("MissionActionState phase_started", self.phase_started),
        )
        object.__setattr__(
            self,
            "start_timing",
            _validate_identifier("MissionActionState start_timing", self.start_timing),
        )
        object.__setattr__(
            self,
            "completion_timing",
            _validate_identifier("MissionActionState completion_timing", self.completion_timing),
        )
        eligible_ids = _validate_identifier_tuple(
            "MissionActionState eligible_unit_instance_ids",
            self.eligible_unit_instance_ids,
            min_length=1,
        )
        if self.unit_instance_id not in eligible_ids:
            raise GameLifecycleError("MissionActionState unit must be eligible for action.")
        object.__setattr__(self, "eligible_unit_instance_ids", eligible_ids)
        object.__setattr__(
            self,
            "interruption_conditions",
            _validate_identifier_tuple(
                "MissionActionState interruption_conditions",
                self.interruption_conditions,
                min_length=0,
            ),
        )
        object.__setattr__(
            self,
            "scoring_source_id",
            _validate_identifier("MissionActionState scoring_source_id", self.scoring_source_id),
        )
        object.__setattr__(
            self,
            "victory_points",
            _validate_positive_int("MissionActionState victory_points", self.victory_points),
        )
        object.__setattr__(self, "status", mission_action_status_from_token(self.status))
        object.__setattr__(
            self,
            "completed_battle_round",
            _validate_optional_positive_int(
                "MissionActionState completed_battle_round",
                self.completed_battle_round,
            ),
        )
        object.__setattr__(
            self,
            "completed_phase",
            _validate_optional_identifier(
                "MissionActionState completed_phase",
                self.completed_phase,
            ),
        )
        object.__setattr__(
            self,
            "interrupted_reason",
            _validate_optional_identifier(
                "MissionActionState interrupted_reason",
                self.interrupted_reason,
            ),
        )
        object.__setattr__(
            self,
            "score_transaction_id",
            _validate_optional_identifier(
                "MissionActionState score_transaction_id",
                self.score_transaction_id,
            ),
        )
        self._validate_status_fields()

    @classmethod
    def start(
        cls,
        *,
        action_id: str,
        player_id: str,
        unit_instance_id: str,
        target_id: str,
        mission_id: str,
        battle_round: int,
        phase: str,
        start_timing: str,
        completion_timing: str,
        eligible_unit_instance_ids: tuple[str, ...],
        interruption_conditions: tuple[str, ...],
        scoring_source_id: str,
        victory_points: int,
    ) -> Self:
        return cls(
            action_id=action_id,
            player_id=player_id,
            unit_instance_id=unit_instance_id,
            target_id=target_id,
            mission_id=mission_id,
            battle_round_started=battle_round,
            phase_started=phase,
            start_timing=start_timing,
            completion_timing=completion_timing,
            eligible_unit_instance_ids=eligible_unit_instance_ids,
            interruption_conditions=interruption_conditions,
            scoring_source_id=scoring_source_id,
            victory_points=victory_points,
        )

    def complete(
        self,
        *,
        battle_round: int,
        phase: str,
        completion_timing: str,
        award: VictoryPointAward,
        transaction_id: str,
    ) -> Self:
        if self.status is not MissionActionStatus.STARTED:
            raise GameLifecycleError("Only started mission Actions can complete.")
        requested_timing = _validate_identifier("completion_timing", completion_timing)
        if requested_timing != self.completion_timing:
            raise GameLifecycleError("Mission Action completion timing drift.")
        if type(award) is not VictoryPointAward:
            raise GameLifecycleError("Mission Action completion requires a VP award.")
        if award.player_id != self.player_id:
            raise GameLifecycleError("Mission Action scoring player drift.")
        if award.source_id != self.scoring_source_id:
            raise GameLifecycleError("Mission Action scoring source drift.")
        if award.amount != self.victory_points:
            raise GameLifecycleError("Mission Action scoring amount drift.")
        return type(self)(
            action_id=self.action_id,
            player_id=self.player_id,
            unit_instance_id=self.unit_instance_id,
            target_id=self.target_id,
            mission_id=self.mission_id,
            battle_round_started=self.battle_round_started,
            phase_started=self.phase_started,
            start_timing=self.start_timing,
            completion_timing=self.completion_timing,
            eligible_unit_instance_ids=self.eligible_unit_instance_ids,
            interruption_conditions=self.interruption_conditions,
            scoring_source_id=self.scoring_source_id,
            victory_points=self.victory_points,
            status=MissionActionStatus.COMPLETED,
            completed_battle_round=_validate_positive_int("battle_round", battle_round),
            completed_phase=_validate_identifier("phase", phase),
            interrupted_reason=None,
            score_transaction_id=transaction_id,
        )

    def interrupt(self, *, reason: str) -> Self:
        if self.status is not MissionActionStatus.STARTED:
            raise GameLifecycleError("Only started mission Actions can be interrupted.")
        requested_reason = _validate_identifier("reason", reason)
        if requested_reason not in self.interruption_conditions:
            raise GameLifecycleError("Mission Action interruption reason is not configured.")
        return type(self)(
            action_id=self.action_id,
            player_id=self.player_id,
            unit_instance_id=self.unit_instance_id,
            target_id=self.target_id,
            mission_id=self.mission_id,
            battle_round_started=self.battle_round_started,
            phase_started=self.phase_started,
            start_timing=self.start_timing,
            completion_timing=self.completion_timing,
            eligible_unit_instance_ids=self.eligible_unit_instance_ids,
            interruption_conditions=self.interruption_conditions,
            scoring_source_id=self.scoring_source_id,
            victory_points=self.victory_points,
            status=MissionActionStatus.INTERRUPTED,
            interrupted_reason=requested_reason,
        )

    def to_payload(self) -> MissionActionStatePayload:
        return {
            "action_id": self.action_id,
            "player_id": self.player_id,
            "unit_instance_id": self.unit_instance_id,
            "target_id": self.target_id,
            "mission_id": self.mission_id,
            "battle_round_started": self.battle_round_started,
            "phase_started": self.phase_started,
            "start_timing": self.start_timing,
            "completion_timing": self.completion_timing,
            "eligible_unit_instance_ids": list(self.eligible_unit_instance_ids),
            "interruption_conditions": list(self.interruption_conditions),
            "scoring_source_id": self.scoring_source_id,
            "victory_points": self.victory_points,
            "status": self.status.value,
            "completed_battle_round": self.completed_battle_round,
            "completed_phase": self.completed_phase,
            "interrupted_reason": self.interrupted_reason,
            "score_transaction_id": self.score_transaction_id,
        }

    @classmethod
    def from_payload(cls, payload: MissionActionStatePayload) -> Self:
        return cls(
            action_id=payload["action_id"],
            player_id=payload["player_id"],
            unit_instance_id=payload["unit_instance_id"],
            target_id=payload["target_id"],
            mission_id=payload["mission_id"],
            battle_round_started=payload["battle_round_started"],
            phase_started=payload["phase_started"],
            start_timing=payload["start_timing"],
            completion_timing=payload["completion_timing"],
            eligible_unit_instance_ids=tuple(payload["eligible_unit_instance_ids"]),
            interruption_conditions=tuple(payload["interruption_conditions"]),
            scoring_source_id=payload["scoring_source_id"],
            victory_points=payload["victory_points"],
            status=mission_action_status_from_token(payload["status"]),
            completed_battle_round=payload["completed_battle_round"],
            completed_phase=payload["completed_phase"],
            interrupted_reason=payload["interrupted_reason"],
            score_transaction_id=payload["score_transaction_id"],
        )

    def _validate_status_fields(self) -> None:
        if self.status is MissionActionStatus.STARTED:
            if self.completed_battle_round is not None or self.completed_phase is not None:
                raise GameLifecycleError("Started mission Action must not have completion fields.")
            if self.interrupted_reason is not None or self.score_transaction_id is not None:
                raise GameLifecycleError("Started mission Action must not have terminal fields.")
        if self.status is MissionActionStatus.COMPLETED:
            if self.completed_battle_round is None or self.completed_phase is None:
                raise GameLifecycleError("Completed mission Action requires completion fields.")
            if self.score_transaction_id is None:
                raise GameLifecycleError("Completed mission Action requires score transaction.")
            if self.interrupted_reason is not None:
                raise GameLifecycleError("Completed mission Action cannot be interrupted.")
        if self.status is MissionActionStatus.INTERRUPTED:
            if self.interrupted_reason is None:
                raise GameLifecycleError("Interrupted mission Action requires a reason.")
            if self.completed_battle_round is not None or self.completed_phase is not None:
                raise GameLifecycleError(
                    "Interrupted mission Action cannot have completion fields."
                )
            if self.score_transaction_id is not None:
                raise GameLifecycleError("Interrupted mission Action cannot score.")


def mission_action_status_from_token(token: object) -> MissionActionStatus:
    if type(token) is MissionActionStatus:
        return token
    if type(token) is not str:
        raise GameLifecycleError("MissionActionStatus token must be a string.")
    try:
        return MissionActionStatus(token)
    except ValueError as exc:
        raise GameLifecycleError(f"Unsupported MissionActionStatus token: {token}.") from exc


def _validate_identifier_tuple(
    field_name: str,
    values: object,
    *,
    min_length: int,
) -> tuple[str, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError(f"{field_name} must be a tuple.")
    identifiers: list[str] = []
    seen: set[str] = set()
    for value in cast(tuple[object, ...], values):
        identifier = _validate_identifier(f"{field_name} value", value)
        if identifier in seen:
            raise GameLifecycleError(f"{field_name} must not contain duplicates.")
        seen.add(identifier)
        identifiers.append(identifier)
    if len(identifiers) < min_length:
        raise GameLifecycleError(f"{field_name} must contain at least {min_length} values.")
    return tuple(sorted(identifiers))


def _validate_identifier(field_name: str, value: object) -> str:
    if type(value) is not str:
        raise GameLifecycleError(f"{field_name} must be a string.")
    stripped = value.strip()
    if not stripped:
        raise GameLifecycleError(f"{field_name} must not be empty.")
    return stripped


def _validate_optional_identifier(field_name: str, value: object | None) -> str | None:
    if value is None:
        return None
    return _validate_identifier(field_name, value)


def _validate_positive_int(field_name: str, value: object) -> int:
    if type(value) is not int:
        raise GameLifecycleError(f"{field_name} must be an integer.")
    if value < 1:
        raise GameLifecycleError(f"{field_name} must be at least 1.")
    return value


def _validate_optional_positive_int(field_name: str, value: object | None) -> int | None:
    if value is None:
        return None
    return _validate_positive_int(field_name, value)
