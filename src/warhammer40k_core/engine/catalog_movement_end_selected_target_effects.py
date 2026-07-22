from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import TYPE_CHECKING

from warhammer40k_core.engine.abilities import AbilityCatalogIndex, AbilityCatalogRecord
from warhammer40k_core.engine.army_mustering import ArmyDefinition
from warhammer40k_core.engine.catalog_rule_consumption import (
    CATALOG_IR_MOVEMENT_END_SELECTED_TARGET_EFFECT_CONSUMER_ID,
    catalog_rule_current_placed_alive_model_instance_ids_for_unit,
)
from warhammer40k_core.engine.catalog_selected_target_decisions import (
    SelectedTargetGroup,
    invalid_selected_target_effect_status,
    resolved_phase_selected_target_group_keys,
    selected_target_request,
)
from warhammer40k_core.engine.catalog_selected_target_effects import (
    append_selected_target_event,
    options_for_targets,
    record_selected_target_effects_from_payload,
)
from warhammer40k_core.engine.catalog_selected_target_effects_support import (
    army_for_player,
    catalog_selected_target_clauses_from_record,
    clause_is_movement_end_selection,
    eligible_selection_target_unit_ids,
    has_movement_end_selected_target_runtime_records,
    movement_end_effect_clauses_after,
    payload_object,
    runtime_clause_id_from_record,
    selection_source_model_ids_for_record,
    unit_scoped_generic_records_for_timing,
    validate_ability_indexes,
    validate_armies,
)
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.event_log import validate_json_value
from warhammer40k_core.engine.phase import (
    BattlePhase,
    GameLifecycleError,
    GameLifecycleStage,
    LifecycleStatus,
)
from warhammer40k_core.engine.timing_windows import TimingTriggerKind
from warhammer40k_core.engine.unit_factory import UnitInstance

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState

SELECT_CATALOG_MOVEMENT_END_TARGET_EFFECT_DECISION_TYPE = (
    "select_catalog_movement_end_target_effect"
)
SELECT_CATALOG_MOVEMENT_END_TARGET_EFFECT_SUBMISSION_KIND = (
    "select_catalog_movement_end_target_effect"
)
CATALOG_MOVEMENT_END_SELECTED_TARGET_EFFECT_SELECTED_EVENT = (
    "catalog_movement_end_selected_target_effect_selected"
)


@dataclass(frozen=True, slots=True)
class CatalogMovementEndSelectedTargetEffectRuntime:
    ability_indexes_by_player_id: Mapping[str, AbilityCatalogIndex]
    armies: tuple[ArmyDefinition, ...]

    def __post_init__(self) -> None:
        indexes = validate_ability_indexes(self.ability_indexes_by_player_id)
        armies = validate_armies(self.armies)
        if {army.player_id for army in armies} - set(indexes):
            raise GameLifecycleError("Catalog selected-target runtime missing ability index.")
        object.__setattr__(self, "ability_indexes_by_player_id", MappingProxyType(dict(indexes)))
        object.__setattr__(self, "armies", armies)

    def request(
        self,
        *,
        state: GameState,
        decisions: DecisionController,
    ) -> LifecycleStatus | None:
        if not has_movement_end_selected_target_runtime_records(
            self.ability_indexes_by_player_id,
            self.armies,
        ):
            return None
        groups = _selected_target_groups(
            ability_indexes_by_player_id=self.ability_indexes_by_player_id,
            armies=self.armies,
            state=state,
        )
        resolved = resolved_phase_selected_target_group_keys(
            decisions,
            event_type=CATALOG_MOVEMENT_END_SELECTED_TARGET_EFFECT_SELECTED_EVENT,
        )
        unresolved = tuple(group for group in groups if group.sort_key not in resolved)
        if not unresolved:
            return None
        group = unresolved[0]
        request = selected_target_request(
            state=state,
            group=group,
            decision_type=SELECT_CATALOG_MOVEMENT_END_TARGET_EFFECT_DECISION_TYPE,
        )
        decisions.request_decision(request)
        decisions.event_log.append(
            "catalog_movement_end_selected_target_effect_requested",
            validate_json_value(
                {
                    "game_id": state.game_id,
                    "battle_round": state.battle_round,
                    "phase": BattlePhase.MOVEMENT.value,
                    "active_player_id": state.active_player_id,
                    "player_id": group.player_id,
                    "hook_id": CATALOG_IR_MOVEMENT_END_SELECTED_TARGET_EFFECT_CONSUMER_ID,
                    "request_id": request.request_id,
                    "catalog_record_id": group.record.record_id,
                    "source_rule_id": group.record.definition.source_id,
                    "source_unit_instance_id": group.unit.unit_instance_id,
                    "source_model_instance_id": group.source_model_instance_id,
                    "selection_clause_id": group.selection_clause.clause_id,
                    "available_target_unit_instance_ids": [
                        option.target_unit_instance_id for option in group.options
                    ],
                    "phase_body_status": "catalog_movement_end_target_effect_pending",
                }
            ),
        )
        return LifecycleStatus.waiting_for_decision(
            stage=GameLifecycleStage.BATTLE,
            decision_request=request,
            payload=validate_json_value(
                {
                    "phase": BattlePhase.MOVEMENT.value,
                    "battle_round": state.battle_round,
                    "active_player_id": state.active_player_id,
                    "player_id": group.player_id,
                    "pending_request_id": request.request_id,
                    "phase_body_status": "catalog_movement_end_target_effect_pending",
                }
            ),
        )

    def apply_result(
        self,
        *,
        state: GameState,
        decisions: DecisionController,
        request: DecisionRequest,
        result: DecisionResult,
    ) -> LifecycleStatus | None:
        invalid_status = invalid_catalog_movement_end_target_effect_status(
            state=state,
            request=request,
            result=result,
        )
        if invalid_status is not None:
            return invalid_status
        payload = payload_object(result.payload)
        recording = record_selected_target_effects_from_payload(
            state=state,
            decisions=decisions,
            result=result,
            payload=payload,
            phase=BattlePhase.MOVEMENT,
            event_type=CATALOG_MOVEMENT_END_SELECTED_TARGET_EFFECT_SELECTED_EVENT,
        )
        if recording.pending_status is not None:
            return recording.pending_status
        append_selected_target_event(
            state=state,
            decisions=decisions,
            result=result,
            payload=payload,
            effects=recording.effects,
            event_type=CATALOG_MOVEMENT_END_SELECTED_TARGET_EFFECT_SELECTED_EVENT,
            phase=BattlePhase.MOVEMENT,
        )
        return None


