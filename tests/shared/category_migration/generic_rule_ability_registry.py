from __future__ import annotations

import copy
from collections.abc import Callable
from dataclasses import replace
from typing import cast

import pytest

from tests.unit_keyword_helpers import with_unit_keywords
from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.core.attributes import Characteristic, CharacteristicValue
from warhammer40k_core.core.datasheet import BaseSizeDefinition
from warhammer40k_core.core.model_keywords import ModelKeywordAssignment
from warhammer40k_core.core.modifiers import ModifierOperation, ModifierTerm
from warhammer40k_core.core.ruleset_descriptor import RulesetDescriptor
from warhammer40k_core.core.weapon_profiles import WeaponKeyword
from warhammer40k_core.engine import generic_detachment_rule_effects as generic_detachment_effects
from warhammer40k_core.engine import (
    generic_rule_advance_move_lifecycle_hooks as advance_move_lifecycle_hooks,
)
from warhammer40k_core.engine import (
    generic_rule_lifecycle_hook_handlers,
    generic_rule_lifecycle_hooks,
    generic_rule_selected_to_fight_effects,
)
from warhammer40k_core.engine.advance_eligibility_hooks import AdvanceEligibilityContext
from warhammer40k_core.engine.advance_hooks import AdvanceMoveContext, AdvanceMoveGrant
from warhammer40k_core.engine.army_mustering import (
    ArmyDefinition,
    ArmyMusterRequest,
    EnhancementAssignment,
)
from warhammer40k_core.engine.battle_formation_hooks import (
    BattleFormationRequestContext,
    BattleFormationResultContext,
)
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.effects import (
    EffectExpiration,
    PersistingEffect,
    generic_rule_persisting_effect,
)
from warhammer40k_core.engine.enhancement_effects import EnhancementEffectContext
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.faction_content.activation import RuntimeContentActivation
from warhammer40k_core.engine.faction_content.warhammer_40000_11th.aeldari.detachments.corsair_coterie import (  # noqa: E501 - canonical source module path
    enhancements as corsair_enhancements,
)
from warhammer40k_core.engine.faction_content.warhammer_40000_11th.chaos_space_marines import (
    army_rule as dark_pacts,
)
from warhammer40k_core.engine.faction_content.warhammer_40000_11th.emperors_children.detachments.court_of_the_phoenician import (  # noqa: E501 - canonical source module path
    rule as court_rule,
)
from warhammer40k_core.engine.fall_back_hooks import FallBackEligibilityContext
from warhammer40k_core.engine.fight_activation_abilities import FightActivationAbilityContext
from warhammer40k_core.engine.fight_phase_start_hooks import (
    FightPhaseStartRequestContext,
    FightPhaseStartResultContext,
)
from warhammer40k_core.engine.fight_unit_selected_hooks import FightUnitSelectedContext
from warhammer40k_core.engine.game_state import GameConfig, GameState
from warhammer40k_core.engine.generic_rule_ability_effects import (
    generic_rule_ability_effects_for_unit,
    rule_ir_grants_any_ability,
)
from warhammer40k_core.engine.generic_rule_ability_registry import (
    GenericRuleAbilityHookFamily,
    GenericRuleAbilityRegistry,
    GenericRuleAbilitySource,
)
from warhammer40k_core.engine.generic_rule_ability_registry_defaults import (
    DEFAULT_GENERIC_RULE_ABILITY_REGISTRY,
)
from warhammer40k_core.engine.list_validation import DetachmentSelection, UnitMusterSelection
from warhammer40k_core.engine.movement_end_surge_hooks import MovementEndSurgeContext
from warhammer40k_core.engine.phase import (
    BattlePhase,
    GameLifecycleError,
    GameLifecycleStage,
    SetupStep,
)
from warhammer40k_core.engine.reserve_arrival_hooks import ReserveArrivalDistanceContext
from warhammer40k_core.engine.rule_execution import RuleExecutionResult, RuleExecutionStatus
from warhammer40k_core.engine.runtime_modifiers import (
    ObjectiveControlModifierContext,
    SaveOptionModifierContext,
)
from warhammer40k_core.engine.shooting_unit_selected_hooks import ShootingUnitSelectedContext
from warhammer40k_core.engine.sticky_objective_control import PhaseEndObjectiveControlContext
from warhammer40k_core.engine.stratagem_cost_choice_hooks import (
    StratagemCostChoiceRequestContext,
    StratagemCostChoiceResultContext,
)
from warhammer40k_core.engine.stratagem_cost_modifiers import StratagemCostModifierContext
from warhammer40k_core.engine.stratagems import (
    CORE_FIRE_OVERWATCH_HANDLER_ID,
    StratagemCategory,
    StratagemDefinition,
    StratagemEligibilityContext,
    StratagemTargetBinding,
    StratagemTargetKind,
    StratagemTargetSpec,
    StratagemTimingDescriptor,
)
from warhammer40k_core.engine.target_restriction_hooks import ShootingTargetRestrictionContext
from warhammer40k_core.engine.timing_windows import TimingTriggerKind
from warhammer40k_core.engine.turn_end_hooks import TurnEndRequestContext, TurnEndResultContext
from warhammer40k_core.engine.unit_destroyed_hooks import UnitDestroyedContext
from warhammer40k_core.engine.unit_factory import ModelInstance, UnitInstance
from warhammer40k_core.engine.unit_state import StartingStrengthRecord
from warhammer40k_core.engine.wargear_selections import ModelProfileSelection
from warhammer40k_core.geometry.model_geometry import ModelGeometry
from warhammer40k_core.rules.rule_ir import RuleEffectKind, RuleIR, RuleTargetKind
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    faction_aeldari_corsair_coterie_ir_support_2026_27 as corsair_ir,
)
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    faction_aeldari_path_of_the_outcast_ir_support_2026_27 as path_outcast_ir,
)
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    faction_blood_legion_ir_support_2026_27 as blood_legion_ir,
)
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    faction_court_of_the_phoenician_ir_support_2026_27 as court_ir,
)
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    faction_execution_2026_27,
    faction_generic_ir_support_2026_27,
)
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    faction_shadow_legion_ir_support_2026_27 as shadow_legion_ir,
)
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    faction_warptide_ir_support_2026_27 as warptide_ir,
)

