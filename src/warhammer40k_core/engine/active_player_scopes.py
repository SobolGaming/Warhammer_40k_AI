from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, Self, TypedDict

from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine.phase import GameLifecycleError

if TYPE_CHECKING:
    from warhammer40k_core.engine.decision_controller import DecisionController
    from warhammer40k_core.engine.decision_result import DecisionResult
    from warhammer40k_core.engine.fight_order import FightPhaseState
    from warhammer40k_core.engine.game_state import GameState
    from warhammer40k_core.engine.phases.shooting_model import OutOfPhaseShootingState


class ActivePlayerScopeKind(StrEnum):
    REACTIVE_MOVE = "reactive_move"
    OUT_OF_PHASE_SHOOT = "out_of_phase_shoot"
    FIGHT = "fight"
    FIGHT_MOVE = "fight_move"


class ActivePlayerScopePayload(TypedDict):
    kind: str
    player_id: str
    unit_instance_id: str
    source_rule_id: str
    selection_request_id: str
    selection_result_id: str


@dataclass(frozen=True, slots=True)
class ActivePlayerScope:
    kind: ActivePlayerScopeKind
    player_id: str
    unit_instance_id: str
    source_rule_id: str
    selection_request_id: str
    selection_result_id: str

    def __post_init__(self) -> None:
        if type(self.kind) is not ActivePlayerScopeKind:
            raise GameLifecycleError("Active-player scope requires a typed action kind.")
        for name, value in (
            ("player_id", self.player_id),
            ("unit_instance_id", self.unit_instance_id),
            ("source_rule_id", self.source_rule_id),
            ("selection_request_id", self.selection_request_id),
            ("selection_result_id", self.selection_result_id),
        ):
            object.__setattr__(self, name, IdentifierValidator(GameLifecycleError)(name, value))

    def to_payload(self) -> ActivePlayerScopePayload:
        return {
            "kind": self.kind.value,
            "player_id": self.player_id,
            "unit_instance_id": self.unit_instance_id,
            "source_rule_id": self.source_rule_id,
            "selection_request_id": self.selection_request_id,
            "selection_result_id": self.selection_result_id,
        }

    @classmethod
    def from_payload(cls, payload: ActivePlayerScopePayload) -> Self:
        try:
            kind = ActivePlayerScopeKind(payload["kind"])
        except ValueError as exc:
            raise GameLifecycleError("Unknown active-player scope kind.") from exc
        return cls(
            kind=kind,
            player_id=payload["player_id"],
            unit_instance_id=payload["unit_instance_id"],
            source_rule_id=payload["source_rule_id"],
            selection_request_id=payload["selection_request_id"],
            selection_result_id=payload["selection_result_id"],
        )


def validate_scopes(state: GameState) -> None:
    scopes = state.active_player_scopes
    if type(scopes) is not tuple or any(type(scope) is not ActivePlayerScope for scope in scopes):
        raise GameLifecycleError("Active-player scopes must be a tuple of typed scopes.")
    keys = {(scope.kind, scope.selection_request_id, scope.selection_result_id) for scope in scopes}
    if len(keys) != len(scopes):
        raise GameLifecycleError("Duplicate active-player scope.")
    for scope in scopes:
        _validate_scope_owner(state, scope)


def _validate_scope_owner(state: GameState, scope: ActivePlayerScope) -> None:
    from warhammer40k_core.engine.rules_units import rules_unit_view_from_armies

    if scope.player_id not in state.player_ids:
        raise GameLifecycleError("Active-player scope owner is not in this game.")
    view = rules_unit_view_from_armies(
        armies=tuple(state.army_definitions),
        unit_instance_id=scope.unit_instance_id,
    )
    if view.owner_player_id != scope.player_id:
        raise GameLifecycleError("Active-player scope unit ownership drift.")


def push_scope(state: GameState, scope: ActivePlayerScope) -> None:
    previous = state.active_player_scopes
    if any(
        item.kind == scope.kind
        and item.selection_request_id == scope.selection_request_id
        and item.selection_result_id == scope.selection_result_id
        for item in previous
    ):
        raise GameLifecycleError("Active-player scope was already selected.")
    _validate_scope_owner(state, scope)
    state.replace_active_player_scopes((*previous, scope))


