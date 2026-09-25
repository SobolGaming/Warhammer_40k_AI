"""Recover chooser authority at a recorded dice-reference boundary."""

from __future__ import annotations

from dataclasses import dataclass
from typing import cast

from warhammer40k_core.engine.active_player_scopes import (
    ActivePlayerScope,
    ActivePlayerScopeKind,
    ActivePlayerScopePayload,
    fight_scope,
    shooting_scope,
)
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_record import DecisionRecord, DecisionRecordPayload
from warhammer40k_core.engine.event_log import EventRecord, JsonValue
from warhammer40k_core.engine.fight_order import (
    FIGHT_ACTIVATION_DECISION_TYPE,
    FIGHT_INTERRUPT_DECISION_TYPE,
    FightPhaseState,
    FightPhaseStatePayload,
    current_fight_activation_selection_from_payload,
    fight_interrupt_request_from_payload,
)
from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.objective_control_boundary_history_integrity import (
    _canonical_phase_start_context_or_none,  # pyright: ignore[reportPrivateUsage]
)
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.phases.shooting_model import (
    OutOfPhaseShootingState,
    OutOfPhaseShootingStatePayload,
)
from warhammer40k_core.engine.retained_shooting import RetainedShootingExecution
from warhammer40k_core.rules.source_packages.warhammer_40000_11th.core_sequencing_2026_09 import (
    ACTIVE_PLAYER_SOURCE_ID,
)


@dataclass(frozen=True, slots=True)
class HistoricalActivePlayerAuthority:
    battle_round: int
    turn_player_id: str
    phase: str | None
    effective_player_id: str
    clock_event_id: str
    scopes: tuple[ActivePlayerScope, ...]


def active_player_authority_before_event(
    *, state: GameState, decisions: DecisionController, event_index: int
) -> HistoricalActivePlayerAuthority:
    events = decisions.event_log.records
    if type(event_index) is not int or not 0 <= event_index <= len(events):
        raise GameLifecycleError("Active-player history boundary is invalid.")
    clock: tuple[int, str, str | None] | None = None
    clock_id = ""
    scopes: list[ActivePlayerScope] = []
    retained: list[RetainedShootingExecution] = []
    accepted = {record.request.request_id: record for record in decisions.records}
    records: dict[str, DecisionRecord] = {}
    shooting_hosts: list[OutOfPhaseShootingState] = []
    attack_scopes: dict[str, ActivePlayerScope] = {}
    used_scope_boundaries: set[tuple[str, str]] = set()
    for index, event in enumerate(events[:event_index]):
        phase_start = _canonical_phase_start_context_or_none(state=state, event=event)
        if phase_start is not None:
            clock, clock_id = phase_start, event.event_id
        elif event.event_type == "battle_started":
            clock = (1, state.turn_order[0], state.battle_phase_sequence[0].value)
            clock_id = event.event_id
        elif event.event_type == "battle_phase_completed":
            payload = _object(event.payload)
            phase = payload["next_phase"]
            if phase is not None and phase not in {
                value.value for value in state.battle_phase_sequence
            }:
                raise GameLifecycleError("Active-player historical phase is invalid.")
            clock = (
                _integer(payload["battle_round"]),
                _identifier(payload["active_player_id"]),
                phase,
            )
            clock_id = event.event_id
        if event.event_type == "decision_recorded":
            record = DecisionRecord.from_payload(cast(DecisionRecordPayload, event.payload))
            if (
                accepted.get(record.request.request_id) != record
                or record.request.request_id in records
            ):
                raise GameLifecycleError("Active-player accepted decision chronology drift.")
            records[record.request.request_id] = record
        if event.event_type in {
            "out_of_phase_shooting_started",
            "fight_activation_selected",
            "fight_interrupt_activation_selected",
            "fight_activation_completed",
        }:
            payload = _object(event.payload)
            request_id = (
                payload["source_decision_request_id"]
                if event.event_type == "out_of_phase_shooting_started"
                else payload["request_id"]
                if event.event_type == "fight_activation_completed"
                else _object(payload["activation_selection"])["request_id"]
            )
            family = (
                "fight_activation_selected"
                if event.event_type == "fight_interrupt_activation_selected"
                else event.event_type
            )
            key = (family, _identifier(request_id))
            if key in used_scope_boundaries:
                raise GameLifecycleError("Active-player source scope boundary was reused.")
            used_scope_boundaries.add(key)
        _fold_scopes(
            state, decisions, records, scopes, retained, shooting_hosts, attack_scopes, event, index
        )
    if clock is None or clock[1] not in state.player_ids:
        raise GameLifecycleError("Highest/lowest reference lacks historical turn authority.")
    return HistoricalActivePlayerAuthority(
        clock[0],
        clock[1],
        clock[2],
        scopes[-1].player_id if scopes else clock[1],
        clock_id,
        tuple(scopes),
    )