_RANGERS_UNIT_ID = "army-a:rangers"
_SHROUD_RUNNERS_UNIT_ID = "army-a:shroud-runners"
_ENEMY_UNIT_ID = "army-b:target"
_WARPTIDE_UNIT_ID = "army-a:daemonettes"


def _raise_selected_to_fight_payload_error(
    *,
    case: str,
    payload: dict[str, JsonValue],
) -> None:
    effect = cast(dict[str, JsonValue], payload["effect"])
    parameters = cast(list[JsonValue], effect["parameters"])
    if case == "missing_effect":
        payload["effect"] = None
        generic_rule_selected_to_fight_effects._effect_kind(  # pyright: ignore[reportPrivateUsage]
            payload
        )
    elif case == "missing_kind":
        effect["kind"] = None
        generic_rule_selected_to_fight_effects._effect_kind(  # pyright: ignore[reportPrivateUsage]
            payload
        )
    elif case == "unknown_kind":
        effect["kind"] = "unsupported"
        generic_rule_selected_to_fight_effects._effect_kind(  # pyright: ignore[reportPrivateUsage]
            payload
        )
    elif case == "parameters_not_list":
        effect["parameters"] = None
        generic_rule_selected_to_fight_effects._effect_parameters(  # pyright: ignore[reportPrivateUsage]
            payload
        )
    elif case == "parameter_not_object":
        effect["parameters"] = ["invalid"]
        generic_rule_selected_to_fight_effects._effect_parameters(  # pyright: ignore[reportPrivateUsage]
            payload
        )
    elif case == "parameter_missing_key":
        effect["parameters"] = [{"value": 1}]
        generic_rule_selected_to_fight_effects._effect_parameters(  # pyright: ignore[reportPrivateUsage]
            payload
        )
    elif case == "duplicate_parameter":
        parameters.append({"key": "mortal_wounds_dice_quantity", "value": 1})
        generic_rule_selected_to_fight_effects._effect_parameters(  # pyright: ignore[reportPrivateUsage]
            payload
        )
    elif case == "wrong_target":
        payload["target"] = {"kind": RuleTargetKind.THIS_UNIT.value}
        generic_rule_selected_to_fight_effects._require_this_model_target(  # pyright: ignore[reportPrivateUsage]
            payload
        )
    elif case == "wrong_dice_quantity":
        generic_rule_selected_to_fight_effects._validate_self_mortal_wound_parameters(  # pyright: ignore[reportPrivateUsage]
            {"mortal_wounds_dice_quantity": 2}
        )
    elif case == "wrong_dice_sides":
        generic_rule_selected_to_fight_effects._validate_self_mortal_wound_parameters(  # pyright: ignore[reportPrivateUsage]
            {"mortal_wounds_dice_quantity": 1, "mortal_wounds_dice_sides": 6}
        )
    elif case == "wrong_modifier":
        generic_rule_selected_to_fight_effects._validate_self_mortal_wound_parameters(  # pyright: ignore[reportPrivateUsage]
            {
                "mortal_wounds_dice_quantity": 1,
                "mortal_wounds_dice_sides": 3,
                "mortal_wounds_modifier": 0,
            }
        )
    elif case == "missing_duration":
        payload["duration"] = None
        generic_rule_selected_to_fight_effects._require_end_phase_duration(  # pyright: ignore[reportPrivateUsage]
            payload
        )
    elif case == "wrong_duration_kind":
        payload["duration"] = {"kind": "end_phase"}
        generic_rule_selected_to_fight_effects._require_end_phase_duration(  # pyright: ignore[reportPrivateUsage]
            payload
        )
    elif case == "duration_parameters_not_list":
        duration = cast(dict[str, JsonValue], payload["duration"])
        duration["parameters"] = None
        generic_rule_selected_to_fight_effects._require_end_phase_duration(  # pyright: ignore[reportPrivateUsage]
            payload
        )
    elif case == "duration_parameter_not_object":
        duration = cast(dict[str, JsonValue], payload["duration"])
        duration["parameters"] = ["invalid"]
        generic_rule_selected_to_fight_effects._require_end_phase_duration(  # pyright: ignore[reportPrivateUsage]
            payload
        )
    elif case == "wrong_duration_endpoint":
        duration = cast(dict[str, JsonValue], payload["duration"])
        duration["parameters"] = [{"key": "endpoint", "value": "turn"}]
        generic_rule_selected_to_fight_effects._require_end_phase_duration(  # pyright: ignore[reportPrivateUsage]
            payload
        )
    else:
        raise AssertionError(f"Unhandled test case: {case}")


