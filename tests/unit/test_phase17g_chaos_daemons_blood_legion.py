from __future__ import annotations

import importlib
import json
from collections.abc import Callable
from dataclasses import replace
from typing import Protocol, cast

import pytest
from tests.movement_submission_helpers import (
    straight_line_witness_for_unit,
    submit_action_and_movement_proposal,
)
from tests.phase10o_fall_back_helpers import (
    advance_to_movement_unit_selection,
    decision_request,
    fall_back_state,
)
from tests.phase11c_command_phase_helpers import (
    center_marker_definition,
    complete_setup_through_gate,
    with_model_offsets,
)
from tests.phase13b_shooting_declaration_helpers import (
    _attack_pool_for_test,
    _fixed_roll_result,
)
from tests.phase15c_fight_order_helpers import fight_lifecycle

from warhammer40k_core.adapters.contracts import ParameterizedSubmission
from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.core.attachment_eligibility import (
    AttachmentEligibility,
    AttachmentRole,
    AttachmentTargetEligibility,
)
from warhammer40k_core.core.attributes import Characteristic, CharacteristicValue
from warhammer40k_core.core.datasheet import (
    CatalogAbilitySourceKind,
    CatalogAbilitySupport,
    DatasheetAbilityDescriptor,
    DatasheetDefinition,
    DatasheetKeywordSet,
)
from warhammer40k_core.core.detachment import DetachmentDefinition, EnhancementDefinition
from warhammer40k_core.core.dice import DiceRollResult
from warhammer40k_core.core.faction import FactionDefinition
from warhammer40k_core.core.modifiers import RollModifier
from warhammer40k_core.core.ruleset_descriptor import (
    BattlePhaseKind,
    FightPhaseStepKind,
    FightTypeKind,
    MovementMode,
    RulesetDescriptor,
)
from warhammer40k_core.core.weapon_profiles import (
    DamageProfile,
    WeaponKeyword,
    WeaponProfile,
)
from warhammer40k_core.engine.army_mustering import (
    ArmyDefinition,
    ArmyMusterRequest,
    EnhancementAssignment,
    muster_army,
    validate_roster_legality,
)
from warhammer40k_core.engine.attack_sequence import (
    AttackSequence,
    resolve_attack_sequence_until_blocked,
)
from warhammer40k_core.engine.attack_sequence_model import (
    attack_sequence_hit_roll_spec,
    attack_sequence_wound_roll_spec,
    deadly_demise_trigger_roll_spec,
)
from warhammer40k_core.engine.battle_formation_hooks import BattleFormationRequestContext
from warhammer40k_core.engine.battle_round_flow import BattleRoundFlow
from warhammer40k_core.engine.battlefield_state import ModelPlacement, UnitPlacement
from warhammer40k_core.engine.damage_allocation import (
    DECLINE_DESTRUCTION_REACTION_OPTION_ID,
    DECLINE_FEEL_NO_PAIN_OPTION_ID,
    SELECT_DESTRUCTION_REACTION_DECISION_TYPE,
    SELECT_FEEL_NO_PAIN_DECISION_TYPE,
    DamageKind,
    DestructionReactionKind,
    DestructionReactionSource,
    FeelNoPainSource,
    apply_damage_to_model,
    apply_mortal_wounds_to_unit,
    mortal_wound_feel_no_pain_source_context,
)
from warhammer40k_core.engine.deadly_demise import (
    deadly_demise_mortal_wounds_for_target,
    effective_deadly_demise_descriptor,
    resolve_deadly_demise_trigger,
)
from warhammer40k_core.engine.deadly_demise_modifiers import (
    DEADLY_DEMISE_MODIFIER_CONDITION_EFFECT_KIND,
    DeadlyDemiseModifier,
    deadly_demise_modifier_for_model,
)
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.destruction_provenance import (
    DestructionSourceKind,
    ModelDestructionAttribution,
)
from warhammer40k_core.engine.dice import DiceRollManager
from warhammer40k_core.engine.effects import (
    EffectExpiration,
    EffectExpirationBoundary,
    PersistingEffect,
)
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.faction_content.bundle import RuntimeContentBundle
from warhammer40k_core.engine.faction_content.runtime import build_runtime_content_bundle
from warhammer40k_core.engine.faction_content.warhammer_40000_11th.chaos_daemons import (
    datasheets,
)
from warhammer40k_core.engine.faction_content.warhammer_40000_11th.chaos_daemons.detachments.blood_legion import (  # noqa: E501
    enhancements,
    rule,
)
from warhammer40k_core.engine.fight_order import (
    FIGHT_ACTIVATION_DECISION_TYPE,
    FightPhaseState,
    FightsFirstRegistry,
    eligible_fight_contexts_for_player,
    fight_activation_option_id,
)
from warhammer40k_core.engine.fight_unit_selected_grant_resolution import (
    SELECTED_TO_FIGHT_SELF_MORTAL_WOUNDS_PENDING_EVENT,
    SELECTED_TO_FIGHT_SELF_MORTAL_WOUNDS_RESOLVED_EVENT,
    SELECTED_TO_FIGHT_SELF_MORTAL_WOUNDS_SOURCE_KIND,
)
from warhammer40k_core.engine.fight_unit_selected_hooks import (
    DECLINE_FIGHT_UNIT_GRANT_OPTION_ID,
    SELECT_FIGHT_UNIT_GRANT_DECISION_TYPE,
)
from warhammer40k_core.engine.game_state import (
    GameConfig,
    GameState,
    SecondaryMissionChoice,
    SecondaryMissionMode,
)
from warhammer40k_core.engine.generic_rule_ability_registry import GenericRuleAbilitySource
from warhammer40k_core.engine.generic_rule_ability_registry_blood_legion_defaults import (
    blood_legion_fight_unit_selected_grant_abilities,
    blood_legion_mortal_wound_feel_no_pain_abilities,
)
from warhammer40k_core.engine.generic_rule_attack_hooks import (
    generic_rule_reroll_permission_context_for_unit,
)
from warhammer40k_core.engine.lifecycle import GameLifecycle
from warhammer40k_core.engine.list_validation import (
    AttachmentDeclaration,
    DetachmentSelection,
    UnitMusterSelection,
)
from warhammer40k_core.engine.mission_setup import MissionSetup
from warhammer40k_core.engine.mortal_wound_destruction_evidence import (
    MortalWoundDestructionEvidence,
)
from warhammer40k_core.engine.movement_proposals import (
    MOVEMENT_PROPOSAL_DECISION_TYPE,
    MovementProposalPayload,
    MovementProposalRequest,
    ProposalKind,
)
from warhammer40k_core.engine.objective_control import (
    ObjectiveControlContext,
    ObjectiveControlTiming,
    resolve_objective_control,
)
from warhammer40k_core.engine.phase import (
    BattlePhase,
    GameLifecycleError,
    LifecycleStatus,
    LifecycleStatusKind,
    PlaceholderPhaseHandler,
    SetupStep,
)
from warhammer40k_core.engine.phases.fight import FightPhaseHandler
from warhammer40k_core.engine.phases.movement import (
    SELECT_MOVEMENT_ACTION_DECISION_TYPE,
    MovementPhaseActionKind,
)
from warhammer40k_core.engine.placement import create_deterministic_battlefield_scenario
from warhammer40k_core.engine.rule_deadly_demise_continuation import (
    RULE_MODEL_DESTRUCTION_APPLIED_DAMAGE_COMPLETION_KIND,
)
from warhammer40k_core.engine.rule_model_destruction import (
    RULE_MODEL_DESTRUCTION_DEADLY_DEMISE_SOURCE_KIND,
    RULE_MODEL_DESTRUCTION_FINALIZED_EVENT,
    RuleModelDestructionResult,
    destroy_model_with_rule_reactions,
)
from warhammer40k_core.engine.rule_model_destruction_applied_damage import (
    continue_applied_mortal_wound_destruction_with_rule_reactions,
)
from warhammer40k_core.engine.runtime_modifiers import (
    ChargeRollModifierContext,
    WeaponProfileModifierContext,
)
from warhammer40k_core.engine.saves import SaveKind, saving_throw_roll_spec
from warhammer40k_core.engine.triggered_movement import (
    SELECT_TRIGGERED_MOVEMENT_DECISION_TYPE,
)
from warhammer40k_core.engine.unit_factory import UnitInstance
from warhammer40k_core.engine.wargear_selections import (
    ModelProfileSelection,
)
from warhammer40k_core.geometry.pathing import PathWitness
from warhammer40k_core.geometry.pose import Pose
from warhammer40k_core.rules.mission_pack_import import chapter_approved_2026_27_mission_pack
from warhammer40k_core.rules.rule_ir import (
    RuleDurationKind,
    RuleEffectKind,
    RuleTargetKind,
    RuleTriggerKind,
    parameter_payload,
)
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    faction_blood_legion_ir_support_2026_27 as blood_legion_ir,
)
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    faction_execution_2026_27,
    faction_rule_ir_promotion_2026_07,
)
from warhammer40k_core.rules.source_packages.warhammer_40000_11th.faction_coverage_2026_27 import (
    Phase17ECoverageKind,
)
from warhammer40k_core.rules.source_packages.warhammer_40000_11th.faction_execution_2026_27 import (
    Phase17FExecutionRecord,
    Phase17FExecutionStatus,
)

_BLOOD_LEGION_DATASHEET_ID = "phase17g-blood-legion-khorne-daemon"
_BLOOD_LEGION_NON_KHORNE_DATASHEET_ID = "phase17g-blood-legion-non-khorne-daemon"
_BLOOD_LEGION_KHORNE_MONSTER_DATASHEET_ID = "phase17g-blood-legion-khorne-monster"
_BLOOD_UNIT_ID = "army-alpha:blood-daemon-unit"
_OTHER_FRIENDLY_UNIT_ID = "army-alpha:non-khorne-daemon-unit"
_OTHER_KHORNE_UNIT_ID = "army-alpha:khorne-daemon-unit"
_OTHER_KHORNE_MONSTER_UNIT_ID = "army-alpha:khorne-monster-unit"
_ENEMY_UNIT_ID = "army-beta:enemy-unit"
_OTHER_DAEMON_DETACHMENT_ID = "warptide"
_ATTACHED_UNIT_ID = "attached-unit:army-alpha:non-khorne-daemon-unit"


class _EnhancementRuntimeMetadata(Protocol):
    runtime_consumer_ids: tuple[str, ...]


def test_blood_legion_runtime_hooks_materialize_only_for_selected_detachment() -> None:
    blood_summary = build_runtime_content_bundle(_blood_legion_config()).to_summary_payload()

    assert rule.MURDERCALL_HOOK_ID in blood_summary["movement_end_surge_hook_ids"]
    assert rule.BLOOD_TAINTED_HOOK_ID in blood_summary["phase_end_objective_control_hook_ids"]
    assert rule.SOURCE_RULE_ID in blood_summary["selected_execution_record_ids"]
    assert any(
        path.endswith(".chaos_daemons.detachments.blood_legion.manifest")
        for path in blood_summary["selected_module_paths"]
    )

    other_summary = build_runtime_content_bundle(
        _blood_legion_config(
            daemon_detachment_id=_OTHER_DAEMON_DETACHMENT_ID,
            game_id="phase17g-blood-legion-not-selected",
        )
    ).to_summary_payload()

    assert rule.MURDERCALL_HOOK_ID not in other_summary["movement_end_surge_hook_ids"]
    assert rule.BLOOD_TAINTED_HOOK_ID not in other_summary["phase_end_objective_control_hook_ids"]


def test_brazenmaw_is_exact_source_backed_executable_generic_rule_ir() -> None:
    rule_ir = faction_rule_ir_promotion_2026_07.current_rule_ir_by_coverage_descriptor_id(
        enhancements.BRAZENMAW_DESCRIPTOR_ID
    )
    record = _brazenmaw_execution_record()

    assert rule_ir.is_supported
    assert rule_ir.source_id == (
        f"{blood_legion_ir.SOURCE_PACKAGE_ID}:{blood_legion_ir.BRAZENMAW_DESCRIPTOR_ID}:source-text"
    )
    assert rule_ir.normalized_text == (
        "Legiones Daemonica Khorne model only. Add 2 to Charge rolls made for the bearer's unit."
    )
    assert not rule_ir.diagnostics
    assert record.execution_status is Phase17FExecutionStatus.EXECUTABLE_GENERIC_IR
    assert record.execution_id == enhancements.BRAZENMAW_SOURCE_RULE_ID
    assert record.rule_ir_hash == rule_ir.ir_hash()
    modifier_effect = next(
        effect
        for clause in rule_ir.clauses
        for effect in clause.effects
        if effect.kind is RuleEffectKind.MODIFY_DICE_ROLL
    )
    assert parameter_payload(modifier_effect.parameters) == {
        "delta": 2,
        "roll_type": "charge",
    }


def test_furys_cage_is_exact_source_backed_executable_generic_rule_ir() -> None:
    rule_ir = faction_rule_ir_promotion_2026_07.current_rule_ir_by_coverage_descriptor_id(
        enhancements.FURYS_CAGE_DESCRIPTOR_ID
    )
    record = _furys_cage_execution_record()

    assert rule_ir.is_supported
    assert rule_ir.source_id == (
        f"{blood_legion_ir.SOURCE_PACKAGE_ID}:"
        f"{blood_legion_ir.FURYS_CAGE_DESCRIPTOR_ID}:source-text"
    )
    assert rule_ir.normalized_text == (
        "Legiones Daemonica Khorne Monster model only. Each time the bearer is selected "
        "to fight, it can use this Enhancement. If it does, the bearer suffers D3+1 "
        "mortal wounds, and until the end of the phase, each time it makes an attack, "
        "you can re-roll the Hit roll and you can re-roll the Wound roll."
    )
    assert not rule_ir.diagnostics
    assert record.execution_status is Phase17FExecutionStatus.EXECUTABLE_GENERIC_IR
    assert record.execution_id == enhancements.FURYS_CAGE_SOURCE_RULE_ID
    assert record.runtime_consumer_ids == enhancements.FURYS_CAGE_RUNTIME_CONSUMER_IDS
    assert record.handler_id is None
    assert record.rule_ir_hash == rule_ir.ir_hash()

    gate_clause = next(clause for clause in rule_ir.clauses if not clause.effects)
    assert tuple(
        parameter_payload(condition.parameters) for condition in gate_clause.conditions
    ) == (
        {"required_keyword_sequence": (blood_legion_ir.LEGIONES_DAEMONICA_KEYWORD,)},
        {"required_keyword": blood_legion_ir.KHORNE_KEYWORD},
        {"required_keyword": blood_legion_ir.MONSTER_KEYWORD},
    )

    marker_clause = next(
        clause
        for clause in rule_ir.clauses
        if any(effect.kind is RuleEffectKind.GRANT_ABILITY for effect in clause.effects)
    )
    assert marker_clause.trigger is None
    assert marker_clause.target is not None
    assert marker_clause.target.kind is RuleTargetKind.THIS_MODEL
    assert marker_clause.duration is not None
    assert marker_clause.duration.kind is RuleDurationKind.PERMANENT
    (marker_effect,) = marker_clause.effects
    assert parameter_payload(marker_effect.parameters) == {
        "ability": enhancements.FURYS_CAGE_SELECTED_TO_FIGHT_ABILITY,
        "hook_family": "fight_unit_selected_grant",
        "phase": "fight",
        "timing_window": "selected_to_fight",
        "optional": True,
    }

    triggered_clauses = tuple(clause for clause in rule_ir.clauses if clause.trigger is not None)
    assert len(triggered_clauses) == 2
    for clause in triggered_clauses:
        assert clause.trigger is not None
        assert clause.trigger.kind is RuleTriggerKind.UNIT_SELECTED
        assert parameter_payload(clause.trigger.parameters) == {
            "phase": "fight",
            "timing_window": "selected_to_fight",
            "optional": True,
        }
        assert clause.target is not None
        assert clause.target.kind is RuleTargetKind.THIS_MODEL

    mortal_clause = next(
        clause
        for clause in triggered_clauses
        if any(effect.kind is RuleEffectKind.INFLICT_MORTAL_WOUNDS for effect in clause.effects)
    )
    assert mortal_clause.duration is not None
    assert mortal_clause.duration.kind is RuleDurationKind.IMMEDIATE
    (mortal_effect,) = mortal_clause.effects
    assert parameter_payload(mortal_effect.parameters) == {
        "damage_kind": "mortal_wounds",
        "mortal_wounds_expression": "D3+1",
        "mortal_wounds_dice_quantity": 1,
        "mortal_wounds_dice_sides": 3,
        "mortal_wounds_modifier": 1,
        "target_scope": "this_model",
    }

    reroll_clause = next(
        clause
        for clause in triggered_clauses
        if any(effect.kind is RuleEffectKind.REROLL_PERMISSION for effect in clause.effects)
    )
    assert reroll_clause.duration is not None
    assert reroll_clause.duration.kind is RuleDurationKind.UNTIL_TIMING_ENDPOINT
    assert parameter_payload(reroll_clause.duration.parameters) == {"endpoint": "phase"}
    assert tuple(parameter_payload(effect.parameters) for effect in reroll_clause.effects) == (
        {"roll_type": "hit", "attack_role": "attacker", "target_scope": "this_model"},
        {"roll_type": "wound", "attack_role": "attacker", "target_scope": "this_model"},
    )


