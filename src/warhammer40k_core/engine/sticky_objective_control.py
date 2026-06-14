from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Self, TypedDict, cast

from warhammer40k_core.engine.event_log import EventLog, JsonValue, validate_json_value
from warhammer40k_core.engine.objective_control import (
    ObjectiveControlRecord,
    ObjectiveControlResult,
    ObjectiveControlScore,
    ObjectiveControlStatus,
)
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState


class StickyObjectiveControlStatePayload(TypedDict):
    state_id: str
    game_id: str
    player_id: str
    objective_id: str
    source_rule_id: str
    source_event_id: str
    battle_round: int
    phase: str
    active_player_id: str
    originating_unit_instance_id: str
    destroyed_unit_instance_id: str
    replay_payload: JsonValue


type PhaseEndObjectiveControlHandler = Callable[
    ["PhaseEndObjectiveControlContext"],
    tuple["StickyObjectiveControlState", ...],
]


@dataclass(frozen=True, slots=True)
class PhaseEndObjectiveControlContext:
    state: GameState
    event_log: EventLog
    completed_phase: BattlePhase

    def __post_init__(self) -> None:
        from warhammer40k_core.engine.game_state import GameState

        if type(self.state) is not GameState:
            raise GameLifecycleError("PhaseEndObjectiveControlContext state must be a GameState.")
        if type(self.event_log) is not EventLog:
            raise GameLifecycleError(
                "PhaseEndObjectiveControlContext event_log must be an EventLog."
            )
        object.__setattr__(
            self,
            "completed_phase",
            _battle_phase_from_token(self.completed_phase),
        )
        if self.state.current_battle_phase is not self.completed_phase:
            raise GameLifecycleError("PhaseEndObjectiveControlContext phase drift.")


@dataclass(frozen=True, slots=True)
class PhaseEndObjectiveControlHookBinding:
    hook_id: str
    source_id: str
    handler: PhaseEndObjectiveControlHandler

    def __post_init__(self) -> None:
        object.__setattr__(self, "hook_id", _validate_identifier("hook_id", self.hook_id))
        object.__setattr__(self, "source_id", _validate_identifier("source_id", self.source_id))
        if not callable(self.handler):
            raise GameLifecycleError(
                "PhaseEndObjectiveControlHookBinding handler must be callable."
            )


@dataclass(frozen=True, slots=True)
class PhaseEndObjectiveControlHookRegistry:
    bindings: tuple[PhaseEndObjectiveControlHookBinding, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "bindings", _validate_hook_bindings(self.bindings))

    @classmethod
    def empty(cls) -> Self:
        return cls(bindings=())

    @classmethod
    def from_bindings(
        cls,
        bindings: tuple[PhaseEndObjectiveControlHookBinding, ...],
    ) -> Self:
        return cls(bindings=bindings)

    def all_bindings(self) -> tuple[PhaseEndObjectiveControlHookBinding, ...]:
        return self.bindings

    def states_for(
        self,
        context: PhaseEndObjectiveControlContext,
    ) -> tuple[StickyObjectiveControlState, ...]:
        if type(context) is not PhaseEndObjectiveControlContext:
            raise GameLifecycleError("Phase-end objective-control hooks require a context.")
        states: list[StickyObjectiveControlState] = []
        for binding in self.bindings:
            handler_states = binding.handler(context)
            if type(handler_states) is not tuple:
                raise GameLifecycleError(
                    "Phase-end objective-control handlers must return a tuple."
                )
            for state in handler_states:
                if type(state) is not StickyObjectiveControlState:
                    raise GameLifecycleError(
                        "Phase-end objective-control handlers must return sticky states."
                    )
                if state.source_rule_id != binding.source_id:
                    raise GameLifecycleError(
                        "Phase-end objective-control handler returned source_id drift."
                    )
                states.append(state)
        return tuple(sorted(states, key=lambda state: state.state_id))


