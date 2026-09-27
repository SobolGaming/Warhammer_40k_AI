"""Complete a selected shooting type without claiming a weapon or model shot."""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING

import msgspec

from warhammer40k_core.engine.activity_restrictions import build_activity_restriction
from warhammer40k_core.engine.effects import EffectExpiration, PersistingEffect
from warhammer40k_core.engine.event_log import EventRecord, JsonValue, validate_json_value
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError, LifecycleStatus
from warhammer40k_core.engine.rules_units import rules_unit_identity_ids, rules_unit_view_by_id
from warhammer40k_core.engine.shooting_types import ShootingType

if TYPE_CHECKING:
    from warhammer40k_core.core.army_catalog import ArmyCatalog
    from warhammer40k_core.engine.decision_controller import DecisionController
    from warhammer40k_core.engine.decision_record import DecisionRecord
    from warhammer40k_core.engine.game_state import GameState
    from warhammer40k_core.engine.phases.shooting_model import ShootingUnitSelection

NO_ATTACK_COMPLETION_EVENT = "shooting_without_attacks_completed"


class NoAttackCompletion(msgspec.Struct, frozen=True, forbid_unknown_fields=True):
    game_id: str
    battle_round: int
    active_player_id: str
    phase: BattlePhase
    player_id: str
    unit_instance_id: str
    source_decision_request_id: str
    source_decision_result_id: str
    type_request_id: str | None
    type_result_id: str | None
    shooting_type: ShootingType | None
    out_of_phase: bool
    firing_deck_embarked_unit_instance_ids: tuple[str, ...]

    @property
    def activity_id(self) -> str:
        return f"shooting-without-attacks:{self.source_decision_result_id}"


def completion_from_event(event: EventRecord) -> NoAttackCompletion:
    if event.event_type != NO_ATTACK_COMPLETION_EVENT:
        raise GameLifecycleError("No-attack completion requires its own event.")
    try:
        return msgspec.convert(event.payload, type=NoAttackCompletion)
    except msgspec.ValidationError as exc:
        raise GameLifecycleError("No-attack shooting completion is malformed.") from exc


def restriction_for_completion(*, state: GameState, row: NoAttackCompletion) -> PersistingEffect:
    return build_activity_restriction(
        owner_player_id=row.player_id,
        target_unit_instance_ids=tuple(
            sorted(rules_unit_identity_ids(state=state, unit_instance_id=row.unit_instance_id))
        ),
        activity="completed_shooting",
        activity_id=row.activity_id,
        battle_round=row.battle_round,
        phase=row.phase,
        expiration=EffectExpiration.end_phase(
            battle_round=row.battle_round, player_id=row.active_player_id, phase=row.phase
        ),
    )


