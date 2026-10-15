from __future__ import annotations

from dataclasses import replace
from typing import cast

import pytest

from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.core.ruleset_descriptor import BattlePhaseKind, RulesetDescriptor
from warhammer40k_core.engine import (
    catalog_contextual_status_consumption as catalog_contextual_module,
)
from warhammer40k_core.engine import (
    catalog_tracked_target_runtime as catalog_tracked_target_runtime_module,
)
from warhammer40k_core.engine import tracked_targets as tracked_targets_module
from warhammer40k_core.engine.abilities import (
    GENERIC_RULE_IR_ABILITY_HANDLER_ID,
    AbilityCatalogIndex,
    AbilityCatalogRecord,
    AbilityDefinition,
    AbilitySourceKind,
    AbilityTimingDescriptor,
)
from warhammer40k_core.engine.army_mustering import ArmyDefinition, ArmyMusterRequest, muster_army
from warhammer40k_core.engine.battle_round_hooks import (
    BattleRoundStartRequestContext,
    BattleRoundStartResultContext,
)
from warhammer40k_core.engine.battle_shock import (
    BattleShockResult,
    BattleShockTestReason,
    BattleShockTestRequest,
)
from warhammer40k_core.engine.battle_shock_hooks import (
    BattleShockForcedTestContext,
    BattleShockOutcomeContext,
)
from warhammer40k_core.engine.catalog_battle_shock_runtime import (
    CATALOG_BATTLE_SHOCK_FAILED_HEAL_EVENT,
    CATALOG_BATTLE_SHOCK_FAILED_HEAL_ROLL_TYPE,
    CatalogBattleShockRerollRuntime,
    catalog_battle_shock_hook_bindings,
    catalog_forced_battle_shock_unit_ids,
    resolve_catalog_battle_shock_failed_heal,
)
from warhammer40k_core.engine.catalog_contextual_status_consumption import (
    CATALOG_IR_BATTLE_SHOCK_FAILED_HEAL_CONSUMER_ID,
    CATALOG_IR_BATTLE_SHOCK_FORCED_TEST_CONSUMER_ID,
    CATALOG_IR_HIT_ROLL_REROLL_CONSUMER_ID,
    CATALOG_IR_SHADOW_FORM_CHOICE_CONSUMER_ID,
    CATALOG_IR_SHADOW_OF_CHAOS_AURA_CONSUMER_ID,
    CATALOG_IR_SHOOTING_TARGET_RANGE_RESTRICTION_CONSUMER_ID,
    consumer_ids_for_clause,
    hook_ids_for_effect,
)
from warhammer40k_core.engine.catalog_rule_consumption import catalog_rule_clauses_from_record
from warhammer40k_core.engine.catalog_selected_target_test_modifiers import (
    CATALOG_SELECTED_TARGET_TEST_MODIFIER_HOOK_ID,
)
from warhammer40k_core.engine.catalog_shadow_form_runtime import (
    CATALOG_SHADOW_FORM_SELECTED_EVENT,
    CATALOG_SHADOW_FORM_SELECTION_EFFECT_KIND,
    CATALOG_SHADOW_FORM_SUBMISSION_KIND,
    CatalogShadowFormRuntime,
)
from warhammer40k_core.engine.catalog_tracked_target_runtime import CatalogTrackedTargetRuntime
from warhammer40k_core.engine.command_points import initial_command_point_ledgers
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.dice import DiceRollManager
from warhammer40k_core.engine.effects import (
    GENERIC_RULE_EFFECT_KIND,
    EffectExpiration,
    PersistingEffect,
)
from warhammer40k_core.engine.event_log import EventLog, JsonValue, canonical_json
from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.list_validation import DetachmentSelection, UnitMusterSelection
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError, GameLifecycleStage
from warhammer40k_core.engine.placement import create_deterministic_battlefield_scenario
from warhammer40k_core.engine.scoring import initial_victory_point_ledgers
from warhammer40k_core.engine.source_backed_rerolls import (
    SourceBackedRerollPermissionContext,
    source_backed_reroll_permission_context_for_unit,
)
from warhammer40k_core.engine.timing_windows import TimingTriggerKind
from warhammer40k_core.engine.tracked_targets import (
    SELECT_TRACKED_TARGET_DECISION_TYPE,
    TRACKED_TARGET_EXPIRED_EVENT_TYPE,
    TrackedTargetOwnerScope,
    TrackedTargetRecord,
    TrackedTargetRole,
    apply_select_tracked_target_decision,
    build_select_tracked_target_request,
    invalid_select_tracked_target_status,
    tracked_target_reroll_permission_context_for_unit,
)
from warhammer40k_core.engine.unit_destroyed_hooks import UnitDestroyedContext
from warhammer40k_core.engine.unit_state import BelowHalfStrengthContext, StartingStrengthRecord
from warhammer40k_core.engine.wargear_selections import ModelProfileSelection
from warhammer40k_core.rules.objective_terminology import ObjectiveRuleScope
from warhammer40k_core.rules.rule_compiler import compile_rule_source_text
from warhammer40k_core.rules.rule_ir import (
    RuleClause,
    RuleEffectKind,
    RuleEffectSpec,
    RuleIR,
    RuleTriggerKind,
)
from warhammer40k_core.rules.source_data import RuleSourceText
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    datasheet_keyword_lexicon_2026_06_14 as datasheet_keyword_lexicon_source,
)
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import faction_pack_rule_ir

