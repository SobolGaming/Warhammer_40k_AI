from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from typing import Any, cast

import pytest
from tests.movement_submission_helpers import (
    straight_line_witness_for_unit,
    submit_movement_proposal,
)
from tests.phase15c_fight_order_helpers import (
    advance_to_fight_order_request,
    fight_lifecycle,
    submit_minimal_melee_declaration,
)

from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.core.attributes import Characteristic, CharacteristicValue
from warhammer40k_core.core.datasheet import (
    BaseSizeDefinition,
    DatasheetDefinition,
    DatasheetKeywordSet,
)
from warhammer40k_core.core.detachment import DetachmentDefinition, EnhancementDefinition
from warhammer40k_core.core.dice import (
    DiceExpression,
    DiceRollState,
    DiceRollStatePayload,
    RerollComponentSelectionPolicy,
)
from warhammer40k_core.core.faction import FactionDefinition
from warhammer40k_core.core.ruleset import RulesetId
from warhammer40k_core.core.ruleset_descriptor import MovementMode, RulesetDescriptor
from warhammer40k_core.core.weapon_profiles import (
    AbilityDescriptor,
    AbilityKind,
    AbilityParameter,
    AttackProfile,
    DamageProfile,
    RangeProfile,
    WeaponKeyword,
    WeaponProfile,
)
from warhammer40k_core.engine.abilities import AbilityCatalogIndex
from warhammer40k_core.engine.advance_hooks import (
    DECLINE_MOVEMENT_ACTION_GRANT_OPTION_ID,
    SELECT_MOVEMENT_ACTION_GRANT_DECISION_TYPE,
)
from warhammer40k_core.engine.army_mustering import (
    ArmyDefinition,
    ArmyMusterRequest,
    EnhancementAssignment,
    WarlordSelection,
    muster_army,
    validate_roster_legality,
)
from warhammer40k_core.engine.attack_sequence import (
    AttackSequenceStep,
    attack_sequence_hit_roll_spec,
    attack_sequence_wound_roll_spec,
)
from warhammer40k_core.engine.battle_formation_hooks import (
    BattleFormationRequestContext,
    BattleFormationResultContext,
)
from warhammer40k_core.engine.battle_shock_hooks import BattleShockHookRegistry
from warhammer40k_core.engine.battlefield_state import (
    BattlefieldRuntimeState,
    ModelPlacement,
    PlacedArmy,
    UnitPlacement,
)
from warhammer40k_core.engine.command_points import CommandPointSourceKind
from warhammer40k_core.engine.core_stratagem_effects import SMOKESCREEN_EFFECT_KIND
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_request import DecisionOption, DecisionRequest
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.dice import DICE_REROLL_DECISION_TYPE, DiceRollManager
from warhammer40k_core.engine.effects import GENERIC_RULE_EFFECT_KIND
from warhammer40k_core.engine.enhancement_effects import (
    EnhancementEffectContext,
    apply_enhancement_effects,
)
from warhammer40k_core.engine.event_log import EventRecord, JsonValue, validate_json_value
from warhammer40k_core.engine.faction_content.activation import RuntimeContentActivation
from warhammer40k_core.engine.faction_content.bundle import RuntimeContentBundle
from warhammer40k_core.engine.faction_content.runtime import runtime_content_activation_for_armies
from warhammer40k_core.engine.faction_content.stratagem_handlers import (
    StratagemHandlerContext,
    StratagemHandlerRegistry,
)
from warhammer40k_core.engine.faction_content.warhammer_40000_11th.aeldari.detachments.corsair_coterie import (  # noqa: E501
    enhancements,
    manifest,
    rule,
    stratagems,
)
from warhammer40k_core.engine.faction_rule_states import FactionRuleState
from warhammer40k_core.engine.fight_activation_abilities import (
    DECLINE_FIGHT_ACTIVATION_ABILITY_OPTION_ID,
    FIGHT_ACTIVATION_ABILITY_DECISION_TYPE,
)
from warhammer40k_core.engine.fight_order import (
    FIGHT_ACTIVATION_DECISION_TYPE,
    FightPhaseState,
    FightsFirstRegistry,
    fight_activation_option_id,
)
from warhammer40k_core.engine.fight_resolution import MeleeDeclarationProposalRequest
from warhammer40k_core.engine.game_state import (
    GameConfig,
    GameState,
    SecondaryMissionChoice,
    SecondaryMissionMode,
)
from warhammer40k_core.engine.generic_target_restriction_effects import (
    GENERIC_PERSISTED_SHOOTING_TARGET_RANGE_RESTRICTION_HOOK_ID,
    GENERIC_PERSISTED_SHOOTING_TARGET_RANGE_RESTRICTION_SOURCE_ID,
    GENERIC_PERSISTED_SHOOTING_TARGET_RANGE_RESTRICTION_VIOLATION_CODE,
    generic_persisted_shooting_target_range_restriction,
)
from warhammer40k_core.engine.lifecycle import GameLifecycle
from warhammer40k_core.engine.list_validation import (
    DetachmentSelection,
    UnitMusterSelection,
)
from warhammer40k_core.engine.mission_setup import MissionSetup
from warhammer40k_core.engine.phase import (
    BattlePhase,
    GameLifecycleError,
    GameLifecycleStage,
    LifecycleStatus,
    LifecycleStatusKind,
    SetupStep,
)
from warhammer40k_core.engine.phases.movement import (
    SELECT_MOVEMENT_ACTION_DECISION_TYPE,
    SELECT_MOVEMENT_UNIT_DECISION_TYPE,
    MovementPhaseActionKind,
)
from warhammer40k_core.engine.phases.shooting import ShootingPhaseState
from warhammer40k_core.engine.roster_points import RosterUnitPointValue
from warhammer40k_core.engine.runtime_modifiers import (
    ObjectiveControlModifierContext,
    RuntimeModifierRegistry,
    SaveOptionModifierContext,
    WeaponProfileModifierContext,
)
from warhammer40k_core.engine.saves import SaveKind, SaveOption
from warhammer40k_core.engine.source_backed_rerolls import (
    source_backed_reroll_permission_context_for_unit,
)
from warhammer40k_core.engine.sticky_objective_control import PhaseEndObjectiveControlContext
from warhammer40k_core.engine.stratagem_cost_choice_hooks import (
    SELECT_STRATAGEM_COST_MODIFIER_OPTION_DECISION_TYPE,
    StratagemCostChoiceHookBinding,
    StratagemCostChoiceHookRegistry,
    StratagemCostChoiceRequestContext,
    StratagemCostChoiceResultContext,
    source_result_payload_for_cost_choice,
    stratagem_cost_choice_source_result,
)
from warhammer40k_core.engine.stratagem_cost_modifiers import (
    StratagemCostModificationResult,
    StratagemCostModifierBinding,
    StratagemCostModifierContext,
    StratagemCostModifierRegistry,
)
from warhammer40k_core.engine.stratagems import (
    DECLINE_STRATAGEM_WINDOW_OPTION_ID,
    DESTROYED_ENEMY_UNIT_CONTEXT_KEY,
    DESTROYED_TARGET_UNIT_CONTEXT_KEY,
    ENGAGED_ENEMY_UNIT_CONTEXT_KEY,
    ENGAGED_ENEMY_UNIT_EFFECT_SELECTION_KIND,
    ENGAGED_ENEMY_UNIT_IDS_CONTEXT_KEY,
    GENERIC_RULE_IR_STRATAGEM_HANDLER_ID,
    HIT_TARGET_UNIT_CONTEXT_KEY,
    JUST_FELL_BACK_UNIT_CONTEXT_KEY,
    JUST_SHOT_UNIT_CONTEXT_KEY,
    SELECTED_TARGET_UNIT_CONTEXT_KEY,
    STRATAGEM_DECISION_TYPE,
    StratagemCatalogRecord,
    StratagemCategory,
    StratagemDefinition,
    StratagemEligibilityContext,
    StratagemTargetBinding,
    StratagemTargetKind,
    StratagemTargetSpec,
    StratagemTimingDescriptor,
    StratagemUseRecord,
    apply_stratagem_decision,
    request_stratagem_use,
)
from warhammer40k_core.engine.target_restriction_hooks import ShootingTargetRestrictionContext
from warhammer40k_core.engine.timing_windows import TimingTriggerKind
from warhammer40k_core.engine.turn_end_hooks import (
    SELECT_FACTION_RULE_TURN_END_OPTION_DECISION_TYPE,
    TurnEndHookBinding,
    TurnEndHookRegistry,
    TurnEndRequestContext,
    TurnEndResultContext,
)
from warhammer40k_core.engine.unit_factory import ModelInstance, UnitInstance
from warhammer40k_core.engine.unit_move_completed_hooks import (
    UNIT_MOVE_COMPLETED_BATTLE_SHOCK_RESOLVED_EVENT,
    UNIT_MOVE_COMPLETED_MORTAL_WOUNDS_IGNORED_EVENT,
    UNIT_MOVE_COMPLETED_MORTAL_WOUNDS_PENDING_EVENT,
    UNIT_MOVE_COMPLETED_MORTAL_WOUNDS_RESOLVED_EVENT,
    UNIT_MOVE_COMPLETED_MORTAL_WOUNDS_ROLLED_EVENT,
    UnitMoveCompletedBattleShockEffect,
    UnitMoveCompletedBattleShockHookBinding,
    UnitMoveCompletedBattleShockHookRegistry,
    UnitMoveCompletedContext,
    UnitMoveCompletedMortalWoundEffect,
    UnitMoveCompletedMortalWoundHookBinding,
    UnitMoveCompletedMortalWoundHookRegistry,
    resolve_unit_move_completed_battle_shock_hooks,
    resolve_unit_move_completed_mortal_wound_hooks,
)
from warhammer40k_core.engine.unit_state import starting_strength_records_for_units
from warhammer40k_core.engine.wargear_selections import (
    ModelProfileSelection,
)
from warhammer40k_core.geometry.model_geometry import ModelGeometry
from warhammer40k_core.geometry.pose import Pose
from warhammer40k_core.rules.mission_pack_import import chapter_approved_2026_27_mission_pack
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    faction_execution_2026_27,
)

_CORSAIR_UNIT_ID = "army-a:corsairs"
_ARCHRAIDER_UNIT_ID = "army-a:archraider"
_VOIDSTONE_UNIT_ID = "army-a:voidstone-bearers"
_WEBWAY_UNIT_ID = "army-a:webway-bearers"
_ENEMY_UNIT_ID = "army-b:enemy-raiders"
_LIFECYCLE_ENEMY_UNIT_ID = "army-b:corsairs"


def test_veterans_of_the_void_allows_four_unique_corsair_enhancements() -> None:
    catalog = _corsair_mustering_catalog()
    request = _corsair_muster_request(
        catalog,
        enhancement_assignments=(
            _assignment(enhancements.ARCHRAIDER_ENHANCEMENT_ID, "archraider"),
            _assignment(enhancements.INFAMY_ENHANCEMENT_ID, "corsairs"),
            _assignment(enhancements.VOIDSTONE_ENHANCEMENT_ID, "voidstone-bearers"),
            _assignment(enhancements.WEBWAY_PATHSTONE_ENHANCEMENT_ID, "webway-bearers"),
        ),
    )

    report = validate_roster_legality(catalog=catalog, request=request)

    assert report.violations == ()


def test_veterans_of_the_void_enforces_unique_and_target_restrictions() -> None:
    catalog = _corsair_mustering_catalog()
    request = _corsair_muster_request(
        catalog,
        enhancement_assignments=(
            _assignment(enhancements.INFAMY_ENHANCEMENT_ID, "corsairs"),
            _assignment(enhancements.INFAMY_ENHANCEMENT_ID, "webway-bearers"),
            _assignment(enhancements.INFAMY_ENHANCEMENT_ID, "guardian-defenders"),
            _assignment(enhancements.ARCHRAIDER_ENHANCEMENT_ID, "voidstone-bearers"),
            _assignment(enhancements.VOIDSTONE_ENHANCEMENT_ID, "corsair-bikers"),
        ),
    )

    report = validate_roster_legality(catalog=catalog, request=request)
    violation_codes = {violation.violation_code for violation in report.violations}

    assert "enhancement_repeated_assignment_forbidden" in violation_codes
    assert "corsair_coterie_anhrathe_required" in violation_codes
    assert "corsair_coterie_archraider_character_required" in violation_codes
    assert "corsair_coterie_voidstone_infantry_required" in violation_codes


def test_corsair_coterie_runtime_contribution_registers_rule_and_enhancement_hooks() -> None:
    contribution = manifest.runtime_contribution()

    assert rule.RELENTLESS_RAIDERS_HOOK_ID in {
        binding.hook_id for binding in contribution.unit_move_completed_mortal_wound_hook_bindings
    }
    assert rule.VOID_THIEVES_HOOK_ID in {
        binding.hook_id for binding in contribution.phase_end_objective_control_hook_bindings
    }
    assert contribution.enhancement_effect_bindings == ()
    assert contribution.battle_formation_hook_bindings == ()
    assert contribution.stratagem_cost_choice_hook_bindings == ()
    assert contribution.stratagem_cost_modifier_bindings == ()
    assert contribution.objective_control_modifier_bindings == ()
    assert contribution.save_option_modifier_bindings == ()
    assert contribution.turn_end_hook_bindings == ()
    assert {record.definition.stratagem_id for record in contribution.stratagem_records} == {
        stratagems.PIRATES_DUE_STRATAGEM_ID,
        stratagems.LETHAL_RUSE_STRATAGEM_ID,
        stratagems.OUTCAST_AMBUSH_STRATAGEM_ID,
        stratagems.INTO_THE_BREACH_STRATAGEM_ID,
        stratagems.CLOAK_AND_SHADOW_STRATAGEM_ID,
        stratagems.VENGEFUL_SORROW_STRATAGEM_ID,
    }
    assert {record.definition.handler_id for record in contribution.stratagem_records} == {
        GENERIC_RULE_IR_STRATAGEM_HANDLER_ID,
    }
    assert all(
        isinstance(record.definition.effect_payload, dict)
        and isinstance(record.definition.effect_payload.get("rule_ir"), dict)
        for record in contribution.stratagem_records
    )
    assert contribution.stratagem_handler_bindings == ()
    assert contribution.weapon_profile_modifier_bindings == ()
    assert contribution.shooting_target_restriction_hook_bindings == ()


def test_corsair_coterie_runtime_bundle_exposes_new_hook_registries_and_summary() -> None:
    assignments = (
        _assignment(enhancements.ARCHRAIDER_ENHANCEMENT_ID, "archraider"),
        _assignment(enhancements.INFAMY_ENHANCEMENT_ID, "corsairs"),
        _assignment(enhancements.VOIDSTONE_ENHANCEMENT_ID, "voidstone-bearers"),
        _assignment(enhancements.WEBWAY_PATHSTONE_ENHANCEMENT_ID, "webway-bearers"),
    )
    config = _corsair_game_config(enhancement_assignments=assignments)
    armies = tuple(
        muster_army(catalog=config.army_catalog, request=request)
        for request in config.army_muster_requests
    )
    activation = runtime_content_activation_for_armies(config=config, armies=armies)

    bundle = RuntimeContentBundle.from_contributions(
        activation=activation,
        armies=armies,
        catalog=config.army_catalog,
        contributions=(manifest.runtime_contribution(),),
        faction_execution_records=faction_execution_2026_27.execution_records(),
    )
    summary = bundle.to_summary_payload()

    assert {binding.effect_id for binding in bundle.enhancement_effect_registry.all_bindings()} == {
        enhancements.ARCHRAIDER_EFFECT_ID,
        enhancements.INFAMY_EFFECT_ID,
        enhancements.VOIDSTONE_EFFECT_ID,
        enhancements.WEBWAY_PATHSTONE_EFFECT_ID,
        enhancements.WEBWAY_PATHSTONE_DEEP_STRIKE_EFFECT_ID,
    }
    assert {
        binding.hook_id for binding in bundle.battle_formation_hook_registry.all_bindings()
    } == {
        enhancements.ARCHRAIDER_SETUP_HOOK_ID,
    }
    assert {binding.hook_id for binding in bundle.turn_end_hook_registry.all_bindings()} == {
        enhancements.WEBWAY_PATHSTONE_TURN_END_HOOK_ID
    }
    assert {
        binding.hook_id
        for binding in bundle.unit_move_completed_mortal_wound_hook_registry.all_bindings()
    } == {rule.RELENTLESS_RAIDERS_HOOK_ID}
    assert {
        binding.hook_id for binding in bundle.stratagem_cost_choice_hook_registry.all_bindings()
    } == {enhancements.ARCHRAIDER_COST_CHOICE_HOOK_ID}
    assert {
        binding.modifier_id for binding in bundle.stratagem_cost_modifier_registry.all_bindings()
    } == {enhancements.ARCHRAIDER_COST_MODIFIER_ID}
    assert {
        binding.modifier_id
        for binding in bundle.runtime_modifier_registry.all_objective_control_bindings()
    } == {enhancements.INFAMY_OBJECTIVE_CONTROL_MODIFIER_ID}
    assert {
        binding.modifier_id
        for binding in bundle.runtime_modifier_registry.all_save_option_bindings()
    } == {enhancements.VOIDSTONE_SAVE_MODIFIER_ID}
    assert {
        binding.hook_id
        for binding in bundle.shooting_target_restriction_hook_registry.all_bindings()
    } == {GENERIC_PERSISTED_SHOOTING_TARGET_RANGE_RESTRICTION_HOOK_ID}
    assert summary["enhancement_effect_binding_ids"] == [
        enhancements.ARCHRAIDER_EFFECT_ID,
        enhancements.INFAMY_EFFECT_ID,
        enhancements.VOIDSTONE_EFFECT_ID,
        enhancements.WEBWAY_PATHSTONE_EFFECT_ID,
        enhancements.WEBWAY_PATHSTONE_DEEP_STRIKE_EFFECT_ID,
    ]
    assert summary["battle_formation_hook_ids"] == [enhancements.ARCHRAIDER_SETUP_HOOK_ID]
    assert summary["turn_end_hook_ids"] == [enhancements.WEBWAY_PATHSTONE_TURN_END_HOOK_ID]
    assert summary["unit_move_completed_mortal_wound_hook_ids"] == [rule.RELENTLESS_RAIDERS_HOOK_ID]
    assert summary["stratagem_cost_choice_hook_ids"] == [
        enhancements.ARCHRAIDER_COST_CHOICE_HOOK_ID
    ]
    assert summary["stratagem_cost_modifier_ids"] == [enhancements.ARCHRAIDER_COST_MODIFIER_ID]
    assert summary["objective_control_modifier_ids"] == [
        enhancements.INFAMY_OBJECTIVE_CONTROL_MODIFIER_ID
    ]
    assert summary["save_option_modifier_ids"] == [enhancements.VOIDSTONE_SAVE_MODIFIER_ID]
    assert summary["shooting_target_restriction_hook_ids"] == [
        GENERIC_PERSISTED_SHOOTING_TARGET_RANGE_RESTRICTION_HOOK_ID
    ]
    assert summary["bundle_summary_hash"]


def test_pirates_due_records_source_backed_wound_reroll_permission() -> None:
    state, _corsair_army, _enemy_army = _corsair_state(
        phase=BattlePhase.FIGHT,
        active_player_id="player-a",
    )
    context = _corsair_stratagem_handler_context(
        state=state,
        stratagem_id=stratagems.PIRATES_DUE_STRATAGEM_ID,
        handler_id=stratagems.PIRATES_DUE_HANDLER_ID,
        target_unit_id=_CORSAIR_UNIT_ID,
        phase=BattlePhase.FIGHT,
        trigger_kind=TimingTriggerKind.DURING_PHASE,
    )

    result = stratagems.apply_pirates_due(context)

    assert result.reason is None
    permission_context = source_backed_reroll_permission_context_for_unit(
        state=state,
        player_id="player-a",
        unit_instance_id=_CORSAIR_UNIT_ID,
        roll_type="attack_sequence.wound",
        timing_window="attack_sequence.wound",
    )
    assert permission_context is not None
    assert (
        permission_context.permission.component_selection_policy
        is RerollComponentSelectionPolicy.COMPONENT_SELECTION
    )
    assert permission_context.permission.allowed_component_selections == ((0,),)
    assert permission_context.source_payload["effect_kind"] == stratagems.PIRATES_DUE_EFFECT_KIND
    conditional = permission_context.source_payload["conditional_wound_reroll"]
    assert isinstance(conditional, dict)
    assert conditional["reroll_unmodified_values"] == [1]
    assert conditional["full_reroll_if_target_within_objective_range"] is True


def test_pirates_due_lifecycle_accepts_fight_wound_reroll_and_resumes_attack() -> None:
    lifecycle, units = fight_lifecycle(
        alpha_unit_ids=("corsairs",),
        enemy_unit_ids=("enemy",),
        origins={
            "corsairs": Pose.at(94.0, 95.0),
            "enemy": Pose.at(95.0, 95.0),
        },
        game_id="phase17g-corsair-pirates-due-wound-reroll-2",
        datasheet_id="core-character-leader",
        model_profile_id="core-character-leader",
        model_count=1,
    )
    state = _lifecycle_state(lifecycle)
    _mark_player_as_corsair_coterie(state, player_id="player-a")
    state.gain_command_points(
        player_id="player-a",
        amount=1,
        source_id="phase17g-corsair-pirates-due-cp",
        source_kind=CommandPointSourceKind.OTHER,
        cap_exempt=True,
    )
    _refresh_lifecycle_runtime_content(lifecycle)
    unit = units["corsairs"]

    stratagem_request = advance_to_fight_order_request(lifecycle)
    assert stratagem_request.decision_type == STRATAGEM_DECISION_TYPE
    pirates_due_option = _stratagem_option(stratagem_request, stratagems.PIRATES_DUE_STRATAGEM_ID)
    activation_request = _decision_request(
        lifecycle.submit_decision(
            DecisionResult.for_request(
                result_id="phase17g-corsair-pirates-due-use",
                request=stratagem_request,
                selected_option_id=pirates_due_option.option_id,
            )
        )
    )
    assert activation_request.decision_type == FIGHT_ACTIVATION_DECISION_TYPE
    ability_request = _decision_request(
        lifecycle.submit_decision(
            DecisionResult.for_request(
                result_id="phase17g-corsair-pirates-due-select-fight",
                request=activation_request,
                selected_option_id=fight_activation_option_id(
                    unit_instance_id=unit.unit_instance_id,
                    fight_type=RulesetDescriptor.warhammer_40000_eleventh().fight_policy.fight_types[
                        0
                    ],
                ),
            )
        )
    )
    assert ability_request.decision_type == FIGHT_ACTIVATION_ABILITY_DECISION_TYPE
    melee_request = _decision_request(
        lifecycle.submit_decision(
            DecisionResult.for_request(
                result_id="phase17g-corsair-pirates-due-decline-ability",
                request=ability_request,
                selected_option_id=DECLINE_FIGHT_ACTIVATION_ABILITY_OPTION_ID,
            )
        )
    )
    proposal_request = MeleeDeclarationProposalRequest.from_decision_request(melee_request)
    weapon_payload = _first_primary_melee_weapon_payload(proposal_request)
    weapon_profile_id = cast(str, weapon_payload["weapon_profile_id"])
    declaration_result_id = "phase17g-corsair-pirates-due-melee"
    sequence_id = (
        f"melee-sequence:{state.game_id}:round-{state.battle_round:02d}:"
        f"{unit.unit_instance_id}:{declaration_result_id}"
    )
    attack_context_id = f"{sequence_id}:pool-001:attack-001"
    fixed_rolls = DiceRollManager(state.game_id, event_log=lifecycle.decision_controller.event_log)
    fixed_rolls.roll_fixed(
        attack_sequence_hit_roll_spec(
            weapon_profile_id=weapon_profile_id,
            attack_context_id=attack_context_id,
            attacker_player_id="player-a",
        ),
        [6],
    )
    wound_spec = attack_sequence_wound_roll_spec(
        weapon_profile_id=weapon_profile_id,
        attack_context_id=attack_context_id,
        attacker_player_id="player-a",
    )
    fixed_rolls.roll_fixed(wound_spec, [1])

    reroll_request = _decision_request(
        submit_minimal_melee_declaration(
            lifecycle,
            request=melee_request,
            result_id=declaration_result_id,
        )
    )
    assert reroll_request.decision_type == DICE_REROLL_DECISION_TYPE
    reroll_request_payload = cast(dict[str, object], reroll_request.payload)
    assert reroll_request_payload["roll_type"] == "attack_sequence.wound"
    permission_payload = cast(dict[str, object], reroll_request_payload["permission"])
    assert permission_payload["timing_window"] == "attack_sequence.wound"
    assert permission_payload["eligible_roll_type"] == "attack_sequence.wound"
    assert permission_payload["component_selection_policy"] == "whole_roll"
    assert permission_payload["allowed_component_selections"] is None
    attack_context_payload = cast(dict[str, object], reroll_request_payload["attack_context"])
    assert attack_context_payload["phase"] == BattlePhase.FIGHT.value
    wound_roll_state = cast(dict[str, object], attack_context_payload["wound_roll_state"])
    assert wound_roll_state["current_values"] == [1]

    accepted_status = lifecycle.submit_decision(
        DecisionResult.for_request(
            result_id="phase17g-corsair-pirates-due-accept-wound-reroll",
            request=reroll_request,
            selected_option_id="reroll:0",
        )
    )

    assert accepted_status.status_kind is not LifecycleStatusKind.INVALID
    reroll_payloads = _lifecycle_event_payloads(lifecycle, "dice_reroll_resolved")
    assert len(reroll_payloads) == 1
    rerolled_state = DiceRollState.from_payload(cast(DiceRollStatePayload, reroll_payloads[0]))
    wound_original_result = cast(dict[str, object], wound_roll_state["original_result"])
    assert rerolled_state.original_result.roll_id == wound_original_result["roll_id"]
    wound_payload = _attack_step_payload(
        _lifecycle_event_payloads(lifecycle, "attack_sequence_step"),
        AttackSequenceStep.WOUND,
    )
    resolved_wound = cast(dict[str, object], wound_payload["payload"])
    assert resolved_wound["successful"] is True
    assert cast(dict[str, object], resolved_wound["roll_state"]) == rerolled_state.to_payload()
    downstream_status = _drain_until_downstream_attack_resolution(
        lifecycle,
        accepted_status,
        result_id_prefix="phase17g-corsair-pirates-due-downstream",
    )
    assert downstream_status.status_kind is not LifecycleStatusKind.INVALID
    downstream_steps = {
        cast(str, payload["step"])
        for payload in _lifecycle_event_payloads(lifecycle, "attack_sequence_step")
    }
    assert downstream_steps & {
        AttackSequenceStep.ALLOCATE.value,
        AttackSequenceStep.SAVE.value,
        AttackSequenceStep.DAMAGE.value,
    }


def test_lethal_ruse_records_charge_after_fall_back_and_resolves_anhrathe_mortal_rolls() -> None:
    state, _corsair_army, _enemy_army = _corsair_state(
        phase=BattlePhase.MOVEMENT,
        active_player_id="player-a",
        corsair_x=30.0,
        enemy_x=31.0,
    )
    context = _corsair_stratagem_handler_context(
        state=state,
        stratagem_id=stratagems.LETHAL_RUSE_STRATAGEM_ID,
        handler_id=stratagems.LETHAL_RUSE_HANDLER_ID,
        target_unit_id=_CORSAIR_UNIT_ID,
        phase=BattlePhase.MOVEMENT,
        trigger_kind=TimingTriggerKind.JUST_AFTER_FRIENDLY_UNIT_FALLS_BACK,
        trigger_payload={
            JUST_FELL_BACK_UNIT_CONTEXT_KEY: _CORSAIR_UNIT_ID,
            ENGAGED_ENEMY_UNIT_IDS_CONTEXT_KEY: [_ENEMY_UNIT_ID],
            "movement_activation_completed_event_id": "event-lethal-ruse-fall-back",
        },
        effect_selection={
            "effect_selection_kind": ENGAGED_ENEMY_UNIT_EFFECT_SELECTION_KIND,
            ENGAGED_ENEMY_UNIT_CONTEXT_KEY: _ENEMY_UNIT_ID,
        },
    )

    result = stratagems.apply_lethal_ruse(context)

    assert result.reason is None
    effects = state.persisting_effects_for_unit(_CORSAIR_UNIT_ID)
    assert len(effects) == 1
    effect_payload = _json_object(effects[0].effect_payload)
    assert effect_payload["effect_kind"] == "charge_after_fall_back_allowed"
    replay_payload = _json_object(result.replay_payload)
    mortal_payload = _json_object(replay_payload["mortal_wound_resolution"])
    assert mortal_payload["enemy_unit_instance_id"] == _ENEMY_UNIT_ID
    rolls = mortal_payload["rolls"]
    assert isinstance(rolls, list)
    assert len(cast(list[object], rolls)) == 6


