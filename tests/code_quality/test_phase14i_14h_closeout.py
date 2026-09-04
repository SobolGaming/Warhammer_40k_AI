from __future__ import annotations

import ast
from pathlib import Path

from tests.code_quality.source_index import (
    ast_for,
    combined_source_for,
    function_source_for,
    source_for,
)
from warhammer40k_core.rules.source_packages.warhammer_40000_11th.core_abilities import (
    ability_rows,
)
from warhammer40k_core.rules.source_packages.warhammer_40000_11th.core_stratagems import (
    core_stratagem_rows,
)

ROOT = Path(__file__).resolve().parents[2]
ENGINE_ROOT = ROOT / "src" / "warhammer40k_core" / "engine"
ARCHITECTURE_PATH = ROOT / "ARCHITECTURE_V2.md"
README_PATH = ROOT / "README.md"
TRANSPORTS_PATH = ROOT / "src" / "warhammer40k_core" / "engine" / "transports.py"
EMERGENCY_DISEMBARK_PATH = ROOT / "src" / "warhammer40k_core" / "engine" / "emergency_disembark.py"
ASSAULT_DISEMBARK_PATH = ROOT / "src" / "warhammer40k_core" / "engine" / "assault_disembark.py"
SHOCK_DISEMBARK_PATH = ROOT / "src" / "warhammer40k_core" / "engine" / "shock_disembark.py"
TRANSPORT_DISEMBARK_PERMISSIONS_PATH = (
    ROOT / "src" / "warhammer40k_core" / "engine" / "transport_disembark_permissions.py"
)
TRANSPORT_DISEMBARK_STATE_PATH = (
    ROOT / "src" / "warhammer40k_core" / "engine" / "transport_disembark_state.py"
)
MOVEMENT_TRANSPORTS_PATH = (
    ROOT / "src" / "warhammer40k_core" / "engine" / "phases" / "movement_transports.py"
)
MOVEMENT_PROPOSALS_PATH = ROOT / "src" / "warhammer40k_core" / "engine" / "movement_proposals.py"
MOVEMENT_PLACEMENT_PROPOSALS_PATH = (
    ROOT / "src" / "warhammer40k_core" / "engine" / "phases" / "movement_placement_proposals.py"
)
FIGHT_ORDER_PATH = ROOT / "src" / "warhammer40k_core" / "engine" / "fight_order.py"
FIGHT_PHASE_PATH = ROOT / "src" / "warhammer40k_core" / "engine" / "phases" / "fight.py"
FIGHT_UNIT_SELECTED_HOOKS_PATH = (
    ROOT / "src" / "warhammer40k_core" / "engine" / "fight_unit_selected_hooks.py"
)
LIFECYCLE_PATH = ROOT / "src" / "warhammer40k_core" / "engine" / "lifecycle.py"
CHARGE_PHASE_PATH = ROOT / "src" / "warhammer40k_core" / "engine" / "phases" / "charge.py"
DESTROYED_TRANSPORT_RULES_UNIT_DISEMBARK_PATH = (
    ROOT / "src" / "warhammer40k_core" / "engine" / "destroyed_transport_rules_unit_disembark.py"
)
RULE_MODEL_DESTRUCTION_UNPLACED_PATH = (
    ROOT / "src" / "warhammer40k_core" / "engine" / "rule_model_destruction_unplaced.py"
)
DESTROYED_TRANSPORT_PENDING_PATH = (
    ROOT / "src" / "warhammer40k_core" / "engine" / "destroyed_transport_pending.py"
)
ATTACK_SEQUENCE_PATH = ROOT / "src" / "warhammer40k_core" / "engine" / "attack_sequence.py"
ATTACK_SEQUENCE_SPLIT_PATHS = tuple(sorted(ATTACK_SEQUENCE_PATH.parent.glob("attack_sequence*.py")))
DAMAGE_ALLOCATION_PATH = ROOT / "src" / "warhammer40k_core" / "engine" / "damage_allocation.py"
HAZARD_PATH = ROOT / "src" / "warhammer40k_core" / "engine" / "hazard.py"
GAME_STATE_PATH = ROOT / "src" / "warhammer40k_core" / "engine" / "game_state.py"
LIFECYCLE_STATE_VALIDATION_PATH = (
    ROOT / "src" / "warhammer40k_core" / "engine" / "lifecycle_state_validation.py"
)
UNIT_MOVE_COMPLETED_HOOKS_PATH = (
    ROOT / "src" / "warhammer40k_core" / "engine" / "unit_move_completed_hooks.py"
)
UNIT_STATE_PATH = ROOT / "src" / "warhammer40k_core" / "engine" / "unit_state.py"
HEALING_PATH = ROOT / "src" / "warhammer40k_core" / "engine" / "healing.py"
HEALING_REVIVAL_PATH = ROOT / "src" / "warhammer40k_core" / "engine" / "healing_revival.py"
MORTAL_WOUND_TARGET_LINEAGE_PATH = (
    ROOT / "src" / "warhammer40k_core" / "engine" / "mortal_wound_target_lineage.py"
)
FIGHT_MODEL_AUTHORITY_HISTORY_PATH = (
    ROOT / "src" / "warhammer40k_core" / "engine" / "fight_model_authority_history.py"
)
DATASHEET_PATH = ROOT / "src" / "warhammer40k_core" / "core" / "datasheet.py"
ATTACHMENT_ELIGIBILITY_PATH = (
    ROOT / "src" / "warhammer40k_core" / "core" / "attachment_eligibility.py"
)
LIST_VALIDATION_PATH = ROOT / "src" / "warhammer40k_core" / "engine" / "list_validation.py"
ARMY_MUSTERING_PATH = ROOT / "src" / "warhammer40k_core" / "engine" / "army_mustering.py"
ATTACHED_UNIT_FORMATION_PATH = (
    ROOT / "src" / "warhammer40k_core" / "engine" / "attached_unit_formation.py"
)
STRATAGEMS_PATH = ROOT / "src" / "warhammer40k_core" / "engine" / "stratagems.py"
STRATAGEMS_SPLIT_PATHS = tuple(sorted(STRATAGEMS_PATH.parent.glob("stratagems*.py")))
SHOOTING_PHASE_PATH = ROOT / "src" / "warhammer40k_core" / "engine" / "phases" / "shooting.py"
SHOOTING_PHASE_SPLIT_PATHS = tuple(sorted(SHOOTING_PHASE_PATH.parent.glob("shooting*.py")))
ADAPTER_CONTRACT_PATH = ROOT / "docs" / "ADAPTER_DECISION_CONTRACT.md"
PHASE_USE_EXCEPTION_MODULE = "warhammer40k_core.engine.stratagem_phase_use_exceptions"


