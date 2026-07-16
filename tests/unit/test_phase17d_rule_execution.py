from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from typing import Any, cast

import pytest

from warhammer40k_core.adapters.contracts import ParameterizedSubmission
from warhammer40k_core.adapters.event_stream import EventStreamCursor
from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.core.datasheet import (
    CatalogAbilitySourceKind,
    CatalogAbilitySupport,
    CatalogJsonObject,
    DatasheetAbilityDescriptor,
)
from warhammer40k_core.core.ruleset_descriptor import (
    BattlePhaseKind,
    MovementMode,
    RulesetDescriptor,
)
from warhammer40k_core.core.weapon_profiles import WeaponKeyword, WeaponProfile
from warhammer40k_core.engine.abilities import (
    GENERIC_RULE_IR_ABILITY_HANDLER_ID,
    AbilityCatalogIndex,
    AbilityCatalogRecord,
    AbilityDefinition,
    AbilityExecutionContext,
    AbilityResolutionStatus,
    AbilitySourceKind,
    AbilityTimingDescriptor,
    KeywordGate,
    default_ability_handler_registry,
    execute_abilities_from_index,
)
from warhammer40k_core.engine.ability_catalog import (
    build_player_ability_index,
    catalog_ability_records_from_catalog,
)
from warhammer40k_core.engine.army_mustering import (
    ArmyDefinition,
    ArmyMusterRequest,
    muster_army,
)
from warhammer40k_core.engine.battlefield_state import (
    BattlefieldPlacementKind,
    BattlefieldRuntimeState,
    BattlefieldScenario,
    UnitPlacement,
)
from warhammer40k_core.engine.catalog_rule_consumption import (
    catalog_restore_lost_wounds_after_destroying_unit,
    catalog_wound_roll_reroll_permission_for_attack,
)
from warhammer40k_core.engine.catalog_setup_reactive_charge_move import (
    apply_catalog_setup_reactive_charge_move,
    invalid_catalog_setup_reactive_charge_move_status,
    is_catalog_setup_reactive_charge_move_request,
)
from warhammer40k_core.engine.catalog_setup_reactive_shoot_charge import (
    CATALOG_SETUP_REACTIVE_SOURCE_KIND,
    SELECT_CATALOG_SETUP_REACTIVE_SHOOT_CHARGE_DECISION_TYPE,
    apply_catalog_setup_reactive_shoot_charge_result,
    invalid_catalog_setup_reactive_shoot_charge_status,
    request_catalog_setup_reactive_shoot_charge_if_available,
)
from warhammer40k_core.engine.command_point_rule_execution import (
    CommandPointRuleMutationResult,
    apply_command_point_rule_mutation,
    command_point_operation_and_delta,
    command_point_operation_shape_reason,
    command_point_rule_unavailable_reason,
)
from warhammer40k_core.engine.command_points import (
    CommandPointLedger,
    CommandPointSourceKind,
    initial_command_point_ledgers,
)
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_request import DecisionOption, DecisionRequest
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.effects import (
    EffectError,
    EffectExpiration,
    generic_rule_persisting_effect,
)
from warhammer40k_core.engine.event_log import EventLog, JsonValue, validate_json_value
from warhammer40k_core.engine.fight_phase_start_hooks import (
    SELECT_FACTION_RULE_FIGHT_PHASE_START_OPTION_DECISION_TYPE,
)
from warhammer40k_core.engine.game_state import GameConfig, GameState
from warhammer40k_core.engine.lifecycle import GameLifecycle
from warhammer40k_core.engine.lifecycle_reaction_queue import (
    validate_reaction_queue_consistency,
)
from warhammer40k_core.engine.list_validation import (
    AttachmentDeclaration,
    DetachmentSelection,
    UnitMusterSelection,
)
from warhammer40k_core.engine.movement_proposals import (
    MOVEMENT_PROPOSAL_DECISION_TYPE,
    PLACEMENT_PROPOSAL_DECISION_TYPE,
    MovementProposalRequest,
    ProposalKind,
)
from warhammer40k_core.engine.phase import (
    BattlePhase,
    GameLifecycleError,
    GameLifecycleStage,
    LifecycleStatusKind,
)
from warhammer40k_core.engine.phases.charge import (
    CHARGE_MOVE_REQUIRED_TARGET_UNIT_INSTANCE_IDS_KEY,
    FIGHTS_FIRST_CHARGE_EFFECT_KIND,
    ChargeMoveProposal,
)
from warhammer40k_core.engine.placement import create_deterministic_battlefield_scenario
from warhammer40k_core.engine.reaction_queue import ReactionQueue
from warhammer40k_core.engine.replay import ReplayRunner, ReplayRunStatus
from warhammer40k_core.engine.rule_execution import (
    RuleExecutionContext,
    RuleExecutionRegistry,
    RuleExecutionResult,
    RuleExecutionStatus,
    RuleRuntimeBinding,
    default_rule_execution_registry,
    execute_rule_ir,
    rule_execution_status_from_token,
    rule_ir_from_execution_payload,
    scoped_rule_ir_from_execution_payload,
)
from warhammer40k_core.engine.rule_frequency import RULE_FREQUENCY_LIMIT_CONSUMED_EVENT
from warhammer40k_core.engine.runtime_modifiers import (
    RuntimeModifierRegistry,
    WeaponProfileModifierContext,
)
from warhammer40k_core.engine.scoring import initial_victory_point_ledgers
from warhammer40k_core.engine.selected_target_context import SELECTED_TARGET_UNIT_CONTEXT_KEY
from warhammer40k_core.engine.target_restriction_hooks import ChargeTargetRestrictionHookRegistry
from warhammer40k_core.engine.timing_windows import (
    ReactionWindow,
    TimingTriggerKind,
    TimingWindow,
    TimingWindowDescriptor,
)
from warhammer40k_core.engine.unit_factory import ModelInstance, UnitInstance
from warhammer40k_core.engine.wargear_selections import (
    ModelProfileSelection,
)
from warhammer40k_core.geometry.pathing import PathWitness
from warhammer40k_core.geometry.pose import Pose
from warhammer40k_core.rules.rule_compiler import CompiledRuleSource, compile_rule_source_text
from warhammer40k_core.rules.rule_ir import (
    RuleClause,
    RuleEffectKind,
    RuleEffectSpec,
    RuleIR,
    RuleIRPayload,
    RuleParameter,
    RuleTriggerKind,
    parameter_payload,
)
from warhammer40k_core.rules.source_data import RuleSourceText
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    datasheet_keyword_lexicon_2026_06_14 as datasheet_keyword_lexicon_source,
)

SOURCE_KEYWORD_SEQUENCE_PARTS = (
    datasheet_keyword_lexicon_source.canonical_datasheet_keyword_sequence_parts()
)
SETUP_REACTIVE_SHOOT_CHARGE_TEXT = (
    "At the end of your opponent's Movement phase, you can select one enemy unit that was "
    'set up on the battlefield within 12" of this model; this model can then either: '
    "Shoot at that unit, but only if it is an eligible target. Declare a charge. This unit "
    "must end that charge move engaged with the enemy unit you selected (note that even if "
    "this charge is successful, this unit does not receive any Charge bonus this turn)."
)
ONCE_PER_BATTLE_FIGHT_BOOST_TEXT = (
    "Once per battle, at the start of the Fight phase, this model can use this ability. "
    "If it does, until the end of the phase, add 3 to the Attacks characteristic of melee "
    "weapons equipped by this model and those weapons have the [DEVASTATING WOUNDS] ability."
)


def test_phase17d_once_per_battle_activation_consumes_and_modifies_source_model() -> None:
    state = _battle_state_with_attached_leader_support()
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.FIGHT)
    source_unit = _unit_by_id(state, "army-alpha:leader-unit")
    source_model = source_unit.own_models[0]
    source_rules_unit_id = "attached-unit:army-alpha:bodyguard-unit"
    event_log = EventLog()
    compiled = _compiled(ONCE_PER_BATTLE_FIGHT_BOOST_TEXT)
    context = _execution_context(
        state=state,
        event_log=event_log,
        source_unit_instance_id=source_rules_unit_id,
        source_model_instance_id=source_model.model_instance_id,
        phase=BattlePhaseKind.FIGHT,
    )

    missing_log = execute_rule_ir(
        rule_ir=compiled.rule_ir,
        context=replace(context, event_log=None),
    )
    applied = execute_rule_ir(rule_ir=compiled.rule_ir, context=context)
    effect_count = len(state.persisting_effects)
    repeated = execute_rule_ir(rule_ir=compiled.rule_ir, context=context)

    assert missing_log.status is RuleExecutionStatus.INVALID
    assert missing_log.reason == "missing_input:event_log"
    assert applied.status is RuleExecutionStatus.APPLIED
    assert len(applied.effect_payloads) == 2
    assert len(state.persisting_effects) == 2
    assert [
        event.event_type
        for event in event_log.records
        if event.event_type == RULE_FREQUENCY_LIMIT_CONSUMED_EVENT
    ] == [RULE_FREQUENCY_LIMIT_CONSUMED_EVENT]
    assert EventLog.from_payload(event_log.to_payload()).to_payload() == event_log.to_payload()
    assert repeated.status is RuleExecutionStatus.INVALID
    assert repeated.reason == "frequency_limit_exhausted:battle"
    assert len(state.persisting_effects) == effect_count

    profile = _weapon_profile("core-leader-blade")
    modified = RuntimeModifierRegistry.empty().modified_weapon_profile(
        WeaponProfileModifierContext(
            state=state,
            source_phase=BattlePhase.FIGHT,
            attacking_unit_instance_id=source_rules_unit_id,
            attacker_model_instance_id=source_model.model_instance_id,
            target_unit_instance_id="army-alpha:bodyguard-unit",
            weapon_profile=profile,
        )
    )

    assert profile.attack_profile.fixed_attacks == 5
    assert modified.attack_profile.fixed_attacks == 8
    assert WeaponKeyword.DEVASTATING_WOUNDS in modified.keywords


def test_phase17d_generic_modifier_rule_executes_as_source_linked_effect() -> None:
    compiled = _compiled("Add 1 to hit rolls for that unit.")
    context = _execution_context(
        target_unit_instance_ids=("army-alpha:intercessor-unit-1",),
    )

    result = execute_rule_ir(
        rule_ir=compiled.rule_ir,
        context=context,
        registry=default_rule_execution_registry(),
    )
    effect_payload = result.effect_payloads[0]
    effect = _json_object(effect_payload["effect"])

    assert result.status is RuleExecutionStatus.APPLIED
    assert result.reason is None
    assert result.applied_clause_ids == (compiled.rule_ir.clauses[0].clause_id,)
    assert effect["kind"] == "modify_dice_roll"
    assert effect["parameters"] == [
        {"key": "delta", "value": 1},
        {"key": "roll_type", "value": "hit"},
    ]
    assert result.event_records[0].event_type == "rule_execution_effect_applied"
    assert result.to_payload()["source_id"] == compiled.rule_ir.source_id


def test_phase17d_target_scoped_effect_requires_target_binding() -> None:
    compiled = _compiled("Add 1 to hit rolls for that unit.")

    result = execute_rule_ir(
        rule_ir=compiled.rule_ir,
        context=_execution_context(),
        registry=default_rule_execution_registry(),
    )

    assert result.status is RuleExecutionStatus.INVALID
    assert result.reason == "missing_target:unit_instance_ids"
    assert result.effect_payloads == ()
    assert result.event_records == ()


def test_phase17d_this_unit_effect_uses_source_unit_binding() -> None:
    source_unit_id = "army-alpha:intercessor-unit-1"
    unrelated_target_unit_id = "army-beta:intercessor-unit-2"
    compiled = _compiled("This unit can be set up more than 9 inches away from enemy units.")

    missing_source = execute_rule_ir(
        rule_ir=compiled.rule_ir,
        context=_execution_context(),
        registry=default_rule_execution_registry(),
    )
    explicit_target_without_source = execute_rule_ir(
        rule_ir=compiled.rule_ir,
        context=_execution_context(target_unit_instance_ids=(unrelated_target_unit_id,)),
        registry=default_rule_execution_registry(),
    )
    applied = execute_rule_ir(
        rule_ir=compiled.rule_ir,
        context=_execution_context(
            source_unit_instance_id=source_unit_id,
            target_unit_instance_ids=(unrelated_target_unit_id,),
        ),
        registry=default_rule_execution_registry(),
    )

    assert missing_source.status is RuleExecutionStatus.INVALID
    assert missing_source.reason == "missing_input:source_unit_instance_id"
    assert explicit_target_without_source.status is RuleExecutionStatus.INVALID
    assert explicit_target_without_source.reason == "missing_input:source_unit_instance_id"
    assert applied.status is RuleExecutionStatus.APPLIED
    assert applied.effect_payloads[0]["target_unit_instance_ids"] == [source_unit_id]


def test_phase17d_optional_wargear_bearer_unit_effects_execute_generically() -> None:
    source_unit_id = "army-alpha:bloodletters-1"
    icon = _compiled("Models in the bearer's unit have a Leadership characteristic of 6+.")
    instrument = _compiled("Add 1 to Charge rolls made for the bearer's unit.")

    icon_result = execute_rule_ir(
        rule_ir=icon.rule_ir,
        context=_execution_context(source_unit_instance_id=source_unit_id),
        registry=default_rule_execution_registry(),
    )
    instrument_result = execute_rule_ir(
        rule_ir=instrument.rule_ir,
        context=_execution_context(source_unit_instance_id=source_unit_id),
        registry=default_rule_execution_registry(),
    )

    assert icon_result.status is RuleExecutionStatus.APPLIED
    assert icon_result.effect_payloads[0]["target_unit_instance_ids"] == [source_unit_id]
    assert _json_object(icon_result.effect_payloads[0]["effect"])["parameters"] == [
        {"key": "characteristic", "value": "leadership"},
        {"key": "value", "value": "6+"},
    ]
    assert instrument_result.status is RuleExecutionStatus.APPLIED
    assert instrument_result.effect_payloads[0]["target_unit_instance_ids"] == [source_unit_id]
    assert _json_object(instrument_result.effect_payloads[0]["effect"])["parameters"] == [
        {"key": "delta", "value": 1},
        {"key": "roll_type", "value": "charge"},
    ]


def test_phase17d_catalog_setup_reactive_shoot_charge_requests_finite_actions_and_drift() -> None:
    descriptor = _generic_catalog_descriptor(
        SETUP_REACTIVE_SHOOT_CHARGE_TEXT,
        ability_id="setup-reactive-shoot-charge",
    )
    catalog = _catalog_with_descriptor(descriptor)
    armies = (
        muster_army(
            catalog=catalog,
            request=_muster_request(
                catalog=catalog,
                player_id="player-a",
                army_id="army-alpha",
                unit_selection_id="intercessor-unit-1",
            ),
        ),
        muster_army(
            catalog=catalog,
            request=_muster_request(
                catalog=catalog,
                player_id="player-b",
                army_id="army-beta",
                unit_selection_id="intercessor-unit-2",
            ),
        ),
    )
    state = _battle_state()
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.MOVEMENT)
    for army in armies:
        state.record_army_definition(army)
    scenario = create_deterministic_battlefield_scenario(
        battlefield_id="phase17d-setup-reactive",
        armies=armies,
    )
    state.battlefield_state = scenario.battlefield_state
    target_unit_id = "army-alpha:intercessor-unit-1"
    source_unit_id = "army-beta:intercessor-unit-2"
    state.battlefield_state = _with_unit_pose(
        state.battlefield_state,
        unit_instance_id=target_unit_id,
        pose=Pose.at(0.0, 10.0),
    )
    state.battlefield_state = _with_unit_pose(
        state.battlefield_state,
        unit_instance_id=source_unit_id,
        pose=Pose.at(16.0, 10.0),
    )
    source_unit = _unit_by_id(state, source_unit_id)
    source_model = source_unit.own_models[0]
    updated_armies: list[ArmyDefinition] = []
    for army in state.army_definitions:
        updated_armies.append(
            replace(
                army,
                units=tuple(
                    replace(unit, own_models=(source_model,))
                    if unit.unit_instance_id == source_unit_id
                    else unit
                    for unit in army.units
                ),
            )
        )
    state.army_definitions = updated_armies
    assert state.battlefield_state is not None
    source_placement = state.battlefield_state.unit_placement_by_id(source_unit_id)
    state.battlefield_state = state.battlefield_state.with_unit_placement(
        replace(
            source_placement,
            model_placements=(
                next(
                    placement
                    for placement in source_placement.model_placements
                    if placement.model_instance_id == source_model.model_instance_id
                ),
            ),
        )
    )
    records = catalog_ability_records_from_catalog(catalog)
    player_b_index = build_player_ability_index(
        records,
        army=state.army_definitions[1],
        catalog=catalog,
    )
    decisions = DecisionController()
    reaction_queue = ReactionQueue()
    setup_event = decisions.event_log.append(
        "reinforcement_unit_arrived",
        {
            "game_id": state.game_id,
            "battle_round": state.battle_round,
            "active_player_id": "player-a",
            "phase": BattlePhase.MOVEMENT.value,
            "step": "move_units",
            "unit_instance_id": target_unit_id,
            "placement_kind": "strategic_reserves",
            "request_id": "phase17d-setup-request",
            "result_id": "phase17d-setup-result",
            "phase_body_status": "reinforcement_unit_arrived",
        },
    )

    status = request_catalog_setup_reactive_shoot_charge_if_available(
        state=state,
        decisions=decisions,
        reaction_queue=reaction_queue,
        ability_indexes_by_player_id={"player-b": player_b_index},
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(),
        army_catalog=catalog,
        runtime_modifier_registry=RuntimeModifierRegistry.empty(),
        charge_target_restriction_hooks=ChargeTargetRestrictionHookRegistry.empty(),
    )

    assert status is not None
    assert status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    assert status.decision_request is not None
    request = status.decision_request
    assert request.decision_type == SELECT_CATALOG_SETUP_REACTIVE_SHOOT_CHARGE_DECISION_TYPE
    assert request.actor_id == "player-b"
    assert {option.option_id for option in request.options} == {"decline", "shoot", "charge"}
    charge_payload = cast(dict[str, JsonValue], request.option_by_id("charge").payload)
    assert charge_payload["trigger_event_id"] == setup_event.event_id
    assert charge_payload["source_unit_instance_id"] == source_unit_id
    assert charge_payload["target_unit_instance_id"] == target_unit_id
    assert charge_payload["action"] == "charge"

    state.battlefield_state = _with_unit_pose(
        state.battlefield_state,
        unit_instance_id=target_unit_id,
        pose=Pose.at(40.0, 10.0),
    )
    invalid_status = invalid_catalog_setup_reactive_shoot_charge_status(
        state=state,
        request=request,
        result=DecisionResult.for_request(
            result_id="phase17d-setup-reactive-charge",
            request=request,
            selected_option_id="charge",
        ),
        decisions=decisions,
        ability_indexes_by_player_id={"player-b": player_b_index},
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(),
        army_catalog=catalog,
    )

    assert invalid_status is not None
    assert invalid_status.status_kind is LifecycleStatusKind.INVALID
    assert invalid_status.payload == {
        "invalid_reason": "setup_reactive_distance_drift",
        "field": "payload",
    }