def test_outcast_ambush_records_effect_and_modifies_ranged_weapon_profile() -> None:
    state, _corsair_army, _enemy_army = _corsair_state(
        phase=BattlePhase.SHOOTING,
        active_player_id="player-a",
        corsair_keywords=("RANGERS", "INFANTRY"),
    )
    context = _corsair_stratagem_handler_context(
        state=state,
        stratagem_id=stratagems.OUTCAST_AMBUSH_STRATAGEM_ID,
        handler_id=stratagems.OUTCAST_AMBUSH_HANDLER_ID,
        target_unit_id=_CORSAIR_UNIT_ID,
        phase=BattlePhase.SHOOTING,
        trigger_kind=TimingTriggerKind.DURING_PHASE,
    )

    result = stratagems.apply_outcast_ambush(context)

    assert result.reason is None
    modified = stratagems.outcast_ambush_weapon_profile_modifier(
        WeaponProfileModifierContext(
            state=state,
            source_phase=BattlePhase.SHOOTING,
            attacking_unit_instance_id=_CORSAIR_UNIT_ID,
            attacker_model_instance_id=f"{_CORSAIR_UNIT_ID}:model-001",
            target_unit_instance_id=_ENEMY_UNIT_ID,
            weapon_profile=_corsair_test_weapon_profile(ap=-1),
        )
    )
    assert modified.armor_penetration.final == -2
    assert WeaponKeyword.IGNORES_COVER in modified.keywords
    assert WeaponKeyword.RAPID_FIRE in modified.keywords
    assert any(ability.ability_kind is AbilityKind.RAPID_FIRE for ability in modified.abilities)


def test_into_the_breach_requires_destroyed_enemy_unit_and_requests_d6_plus_one_move() -> None:
    state, _corsair_army, _enemy_army = _corsair_state(
        phase=BattlePhase.SHOOTING,
        active_player_id="player-a",
    )
    context = _corsair_stratagem_handler_context(
        state=state,
        stratagem_id=stratagems.INTO_THE_BREACH_STRATAGEM_ID,
        handler_id=stratagems.INTO_THE_BREACH_HANDLER_ID,
        target_unit_id=_CORSAIR_UNIT_ID,
        phase=BattlePhase.SHOOTING,
        trigger_kind=TimingTriggerKind.JUST_AFTER_FRIENDLY_UNIT_HAS_SHOT,
        trigger_payload={
            JUST_SHOT_UNIT_CONTEXT_KEY: _CORSAIR_UNIT_ID,
            HIT_TARGET_UNIT_CONTEXT_KEY: [_ENEMY_UNIT_ID],
            DESTROYED_TARGET_UNIT_CONTEXT_KEY: [_ENEMY_UNIT_ID],
            DESTROYED_ENEMY_UNIT_CONTEXT_KEY: [_ENEMY_UNIT_ID],
            "attack_sequence_completed_event_id": "event-into-the-breach-shot",
        },
    )

    result = stratagems.apply_into_the_breach(context)

    assert result.reason is None
    request = context.decisions.queue.peek_next()
    assert request.decision_type == "select_triggered_movement"
    replay_payload = _json_object(result.replay_payload)
    distance_roll = _json_object(replay_payload["distance_roll"])
    assert replay_payload["triggered_movement_request_id"] == request.request_id
    assert 2 <= cast(int, distance_roll["current_total"]) + 1 <= 7

    model_destroyed_only_context = _corsair_stratagem_handler_context(
        state=state,
        stratagem_id=stratagems.INTO_THE_BREACH_STRATAGEM_ID,
        handler_id=stratagems.INTO_THE_BREACH_HANDLER_ID,
        target_unit_id=_CORSAIR_UNIT_ID,
        phase=BattlePhase.SHOOTING,
        trigger_kind=TimingTriggerKind.JUST_AFTER_FRIENDLY_UNIT_HAS_SHOT,
        trigger_payload={
            JUST_SHOT_UNIT_CONTEXT_KEY: _CORSAIR_UNIT_ID,
            HIT_TARGET_UNIT_CONTEXT_KEY: [_ENEMY_UNIT_ID],
            DESTROYED_TARGET_UNIT_CONTEXT_KEY: [_ENEMY_UNIT_ID],
            "attack_sequence_completed_event_id": "event-into-the-breach-model-only",
        },
    )
    assert stratagems.validate_into_the_breach(model_destroyed_only_context).reason == (
        "no_enemy_unit_destroyed"
    )


def test_cloak_and_shadow_records_stealth_effect_and_blocks_distant_attacking_models() -> None:
    state, _corsair_army, _enemy_army = _corsair_state(
        phase=BattlePhase.SHOOTING,
        active_player_id="player-b",
        corsair_x=30.0,
        enemy_x=55.0,
    )
    context = _corsair_stratagem_handler_context(
        state=state,
        player_id="player-a",
        stratagem_id=stratagems.CLOAK_AND_SHADOW_STRATAGEM_ID,
        handler_id=stratagems.CLOAK_AND_SHADOW_HANDLER_ID,
        target_unit_id=_CORSAIR_UNIT_ID,
        phase=BattlePhase.SHOOTING,
        trigger_kind=TimingTriggerKind.AFTER_UNIT_SELECTED_AS_TARGET,
        trigger_payload={
            SELECTED_TARGET_UNIT_CONTEXT_KEY: [_CORSAIR_UNIT_ID],
            "attacking_unit_instance_id": _ENEMY_UNIT_ID,
            "attack_sequence_id": "attack-sequence-cloak",
        },
    )

    result = stratagems.apply_cloak_and_shadow(context)

    assert result.reason is None
    effect_payload = _json_object(
        state.persisting_effects_for_unit(_CORSAIR_UNIT_ID)[0].effect_payload
    )
    assert effect_payload["effect_kind"] == SMOKESCREEN_EFFECT_KIND
    assert effect_payload["source_effect_kind"] == stratagems.CLOAK_AND_SHADOW_EFFECT_KIND
    restrictions = _corsair_runtime_bundle_for_state(
        state
    ).shooting_target_restriction_hook_registry.restrictions_for(
        ShootingTargetRestrictionContext(
            state=state,
            player_id="player-b",
            battle_round=state.battle_round,
            attacking_unit_instance_id=_ENEMY_UNIT_ID,
            attacker_model_instance_id=f"{_ENEMY_UNIT_ID}:model-001",
            target_unit_instance_id=_CORSAIR_UNIT_ID,
        )
    )
    assert len(restrictions) == 1
    restriction = restrictions[0]
    assert restriction.hook_id == GENERIC_PERSISTED_SHOOTING_TARGET_RANGE_RESTRICTION_HOOK_ID
    assert restriction.source_id == GENERIC_PERSISTED_SHOOTING_TARGET_RANGE_RESTRICTION_SOURCE_ID
    assert restriction.violation_code == (
        GENERIC_PERSISTED_SHOOTING_TARGET_RANGE_RESTRICTION_VIOLATION_CODE
    )
    restriction_payload = _json_object(restriction.replay_payload)
    assert restriction_payload["source_effect_kind"] == stratagems.CLOAK_AND_SHADOW_EFFECT_KIND
    assert restriction_payload["max_range_inches"] == stratagems.CLOAK_AND_SHADOW_MAX_RANGE_INCHES


def test_vengeful_sorrow_uses_destroyed_model_context_and_requests_surge_move() -> None:
    state, _corsair_army, _enemy_army = _corsair_state(
        phase=BattlePhase.SHOOTING,
        active_player_id="player-b",
        corsair_x=30.0,
        enemy_x=55.0,
    )
    context = _corsair_stratagem_handler_context(
        state=state,
        player_id="player-a",
        stratagem_id=stratagems.VENGEFUL_SORROW_STRATAGEM_ID,
        handler_id=stratagems.VENGEFUL_SORROW_HANDLER_ID,
        target_unit_id=_CORSAIR_UNIT_ID,
        phase=BattlePhase.SHOOTING,
        trigger_kind=TimingTriggerKind.JUST_AFTER_ENEMY_UNIT_HAS_SHOT,
        trigger_payload={
            JUST_SHOT_UNIT_CONTEXT_KEY: _ENEMY_UNIT_ID,
            HIT_TARGET_UNIT_CONTEXT_KEY: [_CORSAIR_UNIT_ID],
            DESTROYED_TARGET_UNIT_CONTEXT_KEY: [_CORSAIR_UNIT_ID],
            "shooting_player_id": "player-b",
            "attack_sequence_completed_event_id": "event-vengeful-sorrow-shot",
        },
    )

    result = stratagems.apply_vengeful_sorrow(context)

    assert result.reason is None
    request = context.decisions.queue.peek_next()
    assert request.decision_type == "select_triggered_movement"
    replay_payload = _json_object(result.replay_payload)
    assert replay_payload["triggered_movement_request_id"] == request.request_id
    assert replay_payload["effect_kind"] == "vengeful_sorrow"


def test_corsair_stratagem_validators_reject_ineligible_targets_and_phase_state() -> None:
    fight_state, _fight_corsair_army, _fight_enemy_army = _corsair_state(
        phase=BattlePhase.FIGHT,
        active_player_id="player-a",
    )
    started_fight_state = FightPhaseState.start(
        battle_round=fight_state.battle_round,
        active_player_id="player-a",
        policy=RulesetDescriptor.warhammer_40000_eleventh().fight_policy,
        engaged_at_fight_step_start_unit_ids=(_CORSAIR_UNIT_ID, _ENEMY_UNIT_ID),
        fights_first_registry=FightsFirstRegistry(),
    )
    fight_state.fight_phase_state = replace(
        started_fight_state,
        fight_order_state=replace(
            started_fight_state.fight_order_state,
            selected_to_fight_unit_ids=(_CORSAIR_UNIT_ID,),
        ),
    )
    pirates_context = _corsair_stratagem_handler_context(
        state=fight_state,
        stratagem_id=stratagems.PIRATES_DUE_STRATAGEM_ID,
        handler_id=stratagems.PIRATES_DUE_HANDLER_ID,
        target_unit_id=_CORSAIR_UNIT_ID,
        phase=BattlePhase.FIGHT,
        trigger_kind=TimingTriggerKind.DURING_PHASE,
    )

    assert stratagems.validate_pirates_due(pirates_context).reason == (
        "target_already_selected_to_fight"
    )
    assert (
        stratagems.validate_pirates_due(
            replace(
                pirates_context,
                definition=replace(pirates_context.definition, stratagem_id="wrong-stratagem"),
            )
        ).reason
        == "wrong_stratagem"
    )
    assert (
        stratagems.validate_pirates_due(
            replace(
                pirates_context,
                definition=replace(pirates_context.definition, handler_id="wrong-handler"),
            )
        ).reason
        == "wrong_handler"
    )
    assert (
        stratagems.validate_pirates_due(
            replace(
                pirates_context,
                eligibility_context=replace(
                    pirates_context.eligibility_context,
                    trigger_kind=TimingTriggerKind.START_PHASE,
                ),
            )
        ).reason
        == "wrong_timing"
    )
    assert (
        stratagems.validate_pirates_due(
            replace(
                pirates_context,
                eligibility_context=replace(
                    pirates_context.eligibility_context,
                    phase=BattlePhase.SHOOTING,
                ),
            )
        ).reason
        == "wrong_phase"
    )

    enemy_context = _corsair_stratagem_handler_context(
        state=fight_state,
        player_id="player-b",
        stratagem_id=stratagems.PIRATES_DUE_STRATAGEM_ID,
        handler_id=stratagems.PIRATES_DUE_HANDLER_ID,
        target_unit_id=_ENEMY_UNIT_ID,
        phase=BattlePhase.FIGHT,
        trigger_kind=TimingTriggerKind.DURING_PHASE,
    )
    assert stratagems.validate_pirates_due(enemy_context).reason == "detachment_missing"

    outcast_state, _outcast_corsair_army, _outcast_enemy_army = _corsair_state(
        phase=BattlePhase.SHOOTING,
        active_player_id="player-a",
    )
    outcast_context = _corsair_stratagem_handler_context(
        state=outcast_state,
        stratagem_id=stratagems.OUTCAST_AMBUSH_STRATAGEM_ID,
        handler_id=stratagems.OUTCAST_AMBUSH_HANDLER_ID,
        target_unit_id=_CORSAIR_UNIT_ID,
        phase=BattlePhase.SHOOTING,
        trigger_kind=TimingTriggerKind.DURING_PHASE,
    )
    assert stratagems.validate_outcast_ambush(outcast_context).reason == (
        "target_missing_rangers_or_shroud_runners"
    )

    selected_shooting_state, _selected_corsair_army, _selected_enemy_army = _corsair_state(
        phase=BattlePhase.SHOOTING,
        active_player_id="player-a",
        corsair_keywords=("RANGERS", "INFANTRY"),
    )
    selected_shooting_state.shooting_phase_state = ShootingPhaseState(
        battle_round=selected_shooting_state.battle_round,
        active_player_id="player-a",
        selected_unit_ids=(_CORSAIR_UNIT_ID,),
    )
    selected_context = _corsair_stratagem_handler_context(
        state=selected_shooting_state,
        stratagem_id=stratagems.OUTCAST_AMBUSH_STRATAGEM_ID,
        handler_id=stratagems.OUTCAST_AMBUSH_HANDLER_ID,
        target_unit_id=_CORSAIR_UNIT_ID,
        phase=BattlePhase.SHOOTING,
        trigger_kind=TimingTriggerKind.DURING_PHASE,
    )
    assert stratagems.validate_outcast_ambush(selected_context).reason == (
        "target_already_selected_to_shoot"
    )

    breach_state, _breach_corsair_army, _breach_enemy_army = _corsair_state(
        phase=BattlePhase.SHOOTING,
        active_player_id="player-a",
    )
    breach_context = _corsair_stratagem_handler_context(
        state=breach_state,
        stratagem_id=stratagems.INTO_THE_BREACH_STRATAGEM_ID,
        handler_id=stratagems.INTO_THE_BREACH_HANDLER_ID,
        target_unit_id=_CORSAIR_UNIT_ID,
        phase=BattlePhase.SHOOTING,
        trigger_kind=TimingTriggerKind.JUST_AFTER_FRIENDLY_UNIT_HAS_SHOT,
        trigger_payload={
            JUST_SHOT_UNIT_CONTEXT_KEY: _VOIDSTONE_UNIT_ID,
            DESTROYED_ENEMY_UNIT_CONTEXT_KEY: [_ENEMY_UNIT_ID],
        },
    )
    assert stratagems.validate_into_the_breach(breach_context).reason == ("target_not_just_shot")

    non_anhrathe_state, _non_anhrathe_corsair_army, _non_anhrathe_enemy_army = _corsair_state(
        phase=BattlePhase.SHOOTING,
        active_player_id="player-a",
        corsair_keywords=("INFANTRY",),
    )
    non_anhrathe_breach_context = _corsair_stratagem_handler_context(
        state=non_anhrathe_state,
        stratagem_id=stratagems.INTO_THE_BREACH_STRATAGEM_ID,
        handler_id=stratagems.INTO_THE_BREACH_HANDLER_ID,
        target_unit_id=_CORSAIR_UNIT_ID,
        phase=BattlePhase.SHOOTING,
        trigger_kind=TimingTriggerKind.JUST_AFTER_FRIENDLY_UNIT_HAS_SHOT,
        trigger_payload={
            JUST_SHOT_UNIT_CONTEXT_KEY: _CORSAIR_UNIT_ID,
            DESTROYED_ENEMY_UNIT_CONTEXT_KEY: [_ENEMY_UNIT_ID],
        },
    )
    assert stratagems.validate_into_the_breach(non_anhrathe_breach_context).reason == (
        "target_not_anhrathe"
    )

    non_infantry_state, _non_infantry_corsair_army, _non_infantry_enemy_army = _corsair_state(
        phase=BattlePhase.SHOOTING,
        active_player_id="player-b",
        corsair_keywords=("ANHRATHE",),
    )
    cloak_context = _corsair_stratagem_handler_context(
        state=non_infantry_state,
        player_id="player-a",
        stratagem_id=stratagems.CLOAK_AND_SHADOW_STRATAGEM_ID,
        handler_id=stratagems.CLOAK_AND_SHADOW_HANDLER_ID,
        target_unit_id=_CORSAIR_UNIT_ID,
        phase=BattlePhase.SHOOTING,
        trigger_kind=TimingTriggerKind.AFTER_UNIT_SELECTED_AS_TARGET,
        trigger_payload={SELECTED_TARGET_UNIT_CONTEXT_KEY: [_CORSAIR_UNIT_ID]},
    )
    assert stratagems.validate_cloak_and_shadow(cloak_context).reason == "target_not_infantry"

    vengeful_context = _corsair_stratagem_handler_context(
        state=non_infantry_state,
        player_id="player-a",
        stratagem_id=stratagems.VENGEFUL_SORROW_STRATAGEM_ID,
        handler_id=stratagems.VENGEFUL_SORROW_HANDLER_ID,
        target_unit_id=_CORSAIR_UNIT_ID,
        phase=BattlePhase.SHOOTING,
        trigger_kind=TimingTriggerKind.JUST_AFTER_ENEMY_UNIT_HAS_SHOT,
        trigger_payload={DESTROYED_TARGET_UNIT_CONTEXT_KEY: [_CORSAIR_UNIT_ID]},
    )
    assert stratagems.validate_vengeful_sorrow(vengeful_context).reason == "target_not_infantry"

    eligible_vengeful_state, _eligible_corsair_army, _eligible_enemy_army = _corsair_state(
        phase=BattlePhase.SHOOTING,
        active_player_id="player-b",
        corsair_x=30.0,
        enemy_x=55.0,
    )
    missing_destroyed_context = _corsair_stratagem_handler_context(
        state=eligible_vengeful_state,
        player_id="player-a",
        stratagem_id=stratagems.VENGEFUL_SORROW_STRATAGEM_ID,
        handler_id=stratagems.VENGEFUL_SORROW_HANDLER_ID,
        target_unit_id=_CORSAIR_UNIT_ID,
        phase=BattlePhase.SHOOTING,
        trigger_kind=TimingTriggerKind.JUST_AFTER_ENEMY_UNIT_HAS_SHOT,
        trigger_payload={DESTROYED_TARGET_UNIT_CONTEXT_KEY: [_VOIDSTONE_UNIT_ID]},
    )
    assert stratagems.validate_vengeful_sorrow(missing_destroyed_context).reason == (
        "target_models_not_destroyed"
    )
    eligible_vengeful_state.battle_shocked_unit_ids.append(_CORSAIR_UNIT_ID)
    battle_shocked_context = replace(
        missing_destroyed_context,
        eligibility_context=replace(
            missing_destroyed_context.eligibility_context,
            trigger_payload={DESTROYED_TARGET_UNIT_CONTEXT_KEY: [_CORSAIR_UNIT_ID]},
        ),
    )
    assert stratagems.validate_vengeful_sorrow(battle_shocked_context).reason == (
        "target_battle_shocked"
    )

    engaged_state, _engaged_corsair_army, _engaged_enemy_army = _corsair_state(
        phase=BattlePhase.SHOOTING,
        active_player_id="player-b",
        corsair_x=30.0,
        enemy_x=30.5,
    )
    engaged_context = _corsair_stratagem_handler_context(
        state=engaged_state,
        player_id="player-a",
        stratagem_id=stratagems.VENGEFUL_SORROW_STRATAGEM_ID,
        handler_id=stratagems.VENGEFUL_SORROW_HANDLER_ID,
        target_unit_id=_CORSAIR_UNIT_ID,
        phase=BattlePhase.SHOOTING,
        trigger_kind=TimingTriggerKind.JUST_AFTER_ENEMY_UNIT_HAS_SHOT,
        trigger_payload={DESTROYED_TARGET_UNIT_CONTEXT_KEY: [_CORSAIR_UNIT_ID]},
    )
    assert stratagems.validate_vengeful_sorrow(engaged_context).reason == (
        "target_within_engagement_range"
    )


def test_lethal_ruse_handles_non_anhrathe_and_rejects_invalid_enemy_selection() -> None:
    non_anhrathe_state, _corsair_army, _enemy_army = _corsair_state(
        phase=BattlePhase.MOVEMENT,
        active_player_id="player-a",
        corsair_keywords=("INFANTRY",),
    )
    non_anhrathe_context = _corsair_stratagem_handler_context(
        state=non_anhrathe_state,
        stratagem_id=stratagems.LETHAL_RUSE_STRATAGEM_ID,
        handler_id=stratagems.LETHAL_RUSE_HANDLER_ID,
        target_unit_id=_CORSAIR_UNIT_ID,
        phase=BattlePhase.MOVEMENT,
        trigger_kind=TimingTriggerKind.JUST_AFTER_FRIENDLY_UNIT_FALLS_BACK,
        trigger_payload={JUST_FELL_BACK_UNIT_CONTEXT_KEY: _CORSAIR_UNIT_ID},
    )

    result = stratagems.apply_lethal_ruse(non_anhrathe_context)

    assert result.reason is None
    assert result.replay_payload is not None
    replay_payload = _json_object(result.replay_payload)
    assert replay_payload["mortal_wound_resolution"] is None

    wrong_target_context = _corsair_stratagem_handler_context(
        state=non_anhrathe_state,
        stratagem_id=stratagems.LETHAL_RUSE_STRATAGEM_ID,
        handler_id=stratagems.LETHAL_RUSE_HANDLER_ID,
        target_unit_id=_CORSAIR_UNIT_ID,
        phase=BattlePhase.MOVEMENT,
        trigger_kind=TimingTriggerKind.JUST_AFTER_FRIENDLY_UNIT_FALLS_BACK,
        trigger_payload={JUST_FELL_BACK_UNIT_CONTEXT_KEY: _VOIDSTONE_UNIT_ID},
    )
    assert stratagems.validate_lethal_ruse(wrong_target_context).reason == (
        "target_not_fell_back_unit"
    )

    selected_not_engaged_state, _selected_corsair_army, _selected_enemy_army = _corsair_state(
        phase=BattlePhase.MOVEMENT,
        active_player_id="player-a",
        corsair_x=30.0,
        enemy_x=31.0,
    )
    selected_not_engaged_context = _corsair_stratagem_handler_context(
        state=selected_not_engaged_state,
        stratagem_id=stratagems.LETHAL_RUSE_STRATAGEM_ID,
        handler_id=stratagems.LETHAL_RUSE_HANDLER_ID,
        target_unit_id=_CORSAIR_UNIT_ID,
        phase=BattlePhase.MOVEMENT,
        trigger_kind=TimingTriggerKind.JUST_AFTER_FRIENDLY_UNIT_FALLS_BACK,
        trigger_payload={
            JUST_FELL_BACK_UNIT_CONTEXT_KEY: _CORSAIR_UNIT_ID,
            ENGAGED_ENEMY_UNIT_IDS_CONTEXT_KEY: [_ENEMY_UNIT_ID],
        },
        effect_selection={
            "effect_selection_kind": ENGAGED_ENEMY_UNIT_EFFECT_SELECTION_KIND,
            ENGAGED_ENEMY_UNIT_CONTEXT_KEY: _VOIDSTONE_UNIT_ID,
        },
    )
    assert stratagems.validate_lethal_ruse(selected_not_engaged_context).reason == (
        "selected_enemy_not_start_engaged"
    )

    friendly_selected_context = _corsair_stratagem_handler_context(
        state=selected_not_engaged_state,
        stratagem_id=stratagems.LETHAL_RUSE_STRATAGEM_ID,
        handler_id=stratagems.LETHAL_RUSE_HANDLER_ID,
        target_unit_id=_CORSAIR_UNIT_ID,
        phase=BattlePhase.MOVEMENT,
        trigger_kind=TimingTriggerKind.JUST_AFTER_FRIENDLY_UNIT_FALLS_BACK,
        trigger_payload={
            JUST_FELL_BACK_UNIT_CONTEXT_KEY: _CORSAIR_UNIT_ID,
            ENGAGED_ENEMY_UNIT_IDS_CONTEXT_KEY: [_VOIDSTONE_UNIT_ID],
        },
        effect_selection={
            "effect_selection_kind": ENGAGED_ENEMY_UNIT_EFFECT_SELECTION_KIND,
            ENGAGED_ENEMY_UNIT_CONTEXT_KEY: _VOIDSTONE_UNIT_ID,
        },
    )
    assert stratagems.validate_lethal_ruse(friendly_selected_context).reason == (
        "selected_unit_not_enemy"
    )


def test_lethal_ruse_request_option_carries_engaged_enemy_effect_selection() -> None:
    state, _corsair_army, _enemy_army = _corsair_state(
        phase=BattlePhase.MOVEMENT,
        active_player_id="player-a",
        corsair_x=30.0,
        enemy_x=31.0,
    )
    state.gain_command_points(
        player_id="player-a",
        amount=3,
        source_id="phase17g-corsair-lethal-ruse-request-cp",
        source_kind=CommandPointSourceKind.OTHER,
        cap_exempt=True,
    )
    decisions = DecisionController()
    record = _corsair_stratagem_record(stratagems.LETHAL_RUSE_STRATAGEM_ID)
    status = request_stratagem_use(
        state=state,
        decisions=decisions,
        catalog_records=(record,),
        context=StratagemEligibilityContext.from_state(
            state=state,
            player_id="player-a",
            trigger_kind=TimingTriggerKind.JUST_AFTER_FRIENDLY_UNIT_FALLS_BACK,
            trigger_payload={
                JUST_FELL_BACK_UNIT_CONTEXT_KEY: _CORSAIR_UNIT_ID,
                ENGAGED_ENEMY_UNIT_IDS_CONTEXT_KEY: [_ENEMY_UNIT_ID],
            },
        ),
    )
    request = _decision_request(status)

    assert request.decision_type == STRATAGEM_DECISION_TYPE
    assert len(request.options) == 1
    option = request.options[0]
    assert option.option_id == (
        "use-stratagem:aeldari:corsair-coterie:lethal-ruse:target:"
        "army-a:corsairs:effect:engaged_enemy_unit:army-b:enemy-raiders"
    )
    option_payload = _json_object(option.payload)
    effect_selection = _json_object(option_payload["effect_selection"])
    assert effect_selection == {
        "effect_selection_kind": ENGAGED_ENEMY_UNIT_EFFECT_SELECTION_KIND,
        ENGAGED_ENEMY_UNIT_CONTEXT_KEY: _ENEMY_UNIT_ID,
    }

    use_record = apply_stratagem_decision(
        state=state,
        result=DecisionResult.for_request(
            result_id="phase17g-corsair-lethal-ruse-request-result",
            request=request,
            selected_option_id=option.option_id,
        ),
        decisions=decisions,
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(),
        army_catalog=ArmyCatalog.phase9a_canonical_content_pack(),
        stratagem_handler_registry=StratagemHandlerRegistry.from_bindings(
            manifest.runtime_contribution().stratagem_handler_bindings
        ),
    )

    assert use_record.effect_selection == effect_selection
    assert use_record.affected_unit_instance_ids == (_CORSAIR_UNIT_ID, _ENEMY_UNIT_ID)
    lethal_effects = tuple(
        effect.effect_payload
        for effect in state.persisting_effects_for_unit(_CORSAIR_UNIT_ID)
        if isinstance(effect.effect_payload, dict)
        and effect.effect_payload.get("source_effect_kind") == stratagems.LETHAL_RUSE_EFFECT_KIND
    )
    assert len(lethal_effects) == 1
    lethal_effect = lethal_effects[0]
    assert lethal_effect["effect_kind"] == "charge_after_fall_back_allowed"
    assert lethal_effect["stratagem_id"] == stratagems.LETHAL_RUSE_STRATAGEM_ID
    assert lethal_effect["stratagem_use_id"] == use_record.use_id
    assert isinstance(lethal_effect["generic_rule_effect"], dict)