def test_furys_cage_adapter_decline_inflicts_no_wounds_and_records_no_rerolls() -> None:
    lifecycle = _furys_cage_fight_lifecycle(
        game_id="phase17g-furys-cage-decline",
        attached=False,
    )
    state = _started_state(lifecycle)
    bearer = _physical_unit_by_id(
        state=state,
        unit_instance_id=_OTHER_KHORNE_MONSTER_UNIT_ID,
    )
    starting_wounds = bearer.own_models[0].wounds_remaining
    starting_effect_ids = tuple(effect.effect_id for effect in state.persisting_effects)
    session = LocalGameSession(lifecycle=lifecycle)
    grant_request = _select_furys_cage_grant_request(
        session=session,
        selected_unit_instance_id=bearer.unit_instance_id,
        result_id_prefix="phase17g-furys-cage-decline",
    )

    assert grant_request.decision_type == SELECT_FIGHT_UNIT_GRANT_DECISION_TYPE
    assert {option.option_id for option in grant_request.options} == {
        DECLINE_FIGHT_UNIT_GRANT_OPTION_ID,
        enhancements.FURYS_CAGE_SELECTED_TO_FIGHT_CONSUMER_ID,
    }
    session.submit_option(
        request_id=grant_request.request_id,
        option_id=DECLINE_FIGHT_UNIT_GRANT_OPTION_ID,
        result_id="phase17g-furys-cage-decline:grant",
    )

    refreshed_bearer = _physical_unit_by_id(
        state=state,
        unit_instance_id=bearer.unit_instance_id,
    )
    assert refreshed_bearer.own_models[0].wounds_remaining == starting_wounds
    assert tuple(effect.effect_id for effect in state.persisting_effects) == starting_effect_ids
    assert not _events_of_type(
        lifecycle.decision_controller,
        SELECTED_TO_FIGHT_SELF_MORTAL_WOUNDS_PENDING_EVENT,
    )
    assert not _events_of_type(
        lifecycle.decision_controller,
        SELECTED_TO_FIGHT_SELF_MORTAL_WOUNDS_RESOLVED_EVENT,
    )


def test_furys_cage_lethal_self_wounds_complete_the_active_fight_activation() -> None:
    lifecycle = _furys_cage_fight_lifecycle(
        game_id="phase17g-furys-cage-lethal",
        attached=False,
        bearer_wounds=2,
    )
    state = _started_state(lifecycle)
    bearer = _physical_unit_by_id(
        state=state,
        unit_instance_id=_OTHER_KHORNE_MONSTER_UNIT_ID,
    )
    bearer_model_id = bearer.own_models[0].model_instance_id
    state.clear_model_destruction_reaction_sources(model_instance_id=bearer_model_id)
    session = LocalGameSession(lifecycle=lifecycle)
    grant_request = _select_furys_cage_grant_request(
        session=session,
        selected_unit_instance_id=bearer.unit_instance_id,
        result_id_prefix="phase17g-furys-cage-lethal",
    )

    status = session.submit_option(
        request_id=grant_request.request_id,
        option_id=enhancements.FURYS_CAGE_SELECTED_TO_FIGHT_CONSUMER_ID,
        result_id="phase17g-furys-cage-lethal:grant",
    )

    refreshed_bearer = _physical_unit_by_id(
        state=state,
        unit_instance_id=bearer.unit_instance_id,
    )
    assert not refreshed_bearer.own_models[0].is_alive
    assert state.battlefield_state is not None
    assert bearer_model_id not in state.battlefield_state.placed_model_ids()
    assert state.fight_phase_state is not None
    assert state.fight_phase_state.active_activation is None
    assert bearer.unit_instance_id in (
        state.fight_phase_state.fight_order_state.selected_to_fight_unit_ids
    )
    assert status.status_kind in {
        LifecycleStatusKind.ADVANCED,
        LifecycleStatusKind.WAITING_FOR_DECISION,
    }
    resolved_payload = _event_payload(
        lifecycle.decision_controller,
        SELECTED_TO_FIGHT_SELF_MORTAL_WOUNDS_RESOLVED_EVENT,
    )
    application = cast(dict[str, JsonValue], resolved_payload["mortal_wound_application"])
    assert application["spill_over"] is False
    assert (
        cast(list[dict[str, JsonValue]], application["applications"])[0]["model_instance_id"]
        == bearer.own_models[0].model_instance_id
    )
    destroyed_payload = next(
        payload
        for payload in _events_of_type(lifecycle.decision_controller, "model_destroyed")
        if payload["model_instance_id"] == bearer_model_id
    )
    attribution = ModelDestructionAttribution.from_model_destroyed_payload(destroyed_payload)
    assert destroyed_payload["destroyed_model_rules_triggered"] is True
    assert destroyed_payload["damage_kind"] == "mortal"
    assert (
        destroyed_payload["damage_application"]
        == cast(list[dict[str, JsonValue]], application["applications"])[-1]
    )
    assert (
        attribution.destruction_provenance.destruction_source_kind is DestructionSourceKind.ABILITY
    )
    finalized_payload = _event_payload(
        lifecycle.decision_controller,
        RULE_MODEL_DESTRUCTION_FINALIZED_EVENT,
    )
    assert (
        finalized_payload["completion_kind"]
        == RULE_MODEL_DESTRUCTION_APPLIED_DAMAGE_COMPLETION_KIND
    )
    assert finalized_payload["defer_attached_split_until_fight_activation_completion"] is False
    checkpoint = json.loads(json.dumps(session.to_persistence_payload(), sort_keys=True))
    restored_session = LocalGameSession.from_persistence_payload(checkpoint)
    assert restored_session.to_persistence_payload() == checkpoint


def test_furys_cage_lethal_attached_bearer_continues_with_surviving_bodyguard() -> None:
    lifecycle = _furys_cage_fight_lifecycle(
        game_id="phase17g-furys-cage-lethal-attached",
        attached=True,
        bearer_wounds=2,
    )
    state = _started_state(lifecycle)
    bearer = _physical_unit_by_id(
        state=state,
        unit_instance_id=_OTHER_KHORNE_MONSTER_UNIT_ID,
    )
    bodyguard = _physical_unit_by_id(
        state=state,
        unit_instance_id=_OTHER_FRIENDLY_UNIT_ID,
    )
    state.clear_model_destruction_reaction_sources(
        model_instance_id=bearer.own_models[0].model_instance_id
    )
    session = LocalGameSession(lifecycle=lifecycle)
    grant_request = _select_furys_cage_grant_request(
        session=session,
        selected_unit_instance_id=bearer.unit_instance_id,
        result_id_prefix="phase17g-furys-cage-lethal-attached",
    )

    status = session.submit_option(
        request_id=grant_request.request_id,
        option_id=enhancements.FURYS_CAGE_SELECTED_TO_FIGHT_CONSUMER_ID,
        result_id="phase17g-furys-cage-lethal-attached:grant",
    )

    assert status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    assert status.decision_request is not None
    assert state.fight_phase_state is not None
    assert state.fight_phase_state.active_activation is None
    assert (
        state.fight_phase_state.fight_order_state.activation_selections[-1].unit_instance_id
        == bearer.unit_instance_id
    )
    assert {
        bearer.unit_instance_id,
        bodyguard.unit_instance_id,
    }.issubset(state.fight_phase_state.fight_order_state.selected_to_fight_unit_ids)
    assert bodyguard.unit_instance_id not in {
        context.unit_instance_id
        for context in eligible_fight_contexts_for_player(
            state=state,
            fight_state=state.fight_phase_state,
            player_id="player-a",
            policy=state.runtime_ruleset_descriptor().fight_policy,
        )
    }
    assert not any(
        formation.attached_unit_instance_id == _ATTACHED_UNIT_ID
        for army in state.army_definitions
        for formation in army.attached_units
    )
    unavailable_payload = _event_payload(
        lifecycle.decision_controller,
        "melee_declaration_not_available",
    )
    activation_payload = cast(
        dict[str, JsonValue],
        unavailable_payload["activation_selection"],
    )
    assert activation_payload["unit_instance_id"] == bearer.unit_instance_id
    assert unavailable_payload["target_unit_instance_ids"] == [_ENEMY_UNIT_ID]
    assert unavailable_payload["available_weapon_count"] == 0
    finalized_payload = _event_payload(
        lifecycle.decision_controller,
        RULE_MODEL_DESTRUCTION_FINALIZED_EVENT,
    )
    assert finalized_payload["defer_attached_split_until_fight_activation_completion"] is True


def test_furys_cage_fight_on_death_uses_same_activation_then_removes_and_splits() -> None:
    game_id = "phase17g-furys-cage-fight-on-death"
    lifecycle = _furys_cage_fight_lifecycle(
        game_id=game_id,
        attached=True,
        bearer_wounds=2,
    )
    state = _started_state(lifecycle)
    bearer = _physical_unit_by_id(
        state=state,
        unit_instance_id=_OTHER_KHORNE_MONSTER_UNIT_ID,
    )
    bearer_model_id = bearer.own_models[0].model_instance_id
    fight_on_death_source = DestructionReactionSource(
        source_id="phase17g-furys-cage:fight-on-death",
        reaction_kind=DestructionReactionKind.FIGHT_ON_DEATH,
        source_rule_id="phase17g-furys-cage:fight-on-death",
    )
    state.clear_model_destruction_reaction_sources(model_instance_id=bearer_model_id)
    state.record_model_destruction_reaction_sources(
        model_instance_id=bearer_model_id,
        sources=(fight_on_death_source,),
    )
    session = LocalGameSession(lifecycle=lifecycle)
    grant_request = _select_furys_cage_grant_request(
        session=session,
        selected_unit_instance_id=bearer.unit_instance_id,
        result_id_prefix=game_id,
    )
    assert state.fight_phase_state is not None
    assert state.fight_phase_state.active_activation is not None
    original_activation_result_id = state.fight_phase_state.active_activation.result_id

    reaction_status = session.submit_option(
        request_id=grant_request.request_id,
        option_id=enhancements.FURYS_CAGE_SELECTED_TO_FIGHT_CONSUMER_ID,
        result_id=f"{game_id}:grant",
    )

    assert reaction_status.decision_request is not None
    assert (
        reaction_status.decision_request.decision_type == SELECT_DESTRUCTION_REACTION_DECISION_TYPE
    )
    reaction_request = session.lifecycle.decision_controller.queue.peek_next()
    reaction_option_id = next(
        option.option_id
        for option in reaction_request.options
        if option.option_id != DECLINE_DESTRUCTION_REACTION_OPTION_ID
    )

    completed_status = session.submit_option(
        request_id=reaction_request.request_id,
        option_id=reaction_option_id,
        result_id=f"{game_id}:accept-fight-on-death",
    )

    restored_state = _started_state(session.lifecycle)
    decisions = session.lifecycle.decision_controller
    assert completed_status.decision_request is not None
    assert completed_status.decision_request.decision_type == FIGHT_ACTIVATION_DECISION_TYPE
    assert restored_state.fight_phase_state is not None
    assert restored_state.fight_phase_state.active_activation is None
    assert restored_state.battlefield_state is not None
    assert bearer_model_id not in restored_state.battlefield_state.placed_model_ids()
    assert all(
        attached.attached_unit_instance_id != _ATTACHED_UNIT_ID
        for army in restored_state.army_definitions
        for attached in army.attached_units
    )
    continued_payload = _event_payload(
        decisions,
        "fight_on_death_active_activation_continued",
    )
    activation_payload = cast(
        dict[str, JsonValue],
        continued_payload["activation_selection"],
    )
    assert activation_payload["result_id"] == original_activation_result_id
    removed_payload = _event_payload(decisions, "fight_on_death_models_removed")
    assert removed_payload["model_instance_ids"] == [bearer_model_id]
    assert removed_payload["reason"] == "no_legal_attack"
    finalized_payload = _event_payload(
        decisions,
        RULE_MODEL_DESTRUCTION_FINALIZED_EVENT,
    )
    assert finalized_payload["defer_attached_split_until_fight_activation_completion"] is True
    resolved_payload = _event_payload(
        decisions,
        SELECTED_TO_FIGHT_SELF_MORTAL_WOUNDS_RESOLVED_EVENT,
    )
    assert isinstance(resolved_payload["model_destroyed_event_id"], str)
    assert GameState.from_payload(restored_state.to_payload()).to_payload() == (
        restored_state.to_payload()
    )
    assert DecisionController.from_payload(decisions.to_payload()) == decisions


def test_applied_mortal_wound_destruction_entry_fails_closed_on_state_and_provenance() -> None:
    lifecycle = _furys_cage_fight_lifecycle(
        game_id="phase17g-furys-cage-applied-damage-invalid",
        attached=False,
        bearer_wounds=5,
    )
    state = _started_state(lifecycle)
    bearer = _physical_unit_by_id(
        state=state,
        unit_instance_id=_OTHER_KHORNE_MONSTER_UNIT_ID,
    )
    bearer_model_id = bearer.own_models[0].model_instance_id
    session = LocalGameSession(lifecycle=lifecycle)
    _select_furys_cage_grant_request(
        session=session,
        selected_unit_instance_id=bearer.unit_instance_id,
        result_id_prefix="phase17g-furys-cage-applied-damage-invalid",
    )
    evidence = MortalWoundDestructionEvidence.for_non_attack_state(
        state=state,
        destroying_player_id="player-a",
        source_rules_unit_instance_id=bearer.unit_instance_id,
        source_model_instance_id=bearer_model_id,
        destruction_source_kind=DestructionSourceKind.ABILITY,
        action_phase=BattlePhase.FIGHT,
        source_step="selected_to_fight_self_mortal_wounds",
    )
    nonlethal = apply_damage_to_model(
        state=state,
        target_unit_instance_id=bearer.unit_instance_id,
        model_instance_id=bearer_model_id,
        damage=1,
        damage_kind=DamageKind.MORTAL,
        remove_destroyed_model=False,
    )
    state_before = state.to_payload()
    decisions_before = lifecycle.decision_controller.to_payload()

    with pytest.raises(GameLifecycleError, match="requires lethal damage"):
        continue_applied_mortal_wound_destruction_with_rule_reactions(
            state=state,
            decisions=lifecycle.decision_controller,
            damage_application=nonlethal,
            rules_unit_instance_id=bearer.unit_instance_id,
            source_rule_id=enhancements.FURYS_CAGE_SELECTED_TO_FIGHT_CONSUMER_ID,
            source_result_id="phase17g-furys-cage-applied-damage-invalid:nonlethal",
            completion_event_type=SELECTED_TO_FIGHT_SELF_MORTAL_WOUNDS_RESOLVED_EVENT,
            completion_event_payload={},
            destruction_evidence=evidence,
            defer_attached_split_until_fight_activation_completion=False,
        )

    assert state.to_payload() == state_before
    assert lifecycle.decision_controller.to_payload() == decisions_before

    lethal = apply_damage_to_model(
        state=state,
        target_unit_instance_id=bearer.unit_instance_id,
        model_instance_id=bearer_model_id,
        damage=4,
        damage_kind=DamageKind.MORTAL,
        remove_destroyed_model=False,
    )
    state_before = state.to_payload()
    decisions_before = lifecycle.decision_controller.to_payload()
    drifted_evidence = replace(evidence, parent_battle_phase=BattlePhase.SHOOTING)

    with pytest.raises(GameLifecycleError, match="parent phase drift"):
        continue_applied_mortal_wound_destruction_with_rule_reactions(
            state=state,
            decisions=lifecycle.decision_controller,
            damage_application=lethal,
            rules_unit_instance_id=bearer.unit_instance_id,
            source_rule_id=enhancements.FURYS_CAGE_SELECTED_TO_FIGHT_CONSUMER_ID,
            source_result_id="phase17g-furys-cage-applied-damage-invalid:phase-drift",
            completion_event_type=SELECTED_TO_FIGHT_SELF_MORTAL_WOUNDS_RESOLVED_EVENT,
            completion_event_payload={},
            destruction_evidence=drifted_evidence,
            defer_attached_split_until_fight_activation_completion=False,
        )
    with pytest.raises(GameLifecycleError, match="requires an attached rules unit"):
        continue_applied_mortal_wound_destruction_with_rule_reactions(
            state=state,
            decisions=lifecycle.decision_controller,
            damage_application=lethal,
            rules_unit_instance_id=bearer.unit_instance_id,
            source_rule_id=enhancements.FURYS_CAGE_SELECTED_TO_FIGHT_CONSUMER_ID,
            source_result_id="phase17g-furys-cage-applied-damage-invalid:split-drift",
            completion_event_type=SELECTED_TO_FIGHT_SELF_MORTAL_WOUNDS_RESOLVED_EVENT,
            completion_event_payload={},
            destruction_evidence=evidence,
            defer_attached_split_until_fight_activation_completion=True,
        )

    assert state.to_payload() == state_before
    assert lifecycle.decision_controller.to_payload() == decisions_before
    assert state.battlefield_state is not None
    assert bearer_model_id in state.battlefield_state.placed_model_ids()


