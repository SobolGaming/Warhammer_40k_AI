from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import TYPE_CHECKING, TypedDict, cast

from warhammer40k_core.engine.event_log import JsonValue, validate_json_value

if TYPE_CHECKING:
    from warhammer40k_core.engine.faction_content.bundle import RuntimeContentBundle


class RuntimeContentBundleSummaryPayload(TypedDict):
    activation: dict[str, JsonValue]
    selected_module_paths: list[str]
    source_package_ids: list[str]
    source_package_hashes: list[str]
    contribution_ids: list[str]
    ability_index_record_ids_by_player_id: dict[str, list[str]]
    stratagem_index_record_ids_by_player_id: dict[str, list[str]]
    ability_handler_ids: list[str]
    stratagem_handler_ids: list[str]
    rule_runtime_binding_ids: list[str]
    event_subscriptions: list[dict[str, JsonValue]]
    battle_formation_hook_ids: list[str]
    battle_round_start_hook_ids: list[str]
    turn_end_hook_ids: list[str]
    command_phase_start_hook_ids: list[str]
    fight_phase_start_hook_ids: list[str]
    fight_phase_end_hook_ids: list[str]
    shooting_phase_start_hook_ids: list[str]
    unit_destroyed_hook_ids: list[str]
    battle_shock_hook_ids: list[str]
    advance_eligibility_hook_ids: list[str]
    advance_move_hook_ids: list[str]
    fall_back_hook_ids: list[str]
    movement_end_surge_hook_ids: list[str]
    reserve_arrival_distance_hook_ids: list[str]
    reserve_arrival_restriction_hook_ids: list[str]
    unit_move_completed_mortal_wound_hook_ids: list[str]
    unit_move_completed_battle_shock_hook_ids: list[str]
    mortal_wound_feel_no_pain_hook_ids: list[str]
    charge_declaration_hook_ids: list[str]
    shooting_target_restriction_hook_ids: list[str]
    charge_target_restriction_hook_ids: list[str]
    shooting_unit_selected_hook_ids: list[str]
    shooting_unit_selected_grant_hook_ids: list[str]
    attack_sequence_completed_hook_ids: list[str]
    shooting_end_surge_hook_ids: list[str]
    enhancement_effect_binding_ids: list[str]
    fight_activation_ability_hook_ids: list[str]
    fight_unit_selected_hook_ids: list[str]
    fight_unit_selected_grant_hook_ids: list[str]
    phase_end_objective_control_hook_ids: list[str]
    stratagem_cost_choice_hook_ids: list[str]
    stratagem_cost_modifier_ids: list[str]
    unit_characteristic_modifier_ids: list[str]
    hit_roll_modifier_ids: list[str]
    wound_roll_modifier_ids: list[str]
    save_option_modifier_ids: list[str]
    movement_budget_modifier_ids: list[str]
    objective_control_modifier_ids: list[str]
    advance_roll_modifier_ids: list[str]
    charge_roll_modifier_ids: list[str]
    weapon_profile_modifier_ids: list[str]
    faction_execution_record_ids: list[str]
    selected_execution_record_ids: list[str]
    bundle_summary_hash: str