def _attack_sequence_source() -> str:
    return combined_source_for(ATTACK_SEQUENCE_SPLIT_PATHS)


def _stratagems_source() -> str:
    return combined_source_for(STRATAGEMS_SPLIT_PATHS)


def _phase_exception_imports(tree: ast.Module) -> tuple[set[str], set[str]]:
    direct_symbols: set[str] = set()
    module_aliases: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == PHASE_USE_EXCEPTION_MODULE:
            direct_symbols.update(alias.asname or alias.name for alias in node.names)
        elif isinstance(node, ast.Import):
            module_aliases.update(
                alias.asname or alias.name.rsplit(".", maxsplit=1)[-1]
                for alias in node.names
                if alias.name == PHASE_USE_EXCEPTION_MODULE
            )
    return direct_symbols, module_aliases


def _called_symbol_name(call: ast.Call) -> str | None:
    if isinstance(call.func, ast.Name):
        return call.func.id
    if isinstance(call.func, ast.Attribute):
        return call.func.attr
    return None


def _call_uses_phase_exception_import(
    call: ast.Call,
    *,
    direct_symbols: set[str],
    module_aliases: set[str],
) -> bool:
    if isinstance(call.func, ast.Name):
        return call.func.id in direct_symbols
    return (
        isinstance(call.func, ast.Attribute)
        and isinstance(call.func.value, ast.Name)
        and call.func.value.id in module_aliases
    )