def test_furys_cage_adapter_accept_hits_exact_bearer_and_grants_scoped_rerolls() -> None:
    lifecycle = _furys_cage_fight_lifecycle(
        game_id="phase17g-furys-cage-accept",
        attached=True,
    )
    state = _started_state(lifecycle)
    bearer = _physical_unit_by_id(
        state=state,
        unit_instance_id=_OTHER_KHORNE_MONSTER_UNIT_ID,
    )
    bodyguard = _physical_unit_by_id(
        state=state,
        unit_instance_id=_OTHER_FRIENDLY_UNIT_ID,
    )
    bearer_model = bearer.own_models[0]
    bodyguard_starting_wounds = {
        model.model_instance_id: model.wounds_remaining for model in bodyguard.own_models
    }
    session = LocalGameSession(lifecycle=lifecycle)
    grant_request = _select_furys_cage_grant_request(
        session=session,
        selected_unit_instance_id=bearer.unit_instance_id,
        result_id_prefix="phase17g-furys-cage-accept",
    )

    session.submit_option(
        request_id=grant_request.request_id,
        option_id=enhancements.FURYS_CAGE_SELECTED_TO_FIGHT_CONSUMER_ID,
        result_id="phase17g-furys-cage-accept:grant",
    )

    resolved_payload = _event_payload(
        lifecycle.decision_controller,
        SELECTED_TO_FIGHT_SELF_MORTAL_WOUNDS_RESOLVED_EVENT,
    )
    d3_payload = cast(dict[str, JsonValue], resolved_payload["d3_result"])
    expected_mortal_wounds = cast(int, d3_payload["value"]) + 1
    application = cast(dict[str, JsonValue], resolved_payload["mortal_wound_application"])
    applications = cast(list[dict[str, JsonValue]], application["applications"])
    refreshed_bearer = _physical_unit_by_id(
        state=state,
        unit_instance_id=bearer.unit_instance_id,
    )
    refreshed_bodyguard = _physical_unit_by_id(
        state=state,
        unit_instance_id=bodyguard.unit_instance_id,
    )

    assert application["mortal_wounds"] == expected_mortal_wounds
    assert application["spill_over"] is False
    assert {cast(str, entry["model_instance_id"]) for entry in applications} == {
        bearer_model.model_instance_id
    }
    assert sum(cast(int, entry["wounds_lost"]) for entry in applications) == (
        expected_mortal_wounds
    )
    assert (
        bearer_model.wounds_remaining - refreshed_bearer.own_models[0].wounds_remaining
        == expected_mortal_wounds
    )
    assert {
        model.model_instance_id: model.wounds_remaining for model in refreshed_bodyguard.own_models
    } == bodyguard_starting_wounds

    reroll_effects = _furys_cage_reroll_effects(state)
    assert len(reroll_effects) == 2
    assert {effect.target_unit_instance_ids for effect in reroll_effects} == {(_ATTACHED_UNIT_ID,)}
    assert {effect.expiration for effect in reroll_effects} == {
        EffectExpiration.end_phase(
            battle_round=1,
            phase=BattlePhaseKind.FIGHT,
            player_id="player-a",
        )
    }
    for roll_type in ("attack_sequence.hit", "attack_sequence.wound"):
        bearer_permission = generic_rule_reroll_permission_context_for_unit(
            state=state,
            player_id="player-a",
            unit_instance_id=_ATTACHED_UNIT_ID,
            model_instance_id=bearer_model.model_instance_id,
            roll_type=roll_type,
            timing_window=roll_type,
            target_unit_instance_id=_ENEMY_UNIT_ID,
        )
        assert bearer_permission is not None
        assert bearer_permission.permission.component_selection_policy.value == "whole_roll"
        assert bearer_permission.permission.allowed_component_selections is None
        assert (
            generic_rule_reroll_permission_context_for_unit(
                state=state,
                player_id="player-a",
                unit_instance_id=_ATTACHED_UNIT_ID,
                model_instance_id=bodyguard.own_models[0].model_instance_id,
                roll_type=roll_type,
                timing_window=roll_type,
                target_unit_instance_id=_ENEMY_UNIT_ID,
            )
            is None
        )
        assert (
            generic_rule_reroll_permission_context_for_unit(
                state=state,
                player_id="player-a",
                unit_instance_id=_ATTACHED_UNIT_ID,
                model_instance_id=None,
                roll_type=roll_type,
                timing_window=roll_type,
                target_unit_instance_id=_ENEMY_UNIT_ID,
            )
            is None
        )

    expired = state.expire_persisting_effects_at_boundary(
        EffectExpirationBoundary.phase_end(
            battle_round=1,
            phase=BattlePhaseKind.FIGHT,
            player_id="player-a",
        )
    )
    assert {effect.effect_id for effect in expired} == {
        effect.effect_id for effect in reroll_effects
    }
    for roll_type in ("attack_sequence.hit", "attack_sequence.wound"):
        assert (
            generic_rule_reroll_permission_context_for_unit(
                state=state,
                player_id="player-a",
                unit_instance_id=_ATTACHED_UNIT_ID,
                model_instance_id=bearer_model.model_instance_id,
                roll_type=roll_type,
                timing_window=roll_type,
                target_unit_instance_id=_ENEMY_UNIT_ID,
            )
            is None
        )


def test_furys_cage_self_mortal_wounds_resume_through_fnp_adapter_decisions() -> None:
    lifecycle = _furys_cage_fight_lifecycle(
        game_id="phase17g-furys-cage-fnp",
        attached=False,
    )
    state = _started_state(lifecycle)
    bearer = _physical_unit_by_id(
        state=state,
        unit_instance_id=_OTHER_KHORNE_MONSTER_UNIT_ID,
    )
    bearer_model = bearer.own_models[0]
    fnp_sources = (
        FeelNoPainSource(source_id="phase17g-furys-cage-fnp-a", threshold=5),
        FeelNoPainSource(source_id="phase17g-furys-cage-fnp-b", threshold=6),
    )
    state.record_model_feel_no_pain_sources(
        model_instance_id=bearer_model.model_instance_id,
        sources=fnp_sources,
    )
    session = LocalGameSession(lifecycle=lifecycle)
    grant_request = _select_furys_cage_grant_request(
        session=session,
        selected_unit_instance_id=bearer.unit_instance_id,
        result_id_prefix="phase17g-furys-cage-fnp",
    )

    status = session.submit_option(
        request_id=grant_request.request_id,
        option_id=enhancements.FURYS_CAGE_SELECTED_TO_FIGHT_CONSUMER_ID,
        result_id="phase17g-furys-cage-fnp:grant",
    )
    fnp_decision_count = 0
    while (
        status.decision_request is not None
        and status.decision_request.decision_type == SELECT_FEEL_NO_PAIN_DECISION_TYPE
    ):
        fnp_request = status.decision_request
        source_context = mortal_wound_feel_no_pain_source_context(fnp_request)
        assert isinstance(source_context, dict)
        assert source_context["source_kind"] == SELECTED_TO_FIGHT_SELF_MORTAL_WOUNDS_SOURCE_KIND
        assert source_context["source_model_instance_id"] == bearer_model.model_instance_id
        assert {option.option_id for option in fnp_request.options} == {
            source.source_id for source in fnp_sources
        }
        fnp_decision_count += 1
        status = session.submit_option(
            request_id=fnp_request.request_id,
            option_id=fnp_sources[0].source_id,
            result_id=f"phase17g-furys-cage-fnp:resolution-{fnp_decision_count:02d}",
        )

    resolved_payload = _event_payload(
        lifecycle.decision_controller,
        SELECTED_TO_FIGHT_SELF_MORTAL_WOUNDS_RESOLVED_EVENT,
    )
    application = cast(dict[str, JsonValue], resolved_payload["mortal_wound_application"])
    assert fnp_decision_count == application["mortal_wounds"]
    assert len(cast(list[JsonValue], application["feel_no_pain_resolutions"])) == (
        fnp_decision_count
    )
    assert (
        len(
            _events_of_type(
                lifecycle.decision_controller,
                SELECTED_TO_FIGHT_SELF_MORTAL_WOUNDS_PENDING_EVENT,
            )
        )
        == fnp_decision_count
    )
    assert status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    assert status.decision_request is not None
    assert status.decision_request.decision_type != SELECT_FEEL_NO_PAIN_DECISION_TYPE


def test_furys_cage_lethal_damage_routes_deadly_demise_through_nested_fnp_and_replay() -> None:
    game_id = "phase17g-furys-cage-dd-fnp-02"
    lifecycle = _furys_cage_fight_lifecycle(
        game_id=game_id,
        attached=False,
        bearer_wounds=2,
    )
    state = _started_state(lifecycle)
    bearer = _physical_unit_by_id(
        state=state,
        unit_instance_id=_OTHER_KHORNE_MONSTER_UNIT_ID,
    )
    enemy = _physical_unit_by_id(state=state, unit_instance_id=_ENEMY_UNIT_ID)
    bearer_model_id = bearer.own_models[0].model_instance_id
    enemy_model_id = enemy.own_models[0].model_instance_id
    fnp_sources = (
        FeelNoPainSource(source_id=f"{game_id}:a", threshold=5),
        FeelNoPainSource(source_id=f"{game_id}:b", threshold=6),
    )
    state.record_model_feel_no_pain_sources(
        model_instance_id=enemy_model_id,
        sources=fnp_sources,
        decline_allowed=True,
    )
    session = LocalGameSession(lifecycle=lifecycle)
    grant_request = _select_furys_cage_grant_request(
        session=session,
        selected_unit_instance_id=bearer.unit_instance_id,
        result_id_prefix=game_id,
    )

    status = session.submit_option(
        request_id=grant_request.request_id,
        option_id=enhancements.FURYS_CAGE_SELECTED_TO_FIGHT_CONSUMER_ID,
        result_id=f"{game_id}:grant",
    )
    assert status.decision_request is not None
    source_context = mortal_wound_feel_no_pain_source_context(status.decision_request)
    assert isinstance(source_context, dict)
    assert source_context["source_kind"] == RULE_MODEL_DESTRUCTION_DEADLY_DEMISE_SOURCE_KIND
    root_context = cast(dict[str, JsonValue], source_context["root_context"])
    assert root_context["completion_kind"] == RULE_MODEL_DESTRUCTION_APPLIED_DAMAGE_COMPLETION_KIND
    assert root_context["defer_attached_split_until_fight_activation_completion"] is False

    restored_lifecycle = replace(
        lifecycle,
        state=GameState.from_payload(state.to_payload()),
        decision_controller=DecisionController.from_payload(
            lifecycle.decision_controller.to_payload()
        ),
    )
    restored_session = LocalGameSession(lifecycle=restored_lifecycle)
    restored_state = _started_state(restored_lifecycle)
    restored_decisions = restored_lifecycle.decision_controller
    pending_request = restored_decisions.queue.peek_next()
    fnp_decision_count = 0
    while (
        pending_request.decision_type == SELECT_FEEL_NO_PAIN_DECISION_TYPE
        and isinstance(
            current_source_context := mortal_wound_feel_no_pain_source_context(pending_request),
            dict,
        )
        and current_source_context.get("source_kind")
        == RULE_MODEL_DESTRUCTION_DEADLY_DEMISE_SOURCE_KIND
    ):
        fnp_decision_count += 1
        continuation_status = restored_session.submit_option(
            request_id=pending_request.request_id,
            option_id=DECLINE_FEEL_NO_PAIN_OPTION_ID,
            result_id=f"phase17g-furys-cage-dd-fnp:decline-{fnp_decision_count:02d}",
        )
        if continuation_status.decision_request is None:
            break
        pending_request = continuation_status.decision_request

    decisions = restored_decisions
    assert fnp_decision_count == 2
    assert restored_state.battlefield_state is not None
    assert bearer_model_id not in restored_state.battlefield_state.placed_model_ids()
    assert enemy_model_id not in restored_state.battlefield_state.placed_model_ids()
    applied_payload = _event_payload(decisions, "deadly_demise_mortal_wounds_applied")
    assert applied_payload["target_unit_instance_id"] == enemy.unit_instance_id
    assert applied_payload["mortal_wounds"] == 2
    destroyed_payloads = {
        cast(str, payload["model_instance_id"]): payload
        for payload in _events_of_type(decisions, "model_destroyed")
    }
    bearer_attribution = ModelDestructionAttribution.from_model_destroyed_payload(
        destroyed_payloads[bearer_model_id]
    )
    enemy_attribution = ModelDestructionAttribution.from_model_destroyed_payload(
        destroyed_payloads[enemy_model_id]
    )
    assert (
        bearer_attribution.destruction_provenance.destruction_source_kind
        is DestructionSourceKind.ABILITY
    )
    assert (
        enemy_attribution.destruction_provenance.destruction_source_kind
        is DestructionSourceKind.DEADLY_DEMISE
    )
    bearer_destroyed_event = next(
        event
        for event in decisions.event_log.records
        if event.event_type == "model_destroyed"
        and isinstance(event.payload, dict)
        and event.payload.get("model_instance_id") == bearer_model_id
    )
    assert (
        _event_payload(
            decisions,
            SELECTED_TO_FIGHT_SELF_MORTAL_WOUNDS_RESOLVED_EVENT,
        )["model_destroyed_event_id"]
        == bearer_destroyed_event.event_id
    )
    assert GameState.from_payload(restored_state.to_payload()).to_payload() == (
        restored_state.to_payload()
    )
    assert DecisionController.from_payload(restored_decisions.to_payload()) == (restored_decisions)


def test_furys_cage_source_runtime_consumer_identity_drift_fails_closed() -> None:
    rule_ir = faction_rule_ir_promotion_2026_07.current_rule_ir_by_coverage_descriptor_id(
        enhancements.FURYS_CAGE_DESCRIPTOR_ID
    )
    record = _furys_cage_execution_record()
    (selected_to_fight_ability,) = blood_legion_fight_unit_selected_grant_abilities()
    (fnp_ability,) = blood_legion_mortal_wound_feel_no_pain_abilities()

    with pytest.raises(GameLifecycleError, match="runtime consumer identity drift"):
        selected_to_fight_ability.hook_id(
            GenericRuleAbilitySource(
                record=replace(
                    record,
                    runtime_consumer_ids=(enhancements.FURYS_CAGE_MORTAL_WOUND_FNP_CONSUMER_ID,),
                ),
                rule_ir=rule_ir,
            )
        )
    with pytest.raises(GameLifecycleError, match="runtime consumer identity drift"):
        fnp_ability.hook_id(
            GenericRuleAbilitySource(
                record=replace(
                    record,
                    runtime_consumer_ids=(enhancements.FURYS_CAGE_SELECTED_TO_FIGHT_CONSUMER_ID,),
                ),
                rule_ir=rule_ir,
            )
        )


@pytest.mark.parametrize(
    ("runtime_support_status", "runtime_consumer_ids", "error_match"),
    [
        (None, (), "source is not engine-consumed"),
        ("source_only", (), "source is not engine-consumed"),
        ("engine_consumed", (), "runtime consumer identity drift"),
    ],
)
def test_furys_cage_source_runtime_consumer_evidence_is_required(
    runtime_support_status: str | None,
    runtime_consumer_ids: tuple[str, ...],
    error_match: str,
) -> None:
    rule_ir = faction_rule_ir_promotion_2026_07.current_rule_ir_by_coverage_descriptor_id(
        enhancements.FURYS_CAGE_DESCRIPTOR_ID
    )
    source = GenericRuleAbilitySource(
        record=replace(
            _furys_cage_execution_record(),
            runtime_support_status=runtime_support_status,
            runtime_consumer_ids=runtime_consumer_ids,
        ),
        rule_ir=rule_ir,
    )
    for ability in blood_legion_fight_unit_selected_grant_abilities():
        with pytest.raises(GameLifecycleError, match=error_match):
            ability.hook_id(source)
    for fnp_ability in blood_legion_mortal_wound_feel_no_pain_abilities():
        with pytest.raises(GameLifecycleError, match=error_match):
            fnp_ability.hook_id(source)