def test_lethal_ruse_rejects_malformed_engaged_enemy_effect_selection_payloads() -> None:
    state, _corsair_army, _enemy_army = _corsair_state(
        phase=BattlePhase.MOVEMENT,
        active_player_id="player-a",
        corsair_x=30.0,
        enemy_x=31.0,
    )
    state.gain_command_points(
        player_id="player-a",
        amount=3,
        source_id="phase17g-corsair-lethal-ruse-invalid-selection-cp",
        source_kind=CommandPointSourceKind.OTHER,
        cap_exempt=True,
    )
    decisions = DecisionController()
    status = request_stratagem_use(
        state=state,
        decisions=decisions,
        catalog_records=(_corsair_stratagem_record(stratagems.LETHAL_RUSE_STRATAGEM_ID),),
        context=StratagemEligibilityContext.from_state(
            state=state,
            player_id="player-a",
            trigger_kind=TimingTriggerKind.JUST_AFTER_FRIENDLY_UNIT_FALLS_BACK,
            trigger_payload={
                JUST_FELL_BACK_UNIT_CONTEXT_KEY: _CORSAIR_UNIT_ID,
                ENGAGED_ENEMY_UNIT_IDS_CONTEXT_KEY: [_ENEMY_UNIT_ID],
            },
        ),
    )
    request = _decision_request(status)
    option = request.options[0]
    option_payload = _json_object(option.payload)

    for result_id, effect_selection, reason in (
        (
            "phase17g-corsair-lethal-ruse-missing-engaged-enemy",
            {"effect_selection_kind": ENGAGED_ENEMY_UNIT_EFFECT_SELECTION_KIND},
            f"{ENGAGED_ENEMY_UNIT_CONTEXT_KEY}_required",
        ),
        (
            "phase17g-corsair-lethal-ruse-wrong-effect-kind",
            {
                "effect_selection_kind": "wrong-kind",
                ENGAGED_ENEMY_UNIT_CONTEXT_KEY: _ENEMY_UNIT_ID,
            },
            "effect_selection_kind_mismatch",
        ),
        (
            "phase17g-corsair-lethal-ruse-enemy-not-in-context",
            {
                "effect_selection_kind": ENGAGED_ENEMY_UNIT_EFFECT_SELECTION_KIND,
                ENGAGED_ENEMY_UNIT_CONTEXT_KEY: "army-b:other-enemy",
            },
            "engaged_enemy_unit_not_in_trigger_context",
        ),
    ):
        with pytest.raises(GameLifecycleError, match=reason):
            apply_stratagem_decision(
                state=state,
                result=DecisionResult(
                    result_id=result_id,
                    request_id=request.request_id,
                    decision_type=request.decision_type,
                    actor_id=request.actor_id,
                    selected_option_id=option.option_id,
                    payload=validate_json_value(
                        {**option_payload, "effect_selection": effect_selection}
                    ),
                ),
                decisions=decisions,
                ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(),
                army_catalog=ArmyCatalog.phase9a_canonical_content_pack(),
                stratagem_handler_registry=StratagemHandlerRegistry.from_bindings(
                    manifest.runtime_contribution().stratagem_handler_bindings
                ),
            )


def test_outcast_ambush_modifier_noops_and_stacks_existing_rapid_fire() -> None:
    state, _corsair_army, _enemy_army = _corsair_state(
        phase=BattlePhase.SHOOTING,
        active_player_id="player-a",
        corsair_keywords=("RANGERS", "INFANTRY"),
    )
    base_profile = _corsair_test_weapon_profile(ap=0)
    base_context = WeaponProfileModifierContext(
        state=state,
        source_phase=BattlePhase.SHOOTING,
        attacking_unit_instance_id=_CORSAIR_UNIT_ID,
        attacker_model_instance_id=f"{_CORSAIR_UNIT_ID}:model-001",
        target_unit_instance_id=_ENEMY_UNIT_ID,
        weapon_profile=base_profile,
    )

    assert stratagems.outcast_ambush_weapon_profile_modifier(base_context) == base_profile
    with pytest.raises(GameLifecycleError, match="weapon profile modifier context"):
        stratagems.outcast_ambush_weapon_profile_modifier(
            cast(WeaponProfileModifierContext, object())
        )

    stratagems.apply_outcast_ambush(
        _corsair_stratagem_handler_context(
            state=state,
            stratagem_id=stratagems.OUTCAST_AMBUSH_STRATAGEM_ID,
            handler_id=stratagems.OUTCAST_AMBUSH_HANDLER_ID,
            target_unit_id=_CORSAIR_UNIT_ID,
            phase=BattlePhase.SHOOTING,
            trigger_kind=TimingTriggerKind.DURING_PHASE,
        )
    )
    assert (
        stratagems.outcast_ambush_weapon_profile_modifier(
            replace(base_context, source_phase=BattlePhase.FIGHT)
        )
        == base_profile
    )

    rapid_fire_profile = replace(
        base_profile,
        abilities=(AbilityDescriptor.rapid_fire(2),),
        keywords=(WeaponKeyword.RAPID_FIRE,),
    )
    modified = stratagems.outcast_ambush_weapon_profile_modifier(
        replace(base_context, weapon_profile=rapid_fire_profile)
    )
    rapid_fire_ability = next(
        ability for ability in modified.abilities if ability.ability_kind is AbilityKind.RAPID_FIRE
    )

    assert rapid_fire_ability.parameters[0].value == 3
    assert modified.armor_penetration.final == -1
    assert stratagems.OUTCAST_AMBUSH_WEAPON_PROFILE_MODIFIER_ID in modified.source_ids


def test_cloak_and_shadow_restriction_noops_when_close_or_unmodified_and_stays_strict() -> None:
    state, _corsair_army, _enemy_army = _corsair_state(
        phase=BattlePhase.SHOOTING,
        active_player_id="player-b",
        corsair_x=30.0,
        enemy_x=40.0,
    )
    base_restriction_context = ShootingTargetRestrictionContext(
        state=state,
        player_id="player-b",
        battle_round=state.battle_round,
        attacking_unit_instance_id=_ENEMY_UNIT_ID,
        attacker_model_instance_id=f"{_ENEMY_UNIT_ID}:model-001",
        target_unit_instance_id=_CORSAIR_UNIT_ID,
    )

    assert generic_persisted_shooting_target_range_restriction(base_restriction_context) is None
    with pytest.raises(GameLifecycleError, match="shooting target context"):
        generic_persisted_shooting_target_range_restriction(
            cast(ShootingTargetRestrictionContext, object())
        )

    apply_context = _corsair_stratagem_handler_context(
        state=state,
        player_id="player-a",
        stratagem_id=stratagems.CLOAK_AND_SHADOW_STRATAGEM_ID,
        handler_id=stratagems.CLOAK_AND_SHADOW_HANDLER_ID,
        target_unit_id=_CORSAIR_UNIT_ID,
        phase=BattlePhase.SHOOTING,
        trigger_kind=TimingTriggerKind.AFTER_UNIT_SELECTED_AS_TARGET,
        trigger_payload={SELECTED_TARGET_UNIT_CONTEXT_KEY: [_CORSAIR_UNIT_ID]},
    )
    assert stratagems.apply_cloak_and_shadow(apply_context).reason is None
    assert generic_persisted_shooting_target_range_restriction(base_restriction_context) is None

    assert (
        generic_persisted_shooting_target_range_restriction(
            replace(base_restriction_context, attacker_model_instance_id=None)
        )
        is None
    )

    state.battlefield_state = None
    with pytest.raises(GameLifecycleError, match="requires battlefield state"):
        generic_persisted_shooting_target_range_restriction(base_restriction_context)


@pytest.mark.parametrize("dead_side", ["attacker", "target"])
def test_generic_persisted_shooting_target_range_restriction_ignores_dead_model_placements(
    dead_side: str,
) -> None:
    state, corsair_army, enemy_army = _corsair_state(
        phase=BattlePhase.SHOOTING,
        active_player_id="player-b",
        corsair_x=30.0,
        enemy_x=40.0,
    )
    target_unit = corsair_army.units[0]
    attacker_unit = enemy_army.units[0]

    apply_context = _corsair_stratagem_handler_context(
        state=state,
        player_id="player-a",
        stratagem_id=stratagems.CLOAK_AND_SHADOW_STRATAGEM_ID,
        handler_id=stratagems.CLOAK_AND_SHADOW_HANDLER_ID,
        target_unit_id=target_unit.unit_instance_id,
        phase=BattlePhase.SHOOTING,
        trigger_kind=TimingTriggerKind.AFTER_UNIT_SELECTED_AS_TARGET,
        trigger_payload={SELECTED_TARGET_UNIT_CONTEXT_KEY: [target_unit.unit_instance_id]},
    )
    assert stratagems.apply_cloak_and_shadow(apply_context).reason is None
    _replace_first_persisting_effect_payload(
        state,
        {
            "effect_kind": GENERIC_RULE_EFFECT_KIND,
            "source_id": "test-source:wreathed-in-shadows-range",
            "clause_id": "test-clause:wreathed-in-shadows-range",
            "effect": {
                "kind": "set_contextual_status",
                "source_span": {"start": 0, "end": 1, "text": "x"},
                "parameters": [
                    {"key": "status", "value": "shooting_target_range_restriction"},
                    {"key": "targeting_max_range_inches", "value": 18.0},
                    {"key": "source_effect_kind", "value": "source_backed_range_limit"},
                ],
            },
        },
    )

    if dead_side == "attacker":
        attacker_unit = _unit_with_second_model_and_dead_model(
            attacker_unit,
            dead_model_index=0,
        )
        _replace_unit_instance_in_state(state=state, replacement=attacker_unit)
        _set_unit_model_x_positions(
            state=state,
            army_id="army-b",
            player_id="player-b",
            unit=attacker_unit,
            model_xs=(10.0, 40.0),
        )
        _set_unit_model_x_positions(
            state=state,
            army_id="army-a",
            player_id="player-a",
            unit=target_unit,
            model_xs=(10.4,),
        )
    elif dead_side == "target":
        target_unit = _unit_with_second_model_and_dead_model(target_unit, dead_model_index=0)
        _replace_unit_instance_in_state(state=state, replacement=target_unit)
        _set_unit_model_x_positions(
            state=state,
            army_id="army-b",
            player_id="player-b",
            unit=attacker_unit,
            model_xs=(10.0,),
        )
        _set_unit_model_x_positions(
            state=state,
            army_id="army-a",
            player_id="player-a",
            unit=target_unit,
            model_xs=(10.4, 40.0),
        )
    else:
        raise AssertionError(f"Unsupported dead-side fixture {dead_side}.")

    restriction_context = ShootingTargetRestrictionContext(
        state=state,
        player_id="player-b",
        battle_round=state.battle_round,
        attacking_unit_instance_id=attacker_unit.unit_instance_id,
        attacker_model_instance_id=None,
        target_unit_instance_id=target_unit.unit_instance_id,
    )

    restriction = generic_persisted_shooting_target_range_restriction(restriction_context)

    assert restriction is not None
    assert (
        restriction.violation_code
        == GENERIC_PERSISTED_SHOOTING_TARGET_RANGE_RESTRICTION_VIOLATION_CODE
    )


def test_generic_persisted_target_range_restriction_rejects_malformed_effect_payloads() -> None:
    state, _corsair_army, _enemy_army = _corsair_state(
        phase=BattlePhase.SHOOTING,
        active_player_id="player-b",
        corsair_x=30.0,
        enemy_x=55.0,
    )
    apply_context = _corsair_stratagem_handler_context(
        state=state,
        player_id="player-a",
        stratagem_id=stratagems.CLOAK_AND_SHADOW_STRATAGEM_ID,
        handler_id=stratagems.CLOAK_AND_SHADOW_HANDLER_ID,
        target_unit_id=_CORSAIR_UNIT_ID,
        phase=BattlePhase.SHOOTING,
        trigger_kind=TimingTriggerKind.AFTER_UNIT_SELECTED_AS_TARGET,
        trigger_payload={SELECTED_TARGET_UNIT_CONTEXT_KEY: [_CORSAIR_UNIT_ID]},
    )
    assert stratagems.apply_cloak_and_shadow(apply_context).reason is None
    restriction_context = ShootingTargetRestrictionContext(
        state=state,
        player_id="player-b",
        battle_round=state.battle_round,
        attacking_unit_instance_id=_ENEMY_UNIT_ID,
        attacker_model_instance_id=f"{_ENEMY_UNIT_ID}:model-001",
        target_unit_instance_id=_CORSAIR_UNIT_ID,
    )

    _replace_first_persisting_effect_payload(state, "not-an-object")
    assert generic_persisted_shooting_target_range_restriction(restriction_context) is None

    _replace_first_persisting_effect_payload(
        state,
        {"effect_kind": "other-effect", "targeting_max_range_inches": 18.0},
    )
    with pytest.raises(GameLifecycleError, match="requires smokescreen effect_kind"):
        generic_persisted_shooting_target_range_restriction(restriction_context)

    _replace_first_persisting_effect_payload(
        state,
        {"effect_kind": SMOKESCREEN_EFFECT_KIND, "targeting_max_range_inches": True},
    )
    with pytest.raises(GameLifecycleError, match="max range must be numeric"):
        generic_persisted_shooting_target_range_restriction(restriction_context)

    _replace_first_persisting_effect_payload(
        state,
        {"effect_kind": SMOKESCREEN_EFFECT_KIND, "targeting_max_range_inches": 0.0},
    )
    with pytest.raises(GameLifecycleError, match="max range must be positive"):
        generic_persisted_shooting_target_range_restriction(restriction_context)

    _replace_first_persisting_effect_payload(
        state,
        {"effect_kind": SMOKESCREEN_EFFECT_KIND, "targeting_max_range_inches": 18.0},
    )
    restriction = generic_persisted_shooting_target_range_restriction(restriction_context)
    assert restriction is not None
    assert _json_object(restriction.replay_payload)["source_effect_kind"] is None

    _replace_first_persisting_effect_payload(
        state,
        {
            "effect_kind": GENERIC_RULE_EFFECT_KIND,
            "source_id": "test-source:generic-range",
            "clause_id": "test-clause:generic-range",
            "effect": {
                "kind": "set_contextual_status",
                "source_span": {"start": 0, "end": 1, "text": "x"},
                "parameters": [
                    {"key": "status", "value": "shooting_target_range_restriction"},
                    {"key": "targeting_max_range_inches", "value": 18.0},
                    {"key": "source_effect_kind", "value": "source_backed_range_limit"},
                ],
            },
        },
    )
    generic_restriction = generic_persisted_shooting_target_range_restriction(
        replace(restriction_context, attacker_model_instance_id=None)
    )
    assert generic_restriction is not None
    generic_payload = _json_object(generic_restriction.replay_payload)
    assert generic_payload["persisting_effect_kind"] == GENERIC_RULE_EFFECT_KIND
    assert generic_payload["source_effect_kind"] == "source_backed_range_limit"
    assert generic_payload["attacker_model_instance_id"] is None
    assert generic_payload["attacking_unit_instance_id"] == _ENEMY_UNIT_ID

    _replace_first_persisting_effect_payload(
        state,
        {
            "effect_kind": SMOKESCREEN_EFFECT_KIND,
            "targeting_max_range_inches": 18.0,
            "source_effect_kind": 1,
        },
    )
    with pytest.raises(GameLifecycleError, match="payload source_effect_kind must be a string"):
        generic_persisted_shooting_target_range_restriction(restriction_context)

    _replace_first_persisting_effect_payload(
        state,
        {"effect_kind": SMOKESCREEN_EFFECT_KIND, "targeting_max_range_inches": 18.0},
    )
    battlefield = state.battlefield_state
    assert battlefield is not None
    state.battlefield_state = battlefield.with_removed_models((f"{_ENEMY_UNIT_ID}:model-001",))
    with pytest.raises(GameLifecycleError, match="attacking unit is not placed"):
        generic_persisted_shooting_target_range_restriction(restriction_context)


def test_corsair_stratagem_guardrails_raise_on_drifted_internal_context() -> None:
    state, _corsair_army, _enemy_army = _corsair_state(
        phase=BattlePhase.MOVEMENT,
        active_player_id="player-a",
    )
    context = _corsair_stratagem_handler_context(
        state=state,
        stratagem_id=stratagems.LETHAL_RUSE_STRATAGEM_ID,
        handler_id=stratagems.LETHAL_RUSE_HANDLER_ID,
        target_unit_id=_CORSAIR_UNIT_ID,
        phase=BattlePhase.MOVEMENT,
        trigger_kind=TimingTriggerKind.JUST_AFTER_FRIENDLY_UNIT_FALLS_BACK,
        trigger_payload={JUST_FELL_BACK_UNIT_CONTEXT_KEY: _CORSAIR_UNIT_ID},
    )
    validate_corsair_stratagem = vars(stratagems)["_validate_corsair_stratagem"]
    active_player_id = vars(stratagems)["_active_player_id"]
    target_unit_id = vars(stratagems)["_target_unit_id"]
    trigger_payload = vars(stratagems)["_trigger_payload"]
    fell_back_unit_id = vars(stratagems)["_fell_back_unit_id"]
    shot_unit_id = vars(stratagems)["_shot_unit_id"]
    engaged_enemy_unit_id = vars(stratagems)["_engaged_enemy_unit_id"]
    engaged_enemy_unit_ids = vars(stratagems)["_engaged_enemy_unit_ids"]
    trigger_event_id = vars(stratagems)["_trigger_event_id"]
    improved_ap = vars(stratagems)["_improved_ap"]
    abilities_with_rapid_fire_one = vars(stratagems)["_abilities_with_rapid_fire_one"]
    ability_integer_value = vars(stratagems)["_ability_integer_value"]
    unit_has_effect = vars(stratagems)["_unit_has_effect"]
    army_for_player = vars(stratagems)["_army_for_player"]
    unit_in_army = vars(stratagems)["_unit_in_army"]
    unit_by_id_for_state = vars(stratagems)["_unit_by_id_for_state"]
    unit_owner = vars(stratagems)["_unit_owner"]
    model_instance_by_id = vars(stratagems)["_model_instance_by_id"]
    armies_for_state = vars(stratagems)["_armies_for_state"]
    validate_identifier = vars(stratagems)["_validate_identifier"]

    assert stratagems.apply_pirates_due(context).reason == "wrong_stratagem"
    assert (
        stratagems.apply_lethal_ruse(
            replace(
                context,
                eligibility_context=replace(
                    context.eligibility_context,
                    active_player_id="player-b",
                ),
            )
        ).reason
        == "wrong_active_player"
    )
    assert stratagems.apply_outcast_ambush(context).reason == "wrong_stratagem"
    assert stratagems.apply_into_the_breach(context).reason == "wrong_stratagem"
    assert stratagems.apply_cloak_and_shadow(context).reason == "wrong_stratagem"
    assert stratagems.apply_vengeful_sorrow(context).reason == "wrong_stratagem"

    with pytest.raises(GameLifecycleError, match="requires a Stratagem handler context"):
        validate_corsair_stratagem(
            object(),
            stratagem_id=stratagems.LETHAL_RUSE_STRATAGEM_ID,
            handler_id=stratagems.LETHAL_RUSE_HANDLER_ID,
            trigger_kind=TimingTriggerKind.JUST_AFTER_FRIENDLY_UNIT_FALLS_BACK,
            phase=BattlePhase.MOVEMENT,
            require_active_player=True,
        )

    no_active_state, _no_active_corsair_army, _no_active_enemy_army = _corsair_state(
        phase=BattlePhase.MOVEMENT,
        active_player_id="player-a",
    )
    no_active_state.active_player_id = None
    with pytest.raises(GameLifecycleError, match="requires an active player"):
        active_player_id(replace(context, state=no_active_state))

    with pytest.raises(GameLifecycleError, match="requires a target unit"):
        target_unit_id(
            replace(
                context,
                target_binding=StratagemTargetBinding(
                    target_kind=StratagemTargetKind.NONE,
                    target_player_id=None,
                    target_unit_instance_id=None,
                ),
            )
        )

    with pytest.raises(GameLifecycleError, match="requires trigger context payload"):
        trigger_payload(
            replace(
                context,
                eligibility_context=replace(context.eligibility_context, trigger_payload="bad"),
            )
        )
    with pytest.raises(GameLifecycleError, match="Fall Back context is missing unit id"):
        fell_back_unit_id(
            replace(
                context,
                eligibility_context=replace(context.eligibility_context, trigger_payload={}),
            )
        )
    with pytest.raises(GameLifecycleError, match="shot context is missing unit id"):
        shot_unit_id(
            replace(
                context,
                eligibility_context=replace(context.eligibility_context, trigger_payload={}),
            )
        )

    with pytest.raises(GameLifecycleError, match="requires engaged enemy effect selection"):
        engaged_enemy_unit_id(
            replace(
                context,
                use_record=replace(context.use_record, effect_selection=None),
            )
        )
    with pytest.raises(GameLifecycleError, match="effect selection kind drift"):
        engaged_enemy_unit_id(
            replace(
                context,
                use_record=replace(
                    context.use_record,
                    effect_selection={"effect_selection_kind": "wrong-kind"},
                ),
            )
        )
    with pytest.raises(GameLifecycleError, match="effect selection is missing enemy unit"):
        engaged_enemy_unit_id(
            replace(
                context,
                use_record=replace(
                    context.use_record,
                    effect_selection={
                        "effect_selection_kind": ENGAGED_ENEMY_UNIT_EFFECT_SELECTION_KIND,
                    },
                ),
            )
        )
    assert (
        engaged_enemy_unit_ids(
            replace(
                context,
                eligibility_context=replace(
                    context.eligibility_context,
                    trigger_payload={ENGAGED_ENEMY_UNIT_IDS_CONTEXT_KEY: "bad"},
                ),
            )
        )
        == ()
    )
    assert trigger_event_id(context) == context.use_record.use_id

    with pytest.raises(GameLifecycleError, match="AP modifier requires a CharacteristicValue"):
        improved_ap(object())

    non_rapid_fire_abilities = abilities_with_rapid_fire_one((AbilityDescriptor.lethal_hits(),))
    assert {ability.ability_kind for ability in non_rapid_fire_abilities} == {
        AbilityKind.LETHAL_HITS,
        AbilityKind.RAPID_FIRE,
    }
    invalid_rapid_fire = _invalid_ability_descriptor(parameters=())
    with pytest.raises(GameLifecycleError, match="requires one value parameter"):
        ability_integer_value(invalid_rapid_fire)
    invalid_rapid_fire = _invalid_ability_descriptor(parameters=(AbilityParameter("other", 1),))
    with pytest.raises(GameLifecycleError, match="parameter drift"):
        ability_integer_value(invalid_rapid_fire)
    invalid_rapid_fire = _invalid_ability_descriptor(parameters=(AbilityParameter("value", "one"),))
    with pytest.raises(GameLifecycleError, match="value must be an integer"):
        ability_integer_value(invalid_rapid_fire)

    with pytest.raises(GameLifecycleError, match="effect lookup requires GameState"):
        unit_has_effect(object(), unit_instance_id=_CORSAIR_UNIT_ID, effect_kind="effect")
    with pytest.raises(GameLifecycleError, match="player army is unknown"):
        army_for_player(
            replace(context, use_record=replace(context.use_record, player_id="unknown"))
        )
    with pytest.raises(GameLifecycleError, match="target unit is not in the selected army"):
        unit_in_army(army=_enemy_army, unit_instance_id=_CORSAIR_UNIT_ID)
    with pytest.raises(GameLifecycleError, match="unit lookup requires GameState"):
        unit_by_id_for_state(object(), unit_instance_id=_CORSAIR_UNIT_ID)
    with pytest.raises(GameLifecycleError, match="unit is unknown"):
        unit_by_id_for_state(state, unit_instance_id="unknown-unit")
    with pytest.raises(GameLifecycleError, match="unit owner is unknown"):
        unit_owner(context, unit_instance_id="unknown-unit")
    with pytest.raises(GameLifecycleError, match="model is unknown"):
        model_instance_by_id(state, "unknown-model")
    with pytest.raises(GameLifecycleError, match="army lookup requires GameState"):
        armies_for_state(object())
    with pytest.raises(GameLifecycleError, match="must be a string"):
        validate_identifier("test", object())
    with pytest.raises(GameLifecycleError, match="must not be empty"):
        validate_identifier("test", " ")

    non_aeldari_state, non_aeldari_army, _non_aeldari_enemy_army = _corsair_state(
        phase=BattlePhase.FIGHT,
        active_player_id="player-a",
    )
    non_aeldari_unit = replace(
        _unit_by_id(non_aeldari_state, _CORSAIR_UNIT_ID),
        faction_keywords=("OPFOR",),
    )
    non_aeldari_state.army_definitions[0] = replace(
        non_aeldari_army,
        units=(non_aeldari_unit, *non_aeldari_army.units[1:]),
    )
    assert (
        stratagems.validate_pirates_due(
            _corsair_stratagem_handler_context(
                state=non_aeldari_state,
                stratagem_id=stratagems.PIRATES_DUE_STRATAGEM_ID,
                handler_id=stratagems.PIRATES_DUE_HANDLER_ID,
                target_unit_id=_CORSAIR_UNIT_ID,
                phase=BattlePhase.FIGHT,
                trigger_kind=TimingTriggerKind.DURING_PHASE,
            )
        ).reason
        == "target_not_aeldari"
    )

    far_from_objective_state, _far_corsair_army, _far_enemy_army = _corsair_state(
        phase=BattlePhase.SHOOTING,
        active_player_id="player-b",
        corsair_x=55.0,
        enemy_x=5.0,
    )
    assert (
        stratagems.validate_cloak_and_shadow(
            _corsair_stratagem_handler_context(
                state=far_from_objective_state,
                stratagem_id=stratagems.CLOAK_AND_SHADOW_STRATAGEM_ID,
                handler_id=stratagems.CLOAK_AND_SHADOW_HANDLER_ID,
                target_unit_id=_CORSAIR_UNIT_ID,
                phase=BattlePhase.SHOOTING,
                trigger_kind=TimingTriggerKind.AFTER_UNIT_SELECTED_AS_TARGET,
                trigger_payload={SELECTED_TARGET_UNIT_CONTEXT_KEY: [_CORSAIR_UNIT_ID]},
            )
        ).reason
        == "target_not_within_controlled_objective"
    )

    no_mission_state, _no_mission_corsair_army, _no_mission_enemy_army = _corsair_state(
        phase=BattlePhase.SHOOTING,
        active_player_id="player-b",
    )
    no_mission_state.mission_setup = None
    with pytest.raises(GameLifecycleError, match="objective checks require mission setup"):
        stratagems.validate_cloak_and_shadow(
            _corsair_stratagem_handler_context(
                state=no_mission_state,
                stratagem_id=stratagems.CLOAK_AND_SHADOW_STRATAGEM_ID,
                handler_id=stratagems.CLOAK_AND_SHADOW_HANDLER_ID,
                target_unit_id=_CORSAIR_UNIT_ID,
                phase=BattlePhase.SHOOTING,
                trigger_kind=TimingTriggerKind.AFTER_UNIT_SELECTED_AS_TARGET,
                trigger_payload={SELECTED_TARGET_UNIT_CONTEXT_KEY: [_CORSAIR_UNIT_ID]},
            )
        )

    unplaced_target_state, _unplaced_corsair_army, _unplaced_enemy_army = _corsair_state(
        phase=BattlePhase.SHOOTING,
        active_player_id="player-b",
        corsair_x=30.0,
        enemy_x=55.0,
    )
    apply_result = stratagems.apply_cloak_and_shadow(
        _corsair_stratagem_handler_context(
            state=unplaced_target_state,
            stratagem_id=stratagems.CLOAK_AND_SHADOW_STRATAGEM_ID,
            handler_id=stratagems.CLOAK_AND_SHADOW_HANDLER_ID,
            target_unit_id=_CORSAIR_UNIT_ID,
            phase=BattlePhase.SHOOTING,
            trigger_kind=TimingTriggerKind.AFTER_UNIT_SELECTED_AS_TARGET,
            trigger_payload={SELECTED_TARGET_UNIT_CONTEXT_KEY: [_CORSAIR_UNIT_ID]},
        )
    )
    assert apply_result.reason is None
    _remove_unit_placement(unplaced_target_state, _CORSAIR_UNIT_ID)
    with pytest.raises(GameLifecycleError, match="target unit is not placed"):
        generic_persisted_shooting_target_range_restriction(
            ShootingTargetRestrictionContext(
                state=unplaced_target_state,
                player_id="player-b",
                battle_round=unplaced_target_state.battle_round,
                attacking_unit_instance_id=_ENEMY_UNIT_ID,
                attacker_model_instance_id=f"{_ENEMY_UNIT_ID}:model-001",
                target_unit_instance_id=_CORSAIR_UNIT_ID,
            )
        )

    unplaced_engagement_state, _unplaced_engagement_corsair, _unplaced_engagement_enemy = (
        _corsair_state(
            phase=BattlePhase.SHOOTING,
            active_player_id="player-b",
        )
    )
    _remove_unit_placement(unplaced_engagement_state, _CORSAIR_UNIT_ID)
    with pytest.raises(GameLifecycleError, match="target unit is not placed"):
        stratagems.validate_vengeful_sorrow(
            _corsair_stratagem_handler_context(
                state=unplaced_engagement_state,
                stratagem_id=stratagems.VENGEFUL_SORROW_STRATAGEM_ID,
                handler_id=stratagems.VENGEFUL_SORROW_HANDLER_ID,
                target_unit_id=_CORSAIR_UNIT_ID,
                phase=BattlePhase.SHOOTING,
                trigger_kind=TimingTriggerKind.JUST_AFTER_ENEMY_UNIT_HAS_SHOT,
                trigger_payload={DESTROYED_TARGET_UNIT_CONTEXT_KEY: [_CORSAIR_UNIT_ID]},
            )
        )

    no_engagement_state, _no_engagement_corsair_army, _no_engagement_enemy_army = _corsair_state(
        phase=BattlePhase.SHOOTING,
        active_player_id="player-b",
    )
    no_engagement_state.battlefield_state = None
    with pytest.raises(GameLifecycleError, match="engagement checks require battlefield state"):
        stratagems.validate_vengeful_sorrow(
            _corsair_stratagem_handler_context(
                state=no_engagement_state,
                stratagem_id=stratagems.VENGEFUL_SORROW_STRATAGEM_ID,
                handler_id=stratagems.VENGEFUL_SORROW_HANDLER_ID,
                target_unit_id=_CORSAIR_UNIT_ID,
                phase=BattlePhase.SHOOTING,
                trigger_kind=TimingTriggerKind.JUST_AFTER_ENEMY_UNIT_HAS_SHOT,
                trigger_payload={DESTROYED_TARGET_UNIT_CONTEXT_KEY: [_CORSAIR_UNIT_ID]},
            )
        )


