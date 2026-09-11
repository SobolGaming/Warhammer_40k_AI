from __future__ import annotations

from typing import cast

from warhammer40k_core.engine.active_player_scopes import (
    ActivePlayerScope,
    ActivePlayerScopeKind,
    ActivePlayerScopePayload,
    shooting_scope,
    validate_scopes,
)
from warhammer40k_core.engine.active_player_scopes import (
    fight_scope as fight_scope_for_state,
)
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.event_log import JsonValue
from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.phase import GameLifecycleError


def validate_active_player_history(*, state: GameState, decisions: DecisionController) -> None:
    """Prove suspended movement authority from accepted selection and completion records."""
    validate_scopes(state)
    active: list[ActivePlayerScope] = []
    seen: set[tuple[ActivePlayerScopeKind, str]] = set()
    for index, event in enumerate(decisions.event_log.records):
        if event.event_type == "active_player_scope_started":
            scope = _scope(event.payload)
            if scope.kind not in (
                ActivePlayerScopeKind.REACTIVE_MOVE,
                ActivePlayerScopeKind.FIGHT_MOVE,
            ):
                raise GameLifecycleError("Active-player movement event has an unrelated action.")
            key = (scope.kind, scope.selection_request_id)
            if key in seen:
                raise GameLifecycleError("Active-player movement selection was reopened.")
            if scope.kind is ActivePlayerScopeKind.REACTIVE_MOVE:
                _validate_selection(scope, decisions)
            else:
                from warhammer40k_core.engine.fight_movement_active_player import (
                    validate_fight_move_selection,
                )

                validate_fight_move_selection(scope, decisions, index)
            seen.add(key)
            active.append(scope)
        elif event.event_type == "active_player_scope_completed":
            if not isinstance(event.payload, dict):
                raise GameLifecycleError("Active-player completion requires an object.")
            scope = _scope(event.payload.get("scope"))
            if not active or active[-1] != scope:
                raise GameLifecycleError("Active-player movement completion order drift.")
            result_id = event.payload.get("result_id")
            completion_type = (
                "triggered_movement_resolved"
                if scope.kind is ActivePlayerScopeKind.REACTIVE_MOVE
                else "fight_movement_completed"
            )
            resolved = [
                prior.payload
                for prior in decisions.event_log.records[:index]
                if prior.event_type == completion_type
                and isinstance(prior.payload, dict)
                and prior.payload.get("result_id") == result_id
                and prior.payload.get("unit_instance_id") == scope.unit_instance_id
                and (
                    scope.kind is ActivePlayerScopeKind.FIGHT_MOVE
                    or prior.payload.get("source_rule_id") == scope.source_rule_id
                )
            ]
            if len(resolved) != 1:
                raise GameLifecycleError("Active-player movement completion lacks a resolved path.")
            active.pop()
    persisted = tuple(
        scope
        for scope in state.active_player_scopes
        if scope.kind in (ActivePlayerScopeKind.REACTIVE_MOVE, ActivePlayerScopeKind.FIGHT_MOVE)
    )
    if tuple(active) != persisted:
        raise GameLifecycleError("Active-player movement scope differs from recorded history.")
    expected_attack_scopes: list[ActivePlayerScope] = []
    fight = state.fight_phase_state
    fight_scope = fight_scope_for_state(fight)
    if (
        fight_scope is not None
        and fight is not None
        and fight.pending_completed_attack_sequence is None
    ):
        expected_attack_scopes.append(fight_scope)
    shooting = state.out_of_phase_shooting_state
    if shooting is not None and shooting.pending_completed_attack_sequence is None:
        expected_attack_scopes.append(shooting_scope(shooting))
    actual_attack_scopes = tuple(
        scope
        for scope in state.active_player_scopes
        if scope.kind in (ActivePlayerScopeKind.FIGHT, ActivePlayerScopeKind.OUT_OF_PHASE_SHOOT)
    )
    if set(expected_attack_scopes) != set(actual_attack_scopes) or len(
        expected_attack_scopes
    ) != len(actual_attack_scopes):
        raise GameLifecycleError("Active-player attack scope differs from its selected action.")
    for request in decisions.queue.pending_requests:
        payload = request.payload
        if not isinstance(payload, dict):
            continue
        proposal = payload.get("proposal_request")
        if (
            isinstance(proposal, dict)
            and proposal.get("phase") == "fight"
            and proposal.get("proposal_kind") in ("pile_in", "consolidate")
        ):
            from warhammer40k_core.engine.fight_movement_active_player import fight_move_scope

            current = fight_move_scope(request)
            matching = tuple(
                scope
                for scope in active
                if scope.kind is current.kind
                and scope.player_id == current.player_id
                and scope.unit_instance_id == current.unit_instance_id
                and scope.selection_result_id == current.selection_result_id
            )
            if len(matching) != 1:
                raise GameLifecycleError("Pending Fight movement lacks selected-unit authority.")
        context = proposal.get("context") if isinstance(proposal, dict) else payload
        if not isinstance(context, dict) or context.get("context_kind") not in (
            "triggered_movement",
            "triggered_movement_distance_reroll",
        ):
            continue
        matches = tuple(
            scope
            for scope in active
            if scope.selection_request_id == context.get("selection_request_id")
            and scope.selection_result_id == context.get("selection_result_id")
            and scope.player_id == request.actor_id
        )
        if len(matches) != 1:
            raise GameLifecycleError("Pending reactive movement lacks selected-unit authority.")


def _scope(payload: JsonValue) -> ActivePlayerScope:
    if not isinstance(payload, dict):
        raise GameLifecycleError("Active-player scope event requires an object.")
    if set(payload) != {
        "kind",
        "player_id",
        "unit_instance_id",
        "source_rule_id",
        "selection_request_id",
        "selection_result_id",
    }:
        raise GameLifecycleError("Active-player scope payload schema drift.")
    return ActivePlayerScope.from_payload(cast(ActivePlayerScopePayload, payload))


def _validate_selection(scope: ActivePlayerScope, decisions: DecisionController) -> None:
    records = tuple(
        record
        for record in decisions.records
        if record.request.request_id == scope.selection_request_id
        and record.result.result_id == scope.selection_result_id
    )
    if len(records) != 1:
        raise GameLifecycleError("Active-player movement requires an accepted selection.")
    record = records[0]
    payload = record.result.payload
    source = record.request.payload
    if (
        record.request.decision_type != "select_triggered_movement"
        or record.result.actor_id != scope.player_id
        or not isinstance(payload, dict)
        or payload.get("unit_instance_id") != scope.unit_instance_id
        or payload.get("declined") is True
        or not isinstance(source, dict)
    ):
        raise GameLifecycleError("Active-player movement selection authority drift.")
    descriptor = source.get("descriptor")
    if not isinstance(descriptor, dict) or descriptor.get("source_rule_id") != scope.source_rule_id:
        raise GameLifecycleError("Active-player movement source authority drift.")