def test_furys_cage_runtime_consumers_generate_from_source_only_execution_record(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    generator = importlib.import_module("tools.generate_faction_subrule_source_package")
    execution_records = faction_execution_2026_27.execution_records()
    pre_runtime_record = replace(
        _furys_cage_execution_record(),
        runtime_support_status="source_only",
        runtime_consumer_ids=(),
    )
    monkeypatch.setattr(
        faction_execution_2026_27,
        "execution_records",
        lambda: tuple(
            pre_runtime_record
            if record.coverage_descriptor_id == enhancements.FURYS_CAGE_DESCRIPTOR_ID
            else record
            for record in execution_records
        ),
    )

    metadata_builder = cast(
        Callable[[], dict[str, _EnhancementRuntimeMetadata]],
        generator.__dict__["_generic_enhancement_runtime_metadata_by_source_row_id"],
    )
    metadata = metadata_builder()

    assert metadata[blood_legion_ir.FURYS_CAGE_SOURCE_ROW_ID].runtime_consumer_ids == (
        enhancements.FURYS_CAGE_RUNTIME_CONSUMER_IDS
    )


def test_furys_cage_catalog_and_eligibility_reject_non_monster_bearer() -> None:
    config = _blood_legion_config(
        game_id="phase17g-furys-cage-invalid-bearer",
        furys_cage_target_unit_selection_id="blood-daemon-unit",
    )
    enhancement = next(
        enhancement
        for enhancement in config.army_catalog.enhancements
        if enhancement.enhancement_id == enhancements.FURYS_CAGE_ENHANCEMENT_ID
    )

    assert enhancement.name == "Fury's Cage"
    assert enhancement.points == 20
    assert enhancement.target_required_keywords == (
        blood_legion_ir.KHORNE_KEYWORD,
        blood_legion_ir.MONSTER_KEYWORD,
    )
    assert enhancement.target_required_faction_keywords == (
        blood_legion_ir.LEGIONES_DAEMONICA_KEYWORD,
    )
    report = validate_roster_legality(
        catalog=config.army_catalog,
        request=config.army_muster_requests[0],
    )
    assert "enhancement_target_keyword_required" in {
        violation.violation_code for violation in report.violations
    }


def test_brazenmaw_assignment_applies_charge_modifier_and_replays() -> None:
    config = _blood_legion_config(
        game_id="phase17g-brazenmaw-game",
        include_other_friendly_unit=True,
        brazenmaw_target_unit_selection_id="blood-daemon-unit",
    )
    lifecycle = _blood_legion_enhancement_lifecycle(config)
    state = _started_state(lifecycle)
    bundle = _runtime_content_bundle(lifecycle)

    assert enhancements.BRAZENMAW_SOURCE_RULE_ID in bundle.activation.selected_execution_record_ids
    source_rule_id = (
        f"{blood_legion_ir.SOURCE_PACKAGE_ID}:{blood_legion_ir.BRAZENMAW_DESCRIPTOR_ID}:source-text"
    )
    persisting_effect = next(
        effect
        for effect in state.persisting_effects_for_unit(_BLOOD_UNIT_ID)
        if effect.source_rule_id == source_rule_id
    )
    (modifier,) = _charge_roll_modifiers(
        bundle,
        state=state,
        unit_instance_id=_BLOOD_UNIT_ID,
    )
    assert type(modifier) is RollModifier
    assert modifier.modifier_id == persisting_effect.effect_id
    assert modifier.operand == 2
    assert modifier.source_id is not None
    assert modifier.source_id.startswith(f"{source_rule_id}:")
    assert modifier.source_id.endswith(":modify_dice_roll")
    assert not _charge_roll_modifiers(
        bundle,
        state=state,
        unit_instance_id=_OTHER_FRIENDLY_UNIT_ID,
    )
    event_payload = _event_payload(lifecycle.decision_controller, "enhancement_effects_applied")
    assert "object at 0x" not in json.dumps(event_payload, sort_keys=True)

    payload = lifecycle.to_payload()
    rebuilt = GameLifecycle.from_payload(payload)

    assert rebuilt.to_payload() == payload
    assert _charge_roll_operands(
        _runtime_content_bundle(rebuilt),
        state=_started_state(rebuilt),
        unit_instance_id=_BLOOD_UNIT_ID,
    ) == (2,)


def test_brazenmaw_follows_bearer_into_attached_rules_unit_without_duplication() -> None:
    config = _blood_legion_config(
        game_id="phase17g-brazenmaw-attached-game",
        brazenmaw_target_unit_selection_id="blood-daemon-unit",
        attach_brazenmaw_bearer=True,
    )
    lifecycle = _blood_legion_enhancement_lifecycle(config)
    state = _started_state(lifecycle)
    bundle = _runtime_content_bundle(lifecycle)

    assert _charge_roll_operands(
        bundle,
        state=state,
        unit_instance_id=_ATTACHED_UNIT_ID,
    ) == (2,)
    assert _charge_roll_operands(
        bundle,
        state=state,
        unit_instance_id=_BLOOD_UNIT_ID,
    ) == (2,)
    assert _charge_roll_operands(
        bundle,
        state=state,
        unit_instance_id=_OTHER_FRIENDLY_UNIT_ID,
    ) == (2,)


def test_brazenmaw_eligibility_rejects_non_khorne_bearer() -> None:
    config = _blood_legion_config(
        game_id="phase17g-brazenmaw-invalid-bearer",
        include_other_friendly_unit=True,
        brazenmaw_target_unit_selection_id="non-khorne-daemon-unit",
    )

    report = validate_roster_legality(
        catalog=config.army_catalog,
        request=config.army_muster_requests[0],
    )

    assert "enhancement_target_keyword_required" in {
        violation.violation_code for violation in report.violations
    }


def test_gateway_unto_damnation_is_exact_source_backed_executable_generic_rule_ir() -> None:
    rule_ir = faction_rule_ir_promotion_2026_07.current_rule_ir_by_coverage_descriptor_id(
        enhancements.GATEWAY_UNTO_DAMNATION_DESCRIPTOR_ID
    )
    record = _gateway_unto_damnation_execution_record()

    assert rule_ir.is_supported
    assert rule_ir.source_id == (
        f"{blood_legion_ir.SOURCE_PACKAGE_ID}:"
        f"{blood_legion_ir.GATEWAY_UNTO_DAMNATION_DESCRIPTOR_ID}:source-text"
    )
    assert rule_ir.normalized_text == (
        "Legiones Daemonica Khorne Monster model only. The bearer's Deadly Demise ability "
        "inflicts mortal wounds on a D6 roll of 2+ instead of on a 6. In addition, if the "
        "bearer has destroyed one or more enemy units this battle, the bearer has the Deadly "
        "Demise D3+3 ability, instead of any other Deadly Demise ability on its datasheet."
    )
    assert not rule_ir.diagnostics
    assert record.execution_status is Phase17FExecutionStatus.EXECUTABLE_GENERIC_IR
    assert record.execution_id == enhancements.GATEWAY_UNTO_DAMNATION_SOURCE_RULE_ID
    assert record.rule_ir_hash == rule_ir.ir_hash()
    modifier_clause = next(
        clause
        for clause in rule_ir.clauses
        if any(effect.kind is RuleEffectKind.GRANT_ABILITY for effect in clause.effects)
    )
    assert modifier_clause.target is not None
    assert modifier_clause.target.kind.value == "this_model"
    assert len(modifier_clause.conditions) == 1
    assert parameter_payload(modifier_clause.conditions[0].parameters) == {
        "relationship": "this_model_destroyed_unit",
        "target_allegiance": "enemy",
        "time_scope": "this_battle",
    }
    (modifier_effect,) = modifier_clause.effects
    assert parameter_payload(modifier_effect.parameters) == {
        "ability": blood_legion_ir.DEADLY_DEMISE_MODIFIER_ABILITY,
        "trigger_roll_threshold": 2,
        "conditional_mortal_wounds_kind": "d3",
        "conditional_mortal_wounds_modifier": 3,
        "condition": blood_legion_ir.DEADLY_DEMISE_DESTROYED_ENEMY_UNIT_CONDITION,
        "replaces_existing_deadly_demise": True,
    }


def test_gateway_unto_damnation_rejects_non_monster_bearer() -> None:
    config = _blood_legion_config(
        game_id="phase17g-gateway-invalid-bearer",
        gateway_target_unit_selection_id="blood-daemon-unit",
    )

    report = validate_roster_legality(
        catalog=config.army_catalog,
        request=config.army_muster_requests[0],
    )

    assert "enhancement_target_keyword_required" in {
        violation.violation_code for violation in report.violations
    }


def test_gateway_unto_damnation_rejects_multi_model_bearer() -> None:
    config = _blood_legion_config(
        game_id="phase17g-gateway-multi-model-bearer",
        include_slaughterthirst_targets=True,
        gateway_target_unit_selection_id="khorne-monster-unit",
    )

    with pytest.raises(GameLifecycleError, match="requires a single-model bearer unit"):
        _blood_legion_enhancement_lifecycle(config)


def test_gateway_unto_damnation_attack_destruction_upgrades_and_persists() -> None:
    config = _blood_legion_config(
        game_id="phase17g-gateway-runtime",
        include_slaughterthirst_targets=True,
        gateway_target_unit_selection_id="khorne-monster-unit",
        khorne_monster_model_count=1,
        enemy_model_count=1,
    )
    lifecycle = _blood_legion_enhancement_lifecycle(config)
    state = _started_state(lifecycle)
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.SHOOTING)
    bundle = _runtime_content_bundle(lifecycle)
    monster = _physical_unit_by_id(
        state=state,
        unit_instance_id=_OTHER_KHORNE_MONSTER_UNIT_ID,
    )
    (bearer_model,) = monster.own_models
    bearer_model_id = bearer_model.model_instance_id
    bearer_source = _single_deadly_demise_source(
        state=state,
        model_instance_id=bearer_model_id,
    )
    decisions = lifecycle.decision_controller

    before_kill = effective_deadly_demise_descriptor(
        state=state,
        event_log=decisions.event_log,
        source=bearer_source,
        model_instance_id=bearer_model_id,
    )
    assert before_kill["trigger_roll_threshold"] == 2
    assert before_kill["mortal_wounds"] == {"kind": "d3"}

    destroyed_payload = _destroy_enemy_unit_with_gateway_attack(
        config=config,
        state=state,
        decisions=decisions,
    )
    attribution = ModelDestructionAttribution.from_model_destroyed_payload(destroyed_payload)
    assert attribution.source_rules_unit_instance_id == _OTHER_KHORNE_MONSTER_UNIT_ID
    assert attribution.attacking_model_instance_id == bearer_model_id
    assert attribution.source_model_instance_id == bearer_model_id
    assert attribution.destruction_provenance.destruction_source_kind is (
        DestructionSourceKind.ATTACK
    )
    upgraded_same_phase = effective_deadly_demise_descriptor(
        state=state,
        event_log=decisions.event_log,
        source=bearer_source,
        model_instance_id=bearer_model_id,
    )
    trigger_spec = deadly_demise_trigger_roll_spec(
        source=bearer_source,
        player_id="player-a",
        model_instance_id=bearer_model_id,
    )
    trigger_descriptor, _roll_payload, triggered = resolve_deadly_demise_trigger(
        state=state,
        manager=DiceRollManager(
            "phase17g-gateway-trigger",
            event_log=decisions.event_log,
            injected_results=(
                DiceRollResult.from_values(
                    roll_id="phase17g-gateway-trigger-roll",
                    spec=trigger_spec,
                    values=(2,),
                    source="fixed",
                ),
            ),
        ),
        source=bearer_source,
        player_id="player-a",
        model_instance_id=bearer_model_id,
    )

    assert upgraded_same_phase["mortal_wounds"] == {"kind": "d3", "modifier": 3}
    assert trigger_descriptor == upgraded_same_phase
    assert triggered

    flow = BattleRoundFlow(
        phase_handlers={
            BattlePhase.SHOOTING: PlaceholderPhaseHandler(BattlePhase.SHOOTING),
        },
        unit_destroyed_hooks=bundle.unit_destroyed_hook_registry,
    )
    flow.advance(state=state, decisions=decisions)
    condition_effects = tuple(
        effect
        for effect in state.persisting_effects
        if isinstance(effect.effect_payload, dict)
        and effect.effect_payload.get("effect_kind") == DEADLY_DEMISE_MODIFIER_CONDITION_EFFECT_KIND
    )

    assert len(condition_effects) == 1
    condition_payload = cast(dict[str, JsonValue], condition_effects[0].effect_payload)
    assert condition_payload["source_model_instance_id"] == bearer_model_id
    assert "object at 0x" not in json.dumps(
        _event_payload(decisions, "deadly_demise_modifier_condition_achieved"),
        sort_keys=True,
    )

    payload = lifecycle.to_payload()
    rebuilt = GameLifecycle.from_payload(payload)
    rebuilt_state = _started_state(rebuilt)
    rebuilt_source = _single_deadly_demise_source(
        state=rebuilt_state,
        model_instance_id=bearer_model_id,
    )
    rebuilt_descriptor = effective_deadly_demise_descriptor(
        state=rebuilt_state,
        event_log=rebuilt.decision_controller.event_log,
        source=rebuilt_source,
        model_instance_id=bearer_model_id,
    )
    damage_spec = DiceRollManager.d3_source_spec(
        reason=(
            f"Deadly Demise mortal wounds for {rebuilt_source.source_id} into {_BLOOD_UNIT_ID}"
        ),
        roll_type="destruction_reaction.deadly_demise.mortal_wounds",
        actor_id="player-a",
    )
    mortal_wounds, _damage_roll = deadly_demise_mortal_wounds_for_target(
        manager=DiceRollManager(
            "phase17g-gateway-damage",
            event_log=rebuilt.decision_controller.event_log,
            injected_results=(
                DiceRollResult.from_values(
                    roll_id="phase17g-gateway-damage-roll",
                    spec=damage_spec,
                    values=(1,),
                    source="fixed",
                ),
            ),
        ),
        source=rebuilt_source,
        descriptor=rebuilt_descriptor,
        player_id="player-a",
        target_unit_instance_id=_BLOOD_UNIT_ID,
    )

    assert rebuilt.to_payload()["state"] == rebuilt_state.to_payload()
    assert rebuilt_descriptor["mortal_wounds"] == {"kind": "d3", "modifier": 3}
    assert mortal_wounds == 4


def test_gateway_unto_damnation_relentless_carnage_destruction_upgrades_and_persists() -> None:
    config = _blood_legion_config(
        game_id="phase17g-gateway-relentless-carnage",
        include_slaughterthirst_targets=True,
        gateway_target_unit_selection_id="khorne-monster-unit",
        khorne_monster_model_count=1,
        enemy_model_count=1,
    )
    lifecycle = _blood_legion_enhancement_lifecycle(config)
    state = _started_state(lifecycle)
    state.active_player_id = "player-a"
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.FIGHT)
    _place_unit_poses(
        state,
        unit_instance_id=_OTHER_KHORNE_MONSTER_UNIT_ID,
        poses=(Pose.at(20.0, 20.0),),
    )
    _place_unit_poses(
        state,
        unit_instance_id=_ENEMY_UNIT_ID,
        poses=(Pose.at(20.5, 20.0),),
    )
    policy = config.ruleset_descriptor.fight_policy
    state.fight_phase_state = FightPhaseState.start(
        battle_round=state.battle_round,
        active_player_id="player-a",
        policy=policy,
        engaged_at_fight_step_start_unit_ids=(
            _OTHER_KHORNE_MONSTER_UNIT_ID,
            _ENEMY_UNIT_ID,
        ),
        fights_first_registry=FightsFirstRegistry(),
    ).with_current_step(current_step=FightPhaseStepKind.END, policy=policy)
    bundle = _runtime_content_bundle(lifecycle)
    decisions = lifecycle.decision_controller
    monster = _physical_unit_by_id(
        state=state,
        unit_instance_id=_OTHER_KHORNE_MONSTER_UNIT_ID,
    )
    enemy = _physical_unit_by_id(state=state, unit_instance_id=_ENEMY_UNIT_ID)
    (bearer_model,) = monster.own_models
    (enemy_model,) = enemy.own_models
    bearer_source = _single_deadly_demise_source(
        state=state,
        model_instance_id=bearer_model.model_instance_id,
    )
    handler = FightPhaseHandler(
        fight_phase_end_hooks=bundle.fight_phase_end_hook_registry,
    )

    status = handler.begin_phase(state=state, decisions=decisions)

    assert status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    request = status.decision_request
    assert request is not None
    target_option = next(
        option
        for option in request.options
        if isinstance(option.payload, dict)
        and option.payload.get("target_enemy_unit_instance_id") == _ENEMY_UNIT_ID
    )
    result = DecisionResult.for_request(
        result_id="phase17g-gateway-relentless-carnage-selected",
        request=request,
        selected_option_id=target_option.option_id,
    )
    decisions.submit_result(result)

    assert handler.apply_decision(state=state, decisions=decisions, result=result) is None
    assert state.battlefield_state is not None
    assert enemy_model.model_instance_id not in state.battlefield_state.placed_model_ids()
    destroyed_payload = next(
        event.payload
        for event in decisions.event_log.records
        if event.event_type == "model_destroyed"
        and isinstance(event.payload, dict)
        and event.payload.get("model_instance_id") == enemy_model.model_instance_id
    )
    attribution = ModelDestructionAttribution.from_model_destroyed_payload(destroyed_payload)
    assert attribution.source_rules_unit_instance_id == _OTHER_KHORNE_MONSTER_UNIT_ID
    assert attribution.source_model_instance_id == bearer_model.model_instance_id
    assert attribution.destruction_provenance.destruction_source_kind is (
        DestructionSourceKind.ABILITY
    )
    assert effective_deadly_demise_descriptor(
        state=state,
        event_log=decisions.event_log,
        source=bearer_source,
        model_instance_id=bearer_model.model_instance_id,
    )["mortal_wounds"] == {"kind": "d3", "modifier": 3}

    flow = BattleRoundFlow(
        phase_handlers={
            BattlePhase.FIGHT: PlaceholderPhaseHandler(BattlePhase.FIGHT),
        },
        unit_destroyed_hooks=bundle.unit_destroyed_hook_registry,
    )
    flow.advance(state=state, decisions=decisions)
    condition_effects = tuple(
        effect
        for effect in state.persisting_effects
        if isinstance(effect.effect_payload, dict)
        and effect.effect_payload.get("effect_kind") == DEADLY_DEMISE_MODIFIER_CONDITION_EFFECT_KIND
    )

    assert len(condition_effects) == 1
    condition_payload = cast(dict[str, JsonValue], condition_effects[0].effect_payload)
    assert condition_payload["source_model_instance_id"] == bearer_model.model_instance_id
    assert condition_payload["model_destroyed_event_id"] in {
        event.event_id
        for event in decisions.event_log.records
        if event.event_type == "model_destroyed"
    }
    payload = lifecycle.to_payload()
    rebuilt = GameLifecycle.from_payload(payload)
    rebuilt_state = _started_state(rebuilt)
    assert rebuilt.to_payload() == payload
    assert effective_deadly_demise_descriptor(
        state=rebuilt_state,
        event_log=rebuilt.decision_controller.event_log,
        source=_single_deadly_demise_source(
            state=rebuilt_state,
            model_instance_id=bearer_model.model_instance_id,
        ),
        model_instance_id=bearer_model.model_instance_id,
    )["mortal_wounds"] == {"kind": "d3", "modifier": 3}