def test_phase17d_catalog_setup_reactive_charge_suppresses_charge_bonus() -> None:
    state, catalog, player_b_index = _setup_reactive_single_model_state(
        target_pose=Pose.at(6.5, 10.0),
        source_pose=Pose.at(16.0, 10.0),
    )
    target_unit_id = "army-alpha:intercessor-unit-1"
    source_unit_id = "army-beta:intercessor-unit-2"
    decisions = DecisionController()
    reaction_queue = ReactionQueue()
    decisions.event_log.append(
        "reinforcement_unit_arrived",
        {
            "game_id": state.game_id,
            "battle_round": state.battle_round,
            "active_player_id": "player-a",
            "phase": BattlePhase.MOVEMENT.value,
            "step": "move_units",
            "unit_instance_id": target_unit_id,
            "placement_kind": "strategic_reserves",
            "request_id": "phase17d-setup-request",
            "result_id": "phase17d-setup-result",
            "phase_body_status": "reinforcement_unit_arrived",
        },
    )
    ruleset_descriptor = RulesetDescriptor.warhammer_40000_eleventh()

    status = request_catalog_setup_reactive_shoot_charge_if_available(
        state=state,
        decisions=decisions,
        reaction_queue=reaction_queue,
        ability_indexes_by_player_id={"player-b": player_b_index},
        ruleset_descriptor=ruleset_descriptor,
        army_catalog=catalog,
        runtime_modifier_registry=RuntimeModifierRegistry.empty(),
        charge_target_restriction_hooks=ChargeTargetRestrictionHookRegistry.empty(),
    )

    assert status is not None
    assert status.decision_request is not None
    action_request = status.decision_request
    assert {option.option_id for option in action_request.options} == {
        "decline",
        "shoot",
        "charge",
    }
    action_result = DecisionResult.for_request(
        result_id="phase17d-setup-reactive-charge-action",
        request=action_request,
        selected_option_id="charge",
    )
    _record_decision_result(decisions=decisions, result=action_result)

    charge_status = apply_catalog_setup_reactive_shoot_charge_result(
        state=state,
        decisions=decisions,
        result=action_result,
        ruleset_descriptor=ruleset_descriptor,
        army_catalog=catalog,
        ability_index=player_b_index,
        runtime_modifier_registry=RuntimeModifierRegistry.empty(),
        charge_target_restriction_hooks=ChargeTargetRestrictionHookRegistry.empty(),
    )

    assert charge_status is not None
    assert charge_status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    assert charge_status.decision_request is not None
    charge_request = charge_status.decision_request
    assert charge_request.decision_type == MOVEMENT_PROPOSAL_DECISION_TYPE
    proposal_request = MovementProposalRequest.from_decision_request_payload(charge_request.payload)
    assert proposal_request.proposal_kind is ProposalKind.CHARGE_MOVE
    assert proposal_request.actor_id == "player-b"
    proposal_context = cast(dict[str, JsonValue], proposal_request.context)
    assert proposal_context[CHARGE_MOVE_REQUIRED_TARGET_UNIT_INSTANCE_IDS_KEY] == [target_unit_id]
    assert proposal_context["charge_bonus_suppressed"] is True
    assert proposal_context["suppressed_charge_bonus"] == "fights_first"
    assert proposal_context["suppressed_charge_bonus_effect_kind"] == (
        FIGHTS_FIRST_CHARGE_EFFECT_KIND
    )

    move_proposal = ChargeMoveProposal(
        proposal_request_id=proposal_request.request_id,
        proposal_kind=proposal_request.proposal_kind,
        unit_instance_id=proposal_request.unit_instance_id,
        movement_phase_action="charge_move",
        movement_mode=MovementMode.CHARGE,
        charge_target_unit_instance_ids=(target_unit_id,),
        witness=_path_witness_for_unit_delta(
            state=state,
            unit_instance_id=source_unit_id,
            dx=-1.25,
        ),
    )
    move_result = _parameterized_result_for_request(
        request=charge_request,
        result_id="phase17d-setup-reactive-charge-move",
        payload=cast(JsonValue, move_proposal.to_payload()),
    )
    _record_decision_result(decisions=decisions, result=move_result)

    move_status = apply_catalog_setup_reactive_charge_move(
        state=state,
        request=charge_request,
        result=move_result,
        decisions=decisions,
        ruleset_descriptor=ruleset_descriptor,
    )

    completed_payloads = _event_payloads(decisions, "catalog_setup_reactive_charge_move_completed")
    assert move_status is None
    assert len(completed_payloads) == 1
    assert completed_payloads[0]["charge_bonus_suppressed"] is True
    assert "persisting_effect" not in completed_payloads[0]
    assert state.persisting_effects_for_unit(source_unit_id) == ()


def test_phase17d_catalog_setup_reactive_charge_submits_through_lifecycle() -> None:
    state, catalog, player_b_index = _setup_reactive_single_model_state(
        target_pose=Pose.at(6.5, 10.0),
        source_pose=Pose.at(16.0, 10.0),
    )
    lifecycle = _setup_reactive_lifecycle(state=state, catalog=catalog)
    target_unit_id = "army-alpha:intercessor-unit-1"
    source_unit_id = "army-beta:intercessor-unit-2"
    lifecycle.decision_controller.event_log.append(
        "reinforcement_unit_arrived",
        {
            "game_id": state.game_id,
            "battle_round": state.battle_round,
            "active_player_id": "player-a",
            "phase": BattlePhase.MOVEMENT.value,
            "step": "move_units",
            "unit_instance_id": target_unit_id,
            "placement_kind": "strategic_reserves",
            "request_id": "phase17d-lifecycle-setup-request",
            "result_id": "phase17d-lifecycle-setup-result",
            "phase_body_status": "reinforcement_unit_arrived",
        },
    )
    status = request_catalog_setup_reactive_shoot_charge_if_available(
        state=state,
        decisions=lifecycle.decision_controller,
        reaction_queue=lifecycle.reaction_queue,
        ability_indexes_by_player_id={"player-b": player_b_index},
        ruleset_descriptor=lifecycle.config.ruleset_descriptor,
        army_catalog=catalog,
        runtime_modifier_registry=RuntimeModifierRegistry.empty(),
        charge_target_restriction_hooks=ChargeTargetRestrictionHookRegistry.empty(),
    )

    assert status is not None
    assert status.decision_request is not None
    action_request = status.decision_request
    action_status = lifecycle.submit_decision(
        DecisionResult.for_request(
            result_id="phase17d-lifecycle-setup-reactive-charge-action",
            request=action_request,
            selected_option_id="charge",
        )
    )

    assert action_status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    charge_request = lifecycle.pending_decision_request()
    assert charge_request is not None
    assert charge_request.decision_type == MOVEMENT_PROPOSAL_DECISION_TYPE
    proposal_request = MovementProposalRequest.from_decision_request_payload(charge_request.payload)
    malformed_status = lifecycle.submit_decision(
        _parameterized_result_for_request(
            request=charge_request,
            result_id="phase17d-lifecycle-setup-reactive-malformed-charge-move",
            payload={},
        )
    )
    assert malformed_status.status_kind is LifecycleStatusKind.INVALID
    assert _json_object(malformed_status.payload)["phase_body_status"] == "invalid"
    assert lifecycle.pending_decision_request() == charge_request

    invalid_move_proposal = ChargeMoveProposal(
        proposal_request_id=proposal_request.request_id,
        proposal_kind=proposal_request.proposal_kind,
        unit_instance_id=proposal_request.unit_instance_id,
        movement_phase_action="charge_move",
        movement_mode=MovementMode.CHARGE,
        charge_target_unit_instance_ids=(target_unit_id,),
        witness=_path_witness_for_unit_delta(
            state=state,
            unit_instance_id=source_unit_id,
            dx=0.0,
        ),
    )
    invalid_move_status = lifecycle.submit_decision(
        _parameterized_result_for_request(
            request=charge_request,
            result_id="phase17d-lifecycle-setup-reactive-invalid-charge-move",
            payload=cast(JsonValue, invalid_move_proposal.to_payload()),
        )
    )

    assert invalid_move_status.status_kind is LifecycleStatusKind.INVALID
    assert _json_object(invalid_move_status.payload)["phase_body_status"] == (
        "catalog_setup_reactive_charge_move_invalid"
    )
    retry_request = lifecycle.pending_decision_request()
    assert retry_request is not None
    assert retry_request.decision_type == MOVEMENT_PROPOSAL_DECISION_TYPE
    retry_proposal_request = MovementProposalRequest.from_decision_request_payload(
        retry_request.payload
    )
    move_proposal = ChargeMoveProposal(
        proposal_request_id=retry_proposal_request.request_id,
        proposal_kind=retry_proposal_request.proposal_kind,
        unit_instance_id=retry_proposal_request.unit_instance_id,
        movement_phase_action="charge_move",
        movement_mode=MovementMode.CHARGE,
        charge_target_unit_instance_ids=(target_unit_id,),
        witness=_path_witness_for_unit_delta(
            state=state,
            unit_instance_id=source_unit_id,
            dx=-1.25,
        ),
    )
    move_status = lifecycle.submit_decision(
        _parameterized_result_for_request(
            request=retry_request,
            result_id="phase17d-lifecycle-setup-reactive-charge-move",
            payload=cast(JsonValue, move_proposal.to_payload()),
        )
    )

    completed_payloads = _event_payloads(
        lifecycle.decision_controller,
        "catalog_setup_reactive_charge_move_completed",
    )
    assert move_status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    assert len(completed_payloads) == 1
    assert completed_payloads[0]["charge_bonus_suppressed"] is True
    assert "persisting_effect" not in completed_payloads[0]
    assert state.persisting_effects_for_unit(source_unit_id) == ()


def test_phase17d_catalog_setup_reactive_decline_submits_through_lifecycle() -> None:
    state, catalog, player_b_index = _setup_reactive_single_model_state(
        target_pose=Pose.at(6.5, 10.0),
        source_pose=Pose.at(16.0, 10.0),
    )
    lifecycle = _setup_reactive_lifecycle(state=state, catalog=catalog)
    lifecycle_state = lifecycle.state
    assert lifecycle_state is not None
    action_request = _request_setup_reactive_lifecycle_action(
        lifecycle=lifecycle,
        state=lifecycle_state,
        catalog=catalog,
        player_b_index=player_b_index,
    )

    status = lifecycle.submit_decision(
        DecisionResult.for_request(
            result_id="phase17d-lifecycle-setup-reactive-decline",
            request=action_request,
            selected_option_id="decline",
        )
    )

    declined_payloads = _event_payloads(
        lifecycle.decision_controller,
        "catalog_setup_reactive_shoot_charge_declined",
    )
    assert status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    assert lifecycle.reaction_queue.frames == ()
    assert len(declined_payloads) == 1
    assert declined_payloads[0]["source_unit_instance_id"] == "army-beta:intercessor-unit-2"
    assert declined_payloads[0]["target_unit_instance_id"] == "army-alpha:intercessor-unit-1"


def test_phase17d_catalog_setup_reactive_shoot_submits_through_lifecycle() -> None:
    state, catalog, player_b_index = _setup_reactive_single_model_state(
        target_pose=Pose.at(6.5, 10.0),
        source_pose=Pose.at(16.0, 10.0),
    )
    lifecycle = _setup_reactive_lifecycle(state=state, catalog=catalog)
    lifecycle_state = lifecycle.state
    assert lifecycle_state is not None
    action_request = _request_setup_reactive_lifecycle_action(
        lifecycle=lifecycle,
        state=lifecycle_state,
        catalog=catalog,
        player_b_index=player_b_index,
    )

    status = lifecycle.submit_decision(
        DecisionResult.for_request(
            result_id="phase17d-lifecycle-setup-reactive-shoot",
            request=action_request,
            selected_option_id="shoot",
        )
    )

    shoot_payloads = _event_payloads(
        lifecycle.decision_controller,
        "catalog_setup_reactive_shoot_requested",
    )
    pending_request = lifecycle.pending_decision_request()
    assert status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    assert pending_request is not None
    assert lifecycle.reaction_queue.frames[-1].request_id == pending_request.request_id
    assert lifecycle_state.out_of_phase_shooting_state is not None
    assert lifecycle_state.out_of_phase_shooting_state.selected_unit_instance_id == (
        "army-beta:intercessor-unit-2"
    )
    assert lifecycle_state.out_of_phase_shooting_state.target_unit_ids == (
        "army-alpha:intercessor-unit-1",
    )
    assert len(shoot_payloads) == 1
    assert shoot_payloads[0]["action"] == "shoot"


@pytest.mark.parametrize(
    ("drift_case", "expected_message"),
    [
        ("wrong_stage", "Lifecycle reaction queue requires battle stage."),
        ("missing_phase", "Lifecycle reaction queue requires a current battle phase."),
        ("missing_pending", "Lifecycle reaction queue requires a pending decision."),
        ("wrong_decision_type", "Lifecycle reaction queue pending decision_type drift."),
        ("placement_drift", "Lifecycle reaction queue pending placement decision drift."),
        ("movement_drift", "Lifecycle reaction queue pending movement decision drift."),
        ("missing_request_id", "Lifecycle reaction queue frame requires request_id."),
        ("duplicate_request_id", "Lifecycle reaction queue request_ids must be unique."),
        ("game_id_drift", "Lifecycle reaction queue frame game_id drift."),
        ("phase_drift", "Lifecycle reaction queue frame phase drift."),
    ],
)
def test_phase17d_reaction_queue_consistency_rejects_drift(
    drift_case: str,
    expected_message: str,
) -> None:
    state = _battle_state()
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.MOVEMENT)
    decisions, reaction_queue, request = _reaction_queue_consistency_fixture(state=state)
    pending_request: DecisionRequest | None = request
    allowlist = {request.decision_type}

    if drift_case == "wrong_stage":
        state.stage = GameLifecycleStage.SETUP
    elif drift_case == "missing_phase":
        state.battle_phase_index = None
    elif drift_case == "missing_pending":
        pending_request = None
    elif drift_case == "wrong_decision_type":
        allowlist = {SELECT_CATALOG_SETUP_REACTIVE_SHOOT_CHARGE_DECISION_TYPE}
    elif drift_case == "placement_drift":
        pending_request = _non_reaction_placement_request(
            state=state,
            request_id=request.request_id,
        )
        allowlist = {PLACEMENT_PROPOSAL_DECISION_TYPE}
    elif drift_case == "movement_drift":
        pending_request = _non_reaction_movement_request(
            state=state,
            request_id=request.request_id,
        )
        allowlist = {MOVEMENT_PROPOSAL_DECISION_TYPE}
    elif drift_case == "missing_request_id":
        payload = reaction_queue.to_payload()
        payload["frames"][0]["request_id"] = None
        reaction_queue = ReactionQueue.from_payload(payload)
    elif drift_case == "duplicate_request_id":
        second = reaction_queue.emit_decision_request(
            state=state,
            decisions=decisions,
            reaction_window=_reaction_queue_window(
                state=state,
                window_id="phase17d-reaction-consistency-duplicate",
            ),
            parent_phase=BattlePhase.MOVEMENT,
            parent_step="end_movement_phase_reactions",
            resume_token="phase17d-reaction-consistency-duplicate-resume",
            actor_id="player-b",
            options=(
                DecisionOption(option_id="decline", label="Decline", payload={"action": "decline"}),
            ),
            payload={"source": "phase17d-reaction-consistency-duplicate"},
        )
        pending_request = second.decision_request
        payload = reaction_queue.to_payload()
        payload["frames"][1]["request_id"] = payload["frames"][0]["request_id"]
        reaction_queue = ReactionQueue.from_payload(payload)
    elif drift_case == "game_id_drift":
        state.game_id = "phase17d-other-game"
    elif drift_case == "phase_drift":
        state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.SHOOTING)
    else:
        raise AssertionError(f"Unhandled drift case: {drift_case}")

    with pytest.raises(GameLifecycleError, match=expected_message):
        validate_reaction_queue_consistency(
            state=state,
            reaction_queue=reaction_queue,
            pending_request=pending_request,
            reaction_frame_decision_types=allowlist,
        )


def test_phase17d_catalog_setup_reactive_records_unsupported_multi_model_source_once() -> None:
    state, catalog, player_b_index = _setup_reactive_single_model_state(
        target_pose=Pose.at(6.5, 10.0),
        source_pose=Pose.at(16.0, 10.0),
        keep_all_source_models=True,
    )
    decisions = DecisionController()
    reaction_queue = ReactionQueue()
    _append_setup_reactive_arrival_event(
        decisions=decisions,
        state=state,
        target_unit_id="army-alpha:intercessor-unit-1",
    )

    for _attempt in range(2):
        status = request_catalog_setup_reactive_shoot_charge_if_available(
            state=state,
            decisions=decisions,
            reaction_queue=reaction_queue,
            ability_indexes_by_player_id={"player-b": player_b_index},
            ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(),
            army_catalog=catalog,
            runtime_modifier_registry=RuntimeModifierRegistry.empty(),
            charge_target_restriction_hooks=ChargeTargetRestrictionHookRegistry.empty(),
        )
        assert status is None

    unsupported_payloads = _event_payloads(
        decisions,
        "catalog_setup_reactive_shoot_charge_unsupported",
    )
    assert len(unsupported_payloads) == 1
    assert unsupported_payloads[0]["source_unit_instance_id"] == ("army-beta:intercessor-unit-2")
    assert unsupported_payloads[0]["target_unit_instance_id"] == ("army-alpha:intercessor-unit-1")
    assert unsupported_payloads[0]["unsupported_reason"] == (
        "model_scoped_action_requires_single_placed_alive_model"
    )


@pytest.mark.parametrize(
    ("payload_field", "payload_value", "diagnostic_field"),
    [
        ("proposal_kind", ProposalKind.NORMAL_MOVE.value, "proposal_kind"),
        ("movement_mode", MovementMode.NORMAL.value, "movement_mode"),
        ("movement_phase_action", "normal_move", "movement_phase_action"),
        ("charge_target_unit_instance_ids", [1], "charge_target_unit_instance_ids"),
        ("witness", {"model_paths": []}, "witness"),
    ],
)
def test_phase17d_catalog_setup_reactive_charge_move_malformed_fields_are_typed(
    payload_field: str,
    payload_value: JsonValue,
    diagnostic_field: str,
) -> None:
    state, catalog, player_b_index = _setup_reactive_single_model_state(
        target_pose=Pose.at(6.5, 10.0),
        source_pose=Pose.at(16.0, 10.0),
    )
    decisions, charge_request = _setup_reactive_charge_move_request(
        state=state,
        catalog=catalog,
        player_b_index=player_b_index,
    )
    proposal_request = MovementProposalRequest.from_decision_request_payload(charge_request.payload)
    valid_payload = ChargeMoveProposal(
        proposal_request_id=proposal_request.request_id,
        proposal_kind=proposal_request.proposal_kind,
        unit_instance_id=proposal_request.unit_instance_id,
        movement_phase_action="charge_move",
        movement_mode=MovementMode.CHARGE,
        charge_target_unit_instance_ids=("army-alpha:intercessor-unit-1",),
        witness=_path_witness_for_unit_delta(
            state=state,
            unit_instance_id="army-beta:intercessor-unit-2",
            dx=-1.25,
        ),
    ).to_payload()
    malformed_payload = dict(valid_payload)
    malformed_payload[payload_field] = payload_value

    status = invalid_catalog_setup_reactive_charge_move_status(
        state=state,
        request=charge_request,
        result=_parameterized_result_for_request(
            request=charge_request,
            result_id=f"phase17d-malformed-setup-reactive-{payload_field}",
            payload=cast(JsonValue, malformed_payload),
        ),
        decisions=decisions,
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(),
        charge_target_restriction_hooks=ChargeTargetRestrictionHookRegistry.empty(),
    )

    assert status is not None
    assert status.status_kind is LifecycleStatusKind.INVALID
    validation = _json_object(_json_object(status.payload)["proposal_validation"])
    violations = cast(list[JsonValue], validation["violations"])
    violation = _json_object(violations[0])
    assert violation["field"] == diagnostic_field


def test_phase17d_catalog_setup_reactive_charge_move_no_move_records_decline() -> None:
    state = _battle_state()
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.MOVEMENT)
    decisions = DecisionController()
    request = MovementProposalRequest(
        request_id="phase17d-setup-reactive-charge-no-move",
        decision_type=MOVEMENT_PROPOSAL_DECISION_TYPE,
        actor_id="player-b",
        game_id=state.game_id,
        battle_round=state.battle_round,
        phase=BattlePhase.MOVEMENT.value,
        unit_instance_id="army-beta:intercessor-unit-2",
        proposal_kind=ProposalKind.CHARGE_MOVE,
        source_decision_request_id="phase17d-setup-reactive-action-request",
        source_decision_result_id="phase17d-setup-reactive-action-result",
        movement_phase_action="charge_move",
        context={
            "source_kind": CATALOG_SETUP_REACTIVE_SOURCE_KIND,
            "movement_mode": MovementMode.CHARGE.value,
            "maximum_distance_inches": 0,
            "reachable_target_unit_instance_ids": [],
            "reachable_target_distances_inches": {},
        },
    ).to_decision_request()
    proposal_request = MovementProposalRequest.from_decision_request_payload(request.payload)
    proposal = ChargeMoveProposal(
        proposal_request_id=proposal_request.request_id,
        proposal_kind=proposal_request.proposal_kind,
        unit_instance_id=proposal_request.unit_instance_id,
        movement_phase_action="charge_move",
        movement_mode=MovementMode.CHARGE,
        charge_target_unit_instance_ids=(),
        witness=None,
    )
    result = _parameterized_result_for_request(
        request=request,
        result_id="phase17d-setup-reactive-charge-no-move-result",
        payload=cast(JsonValue, proposal.to_payload()),
    )

    status = apply_catalog_setup_reactive_charge_move(
        state=state,
        request=request,
        result=result,
        decisions=decisions,
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(),
    )

    declined_payloads = _event_payloads(
        decisions,
        "catalog_setup_reactive_charge_move_declined",
    )
    assert status is None
    assert len(declined_payloads) == 1
    assert declined_payloads[0]["unit_instance_id"] == "army-beta:intercessor-unit-2"
    assert declined_payloads[0]["proposal_request_id"] == proposal_request.request_id