def pop_scope(state: GameState, scope: ActivePlayerScope) -> None:
    if not state.active_player_scopes or state.active_player_scopes[-1] != scope:
        raise GameLifecycleError("Active-player action completion violates nested scope order.")
    state.replace_active_player_scopes(state.active_player_scopes[:-1])


def begin_reactive_move(
    *,
    state: GameState,
    decisions: DecisionController,
    result: DecisionResult,
    unit_instance_id: str,
    source_rule_id: str,
) -> None:
    if result.actor_id is None:
        raise GameLifecycleError("Reactive movement requires a selecting player.")
    scope = ActivePlayerScope(
        kind=ActivePlayerScopeKind.REACTIVE_MOVE,
        player_id=result.actor_id,
        unit_instance_id=unit_instance_id,
        source_rule_id=source_rule_id,
        selection_request_id=result.request_id,
        selection_result_id=result.result_id,
    )
    push_scope(state, scope)
    decisions.event_log.append("active_player_scope_started", dict(scope.to_payload()))


def end_reactive_move(
    *,
    state: GameState,
    decisions: DecisionController,
    unit_instance_id: str,
    selection_request_id: str,
    selection_result_id: str,
    source_rule_id: str,
    result: DecisionResult,
) -> None:
    if result.actor_id is None:
        raise GameLifecycleError("Reactive movement requires a selecting player.")
    scope = ActivePlayerScope(
        kind=ActivePlayerScopeKind.REACTIVE_MOVE,
        player_id=result.actor_id,
        unit_instance_id=unit_instance_id,
        source_rule_id=source_rule_id,
        selection_request_id=selection_request_id,
        selection_result_id=selection_result_id,
    )
    pop_scope(state, scope)
    decisions.event_log.append(
        "active_player_scope_completed",
        {"scope": dict(scope.to_payload()), "result_id": result.result_id},
    )


def shooting_scope(shooting: OutOfPhaseShootingState) -> ActivePlayerScope:
    return ActivePlayerScope(
        kind=ActivePlayerScopeKind.OUT_OF_PHASE_SHOOT,
        player_id=shooting.player_id,
        unit_instance_id=shooting.selected_unit_instance_id,
        source_rule_id=shooting.source_rule_id,
        selection_request_id=shooting.source_decision_request_id,
        selection_result_id=shooting.source_decision_result_id,
    )


def update_out_of_phase_scope(
    state: GameState,
    updated: OutOfPhaseShootingState | None,
) -> None:
    previous = state.out_of_phase_shooting_state
    previous_scope = None if previous is None else shooting_scope(previous)
    next_scope = None if updated is None else shooting_scope(updated)
    if previous_scope != next_scope:
        if previous_scope is not None and previous_scope in state.active_player_scopes:
            pop_scope(state, previous_scope)
        if (
            next_scope is not None
            and updated is not None
            and updated.pending_completed_attack_sequence is None
        ):
            push_scope(state, next_scope)
    elif (
        next_scope is not None
        and updated is not None
        and updated.pending_completed_attack_sequence is not None
        and next_scope in state.active_player_scopes
    ):
        pop_scope(state, next_scope)


def fight_scope(fight: FightPhaseState | None) -> ActivePlayerScope | None:
    if fight is None or fight.active_activation is None:
        return None
    from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
        core_sequencing_2026_09 as source,
    )

    activation = fight.active_activation
    return ActivePlayerScope(
        kind=ActivePlayerScopeKind.FIGHT,
        player_id=activation.player_id,
        unit_instance_id=activation.unit_instance_id,
        source_rule_id=(
            source.ACTIVE_PLAYER_SOURCE_ID
            if fight.forced_activation_context is None
            else fight.forced_activation_context.source_rule_id
        ),
        selection_request_id=activation.request_id,
        selection_result_id=activation.result_id,
    )


def update_fight_scope(state: GameState, updated: FightPhaseState | None) -> None:
    previous_scope = fight_scope(state.fight_phase_state)
    next_scope = fight_scope(updated)
    if previous_scope != next_scope:
        if previous_scope is not None and previous_scope in state.active_player_scopes:
            pop_scope(state, previous_scope)
        if (
            next_scope is not None
            and updated is not None
            and updated.pending_completed_attack_sequence is None
        ):
            push_scope(state, next_scope)
    elif (
        next_scope is not None
        and updated is not None
        and updated.pending_completed_attack_sequence is not None
        and next_scope in state.active_player_scopes
    ):
        pop_scope(state, next_scope)
