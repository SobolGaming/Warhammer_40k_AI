from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import replace
from typing import cast

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

from warhammer40k_core.adapters.contracts import ParameterizedSubmission
from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.core.attachment_eligibility import (
    AttachmentEligibility,
    AttachmentRole,
    AttachmentTargetEligibility,
)
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
from warhammer40k_core.core.ruleset_descriptor import MovementMode, RulesetDescriptor
from warhammer40k_core.core.weapon_profiles import WeaponKeyword, WeaponProfile
from warhammer40k_core.engine.army_mustering import (
    ArmyDefinition,
    ArmyMusterRequest,
    EnhancementAssignment,
    muster_army,
    validate_roster_legality,
)
from warhammer40k_core.engine.attack_sequence_model import deadly_demise_trigger_roll_spec
from warhammer40k_core.engine.battle_formation_hooks import BattleFormationRequestContext
from warhammer40k_core.engine.battle_round_flow import BattleRoundFlow
from warhammer40k_core.engine.battlefield_state import ModelPlacement, UnitPlacement
from warhammer40k_core.engine.damage_allocation import (
    DestructionReactionKind,
    DestructionReactionSource,
)
from warhammer40k_core.engine.deadly_demise import (
    deadly_demise_mortal_wounds_for_target,
    effective_deadly_demise_descriptor,
    resolve_deadly_demise_trigger,
)
from warhammer40k_core.engine.deadly_demise_modifiers import (
    DEADLY_DEMISE_MODIFIER_CONDITION_EFFECT_KIND,
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
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.faction_content.bundle import RuntimeContentBundle
from warhammer40k_core.engine.faction_content.runtime import build_runtime_content_bundle
from warhammer40k_core.engine.faction_content.warhammer_40000_11th.chaos_daemons.detachments.blood_legion import (  # noqa: E501
    enhancements,
    rule,
)
from warhammer40k_core.engine.game_state import (
    GameConfig,
    GameState,
    SecondaryMissionChoice,
    SecondaryMissionMode,
)
from warhammer40k_core.engine.lifecycle import GameLifecycle
from warhammer40k_core.engine.list_validation import (
    AttachmentDeclaration,
    DetachmentSelection,
    UnitMusterSelection,
)
from warhammer40k_core.engine.mission_setup import MissionSetup
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
from warhammer40k_core.engine.phases.movement import (
    SELECT_MOVEMENT_ACTION_DECISION_TYPE,
    MovementPhaseActionKind,
)
from warhammer40k_core.engine.placement import create_deterministic_battlefield_scenario
from warhammer40k_core.engine.runtime_modifiers import (
    ChargeRollModifierContext,
    WeaponProfileModifierContext,
)
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
from warhammer40k_core.rules.rule_ir import RuleEffectKind, parameter_payload
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
_BRAZENMAW_ATTACHED_UNIT_ID = "attached-unit:army-alpha:non-khorne-daemon-unit"


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
        unit_instance_id=_BRAZENMAW_ATTACHED_UNIT_ID,
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


def test_gateway_unto_damnation_modifies_only_bearer_and_persists_destroyed_unit_history() -> None:
    config = _blood_legion_config(
        game_id="phase17g-gateway-runtime",
        include_slaughterthirst_targets=True,
        gateway_target_unit_selection_id="khorne-monster-unit",
    )
    lifecycle = _blood_legion_enhancement_lifecycle(config)
    state = _started_state(lifecycle)
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.SHOOTING)
    bundle = _runtime_content_bundle(lifecycle)
    monster = _physical_unit_by_id(
        state=state,
        unit_instance_id=_OTHER_KHORNE_MONSTER_UNIT_ID,
    )
    bearer_model_id = monster.own_models[0].model_instance_id
    other_model_id = monster.own_models[1].model_instance_id
    bearer_source = _single_deadly_demise_source(
        state=state,
        model_instance_id=bearer_model_id,
    )
    other_source = _single_deadly_demise_source(
        state=state,
        model_instance_id=other_model_id,
    )
    decisions = lifecycle.decision_controller

    before_kill = effective_deadly_demise_descriptor(
        state=state,
        event_log=decisions.event_log,
        source=bearer_source,
        model_instance_id=bearer_model_id,
    )
    other_model_descriptor = effective_deadly_demise_descriptor(
        state=state,
        event_log=decisions.event_log,
        source=other_source,
        model_instance_id=other_model_id,
    )

    assert before_kill["trigger_roll_threshold"] == 2
    assert before_kill["mortal_wounds"] == {"kind": "d3"}
    assert other_model_descriptor == {
        "trigger_roll_threshold": 6,
        "range_inches": 6.0,
        "mortal_wounds": {"kind": "d3"},
    }

    _destroy_enemy_unit_for_gateway(
        state=state,
        decisions=decisions,
        attacking_unit_instance_id=_OTHER_KHORNE_MONSTER_UNIT_ID,
        attacking_model_instance_id=bearer_model_id,
        weapon_profile=_weapon_profile_for_unit(
            config=config,
            state=state,
            unit_instance_id=_OTHER_KHORNE_MONSTER_UNIT_ID,
        ),
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


@pytest.mark.parametrize("attribution_kind", ["other_model_attack", "unit_ability"])
def test_gateway_unto_damnation_multi_model_attribution_fails_closed(
    attribution_kind: str,
) -> None:
    config = _blood_legion_config(
        game_id=f"phase17g-gateway-attribution-{attribution_kind}",
        include_slaughterthirst_targets=True,
        gateway_target_unit_selection_id="khorne-monster-unit",
    )
    lifecycle = _blood_legion_enhancement_lifecycle(config)
    state = _started_state(lifecycle)
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.SHOOTING)
    monster = _physical_unit_by_id(
        state=state,
        unit_instance_id=_OTHER_KHORNE_MONSTER_UNIT_ID,
    )
    bearer_model_id = monster.own_models[0].model_instance_id
    other_model_id = monster.own_models[1].model_instance_id
    source = _single_deadly_demise_source(
        state=state,
        model_instance_id=bearer_model_id,
    )
    if attribution_kind == "other_model_attack":
        _destroy_enemy_unit_for_gateway(
            state=state,
            decisions=lifecycle.decision_controller,
            attacking_unit_instance_id=_OTHER_KHORNE_MONSTER_UNIT_ID,
            attacking_model_instance_id=other_model_id,
            weapon_profile=_weapon_profile_for_unit(
                config=config,
                state=state,
                unit_instance_id=_OTHER_KHORNE_MONSTER_UNIT_ID,
            ),
        )
    else:
        _destroy_enemy_unit_for_gateway(
            state=state,
            decisions=lifecycle.decision_controller,
            attacking_unit_instance_id=_OTHER_KHORNE_MONSTER_UNIT_ID,
            attacking_model_instance_id=None,
            weapon_profile=None,
        )

    descriptor = effective_deadly_demise_descriptor(
        state=state,
        event_log=lifecycle.decision_controller.event_log,
        source=source,
        model_instance_id=bearer_model_id,
    )

    assert descriptor["trigger_roll_threshold"] == 2
    assert descriptor["mortal_wounds"] == {"kind": "d3"}


