from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, Self, TypedDict, cast

from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError, GameLifecycleStage
from warhammer40k_core.engine.rules_units import (
    current_rules_unit_views_for_canonical_identity,
)

if TYPE_CHECKING:
    from warhammer40k_core.engine.decision_record import DecisionRecord
    from warhammer40k_core.engine.event_log import EventRecord, JsonValue
    from warhammer40k_core.engine.game_state import GameState

ONE_NORMAL_MOVE_PER_PHASE_SOURCE_RULE_ID = (
    "gw-11e-rules-and-event-updates-2026-07-22:app-core-rules:09-normal-move-one-per-phase"
)

_validate_identifier = IdentifierValidator(GameLifecycleError)


class NormalMoveSourceKind(StrEnum):
    MOVEMENT_PHASE_ACTION = "movement_phase_action"
    SURGE = "surge"
    TRIGGERED = "triggered"


class NormalMoveStatePayload(TypedDict):
    player_id: str
    turn_player_id: str
    battle_round: int
    phase: str
    unit_instance_id: str
    source_rule_id: str
    source_kind: str
    request_id: str
    result_id: str


@dataclass(frozen=True, slots=True)
class NormalMoveState:
    player_id: str
    turn_player_id: str
    battle_round: int
    phase: BattlePhase
    unit_instance_id: str
    source_rule_id: str
    source_kind: NormalMoveSourceKind
    request_id: str
    result_id: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "player_id",
            _validate_identifier("NormalMoveState player_id", self.player_id),
        )
        object.__setattr__(
            self,
            "turn_player_id",
            _validate_identifier("NormalMoveState turn_player_id", self.turn_player_id),
        )
        if type(self.battle_round) is not int or self.battle_round < 1:
            raise GameLifecycleError("NormalMoveState battle_round must be a positive integer.")
        object.__setattr__(self, "phase", _battle_phase_from_token(self.phase))
        object.__setattr__(
            self,
            "unit_instance_id",
            _validate_identifier("NormalMoveState unit_instance_id", self.unit_instance_id),
        )
        object.__setattr__(
            self,
            "source_rule_id",
            _validate_identifier("NormalMoveState source_rule_id", self.source_rule_id),
        )
        object.__setattr__(
            self,
            "source_kind",
            normal_move_source_kind_from_token(self.source_kind),
        )
        object.__setattr__(
            self,
            "request_id",
            _validate_identifier("NormalMoveState request_id", self.request_id),
        )
        object.__setattr__(
            self,
            "result_id",
            _validate_identifier("NormalMoveState result_id", self.result_id),
        )

    def same_phase_key(self) -> tuple[int, str, BattlePhase, str, str]:
        return (
            self.battle_round,
            self.turn_player_id,
            self.phase,
            self.player_id,
            self.unit_instance_id,
        )

    def to_payload(self) -> NormalMoveStatePayload:
        return {
            "player_id": self.player_id,
            "turn_player_id": self.turn_player_id,
            "battle_round": self.battle_round,
            "phase": self.phase.value,
            "unit_instance_id": self.unit_instance_id,
            "source_rule_id": self.source_rule_id,
            "source_kind": self.source_kind.value,
            "request_id": self.request_id,
            "result_id": self.result_id,
        }

    @classmethod
    def from_payload(cls, payload: NormalMoveStatePayload) -> Self:
        if set(payload) != set(NormalMoveStatePayload.__annotations__):
            raise GameLifecycleError(
                "Normal Move history schema requires explicit phase occurrence."
            )
        return cls(
            player_id=payload["player_id"],
            turn_player_id=payload["turn_player_id"],
            battle_round=payload["battle_round"],
            phase=_battle_phase_from_token(payload["phase"]),
            unit_instance_id=payload["unit_instance_id"],
            source_rule_id=payload["source_rule_id"],
            source_kind=normal_move_source_kind_from_token(payload["source_kind"]),
            request_id=payload["request_id"],
            result_id=payload["result_id"],
        )