def test_phase14i_core_stratagem_source_cutover_is_complete() -> None:
    rows = core_stratagem_rows()
    expected_stratagem_ids = {
        "command-reroll",
        "counteroffensive",
        "crushing-impact",
        "epic-challenge",
        "explosives",
        "fire-overwatch",
        "heroic-intervention",
        "insane-bravery",
        "new-orders",
        "rapid-ingress",
        "smokescreen",
    }

    assert {row.stratagem_id for row in rows} == expected_stratagem_ids
    assert [row.stratagem_id for row in rows if row.handler_id.startswith("unsupported:")] == []


def test_phase14i_core_stratagem_timing_hosts_do_not_roster_gate_on_phase_exceptions() -> None:
    offenders: list[str] = []
    audited_host_count = 0
    for path in sorted(ENGINE_ROOT.rglob("*.py"), key=lambda item: item.as_posix()):
        tree = ast_for(path)
        direct_exception_symbols, exception_module_aliases = _phase_exception_imports(tree)
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            calls = tuple(child for child in ast.walk(node) if isinstance(child, ast.Call))
            if not any(
                _called_symbol_name(call) == "stratagem_target_proposal_from_index"
                for call in calls
            ):
                continue
            audited_host_count += 1
            for call in calls:
                called_symbol = _called_symbol_name(call)
                if (
                    called_symbol is not None and "phase_use_exception" in called_symbol
                ) or _call_uses_phase_exception_import(
                    call,
                    direct_symbols=direct_exception_symbols,
                    module_aliases=exception_module_aliases,
                ):
                    offenders.append(
                        f"{path.relative_to(ROOT).as_posix()}:{node.name}:{call.lineno}"
                    )

    assert audited_host_count > 0
    assert offenders == []


def test_phase14i_core_ability_source_rows_have_no_unsupported_handlers() -> None:
    unsupported_rows = tuple(
        row for row in ability_rows() if row.handler_id.startswith("unsupported:")
    )

    assert tuple((row.ability_id, row.handler_id) for row in unsupported_rows) == ()


def test_phase14i_docs_mark_complete_without_overclaiming_ability_runtime() -> None:
    architecture = source_for(ARCHITECTURE_PATH)
    readme = source_for(README_PATH)
    phase14i_section = architecture.split("## Phase 14I:", maxsplit=1)[1].split(
        "\n## ",
        maxsplit=1,
    )[0]

    assert "Status: Complete." in phase14i_section
    assert "Phase 14I is complete" in architecture
    assert "Phase 14I is complete" in readme
    assert "explicit unsupported" in phase14i_section
    assert "descriptors with owning phase IDs" in phase14i_section
    assert "future ability-runtime families" in phase14i_section
    assert "runtime effects complete" in phase14i_section
    assert "STEALTH grants Benefit of Cover against ranged attacks" not in phase14i_section
    assert "[PSYCHIC] modifier-ignore submissions" not in phase14i_section
    assert "[ONE SHOT] first weapon selection is legal" not in phase14i_section
    assert "Super-heavy Walker movement is offered" not in phase14i_section