def test_phase17d_catalog_setup_reactive_charge_move_request_check_is_strict() -> None:
    ordinary_request = DecisionRequest(
        request_id="phase17d-ordinary-request",
        decision_type="ordinary_decision",
        actor_id="player-b",
        payload={"source": "phase17d"},
        options=(
            DecisionOption(option_id="decline", label="Decline", payload={"action": "decline"}),
        ),
    )

    assert is_catalog_setup_reactive_charge_move_request(ordinary_request) is False
    with pytest.raises(GameLifecycleError, match="requires request"):
        is_catalog_setup_reactive_charge_move_request(cast(DecisionRequest, object()))


def test_phase17d_catalog_setup_reactive_request_validates_dependencies() -> None:
    state, catalog, player_b_index = _setup_reactive_single_model_state(
        target_pose=Pose.at(6.5, 10.0),
        source_pose=Pose.at(16.0, 10.0),
    )
    decisions = DecisionController()
    reaction_queue = ReactionQueue()
    ruleset_descriptor = RulesetDescriptor.warhammer_40000_eleventh()

    assert (
        request_catalog_setup_reactive_shoot_charge_if_available(
            state=state,
            decisions=decisions,
            reaction_queue=None,
            ability_indexes_by_player_id={"player-b": player_b_index},
            ruleset_descriptor=ruleset_descriptor,
            army_catalog=catalog,
            runtime_modifier_registry=RuntimeModifierRegistry.empty(),
            charge_target_restriction_hooks=ChargeTargetRestrictionHookRegistry.empty(),
        )
        is None
    )
    with pytest.raises(GameLifecycleError, match="requires decisions"):
        request_catalog_setup_reactive_shoot_charge_if_available(
            state=state,
            decisions=cast(DecisionController, object()),
            reaction_queue=reaction_queue,
            ability_indexes_by_player_id={"player-b": player_b_index},
            ruleset_descriptor=ruleset_descriptor,
            army_catalog=catalog,
            runtime_modifier_registry=RuntimeModifierRegistry.empty(),
            charge_target_restriction_hooks=ChargeTargetRestrictionHookRegistry.empty(),
        )
    with pytest.raises(GameLifecycleError, match="ability indexes must be a mapping"):
        request_catalog_setup_reactive_shoot_charge_if_available(
            state=state,
            decisions=decisions,
            reaction_queue=reaction_queue,
            ability_indexes_by_player_id=cast(dict[str, AbilityCatalogIndex], []),
            ruleset_descriptor=ruleset_descriptor,
            army_catalog=catalog,
            runtime_modifier_registry=RuntimeModifierRegistry.empty(),
            charge_target_restriction_hooks=ChargeTargetRestrictionHookRegistry.empty(),
        )
    with pytest.raises(GameLifecycleError, match="ability index mapping contained drift"):
        request_catalog_setup_reactive_shoot_charge_if_available(
            state=state,
            decisions=decisions,
            reaction_queue=reaction_queue,
            ability_indexes_by_player_id={
                "player-b": cast(AbilityCatalogIndex, object()),
            },
            ruleset_descriptor=ruleset_descriptor,
            army_catalog=catalog,
            runtime_modifier_registry=RuntimeModifierRegistry.empty(),
            charge_target_restriction_hooks=ChargeTargetRestrictionHookRegistry.empty(),
        )
    with pytest.raises(GameLifecycleError, match="requires a RulesetDescriptor"):
        request_catalog_setup_reactive_shoot_charge_if_available(
            state=state,
            decisions=decisions,
            reaction_queue=reaction_queue,
            ability_indexes_by_player_id={"player-b": player_b_index},
            ruleset_descriptor=cast(RulesetDescriptor, object()),
            army_catalog=catalog,
            runtime_modifier_registry=RuntimeModifierRegistry.empty(),
            charge_target_restriction_hooks=ChargeTargetRestrictionHookRegistry.empty(),
        )
    with pytest.raises(GameLifecycleError, match="requires an ArmyCatalog"):
        request_catalog_setup_reactive_shoot_charge_if_available(
            state=state,
            decisions=decisions,
            reaction_queue=reaction_queue,
            ability_indexes_by_player_id={"player-b": player_b_index},
            ruleset_descriptor=ruleset_descriptor,
            army_catalog=cast(ArmyCatalog, object()),
            runtime_modifier_registry=RuntimeModifierRegistry.empty(),
            charge_target_restriction_hooks=ChargeTargetRestrictionHookRegistry.empty(),
        )
    with pytest.raises(GameLifecycleError, match="requires runtime modifiers"):
        request_catalog_setup_reactive_shoot_charge_if_available(
            state=state,
            decisions=decisions,
            reaction_queue=reaction_queue,
            ability_indexes_by_player_id={"player-b": player_b_index},
            ruleset_descriptor=ruleset_descriptor,
            army_catalog=catalog,
            runtime_modifier_registry=cast(RuntimeModifierRegistry, object()),
            charge_target_restriction_hooks=ChargeTargetRestrictionHookRegistry.empty(),
        )
    with pytest.raises(GameLifecycleError, match="requires charge target restrictions"):
        request_catalog_setup_reactive_shoot_charge_if_available(
            state=state,
            decisions=decisions,
            reaction_queue=reaction_queue,
            ability_indexes_by_player_id={"player-b": player_b_index},
            ruleset_descriptor=ruleset_descriptor,
            army_catalog=catalog,
            runtime_modifier_registry=RuntimeModifierRegistry.empty(),
            charge_target_restriction_hooks=cast(ChargeTargetRestrictionHookRegistry, object()),
        )
    state.active_player_id = None
    with pytest.raises(GameLifecycleError, match="requires an active player"):
        request_catalog_setup_reactive_shoot_charge_if_available(
            state=state,
            decisions=decisions,
            reaction_queue=reaction_queue,
            ability_indexes_by_player_id={"player-b": player_b_index},
            ruleset_descriptor=ruleset_descriptor,
            army_catalog=catalog,
            runtime_modifier_registry=RuntimeModifierRegistry.empty(),
            charge_target_restriction_hooks=ChargeTargetRestrictionHookRegistry.empty(),
        )


def test_phase17d_catalog_setup_reactive_finite_result_malformed_is_typed() -> None:
    state, catalog, player_b_index = _setup_reactive_single_model_state(
        target_pose=Pose.at(6.5, 10.0),
        source_pose=Pose.at(16.0, 10.0),
    )
    decisions = DecisionController()
    reaction_queue = ReactionQueue()
    _append_setup_reactive_arrival_event(
        decisions=decisions,
        state=state,
        target_unit_id="army-alpha:intercessor-unit-1",
    )
    status = request_catalog_setup_reactive_shoot_charge_if_available(
        state=state,
        decisions=decisions,
        reaction_queue=reaction_queue,
        ability_indexes_by_player_id={"player-b": player_b_index},
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(),
        army_catalog=catalog,
        runtime_modifier_registry=RuntimeModifierRegistry.empty(),
        charge_target_restriction_hooks=ChargeTargetRestrictionHookRegistry.empty(),
    )
    assert status is not None
    assert status.decision_request is not None

    invalid_status = invalid_catalog_setup_reactive_shoot_charge_status(
        state=state,
        request=status.decision_request,
        result=DecisionResult(
            result_id="phase17d-setup-reactive-invalid-action",
            request_id=status.decision_request.request_id,
            decision_type=status.decision_request.decision_type,
            actor_id=status.decision_request.actor_id,
            selected_option_id="not-an-option",
            payload=status.decision_request.option_by_id("decline").payload,
        ),
        decisions=decisions,
        ability_indexes_by_player_id={"player-b": player_b_index},
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(),
        army_catalog=catalog,
    )

    assert invalid_status is not None
    assert invalid_status.status_kind is LifecycleStatusKind.INVALID
    assert invalid_status.payload == {
        "invalid_reason": "invalid_catalog_setup_reactive_action_result",
        "detail": "DecisionRequest option_id is not in the finite action space.",
    }


def _parameterized_result_for_request(
    *,
    request: DecisionRequest,
    result_id: str,
    payload: JsonValue,
) -> DecisionResult:
    return ParameterizedSubmission(
        request_id=request.request_id,
        result_id=result_id,
        payload=payload,
    ).to_result(request)


def _record_decision_result(
    *,
    decisions: DecisionController,
    result: DecisionResult,
) -> None:
    decisions.submit_result(result)


def _request_setup_reactive_lifecycle_action(
    *,
    lifecycle: GameLifecycle,
    state: GameState,
    catalog: ArmyCatalog,
    player_b_index: AbilityCatalogIndex,
) -> DecisionRequest:
    target_unit_id = "army-alpha:intercessor-unit-1"
    _append_setup_reactive_arrival_event(
        decisions=lifecycle.decision_controller,
        state=state,
        target_unit_id=target_unit_id,
    )
    status = request_catalog_setup_reactive_shoot_charge_if_available(
        state=state,
        decisions=lifecycle.decision_controller,
        reaction_queue=lifecycle.reaction_queue,
        ability_indexes_by_player_id={"player-b": player_b_index},
        ruleset_descriptor=lifecycle.config.ruleset_descriptor,
        army_catalog=catalog,
        runtime_modifier_registry=RuntimeModifierRegistry.empty(),
        charge_target_restriction_hooks=ChargeTargetRestrictionHookRegistry.empty(),
    )
    assert status is not None
    assert status.decision_request is not None
    return status.decision_request


def _setup_reactive_charge_move_request(
    *,
    state: GameState,
    catalog: ArmyCatalog,
    player_b_index: AbilityCatalogIndex,
) -> tuple[DecisionController, DecisionRequest]:
    decisions = DecisionController()
    reaction_queue = ReactionQueue()
    _append_setup_reactive_arrival_event(
        decisions=decisions,
        state=state,
        target_unit_id="army-alpha:intercessor-unit-1",
    )
    status = request_catalog_setup_reactive_shoot_charge_if_available(
        state=state,
        decisions=decisions,
        reaction_queue=reaction_queue,
        ability_indexes_by_player_id={"player-b": player_b_index},
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(),
        army_catalog=catalog,
        runtime_modifier_registry=RuntimeModifierRegistry.empty(),
        charge_target_restriction_hooks=ChargeTargetRestrictionHookRegistry.empty(),
    )
    assert status is not None
    assert status.decision_request is not None
    action_result = DecisionResult.for_request(
        result_id="phase17d-setup-reactive-charge-action-for-request",
        request=status.decision_request,
        selected_option_id="charge",
    )
    _record_decision_result(decisions=decisions, result=action_result)
    charge_status = apply_catalog_setup_reactive_shoot_charge_result(
        state=state,
        decisions=decisions,
        result=action_result,
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(),
        army_catalog=catalog,
        ability_index=player_b_index,
        runtime_modifier_registry=RuntimeModifierRegistry.empty(),
        charge_target_restriction_hooks=ChargeTargetRestrictionHookRegistry.empty(),
    )
    assert charge_status is not None
    assert charge_status.decision_request is not None
    return decisions, charge_status.decision_request


def _append_setup_reactive_arrival_event(
    *,
    decisions: DecisionController,
    state: GameState,
    target_unit_id: str,
) -> None:
    decisions.event_log.append(
        "reinforcement_unit_arrived",
        {
            "game_id": state.game_id,
            "battle_round": state.battle_round,
            "active_player_id": "player-a",
            "phase": BattlePhase.MOVEMENT.value,
            "step": "move_units",
            "unit_instance_id": target_unit_id,
            "placement_kind": "strategic_reserves",
            "request_id": "phase17d-lifecycle-setup-request",
            "result_id": "phase17d-lifecycle-setup-result",
            "phase_body_status": "reinforcement_unit_arrived",
        },
    )


def _reaction_queue_consistency_fixture(
    *,
    state: GameState,
) -> tuple[DecisionController, ReactionQueue, DecisionRequest]:
    decisions = DecisionController()
    reaction_queue = ReactionQueue()
    triggered = reaction_queue.emit_decision_request(
        state=state,
        decisions=decisions,
        reaction_window=_reaction_queue_window(
            state=state,
            window_id="phase17d-reaction-consistency",
        ),
        parent_phase=BattlePhase.MOVEMENT,
        parent_step="end_movement_phase_reactions",
        resume_token="phase17d-reaction-consistency-resume",
        actor_id="player-b",
        options=(
            DecisionOption(option_id="decline", label="Decline", payload={"action": "decline"}),
        ),
        payload={"source": "phase17d-reaction-consistency"},
    )
    return decisions, reaction_queue, triggered.decision_request


def _reaction_queue_window(*, state: GameState, window_id: str) -> ReactionWindow:
    return ReactionWindow(
        timing_window=TimingWindow(
            window_id=window_id,
            descriptor=TimingWindowDescriptor(
                descriptor_id=f"{window_id}-descriptor",
                trigger_kind=TimingTriggerKind.END_PHASE,
                source_rule_id=f"{window_id}-source",
                phase=BattlePhase.MOVEMENT,
                source_step="end_movement_phase_reactions",
            ),
            game_id=state.game_id,
            battle_round=state.battle_round,
            active_player_id=state.active_player_id,
            phase=BattlePhase.MOVEMENT,
        ),
        eligible_player_ids=("player-b",),
    )


def _non_reaction_movement_request(*, state: GameState, request_id: str) -> DecisionRequest:
    return MovementProposalRequest(
        request_id=request_id,
        decision_type=MOVEMENT_PROPOSAL_DECISION_TYPE,
        actor_id="player-b",
        game_id=state.game_id,
        battle_round=state.battle_round,
        phase=BattlePhase.MOVEMENT.value,
        unit_instance_id="army-beta:intercessor-unit-2",
        proposal_kind=ProposalKind.NORMAL_MOVE,
        source_decision_request_id="phase17d-source-request",
        source_decision_result_id="phase17d-source-result",
        movement_phase_action="normal_move",
        context={"source_kind": "ordinary_movement"},
    ).to_decision_request()


def _non_reaction_placement_request(*, state: GameState, request_id: str) -> DecisionRequest:
    return MovementProposalRequest(
        request_id=request_id,
        decision_type=PLACEMENT_PROPOSAL_DECISION_TYPE,
        actor_id="player-b",
        game_id=state.game_id,
        battle_round=state.battle_round,
        phase=BattlePhase.MOVEMENT.value,
        unit_instance_id="army-beta:intercessor-unit-2",
        proposal_kind=ProposalKind.REINFORCEMENT,
        source_decision_request_id="phase17d-source-request",
        source_decision_result_id="phase17d-source-result",
        placement_kinds=(BattlefieldPlacementKind.STRATEGIC_RESERVES,),
        context={"source_kind": "ordinary_reinforcement"},
    ).to_decision_request()


def test_phase17d_generic_reroll_permission_executes() -> None:
    compiled = _compiled("After a hit roll, re-roll hit rolls.")

    result = execute_rule_ir(
        rule_ir=compiled.rule_ir,
        context=_execution_context(
            trigger_payload={"roll_type": "hit"},
            target_unit_instance_ids=("army-alpha:intercessor-unit-1",),
        ),
        registry=default_rule_execution_registry(),
    )
    effect = _json_object(result.effect_payloads[0]["effect"])

    assert result.status is RuleExecutionStatus.APPLIED
    assert effect["kind"] == "reroll_permission"
    assert effect["parameters"] == [{"key": "roll_type", "value": "hit"}]


def test_phase17d_desperate_escape_modifier_executes_when_target_is_battle_shocked() -> None:
    rule_ir = _desperate_escape_modifier_rule_ir()
    target_unit_id = "army-beta:enemy-unit-1"

    result = execute_rule_ir(
        rule_ir=rule_ir,
        context=_execution_context(
            target_unit_instance_ids=(target_unit_id,),
            trigger_payload={"target_unit_is_battle_shocked": True},
            phase=BattlePhaseKind.MOVEMENT,
        ),
        registry=default_rule_execution_registry(),
    )
    effect_payload = _json_object(result.effect_payloads[0])
    effect = _json_object(effect_payload["effect"])

    assert result.status is RuleExecutionStatus.APPLIED
    assert result.applied_clause_ids == (rule_ir.clauses[0].clause_id,)
    assert effect["kind"] == "modify_dice_roll"
    assert effect["parameters"] == [
        {"key": "delta", "value": -1},
        {"key": "roll_type", "value": "desperate_escape"},
    ]
    assert effect_payload["target_unit_instance_ids"] == [target_unit_id]


def test_phase17d_desperate_escape_modifier_is_invalid_when_target_not_battle_shocked() -> None:
    rule_ir = _desperate_escape_modifier_rule_ir()

    result = execute_rule_ir(
        rule_ir=rule_ir,
        context=_execution_context(
            target_unit_instance_ids=("army-beta:enemy-unit-1",),
            trigger_payload={"target_unit_statuses": []},
            phase=BattlePhaseKind.MOVEMENT,
        ),
        registry=default_rule_execution_registry(),
    )

    assert result.status is RuleExecutionStatus.INVALID
    assert result.reason == "condition_not_met:target_unit_has_status"
    assert result.effect_payloads == ()
    assert result.event_records == ()


def test_phase17d_desperate_escape_modifier_requires_target_status_evidence() -> None:
    rule_ir = _desperate_escape_modifier_rule_ir()

    result = execute_rule_ir(
        rule_ir=rule_ir,
        context=_execution_context(
            target_unit_instance_ids=("army-beta:enemy-unit-1",),
            trigger_payload={},
            phase=BattlePhaseKind.MOVEMENT,
        ),
        registry=default_rule_execution_registry(),
    )

    assert result.status is RuleExecutionStatus.INVALID
    assert result.reason == "missing_input:target_unit_status"
    assert result.effect_payloads == ()
    assert result.event_records == ()


def test_phase17d_desperate_escape_modifier_uses_state_backed_battle_shock_status() -> None:
    rule_ir = _desperate_escape_modifier_rule_ir()
    state = _battle_state_with_scenario()
    target_unit_id = "army-beta:intercessor-unit-2"
    state.battle_shocked_unit_ids.append(target_unit_id)
    state.battle_shocked_unit_ids.sort()

    result = execute_rule_ir(
        rule_ir=rule_ir,
        context=_execution_context(
            state=state,
            target_unit_instance_ids=(target_unit_id,),
            trigger_payload={},
            phase=BattlePhaseKind.MOVEMENT,
        ),
        registry=default_rule_execution_registry(),
    )

    assert result.status is RuleExecutionStatus.APPLIED
    assert result.applied_clause_ids == (rule_ir.clauses[0].clause_id,)
    assert result.effect_payloads[0]["target_unit_instance_ids"] == [target_unit_id]


def test_phase17d_champion_slayer_wound_reroll_only_applies_to_qualifying_melee_attack() -> None:
    state = _battle_state_with_scenario()
    unit = _unit_by_id(state, "army-alpha:intercessor-unit-1")
    source_model_id = unit.own_models[0].model_instance_id
    ability_index = _champion_slayer_ability_index(datasheet_id=unit.datasheet_id)

    qualifying = catalog_wound_roll_reroll_permission_for_attack(
        ability_index=ability_index,
        unit=unit,
        current_model_instance_ids=(source_model_id,),
        player_id="player-a",
        attack_kind="melee",
        target_keywords=("CHARACTER",),
    )
    ranged = catalog_wound_roll_reroll_permission_for_attack(
        ability_index=ability_index,
        unit=unit,
        current_model_instance_ids=(source_model_id,),
        player_id="player-a",
        attack_kind="ranged",
        target_keywords=("CHARACTER",),
    )
    non_keyword_target = catalog_wound_roll_reroll_permission_for_attack(
        ability_index=ability_index,
        unit=unit,
        current_model_instance_ids=(source_model_id,),
        player_id="player-a",
        attack_kind="melee",
        target_keywords=("INFANTRY",),
    )

    assert qualifying is not None
    assert qualifying.eligible_roll_type == "attack_sequence.wound"
    assert qualifying.timing_window == "attack_sequence.wound"
    assert ranged is None
    assert non_keyword_target is None