def test_gateway_unto_damnation_rule_destruction_upgrades_and_persists() -> None:
    config = _blood_legion_config(
        game_id="phase17g-gateway-rule-destruction",
        include_slaughterthirst_targets=True,
        gateway_target_unit_selection_id="khorne-monster-unit",
        khorne_monster_model_count=1,
        enemy_model_count=1,
    )
    lifecycle = _blood_legion_enhancement_lifecycle(config)
    state = _started_state(lifecycle)
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.SHOOTING)
    decisions = lifecycle.decision_controller
    monster = _physical_unit_by_id(
        state=state,
        unit_instance_id=_OTHER_KHORNE_MONSTER_UNIT_ID,
    )
    (bearer_model,) = monster.own_models
    bearer_model_id = bearer_model.model_instance_id
    source = _single_deadly_demise_source(
        state=state,
        model_instance_id=bearer_model_id,
    )
    modifier = deadly_demise_modifier_for_model(
        state=state,
        model_instance_id=bearer_model_id,
    )
    assert modifier is not None
    destruction = _destroy_enemy_unit_with_gateway_rule(
        state=state,
        decisions=decisions,
        modifier=modifier,
        source_rules_unit_instance_id=_OTHER_KHORNE_MONSTER_UNIT_ID,
        source_model_instance_id=bearer_model_id,
        evidence_id="bearer",
    )

    assert destruction.status is None
    assert destruction.model_destroyed_event_id is not None
    destroyed_payload = _event_payload_by_id(
        decisions,
        destruction.model_destroyed_event_id,
    )
    attribution = ModelDestructionAttribution.from_model_destroyed_payload(destroyed_payload)
    assert attribution.source_rules_unit_instance_id == _OTHER_KHORNE_MONSTER_UNIT_ID
    assert attribution.source_model_instance_id == bearer_model_id
    assert attribution.attacking_model_instance_id is None
    assert attribution.destruction_provenance.destruction_source_kind is (
        DestructionSourceKind.ABILITY
    )

    descriptor = effective_deadly_demise_descriptor(
        state=state,
        event_log=decisions.event_log,
        source=source,
        model_instance_id=bearer_model_id,
    )

    assert descriptor["trigger_roll_threshold"] == 2
    assert descriptor["mortal_wounds"] == {"kind": "d3", "modifier": 3}

    flow = BattleRoundFlow(
        phase_handlers={
            BattlePhase.SHOOTING: PlaceholderPhaseHandler(BattlePhase.SHOOTING),
        },
        unit_destroyed_hooks=_runtime_content_bundle(lifecycle).unit_destroyed_hook_registry,
    )
    flow.advance(state=state, decisions=decisions)
    condition_effects = tuple(
        effect
        for effect in state.persisting_effects
        if isinstance(effect.effect_payload, dict)
        and effect.effect_payload.get("effect_kind") == DEADLY_DEMISE_MODIFIER_CONDITION_EFFECT_KIND
    )

    assert len(condition_effects) == 1
    condition_payload = cast(dict[str, JsonValue], condition_effects[0].effect_payload)
    assert condition_payload["model_destroyed_event_id"] == destruction.model_destroyed_event_id


@pytest.mark.parametrize(
    "attribution_case",
    ["non_bearer_component", "missing_source_model"],
)
def test_gateway_unto_damnation_attached_non_bearer_destruction_does_not_upgrade(
    attribution_case: str,
) -> None:
    config = _blood_legion_config(
        game_id="phase17g-gateway-attached-non-bearer",
        include_slaughterthirst_targets=True,
        gateway_target_unit_selection_id="khorne-monster-unit",
        attach_gateway_bearer=True,
        khorne_monster_model_count=1,
        enemy_model_count=1,
    )
    lifecycle = _blood_legion_enhancement_lifecycle(config)
    state = _started_state(lifecycle)
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.SHOOTING)
    decisions = lifecycle.decision_controller
    monster = _physical_unit_by_id(
        state=state,
        unit_instance_id=_OTHER_KHORNE_MONSTER_UNIT_ID,
    )
    bodyguard = _physical_unit_by_id(
        state=state,
        unit_instance_id=_OTHER_FRIENDLY_UNIT_ID,
    )
    (bearer_model,) = monster.own_models
    non_bearer_model = bodyguard.own_models[0]
    attributed_source_model_id = (
        non_bearer_model.model_instance_id if attribution_case == "non_bearer_component" else None
    )
    source = _single_deadly_demise_source(
        state=state,
        model_instance_id=bearer_model.model_instance_id,
    )
    modifier = deadly_demise_modifier_for_model(
        state=state,
        model_instance_id=bearer_model.model_instance_id,
    )
    assert modifier is not None

    destruction = _destroy_enemy_unit_with_gateway_rule(
        state=state,
        decisions=decisions,
        modifier=modifier,
        source_rules_unit_instance_id=_OTHER_FRIENDLY_UNIT_ID,
        source_model_instance_id=attributed_source_model_id,
        evidence_id=attribution_case,
    )
    assert destruction.model_destroyed_event_id is not None
    destroyed_payload = _event_payload_by_id(
        decisions,
        destruction.model_destroyed_event_id,
    )
    attribution = ModelDestructionAttribution.from_model_destroyed_payload(destroyed_payload)

    assert attribution.source_rules_unit_instance_id == _ATTACHED_UNIT_ID
    assert attribution.source_model_instance_id == attributed_source_model_id
    assert effective_deadly_demise_descriptor(
        state=state,
        event_log=decisions.event_log,
        source=source,
        model_instance_id=bearer_model.model_instance_id,
    )["mortal_wounds"] == {"kind": "d3"}

    flow = BattleRoundFlow(
        phase_handlers={
            BattlePhase.SHOOTING: PlaceholderPhaseHandler(BattlePhase.SHOOTING),
        },
        unit_destroyed_hooks=_runtime_content_bundle(lifecycle).unit_destroyed_hook_registry,
    )
    flow.advance(state=state, decisions=decisions)
    assert not tuple(
        effect
        for effect in state.persisting_effects
        if isinstance(effect.effect_payload, dict)
        and effect.effect_payload.get("effect_kind") == DEADLY_DEMISE_MODIFIER_CONDITION_EFFECT_KIND
    )

    payload = lifecycle.to_payload()
    rebuilt = GameLifecycle.from_payload(payload)
    rebuilt_attribution = ModelDestructionAttribution.from_model_destroyed_payload(
        _event_payload_by_id(
            rebuilt.decision_controller,
            destruction.model_destroyed_event_id,
        )
    )
    assert rebuilt.to_payload() == payload
    assert rebuilt_attribution.source_model_instance_id == attributed_source_model_id


def test_gateway_unto_damnation_source_identity_drift_fails_closed() -> None:
    config = _blood_legion_config(
        game_id="phase17g-gateway-source-drift",
        include_slaughterthirst_targets=True,
        gateway_target_unit_selection_id="khorne-monster-unit",
        khorne_monster_model_count=1,
    )
    lifecycle = _blood_legion_enhancement_lifecycle(config)
    state = _started_state(lifecycle)
    monster = _physical_unit_by_id(
        state=state,
        unit_instance_id=_OTHER_KHORNE_MONSTER_UNIT_ID,
    )
    (bearer_model,) = monster.own_models
    bearer_model_id = bearer_model.model_instance_id
    modifier = deadly_demise_modifier_for_model(
        state=state,
        model_instance_id=bearer_model_id,
    )
    assert modifier is not None
    effect_index = next(
        index
        for index, effect in enumerate(state.persisting_effects)
        if effect.effect_id == modifier.effect_id
    )
    state.persisting_effects[effect_index] = replace(
        state.persisting_effects[effect_index],
        source_rule_id="phase17g:gateway:drifted-source-rule",
    )

    with pytest.raises(GameLifecycleError, match="source rule identity drift"):
        deadly_demise_modifier_for_model(
            state=state,
            model_instance_id=bearer_model_id,
        )


def test_model_destruction_attribution_requires_explicit_source_model_field() -> None:
    payload = dict(
        ModelDestructionAttribution.for_non_attack(
            destroying_player_id="player-a",
            source_kind=DestructionSourceKind.ABILITY,
            source_rules_unit_instance_id=_BLOOD_UNIT_ID,
            source_model_instance_id=None,
        ).to_payload()
    )
    payload.pop("source_model_instance_id")

    with pytest.raises(GameLifecycleError, match="missing required fields"):
        ModelDestructionAttribution.from_model_destroyed_payload(payload)


def test_slaughterthirst_is_exact_source_backed_executable_generic_rule_ir() -> None:
    rule_ir = faction_rule_ir_promotion_2026_07.current_rule_ir_by_coverage_descriptor_id(
        enhancements.SLAUGHTERTHIRST_DESCRIPTOR_ID
    )
    record = _slaughterthirst_execution_record()

    assert rule_ir.is_supported
    assert rule_ir.source_id == (
        f"{blood_legion_ir.SOURCE_PACKAGE_ID}:"
        f"{blood_legion_ir.SLAUGHTERTHIRST_DESCRIPTOR_ID}:source-text"
    )
    assert rule_ir.normalized_text == (
        "Legiones Daemonica Khorne model only. While a friendly LEGIONES DAEMONICA "
        'KHORNE unit (excluding Monsters) is within 6" of the bearer, weapons equipped '
        "by models in that unit have the [LANCE] ability."
    )
    assert not rule_ir.diagnostics
    assert record.execution_status is Phase17FExecutionStatus.EXECUTABLE_GENERIC_IR
    assert record.execution_id == enhancements.SLAUGHTERTHIRST_SOURCE_RULE_ID
    assert record.rule_ir_hash == rule_ir.ir_hash()
    aura_clause = next(
        clause
        for clause in rule_ir.clauses
        if any(effect.kind is RuleEffectKind.GRANT_WEAPON_ABILITY for effect in clause.effects)
    )
    assert aura_clause.target is not None
    assert parameter_payload(aura_clause.target.parameters) == {
        "allegiance": "friendly",
        "include_source_unit": True,
    }
    (grant_effect,) = aura_clause.effects
    assert parameter_payload(grant_effect.parameters) == {
        "weapon_ability": "Lance",
        "weapon_scope": "all",
    }


def test_slaughterthirst_dynamically_grants_lance_to_eligible_units_in_range() -> None:
    config = _blood_legion_config(
        game_id="phase17g-slaughterthirst-game",
        include_other_friendly_unit=True,
        include_slaughterthirst_targets=True,
        slaughterthirst_target_unit_selection_id="blood-daemon-unit",
    )
    lifecycle = _blood_legion_enhancement_lifecycle(config)
    state = _started_state(lifecycle)
    bundle = _runtime_content_bundle(lifecycle)
    _place_unit_poses(
        state, unit_instance_id=_BLOOD_UNIT_ID, poses=_unit_line_poses(x=10.0, y=10.0)
    )
    _place_unit_poses(
        state,
        unit_instance_id=_OTHER_KHORNE_UNIT_ID,
        poses=_unit_line_poses(x=15.0, y=10.0),
    )
    _place_unit_poses(
        state,
        unit_instance_id=_OTHER_FRIENDLY_UNIT_ID,
        poses=_unit_line_poses(x=15.0, y=20.0),
    )
    _place_unit_poses(
        state,
        unit_instance_id=_OTHER_KHORNE_MONSTER_UNIT_ID,
        poses=_unit_line_poses(x=15.0, y=30.0),
    )
    profile = _weapon_profile_for_unit(
        config=config,
        state=state,
        unit_instance_id=_OTHER_KHORNE_UNIT_ID,
    )

    in_range = _modified_weapon_profile(
        bundle,
        state=state,
        unit_instance_id=_OTHER_KHORNE_UNIT_ID,
        profile=profile,
    )
    bearer_unit = _modified_weapon_profile(
        bundle,
        state=state,
        unit_instance_id=_BLOOD_UNIT_ID,
        profile=profile,
    )

    assert WeaponKeyword.LANCE in in_range.keywords
    assert WeaponKeyword.LANCE in bearer_unit.keywords
    source_rule_id = (
        f"{blood_legion_ir.SOURCE_PACKAGE_ID}:"
        f"{blood_legion_ir.SLAUGHTERTHIRST_DESCRIPTOR_ID}:source-text"
    )
    assert any(source_id.startswith(source_rule_id) for source_id in in_range.source_ids)
    assert (
        WeaponKeyword.LANCE
        not in _modified_weapon_profile(
            bundle,
            state=state,
            unit_instance_id=_OTHER_FRIENDLY_UNIT_ID,
            profile=profile,
        ).keywords
    )
    assert (
        WeaponKeyword.LANCE
        not in _modified_weapon_profile(
            bundle,
            state=state,
            unit_instance_id=_OTHER_KHORNE_MONSTER_UNIT_ID,
            profile=profile,
        ).keywords
    )

    _place_unit_poses(
        state,
        unit_instance_id=_OTHER_KHORNE_UNIT_ID,
        poses=_unit_line_poses(x=30.0, y=10.0),
    )
    assert (
        WeaponKeyword.LANCE
        not in _modified_weapon_profile(
            bundle,
            state=state,
            unit_instance_id=_OTHER_KHORNE_UNIT_ID,
            profile=profile,
        ).keywords
    )

    _place_unit_poses(
        state,
        unit_instance_id=_OTHER_KHORNE_UNIT_ID,
        poses=_unit_line_poses(x=15.0, y=10.0),
    )
    assert state.battlefield_state is not None
    state.replace_battlefield_state(state.battlefield_state.without_unit_placement(_BLOOD_UNIT_ID))
    assert (
        WeaponKeyword.LANCE
        not in _modified_weapon_profile(
            bundle,
            state=state,
            unit_instance_id=_OTHER_KHORNE_UNIT_ID,
            profile=profile,
        ).keywords
    )


def test_slaughterthirst_uses_bearer_model_and_attached_rules_unit_geometry() -> None:
    config = _blood_legion_config(
        game_id="phase17g-slaughterthirst-attached-game",
        include_slaughterthirst_targets=True,
        slaughterthirst_target_unit_selection_id="blood-daemon-unit",
        attach_brazenmaw_bearer=True,
    )
    lifecycle = _blood_legion_enhancement_lifecycle(config)
    state = _started_state(lifecycle)
    bundle = _runtime_content_bundle(lifecycle)
    _place_unit_poses(
        state, unit_instance_id=_BLOOD_UNIT_ID, poses=_unit_line_poses(x=10.0, y=10.0)
    )
    _place_unit_poses(
        state,
        unit_instance_id=_OTHER_FRIENDLY_UNIT_ID,
        poses=_unit_line_poses(x=30.0, y=10.0),
    )
    _place_unit_poses(
        state,
        unit_instance_id=_OTHER_KHORNE_UNIT_ID,
        poses=_unit_line_poses(x=35.0, y=10.0),
    )
    profile = _weapon_profile_for_unit(
        config=config,
        state=state,
        unit_instance_id=_OTHER_KHORNE_UNIT_ID,
    )

    assert (
        WeaponKeyword.LANCE
        not in _modified_weapon_profile(
            bundle,
            state=state,
            unit_instance_id=_OTHER_KHORNE_UNIT_ID,
            profile=profile,
        ).keywords
    )
    assert (
        WeaponKeyword.LANCE
        in _modified_weapon_profile(
            bundle,
            state=state,
            unit_instance_id=_OTHER_FRIENDLY_UNIT_ID,
            profile=profile,
        ).keywords
    )

    _place_unit_poses(
        state,
        unit_instance_id=_OTHER_KHORNE_UNIT_ID,
        poses=_unit_line_poses(x=15.0, y=10.0),
    )
    assert (
        WeaponKeyword.LANCE
        in _modified_weapon_profile(
            bundle,
            state=state,
            unit_instance_id=_OTHER_KHORNE_UNIT_ID,
            profile=profile,
        ).keywords
    )


def test_slaughterthirst_eligibility_rejects_non_khorne_bearer() -> None:
    config = _blood_legion_config(
        game_id="phase17g-slaughterthirst-invalid-bearer",
        include_other_friendly_unit=True,
        slaughterthirst_target_unit_selection_id="non-khorne-daemon-unit",
    )

    report = validate_roster_legality(
        catalog=config.army_catalog,
        request=config.army_muster_requests[0],
    )

    assert "enhancement_target_keyword_required" in {
        violation.violation_code for violation in report.violations
    }


def test_murdercall_triggers_after_enemy_move_and_resolves_surge_proposal() -> None:
    config = _blood_legion_config(
        game_id="phase17g-murdercall-game",
        turn_order=("player-b", "player-a"),
    )
    lifecycle, movement_status = advance_to_movement_unit_selection(config)
    state = fall_back_state(lifecycle)
    _place_murdercall_units(state)
    summary = _runtime_content_bundle(lifecycle).to_summary_payload()

    assert rule.MURDERCALL_HOOK_ID in summary["movement_end_surge_hook_ids"]

    selection_request = decision_request(movement_status)
    action_status = lifecycle.submit_decision(
        DecisionResult.for_request(
            result_id="phase17g-murdercall-select-enemy",
            request=selection_request,
            selected_option_id=_ENEMY_UNIT_ID,
        )
    )
    action_request = decision_request(action_status)
    assert action_request.decision_type == SELECT_MOVEMENT_ACTION_DECISION_TYPE

    surge_status = submit_action_and_movement_proposal(
        lifecycle,
        request=action_request,
        option_id=MovementPhaseActionKind.NORMAL_MOVE.value,
        action_result_id="phase17g-murdercall-normal-move-action",
        proposal_result_id="phase17g-murdercall-normal-move-proposal",
        unit_instance_id=_ENEMY_UNIT_ID,
        movement_phase_action=MovementPhaseActionKind.NORMAL_MOVE,
        movement_mode=MovementMode.NORMAL,
        witness=straight_line_witness_for_unit(
            lifecycle,
            unit_instance_id=_ENEMY_UNIT_ID,
            dx=4.0,
        ),
    )
    surge_request = decision_request(surge_status)
    assert surge_request.decision_type == SELECT_TRIGGERED_MOVEMENT_DECISION_TYPE
    assert surge_request.actor_id == "player-a"
    surge_option_id = f"surge:{_BLOOD_UNIT_ID}"
    assert surge_option_id in {option.option_id for option in surge_request.options}

    proposal_status = lifecycle.submit_decision(
        DecisionResult.for_request(
            result_id="phase17g-murdercall-select-surge-unit",
            request=surge_request,
            selected_option_id=surge_option_id,
        )
    )
    proposal_request = decision_request(proposal_status)
    proposal = MovementProposalRequest.from_decision_request_payload(proposal_request.payload)
    assert proposal_request.decision_type == MOVEMENT_PROPOSAL_DECISION_TYPE
    assert proposal.proposal_kind is ProposalKind.SURGE_MOVE
    assert proposal.unit_instance_id == _BLOOD_UNIT_ID

    resolved_status = _submit_surge_proposal(
        lifecycle=lifecycle,
        request=proposal_request,
        result_id="phase17g-murdercall-surge-proposal",
        unit_instance_id=_BLOOD_UNIT_ID,
        witness=straight_line_witness_for_unit(
            lifecycle,
            unit_instance_id=_BLOOD_UNIT_ID,
            dx=-1.0,
        ),
    )

    assert resolved_status.status_kind in {
        LifecycleStatusKind.ADVANCED,
        LifecycleStatusKind.WAITING_FOR_DECISION,
    }
    trigger_payload = _event_payload(lifecycle.decision_controller, "movement_end_surge_triggered")
    grants = cast(list[JsonValue], trigger_payload["grants"])
    first_grant = cast(dict[str, JsonValue], grants[0])
    assert first_grant["hook_id"] == rule.MURDERCALL_HOOK_ID
    assert first_grant["source_id"] == rule.SOURCE_RULE_ID
    resolved_payload = _event_payload(lifecycle.decision_controller, "triggered_movement_resolved")
    assert resolved_payload["source_rule_id"] == rule.SOURCE_RULE_ID
    assert resolved_payload["unit_instance_id"] == _BLOOD_UNIT_ID
    assert len(state.normal_move_states) == 2
    surge_states = tuple(
        move_state
        for move_state in state.normal_move_states
        if move_state.source_rule_id == rule.SOURCE_RULE_ID
    )
    assert len(surge_states) == 1