def test_runtime_content_bundle_guardrails_validate_corsair_hook_registries() -> None:
    assignments = (
        _assignment(enhancements.ARCHRAIDER_ENHANCEMENT_ID, "archraider"),
        _assignment(enhancements.INFAMY_ENHANCEMENT_ID, "corsairs"),
        _assignment(enhancements.VOIDSTONE_ENHANCEMENT_ID, "voidstone-bearers"),
        _assignment(enhancements.WEBWAY_PATHSTONE_ENHANCEMENT_ID, "webway-bearers"),
    )
    config = _corsair_game_config(enhancement_assignments=assignments)
    armies = tuple(
        muster_army(catalog=config.army_catalog, request=request)
        for request in config.army_muster_requests
    )
    activation = RuntimeContentActivation(
        selected_faction_ids=("aeldari",),
        selected_detachment_ids=("corsair-coterie",),
        selected_enhancement_ids=(
            enhancements.ARCHRAIDER_ENHANCEMENT_ID,
            enhancements.INFAMY_ENHANCEMENT_ID,
            enhancements.VOIDSTONE_ENHANCEMENT_ID,
            enhancements.WEBWAY_PATHSTONE_ENHANCEMENT_ID,
        ),
        selected_stratagem_ids=(),
        selected_datasheet_ids=(),
        selected_wargear_ids=(),
        selected_weapon_profile_ids=(),
        selected_weapon_keywords=(),
        loaded_unit_instance_ids=(),
    )
    contribution = manifest.runtime_contribution()
    bundle = RuntimeContentBundle.from_contributions(
        activation=activation,
        armies=armies,
        catalog=config.army_catalog,
        contributions=(contribution,),
        faction_execution_records=(),
    )

    with pytest.raises(GameLifecycleError, match="requires RuntimeContentActivation"):
        replace(bundle, activation=cast(Any, object()))
    with pytest.raises(GameLifecycleError, match="ability_indexes_by_player_id must be a mapping"):
        replace(bundle, ability_indexes_by_player_id=cast(Any, []))
    with pytest.raises(GameLifecycleError, match="ability_indexes_by_player_id contains invalid"):
        replace(bundle, ability_indexes_by_player_id=cast(Any, {"player-a": object()}))
    with pytest.raises(GameLifecycleError, match="requires AbilityHandlerRegistry"):
        replace(bundle, ability_handler_registry=cast(Any, object()))
    with pytest.raises(GameLifecycleError, match="requires StratagemHandlerRegistry"):
        replace(bundle, stratagem_handler_registry=cast(Any, object()))
    with pytest.raises(GameLifecycleError, match="requires RuleExecutionRegistry"):
        replace(bundle, rule_execution_registry=cast(Any, object()))
    with pytest.raises(GameLifecycleError, match="requires FactionRuleExecutionRegistry"):
        replace(bundle, faction_rule_execution_registry=cast(Any, object()))
    with pytest.raises(GameLifecycleError, match="requires RuntimeContentEventIndex"):
        replace(bundle, event_index=cast(Any, object()))
    with pytest.raises(GameLifecycleError, match="requires TurnEndHookRegistry"):
        replace(bundle, turn_end_hook_registry=cast(Any, object()))
    with pytest.raises(GameLifecycleError, match="UnitMoveCompletedMortalWoundHookRegistry"):
        replace(bundle, unit_move_completed_mortal_wound_hook_registry=cast(Any, object()))
    with pytest.raises(GameLifecycleError, match="requires StratagemCostChoiceHookRegistry"):
        replace(bundle, stratagem_cost_choice_hook_registry=cast(Any, object()))
    with pytest.raises(GameLifecycleError, match="requires StratagemCostModifierRegistry"):
        replace(bundle, stratagem_cost_modifier_registry=cast(Any, object()))
    with pytest.raises(GameLifecycleError, match="requires RuntimeModifierRegistry"):
        replace(bundle, runtime_modifier_registry=cast(Any, object()))
    with pytest.raises(GameLifecycleError, match="contribution_ids must be a tuple"):
        replace(bundle, contribution_ids=cast(tuple[str, ...], []))
    with pytest.raises(GameLifecycleError, match="contribution_ids value must be a string"):
        replace(bundle, contribution_ids=cast(tuple[str, ...], (object(),)))
    with pytest.raises(GameLifecycleError, match="contribution_ids must not contain duplicates"):
        replace(bundle, contribution_ids=("duplicate", "duplicate"))

    with pytest.raises(GameLifecycleError, match="requires activation"):
        RuntimeContentBundle.from_contributions(
            activation=cast(RuntimeContentActivation, object()),
            armies=armies,
            catalog=config.army_catalog,
            contributions=(contribution,),
        )
    with pytest.raises(GameLifecycleError, match="scope flag is invalid"):
        RuntimeContentBundle.from_contributions(
            activation=activation,
            armies=armies,
            catalog=config.army_catalog,
            contributions=(contribution,),
            include_unselected_faction_execution_records=cast(bool, "yes"),
        )
    with pytest.raises(GameLifecycleError, match="armies must be a tuple"):
        RuntimeContentBundle.from_contributions(
            activation=activation,
            armies=cast(tuple[ArmyDefinition, ...], []),
            catalog=config.army_catalog,
            contributions=(contribution,),
        )
    with pytest.raises(GameLifecycleError, match="armies must contain ArmyDefinition"):
        RuntimeContentBundle.from_contributions(
            activation=activation,
            armies=cast(tuple[ArmyDefinition, ...], (object(),)),
            catalog=config.army_catalog,
            contributions=(contribution,),
        )
    with pytest.raises(GameLifecycleError, match="player IDs must be unique"):
        RuntimeContentBundle.from_contributions(
            activation=activation,
            armies=(armies[0], armies[0]),
            catalog=config.army_catalog,
            contributions=(contribution,),
        )
    with pytest.raises(GameLifecycleError, match="requires ArmyCatalog"):
        RuntimeContentBundle.from_contributions(
            activation=activation,
            armies=armies,
            catalog=cast(ArmyCatalog, object()),
            contributions=(contribution,),
        )
    with pytest.raises(GameLifecycleError, match="contributions must be a tuple"):
        RuntimeContentBundle.from_contributions(
            activation=activation,
            armies=armies,
            catalog=config.army_catalog,
            contributions=cast(tuple[Any, ...], []),
        )
    with pytest.raises(GameLifecycleError, match="RuntimeContentContribution values"):
        RuntimeContentBundle.from_contributions(
            activation=activation,
            armies=armies,
            catalog=config.army_catalog,
            contributions=cast(tuple[Any, ...], (object(),)),
        )
    with pytest.raises(GameLifecycleError, match="base ability registry is invalid"):
        RuntimeContentBundle.from_contributions(
            activation=activation,
            armies=armies,
            catalog=config.army_catalog,
            contributions=(contribution,),
            base_ability_handler_registry=cast(Any, object()),
        )
    with pytest.raises(GameLifecycleError, match="base Stratagem registry is invalid"):
        RuntimeContentBundle.from_contributions(
            activation=activation,
            armies=armies,
            catalog=config.army_catalog,
            contributions=(contribution,),
            base_stratagem_handler_registry=cast(Any, object()),
        )
    with pytest.raises(GameLifecycleError, match="base rule registry is invalid"):
        RuntimeContentBundle.from_contributions(
            activation=activation,
            armies=armies,
            catalog=config.army_catalog,
            contributions=(contribution,),
            base_rule_execution_registry=cast(Any, object()),
        )


def test_relentless_raiders_and_void_thieves_consume_phase_end_objective_control() -> None:
    state, _corsair_army, _enemy_army = _corsair_state(
        phase=BattlePhase.MOVEMENT,
        corsair_x=30.0,
        enemy_x=32.0,
    )
    registry = RuntimeModifierRegistry.empty()

    effects = rule.relentless_raiders_mortal_wound_effects(
        UnitMoveCompletedContext(
            state=state,
            ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(),
            runtime_modifier_registry=registry,
            completed_phase=BattlePhase.MOVEMENT,
            trigger_event_id="event-relentless-raiders-move",
            trigger_event_payload={"unit_instance_id": _ENEMY_UNIT_ID},
            triggering_unit_instance_id=_ENEMY_UNIT_ID,
            triggering_player_id="player-b",
            movement_action="normal_move",
        )
    )

    assert len(effects) == 1
    effect = effects[0]
    assert effect.hook_id == rule.RELENTLESS_RAIDERS_HOOK_ID
    assert effect.target_unit_instance_id == _ENEMY_UNIT_ID
    assert effect.target_player_id == "player-b"
    assert effect.rolling_player_id == "player-a"
    assert effect.roll_threshold == 2
    assert effect.mortal_wounds_expression.quantity == 1
    assert effect.mortal_wounds_expression.sides == 3

    decisions = DecisionController()
    sticky_states = rule.void_thieves_sticky_states(
        PhaseEndObjectiveControlContext(
            state=state,
            event_log=decisions.event_log,
            completed_phase=BattlePhase.MOVEMENT,
            runtime_modifier_registry=registry,
        )
    )

    assert len(sticky_states) == 1
    assert sticky_states[0].source_rule_id == rule.SOURCE_RULE_ID
    assert sticky_states[0].originating_unit_instance_id == _CORSAIR_UNIT_ID


def test_corsair_enhancements_apply_infamy_voidstone_and_webway_pathstone_effects() -> None:
    assignments = (
        _assignment(enhancements.INFAMY_ENHANCEMENT_ID, "corsairs"),
        _assignment(enhancements.VOIDSTONE_ENHANCEMENT_ID, "voidstone-bearers"),
        _assignment(enhancements.WEBWAY_PATHSTONE_ENHANCEMENT_ID, "webway-bearers"),
    )
    state, _corsair_army, _enemy_army = _corsair_state(
        enhancement_assignments=assignments,
        corsair_x=10.0,
        enemy_x=12.5,
        voidstone_x=20.0,
        webway_x=25.0,
    )
    decisions = DecisionController()

    apply_enhancement_effects(
        state=state,
        registry=_corsair_runtime_bundle_for_state(state).enhancement_effect_registry,
        decisions=decisions,
    )

    assert any(
        effect.effect_id.startswith(enhancements.INFAMY_EFFECT_ID)
        for effect in state.persisting_effects_for_unit(_CORSAIR_UNIT_ID)
    )
    assert any(
        effect.effect_id.startswith(enhancements.VOIDSTONE_EFFECT_ID)
        for effect in state.persisting_effects_for_unit(_VOIDSTONE_UNIT_ID)
    )
    assert _unit_by_id(state, _WEBWAY_UNIT_ID).keywords.count(enhancements.DEEP_STRIKE) == 1
    assert (
        enhancements.infamy_objective_control_modifier(
            ObjectiveControlModifierContext(
                state=state,
                unit_instance_id=_ENEMY_UNIT_ID,
                model_instance_id=f"{_ENEMY_UNIT_ID}:model-001",
                base_objective_control=2,
                current_objective_control=2,
            )
        )
        == 1
    )

    save_options = enhancements.voidstone_save_option_modifier(
        SaveOptionModifierContext(
            state=state,
            target_unit_instance_id=_VOIDSTONE_UNIT_ID,
            save_options=(
                SaveOption(
                    save_kind=SaveKind.ARMOUR,
                    target_number=4,
                    characteristic_target_number=4,
                    armor_penetration=-2,
                ),
            ),
        )
    )

    assert any(
        option.save_kind is SaveKind.INVULNERABLE and option.target_number == 5
        for option in save_options
    )


def test_corsair_enhancement_effects_and_modifiers_ignore_non_matching_sources() -> None:
    assignments = (
        _assignment(enhancements.INFAMY_ENHANCEMENT_ID, "corsairs"),
        _assignment(enhancements.VOIDSTONE_ENHANCEMENT_ID, "voidstone-bearers"),
    )
    state, corsair_army, enemy_army = _corsair_state(
        enhancement_assignments=assignments,
        corsair_x=10.0,
        enemy_x=30.0,
    )
    corsairs = _unit_by_id(state, _CORSAIR_UNIT_ID)
    enemy = _unit_by_id(state, _ENEMY_UNIT_ID)
    infamy_context = EnhancementEffectContext(
        state=state,
        army=corsair_army,
        assignment=assignments[0],
        target_unit=corsairs,
    )
    enemy_context = EnhancementEffectContext(
        state=state,
        army=enemy_army,
        assignment=EnhancementAssignment(
            enhancement_id=enhancements.INFAMY_ENHANCEMENT_ID,
            target_unit_selection_id="enemy-raiders",
            source_id="assignment:enemy:infamy",
        ),
        target_unit=enemy,
    )

    assert enhancements.archraider_effect(infamy_context) == ()
    assert enhancements.webway_pathstone_deep_strike_effect(infamy_context) == ()
    with pytest.raises(GameLifecycleError, match="requires EnhancementEffectContext"):
        enhancements.webway_pathstone_deep_strike_effect(cast(EnhancementEffectContext, object()))
    with pytest.raises(GameLifecycleError, match="requires EnhancementEffectContext"):
        enhancements.archraider_effect(cast(EnhancementEffectContext, object()))
    with pytest.raises(GameLifecycleError, match="requires Corsair Coterie"):
        enhancements.infamy_effect(enemy_context)

    assert (
        enhancements.infamy_objective_control_modifier(
            ObjectiveControlModifierContext(
                state=state,
                unit_instance_id=_ENEMY_UNIT_ID,
                model_instance_id=f"{_ENEMY_UNIT_ID}:model-001",
                base_objective_control=2,
                current_objective_control=2,
            )
        )
        == 2
    )
    assert (
        enhancements.voidstone_save_option_modifier(
            SaveOptionModifierContext(
                state=state,
                target_unit_instance_id=_VOIDSTONE_UNIT_ID,
                save_options=(
                    SaveOption(
                        save_kind=SaveKind.ARMOUR,
                        target_number=4,
                        characteristic_target_number=4,
                        armor_penetration=-1,
                    ),
                ),
            )
        )[0].save_kind
        is SaveKind.ARMOUR
    )

    apply_enhancement_effects(
        state=state,
        registry=_corsair_runtime_bundle_for_state(state).enhancement_effect_registry,
        decisions=DecisionController(),
    )
    existing_invulnerable_options = (
        SaveOption(
            save_kind=SaveKind.ARMOUR,
            target_number=4,
            characteristic_target_number=4,
            armor_penetration=-1,
        ),
        SaveOption(
            save_kind=SaveKind.INVULNERABLE,
            target_number=4,
            characteristic_target_number=4,
            armor_penetration=-1,
        ),
    )
    assert (
        enhancements.voidstone_save_option_modifier(
            SaveOptionModifierContext(
                state=state,
                target_unit_instance_id=_VOIDSTONE_UNIT_ID,
                save_options=existing_invulnerable_options,
            )
        )
        == existing_invulnerable_options
    )


def test_webway_pathstone_turn_end_request_skips_ineligible_units() -> None:
    assignments = (_assignment(enhancements.WEBWAY_PATHSTONE_ENHANCEMENT_ID, "webway-bearers"),)
    movement_state, _corsair_army, _enemy_army = _corsair_state(
        enhancement_assignments=assignments,
        phase=BattlePhase.MOVEMENT,
        active_player_id="player-b",
    )
    decisions = DecisionController()
    assert (
        enhancements.webway_pathstone_turn_end_request(
            TurnEndRequestContext(
                state=movement_state,
                decisions=decisions,
                completed_phase=BattlePhase.MOVEMENT,
            )
        )
        is None
    )

    own_turn_state, _own_corsair_army, _own_enemy_army = _corsair_state(
        enhancement_assignments=assignments,
        phase=BattlePhase.FIGHT,
        active_player_id="player-a",
    )
    assert (
        enhancements.webway_pathstone_turn_end_request(
            TurnEndRequestContext(
                state=own_turn_state,
                decisions=decisions,
                completed_phase=BattlePhase.FIGHT,
            )
        )
        is None
    )

    engaged_state, _engaged_corsair_army, _engaged_enemy_army = _corsair_state(
        enhancement_assignments=assignments,
        phase=BattlePhase.FIGHT,
        active_player_id="player-b",
        webway_x=30.0,
        enemy_x=30.5,
    )
    assert (
        enhancements.webway_pathstone_turn_end_request(
            TurnEndRequestContext(
                state=engaged_state,
                decisions=DecisionController(),
                completed_phase=BattlePhase.FIGHT,
            )
        )
        is None
    )

    no_battlefield_state, _no_battlefield_corsair_army, _no_battlefield_enemy_army = _corsair_state(
        enhancement_assignments=assignments,
        phase=BattlePhase.FIGHT,
        active_player_id="player-b",
    )
    no_battlefield_state.battlefield_state = None
    with pytest.raises(GameLifecycleError, match="requires battlefield_state"):
        enhancements.webway_pathstone_turn_end_request(
            TurnEndRequestContext(
                state=no_battlefield_state,
                decisions=DecisionController(),
                completed_phase=BattlePhase.FIGHT,
            )
        )


def test_webway_pathstone_turn_end_choice_moves_unit_to_strategic_reserves_once() -> None:
    assignments = (_assignment(enhancements.WEBWAY_PATHSTONE_ENHANCEMENT_ID, "webway-bearers"),)
    state, _corsair_army, _enemy_army = _corsair_state(
        enhancement_assignments=assignments,
        phase=BattlePhase.FIGHT,
        active_player_id="player-b",
        webway_x=10.0,
        enemy_x=30.0,
    )
    decisions = DecisionController()
    request = enhancements.webway_pathstone_turn_end_request(
        TurnEndRequestContext(
            state=state,
            decisions=decisions,
            completed_phase=BattlePhase.FIGHT,
        )
    )
    assert request is not None

    result = DecisionResult.for_request(
        result_id="result-webway-pathstone-use",
        request=request,
        selected_option_id=(f"aeldari:corsair-coterie:webway-pathstone:{_WEBWAY_UNIT_ID}:use"),
    )
    handled = enhancements.apply_webway_pathstone_turn_end_result(
        TurnEndResultContext(
            state=state,
            decisions=decisions,
            request=request,
            result=result,
        )
    )

    assert handled is True
    reserve_state = state.reserve_state_for_unit(_WEBWAY_UNIT_ID)
    assert reserve_state is not None
    assert reserve_state.source_rule_ids == (enhancements.WEBWAY_PATHSTONE_SOURCE_RULE_ID,)
    assert state.battlefield_state is not None
    assert all(
        unit_placement.unit_instance_id != _WEBWAY_UNIT_ID
        for placed_army in state.battlefield_state.placed_armies
        for unit_placement in placed_army.unit_placements
    )
    assert (
        enhancements.webway_pathstone_turn_end_request(
            TurnEndRequestContext(
                state=state,
                decisions=decisions,
                completed_phase=BattlePhase.FIGHT,
            )
        )
        is None
    )
    with pytest.raises(GameLifecycleError, match="no longer eligible"):
        enhancements.apply_webway_pathstone_turn_end_result(
            TurnEndResultContext(
                state=state,
                decisions=decisions,
                request=request,
                result=result,
            )
        )


def test_webway_pathstone_turn_end_decline_records_no_reserve_mutation() -> None:
    assignments = (_assignment(enhancements.WEBWAY_PATHSTONE_ENHANCEMENT_ID, "webway-bearers"),)
    state, _corsair_army, _enemy_army = _corsair_state(
        enhancement_assignments=assignments,
        phase=BattlePhase.FIGHT,
        active_player_id="player-b",
        webway_x=10.0,
        enemy_x=30.0,
    )
    decisions = DecisionController()
    request = enhancements.webway_pathstone_turn_end_request(
        TurnEndRequestContext(
            state=state,
            decisions=decisions,
            completed_phase=BattlePhase.FIGHT,
        )
    )
    assert request is not None

    result = DecisionResult.for_request(
        result_id="result-webway-pathstone-decline",
        request=request,
        selected_option_id=f"aeldari:corsair-coterie:webway-pathstone:{_WEBWAY_UNIT_ID}:decline",
    )
    handled = enhancements.apply_webway_pathstone_turn_end_result(
        TurnEndResultContext(
            state=state,
            decisions=decisions,
            request=request,
            result=result,
        )
    )

    assert handled is True
    assert state.reserve_state_for_unit(_WEBWAY_UNIT_ID) is None
    assert state.battlefield_state is not None
    assert state.battlefield_state.unit_placement_by_id(_WEBWAY_UNIT_ID).unit_instance_id == (
        _WEBWAY_UNIT_ID
    )
    assert any(
        record.event_type == enhancements.WEBWAY_PATHSTONE_DECLINED_EVENT
        for record in decisions.event_log.records
    )
    assert (
        enhancements.webway_pathstone_turn_end_request(
            TurnEndRequestContext(
                state=state,
                decisions=decisions,
                completed_phase=BattlePhase.FIGHT,
            )
        )
        is None
    )


def test_archraider_setup_choice_records_selected_model_state_and_event() -> None:
    assignments = (_assignment(enhancements.ARCHRAIDER_ENHANCEMENT_ID, "archraider"),)
    state, _corsair_army, _enemy_army = _corsair_state(enhancement_assignments=assignments)
    state.stage = GameLifecycleStage.SETUP
    state.setup_step_index = state.setup_sequence.index(SetupStep.DECLARE_BATTLE_FORMATIONS)
    state.battle_phase_index = None
    decisions = DecisionController()
    config = _corsair_game_config(enhancement_assignments=assignments)
    request_context = BattleFormationRequestContext(
        state=state,
        decisions=decisions,
        config=config,
    )

    request = enhancements.archraider_model_selection_request(request_context)

    assert request is not None
    assert request.actor_id == "player-a"
    assert request.decision_type == "select_faction_rule_setup_option"
    request_payload = request.payload
    assert isinstance(request_payload, dict)
    assert request_payload["hook_id"] == enhancements.ARCHRAIDER_SETUP_HOOK_ID
    assert len(request.options) == 1
    result = DecisionResult.for_request(
        result_id="result-archraider-selection",
        request=request,
        selected_option_id=(
            f"aeldari:corsair-coterie:archraider:{_ARCHRAIDER_UNIT_ID}:"
            f"{_ARCHRAIDER_UNIT_ID}:model-001"
        ),
    )
    result_context = BattleFormationResultContext(
        state=state,
        decisions=decisions,
        config=config,
        request=request,
        result=result,
    )

    assert enhancements.apply_archraider_model_selection_result(result_context) is True
    states = state.faction_rule_states_for_player(
        player_id="player-a",
        state_kind=enhancements.ARCHRAIDER_STATE_KIND,
    )
    assert len(states) == 1
    state_payload = states[0].payload
    assert isinstance(state_payload, dict)
    assert state_payload["selected_model_instance_id"] == f"{_ARCHRAIDER_UNIT_ID}:model-001"
    assert any(
        record.event_type == enhancements.ARCHRAIDER_MODEL_SELECTED_EVENT
        for record in decisions.event_log.records
    )
    assert enhancements.archraider_model_selection_request(request_context) is None
    with pytest.raises(GameLifecycleError, match="already selected"):
        enhancements.apply_archraider_model_selection_result(result_context)


def test_archraider_lord_of_deceit_is_optional_and_modifies_only_accepted_source_result() -> None:
    assignments = (_assignment(enhancements.ARCHRAIDER_ENHANCEMENT_ID, "archraider"),)
    state, _corsair_army, _enemy_army = _corsair_state(
        enhancement_assignments=assignments,
        phase=BattlePhase.SHOOTING,
        active_player_id="player-b",
        archraider_x=10.0,
        enemy_x=18.0,
    )
    _record_archraider_model_selection(state)
    decisions = DecisionController()
    definition = _test_stratagem_definition()
    eligibility = StratagemEligibilityContext.from_state(
        state=state,
        player_id="player-b",
        trigger_kind=TimingTriggerKind.START_PHASE,
    )
    target_binding = StratagemTargetBinding(
        target_kind=StratagemTargetKind.FRIENDLY_UNIT,
        target_player_id="player-b",
        target_unit_instance_id=_ENEMY_UNIT_ID,
    )
    source_request = _source_stratagem_request()
    source_result = DecisionResult.for_request(
        result_id="result-enemy-stratagem",
        request=source_request,
        selected_option_id="use-enemy-stratagem",
    )
    context = StratagemCostChoiceRequestContext(
        state=state,
        decisions=decisions,
        source_request=source_request,
        source_result=source_result,
        definition=definition,
        eligibility_context=eligibility,
        target_binding=target_binding,
        effect_selection=None,
    )

    assert (
        enhancements.archraider_command_point_cost_modifier(
            StratagemCostModifierContext(
                state=state,
                definition=definition,
                eligibility_context=eligibility,
                target_binding=target_binding,
                effect_selection=None,
                base_command_point_cost=1,
                current_command_point_cost=1,
                decisions=decisions,
                source_decision_request_id=source_request.request_id,
                source_decision_result_id=source_result.result_id,
            )
        )
        == 1
    )
    request = enhancements.archraider_command_point_cost_choice_request(context)
    assert request is not None
    assert request.actor_id == "player-a"

    result = DecisionResult.for_request(
        result_id="result-lord-of-deceit-use",
        request=request,
        selected_option_id=(
            f"aeldari:corsair-coterie:archraider:{source_result.result_id}:{_ENEMY_UNIT_ID}:use"
        ),
    )
    handled = enhancements.apply_archraider_command_point_cost_choice_result(
        StratagemCostChoiceResultContext(
            state=state,
            decisions=decisions,
            request=request,
            result=result,
            source_request=source_request,
            source_result=source_result,
            definition=definition,
            eligibility_context=eligibility,
            target_binding=target_binding,
            effect_selection=None,
        )
    )

    assert handled is True
    assert (
        enhancements.archraider_command_point_cost_modifier(
            StratagemCostModifierContext(
                state=state,
                definition=definition,
                eligibility_context=eligibility,
                target_binding=target_binding,
                effect_selection=None,
                base_command_point_cost=1,
                current_command_point_cost=1,
                decisions=decisions,
                source_decision_request_id=source_request.request_id,
                source_decision_result_id=source_result.result_id,
            )
        )
        == 2
    )
    assert enhancements.archraider_command_point_cost_choice_request(context) is None