def test_phase17d_champion_slayer_clause_records_share_source_identity_and_split_timings() -> None:
    ability_index = _champion_slayer_ability_index(datasheet_id="core-intercessor-like-infantry")
    wound_records = ability_index.records_for(TimingTriggerKind.AFTER_DICE_ROLL)
    destroy_records = ability_index.records_for(TimingTriggerKind.AFTER_UNIT_DESTROYED)

    assert len(wound_records) == 1
    assert len(destroy_records) == 1
    assert wound_records[0].definition.ability_id == destroy_records[0].definition.ability_id
    assert wound_records[0].definition.source_id == destroy_records[0].definition.source_id
    wound_payload = cast(dict[str, JsonValue], wound_records[0].definition.replay_payload)
    destroy_payload = cast(dict[str, JsonValue], destroy_records[0].definition.replay_payload)
    assert cast(str, wound_payload["runtime_clause_id"]).endswith(":clause:001")
    assert cast(str, destroy_payload["runtime_clause_id"]).endswith(":clause:002")


def test_phase17d_catalog_builder_emits_clause_records_for_compound_ability() -> None:
    catalog = _catalog_with_champion_slayer_ability()

    records = tuple(
        record
        for record in catalog_ability_records_from_catalog(catalog)
        if record.definition.ability_id == "champion-slayer"
    )
    replay_payloads = tuple(
        cast(dict[str, JsonValue], record.definition.replay_payload) for record in records
    )

    assert len(records) == 2
    assert tuple(record.record_id for record in records) == (
        f"{catalog.source_package_id}:catalog-ability:core-intercessor-like-infantry:"
        "champion-slayer:phase17d:test:champion-slayer:clause:001",
        f"{catalog.source_package_id}:catalog-ability:core-intercessor-like-infantry:"
        "champion-slayer:phase17d:test:champion-slayer:clause:002",
    )
    assert {record.definition.source_id for record in records} == {"phase17d:test:champion-slayer"}
    assert tuple(record.definition.timing.trigger_kind for record in records) == (
        TimingTriggerKind.AFTER_DICE_ROLL,
        TimingTriggerKind.AFTER_UNIT_DESTROYED,
    )
    assert tuple(cast(str, payload["runtime_clause_id"]) for payload in replay_payloads) == (
        "phase17d:test:champion-slayer:clause:001",
        "phase17d:test:champion-slayer:clause:002",
    )


@pytest.mark.parametrize(
    ("raw_text", "expected_trigger_kind"),
    [
        (
            (
                "At the end of your opponent's turn, if this unit is not within Engagement "
                "Range of one or more enemy units, you can remove it from the battlefield "
                "and place it into Strategic Reserves."
            ),
            TimingTriggerKind.END_TURN,
        ),
        (
            "This unit is eligible to declare a charge in a turn in  which it Advanced.",
            TimingTriggerKind.PASSIVE_QUERY,
        ),
        (
            "Daemonic Shadow (Aura): While a friendly Khorne Legiones Daemonica unit is "
            'within 6" of this model, that unit is within your army\u2019s Shadow of Chaos.',
            TimingTriggerKind.PASSIVE_QUERY,
        ),
        (
            "The bearer has a Toughness characteristic of 5.",
            TimingTriggerKind.PASSIVE_QUERY,
        ),
        (
            "The bearer has the Feel No Pain 3+ ability against Psychic Attacks.",
            TimingTriggerKind.PASSIVE_QUERY,
        ),
        (
            "Weapons equipped by models in that unit have the [LANCE] ability.",
            TimingTriggerKind.PASSIVE_QUERY,
        ),
        (ONCE_PER_BATTLE_FIGHT_BOOST_TEXT, TimingTriggerKind.START_PHASE),
        ("After a hit roll, re-roll hit rolls.", TimingTriggerKind.AFTER_DICE_ROLL),
        ("Gain 1CP.", TimingTriggerKind.ANY_PHASE),
    ],
)
def test_phase17d_catalog_builder_classifies_single_clause_generic_timing(
    raw_text: str,
    expected_trigger_kind: TimingTriggerKind,
) -> None:
    descriptor = _generic_catalog_descriptor(raw_text)

    records = catalog_ability_records_from_catalog(_catalog_with_descriptor(descriptor))

    assert len(records) == 1
    assert records[0].definition.timing.trigger_kind is expected_trigger_kind
    assert (
        _json_object(records[0].definition.replay_payload)["rule_ir"] == descriptor.rule_ir_payload
    )
    if raw_text == ONCE_PER_BATTLE_FIGHT_BOOST_TEXT:
        assert records[0].definition.timing.phase is BattlePhaseKind.FIGHT


def test_phase17d_once_per_battle_activation_submits_through_local_session_and_replays() -> None:
    catalog = _catalog_with_descriptor(
        _generic_catalog_descriptor(
            ONCE_PER_BATTLE_FIGHT_BOOST_TEXT,
            ability_id="once-per-battle-fight-boost",
        )
    )
    config = _setup_reactive_config(catalog)
    armies = tuple(
        muster_army(catalog=catalog, request=request) for request in config.army_muster_requests
    )
    state = _battle_state()
    for army in armies:
        state.record_army_definition(army)
    state.battlefield_state = create_deterministic_battlefield_scenario(
        battlefield_id="phase17d-once-per-battle",
        armies=armies,
    ).battlefield_state
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.FIGHT)
    session = LocalGameSession(lifecycle=_setup_reactive_lifecycle(state=state, catalog=catalog))

    status = session.advance_until_decision_or_terminal()
    request = status.decision_request
    assert status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    assert request is not None
    assert request.decision_type == SELECT_FACTION_RULE_FIGHT_PHASE_START_OPTION_DECISION_TYPE
    use_option = next(
        option for option in request.options if _json_object(option.payload)["activate"] is True
    )
    malformed = replace(
        DecisionResult.for_request(
            result_id="phase17d:once-per-battle:malformed",
            request=request,
            selected_option_id=use_option.option_id,
        ),
        payload={},
    )
    malformed_status = session.lifecycle.submit_decision(malformed)
    assert malformed_status.status_kind is LifecycleStatusKind.INVALID
    assert session.lifecycle.pending_decision_request() == request
    assert session.lifecycle.state is not None
    assert not session.lifecycle.state.persisting_effects

    submitted = session.submit_option(
        request_id=request.request_id,
        option_id=use_option.option_id,
        result_id="phase17d:once-per-battle:local-session",
    )

    assert submitted.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    second_request = submitted.decision_request
    assert second_request is not None
    second_use_option = next(
        option
        for option in second_request.options
        if _json_object(option.payload)["activate"] is True
    )
    second_submitted = session.submit_option(
        request_id=second_request.request_id,
        option_id=second_use_option.option_id,
        result_id="phase17d:once-per-battle:local-session:second-model",
    )
    assert second_submitted.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    assert session.lifecycle.state is not None
    assert len(session.lifecycle.state.persisting_effects) == 4
    assert len({effect.effect_id for effect in session.lifecycle.state.persisting_effects}) == 4
    player_a_events = session.events_since(EventStreamCursor(), viewer_player_id="player-a")
    player_b_events = session.events_since(EventStreamCursor(), viewer_player_id="player-b")
    player_a_activations = [
        event
        for event in player_a_events["events"]
        if event["event_type"] == "catalog_once_per_battle_ability_activated"
    ]
    player_b_activations = [
        event
        for event in player_b_events["events"]
        if event["event_type"] == "catalog_once_per_battle_ability_activated"
    ]
    assert player_a_activations == player_b_activations
    assert len(player_a_activations) == 2
    replay = ReplayRunner.from_payload(
        session.replay_artifact(artifact_id="replay:once-per-battle:fight-boost")
    ).run()
    assert replay.status is ReplayRunStatus.REPRODUCED


def test_phase17d_catalog_builder_rejects_malformed_generic_ir_descriptors() -> None:
    missing_rule_ir = _generic_catalog_descriptor("Gain 1CP.", ability_id="missing-rule-ir")
    object.__setattr__(missing_rule_ir, "rule_ir_payload", None)
    invalid_rule_ir = _generic_catalog_descriptor("Gain 1CP.", ability_id="invalid-rule-ir")
    invalid_payload = dict(cast(dict[str, JsonValue], invalid_rule_ir.rule_ir_payload))
    invalid_payload["ir_hash"] = "stale"
    object.__setattr__(invalid_rule_ir, "rule_ir_payload", invalid_payload)
    unsupported_source = _generic_catalog_descriptor(
        "Gain 1CP.",
        ability_id="unsupported-source",
        source_kind=CatalogAbilitySourceKind.CORE,
    )
    missing_wargear_source = _generic_catalog_descriptor(
        "Gain 1CP.",
        ability_id="missing-wargear-source",
        source_kind=CatalogAbilitySourceKind.WARGEAR,
        source_wargear_id="core-bolt-rifle",
    )
    object.__setattr__(missing_wargear_source, "source_wargear_id", None)

    with pytest.raises(GameLifecycleError, match="missing rule_ir"):
        catalog_ability_records_from_catalog(_catalog_with_descriptor(missing_rule_ir))
    with pytest.raises(GameLifecycleError, match="invalid IR"):
        catalog_ability_records_from_catalog(_catalog_with_descriptor(invalid_rule_ir))
    with pytest.raises(GameLifecycleError, match="source kind is unsupported"):
        catalog_ability_records_from_catalog(_catalog_with_descriptor(unsupported_source))
    with pytest.raises(GameLifecycleError, match="missing source_wargear_id"):
        catalog_ability_records_from_catalog(_catalog_with_descriptor(missing_wargear_source))


def test_phase17d_player_ability_index_filters_selected_source_records() -> None:
    catalog = ArmyCatalog.phase9a_canonical_content_pack()
    army = _mustered_armies()[0]
    army = replace(
        army,
        detachment_selection=replace(
            army.detachment_selection,
            enhancement_ids=("selected-enhancement",),
        ),
    )
    records = (
        _ability_record("core", AbilitySourceKind.CORE),
        _ability_record(
            "keyword-infantry",
            AbilitySourceKind.KEYWORD,
            keyword_gate=KeywordGate(required_keywords=("Infantry",)),
        ),
        _ability_record(
            "keyword-vehicle",
            AbilitySourceKind.KEYWORD,
            keyword_gate=KeywordGate(required_keywords=("Vehicle",)),
        ),
        _ability_record(
            "faction-match",
            AbilitySourceKind.FACTION,
            faction_id="core-marine-force",
        ),
        _ability_record("faction-miss", AbilitySourceKind.FACTION, faction_id="other-faction"),
        _ability_record(
            "detachment-match",
            AbilitySourceKind.DETACHMENT,
            detachment_id="core-combined-arms",
        ),
        _ability_record(
            "detachment-miss",
            AbilitySourceKind.DETACHMENT,
            detachment_id="other-detachment",
        ),
        _ability_record(
            "enhancement-match",
            AbilitySourceKind.ENHANCEMENT,
            detachment_id="core-combined-arms",
            ability_id="selected-enhancement",
        ),
        _ability_record(
            "enhancement-miss",
            AbilitySourceKind.ENHANCEMENT,
            detachment_id="core-combined-arms",
            ability_id="unselected-enhancement",
        ),
        _ability_record(
            "datasheet-match",
            AbilitySourceKind.DATASHEET,
            datasheet_id="core-intercessor-like-infantry",
        ),
        _ability_record(
            "datasheet-miss",
            AbilitySourceKind.DATASHEET,
            datasheet_id="other-datasheet",
        ),
        _ability_record("wargear-match", AbilitySourceKind.WARGEAR, wargear_id="core-bolt-rifle"),
        _ability_record("wargear-miss", AbilitySourceKind.WARGEAR, wargear_id="other-wargear"),
        _ability_record(
            "weapon-profile-match",
            AbilitySourceKind.WEAPON,
            weapon_profile_id="core-bolt-rifle:standard",
        ),
        _ability_record(
            "weapon-profile-miss",
            AbilitySourceKind.WEAPON,
            weapon_profile_id="other-profile",
        ),
        _ability_record(
            "weapon-keyword-match",
            AbilitySourceKind.WEAPON,
            keyword_gate=KeywordGate(required_keywords=("Assault",)),
        ),
        _ability_record(
            "weapon-keyword-miss",
            AbilitySourceKind.WEAPON,
            keyword_gate=KeywordGate(required_keywords=("Lance",)),
        ),
    )

    with_catalog = {
        record.record_id
        for record in build_player_ability_index(records, army=army, catalog=catalog).all_records()
    }
    without_catalog = {
        record.record_id for record in build_player_ability_index(records, army=army).all_records()
    }

    assert with_catalog == {
        "core",
        "datasheet-match",
        "detachment-match",
        "enhancement-match",
        "faction-match",
        "keyword-infantry",
        "wargear-match",
        "weapon-keyword-match",
        "weapon-profile-match",
    }
    assert without_catalog == with_catalog - {
        "weapon-keyword-match",
        "weapon-profile-match",
    }
    with pytest.raises(GameLifecycleError, match="requires an ArmyDefinition"):
        build_player_ability_index((), army=cast(ArmyDefinition, object()))
    with pytest.raises(GameLifecycleError, match="catalog must be an ArmyCatalog"):
        build_player_ability_index((), army=army, catalog=cast(ArmyCatalog, object()))


def test_phase17d_champion_slayer_heal_only_applies_after_enemy_character_or_monster() -> None:
    state = _battle_state_with_scenario()
    unit = _unit_by_id(state, "army-alpha:intercessor-unit-1")
    model = unit.own_models[0]
    ability_index = _champion_slayer_ability_index(datasheet_id=unit.datasheet_id)
    _set_model_wounds(state, model_instance_id=model.model_instance_id, wounds_remaining=1)
    wounded_unit = _unit_by_id(state, unit.unit_instance_id)

    resolved = catalog_restore_lost_wounds_after_destroying_unit(
        state=state,
        decisions=DecisionController(),
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(),
        ability_index=ability_index,
        unit=wounded_unit,
        current_model_instance_ids=(model.model_instance_id,),
        player_id="player-a",
        destroyed_player_id="player-b",
        destroyed_unit_keywords=("MONSTER",),
        healing_amount=3,
        source_event_id="event:enemy-monster-destroyed",
    )

    assert resolved is not None
    effect, request = resolved
    assert request is None
    assert effect.amount == 1
    assert len(effect.resolved_steps) == 1
    assert effect.source_context == {
        "catalog_record_id": (
            "phase17d:test:catalog-ability:core-intercessor-like-infantry:"
            "champion-slayer:phase17d:test:champion-slayer:clause:002"
        ),
        "clause_id": "phase17d:test:champion-slayer:clause:002",
        "destroyed_unit_keywords": ["MONSTER"],
        "effect_kind": "restore_lost_wounds",
        "source_model_instance_id": model.model_instance_id,
        "source_event_id": "event:enemy-monster-destroyed",
    }
    healed_unit = _unit_by_id(state, unit.unit_instance_id)
    assert healed_unit.own_models[0].wounds_remaining == model.starting_wounds


def test_phase17d_champion_slayer_heal_does_not_revive_after_source_model_is_full() -> None:
    state = _battle_state_with_scenario()
    unit = _unit_by_id(state, "army-alpha:intercessor-unit-1")
    source_model = unit.own_models[0]
    destroyed_model = unit.own_models[1]
    ability_index = _champion_slayer_ability_index(datasheet_id=unit.datasheet_id)
    _set_model_wounds(
        state,
        model_instance_id=source_model.model_instance_id,
        wounds_remaining=source_model.starting_wounds - 1,
    )
    _destroy_model(state, model_instance_id=destroyed_model.model_instance_id)
    wounded_unit = _unit_by_id(state, unit.unit_instance_id)

    resolved = catalog_restore_lost_wounds_after_destroying_unit(
        state=state,
        decisions=DecisionController(),
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(),
        ability_index=ability_index,
        unit=wounded_unit,
        current_model_instance_ids=(source_model.model_instance_id,),
        player_id="player-a",
        destroyed_player_id="player-b",
        destroyed_unit_keywords=("CHARACTER",),
        healing_amount=3,
        source_event_id="event:enemy-character-destroyed",
    )

    assert resolved is not None
    effect, request = resolved
    assert request is None
    assert effect.amount == 1
    assert len(effect.resolved_steps) == 1
    resolved_unit = _unit_by_id(state, unit.unit_instance_id)
    assert resolved_unit.own_models[0].wounds_remaining == source_model.starting_wounds
    assert resolved_unit.own_models[1].wounds_remaining == 0
    assert state.battlefield_state is not None
    assert destroyed_model.model_instance_id in state.battlefield_state.removed_model_ids


def test_phase17d_champion_slayer_heal_ignores_other_wounded_model_when_source_full() -> None:
    state = _battle_state_with_scenario()
    unit = _unit_by_id(state, "army-alpha:intercessor-unit-1")
    source_model = unit.own_models[0]
    other_model = unit.own_models[1]
    ability_index = _champion_slayer_ability_index(datasheet_id=unit.datasheet_id)
    _set_model_wounds(
        state,
        model_instance_id=other_model.model_instance_id,
        wounds_remaining=other_model.starting_wounds - 1,
    )
    wounded_unit = _unit_by_id(state, unit.unit_instance_id)

    resolved = catalog_restore_lost_wounds_after_destroying_unit(
        state=state,
        decisions=DecisionController(),
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(),
        ability_index=ability_index,
        unit=wounded_unit,
        current_model_instance_ids=(source_model.model_instance_id,),
        player_id="player-a",
        destroyed_player_id="player-b",
        destroyed_unit_keywords=("MONSTER",),
        healing_amount=3,
        source_event_id="event:enemy-monster-destroyed",
    )

    resolved_unit = _unit_by_id(state, unit.unit_instance_id)
    assert resolved is None
    assert resolved_unit.own_models[0].wounds_remaining == source_model.starting_wounds
    assert resolved_unit.own_models[1].wounds_remaining == other_model.starting_wounds - 1


def test_phase17d_champion_slayer_heal_fails_closed_for_multiple_wounded_models() -> None:
    state = _battle_state_with_scenario()
    unit = _unit_by_id(state, "army-alpha:intercessor-unit-1")
    source_model = unit.own_models[0]
    other_model = unit.own_models[1]
    ability_index = _champion_slayer_ability_index(datasheet_id=unit.datasheet_id)
    _set_model_wounds(
        state,
        model_instance_id=source_model.model_instance_id,
        wounds_remaining=source_model.starting_wounds - 1,
    )
    _set_model_wounds(
        state,
        model_instance_id=other_model.model_instance_id,
        wounds_remaining=other_model.starting_wounds - 1,
    )
    wounded_unit = _unit_by_id(state, unit.unit_instance_id)

    with pytest.raises(GameLifecycleError, match="multiple wounded models"):
        catalog_restore_lost_wounds_after_destroying_unit(
            state=state,
            decisions=DecisionController(),
            ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(),
            ability_index=ability_index,
            unit=wounded_unit,
            current_model_instance_ids=(source_model.model_instance_id,),
            player_id="player-a",
            destroyed_player_id="player-b",
            destroyed_unit_keywords=("MONSTER",),
            healing_amount=3,
            source_event_id="event:enemy-monster-destroyed",
        )


def test_phase17d_champion_slayer_restore_clause_executes_to_generic_payload() -> None:
    state = _battle_state_with_scenario()
    unit = _unit_by_id(state, "army-alpha:intercessor-unit-1")
    ability_index = _champion_slayer_ability_index(datasheet_id=unit.datasheet_id)

    results = execute_abilities_from_index(
        registry=default_ability_handler_registry(),
        index=ability_index,
        context=AbilityExecutionContext(
            game_id="phase17d-game",
            player_id="player-a",
            battle_round=1,
            phase=None,
            active_player_id="player-a",
            trigger_kind=TimingTriggerKind.AFTER_UNIT_DESTROYED,
            source_unit_instance_id=unit.unit_instance_id,
            source_model_instance_id=unit.own_models[0].model_instance_id,
            trigger_payload={"destroyed_unit_keywords": ["MONSTER"]},
            state=state,
        ),
    )

    assert len(results) == 1
    assert results[0].status is AbilityResolutionStatus.APPLIED
    replay_payload = cast(dict[str, JsonValue], results[0].replay_payload)
    execution_payload = cast(dict[str, JsonValue], replay_payload["rule_execution"])
    effect_payloads = cast(list[JsonValue], execution_payload["effect_payloads"])
    first_effect_payload = cast(dict[str, JsonValue], effect_payloads[0])
    effect = cast(dict[str, JsonValue], first_effect_payload["effect"])
    assert effect["kind"] == "restore_lost_wounds"