def test_gateway_unto_damnation_source_identity_drift_fails_closed() -> None:
    config = _blood_legion_config(
        game_id="phase17g-gateway-source-drift",
        include_slaughterthirst_targets=True,
        gateway_target_unit_selection_id="khorne-monster-unit",
    )
    lifecycle = _blood_legion_enhancement_lifecycle(config)
    state = _started_state(lifecycle)
    monster = _physical_unit_by_id(
        state=state,
        unit_instance_id=_OTHER_KHORNE_MONSTER_UNIT_ID,
    )
    bearer_model_id = monster.own_models[0].model_instance_id
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


def _blood_legion_config(
    *,
    game_id: str = "phase17g-blood-legion-game",
    daemon_detachment_id: str = rule.BLOOD_LEGION_DETACHMENT_ID,
    turn_order: tuple[str, str] = ("player-a", "player-b"),
    include_other_friendly_unit: bool = False,
    include_slaughterthirst_targets: bool = False,
    brazenmaw_target_unit_selection_id: str | None = None,
    slaughterthirst_target_unit_selection_id: str | None = None,
    gateway_target_unit_selection_id: str | None = None,
    attach_brazenmaw_bearer: bool = False,
) -> GameConfig:
    catalog = _blood_legion_catalog()
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
                ),
                brazenmaw_target_unit_selection_id=brazenmaw_target_unit_selection_id,
                slaughterthirst_target_unit_selection_id=(slaughterthirst_target_unit_selection_id),
                gateway_target_unit_selection_id=gateway_target_unit_selection_id,
                attach_brazenmaw_bearer=attach_brazenmaw_bearer,
            ),
            _army_muster_request(
                catalog=catalog,
                army_id="army-beta",
                player_id="player-b",
                faction_id="core-marine-force",
                detachment_id="core-combined-arms",
                unit_selection_id="enemy-unit",
                datasheet_id="core-intercessor-like-infantry",
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
) -> tuple[tuple[str, str], ...]:
    selections: list[tuple[str, str]] = []
    if include_other_friendly_unit or attach_brazenmaw_bearer:
        selections.append(
            (
                "non-khorne-daemon-unit",
                _BLOOD_LEGION_NON_KHORNE_DATASHEET_ID,
            )
        )
    if include_slaughterthirst_targets:
        selections.extend(
            (
                ("khorne-daemon-unit", _BLOOD_LEGION_DATASHEET_ID),
                ("khorne-monster-unit", _BLOOD_LEGION_KHORNE_MONSTER_DATASHEET_ID),
            )
        )
    return tuple(selections)


