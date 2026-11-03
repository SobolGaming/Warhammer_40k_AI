# pyright: reportPrivateUsage=false
"""Selected-hit target candidates at authenticated model or unit completion."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState

from warhammer40k_core.engine.abilities import AbilityCatalogIndex, AbilityCatalogRecord
from warhammer40k_core.engine.army_mustering import ArmyDefinition
from warhammer40k_core.engine.attack_sequence_completion_hooks import (
    successful_hit_target_unit_ids_for_sequence,
)
from warhammer40k_core.engine.attack_sequence_state import AttackSequence
from warhammer40k_core.engine.catalog_rule_consumption import (
    CATALOG_IR_POST_SHOOT_HIT_TARGET_EFFECT_CONSUMER_ID,
)
from warhammer40k_core.engine.catalog_selected_target_decisions import (
    SelectedTargetGroup as _SelectedTargetGroup,
)
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.model_shooting_completion import (
    model_completion_boundary,
    source_model_completion_event_id,
)
from warhammer40k_core.engine.phase import BattlePhase
from warhammer40k_core.engine.unit_factory import UnitInstance


def post_shoot_groups_for_record(
    *,
    state: GameState,
    decisions: DecisionController,
    army: ArmyDefinition,
    unit: UnitInstance,
    current_model_instance_ids: tuple[str, ...],
    record: AbilityCatalogRecord,
    attack_sequence: AttackSequence,
    attack_sequence_completed_event_id: str,
    completed_model_instance_ids: tuple[str, ...] | None = None,
) -> tuple[_SelectedTargetGroup, ...]:
    from warhammer40k_core.engine import catalog_selected_target_effects as owner
    from warhammer40k_core.engine import catalog_selected_target_effects_support as support

    clauses = support.catalog_selected_target_clauses_from_record(record)
    runtime_clause_id = support.runtime_clause_id_from_record(record)
    groups: list[_SelectedTargetGroup] = []
    for index, selection_clause in enumerate(clauses):
        if runtime_clause_id is not None and runtime_clause_id != selection_clause.clause_id:
            continue
        if not support.clause_is_post_shoot_hit_target_selection(selection_clause):
            continue
        model_subject = support.selection_subject(selection_clause) in {"this_model", "bearer"}
        if model_subject and state.current_battle_phase is not BattlePhase.SHOOTING:
            continue
        if completed_model_instance_ids is not None and not model_subject:
            continue
        effect_clauses = support.post_shoot_selected_target_effect_clauses_after(clauses, index)
        if not effect_clauses:
            continue
        for source_model_id in support.selection_source_model_ids_for_record(
            record, unit, selection_clause, effect_clauses, current_model_instance_ids
        ):
            source_sequence = attack_sequence
            source_event_id = attack_sequence_completed_event_id
            if model_subject:
                if source_model_id is None or (
                    completed_model_instance_ids is not None
                    and source_model_id not in completed_model_instance_ids
                ):
                    continue
                model_event_id = source_model_completion_event_id(
                    decisions.event_log.records,
                    sequence_id=attack_sequence.sequence_id,
                    model_id=source_model_id,
                )
                if model_event_id is None:
                    continue
                source_sequence, _, _ = model_completion_boundary(
                    decisions.event_log.records, model_event_id
                )
                source_event_id = model_event_id
            hit_target_ids = successful_hit_target_unit_ids_for_sequence(
                decisions=decisions,
                sequence=source_sequence,
                attacker_model_instance_id=(
                    None
                    if support.selection_subject(selection_clause) == "this_models_unit"
                    else source_model_id
                ),
                weapon_names=support.selection_weapon_names(selection_clause),
            )
            if not hit_target_ids:
                continue
            target_ids = support.eligible_selection_target_unit_ids(
                state=state,
                source_player_id=army.player_id,
                source_unit_instance_id=unit.unit_instance_id,
                source_model_instance_id=source_model_id,
                selection_clause=selection_clause,
                explicit_target_unit_ids=hit_target_ids,
            )
            target_ids = owner.post_shoot_target_ids_allowed_by_frequency(
                state=state,
                decisions=decisions,
                record=record,
                selection_clause=selection_clause,
                target_unit_instance_ids=target_ids,
            )
            options = owner.options_for_targets(
                state=state,
                record=record,
                player_id=army.player_id,
                unit=unit,
                source_model_instance_id=source_model_id,
                selection_clause=selection_clause,
                effect_clauses=effect_clauses,
                selected_target_unit_ids=target_ids,
                phase=BattlePhase.SHOOTING,
                hook_id=CATALOG_IR_POST_SHOOT_HIT_TARGET_EFFECT_CONSUMER_ID,
                submission_kind=owner.SELECT_CATALOG_POST_SHOOT_HIT_TARGET_EFFECT_SUBMISSION_KIND,
                attack_sequence=source_sequence,
                attack_sequence_completed_event_id=source_event_id,
            )
            if options:
                groups.append(
                    _SelectedTargetGroup(
                        record=record,
                        player_id=army.player_id,
                        unit=unit,
                        source_model_instance_id=source_model_id,
                        selection_clause=selection_clause,
                        effect_clauses=effect_clauses,
                        options=options,
                        phase=BattlePhase.SHOOTING,
                        hook_id=CATALOG_IR_POST_SHOOT_HIT_TARGET_EFFECT_CONSUMER_ID,
                        submission_kind=(
                            owner.SELECT_CATALOG_POST_SHOOT_HIT_TARGET_EFFECT_SUBMISSION_KIND
                        ),
                        optional=support.post_shoot_target_selection_is_optional(selection_clause),
                        attack_sequence=source_sequence,
                        attack_sequence_completed_event_id=source_event_id,
                    )
                )
    return tuple(groups)


def model_shooting_boundary_sources(
    *,
    state: GameState,
    sequence: AttackSequence,
    model_id: str,
    ability_index: AbilityCatalogIndex,
) -> tuple[str, ...]:
    from warhammer40k_core.engine.ability_presence import active_ability_model_ids_for_unit
    from warhammer40k_core.engine.catalog_selected_target_effects_support import (
        catalog_selected_target_clauses_from_record,
        clause_is_post_shoot_hit_target_selection,
        post_shoot_selected_target_effect_clauses_after,
        selection_source_model_ids_for_record,
        selection_subject,
        unit_scoped_generic_records_for_timing,
    )
    from warhammer40k_core.engine.rules_units import rules_unit_view_by_id
    from warhammer40k_core.engine.timing_windows import TimingTriggerKind

    if (
        state.current_battle_phase is not BattlePhase.SHOOTING
        or sequence.source_phase is not BattlePhase.SHOOTING
        or sequence.attacker_player_id != state.active_player_id
    ):
        return ()
    view = rules_unit_view_by_id(state=state, unit_instance_id=sequence.attacking_unit_instance_id)
    source_ids: set[str] = set()
    for component in view.components:
        unit = component.unit
        ids = active_ability_model_ids_for_unit(state=state, unit=unit)
        if model_id not in ids:
            continue
        for record in unit_scoped_generic_records_for_timing(
            ability_index=ability_index,
            unit=unit,
            current_model_instance_ids=ids,
            trigger_kind=TimingTriggerKind.JUST_AFTER_FRIENDLY_UNIT_HAS_SHOT,
        ):
            clauses = catalog_selected_target_clauses_from_record(record)
            for i, clause in enumerate(clauses):
                if not clause_is_post_shoot_hit_target_selection(clause) or selection_subject(
                    clause
                ) not in {"this_model", "bearer"}:
                    continue
                effects = post_shoot_selected_target_effect_clauses_after(clauses, i)
                if effects and model_id in selection_source_model_ids_for_record(
                    record, unit, clause, effects, ids
                ):
                    source_ids.add(clause.clause_id)
    return tuple(sorted(source_ids))