def test_phase17d_champion_slayer_heal_ignores_nonqualifying_destroyed_units() -> None:
    state = _battle_state_with_scenario()
    unit = _unit_by_id(state, "army-alpha:intercessor-unit-1")
    model = unit.own_models[0]
    ability_index = _champion_slayer_ability_index(datasheet_id=unit.datasheet_id)
    _set_model_wounds(state, model_instance_id=model.model_instance_id, wounds_remaining=1)
    wounded_unit = _unit_by_id(state, unit.unit_instance_id)

    non_keyword = catalog_restore_lost_wounds_after_destroying_unit(
        state=state,
        decisions=DecisionController(),
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(),
        ability_index=ability_index,
        unit=wounded_unit,
        current_model_instance_ids=(model.model_instance_id,),
        player_id="player-a",
        destroyed_player_id="player-b",
        destroyed_unit_keywords=("INFANTRY",),
        healing_amount=3,
        source_event_id="event:enemy-infantry-destroyed",
    )
    friendly_destroyed = catalog_restore_lost_wounds_after_destroying_unit(
        state=state,
        decisions=DecisionController(),
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(),
        ability_index=ability_index,
        unit=wounded_unit,
        current_model_instance_ids=(model.model_instance_id,),
        player_id="player-a",
        destroyed_player_id="player-a",
        destroyed_unit_keywords=("CHARACTER",),
        healing_amount=3,
        source_event_id="event:friendly-character-destroyed",
    )

    assert non_keyword is None
    assert friendly_destroyed is None
    assert _unit_by_id(state, unit.unit_instance_id).own_models[0].wounds_remaining == 1


def test_phase17d_generic_vp_scoring_rule_mutates_victory_point_ledger() -> None:
    state = _battle_state()
    event_log = EventLog()
    compiled = _compiled("When this unit is destroyed, score 5VP.")

    result = execute_rule_ir(
        rule_ir=compiled.rule_ir,
        context=_execution_context(state=state, event_log=event_log),
        registry=default_rule_execution_registry(),
    )

    assert result.status is RuleExecutionStatus.APPLIED
    assert state.victory_point_total("player-a") == 5
    assert result.victory_point_transactions[0]["amount"] == 5
    assert result.victory_point_transactions[0]["source_id"] == compiled.rule_ir.source_id
    assert event_log.records[-1].event_type == "rule_execution_victory_points_awarded"


def test_phase17d_generic_cp_rule_mutates_command_point_ledger_and_reports_cap() -> None:
    state = _battle_state()
    event_log = EventLog()
    compiled = _compiled("Gain 1CP and score 3VP.")

    first = execute_rule_ir(
        rule_ir=compiled.rule_ir,
        context=_execution_context(state=state, event_log=event_log),
        registry=default_rule_execution_registry(),
    )
    event_count_after_first = len(event_log.records)
    capped = execute_rule_ir(
        rule_ir=compiled.rule_ir,
        context=_execution_context(state=state, event_log=event_log),
        registry=default_rule_execution_registry(),
    )

    assert first.status is RuleExecutionStatus.APPLIED
    assert state.command_point_total("player-a") == 1
    assert state.victory_point_total("player-a") == 3
    assert first.command_point_transactions[0]["status"] == "applied"
    assert first.command_point_transactions[0]["applied_amount"] == 1
    assert capped.status is RuleExecutionStatus.INVALID
    assert capped.reason == "command_point_gain_capped"
    assert state.command_point_total("player-a") == 1
    assert state.victory_point_total("player-a") == 3
    assert len(event_log.records) == event_count_after_first


def test_phase17d_oversized_generic_cp_gain_applies_only_remaining_round_capacity() -> None:
    state = _battle_state()
    event_log = EventLog()
    compiled = _compiled("Gain 3CP.")

    result = execute_rule_ir(
        rule_ir=compiled.rule_ir,
        context=_execution_context(state=state, event_log=event_log),
        registry=default_rule_execution_registry(),
    )

    assert result.status is RuleExecutionStatus.APPLIED
    assert state.command_point_total("player-a") == 1
    transaction = result.command_point_transactions[0]
    assert transaction["status"] == "capped"
    assert transaction["requested_amount"] == 3
    assert transaction["applied_amount"] == 1
    assert transaction["capped_reason"] == "non_command_cp_gain_cap_reached"


def test_phase17d_later_invalid_effect_does_not_leave_prior_mutation() -> None:
    state = _battle_state()
    event_log = EventLog()
    compiled = _compiled("Gain 1CP and score 3VP.")

    result = execute_rule_ir(
        rule_ir=compiled.rule_ir,
        context=_execution_context(state=state, event_log=event_log, phase=None),
        registry=default_rule_execution_registry(),
    )

    assert result.status is RuleExecutionStatus.INVALID
    assert result.reason == "missing_phase"
    assert state.command_point_total("player-a") == 0
    assert state.victory_point_total("player-a") == 0
    assert event_log.records == ()


def test_phase17d_generic_cp_spend_rule_uses_command_point_ledger() -> None:
    spend_rule_ir = _command_point_spend_rule_ir()
    insufficient_state = _battle_state()
    funded_state = _battle_state()
    funded_state.gain_command_points(
        player_id="player-a",
        amount=1,
        source_id="phase17d:seed-cp",
        source_kind=CommandPointSourceKind.OTHER,
        cap_exempt=True,
    )

    insufficient = execute_rule_ir(
        rule_ir=spend_rule_ir,
        context=_execution_context(state=insufficient_state),
        registry=default_rule_execution_registry(),
    )
    applied = execute_rule_ir(
        rule_ir=spend_rule_ir,
        context=_execution_context(state=funded_state),
        registry=default_rule_execution_registry(),
    )

    assert insufficient.status is RuleExecutionStatus.INVALID
    assert insufficient.reason == "insufficient_command_points"
    assert insufficient_state.command_point_total("player-a") == 0
    assert applied.status is RuleExecutionStatus.APPLIED
    assert funded_state.command_point_total("player-a") == 0
    assert applied.command_point_transactions[0]["status"] == "applied"
    assert applied.command_point_transactions[0]["applied_amount"] == 1


def test_phase17d_command_point_mutation_helper_is_strict_and_simulates_refunds() -> None:
    state = _battle_state()
    effect = _compiled("Gain 1CP.").rule_ir.clauses[0].effects[0]

    assert command_point_operation_and_delta(effect) == ("gain", 1)
    with pytest.raises(GameLifecycleError, match="exactly one payload or reason"):
        CommandPointRuleMutationResult()
    with pytest.raises(GameLifecycleError, match="requires RuleEffectSpec"):
        command_point_operation_and_delta(cast(Any, object()))
    with pytest.raises(GameLifecycleError, match="operation must be a string"):
        command_point_operation_and_delta(replace(effect, parameters=(RuleParameter("delta", 1),)))
    with pytest.raises(GameLifecycleError, match="delta must be an integer"):
        command_point_operation_and_delta(
            replace(
                effect,
                parameters=(
                    RuleParameter("delta", "one"),
                    RuleParameter("operation", "gain"),
                ),
            )
        )

    invalid = apply_command_point_rule_mutation(
        state=state,
        player_id="player-a",
        source_id="phase17d:test:invalid-cp",
        operation="gain",
        delta=-1,
    )
    first_refund = apply_command_point_rule_mutation(
        state=state,
        player_id="player-a",
        source_id="phase17d:test:refund-one",
        operation="refund",
        delta=1,
    )
    capped_refund = apply_command_point_rule_mutation(
        state=state,
        player_id="player-a",
        source_id="phase17d:test:refund-two",
        operation="refund",
        delta=1,
    )

    assert invalid.reason == "invalid_command_point_gain_delta"
    assert first_refund.transaction_payload is not None
    assert first_refund.transaction_payload["source_kind"] == "stratagem_refund"
    assert capped_refund.reason == "command_point_refund_capped"

    simulation_state = _battle_state()
    simulated_ledgers: dict[str, CommandPointLedger] = {}
    assert (
        command_point_rule_unavailable_reason(
            state=simulation_state,
            player_id="player-a",
            source_id="phase17d:test:simulated-refund",
            operation="refund",
            delta=1,
            simulated_ledgers=simulated_ledgers,
        )
        is None
    )
    assert (
        command_point_rule_unavailable_reason(
            state=simulation_state,
            player_id="player-a",
            source_id="phase17d:test:simulated-refund-capped",
            operation="refund",
            delta=1,
            simulated_ledgers=simulated_ledgers,
        )
        == "command_point_refund_capped"
    )
    assert (
        command_point_rule_unavailable_reason(
            state=simulation_state,
            player_id="player-a",
            source_id="phase17d:test:simulated-spend",
            operation="spend",
            delta=-1,
            simulated_ledgers=simulated_ledgers,
        )
        is None
    )
    assert (
        command_point_rule_unavailable_reason(
            state=simulation_state,
            player_id="player-b",
            source_id="phase17d:test:simulated-insufficient",
            operation="spend",
            delta=-1,
            simulated_ledgers=simulated_ledgers,
        )
        == "insufficient_command_points"
    )

    assert command_point_operation_shape_reason(operation="gain", delta=0) == (
        "zero_command_point_delta"
    )
    assert (
        command_point_operation_shape_reason(operation="modify_stratagem_cost", delta=1)
        == "stratagem_cost_context_required"
    )
    assert command_point_operation_shape_reason(operation="refund", delta=-1) == (
        "invalid_command_point_refund_delta"
    )
    assert command_point_operation_shape_reason(operation="spend", delta=1) == (
        "invalid_command_point_spend_delta"
    )
    assert command_point_operation_shape_reason(operation="unknown", delta=1) == (
        "unsupported_command_point_operation:unknown"
    )


def test_phase17d_duration_effect_records_generic_persisting_effect() -> None:
    state = _battle_state_with_scenario()
    target_unit_id = "army-alpha:intercessor-unit-1"
    compiled = _compiled("That unit gains Stealth until the end of the phase.")

    result = execute_rule_ir(
        rule_ir=compiled.rule_ir,
        context=_execution_context(
            state=state,
            target_unit_instance_ids=(target_unit_id,),
        ),
        registry=default_rule_execution_registry(),
    )
    effect = result.created_persisting_effects[0]
    payload = effect.to_payload()
    effect_payload = _json_object(payload["effect_payload"])

    assert result.status is RuleExecutionStatus.APPLIED
    assert state.persisting_effects_for_unit(target_unit_id) == (effect,)
    assert payload["started_phase"] == "command"
    assert payload["expiration"]["expiration_kind"] == "end_phase"
    assert effect_payload["effect_kind"] == "generic_rule_execution"


def test_phase17d_this_model_half_strength_hit_modifier_persists_source_model_conditions() -> None:
    state = _battle_state_with_scenario()
    source_unit_id = "army-alpha:intercessor-unit-1"
    source_model_id = _unit_by_id(state, source_unit_id).own_models[0].model_instance_id
    compiled = _compiled(
        "Until the end of the phase, each time this model makes an attack that targets "
        "an enemy unit that is not below Half-strength, add 1 to the Hit roll."
    )

    result = execute_rule_ir(
        rule_ir=compiled.rule_ir,
        context=_execution_context(
            state=state,
            source_unit_instance_id=source_unit_id,
            source_model_instance_id=source_model_id,
        ),
        registry=default_rule_execution_registry(),
    )
    effect = result.created_persisting_effects[0]
    effect_payload = _json_object(effect.effect_payload)
    conditions = cast(list[JsonValue], effect_payload["conditions"])
    target_constraint = _json_object(conditions[0])

    assert result.status is RuleExecutionStatus.APPLIED
    assert effect.target_unit_instance_ids == (source_unit_id,)
    assert state.persisting_effects_for_unit(source_unit_id) == (effect,)
    assert effect_payload["target_unit_instance_ids"] == [source_unit_id]
    assert _json_object(effect_payload["context"])["source_model_instance_id"] == source_model_id
    assert _json_object(effect_payload["target"])["kind"] == "this_model"
    assert target_constraint["kind"] == "target_constraint"
    assert target_constraint["parameters"] == [
        {"key": "gate_subject", "value": "attack_target"},
        {"key": "relationship", "value": "this_model_makes_attack"},
        {"key": "target_allegiance", "value": "enemy"},
        {"key": "target_constraint", "value": "target_not_below_half_strength"},
    ]


def test_phase17d_this_model_half_strength_hit_modifier_requires_source_model() -> None:
    state = _battle_state_with_scenario()
    source_unit_id = "army-alpha:intercessor-unit-1"
    compiled = _compiled(
        "Until the end of the phase, each time this model makes an attack that targets "
        "an enemy unit that is not below Half-strength, add 1 to the Hit roll."
    )

    result = execute_rule_ir(
        rule_ir=compiled.rule_ir,
        context=_execution_context(
            state=state,
            source_unit_instance_id=source_unit_id,
        ),
        registry=default_rule_execution_registry(),
    )

    assert result.status is RuleExecutionStatus.INVALID
    assert result.reason == "missing_input:source_model_instance_id"
    assert state.persisting_effects_for_unit(source_unit_id) == ()


@pytest.mark.parametrize(
    ("raw_text", "expected_expiration_kind"),
    [
        ("That unit gains Stealth until the end of the turn.", "end_turn"),
        ("That unit gains Stealth until the end of the battle.", "end_of_battle"),
    ],
)
def test_phase17d_duration_endpoint_variants_record_persisting_effects(
    raw_text: str,
    expected_expiration_kind: str,
) -> None:
    state = _battle_state_with_scenario()
    target_unit_id = "army-alpha:intercessor-unit-1"
    compiled = _compiled(raw_text)

    result = execute_rule_ir(
        rule_ir=compiled.rule_ir,
        context=_execution_context(
            state=state,
            target_unit_instance_ids=(target_unit_id,),
        ),
        registry=default_rule_execution_registry(),
    )

    assert result.status is RuleExecutionStatus.APPLIED
    assert len(result.created_persisting_effects) == 1
    assert (
        result.created_persisting_effects[0].to_payload()["expiration"]["expiration_kind"]
        == expected_expiration_kind
    )


def test_phase17d_current_phase_duration_expires_on_active_player_boundary() -> None:
    state = _battle_state_with_scenario()
    state.active_player_id = "player-b"
    target_unit_id = "army-alpha:intercessor-unit-1"
    compiled = _compiled("That unit gains Stealth until the end of the phase.")

    result = execute_rule_ir(
        rule_ir=compiled.rule_ir,
        context=_execution_context(
            state=state,
            target_unit_instance_ids=(target_unit_id,),
            phase=BattlePhaseKind.SHOOTING,
            active_player_id="player-b",
        ),
        registry=default_rule_execution_registry(),
    )
    expiration = result.created_persisting_effects[0].expiration

    assert result.status is RuleExecutionStatus.APPLIED
    assert expiration.expiration_kind.value == "end_phase"
    assert expiration.player_id == "player-b"
    assert expiration.phase is BattlePhaseKind.SHOOTING


@pytest.mark.parametrize(
    ("raw_text", "phase", "active_player_id", "expected_expiration"),
    [
        (
            "That unit has the Stealth ability until your next Command phase.",
            BattlePhaseKind.SHOOTING,
            "player-a",
            {
                "expiration_kind": "start_phase",
                "battle_round": 2,
                "phase": "command",
                "player_id": "player-a",
            },
        ),
        (
            "That unit has the Stealth ability until the end of your next turn.",
            BattlePhaseKind.SHOOTING,
            "player-a",
            {
                "expiration_kind": "end_turn",
                "battle_round": 2,
                "phase": None,
                "player_id": "player-a",
            },
        ),
        (
            "That unit has the Stealth ability until the start of opponent's next turn.",
            BattlePhaseKind.SHOOTING,
            "player-a",
            {
                "expiration_kind": "start_turn",
                "battle_round": 1,
                "phase": None,
                "player_id": "player-b",
            },
        ),
    ],
)
def test_phase17d_relative_duration_endpoints_record_lifecycle_expiration(
    raw_text: str,
    phase: BattlePhaseKind,
    active_player_id: str,
    expected_expiration: dict[str, object],
) -> None:
    state = _battle_state_with_scenario()
    state.active_player_id = active_player_id
    target_unit_id = "army-alpha:intercessor-unit-1"
    compiled = _compiled(raw_text)

    result = execute_rule_ir(
        rule_ir=compiled.rule_ir,
        context=_execution_context(
            state=state,
            target_unit_instance_ids=(target_unit_id,),
            phase=phase,
            active_player_id=active_player_id,
        ),
        registry=default_rule_execution_registry(),
    )

    assert result.status is RuleExecutionStatus.APPLIED
    assert result.created_persisting_effects[0].expiration.to_payload() == expected_expiration


def test_phase17d_phase_duration_requires_phase_before_mutation() -> None:
    state = _battle_state_with_scenario()
    event_log = EventLog()
    target_unit_id = "army-alpha:intercessor-unit-1"
    compiled = _compiled("That unit gains Stealth until the end of the phase.")

    result = execute_rule_ir(
        rule_ir=compiled.rule_ir,
        context=_execution_context(
            state=state,
            event_log=event_log,
            target_unit_instance_ids=(target_unit_id,),
            phase=None,
        ),
        registry=default_rule_execution_registry(),
    )

    assert result.status is RuleExecutionStatus.INVALID
    assert result.reason == "missing_phase"
    assert state.persisting_effects_for_unit(target_unit_id) == ()
    assert event_log.records == ()


def test_phase17d_duration_effect_requires_state_before_applying() -> None:
    target_unit_id = "army-alpha:intercessor-unit-1"
    compiled = _compiled("That unit gains Stealth until the end of the phase.")

    result = execute_rule_ir(
        rule_ir=compiled.rule_ir,
        context=_execution_context(
            target_unit_instance_ids=(target_unit_id,),
            phase=BattlePhaseKind.COMMAND,
            state=None,
        ),
        registry=default_rule_execution_registry(),
    )

    assert result.status is RuleExecutionStatus.INVALID
    assert result.reason == "missing_input:game_state"
    assert result.effect_payloads == ()
    assert result.created_persisting_effects == ()


def test_phase17d_preflight_rejects_missing_state_before_vp_mutation() -> None:
    compiled = _compiled("When this unit is destroyed, score 5VP.")

    result = execute_rule_ir(
        rule_ir=compiled.rule_ir,
        context=_execution_context(),
        registry=default_rule_execution_registry(),
    )

    assert result.status is RuleExecutionStatus.INVALID
    assert result.reason == "missing_input:game_state"
    assert result.event_records == ()


def test_phase17d_handler_invalid_result_propagates_without_merge_exception() -> None:
    state = _battle_state()
    compiled = _compiled("When this unit is destroyed, score 5VP.")

    result = execute_rule_ir(
        rule_ir=compiled.rule_ir,
        context=_execution_context(state=state, phase=None),
        registry=default_rule_execution_registry(),
    )

    assert result.status is RuleExecutionStatus.INVALID
    assert result.reason == "missing_phase"
    assert state.victory_point_total("player-a") == 0


def test_phase17d_generic_stratagem_target_binding_executes() -> None:
    compiled = _compiled("Select one enemy unit.")
    target_unit_id = "army-beta:intercessor-unit-2"

    result = execute_rule_ir(
        rule_ir=compiled.rule_ir,
        context=_execution_context(
            target_unit_instance_ids=(target_unit_id,),
            trigger_payload={"stratagem_id": "phase17d:test-stratagem"},
        ),
        registry=default_rule_execution_registry(),
    )

    assert result.status is RuleExecutionStatus.APPLIED
    assert result.target_bindings == (
        {
            "rule_id": compiled.rule_ir.rule_id,
            "source_id": compiled.rule_ir.source_id,
            "clause_id": compiled.rule_ir.clauses[0].clause_id,
            "target_kind": "enemy_unit",
            "target_unit_instance_ids": [target_unit_id],
            "target_player_id": None,
        },
    )
    assert result.event_records[0].event_type == "rule_execution_target_bound"