def test_phase14h_transport_blocker_and_attached_toughness_cutover_are_explicit() -> None:
    transport_source = source_for(TRANSPORTS_PATH)
    attack_sequence_source = _attack_sequence_source()
    damage_allocation_source = source_for(DAMAGE_ALLOCATION_PATH)
    hazard_source = source_for(HAZARD_PATH)
    game_state_source = source_for(GAME_STATE_PATH)
    unit_state_source = source_for(UNIT_STATE_PATH)
    healing_source = source_for(HEALING_PATH)
    healing_revival_source = source_for(HEALING_REVIVAL_PATH)
    datasheet_source = source_for(DATASHEET_PATH)
    attachment_eligibility_source = source_for(ATTACHMENT_ELIGIBILITY_PATH)
    list_validation_source = source_for(LIST_VALIDATION_PATH)
    army_mustering_source = source_for(ARMY_MUSTERING_PATH)
    attached_unit_formation_source = source_for(ATTACHED_UNIT_FORMATION_PATH)
    stratagems_source = _stratagems_source()

    assert "def resolve_combat_disembark(" in transport_source
    assert "Combat Disembark requires resolve_combat_disembark." in transport_source
    assert "combat_disembark.hazard_roll" in transport_source
    assert "apply_transport_hazard_mortal_wounds" in transport_source
    assert "transport_hazard_mortal_wounds" in transport_source
    assert "HAZARD_ROLL_FAILURE_THRESHOLD = 2" in hazard_source
    assert "hazard_mortal_wounds_per_failed_roll" in attack_sequence_source
    assert "pending_destroyed_transport_disembark" in attack_sequence_source
    assert "destroyed_transport_disembark_placement_requested" in attack_sequence_source
    assert "apply_destroyed_transport_disembark_proposal_decision" in attack_sequence_source
    assert "remove_transport_cargo_state" in game_state_source
    assert "def add_unit_to_army(" in game_state_source
    assert "def apply_strategic_reserve_declarations(" in game_state_source
    assert "def declare_battle_formation_embarkation(" in game_state_source
    assert "def reposition_unit_to_strategic_reserves(" in game_state_source
    assert "is_at_half_strength" in unit_state_source
    assert "attached_unit_bodyguard_model_ids" in attack_sequence_source
    assert "_highest_toughness_for_models" in attack_sequence_source
    assert '"attached-role:leader" in model.source_ids' in damage_allocation_source
    assert '"attached-role:support" in model.source_ids' in damage_allocation_source
    assert "SELECT_HEALING_MODEL_DECISION_TYPE" in healing_source
    assert "resolve_healing_until_blocked" in healing_source
    assert "apply_healing_model_decision" in healing_source
    assert "with_returned_model_placement" in healing_revival_source
    assert "phase_start_enemy_engagement_model_ids" in healing_source
    assert "attachment_eligibilities" in datasheet_source
    assert "class AttachmentEligibility" in attachment_eligibility_source
    assert "class AttachmentDeclaration" in list_validation_source
    assert "class AttachedUnitFormation" in attached_unit_formation_source
    assert "def _resolve_attached_unit_formations(" in army_mustering_source
    assert "def _validate_required_support_attachments(" in army_mustering_source
    assert (
        "Support units must be declared as part of an attached unit during mustering."
        in army_mustering_source
    )
    assert "AttachmentRole.LEADER" in army_mustering_source
    assert "AttachmentRole.SUPPORT" in army_mustering_source
    assert '"runtime-attached-unit:{role}"' in army_mustering_source
    assert "def _starting_strength_records_for_army(" in game_state_source
    assert "def _starting_strength_record_for_attached_unit(" in game_state_source
    assert "def _remove_attached_unit_formation(" not in game_state_source
    assert "attached_unit.component_unit_instance_ids" in stratagems_source