PREY_TARGET_TEXT = (
    "At the start of the first battle round, select one enemy unit to be this model's "
    "prey. Each time a model in this model's unit makes a melee attack that targets "
    "its prey, you can re-roll the Wound roll. Each time this model's prey is "
    "destroyed, select one new enemy unit to be this model's prey."
)
SOURCE_KEYWORD_SEQUENCE_PARTS = (
    datasheet_keyword_lexicon_source.canonical_datasheet_keyword_sequence_parts()
)
BELAKOR_SOURCE_PACKAGE_ID = "gw-11e-chaos-daemons-datasheet-ir-2026-27"
BELAKOR_DARK_MASTER_ROW_ID = "000001148:5"
BELAKOR_SHADOW_FORM_ROW_ID = "000001148:6"
BELAKOR_WREATHED_IN_SHADOWS_ROW_ID = "000001148:8"
BELAKOR_PALL_OF_DESPAIR_ROW_ID = "000001148:9"
BELAKOR_SHADOW_LORD_ROW_ID = "000001148:10"
BELAKOR_SHADOW_FORM_SOURCE_ID = (
    f"{BELAKOR_SOURCE_PACKAGE_ID}:datasheet:{BELAKOR_SHADOW_FORM_ROW_ID}"
)
BELAKOR_WREATHED_IN_SHADOWS_SOURCE_ID = (
    f"{BELAKOR_SOURCE_PACKAGE_ID}:datasheet:{BELAKOR_WREATHED_IN_SHADOWS_ROW_ID}"
)
belakor_source_package = faction_pack_rule_ir.source_package_artifact(BELAKOR_SOURCE_PACKAGE_ID)
MIXED_QUARRY_TARGET_TEXT = (
    "At the start of the first battle round, select one enemy unit to be this model's "
    "quarry. Each time this model makes a melee attack that targets its quarry, "
    "re-roll Hit rolls. Each time this model makes a ranged attack that targets its "
    "quarry, re-roll Wound rolls."
)