def test_phase17d_selected_target_binding_uses_trigger_payload_when_unbound() -> None:
    compiled = _compiled("One friendly unit that was selected as the target.")
    first_target_id = "army-alpha:intercessor-unit-1"
    second_target_id = "army-alpha:intercessor-unit-2"

    result = execute_rule_ir(
        rule_ir=compiled.rule_ir,
        context=_execution_context(
            trigger_payload={
                SELECTED_TARGET_UNIT_CONTEXT_KEY: [second_target_id, first_target_id],
            },
        ),
        registry=default_rule_execution_registry(),
    )

    assert result.status is RuleExecutionStatus.APPLIED
    assert result.target_bindings == (
        {
            "rule_id": compiled.rule_ir.rule_id,
            "source_id": compiled.rule_ir.source_id,
            "clause_id": compiled.rule_ir.clauses[0].clause_id,
            "target_kind": "selected_target",
            "target_unit_instance_ids": [first_target_id, second_target_id],
            "target_player_id": None,
        },
    )


def test_phase17d_selected_target_binding_enforces_target_keywords_with_state() -> None:
    state = _battle_state_with_scenario()
    infantry = _compiled("One friendly INFANTRY unit that was selected as the target.")
    vehicle = _compiled("One friendly VEHICLE unit that was selected as the target.")
    target_unit_id = "army-alpha:intercessor-unit-1"

    applied = execute_rule_ir(
        rule_ir=infantry.rule_ir,
        context=_execution_context(
            state=state,
            trigger_payload={SELECTED_TARGET_UNIT_CONTEXT_KEY: [target_unit_id]},
        ),
        registry=default_rule_execution_registry(),
    )
    missing_state = execute_rule_ir(
        rule_ir=infantry.rule_ir,
        context=_execution_context(
            trigger_payload={SELECTED_TARGET_UNIT_CONTEXT_KEY: [target_unit_id]},
        ),
        registry=default_rule_execution_registry(),
    )
    keyword_mismatch = execute_rule_ir(
        rule_ir=vehicle.rule_ir,
        context=_execution_context(
            state=state,
            trigger_payload={SELECTED_TARGET_UNIT_CONTEXT_KEY: [target_unit_id]},
        ),
        registry=default_rule_execution_registry(),
    )

    assert applied.status is RuleExecutionStatus.APPLIED
    assert applied.target_bindings[0]["target_unit_instance_ids"] == [target_unit_id]
    assert missing_state.status is RuleExecutionStatus.INVALID
    assert missing_state.reason == "missing_input:game_state"
    assert keyword_mismatch.status is RuleExecutionStatus.INVALID
    assert keyword_mismatch.reason == "unit_missing_required_keyword"


def test_phase17d_selected_target_effect_uses_trigger_payload_binding() -> None:
    state = _battle_state_with_scenario()
    compiled = _compiled(
        "One friendly unit that was selected as the target gains Stealth until the end "
        "of the phase."
    )
    target_unit_id = "army-alpha:intercessor-unit-1"

    result = execute_rule_ir(
        rule_ir=compiled.rule_ir,
        context=_execution_context(
            state=state,
            trigger_payload={SELECTED_TARGET_UNIT_CONTEXT_KEY: [target_unit_id]},
        ),
        registry=default_rule_execution_registry(),
    )

    assert result.status is RuleExecutionStatus.APPLIED
    assert result.effect_payloads[0]["target_unit_instance_ids"] == [target_unit_id]
    assert state.persisting_effects_for_unit(target_unit_id) == result.created_persisting_effects


def test_phase17d_selected_target_binding_requires_matching_context() -> None:
    compiled = _compiled("One friendly unit that was selected as the target.")
    selected_target_id = "army-alpha:intercessor-unit-1"
    other_target_id = "army-alpha:intercessor-unit-2"

    missing_context = execute_rule_ir(
        rule_ir=compiled.rule_ir,
        context=_execution_context(),
        registry=default_rule_execution_registry(),
    )
    mismatched_target = execute_rule_ir(
        rule_ir=compiled.rule_ir,
        context=_execution_context(
            target_unit_instance_ids=(other_target_id,),
            trigger_payload={SELECTED_TARGET_UNIT_CONTEXT_KEY: [selected_target_id]},
        ),
        registry=default_rule_execution_registry(),
    )

    assert missing_context.status is RuleExecutionStatus.INVALID
    assert missing_context.reason == "missing_selected_target_context"
    assert mismatched_target.status is RuleExecutionStatus.INVALID
    assert mismatched_target.reason == "unit_not_selected_as_target"
    assert missing_context.target_bindings == ()
    assert mismatched_target.target_bindings == ()


def test_phase17d_preflight_rejects_missing_target_binding() -> None:
    compiled = _compiled("Select one enemy unit.")

    result = execute_rule_ir(
        rule_ir=compiled.rule_ir,
        context=_execution_context(),
        registry=default_rule_execution_registry(),
    )

    assert result.status is RuleExecutionStatus.INVALID
    assert result.reason == "missing_target:unit_instance_ids"
    assert result.target_bindings == ()


def test_phase17d_friendly_aura_evaluation_ignores_enemy_units_in_range() -> None:
    state = _battle_state_with_extra_friendly_unit()
    source_unit_id = "army-alpha:intercessor-unit-1"
    friendly_unit_id = "army-alpha:intercessor-unit-3"
    enemy_unit_id = "army-beta:intercessor-unit-2"
    compiled = _compiled(
        "Aura: while a friendly unit is within 6 inches, subtract 1 from wound rolls."
    )

    state.battlefield_state = _with_unit_pose(
        state.battlefield_state,
        unit_instance_id=friendly_unit_id,
        pose=Pose.at(8.0, 6.0),
    )
    state.battlefield_state = _with_unit_pose(
        state.battlefield_state,
        unit_instance_id=enemy_unit_id,
        pose=Pose.at(8.0, 6.0),
    )
    result = execute_rule_ir(
        rule_ir=compiled.rule_ir,
        context=_execution_context(state=state, source_unit_instance_id=source_unit_id),
        registry=default_rule_execution_registry(),
    )

    assert result.status is RuleExecutionStatus.APPLIED
    assert result.aura_evaluations[0]["affected_unit_instance_ids"] == [friendly_unit_id]
    assert result.effect_payloads[0]["target_unit_instance_ids"] == [friendly_unit_id]


def test_phase17d_enemy_aura_evaluation_ignores_friendly_units_in_range() -> None:
    state = _battle_state_with_extra_friendly_unit()
    source_unit_id = "army-alpha:intercessor-unit-1"
    friendly_unit_id = "army-alpha:intercessor-unit-3"
    enemy_unit_id = "army-beta:intercessor-unit-2"
    compiled = _compiled(
        "Aura: while an enemy unit is within 6 inches, subtract 1 from wound rolls."
    )

    state.battlefield_state = _with_unit_pose(
        state.battlefield_state,
        unit_instance_id=friendly_unit_id,
        pose=Pose.at(8.0, 6.0),
    )
    state.battlefield_state = _with_unit_pose(
        state.battlefield_state,
        unit_instance_id=enemy_unit_id,
        pose=Pose.at(8.0, 6.0),
    )
    result = execute_rule_ir(
        rule_ir=compiled.rule_ir,
        context=_execution_context(state=state, source_unit_instance_id=source_unit_id),
        registry=default_rule_execution_registry(),
    )

    assert result.status is RuleExecutionStatus.APPLIED
    assert result.aura_evaluations[0]["affected_unit_instance_ids"] == [enemy_unit_id]
    assert result.effect_payloads[0]["target_unit_instance_ids"] == [enemy_unit_id]


def test_phase17d_any_aura_evaluation_affects_all_allegiances_in_range() -> None:
    state = _battle_state_with_extra_friendly_unit()
    source_unit_id = "army-alpha:intercessor-unit-1"
    friendly_unit_id = "army-alpha:intercessor-unit-3"
    enemy_unit_id = "army-beta:intercessor-unit-2"
    compiled = _compiled("Aura: while a unit is within 6 inches, subtract 1 from wound rolls.")

    state.battlefield_state = _with_unit_pose(
        state.battlefield_state,
        unit_instance_id=friendly_unit_id,
        pose=Pose.at(8.0, 6.0),
    )
    state.battlefield_state = _with_unit_pose(
        state.battlefield_state,
        unit_instance_id=enemy_unit_id,
        pose=Pose.at(8.0, 6.0),
    )
    result = execute_rule_ir(
        rule_ir=compiled.rule_ir,
        context=_execution_context(state=state, source_unit_instance_id=source_unit_id),
        registry=default_rule_execution_registry(),
    )

    assert result.status is RuleExecutionStatus.APPLIED
    assert result.aura_evaluations[0]["affected_unit_instance_ids"] == [
        friendly_unit_id,
        enemy_unit_id,
    ]


def test_phase17d_aura_keyword_gates_match_target_faction_keywords() -> None:
    state = _battle_state_with_extra_friendly_unit()
    source_unit_id = "army-alpha:intercessor-unit-1"
    target_unit_id = "army-alpha:intercessor-unit-3"
    excluded_unit_id = "army-beta:intercessor-unit-2"
    compiled = _compiled(
        "Daemon Lord of Khorne (Aura): While a friendly Khorne Legiones Daemonica "
        'unit is within 6" of this model, each time a model in that unit makes a '
        "melee attack, add 1 to the Hit roll."
    )

    state = _with_unit_keywords(
        state,
        unit_instance_id=source_unit_id,
        keywords=("CHARACTER",),
        faction_keywords=("LEGIONES DAEMONICA", "KHORNE"),
    )
    state = _with_unit_keywords(
        state,
        unit_instance_id=target_unit_id,
        keywords=("INFANTRY",),
        faction_keywords=("LEGIONES DAEMONICA", "KHORNE"),
    )
    state = _with_unit_keywords(
        state,
        unit_instance_id=excluded_unit_id,
        keywords=("INFANTRY",),
        faction_keywords=("LEGIONES DAEMONICA",),
    )
    state.battlefield_state = _with_unit_pose(
        state.battlefield_state,
        unit_instance_id=target_unit_id,
        pose=Pose.at(8.0, 6.0),
    )
    state.battlefield_state = _with_unit_pose(
        state.battlefield_state,
        unit_instance_id=excluded_unit_id,
        pose=Pose.at(8.0, 6.0),
    )
    result = execute_rule_ir(
        rule_ir=compiled.rule_ir,
        context=_execution_context(state=state, source_unit_instance_id=source_unit_id),
        registry=default_rule_execution_registry(),
    )

    assert result.status is RuleExecutionStatus.APPLIED
    assert result.aura_evaluations[0]["affected_unit_instance_ids"] == [target_unit_id]
    assert result.effect_payloads[0]["target_unit_instance_ids"] == [target_unit_id]


def test_phase17d_shadow_of_chaos_aura_status_targets_matching_daemons() -> None:
    state = _battle_state_with_extra_friendly_unit()
    source_unit_id = "army-alpha:intercessor-unit-1"
    target_unit_id = "army-alpha:intercessor-unit-3"
    excluded_unit_id = "army-beta:intercessor-unit-2"
    compiled = _compiled(
        'Daemonic Shadow (Aura): While a friendly Nurgle Legiones Daemonica unit is within 6" '
        "of this model, that unit is within your army's Shadow of Chaos."
    )

    state = _with_unit_keywords(
        state,
        unit_instance_id=source_unit_id,
        keywords=("CHARACTER",),
        faction_keywords=("LEGIONES DAEMONICA", "NURGLE"),
    )
    state = _with_unit_keywords(
        state,
        unit_instance_id=target_unit_id,
        keywords=("INFANTRY",),
        faction_keywords=("LEGIONES DAEMONICA", "NURGLE"),
    )
    state = _with_unit_keywords(
        state,
        unit_instance_id=excluded_unit_id,
        keywords=("INFANTRY",),
        faction_keywords=("LEGIONES DAEMONICA", "KHORNE"),
    )
    state.battlefield_state = _with_unit_pose(
        state.battlefield_state,
        unit_instance_id=target_unit_id,
        pose=Pose.at(8.0, 6.0),
    )
    state.battlefield_state = _with_unit_pose(
        state.battlefield_state,
        unit_instance_id=excluded_unit_id,
        pose=Pose.at(8.0, 6.0),
    )
    result = execute_rule_ir(
        rule_ir=compiled.rule_ir,
        context=_execution_context(state=state, source_unit_instance_id=source_unit_id),
        registry=default_rule_execution_registry(),
    )
    effect = _json_object(result.effect_payloads[0]["effect"])

    assert result.status is RuleExecutionStatus.APPLIED
    assert result.aura_evaluations[0]["affected_unit_instance_ids"] == [target_unit_id]
    assert result.effect_payloads[0]["target_unit_instance_ids"] == [target_unit_id]
    assert effect["kind"] == "set_contextual_status"
    assert parameter_payload(compiled.rule_ir.clauses[0].effects[0].parameters) == {
        "owner": "your_army",
        "rules_context": "shadow_of_chaos",
        "status": "within_shadow_of_chaos",
    }


def test_phase17d_enemy_aura_keyword_gate_applies_only_to_matching_enemy_units() -> None:
    state = _battle_state_with_extra_friendly_unit()
    source_unit_id = "army-beta:intercessor-unit-2"
    target_unit_id = "army-alpha:intercessor-unit-3"
    excluded_unit_id = "army-alpha:intercessor-unit-1"
    compiled = _compiled(
        'Ded Glowy Ammo (Aura): While an enemy Infantry unit is within 6" of this '
        "model, subtract 1 from the Toughness characteristic of models in that unit."
    )

    state = _with_unit_keywords(
        state,
        unit_instance_id=target_unit_id,
        keywords=("INFANTRY",),
        faction_keywords=(),
    )
    state = _with_unit_keywords(
        state,
        unit_instance_id=excluded_unit_id,
        keywords=("VEHICLE",),
        faction_keywords=(),
    )
    state.battlefield_state = _with_unit_pose(
        state.battlefield_state,
        unit_instance_id=source_unit_id,
        pose=Pose.at(0.0, 0.0),
    )
    state.battlefield_state = _with_unit_pose(
        state.battlefield_state,
        unit_instance_id=target_unit_id,
        pose=Pose.at(2.0, 0.0),
    )
    state.battlefield_state = _with_unit_pose(
        state.battlefield_state,
        unit_instance_id=excluded_unit_id,
        pose=Pose.at(2.0, 1.0),
    )
    result = execute_rule_ir(
        rule_ir=compiled.rule_ir,
        context=_execution_context(state=state, source_unit_instance_id=source_unit_id),
        registry=default_rule_execution_registry(),
    )

    assert result.status is RuleExecutionStatus.APPLIED
    assert result.aura_evaluations[0]["affected_unit_instance_ids"] == [target_unit_id]
    assert result.effect_payloads[0]["target_unit_instance_ids"] == [target_unit_id]


def test_phase17d_unsupported_rule_ir_produces_typed_unsupported_status() -> None:
    compiled = _compiled("Roll a scatter die and consult the legacy table.")

    result = execute_rule_ir(
        rule_ir=compiled.rule_ir,
        context=_execution_context(),
        registry=default_rule_execution_registry(),
    )

    assert result.status is RuleExecutionStatus.UNSUPPORTED
    assert result.reason == "unsupported_rule_ir"
    assert result.applied_clause_ids == ()
    assert result.event_records == ()


def test_phase17d_missing_registry_binding_produces_typed_unsupported_status() -> None:
    compiled = _compiled("Add 1 to hit rolls for that unit.")

    result = execute_rule_ir(
        rule_ir=compiled.rule_ir,
        context=_execution_context(),
        registry=RuleExecutionRegistry.empty(),
    )

    assert result.status is RuleExecutionStatus.UNSUPPORTED
    assert result.reason == "missing_effect_handler:modify_dice_roll"
    assert result.event_records == ()


def test_phase17d_no_effect_clause_executes_as_deterministic_noop() -> None:
    compiled = _compiled("At the start of your Command phase.")

    result = execute_rule_ir(
        rule_ir=compiled.rule_ir,
        context=_execution_context(),
        registry=default_rule_execution_registry(),
    )
    replay_payload = _json_object(result.replay_payload)

    assert result.status is RuleExecutionStatus.APPLIED
    assert result.applied_clause_ids == (compiled.rule_ir.clauses[0].clause_id,)
    assert result.effect_payloads == ()
    assert result.event_records == ()
    assert replay_payload["executed_clause_count"] == 1
    assert replay_payload["event_count"] == 0


def test_phase17d_rule_ir_payload_round_trips_through_execution_result() -> None:
    compiled = _compiled("Add 1 to hit rolls for that unit.")
    rule_ir_payload = cast(RuleIRPayload, json.loads(compiled.rule_ir.to_json_bytes()))

    result = execute_rule_ir(
        rule_ir=compiled.rule_ir,
        context=_execution_context(
            target_unit_instance_ids=("army-alpha:intercessor-unit-1",),
        ),
        registry=default_rule_execution_registry(),
    )

    assert result.status is RuleExecutionStatus.APPLIED
    assert result.to_payload()["rule_ir_hash"] == rule_ir_payload["ir_hash"]
    assert "<" not in json.dumps(result.to_payload(), sort_keys=True)
    assert "object at 0x" not in json.dumps(result.to_payload(), sort_keys=True)


def test_phase17d_execution_payload_and_registry_metadata_are_json_safe() -> None:
    compiled = _compiled("Add 1 to hit rolls for that unit.")
    execution_payload = validate_json_value({"rule_ir": compiled.rule_ir.to_payload()})

    rule_ir = rule_ir_from_execution_payload(execution_payload)
    registry_payload = default_rule_execution_registry().to_payload()

    assert rule_ir.ir_hash() == compiled.rule_ir.ir_hash()
    assert rule_execution_status_from_token("applied") is RuleExecutionStatus.APPLIED
    assert "phase17d:generic-command-points" in {
        binding["binding_id"] for binding in registry_payload
    }
    assert "<" not in json.dumps(registry_payload, sort_keys=True)
    with pytest.raises(GameLifecycleError, match="must be a JSON object"):
        rule_ir_from_execution_payload([])
    with pytest.raises(GameLifecycleError, match="requires rule_ir"):
        rule_ir_from_execution_payload({"missing": None})
    with pytest.raises(GameLifecycleError, match="must be a string"):
        rule_execution_status_from_token(1)
    with pytest.raises(GameLifecycleError, match="Unsupported RuleExecutionStatus"):
        rule_execution_status_from_token("not-a-status")


def test_phase17d_rule_execution_registry_and_binding_validators_fail_fast() -> None:
    compiled = _compiled("Add 1 to hit rolls for that unit.")
    clause = compiled.rule_ir.clauses[0]
    effect = clause.effects[0]
    binding = RuleRuntimeBinding(
        binding_id="phase17d:test-binding",
        template_id=None,
        effect_kinds=(RuleEffectKind.MODIFY_DICE_ROLL,),
        handler=_noop_rule_handler,
    )

    assert binding.matches_clause(clause)
    assert binding.matches_effect(clause=clause, effect=effect)
    assert RuleExecutionRegistry.from_bindings((binding,)).all_bindings() == (binding,)
    with pytest.raises(GameLifecycleError, match="state must be a GameState"):
        _execution_context(state=cast(GameState, object()))
    with pytest.raises(GameLifecycleError, match="event_log must be an EventLog"):
        _execution_context(event_log=cast(EventLog, object()))
    with pytest.raises(GameLifecycleError, match="trigger_kind must be RuleTriggerKind"):
        RuleRuntimeBinding(
            binding_id="phase17d:bad-trigger",
            template_id=None,
            effect_kinds=(RuleEffectKind.MODIFY_DICE_ROLL,),
            handler=_noop_rule_handler,
            trigger_kind=cast(RuleTriggerKind, "bad"),
        )
    with pytest.raises(GameLifecycleError, match="handler must be callable"):
        RuleRuntimeBinding(
            binding_id="phase17d:bad-handler",
            template_id=None,
            effect_kinds=(RuleEffectKind.MODIFY_DICE_ROLL,),
            handler=cast(Any, object()),
        )
    with pytest.raises(GameLifecycleError, match="requires a template, effect, or target"):
        RuleRuntimeBinding(
            binding_id="phase17d:no-match-surface",
            template_id=None,
            effect_kinds=(),
            handler=_noop_rule_handler,
        )
    with pytest.raises(GameLifecycleError, match="clause match requires a RuleClause"):
        binding.matches_clause(cast(RuleClause, object()))
    with pytest.raises(GameLifecycleError, match="effect match requires RuleEffectSpec"):
        binding.matches_effect(clause=clause, effect=cast(RuleEffectSpec, object()))
    with pytest.raises(GameLifecycleError, match="bindings must be a tuple"):
        RuleExecutionRegistry.from_bindings(cast(tuple[RuleRuntimeBinding, ...], []))
    with pytest.raises(GameLifecycleError, match="binding IDs must be unique"):
        RuleExecutionRegistry.from_bindings((binding, binding))
    with pytest.raises(GameLifecycleError, match="binding must be RuleRuntimeBinding"):
        RuleExecutionRegistry.empty().with_binding(cast(RuleRuntimeBinding, object()))
    with pytest.raises(GameLifecycleError, match="requires RuleExecutionContext"):
        execute_rule_ir(
            rule_ir=compiled.rule_ir,
            context=cast(RuleExecutionContext, object()),
        )
    with pytest.raises(GameLifecycleError, match="requires RuleExecutionRegistry"):
        execute_rule_ir(
            rule_ir=compiled.rule_ir,
            context=_execution_context(target_unit_instance_ids=("army-alpha:intercessor-unit-1",)),
            registry=cast(RuleExecutionRegistry, object()),
        )


