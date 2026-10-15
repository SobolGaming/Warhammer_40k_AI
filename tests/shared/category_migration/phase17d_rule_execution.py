from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import replace
from typing import Any, cast

import pytest

from tests.setup_completion_helpers import ensure_army_mustered_events_for_fixture
from tests.unit_keyword_helpers import with_unit_keywords
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
from warhammer40k_core.engine.army_mustering import ArmyDefinition, ArmyMusterRequest, muster_army
from warhammer40k_core.engine.battlefield_state import (
    BattlefieldPlacementKind,
    BattlefieldRuntimeState,
    BattlefieldScenario,
    UnitPlacement,
)
from warhammer40k_core.engine.catalog_any_phase_once_per_battle import (
    SELECT_CATALOG_ANY_PHASE_ONCE_PER_BATTLE_DECISION_TYPE,
)
from warhammer40k_core.engine.catalog_datasheet_rule_runtime import CatalogDatasheetRuleRuntime
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
from warhammer40k_core.engine.charge_required_targets import (
    CHARGE_MOVE_REQUIRED_TARGET_UNIT_INSTANCE_IDS_KEY,
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
from warhammer40k_core.engine.damage_allocation import destroy_model_by_rule
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
from warhammer40k_core.engine.game_state import (
    GameConfig,
    GameState,
    SecondaryMissionChoice,
    SecondaryMissionMode,
)
from warhammer40k_core.engine.generic_rule_attack_hooks import generic_rule_wound_roll_modifier
from warhammer40k_core.engine.lifecycle import GameLifecycle
from warhammer40k_core.engine.lifecycle_reaction_queue import validate_reaction_queue_consistency
from warhammer40k_core.engine.list_validation import (
    AttachmentDeclaration,
    DetachmentSelection,
    UnitMusterSelection,
)
from warhammer40k_core.engine.mission_setup import MissionSetup
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
    FIGHTS_FIRST_CHARGE_EFFECT_KIND,
    ChargeMoveProposal,
)
from warhammer40k_core.engine.placement import create_deterministic_battlefield_scenario
from warhammer40k_core.engine.psychic_ability_usage import psychic_uses
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
from warhammer40k_core.engine.rules_unit_effects import rules_unit_persisting_effects
from warhammer40k_core.engine.runtime_modifiers import (
    HitRollModifierContext,
    RuntimeModifierRegistry,
    WeaponProfileModifierContext,
    WoundRollModifierContext,
)
from warhammer40k_core.engine.scoring import initial_victory_point_ledgers
from warhammer40k_core.engine.selected_target_context import SELECTED_TARGET_UNIT_CONTEXT_KEY
from warhammer40k_core.engine.stratagems import (
    STRATAGEM_TARGET_PROPOSAL_DECISION_TYPE,
    stratagem_decline_payload,
)
from warhammer40k_core.engine.target_restriction_hooks import ChargeTargetRestrictionHookRegistry
from warhammer40k_core.engine.timing_windows import (
    ReactionWindow,
    TimingTriggerKind,
    TimingWindow,
    TimingWindowDescriptor,
)
from warhammer40k_core.engine.unit_factory import ModelInstance, UnitInstance
from warhammer40k_core.engine.wargear_selections import ModelProfileSelection
from warhammer40k_core.geometry.pathing import PathWitness
from warhammer40k_core.geometry.pose import Pose
from warhammer40k_core.rules.mission_pack_import import chapter_approved_2026_27_mission_pack
from warhammer40k_core.rules.objective_terminology import ObjectiveRuleScope
from warhammer40k_core.rules.parsed_tokens import TextSpan
from warhammer40k_core.rules.rule_compiler import CompiledRuleSource, compile_rule_source_text
from warhammer40k_core.rules.rule_ir import (
    RuleClause,
    RuleCondition,
    RuleConditionKind,
    RuleEffectKind,
    RuleEffectSpec,
    RuleIR,
    RuleIRError,
    RuleIRPayload,
    RuleParameter,
    RuleTrigger,
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


def _next_psychic_request(session: LocalGameSession) -> DecisionRequest:
    for index in range(8):
        status = session.advance_until_decision_or_terminal()
        request = status.decision_request
        assert request is not None, status.payload
        if request.decision_type != "resolve_sequencing_order":
            return request
        participants = _json_object(request.payload)["participants"]
        assert isinstance(participants, list)
        selected = min(
            (_json_object(participant) for participant in participants),
            key=lambda participant: str(participant["payload"]),
        )
        option = next(
            option
            for option in request.options
            if _json_object(option.payload)["selected_participant_id"] == selected["participant_id"]
        )
        session.submit_option(
            request_id=request.request_id,
            option_id=option.option_id,
            result_id=f"psychic-order:{request.request_id}:{index}",
        )
    raise AssertionError("Psychic timing order did not reach its selected rule")


def _psychic_level_session(
    *, attached: bool = False, any_phase: bool = False, start_phase: BattlePhase = BattlePhase.FIGHT
) -> LocalGameSession:
    text = ONCE_PER_BATTLE_FIGHT_BOOST_TEXT
    if any_phase:
        text = text.replace("at the start of the Fight phase", "at the start of any phase")
    descriptor = _generic_catalog_descriptor(
        "Might (Psychic level 1): " + text, ability_id="psychic-level-fight-boost"
    )
    if any_phase:
        # The catalog can carry a typed any-phase trigger independently of text-parser coverage.
        ir = RuleIR.from_payload(cast(RuleIRPayload, descriptor.rule_ir_payload))
        phrase = "at the start of any phase"
        start = ir.normalized_text.index(phrase)
        trigger = RuleTrigger(
            kind=RuleTriggerKind.TIMING_WINDOW,
            source_span=TextSpan(text=phrase, start=start, end=start + len(phrase)),
            parameters=(RuleParameter("edge", "start"), RuleParameter("phase", "any")),
        )
        ir = replace(ir, clauses=tuple(replace(clause, trigger=trigger) for clause in ir.clauses))
        descriptor = replace(descriptor, rule_ir_payload=cast(CatalogJsonObject, ir.to_payload()))
    catalog = ArmyCatalog.phase9a_canonical_content_pack()
    source_sheets = (
        {"core-character-leader", "core-character-support"}
        if attached
        else {"core-intercessor-like-infantry"}
    )
    catalog = replace(
        catalog,
        datasheets=tuple(
            replace(
                sheet,
                keywords=replace(sheet.keywords, keywords=(*sheet.keywords.keywords, "PSYKER")),
                abilities=(*sheet.abilities, descriptor),
            )
            if sheet.datasheet_id in source_sheets
            else sheet
            for sheet in catalog.datasheets
        ),
    )
    config = _setup_reactive_config(catalog)
    if attached:
        config = replace(
            config,
            army_muster_requests=(
                _attached_leader_support_muster_request(catalog),
                replace(
                    config.army_muster_requests[1],
                    unit_selections=(
                        UnitMusterSelection(
                            unit_selection_id="enemy-psyker",
                            datasheet_id="core-character-leader",
                            model_profile_selections=(
                                ModelProfileSelection(
                                    model_profile_id="core-character-leader",
                                    model_count=1,
                                ),
                            ),
                        ),
                    ),
                ),
            ),
        )
    armies = tuple(
        muster_army(catalog=catalog, request=request) for request in config.army_muster_requests
    )
    state = _battle_state()
    for army in armies:
        state.record_army_definition(army)
    state.battlefield_state = create_deterministic_battlefield_scenario(
        battlefield_id="psychic-level",
        armies=armies,
    ).battlefield_state
    state.battle_phase_index = state.battle_phase_sequence.index(start_phase)
    for player_id in state.player_ids:
        state.record_secondary_mission_choice(
            SecondaryMissionChoice(
                player_id=player_id,
                mode=SecondaryMissionMode.FIXED,
                fixed_mission_ids=("assassination", "bring_it_down"),
            )
        )
    decisions = DecisionController()
    ensure_army_mustered_events_for_fixture(state, decisions=decisions)
    return LocalGameSession(
        lifecycle=GameLifecycle.from_payload(
            cast(
                Any,
                {
                    "config": config.to_payload(),
                    "parameterized_movement_proposals": True,
                    "state": state.to_payload(),
                    "decisions": decisions.to_payload(),
                    "reaction_queue": ReactionQueue().to_payload(),
                },
            )
        )
    )


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
        result_id="phase17d-setup-reactive-charge-action",
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
            "player_id": "player-a",
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
        spatial_context_hash=state.physical_proposal_context_hash(),
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
        spatial_context_hash=state.physical_proposal_context_hash(),
        placement_kinds=(BattlefieldPlacementKind.STRATEGIC_RESERVES,),
        context={"source_kind": "ordinary_reinforcement"},
    ).to_decision_request()