def test_archraider_lord_of_deceit_decline_and_drift_paths_do_not_modify_cost() -> None:
    assignments = (_assignment(enhancements.ARCHRAIDER_ENHANCEMENT_ID, "archraider"),)
    state, _corsair_army, _enemy_army = _corsair_state(
        enhancement_assignments=assignments,
        phase=BattlePhase.SHOOTING,
        active_player_id="player-b",
        archraider_x=10.0,
        enemy_x=18.0,
    )
    _record_archraider_model_selection(state)
    decisions = DecisionController()
    definition = _test_stratagem_definition()
    eligibility = StratagemEligibilityContext.from_state(
        state=state,
        player_id="player-b",
        trigger_kind=TimingTriggerKind.START_PHASE,
    )
    target_binding = StratagemTargetBinding(
        target_kind=StratagemTargetKind.FRIENDLY_UNIT,
        target_player_id="player-b",
        target_unit_instance_id=_ENEMY_UNIT_ID,
    )
    source_request = _source_stratagem_request()
    source_result = DecisionResult.for_request(
        result_id="result-enemy-stratagem-decline",
        request=source_request,
        selected_option_id="use-enemy-stratagem",
    )
    request_context = StratagemCostChoiceRequestContext(
        state=state,
        decisions=decisions,
        source_request=source_request,
        source_result=source_result,
        definition=definition,
        eligibility_context=eligibility,
        target_binding=target_binding,
        effect_selection=None,
    )
    request = enhancements.archraider_command_point_cost_choice_request(request_context)
    assert request is not None
    result = DecisionResult.for_request(
        result_id="result-lord-of-deceit-decline",
        request=request,
        selected_option_id=(
            f"aeldari:corsair-coterie:archraider:{source_result.result_id}:{_ENEMY_UNIT_ID}:decline"
        ),
    )
    result_context = StratagemCostChoiceResultContext(
        state=state,
        decisions=decisions,
        request=request,
        result=result,
        source_request=source_request,
        source_result=source_result,
        definition=definition,
        eligibility_context=eligibility,
        target_binding=target_binding,
        effect_selection=None,
    )

    assert enhancements.apply_archraider_command_point_cost_choice_result(result_context) is True
    assert (
        enhancements.archraider_command_point_cost_modifier(
            StratagemCostModifierContext(
                state=state,
                definition=definition,
                eligibility_context=eligibility,
                target_binding=target_binding,
                effect_selection=None,
                base_command_point_cost=1,
                current_command_point_cost=1,
                decisions=decisions,
                source_decision_request_id=source_request.request_id,
                source_decision_result_id=source_result.result_id,
            )
        )
        == 1
    )
    assert any(
        record.event_type == enhancements.ARCHRAIDER_COST_MODIFIER_DECLINED_EVENT
        for record in decisions.event_log.records
    )
    assert enhancements.archraider_command_point_cost_choice_request(request_context) is None
    wrong_hook_request = DecisionRequest(
        request_id="request-wrong-archraider-hook",
        decision_type=SELECT_STRATAGEM_COST_MODIFIER_OPTION_DECISION_TYPE,
        actor_id="player-a",
        payload={"hook_id": "wrong-hook"},
        options=(
            DecisionOption(
                option_id="wrong-archraider-hook-option",
                label="Wrong",
                payload={"use_ability": True},
            ),
        ),
    )
    wrong_hook_result = DecisionResult.for_request(
        result_id="result-wrong-archraider-hook",
        request=wrong_hook_request,
        selected_option_id="wrong-archraider-hook-option",
    )
    assert (
        enhancements.apply_archraider_command_point_cost_choice_result(
            StratagemCostChoiceResultContext(
                state=state,
                decisions=decisions,
                request=wrong_hook_request,
                result=wrong_hook_result,
                source_request=source_request,
                source_result=source_result,
                definition=definition,
                eligibility_context=eligibility,
                target_binding=target_binding,
                effect_selection=None,
            )
        )
        is False
    )

    drifted_result = DecisionResult(
        result_id="result-lord-of-deceit-source-drift",
        request_id=request.request_id,
        decision_type=request.decision_type,
        actor_id=request.actor_id,
        selected_option_id=result.selected_option_id,
        payload={
            **cast(dict[str, JsonValue], result.payload),
            "source_decision_request_id": "other-request",
        },
    )
    with pytest.raises(GameLifecycleError, match="source request drift"):
        enhancements.apply_archraider_command_point_cost_choice_result(
            StratagemCostChoiceResultContext(
                state=state,
                decisions=decisions,
                request=request,
                result=drifted_result,
                source_request=source_request,
                source_result=source_result,
                definition=definition,
                eligibility_context=eligibility,
                target_binding=target_binding,
                effect_selection=None,
            )
        )

    untargeted_binding = StratagemTargetBinding(
        target_kind=StratagemTargetKind.NONE,
        target_player_id=None,
        target_unit_instance_id=None,
    )
    untargeted_context = StratagemCostChoiceRequestContext(
        state=state,
        decisions=decisions,
        source_request=source_request,
        source_result=source_result,
        definition=definition,
        eligibility_context=eligibility,
        target_binding=untargeted_binding,
        effect_selection=None,
    )
    assert enhancements.archraider_command_point_cost_choice_request(untargeted_context) is None


def test_webway_pathstone_lifecycle_records_void_thieves_before_turn_end_reserves() -> None:
    assignments = (_assignment(enhancements.WEBWAY_PATHSTONE_ENHANCEMENT_ID, "webway-bearers"),)
    config = _corsair_game_config(enhancement_assignments=assignments)
    state, _corsair_army, _enemy_army = _corsair_state(
        enhancement_assignments=assignments,
        phase=BattlePhase.FIGHT,
        active_player_id="player-b",
        webway_x=30.0,
        enemy_x=42.0,
    )
    lifecycle = _corsair_lifecycle_for_state(config=config, state=state)

    status = lifecycle.advance_until_decision_or_terminal()
    request = _decision_request(status)

    assert request.decision_type == SELECT_FACTION_RULE_TURN_END_OPTION_DECISION_TYPE
    assert len(state.sticky_objective_control_states) == 1
    sticky_state = state.sticky_objective_control_states[0]
    assert sticky_state.source_rule_id == rule.SOURCE_RULE_ID
    assert sticky_state.originating_unit_instance_id == _WEBWAY_UNIT_ID
    assert _event_index(
        lifecycle.decision_controller,
        "sticky_objective_control_state_recorded",
    ) < _event_index(lifecycle.decision_controller, "turn_end_faction_rule_requested")

    resolved_status = lifecycle.submit_decision(
        DecisionResult.for_request(
            result_id="phase17g-corsair-webway-lifecycle-use",
            request=request,
            selected_option_id=(f"aeldari:corsair-coterie:webway-pathstone:{_WEBWAY_UNIT_ID}:use"),
        )
    )

    reserve_state = state.reserve_state_for_unit(_WEBWAY_UNIT_ID)
    assert reserve_state is not None
    assert reserve_state.source_rule_ids == (enhancements.WEBWAY_PATHSTONE_SOURCE_RULE_ID,)
    assert state.battlefield_state is not None
    assert all(
        unit_placement.unit_instance_id != _WEBWAY_UNIT_ID
        for placed_army in state.battlefield_state.placed_armies
        for unit_placement in placed_army.unit_placements
    )
    assert len(state.sticky_objective_control_states) == 1
    assert (
        len(_event_records(lifecycle.decision_controller, "turn_end_faction_rule_requested")) == 1
    )
    if resolved_status.decision_request is not None:
        assert (
            resolved_status.decision_request.decision_type
            != SELECT_FACTION_RULE_TURN_END_OPTION_DECISION_TYPE
        )


def test_archraider_lord_of_deceit_lifecycle_pauses_and_resumes_stratagem_cost() -> None:
    assignments = (_assignment(enhancements.ARCHRAIDER_ENHANCEMENT_ID, "archraider"),)
    config = _corsair_game_config(enhancement_assignments=assignments)
    state, _corsair_army, _enemy_army = _corsair_state(
        enhancement_assignments=assignments,
        phase=BattlePhase.SHOOTING,
        active_player_id="player-b",
        archraider_x=10.0,
        enemy_x=18.0,
    )
    state.gain_command_points(
        player_id="player-b",
        amount=3,
        source_id="phase17g-corsair-lord-of-deceit-test-cp",
        source_kind=CommandPointSourceKind.OTHER,
        cap_exempt=True,
    )
    lifecycle = _corsair_lifecycle_for_state(config=config, state=state)
    _record_archraider_model_selection(state)
    definition = replace(
        _test_stratagem_definition(),
        target_spec=StratagemTargetSpec(target_kind=StratagemTargetKind.FRIENDLY_UNIT),
    )
    catalog_record = StratagemCatalogRecord(
        record_id="phase17g-corsair-lifecycle-enemy-self-buff",
        definition=definition,
    )

    status = request_stratagem_use(
        state=state,
        decisions=lifecycle.decision_controller,
        catalog_records=(catalog_record,),
        context=StratagemEligibilityContext.from_state(
            state=state,
            player_id="player-b",
            trigger_kind=TimingTriggerKind.START_PHASE,
        ),
    )
    stratagem_request = _decision_request(status)
    assert stratagem_request.decision_type == STRATAGEM_DECISION_TYPE
    assert state.command_point_total("player-b") == 3

    cost_choice_status = lifecycle.submit_decision(
        DecisionResult.for_request(
            result_id="phase17g-corsair-lifecycle-enemy-stratagem",
            request=stratagem_request,
            selected_option_id=f"use-stratagem:enemy-self-buff:target:{_LIFECYCLE_ENEMY_UNIT_ID}",
        )
    )
    cost_choice_request = _decision_request(cost_choice_status)
    assert cost_choice_request.decision_type == SELECT_STRATAGEM_COST_MODIFIER_OPTION_DECISION_TYPE
    assert state.command_point_total("player-b") == 3

    resolved_status = lifecycle.submit_decision(
        DecisionResult.for_request(
            result_id="phase17g-corsair-lifecycle-lord-of-deceit-use",
            request=cost_choice_request,
            selected_option_id=(
                "aeldari:corsair-coterie:archraider:"
                "phase17g-corsair-lifecycle-enemy-stratagem:"
                f"{_LIFECYCLE_ENEMY_UNIT_ID}:use"
            ),
        )
    )

    assert resolved_status.status_kind is not LifecycleStatusKind.INVALID
    assert state.command_point_total("player-b") == 1
    assert len(state.stratagem_use_records) == 1
    use_record = state.stratagem_use_records[0]
    assert use_record.command_point_cost == 2
    assert use_record.command_point_modifier_ids == (enhancements.ARCHRAIDER_COST_MODIFIER_ID,)
    assert use_record.command_point_modifier_source_ids == (enhancements.ARCHRAIDER_SOURCE_RULE_ID,)
    assert any(
        record.event_type == enhancements.ARCHRAIDER_COST_MODIFIER_USED_EVENT
        for record in lifecycle.decision_controller.event_log.records
    )


def test_archraider_cost_increase_can_make_stratagem_used_without_resolving_effects() -> None:
    assignments = (_assignment(enhancements.ARCHRAIDER_ENHANCEMENT_ID, "archraider"),)
    config = _corsair_game_config(enhancement_assignments=assignments)
    state, _corsair_army, _enemy_army = _corsair_state(
        enhancement_assignments=assignments,
        phase=BattlePhase.SHOOTING,
        active_player_id="player-b",
        archraider_x=10.0,
        enemy_x=18.0,
    )
    state.gain_command_points(
        player_id="player-b",
        amount=1,
        source_id="phase17g-corsair-unaffordable-lord-of-deceit-test-cp",
        source_kind=CommandPointSourceKind.OTHER,
        cap_exempt=True,
    )
    lifecycle = _corsair_lifecycle_for_state(config=config, state=state)
    _record_archraider_model_selection(state)
    definition = replace(
        _test_stratagem_definition(),
        target_spec=StratagemTargetSpec(target_kind=StratagemTargetKind.FRIENDLY_UNIT),
    )
    catalog_record = StratagemCatalogRecord(
        record_id="phase17g-corsair-unaffordable-enemy-self-buff",
        definition=definition,
    )
    status = request_stratagem_use(
        state=state,
        decisions=lifecycle.decision_controller,
        catalog_records=(catalog_record,),
        context=StratagemEligibilityContext.from_state(
            state=state,
            player_id="player-b",
            trigger_kind=TimingTriggerKind.START_PHASE,
        ),
    )
    stratagem_request = _decision_request(status)
    cost_choice_status = lifecycle.submit_decision(
        DecisionResult.for_request(
            result_id="phase17g-corsair-unaffordable-enemy-stratagem",
            request=stratagem_request,
            selected_option_id=f"use-stratagem:enemy-self-buff:target:{_LIFECYCLE_ENEMY_UNIT_ID}",
        )
    )
    cost_choice_request = _decision_request(cost_choice_status)

    resolved_status = lifecycle.submit_decision(
        DecisionResult.for_request(
            result_id="phase17g-corsair-unaffordable-lord-of-deceit-use",
            request=cost_choice_request,
            selected_option_id=(
                "aeldari:corsair-coterie:archraider:"
                "phase17g-corsair-unaffordable-enemy-stratagem:"
                f"{_LIFECYCLE_ENEMY_UNIT_ID}:use"
            ),
        )
    )

    assert resolved_status.status_kind is not LifecycleStatusKind.INVALID
    assert state.command_point_total("player-b") == 1
    assert len(state.stratagem_use_records) == 1
    use_record = state.stratagem_use_records[0]
    assert use_record.command_point_cost == 2
    assert use_record.command_point_transaction_id is None
    assert use_record.effects_resolved is False
    assert use_record.unresolved_reason == "insufficient_command_points_after_cost_increase"
    assert use_record.command_point_modifier_ids == (enhancements.ARCHRAIDER_COST_MODIFIER_ID,)
    assert use_record.command_point_modifier_source_ids == (enhancements.ARCHRAIDER_SOURCE_RULE_ID,)
    assert StratagemUseRecord.from_payload(use_record.to_payload()) == use_record
    assert any(
        record.event_type == "stratagem_effects_not_resolved"
        for record in lifecycle.decision_controller.event_log.records
    )


def test_relentless_raiders_lifecycle_resolves_move_completed_mortal_wounds_once() -> None:
    config = _corsair_game_config()
    state, _corsair_army, _enemy_army = _corsair_state(
        phase=BattlePhase.MOVEMENT,
        active_player_id="player-b",
        corsair_x=27.0,
        webway_x=28.0,
        enemy_x=35.0,
    )
    lifecycle = _corsair_lifecycle_for_state(config=config, state=state)

    status = lifecycle.advance_until_decision_or_terminal()
    unit_request = _decision_request(status)
    assert unit_request.decision_type == SELECT_MOVEMENT_UNIT_DECISION_TYPE
    action_status = lifecycle.submit_decision(
        DecisionResult.for_request(
            result_id="phase17g-corsair-relentless-select-enemy",
            request=unit_request,
            selected_option_id=_LIFECYCLE_ENEMY_UNIT_ID,
        )
    )
    action_request = _decision_request(action_status)
    assert action_request.decision_type == SELECT_MOVEMENT_ACTION_DECISION_TYPE

    proposal_status = lifecycle.submit_decision(
        DecisionResult.for_request(
            result_id="phase17g-corsair-relentless-normal-action",
            request=action_request,
            selected_option_id=MovementPhaseActionKind.NORMAL_MOVE.value,
        )
    )
    proposal_request = _decision_request(proposal_status)
    if proposal_request.decision_type == SELECT_MOVEMENT_ACTION_GRANT_DECISION_TYPE:
        proposal_status = lifecycle.submit_decision(
            DecisionResult.for_request(
                result_id="phase17g-corsair-relentless-normal-grant-decline",
                request=proposal_request,
                selected_option_id=DECLINE_MOVEMENT_ACTION_GRANT_OPTION_ID,
            )
        )
        proposal_request = _decision_request(proposal_status)

    submit_movement_proposal(
        lifecycle,
        request=proposal_request,
        result_id="phase17g-corsair-relentless-normal-proposal",
        unit_instance_id=_LIFECYCLE_ENEMY_UNIT_ID,
        movement_phase_action=MovementPhaseActionKind.NORMAL_MOVE,
        movement_mode=MovementMode.NORMAL,
        witness=straight_line_witness_for_unit(
            lifecycle,
            unit_instance_id=_LIFECYCLE_ENEMY_UNIT_ID,
            dx=-3.0,
        ),
    )

    rolled_payloads = _event_payloads(
        lifecycle.decision_controller,
        UNIT_MOVE_COMPLETED_MORTAL_WOUNDS_ROLLED_EVENT,
    )
    assert len(rolled_payloads) == 1
    rolled_payload = rolled_payloads[0]
    trigger_event_id = _json_payload_string(rolled_payload, "trigger_event_id")
    movement_record = _event_record_by_id(lifecycle.decision_controller, trigger_event_id)
    assert movement_record.event_type == "movement_activation_completed"
    assert rolled_payload["hook_id"] == rule.RELENTLESS_RAIDERS_HOOK_ID
    assert rolled_payload["source_rule_id"] == rule.SOURCE_RULE_ID
    assert rolled_payload["target_unit_instance_id"] == _LIFECYCLE_ENEMY_UNIT_ID
    assert rolled_payload["movement_action"] == MovementPhaseActionKind.NORMAL_MOVE.value

    processed_count_before = _unit_move_completed_mortal_wound_processed_event_count(
        lifecycle.decision_controller
    )
    lifecycle.advance_until_decision_or_terminal()
    assert (
        _unit_move_completed_mortal_wound_processed_event_count(lifecycle.decision_controller)
        == processed_count_before
    )


def test_corsair_event_filter_helpers_and_rule_guardrails_are_strict() -> None:
    state, _corsair_army, _enemy_army = _corsair_state(
        phase=BattlePhase.FIGHT,
        active_player_id="player-b",
    )
    decisions = DecisionController()
    definition = _test_stratagem_definition()
    eligibility = StratagemEligibilityContext.from_state(
        state=state,
        player_id="player-b",
        trigger_kind=TimingTriggerKind.START_PHASE,
    )
    target_binding = StratagemTargetBinding(
        target_kind=StratagemTargetKind.FRIENDLY_UNIT,
        target_player_id="player-b",
        target_unit_instance_id=_ENEMY_UNIT_ID,
    )
    cost_context = StratagemCostModifierContext(
        state=state,
        definition=definition,
        eligibility_context=eligibility,
        target_binding=target_binding,
        effect_selection=None,
        base_command_point_cost=1,
        current_command_point_cost=1,
        decisions=decisions,
        source_decision_request_id="source-request",
        source_decision_result_id="source-result",
    )
    turn_context = TurnEndRequestContext(
        state=state,
        decisions=decisions,
        completed_phase=BattlePhase.FIGHT,
    )
    archraider_used_this_turn = vars(enhancements)["_archraider_used_this_turn"]
    archraider_cost_choice_used_for_source_result = vars(enhancements)[
        "_archraider_cost_choice_used_for_source_result"
    ]
    webway_pathstone_decision_recorded_this_turn = vars(enhancements)[
        "_webway_pathstone_decision_recorded_this_turn"
    ]
    webway_pathstone_used_this_battle = vars(enhancements)["_webway_pathstone_used_this_battle"]
    enhancement_active_player_id = vars(enhancements)["_active_player_id"]
    enhancement_payload_object = vars(enhancements)["_payload_object"]
    enhancement_payload_string = vars(enhancements)["_payload_string"]
    enhancement_payload_bool = vars(enhancements)["_payload_bool"]
    enhancement_validate_identifier = vars(enhancements)["_validate_identifier"]
    objective_control_record_for_state = vars(rule)["_objective_control_record_for_state"]
    army_has_corsair_coterie = vars(rule)["_army_has_corsair_coterie"]
    unit_has_keyword = vars(rule)["_unit_has_keyword"]
    rule_validate_identifier = vars(rule)["_validate_identifier"]
    with pytest.raises(GameLifecycleError, match="requires GameState"):
        archraider_used_this_turn(
            cast(GameState, object()),
            decisions=decisions,
            player_id="player-a",
            active_player_id="player-b",
            source_decision_result_id=None,
        )
    with pytest.raises(GameLifecycleError, match="requires DecisionController"):
        archraider_used_this_turn(
            state,
            decisions=object(),
            player_id="player-a",
            active_player_id="player-b",
            source_decision_result_id=None,
        )
    decisions.event_log.append(enhancements.ARCHRAIDER_COST_MODIFIER_USED_EVENT, "bad-payload")
    decisions.event_log.append(
        enhancements.ARCHRAIDER_COST_MODIFIER_USED_EVENT,
        {
            "game_id": "other-game",
            "battle_round": state.battle_round,
            "active_player_id": "player-b",
            "player_id": "player-a",
            "source_decision_result_id": "source-result",
            "use_ability": True,
        },
    )
    decisions.event_log.append(
        enhancements.ARCHRAIDER_COST_MODIFIER_USED_EVENT,
        {
            "game_id": state.game_id,
            "battle_round": state.battle_round + 1,
            "active_player_id": "player-b",
            "player_id": "player-a",
            "source_decision_result_id": "source-result",
            "use_ability": True,
        },
    )
    decisions.event_log.append(
        enhancements.ARCHRAIDER_COST_MODIFIER_USED_EVENT,
        {
            "game_id": state.game_id,
            "battle_round": state.battle_round,
            "active_player_id": "other-active-player",
            "player_id": "player-a",
            "source_decision_result_id": "source-result",
            "use_ability": True,
        },
    )
    decisions.event_log.append(
        enhancements.ARCHRAIDER_COST_MODIFIER_USED_EVENT,
        {
            "game_id": state.game_id,
            "battle_round": state.battle_round,
            "active_player_id": "player-b",
            "player_id": "other-player",
            "source_decision_result_id": "source-result",
            "use_ability": True,
        },
    )
    decisions.event_log.append(
        enhancements.ARCHRAIDER_COST_MODIFIER_USED_EVENT,
        {
            "game_id": state.game_id,
            "battle_round": state.battle_round,
            "active_player_id": "player-b",
            "player_id": "player-a",
            "source_decision_result_id": "source-result",
            "modifier_id": enhancements.ARCHRAIDER_COST_MODIFIER_ID,
            "use_ability": True,
        },
    )
    assert (
        archraider_used_this_turn(
            state,
            decisions=decisions,
            player_id="player-a",
            active_player_id="player-b",
            source_decision_result_id="source-result",
        )
        is False
    )
    decisions.event_log.append(
        enhancements.ARCHRAIDER_COST_MODIFIER_USED_EVENT,
        {
            "game_id": state.game_id,
            "battle_round": state.battle_round,
            "active_player_id": "player-b",
            "player_id": "player-a",
            "source_decision_result_id": "other-source-result",
            "modifier_id": enhancements.ARCHRAIDER_COST_MODIFIER_ID,
            "use_ability": True,
        },
    )
    assert (
        archraider_used_this_turn(
            state,
            decisions=decisions,
            player_id="player-a",
            active_player_id="player-b",
            source_decision_result_id="source-result",
        )
        is True
    )
    assert archraider_cost_choice_used_for_source_result(cost_context) is True
    no_source_context = StratagemCostModifierContext(
        state=state,
        definition=definition,
        eligibility_context=eligibility,
        target_binding=target_binding,
        effect_selection=None,
        base_command_point_cost=1,
        current_command_point_cost=1,
        decisions=decisions,
    )
    assert archraider_cost_choice_used_for_source_result(no_source_context) is False
    with pytest.raises(GameLifecycleError, match="requires context"):
        archraider_cost_choice_used_for_source_result(cast(StratagemCostModifierContext, object()))

    decisions.event_log.append(enhancements.WEBWAY_PATHSTONE_USED_EVENT, "bad-payload")
    decisions.event_log.append(
        enhancements.WEBWAY_PATHSTONE_DECLINED_EVENT,
        {
            "game_id": "other-game",
            "battle_round": state.battle_round,
            "active_player_id": "player-b",
            "phase": BattlePhase.FIGHT.value,
            "target_unit_instance_id": _WEBWAY_UNIT_ID,
        },
    )
    decisions.event_log.append(
        enhancements.WEBWAY_PATHSTONE_DECLINED_EVENT,
        {
            "game_id": state.game_id,
            "battle_round": state.battle_round,
            "active_player_id": "player-b",
            "phase": BattlePhase.FIGHT.value,
            "target_unit_instance_id": _WEBWAY_UNIT_ID,
        },
    )
    assert (
        webway_pathstone_decision_recorded_this_turn(
            turn_context,
            unit_instance_id=_WEBWAY_UNIT_ID,
        )
        is True
    )
    with pytest.raises(GameLifecycleError, match="requires DecisionController"):
        webway_pathstone_used_this_battle(
            object(),
            unit_instance_id=_WEBWAY_UNIT_ID,
        )
    assert (
        webway_pathstone_used_this_battle(
            decisions,
            unit_instance_id=_WEBWAY_UNIT_ID,
        )
        is False
    )
    decisions.event_log.append(
        enhancements.WEBWAY_PATHSTONE_USED_EVENT,
        {"target_unit_instance_id": _WEBWAY_UNIT_ID},
    )
    assert (
        webway_pathstone_used_this_battle(
            decisions,
            unit_instance_id=_WEBWAY_UNIT_ID,
        )
        is True
    )

    no_active_state, _no_active_corsair_army, _no_active_enemy_army = _corsair_state(
        phase=BattlePhase.FIGHT
    )
    no_active_state.active_player_id = None
    with pytest.raises(GameLifecycleError, match="requires an active player"):
        enhancement_active_player_id(no_active_state)
    with pytest.raises(GameLifecycleError, match="payload must be an object"):
        enhancement_payload_object("bad-payload")
    with pytest.raises(GameLifecycleError, match="missing string"):
        enhancement_payload_string({}, "missing")
    with pytest.raises(GameLifecycleError, match="missing bool"):
        enhancement_payload_bool({}, "missing")
    with pytest.raises(GameLifecycleError, match="must be a string"):
        enhancement_validate_identifier("test", object())
    with pytest.raises(GameLifecycleError, match="must not be empty"):
        enhancement_validate_identifier("test", " ")

    with pytest.raises(GameLifecycleError, match="movement completion context"):
        rule.relentless_raiders_mortal_wound_effects(cast(UnitMoveCompletedContext, object()))
    with pytest.raises(GameLifecycleError, match="phase-end objective context"):
        rule.void_thieves_sticky_states(cast(PhaseEndObjectiveControlContext, object()))
    no_mission_state, _no_mission_corsair_army, _no_mission_enemy_army = _corsair_state(
        phase=BattlePhase.FIGHT
    )
    no_mission_state.mission_setup = None
    assert (
        rule.void_thieves_sticky_states(
            PhaseEndObjectiveControlContext(
                state=no_mission_state,
                event_log=DecisionController().event_log,
                completed_phase=BattlePhase.FIGHT,
                runtime_modifier_registry=RuntimeModifierRegistry.empty(),
            )
        )
        == ()
    )
    with pytest.raises(GameLifecycleError, match="requires GameState"):
        objective_control_record_for_state(
            state_context=object(),
            completed_phase=BattlePhase.FIGHT,
            ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(),
            runtime_modifier_registry=RuntimeModifierRegistry.empty(),
        )
    with pytest.raises(GameLifecycleError, match="requires ArmyDefinition"):
        army_has_corsair_coterie(cast(ArmyDefinition, object()))
    with pytest.raises(GameLifecycleError, match="requires UnitInstance"):
        unit_has_keyword(cast(UnitInstance, object()), "ANHRATHE")
    with pytest.raises(GameLifecycleError, match="must not be empty"):
        rule_validate_identifier("test", " ")


def test_turn_end_hook_registry_routes_single_request_and_result() -> None:
    state, _corsair_army, _enemy_army = _corsair_state(
        phase=BattlePhase.FIGHT,
        active_player_id="player-b",
    )
    decisions = DecisionController()
    request = DecisionRequest(
        request_id="request-turn-end",
        decision_type=SELECT_FACTION_RULE_TURN_END_OPTION_DECISION_TYPE,
        actor_id="player-a",
        payload={"hook_id": "hook-a"},
        options=(
            DecisionOption(
                option_id="turn-end-use",
                label="Use",
                payload={"use_ability": True},
            ),
        ),
    )
    result = DecisionResult.for_request(
        result_id="result-turn-end",
        request=request,
        selected_option_id="turn-end-use",
    )
    registry = TurnEndHookRegistry.from_bindings(
        (
            TurnEndHookBinding(
                hook_id="hook-b",
                source_id="source-b",
                request_handler=lambda _context: None,
                result_handler=lambda _context: False,
            ),
            TurnEndHookBinding(
                hook_id="hook-a",
                source_id="source-a",
                request_handler=lambda _context: request,
                result_handler=lambda _context: True,
            ),
        )
    )

    request_context = TurnEndRequestContext(
        state=state,
        decisions=decisions,
        completed_phase=BattlePhase.FIGHT,
    )
    assert [binding.hook_id for binding in registry.all_bindings()] == ["hook-a", "hook-b"]
    assert registry.next_request_for(request_context) == request
    assert TurnEndHookRegistry.empty().next_request_for(request_context) is None
    result_context = TurnEndResultContext(
        state=state,
        decisions=decisions,
        request=request,
        result=result,
    )
    assert registry.apply_result(result_context) is True
    assert TurnEndHookRegistry.empty().apply_result(result_context) is False

    with pytest.raises(GameLifecycleError, match="requires a handler"):
        TurnEndHookBinding(hook_id="empty", source_id="source")
    with pytest.raises(GameLifecycleError, match="hook IDs must be unique"):
        TurnEndHookRegistry.from_bindings((registry.all_bindings()[0], registry.all_bindings()[0]))
    with pytest.raises(GameLifecycleError, match="multiple simultaneous requests"):
        TurnEndHookRegistry.from_bindings(
            (
                TurnEndHookBinding(
                    hook_id="request-a",
                    source_id="source-a",
                    request_handler=lambda _context: request,
                ),
                TurnEndHookBinding(
                    hook_id="request-b",
                    source_id="source-b",
                    request_handler=lambda _context: request,
                ),
            )
        ).next_request_for(request_context)
    with pytest.raises(GameLifecycleError, match="handled by multiple hooks"):
        TurnEndHookRegistry.from_bindings(
            (
                TurnEndHookBinding(
                    hook_id="result-a",
                    source_id="source-a",
                    result_handler=lambda _context: True,
                ),
                TurnEndHookBinding(
                    hook_id="result-b",
                    source_id="source-b",
                    result_handler=lambda _context: True,
                ),
            )
        ).apply_result(result_context)