def test_p18c_emergency_disembark_resolves_hazard_before_survivor_placement() -> None:
    transport_source = source_for(TRANSPORTS_PATH)
    destroyed_transport_source = source_for(ENGINE_ROOT / "attack_sequence_destroyed_transport.py")
    lineage_source = source_for(MORTAL_WOUND_TARGET_LINEAGE_PATH)
    authority_history_source = source_for(FIGHT_MODEL_AUTHORITY_HISTORY_PATH)
    continuation_source = function_source_for(
        ATTACK_SEQUENCE_SPLIT_PATHS,
        "_continue_pending_destroyed_transport_disembark",
    )
    placement_request_source = function_source_for(
        ATTACK_SEQUENCE_SPLIT_PATHS,
        "_request_destroyed_transport_disembark_placement",
    )
    placement_resolution_source = function_source_for(
        ATTACK_SEQUENCE_SPLIT_PATHS,
        "_resolve_destroyed_transport_disembark_submission",
    )
    transport_resolution_source = function_source_for(
        (TRANSPORTS_PATH,),
        "resolve_destroyed_transport_disembark",
    )
    transport_resolution_service_source = function_source_for(
        (EMERGENCY_DISEMBARK_PATH,),
        "resolve_destroyed_transport_disembark_service",
    )
    grouped_disembark_source = source_for(DESTROYED_TRANSPORT_RULES_UNIT_DISEMBARK_PATH)
    omitted_destruction_source = function_source_for(
        (RULE_MODEL_DESTRUCTION_UNPLACED_PATH,),
        "_destroy_emergency_disembark_omitted_models",
    )
    pending_validation_source = function_source_for(
        (DESTROYED_TRANSPORT_PENDING_PATH,),
        "validate_pending_destroyed_transport_disembark",
    )

    assert continuation_source.index("resolve_destroyed_transport_rules_unit_hazard_rolls") < (
        continuation_source.index("_request_destroyed_transport_disembark_placement")
    )
    assert continuation_source.index("apply_transport_hazard_mortal_wounds") < (
        continuation_source.index("_request_destroyed_transport_disembark_placement")
    )
    assert "current_hazard_surviving_model_instance_ids" in continuation_source
    assert "rules_unit_view_by_id" in continuation_source
    assert "completed hazard survivors" in placement_request_source
    assert '"surviving_model_instance_ids"' in placement_request_source
    assert '"hazard_rolls"' in placement_request_source
    assert "survivor_id_set" in placement_resolution_source
    assert "hazard_rolls=component_hazard_rolls" in placement_resolution_source
    assert "submission.resolved_rules_unit_placement()" in placement_resolution_source
    assert "resolve_destroyed_transport_rules_unit_disembark" in placement_resolution_source
    assert "RulesUnitPlacement" in grouped_disembark_source
    assert "apply_rules_unit_disembark_to_battlefield" in grouped_disembark_source
    assert "DESTROYED_TRANSPORT_RULES_UNIT_DISEMBARK_EVENT_FIELD" in grouped_disembark_source
    assert "for component_id in hazard_rolls.component_unit_instance_ids" in (
        grouped_disembark_source
    )
    assert "rules_unit_contains_component_lineage" in grouped_disembark_source
    assert "if updated_cargo.contains_unit(component_id)" in grouped_disembark_source
    assert "rules_unit_contains_component_lineage" in destroyed_transport_source
    assert "rules_unit_contains_component_lineage" in omitted_destruction_source
    assert "survivor_component_ids" in omitted_destruction_source
    assert "for component_id in survivor_component_ids" in omitted_destruction_source
    assert "_current_hazard_component_survivor_ids" not in destroyed_transport_source
    assert "retain_current_hazard=" not in destroyed_transport_source
    assert '"pending_unit_instance_ids"' in pending_validation_source
    assert "_validate_ordered_identifier_tuple(" in pending_validation_source
    assert "dice_manager" not in transport_resolution_source
    assert "pre-placement hazard rolls" in transport_resolution_service_source
    assert "FROZEN_EMBARKED_RULES_UNIT_COMPONENTS_POLICY" in lineage_source
    assert "TRANSPORT_HAZARD_MORTAL_WOUNDS_EVENT_TYPE" in authority_history_source
    assert "EMERGENCY_DISEMBARK_MOVE_SOURCE_ID" in transport_source