def test_phase17d_rule_execution_registry_order_is_binding_id_deterministic() -> None:
    effect_clause = _compiled("Add 1 to hit rolls for that unit.").rule_ir.clauses[0]
    effect = effect_clause.effects[0]
    target_clause = _compiled("Select one enemy unit.").rule_ir.clauses[0]
    first_effect = RuleRuntimeBinding(
        binding_id="phase17d:binding-a",
        template_id=None,
        effect_kinds=(RuleEffectKind.MODIFY_DICE_ROLL,),
        handler=_noop_rule_handler,
    )
    second_effect = RuleRuntimeBinding(
        binding_id="phase17d:binding-b",
        template_id=None,
        effect_kinds=(RuleEffectKind.MODIFY_DICE_ROLL,),
        handler=_noop_rule_handler,
    )
    first_target = RuleRuntimeBinding(
        binding_id="phase17d:target-binding-a",
        template_id=None,
        effect_kinds=(),
        handler=_noop_rule_handler,
        required_target_bindings=("unit_instance_ids",),
    )
    second_target = RuleRuntimeBinding(
        binding_id="phase17d:target-binding-b",
        template_id=None,
        effect_kinds=(),
        handler=_noop_rule_handler,
        required_target_bindings=("unit_instance_ids",),
    )

    forward = RuleExecutionRegistry.from_bindings(
        (first_effect, second_effect, first_target, second_target)
    )
    reverse = RuleExecutionRegistry.from_bindings(
        (second_target, first_target, second_effect, first_effect)
    )
    forward_payload_bytes = json.dumps(forward.to_payload(), separators=(",", ":")).encode("utf-8")
    reverse_payload_bytes = json.dumps(reverse.to_payload(), separators=(",", ":")).encode("utf-8")

    assert forward.binding_for_effect(clause=effect_clause, effect=effect) == first_effect
    assert reverse.binding_for_effect(clause=effect_clause, effect=effect) == first_effect
    assert forward.binding_for_clause(target_clause) == first_target
    assert reverse.binding_for_clause(target_clause) == first_target
    assert forward_payload_bytes == reverse_payload_bytes


def test_phase17d_rule_execution_result_and_binding_shape_validators_fail_fast() -> None:
    compiled = _compiled("Add 1 to hit rolls for that unit.")
    rule_ir = compiled.rule_ir

    with pytest.raises(GameLifecycleError, match="must contain effects"):
        RuleExecutionResult(
            rule_id=rule_ir.rule_id,
            source_id=rule_ir.source_id,
            rule_ir_hash=rule_ir.ir_hash(),
            status=RuleExecutionStatus.APPLIED,
            created_persisting_effects=cast(Any, (object(),)),
        )
    with pytest.raises(GameLifecycleError, match="event_records must contain events"):
        RuleExecutionResult(
            rule_id=rule_ir.rule_id,
            source_id=rule_ir.source_id,
            rule_ir_hash=rule_ir.ir_hash(),
            status=RuleExecutionStatus.APPLIED,
            event_records=cast(Any, (object(),)),
        )
    with pytest.raises(GameLifecycleError, match="Applied RuleExecutionResult"):
        RuleExecutionResult(
            rule_id=rule_ir.rule_id,
            source_id=rule_ir.source_id,
            rule_ir_hash=rule_ir.ir_hash(),
            status=RuleExecutionStatus.APPLIED,
            reason="not-allowed",
        )
    with pytest.raises(GameLifecycleError, match="Non-applied RuleExecutionResult"):
        RuleExecutionResult(
            rule_id=rule_ir.rule_id,
            source_id=rule_ir.source_id,
            rule_ir_hash=rule_ir.ir_hash(),
            status=RuleExecutionStatus.INVALID,
        )
    with pytest.raises(GameLifecycleError, match="effect_payloads must be a tuple"):
        RuleExecutionResult(
            rule_id=rule_ir.rule_id,
            source_id=rule_ir.source_id,
            rule_ir_hash=rule_ir.ir_hash(),
            status=RuleExecutionStatus.APPLIED,
            effect_payloads=cast(Any, []),
        )
    with pytest.raises(GameLifecycleError, match="payload must be a JSON object"):
        RuleExecutionResult(
            rule_id=rule_ir.rule_id,
            source_id=rule_ir.source_id,
            rule_ir_hash=rule_ir.ir_hash(),
            status=RuleExecutionStatus.APPLIED,
            effect_payloads=cast(Any, ([],)),
        )
    with pytest.raises(GameLifecycleError, match="binding_id must be a string"):
        RuleRuntimeBinding(
            binding_id=cast(str, 1),
            template_id=None,
            effect_kinds=(RuleEffectKind.MODIFY_DICE_ROLL,),
            handler=_noop_rule_handler,
        )
    with pytest.raises(GameLifecycleError, match="binding_id must not be empty"):
        RuleRuntimeBinding(
            binding_id="",
            template_id=None,
            effect_kinds=(RuleEffectKind.MODIFY_DICE_ROLL,),
            handler=_noop_rule_handler,
        )
    with pytest.raises(GameLifecycleError, match="effect_kinds must be a tuple"):
        RuleRuntimeBinding(
            binding_id="phase17d:bad-effect-kind-tuple",
            template_id=None,
            effect_kinds=cast(Any, []),
            handler=_noop_rule_handler,
        )
    with pytest.raises(GameLifecycleError, match="effect_kinds values must be RuleEffectKind"):
        RuleRuntimeBinding(
            binding_id="phase17d:bad-effect-kind-value",
            template_id=None,
            effect_kinds=cast(Any, ("bad",)),
            handler=_noop_rule_handler,
        )
    with pytest.raises(GameLifecycleError, match="effect_kinds values must not be duplicated"):
        RuleRuntimeBinding(
            binding_id="phase17d:duplicate-effect-kind",
            template_id=None,
            effect_kinds=(
                RuleEffectKind.MODIFY_DICE_ROLL,
                RuleEffectKind.MODIFY_DICE_ROLL,
            ),
            handler=_noop_rule_handler,
        )
    with pytest.raises(GameLifecycleError, match="required_state_inputs must be a tuple"):
        RuleRuntimeBinding(
            binding_id="phase17d:bad-required-state-inputs",
            template_id=None,
            effect_kinds=(RuleEffectKind.MODIFY_DICE_ROLL,),
            handler=_noop_rule_handler,
            required_state_inputs=cast(Any, []),
        )
    with pytest.raises(
        GameLifecycleError,
        match="required_state_inputs must not contain duplicate",
    ):
        RuleRuntimeBinding(
            binding_id="phase17d:duplicate-required-state-inputs",
            template_id=None,
            effect_kinds=(RuleEffectKind.MODIFY_DICE_ROLL,),
            handler=_noop_rule_handler,
            required_state_inputs=("state", "state"),
        )


def test_phase17d_target_only_clause_reports_missing_target_handler() -> None:
    compiled = _compiled("Select one enemy unit.")

    result = execute_rule_ir(
        rule_ir=compiled.rule_ir,
        context=_execution_context(target_unit_instance_ids=("army-beta:intercessor-unit-2",)),
        registry=RuleExecutionRegistry.empty(),
    )

    assert result.status is RuleExecutionStatus.UNSUPPORTED
    assert result.reason == "missing_target_handler"


def test_phase17d_runtime_clause_payload_scopes_rule_ir_or_fails_closed() -> None:
    rule_ir = _champion_slayer_rule_ir()

    scoped = scoped_rule_ir_from_execution_payload(
        validate_json_value(
            {
                "rule_ir": rule_ir.to_payload(),
                "runtime_clause_id": "phase17d:test:champion-slayer:clause:002",
            }
        )
    )

    assert len(scoped.clauses) == 1
    assert scoped.clauses[0].clause_id == "phase17d:test:champion-slayer:clause:002"
    with pytest.raises(GameLifecycleError, match="runtime_clause_id is unknown"):
        scoped_rule_ir_from_execution_payload(
            validate_json_value(
                {
                    "rule_ir": rule_ir.to_payload(),
                    "runtime_clause_id": "phase17d:test:champion-slayer:clause:999",
                }
            )
        )


def test_phase17d_generic_persisting_effect_rejects_invalid_payload_shape() -> None:
    with pytest.raises(EffectError, match="JSON object"):
        generic_rule_persisting_effect(
            effect_id="phase17d:effect",
            source_rule_id="phase17d:source",
            owner_player_id="player-a",
            target_unit_instance_ids=("army-alpha:intercessor-unit-1",),
            started_battle_round=1,
            started_phase=BattlePhaseKind.COMMAND,
            expiration=EffectExpiration.end_phase(
                battle_round=1,
                phase=BattlePhaseKind.COMMAND,
                player_id="player-a",
            ),
            effect_payload="not-object",
        )
    with pytest.raises(EffectError, match="payload kind"):
        generic_rule_persisting_effect(
            effect_id="phase17d:effect",
            source_rule_id="phase17d:source",
            owner_player_id="player-a",
            target_unit_instance_ids=("army-alpha:intercessor-unit-1",),
            started_battle_round=1,
            started_phase=BattlePhaseKind.COMMAND,
            expiration=EffectExpiration.end_phase(
                battle_round=1,
                phase=BattlePhaseKind.COMMAND,
                player_id="player-a",
            ),
            effect_payload={"effect_kind": "wrong"},
        )


def test_phase17d_ability_bridge_executes_compiled_rule_ir_payload() -> None:
    compiled = _compiled("Add 1 to hit rolls for that unit.")
    record = AbilityCatalogRecord(
        record_id="phase17d:ability-record",
        source_kind=AbilitySourceKind.DATASHEET,
        datasheet_id="phase17d:datasheet",
        definition=AbilityDefinition(
            ability_id="phase17d:ability",
            name="phase17d generic ability",
            source_id="phase17d:ability-source",
            when_descriptor="phase17d:when",
            effect_descriptor="phase17d:effect",
            restrictions_descriptor="phase17d:restrictions",
            timing=AbilityTimingDescriptor(trigger_kind=TimingTriggerKind.ANY_PHASE),
            handler_id=GENERIC_RULE_IR_ABILITY_HANDLER_ID,
            replay_payload=validate_json_value({"rule_ir": compiled.rule_ir.to_payload()}),
        ),
    )

    result = default_ability_handler_registry().execute(
        record=record,
        context=AbilityExecutionContext(
            game_id="phase17d-game",
            player_id="player-a",
            battle_round=1,
            phase=BattlePhaseKind.COMMAND,
            active_player_id="player-a",
            trigger_kind=TimingTriggerKind.ANY_PHASE,
            target_unit_instance_id="army-alpha:intercessor-unit-1",
            source_keywords=(),
        ),
    )
    replay_payload = _json_object(result.replay_payload)
    rule_execution = _json_object(replay_payload["rule_execution"])

    assert result.status is AbilityResolutionStatus.APPLIED
    assert rule_execution["status"] == "applied"
    assert rule_execution["rule_ir_hash"] == compiled.rule_ir.ir_hash()


def test_phase17d_leading_model_condition_survives_destroyed_bodyguard_split() -> None:
    leader_state = _bodyguard_destroyed_split_state()
    support_state = _bodyguard_destroyed_split_state()
    bodyguard_state = _bodyguard_destroyed_split_state()
    bodyguard_id = "army-alpha:bodyguard-unit"
    leader_id = "army-alpha:leader-unit"
    support_id = "army-alpha:support-unit"
    compiled = _compiled(_skullmaster_fury_text())

    leader_result = execute_rule_ir(
        rule_ir=compiled.rule_ir,
        context=_execution_context(
            state=leader_state,
            source_model_instance_id=f"{leader_id}:core-character-leader:001",
            target_unit_instance_ids=(leader_id,),
            phase=BattlePhaseKind.CHARGE,
        ),
        registry=default_rule_execution_registry(),
    )
    support_result = execute_rule_ir(
        rule_ir=compiled.rule_ir,
        context=_execution_context(
            state=support_state,
            source_unit_instance_id=support_id,
            target_unit_instance_ids=(support_id,),
            phase=BattlePhaseKind.CHARGE,
        ),
        registry=default_rule_execution_registry(),
    )
    bodyguard_result = execute_rule_ir(
        rule_ir=compiled.rule_ir,
        context=_execution_context(
            state=bodyguard_state,
            source_unit_instance_id=bodyguard_id,
            target_unit_instance_ids=(leader_id,),
            phase=BattlePhaseKind.CHARGE,
        ),
        registry=default_rule_execution_registry(),
    )

    assert not leader_state.army_definitions[0].attached_units
    assert leader_state.unit_started_battle_as_attached_leader_or_support(leader_id)
    assert leader_state.unit_started_battle_as_attached_leader_or_support(support_id)
    assert (
        GameState.from_payload(leader_state.to_payload()).to_payload() == leader_state.to_payload()
    )
    assert leader_result.status is RuleExecutionStatus.APPLIED
    assert support_result.status is RuleExecutionStatus.APPLIED
    assert bodyguard_result.status is RuleExecutionStatus.INVALID
    assert bodyguard_result.reason == "condition_not_met:this_model_leading_unit"


def test_phase17d_leading_model_condition_fails_closed_without_state_or_source() -> None:
    compiled = _compiled(_skullmaster_fury_text())

    missing_state = execute_rule_ir(
        rule_ir=compiled.rule_ir,
        context=_execution_context(
            source_unit_instance_id="army-alpha:leader-unit",
            target_unit_instance_ids=("army-alpha:leader-unit",),
            phase=BattlePhaseKind.CHARGE,
        ),
        registry=default_rule_execution_registry(),
    )
    missing_source = execute_rule_ir(
        rule_ir=compiled.rule_ir,
        context=_execution_context(
            state=_battle_state_with_attached_leader_support(),
            target_unit_instance_ids=("army-alpha:leader-unit",),
            phase=BattlePhaseKind.CHARGE,
        ),
        registry=default_rule_execution_registry(),
    )

    assert missing_state.status is RuleExecutionStatus.INVALID
    assert missing_state.reason == "missing_input:game_state"
    assert missing_source.status is RuleExecutionStatus.INVALID
    assert missing_source.reason == "missing_input:source_unit_instance_id"


def test_phase17d_ability_bridge_passes_state_for_leading_model_condition() -> None:
    state = _bodyguard_destroyed_split_state()
    leader_id = "army-alpha:leader-unit"
    compiled = _compiled(_skullmaster_fury_text())
    record = AbilityCatalogRecord(
        record_id="phase17d:leading-ability-record",
        source_kind=AbilitySourceKind.DATASHEET,
        datasheet_id="phase17d:skullmaster",
        definition=AbilityDefinition(
            ability_id="phase17d:leading-ability",
            name="phase17d leading ability",
            source_id="phase17d:leading-ability-source",
            when_descriptor="phase17d:when",
            effect_descriptor="phase17d:effect",
            restrictions_descriptor="phase17d:restrictions",
            timing=AbilityTimingDescriptor(trigger_kind=TimingTriggerKind.ANY_PHASE),
            handler_id=GENERIC_RULE_IR_ABILITY_HANDLER_ID,
            replay_payload=validate_json_value({"rule_ir": compiled.rule_ir.to_payload()}),
        ),
    )

    result = default_ability_handler_registry().execute(
        record=record,
        context=AbilityExecutionContext(
            game_id="phase17d-game",
            player_id="player-a",
            battle_round=1,
            phase=BattlePhaseKind.CHARGE,
            active_player_id="player-a",
            trigger_kind=TimingTriggerKind.ANY_PHASE,
            source_unit_instance_id=leader_id,
            target_unit_instance_id=leader_id,
            source_keywords=(),
            state=state,
        ),
    )

    assert result.status is AbilityResolutionStatus.APPLIED


def _compiled(raw_text: str) -> CompiledRuleSource:
    return compile_rule_source_text(
        RuleSourceText.from_raw(source_id=f"phase17d:{raw_text.lower()}", raw_text=raw_text),
        source_keyword_sequence_parts=SOURCE_KEYWORD_SEQUENCE_PARTS,
    )


def _skullmaster_fury_text() -> str:
    return (
        "While this model is leading a unit, each time that unit ends a Charge move, "
        "until the end of the turn, Juggernaut's bladed horns equipped by models in "
        "that unit have the [DEVASTATING WOUNDS] ability."
    )


def _desperate_escape_modifier_rule_ir() -> RuleIR:
    compiled = _compiled(
        "Each time an enemy unit (excluding Monsters and Vehicles) within Engagement Range "
        "of one or more units from your army with this ability Falls Back, models in that "
        "enemy unit must take Desperate Escape tests. When doing so, if that enemy unit is "
        "also Battle-shocked, subtract 1 from each of those Desperate Escape tests."
    )
    modifier_clause = compiled.rule_ir.clauses[1]
    return replace(
        compiled.rule_ir,
        clauses=(modifier_clause,),
        diagnostics=modifier_clause.diagnostics,
    )


def _command_point_spend_rule_ir() -> RuleIR:
    compiled = _compiled("Gain 1CP and score 3VP.")
    clause = compiled.rule_ir.clauses[0]
    command_point_effect = clause.effects[0]
    spend_effect = replace(
        command_point_effect,
        parameters=(
            RuleParameter("affected_player", "source_player"),
            RuleParameter("delta", -1),
            RuleParameter("operation", "spend"),
        ),
    )
    spend_clause = replace(clause, effects=(spend_effect,))
    return replace(compiled.rule_ir, clauses=(spend_clause,))


def _champion_slayer_rule_ir() -> RuleIR:
    return compile_rule_source_text(
        RuleSourceText.from_raw(
            source_id="phase17d:test:champion-slayer",
            raw_text=(
                "Each time this model makes a melee attack that targets a Character or Monster "
                "unit, you can re-roll the Wound roll. Each time this model destroys an enemy "
                "Character or Monster unit, this model regains up to D6 lost wounds."
            ),
        ),
        source_keyword_sequence_parts=SOURCE_KEYWORD_SEQUENCE_PARTS,
    ).rule_ir


def _catalog_with_champion_slayer_ability() -> ArmyCatalog:
    catalog = ArmyCatalog.phase9a_canonical_content_pack()
    datasheet = catalog.datasheet_by_id("core-intercessor-like-infantry")
    descriptor = _champion_slayer_descriptor()
    updated_datasheet = replace(datasheet, abilities=(*datasheet.abilities, descriptor))
    return replace(
        catalog,
        datasheets=tuple(
            updated_datasheet
            if candidate.datasheet_id == updated_datasheet.datasheet_id
            else candidate
            for candidate in catalog.datasheets
        ),
    )


def _catalog_with_descriptor(descriptor: DatasheetAbilityDescriptor) -> ArmyCatalog:
    catalog = ArmyCatalog.phase9a_canonical_content_pack()
    datasheet = catalog.datasheet_by_id("core-intercessor-like-infantry")
    updated_datasheet = replace(datasheet, abilities=(descriptor,))
    return replace(
        catalog,
        datasheets=tuple(
            updated_datasheet
            if candidate.datasheet_id == updated_datasheet.datasheet_id
            else candidate
            for candidate in catalog.datasheets
        ),
    )


def _champion_slayer_descriptor() -> DatasheetAbilityDescriptor:
    rule_ir = _champion_slayer_rule_ir()
    return DatasheetAbilityDescriptor(
        ability_id="champion-slayer",
        name="Champion Slayer",
        source_id="phase17d:test:champion-slayer",
        support=CatalogAbilitySupport.GENERIC_RULE_IR,
        source_kind=CatalogAbilitySourceKind.DATASHEET,
        effect_description="Champion Slayer compound ability.",
        rule_ir_payload=cast(CatalogJsonObject, rule_ir.to_payload()),
        rule_ir_diagnostics=tuple(
            cast(CatalogJsonObject, diagnostic.to_payload()) for diagnostic in rule_ir.diagnostics
        ),
    )