def test_turn_end_hook_context_and_handler_validation_paths() -> None:
    state, _corsair_army, _enemy_army = _corsair_state(
        phase=BattlePhase.FIGHT,
        active_player_id="player-b",
    )
    decisions = DecisionController()
    request = DecisionRequest(
        request_id="request-turn-end-validation",
        decision_type=SELECT_FACTION_RULE_TURN_END_OPTION_DECISION_TYPE,
        actor_id="player-a",
        payload={"hook_id": "hook-a"},
        options=(
            DecisionOption(
                option_id="turn-end-use-validation",
                label="Use",
                payload={"use_ability": True},
            ),
        ),
    )
    result = DecisionResult.for_request(
        result_id="result-turn-end-validation",
        request=request,
        selected_option_id="turn-end-use-validation",
    )

    assert (
        TurnEndRequestContext(
            state=state,
            decisions=decisions,
            completed_phase=cast(BattlePhase, BattlePhase.FIGHT.value),
        ).completed_phase
        is BattlePhase.FIGHT
    )
    with pytest.raises(GameLifecycleError, match="state must be GameState"):
        TurnEndRequestContext(
            state=cast(GameState, object()),
            decisions=decisions,
            completed_phase=BattlePhase.FIGHT,
        )
    with pytest.raises(GameLifecycleError, match="decisions must be DecisionController"):
        TurnEndRequestContext(
            state=state,
            decisions=cast(DecisionController, object()),
            completed_phase=BattlePhase.FIGHT,
        )
    with pytest.raises(GameLifecycleError, match="Unsupported turn-end hook phase"):
        TurnEndRequestContext(
            state=state,
            decisions=decisions,
            completed_phase=cast(BattlePhase, "not-a-phase"),
        )
    with pytest.raises(GameLifecycleError, match="phase drift"):
        TurnEndRequestContext(
            state=state,
            decisions=decisions,
            completed_phase=BattlePhase.MOVEMENT,
        )

    setup_state, _setup_corsair_army, _setup_enemy_army = _corsair_state(phase=BattlePhase.FIGHT)
    setup_state.stage = GameLifecycleStage.SETUP
    with pytest.raises(GameLifecycleError, match="battle stage"):
        TurnEndRequestContext(
            state=setup_state,
            decisions=decisions,
            completed_phase=BattlePhase.FIGHT,
        )

    with pytest.raises(GameLifecycleError, match="request must be DecisionRequest"):
        TurnEndResultContext(
            state=state,
            decisions=decisions,
            request=cast(DecisionRequest, object()),
            result=result,
        )
    with pytest.raises(GameLifecycleError, match="result must be DecisionResult"):
        TurnEndResultContext(
            state=state,
            decisions=decisions,
            request=request,
            result=cast(DecisionResult, object()),
        )
    wrong_request = DecisionRequest(
        request_id="request-turn-end-wrong-type",
        decision_type="wrong-decision-type",
        actor_id="player-a",
        payload={"hook_id": "hook-a"},
        options=(
            DecisionOption(
                option_id="wrong-turn-end-use",
                label="Use",
                payload={"use_ability": True},
            ),
        ),
    )
    wrong_result = DecisionResult.for_request(
        result_id="result-turn-end-wrong-type",
        request=wrong_request,
        selected_option_id="wrong-turn-end-use",
    )
    with pytest.raises(GameLifecycleError, match="decision_type drift"):
        TurnEndResultContext(
            state=state,
            decisions=decisions,
            request=wrong_request,
            result=wrong_result,
        )
    no_phase_state, _no_phase_corsair_army, _no_phase_enemy_army = _corsair_state(
        phase=BattlePhase.FIGHT
    )
    no_phase_state.battle_phase_index = None
    with pytest.raises(GameLifecycleError, match="requires a current phase"):
        TurnEndResultContext(
            state=no_phase_state,
            decisions=decisions,
            request=request,
            result=result,
        )

    with pytest.raises(GameLifecycleError, match="request_handler must be callable"):
        TurnEndHookBinding(
            hook_id="bad-request-handler",
            source_id="source",
            request_handler=cast(Any, object()),
        )
    with pytest.raises(GameLifecycleError, match="result_handler must be callable"):
        TurnEndHookBinding(
            hook_id="bad-result-handler",
            source_id="source",
            result_handler=cast(Any, object()),
        )
    with pytest.raises(GameLifecycleError, match="bindings must be a tuple"):
        TurnEndHookRegistry(bindings=cast(tuple[TurnEndHookBinding, ...], []))
    with pytest.raises(GameLifecycleError, match="requires hook bindings"):
        TurnEndHookRegistry.from_bindings(cast(tuple[TurnEndHookBinding, ...], (object(),)))
    registry = TurnEndHookRegistry.from_bindings(
        (
            TurnEndHookBinding(
                hook_id="bad-return-request",
                source_id="source",
                request_handler=lambda _context: cast(DecisionRequest, object()),
            ),
        )
    )
    request_context = TurnEndRequestContext(
        state=state,
        decisions=decisions,
        completed_phase=BattlePhase.FIGHT,
    )
    with pytest.raises(GameLifecycleError, match="must return DecisionRequest or None"):
        registry.next_request_for(request_context)
    with pytest.raises(GameLifecycleError, match="request hooks require a context"):
        registry.next_request_for(cast(TurnEndRequestContext, object()))
    result_registry = TurnEndHookRegistry.from_bindings(
        (
            TurnEndHookBinding(
                hook_id="bad-return-result",
                source_id="source",
                result_handler=lambda _context: cast(bool, "yes"),
            ),
        )
    )
    result_context = TurnEndResultContext(
        state=state,
        decisions=decisions,
        request=request,
        result=result,
    )
    with pytest.raises(GameLifecycleError, match="must return bool"):
        result_registry.apply_result(result_context)
    with pytest.raises(GameLifecycleError, match="result hooks require a context"):
        result_registry.apply_result(cast(TurnEndResultContext, object()))


def test_stratagem_cost_hook_registries_track_sources_and_round_trip_result() -> None:
    state, _corsair_army, _enemy_army = _corsair_state(
        phase=BattlePhase.SHOOTING,
        active_player_id="player-b",
    )
    decisions = DecisionController()
    definition = _test_stratagem_definition()
    eligibility = StratagemEligibilityContext.from_state(
        state=state,
        player_id="player-b",
        trigger_kind=TimingTriggerKind.START_PHASE,
    )
    target_binding = StratagemTargetBinding(
        target_kind=StratagemTargetKind.FRIENDLY_UNIT,
        target_player_id="player-b",
        target_unit_instance_id=_ENEMY_UNIT_ID,
    )
    source_request = _source_stratagem_request()
    source_result = DecisionResult.for_request(
        result_id="result-source-stratagem",
        request=source_request,
        selected_option_id="use-enemy-stratagem",
    )
    cost_context = StratagemCostModifierContext(
        state=state,
        definition=definition,
        eligibility_context=eligibility,
        target_binding=target_binding,
        effect_selection=None,
        base_command_point_cost=1,
        current_command_point_cost=1,
        decisions=decisions,
        source_decision_request_id=source_request.request_id,
        source_decision_result_id=source_result.result_id,
    )
    cost_registry = StratagemCostModifierRegistry.from_bindings(
        (
            StratagemCostModifierBinding(
                modifier_id="modifier-same",
                source_id="source-same",
                handler=lambda context: context.current_command_point_cost,
            ),
            StratagemCostModifierBinding(
                modifier_id="modifier-plus-one",
                source_id="source-plus-one",
                handler=lambda context: context.current_command_point_cost + 1,
            ),
        )
    )

    cost_result = cost_registry.modified_command_point_cost_with_sources(cost_context)

    assert cost_result.command_point_cost == 2
    assert cost_result.modifier_ids == ("modifier-plus-one",)
    assert cost_result.source_ids == ("source-plus-one",)
    assert cost_registry.modified_command_point_cost(cost_context) == 2
    with pytest.raises(GameLifecycleError, match="IDs must be unique"):
        StratagemCostModifierRegistry.from_bindings(
            (cost_registry.all_bindings()[0], cost_registry.all_bindings()[0])
        )
    floored_cost = StratagemCostModifierRegistry.from_bindings(
        (
            StratagemCostModifierBinding(
                modifier_id="negative-modifier",
                source_id="source-negative",
                handler=lambda _context: -1,
            ),
        )
    ).modified_command_point_cost(cost_context)
    assert floored_cost == 0

    cost_choice_request = DecisionRequest(
        request_id="request-cost-choice",
        decision_type=SELECT_STRATAGEM_COST_MODIFIER_OPTION_DECISION_TYPE,
        actor_id="player-a",
        payload={
            "source_decision_result": source_result_payload_for_cost_choice(source_result),
        },
        options=(
            DecisionOption(
                option_id="cost-choice-use",
                label="Use",
                payload={"use_ability": True},
            ),
        ),
    )
    cost_choice_result = DecisionResult.for_request(
        result_id="result-cost-choice",
        request=cost_choice_request,
        selected_option_id="cost-choice-use",
    )
    request_context = StratagemCostChoiceRequestContext(
        state=state,
        decisions=decisions,
        source_request=source_request,
        source_result=source_result,
        definition=definition,
        eligibility_context=eligibility,
        target_binding=target_binding,
        effect_selection={"selected": True},
    )
    result_context = StratagemCostChoiceResultContext(
        state=state,
        decisions=decisions,
        request=cost_choice_request,
        result=cost_choice_result,
        source_request=source_request,
        source_result=source_result,
        definition=definition,
        eligibility_context=eligibility,
        target_binding=target_binding,
        effect_selection={"selected": True},
    )
    cost_choice_registry = StratagemCostChoiceHookRegistry.from_bindings(
        (
            StratagemCostChoiceHookBinding(
                hook_id="cost-choice-hook",
                source_id="source-cost-choice",
                request_handler=lambda _context: cost_choice_request,
                result_handler=lambda _context: True,
            ),
        )
    )

    restored_source_result = stratagem_cost_choice_source_result(cost_choice_request)

    assert restored_source_result.to_payload() == source_result.to_payload()
    assert cost_choice_registry.next_request_for(request_context) == cost_choice_request
    assert cost_choice_registry.apply_result(result_context) is True
    assert StratagemCostChoiceHookRegistry.empty().next_request_for(request_context) is None
    assert StratagemCostChoiceHookRegistry.empty().apply_result(result_context) is False
    with pytest.raises(GameLifecycleError, match="requires a handler"):
        StratagemCostChoiceHookBinding(hook_id="empty-choice", source_id="source")
    with pytest.raises(GameLifecycleError, match="hook IDs must be unique"):
        StratagemCostChoiceHookRegistry.from_bindings(
            (
                cost_choice_registry.all_bindings()[0],
                cost_choice_registry.all_bindings()[0],
            )
        )
    with pytest.raises(GameLifecycleError, match="missing source result"):
        stratagem_cost_choice_source_result(
            DecisionRequest(
                request_id="request-missing-source",
                decision_type=SELECT_STRATAGEM_COST_MODIFIER_OPTION_DECISION_TYPE,
                actor_id="player-a",
                payload={},
                options=(
                    DecisionOption(
                        option_id="missing-source-option",
                        label="Missing",
                        payload={"missing_source": True},
                    ),
                ),
            )
        )


def test_stratagem_cost_hook_context_and_handler_validation_paths() -> None:
    state, _corsair_army, _enemy_army = _corsair_state(
        phase=BattlePhase.SHOOTING,
        active_player_id="player-b",
    )
    decisions = DecisionController()
    definition = _test_stratagem_definition()
    eligibility = StratagemEligibilityContext.from_state(
        state=state,
        player_id="player-b",
        trigger_kind=TimingTriggerKind.START_PHASE,
    )
    target_binding = StratagemTargetBinding(
        target_kind=StratagemTargetKind.FRIENDLY_UNIT,
        target_player_id="player-b",
        target_unit_instance_id=_ENEMY_UNIT_ID,
    )
    source_request = _source_stratagem_request()
    source_result = DecisionResult.for_request(
        result_id="result-source-stratagem-validation",
        request=source_request,
        selected_option_id="use-enemy-stratagem",
    )
    request_context = StratagemCostChoiceRequestContext(
        state=state,
        decisions=decisions,
        source_request=source_request,
        source_result=source_result,
        definition=definition,
        eligibility_context=eligibility,
        target_binding=target_binding,
        effect_selection={"selected": True},
    )
    cost_choice_request = DecisionRequest(
        request_id="request-cost-choice-validation",
        decision_type=SELECT_STRATAGEM_COST_MODIFIER_OPTION_DECISION_TYPE,
        actor_id="player-a",
        payload={"source_decision_result": source_result_payload_for_cost_choice(source_result)},
        options=(
            DecisionOption(
                option_id="cost-choice-validation-use",
                label="Use",
                payload={"use_ability": True},
            ),
        ),
    )
    cost_choice_result = DecisionResult.for_request(
        result_id="result-cost-choice-validation",
        request=cost_choice_request,
        selected_option_id="cost-choice-validation-use",
    )
    result_context = StratagemCostChoiceResultContext(
        state=state,
        decisions=decisions,
        request=cost_choice_request,
        result=cost_choice_result,
        source_request=source_request,
        source_result=source_result,
        definition=definition,
        eligibility_context=eligibility,
        target_binding=target_binding,
        effect_selection={"selected": True},
    )

    with pytest.raises(GameLifecycleError, match="requires GameState"):
        StratagemCostChoiceRequestContext(
            state=cast(GameState, object()),
            decisions=decisions,
            source_request=source_request,
            source_result=source_result,
            definition=definition,
            eligibility_context=eligibility,
            target_binding=target_binding,
            effect_selection=None,
        )
    setup_state, _setup_corsair_army, _setup_enemy_army = _corsair_state(phase=BattlePhase.SHOOTING)
    setup_state.stage = GameLifecycleStage.SETUP
    with pytest.raises(GameLifecycleError, match="require battle stage"):
        StratagemCostChoiceRequestContext(
            state=setup_state,
            decisions=decisions,
            source_request=source_request,
            source_result=source_result,
            definition=definition,
            eligibility_context=eligibility,
            target_binding=target_binding,
            effect_selection=None,
        )
    wrong_source_request = DecisionRequest(
        request_id="request-wrong-source",
        decision_type="wrong-decision-type",
        actor_id="player-b",
        payload={},
        options=(
            DecisionOption(
                option_id="wrong-source-option",
                label="Wrong",
                payload={},
            ),
        ),
    )
    wrong_source_result = DecisionResult.for_request(
        result_id="result-wrong-source",
        request=wrong_source_request,
        selected_option_id="wrong-source-option",
    )
    with pytest.raises(GameLifecycleError, match="source_request decision_type drift"):
        StratagemCostChoiceRequestContext(
            state=state,
            decisions=decisions,
            source_request=wrong_source_request,
            source_result=wrong_source_result,
            definition=definition,
            eligibility_context=eligibility,
            target_binding=target_binding,
            effect_selection=None,
        )
    with pytest.raises(GameLifecycleError, match="source result request drift"):
        StratagemCostChoiceRequestContext(
            state=state,
            decisions=decisions,
            source_request=source_request,
            source_result=DecisionResult(
                result_id="result-drifted-source",
                request_id="other-request",
                decision_type=source_request.decision_type,
                actor_id=source_request.actor_id,
                selected_option_id="use-enemy-stratagem",
                payload={},
            ),
            definition=definition,
            eligibility_context=eligibility,
            target_binding=target_binding,
            effect_selection=None,
        )
    with pytest.raises(GameLifecycleError, match="request decision_type drift"):
        StratagemCostChoiceResultContext(
            state=state,
            decisions=decisions,
            request=source_request,
            result=source_result,
            source_request=source_request,
            source_result=source_result,
            definition=definition,
            eligibility_context=eligibility,
            target_binding=target_binding,
            effect_selection=None,
        )
    with pytest.raises(GameLifecycleError, match="result request drift"):
        StratagemCostChoiceResultContext(
            state=state,
            decisions=decisions,
            request=cost_choice_request,
            result=DecisionResult(
                result_id="result-cost-choice-drift",
                request_id="other-request",
                decision_type=SELECT_STRATAGEM_COST_MODIFIER_OPTION_DECISION_TYPE,
                actor_id="player-a",
                selected_option_id="cost-choice-validation-use",
                payload={},
            ),
            source_request=source_request,
            source_result=source_result,
            definition=definition,
            eligibility_context=eligibility,
            target_binding=target_binding,
            effect_selection=None,
        )

    with pytest.raises(GameLifecycleError, match="request_handler must be callable"):
        StratagemCostChoiceHookBinding(
            hook_id="bad-choice-request-handler",
            source_id="source",
            request_handler=cast(Any, object()),
        )
    with pytest.raises(GameLifecycleError, match="result_handler must be callable"):
        StratagemCostChoiceHookBinding(
            hook_id="bad-choice-result-handler",
            source_id="source",
            result_handler=cast(Any, object()),
        )
    with pytest.raises(GameLifecycleError, match="bindings must be a tuple"):
        StratagemCostChoiceHookRegistry(
            bindings=cast(tuple[StratagemCostChoiceHookBinding, ...], [])
        )
    with pytest.raises(GameLifecycleError, match="requires hook bindings"):
        StratagemCostChoiceHookRegistry.from_bindings(
            cast(tuple[StratagemCostChoiceHookBinding, ...], (object(),))
        )
    request_registry = StratagemCostChoiceHookRegistry.from_bindings(
        (
            StratagemCostChoiceHookBinding(
                hook_id="bad-choice-return-request",
                source_id="source",
                request_handler=lambda _context: cast(DecisionRequest, object()),
            ),
        )
    )
    with pytest.raises(GameLifecycleError, match="must return DecisionRequest or None"):
        request_registry.next_request_for(request_context)
    with pytest.raises(GameLifecycleError, match="request hooks require a context"):
        request_registry.next_request_for(cast(StratagemCostChoiceRequestContext, object()))
    assert (
        StratagemCostChoiceHookRegistry.from_bindings(
            (
                StratagemCostChoiceHookBinding(
                    hook_id="choice-request-a",
                    source_id="source-a",
                    request_handler=lambda _context: cost_choice_request,
                ),
                StratagemCostChoiceHookBinding(
                    hook_id="choice-request-b",
                    source_id="source-b",
                    request_handler=lambda _context: cost_choice_request,
                ),
            )
        ).next_request_for(request_context)
        == cost_choice_request
    )
    result_registry = StratagemCostChoiceHookRegistry.from_bindings(
        (
            StratagemCostChoiceHookBinding(
                hook_id="bad-choice-return-result",
                source_id="source",
                result_handler=lambda _context: cast(bool, "yes"),
            ),
        )
    )
    with pytest.raises(GameLifecycleError, match="must return bool"):
        result_registry.apply_result(result_context)
    with pytest.raises(GameLifecycleError, match="result hooks require a context"):
        result_registry.apply_result(cast(StratagemCostChoiceResultContext, object()))
    with pytest.raises(GameLifecycleError, match="handled by multiple hooks"):
        StratagemCostChoiceHookRegistry.from_bindings(
            (
                StratagemCostChoiceHookBinding(
                    hook_id="choice-result-a",
                    source_id="source-a",
                    result_handler=lambda _context: True,
                ),
                StratagemCostChoiceHookBinding(
                    hook_id="choice-result-b",
                    source_id="source-b",
                    result_handler=lambda _context: True,
                ),
            )
        ).apply_result(result_context)

    with pytest.raises(GameLifecycleError, match="requires DecisionRequest"):
        stratagem_cost_choice_source_result(cast(DecisionRequest, object()))
    with pytest.raises(GameLifecycleError, match="not a stratagem cost choice"):
        stratagem_cost_choice_source_result(source_request)
    with pytest.raises(GameLifecycleError, match="payload must be an object"):
        stratagem_cost_choice_source_result(
            DecisionRequest(
                request_id="request-cost-choice-string-payload",
                decision_type=SELECT_STRATAGEM_COST_MODIFIER_OPTION_DECISION_TYPE,
                actor_id="player-a",
                payload="not-an-object",
                options=(
                    DecisionOption(
                        option_id="string-payload-option",
                        label="String",
                        payload={},
                    ),
                ),
            )
        )
    with pytest.raises(GameLifecycleError, match="source result is malformed"):
        stratagem_cost_choice_source_result(
            DecisionRequest(
                request_id="request-cost-choice-malformed-source",
                decision_type=SELECT_STRATAGEM_COST_MODIFIER_OPTION_DECISION_TYPE,
                actor_id="player-a",
                payload={"source_decision_result": {"result_id": "only-result-id"}},
                options=(
                    DecisionOption(
                        option_id="malformed-source-option",
                        label="Malformed",
                        payload={},
                    ),
                ),
            )
        )
    with pytest.raises(GameLifecycleError, match="source result must be DecisionResult"):
        source_result_payload_for_cost_choice(cast(DecisionResult, object()))


def test_stratagem_cost_modifier_validation_paths() -> None:
    state, _corsair_army, _enemy_army = _corsair_state(
        phase=BattlePhase.SHOOTING,
        active_player_id="player-b",
    )
    decisions = DecisionController()
    definition = _test_stratagem_definition()
    eligibility = StratagemEligibilityContext.from_state(
        state=state,
        player_id="player-b",
        trigger_kind=TimingTriggerKind.START_PHASE,
    )
    target_binding = StratagemTargetBinding(
        target_kind=StratagemTargetKind.FRIENDLY_UNIT,
        target_player_id="player-b",
        target_unit_instance_id=_ENEMY_UNIT_ID,
    )
    context = StratagemCostModifierContext(
        state=state,
        definition=definition,
        eligibility_context=eligibility,
        target_binding=target_binding,
        effect_selection=None,
        base_command_point_cost=1,
        current_command_point_cost=1,
        decisions=decisions,
        source_decision_request_id="source-request",
        source_decision_result_id="source-result",
    )

    assert StratagemCostModifierRegistry.empty().modified_command_point_cost(context) == 1
    with pytest.raises(GameLifecycleError, match="must be an int"):
        StratagemCostModificationResult(
            command_point_cost=cast(int, "1"),
            modifier_ids=(),
            source_ids=(),
        )
    with pytest.raises(GameLifecycleError, match="modifier_ids must be a tuple"):
        StratagemCostModificationResult(
            command_point_cost=1,
            modifier_ids=cast(tuple[str, ...], []),
            source_ids=(),
        )
    with pytest.raises(GameLifecycleError, match="requires GameState"):
        StratagemCostModifierContext(
            state=cast(GameState, object()),
            definition=definition,
            eligibility_context=eligibility,
            target_binding=target_binding,
            effect_selection=None,
            base_command_point_cost=1,
            current_command_point_cost=1,
        )
    with pytest.raises(GameLifecycleError, match="requires StratagemDefinition"):
        StratagemCostModifierContext(
            state=state,
            definition=cast(StratagemDefinition, object()),
            eligibility_context=eligibility,
            target_binding=target_binding,
            effect_selection=None,
            base_command_point_cost=1,
            current_command_point_cost=1,
        )
    with pytest.raises(GameLifecycleError, match="requires eligibility context"):
        StratagemCostModifierContext(
            state=state,
            definition=definition,
            eligibility_context=cast(StratagemEligibilityContext, object()),
            target_binding=target_binding,
            effect_selection=None,
            base_command_point_cost=1,
            current_command_point_cost=1,
        )
    with pytest.raises(GameLifecycleError, match="target_binding must be"):
        StratagemCostModifierContext(
            state=state,
            definition=definition,
            eligibility_context=eligibility,
            target_binding=cast(StratagemTargetBinding, object()),
            effect_selection=None,
            base_command_point_cost=1,
            current_command_point_cost=1,
        )
    with pytest.raises(GameLifecycleError, match="must not be negative"):
        StratagemCostModifierContext(
            state=state,
            definition=definition,
            eligibility_context=eligibility,
            target_binding=target_binding,
            effect_selection=None,
            base_command_point_cost=-1,
            current_command_point_cost=1,
        )
    with pytest.raises(GameLifecycleError, match="decisions must be DecisionController"):
        StratagemCostModifierContext(
            state=state,
            definition=definition,
            eligibility_context=eligibility,
            target_binding=target_binding,
            effect_selection=None,
            base_command_point_cost=1,
            current_command_point_cost=1,
            decisions=cast(DecisionController, object()),
        )
    with pytest.raises(GameLifecycleError, match="must not be empty"):
        StratagemCostModifierContext(
            state=state,
            definition=definition,
            eligibility_context=eligibility,
            target_binding=target_binding,
            effect_selection=None,
            base_command_point_cost=1,
            current_command_point_cost=1,
            source_decision_request_id=" ",
        )
    with pytest.raises(GameLifecycleError, match="handler must be callable"):
        StratagemCostModifierBinding(
            modifier_id="bad-cost-handler",
            source_id="source",
            handler=cast(Any, object()),
        )
    with pytest.raises(GameLifecycleError, match="bindings must be a tuple"):
        StratagemCostModifierRegistry(bindings=cast(tuple[StratagemCostModifierBinding, ...], []))
    with pytest.raises(GameLifecycleError, match="requires modifier bindings"):
        StratagemCostModifierRegistry.from_bindings(
            cast(tuple[StratagemCostModifierBinding, ...], (object(),))
        )
    with pytest.raises(GameLifecycleError, match="modifiers require a context"):
        StratagemCostModifierRegistry.empty().modified_command_point_cost(
            cast(StratagemCostModifierContext, object())
        )
    with pytest.raises(GameLifecycleError, match="must be an int"):
        StratagemCostModifierRegistry.from_bindings(
            (
                StratagemCostModifierBinding(
                    modifier_id="string-cost",
                    source_id="source",
                    handler=lambda _context: cast(int, "2"),
                ),
            )
        ).modified_command_point_cost(context)


def test_unit_move_completed_mortal_wound_hooks_resolve_and_validate() -> None:
    state, _corsair_army, _enemy_army = _corsair_state(
        phase=BattlePhase.MOVEMENT,
        active_player_id="player-b",
    )
    decisions = DecisionController()
    decisions.event_log.append(
        "test_move_completed",
        {
            "game_id": state.game_id,
            "battle_round": state.battle_round,
            "phase": BattlePhase.MOVEMENT.value,
            "active_player_id": "player-b",
            "unit_instance_id": _ENEMY_UNIT_ID,
            "movement_phase_action": "normal_move",
        },
    )

    def mortal_wound_handler(
        context: UnitMoveCompletedContext,
    ) -> tuple[UnitMoveCompletedMortalWoundEffect, ...]:
        return (
            UnitMoveCompletedMortalWoundEffect(
                hook_id="move-hook",
                source_id="move-source",
                source_rule_id="move-source",
                target_unit_instance_id=context.triggering_unit_instance_id,
                target_player_id=context.triggering_player_id,
                rolling_player_id="player-a",
                trigger_event_id=context.trigger_event_id,
                roll_threshold=2,
                mortal_wounds_expression=DiceExpression(quantity=1, sides=3),
                replay_payload={"test": "move-completed"},
            ),
        )

    registry = UnitMoveCompletedMortalWoundHookRegistry.from_bindings(
        (
            UnitMoveCompletedMortalWoundHookBinding(
                hook_id="move-hook",
                source_id="move-source",
                handler=mortal_wound_handler,
            ),
        )
    )

    status = resolve_unit_move_completed_mortal_wound_hooks(
        state=state,
        decisions=decisions,
        registry=registry,
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(),
        runtime_modifier_registry=RuntimeModifierRegistry.empty(),
        completed_phase=BattlePhase.MOVEMENT,
        event_type="test_move_completed",
        movement_actions=("normal_move",),
    )

    event_types = {record.event_type for record in decisions.event_log.records}
    assert status is None
    assert UNIT_MOVE_COMPLETED_MORTAL_WOUNDS_ROLLED_EVENT in event_types
    assert event_types & {
        UNIT_MOVE_COMPLETED_MORTAL_WOUNDS_RESOLVED_EVENT,
        UNIT_MOVE_COMPLETED_MORTAL_WOUNDS_IGNORED_EVENT,
    }
    event_count_after_first_resolution = len(decisions.event_log.records)
    assert (
        resolve_unit_move_completed_mortal_wound_hooks(
            state=state,
            decisions=decisions,
            registry=registry,
            ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(),
            runtime_modifier_registry=RuntimeModifierRegistry.empty(),
            completed_phase=BattlePhase.MOVEMENT,
            event_type="test_move_completed",
            movement_actions=("normal_move",),
        )
        is None
    )
    assert len(decisions.event_log.records) == event_count_after_first_resolution

    context = UnitMoveCompletedContext(
        state=state,
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(),
        runtime_modifier_registry=RuntimeModifierRegistry.empty(),
        completed_phase=BattlePhase.MOVEMENT,
        trigger_event_id="event-drift",
        trigger_event_payload={"payload": "ok"},
        triggering_unit_instance_id=_ENEMY_UNIT_ID,
        triggering_player_id="player-b",
        movement_action="normal_move",
    )
    with pytest.raises(GameLifecycleError, match="between 2 and 6"):
        UnitMoveCompletedMortalWoundEffect(
            hook_id="move-hook",
            source_id="move-source",
            source_rule_id="move-source",
            target_unit_instance_id=_ENEMY_UNIT_ID,
            target_player_id="player-b",
            rolling_player_id="player-a",
            trigger_event_id="event-drift",
            roll_threshold=1,
            mortal_wounds_expression=DiceExpression(quantity=1, sides=3),
        )
    with pytest.raises(GameLifecycleError, match="hook IDs must be unique"):
        UnitMoveCompletedMortalWoundHookRegistry.from_bindings(
            (registry.all_bindings()[0], registry.all_bindings()[0])
        )
    with pytest.raises(GameLifecycleError, match="effect tuple"):
        UnitMoveCompletedMortalWoundHookRegistry.from_bindings(
            (
                UnitMoveCompletedMortalWoundHookBinding(
                    hook_id="bad-return",
                    source_id="move-source",
                    handler=_bad_unit_move_completed_handler,
                ),
            )
        ).effects_for(context)
    with pytest.raises(GameLifecycleError, match="hook_id drift"):
        UnitMoveCompletedMortalWoundHookRegistry.from_bindings(
            (
                UnitMoveCompletedMortalWoundHookBinding(
                    hook_id="expected-hook",
                    source_id="move-source",
                    handler=lambda _context: (
                        UnitMoveCompletedMortalWoundEffect(
                            hook_id="drifted-hook",
                            source_id="move-source",
                            source_rule_id="move-source",
                            target_unit_instance_id=_ENEMY_UNIT_ID,
                            target_player_id="player-b",
                            rolling_player_id="player-a",
                            trigger_event_id="event-drift",
                            roll_threshold=2,
                            mortal_wounds_expression=DiceExpression(quantity=1, sides=3),
                        ),
                    ),
                ),
            )
        ).effects_for(context)