def _record_selection(
    *,
    state: GameState,
    source_unit_instance_id: str,
    source_model_instance_id: str | None,
    target_unit_instance_id: str,
    owner_scope: TrackedTargetOwnerScope,
) -> None:
    state.record_tracked_target(
        TrackedTargetRecord(
            record_id=f"record:{owner_scope.value}",
            source_rule_id=f"rule:{owner_scope.value}",
            source_ability_id="ability:prey",
            source_clause_id="clause:select",
            source_effect_index=0,
            owner_player_id="player-a",
            source_unit_instance_id=source_unit_instance_id,
            source_model_instance_id=source_model_instance_id,
            owner_scope=owner_scope,
            role=TrackedTargetRole.PREY,
            supported_attack_roll_pairs=(("melee", "attack_sequence.wound"),),
            target_unit_instance_id=target_unit_instance_id,
            target_allegiance="enemy",
            target_lifecycle="until_destroyed",
            selected_battle_round=1,
            selection_request_id=f"request:{owner_scope.value}",
            selection_result_id=f"result:{owner_scope.value}",
            active=True,
        )
    )


def _battle_state_with_scenario(
    *,
    alpha_unit_count: int = 1,
    beta_unit_count: int = 1,
    alpha_datasheet_id: str = "core-intercessor-like-infantry",
    alpha_model_profile_id: str = "core-intercessor-like",
    alpha_model_count: int = 5,
) -> GameState:
    scenario = create_deterministic_battlefield_scenario(
        battlefield_id="tracked-target-battlefield",
        armies=_mustered_armies(
            alpha_unit_count=alpha_unit_count,
            beta_unit_count=beta_unit_count,
            alpha_datasheet_id=alpha_datasheet_id,
            alpha_model_profile_id=alpha_model_profile_id,
            alpha_model_count=alpha_model_count,
        ),
    )
    descriptor = RulesetDescriptor.warhammer_40000_eleventh()
    state = GameState(
        game_id="tracked-target-game",
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
    for army in scenario.armies:
        state.record_army_definition(army)
    state.battlefield_state = scenario.battlefield_state
    return state


def _mustered_armies(
    *,
    alpha_unit_count: int = 1,
    beta_unit_count: int = 1,
    alpha_datasheet_id: str = "core-intercessor-like-infantry",
    alpha_model_profile_id: str = "core-intercessor-like",
    alpha_model_count: int = 5,
) -> tuple[ArmyDefinition, ...]:
    catalog = ArmyCatalog.phase9a_canonical_content_pack()
    return (
        muster_army(
            catalog=catalog,
            request=_muster_request(
                catalog=catalog,
                player_id="player-a",
                army_id="army-alpha",
                unit_count=alpha_unit_count,
                datasheet_id=alpha_datasheet_id,
                model_profile_id=alpha_model_profile_id,
                model_count=alpha_model_count,
            ),
        ),
        muster_army(
            catalog=catalog,
            request=_muster_request(
                catalog=catalog,
                player_id="player-b",
                army_id="army-beta",
                unit_count=beta_unit_count,
            ),
        ),
    )


def _shared_target_record(
    *,
    record_id: str,
    catalog_record: AbilityCatalogRecord,
    source_unit_instance_id: str,
    source_model_instance_id: str,
    target_unit_instance_id: str,
) -> TrackedTargetRecord:
    return TrackedTargetRecord(
        record_id=record_id,
        source_rule_id=catalog_record.definition.source_id,
        source_ability_id=catalog_record.definition.ability_id,
        source_clause_id="tracked:initial-clause",
        source_effect_index=0,
        owner_player_id="player-a",
        source_unit_instance_id=source_unit_instance_id,
        source_model_instance_id=source_model_instance_id,
        owner_scope=TrackedTargetOwnerScope.THIS_MODEL,
        role=TrackedTargetRole.PREY,
        supported_attack_roll_pairs=(("melee", "attack_sequence.wound"),),
        target_unit_instance_id=target_unit_instance_id,
        target_allegiance="enemy",
        target_lifecycle="until_destroyed",
        selected_battle_round=1,
        selection_request_id=f"request:{record_id}",
        selection_result_id=f"result:{record_id}",
        active=True,
    )


def _tracked_target_destroyed_context(
    *,
    state: GameState,
    decisions: DecisionController,
    destroyed_unit_instance_id: str,
    destroyed_model_instance_id: str,
) -> UnitDestroyedContext:
    current_phase = state.current_battle_phase
    assert current_phase is not None
    return UnitDestroyedContext(
        sequencing_active_player_id=cast(str, state.active_player_id),
        state=state,
        decisions=decisions,
        completed_phase=current_phase,
        model_destroyed_event_id=f"event:destroyed:{destroyed_unit_instance_id}",
        model_destroyed_payload={
            "game_id": state.game_id,
            "battle_round": state.battle_round,
            "active_player_id": state.active_player_id,
            "phase": current_phase.value,
            "destroying_player_id": "player-a",
            "target_unit_instance_id": destroyed_unit_instance_id,
            "model_instance_id": destroyed_model_instance_id,
        },
        destroying_player_id="player-a",
        destroyed_unit_instance_id=destroyed_unit_instance_id,
        destroyed_player_id="player-b",
    )


def _muster_request(
    *,
    catalog: ArmyCatalog,
    player_id: str,
    army_id: str,
    unit_count: int = 1,
    datasheet_id: str = "core-intercessor-like-infantry",
    model_profile_id: str = "core-intercessor-like",
    model_count: int = 5,
) -> ArmyMusterRequest:
    if unit_count < 1:
        raise AssertionError("unit_count must be positive")
    if model_count < 1:
        raise AssertionError("model_count must be positive")
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
                unit_selection_id=(
                    f"{army_id}-unit" if unit_count == 1 else f"{army_id}-unit-{index}"
                ),
                datasheet_id=datasheet_id,
                model_profile_selections=(
                    ModelProfileSelection(
                        model_profile_id=model_profile_id,
                        model_count=model_count,
                    ),
                ),
            )
            for index in range(1, unit_count + 1)
        ),
    )