@dataclass(frozen=True, slots=True)
class StickyObjectiveControlState:
    state_id: str
    game_id: str
    player_id: str
    objective_id: str
    source_rule_id: str
    source_event_id: str
    battle_round: int
    phase: str
    active_player_id: str
    originating_unit_instance_id: str
    destroyed_unit_instance_id: str
    replay_payload: JsonValue = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "state_id", _validate_identifier("state_id", self.state_id))
        object.__setattr__(self, "game_id", _validate_identifier("game_id", self.game_id))
        object.__setattr__(self, "player_id", _validate_identifier("player_id", self.player_id))
        object.__setattr__(
            self,
            "objective_id",
            _validate_identifier("objective_id", self.objective_id),
        )
        object.__setattr__(
            self,
            "source_rule_id",
            _validate_identifier("source_rule_id", self.source_rule_id),
        )
        object.__setattr__(
            self,
            "source_event_id",
            _validate_identifier("source_event_id", self.source_event_id),
        )
        object.__setattr__(
            self,
            "battle_round",
            _validate_positive_int("battle_round", self.battle_round),
        )
        object.__setattr__(self, "phase", _validate_identifier("phase", self.phase))
        object.__setattr__(
            self,
            "active_player_id",
            _validate_identifier("active_player_id", self.active_player_id),
        )
        object.__setattr__(
            self,
            "originating_unit_instance_id",
            _validate_identifier(
                "originating_unit_instance_id",
                self.originating_unit_instance_id,
            ),
        )
        object.__setattr__(
            self,
            "destroyed_unit_instance_id",
            _validate_identifier("destroyed_unit_instance_id", self.destroyed_unit_instance_id),
        )
        object.__setattr__(self, "replay_payload", validate_json_value(self.replay_payload))

    def to_payload(self) -> StickyObjectiveControlStatePayload:
        return {
            "state_id": self.state_id,
            "game_id": self.game_id,
            "player_id": self.player_id,
            "objective_id": self.objective_id,
            "source_rule_id": self.source_rule_id,
            "source_event_id": self.source_event_id,
            "battle_round": self.battle_round,
            "phase": self.phase,
            "active_player_id": self.active_player_id,
            "originating_unit_instance_id": self.originating_unit_instance_id,
            "destroyed_unit_instance_id": self.destroyed_unit_instance_id,
            "replay_payload": self.replay_payload,
        }

    @classmethod
    def from_payload(cls, payload: StickyObjectiveControlStatePayload) -> Self:
        return cls(
            state_id=payload["state_id"],
            game_id=payload["game_id"],
            player_id=payload["player_id"],
            objective_id=payload["objective_id"],
            source_rule_id=payload["source_rule_id"],
            source_event_id=payload["source_event_id"],
            battle_round=payload["battle_round"],
            phase=payload["phase"],
            active_player_id=payload["active_player_id"],
            originating_unit_instance_id=payload["originating_unit_instance_id"],
            destroyed_unit_instance_id=payload["destroyed_unit_instance_id"],
            replay_payload=payload["replay_payload"],
        )


def apply_sticky_objective_control(
    *,
    record: ObjectiveControlRecord,
    states: tuple[StickyObjectiveControlState, ...],
) -> ObjectiveControlRecord:
    if type(record) is not ObjectiveControlRecord:
        raise GameLifecycleError("Sticky objective control requires an ObjectiveControlRecord.")
    active_states = _validate_sticky_states(states)
    if not active_states:
        return record
    updated_results = tuple(
        _result_with_sticky_control(result=result, states=active_states)
        for result in record.results
    )
    return ObjectiveControlRecord(
        record_id=record.record_id,
        game_id=record.game_id,
        battle_round=record.battle_round,
        active_player_id=record.active_player_id,
        timing=record.timing,
        phase=record.phase,
        battlefield_id=record.battlefield_id,
        results=updated_results,
    )


def sticky_objective_control_state_is_expired(
    *,
    state: StickyObjectiveControlState,
    record: ObjectiveControlRecord,
    player_ids: tuple[str, ...],
) -> bool:
    if type(state) is not StickyObjectiveControlState:
        raise GameLifecycleError("Sticky objective-control expiry requires a sticky state.")
    if type(record) is not ObjectiveControlRecord:
        raise GameLifecycleError("Sticky objective-control expiry requires a record.")
    player_id_tuple = _validate_identifier_tuple("player_ids", player_ids)
    opponent_ids = tuple(player_id for player_id in player_id_tuple if player_id != state.player_id)
    if not opponent_ids:
        raise GameLifecycleError("Sticky objective-control expiry requires an opponent.")
    result = record.result_by_objective_id(state.objective_id)
    player_score = _score_for_player(result, state.player_id)
    return any(
        _score_for_player(result, opponent_id) > player_score for opponent_id in opponent_ids
    )