def normal_move_source_kind_from_token(value: object) -> NormalMoveSourceKind:
    if type(value) is NormalMoveSourceKind:
        return value
    if type(value) is not str:
        raise GameLifecycleError("NormalMoveSourceKind token must be a string.")
    try:
        return NormalMoveSourceKind(value)
    except ValueError as exc:
        raise GameLifecycleError(f"Unsupported NormalMoveSourceKind token: {value}.") from exc


def validate_normal_move_state_consistency(
    *,
    state: GameState,
    event_records: tuple[EventRecord, ...],
    decision_records: tuple[DecisionRecord, ...],
) -> None:
    if state.normal_move_states and state.stage is not GameLifecycleStage.BATTLE:
        raise GameLifecycleError("normal_move_states require battle stage.")
    for normal_move_state in state.normal_move_states:
        views = current_rules_unit_views_for_canonical_identity(
            state=state,
            unit_instance_id=normal_move_state.unit_instance_id,
        )
        if any(view.owner_player_id != normal_move_state.player_id for view in views):
            raise GameLifecycleError("normal_move_states player_id does not match unit owner.")
    expected: list[NormalMoveState] = []
    decisions = {row.result.result_id: row for row in decision_records}
    requests = {row.request.request_id: row.request for row in decision_records}
    for event_index, event in enumerate(event_records):
        if event.event_type == "movement_activation_completed":
            from warhammer40k_core.engine.movement_decision_authority import (
                validate_movement_completion_decision_authority,
            )

            if not isinstance(event.payload, dict) or event.payload.get("game_id") != state.game_id:
                raise GameLifecycleError("Normal Move completion game authority drifted.")
            source = decisions.get(_completion_text(event.payload, "result_id"))
            accepted_action = (
                source.result.payload.get("movement_phase_action")
                if source is not None and isinstance(source.result.payload, dict)
                else None
            )
            if (
                event.payload.get("movement_phase_action") == "normal_move"
                or accepted_action == "normal_move"
            ):
                validate_movement_completion_decision_authority(
                    event_records=event_records,
                    decision_records=decision_records,
                    mutation_index=event_index,
                    payload=event.payload,
                )
        _validate_triggered_completion_classification(event, decisions)
        row = normal_move_from_completion(state, event)
        if row is None:
            continue
        if row.result_id not in decisions:
            raise GameLifecycleError("Normal Move history lacks an accepted decision.")
        record = decisions[row.result_id]
        request = record.request
        if record.result.actor_id != row.player_id or request.request_id != row.request_id:
            raise GameLifecycleError("Normal Move history decision ownership drifted.")
        from warhammer40k_core.engine.movement_proposals import (
            MOVEMENT_PROPOSAL_DECISION_TYPE,
            MovementProposalRequest,
        )

        if request.decision_type == MOVEMENT_PROPOSAL_DECISION_TYPE:
            proposal = MovementProposalRequest.from_decision_request_payload(request.payload)
            if proposal.source_decision_request_id not in requests:
                raise GameLifecycleError("Normal Move history lacks its selection decision.")
            request = requests[proposal.source_decision_request_id]
        payload = request.payload
        if not isinstance(payload, dict) or (
            payload.get("active_player_id") != row.turn_player_id
            or payload.get("battle_round") != row.battle_round
            or payload.get(
                "phase"
                if row.source_kind is NormalMoveSourceKind.MOVEMENT_PHASE_ACTION
                else "current_phase"
            )
            != row.phase.value
        ):
            raise GameLifecycleError("Normal Move history phase occurrence differs from decision.")
        if row.source_kind is NormalMoveSourceKind.TRIGGERED:
            from warhammer40k_core.engine.triggered_movement import (
                TriggeredMovementDescriptor,
                TriggeredMovementDescriptorPayload,
            )

            raw_descriptor = payload.get("descriptor")
            if not isinstance(raw_descriptor, dict):
                raise GameLifecycleError("Normal Move history lacks its source descriptor.")
            descriptor = TriggeredMovementDescriptor.from_payload(
                cast(TriggeredMovementDescriptorPayload, raw_descriptor)
            )
            if (
                descriptor.source_rule_id != row.source_rule_id
                or descriptor.movement_mode.value != "normal"
                or descriptor.trigger_timing.phase is not row.phase
            ):
                raise GameLifecycleError("Normal Move history source descriptor drifted.")
        expected.append(row)
    if validate_normal_move_states(expected, state=state) != state.normal_move_states:
        raise GameLifecycleError("Normal Move history differs from accepted completion evidence.")