def _fold_scopes(
    state: GameState,
    decisions: DecisionController,
    records: dict[str, DecisionRecord],
    scopes: list[ActivePlayerScope],
    retained: list[RetainedShootingExecution],
    shooting_hosts: list[OutOfPhaseShootingState],
    attack_scopes: dict[str, ActivePlayerScope],
    event: EventRecord,
    index: int,
) -> None:
    kind = event.event_type
    if kind == "active_player_scope_started":
        from warhammer40k_core.engine.active_player_scope_history import (
            _validate_selection,  # pyright: ignore[reportPrivateUsage]
        )
        from warhammer40k_core.engine.fight_movement_active_player import (
            validate_fight_move_selection,
        )

        scope = ActivePlayerScope.from_payload(cast(ActivePlayerScopePayload, event.payload))
        if scope.kind is ActivePlayerScopeKind.REACTIVE_MOVE:
            _record(records, scope.selection_request_id)
            _validate_selection(scope, decisions)
        elif scope.kind is ActivePlayerScopeKind.FIGHT_MOVE:
            validate_fight_move_selection(scope, decisions, index)
        else:
            raise GameLifecycleError("Active-player movement source kind drift.")
        scopes.append(scope)
    elif kind == "active_player_scope_completed":
        scope = ActivePlayerScope.from_payload(
            cast(ActivePlayerScopePayload, _object(event.payload)["scope"])
        )
        if not scopes or scopes[-1] != scope:
            raise GameLifecycleError("Active-player historical movement order drift.")
        scopes.pop()
    elif kind in {"fight_activation_selected", "fight_interrupt_activation_selected"}:
        payload = _object(event.payload)
        selected = _object(payload["activation_selection"])
        record = _record(records, _identifier(selected["request_id"]))
        expected_type = (
            FIGHT_INTERRUPT_DECISION_TYPE
            if kind == "fight_interrupt_activation_selected"
            else FIGHT_ACTIVATION_DECISION_TYPE
        )
        if record.request.decision_type != expected_type:
            raise GameLifecycleError("Active-player Fight source decision type drift.")
        selection = current_fight_activation_selection_from_payload(
            result_payload=record.result.payload,
            request_id=record.request.request_id,
            result_id=record.result.result_id,
            interrupt_id=(
                fight_interrupt_request_from_payload(record.result.payload).interrupt_id
                if kind == "fight_interrupt_activation_selected"
                else None
            ),
        )
        if selection.to_payload() != selected:
            raise GameLifecycleError("Active-player Fight selection history drift.")
        forced = payload.get("forced_activation_context")
        source_id = (
            ACTIVE_PLAYER_SOURCE_ID
            if forced is None
            else _identifier(_object(forced)["source_rule_id"])
        )
        _replace_kind(
            scopes,
            ActivePlayerScopeKind.FIGHT,
            ActivePlayerScope(
                ActivePlayerScopeKind.FIGHT,
                selection.player_id,
                selection.unit_instance_id,
                source_id,
                selection.request_id,
                selection.result_id,
            ),
        )
    elif kind == "forced_fight_activation_queue_started":
        _replace_kind(scopes, ActivePlayerScopeKind.FIGHT, None)
    elif kind == "forced_fight_activation_queue_completed":
        restored = _object(event.payload).get("resumed_state")
        fight = (
            None
            if restored is None
            else FightPhaseState.from_payload(cast(FightPhaseStatePayload, restored))
        )
        resumed_fight_scope = (
            None
            if fight is None or fight.pending_completed_attack_sequence is not None
            else fight_scope(fight)
        )
        _replace_kind(scopes, ActivePlayerScopeKind.FIGHT, resumed_fight_scope)
    elif kind == "fight_activation_completed":
        selected = _object(event.payload)
        _record(records, _identifier(selected["request_id"]))
        completed = [
            prior
            for prior in decisions.event_log.records[:index]
            if prior.event_type == "unit_has_fought"
            and isinstance(prior.payload, dict)
            and prior.payload.get("activation_selection") == selected
        ]
        if len(completed) != 1:
            raise GameLifecycleError("Active-player Fight closure lacks completed activation.")
        _replace_kind(scopes, ActivePlayerScopeKind.FIGHT, None)
    elif kind == "out_of_phase_shooting_started":
        shooting = OutOfPhaseShootingState.from_payload(
            cast(OutOfPhaseShootingStatePayload, event.payload)
        )
        scope = shooting_scope(shooting)
        record = _record(records, scope.selection_request_id)
        from warhammer40k_core.engine.shooting_scope_history import validate_shooting_scope_source

        validate_shooting_scope_source(
            state=state,
            decisions=decisions,
            shooting=shooting,
            record=record,
            event_index=index,
            retained=tuple(retained),
        )
        shooting_hosts.append(shooting)
        _replace_kind(scopes, ActivePlayerScopeKind.OUT_OF_PHASE_SHOOT, scope)
    elif kind == "out_of_phase_shooting_completed":
        payload = _object(event.payload)
        if not shooting_hosts:
            raise GameLifecycleError("Active-player shooting completion lacks an opening.")
        host = shooting_hosts.pop()
        expected = {
            "game_id": state.game_id,
            "battle_round": host.battle_round,
            "player_id": host.player_id,
            "parent_phase": host.parent_phase.value,
            "source_rule_id": host.source_rule_id,
            "selected_unit_instance_id": host.selected_unit_instance_id,
        }
        if any(payload.get(key) != value for key, value in expected.items()):
            raise GameLifecycleError("Active-player shooting completion source drift.")
        _replace_kind(scopes, ActivePlayerScopeKind.OUT_OF_PHASE_SHOOT, None)
    elif kind == "retained_shooting_started":
        retained.append(RetainedShootingExecution.from_payload(event.payload))
        _replace_kind(scopes, ActivePlayerScopeKind.OUT_OF_PHASE_SHOOT, None)
    elif kind == "retained_shooting_resumed_parent":
        if not retained or retained[-1].cause_id != _object(event.payload)["cause_id"]:
            raise GameLifecycleError("Active-player retained shooting order drift.")
        resumed_shooting = retained.pop().suspended_shooting
        resumed_shooting_scope = (
            None
            if resumed_shooting is None
            or resumed_shooting.pending_completed_attack_sequence is not None
            else shooting_scope(resumed_shooting)
        )
        _replace_kind(scopes, ActivePlayerScopeKind.OUT_OF_PHASE_SHOOT, resumed_shooting_scope)
    elif kind == "interrupted_charge_started":
        payload = _object(event.payload)
        source = _object(payload["source"])
        record = _record(records, _identifier(source["source_request_id"]))
        player = _identifier(payload["player_id"])
        if (
            record.result.actor_id != player
            or record.result.result_id != source["source_result_id"]
        ):
            raise GameLifecycleError("Active-player Charge selection authority drift.")
        scopes.append(
            ActivePlayerScope(
                ActivePlayerScopeKind.CHARGE,
                player,
                _identifier(source["unit_instance_id"]),
                _identifier(source["source_id"]),
                record.request.request_id,
                record.result.result_id,
            )
        )
    elif kind == "interrupted_charge_completed":
        _replace_kind(scopes, ActivePlayerScopeKind.CHARGE, None)
    elif kind in {"melee_declaration_accepted", "out_of_phase_shooting_declaration_accepted"}:
        payload = _object(event.payload)
        scope_kind = (
            ActivePlayerScopeKind.FIGHT
            if kind == "melee_declaration_accepted"
            else ActivePlayerScopeKind.OUT_OF_PHASE_SHOOT
        )
        matching = [scope for scope in scopes if scope.kind is scope_kind]
        if len(matching) != 1:
            raise GameLifecycleError("Attack declaration lacks historical active-player scope.")
        attack_scopes[_identifier(payload["attack_sequence_id"])] = matching[0]
    elif kind == "attack_sequence_completed":
        sequence_id = _identifier(_object(event.payload)["sequence_id"])
        if sequence_id in attack_scopes:
            scope = attack_scopes.pop(sequence_id)
            scopes[:] = [current for current in scopes if current != scope]
    for scope in scopes:
        if scope.player_id not in state.player_ids:
            raise GameLifecycleError("Active-player historical owner is not in this game.")


def _replace_kind(
    scopes: list[ActivePlayerScope], kind: ActivePlayerScopeKind, scope: ActivePlayerScope | None
) -> None:
    scopes[:] = [current for current in scopes if current.kind is not kind]
    if scope is not None:
        scopes.append(scope)


def _record(records: dict[str, DecisionRecord], request_id: str) -> DecisionRecord:
    if request_id not in records:
        raise GameLifecycleError("Active-player history lacks its accepted source selection.")
    return records[request_id]


def _object(value: JsonValue) -> dict[str, JsonValue]:
    if not isinstance(value, dict):
        raise GameLifecycleError("Active-player history requires an object.")
    return value


def _identifier(value: JsonValue) -> str:
    if type(value) is not str or not value:
        raise GameLifecycleError("Active-player history requires an identifier.")
    return value


def _integer(value: JsonValue) -> int:
    if type(value) is not int or value < 1:
        raise GameLifecycleError("Active-player history requires a positive round.")
    return value