def _compiled(raw_text: str) -> CompiledRuleSource:
    return compile_rule_source_text(
        RuleSourceText.from_raw(
            objective_scope=ObjectiveRuleScope.CORE_RULES,
            source_id=f"phase17d:{raw_text.lower()}",
            raw_text=raw_text,
        ),
        source_keyword_sequence_parts=SOURCE_KEYWORD_SEQUENCE_PARTS,
    )


def _rule_ir_with_aura_object_reference(
    rule_ir: RuleIR,
    *,
    object_reference: str | None,
) -> RuleIR:
    updated_clauses: list[RuleClause] = []
    updated_distance_condition = False
    for clause in rule_ir.clauses:
        updated_conditions: list[RuleCondition] = []
        for condition in clause.conditions:
            if condition.kind is not RuleConditionKind.DISTANCE_PREDICATE:
                updated_conditions.append(condition)
                continue
            parameters = tuple(
                parameter
                for parameter in condition.parameters
                if parameter.key != "object_reference"
            )
            if object_reference is not None:
                parameters = (*parameters, RuleParameter("object_reference", object_reference))
            updated_conditions.append(replace(condition, parameters=parameters))
            updated_distance_condition = True
        updated_clauses.append(replace(clause, conditions=tuple(updated_conditions)))
    if not updated_distance_condition:
        raise AssertionError("test RuleIR requires a distance predicate")
    return replace(rule_ir, clauses=tuple(updated_clauses))


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
            objective_scope=ObjectiveRuleScope.CORE_RULES,
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
            objective_scope=ObjectiveRuleScope.CORE_RULES,
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
    fly: bool = False,
) -> tuple[GameState, ArmyCatalog, AbilityCatalogIndex]:
    descriptor = _generic_catalog_descriptor(
        SETUP_REACTIVE_SHOOT_CHARGE_TEXT,
        ability_id="setup-reactive-shoot-charge",
    )
    catalog = _catalog_with_descriptor(descriptor)
    if fly:
        catalog = replace(
            catalog,
            datasheets=tuple(
                replace(
                    sheet,
                    keywords=replace(sheet.keywords, keywords=(*sheet.keywords.keywords, "FLY")),
                )
                for sheet in catalog.datasheets
            ),
        )
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
        for model in source_unit.own_models[1:]:
            _destroy_model(state, model_instance_id=model.model_instance_id)
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
    effect_index: int | None,
) -> RuleExecutionResult:
    del effect, context, effect_index
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
    record_persisting_effects: bool = True,
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
        record_persisting_effects=record_persisting_effects,
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
        battlefield_state=BattlefieldRuntimeState(
            battlefield_id="phase17d-battlefield",
            battlefield_width_inches=60.0,
            battlefield_depth_inches=44.0,
            placed_armies=(),
        ),
        mission_setup=_mission_setup(),
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