def test_p18d_assault_disembark_is_source_bound_grouped_and_adapter_authoritative() -> None:
    transport_source = source_for(TRANSPORTS_PATH)
    disembark_state_source = source_for(TRANSPORT_DISEMBARK_STATE_PATH)
    permission_source = source_for(ASSAULT_DISEMBARK_PATH)
    shared_permission_source = source_for(TRANSPORT_DISEMBARK_PERMISSIONS_PATH)
    candidate_source = function_source_for(
        (MOVEMENT_TRANSPORTS_PATH,),
        "_disembark_candidate_for_movement_unit",
    )
    proposal_validation_source = source_for(MOVEMENT_PROPOSALS_PATH)
    charge_eligibility_source = function_source_for(
        (CHARGE_PHASE_PATH,),
        "_charge_unit_ineligibility_reason",
    )
    adapter_contract = source_for(ADAPTER_CONTRACT_PATH)
    turn_cleanup_source = source_for(GAME_STATE_PATH)
    restore_integrity_source = function_source_for(
        (LIFECYCLE_STATE_VALIDATION_PATH,),
        "_validate_disembarked_unit_state_history",
    )
    move_completed_owner_source = function_source_for(
        (UNIT_MOVE_COMPLETED_HOOKS_PATH,),
        "_triggering_player_id_from_move_completion_payload",
    )
    mortal_wound_hook_source = function_source_for(
        (UNIT_MOVE_COMPLETED_HOOKS_PATH,),
        "resolve_unit_move_completed_mortal_wound_hooks",
    )
    battle_shock_hook_source = function_source_for(
        (UNIT_MOVE_COMPLETED_HOOKS_PATH,),
        "resolve_unit_move_completed_battle_shock_hooks",
    )

    assert "ASSAULT_DISEMBARK_MOVE_SOURCE_ID" in transport_source
    assert 'ASSAULT_DISEMBARK = "assault_disembark"' in disembark_state_source
    assert "ALLOW_ASSAULT_DISEMBARK_AFTER_NORMAL_MOVE" in disembark_state_source
    assert "ASSAULT_DISEMBARK_PERMISSION_REQUIRED" in transport_source
    assert "permission_source_rule_id" in disembark_state_source
    assert "_DISEMBARK_DISTANCE_INCHES" in transport_source
    assert "ASSAULT_DISEMBARK_PERMISSION_EFFECT_KIND" in permission_source
    assert "eligible_rules_unit_instance_ids" in permission_source
    assert "effect.source_rule_id" in shared_permission_source
    assert "assault_disembark_restriction_overrides" in candidate_source
    assert "DisembarkModeKind.ASSAULT_DISEMBARK" in candidate_source
    assert "proposal_transport_unit_drift" in proposal_validation_source
    assert "proposal_transport_override_drift" in proposal_validation_source
    assert "disembarked_unit_state_for_unit" in charge_eligibility_source
    assert "disembarked_state.can_declare_charge" in charge_eligibility_source
    assert "state.turn_player_id == requested_player_id" in turn_cleanup_source
    assert 'event_record.event_type != "unit_disembarked"' in restore_integrity_source
    assert "proposal.validation_result_for_request" in restore_integrity_source
    assert "event_state != disembarked_state" in restore_integrity_source
    assert 'record.event_type == "decision_requested"' in restore_integrity_source
    assert 'record.event_type == "decision_recorded"' in restore_integrity_source
    assert "assault_permission_sources" in restore_integrity_source
    assert "disembarked_unit_state_from_event_payload" in move_completed_owner_source
    assert "disembarked_state.turn_player_id" in move_completed_owner_source
    assert "return disembarked_state.player_id" in move_completed_owner_source
    assert "_triggering_player_id_from_move_completion_payload" in mortal_wound_hook_source
    assert "_triggering_player_id_from_move_completion_payload" in battle_shock_hook_source
    assert "assault_disembark" in adapter_contract
    for forbidden_display_name in (
        "Assault Ramp",
        "Full-throttle Assault",
        "Full-Throttle Assault",
    ):
        assert forbidden_display_name not in permission_source
        assert forbidden_display_name not in candidate_source