def _selected_to_fight_grant_payload(ability_id: str) -> dict[str, JsonValue]:
    return {
        "target": {"kind": RuleTargetKind.THIS_MODEL.value},
        "effect": {
            "kind": RuleEffectKind.GRANT_ABILITY.value,
            "parameters": [{"key": "ability", "value": ability_id}],
        },
    }


def _selected_to_fight_reroll_payload(roll_type: str) -> dict[str, JsonValue]:
    return {
        "target": {"kind": RuleTargetKind.THIS_MODEL.value},
        "effect": {
            "kind": RuleEffectKind.REROLL_PERMISSION.value,
            "parameters": [{"key": "roll_type", "value": roll_type}],
        },
        "duration": {
            "kind": "until_timing_endpoint",
            "parameters": [{"key": "endpoint", "value": "phase"}],
        },
    }


def _selected_to_fight_effect_payload() -> dict[str, JsonValue]:
    return {
        "target": {"kind": RuleTargetKind.THIS_MODEL.value},
        "effect": {
            "kind": RuleEffectKind.INFLICT_MORTAL_WOUNDS.value,
            "parameters": [
                {"key": "mortal_wounds_dice_quantity", "value": 1},
                {"key": "mortal_wounds_dice_sides", "value": 3},
                {"key": "mortal_wounds_modifier", "value": 1},
            ],
        },
        "duration": {
            "kind": "until_timing_endpoint",
            "parameters": [{"key": "endpoint", "value": "phase"}],
        },
    }


def _shadow_legion_source() -> GenericRuleAbilitySource:
    record = next(
        record
        for record in faction_execution_2026_27.execution_records()
        if record.coverage_descriptor_id
        == shadow_legion_ir.SHADOW_LEGION_DETACHMENT_RULE_DESCRIPTOR_ID
    )
    rule_ir = faction_generic_ir_support_2026_27.generic_rule_ir_by_coverage_descriptor_id(
        record.coverage_descriptor_id
    )
    return GenericRuleAbilitySource(record=record, rule_ir=rule_ir)