def _validate_triggered_completion_classification(
    event: EventRecord, decisions: dict[str, DecisionRecord]
) -> None:
    if event.event_type != "triggered_movement_resolved":
        return
    payload = event.payload
    if not isinstance(payload, dict):
        raise GameLifecycleError("Triggered completion requires an object.")
    result_id = _completion_text(payload, "result_id")
    if result_id not in decisions:
        raise GameLifecycleError("Triggered completion lacks an accepted decision.")
    request = decisions[result_id].request
    from warhammer40k_core.engine.movement_proposals import (
        MOVEMENT_PROPOSAL_DECISION_TYPE,
        MovementProposalRequest,
    )

    context = request.payload
    if request.decision_type == MOVEMENT_PROPOSAL_DECISION_TYPE:
        context = MovementProposalRequest.from_decision_request_payload(context).context
    if not isinstance(context, dict) or not isinstance(context.get("descriptor"), dict):
        raise GameLifecycleError("Triggered completion lacks its descriptor.")
    descriptor = cast("dict[str, JsonValue]", context["descriptor"])
    for field in ("movement_mode", "source_rule_id"):
        if payload.get(field) != descriptor.get(field):
            raise GameLifecycleError("Triggered completion classification differs from decision.")
    if payload.get("triggered_movement_kind") != descriptor.get("movement_kind"):
        raise GameLifecycleError("Triggered completion kind differs from decision.")


def normal_move_from_completion(state: GameState, event: EventRecord) -> NormalMoveState | None:
    """One classification shared by live recording and historical reconstruction."""
    if event.event_type not in {"movement_activation_completed", "triggered_movement_resolved"}:
        return None
    payload = event.payload
    if not isinstance(payload, dict):
        raise GameLifecycleError("Normal Move completion requires an object.")
    if event.event_type == "movement_activation_completed":
        if payload.get("movement_phase_action") != "normal_move":
            return None
        source_kind = NormalMoveSourceKind.MOVEMENT_PHASE_ACTION
        source_rule_id = ONE_NORMAL_MOVE_PER_PHASE_SOURCE_RULE_ID
    else:
        if payload.get("triggered_movement_kind") == "surge":
            return None
        from warhammer40k_core.core.ruleset_descriptor import movement_mode_from_token

        if movement_mode_from_token(_completion_text(payload, "movement_mode")).value != "normal":
            return None
        source_kind = NormalMoveSourceKind.TRIGGERED
        source_rule_id = _completion_text(payload, "source_rule_id")
    unit_id = _completion_text(payload, "unit_instance_id")
    views = current_rules_unit_views_for_canonical_identity(state=state, unit_instance_id=unit_id)
    owners = {view.owner_player_id for view in views}
    if len(owners) != 1:
        raise GameLifecycleError("Normal Move completion requires one unit owner.")
    return NormalMoveState(
        player_id=owners.pop(),
        turn_player_id=_completion_text(payload, "active_player_id"),
        battle_round=cast(int, payload["battle_round"]),
        phase=_battle_phase_from_token(payload["phase"]),
        unit_instance_id=unit_id,
        source_rule_id=source_rule_id,
        source_kind=source_kind,
        request_id=_completion_text(payload, "request_id"),
        result_id=_completion_text(payload, "result_id"),
    )


def _completion_text(payload: dict[str, JsonValue], key: str) -> str:
    return _validate_identifier(f"Normal Move completion {key}", payload.get(key))