def test_p18e_shock_disembark_is_source_bound_and_reuses_canonical_fight_activation() -> None:
    transport_source = source_for(TRANSPORTS_PATH)
    disembark_state_source = source_for(TRANSPORT_DISEMBARK_STATE_PATH)
    shock_permission_source = source_for(SHOCK_DISEMBARK_PATH)
    shared_permission_source = source_for(TRANSPORT_DISEMBARK_PERMISSIONS_PATH)
    candidate_source = function_source_for(
        (MOVEMENT_TRANSPORTS_PATH,),
        "_disembark_candidate_for_movement_unit",
    )
    proposal_source = source_for(MOVEMENT_PROPOSALS_PATH)
    placement_source = source_for(MOVEMENT_PLACEMENT_PROPOSALS_PATH)
    fight_order_source = source_for(FIGHT_ORDER_PATH)
    fight_phase_source = source_for(FIGHT_PHASE_PATH)
    fight_hook_source = source_for(FIGHT_UNIT_SELECTED_HOOKS_PATH)
    lifecycle_source = source_for(LIFECYCLE_PATH)
    restore_source = source_for(LIFECYCLE_STATE_VALIDATION_PATH)
    adapter_contract = source_for(ADAPTER_CONTRACT_PATH)

    assert "SHOCK_DISEMBARK_MOVE_SOURCE_ID" in transport_source
    assert 'SHOCK_DISEMBARK = "shock_disembark"' in disembark_state_source
    assert "ALLOW_SHOCK_DISEMBARK_AFTER_ADVANCE" in disembark_state_source
    assert "SHOCK_DISEMBARK_PERMISSION_REQUIRED" in transport_source
    assert "SHOCK_DISEMBARK_ENGAGEMENT_SNAPSHOT_DRIFT" in transport_source
    assert "SHOCK_DISEMBARK_ENGAGEMENT_NOT_PRESERVED" in transport_source
    assert "SHOCK_DISEMBARK_PERMISSION_EFFECT_KIND" in shock_permission_source
    assert "transport_disembark_permission_effect" in shared_permission_source
    assert "shock_disembark_restriction_overrides" in candidate_source
    assert "start_engaged_enemy_unit_instance_ids" in candidate_source
    assert "ruleset_descriptor=ruleset_descriptor" in candidate_source
    assert "RulesetDescriptor.warhammer_40000_eleventh()" not in candidate_source
    assert "proposal_start_engagement_drift" in proposal_source
    assert "_start_shock_disembark_forced_fight_activations" in placement_source
    assert "ForcedFightActivationContext" in fight_order_source
    assert "for_forced_activations" in fight_order_source
    assert "advance_forced_fight_activations_if_needed" in fight_phase_source
    assert "FIGHT_ACTIVATION_DECISION_TYPE" in fight_phase_source
    assert "pass_available=False" in fight_phase_source
    assert "forced_activation_context" in fight_hook_source
    assert "advance_forced_fight_activations_if_needed" in lifecycle_source
    assert "_validate_shock_disembark_fight_history" in restore_source
    assert "_authenticated_forced_fight_selections" in restore_source
    assert "omitted mandatory forced-Fight activations" in restore_source
    assert "shock_disembark" in adapter_contract
    for forbidden_display_name in (
        "Assault Ramp",
        "Full-throttle Assault",
        "Full-Throttle Assault",
    ):
        assert forbidden_display_name not in shock_permission_source
        assert forbidden_display_name not in candidate_source