def _bodyguard_destroyed_attached_state() -> GameState:
    state = _battle_state_with_attached_leader_support()
    bodyguard = _unit_by_id(state, "army-alpha:bodyguard-unit")
    for model_instance_id in bodyguard.own_model_ids():
        destroy_model_by_rule(
            state=state,
            model_instance_id=model_instance_id,
            remove_from_battlefield=False,
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
        force_disposition_id=("take-and-hold" if player_id == "player-a" else "purge-the-foe"),
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
        force_disposition_id="take-and-hold",
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


def _with_unit_model_poses(
    battlefield_state: BattlefieldRuntimeState | None,
    *,
    unit_instance_id: str,
    poses: tuple[Pose, ...],
) -> BattlefieldRuntimeState:
    if battlefield_state is None:
        raise AssertionError("test requires battlefield_state")
    unit_placement = battlefield_state.unit_placement_by_id(unit_instance_id)
    if len(poses) != len(unit_placement.model_placements):
        raise AssertionError("test pose count must match model placement count")
    moved = replace(
        unit_placement,
        model_placements=tuple(
            model_placement.with_pose(pose)
            for model_placement, pose in zip(unit_placement.model_placements, poses, strict=True)
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
                    with_unit_keywords(unit, keywords=keywords, faction_keywords=faction_keywords)
                    if unit.unit_instance_id == unit_instance_id
                    else unit
                    for unit in army_definition.units
                ),
            )
        )
    state.army_definitions = sorted(army_definitions, key=lambda army: army.player_id)
    return state