def _tracked_target_catalog_record(
    *,
    trigger_kind: TimingTriggerKind = TimingTriggerKind.AFTER_UNIT_DESTROYED,
    raw_text: str = PREY_TARGET_TEXT,
    source_id: str = "rule:tracked-target",
    include_reselection: bool = True,
) -> AbilityCatalogRecord:
    source = RuleSourceText.from_raw(
        objective_scope=ObjectiveRuleScope.CORE_RULES,
        source_id=source_id,
        raw_text=raw_text,
    )
    rule_ir = compile_rule_source_text(
        source,
        source_keyword_sequence_parts=SOURCE_KEYWORD_SEQUENCE_PARTS,
    ).rule_ir
    if not include_reselection:
        rule_ir = replace(
            rule_ir,
            clauses=tuple(
                clause
                for clause in rule_ir.clauses
                if clause.trigger is None
                or clause.trigger.kind is not RuleTriggerKind.UNIT_DESTROYED
            ),
        )
    return AbilityCatalogRecord(
        record_id="record:tracked-target",
        definition=AbilityDefinition(
            ability_id="ability:tracked-target",
            name="Tracked Target",
            source_id=source.source_id,
            when_descriptor="Battle-round start and tracked target destroyed.",
            effect_descriptor="Select prey and reselect when destroyed.",
            restrictions_descriptor="Enemy unit target.",
            timing=AbilityTimingDescriptor(trigger_kind=trigger_kind),
            handler_id=GENERIC_RULE_IR_ABILITY_HANDLER_ID,
            replay_payload=cast(JsonValue, {"rule_ir": rule_ir.to_payload()}),
        ),
        source_kind=AbilitySourceKind.DATASHEET,
        datasheet_id="core-intercessor-like-infantry",
    )