def _blood_legion_source() -> GenericRuleAbilitySource:
    record = next(
        record
        for record in faction_execution_2026_27.execution_records()
        if record.coverage_descriptor_id
        == blood_legion_ir.BLOOD_LEGION_DETACHMENT_RULE_DESCRIPTOR_ID
    )
    rule_ir = faction_generic_ir_support_2026_27.generic_rule_ir_by_coverage_descriptor_id(
        record.coverage_descriptor_id
    )
    return GenericRuleAbilitySource(record=record, rule_ir=rule_ir)


def _warptide_source(coverage_descriptor_id: str) -> GenericRuleAbilitySource:
    record = next(
        record
        for record in faction_execution_2026_27.execution_records()
        if record.coverage_descriptor_id == coverage_descriptor_id
    )
    rule_ir = faction_generic_ir_support_2026_27.generic_rule_ir_by_coverage_descriptor_id(
        record.coverage_descriptor_id
    )
    return GenericRuleAbilitySource(record=record, rule_ir=rule_ir)


def _court_of_the_phoenician_source() -> GenericRuleAbilitySource:
    record = next(
        record
        for record in faction_execution_2026_27.execution_records()
        if record.coverage_descriptor_id
        == court_ir.COURT_OF_THE_PHOENICIAN_DETACHMENT_RULE_DESCRIPTOR_ID
    )
    rule_ir = faction_generic_ir_support_2026_27.generic_rule_ir_by_coverage_descriptor_id(
        record.coverage_descriptor_id
    )
    return GenericRuleAbilitySource(record=record, rule_ir=rule_ir)


def _shadow_legion_enhancement_source(coverage_descriptor_id: str) -> GenericRuleAbilitySource:
    record = next(
        record
        for record in faction_execution_2026_27.execution_records()
        if record.coverage_descriptor_id == coverage_descriptor_id
    )
    rule_ir = faction_generic_ir_support_2026_27.generic_rule_ir_by_coverage_descriptor_id(
        record.coverage_descriptor_id
    )
    return GenericRuleAbilitySource(record=record, rule_ir=rule_ir)


def _aeldari_path_of_the_outcast_source(coverage_descriptor_id: str) -> GenericRuleAbilitySource:
    record = next(
        record
        for record in faction_execution_2026_27.execution_records()
        if record.coverage_descriptor_id == coverage_descriptor_id
    )
    rule_ir = faction_generic_ir_support_2026_27.generic_rule_ir_by_coverage_descriptor_id(
        record.coverage_descriptor_id
    )
    return GenericRuleAbilitySource(record=record, rule_ir=rule_ir)


def _aeldari_corsair_coterie_source(coverage_descriptor_id: str) -> GenericRuleAbilitySource:
    record = next(
        record
        for record in faction_execution_2026_27.execution_records()
        if record.coverage_descriptor_id == coverage_descriptor_id
    )
    rule_ir = faction_generic_ir_support_2026_27.generic_rule_ir_by_coverage_descriptor_id(
        record.coverage_descriptor_id
    )
    return GenericRuleAbilitySource(record=record, rule_ir=rule_ir)


def _keyword_any_state() -> GameState:
    ruleset = RulesetDescriptor.warhammer_40000_eleventh()
    rangers = _unit(
        unit_instance_id=_RANGERS_UNIT_ID,
        datasheet_id="aeldari-rangers",
        name="Rangers",
        keywords=(path_outcast_ir.RANGERS_KEYWORD, "INFANTRY"),
        faction_keywords=("AELDARI",),
    )
    shroud_runners = _unit(
        unit_instance_id=_SHROUD_RUNNERS_UNIT_ID,
        datasheet_id="aeldari-shroud-runners",
        name="Shroud Runners",
        keywords=(path_outcast_ir.SHROUD_RUNNERS_KEYWORD, "MOUNTED"),
        faction_keywords=("AELDARI",),
    )
    enemy = _unit(
        unit_instance_id=_ENEMY_UNIT_ID,
        datasheet_id="opfor-target",
        name="Target",
        keywords=("INFANTRY",),
        faction_keywords=("OPFOR",),
    )
    friendly_army = _army(
        army_id="army-a",
        player_id="player-a",
        ruleset=ruleset,
        faction_id="aeldari",
        detachment_id="path-of-the-outcast",
        units=(rangers, shroud_runners),
    )
    enemy_army = _army(
        army_id="army-b",
        player_id="player-b",
        ruleset=ruleset,
        faction_id="opfor",
        detachment_id="target-practice",
        units=(enemy,),
    )
    battle_phases = tuple(ruleset.battle_phase_sequence.phases)
    return GameState(
        game_id="generic-rule-ability-keyword-any",
        ruleset_descriptor_hash=ruleset.descriptor_hash,
        stage=GameLifecycleStage.BATTLE,
        setup_sequence=tuple(ruleset.setup_sequence.steps),
        battle_phase_sequence=battle_phases,
        player_ids=("player-a", "player-b"),
        turn_order=("player-a", "player-b"),
        tactical_secondary_draw_count=2,
        setup_step_index=None,
        battle_phase_index=battle_phases.index(BattlePhase.SHOOTING),
        battle_round=1,
        active_player_id="player-a",
        army_definitions=[friendly_army, enemy_army],
        starting_strength_records=[
            StartingStrengthRecord.from_unit(player_id="player-a", unit=rangers),
            StartingStrengthRecord.from_unit(player_id="player-a", unit=shroud_runners),
            StartingStrengthRecord.from_unit(player_id="player-b", unit=enemy),
        ],
    )