def invalid_catalog_movement_end_target_effect_status(
    *,
    state: GameState,
    request: DecisionRequest,
    result: DecisionResult,
) -> LifecycleStatus | None:
    return invalid_selected_target_effect_status(
        state=state,
        request=request,
        result=result,
        expected_decision_type=SELECT_CATALOG_MOVEMENT_END_TARGET_EFFECT_DECISION_TYPE,
        expected_submission_kind=SELECT_CATALOG_MOVEMENT_END_TARGET_EFFECT_SUBMISSION_KIND,
        expected_phase=BattlePhase.MOVEMENT,
        invalid_reason="invalid_catalog_movement_end_target_effect_result",
    )


def _selected_target_groups(
    *,
    ability_indexes_by_player_id: Mapping[str, AbilityCatalogIndex],
    armies: tuple[ArmyDefinition, ...],
    state: GameState,
) -> tuple[SelectedTargetGroup, ...]:
    if state.current_battle_phase is not BattlePhase.MOVEMENT:
        return ()
    if state.battlefield_state is None:
        return ()
    active_player_id = state.active_player_id
    if active_player_id is None:
        raise GameLifecycleError("Catalog Movement-end target effect requires active player.")
    army = army_for_player(armies, player_id=active_player_id)
    index = ability_indexes_by_player_id.get(active_player_id)
    if index is None:
        raise GameLifecycleError("Catalog Movement-end target effect missing ability index.")
    groups: list[SelectedTargetGroup] = []
    for unit in sorted(army.units, key=lambda item: item.unit_instance_id):
        current_model_ids = catalog_rule_current_placed_alive_model_instance_ids_for_unit(
            state=state,
            unit=unit,
        )
        if not current_model_ids:
            continue
        for record in unit_scoped_generic_records_for_timing(
            ability_index=index,
            unit=unit,
            current_model_instance_ids=current_model_ids,
            trigger_kind=TimingTriggerKind.END_PHASE,
        ):
            groups.extend(
                _groups_for_record(
                    state=state,
                    army=army,
                    unit=unit,
                    current_model_instance_ids=current_model_ids,
                    record=record,
                )
            )
    return tuple(sorted(groups, key=lambda group: group.sort_key))


def _groups_for_record(
    *,
    state: GameState,
    army: ArmyDefinition,
    unit: UnitInstance,
    current_model_instance_ids: tuple[str, ...],
    record: AbilityCatalogRecord,
) -> tuple[SelectedTargetGroup, ...]:
    clauses = catalog_selected_target_clauses_from_record(record)
    runtime_clause_id = runtime_clause_id_from_record(record)
    groups: list[SelectedTargetGroup] = []
    for index, selection_clause in enumerate(clauses):
        if runtime_clause_id is not None and runtime_clause_id != selection_clause.clause_id:
            continue
        if not clause_is_movement_end_selection(selection_clause):
            continue
        effect_clauses = movement_end_effect_clauses_after(clauses, index)
        if not effect_clauses:
            continue
        for source_model_id in selection_source_model_ids_for_record(
            record,
            unit,
            selection_clause,
            effect_clauses,
            current_model_instance_ids,
        ):
            target_ids = eligible_selection_target_unit_ids(
                state=state,
                source_player_id=army.player_id,
                source_unit_instance_id=unit.unit_instance_id,
                source_model_instance_id=source_model_id,
                selection_clause=selection_clause,
                explicit_target_unit_ids=None,
            )
            options = options_for_targets(
                state=state,
                record=record,
                player_id=army.player_id,
                unit=unit,
                source_model_instance_id=source_model_id,
                selection_clause=selection_clause,
                effect_clauses=effect_clauses,
                selected_target_unit_ids=target_ids,
                phase=BattlePhase.MOVEMENT,
                hook_id=CATALOG_IR_MOVEMENT_END_SELECTED_TARGET_EFFECT_CONSUMER_ID,
                submission_kind=SELECT_CATALOG_MOVEMENT_END_TARGET_EFFECT_SUBMISSION_KIND,
                attack_sequence=None,
                attack_sequence_completed_event_id=None,
            )
            if options:
                groups.append(
                    SelectedTargetGroup(
                        record=record,
                        player_id=army.player_id,
                        unit=unit,
                        source_model_instance_id=source_model_id,
                        selection_clause=selection_clause,
                        effect_clauses=effect_clauses,
                        options=options,
                        phase=BattlePhase.MOVEMENT,
                        hook_id=CATALOG_IR_MOVEMENT_END_SELECTED_TARGET_EFFECT_CONSUMER_ID,
                        submission_kind=SELECT_CATALOG_MOVEMENT_END_TARGET_EFFECT_SUBMISSION_KIND,
                    )
                )
    return tuple(groups)