def _belakor_catalog_record(
    *,
    row_id: str,
    ability_id: str,
    name: str,
    datasheet_id: str = "core-intercessor-like-infantry",
) -> AbilityCatalogRecord:
    rule_ir = _belakor_rule_ir(row_id)
    return AbilityCatalogRecord(
        record_id=f"record:{ability_id}",
        definition=AbilityDefinition(
            ability_id=ability_id,
            name=name,
            source_id=rule_ir.source_id,
            when_descriptor="Source-backed Be'lakor runtime test ability.",
            effect_descriptor="Generic RuleIR effect.",
            restrictions_descriptor="Source-backed test restrictions.",
            timing=AbilityTimingDescriptor(trigger_kind=TimingTriggerKind.START_BATTLE_ROUND),
            handler_id=GENERIC_RULE_IR_ABILITY_HANDLER_ID,
            replay_payload=cast(JsonValue, {"rule_ir": rule_ir.to_payload()}),
        ),
        source_kind=AbilitySourceKind.DATASHEET,
        datasheet_id=datasheet_id,
    )


def _belakor_shadow_form_records(
    *,
    datasheet_id: str = "core-character-leader",
) -> tuple[AbilityCatalogRecord, ...]:
    return (
        _belakor_catalog_record(
            row_id=BELAKOR_SHADOW_FORM_ROW_ID,
            ability_id="ability:shadow-form",
            name="Shadow Form",
            datasheet_id=datasheet_id,
        ),
        _belakor_catalog_record(
            row_id=BELAKOR_WREATHED_IN_SHADOWS_ROW_ID,
            ability_id="ability:wreathed-in-shadows",
            name="Wreathed in Shadows",
            datasheet_id=datasheet_id,
        ),
        _belakor_catalog_record(
            row_id=BELAKOR_PALL_OF_DESPAIR_ROW_ID,
            ability_id="ability:pall-of-despair",
            name="Pall of Despair",
            datasheet_id=datasheet_id,
        ),
        _belakor_catalog_record(
            row_id=BELAKOR_SHADOW_LORD_ROW_ID,
            ability_id="ability:shadow-lord",
            name="Shadow Lord",
            datasheet_id=datasheet_id,
        ),
    )


def _belakor_rule_ir(row_id: str) -> RuleIR:
    payload = belakor_source_package.datasheet_rule_ir_payload_by_source_row_id(row_id)
    if payload is None:
        raise AssertionError(f"Missing Be'lakor RuleIR payload for row: {row_id}.")
    return RuleIR.from_payload(payload)