def _warptide_state() -> GameState:
    ruleset = RulesetDescriptor.warhammer_40000_eleventh()
    daemon = _unit(
        unit_instance_id=_WARPTIDE_UNIT_ID,
        datasheet_id="chaos-daemons-daemonettes",
        name="Daemonettes",
        keywords=(warptide_ir.BATTLELINE_KEYWORD,),
        faction_keywords=(warptide_ir.LEGIONES_DAEMONICA_KEYWORD,),
    )
    enemy = _unit(
        unit_instance_id=_ENEMY_UNIT_ID,
        datasheet_id="opfor-target",
        name="Target",
        keywords=("INFANTRY",),
        faction_keywords=("OPFOR",),
    )
    friendly_army = _army(
        army_id="army-a",
        player_id="player-a",
        ruleset=ruleset,
        faction_id=warptide_ir.CHAOS_DAEMONS_FACTION_ID,
        detachment_id=warptide_ir.WARPTIDE_DETACHMENT_ID,
        units=(daemon,),
    )
    enemy_army = _army(
        army_id="army-b",
        player_id="player-b",
        ruleset=ruleset,
        faction_id="opfor",
        detachment_id="target-practice",
        units=(enemy,),
    )
    battle_phases = tuple(ruleset.battle_phase_sequence.phases)
    return GameState(
        game_id="generic-rule-ability-warptide",
        ruleset_descriptor_hash=ruleset.descriptor_hash,
        stage=GameLifecycleStage.BATTLE,
        setup_sequence=tuple(ruleset.setup_sequence.steps),
        battle_phase_sequence=battle_phases,
        player_ids=("player-a", "player-b"),
        turn_order=("player-a", "player-b"),
        tactical_secondary_draw_count=2,
        setup_step_index=None,
        battle_phase_index=battle_phases.index(BattlePhase.MOVEMENT),
        battle_round=1,
        active_player_id="player-a",
        army_definitions=[friendly_army, enemy_army],
        starting_strength_records=[
            StartingStrengthRecord.from_unit(player_id="player-a", unit=daemon),
            StartingStrengthRecord.from_unit(player_id="player-b", unit=enemy),
        ],
    )


def _warptide_activation() -> RuntimeContentActivation:
    return RuntimeContentActivation(
        selected_faction_ids=(warptide_ir.CHAOS_DAEMONS_FACTION_ID,),
        selected_detachment_ids=(warptide_ir.WARPTIDE_DETACHMENT_ID,),
        selected_enhancement_ids=(),
        selected_stratagem_ids=(),
        selected_datasheet_ids=(),
        selected_wargear_ids=(),
        selected_weapon_profile_ids=(),
        selected_weapon_keywords=(),
        loaded_unit_instance_ids=(),
    )


def _warptide_setup_state() -> GameState:
    battle_state = _warptide_state()
    return replace(
        battle_state,
        stage=GameLifecycleStage.SETUP,
        setup_step_index=battle_state.setup_sequence.index(SetupStep.DECLARE_BATTLE_FORMATIONS),
        battle_phase_index=None,
        battle_round=0,
        active_player_id=None,
    )