def complete_shooting_without_attacks(
    *,
    state: GameState,
    decisions: DecisionController,
    selection: ShootingUnitSelection,
    selected_shooting_type: ShootingType | None,
    forced_shooting_type: ShootingType | None,
    army_catalog: ArmyCatalog,
) -> LifecycleStatus:
    from warhammer40k_core.engine.firing_deck_restrictions import record_firing_deck_restriction
    from warhammer40k_core.engine.phases.shooting_firing_deck import firing_deck_cargo_snapshot
    from warhammer40k_core.engine.phases.shooting_reactions import _complete_out_of_phase_shooting

    phase, active_player = state.current_battle_phase, state.active_player_id
    if phase is None or active_player is None:
        raise GameLifecycleError("No-attack shooting requires a current phase and turn.")
    host = state.out_of_phase_shooting_state
    ordinary = state.shooting_phase_state
    type_selection = None
    if host is not None:
        if (
            host.source_decision_request_id != selection.request_id
            or host.source_decision_result_id != selection.result_id
            or host.selected_unit_instance_id != selection.unit_instance_id
            or host.attack_pools
            or host.attack_sequence is not None
        ):
            raise GameLifecycleError("No-attack out-of-phase shooting context drifted.")
    else:
        if (
            ordinary is None
            or ordinary.active_selection != selection
            or ordinary.selected_shooting_type is None
        ):
            raise GameLifecycleError("No-attack shooting requires a selected unit and type.")
        type_selection = ordinary.selected_shooting_type
        if type_selection.shooting_type is not selected_shooting_type:
            raise GameLifecycleError("No-attack shooting type drifted.")
    cargo = firing_deck_cargo_snapshot(
        state=state, unit_instance_id=selection.unit_instance_id, army_catalog=army_catalog
    )
    row = NoAttackCompletion(
        game_id=state.game_id,
        battle_round=state.battle_round,
        active_player_id=active_player,
        phase=phase,
        player_id=selection.player_id,
        unit_instance_id=selection.unit_instance_id,
        source_decision_request_id=selection.request_id,
        source_decision_result_id=selection.result_id,
        type_request_id=None if type_selection is None else type_selection.request_id,
        type_result_id=None if type_selection is None else type_selection.result_id,
        shooting_type=forced_shooting_type if host is not None else selected_shooting_type,
        out_of_phase=host is not None,
        firing_deck_embarked_unit_instance_ids=cargo,
    )
    state.record_persisting_effect(restriction_for_completion(state=state, row=row))
    record_firing_deck_restriction(
        state=state,
        transport_unit_instance_id=selection.unit_instance_id,
        embarked_unit_instance_ids=cargo,
        result_id=selection.result_id,
    )
    decisions.event_log.append(
        NO_ATTACK_COMPLETION_EVENT, validate_json_value(msgspec.to_builtins(row))
    )
    if host is not None:
        return _complete_out_of_phase_shooting(
            state=state, decisions=decisions, completed_state=host
        )
    assert ordinary is not None
    state.replace_shooting_phase_state(
        replace(ordinary, active_selection=None, selected_shooting_type=None)
    )
    return LifecycleStatus.advanced(
        stage=state.stage,
        payload={
            "phase": phase.value,
            "phase_body_status": "shooting_without_attacks_completed",
            "unit_instance_id": selection.unit_instance_id,
        },
    )