def runtime_content_bundle_summary_payload(
    bundle: RuntimeContentBundle,
    *,
    summary_hash: Callable[[Mapping[str, JsonValue]], str],
) -> RuntimeContentBundleSummaryPayload:
    payload = {
        "activation": cast(
            dict[str, JsonValue], validate_json_value(bundle.activation.to_payload())
        ),
        "selected_module_paths": list(bundle.activation.selected_module_paths),
        "source_package_ids": list(bundle.activation.source_package_ids),
        "source_package_hashes": list(bundle.activation.source_package_hashes),
        "contribution_ids": list(bundle.contribution_ids),
        "ability_index_record_ids_by_player_id": {
            player_id: [record.record_id for record in index.all_records()]
            for player_id, index in bundle.ability_indexes_by_player_id.items()
        },
        "stratagem_index_record_ids_by_player_id": {
            player_id: [record.record_id for record in index.all_records()]
            for player_id, index in bundle.stratagem_indexes_by_player_id.items()
        },
        "ability_handler_ids": [
            binding.handler_id for binding in bundle.ability_handler_registry.all_bindings()
        ],
        "stratagem_handler_ids": [
            binding.handler_id for binding in bundle.stratagem_handler_registry.all_bindings()
        ],
        "rule_runtime_binding_ids": [
            binding.binding_id for binding in bundle.rule_execution_registry.all_bindings()
        ],
        "event_subscriptions": bundle.event_index.to_summary_payload(),
        "battle_formation_hook_ids": [
            binding.hook_id for binding in bundle.battle_formation_hook_registry.all_bindings()
        ],
        "battle_round_start_hook_ids": [
            binding.hook_id for binding in bundle.battle_round_start_hook_registry.all_bindings()
        ],
        "turn_end_hook_ids": [
            binding.hook_id for binding in bundle.turn_end_hook_registry.all_bindings()
        ],
        "command_phase_start_hook_ids": [
            binding.hook_id for binding in bundle.command_phase_start_hook_registry.all_bindings()
        ],
        "fight_phase_start_hook_ids": [
            binding.hook_id for binding in bundle.fight_phase_start_hook_registry.all_bindings()
        ],
        "fight_phase_end_hook_ids": [
            binding.hook_id for binding in bundle.fight_phase_end_hook_registry.all_bindings()
        ],
        "shooting_phase_start_hook_ids": [
            binding.hook_id for binding in bundle.shooting_phase_start_hook_registry.all_bindings()
        ],
        "unit_destroyed_hook_ids": [
            binding.hook_id for binding in bundle.unit_destroyed_hook_registry.all_bindings()
        ],
        "battle_shock_hook_ids": [
            binding.hook_id for binding in bundle.battle_shock_hook_registry.all_bindings()
        ],
        "advance_eligibility_hook_ids": [
            binding.hook_id for binding in bundle.advance_eligibility_hook_registry.all_bindings()
        ],
        "advance_move_hook_ids": [
            binding.hook_id for binding in bundle.advance_move_hook_registry.all_bindings()
        ],
        "fall_back_hook_ids": [
            binding.hook_id for binding in bundle.fall_back_hook_registry.all_bindings()
        ],
        "movement_end_surge_hook_ids": [
            binding.hook_id for binding in bundle.movement_end_surge_hook_registry.all_bindings()
        ],
        "reserve_arrival_distance_hook_ids": [
            binding.hook_id
            for binding in bundle.reserve_arrival_distance_hook_registry.all_bindings()
        ],
        "reserve_arrival_restriction_hook_ids": [
            binding.hook_id
            for binding in bundle.reserve_arrival_restriction_hook_registry.all_bindings()
        ],
        "unit_move_completed_mortal_wound_hook_ids": [
            binding.hook_id
            for binding in (bundle.unit_move_completed_mortal_wound_hook_registry.all_bindings())
        ],
        "unit_move_completed_battle_shock_hook_ids": [
            binding.hook_id
            for binding in (bundle.unit_move_completed_battle_shock_hook_registry.all_bindings())
        ],
        "mortal_wound_feel_no_pain_hook_ids": [
            binding.hook_id
            for binding in bundle.mortal_wound_feel_no_pain_hook_registry.all_bindings()
        ],
        "charge_declaration_hook_ids": [
            binding.hook_id for binding in bundle.charge_declaration_hook_registry.all_bindings()
        ],
        "shooting_target_restriction_hook_ids": [
            binding.hook_id
            for binding in bundle.shooting_target_restriction_hook_registry.all_bindings()
        ],
        "charge_target_restriction_hook_ids": [
            binding.hook_id
            for binding in bundle.charge_target_restriction_hook_registry.all_bindings()
        ],
        "shooting_unit_selected_hook_ids": [
            binding.hook_id
            for binding in bundle.shooting_unit_selected_hook_registry.all_bindings()
        ],
        "shooting_unit_selected_grant_hook_ids": [
            binding.hook_id
            for binding in bundle.shooting_unit_selected_grant_hook_registry.all_bindings()
        ],
        "attack_sequence_completed_hook_ids": [
            binding.hook_id
            for binding in bundle.attack_sequence_completed_hook_registry.all_bindings()
        ],
        "shooting_end_surge_hook_ids": [
            binding.hook_id for binding in bundle.shooting_end_surge_hook_registry.all_bindings()
        ],
        "enhancement_effect_binding_ids": [
            binding.effect_id for binding in bundle.enhancement_effect_registry.all_bindings()
        ],
        "fight_activation_ability_hook_ids": [
            binding.hook_id
            for binding in bundle.fight_activation_ability_hook_registry.all_bindings()
        ],
        "fight_unit_selected_hook_ids": [
            binding.hook_id for binding in bundle.fight_unit_selected_hook_registry.all_bindings()
        ],
        "fight_unit_selected_grant_hook_ids": [
            binding.hook_id
            for binding in bundle.fight_unit_selected_grant_hook_registry.all_bindings()
        ],
        "phase_end_objective_control_hook_ids": [
            binding.hook_id
            for binding in bundle.phase_end_objective_control_hook_registry.all_bindings()
        ],
        "stratagem_cost_choice_hook_ids": [
            binding.hook_id for binding in bundle.stratagem_cost_choice_hook_registry.all_bindings()
        ],
        "stratagem_cost_modifier_ids": [
            binding.modifier_id
            for binding in bundle.stratagem_cost_modifier_registry.all_bindings()
        ],
        "unit_characteristic_modifier_ids": [
            binding.modifier_id
            for binding in bundle.runtime_modifier_registry.all_unit_characteristic_bindings()
        ],
        "hit_roll_modifier_ids": [
            binding.modifier_id
            for binding in bundle.runtime_modifier_registry.all_hit_roll_bindings()
        ],
        "wound_roll_modifier_ids": [
            binding.modifier_id
            for binding in bundle.runtime_modifier_registry.all_wound_roll_bindings()
        ],
        "save_option_modifier_ids": [
            binding.modifier_id
            for binding in bundle.runtime_modifier_registry.all_save_option_bindings()
        ],
        "movement_budget_modifier_ids": [
            binding.modifier_id
            for binding in bundle.runtime_modifier_registry.all_movement_budget_bindings()
        ],
        "objective_control_modifier_ids": [
            binding.modifier_id
            for binding in bundle.runtime_modifier_registry.all_objective_control_bindings()
        ],
        "advance_roll_modifier_ids": [
            binding.modifier_id
            for binding in bundle.runtime_modifier_registry.all_advance_roll_bindings()
        ],
        "charge_roll_modifier_ids": [
            binding.modifier_id
            for binding in bundle.runtime_modifier_registry.all_charge_roll_bindings()
        ],
        "weapon_profile_modifier_ids": [
            binding.modifier_id
            for binding in bundle.runtime_modifier_registry.all_weapon_profile_bindings()
        ],
        "faction_execution_record_ids": [
            record.execution_id for record in bundle.faction_rule_execution_registry.all_records()
        ],
        "selected_execution_record_ids": list(bundle.activation.selected_execution_record_ids),
        "bundle_summary_hash": "",
    }
    payload["bundle_summary_hash"] = summary_hash(
        cast(Mapping[str, JsonValue], validate_json_value(payload))
    )
    return cast(RuntimeContentBundleSummaryPayload, validate_json_value(payload))