def _minimal_warptide_game_config() -> GameConfig:
    ruleset = RulesetDescriptor.warhammer_40000_eleventh()
    catalog = ArmyCatalog.phase9a_canonical_content_pack()
    return GameConfig(
        game_id="generic-rule-ability-warptide",
        allow_legacy_non_strict_rosters=True,
        ruleset_descriptor=ruleset,
        army_catalog=catalog,
        army_muster_requests=(
            _muster_request(
                catalog=catalog,
                player_id="player-a",
                army_id="army-a",
                unit_selection_id="intercessor-unit-1",
            ),
            _muster_request(
                catalog=catalog,
                player_id="player-b",
                army_id="army-b",
                unit_selection_id="intercessor-unit-2",
            ),
        ),
        player_ids=("player-a", "player-b"),
        turn_order=("player-a", "player-b"),
        fixed_secondary_mission_ids=("assassination", "bring_it_down", "cleanse"),
    )


def _muster_request(
    *,
    catalog: ArmyCatalog,
    player_id: str,
    army_id: str,
    unit_selection_id: str,
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
        unit_selections=(
            UnitMusterSelection(
                unit_selection_id=unit_selection_id,
                datasheet_id="core-intercessor-like-infantry",
                model_profile_selections=(
                    ModelProfileSelection(
                        model_profile_id="core-intercessor-like",
                        model_count=5,
                    ),
                ),
            ),
        ),
    )


def _warptide_cost_modifier_context(
    *,
    state: GameState,
    target_unit_id: str,
) -> StratagemCostModifierContext:
    definition = StratagemDefinition(
        stratagem_id="fire-overwatch",
        name="fire-overwatch",
        source_id="source:fire-overwatch",
        command_point_cost=1,
        category=StratagemCategory.STRATEGIC_PLOY,
        when_descriptor="when",
        target_descriptor="target",
        effect_descriptor="effect",
        restrictions_descriptor="restrictions",
        timing=StratagemTimingDescriptor(
            trigger_kind=TimingTriggerKind.END_PHASE,
            phase=BattlePhase.MOVEMENT,
        ),
        target_spec=StratagemTargetSpec(target_kind=StratagemTargetKind.FRIENDLY_UNIT),
        handler_id=CORE_FIRE_OVERWATCH_HANDLER_ID,
    )
    eligibility_context = StratagemEligibilityContext.from_state(
        state=state,
        player_id="player-a",
        trigger_kind=TimingTriggerKind.END_PHASE,
        trigger_payload=None,
    )
    return StratagemCostModifierContext(
        state=state,
        definition=definition,
        eligibility_context=eligibility_context,
        target_binding=StratagemTargetBinding(
            target_kind=StratagemTargetKind.FRIENDLY_UNIT,
            target_player_id=_owner_player_id_for_unit_id(target_unit_id),
            target_unit_instance_id=target_unit_id,
        ),
        effect_selection=None,
        base_command_point_cost=1,
    )


def _army(
    *,
    army_id: str,
    player_id: str,
    ruleset: RulesetDescriptor,
    faction_id: str,
    detachment_id: str,
    units: tuple[UnitInstance, ...],
) -> ArmyDefinition:
    return ArmyDefinition(
        army_id=army_id,
        player_id=player_id,
        catalog_id="generic-rule-ability-test-catalog",
        source_package_id=path_outcast_ir.SOURCE_PACKAGE_ID,
        ruleset_id=ruleset.ruleset_id,
        detachment_selection=DetachmentSelection(
            faction_id=faction_id,
            detachment_ids=(detachment_id,),
        ),
        force_disposition_id="purge-the-foe",
        units=units,
    )


def _unit(
    *,
    unit_instance_id: str,
    datasheet_id: str,
    name: str,
    keywords: tuple[str, ...],
    faction_keywords: tuple[str, ...],
) -> UnitInstance:
    model = _model(
        model_instance_id=f"{unit_instance_id}:model-001",
        datasheet_id=datasheet_id,
        model_profile_id=f"{datasheet_id}-profile",
        name=f"{name} model",
        keywords=keywords,
    )
    return with_unit_keywords(
        UnitInstance(
            unit_instance_id=unit_instance_id,
            datasheet_id=datasheet_id,
            name=name,
            datasheet_abilities=(),
            datasheet_source_ids=(f"source:{datasheet_id}",),
            own_models=(model,),
            wargear_selections=(),
        ),
        keywords=keywords,
        faction_keywords=faction_keywords,
    )