def record_normal_move_state(state: GameState, row: NormalMoveState) -> None:
    if type(row) is not NormalMoveState:
        raise GameLifecycleError("Normal move state must be a NormalMoveState.")
    if row.player_id not in state.player_ids or row.turn_player_id not in state.player_ids:
        raise GameLifecycleError("NormalMoveState player_id is not in this game.")
    if any(stored.result_id == row.result_id for stored in state.normal_move_states):
        raise GameLifecycleError("NormalMoveState already exists for result_id.")
    if any(_same_occurrence_lineage(state, stored, row) for stored in state.normal_move_states):
        raise GameLifecycleError(
            "Normal Move history already exists for unit in this phase (rules-unit lineage)."
        )
    state.normal_move_states.append(row)
    state.normal_move_states.sort(key=lambda item: (*item.same_phase_key(), item.result_id))


def normal_moves_for_unit_phase(
    state: GameState,
    *,
    player_id: str,
    battle_round: int,
    phase: BattlePhase,
    unit_instance_id: str,
) -> tuple[NormalMoveState, ...]:
    from warhammer40k_core.engine.rules_units import rules_unit_identities_share_lineage

    actor = _validate_identifier("player_id", player_id)
    unit_id = _validate_identifier("unit_instance_id", unit_instance_id)
    if actor not in state.player_ids or state.active_player_id not in state.player_ids:
        raise GameLifecycleError("Normal Move query requires valid unit and turn owners.")
    if type(battle_round) is not int or battle_round < 1 or type(phase) is not BattlePhase:
        raise GameLifecycleError("Normal Move query requires a positive round and BattlePhase.")
    return tuple(
        row
        for row in state.normal_move_states
        if row.player_id == actor
        and row.battle_round == battle_round
        and row.phase is phase
        and row.turn_player_id == state.active_player_id
        and (
            row.unit_instance_id == unit_id
            or rules_unit_identities_share_lineage(
                state=state,
                first_unit_instance_id=row.unit_instance_id,
                second_unit_instance_id=unit_id,
            )
        )
    )


def normal_move_turn_player_id(state: GameState) -> str:
    if state.active_player_id is None or state.active_player_id not in state.player_ids:
        raise GameLifecycleError("Normal Move requires the current turn owner.")
    return state.active_player_id


def _battle_phase_from_token(value: object) -> BattlePhase:
    if type(value) is BattlePhase:
        return value
    if type(value) is not str:
        raise GameLifecycleError("NormalMoveState phase token must be a string.")
    try:
        return BattlePhase(value)
    except ValueError as exc:
        raise GameLifecycleError(f"Unsupported NormalMoveState phase token: {value}.") from exc


def validate_normal_move_states(
    values: object,
    *,
    state: GameState,
) -> list[NormalMoveState]:
    if not isinstance(values, list):
        raise GameLifecycleError("GameState normal_move_states must be a list.")
    validated: list[NormalMoveState] = []
    seen_result_ids: set[str] = set()
    for value in cast(list[object], values):
        if type(value) is not NormalMoveState:
            raise GameLifecycleError(
                "GameState normal_move_states must contain NormalMoveState values."
            )
        if value.player_id not in state.player_ids or value.turn_player_id not in state.player_ids:
            raise GameLifecycleError("NormalMoveState player_id is not in this game.")
        if value.result_id in seen_result_ids:
            raise GameLifecycleError("GameState normal_move_states must be unique by result.")
        seen_result_ids.add(value.result_id)
        if any(_same_occurrence_lineage(state, previous, value) for previous in validated):
            raise GameLifecycleError(
                "Normal Move history must be unique by unit phase and rules-unit lineage."
            )
        validated.append(value)
    return sorted(
        validated,
        key=lambda state: (
            state.battle_round,
            state.turn_player_id,
            state.phase,
            state.player_id,
            state.unit_instance_id,
            state.result_id,
        ),
    )


def _same_occurrence_lineage(
    state: GameState, first: NormalMoveState, second: NormalMoveState
) -> bool:
    from warhammer40k_core.engine.rules_units import rules_unit_identities_share_lineage

    return first.same_phase_key()[:4] == second.same_phase_key()[:4] and (
        first.unit_instance_id == second.unit_instance_id
        or rules_unit_identities_share_lineage(
            state=state,
            first_unit_instance_id=first.unit_instance_id,
            second_unit_instance_id=second.unit_instance_id,
        )
    )