def test_unit_move_completed_battle_shock_hooks_resolve_and_validate() -> None:
    state, corsair_army, enemy_army = _corsair_state(
        phase=BattlePhase.CHARGE,
        active_player_id="player-a",
    )
    enemy_unit = _unit_with_leadership(enemy_army.units[0], leadership=6)
    enemy_army = replace(enemy_army, units=(enemy_unit,))
    state.army_definitions = [corsair_army, enemy_army]
    state.starting_strength_records = [
        record
        for army in state.army_definitions
        for record in starting_strength_records_for_units(
            player_id=army.player_id,
            units=army.units,
        )
    ]
    decisions = DecisionController()
    decisions.event_log.append(
        "test_charge_completed",
        {
            "game_id": state.game_id,
            "battle_round": state.battle_round,
            "phase": BattlePhase.CHARGE.value,
            "active_player_id": "player-a",
            "unit_instance_id": _CORSAIR_UNIT_ID,
            "movement_phase_action": "charge_move",
        },
    )

    def battle_shock_handler(
        context: UnitMoveCompletedContext,
    ) -> tuple[UnitMoveCompletedBattleShockEffect, ...]:
        return (
            UnitMoveCompletedBattleShockEffect(
                hook_id="battle-shock-hook",
                source_id="battle-shock-source",
                source_rule_id="battle-shock-source",
                target_unit_instance_id=_ENEMY_UNIT_ID,
                target_player_id="player-b",
                trigger_event_id=context.trigger_event_id,
                replay_payload={"test": "battle-shock"},
            ),
        )

    registry = UnitMoveCompletedBattleShockHookRegistry.from_bindings(
        (
            UnitMoveCompletedBattleShockHookBinding(
                hook_id="battle-shock-hook",
                source_id="battle-shock-source",
                handler=battle_shock_handler,
            ),
        )
    )
    ability_indexes = {"player-b": AbilityCatalogIndex.from_records(())}

    resolve_unit_move_completed_battle_shock_hooks(
        state=state,
        decisions=decisions,
        registry=registry,
        battle_shock_hooks=BattleShockHookRegistry.empty(),
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(),
        runtime_modifier_registry=RuntimeModifierRegistry.empty(),
        completed_phase=BattlePhase.CHARGE,
        event_type="test_charge_completed",
        movement_actions=("charge_move",),
        ability_indexes_by_player_id=ability_indexes,
    )

    event_types = {record.event_type for record in decisions.event_log.records}
    assert "battle_shock_test_requested" in event_types
    assert "battle_shock_test_resolved" in event_types
    assert UNIT_MOVE_COMPLETED_BATTLE_SHOCK_RESOLVED_EVENT in event_types
    event_count_after_first_resolution = len(decisions.event_log.records)
    resolve_unit_move_completed_battle_shock_hooks(
        state=state,
        decisions=decisions,
        registry=registry,
        battle_shock_hooks=BattleShockHookRegistry.empty(),
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(),
        runtime_modifier_registry=RuntimeModifierRegistry.empty(),
        completed_phase=BattlePhase.CHARGE,
        event_type="test_charge_completed",
        movement_actions=("charge_move",),
        ability_indexes_by_player_id=ability_indexes,
    )
    assert len(decisions.event_log.records) == event_count_after_first_resolution

    context = UnitMoveCompletedContext(
        state=state,
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(),
        runtime_modifier_registry=RuntimeModifierRegistry.empty(),
        completed_phase=BattlePhase.CHARGE,
        trigger_event_id="event-drift",
        trigger_event_payload={"payload": "ok"},
        triggering_unit_instance_id=_CORSAIR_UNIT_ID,
        triggering_player_id="player-a",
        movement_action="charge_move",
        ability_indexes_by_player_id=ability_indexes,
        decisions=decisions,
    )
    with pytest.raises(GameLifecycleError, match="Unsupported BattleShockTestReason"):
        UnitMoveCompletedBattleShockEffect(
            hook_id="battle-shock-hook",
            source_id="battle-shock-source",
            source_rule_id="battle-shock-source",
            target_unit_instance_id=_ENEMY_UNIT_ID,
            target_player_id="player-b",
            trigger_event_id="event-drift",
            reason=cast(Any, "bad-reason"),
        )
    with pytest.raises(GameLifecycleError, match="hook IDs must be unique"):
        UnitMoveCompletedBattleShockHookRegistry.from_bindings(
            (registry.all_bindings()[0], registry.all_bindings()[0])
        )
    with pytest.raises(GameLifecycleError, match="handler must be callable"):
        UnitMoveCompletedBattleShockHookBinding(
            hook_id="bad-handler",
            source_id="battle-shock-source",
            handler=cast(Any, object()),
        )
    with pytest.raises(GameLifecycleError, match="Battle-shock hooks require a context"):
        registry.effects_for(cast(UnitMoveCompletedContext, object()))
    with pytest.raises(GameLifecycleError, match="effect tuple"):
        UnitMoveCompletedBattleShockHookRegistry.from_bindings(
            (
                UnitMoveCompletedBattleShockHookBinding(
                    hook_id="bad-return",
                    source_id="battle-shock-source",
                    handler=lambda _context: cast(
                        tuple[UnitMoveCompletedBattleShockEffect, ...],
                        [],
                    ),
                ),
            )
        ).effects_for(context)
    with pytest.raises(GameLifecycleError, match="hook_id drift"):
        UnitMoveCompletedBattleShockHookRegistry.from_bindings(
            (
                UnitMoveCompletedBattleShockHookBinding(
                    hook_id="expected-hook",
                    source_id="battle-shock-source",
                    handler=lambda _context: (
                        UnitMoveCompletedBattleShockEffect(
                            hook_id="drifted-hook",
                            source_id="battle-shock-source",
                            source_rule_id="battle-shock-source",
                            target_unit_instance_id=_ENEMY_UNIT_ID,
                            target_player_id="player-b",
                            trigger_event_id="event-drift",
                        ),
                    ),
                ),
            )
        ).effects_for(context)
    with pytest.raises(GameLifecycleError, match="requires Battle-shock hooks"):
        resolve_unit_move_completed_battle_shock_hooks(
            state=state,
            decisions=decisions,
            registry=registry,
            battle_shock_hooks=cast(BattleShockHookRegistry, object()),
            ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(),
            runtime_modifier_registry=RuntimeModifierRegistry.empty(),
            completed_phase=BattlePhase.CHARGE,
            event_type="test_charge_completed",
            movement_actions=("charge_move",),
            ability_indexes_by_player_id=ability_indexes,
        )


def test_unit_move_completed_hook_context_and_event_validation_paths() -> None:
    state, _corsair_army, _enemy_army = _corsair_state(
        phase=BattlePhase.MOVEMENT,
        active_player_id="player-b",
    )
    decisions = DecisionController()
    ruleset = RulesetDescriptor.warhammer_40000_eleventh()
    runtime_modifiers = RuntimeModifierRegistry.empty()
    context = UnitMoveCompletedContext(
        state=state,
        ruleset_descriptor=ruleset,
        runtime_modifier_registry=runtime_modifiers,
        completed_phase=cast(BattlePhase, BattlePhase.MOVEMENT.value),
        trigger_event_id="event-validation",
        trigger_event_payload={"unit_instance_id": _ENEMY_UNIT_ID},
        triggering_unit_instance_id=_ENEMY_UNIT_ID,
        triggering_player_id="player-b",
        movement_action="normal_move",
    )
    assert context.completed_phase is BattlePhase.MOVEMENT

    with pytest.raises(GameLifecycleError, match="requires GameState"):
        UnitMoveCompletedContext(
            state=cast(GameState, object()),
            ruleset_descriptor=ruleset,
            runtime_modifier_registry=runtime_modifiers,
            completed_phase=BattlePhase.MOVEMENT,
            trigger_event_id="event-validation",
            trigger_event_payload={},
            triggering_unit_instance_id=_ENEMY_UNIT_ID,
            triggering_player_id="player-b",
            movement_action="normal_move",
        )
    with pytest.raises(GameLifecycleError, match="requires a RulesetDescriptor"):
        UnitMoveCompletedContext(
            state=state,
            ruleset_descriptor=cast(RulesetDescriptor, object()),
            runtime_modifier_registry=runtime_modifiers,
            completed_phase=BattlePhase.MOVEMENT,
            trigger_event_id="event-validation",
            trigger_event_payload={},
            triggering_unit_instance_id=_ENEMY_UNIT_ID,
            triggering_player_id="player-b",
            movement_action="normal_move",
        )
    with pytest.raises(GameLifecycleError, match="requires a RuntimeModifierRegistry"):
        UnitMoveCompletedContext(
            state=state,
            ruleset_descriptor=ruleset,
            runtime_modifier_registry=cast(RuntimeModifierRegistry, object()),
            completed_phase=BattlePhase.MOVEMENT,
            trigger_event_id="event-validation",
            trigger_event_payload={},
            triggering_unit_instance_id=_ENEMY_UNIT_ID,
            triggering_player_id="player-b",
            movement_action="normal_move",
        )
    with pytest.raises(GameLifecycleError, match="Unsupported battle phase token"):
        UnitMoveCompletedContext(
            state=state,
            ruleset_descriptor=ruleset,
            runtime_modifier_registry=runtime_modifiers,
            completed_phase=cast(BattlePhase, "bad-phase"),
            trigger_event_id="event-validation",
            trigger_event_payload={},
            triggering_unit_instance_id=_ENEMY_UNIT_ID,
            triggering_player_id="player-b",
            movement_action="normal_move",
        )
    with pytest.raises(GameLifecycleError, match="trigger_event_payload must be an object"):
        UnitMoveCompletedContext(
            state=state,
            ruleset_descriptor=ruleset,
            runtime_modifier_registry=runtime_modifiers,
            completed_phase=BattlePhase.MOVEMENT,
            trigger_event_id="event-validation",
            trigger_event_payload=cast(dict[str, JsonValue], "bad"),
            triggering_unit_instance_id=_ENEMY_UNIT_ID,
            triggering_player_id="player-b",
            movement_action="normal_move",
        )
    with pytest.raises(GameLifecycleError, match="movement_action must not be empty"):
        UnitMoveCompletedContext(
            state=state,
            ruleset_descriptor=ruleset,
            runtime_modifier_registry=runtime_modifiers,
            completed_phase=BattlePhase.MOVEMENT,
            trigger_event_id="event-validation",
            trigger_event_payload={},
            triggering_unit_instance_id=_ENEMY_UNIT_ID,
            triggering_player_id="player-b",
            movement_action=" ",
        )

    with pytest.raises(GameLifecycleError, match="requires DiceExpression"):
        UnitMoveCompletedMortalWoundEffect(
            hook_id="move-hook",
            source_id="move-source",
            source_rule_id="move-source",
            target_unit_instance_id=_ENEMY_UNIT_ID,
            target_player_id="player-b",
            rolling_player_id="player-a",
            trigger_event_id="event-validation",
            roll_threshold=2,
            mortal_wounds_expression=cast(DiceExpression, object()),
        )
    with pytest.raises(GameLifecycleError, match="handler must be callable"):
        UnitMoveCompletedMortalWoundHookBinding(
            hook_id="move-hook",
            source_id="move-source",
            handler=cast(Any, object()),
        )
    with pytest.raises(GameLifecycleError, match="bindings must be a tuple"):
        UnitMoveCompletedMortalWoundHookRegistry(
            bindings=cast(tuple[UnitMoveCompletedMortalWoundHookBinding, ...], [])
        )
    with pytest.raises(GameLifecycleError, match="requires hook bindings"):
        UnitMoveCompletedMortalWoundHookRegistry.from_bindings(
            cast(tuple[UnitMoveCompletedMortalWoundHookBinding, ...], (object(),))
        )
    registry = UnitMoveCompletedMortalWoundHookRegistry.from_bindings(
        (
            UnitMoveCompletedMortalWoundHookBinding(
                hook_id="move-hook",
                source_id="move-source",
                handler=lambda _context: (),
            ),
        )
    )
    with pytest.raises(GameLifecycleError, match="hooks require a context"):
        registry.effects_for(cast(UnitMoveCompletedContext, object()))
    with pytest.raises(GameLifecycleError, match="must return mortal wound effects"):
        UnitMoveCompletedMortalWoundHookRegistry.from_bindings(
            (
                UnitMoveCompletedMortalWoundHookBinding(
                    hook_id="move-hook",
                    source_id="move-source",
                    handler=lambda _context: cast(
                        tuple[UnitMoveCompletedMortalWoundEffect, ...],
                        (object(),),
                    ),
                ),
            )
        ).effects_for(context)
    with pytest.raises(GameLifecycleError, match="source_id drift"):
        UnitMoveCompletedMortalWoundHookRegistry.from_bindings(
            (
                UnitMoveCompletedMortalWoundHookBinding(
                    hook_id="move-hook",
                    source_id="move-source",
                    handler=lambda _context: (
                        UnitMoveCompletedMortalWoundEffect(
                            hook_id="move-hook",
                            source_id="other-source",
                            source_rule_id="move-source",
                            target_unit_instance_id=_ENEMY_UNIT_ID,
                            target_player_id="player-b",
                            rolling_player_id="player-a",
                            trigger_event_id="event-validation",
                            roll_threshold=2,
                            mortal_wounds_expression=DiceExpression(quantity=1, sides=3),
                        ),
                    ),
                ),
            )
        ).effects_for(context)
    with pytest.raises(GameLifecycleError, match="trigger event drift"):
        UnitMoveCompletedMortalWoundHookRegistry.from_bindings(
            (
                UnitMoveCompletedMortalWoundHookBinding(
                    hook_id="move-hook",
                    source_id="move-source",
                    handler=lambda _context: (
                        UnitMoveCompletedMortalWoundEffect(
                            hook_id="move-hook",
                            source_id="move-source",
                            source_rule_id="move-source",
                            target_unit_instance_id=_ENEMY_UNIT_ID,
                            target_player_id="player-b",
                            rolling_player_id="player-a",
                            trigger_event_id="other-event",
                            roll_threshold=2,
                            mortal_wounds_expression=DiceExpression(quantity=1, sides=3),
                        ),
                    ),
                ),
            )
        ).effects_for(context)

    with pytest.raises(GameLifecycleError, match="require a DecisionController"):
        resolve_unit_move_completed_mortal_wound_hooks(
            state=state,
            decisions=cast(DecisionController, object()),
            registry=registry,
            ruleset_descriptor=ruleset,
            runtime_modifier_registry=runtime_modifiers,
            completed_phase=BattlePhase.MOVEMENT,
            event_type="move-completed",
            movement_actions=("normal_move",),
        )
    with pytest.raises(GameLifecycleError, match="require a registry"):
        resolve_unit_move_completed_mortal_wound_hooks(
            state=state,
            decisions=decisions,
            registry=cast(UnitMoveCompletedMortalWoundHookRegistry, object()),
            ruleset_descriptor=ruleset,
            runtime_modifier_registry=runtime_modifiers,
            completed_phase=BattlePhase.MOVEMENT,
            event_type="move-completed",
            movement_actions=("normal_move",),
        )
    with pytest.raises(GameLifecycleError, match="require a RulesetDescriptor"):
        resolve_unit_move_completed_mortal_wound_hooks(
            state=state,
            decisions=decisions,
            registry=registry,
            ruleset_descriptor=cast(RulesetDescriptor, object()),
            runtime_modifier_registry=runtime_modifiers,
            completed_phase=BattlePhase.MOVEMENT,
            event_type="move-completed",
            movement_actions=("normal_move",),
        )
    with pytest.raises(GameLifecycleError, match="require a RuntimeModifierRegistry"):
        resolve_unit_move_completed_mortal_wound_hooks(
            state=state,
            decisions=decisions,
            registry=registry,
            ruleset_descriptor=ruleset,
            runtime_modifier_registry=cast(RuntimeModifierRegistry, object()),
            completed_phase=BattlePhase.MOVEMENT,
            event_type="move-completed",
            movement_actions=("normal_move",),
        )
    with pytest.raises(GameLifecycleError, match="movement_actions must be a tuple"):
        resolve_unit_move_completed_mortal_wound_hooks(
            state=state,
            decisions=decisions,
            registry=registry,
            ruleset_descriptor=ruleset,
            runtime_modifier_registry=runtime_modifiers,
            completed_phase=BattlePhase.MOVEMENT,
            event_type="move-completed",
            movement_actions=cast(tuple[str, ...], ["normal_move"]),
        )

    charge_actions: list[str] = []
    charge_decisions = DecisionController()
    charge_decisions.event_log.append(
        "charge_move_completed",
        {
            "game_id": state.game_id,
            "battle_round": state.battle_round,
            "phase": BattlePhase.CHARGE.value,
            "active_player_id": "player-b",
            "unit_instance_id": _ENEMY_UNIT_ID,
        },
    )

    def record_charge_action(
        charge_context: UnitMoveCompletedContext,
    ) -> tuple[UnitMoveCompletedMortalWoundEffect, ...]:
        charge_actions.append(charge_context.movement_action)
        return ()

    charge_registry = UnitMoveCompletedMortalWoundHookRegistry.from_bindings(
        (
            UnitMoveCompletedMortalWoundHookBinding(
                hook_id="charge-hook",
                source_id="charge-source",
                handler=record_charge_action,
            ),
        )
    )
    assert (
        resolve_unit_move_completed_mortal_wound_hooks(
            state=state,
            decisions=charge_decisions,
            registry=charge_registry,
            ruleset_descriptor=ruleset,
            runtime_modifier_registry=runtime_modifiers,
            completed_phase=BattlePhase.CHARGE,
            event_type="charge_move_completed",
            movement_actions=("charge_move",),
        )
        is None
    )
    assert charge_actions == ["charge_move"]

    bad_event_decisions = DecisionController()
    bad_event_decisions.event_log.append(
        "move-completed-missing-action",
        {
            "game_id": state.game_id,
            "battle_round": state.battle_round,
            "phase": BattlePhase.MOVEMENT.value,
            "active_player_id": "player-b",
            "unit_instance_id": _ENEMY_UNIT_ID,
        },
    )
    with pytest.raises(GameLifecycleError, match="missing movement action"):
        resolve_unit_move_completed_mortal_wound_hooks(
            state=state,
            decisions=bad_event_decisions,
            registry=registry,
            ruleset_descriptor=ruleset,
            runtime_modifier_registry=runtime_modifiers,
            completed_phase=BattlePhase.MOVEMENT,
            event_type="move-completed-missing-action",
            movement_actions=("normal_move",),
        )


def _bad_unit_move_completed_handler(
    _context: UnitMoveCompletedContext,
) -> tuple[UnitMoveCompletedMortalWoundEffect, ...]:
    return cast(tuple[UnitMoveCompletedMortalWoundEffect, ...], [])


def _corsair_stratagem_handler_context(
    *,
    state: GameState,
    stratagem_id: str,
    handler_id: str,
    target_unit_id: str,
    phase: BattlePhase,
    trigger_kind: TimingTriggerKind,
    player_id: str = "player-a",
    trigger_payload: JsonValue = None,
    effect_selection: JsonValue = None,
) -> StratagemHandlerContext:
    definition = _corsair_stratagem_definition(stratagem_id)
    target_binding = StratagemTargetBinding(
        target_kind=StratagemTargetKind.FRIENDLY_UNIT,
        target_player_id=player_id,
        target_unit_instance_id=target_unit_id,
    )
    use_id = f"phase17g-corsair:{stratagem_id}:use"
    result = DecisionResult(
        result_id=f"{use_id}:result",
        request_id=f"{use_id}:request",
        decision_type=STRATAGEM_DECISION_TYPE,
        actor_id=player_id,
        selected_option_id=f"{use_id}:option",
        payload=None,
    )
    eligibility_context = StratagemEligibilityContext(
        game_id=state.game_id,
        player_id=player_id,
        battle_round=state.battle_round,
        phase=phase,
        active_player_id=state.active_player_id,
        trigger_kind=trigger_kind,
        timing_window_id=f"{use_id}:window",
        trigger_payload=trigger_payload,
    )
    affected_unit_ids = {target_unit_id}
    if isinstance(effect_selection, dict):
        selected_enemy = effect_selection.get(ENGAGED_ENEMY_UNIT_CONTEXT_KEY)
        if type(selected_enemy) is str:
            affected_unit_ids.add(selected_enemy)
    use_record = StratagemUseRecord(
        use_id=use_id,
        player_id=player_id,
        stratagem_id=stratagem_id,
        source_id=definition.source_id,
        battle_round=state.battle_round,
        phase=phase,
        active_player_id=state.active_player_id,
        timing_window_id=eligibility_context.timing_window_id,
        request_id=result.request_id,
        result_id=result.result_id,
        selected_option_id=result.selected_option_id,
        target_binding=target_binding,
        targeted_unit_instance_ids=(target_unit_id,),
        affected_unit_instance_ids=tuple(sorted(affected_unit_ids)),
        command_point_cost=1,
        command_point_transaction_id=f"{use_id}:cp",
        handler_id=handler_id,
        effect_selection=effect_selection,
        effect_payload=definition.effect_payload,
    )
    return StratagemHandlerContext(
        state=state,
        decisions=DecisionController(),
        result=result,
        eligibility_context=eligibility_context,
        definition=definition,
        target_binding=target_binding,
        use_record=use_record,
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(),
        army_catalog=ArmyCatalog.phase9a_canonical_content_pack(),
    )


def _corsair_stratagem_definition(stratagem_id: str) -> StratagemDefinition:
    for record in manifest.runtime_contribution().stratagem_records:
        if record.definition.stratagem_id == stratagem_id:
            return record.definition
    raise AssertionError(f"Missing Corsair stratagem definition: {stratagem_id}")


def _corsair_stratagem_record(stratagem_id: str) -> StratagemCatalogRecord:
    for record in manifest.runtime_contribution().stratagem_records:
        if record.definition.stratagem_id == stratagem_id:
            return record
    raise AssertionError(f"Missing Corsair stratagem record: {stratagem_id}")


def _corsair_test_weapon_profile(*, ap: int) -> WeaponProfile:
    return WeaponProfile(
        profile_id="phase17g-corsair-test-shuriken-rifle",
        name="Corsair test shuriken rifle",
        range_profile=RangeProfile.distance(24),
        attack_profile=AttackProfile.fixed(1),
        skill=CharacteristicValue.from_raw(Characteristic.BALLISTIC_SKILL, 3),
        strength=CharacteristicValue.from_raw(Characteristic.STRENGTH, 4),
        armor_penetration=CharacteristicValue.from_raw(Characteristic.ARMOR_PENETRATION, ap),
        damage_profile=DamageProfile.fixed(1),
    )


def _invalid_ability_descriptor(
    *,
    parameters: tuple[AbilityParameter, ...],
) -> AbilityDescriptor:
    descriptor = object.__new__(AbilityDescriptor)
    object.__setattr__(descriptor, "ability_id", "rapid-fire:invalid")
    object.__setattr__(descriptor, "name", "Rapid Fire Invalid")
    object.__setattr__(descriptor, "ability_kind", AbilityKind.RAPID_FIRE)
    object.__setattr__(descriptor, "parameters", parameters)
    object.__setattr__(descriptor, "target_keywords", ())
    object.__setattr__(descriptor, "timing", None)
    object.__setattr__(descriptor, "condition", None)
    return descriptor