def _model(
    *,
    model_instance_id: str,
    datasheet_id: str,
    model_profile_id: str,
    name: str,
    keywords: tuple[str, ...],
) -> ModelInstance:
    base_size = BaseSizeDefinition.circular(32.0)
    return ModelInstance(
        keyword_assignment=ModelKeywordAssignment(
            datasheet_id=datasheet_id,
            model_profile_id=model_profile_id,
            keywords=(),
            faction_keywords=(),
            source_ids=(f"source:{model_profile_id}",),
        ),
        model_instance_id=model_instance_id,
        datasheet_id=datasheet_id,
        model_profile_id=model_profile_id,
        name=name,
        characteristics=(
            CharacteristicValue.from_raw(Characteristic.WOUNDS, 1),
            CharacteristicValue.from_raw(Characteristic.LEADERSHIP, 7),
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


def _grant_ability_effect(
    *,
    source: GenericRuleAbilitySource,
    effect_id: str,
    target_unit_instance_id: str,
    ability: str,
    required_keyword_any: tuple[str, ...],
) -> PersistingEffect:
    return generic_rule_persisting_effect(
        effect_id=effect_id,
        source_rule_id=source.rule_ir.source_id,
        owner_player_id=_owner_player_id_for_unit_id(target_unit_instance_id),
        target_unit_instance_ids=(target_unit_instance_id,),
        started_battle_round=1,
        started_phase=BattlePhase.SHOOTING,
        expiration=EffectExpiration.end_of_battle(),
        effect_payload=validate_json_value(
            {
                "effect_kind": "generic_rule_execution",
                "coverage_descriptor_id": source.record.coverage_descriptor_id,
                "execution_id": source.record.execution_id,
                "target_unit_instance_ids": [target_unit_instance_id],
                "target": {"kind": RuleTargetKind.THIS_UNIT.value},
                "effect": {
                    "kind": RuleEffectKind.GRANT_ABILITY.value,
                    "parameters": [
                        {"key": "ability", "value": ability},
                        {"key": "required_keyword_any", "value": list(required_keyword_any)},
                    ],
                },
            }
        ),
    )


def _warptide_grant_ability_effect(
    *,
    source: GenericRuleAbilitySource,
    effect_id: str,
    target_unit_instance_id: str,
    ability: str,
) -> PersistingEffect:
    return generic_rule_persisting_effect(
        effect_id=effect_id,
        source_rule_id=source.rule_ir.source_id,
        owner_player_id=_owner_player_id_for_unit_id(target_unit_instance_id),
        target_unit_instance_ids=(target_unit_instance_id,),
        started_battle_round=1,
        started_phase=BattlePhase.MOVEMENT,
        expiration=EffectExpiration.end_of_battle(),
        effect_payload=validate_json_value(
            {
                "effect_kind": "generic_rule_execution",
                "coverage_descriptor_id": source.record.coverage_descriptor_id,
                "execution_id": source.record.execution_id,
                "target_unit_instance_ids": [target_unit_instance_id],
                "target": {"kind": RuleTargetKind.THIS_UNIT.value},
                "effect": {
                    "kind": RuleEffectKind.GRANT_ABILITY.value,
                    "parameters": [
                        {"key": "ability", "value": ability},
                        {
                            "key": "required_faction_keyword_sequence",
                            "value": [warptide_ir.LEGIONES_DAEMONICA_KEYWORD],
                        },
                        {
                            "key": "required_keyword_sequence",
                            "value": [warptide_ir.BATTLELINE_KEYWORD],
                        },
                    ],
                },
            }
        ),
    )


def _owner_player_id_for_unit_id(unit_instance_id: str) -> str:
    if unit_instance_id.startswith("army-a:"):
        return "player-a"
    if unit_instance_id.startswith("army-b:"):
        return "player-b"
    raise AssertionError(f"Unknown test unit ID: {unit_instance_id}")


__all__: list[str] = []
__all__ += ["AdvanceEligibilityContext", "AdvanceMoveContext", "AdvanceMoveGrant", "ArmyCatalog"]
__all__ += ["ArmyDefinition", "ArmyMusterRequest", "BaseSizeDefinition"]
__all__ += ["BattleFormationRequestContext", "BattleFormationResultContext", "BattlePhase"]
__all__ += ["CORE_FIRE_OVERWATCH_HANDLER_ID", "Callable", "Characteristic", "CharacteristicValue"]
__all__ += ["DEFAULT_GENERIC_RULE_ABILITY_REGISTRY", "DecisionController", "DetachmentSelection"]
__all__ += ["EffectExpiration", "EnhancementAssignment", "EnhancementEffectContext"]
__all__ += ["FallBackEligibilityContext", "FightActivationAbilityContext"]
__all__ += ["FightPhaseStartRequestContext", "FightPhaseStartResultContext"]
__all__ += ["FightUnitSelectedContext", "GameConfig", "GameLifecycleError", "GameLifecycleStage"]
__all__ += ["GameState", "GenericRuleAbilityHookFamily", "GenericRuleAbilityRegistry"]
__all__ += ["GenericRuleAbilitySource", "JsonValue", "ModelGeometry", "ModelInstance"]
__all__ += ["ModelKeywordAssignment", "ModelProfileSelection", "ModifierOperation"]
__all__ += ["ModifierTerm", "MovementEndSurgeContext", "ObjectiveControlModifierContext"]
__all__ += ["PersistingEffect", "PhaseEndObjectiveControlContext"]
__all__ += ["ReserveArrivalDistanceContext", "RuleEffectKind", "RuleExecutionResult"]
__all__ += ["RuleExecutionStatus", "RuleIR", "RuleTargetKind", "RulesetDescriptor"]
__all__ += ["RuntimeContentActivation", "SaveOptionModifierContext", "SetupStep"]
__all__ += ["ShootingTargetRestrictionContext", "ShootingUnitSelectedContext"]
__all__ += ["StartingStrengthRecord", "StratagemCategory", "StratagemCostChoiceRequestContext"]
__all__ += ["StratagemCostChoiceResultContext", "StratagemCostModifierContext"]
__all__ += ["StratagemDefinition", "StratagemEligibilityContext", "StratagemTargetBinding"]
__all__ += ["StratagemTargetKind", "StratagemTargetSpec", "StratagemTimingDescriptor"]
__all__ += ["TimingTriggerKind", "TurnEndRequestContext", "TurnEndResultContext"]
__all__ += ["UnitDestroyedContext", "UnitInstance", "UnitMusterSelection", "WeaponKeyword"]
__all__ += ["_ENEMY_UNIT_ID", "_RANGERS_UNIT_ID", "_SHROUD_RUNNERS_UNIT_ID", "_WARPTIDE_UNIT_ID"]
__all__ += ["_aeldari_corsair_coterie_source", "_aeldari_path_of_the_outcast_source", "_army"]
__all__ += ["_blood_legion_source", "_court_of_the_phoenician_source", "_grant_ability_effect"]
__all__ += ["_keyword_any_state", "_minimal_warptide_game_config", "_model", "_muster_request"]
__all__ += ["_owner_player_id_for_unit_id", "_raise_selected_to_fight_payload_error"]
__all__ += ["_selected_to_fight_effect_payload", "_selected_to_fight_grant_payload"]
__all__ += ["_selected_to_fight_reroll_payload", "_shadow_legion_enhancement_source"]
__all__ += ["_shadow_legion_source", "_unit", "_warptide_activation"]
__all__ += ["_warptide_cost_modifier_context", "_warptide_grant_ability_effect"]
__all__ += ["_warptide_setup_state", "_warptide_source", "_warptide_state"]
__all__ += ["advance_move_lifecycle_hooks", "blood_legion_ir", "cast", "copy"]
__all__ += ["corsair_enhancements", "corsair_ir", "court_ir", "court_rule", "dark_pacts"]
__all__ += ["faction_execution_2026_27", "faction_generic_ir_support_2026_27"]
__all__ += ["generic_detachment_effects", "generic_rule_ability_effects_for_unit"]
__all__ += ["generic_rule_lifecycle_hook_handlers", "generic_rule_lifecycle_hooks"]
__all__ += ["generic_rule_persisting_effect", "generic_rule_selected_to_fight_effects"]
__all__ += ["path_outcast_ir", "pytest", "replace", "rule_ir_grants_any_ability"]
__all__ += ["shadow_legion_ir", "validate_json_value", "warptide_ir", "with_unit_keywords"]