__all__: list[str] = []
__all__ += ["AbilityCatalogIndex", "AbilityCatalogRecord", "AbilityDefinition"]
__all__ += ["AbilityExecutionContext", "AbilityResolutionStatus", "AbilitySourceKind"]
__all__ += ["AbilityTimingDescriptor", "Any", "ArmyCatalog", "ArmyDefinition"]
__all__ += ["ArmyMusterRequest", "AttachmentDeclaration", "BattlePhase", "BattlePhaseKind"]
__all__ += ["BattlefieldPlacementKind", "BattlefieldRuntimeState", "BattlefieldScenario"]
__all__ += ["CATALOG_SETUP_REACTIVE_SOURCE_KIND"]
__all__ += ["CHARGE_MOVE_REQUIRED_TARGET_UNIT_INSTANCE_IDS_KEY", "CatalogAbilitySourceKind"]
__all__ += ["CatalogAbilitySupport", "CatalogDatasheetRuleRuntime", "CatalogJsonObject"]
__all__ += ["ChargeMoveProposal", "ChargeTargetRestrictionHookRegistry", "CommandPointLedger"]
__all__ += ["CommandPointRuleMutationResult", "CommandPointSourceKind", "CompiledRuleSource"]
__all__ += ["DatasheetAbilityDescriptor", "DecisionController", "DecisionOption"]
__all__ += ["DecisionRequest", "DecisionResult", "DetachmentSelection", "EffectError"]
__all__ += ["EffectExpiration", "EventLog", "EventStreamCursor"]
__all__ += ["FIGHTS_FIRST_CHARGE_EFFECT_KIND", "GENERIC_RULE_IR_ABILITY_HANDLER_ID", "GameConfig"]
__all__ += ["GameLifecycle", "GameLifecycleError", "GameLifecycleStage", "GameState"]
__all__ += ["HitRollModifierContext", "JsonValue", "KeywordGate", "LifecycleStatusKind"]
__all__ += ["MOVEMENT_PROPOSAL_DECISION_TYPE", "LocalGameSession", "MissionSetup"]
__all__ += ["ModelInstance", "ModelProfileSelection", "MovementMode", "MovementProposalRequest"]
__all__ += ["ONCE_PER_BATTLE_FIGHT_BOOST_TEXT", "ObjectiveRuleScope"]
__all__ += ["PLACEMENT_PROPOSAL_DECISION_TYPE", "ParameterizedSubmission", "PathWitness", "Pose"]
__all__ += ["RULE_FREQUENCY_LIMIT_CONSUMED_EVENT", "ProposalKind", "ReactionQueue"]
__all__ += ["ReactionWindow", "ReplayRunStatus", "ReplayRunner", "RuleClause", "RuleCondition"]
__all__ += ["RuleConditionKind", "RuleEffectKind", "RuleEffectSpec", "RuleExecutionContext"]
__all__ += ["RuleExecutionRegistry", "RuleExecutionResult", "RuleExecutionStatus", "RuleIR"]
__all__ += ["RuleIRError", "RuleIRPayload", "RuleParameter", "RuleRuntimeBinding"]
__all__ += ["RuleSourceText", "RuleTrigger", "RuleTriggerKind", "RulesetDescriptor"]
__all__ += ["SELECTED_TARGET_UNIT_CONTEXT_KEY", "RuntimeModifierRegistry"]
__all__ += ["SELECT_CATALOG_ANY_PHASE_ONCE_PER_BATTLE_DECISION_TYPE"]
__all__ += ["SELECT_CATALOG_SETUP_REACTIVE_SHOOT_CHARGE_DECISION_TYPE"]
__all__ += ["SELECT_FACTION_RULE_FIGHT_PHASE_START_OPTION_DECISION_TYPE"]
__all__ += ["SETUP_REACTIVE_SHOOT_CHARGE_TEXT", "SOURCE_KEYWORD_SEQUENCE_PARTS"]
__all__ += ["STRATAGEM_TARGET_PROPOSAL_DECISION_TYPE", "SecondaryMissionChoice"]
__all__ += ["SecondaryMissionMode", "TextSpan", "TimingTriggerKind", "TimingWindow"]
__all__ += ["TimingWindowDescriptor", "UnitInstance", "UnitMusterSelection", "UnitPlacement"]
__all__ += ["WeaponKeyword", "WeaponProfile", "WeaponProfileModifierContext"]
__all__ += ["WoundRollModifierContext", "_ability_record", "_append_setup_reactive_arrival_event"]
__all__ += ["_attached_leader_support_muster_request", "_battle_state"]
__all__ += ["_battle_state_with_attached_leader_support"]
__all__ += ["_battle_state_with_extra_friendly_unit", "_battle_state_with_scenario"]
__all__ += ["_bodyguard_destroyed_attached_state", "_catalog_with_champion_slayer_ability"]
__all__ += ["_catalog_with_descriptor", "_champion_slayer_ability_index"]
__all__ += ["_champion_slayer_clause_record", "_champion_slayer_descriptor"]
__all__ += ["_champion_slayer_rule_ir", "_command_point_spend_rule_ir", "_compiled"]
__all__ += ["_desperate_escape_modifier_rule_ir", "_destroy_model", "_event_payloads"]
__all__ += ["_execution_context", "_generic_catalog_descriptor", "_json_object", "_mission_setup"]
__all__ += ["_muster_request", "_muster_request_with_unit_ids", "_mustered_armies"]
__all__ += ["_mustered_armies_with_extra_friendly_unit", "_next_psychic_request"]
__all__ += ["_non_reaction_movement_request", "_non_reaction_placement_request"]
__all__ += ["_noop_rule_handler", "_parameterized_result_for_request"]
__all__ += ["_path_witness_for_unit_delta", "_psychic_level_session"]
__all__ += ["_reaction_queue_consistency_fixture", "_reaction_queue_window"]
__all__ += ["_record_decision_result", "_request_setup_reactive_lifecycle_action"]
__all__ += ["_rule_ir_with_aura_object_reference", "_scenario"]
__all__ += ["_scenario_with_extra_friendly_unit", "_set_model_wounds"]
__all__ += ["_setup_reactive_charge_move_request", "_setup_reactive_config"]
__all__ += ["_setup_reactive_lifecycle", "_setup_reactive_single_model_state"]
__all__ += ["_skullmaster_fury_text", "_unit_by_id", "_weapon_profile", "_with_unit_keywords"]
__all__ += ["_with_unit_model_poses", "_with_unit_pose"]
__all__ += ["apply_catalog_setup_reactive_charge_move"]
__all__ += ["apply_catalog_setup_reactive_shoot_charge_result"]
__all__ += ["apply_command_point_rule_mutation", "build_player_ability_index", "cast"]
__all__ += ["catalog_ability_records_from_catalog"]
__all__ += ["catalog_restore_lost_wounds_after_destroying_unit"]
__all__ += ["catalog_wound_roll_reroll_permission_for_attack"]
__all__ += ["chapter_approved_2026_27_mission_pack", "command_point_operation_and_delta"]
__all__ += ["command_point_operation_shape_reason", "command_point_rule_unavailable_reason"]
__all__ += ["compile_rule_source_text", "copy", "create_deterministic_battlefield_scenario"]
__all__ += ["datasheet_keyword_lexicon_source", "default_ability_handler_registry"]
__all__ += ["default_rule_execution_registry", "destroy_model_by_rule"]
__all__ += ["ensure_army_mustered_events_for_fixture", "execute_abilities_from_index"]
__all__ += ["execute_rule_ir", "generic_rule_persisting_effect"]
__all__ += ["generic_rule_wound_roll_modifier", "hashlib", "initial_command_point_ledgers"]
__all__ += ["initial_victory_point_ledgers", "invalid_catalog_setup_reactive_charge_move_status"]
__all__ += ["invalid_catalog_setup_reactive_shoot_charge_status"]
__all__ += ["is_catalog_setup_reactive_charge_move_request", "json", "muster_army"]
__all__ += ["parameter_payload", "psychic_uses", "pytest", "replace"]
__all__ += ["request_catalog_setup_reactive_shoot_charge_if_available"]
__all__ += ["rule_execution_status_from_token", "rule_ir_from_execution_payload"]
__all__ += ["rules_unit_persisting_effects", "scoped_rule_ir_from_execution_payload"]
__all__ += ["stratagem_decline_payload", "validate_json_value"]
__all__ += ["validate_reaction_queue_consistency", "with_unit_keywords"]