def test_phase14h_shooting_selector_and_range_helpers_are_rules_unit_aware() -> None:
    active_selector_source = function_source_for(
        SHOOTING_PHASE_SPLIT_PATHS,
        "_active_player_placed_unit_ids",
    )
    legal_selector_source = function_source_for(
        SHOOTING_PHASE_SPLIT_PATHS, "_legal_shooting_unit_ids"
    )
    options_source = function_source_for(SHOOTING_PHASE_SPLIT_PATHS, "_shooting_unit_options")
    available_weapons_source = function_source_for(
        SHOOTING_PHASE_SPLIT_PATHS,
        "_available_weapons_for_rules_unit",
    )
    range_source = function_source_for(SHOOTING_PHASE_SPLIT_PATHS, "_unit_target_within_max_range")

    assert "rules_unit_id_for_unit_id" in active_selector_source
    assert "unit_ids.append(placement.unit_instance_id)" not in active_selector_source
    assert "seen: set[str]" in active_selector_source

    assert "rules_unit_view_by_id" in legal_selector_source
    assert "_unit_by_id" not in legal_selector_source
    assert "_rules_unit_has_legal_shooting_declaration" in legal_selector_source
    assert "legal.append(rules_unit.unit_instance_id)" in legal_selector_source

    assert "option_id=rules_unit.unit_instance_id" in options_source
    assert '"unit_instance_id": rules_unit.unit_instance_id' in options_source
    assert "_available_weapons_for_unit" in available_weapons_source
    assert "for component in rules_unit.components" in available_weapons_source

    assert "target_within_shooting_selection_range" in range_source
    assert "rules_unit_view_from_armies" not in range_source
    assert "_unit_placements_for_rules_unit_or_none" not in range_source
    assert "unit_placement_by_id(component" not in range_source


def test_phase14h_docs_mark_complete_after_attached_formation_cutover() -> None:
    architecture = source_for(ARCHITECTURE_PATH)
    readme = source_for(README_PATH)
    phase14h_section = architecture.split("## Phase 14H:", maxsplit=1)[1].split(
        "\n## Phase 14I:",
        maxsplit=1,
    )[0]

    assert "Status: Complete." in phase14h_section
    assert "Phase 14H is complete" in architecture
    assert "Phase 14H is complete" in readme
    assert "Phase 14H remains deferred" not in architecture
    assert "Phase 14H remains deferred" not in readme
    assert "runtime Attached Unit formation" in architecture
    assert "runtime Attached Unit formation" in readme
    assert "structured army-list Leader/Support declarations" in architecture
    assert "structured army-list Leader/Support declarations" in readme
    assert "first-class attached rules-unit formation records" in architecture
    assert "first-class attached rules-unit formation records" in readme
    assert "Broader real-faction Leader/Support eligibility data" in architecture
    assert "runtime attached-unit formation;" not in readme
    assert "open blocker" not in phase14h_section
    assert "Healing Wounds primitive now iterates each healing amount" in architecture
    assert "healing, revival, persisting effects" in readme
    assert "Movement-phase Combat Disembark fallback now accepts Combat mode" in architecture
    assert "Movement-phase Combat Disembark fallback with engine-owned" in readme
    assert "Attached Unit formation" in architecture
    assert "full repositioned-unit effect persistence" not in architecture
    assert "setup-time reserve/transport declarations" not in architecture
    assert "setup-time Strategic Reserve declarations" in architecture
    assert "setup-time Strategic Reserve declarations" in readme
    assert "repositioned-unit Advance/Fall Back/Disembark history" in architecture
    assert "repositioned-unit Advance/Fall Back/Disembark history" in readme
    assert "destroyed-Transport orchestration from real destruction timing" not in architecture
    assert "destroyed-Transport orchestration from real destruction timing" not in readme
    adapter_contract = source_for(ADAPTER_CONTRACT_PATH)
    assert "player-facing destruction-time host remains Phase 14H work" not in adapter_contract
    assert "actual destruction event before Transport removal and Deadly Demise" in adapter_contract
    assert "mixed-Toughness attached-unit attack handling" not in architecture
    assert "mixed-Toughness attached-unit attack handling" not in readme