def _json_object(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        raise TypeError("Expected JSON object.")
    return cast(dict[str, object], value)


def _corsair_lifecycle_for_state(*, config: GameConfig, state: GameState) -> GameLifecycle:
    lifecycle = GameLifecycle()
    lifecycle.start(config)
    _use_source_backed_lifecycle_armies(config=config, state=state)
    lifecycle.state = state
    refresh_runtime_content_bundle = cast(
        Callable[[], None],
        object.__getattribute__(
            lifecycle,
            "_refresh_runtime_content_bundle_if_armies_mustered",
        ),
    )
    refresh_runtime_content_bundle()
    return lifecycle


def _corsair_runtime_bundle_for_state(state: GameState) -> RuntimeContentBundle:
    catalog = _corsair_mustering_catalog()
    armies = tuple(state.army_definitions)
    activation = RuntimeContentActivation.from_armies(armies=armies, catalog=catalog)
    return RuntimeContentBundle.from_contributions(
        activation=activation.with_reachable_content(
            reachable_content_ids=activation.roster_content_ids(),
            selected_module_paths=(),
            source_package_ids=(),
            source_package_hashes=(),
            selected_execution_record_ids=_corsair_selected_enhancement_execution_record_ids(
                activation.selected_enhancement_ids
            ),
            unsupported_content_ids=(),
            unsupported_reasons_by_content_id={},
        ),
        armies=armies,
        catalog=catalog,
        contributions=(manifest.runtime_contribution(),),
        faction_execution_records=faction_execution_2026_27.execution_records(),
    )


def _corsair_selected_enhancement_execution_record_ids(
    enhancement_ids: tuple[str, ...],
) -> tuple[str, ...]:
    selected_ids = set(enhancement_ids)
    record_ids: list[str] = []
    if enhancements.ARCHRAIDER_ENHANCEMENT_ID in selected_ids:
        record_ids.append(enhancements.ARCHRAIDER_SOURCE_RULE_ID)
    if enhancements.INFAMY_ENHANCEMENT_ID in selected_ids:
        record_ids.append(enhancements.INFAMY_SOURCE_RULE_ID)
    if enhancements.VOIDSTONE_ENHANCEMENT_ID in selected_ids:
        record_ids.append(enhancements.VOIDSTONE_SOURCE_RULE_ID)
    if enhancements.WEBWAY_PATHSTONE_ENHANCEMENT_ID in selected_ids:
        record_ids.append(enhancements.WEBWAY_PATHSTONE_SOURCE_RULE_ID)
    return tuple(sorted(record_ids))


def _use_source_backed_lifecycle_armies(*, config: GameConfig, state: GameState) -> None:
    positions_by_unit_id = _unit_x_positions_by_id(state)
    if _ENEMY_UNIT_ID in positions_by_unit_id:
        positions_by_unit_id[_LIFECYCLE_ENEMY_UNIT_ID] = positions_by_unit_id[_ENEMY_UNIT_ID]
    source_armies = tuple(
        _source_backed_lifecycle_army(muster_army(catalog=config.army_catalog, request=request))
        for request in config.army_muster_requests
    )
    state.army_definitions = list(source_armies)
    state.starting_strength_records = [
        record
        for army in source_armies
        for record in starting_strength_records_for_units(
            player_id=army.player_id,
            units=army.units,
        )
    ]
    state.starting_strength_records.sort(key=lambda record: record.unit_instance_id)
    _record_lifecycle_secondary_choices(state)
    battlefield = state.battlefield_state
    if battlefield is None:
        raise AssertionError("Lifecycle Corsair fixture requires battlefield state.")
    state.battlefield_state = BattlefieldRuntimeState(
        battlefield_id=battlefield.battlefield_id,
        battlefield_width_inches=battlefield.battlefield_width_inches,
        battlefield_depth_inches=battlefield.battlefield_depth_inches,
        placed_armies=tuple(
            _source_backed_lifecycle_placed_army(
                army,
                positions_by_unit_id=positions_by_unit_id,
            )
            for army in source_armies
        ),
        removed_model_ids=battlefield.removed_model_ids,
    )


def _record_lifecycle_secondary_choices(state: GameState) -> None:
    for player_id in state.player_ids:
        if state.secondary_mission_choice_for_player(player_id) is not None:
            continue
        state.record_secondary_mission_choice(
            SecondaryMissionChoice(
                player_id=player_id,
                mode=SecondaryMissionMode.FIXED,
                fixed_mission_ids=("area-denial", "assassination"),
            )
        )


def _source_backed_lifecycle_army(army: ArmyDefinition) -> ArmyDefinition:
    keep_unit_ids = (
        {
            _CORSAIR_UNIT_ID,
            _ARCHRAIDER_UNIT_ID,
            _VOIDSTONE_UNIT_ID,
            _WEBWAY_UNIT_ID,
        }
        if army.player_id == "player-a"
        else {_LIFECYCLE_ENEMY_UNIT_ID}
    )
    return replace(
        army,
        units=tuple(
            replace(unit, own_models=(unit.own_models[0],))
            for unit in army.units
            if unit.unit_instance_id in keep_unit_ids
        ),
        attached_units=(),
    )


def _source_backed_lifecycle_placed_army(
    army: ArmyDefinition,
    *,
    positions_by_unit_id: dict[str, float],
) -> PlacedArmy:
    return PlacedArmy(
        army_id=army.army_id,
        player_id=army.player_id,
        unit_placements=tuple(
            _unit_placement(
                army.army_id,
                army.player_id,
                unit,
                x=positions_by_unit_id.get(unit.unit_instance_id, _fallback_unit_x(unit)),
            )
            for unit in army.units
        ),
    )


def _unit_x_positions_by_id(state: GameState) -> dict[str, float]:
    battlefield = state.battlefield_state
    if battlefield is None:
        raise AssertionError("Lifecycle Corsair fixture requires battlefield state.")
    positions: dict[str, float] = {}
    for placed_army in battlefield.placed_armies:
        for unit_placement in placed_army.unit_placements:
            positions[unit_placement.unit_instance_id] = unit_placement.model_placements[
                0
            ].pose.position.x
    return positions


def _fallback_unit_x(unit: UnitInstance) -> float:
    if unit.unit_instance_id.startswith("army-a:"):
        return 5.0
    return 50.0


def _decision_request(status: LifecycleStatus) -> DecisionRequest:
    request = status.decision_request
    if request is None:
        raise AssertionError(f"Expected lifecycle decision request, got {status.status_kind}.")
    return request


def _lifecycle_state(lifecycle: GameLifecycle) -> GameState:
    if lifecycle.state is None:
        raise AssertionError("Lifecycle state is missing.")
    return lifecycle.state


def _refresh_lifecycle_runtime_content(lifecycle: GameLifecycle) -> None:
    refresh = cast(
        Callable[[], None],
        object.__getattribute__(
            lifecycle,
            "_refresh_runtime_content_bundle_if_armies_mustered",
        ),
    )
    refresh()


def _lifecycle_event_payloads(
    lifecycle: GameLifecycle,
    event_type: str,
) -> tuple[dict[str, JsonValue], ...]:
    return tuple(
        cast(dict[str, JsonValue], event.payload)
        for event in lifecycle.decision_controller.event_log.records
        if event.event_type == event_type
    )


def _attack_step_payload(
    events: tuple[dict[str, JsonValue], ...],
    step: AttackSequenceStep,
) -> dict[str, JsonValue]:
    for event in events:
        if event["step"] == step.value:
            return event
    raise AssertionError(f"Missing attack sequence step {step.value}.")


def _drain_until_downstream_attack_resolution(
    lifecycle: GameLifecycle,
    status: LifecycleStatus,
    *,
    result_id_prefix: str,
) -> LifecycleStatus:
    current = status
    downstream_steps = {
        AttackSequenceStep.ALLOCATE.value,
        AttackSequenceStep.SAVE.value,
        AttackSequenceStep.DAMAGE.value,
    }
    for index in range(128):
        if {
            cast(str, payload["step"])
            for payload in _lifecycle_event_payloads(lifecycle, "attack_sequence_step")
        } & downstream_steps:
            return current
        if (
            current.status_kind is not LifecycleStatusKind.WAITING_FOR_DECISION
            or current.decision_request is None
        ):
            return current
        request = current.decision_request
        if request.is_parameterized_submission_request():
            raise AssertionError(f"Unexpected parameterized decision {request.decision_type}.")
        if request.decision_type == DICE_REROLL_DECISION_TYPE:
            option_id = "decline"
        elif request.decision_type == STRATAGEM_DECISION_TYPE:
            option_id = DECLINE_STRATAGEM_WINDOW_OPTION_ID
        else:
            option_id = request.options[0].option_id
        current = lifecycle.submit_decision(
            DecisionResult.for_request(
                result_id=f"{result_id_prefix}-{index:03d}",
                request=request,
                selected_option_id=option_id,
            )
        )
    raise AssertionError("Attack sequence did not reach allocation, save, or damage resolution.")


def _stratagem_option(request: DecisionRequest, stratagem_id: str) -> DecisionOption:
    option_prefix = f"use-stratagem:{stratagem_id}:"
    for option in request.options:
        if option.option_id.startswith(option_prefix):
            return option
    raise AssertionError(f"Missing Stratagem option {stratagem_id}.")


def _first_primary_melee_weapon_payload(
    proposal_request: MeleeDeclarationProposalRequest,
) -> dict[str, object]:
    for weapon in proposal_request.available_weapons:
        weapon_payload = cast(dict[str, object], weapon)
        if weapon_payload["is_extra_attacks"] is True:
            continue
        engaged_target_ids = cast(list[str], weapon_payload["engaged_target_unit_instance_ids"])
        if engaged_target_ids:
            return weapon_payload
    raise AssertionError("Missing primary engaged melee weapon.")


def _mark_player_as_corsair_coterie(state: GameState, *, player_id: str) -> None:
    updated_armies: list[ArmyDefinition] = []
    for army in state.army_definitions:
        if army.player_id != player_id:
            updated_armies.append(army)
            continue
        updated_armies.append(
            replace(
                army,
                detachment_selection=replace(
                    army.detachment_selection,
                    faction_id="aeldari",
                    detachment_ids=("corsair-coterie",),
                ),
                units=tuple(
                    replace(
                        unit,
                        keywords=("ANHRATHE", "INFANTRY"),
                        faction_keywords=("AELDARI",),
                    )
                    for unit in army.units
                ),
            )
        )
    state.army_definitions = updated_armies


def _event_records(decisions: DecisionController, event_type: str) -> tuple[EventRecord, ...]:
    return tuple(
        record for record in decisions.event_log.records if record.event_type == event_type
    )


def _event_payloads(
    decisions: DecisionController,
    event_type: str,
) -> tuple[dict[str, JsonValue], ...]:
    payloads: list[dict[str, JsonValue]] = []
    for record in _event_records(decisions, event_type):
        if not isinstance(record.payload, dict):
            raise TypeError(f"{event_type} payload must be an object.")
        payloads.append(record.payload)
    return tuple(payloads)


def _event_index(decisions: DecisionController, event_type: str) -> int:
    for index, record in enumerate(decisions.event_log.records):
        if record.event_type == event_type:
            return index
    raise AssertionError(f"Missing event {event_type}.")


def _event_record_by_id(decisions: DecisionController, event_id: str) -> EventRecord:
    for record in decisions.event_log.records:
        if record.event_id == event_id:
            return record
    raise AssertionError(f"Missing event record {event_id}.")


def _json_payload_string(payload: dict[str, JsonValue], key: str) -> str:
    value = payload.get(key)
    if type(value) is not str:
        raise AssertionError(f"{key} must be a string.")
    return value


def _unit_move_completed_mortal_wound_processed_event_count(
    decisions: DecisionController,
) -> int:
    return len(
        _event_records(decisions, UNIT_MOVE_COMPLETED_MORTAL_WOUNDS_PENDING_EVENT)
        + _event_records(decisions, UNIT_MOVE_COMPLETED_MORTAL_WOUNDS_RESOLVED_EVENT)
        + _event_records(decisions, UNIT_MOVE_COMPLETED_MORTAL_WOUNDS_IGNORED_EVENT)
    )


def _corsair_state(
    *,
    enhancement_assignments: tuple[EnhancementAssignment, ...] = (),
    phase: BattlePhase = BattlePhase.MOVEMENT,
    active_player_id: str = "player-a",
    corsair_keywords: tuple[str, ...] = ("ANHRATHE", "INFANTRY"),
    corsair_x: float = 10.0,
    archraider_x: float = 15.0,
    voidstone_x: float = 20.0,
    webway_x: float = 25.0,
    enemy_x: float = 30.0,
) -> tuple[GameState, ArmyDefinition, ArmyDefinition]:
    ruleset = RulesetDescriptor.warhammer_40000_eleventh()
    catalog = ArmyCatalog.phase9a_canonical_content_pack()
    corsairs = _unit(
        unit_instance_id=_CORSAIR_UNIT_ID,
        datasheet_id="aeldari-corsairs",
        name="Corsairs",
        keywords=corsair_keywords,
        faction_keywords=("AELDARI",),
        objective_control=3,
    )
    archraider = _unit(
        unit_instance_id=_ARCHRAIDER_UNIT_ID,
        datasheet_id="aeldari-archraider",
        name="Archraider",
        keywords=("ANHRATHE", "CHARACTER", "INFANTRY"),
        faction_keywords=("AELDARI",),
        objective_control=1,
    )
    voidstone = _unit(
        unit_instance_id=_VOIDSTONE_UNIT_ID,
        datasheet_id="aeldari-voidstone",
        name="Voidstone Bearers",
        keywords=("ANHRATHE", "INFANTRY"),
        faction_keywords=("AELDARI",),
        objective_control=1,
    )
    webway = _unit(
        unit_instance_id=_WEBWAY_UNIT_ID,
        datasheet_id="aeldari-webway",
        name="Webway Bearers",
        keywords=("ANHRATHE", "INFANTRY"),
        faction_keywords=("AELDARI",),
        objective_control=1,
    )
    enemy = _unit(
        unit_instance_id=_ENEMY_UNIT_ID,
        datasheet_id="enemy-raiders",
        name="Enemy Raiders",
        keywords=("INFANTRY",),
        faction_keywords=("OPFOR",),
        objective_control=1,
    )
    corsair_army = _army(
        army_id="army-a",
        player_id="player-a",
        catalog_id=catalog.catalog_id,
        source_package_id=catalog.source_package_id,
        ruleset_id=catalog.ruleset_id,
        faction_id="aeldari",
        detachment_id="corsair-coterie",
        units=(corsairs, archraider, voidstone, webway),
        enhancement_assignments=enhancement_assignments,
    )
    enemy_army = _army(
        army_id="army-b",
        player_id="player-b",
        catalog_id=catalog.catalog_id,
        source_package_id=catalog.source_package_id,
        ruleset_id=catalog.ruleset_id,
        faction_id="opfor",
        detachment_id="target-practice",
        units=(enemy,),
    )
    battle_phases = tuple(ruleset.battle_phase_sequence.phases)
    state = GameState(
        game_id="corsair-coterie-game",
        ruleset_descriptor_hash=ruleset.descriptor_hash,
        stage=GameLifecycleStage.BATTLE,
        setup_sequence=tuple(ruleset.setup_sequence.steps),
        battle_phase_sequence=battle_phases,
        player_ids=("player-a", "player-b"),
        turn_order=("player-a", "player-b"),
        tactical_secondary_draw_count=2,
        setup_step_index=None,
        battle_phase_index=battle_phases.index(phase),
        battle_round=1,
        active_player_id=active_player_id,
        army_definitions=[corsair_army, enemy_army],
        mission_setup=_mission_setup(),
        battlefield_state=BattlefieldRuntimeState(
            battlefield_id="battlefield-corsair-coterie",
            battlefield_width_inches=60.0,
            battlefield_depth_inches=44.0,
            placed_armies=(
                PlacedArmy(
                    army_id="army-a",
                    player_id="player-a",
                    unit_placements=(
                        _unit_placement("army-a", "player-a", corsairs, x=corsair_x),
                        _unit_placement("army-a", "player-a", archraider, x=archraider_x),
                        _unit_placement("army-a", "player-a", voidstone, x=voidstone_x),
                        _unit_placement("army-a", "player-a", webway, x=webway_x),
                    ),
                ),
                PlacedArmy(
                    army_id="army-b",
                    player_id="player-b",
                    unit_placements=(_unit_placement("army-b", "player-b", enemy, x=enemy_x),),
                ),
            ),
        ),
    )
    return state, corsair_army, enemy_army


def _corsair_mustering_catalog() -> ArmyCatalog:
    base_catalog = ArmyCatalog.phase9a_canonical_content_pack()
    base_datasheet = base_catalog.datasheet_by_id("core-intercessor-like-infantry")
    datasheets = (
        _corsair_datasheet(
            base_datasheet,
            datasheet_id="phase17g-corsair-archraider",
            name="Corsair Archraider",
            keywords=("Anhrathe", "Character", "Infantry"),
        ),
        _corsair_datasheet(
            base_datasheet,
            datasheet_id="phase17g-corsairs",
            name="Corsairs",
            keywords=("Anhrathe", "Infantry"),
        ),
        _corsair_datasheet(
            base_datasheet,
            datasheet_id="phase17g-voidstone-bearers",
            name="Voidstone Bearers",
            keywords=("Anhrathe", "Infantry"),
        ),
        _corsair_datasheet(
            base_datasheet,
            datasheet_id="phase17g-webway-bearers",
            name="Webway Bearers",
            keywords=("Anhrathe", "Infantry"),
        ),
        _corsair_datasheet(
            base_datasheet,
            datasheet_id="phase17g-guardian-defenders",
            name="Guardian Defenders",
            keywords=("Infantry",),
        ),
        _corsair_datasheet(
            base_datasheet,
            datasheet_id="phase17g-corsair-bikers",
            name="Corsair Bikers",
            keywords=("Anhrathe", "Mounted"),
        ),
    )
    enhancement_ids = (
        enhancements.ARCHRAIDER_ENHANCEMENT_ID,
        enhancements.INFAMY_ENHANCEMENT_ID,
        enhancements.VOIDSTONE_ENHANCEMENT_ID,
        enhancements.WEBWAY_PATHSTONE_ENHANCEMENT_ID,
    )
    return ArmyCatalog(
        catalog_id="phase17g-corsair-coterie-catalog",
        ruleset_id=base_catalog.ruleset_id,
        source_package_id="phase17g-corsair-coterie-source",
        datasheets=datasheets,
        wargear=base_catalog.wargear,
        factions=(
            FactionDefinition(
                faction_id="aeldari",
                name="Aeldari",
                faction_keywords=("Aeldari",),
                source_ids=("phase17g:aeldari",),
            ),
        ),
        detachments=(
            DetachmentDefinition(
                detachment_id="corsair-coterie",
                name="Corsair Coterie",
                faction_id="aeldari",
                detachment_point_cost=1,
                unit_datasheet_ids=tuple(datasheet.datasheet_id for datasheet in datasheets),
                force_disposition_ids=("phase17g-force",),
                enhancement_ids=enhancement_ids,
                source_ids=("phase17g:aeldari:corsair-coterie",),
            ),
        ),
        enhancements=tuple(
            EnhancementDefinition(
                enhancement_id=enhancement_id,
                name=enhancement_id.replace("-", " ").title(),
                source_id=f"phase17g:aeldari:corsair-coterie:{enhancement_id}",
                points=10,
            )
            for enhancement_id in enhancement_ids
        ),
        source_ids=("phase17g:catalog:aeldari-corsair-coterie",),
    )


def _corsair_game_config(
    *,
    enhancement_assignments: tuple[EnhancementAssignment, ...] = (),
) -> GameConfig:
    catalog = _corsair_mustering_catalog()
    return GameConfig(
        game_id="phase17g-corsair-coterie-config",
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(),
        army_catalog=catalog,
        army_muster_requests=(
            _corsair_muster_request(
                catalog,
                army_id="army-a",
                player_id="player-a",
                enhancement_assignments=enhancement_assignments,
            ),
            _corsair_muster_request(
                catalog,
                army_id="army-b",
                player_id="player-b",
                enhancement_assignments=(),
            ),
        ),
        player_ids=("player-a", "player-b"),
        turn_order=("player-a", "player-b"),
        fixed_secondary_mission_ids=("area-denial", "assassination"),
        mission_setup=_mission_setup(),
        allow_legacy_non_strict_rosters=True,
    )


def _corsair_datasheet(
    base_datasheet: DatasheetDefinition,
    *,
    datasheet_id: str,
    name: str,
    keywords: tuple[str, ...],
) -> DatasheetDefinition:
    return replace(
        base_datasheet,
        datasheet_id=datasheet_id,
        name=name,
        keywords=DatasheetKeywordSet(
            keywords=keywords,
            faction_keywords=("Aeldari",),
        ),
        attachment_eligibilities=(),
    )


def _corsair_muster_request(
    catalog: ArmyCatalog,
    *,
    enhancement_assignments: tuple[EnhancementAssignment, ...],
    army_id: str = "army-a",
    player_id: str = "player-a",
) -> ArmyMusterRequest:
    unit_selection_ids_by_datasheet = {
        "archraider": "phase17g-corsair-archraider",
        "corsairs": "phase17g-corsairs",
        "voidstone-bearers": "phase17g-voidstone-bearers",
        "webway-bearers": "phase17g-webway-bearers",
        "guardian-defenders": "phase17g-guardian-defenders",
        "corsair-bikers": "phase17g-corsair-bikers",
    }
    unit_selections = tuple(
        _corsair_unit_selection(
            unit_selection_id=unit_selection_id,
            datasheet_id=datasheet_id,
        )
        for unit_selection_id, datasheet_id in unit_selection_ids_by_datasheet.items()
    )
    return ArmyMusterRequest(
        army_id=army_id,
        player_id=player_id,
        catalog_id=catalog.catalog_id,
        source_package_id=catalog.source_package_id,
        ruleset_id=catalog.ruleset_id,
        detachment_selection=DetachmentSelection(
            faction_id="aeldari",
            detachment_ids=("corsair-coterie",),
            enhancement_ids=tuple(
                sorted({assignment.enhancement_id for assignment in enhancement_assignments})
            ),
        ),
        force_disposition_id="phase17g-force",
        unit_selections=unit_selections,
        unit_points=tuple(
            RosterUnitPointValue(
                unit_selection_id=selection.unit_selection_id,
                points=100,
                source_id=f"phase17g:points:{selection.unit_selection_id}",
            )
            for selection in unit_selections
        ),
        enhancement_assignments=enhancement_assignments,
        warlord_selection=WarlordSelection(
            unit_selection_id="archraider",
            source_id="phase17g:warlord:archraider",
        ),
    )


def _corsair_unit_selection(
    *,
    unit_selection_id: str,
    datasheet_id: str,
) -> UnitMusterSelection:
    return UnitMusterSelection(
        unit_selection_id=unit_selection_id,
        datasheet_id=datasheet_id,
        model_profile_selections=(
            ModelProfileSelection(
                model_profile_id="core-intercessor-like",
                model_count=5,
            ),
        ),
        wargear_selections=(),
    )


def _army(
    *,
    army_id: str,
    player_id: str,
    catalog_id: str,
    source_package_id: str,
    ruleset_id: RulesetId,
    faction_id: str,
    detachment_id: str,
    units: tuple[UnitInstance, ...],
    enhancement_assignments: tuple[EnhancementAssignment, ...] = (),
) -> ArmyDefinition:
    return ArmyDefinition(
        army_id=army_id,
        player_id=player_id,
        catalog_id=catalog_id,
        source_package_id=source_package_id,
        ruleset_id=ruleset_id,
        detachment_selection=DetachmentSelection(
            faction_id=faction_id,
            detachment_ids=(detachment_id,),
            enhancement_ids=(
                enhancements.ARCHRAIDER_ENHANCEMENT_ID,
                enhancements.INFAMY_ENHANCEMENT_ID,
                enhancements.VOIDSTONE_ENHANCEMENT_ID,
                enhancements.WEBWAY_PATHSTONE_ENHANCEMENT_ID,
            ),
            stratagem_ids=(),
        ),
        force_disposition_id="phase17g-force",
        units=units,
        enhancement_assignments=enhancement_assignments,
    )


def _unit(
    *,
    unit_instance_id: str,
    datasheet_id: str,
    name: str,
    keywords: tuple[str, ...],
    faction_keywords: tuple[str, ...],
    objective_control: int,
) -> UnitInstance:
    model = _model(
        model_instance_id=f"{unit_instance_id}:model-001",
        datasheet_id=datasheet_id,
        model_profile_id=f"{datasheet_id}-profile",
        name=f"{name} model",
        keywords=keywords,
        objective_control=objective_control,
    )
    return UnitInstance(
        unit_instance_id=unit_instance_id,
        datasheet_id=datasheet_id,
        name=name,
        keywords=keywords,
        faction_keywords=faction_keywords,
        datasheet_abilities=(),
        datasheet_source_ids=(f"source:{datasheet_id}",),
        own_models=(model,),
        wargear_selections=(),
    )


def _unit_with_leadership(unit: UnitInstance, *, leadership: int) -> UnitInstance:
    model = unit.own_models[0]
    return replace(
        unit,
        own_models=(
            replace(
                model,
                characteristics=(
                    *model.characteristics,
                    CharacteristicValue.from_raw(Characteristic.LEADERSHIP, leadership),
                ),
            ),
        ),
    )


def _model(
    *,
    model_instance_id: str,
    datasheet_id: str,
    model_profile_id: str,
    name: str,
    keywords: tuple[str, ...],
    objective_control: int,
) -> ModelInstance:
    base_size = BaseSizeDefinition.circular(32.0)
    return ModelInstance(
        model_instance_id=model_instance_id,
        datasheet_id=datasheet_id,
        model_profile_id=model_profile_id,
        name=name,
        characteristics=(
            CharacteristicValue.from_raw(Characteristic.WOUNDS, 1),
            CharacteristicValue.from_raw(Characteristic.SAVE, 4),
            CharacteristicValue.from_raw(Characteristic.OBJECTIVE_CONTROL, objective_control),
        ),
        base_size=base_size,
        geometry=ModelGeometry.from_base_size(
            base_size,
            keywords=keywords,
            geometry_source_id=model_profile_id,
        ),
        starting_wounds=1,
        wounds_remaining=1,
        wargear_ids=(),
        source_ids=(f"source:{model_profile_id}",),
    )


def _unit_placement(
    army_id: str,
    player_id: str,
    unit: UnitInstance,
    *,
    x: float,
) -> UnitPlacement:
    return UnitPlacement(
        army_id=army_id,
        player_id=player_id,
        unit_instance_id=unit.unit_instance_id,
        model_placements=(
            ModelPlacement(
                army_id=army_id,
                player_id=player_id,
                unit_instance_id=unit.unit_instance_id,
                model_instance_id=unit.own_models[0].model_instance_id,
                pose=Pose.at(x=x, y=22.0, facing_degrees=0.0),
            ),
        ),
    )


def _unit_with_second_model_and_dead_model(
    unit: UnitInstance,
    *,
    dead_model_index: int,
) -> UnitInstance:
    if len(unit.own_models) != 1:
        raise AssertionError("Test unit must start with one model.")
    if dead_model_index not in (0, 1):
        raise AssertionError("Dead model index must select one of the test models.")
    first_model = unit.own_models[0]
    second_model = replace(
        first_model,
        model_instance_id=f"{unit.unit_instance_id}:model-002",
        name=f"{first_model.name} 2",
    )
    models = [first_model, second_model]
    models[dead_model_index] = replace(models[dead_model_index], wounds_remaining=0)
    return replace(unit, own_models=tuple(models))


def _replace_unit_instance_in_state(
    *,
    state: GameState,
    replacement: UnitInstance,
) -> None:
    for army_index, army in enumerate(state.army_definitions):
        units = tuple(
            replacement if unit.unit_instance_id == replacement.unit_instance_id else unit
            for unit in army.units
        )
        if units != army.units:
            state.army_definitions[army_index] = replace(army, units=units)
            return
    raise AssertionError(f"Missing unit {replacement.unit_instance_id}.")


def _set_unit_model_x_positions(
    *,
    state: GameState,
    army_id: str,
    player_id: str,
    unit: UnitInstance,
    model_xs: tuple[float, ...],
) -> None:
    if len(model_xs) != len(unit.own_models):
        raise AssertionError("Test placement positions must match unit models.")
    battlefield = state.battlefield_state
    if battlefield is None:
        raise AssertionError("Test state requires a battlefield.")
    state.battlefield_state = battlefield.with_unit_placement(
        UnitPlacement(
            army_id=army_id,
            player_id=player_id,
            unit_instance_id=unit.unit_instance_id,
            model_placements=tuple(
                ModelPlacement(
                    army_id=army_id,
                    player_id=player_id,
                    unit_instance_id=unit.unit_instance_id,
                    model_instance_id=model.model_instance_id,
                    pose=Pose.at(x=x, y=22.0, facing_degrees=0.0),
                )
                for model, x in zip(unit.own_models, model_xs, strict=True)
            ),
        )
    )


def _assignment(enhancement_id: str, target_unit_selection_id: str) -> EnhancementAssignment:
    return EnhancementAssignment(
        enhancement_id=enhancement_id,
        target_unit_selection_id=target_unit_selection_id,
        source_id=f"assignment:{enhancement_id}:{target_unit_selection_id}",
    )


def _mission_setup() -> MissionSetup:
    return MissionSetup.from_mission_pack(
        mission_pack=chapter_approved_2026_27_mission_pack(),
        mission_pool_entry_id="mission-take-and-hold-vs-purge-the-foe-layout-3",
        terrain_layout_id="take-and-hold-vs-purge-the-foe-layout-3",
        attacker_player_id="player-a",
        defender_player_id="player-b",
    )


def _record_archraider_model_selection(state: GameState) -> None:
    selected_model_instance_id = (
        _unit_by_id(state, _ARCHRAIDER_UNIT_ID).own_models[0].model_instance_id
    )
    state.record_faction_rule_state(
        FactionRuleState(
            state_id=f"{enhancements.ARCHRAIDER_SETUP_HOOK_ID}:{_ARCHRAIDER_UNIT_ID}:selected",
            player_id="player-a",
            faction_id="aeldari",
            source_rule_id=enhancements.ARCHRAIDER_SOURCE_RULE_ID,
            state_kind=enhancements.ARCHRAIDER_STATE_KIND,
            setup_step=SetupStep.DECLARE_BATTLE_FORMATIONS,
            request_id="request-archraider-selection",
            result_id="result-archraider-selection",
            payload={
                "effect_kind": enhancements.ARCHRAIDER_EFFECT_KIND,
                "target_unit_instance_id": _ARCHRAIDER_UNIT_ID,
                "selected_model_instance_id": selected_model_instance_id,
            },
        )
    )


def _test_stratagem_definition() -> StratagemDefinition:
    return StratagemDefinition(
        stratagem_id="enemy-self-buff",
        name="Enemy Self Buff",
        source_id="source:enemy-self-buff",
        command_point_cost=1,
        category=StratagemCategory.BATTLE_TACTIC,
        when_descriptor="Start of the Shooting phase.",
        target_descriptor="One friendly unit.",
        effect_descriptor="Record-only test effect.",
        restrictions_descriptor="Test Stratagem.",
        timing=StratagemTimingDescriptor(
            trigger_kind=TimingTriggerKind.START_PHASE,
            phase=BattlePhase.SHOOTING,
        ),
    )


def _source_stratagem_request() -> DecisionRequest:
    return DecisionRequest(
        request_id="request-enemy-stratagem",
        decision_type=STRATAGEM_DECISION_TYPE,
        actor_id="player-b",
        payload={"stratagem_context": {"test": "context"}, "finite": True},
        options=(
            DecisionOption(
                option_id="use-enemy-stratagem",
                label="Use Enemy Stratagem",
                payload={"submission_kind": STRATAGEM_DECISION_TYPE},
            ),
        ),
    )


def _unit_by_id(state: GameState, unit_instance_id: str) -> UnitInstance:
    for army in state.army_definitions:
        for unit in army.units:
            if unit.unit_instance_id == unit_instance_id:
                return unit
    raise AssertionError(f"missing unit {unit_instance_id}")


def _remove_unit_placement(state: GameState, unit_instance_id: str) -> None:
    battlefield = state.battlefield_state
    if battlefield is None:
        raise AssertionError("Expected battlefield state.")
    state.battlefield_state = replace(
        battlefield,
        placed_armies=tuple(
            replace(
                placed_army,
                unit_placements=tuple(
                    placement
                    for placement in placed_army.unit_placements
                    if placement.unit_instance_id != unit_instance_id
                ),
            )
            for placed_army in battlefield.placed_armies
        ),
    )


def _replace_first_persisting_effect_payload(state: GameState, payload: JsonValue) -> None:
    if not state.persisting_effects:
        raise AssertionError("Expected at least one persisting effect.")
    state.persisting_effects[0] = replace(state.persisting_effects[0], effect_payload=payload)