def test_blood_tainted_records_sticky_control_at_phase_end_boundary() -> None:
    config = _blood_legion_config(game_id="phase17g-blood-tainted-game")
    lifecycle = GameLifecycle()
    lifecycle.start(config)
    state = _battle_ready_state(lifecycle=lifecycle, config=config)
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.SHOOTING)
    _place_blood_tainted_units_on_center_objective(state)
    decisions = DecisionController()
    snapshot_payload = _emit_objective_proximity_snapshot(
        state=state,
        decisions=decisions,
        phase=BattlePhase.SHOOTING,
        ruleset_descriptor=config.ruleset_descriptor,
    )
    objective_id = _single_objective_id_for_unit(snapshot_payload, _ENEMY_UNIT_ID)
    _destroy_enemy_unit_for_blood_tainted(state=state, decisions=decisions)
    flow = BattleRoundFlow(
        phase_handlers={
            BattlePhase.SHOOTING: PlaceholderPhaseHandler(BattlePhase.SHOOTING),
        },
        phase_end_objective_control_hooks=(
            _runtime_content_bundle(lifecycle).phase_end_objective_control_hook_registry
        ),
    )

    status = flow.advance(state=state, decisions=decisions)

    assert status.status_kind is LifecycleStatusKind.UNSUPPORTED
    assert len(state.sticky_objective_control_states) == 1
    sticky_state = state.sticky_objective_control_states[0]
    assert sticky_state.source_rule_id == rule.SOURCE_RULE_ID
    assert sticky_state.objective_id == objective_id
    sticky_event = _event_payload(decisions, "sticky_objective_control_state_recorded")
    sticky_payload = cast(dict[str, JsonValue], sticky_event["sticky_objective_control_state"])
    assert sticky_payload["source_rule_id"] == rule.SOURCE_RULE_ID
    phase_end_record = state.objective_control_records[-1]
    retained_result = phase_end_record.result_by_objective_id(objective_id)
    assert retained_result.controlled_by_player_id == "player-a"
    assert retained_result.retained_control_source_id is None
    event_types = tuple(event.event_type for event in decisions.event_log.records)
    assert event_types.index("end_boundary_objective_control_determined") < event_types.index(
        "sticky_objective_control_state_recorded"
    )


def test_blood_tainted_credits_only_unit_destruction_completion_attacker() -> None:
    config = _blood_legion_config(
        game_id="phase17g-blood-tainted-completion-attribution-game",
        include_other_friendly_unit=True,
    )
    lifecycle = GameLifecycle()
    lifecycle.start(config)
    state = _battle_ready_state(lifecycle=lifecycle, config=config)
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.SHOOTING)
    _place_blood_tainted_units_on_center_objective(state)
    decisions = DecisionController()
    snapshot_payload = _emit_objective_proximity_snapshot(
        state=state,
        decisions=decisions,
        phase=BattlePhase.SHOOTING,
        ruleset_descriptor=config.ruleset_descriptor,
    )
    objective_id = _single_objective_id_for_unit(snapshot_payload, _ENEMY_UNIT_ID)
    _destroy_enemy_unit_with_split_attackers_for_blood_tainted(
        state=state,
        decisions=decisions,
    )
    flow = BattleRoundFlow(
        phase_handlers={
            BattlePhase.SHOOTING: PlaceholderPhaseHandler(BattlePhase.SHOOTING),
        },
        phase_end_objective_control_hooks=(
            _runtime_content_bundle(lifecycle).phase_end_objective_control_hook_registry
        ),
    )

    status = flow.advance(state=state, decisions=decisions)

    assert status.status_kind is LifecycleStatusKind.UNSUPPORTED
    assert state.sticky_objective_control_states == []
    assert all(
        event.event_type != "sticky_objective_control_state_recorded"
        for event in decisions.event_log.records
    )
    phase_end_record = state.objective_control_records[-1]
    result = phase_end_record.result_by_objective_id(objective_id)
    assert result.controlled_by_player_id == "player-a"
    assert result.retained_control_source_id is None


def test_blood_legion_rule_hooks_use_phase17f_execution_source_id() -> None:
    record = _blood_legion_rule_execution_record()
    bundle = build_runtime_content_bundle(_blood_legion_config(game_id="phase17g-blood-source-id"))
    surge_binding = next(
        binding
        for binding in bundle.movement_end_surge_hook_registry.all_bindings()
        if binding.hook_id == rule.MURDERCALL_HOOK_ID
    )
    sticky_binding = next(
        binding
        for binding in bundle.phase_end_objective_control_hook_registry.all_bindings()
        if binding.hook_id == rule.BLOOD_TAINTED_HOOK_ID
    )

    assert record.execution_id == rule.SOURCE_RULE_ID
    assert surge_binding.source_id == record.execution_id
    assert sticky_binding.source_id == record.execution_id


def _blood_legion_rule_execution_record() -> Phase17FExecutionRecord:
    records = tuple(
        record
        for record in faction_execution_2026_27.execution_records()
        if record.faction_id == rule.CHAOS_DAEMONS_FACTION_ID
        and record.detachment_id == rule.BLOOD_LEGION_DETACHMENT_ID
        and record.coverage_kind is Phase17ECoverageKind.DETACHMENT_RULE
    )
    if len(records) != 1:
        raise AssertionError("expected one Blood Legion detachment-rule execution record")
    return records[0]


def _brazenmaw_execution_record() -> Phase17FExecutionRecord:
    records = tuple(
        record
        for record in faction_execution_2026_27.execution_records()
        if record.coverage_descriptor_id == enhancements.BRAZENMAW_DESCRIPTOR_ID
    )
    if len(records) != 1:
        raise AssertionError("expected one Brazenmaw execution record")
    return records[0]


def _furys_cage_execution_record() -> Phase17FExecutionRecord:
    records = tuple(
        record
        for record in faction_execution_2026_27.execution_records()
        if record.coverage_descriptor_id == enhancements.FURYS_CAGE_DESCRIPTOR_ID
    )
    if len(records) != 1:
        raise AssertionError("expected one Fury's Cage execution record")
    return records[0]


def _gateway_unto_damnation_execution_record() -> Phase17FExecutionRecord:
    records = tuple(
        record
        for record in faction_execution_2026_27.execution_records()
        if record.coverage_descriptor_id == enhancements.GATEWAY_UNTO_DAMNATION_DESCRIPTOR_ID
    )
    if len(records) != 1:
        raise AssertionError("expected one Gateway Unto Damnation execution record")
    return records[0]


def _slaughterthirst_execution_record() -> Phase17FExecutionRecord:
    records = tuple(
        record
        for record in faction_execution_2026_27.execution_records()
        if record.coverage_descriptor_id == enhancements.SLAUGHTERTHIRST_DESCRIPTOR_ID
    )
    if len(records) != 1:
        raise AssertionError("expected one Slaughterthirst execution record")
    return records[0]


def _furys_cage_fight_lifecycle(
    *,
    game_id: str,
    attached: bool,
    bearer_wounds: int = 10,
) -> GameLifecycle:
    config = _blood_legion_config(
        game_id=game_id,
        include_slaughterthirst_targets=True,
        furys_cage_target_unit_selection_id="khorne-monster-unit",
        attach_furys_cage_bearer=attached,
        khorne_monster_model_count=1,
        khorne_monster_wounds=bearer_wounds,
        enemy_model_count=1,
    )
    lifecycle, _units = fight_lifecycle(
        alpha_unit_ids=("blood-daemon-unit",),
        enemy_unit_ids=("enemy-unit",),
        origins={
            "blood-daemon-unit": Pose.at(42.0, 10.0),
            "khorne-daemon-unit": Pose.at(42.0, 30.0),
            "khorne-monster-unit": Pose.at(10.0, 21.4 if attached else 20.0),
            **({"non-khorne-daemon-unit": Pose.at(10.0, 20.0)} if attached else {}),
            "enemy-unit": Pose.at(8.0 if attached else 12.0, 20.0),
        },
        game_id=game_id,
        config=config,
    )
    return lifecycle


def _select_furys_cage_grant_request(
    *,
    session: LocalGameSession,
    selected_unit_instance_id: str,
    result_id_prefix: str,
) -> DecisionRequest:
    activation_status = session.advance_until_decision_or_terminal()
    movement_number = 1
    while (
        activation_status.decision_request is not None
        and activation_status.decision_request.decision_type == MOVEMENT_PROPOSAL_DECISION_TYPE
    ):
        movement_request = activation_status.decision_request
        proposal = MovementProposalRequest.from_decision_request_payload(movement_request.payload)
        context = cast(dict[str, JsonValue], proposal.context)
        activation_status = session.submit_parameterized_payload(
            request_id=movement_request.request_id,
            result_id=f"{result_id_prefix}:fight-movement-{movement_number:02d}",
            payload=cast(
                JsonValue,
                {
                    "proposal_request_id": proposal.request_id,
                    "proposal_kind": proposal.proposal_kind.value,
                    "unit_instance_id": proposal.unit_instance_id,
                    "movement_phase_action": proposal.movement_phase_action,
                    "movement_mode": context["movement_mode"],
                },
            ),
        )
        movement_number += 1
    activation_request = decision_request(activation_status)
    activation_option_id = fight_activation_option_id(
        unit_instance_id=selected_unit_instance_id,
        fight_type=FightTypeKind.NORMAL,
    )
    if activation_option_id not in {option.option_id for option in activation_request.options}:
        raise AssertionError(
            "Missing Fury's Cage fight activation option; received "
            f"{tuple(option.option_id for option in activation_request.options)}"
        )
    grant_status = session.submit_option(
        request_id=activation_request.request_id,
        option_id=activation_option_id,
        result_id=f"{result_id_prefix}:activation",
    )
    grant_request = decision_request(grant_status)
    if grant_request.decision_type != SELECT_FIGHT_UNIT_GRANT_DECISION_TYPE:
        raise AssertionError("Fury's Cage activation must request its optional grant")
    return grant_request


def _furys_cage_reroll_effects(state: GameState) -> tuple[PersistingEffect, ...]:
    return tuple(
        effect
        for effect in state.persisting_effects
        if effect.source_rule_id == enhancements.FURYS_CAGE_SOURCE_RULE_ID
        and _is_rule_ir_reroll_effect(effect)
    )


def _is_rule_ir_reroll_effect(effect: PersistingEffect) -> bool:
    payload = effect.effect_payload
    if not isinstance(payload, dict):
        return False
    rule_effect = payload.get("effect")
    return (
        isinstance(rule_effect, dict)
        and rule_effect.get("kind") == RuleEffectKind.REROLL_PERMISSION.value
    )


def _blood_legion_config(
    *,
    game_id: str = "phase17g-blood-legion-game",
    daemon_detachment_id: str = rule.BLOOD_LEGION_DETACHMENT_ID,
    turn_order: tuple[str, str] = ("player-a", "player-b"),
    include_other_friendly_unit: bool = False,
    include_slaughterthirst_targets: bool = False,
    brazenmaw_target_unit_selection_id: str | None = None,
    furys_cage_target_unit_selection_id: str | None = None,
    slaughterthirst_target_unit_selection_id: str | None = None,
    gateway_target_unit_selection_id: str | None = None,
    attach_brazenmaw_bearer: bool = False,
    attach_furys_cage_bearer: bool = False,
    attach_gateway_bearer: bool = False,
    khorne_monster_model_count: int = 5,
    khorne_monster_wounds: int = 2,
    enemy_model_count: int = 5,
) -> GameConfig:
    catalog = _blood_legion_catalog(khorne_monster_wounds=khorne_monster_wounds)
    return GameConfig(
        game_id=game_id,
        allow_legacy_non_strict_rosters=True,
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(
            descriptor_version="core-v2-phase17g-blood-legion-test"
        ),
        army_catalog=catalog,
        army_muster_requests=(
            _army_muster_request(
                catalog=catalog,
                army_id="army-alpha",
                player_id="player-a",
                faction_id=rule.CHAOS_DAEMONS_FACTION_ID,
                detachment_id=daemon_detachment_id,
                unit_selection_id="blood-daemon-unit",
                datasheet_id=_BLOOD_LEGION_DATASHEET_ID,
                extra_unit_selections=_blood_legion_extra_unit_selections(
                    include_other_friendly_unit=include_other_friendly_unit,
                    include_slaughterthirst_targets=include_slaughterthirst_targets,
                    attach_brazenmaw_bearer=attach_brazenmaw_bearer,
                    attach_furys_cage_bearer=attach_furys_cage_bearer,
                    attach_gateway_bearer=attach_gateway_bearer,
                    khorne_monster_model_count=khorne_monster_model_count,
                ),
                brazenmaw_target_unit_selection_id=brazenmaw_target_unit_selection_id,
                furys_cage_target_unit_selection_id=furys_cage_target_unit_selection_id,
                slaughterthirst_target_unit_selection_id=(slaughterthirst_target_unit_selection_id),
                gateway_target_unit_selection_id=gateway_target_unit_selection_id,
                attach_brazenmaw_bearer=attach_brazenmaw_bearer,
                attach_furys_cage_bearer=attach_furys_cage_bearer,
                attach_gateway_bearer=attach_gateway_bearer,
            ),
            _army_muster_request(
                catalog=catalog,
                army_id="army-beta",
                player_id="player-b",
                faction_id="core-marine-force",
                detachment_id="core-combined-arms",
                unit_selection_id="enemy-unit",
                datasheet_id="core-intercessor-like-infantry",
                unit_model_count=enemy_model_count,
            ),
        ),
        player_ids=("player-a", "player-b"),
        turn_order=turn_order,
        fixed_secondary_mission_ids=("assassination", "bring_it_down", "cleanse"),
        mission_setup=_mission_setup(),
    )


def _blood_legion_extra_unit_selections(
    *,
    include_other_friendly_unit: bool,
    include_slaughterthirst_targets: bool,
    attach_brazenmaw_bearer: bool,
    attach_furys_cage_bearer: bool,
    attach_gateway_bearer: bool,
    khorne_monster_model_count: int,
) -> tuple[tuple[str, str, int], ...]:
    selections: list[tuple[str, str, int]] = []
    if (
        include_other_friendly_unit
        or attach_brazenmaw_bearer
        or attach_furys_cage_bearer
        or attach_gateway_bearer
    ):
        selections.append(
            (
                "non-khorne-daemon-unit",
                _BLOOD_LEGION_NON_KHORNE_DATASHEET_ID,
                5,
            )
        )
    if include_slaughterthirst_targets:
        selections.extend(
            (
                ("khorne-daemon-unit", _BLOOD_LEGION_DATASHEET_ID, 5),
                (
                    "khorne-monster-unit",
                    _BLOOD_LEGION_KHORNE_MONSTER_DATASHEET_ID,
                    khorne_monster_model_count,
                ),
            )
        )
    return tuple(selections)