def _blood_legion_catalog() -> ArmyCatalog:
    base_catalog = ArmyCatalog.phase9a_canonical_content_pack()
    base_datasheet = base_catalog.datasheet_by_id("core-intercessor-like-infantry")
    daemon_datasheet = _blood_legion_datasheet(base_datasheet)
    non_khorne_daemon_datasheet = _blood_legion_non_khorne_datasheet(base_datasheet)
    khorne_monster_datasheet = _blood_legion_khorne_monster_datasheet(base_datasheet)
    return replace(
        base_catalog,
        datasheets=(
            *base_catalog.datasheets,
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
                force_disposition_ids=("phase17g-force",),
                enhancement_ids=(
                    blood_legion_ir.BRAZENMAW_ENHANCEMENT_ID,
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
                force_disposition_ids=("phase17g-force",),
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
) -> DatasheetDefinition:
    return replace(
        base_datasheet,
        datasheet_id=_BLOOD_LEGION_KHORNE_MONSTER_DATASHEET_ID,
        name="Blood Legion Khorne Monster",
        keywords=DatasheetKeywordSet(
            keywords=("Character", "Khorne", "Monster"),
            faction_keywords=("Legiones Daemonica",),
        ),
        attachment_eligibilities=(),
        abilities=(
            *base_datasheet.abilities,
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
    extra_unit_selections: tuple[tuple[str, str], ...] = (),
    brazenmaw_target_unit_selection_id: str | None = None,
    slaughterthirst_target_unit_selection_id: str | None = None,
    gateway_target_unit_selection_id: str | None = None,
    attach_brazenmaw_bearer: bool = False,
) -> ArmyMusterRequest:
    unit_selections = [
        _unit_muster_selection(
            unit_selection_id=unit_selection_id,
            datasheet_id=datasheet_id,
        )
    ]
    unit_selections.extend(
        _unit_muster_selection(
            unit_selection_id=extra_unit_selection_id,
            datasheet_id=extra_datasheet_id,
        )
        for extra_unit_selection_id, extra_datasheet_id in extra_unit_selections
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
            "purge-the-foe" if faction_id == "core-marine-force" else "phase17g-force"
        ),
        unit_selections=tuple(unit_selections),
        attachment_declarations=(
            (
                AttachmentDeclaration(
                    source_unit_selection_id="blood-daemon-unit",
                    bodyguard_unit_selection_id="non-khorne-daemon-unit",
                ),
            )
            if attach_brazenmaw_bearer
            else ()
        ),
        enhancement_assignments=tuple(enhancement_assignments),
    )


def _unit_muster_selection(
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
    )


def _mission_setup() -> MissionSetup:
    return MissionSetup.from_mission_pack(
        mission_pack=chapter_approved_2026_27_mission_pack(),
        mission_pool_entry_id="mission-take-and-hold-vs-purge-the-foe-layout-3",
        terrain_layout_id="take-and-hold-vs-purge-the-foe-layout-3",
        attacker_player_id="player-a",
        defender_player_id="player-b",
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
            decisions=DecisionController(),
            config=config,
        )
    )
    if request is not None:
        raise AssertionError("Blood Legion test fixture should not require battle formation input")
    complete_setup_through_gate(state=state, config=config)
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
    if state.battlefield_state is None:
        raise AssertionError("test state requires battlefield_state")
    phase = state.current_battle_phase
    if phase is None:
        raise AssertionError("test state requires current battle phase")
    enemy_army = state.army_definition_for_player("player-b")
    if enemy_army is None:
        raise AssertionError("test state requires player-b army")
    enemy_unit = enemy_army.unit_by_id(_ENEMY_UNIT_ID)
    destroyed_model_ids = tuple(model.model_instance_id for model in enemy_unit.own_models)
    state.replace_battlefield_state(
        state.battlefield_state.with_removed_models(destroyed_model_ids)
    )
    for index, model_id in enumerate(destroyed_model_ids, start=1):
        decisions.event_log.append(
            "model_destroyed",
            {
                "game_id": state.game_id,
                "battle_round": state.battle_round,
                "active_player_id": state.active_player_id,
                "phase": phase.value,
                **ModelDestructionAttribution.for_non_attack(
                    destroying_player_id="player-a",
                    source_kind=DestructionSourceKind.ABILITY,
                    source_rules_unit_instance_id=_BLOOD_UNIT_ID,
                ).to_payload(),
                "target_unit_instance_id": _ENEMY_UNIT_ID,
                "model_instance_id": model_id,
                "damage_kind": "normal",
                "damage_event_id": f"phase17g-blood-tainted-damage-{index:02d}",
                "destroyed_model_rules_triggered": True,
            },
        )


def _destroy_enemy_unit_for_gateway(
    *,
    state: GameState,
    decisions: DecisionController,
    attacking_unit_instance_id: str,
    attacking_model_instance_id: str | None,
    weapon_profile: WeaponProfile | None,
) -> None:
    if state.battlefield_state is None:
        raise AssertionError("test state requires battlefield_state")
    phase = state.current_battle_phase
    if phase is None:
        raise AssertionError("test state requires current battle phase")
    enemy_unit = _physical_unit_by_id(state=state, unit_instance_id=_ENEMY_UNIT_ID)
    destroyed_model_ids = tuple(model.model_instance_id for model in enemy_unit.own_models)
    state.replace_battlefield_state(
        state.battlefield_state.with_removed_models(destroyed_model_ids)
    )
    state.replace_army_definitions(
        [
            replace(
                army,
                units=tuple(
                    replace(
                        unit,
                        own_models=tuple(
                            replace(model, wounds_remaining=0) for model in unit.own_models
                        ),
                    )
                    if unit.unit_instance_id == _ENEMY_UNIT_ID
                    else unit
                    for unit in army.units
                ),
            )
            for army in state.army_definitions
        ]
    )
    if attacking_model_instance_id is None:
        if weapon_profile is not None:
            raise AssertionError("non-attack attribution cannot carry a weapon profile")
        attribution = ModelDestructionAttribution.for_non_attack(
            destroying_player_id="player-a",
            source_kind=DestructionSourceKind.ABILITY,
            source_rules_unit_instance_id=attacking_unit_instance_id,
        )
    else:
        if weapon_profile is None:
            raise AssertionError("attack attribution requires a weapon profile")
        attribution = ModelDestructionAttribution.for_attack(
            destroying_player_id="player-a",
            attacking_unit_instance_id=attacking_unit_instance_id,
            attacking_model_instance_id=attacking_model_instance_id,
            weapon_profile=weapon_profile,
            attack_context_id="phase17g-gateway-destroyed-unit",
        )
    for index, model_id in enumerate(destroyed_model_ids, start=1):
        decisions.event_log.append(
            "model_destroyed",
            {
                "game_id": state.game_id,
                "battle_round": state.battle_round,
                "active_player_id": state.active_player_id,
                "phase": phase.value,
                **attribution.to_payload(),
                "target_unit_instance_id": _ENEMY_UNIT_ID,
                "model_instance_id": model_id,
                "damage_kind": "normal",
                "damage_event_id": f"phase17g-gateway-damage-{index:02d}",
                "destroyed_model_rules_triggered": True,
            },
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
    if state.battlefield_state is None:
        raise AssertionError("test state requires battlefield_state")
    phase = state.current_battle_phase
    if phase is None:
        raise AssertionError("test state requires current battle phase")
    enemy_army = state.army_definition_for_player("player-b")
    if enemy_army is None:
        raise AssertionError("test state requires player-b army")
    enemy_unit = enemy_army.unit_by_id(_ENEMY_UNIT_ID)
    destroyed_model_ids = tuple(model.model_instance_id for model in enemy_unit.own_models)
    state.replace_battlefield_state(
        state.battlefield_state.with_removed_models(destroyed_model_ids)
    )
    for index, model_id in enumerate(destroyed_model_ids, start=1):
        attacker_id = _BLOOD_UNIT_ID if index == 1 else _OTHER_FRIENDLY_UNIT_ID
        decisions.event_log.append(
            "model_destroyed",
            {
                "game_id": state.game_id,
                "battle_round": state.battle_round,
                "active_player_id": state.active_player_id,
                "phase": phase.value,
                **ModelDestructionAttribution.for_non_attack(
                    destroying_player_id="player-a",
                    source_kind=DestructionSourceKind.ABILITY,
                    source_rules_unit_instance_id=attacker_id,
                ).to_payload(),
                "target_unit_instance_id": _ENEMY_UNIT_ID,
                "model_instance_id": model_id,
                "damage_kind": "normal",
                "damage_event_id": f"phase17g-blood-tainted-split-damage-{index:02d}",
                "destroyed_model_rules_triggered": True,
            },
        )


def _event_payload(
    decisions: DecisionController,
    event_type: str,
) -> dict[str, JsonValue]:
    for event in decisions.event_log.records:
        if event.event_type == event_type:
            return cast(dict[str, JsonValue], event.payload)
    raise AssertionError(f"missing event {event_type}")