def _generic_catalog_descriptor(
    raw_text: str,
    *,
    ability_id: str | None = None,
    source_kind: CatalogAbilitySourceKind = CatalogAbilitySourceKind.DATASHEET,
    source_wargear_id: str | None = None,
) -> DatasheetAbilityDescriptor:
    source_suffix = hashlib.sha256(raw_text.encode()).hexdigest()[:12]
    rule_ir = compile_rule_source_text(
        RuleSourceText.from_raw(
            source_id=f"phase17d:test:generic-catalog:{source_suffix}",
            raw_text=raw_text,
        ),
        source_keyword_sequence_parts=SOURCE_KEYWORD_SEQUENCE_PARTS,
    ).rule_ir
    resolved_ability_id = ability_id or f"generic-catalog-{source_suffix}"
    return DatasheetAbilityDescriptor(
        ability_id=resolved_ability_id,
        name=f"Generic Catalog {source_suffix}",
        source_id=rule_ir.source_id,
        support=CatalogAbilitySupport.GENERIC_RULE_IR,
        source_kind=source_kind,
        source_wargear_id=source_wargear_id,
        effect_description=raw_text,
        rule_ir_payload=cast(CatalogJsonObject, rule_ir.to_payload()),
        rule_ir_diagnostics=tuple(
            cast(CatalogJsonObject, diagnostic.to_payload()) for diagnostic in rule_ir.diagnostics
        ),
    )


def _setup_reactive_single_model_state(
    *,
    target_pose: Pose,
    source_pose: Pose,
    keep_all_source_models: bool = False,
) -> tuple[GameState, ArmyCatalog, AbilityCatalogIndex]:
    descriptor = _generic_catalog_descriptor(
        SETUP_REACTIVE_SHOOT_CHARGE_TEXT,
        ability_id="setup-reactive-shoot-charge",
    )
    catalog = _catalog_with_descriptor(descriptor)
    armies = (
        muster_army(
            catalog=catalog,
            request=_muster_request(
                catalog=catalog,
                player_id="player-a",
                army_id="army-alpha",
                unit_selection_id="intercessor-unit-1",
            ),
        ),
        muster_army(
            catalog=catalog,
            request=_muster_request(
                catalog=catalog,
                player_id="player-b",
                army_id="army-beta",
                unit_selection_id="intercessor-unit-2",
            ),
        ),
    )
    state = _battle_state()
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.MOVEMENT)
    for army in armies:
        state.record_army_definition(army)
    state.battlefield_state = create_deterministic_battlefield_scenario(
        battlefield_id="phase17d-setup-reactive",
        armies=armies,
    ).battlefield_state
    state.battlefield_state = _with_unit_pose(
        state.battlefield_state,
        unit_instance_id="army-alpha:intercessor-unit-1",
        pose=target_pose,
    )
    state.battlefield_state = _with_unit_pose(
        state.battlefield_state,
        unit_instance_id="army-beta:intercessor-unit-2",
        pose=source_pose,
    )
    assert state.battlefield_state is not None
    source_unit = _unit_by_id(state, "army-beta:intercessor-unit-2")
    if not keep_all_source_models:
        state.battlefield_state = state.battlefield_state.with_removed_models(
            tuple(model.model_instance_id for model in source_unit.own_models[1:])
        )
    records = catalog_ability_records_from_catalog(catalog)
    player_b_index = build_player_ability_index(
        records,
        army=state.army_definitions[1],
        catalog=catalog,
    )
    return state, catalog, player_b_index


def _setup_reactive_lifecycle(*, state: GameState, catalog: ArmyCatalog) -> GameLifecycle:
    config = _setup_reactive_config(catalog)
    return GameLifecycle.from_payload(
        cast(
            Any,
            {
                "config": config.to_payload(),
                "parameterized_movement_proposals": True,
                "state": state.to_payload(),
                "decisions": DecisionController().to_payload(),
                "reaction_queue": ReactionQueue().to_payload(),
            },
        )
    )


def _setup_reactive_config(catalog: ArmyCatalog) -> GameConfig:
    return GameConfig(
        game_id="phase17d-game",
        allow_legacy_non_strict_rosters=True,
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(),
        army_catalog=catalog,
        army_muster_requests=(
            _muster_request(
                catalog=catalog,
                player_id="player-a",
                army_id="army-alpha",
                unit_selection_id="intercessor-unit-1",
            ),
            _muster_request(
                catalog=catalog,
                player_id="player-b",
                army_id="army-beta",
                unit_selection_id="intercessor-unit-2",
            ),
        ),
        player_ids=("player-a", "player-b"),
        turn_order=("player-a", "player-b"),
        fixed_secondary_mission_ids=("assassination", "bring_it_down"),
    )


def _champion_slayer_ability_index(*, datasheet_id: str) -> AbilityCatalogIndex:
    rule_ir = _champion_slayer_rule_ir()
    records = tuple(
        _champion_slayer_clause_record(
            rule_ir=rule_ir,
            clause_index=clause_index,
            datasheet_id=datasheet_id,
            trigger_kind=trigger_kind,
        )
        for clause_index, trigger_kind in (
            (0, TimingTriggerKind.AFTER_DICE_ROLL),
            (1, TimingTriggerKind.AFTER_UNIT_DESTROYED),
        )
    )
    return AbilityCatalogIndex.from_records(records)


def _champion_slayer_clause_record(
    *,
    rule_ir: RuleIR,
    clause_index: int,
    datasheet_id: str,
    trigger_kind: TimingTriggerKind,
) -> AbilityCatalogRecord:
    clause = rule_ir.clauses[clause_index]
    return AbilityCatalogRecord(
        record_id=(
            f"phase17d:test:catalog-ability:{datasheet_id}:champion-slayer:{clause.clause_id}"
        ),
        definition=AbilityDefinition(
            ability_id="champion-slayer",
            name="Champion Slayer",
            source_id="phase17d:test:champion-slayer",
            when_descriptor="Catalog generic rule IR.",
            effect_descriptor="Champion Slayer compound ability.",
            restrictions_descriptor="Datasheet ability source kind: datasheet.",
            timing=AbilityTimingDescriptor(trigger_kind=trigger_kind),
            handler_id=GENERIC_RULE_IR_ABILITY_HANDLER_ID,
            replay_payload=validate_json_value(
                {
                    "rule_ir": rule_ir.to_payload(),
                    "runtime_clause_id": clause.clause_id,
                }
            ),
        ),
        source_kind=AbilitySourceKind.DATASHEET,
        datasheet_id=datasheet_id,
    )


def _ability_record(
    record_id: str,
    source_kind: AbilitySourceKind,
    *,
    ability_id: str | None = None,
    faction_id: str | None = None,
    detachment_id: str | None = None,
    datasheet_id: str | None = None,
    wargear_id: str | None = None,
    weapon_profile_id: str | None = None,
    keyword_gate: KeywordGate | None = None,
) -> AbilityCatalogRecord:
    resolved_ability_id = ability_id or record_id
    return AbilityCatalogRecord(
        record_id=record_id,
        definition=AbilityDefinition(
            ability_id=resolved_ability_id,
            name=record_id,
            source_id=f"phase17d:test:{record_id}",
            when_descriptor="test timing",
            effect_descriptor="test effect",
            restrictions_descriptor="test restrictions",
            timing=AbilityTimingDescriptor(trigger_kind=TimingTriggerKind.ANY_PHASE),
            keyword_gate=KeywordGate() if keyword_gate is None else keyword_gate,
            handler_id=GENERIC_RULE_IR_ABILITY_HANDLER_ID,
        ),
        source_kind=source_kind,
        faction_id=faction_id,
        detachment_id=detachment_id,
        datasheet_id=datasheet_id,
        wargear_id=wargear_id,
        weapon_profile_id=weapon_profile_id,
    )


def _noop_rule_handler(
    rule_ir: RuleIR,
    clause: RuleClause,
    effect: RuleEffectSpec | None,
    context: RuleExecutionContext,
) -> RuleExecutionResult:
    del effect, context
    return RuleExecutionResult.applied(rule_ir, applied_clause_ids=(clause.clause_id,))


def _execution_context(
    *,
    state: GameState | None = None,
    event_log: EventLog | None = None,
    source_unit_instance_id: str | None = None,
    source_model_instance_id: str | None = None,
    target_unit_instance_ids: tuple[str, ...] = (),
    trigger_payload: JsonValue = None,
    phase: BattlePhaseKind | None = BattlePhaseKind.COMMAND,
    active_player_id: str | None = "player-a",
) -> RuleExecutionContext:
    return RuleExecutionContext(
        game_id="phase17d-game",
        player_id="player-a",
        battle_round=1,
        phase=phase,
        active_player_id=active_player_id,
        timing_window_id="phase17d:test-window",
        source_unit_instance_id=source_unit_instance_id,
        source_model_instance_id=source_model_instance_id,
        target_unit_instance_ids=target_unit_instance_ids,
        trigger_payload=trigger_payload,
        state=state,
        event_log=event_log,
    )


def _json_object(value: JsonValue) -> dict[str, JsonValue]:
    assert isinstance(value, dict)
    return value


def _event_payloads(
    decisions: DecisionController,
    event_type: str,
) -> tuple[dict[str, JsonValue], ...]:
    return tuple(
        _json_object(event.payload)
        for event in decisions.event_log.records
        if event.event_type == event_type
    )


def _battle_state() -> GameState:
    descriptor = RulesetDescriptor.warhammer_40000_eleventh()
    return GameState(
        game_id="phase17d-game",
        ruleset_descriptor_hash=descriptor.descriptor_hash,
        stage=GameLifecycleStage.BATTLE,
        setup_sequence=tuple(descriptor.setup_sequence.steps),
        battle_phase_sequence=tuple(descriptor.battle_phase_sequence.phases),
        setup_step_index=None,
        battle_phase_index=0,
        battle_round=1,
        active_player_id="player-a",
        player_ids=("player-a", "player-b"),
        turn_order=("player-a", "player-b"),
        tactical_secondary_draw_count=2,
        command_point_ledgers=initial_command_point_ledgers(("player-a", "player-b")),
        victory_point_ledgers=initial_victory_point_ledgers(("player-a", "player-b")),
    )


def _battle_state_with_scenario() -> GameState:
    scenario = _scenario()
    state = _battle_state()
    for army_definition in scenario.armies:
        state.record_army_definition(army_definition)
    state.battlefield_state = scenario.battlefield_state
    return state


def _battle_state_with_attached_leader_support() -> GameState:
    catalog = ArmyCatalog.phase9a_canonical_content_pack()
    state = _battle_state()
    state.record_army_definition(
        muster_army(
            catalog=catalog,
            request=_attached_leader_support_muster_request(catalog),
        )
    )
    return state


def _bodyguard_destroyed_split_state() -> GameState:
    state = _battle_state_with_attached_leader_support()
    state.recover_starting_strength_after_attached_unit_split(
        player_id="player-a",
        attached_unit_instance_id="attached-unit:army-alpha:bodyguard-unit",
        surviving_unit_instance_ids=(
            "army-alpha:leader-unit",
            "army-alpha:support-unit",
        ),
    )
    return state


def _battle_state_with_extra_friendly_unit() -> GameState:
    scenario = _scenario_with_extra_friendly_unit()
    state = _battle_state()
    for army_definition in scenario.armies:
        state.record_army_definition(army_definition)
    state.battlefield_state = scenario.battlefield_state
    return state


def _unit_by_id(state: GameState, unit_instance_id: str) -> UnitInstance:
    for army in state.army_definitions:
        for unit in army.units:
            if unit.unit_instance_id == unit_instance_id:
                return unit
    raise AssertionError(f"missing unit {unit_instance_id}")


def _weapon_profile(wargear_id: str) -> WeaponProfile:
    for wargear in ArmyCatalog.phase9a_canonical_content_pack().wargear:
        if wargear.wargear_id == wargear_id:
            return wargear.weapon_profiles[0]
    raise AssertionError(f"missing wargear {wargear_id}")


def _set_model_wounds(
    state: GameState,
    *,
    model_instance_id: str,
    wounds_remaining: int,
) -> None:
    updated_armies: list[ArmyDefinition] = []
    did_update = False
    for army in state.army_definitions:
        updated_units: list[UnitInstance] = []
        for unit in army.units:
            updated_models: list[ModelInstance] = []
            for model in unit.own_models:
                if model.model_instance_id != model_instance_id:
                    updated_models.append(model)
                    continue
                updated_models.append(replace(model, wounds_remaining=wounds_remaining))
                did_update = True
            updated_units.append(replace(unit, own_models=tuple(updated_models)))
        updated_armies.append(replace(army, units=tuple(updated_units)))
    if not did_update:
        raise AssertionError(f"missing model {model_instance_id}")
    state.army_definitions = updated_armies


def _destroy_model(state: GameState, *, model_instance_id: str) -> None:
    _set_model_wounds(state, model_instance_id=model_instance_id, wounds_remaining=0)
    assert state.battlefield_state is not None
    state.battlefield_state = state.battlefield_state.with_removed_models((model_instance_id,))


def _scenario() -> BattlefieldScenario:
    return create_deterministic_battlefield_scenario(
        battlefield_id="phase17d-battlefield",
        armies=_mustered_armies(),
    )


def _scenario_with_extra_friendly_unit() -> BattlefieldScenario:
    return create_deterministic_battlefield_scenario(
        battlefield_id="phase17d-battlefield-extra-friendly",
        armies=_mustered_armies_with_extra_friendly_unit(),
    )


def _mustered_armies() -> tuple[ArmyDefinition, ...]:
    catalog = ArmyCatalog.phase9a_canonical_content_pack()
    return (
        muster_army(
            catalog=catalog,
            request=_muster_request(
                catalog=catalog,
                player_id="player-a",
                army_id="army-alpha",
                unit_selection_id="intercessor-unit-1",
            ),
        ),
        muster_army(
            catalog=catalog,
            request=_muster_request(
                catalog=catalog,
                player_id="player-b",
                army_id="army-beta",
                unit_selection_id="intercessor-unit-2",
            ),
        ),
    )


def _mustered_armies_with_extra_friendly_unit() -> tuple[ArmyDefinition, ...]:
    catalog = ArmyCatalog.phase9a_canonical_content_pack()
    return (
        muster_army(
            catalog=catalog,
            request=_muster_request_with_unit_ids(
                catalog=catalog,
                player_id="player-a",
                army_id="army-alpha",
                unit_selection_ids=(
                    "intercessor-unit-1",
                    "intercessor-unit-3",
                ),
            ),
        ),
        muster_army(
            catalog=catalog,
            request=_muster_request(
                catalog=catalog,
                player_id="player-b",
                army_id="army-beta",
                unit_selection_id="intercessor-unit-2",
            ),
        ),
    )


def _muster_request(
    *,
    catalog: ArmyCatalog,
    player_id: str,
    army_id: str,
    unit_selection_id: str,
) -> ArmyMusterRequest:
    return _muster_request_with_unit_ids(
        catalog=catalog,
        player_id=player_id,
        army_id=army_id,
        unit_selection_ids=(unit_selection_id,),
    )


def _muster_request_with_unit_ids(
    *,
    catalog: ArmyCatalog,
    player_id: str,
    army_id: str,
    unit_selection_ids: tuple[str, ...],
) -> ArmyMusterRequest:
    return ArmyMusterRequest(
        army_id=army_id,
        player_id=player_id,
        catalog_id=catalog.catalog_id,
        source_package_id=catalog.source_package_id,
        ruleset_id=catalog.ruleset_id,
        detachment_selection=DetachmentSelection(
            faction_id="core-marine-force",
            detachment_ids=("core-combined-arms",),
        ),
        force_disposition_id="purge-the-foe",
        unit_selections=tuple(
            UnitMusterSelection(
                unit_selection_id=unit_selection_id,
                datasheet_id="core-intercessor-like-infantry",
                model_profile_selections=(
                    ModelProfileSelection(
                        model_profile_id="core-intercessor-like",
                        model_count=5,
                    ),
                ),
            )
            for unit_selection_id in unit_selection_ids
        ),
    )


def _attached_leader_support_muster_request(catalog: ArmyCatalog) -> ArmyMusterRequest:
    return ArmyMusterRequest(
        army_id="army-alpha",
        player_id="player-a",
        catalog_id=catalog.catalog_id,
        source_package_id=catalog.source_package_id,
        ruleset_id=catalog.ruleset_id,
        detachment_selection=DetachmentSelection(
            faction_id="core-marine-force",
            detachment_ids=("core-combined-arms",),
        ),
        force_disposition_id="purge-the-foe",
        unit_selections=(
            UnitMusterSelection(
                unit_selection_id="bodyguard-unit",
                datasheet_id="core-intercessor-like-infantry",
                model_profile_selections=(
                    ModelProfileSelection(
                        model_profile_id="core-intercessor-like",
                        model_count=5,
                    ),
                ),
            ),
            UnitMusterSelection(
                unit_selection_id="leader-unit",
                datasheet_id="core-character-leader",
                model_profile_selections=(
                    ModelProfileSelection(
                        model_profile_id="core-character-leader",
                        model_count=1,
                    ),
                ),
            ),
            UnitMusterSelection(
                unit_selection_id="support-unit",
                datasheet_id="core-character-support",
                model_profile_selections=(
                    ModelProfileSelection(
                        model_profile_id="core-character-support",
                        model_count=1,
                    ),
                ),
            ),
        ),
        attachment_declarations=(
            AttachmentDeclaration(
                source_unit_selection_id="leader-unit",
                bodyguard_unit_selection_id="bodyguard-unit",
            ),
            AttachmentDeclaration(
                source_unit_selection_id="support-unit",
                bodyguard_unit_selection_id="bodyguard-unit",
            ),
        ),
    )


def _with_unit_pose(
    battlefield_state: BattlefieldRuntimeState | None,
    *,
    unit_instance_id: str,
    pose: Pose,
) -> BattlefieldRuntimeState:
    if battlefield_state is None:
        raise AssertionError("test requires battlefield_state")
    unit_placement = battlefield_state.unit_placement_by_id(unit_instance_id)
    moved = UnitPlacement(
        army_id=unit_placement.army_id,
        player_id=unit_placement.player_id,
        unit_instance_id=unit_placement.unit_instance_id,
        model_placements=tuple(
            model_placement.with_pose(
                Pose.at(
                    pose.position.x + index * 1.5,
                    pose.position.y,
                    pose.position.z,
                    model_placement.pose.facing.degrees,
                )
            )
            for index, model_placement in enumerate(unit_placement.model_placements)
        ),
    )
    return battlefield_state.with_unit_placement(moved)


def _path_witness_for_unit_delta(
    *,
    state: GameState,
    unit_instance_id: str,
    dx: float,
    dy: float = 0.0,
) -> PathWitness:
    battlefield_state = state.battlefield_state
    if battlefield_state is None:
        raise AssertionError("test requires battlefield_state")
    unit_placement = battlefield_state.unit_placement_by_id(unit_instance_id)
    model_paths: list[tuple[str, tuple[Pose, ...]]] = []
    for placement in unit_placement.model_placements:
        start = placement.pose
        midpoint = Pose.at(
            start.position.x + (dx / 2.0),
            start.position.y + (dy / 2.0),
            start.position.z,
            facing_degrees=start.facing.degrees,
        )
        end = Pose.at(
            start.position.x + dx,
            start.position.y + dy,
            start.position.z,
            facing_degrees=start.facing.degrees,
        )
        model_paths.append((placement.model_instance_id, (start, midpoint, end)))
    return PathWitness.for_paths(tuple(model_paths))


def _with_unit_keywords(
    state: GameState,
    *,
    unit_instance_id: str,
    keywords: tuple[str, ...],
    faction_keywords: tuple[str, ...],
) -> GameState:
    army_definitions: list[ArmyDefinition] = []
    for army_definition in state.army_definitions:
        army_definitions.append(
            replace(
                army_definition,
                units=tuple(
                    replace(unit, keywords=keywords, faction_keywords=faction_keywords)
                    if unit.unit_instance_id == unit_instance_id
                    else unit
                    for unit in army_definition.units
                ),
            )
        )
    state.army_definitions = sorted(army_definitions, key=lambda army: army.player_id)
    return state