def _result_with_sticky_control(
    *,
    result: ObjectiveControlResult,
    states: tuple[StickyObjectiveControlState, ...],
) -> ObjectiveControlResult:
    if result.status is ObjectiveControlStatus.UNSUPPORTED:
        return result
    matching = tuple(state for state in states if state.objective_id == result.objective_id)
    if not matching:
        return result
    controller_ids = tuple(sorted({state.player_id for state in matching}))
    active_controller_ids = tuple(
        player_id
        for player_id in controller_ids
        if not any(
            _score_for_player(result, opponent_id) > _score_for_player(result, player_id)
            for opponent_id in _scored_opponent_ids(result=result, player_id=player_id)
        )
    )
    if not active_controller_ids:
        return result
    if len(active_controller_ids) != 1:
        raise GameLifecycleError("Sticky objective-control states produced ambiguous control.")
    controller_id = active_controller_ids[0]
    current_scores = {score.player_id: score.score for score in result.scores}
    current_scores.setdefault(controller_id, 0)
    source_state = tuple(state for state in matching if state.player_id == controller_id)[-1]
    return ObjectiveControlResult(
        objective_id=result.objective_id,
        status=ObjectiveControlStatus.CONTROLLED,
        controlled_by_player_id=controller_id,
        scores=tuple(
            ObjectiveControlScore(player_id=player_id, score=score)
            for player_id, score in sorted(current_scores.items(), key=lambda item: item[0])
        ),
        contributors=result.contributors,
        unsupported_reason=None,
        retained_control_source_id=source_state.source_rule_id,
    )


def _score_for_player(result: ObjectiveControlResult, player_id: str) -> int:
    requested_player_id = _validate_identifier("player_id", player_id)
    for score in result.scores:
        if score.player_id == requested_player_id:
            return score.score
    return 0


def _scored_opponent_ids(
    *,
    result: ObjectiveControlResult,
    player_id: str,
) -> tuple[str, ...]:
    requested_player_id = _validate_identifier("player_id", player_id)
    return tuple(
        sorted(score.player_id for score in result.scores if score.player_id != requested_player_id)
    )


def _validate_hook_bindings(
    value: object,
) -> tuple[PhaseEndObjectiveControlHookBinding, ...]:
    if type(value) is not tuple:
        raise GameLifecycleError("PhaseEndObjectiveControlHookRegistry bindings must be a tuple.")
    bindings: list[PhaseEndObjectiveControlHookBinding] = []
    seen: set[str] = set()
    for binding in cast(tuple[object, ...], value):
        if type(binding) is not PhaseEndObjectiveControlHookBinding:
            raise GameLifecycleError(
                "PhaseEndObjectiveControlHookRegistry bindings must contain hook bindings."
            )
        if binding.hook_id in seen:
            raise GameLifecycleError(
                "PhaseEndObjectiveControlHookRegistry hook IDs must be unique."
            )
        seen.add(binding.hook_id)
        bindings.append(binding)
    return tuple(sorted(bindings, key=lambda binding: binding.hook_id))


def _validate_sticky_states(
    values: object,
) -> tuple[StickyObjectiveControlState, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError("sticky objective-control states must be a tuple.")
    states: list[StickyObjectiveControlState] = []
    for value in cast(tuple[object, ...], values):
        if type(value) is not StickyObjectiveControlState:
            raise GameLifecycleError("sticky objective-control states must contain sticky states.")
        states.append(value)
    return tuple(sorted(states, key=lambda state: state.state_id))


def _battle_phase_from_token(token: object) -> BattlePhase:
    if type(token) is BattlePhase:
        return token
    if type(token) is not str:
        raise GameLifecycleError("Battle phase token must be a string.")
    try:
        return BattlePhase(token)
    except ValueError as exc:
        raise GameLifecycleError(f"Unsupported battle phase token: {token}.") from exc


def _validate_identifier_tuple(field_name: str, values: object) -> tuple[str, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError(f"{field_name} must be a tuple.")
    identifiers: list[str] = []
    seen: set[str] = set()
    for value in cast(tuple[object, ...], values):
        identifier = _validate_identifier(field_name, value)
        if identifier in seen:
            raise GameLifecycleError(f"{field_name} must not contain duplicate values.")
        seen.add(identifier)
        identifiers.append(identifier)
    return tuple(sorted(identifiers))


def _validate_positive_int(field_name: str, value: object) -> int:
    if type(value) is not int:
        raise GameLifecycleError(f"{field_name} must be an int.")
    if value <= 0:
        raise GameLifecycleError(f"{field_name} must be greater than zero.")
    return value


def _validate_identifier(field_name: str, value: object) -> str:
    if type(value) is not str:
        raise GameLifecycleError(f"{field_name} must be a string.")
    stripped = value.strip()
    if not stripped:
        raise GameLifecycleError(f"{field_name} must not be empty.")
    return stripped