def _blood_legion_catalog(*, khorne_monster_wounds: int = 2) -> ArmyCatalog:
    base_catalog = ArmyCatalog.phase9a_canonical_content_pack()
    base_datasheet = base_catalog.datasheet_by_id("core-intercessor-like-infantry")
    fixture_datasheet = replace(
        base_datasheet,
        composition=tuple(
            replace(composition, min_models=1) for composition in base_datasheet.composition
        ),
    )
    daemon_datasheet = _blood_legion_datasheet(fixture_datasheet)
    non_khorne_daemon_datasheet = _blood_legion_non_khorne_datasheet(fixture_datasheet)
    khorne_monster_datasheet = _blood_legion_khorne_monster_datasheet(
        fixture_datasheet,
        wounds=khorne_monster_wounds,
    )
    return replace(
        base_catalog,
        datasheets=(
            *(
                fixture_datasheet
                if datasheet.datasheet_id == fixture_datasheet.datasheet_id
                else datasheet
                for datasheet in base_catalog.datasheets
            ),
            daemon_datasheet,
            non_khorne_daemon_datasheet,
            khorne_monster_datasheet,
        ),
        factions=(
            *base_catalog.factions,
            FactionDefinition(
                faction_id=rule.CHAOS_DAEMONS_FACTION_ID,
                name="Chaos Daemons",
                faction_keywords=("Legiones Daemonica",),
                source_ids=("gw-11e-faction-detachments-2026-27:faction:chaos-daemons",),
            ),
        ),
        detachments=(
            *base_catalog.detachments,
            DetachmentDefinition(
                detachment_id=rule.BLOOD_LEGION_DETACHMENT_ID,
                name="Blood Legion",
                faction_id=rule.CHAOS_DAEMONS_FACTION_ID,
                detachment_point_cost=2,
                unit_datasheet_ids=(
                    _BLOOD_LEGION_DATASHEET_ID,
                    _BLOOD_LEGION_NON_KHORNE_DATASHEET_ID,
                    _BLOOD_LEGION_KHORNE_MONSTER_DATASHEET_ID,
                ),
                force_disposition_ids=("phase17g-force", "take-and-hold"),
                enhancement_ids=(
                    blood_legion_ir.BRAZENMAW_ENHANCEMENT_ID,
                    blood_legion_ir.FURYS_CAGE_ENHANCEMENT_ID,
                    blood_legion_ir.GATEWAY_UNTO_DAMNATION_ENHANCEMENT_ID,
                    blood_legion_ir.SLAUGHTERTHIRST_ENHANCEMENT_ID,
                ),
                source_ids=(
                    "gw-11e-faction-detachments-2026-27:detachment:chaos-daemons:blood-legion",
                ),
            ),
            DetachmentDefinition(
                detachment_id=_OTHER_DAEMON_DETACHMENT_ID,
                name="Warptide",
                faction_id=rule.CHAOS_DAEMONS_FACTION_ID,
                detachment_point_cost=1,
                unit_datasheet_ids=(_BLOOD_LEGION_DATASHEET_ID,),
                force_disposition_ids=("phase17g-force", "take-and-hold"),
                source_ids=(
                    "gw-11e-faction-detachments-2026-27:detachment:chaos-daemons:warptide",
                ),
            ),
        ),
        enhancements=(
            *base_catalog.enhancements,
            EnhancementDefinition(
                enhancement_id=blood_legion_ir.BRAZENMAW_ENHANCEMENT_ID,
                name="Brazenmaw",
                source_id=blood_legion_ir.BRAZENMAW_DESCRIPTOR_ID,
                points=15,
                target_required_keywords=(blood_legion_ir.KHORNE_KEYWORD,),
                target_required_faction_keywords=(blood_legion_ir.LEGIONES_DAEMONICA_KEYWORD,),
            ),
            EnhancementDefinition(
                enhancement_id=blood_legion_ir.FURYS_CAGE_ENHANCEMENT_ID,
                name="Fury's Cage",
                source_id=blood_legion_ir.FURYS_CAGE_DESCRIPTOR_ID,
                points=20,
                target_required_keywords=(
                    blood_legion_ir.KHORNE_KEYWORD,
                    blood_legion_ir.MONSTER_KEYWORD,
                ),
                target_required_faction_keywords=(blood_legion_ir.LEGIONES_DAEMONICA_KEYWORD,),
            ),
            EnhancementDefinition(
                enhancement_id=blood_legion_ir.GATEWAY_UNTO_DAMNATION_ENHANCEMENT_ID,
                name="Gateway Unto Damnation",
                source_id=blood_legion_ir.GATEWAY_UNTO_DAMNATION_DESCRIPTOR_ID,
                points=10,
                target_required_keywords=(
                    blood_legion_ir.KHORNE_KEYWORD,
                    blood_legion_ir.MONSTER_KEYWORD,
                ),
                target_required_faction_keywords=(blood_legion_ir.LEGIONES_DAEMONICA_KEYWORD,),
            ),
            EnhancementDefinition(
                enhancement_id=blood_legion_ir.SLAUGHTERTHIRST_ENHANCEMENT_ID,
                name="Slaughterthirst (Aura)",
                source_id=blood_legion_ir.SLAUGHTERTHIRST_DESCRIPTOR_ID,
                points=25,
                target_required_keywords=(blood_legion_ir.KHORNE_KEYWORD,),
                target_required_faction_keywords=(blood_legion_ir.LEGIONES_DAEMONICA_KEYWORD,),
            ),
        ),
    )


def _blood_legion_datasheet(base_datasheet: DatasheetDefinition) -> DatasheetDefinition:
    return replace(
        base_datasheet,
        datasheet_id=_BLOOD_LEGION_DATASHEET_ID,
        name="Blood Legion Khorne Daemon",
        keywords=DatasheetKeywordSet(
            keywords=("Character", "Infantry", "Khorne"),
            faction_keywords=("Legiones Daemonica",),
        ),
        attachment_eligibilities=(
            AttachmentEligibility(
                role=AttachmentRole.LEADER,
                targets=(
                    AttachmentTargetEligibility(
                        bodyguard_datasheet_id=_BLOOD_LEGION_NON_KHORNE_DATASHEET_ID,
                        source_ids=("phase17g:test:blood-legion:leader-eligibility",),
                    ),
                ),
            ),
        ),
        source_ids=("phase17g:test:chaos-daemons:blood-legion-khorne-daemon",),
    )


def _blood_legion_non_khorne_datasheet(
    base_datasheet: DatasheetDefinition,
) -> DatasheetDefinition:
    return replace(
        base_datasheet,
        datasheet_id=_BLOOD_LEGION_NON_KHORNE_DATASHEET_ID,
        name="Blood Legion Non-Khorne Daemon",
        keywords=DatasheetKeywordSet(
            keywords=("Character", "Infantry", "Tzeentch"),
            faction_keywords=("Legiones Daemonica",),
        ),
        attachment_eligibilities=(),
        source_ids=("phase17g:test:chaos-daemons:blood-legion-non-khorne-daemon",),
    )


def _blood_legion_khorne_monster_datasheet(
    base_datasheet: DatasheetDefinition,
    *,
    wounds: int,
) -> DatasheetDefinition:
    return replace(
        base_datasheet,
        datasheet_id=_BLOOD_LEGION_KHORNE_MONSTER_DATASHEET_ID,
        name="Blood Legion Khorne Monster",
        keywords=DatasheetKeywordSet(
            keywords=("Character", "Khorne", "Monster"),
            faction_keywords=("Legiones Daemonica",),
        ),
        model_profiles=tuple(
            replace(
                profile,
                characteristics=tuple(
                    CharacteristicValue.from_raw(Characteristic.WOUNDS, wounds)
                    if value.characteristic is Characteristic.WOUNDS
                    else value
                    for value in profile.characteristics
                ),
            )
            for profile in base_datasheet.model_profiles
        ),
        attachment_eligibilities=(
            AttachmentEligibility(
                role=AttachmentRole.LEADER,
                targets=(
                    AttachmentTargetEligibility(
                        bodyguard_datasheet_id=_BLOOD_LEGION_NON_KHORNE_DATASHEET_ID,
                        source_ids=("phase17g:test:blood-legion:monster-leader-eligibility",),
                    ),
                ),
            ),
        ),
        abilities=(
            *base_datasheet.abilities,
            DatasheetAbilityDescriptor(
                ability_id=datasheets.BLOODTHIRSTER_RELENTLESS_CARNAGE_ABILITY_ID,
                name="Relentless Carnage",
                source_id=datasheets.BLOODTHIRSTER_RELENTLESS_CARNAGE_ABILITY_ID,
                support=CatalogAbilitySupport.DESCRIPTOR_ONLY,
                source_kind=CatalogAbilitySourceKind.DATASHEET,
                effect_description="Fight-end Relentless Carnage runtime source.",
                timing_tags=("fight_phase_end",),
                parameter_tokens=("D6",),
            ),
            DatasheetAbilityDescriptor(
                ability_id="phase17g-blood-legion-deadly-demise-d3",
                name="Deadly Demise D3",
                source_id="phase17g:test:chaos-daemons:blood-legion:deadly-demise-d3",
                support=CatalogAbilitySupport.DESCRIPTOR_ONLY,
                source_kind=CatalogAbilitySourceKind.CORE,
                effect_description="Deadly Demise D3 descriptor.",
                timing_tags=("after_destroyed", "deadly_demise"),
                parameter_tokens=("D3",),
            ),
        ),
        source_ids=("phase17g:test:chaos-daemons:blood-legion-khorne-monster",),
    )


def _army_muster_request(
    *,
    catalog: ArmyCatalog,
    army_id: str,
    player_id: str,
    faction_id: str,
    detachment_id: str,
    unit_selection_id: str,
    datasheet_id: str,
    extra_unit_selections: tuple[tuple[str, str, int], ...] = (),
    unit_model_count: int = 5,
    brazenmaw_target_unit_selection_id: str | None = None,
    furys_cage_target_unit_selection_id: str | None = None,
    slaughterthirst_target_unit_selection_id: str | None = None,
    gateway_target_unit_selection_id: str | None = None,
    attach_brazenmaw_bearer: bool = False,
    attach_furys_cage_bearer: bool = False,
    attach_gateway_bearer: bool = False,
) -> ArmyMusterRequest:
    unit_selections = [
        _unit_muster_selection(
            unit_selection_id=unit_selection_id,
            datasheet_id=datasheet_id,
            model_count=unit_model_count,
        )
    ]
    unit_selections.extend(
        _unit_muster_selection(
            unit_selection_id=extra_unit_selection_id,
            datasheet_id=extra_datasheet_id,
            model_count=extra_model_count,
        )
        for extra_unit_selection_id, extra_datasheet_id, extra_model_count in extra_unit_selections
    )
    enhancement_ids: list[str] = []
    enhancement_assignments: list[EnhancementAssignment] = []
    if brazenmaw_target_unit_selection_id is not None:
        enhancement_ids.append(blood_legion_ir.BRAZENMAW_ENHANCEMENT_ID)
        enhancement_assignments.append(
            EnhancementAssignment(
                enhancement_id=blood_legion_ir.BRAZENMAW_ENHANCEMENT_ID,
                target_unit_selection_id=brazenmaw_target_unit_selection_id,
                source_id=(
                    "phase17g:test:blood-legion:brazenmaw-assignment:"
                    f"{brazenmaw_target_unit_selection_id}"
                ),
            )
        )
    if slaughterthirst_target_unit_selection_id is not None:
        enhancement_ids.append(blood_legion_ir.SLAUGHTERTHIRST_ENHANCEMENT_ID)
        enhancement_assignments.append(
            EnhancementAssignment(
                enhancement_id=blood_legion_ir.SLAUGHTERTHIRST_ENHANCEMENT_ID,
                target_unit_selection_id=slaughterthirst_target_unit_selection_id,
                source_id=(
                    "phase17g:test:blood-legion:slaughterthirst-assignment:"
                    f"{slaughterthirst_target_unit_selection_id}"
                ),
            )
        )
    if furys_cage_target_unit_selection_id is not None:
        enhancement_ids.append(blood_legion_ir.FURYS_CAGE_ENHANCEMENT_ID)
        enhancement_assignments.append(
            EnhancementAssignment(
                enhancement_id=blood_legion_ir.FURYS_CAGE_ENHANCEMENT_ID,
                target_unit_selection_id=furys_cage_target_unit_selection_id,
                source_id=(
                    "phase17g:test:blood-legion:furys-cage-assignment:"
                    f"{furys_cage_target_unit_selection_id}"
                ),
            )
        )
    if gateway_target_unit_selection_id is not None:
        enhancement_ids.append(blood_legion_ir.GATEWAY_UNTO_DAMNATION_ENHANCEMENT_ID)
        enhancement_assignments.append(
            EnhancementAssignment(
                enhancement_id=blood_legion_ir.GATEWAY_UNTO_DAMNATION_ENHANCEMENT_ID,
                target_unit_selection_id=gateway_target_unit_selection_id,
                source_id=(
                    "phase17g:test:blood-legion:gateway-unto-damnation-assignment:"
                    f"{gateway_target_unit_selection_id}"
                ),
            )
        )
    attachment_sources = tuple(
        source_selection_id
        for selected, source_selection_id in (
            (attach_brazenmaw_bearer, "blood-daemon-unit"),
            (attach_furys_cage_bearer, "khorne-monster-unit"),
            (attach_gateway_bearer, "khorne-monster-unit"),
        )
        if selected
    )
    if len(attachment_sources) > 1:
        raise AssertionError("Blood Legion fixture supports one attached bearer at a time")
    return ArmyMusterRequest(
        army_id=army_id,
        player_id=player_id,
        catalog_id=catalog.catalog_id,
        source_package_id=catalog.source_package_id,
        ruleset_id=catalog.ruleset_id,
        detachment_selection=DetachmentSelection(
            faction_id=faction_id,
            detachment_ids=(detachment_id,),
            enhancement_ids=tuple(enhancement_ids),
        ),
        force_disposition_id=(
            "purge-the-foe" if faction_id == "core-marine-force" else "take-and-hold"
        ),
        unit_selections=tuple(unit_selections),
        attachment_declarations=tuple(
            AttachmentDeclaration(
                source_unit_selection_id=source_selection_id,
                bodyguard_unit_selection_id="non-khorne-daemon-unit",
            )
            for source_selection_id in attachment_sources
        ),
        enhancement_assignments=tuple(enhancement_assignments),
    )


def _unit_muster_selection(
    *,
    unit_selection_id: str,
    datasheet_id: str,
    model_count: int = 5,
) -> UnitMusterSelection:
    return UnitMusterSelection(
        unit_selection_id=unit_selection_id,
        datasheet_id=datasheet_id,
        model_profile_selections=(
            ModelProfileSelection(
                model_profile_id="core-intercessor-like",
                model_count=model_count,
            ),
        ),
    )


def _mission_setup() -> MissionSetup:
    return MissionSetup.from_mission_pack(
        mission_pack=chapter_approved_2026_27_mission_pack(),
        mission_pool_entry_id="mission-take-and-hold-vs-purge-the-foe-layout-3",
        terrain_layout_id="take-and-hold-vs-purge-the-foe-layout-3",
        attacker_player_id="player-a",
        attacker_force_disposition_id="take-and-hold",
        defender_player_id="player-b",
        defender_force_disposition_id="purge-the-foe",
    )


def _battle_ready_state(
    *,
    lifecycle: GameLifecycle,
    config: GameConfig,
) -> GameState:
    state = lifecycle.state
    if state is None:
        raise AssertionError("lifecycle must be started")
    for army in _mustered_armies(config):
        state.record_army_definition(army)
    scenario = create_deterministic_battlefield_scenario(
        battlefield_id="phase17g-blood-legion-battlefield",
        armies=tuple(state.army_definitions),
    )
    state.record_battlefield_state(scenario.battlefield_state)
    state.record_secondary_mission_choice(_fixed_secondary_choice(player_id="player-a"))
    state.record_secondary_mission_choice(_fixed_secondary_choice(player_id="player-b"))
    while state.current_setup_step is not SetupStep.DECLARE_BATTLE_FORMATIONS:
        state.complete_current_setup_step()
    request = _runtime_content_bundle(lifecycle).battle_formation_hook_registry.next_request_for(
        BattleFormationRequestContext(
            state=state,
            decisions=lifecycle.decision_controller,
            config=config,
        )
    )
    if request is not None:
        raise AssertionError("Blood Legion test fixture should not require battle formation input")
    complete_setup_through_gate(
        state=state,
        decisions=lifecycle.decision_controller,
        config=config,
    )
    return state


def _blood_legion_enhancement_lifecycle(config: GameConfig) -> GameLifecycle:
    lifecycle = GameLifecycle()
    lifecycle.start(config)
    _battle_ready_state(lifecycle=lifecycle, config=config)
    return GameLifecycle.from_payload(lifecycle.to_payload())


def _started_state(lifecycle: GameLifecycle) -> GameState:
    state = lifecycle.state
    if state is None:
        raise AssertionError("lifecycle must be started")
    return state


def _charge_roll_modifiers(
    bundle: RuntimeContentBundle,
    *,
    state: GameState,
    unit_instance_id: str,
) -> tuple[RollModifier, ...]:
    return bundle.runtime_modifier_registry.charge_roll_modifiers(
        ChargeRollModifierContext(
            state=state,
            unit_instance_id=unit_instance_id,
            current_roll_modifiers=(),
        )
    )


def _charge_roll_operands(
    bundle: RuntimeContentBundle,
    *,
    state: GameState,
    unit_instance_id: str,
) -> tuple[int, ...]:
    return tuple(
        modifier.operand
        for modifier in _charge_roll_modifiers(
            bundle,
            state=state,
            unit_instance_id=unit_instance_id,
        )
    )


def _weapon_profile_for_unit(
    *,
    config: GameConfig,
    state: GameState,
    unit_instance_id: str,
) -> WeaponProfile:
    unit = _physical_unit_by_id(state=state, unit_instance_id=unit_instance_id)
    equipped_wargear_ids = {
        wargear_id for model in unit.own_models for wargear_id in model.wargear_ids
    }
    profiles = tuple(
        profile
        for wargear in config.army_catalog.wargear
        if wargear.wargear_id in equipped_wargear_ids
        for profile in wargear.weapon_profiles
    )
    if not profiles:
        raise AssertionError("test unit requires an equipped weapon profile")
    return profiles[0]