def validate_no_attack_completions(
    *, state: GameState, events: tuple[EventRecord, ...], decisions: tuple[DecisionRecord, ...]
) -> dict[str, NoAttackCompletion]:
    """Bind each terminal to the accepted selection and its historical host."""
    by_result = {record.result.result_id: record for record in decisions}
    completed: dict[str, NoAttackCompletion] = {}
    from warhammer40k_core.engine.objective_control_boundary_history_integrity import (
        _canonical_phase_start_context_or_none,  # pyright: ignore[reportPrivateUsage]
    )
    from warhammer40k_core.engine.weapon_abilities import FIRE_OVERWATCH_RULE_ID

    started: dict[str, dict[str, JsonValue]] = {}
    host_stack: list[str] = []
    clock: tuple[int, str | None, str | None] | None = None
    accepted_results: set[str] = set()
    declarations: set[str] = set()
    for event in events:
        boundary = _canonical_phase_start_context_or_none(state=state, event=event)
        if boundary is not None:
            clock = boundary
        elif event.event_type == "battle_phase_completed":
            payload = _object(event.payload)
            round_number, player_id, phase = (
                payload["battle_round"],
                payload["active_player_id"],
                payload["next_phase"],
            )
            if (
                type(round_number) is not int
                or not (player_id is None or isinstance(player_id, str))
                or not (phase is None or isinstance(phase, str))
                or (player_id is None) != (phase is None)
            ):
                raise GameLifecycleError("No-attack phase history is malformed.")
            clock = (round_number, player_id, phase)
        if event.event_type == "decision_recorded":
            accepted = _object(_object(event.payload)["result"])["result_id"]
            if not isinstance(accepted, str):
                raise GameLifecycleError("No-attack source decision identity is invalid.")
            accepted_results.add(accepted)
        if event.event_type == "out_of_phase_shooting_started":
            payload = _object(event.payload)
            result_id = payload["source_decision_result_id"]
            if not isinstance(result_id, str):
                raise GameLifecycleError("No-attack shooting host identity is invalid.")
            if result_id not in accepted_results:
                raise GameLifecycleError("No-attack host lacks its accepted source selection.")
            started[result_id] = payload
            host_stack.append(result_id)
        elif event.event_type == "out_of_phase_shooting_completed":
            if not host_stack:
                raise GameLifecycleError("No-attack completion lacks an out-of-phase host.")
            source = host_stack.pop()
            if source not in declarations and source not in completed:
                raise GameLifecycleError("No-attack out-of-phase completion history is missing.")
        elif event.event_type == "shooting_declaration_requested":
            payload = _object(event.payload)
            result_id = payload["source_decision_result_id"]
            if not isinstance(result_id, str):
                raise GameLifecycleError("No-attack declaration identity is invalid.")
            declarations.add(result_id)
        elif event.event_type == NO_ATTACK_COMPLETION_EVENT:
            row = completion_from_event(event)
            record = by_result.get(row.source_decision_result_id)
            if (
                record is None
                or record.request.request_id != row.source_decision_request_id
                or record.request.actor_id != row.player_id
                or row.game_id != state.game_id
                or clock != (row.battle_round, row.active_player_id, row.phase.value)
                or row.source_decision_result_id in completed
                or row.source_decision_result_id in declarations
                or rules_unit_view_by_id(
                    state=state, unit_instance_id=row.unit_instance_id
                ).owner_player_id
                != row.player_id
            ):
                raise GameLifecycleError("No-attack shooting selection identity drifted.")
            if row.out_of_phase:
                host = started.get(row.source_decision_result_id)
                if (
                    host is None
                    or host["source_decision_request_id"] != row.source_decision_request_id
                    or host["selected_unit_instance_id"] != row.unit_instance_id
                    or host["battle_round"] != row.battle_round
                    or host["parent_phase"] != row.phase.value
                    or host["player_id"] != row.player_id
                    or row.shooting_type
                    != (
                        ShootingType.SNAP
                        if host["source_rule_id"] == FIRE_OVERWATCH_RULE_ID
                        else None
                    )
                    or row.type_request_id is not None
                    or row.type_result_id is not None
                    or row.firing_deck_embarked_unit_instance_ids
                ):
                    raise GameLifecycleError("No-attack shooting host drifted.")
            else:
                typed = (
                    by_result.get(row.type_result_id) if row.type_result_id is not None else None
                )
                if typed is None or typed.request.decision_type != "select_shooting_type":
                    raise GameLifecycleError("No-attack shooting lacks its type decision.")
                context = _object(typed.request.payload)
                option = _object(typed.result.payload)
                if (
                    record.request.decision_type != "select_shooting_unit"
                    or _object(record.result.payload).get("unit_instance_id")
                    != row.unit_instance_id
                    or typed.request.request_id != row.type_request_id
                    or typed.request.actor_id != row.player_id
                    or context.get("source_decision_request_id") != row.source_decision_request_id
                    or context.get("source_decision_result_id") != row.source_decision_result_id
                    or context.get("battle_round") != row.battle_round
                    or context.get("active_player_id") != row.active_player_id
                    or context.get("phase") != row.phase.value
                    or option.get("unit_instance_id") != row.unit_instance_id
                    or option.get("shooting_type") != row.shooting_type
                    or context.get("firing_deck_embarked_unit_instance_ids")
                    != (
                        list(row.firing_deck_embarked_unit_instance_ids)
                        if row.firing_deck_embarked_unit_instance_ids
                        else None
                    )
                ):
                    raise GameLifecycleError("No-attack shooting type or cargo identity drifted.")
            completed[row.source_decision_result_id] = row
    for record in decisions:
        if record.request.decision_type != "select_shooting_type":
            continue
        context = _object(record.request.payload)
        selected_source = context["source_decision_result_id"]
        if (
            not isinstance(selected_source, str)
            or selected_source not in declarations | completed.keys()
        ):
            raise GameLifecycleError("No-attack shooting completion history is missing.")
    phase_state = state.shooting_phase_state
    for row in completed.values():
        if (
            not row.out_of_phase
            and phase_state is not None
            and row.battle_round == phase_state.battle_round
            and row.player_id == phase_state.active_player_id
        ) and (
            row.unit_instance_id not in phase_state.selected_unit_ids
            or row.unit_instance_id in phase_state.shot_unit_ids
            or row.unit_instance_id in phase_state.skipped_unit_ids
            or (
                phase_state.active_selection is not None
                and phase_state.active_selection.result_id == row.source_decision_result_id
            )
        ):
            raise GameLifecycleError("No-attack selection state claims an incompatible outcome.")
    return completed


def _object(payload: JsonValue) -> dict[str, JsonValue]:
    if not isinstance(payload, dict):
        raise GameLifecycleError("No-attack shooting history requires an object.")
    return payload