__all__: list[str] = []
__all__ += ["AbilityCatalogIndex", "AbilityCatalogRecord", "AbilityDefinition"]
__all__ += ["AbilitySourceKind", "AbilityTimingDescriptor", "ArmyCatalog", "ArmyDefinition"]
__all__ += ["BELAKOR_DARK_MASTER_ROW_ID", "BELAKOR_PALL_OF_DESPAIR_ROW_ID", "ArmyMusterRequest"]
__all__ += ["BELAKOR_SHADOW_FORM_ROW_ID", "BELAKOR_SHADOW_FORM_SOURCE_ID"]
__all__ += ["BELAKOR_SHADOW_LORD_ROW_ID", "BELAKOR_SOURCE_PACKAGE_ID"]
__all__ += ["BELAKOR_WREATHED_IN_SHADOWS_ROW_ID", "BELAKOR_WREATHED_IN_SHADOWS_SOURCE_ID"]
__all__ += ["BattlePhase", "BattlePhaseKind", "BattleRoundStartRequestContext"]
__all__ += ["BattleRoundStartResultContext", "BattleShockForcedTestContext"]
__all__ += ["BattleShockOutcomeContext", "BattleShockResult", "BattleShockTestReason"]
__all__ += ["BattleShockTestRequest", "BelowHalfStrengthContext"]
__all__ += ["CATALOG_BATTLE_SHOCK_FAILED_HEAL_EVENT"]
__all__ += ["CATALOG_BATTLE_SHOCK_FAILED_HEAL_ROLL_TYPE"]
__all__ += ["CATALOG_IR_BATTLE_SHOCK_FAILED_HEAL_CONSUMER_ID"]
__all__ += ["CATALOG_IR_BATTLE_SHOCK_FORCED_TEST_CONSUMER_ID"]
__all__ += ["CATALOG_IR_HIT_ROLL_REROLL_CONSUMER_ID", "CATALOG_IR_SHADOW_FORM_CHOICE_CONSUMER_ID"]
__all__ += ["CATALOG_IR_SHADOW_OF_CHAOS_AURA_CONSUMER_ID"]
__all__ += ["CATALOG_IR_SHOOTING_TARGET_RANGE_RESTRICTION_CONSUMER_ID"]
__all__ += ["CATALOG_SELECTED_TARGET_TEST_MODIFIER_HOOK_ID", "CATALOG_SHADOW_FORM_SELECTED_EVENT"]
__all__ += ["CATALOG_SHADOW_FORM_SELECTION_EFFECT_KIND", "CATALOG_SHADOW_FORM_SUBMISSION_KIND"]
__all__ += ["CatalogBattleShockRerollRuntime", "CatalogShadowFormRuntime"]
__all__ += ["CatalogTrackedTargetRuntime", "DecisionController", "DecisionResult"]
__all__ += ["DetachmentSelection", "DiceRollManager", "EffectExpiration", "EventLog"]
__all__ += ["GENERIC_RULE_EFFECT_KIND", "GENERIC_RULE_IR_ABILITY_HANDLER_ID"]
__all__ += ["GameLifecycleError", "GameLifecycleStage", "GameState", "JsonValue"]
__all__ += ["MIXED_QUARRY_TARGET_TEXT", "ModelProfileSelection", "ObjectiveRuleScope"]
__all__ += ["PREY_TARGET_TEXT", "PersistingEffect", "RuleClause", "RuleEffectKind"]
__all__ += ["RuleEffectSpec", "RuleIR", "RuleSourceText", "RuleTriggerKind", "RulesetDescriptor"]
__all__ += ["SELECT_TRACKED_TARGET_DECISION_TYPE", "SOURCE_KEYWORD_SEQUENCE_PARTS"]
__all__ += ["SourceBackedRerollPermissionContext", "StartingStrengthRecord"]
__all__ += ["TRACKED_TARGET_EXPIRED_EVENT_TYPE", "TimingTriggerKind", "TrackedTargetOwnerScope"]
__all__ += ["TrackedTargetRecord", "TrackedTargetRole", "UnitDestroyedContext"]
__all__ += ["UnitMusterSelection", "_battle_state_with_scenario", "_belakor_catalog_record"]
__all__ += ["_belakor_rule_ir", "_belakor_shadow_form_records", "_muster_request"]
__all__ += ["_mustered_armies", "_record_selection", "_shared_target_record"]
__all__ += ["_tracked_target_catalog_record", "_tracked_target_destroyed_context"]
__all__ += ["apply_select_tracked_target_decision", "belakor_source_package"]
__all__ += ["build_select_tracked_target_request", "canonical_json", "cast"]
__all__ += ["catalog_battle_shock_hook_bindings", "catalog_contextual_module"]
__all__ += ["catalog_forced_battle_shock_unit_ids", "catalog_rule_clauses_from_record"]
__all__ += ["catalog_tracked_target_runtime_module", "compile_rule_source_text"]
__all__ += ["consumer_ids_for_clause", "create_deterministic_battlefield_scenario"]
__all__ += ["datasheet_keyword_lexicon_source", "faction_pack_rule_ir", "hook_ids_for_effect"]
__all__ += ["initial_command_point_ledgers", "initial_victory_point_ledgers"]
__all__ += ["invalid_select_tracked_target_status", "muster_army", "pytest", "replace"]
__all__ += ["resolve_catalog_battle_shock_failed_heal"]
__all__ += ["source_backed_reroll_permission_context_for_unit"]
__all__ += ["tracked_target_reroll_permission_context_for_unit", "tracked_targets_module"]