def _modified_weapon_profile(
    bundle: RuntimeContentBundle,
    *,
    state: GameState,
    unit_instance_id: str,
    profile: WeaponProfile,
) -> WeaponProfile:
    unit = _physical_unit_by_id(state=state, unit_instance_id=unit_instance_id)
    return bundle.runtime_modifier_registry.modified_weapon_profile(
        WeaponProfileModifierContext(
            state=state,
            source_phase=BattlePhase.FIGHT,
            attacking_unit_instance_id=unit_instance_id,
            attacker_model_instance_id=unit.own_models[0].model_instance_id,
            target_unit_instance_id=_ENEMY_UNIT_ID,
            weapon_profile=profile,
        )
    )


def _physical_unit_by_id(*, state: GameState, unit_instance_id: str) -> UnitInstance:
    matches = tuple(
        unit
        for army in state.army_definitions
        for unit in army.units
        if unit.unit_instance_id == unit_instance_id
    )
    if len(matches) != 1:
        raise AssertionError("expected one physical unit")
    return matches[0]


def _mustered_armies(config: GameConfig) -> tuple[ArmyDefinition, ...]:
    return tuple(
        muster_army(catalog=config.army_catalog, request=request)
        for request in config.army_muster_requests
    )


def _fixed_secondary_choice(*, player_id: str) -> SecondaryMissionChoice:
    return SecondaryMissionChoice(
        player_id=player_id,
        mode=SecondaryMissionMode.FIXED,
        fixed_mission_ids=("assassination", "bring_it_down"),
    )


def _runtime_content_bundle(lifecycle: GameLifecycle) -> RuntimeContentBundle:
    require_runtime_content_bundle = cast(
        Callable[[], RuntimeContentBundle],
        object.__getattribute__(lifecycle, "_require_runtime_content_bundle"),
    )
    return require_runtime_content_bundle()


def _place_murdercall_units(state: GameState) -> None:
    _place_unit_poses(
        state,
        unit_instance_id=_ENEMY_UNIT_ID,
        poses=_unit_line_poses(x=20.0, y=20.0),
    )
    _place_unit_poses(
        state,
        unit_instance_id=_BLOOD_UNIT_ID,
        poses=_unit_line_poses(x=30.0, y=20.0),
    )


def _place_blood_tainted_units_on_center_objective(state: GameState) -> None:
    if state.battlefield_state is None:
        raise AssertionError("test state requires battlefield_state")
    marker = center_marker_definition(state)
    blood = state.battlefield_state.unit_placement_by_id(_BLOOD_UNIT_ID)
    enemy = state.battlefield_state.unit_placement_by_id(_ENEMY_UNIT_ID)
    battlefield_state = state.battlefield_state.with_unit_placement(
        with_model_offsets(
            blood,
            marker,
            offsets=((0.0, 0.0), (1.5, 0.0), (0.0, 1.5), (1.5, 1.5), (-1.5, 0.0)),
        )
    )
    battlefield_state = battlefield_state.with_unit_placement(
        with_model_offsets(
            enemy,
            marker,
            offsets=((2.5, 0.0), (2.5, 1.5), (2.5, -1.5), (4.0, 0.0), (4.0, 1.5)),
        )
    )
    state.replace_battlefield_state(battlefield_state)


def _place_unit_poses(
    state: GameState,
    *,
    unit_instance_id: str,
    poses: tuple[Pose, ...],
) -> None:
    if state.battlefield_state is None:
        raise AssertionError("test state requires battlefield_state")
    placement = state.battlefield_state.unit_placement_by_id(unit_instance_id)
    state.replace_battlefield_state(
        state.battlefield_state.with_unit_placement(_with_model_poses(placement, poses=poses))
    )


def _unit_line_poses(*, x: float, y: float) -> tuple[Pose, ...]:
    return tuple(Pose.at(x, y + index * 1.8) for index in range(5))


def _with_model_poses(
    unit_placement: UnitPlacement,
    *,
    poses: tuple[Pose, ...],
) -> UnitPlacement:
    if len(poses) != len(unit_placement.model_placements):
        raise AssertionError("test pose fixture must match unit model count")
    return UnitPlacement(
        army_id=unit_placement.army_id,
        player_id=unit_placement.player_id,
        unit_instance_id=unit_placement.unit_instance_id,
        model_placements=tuple(
            ModelPlacement(
                army_id=placement.army_id,
                player_id=placement.player_id,
                unit_instance_id=placement.unit_instance_id,
                model_instance_id=placement.model_instance_id,
                pose=pose,
            )
            for placement, pose in zip(unit_placement.model_placements, poses, strict=True)
        ),
    )


def _submit_surge_proposal(
    *,
    lifecycle: GameLifecycle,
    request: DecisionRequest,
    result_id: str,
    unit_instance_id: str,
    witness: PathWitness,
) -> LifecycleStatus:
    proposal_request = MovementProposalRequest.from_decision_request_payload(request.payload)
    return lifecycle.submit_decision(
        ParameterizedSubmission(
            request_id=request.request_id,
            result_id=result_id,
            payload=validate_json_value(
                MovementProposalPayload(
                    proposal_request_id=proposal_request.request_id,
                    proposal_kind=proposal_request.proposal_kind,
                    unit_instance_id=unit_instance_id,
                    movement_phase_action="surge_move",
                    witness=witness,
                ).to_payload()
            ),
        ).to_result(request)
    )


def _emit_objective_proximity_snapshot(
    *,
    state: GameState,
    decisions: DecisionController,
    phase: BattlePhase,
    ruleset_descriptor: RulesetDescriptor,
) -> dict[str, JsonValue]:
    active_player_id = state.active_player_id
    if active_player_id is None:
        raise AssertionError("test state requires active_player_id")
    if state.battlefield_state is None:
        raise AssertionError("test state requires battlefield_state")
    record = resolve_objective_control(
        ObjectiveControlContext.from_game_state(
            state,
            timing=ObjectiveControlTiming.PHASE_END,
            phase=phase,
            ruleset_descriptor=ruleset_descriptor,
        )
    )
    objective_ids_by_unit: dict[str, set[str]] = {}
    for result in record.results:
        for contribution in result.contributors:
            objective_ids_by_unit.setdefault(contribution.unit_instance_id, set()).add(
                result.objective_id
            )
    payload = {
        "snapshot_id": (
            f"objective-proximity:{state.game_id}:round-{state.battle_round:02d}:"
            f"turn:{active_player_id}:phase:{phase.value}:start"
        ),
        "game_id": state.game_id,
        "battle_round": state.battle_round,
        "active_player_id": active_player_id,
        "phase": phase.value,
        "objective_ids_by_unit_instance_id": {
            unit_id: sorted(objective_ids)
            for unit_id, objective_ids in sorted(objective_ids_by_unit.items())
        },
        "removed_model_ids": sorted(state.battlefield_state.removed_model_ids),
        "source_objective_control_record": record.to_payload(),
    }
    decisions.event_log.append("objective_marker_phase_start_proximity_snapshot", payload)
    return cast(dict[str, JsonValue], validate_json_value(payload))


def _single_objective_id_for_unit(
    snapshot_payload: dict[str, JsonValue],
    unit_instance_id: str,
) -> str:
    mapping = cast(dict[str, JsonValue], snapshot_payload["objective_ids_by_unit_instance_id"])
    raw_objective_ids = mapping[unit_instance_id]
    if not isinstance(raw_objective_ids, list) or len(raw_objective_ids) != 1:
        raise AssertionError("expected one objective in range for unit")
    objective_id = raw_objective_ids[0]
    if type(objective_id) is not str:
        raise AssertionError("objective id must be a string")
    return objective_id


def _destroy_enemy_unit_for_blood_tainted(
    *,
    state: GameState,
    decisions: DecisionController,
) -> None:
    enemy_unit = _physical_unit_by_id(state=state, unit_instance_id=_ENEMY_UNIT_ID)
    expected_destroyed_ids = tuple(model.model_instance_id for model in enemy_unit.own_models)
    destroyed_ids = _apply_blood_tainted_fixture_mortal_wounds(
        state=state,
        decisions=decisions,
        source_unit_instance_id=_BLOOD_UNIT_ID,
        application_id="phase17g-blood-tainted-destruction",
        mortal_wounds=sum(model.wounds_remaining for model in enemy_unit.own_models),
    )
    if destroyed_ids != expected_destroyed_ids:
        raise AssertionError("Blood Tainted fixture did not destroy the complete enemy unit")


def _apply_blood_tainted_fixture_mortal_wounds(
    *,
    state: GameState,
    decisions: DecisionController,
    source_unit_instance_id: str,
    application_id: str,
    mortal_wounds: int,
) -> tuple[str, ...]:
    phase = state.current_battle_phase
    if phase is None:
        raise AssertionError("test state requires current battle phase")
    source_unit = _physical_unit_by_id(
        state=state,
        unit_instance_id=source_unit_instance_id,
    )
    if not source_unit.own_models:
        raise AssertionError("Blood Tainted fixture source unit requires a model")
    source_model = source_unit.own_models[0]
    application = apply_mortal_wounds_to_unit(
        state=state,
        decisions=decisions,
        application_id=application_id,
        source_rule_id=f"{application_id}:fixture-rule",
        source_context={
            "source_kind": "blood_tainted_fixture_mortal_wounds",
            "source_unit_instance_id": source_unit_instance_id,
            "source_model_instance_id": source_model.model_instance_id,
        },
        destruction_evidence=MortalWoundDestructionEvidence.for_non_attack_state(
            state=state,
            destroying_player_id="player-a",
            source_rules_unit_instance_id=source_unit_instance_id,
            source_model_instance_id=source_model.model_instance_id,
            destruction_source_kind=DestructionSourceKind.ABILITY,
            action_phase=phase,
            source_step="blood_tainted_fixture_mortal_wounds",
        ),
        target_unit_instance_id=_ENEMY_UNIT_ID,
        mortal_wounds=mortal_wounds,
    )
    return tuple(
        damage.model_instance_id for damage in application.applications if damage.destroyed
    )


def _destroy_enemy_unit_with_gateway_attack(
    *,
    config: GameConfig,
    state: GameState,
    decisions: DecisionController,
) -> dict[str, JsonValue]:
    attacker = _physical_unit_by_id(
        state=state,
        unit_instance_id=_OTHER_KHORNE_MONSTER_UNIT_ID,
    )
    defender = _physical_unit_by_id(state=state, unit_instance_id=_ENEMY_UNIT_ID)
    if len(attacker.own_models) != 1:
        raise AssertionError("Gateway attack source must be a singleton bearer")
    (defender_model,) = defender.own_models
    weapon_profile = replace(
        _weapon_profile_for_unit(
            config=config,
            state=state,
            unit_instance_id=_OTHER_KHORNE_MONSTER_UNIT_ID,
        ),
        damage_profile=DamageProfile.fixed(defender_model.wounds_remaining),
    )
    sequence_id = "phase17g-gateway-attack-destruction"
    attack_context_id = f"{sequence_id}:pool-001:attack-001"
    hit_spec = attack_sequence_hit_roll_spec(
        weapon_profile_id=weapon_profile.profile_id,
        attack_context_id=attack_context_id,
        attacker_player_id="player-a",
    )
    wound_spec = attack_sequence_wound_roll_spec(
        weapon_profile_id=weapon_profile.profile_id,
        attack_context_id=attack_context_id,
        attacker_player_id="player-a",
    )
    save_spec = saving_throw_roll_spec(
        save_kind=SaveKind.ARMOUR,
        player_id="player-b",
        allocated_model_id=defender_model.model_instance_id,
        attack_context_id=attack_context_id,
    )

    remaining, _allocated_model_ids, status = resolve_attack_sequence_until_blocked(
        state=state,
        decisions=decisions,
        ruleset_descriptor=config.ruleset_descriptor,
        attack_sequence=AttackSequence.start(
            sequence_id=sequence_id,
            attacker_player_id="player-a",
            attacking_unit_instance_id=_OTHER_KHORNE_MONSTER_UNIT_ID,
            attack_pools=(
                _attack_pool_for_test(
                    attacker=attacker,
                    defender=defender,
                    weapon_profile=weapon_profile,
                    attacks=1,
                ),
            ),
        ),
        already_allocated_model_ids=(),
        dice_manager=DiceRollManager(
            sequence_id,
            event_log=decisions.event_log,
            injected_results=(
                _fixed_roll_result(
                    roll_id=f"{sequence_id}:hit",
                    spec=hit_spec,
                    value=5,
                ),
                _fixed_roll_result(
                    roll_id=f"{sequence_id}:wound",
                    spec=wound_spec,
                    value=5,
                ),
                _fixed_roll_result(
                    roll_id=f"{sequence_id}:save",
                    spec=save_spec,
                    value=1,
                ),
            ),
        ),
    )
    if remaining is not None or status is not None:
        raise AssertionError("Gateway attack destruction should complete without a decision")
    matching_events = tuple(
        record
        for record in decisions.event_log.records
        if record.event_type == "model_destroyed"
        and isinstance(record.payload, dict)
        and record.payload.get("model_instance_id") == defender_model.model_instance_id
    )
    if len(matching_events) != 1 or not isinstance(matching_events[0].payload, dict):
        raise AssertionError("Gateway attack must emit one production model_destroyed event")
    return matching_events[0].payload


def _destroy_enemy_unit_with_gateway_rule(
    *,
    state: GameState,
    decisions: DecisionController,
    modifier: DeadlyDemiseModifier,
    source_rules_unit_instance_id: str,
    source_model_instance_id: str | None,
    evidence_id: str,
) -> RuleModelDestructionResult:
    enemy = _physical_unit_by_id(state=state, unit_instance_id=_ENEMY_UNIT_ID)
    (enemy_model,) = enemy.own_models
    destruction_effect = PersistingEffect(
        effect_id=f"phase17g-gateway-rule-destruction-effect:{evidence_id}",
        source_rule_id=modifier.source_rule_id,
        owner_player_id="player-a",
        target_unit_instance_ids=(_ENEMY_UNIT_ID,),
        started_battle_round=state.battle_round,
        started_phase=BattlePhase.SHOOTING,
        expiration=EffectExpiration.end_of_battle(),
        effect_payload={
            "effect_kind": "test_rule_model_destruction",
            "source_model_instance_id": source_model_instance_id,
        },
    )
    state.record_persisting_effect(destruction_effect)
    return destroy_model_with_rule_reactions(
        state=state,
        decisions=decisions,
        model_instance_id=enemy_model.model_instance_id,
        rules_unit_instance_id=_ENEMY_UNIT_ID,
        destroying_player_id="player-a",
        source_rule_id=modifier.source_rule_id,
        source_effect_ids=(destruction_effect.effect_id,),
        source_phase=BattlePhase.SHOOTING,
        source_step="gateway_rule_destruction",
        source_result_id=f"phase17g-gateway-rule-destruction-result:{evidence_id}",
        completion_event_type="gateway_rule_destruction_completed",
        completion_event_payload={
            "source_model_instance_id": source_model_instance_id,
            "target_model_instance_id": enemy_model.model_instance_id,
        },
        source_rules_unit_instance_id=source_rules_unit_instance_id,
        source_model_instance_id=source_model_instance_id,
    )


def _single_deadly_demise_source(
    *,
    state: GameState,
    model_instance_id: str,
) -> DestructionReactionSource:
    sources = tuple(
        source
        for source in state.destruction_reaction_sources_for_model(
            model_instance_id=model_instance_id
        )
        if source.reaction_kind is DestructionReactionKind.DEADLY_DEMISE
    )
    if len(sources) != 1:
        raise AssertionError("expected one Deadly Demise source")
    return sources[0]


def _destroy_enemy_unit_with_split_attackers_for_blood_tainted(
    *,
    state: GameState,
    decisions: DecisionController,
) -> None:
    enemy_unit = _physical_unit_by_id(state=state, unit_instance_id=_ENEMY_UNIT_ID)
    if len(enemy_unit.own_models) < 2:
        raise AssertionError("split-attacker fixture requires at least two enemy models")
    first_model = enemy_unit.own_models[0]
    first_destroyed_ids = _apply_blood_tainted_fixture_mortal_wounds(
        state=state,
        decisions=decisions,
        source_unit_instance_id=_BLOOD_UNIT_ID,
        application_id="phase17g-blood-tainted-split-first-attacker",
        mortal_wounds=first_model.wounds_remaining,
    )
    if first_destroyed_ids != (first_model.model_instance_id,):
        raise AssertionError("split-attacker fixture first source destroyed unexpected models")
    remaining_models = enemy_unit.own_models[1:]
    completion_destroyed_ids = _apply_blood_tainted_fixture_mortal_wounds(
        state=state,
        decisions=decisions,
        source_unit_instance_id=_OTHER_FRIENDLY_UNIT_ID,
        application_id="phase17g-blood-tainted-split-completion-attacker",
        mortal_wounds=sum(model.wounds_remaining for model in remaining_models),
    )
    expected_completion_ids = tuple(model.model_instance_id for model in remaining_models)
    if completion_destroyed_ids != expected_completion_ids:
        raise AssertionError("split-attacker fixture completion source destroyed unexpected models")


def _event_payload(
    decisions: DecisionController,
    event_type: str,
) -> dict[str, JsonValue]:
    for event in decisions.event_log.records:
        if event.event_type == event_type:
            return cast(dict[str, JsonValue], event.payload)
    raise AssertionError(f"missing event {event_type}")


def _events_of_type(
    decisions: DecisionController,
    event_type: str,
) -> tuple[dict[str, JsonValue], ...]:
    return tuple(
        cast(dict[str, JsonValue], event.payload)
        for event in decisions.event_log.records
        if event.event_type == event_type
    )


def _event_payload_by_id(
    decisions: DecisionController,
    event_id: str,
) -> dict[str, JsonValue]:
    for event in decisions.event_log.records:
        if event.event_id == event_id:
            return cast(dict[str, JsonValue], event.payload)
    raise AssertionError(f"missing event {event_id}")
