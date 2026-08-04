from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING

from warhammer40k_core.engine.abilities import AbilityCatalogIndex, AbilityCatalogRecord
from warhammer40k_core.engine.army_mustering import ArmyDefinition
from warhammer40k_core.engine.attack_sequence import AttackSequence
from warhammer40k_core.engine.attack_sequence_completion_hooks import (
    AttackSequenceCompletedContext,
    successful_hit_target_unit_ids_for_sequence,
)
from warhammer40k_core.engine.catalog_rule_consumption import (
    catalog_rule_current_placed_alive_model_instance_ids_for_unit,
)
from warhammer40k_core.engine.catalog_rule_selected_target_classification import (
    CATALOG_IR_POST_FIGHT_HIT_TARGET_EFFECT_CONSUMER_ID,
)
from warhammer40k_core.engine.catalog_selected_target_decisions import (
    SelectedTargetGroup,
    invalid_selected_target_effect_status,
    post_shoot_group_key,
    resolved_post_shoot_target_effect_group_keys,
    selected_target_request,
)
from warhammer40k_core.engine.catalog_selected_target_effects_support import (
    army_for_player,
    catalog_selected_target_clauses_from_record,
    clause_is_post_fight_hit_target_selection,
    eligible_selection_target_unit_ids,
    payload_object,
    post_fight_selected_target_effect_clauses_after,
    record_has_supported_post_fight_selected_target_effect,
    runtime_clause_id_from_record,
    selection_source_model_ids_for_record,
    selection_weapon_names,
    unit_scoped_generic_records_for_timing,
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
from warhammer40k_core.engine.rules_units import rules_unit_view_by_id
from warhammer40k_core.engine.timing_windows import TimingTriggerKind
from warhammer40k_core.engine.unit_factory import UnitInstance

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState


SELECT_CATALOG_POST_FIGHT_HIT_TARGET_EFFECT_DECISION_TYPE = (
    "select_catalog_post_fight_hit_target_effect"
)
SELECT_CATALOG_POST_FIGHT_HIT_TARGET_EFFECT_SUBMISSION_KIND = (
    "select_catalog_post_fight_hit_target_effect"
)
CATALOG_POST_FIGHT_HIT_TARGET_EFFECT_SELECTED_EVENT = (
    "catalog_post_fight_hit_target_effect_selected"
)


def post_fight_hit_target_request(
    *,
    ability_indexes_by_player_id: Mapping[str, AbilityCatalogIndex],
    armies: tuple[ArmyDefinition, ...],
    context: AttackSequenceCompletedContext,
) -> LifecycleStatus | None:
    if type(context) is not AttackSequenceCompletedContext:
        raise GameLifecycleError("Catalog post-fight target effect requires context.")
    groups = _post_fight_hit_target_effect_groups(
        ability_indexes_by_player_id=ability_indexes_by_player_id,
        armies=armies,
        context=context,
    )
    if not groups:
        return None
    resolved = resolved_post_shoot_target_effect_group_keys(
        context.decisions,
        event_type=CATALOG_POST_FIGHT_HIT_TARGET_EFFECT_SELECTED_EVENT,
    )
    unresolved = tuple(group for group in groups if post_shoot_group_key(group) not in resolved)
    if not unresolved:
        return None
    group = unresolved[0]
    request = selected_target_request(
        state=context.state,
        group=group,
        decision_type=SELECT_CATALOG_POST_FIGHT_HIT_TARGET_EFFECT_DECISION_TYPE,
    )
    context.decisions.request_decision(request)
    context.decisions.event_log.append(
        "catalog_post_fight_hit_target_effect_requested",
        validate_json_value(
            {
                "game_id": context.state.game_id,
                "battle_round": context.state.battle_round,
                "phase": BattlePhase.FIGHT.value,
                "active_player_id": context.state.active_player_id,
                "player_id": group.player_id,
                "hook_id": CATALOG_IR_POST_FIGHT_HIT_TARGET_EFFECT_CONSUMER_ID,
                "request_id": request.request_id,
                "catalog_record_id": group.record.record_id,
                "source_rule_id": group.record.definition.source_id,
                "unit_instance_id": group.unit.unit_instance_id,
                "source_model_instance_id": group.source_model_instance_id,
                "selection_clause_id": group.selection_clause.clause_id,
                "attack_sequence_id": (
                    None if group.attack_sequence is None else group.attack_sequence.sequence_id
                ),
                "attack_sequence_completed_event_id": group.attack_sequence_completed_event_id,
                "available_target_unit_instance_ids": [
                    option.target_unit_instance_id for option in group.options
                ],
                "phase_body_status": "catalog_post_fight_hit_target_effect_pending",
            }
        ),
    )
    return LifecycleStatus.waiting_for_decision(
        stage=GameLifecycleStage.BATTLE,
        decision_request=request,
        payload=validate_json_value(
            {
                "phase": BattlePhase.FIGHT.value,
                "battle_round": context.state.battle_round,
                "active_player_id": context.state.active_player_id,
                "player_id": group.player_id,
                "pending_request_id": request.request_id,
                "phase_body_status": "catalog_post_fight_hit_target_effect_pending",
            }
        ),
    )


def invalid_catalog_post_fight_hit_target_effect_status(
    *,
    state: GameState,
    request: DecisionRequest,
    result: DecisionResult,
) -> LifecycleStatus | None:
    return invalid_selected_target_effect_status(
        state=state,
        request=request,
        result=result,
        expected_decision_type=SELECT_CATALOG_POST_FIGHT_HIT_TARGET_EFFECT_DECISION_TYPE,
        expected_submission_kind=SELECT_CATALOG_POST_FIGHT_HIT_TARGET_EFFECT_SUBMISSION_KIND,
        expected_phase=BattlePhase.FIGHT,
        invalid_reason="invalid_catalog_post_fight_hit_target_effect_result",
    )


def apply_catalog_post_fight_hit_target_effect_result(
    *,
    state: GameState,
    decisions: DecisionController,
    result: DecisionResult,
) -> LifecycleStatus | None:
    from warhammer40k_core.engine.catalog_selected_target_effects import (
        record_selected_target_effects_from_payload,
    )
    from warhammer40k_core.engine.catalog_selected_target_event import (
        append_selected_target_event,
    )

    if type(decisions) is not DecisionController:
        raise GameLifecycleError("Catalog post-fight target effect apply requires decisions.")
    if type(result) is not DecisionResult:
        raise GameLifecycleError("Catalog post-fight target effect apply requires result.")
    record = decisions.record_for_result(result)
    invalid_status = invalid_catalog_post_fight_hit_target_effect_status(
        state=state,
        request=record.request,
        result=record.result,
    )
    if invalid_status is not None:
        return invalid_status
    payload = payload_object(record.result.payload)
    recording = record_selected_target_effects_from_payload(
        state=state,
        decisions=decisions,
        result=record.result,
        payload=payload,
        phase=BattlePhase.FIGHT,
        event_type=CATALOG_POST_FIGHT_HIT_TARGET_EFFECT_SELECTED_EVENT,
    )
    if recording.pending_status is not None:
        return recording.pending_status
    append_selected_target_event(
        state=state,
        decisions=decisions,
        result=record.result,
        payload=payload,
        effects=recording.effects,
        event_type=CATALOG_POST_FIGHT_HIT_TARGET_EFFECT_SELECTED_EVENT,
        phase=BattlePhase.FIGHT,
    )
    return None


def _post_fight_hit_target_effect_groups(
    *,
    ability_indexes_by_player_id: Mapping[str, AbilityCatalogIndex],
    armies: tuple[ArmyDefinition, ...],
    context: AttackSequenceCompletedContext,
) -> tuple[SelectedTargetGroup, ...]:
    if (
        context.source_phase is not BattlePhase.FIGHT
        or context.attack_sequence.source_phase is not BattlePhase.FIGHT
    ):
        return ()
    player_id = context.attack_sequence.attacker_player_id
    army = army_for_player(armies, player_id=player_id)
    rules_unit = rules_unit_view_by_id(
        state=context.state,
        unit_instance_id=context.attack_sequence.attacking_unit_instance_id,
    )
    index = ability_indexes_by_player_id.get(player_id)
    if index is None:
        raise GameLifecycleError("Catalog post-fight target effect missing ability index.")
    groups: list[SelectedTargetGroup] = []
    for component in sorted(
        rules_unit.components,
        key=lambda value: value.unit.unit_instance_id,
    ):
        unit = component.unit
        current_model_ids = catalog_rule_current_placed_alive_model_instance_ids_for_unit(
            state=context.state,
            unit=unit,
        )
        if not current_model_ids:
            continue
        for record in unit_scoped_generic_records_for_timing(
            ability_index=index,
            unit=unit,
            current_model_instance_ids=current_model_ids,
            trigger_kind=TimingTriggerKind.ANY_PHASE,
        ):
            if not record_has_supported_post_fight_selected_target_effect(record):
                continue
            groups.extend(
                _post_fight_groups_for_record(
                    state=context.state,
                    decisions=context.decisions,
                    army=army,
                    unit=unit,
                    current_model_instance_ids=current_model_ids,
                    record=record,
                    attack_sequence=context.attack_sequence,
                    attack_sequence_completed_event_id=(context.attack_sequence_completed_event_id),
                )
            )
    return tuple(sorted(groups, key=lambda group: group.sort_key))


def _post_fight_groups_for_record(
    *,
    state: GameState,
    decisions: DecisionController,
    army: ArmyDefinition,
    unit: UnitInstance,
    current_model_instance_ids: tuple[str, ...],
    record: AbilityCatalogRecord,
    attack_sequence: AttackSequence,
    attack_sequence_completed_event_id: str,
) -> tuple[SelectedTargetGroup, ...]:
    from warhammer40k_core.engine.catalog_selected_target_effects import options_for_targets

    clauses = catalog_selected_target_clauses_from_record(record)
    runtime_clause_id = runtime_clause_id_from_record(record)
    groups: list[SelectedTargetGroup] = []
    for index, selection_clause in enumerate(clauses):
        if runtime_clause_id is not None and runtime_clause_id != selection_clause.clause_id:
            continue
        if not clause_is_post_fight_hit_target_selection(selection_clause):
            continue
        effect_clauses = post_fight_selected_target_effect_clauses_after(clauses, index)
        if not effect_clauses:
            continue
        for source_model_id in selection_source_model_ids_for_record(
            record,
            unit,
            selection_clause,
            effect_clauses,
            current_model_instance_ids,
        ):
            hit_target_ids = successful_hit_target_unit_ids_for_sequence(
                decisions=decisions,
                sequence=attack_sequence,
                attacker_model_instance_id=source_model_id,
                weapon_names=selection_weapon_names(selection_clause),
            )
            if not hit_target_ids:
                continue
            target_ids = eligible_selection_target_unit_ids(
                state=state,
                source_player_id=army.player_id,
                source_unit_instance_id=unit.unit_instance_id,
                source_model_instance_id=source_model_id,
                selection_clause=selection_clause,
                explicit_target_unit_ids=hit_target_ids,
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
                phase=BattlePhase.FIGHT,
                hook_id=CATALOG_IR_POST_FIGHT_HIT_TARGET_EFFECT_CONSUMER_ID,
                submission_kind=SELECT_CATALOG_POST_FIGHT_HIT_TARGET_EFFECT_SUBMISSION_KIND,
                attack_sequence=attack_sequence,
                attack_sequence_completed_event_id=attack_sequence_completed_event_id,
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
                        phase=BattlePhase.FIGHT,
                        hook_id=CATALOG_IR_POST_FIGHT_HIT_TARGET_EFFECT_CONSUMER_ID,
                        submission_kind=(
                            SELECT_CATALOG_POST_FIGHT_HIT_TARGET_EFFECT_SUBMISSION_KIND
                        ),
                        attack_sequence=attack_sequence,
                        attack_sequence_completed_event_id=attack_sequence_completed_event_id,
                    )
                )
    return tuple(groups)
