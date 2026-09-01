# pyright: reportPrivateUsage=false
from __future__ import annotations

import copy
from dataclasses import dataclass, replace
from typing import Any, cast

import pytest
from tests.support.catalog_package_fixtures import horrors_package
from tests.support.catalog_runtime_fixtures import (
    battle_state_with_armies,
    player_ability_index,
)

from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.core.attributes import Characteristic, CharacteristicValue
from warhammer40k_core.core.dice import DiceExpression, DiceRollResult, DiceRollSpec
from warhammer40k_core.core.ruleset_descriptor import (
    FightEligibilityKind,
    FightPhaseStepKind,
    RulesetDescriptor,
    battle_phase_kind_from_token,
)
from warhammer40k_core.core.weapon_profiles import DamageProfile, WeaponKeyword
from warhammer40k_core.engine import lifecycle as lifecycle_module
from warhammer40k_core.engine import rule_model_destruction
from warhammer40k_core.engine.ability_catalog import catalog_ability_records_from_catalog
from warhammer40k_core.engine.army_mustering import ArmyDefinition, ArmyMusterRequest
from warhammer40k_core.engine.attached_unit_formation import AttachedUnitFormation
from warhammer40k_core.engine.attached_unit_reconciliation import (
    reconcile_after_attack_sequence,
)
from warhammer40k_core.engine.attack_sequence import (
    AttackSequence,
    apply_feel_no_pain_decision,
    attack_sequence_wound_roll_spec,
    deadly_demise_trigger_roll_spec,
    resolve_attack_sequence_until_blocked,
)
from warhammer40k_core.engine.attack_sequence_completion_hooks import (
    AttackSequenceCompletedContext,
)
from warhammer40k_core.engine.battle_round_flow import BattleRoundFlow
from warhammer40k_core.engine.battlefield_state import (
    BattlefieldPlacementKind,
    BattlefieldRemovalKind,
    BattlefieldRuntimeState,
    BattlefieldTransitionBatch,
    BattlefieldTransitionBatchPayload,
    ModelPlacement,
    ModelRemovalRecord,
    PlacedArmy,
    UnitPlacement,
)
from warhammer40k_core.engine.catalog_materialization_integrity import (
    _required_string_list,
    authenticated_catalog_materialized_model_payloads_by_unit_id,
)
from warhammer40k_core.engine.catalog_model_materialization_runtime import (
    CATALOG_MODEL_MATERIALIZATION_ROLL_EVENT,
    CATALOG_MODELS_MATERIALIZED_EVENT,
    CATALOG_UNIT_DATASHEET_REPLACED_EVENT,
    SUBMIT_CATALOG_MODEL_MATERIALIZATION_PLACEMENT_DECISION_TYPE,
    CatalogModelMaterializationRuntime,
    apply_recorded_catalog_model_materialization_placement,
    invalid_catalog_model_materialization_placement_status,
)
from warhammer40k_core.engine.catalog_selected_target_mortal_wounds import (
    resolve_selected_target_mortal_wound_effect,
)
from warhammer40k_core.engine.damage_allocation import (
    DECLINE_DESTRUCTION_REACTION_OPTION_ID,
    DestructionReactionKind,
    DestructionReactionSource,
    FeelNoPainSource,
    feel_no_pain_roll_spec,
)
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_record import DecisionRecord
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.destruction_provenance import (
    DestructionSourceKind,
    ModelDestructionAttribution,
)
from warhammer40k_core.engine.dice import DiceRollManager
from warhammer40k_core.engine.effects import EffectExpiration, PersistingEffect
from warhammer40k_core.engine.event_log import EventRecord, JsonValue, validate_json_value
from warhammer40k_core.engine.faction_content.activation import RuntimeContentActivation
from warhammer40k_core.engine.faction_content.bundle import (
    RuntimeContentBundle,
    RuntimeContentContribution,
)
from warhammer40k_core.engine.faction_content.events import (
    RuntimeContentEventContext,
    RuntimeContentEventHandlerBinding,
    RuntimeContentEventResult,
    RuntimeContentEventSubscription,
)
from warhammer40k_core.engine.fight_order import (
    FightActivationSelection,
    FightPhaseState,
    FightsFirstRegistry,
)
from warhammer40k_core.engine.game_state import GameConfig, GameState
from warhammer40k_core.engine.lifecycle import GameLifecycle
from warhammer40k_core.engine.list_validation import DetachmentSelection, UnitMusterSelection
from warhammer40k_core.engine.mortal_wound_destruction_evidence import (
    MORTAL_WOUND_MODEL_DESTRUCTIONS_FINALIZED_EVENT,
)
from warhammer40k_core.engine.mortal_wound_model_allocation import (
    is_mortal_wound_model_request,
    resolve_mortal_wound_decision,
)
from warhammer40k_core.engine.movement_proposals import PlacementProposalPayload, ProposalKind
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError, LifecycleStatusKind
from warhammer40k_core.engine.phases.fight import FightPhaseHandler
from warhammer40k_core.engine.phases.movement import MovementPhaseHandler
from warhammer40k_core.engine.phases.shooting import (
    OutOfPhaseShootingState,
    ShootingPhaseHandler,
    ShootingPhaseState,
)
from warhammer40k_core.engine.reaction_queue import ReactionQueue, ReactionQueueFrame
from warhammer40k_core.engine.rule_model_destruction import (
    RULE_MODEL_DESTRUCTION_FINALIZED_EVENT,
)
from warhammer40k_core.engine.rules_units import rules_unit_view_by_id
from warhammer40k_core.engine.runtime_modifiers import RuntimeModifierRegistry
from warhammer40k_core.engine.saves import (
    mandatory_save_option,
    save_options_for_model,
    saving_throw_roll_spec,
)
from warhammer40k_core.engine.shooting_types import ShootingType
from warhammer40k_core.engine.timing_windows import (
    ReactionWindow,
    TimingTriggerKind,
    TimingWindow,
    TimingWindowDescriptor,
)
from warhammer40k_core.engine.unit_factory import ModelInstance, UnitFactory, UnitInstance
from warhammer40k_core.engine.wargear_selections import ModelProfileSelection
from warhammer40k_core.engine.weapon_declaration import RangedAttackPool
from warhammer40k_core.geometry.pose import Pose
from warhammer40k_core.rules.catalog_package import CanonicalCatalogPackage


@dataclass(frozen=True, slots=True)
class _SplitScenario:
    package: CanonicalCatalogPackage
    state: GameState
    decisions: DecisionController
    runtime: CatalogModelMaterializationRuntime
    context: AttackSequenceCompletedContext
    source_army: ArmyDefinition
    enemy_army: ArmyDefinition
    bodyguard: UnitInstance
    leader: UnitInstance
    attack_sequence: AttackSequence
    destroyed_model_instance_id: str
    destroyed_model_instance_ids: tuple[str, ...]
    attached_unit_instance_id: str


@pytest.mark.parametrize(
    ("pink_datasheet_id", "blue_datasheet_id", "source_phase"),
    [
        ("000002584", "000002583", BattlePhase.SHOOTING),
        ("000002584", "000002583", BattlePhase.FIGHT),
        ("000004127", "000004128", BattlePhase.SHOOTING),
        ("000004127", "000004128", BattlePhase.FIGHT),
    ],
)
def test_split_materializes_models_then_hands_off_attached_unit_datasheet(
    pink_datasheet_id: str,
    blue_datasheet_id: str,
    source_phase: BattlePhase,
) -> None:
    scenario = _split_scenario(
        pink_datasheet_id=pink_datasheet_id,
        blue_datasheet_id=blue_datasheet_id,
        destruction_kind="attack",
        source_phase=source_phase,
    )
    starting_strength = scenario.state.starting_strength_record_for_unit(
        scenario.attached_unit_instance_id
    )

    status = scenario.runtime.resolve_completed_attack_sequence(scenario.context)

    assert status is not None
    assert status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    request = scenario.decisions.queue.peek_next()
    assert request.decision_type == SUBMIT_CATALOG_MODEL_MATERIALIZATION_PLACEMENT_DECISION_TYPE
    assert request.actor_id == scenario.source_army.player_id
    assert type(request).from_payload(request.to_payload()).to_payload() == request.to_payload()
    request_payload = cast(dict[str, JsonValue], request.payload)
    assert len(cast(list[JsonValue], request_payload["models"])) == 2
    assert request_payload["source_phase"] == source_phase.value
    pending_lifecycle = GameLifecycle(
        state=scenario.state,
        decision_controller=scenario.decisions,
    )
    restored_pending_lifecycle = GameLifecycle.from_payload(pending_lifecycle.to_payload())
    assert (
        restored_pending_lifecycle.decision_controller.queue.peek_next().to_payload()
        == request.to_payload()
    )

    valid_payload = _placement_payload(
        request=request,
        army=scenario.source_army,
        unit=scenario.bodyguard,
    )
    stale_payload = dict(valid_payload)
    stale_payload["proposal_request_id"] = "stale-split-request"
    stale_result = _parameterized_result(
        request=request,
        payload=validate_json_value(stale_payload),
        result_id="result:split:stale",
    )
    stale_status = invalid_catalog_model_materialization_placement_status(
        state=scenario.state,
        request=request,
        result=stale_result,
        decisions=scenario.decisions,
        ability_indexes_by_player_id=scenario.runtime.ability_indexes_by_player_id,
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(),
        army_catalog=scenario.package.army_catalog,
    )
    assert stale_status is not None
    assert stale_status.status_kind is LifecycleStatusKind.INVALID
    assert scenario.decisions.queue.peek_next() == request

    result = _parameterized_result(
        request=request,
        payload=valid_payload,
        result_id=f"result:split:{pink_datasheet_id}",
    )
    assert (
        invalid_catalog_model_materialization_placement_status(
            state=scenario.state,
            request=request,
            result=result,
            decisions=scenario.decisions,
            ability_indexes_by_player_id=scenario.runtime.ability_indexes_by_player_id,
            ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(),
            army_catalog=scenario.package.army_catalog,
        )
        is None
    )
    scenario.decisions.submit_result(result)
    placements = apply_recorded_catalog_model_materialization_placement(
        state=scenario.state,
        decisions=scenario.decisions,
        request=request,
        result=result,
        ability_indexes_by_player_id=scenario.runtime.ability_indexes_by_player_id,
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(),
        army_catalog=scenario.package.army_catalog,
    )
    assert len(placements) == 2
    assert {placement.placement_kind for placement in placements} == {
        BattlefieldPlacementKind.SPLIT_UNIT
    }
    assert {placement.source_phase for placement in placements} == {source_phase.value}

    assert scenario.runtime.resolve_completed_attack_sequence(scenario.context) is None
    reconcile_after_attack_sequence(
        scenario.state,
        scenario.attack_sequence,
    )
    updated_bodyguard = _unit_by_id(scenario.state, scenario.bodyguard.unit_instance_id)
    assert updated_bodyguard.datasheet_id == blue_datasheet_id
    assert len(updated_bodyguard.own_models) == 2
    assert scenario.destroyed_model_instance_id not in updated_bodyguard.own_model_ids()
    assert {model.model_profile_id for model in updated_bodyguard.own_models} == {
        f"{blue_datasheet_id}:blue-horrors"
    }
    assert all(model.base_size.diameter_mm == 25.0 for model in updated_bodyguard.own_models)
    assert all(
        "horror-materialization:blue-horror" in model.source_ids
        for model in updated_bodyguard.own_models
    )
    rules_unit = rules_unit_view_by_id(
        state=scenario.state,
        unit_instance_id=scenario.bodyguard.unit_instance_id,
    )
    assert rules_unit.is_attached_rules_unit
    assert len(rules_unit.alive_models()) == 3
    assert starting_strength.starting_model_count == 2
    assert (
        scenario.state.starting_strength_record_for_unit(scenario.attached_unit_instance_id)
        == starting_strength
    )
    assert scenario.state.battlefield_state is not None
    assert scenario.destroyed_model_instance_id not in (
        scenario.state.battlefield_state.removed_model_ids
    )
    event_types = tuple(record.event_type for record in scenario.decisions.event_log.records)
    assert CATALOG_MODELS_MATERIALIZED_EVENT in event_types
    assert CATALOG_UNIT_DATASHEET_REPLACED_EVENT in event_types
    assert "battlefield_models_placed" in event_types
    materialized_event = next(
        record
        for record in scenario.decisions.event_log.records
        if record.event_type == CATALOG_MODELS_MATERIALIZED_EVENT
    )
    materialized_payload = cast(dict[str, JsonValue], materialized_event.payload)
    assert materialized_payload["source_phase"] == source_phase.value
    transition = BattlefieldTransitionBatch.from_payload(
        cast(BattlefieldTransitionBatchPayload, materialized_payload["transition_batch"])
    )
    assert {placement.source_phase for placement in transition.placements} == {source_phase.value}
    restored = GameState.from_payload(scenario.state.to_payload())
    assert _unit_by_id(restored, scenario.bodyguard.unit_instance_id).datasheet_id == (
        blue_datasheet_id
    )
    assert GameState.from_payload(restored.to_payload()).to_payload() == restored.to_payload()
    restored_decisions = DecisionController.from_payload(scenario.decisions.to_payload())
    restored_materialized = next(
        record
        for record in restored_decisions.event_log.records
        if record.event_type == CATALOG_MODELS_MATERIALIZED_EVENT
    )
    restored_payload = cast(dict[str, JsonValue], restored_materialized.payload)
    restored_transition = BattlefieldTransitionBatch.from_payload(
        cast(BattlefieldTransitionBatchPayload, restored_payload["transition_batch"])
    )
    assert {placement.source_phase for placement in restored_transition.placements} == {
        source_phase.value
    }
    authenticated_models = authenticated_catalog_materialized_model_payloads_by_unit_id(
        game_id=scenario.state.game_id,
        catalog=scenario.package.army_catalog,
        expected_armies=(scenario.source_army, scenario.enemy_army),
        event_records=scenario.decisions.event_log.records,
        decision_records=scenario.decisions.records,
    )
    assert set(authenticated_models[scenario.bodyguard.unit_instance_id]) == set(
        cast(list[str], materialized_payload["model_instance_ids"])
    )
    resolved_lifecycle = GameLifecycle(
        state=scenario.state,
        decision_controller=scenario.decisions,
    )
    restored_resolved_lifecycle = GameLifecycle.from_payload(resolved_lifecycle.to_payload())
    restored_resolved_state = restored_resolved_lifecycle.state
    assert restored_resolved_state is not None
    assert (
        _unit_by_id(
            restored_resolved_state,
            scenario.bodyguard.unit_instance_id,
        ).datasheet_id
        == blue_datasheet_id
    )
    assert restored_resolved_lifecycle.decision_controller.to_payload() == (
        scenario.decisions.to_payload()
    )


def test_split_complete_standalone_wipe_skips_empty_datasheet_handoff() -> None:
    scenario = _split_scenario(
        pink_datasheet_id="000002584",
        blue_datasheet_id="000002583",
        destruction_kind="attack",
        attached=False,
    )

    assert scenario.runtime.resolve_completed_attack_sequence(scenario.context) is None

    unit = _unit_by_id(scenario.state, scenario.bodyguard.unit_instance_id)
    assert unit.datasheet_id == "000002584"
    assert unit.own_models
    assert not any(model.is_alive for model in unit.own_models)
    assert all(
        record.event_type != CATALOG_UNIT_DATASHEET_REPLACED_EVENT
        for record in scenario.decisions.event_log.records
    )


@pytest.mark.parametrize("source_phase", [BattlePhase.SHOOTING, BattlePhase.FIGHT])
def test_real_attack_pipeline_hands_off_attached_horror_component(
    source_phase: BattlePhase,
) -> None:
    scenario = _split_scenario(
        pink_datasheet_id="000002584",
        blue_datasheet_id="000002583",
        destruction_kind="attack",
        source_phase=source_phase,
        models_start_destroyed=False,
        emit_destruction_events=False,
    )
    pink_model = scenario.bodyguard.own_models[0]
    valid_save_model = replace(
        pink_model,
        characteristics=tuple(
            CharacteristicValue.from_raw(Characteristic.SAVE, 6)
            if value.characteristic is Characteristic.SAVE
            else value
            for value in pink_model.characteristics
        ),
    )
    bodyguard = replace(scenario.bodyguard, own_models=(valid_save_model,))
    source_army = replace(
        scenario.source_army,
        units=tuple(
            bodyguard if unit.unit_instance_id == bodyguard.unit_instance_id else unit
            for unit in scenario.source_army.units
        ),
    )
    scenario.state.replace_army_definitions([source_army, scenario.enemy_army])
    base_pool = scenario.attack_sequence.attack_pools[0]
    lethal_profile = replace(
        base_pool.weapon_profile,
        strength=CharacteristicValue.from_raw(Characteristic.STRENGTH, 20),
        armor_penetration=CharacteristicValue.from_raw(Characteristic.ARMOR_PENETRATION, 0),
        damage_profile=DamageProfile.fixed(1),
        keywords=(WeaponKeyword.TORRENT,),
        abilities=(),
    )
    lethal_pool = replace(base_pool, weapon_profile=lethal_profile)
    attack_sequence = AttackSequence.start(
        sequence_id=f"real-pipeline:{source_phase.value}:horror-split",
        attacker_player_id=scenario.enemy_army.player_id,
        attacking_unit_instance_id=scenario.attack_sequence.attacking_unit_instance_id,
        attack_pools=(lethal_pool,),
        source_phase=source_phase,
    )
    wound_spec = attack_sequence_wound_roll_spec(
        weapon_profile_id=lethal_pool.weapon_profile_id,
        attack_context_id=attack_sequence.attack_context_id(),
        attacker_player_id=scenario.enemy_army.player_id,
    )
    save_option = mandatory_save_option(
        save_options_for_model(
            model=valid_save_model,
            armor_penetration=0,
        )
    )
    assert save_option is not None
    save_spec = saving_throw_roll_spec(
        save_kind=save_option.save_kind,
        player_id=scenario.source_army.player_id,
        allocated_model_id=valid_save_model.model_instance_id,
        attack_context_id=attack_sequence.attack_context_id(),
    )
    manager = DiceRollManager(
        scenario.state.game_id,
        event_log=scenario.decisions.event_log,
        injected_results=(
            DiceRollResult.from_values(
                roll_id=f"roll:real-pipeline:{source_phase.value}:wound",
                spec=wound_spec,
                values=(6,),
                source="fixed",
            ),
            DiceRollResult.from_values(
                roll_id=f"roll:real-pipeline:{source_phase.value}:save",
                spec=save_spec,
                values=(1,),
                source="fixed",
            ),
        ),
    )

    remaining, _allocated_ids, blocked = resolve_attack_sequence_until_blocked(
        state=scenario.state,
        decisions=scenario.decisions,
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(),
        attack_sequence=attack_sequence,
        already_allocated_model_ids=(),
        dice_manager=manager,
    )

    assert remaining is None
    assert blocked is None
    destroyed_event = next(
        record
        for record in scenario.decisions.event_log.records
        if record.event_type == "model_destroyed"
    )
    destroyed_payload = cast(dict[str, JsonValue], destroyed_event.payload)
    assert destroyed_payload["target_unit_instance_id"] == scenario.attached_unit_instance_id
    completed_event = next(
        record
        for record in reversed(scenario.decisions.event_log.records)
        if record.event_type == "attack_sequence_completed"
        and cast(dict[str, JsonValue], record.payload).get("sequence_id")
        == attack_sequence.sequence_id
    )
    completed_sequence = replace(attack_sequence, used_pool_indices=(0,), pool_index=1)
    context = replace(
        scenario.context,
        attack_sequence=completed_sequence,
        attack_sequence_completed_event_id=completed_event.event_id,
        source_phase=source_phase,
    )
    assert scenario.runtime.resolve_completed_attack_sequence(context) is not None
    request = scenario.decisions.queue.peek_next()
    result = _parameterized_result(
        request=request,
        payload=_placement_payload(
            request=request,
            army=scenario.source_army,
            unit=scenario.bodyguard,
        ),
        result_id=f"result:real-pipeline:{source_phase.value}",
    )
    scenario.decisions.submit_result(result)
    apply_recorded_catalog_model_materialization_placement(
        state=scenario.state,
        decisions=scenario.decisions,
        request=request,
        result=result,
        ability_indexes_by_player_id=scenario.runtime.ability_indexes_by_player_id,
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(),
        army_catalog=scenario.package.army_catalog,
    )

    assert scenario.runtime.resolve_completed_attack_sequence(context) is None
    assert _unit_by_id(scenario.state, scenario.bodyguard.unit_instance_id).datasheet_id == (
        "000002583"
    )


def test_real_hazardous_attack_uses_typed_destruction_once_for_horror_split() -> None:
    scenario = _split_scenario(
        pink_datasheet_id="000002584",
        blue_datasheet_id="000002583",
        destruction_kind="hazardous",
        models_start_destroyed=False,
        emit_destruction_events=False,
    )
    enemy_model = scenario.enemy_army.units[0].own_models[0]
    valid_save_model = replace(
        enemy_model,
        characteristics=tuple(
            CharacteristicValue.from_raw(Characteristic.SAVE, 6)
            if value.characteristic is Characteristic.SAVE
            else value
            for value in enemy_model.characteristics
        ),
    )
    enemy_unit = replace(scenario.enemy_army.units[0], own_models=(valid_save_model,))
    enemy_army = replace(scenario.enemy_army, units=(enemy_unit,))
    scenario.state.replace_army_definitions([scenario.source_army, enemy_army])
    base_pool = scenario.attack_sequence.attack_pools[0]
    hazardous_profile = replace(
        base_pool.weapon_profile,
        profile_id="real-hazardous:horror-split",
        keywords=(WeaponKeyword.TORRENT, WeaponKeyword.HAZARDOUS),
        abilities=(),
    )
    hazardous_pool = replace(
        base_pool,
        weapon_profile_id=hazardous_profile.profile_id,
        weapon_profile=hazardous_profile,
    )
    attack_sequence = AttackSequence.start(
        sequence_id="real-hazardous:horror-split",
        attacker_player_id=scenario.source_army.player_id,
        attacking_unit_instance_id=scenario.attached_unit_instance_id,
        attack_pools=(hazardous_pool,),
    )
    wound_spec = attack_sequence_wound_roll_spec(
        weapon_profile_id=hazardous_profile.profile_id,
        attack_context_id=attack_sequence.attack_context_id(),
        attacker_player_id=scenario.source_army.player_id,
    )
    hazardous_spec = DiceRollSpec(
        expression=DiceExpression(quantity=1, sides=6),
        reason=(f"Hazardous test for {scenario.attached_unit_instance_id} after shooting"),
        roll_type="hazardous_test",
        actor_id=scenario.attached_unit_instance_id,
    )

    remaining, _allocated_ids, blocked = resolve_attack_sequence_until_blocked(
        state=scenario.state,
        decisions=scenario.decisions,
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(),
        attack_sequence=attack_sequence,
        already_allocated_model_ids=(),
        dice_manager=DiceRollManager(
            scenario.state.game_id,
            event_log=scenario.decisions.event_log,
            injected_results=(
                DiceRollResult.from_values(
                    roll_id="roll:real-hazardous:horror-split:wound",
                    spec=wound_spec,
                    values=(1,),
                    source="fixed",
                ),
                DiceRollResult.from_values(
                    roll_id="roll:real-hazardous:horror-split:test",
                    spec=hazardous_spec,
                    values=(1,),
                    source="fixed",
                ),
            ),
        ),
    )

    assert remaining is None
    assert blocked is None
    completed_event = next(
        record
        for record in reversed(scenario.decisions.event_log.records)
        if record.event_type == "attack_sequence_completed"
        and cast(dict[str, JsonValue], record.payload).get("sequence_id")
        == attack_sequence.sequence_id
    )
    completed_sequence = replace(attack_sequence, used_pool_indices=(0,), pool_index=1)
    context = replace(
        scenario.context,
        attack_sequence=completed_sequence,
        attack_sequence_completed_event_id=completed_event.event_id,
    )

    status = scenario.runtime.resolve_completed_attack_sequence(context)

    assert status is not None
    assert status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    assert (
        sum(
            record.event_type == "hazardous_mortal_wounds_applied"
            for record in scenario.decisions.event_log.records
        )
        == 1
    )
    hazardous_destroyed_payloads = tuple(
        cast(dict[str, JsonValue], record.payload)
        for record in scenario.decisions.event_log.records
        if record.event_type == "model_destroyed"
        and cast(dict[str, JsonValue], record.payload).get("model_instance_id")
        == scenario.destroyed_model_instance_id
    )
    assert len(hazardous_destroyed_payloads) == 1
    assert isinstance(
        hazardous_destroyed_payloads[0]["destroyed_model_placement"],
        dict,
    )
    assert (
        ModelDestructionAttribution.from_model_destroyed_payload(
            hazardous_destroyed_payloads[0]
        ).destruction_provenance.destruction_source_kind
        is DestructionSourceKind.HAZARDOUS
    )
    assert (
        sum(
            record.event_type == CATALOG_MODEL_MATERIALIZATION_ROLL_EVENT
            for record in scenario.decisions.event_log.records
        )
        == 1
    )


def test_split_failed_attached_wipe_skips_handoff_and_retains_attachment() -> None:
    scenario = _split_scenario(
        pink_datasheet_id="000002584",
        blue_datasheet_id="000002583",
        destruction_kind="attack",
        roll_values=(1,),
    )

    assert scenario.runtime.resolve_completed_attack_sequence(scenario.context) is None
    assert all(
        record.event_type != CATALOG_UNIT_DATASHEET_REPLACED_EVENT
        for record in scenario.decisions.event_log.records
    )
    reconcile_after_attack_sequence(
        scenario.state,
        scenario.attack_sequence,
    )
    bodyguard = _unit_by_id(scenario.state, scenario.bodyguard.unit_instance_id)
    assert bodyguard.own_models
    assert not any(model.is_alive for model in bodyguard.own_models)
    retained_view = rules_unit_view_by_id(
        state=scenario.state,
        unit_instance_id=scenario.leader.unit_instance_id,
    )
    assert retained_view.is_attached_rules_unit
    assert retained_view.unit_instance_id == scenario.attached_unit_instance_id


def test_attack_reconciliation_retains_canonical_attached_identity() -> None:
    scenario = _split_scenario(
        pink_datasheet_id="000002584",
        blue_datasheet_id="000002583",
        destruction_kind="attack",
        roll_values=(1,),
    )

    reconcile_after_attack_sequence(
        scenario.state,
        scenario.attack_sequence,
    )
    retained_view = rules_unit_view_by_id(
        state=scenario.state,
        unit_instance_id=scenario.leader.unit_instance_id,
    )
    assert retained_view.is_attached_rules_unit
    assert retained_view.unit_instance_id == scenario.attached_unit_instance_id


def test_split_multiple_failed_rolls_do_not_construct_empty_replacement_unit() -> None:
    scenario = _split_scenario(
        pink_datasheet_id="000002584",
        blue_datasheet_id="000002583",
        destruction_kind="attack",
        pink_model_count=3,
        roll_values=(1, 2, 3),
    )

    assert scenario.runtime.resolve_completed_attack_sequence(scenario.context) is None

    roll_events = tuple(
        record
        for record in scenario.decisions.event_log.records
        if record.event_type == CATALOG_MODEL_MATERIALIZATION_ROLL_EVENT
    )
    assert len(roll_events) == 3
    assert all(
        cast(dict[str, JsonValue], record.payload)["successful"] is False for record in roll_events
    )
    unit = _unit_by_id(scenario.state, scenario.bodyguard.unit_instance_id)
    assert len(unit.own_models) == 3
    assert not any(model.is_alive for model in unit.own_models)
    assert all(
        record.event_type != CATALOG_UNIT_DATASHEET_REPLACED_EVENT
        for record in scenario.decisions.event_log.records
    )


def test_split_mixed_rolls_materialize_only_successes_before_handoff() -> None:
    scenario = _split_scenario(
        pink_datasheet_id="000002584",
        blue_datasheet_id="000002583",
        destruction_kind="attack",
        pink_model_count=2,
        roll_values=(6, 1),
    )

    status = scenario.runtime.resolve_completed_attack_sequence(scenario.context)
    assert status is not None
    request = scenario.decisions.queue.peek_next()
    result = _parameterized_result(
        request=request,
        payload=_placement_payload(
            request=request,
            army=scenario.source_army,
            unit=scenario.bodyguard,
        ),
        result_id="result:split:mixed",
    )
    scenario.decisions.submit_result(result)
    apply_recorded_catalog_model_materialization_placement(
        state=scenario.state,
        decisions=scenario.decisions,
        request=request,
        result=result,
        ability_indexes_by_player_id=scenario.runtime.ability_indexes_by_player_id,
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(),
        army_catalog=scenario.package.army_catalog,
    )

    assert scenario.runtime.resolve_completed_attack_sequence(scenario.context) is None

    updated = _unit_by_id(scenario.state, scenario.bodyguard.unit_instance_id)
    assert updated.datasheet_id == "000002583"
    assert len(updated.own_models) == 2
    roll_events = tuple(
        cast(dict[str, JsonValue], record.payload)
        for record in scenario.decisions.event_log.records
        if record.event_type == CATALOG_MODEL_MATERIALIZATION_ROLL_EVENT
    )
    assert [payload["successful"] for payload in roll_events] == [True, False]


@pytest.mark.parametrize(
    "source_kind",
    [DestructionSourceKind.ABILITY, DestructionSourceKind.DEADLY_DEMISE],
)
def test_matching_attack_sequence_id_does_not_override_destruction_provenance(
    source_kind: DestructionSourceKind,
) -> None:
    scenario = _split_scenario(
        pink_datasheet_id="000002584",
        blue_datasheet_id="000002583",
        destruction_kind=source_kind.value,
        event_sequence_matches=True,
        retained_horror_kinds=("blue",),
    )

    assert scenario.runtime.resolve_completed_attack_sequence(scenario.context) is None
    assert scenario.decisions.queue.pending_requests == ()
    assert all(
        record.event_type != CATALOG_MODEL_MATERIALIZATION_ROLL_EVENT
        for record in scenario.decisions.event_log.records
    )
    assert (
        _unit_by_id(
            scenario.state,
            scenario.bodyguard.unit_instance_id,
        ).datasheet_id
        == "000002583"
    )


def test_matching_sequence_model_destroyed_event_requires_typed_attribution() -> None:
    scenario = _split_scenario(
        pink_datasheet_id="000002584",
        blue_datasheet_id="000002583",
        destruction_kind=DestructionSourceKind.ATTACK.value,
    )
    malformed_decisions = DecisionController()
    source_event = next(
        record
        for record in scenario.decisions.event_log.records
        if record.event_type == "model_destroyed"
    )
    malformed_payload = cast(dict[str, JsonValue], source_event.payload).copy()
    del malformed_payload["destruction_provenance"]
    malformed_decisions.event_log.append("model_destroyed", malformed_payload)
    completed_event = malformed_decisions.event_log.append(
        "attack_sequence_completed",
        {
            "sequence_id": scenario.attack_sequence.sequence_id,
            "attacker_player_id": scenario.attack_sequence.attacker_player_id,
            "attacking_unit_instance_id": scenario.attack_sequence.attacking_unit_instance_id,
        },
    )
    malformed_context = replace(
        scenario.context,
        decisions=malformed_decisions,
        dice_manager=DiceRollManager(
            scenario.state.game_id,
            event_log=malformed_decisions.event_log,
        ),
        attack_sequence_completed_event_id=completed_event.event_id,
    )

    with pytest.raises(
        GameLifecycleError,
        match="model_destroyed attribution payload is missing required fields",
    ):
        scenario.runtime.resolve_completed_attack_sequence(malformed_context)


@pytest.mark.parametrize(
    ("source_kind", "source_step"),
    [
        (DestructionSourceKind.ABILITY, "ability_resolution"),
        (DestructionSourceKind.DEADLY_DEMISE, "deadly_demise_collateral"),
        (DestructionSourceKind.ABILITY, "mortal_wound_feel_no_pain_continuation"),
        (DestructionSourceKind.ABILITY, "generic_rule_model_destruction"),
    ],
)
def test_non_attack_destruction_reconciles_horror_datasheet_from_composition(
    source_kind: DestructionSourceKind,
    source_step: str,
) -> None:
    scenario = _split_scenario(
        pink_datasheet_id="000002584",
        blue_datasheet_id="000002583",
        destruction_kind=source_kind.value,
        retained_horror_kinds=("blue",),
        non_attack_source_step=source_step,
    )
    starting_strength = scenario.state.starting_strength_record_for_unit(
        scenario.attached_unit_instance_id
    )

    lifecycle = GameLifecycle(
        state=scenario.state,
        decision_controller=scenario.decisions,
    )
    lifecycle._config = _game_config(scenario)
    lifecycle._runtime_content_bundle = _runtime_content_bundle(scenario)
    lifecycle._reconcile_catalog_model_state_changes()

    updated = _unit_by_id(scenario.state, scenario.bodyguard.unit_instance_id)
    assert updated.datasheet_id == "000002583"
    assert len(updated.own_models) == 1
    assert updated.own_models[0].is_alive
    assert (
        scenario.state.starting_strength_record_for_unit(scenario.attached_unit_instance_id)
        == starting_strength
    )
    rules_unit = rules_unit_view_by_id(
        state=scenario.state,
        unit_instance_id=scenario.bodyguard.unit_instance_id,
    )
    assert rules_unit.is_attached_rules_unit
    assert len(rules_unit.alive_models()) == 2
    replacement_events = tuple(
        record
        for record in scenario.decisions.event_log.records
        if record.event_type == CATALOG_UNIT_DATASHEET_REPLACED_EVENT
    )
    assert len(replacement_events) == 1
    restored_state = GameState.from_payload(scenario.state.to_payload())
    restored_decisions = DecisionController.from_payload(scenario.decisions.to_payload())
    assert (
        _unit_by_id(
            restored_state,
            scenario.bodyguard.unit_instance_id,
        ).datasheet_id
        == "000002583"
    )
    assert (
        len(
            tuple(
                record
                for record in restored_decisions.event_log.records
                if record.event_type == CATALOG_UNIT_DATASHEET_REPLACED_EVENT
            )
        )
        == 1
    )


@pytest.mark.parametrize("select_reaction", [False, True])
def test_non_attack_handoff_waits_for_optional_destruction_reaction_finalization(
    select_reaction: bool,
) -> None:
    scenario = _split_scenario(
        pink_datasheet_id="000002584",
        blue_datasheet_id="000002583",
        destruction_kind=DestructionSourceKind.ABILITY.value,
        retained_horror_kinds=("blue",),
        models_start_destroyed=False,
        emit_destruction_events=False,
    )
    pink_model_id = scenario.bodyguard.own_models[0].model_instance_id
    liability = PersistingEffect(
        effect_id="test:horrors:pending-reaction:liability",
        source_rule_id="test:horrors:pending-reaction:rule",
        owner_player_id=scenario.enemy_army.player_id,
        target_unit_instance_ids=(scenario.attached_unit_instance_id,),
        started_battle_round=scenario.state.battle_round,
        started_phase=BattlePhase.SHOOTING,
        expiration=EffectExpiration.end_phase(
            battle_round=scenario.state.battle_round,
            phase=BattlePhase.SHOOTING,
            player_id=scenario.enemy_army.player_id,
        ),
        effect_payload={"effect_kind": "test_rule_destruction_liability"},
    )
    scenario.state.record_persisting_effect(liability)
    reaction = DestructionReactionSource(
        source_id="test:horrors:pending-reaction:shoot-on-death",
        reaction_kind=DestructionReactionKind.SHOOT_ON_DEATH,
        source_rule_id="test:horrors:pending-reaction:source-rule",
    )
    scenario.state.record_model_destruction_reaction_sources(
        model_instance_id=pink_model_id,
        sources=(reaction,),
    )

    destruction = rule_model_destruction.destroy_model_with_rule_reactions(
        state=scenario.state,
        decisions=scenario.decisions,
        model_instance_id=pink_model_id,
        rules_unit_instance_id=scenario.attached_unit_instance_id,
        destroying_player_id=scenario.enemy_army.player_id,
        source_rule_id="test:horrors:pending-reaction:destruction",
        source_effect_ids=(liability.effect_id,),
        source_phase=BattlePhase.SHOOTING,
        source_step="ability_resolution",
        source_result_id="test:horrors:pending-reaction:source-result",
        completion_event_type="test_horror_rule_destruction_completed",
        completion_event_payload={"model_instance_id": pink_model_id},
    )

    assert destruction.status is not None
    assert destruction.status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    assert (
        scenario.runtime.reconcile_non_attack_model_destruction_events(
            state=scenario.state,
            decisions=scenario.decisions,
        )
        is False
    )
    pending_unit = _unit_by_id(scenario.state, scenario.bodyguard.unit_instance_id)
    assert pending_unit.datasheet_id == "000002584"
    assert pink_model_id in pending_unit.own_model_ids()
    restored_state = GameState.from_payload(scenario.state.to_payload())
    restored_decisions = DecisionController.from_payload(scenario.decisions.to_payload())
    assert (
        scenario.runtime.reconcile_non_attack_model_destruction_events(
            state=restored_state,
            decisions=restored_decisions,
        )
        is False
    )
    request = restored_decisions.queue.peek_next()
    selected_option_id = (
        reaction.source_id if select_reaction else DECLINE_DESTRUCTION_REACTION_OPTION_ID
    )
    result = DecisionResult.for_request(
        result_id=f"result:horrors:pending-reaction:{select_reaction}",
        request=request,
        selected_option_id=selected_option_id,
    )
    restored_decisions.submit_result(result)
    assert (
        rule_model_destruction.apply_rule_model_destruction_reaction_decision(
            state=restored_state,
            decisions=restored_decisions,
            result=result,
        )
        is None
    )

    assert (
        scenario.runtime.reconcile_non_attack_model_destruction_events(
            state=restored_state,
            decisions=restored_decisions,
        )
        is True
    )
    updated = _unit_by_id(restored_state, scenario.bodyguard.unit_instance_id)
    assert updated.datasheet_id == "000002583"
    assert len(updated.own_models) == 1
    assert updated.own_models[0].is_alive
    assert (
        scenario.runtime.reconcile_non_attack_model_destruction_events(
            state=restored_state,
            decisions=restored_decisions,
        )
        is False
    )
    assert (
        sum(
            record.event_type == RULE_MODEL_DESTRUCTION_FINALIZED_EVENT
            for record in restored_decisions.event_log.records
        )
        == 1
    )
    assert (
        sum(
            record.event_type == CATALOG_UNIT_DATASHEET_REPLACED_EVENT
            for record in restored_decisions.event_log.records
        )
        == 1
    )


@pytest.mark.parametrize("use_feel_no_pain", [False, True])
def test_selected_target_mortal_wounds_finalize_horror_composition_handoff(
    use_feel_no_pain: bool,
) -> None:
    scenario = _split_scenario(
        pink_datasheet_id="000002584",
        blue_datasheet_id="000002583",
        destruction_kind=DestructionSourceKind.ABILITY.value,
        retained_horror_kinds=("blue",),
        models_start_destroyed=False,
        emit_destruction_events=False,
    )
    scenario.state.game_id = "horror-selected-target-5"
    pink_model_id = scenario.bodyguard.own_models[0].model_instance_id
    fnp_source = FeelNoPainSource(
        source_id="test:horrors:selected-target:fnp-a",
        threshold=5,
    )
    if use_feel_no_pain:
        scenario.state.record_model_feel_no_pain_sources(
            model_instance_id=pink_model_id,
            sources=(
                fnp_source,
                FeelNoPainSource(
                    source_id="test:horrors:selected-target:fnp-b",
                    threshold=6,
                ),
            ),
        )
    selected_result = DecisionResult(
        result_id=f"result:horrors:selected-target:{use_feel_no_pain}",
        request_id="request:horrors:selected-target",
        decision_type="select_catalog_post_shoot_hit_target_effect",
        actor_id=scenario.enemy_army.player_id,
        selected_option_id=scenario.attached_unit_instance_id,
        payload={"target_unit_instance_id": scenario.attached_unit_instance_id},
    )
    resolution = resolve_selected_target_mortal_wound_effect(
        state=scenario.state,
        decisions=scenario.decisions,
        result=selected_result,
        selected_target_payload={"phase": BattlePhase.SHOOTING.value},
        record={"source_rule_id": "test:selected-target:mortal-wounds"},
        effect_payload={
            "effect": {
                "kind": "inflict_mortal_wounds",
                "parameters": [
                    {"key": "damage_kind", "value": "mortal_wounds"},
                    {"key": "mortal_wounds_expression", "value": "1"},
                    {"key": "roll_count", "value": 3},
                    {"key": "roll_expression", "value": "D6"},
                    {"key": "success_threshold", "value": 4},
                    {"key": "target_scope", "value": "selected_unit"},
                ],
            }
        },
        target_unit_ids=(scenario.attached_unit_instance_id,),
        recorded_effects_before_mortal_wounds=(),
        remaining_effect_records_after_mortal_wounds=(),
        remaining_effect_start_index=1,
    )
    if resolution.pending_status is None:
        assert resolution.resolved_payload is not None
    else:
        routed = None
        decision_index = 0
        while routed is None or routed.request is not None:
            request = scenario.decisions.queue.peek_next()
            is_model_choice = is_mortal_wound_model_request(request)
            selected_option_id = (
                pink_model_id
                if is_model_choice
                and pink_model_id in {option.option_id for option in request.options}
                else request.options[0].option_id
            )
            if not is_model_choice and use_feel_no_pain:
                selected_option_id = fnp_source.source_id
            decision_index += 1
            mortal_result = DecisionResult.for_request(
                result_id=f"result:horrors:selected-target:mortal:{decision_index}",
                request=request,
                selected_option_id=selected_option_id,
            )
            scenario.decisions.submit_result(mortal_result)
            dice_manager = None
            if not is_model_choice and use_feel_no_pain:
                fnp_spec = feel_no_pain_roll_spec(
                    source=fnp_source,
                    player_id=scenario.source_army.player_id,
                    model_instance_id=pink_model_id,
                    wound_index=1,
                )
                dice_manager = DiceRollManager(
                    scenario.state.game_id,
                    event_log=scenario.decisions.event_log,
                    injected_results=(
                        DiceRollResult.from_values(
                            roll_id="roll:horrors:selected-target:fnp",
                            spec=fnp_spec,
                            values=(1,),
                            source="fixed",
                        ),
                    ),
                )
            routed = resolve_mortal_wound_decision(
                state=scenario.state,
                decisions=scenario.decisions,
                request=request,
                result=mortal_result,
                next_request_id=f"request:horrors:selected-target:mortal:{decision_index + 1}",
                dice_manager=dice_manager,
            )
            if routed.request is not None:
                scenario.decisions.request_decision(routed.request)
        assert routed.application is not None

    lifecycle = GameLifecycle(
        state=scenario.state,
        decision_controller=scenario.decisions,
    )
    lifecycle._config = _game_config(scenario)
    lifecycle._runtime_content_bundle = _runtime_content_bundle(scenario)
    lifecycle._reconcile_catalog_model_state_changes()
    lifecycle._reconcile_catalog_model_state_changes()

    updated = _unit_by_id(scenario.state, scenario.bodyguard.unit_instance_id)
    assert updated.datasheet_id == "000002583"
    assert len(updated.own_models) == 1
    assert updated.own_models[0].is_alive
    finalizations = tuple(
        record
        for record in scenario.decisions.event_log.records
        if record.event_type == MORTAL_WOUND_MODEL_DESTRUCTIONS_FINALIZED_EVENT
    )
    assert len(finalizations) == 1
    finalization_payload = cast(dict[str, JsonValue], finalizations[0].payload)
    evidence = cast(dict[str, JsonValue], finalization_payload["destruction_evidence"])
    assert evidence["source_step"] == "selected_target_mortal_wounds"
    assert finalization_payload["physical_unit_instance_ids"] == [
        scenario.bodyguard.unit_instance_id
    ]
    assert finalization_payload["rules_unit_instance_ids"] == [scenario.attached_unit_instance_id]
    assert (
        sum(
            record.event_type == CATALOG_UNIT_DATASHEET_REPLACED_EVENT
            for record in scenario.decisions.event_log.records
        )
        == 1
    )


def test_deadly_demise_collateral_finalizes_horror_composition_handoff() -> None:
    scenario = _split_scenario(
        pink_datasheet_id="000002584",
        blue_datasheet_id="000002583",
        destruction_kind=DestructionSourceKind.ATTACK.value,
        retained_horror_kinds=("blue",),
        models_start_destroyed=False,
        emit_destruction_events=False,
    )
    scenario.state.active_player_id = scenario.source_army.player_id
    battlefield = scenario.state.battlefield_state
    assert battlefield is not None
    scenario.state.replace_battlefield_state(
        replace(
            battlefield,
            placed_armies=tuple(
                replace(
                    placed_army,
                    unit_placements=tuple(
                        replace(
                            placement,
                            model_placements=tuple(
                                replace(model_placement, pose=Pose.at(12.5, 10.0))
                                for model_placement in placement.model_placements
                            ),
                        )
                        if placement.unit_instance_id
                        == scenario.attack_sequence.attacking_unit_instance_id
                        else placement
                        for placement in placed_army.unit_placements
                    ),
                )
                for placed_army in battlefield.placed_armies
            ),
        )
    )
    pink_model = scenario.bodyguard.own_models[0]
    enemy_unit = _unit_by_id(
        scenario.state,
        scenario.attack_sequence.attacking_unit_instance_id,
    )
    enemy_model = replace(
        enemy_unit.own_models[0],
        characteristics=tuple(
            CharacteristicValue.from_raw(Characteristic.SAVE, 5)
            if value.characteristic is Characteristic.SAVE
            else value
            for value in enemy_unit.own_models[0].characteristics
        ),
    )
    enemy_unit = replace(enemy_unit, own_models=(enemy_model,))
    enemy_army = replace(
        scenario.enemy_army,
        units=tuple(
            enemy_unit if unit.unit_instance_id == enemy_unit.unit_instance_id else unit
            for unit in scenario.enemy_army.units
        ),
    )
    scenario.state.replace_army_definitions([scenario.source_army, enemy_army])
    deadly_demise_source = DestructionReactionSource(
        source_id="test:horrors:deadly-demise",
        reaction_kind=DestructionReactionKind.DEADLY_DEMISE,
        source_rule_id="test:horrors:deadly-demise-rule",
        payload={
            "trigger_roll_threshold": 6,
            "range_inches": 6.0,
            "mortal_wounds": {"kind": "fixed", "value": 1},
        },
        optional=False,
    )
    scenario.state.record_model_destruction_reaction_sources(
        model_instance_id=enemy_model.model_instance_id,
        sources=(deadly_demise_source,),
    )
    source_sequence = _attack_sequence(
        package=scenario.package,
        attacker=scenario.bodyguard,
        attacker_player_id=scenario.source_army.player_id,
        target=enemy_unit,
        target_unit_instance_id=enemy_unit.unit_instance_id,
    )
    base_pool = source_sequence.attack_pools[0]
    lethal_profile = replace(
        base_pool.weapon_profile,
        strength=CharacteristicValue.from_raw(Characteristic.STRENGTH, 20),
        armor_penetration=CharacteristicValue.from_raw(Characteristic.ARMOR_PENETRATION, 0),
        damage_profile=DamageProfile.fixed(enemy_model.wounds_remaining),
        keywords=(WeaponKeyword.TORRENT,),
        abilities=(),
    )
    lethal_pool = replace(base_pool, weapon_profile=lethal_profile)
    attack_sequence = AttackSequence.start(
        sequence_id="deadly-demise:horror-composition-handoff",
        attacker_player_id=scenario.source_army.player_id,
        attacking_unit_instance_id=scenario.attached_unit_instance_id,
        attack_pools=(lethal_pool,),
        source_phase=BattlePhase.SHOOTING,
    )
    scenario.state.replace_shooting_phase_state(
        ShootingPhaseState(
            battle_round=scenario.state.battle_round,
            active_player_id=scenario.source_army.player_id,
            selected_unit_ids=(scenario.attached_unit_instance_id,),
            shot_unit_ids=(scenario.attached_unit_instance_id,),
            attack_pools=attack_sequence.attack_pools,
            attack_sequence=attack_sequence,
        )
    )
    wound_spec = attack_sequence_wound_roll_spec(
        weapon_profile_id=lethal_pool.weapon_profile_id,
        attack_context_id=attack_sequence.attack_context_id(),
        attacker_player_id=scenario.source_army.player_id,
    )
    save_option = mandatory_save_option(
        save_options_for_model(
            model=enemy_model,
            armor_penetration=0,
        )
    )
    assert save_option is not None
    save_spec = saving_throw_roll_spec(
        save_kind=save_option.save_kind,
        player_id=scenario.enemy_army.player_id,
        allocated_model_id=enemy_model.model_instance_id,
        attack_context_id=attack_sequence.attack_context_id(),
    )
    deadly_demise_spec = deadly_demise_trigger_roll_spec(
        source=deadly_demise_source,
        player_id=scenario.enemy_army.player_id,
        model_instance_id=enemy_model.model_instance_id,
    )

    dice_manager = DiceRollManager(
        scenario.state.game_id,
        event_log=scenario.decisions.event_log,
        injected_results=(
            DiceRollResult.from_values(
                roll_id="roll:horrors:deadly-demise:wound",
                spec=wound_spec,
                values=(6,),
                source="fixed",
            ),
            DiceRollResult.from_values(
                roll_id="roll:horrors:deadly-demise:save",
                spec=save_spec,
                values=(1,),
                source="fixed",
            ),
            DiceRollResult.from_values(
                roll_id="roll:horrors:deadly-demise:trigger",
                spec=deadly_demise_spec,
                values=(6,),
                source="fixed",
            ),
        ),
    )
    remaining, allocated_model_ids, status = resolve_attack_sequence_until_blocked(
        state=scenario.state,
        decisions=scenario.decisions,
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(),
        attack_sequence=attack_sequence,
        already_allocated_model_ids=(),
        dice_manager=dice_manager,
    )

    for decision_index in range(128):
        if status is None:
            if remaining is None:
                break
            remaining, allocated_model_ids, status = resolve_attack_sequence_until_blocked(
                state=scenario.state,
                decisions=scenario.decisions,
                ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(),
                attack_sequence=remaining,
                already_allocated_model_ids=allocated_model_ids,
                dice_manager=dice_manager,
            )
            continue
        request = status.decision_request
        assert request is not None
        assert is_mortal_wound_model_request(request)
        selected_model_id = (
            pink_model.model_instance_id
            if pink_model.model_instance_id in {option.option_id for option in request.options}
            else request.options[0].option_id
        )
        mortal_result = DecisionResult.for_request(
            result_id=f"result:horrors:deadly-demise:model:{decision_index}",
            request=request,
            selected_option_id=selected_model_id,
        )
        scenario.decisions.submit_result(mortal_result)
        assert remaining is not None
        remaining, allocated_model_ids, status = apply_feel_no_pain_decision(
            state=scenario.state,
            decisions=scenario.decisions,
            ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(),
            attack_sequence=remaining,
            result=mortal_result,
            already_allocated_model_ids=allocated_model_ids,
            dice_manager=dice_manager,
        )
    else:
        raise AssertionError("Deadly Demise mortal wound model choices did not drain.")

    assert remaining is None
    assert status is None
    pink_destruction = next(
        cast(dict[str, JsonValue], record.payload)
        for record in scenario.decisions.event_log.records
        if record.event_type == "model_destroyed"
        and cast(dict[str, JsonValue], record.payload).get("model_instance_id")
        == pink_model.model_instance_id
    )
    attribution = ModelDestructionAttribution.from_model_destroyed_payload(pink_destruction)
    assert (
        attribution.destruction_provenance.destruction_source_kind
        is DestructionSourceKind.DEADLY_DEMISE
    )
    lifecycle = GameLifecycle(
        state=scenario.state,
        decision_controller=scenario.decisions,
    )
    lifecycle._config = _game_config(scenario)
    lifecycle._runtime_content_bundle = _runtime_content_bundle(scenario)
    lifecycle._reconcile_catalog_model_state_changes()
    lifecycle._reconcile_catalog_model_state_changes()

    updated = _unit_by_id(scenario.state, scenario.bodyguard.unit_instance_id)
    assert updated.datasheet_id == "000002583"
    assert tuple(model.model_instance_id for model in updated.own_models) == (
        scenario.bodyguard.own_models[1].model_instance_id,
    )
    assert (
        sum(
            record.event_type == CATALOG_UNIT_DATASHEET_REPLACED_EVENT
            for record in scenario.decisions.event_log.records
        )
        == 1
    )


def test_split_triggers_for_hazardous_but_not_non_attack_destruction() -> None:
    hazardous = _split_scenario(
        pink_datasheet_id="000002584",
        blue_datasheet_id="000002583",
        destruction_kind="hazardous",
    )
    status = hazardous.runtime.resolve_completed_attack_sequence(hazardous.context)
    assert status is not None
    assert status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION

    non_attack = _split_scenario(
        pink_datasheet_id="000002584",
        blue_datasheet_id="000002583",
        destruction_kind=DestructionSourceKind.ABILITY.value,
    )
    assert non_attack.runtime.resolve_completed_attack_sequence(non_attack.context) is None
    assert non_attack.decisions.queue.pending_requests == ()
    assert all(
        record.event_type != CATALOG_MODEL_MATERIALIZATION_ROLL_EVENT
        for record in non_attack.decisions.event_log.records
    )


@pytest.mark.parametrize("parent_battle_phase", [BattlePhase.SHOOTING, BattlePhase.MOVEMENT])
def test_adapter_submission_dispatches_model_placed_runtime_events(
    parent_battle_phase: BattlePhase,
) -> None:
    scenario = _split_scenario(
        pink_datasheet_id="000002584",
        blue_datasheet_id="000002583",
        destruction_kind="attack",
        parent_battle_phase=parent_battle_phase,
    )
    status = scenario.runtime.resolve_completed_attack_sequence(scenario.context)
    assert status is not None
    request = scenario.decisions.queue.peek_next()
    payload = _placement_payload(
        request=request,
        army=scenario.source_army,
        unit=scenario.bodyguard,
    )
    config = _game_config(scenario)
    lifecycle = GameLifecycle(
        state=scenario.state,
        decision_controller=scenario.decisions,
    )
    lifecycle._config = config
    lifecycle._shooting_phase_handler = ShootingPhaseHandler(
        ruleset_descriptor=config.ruleset_descriptor,
        army_catalog=config.army_catalog,
    )
    lifecycle._movement_phase_handler = MovementPhaseHandler(
        ruleset_descriptor=config.ruleset_descriptor,
        army_catalog=config.army_catalog,
    )
    seen_model_ids: list[str] = []
    seen_phase_evidence: list[tuple[str, str, str]] = []
    subscription = RuntimeContentEventSubscription(
        subscription_id="test:model-placed:subscription",
        source_rule_id="test:model-placed:rule",
        trigger_kind=TimingTriggerKind.MODEL_PLACED_ON_BATTLEFIELD,
        handler_id="test:model-placed:handler",
        filters={"player_id": scenario.source_army.player_id},
    )

    def record_placement(context: RuntimeContentEventContext) -> RuntimeContentEventResult:
        event_payload = cast(dict[str, JsonValue], context.event.event_payload)
        seen_model_ids.append(cast(str, event_payload["model_instance_id"]))
        seen_phase_evidence.append(
            (
                cast(str, event_payload["source_phase"]),
                cast(str, event_payload["action_phase"]),
                cast(str, event_payload["parent_battle_phase"]),
            )
        )
        lifecycle._runtime_content_activation_input_hash = (
            lifecycle_module._runtime_content_activation_input_hash(
                config=config,
                armies=tuple(context.state.army_definitions),
            )
        )
        return RuntimeContentEventResult.applied(
            subscription,
            replay_payload={"model_instance_id": event_payload["model_instance_id"]},
        )

    activation = RuntimeContentActivation.from_armies(
        armies=(scenario.source_army, scenario.enemy_army),
        catalog=config.army_catalog,
    )
    bundle = RuntimeContentBundle.from_contributions(
        activation=activation,
        armies=(scenario.source_army, scenario.enemy_army),
        catalog=config.army_catalog,
        contributions=(
            RuntimeContentContribution(
                contribution_id="test:horror:model-placed",
                event_subscriptions=(subscription,),
                event_handler_bindings=(
                    RuntimeContentEventHandlerBinding(
                        handler_id="test:model-placed:handler",
                        handler=record_placement,
                    ),
                ),
            ),
        ),
        base_ability_records=catalog_ability_records_from_catalog(config.army_catalog),
    )
    lifecycle._runtime_content_bundle = bundle
    lifecycle._runtime_content_activation_input_hash = (
        lifecycle_module._runtime_content_activation_input_hash(
            config=config,
            armies=(scenario.source_army, scenario.enemy_army),
        )
    )
    lifecycle._battle_round_flow = BattleRoundFlow(
        phase_handlers=lifecycle._phase_handlers(),
        runtime_modifier_registry=bundle.runtime_modifier_registry,
        runtime_event_index=bundle.event_index,
        ruleset_descriptor=config.ruleset_descriptor,
        army_catalog=config.army_catalog,
    )
    session = LocalGameSession(lifecycle=lifecycle)

    submission_status = session.submit_parameterized_payload(
        request_id=request.request_id,
        payload=payload,
        result_id="result:split:adapter",
    )

    assert submission_status.status_kind is not LifecycleStatusKind.INVALID
    assert tuple(sorted(seen_model_ids)) == tuple(
        sorted(cast(list[str], cast(dict[str, JsonValue], request.payload)["model_instance_ids"]))
    )
    assert set(seen_phase_evidence) == {
        (
            parent_battle_phase.value,
            BattlePhase.SHOOTING.value,
            parent_battle_phase.value,
        )
    }
    resolved_events = tuple(
        record
        for record in lifecycle.decision_controller.event_log.records
        if record.event_type == "runtime_content_event_resolved"
    )
    assert len(resolved_events) == 2
    assert all(
        cast(dict[str, JsonValue], record.payload)["trigger_kind"]
        == TimingTriggerKind.MODEL_PLACED_ON_BATTLEFIELD.value
        for record in resolved_events
    )


@pytest.mark.parametrize(
    ("parent_battle_phase", "out_of_phase_path"),
    [
        (BattlePhase.MOVEMENT, "fire_overwatch"),
        (BattlePhase.CHARGE, "source_backed_out_of_phase_shooting"),
    ],
)
def test_out_of_phase_split_restores_and_preserves_action_and_parent_phase_evidence(
    parent_battle_phase: BattlePhase,
    out_of_phase_path: str,
) -> None:
    scenario = _split_scenario(
        pink_datasheet_id="000002584",
        blue_datasheet_id="000002583",
        destruction_kind="attack",
        source_phase=BattlePhase.SHOOTING,
        parent_battle_phase=parent_battle_phase,
    )

    status = scenario.runtime.resolve_completed_attack_sequence(scenario.context)

    assert status is not None
    request = scenario.decisions.queue.peek_next()
    request_payload = cast(dict[str, JsonValue], request.payload)
    assert request_payload["action_phase"] == BattlePhase.SHOOTING.value
    assert request_payload["parent_battle_phase"] == parent_battle_phase.value
    assert request_payload["source_phase"] == parent_battle_phase.value
    restored_state = GameState.from_payload(scenario.state.to_payload())
    restored_decisions = DecisionController.from_payload(scenario.decisions.to_payload())
    restored_request = restored_decisions.queue.peek_next()
    result = _parameterized_result(
        request=restored_request,
        payload=_placement_payload(
            request=restored_request,
            army=scenario.source_army,
            unit=scenario.bodyguard,
        ),
        result_id=f"result:split:{out_of_phase_path}",
    )
    assert (
        invalid_catalog_model_materialization_placement_status(
            state=restored_state,
            request=restored_request,
            result=result,
            decisions=restored_decisions,
            ability_indexes_by_player_id=scenario.runtime.ability_indexes_by_player_id,
            ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(),
            army_catalog=scenario.package.army_catalog,
        )
        is None
    )
    restored_decisions.submit_result(result)
    placements = apply_recorded_catalog_model_materialization_placement(
        state=restored_state,
        decisions=restored_decisions,
        request=restored_request,
        result=result,
        ability_indexes_by_player_id=scenario.runtime.ability_indexes_by_player_id,
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(),
        army_catalog=scenario.package.army_catalog,
    )

    assert {placement.source_phase for placement in placements} == {parent_battle_phase.value}
    for event_type in (CATALOG_MODELS_MATERIALIZED_EVENT, "battlefield_models_placed"):
        event = next(
            record
            for record in restored_decisions.event_log.records
            if record.event_type == event_type
        )
        event_payload = cast(dict[str, JsonValue], event.payload)
        assert event_payload["action_phase"] == BattlePhase.SHOOTING.value
        assert event_payload["parent_battle_phase"] == parent_battle_phase.value
        assert event_payload["source_phase"] == parent_battle_phase.value
    replayed = DecisionController.from_payload(restored_decisions.to_payload())
    assert replayed.to_payload() == restored_decisions.to_payload()


def test_overwatch_split_resumes_completed_sequence_and_resolves_reaction_frame() -> None:
    scenario = _split_scenario(
        pink_datasheet_id="000002584",
        blue_datasheet_id="000002583",
        destruction_kind=DestructionSourceKind.ATTACK.value,
        source_phase=BattlePhase.SHOOTING,
        parent_battle_phase=BattlePhase.MOVEMENT,
        pink_model_count=2,
        roll_values=(6, 6),
    )
    _record_successful_materialization_rolls(scenario)
    scenario.state.replace_out_of_phase_shooting_state(
        OutOfPhaseShootingState(
            battle_round=scenario.state.battle_round,
            player_id=scenario.enemy_army.player_id,
            parent_phase=BattlePhase.MOVEMENT,
            source_rule_id="core:fire-overwatch",
            source_decision_request_id="request:fire-overwatch",
            source_decision_result_id="result:fire-overwatch",
            source_context={
                "triggering_enemy_unit_instance_id": scenario.attached_unit_instance_id,
            },
            selected_unit_instance_id=scenario.attack_sequence.attacking_unit_instance_id,
            target_unit_ids=(scenario.attached_unit_instance_id,),
            attack_pools=scenario.attack_sequence.attack_pools,
            attack_sequence=scenario.attack_sequence,
        )
    )
    lifecycle = GameLifecycle(
        state=scenario.state,
        decision_controller=scenario.decisions,
    )
    _configure_phase_lifecycle(lifecycle=lifecycle, scenario=scenario)

    split_status = lifecycle.advance_until_decision_or_terminal()

    assert split_status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    split_request = scenario.decisions.queue.peek_next()
    out_of_phase = scenario.state.out_of_phase_shooting_state
    assert out_of_phase is not None
    assert out_of_phase.attack_sequence is None
    assert out_of_phase.pending_completed_attack_sequence == scenario.attack_sequence
    phase_kind = battle_phase_kind_from_token(BattlePhase.MOVEMENT.value)
    reaction_window = ReactionWindow(
        timing_window=TimingWindow(
            window_id="window:fire-overwatch:horror-split",
            descriptor=TimingWindowDescriptor(
                descriptor_id="window:fire-overwatch:horror-split:descriptor",
                trigger_kind=TimingTriggerKind.DURING_PHASE,
                source_rule_id="core:fire-overwatch",
                phase=phase_kind,
                source_step="movement",
            ),
            game_id=scenario.state.game_id,
            battle_round=scenario.state.battle_round,
            active_player_id=scenario.state.active_player_id,
            phase=phase_kind,
        ),
        eligible_player_ids=(scenario.enemy_army.player_id,),
    )
    reaction_queue = ReactionQueue.from_payload(
        {
            "frames": [
                ReactionQueueFrame(
                    reaction_window=reaction_window,
                    parent_phase=phase_kind,
                    parent_step="movement",
                    resume_token="resume:fire-overwatch:horror-split",
                    request_id=split_request.request_id,
                ).to_payload()
            ]
        }
    )
    lifecycle = GameLifecycle(
        state=scenario.state,
        decision_controller=scenario.decisions,
        reaction_queue=reaction_queue,
    )
    _configure_phase_lifecycle(lifecycle=lifecycle, scenario=scenario)
    restored = _restored_phase_lifecycle(lifecycle=lifecycle, scenario=scenario)

    for placement_index in range(1, 3):
        restored_state = restored.state
        assert restored_state is not None
        restored_out_of_phase = restored_state.out_of_phase_shooting_state
        assert restored_out_of_phase is not None
        assert restored_out_of_phase.pending_completed_attack_sequence is not None
        restored_request = restored.decision_controller.queue.peek_next()
        assert restored.reaction_queue.frames[-1].request_id == restored_request.request_id
        session = LocalGameSession(lifecycle=restored)
        status = session.submit_parameterized_payload(
            request_id=restored_request.request_id,
            payload=_placement_payload(
                request=restored_request,
                army=scenario.source_army,
                unit=scenario.bodyguard,
                y_offset=-(placement_index - 1) * 1.2,
            ),
            result_id=f"result:fire-overwatch:horror-split:placement:{placement_index}",
        )
        assert status.status_kind is not LifecycleStatusKind.INVALID
        if placement_index == 1:
            assert status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
            assert status.decision_request is not None
            assert restored.reaction_queue.frames
            assert (
                restored.reaction_queue.frames[-1].request_id == status.decision_request.request_id
            )
            restored = _restored_phase_lifecycle(lifecycle=restored, scenario=scenario)

    assert restored.reaction_queue.frames == ()
    restored_state = restored.state
    assert restored_state is not None
    assert restored_state.out_of_phase_shooting_state is None
    assert _unit_by_id(restored_state, scenario.bodyguard.unit_instance_id).datasheet_id == (
        "000002583"
    )
    assert (
        sum(
            record.event_type == "out_of_phase_shooting_completed"
            for record in restored.decision_controller.event_log.records
        )
        == 1
    )
    assert (
        sum(
            record.event_type == CATALOG_UNIT_DATASHEET_REPLACED_EVENT
            for record in restored.decision_controller.event_log.records
        )
        == 1
    )


def test_fight_interrupt_split_resumes_completed_activation_and_resolves_reaction_frame() -> None:
    scenario = _split_scenario(
        pink_datasheet_id="000002584",
        blue_datasheet_id="000002583",
        destruction_kind=DestructionSourceKind.ATTACK.value,
        source_phase=BattlePhase.FIGHT,
    )
    _record_successful_materialization_rolls(scenario)
    config = _game_config(scenario)
    policy = config.ruleset_descriptor.fight_policy
    active_player_id = scenario.state.active_player_id
    assert active_player_id is not None
    fight_state = FightPhaseState.start(
        battle_round=scenario.state.battle_round,
        active_player_id=active_player_id,
        policy=policy,
        engaged_at_fight_step_start_unit_ids=(
            scenario.attack_sequence.attacking_unit_instance_id,
            scenario.attached_unit_instance_id,
        ),
        fights_first_registry=FightsFirstRegistry(),
    ).with_current_step(
        current_step=FightPhaseStepKind.FIGHT,
        policy=policy,
    )
    activation = FightActivationSelection(
        player_id=scenario.enemy_army.player_id,
        battle_round=scenario.state.battle_round,
        unit_instance_id=scenario.attack_sequence.attacking_unit_instance_id,
        ordering_band=fight_state.current_ordering_band,
        fight_type=policy.fight_types[0],
        eligibility_reasons=(FightEligibilityKind.ENGAGED_AT_FIGHT_STEP_START,),
        request_id="request:fight-interrupt:horror-split",
        result_id="result:fight-interrupt:horror-split",
        interrupt_id="interrupt:fight:horror-split",
    )
    fight_state = (
        fight_state.with_activation(activation)
        .with_active_activation(activation)
        .with_attack_sequence_update(
            attack_sequence=scenario.attack_sequence,
            allocated_model_ids_this_phase=(),
        )
    )
    scenario.state.replace_fight_phase_state(fight_state)
    lifecycle = GameLifecycle(
        state=scenario.state,
        decision_controller=scenario.decisions,
    )
    _configure_phase_lifecycle(lifecycle=lifecycle, scenario=scenario)

    split_status = lifecycle.advance_until_decision_or_terminal()

    assert split_status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    split_request = scenario.decisions.queue.peek_next()
    pending_fight_state = scenario.state.fight_phase_state
    assert pending_fight_state is not None
    assert pending_fight_state.attack_sequence is None
    assert pending_fight_state.pending_completed_attack_sequence == scenario.attack_sequence
    phase_kind = battle_phase_kind_from_token(BattlePhase.FIGHT.value)
    reaction_window = ReactionWindow(
        timing_window=TimingWindow(
            window_id="window:fight-interrupt:horror-split",
            descriptor=TimingWindowDescriptor(
                descriptor_id="window:fight-interrupt:horror-split:descriptor",
                trigger_kind=TimingTriggerKind.DURING_PHASE,
                source_rule_id="core:counter-offensive",
                phase=phase_kind,
                source_step="fight",
            ),
            game_id=scenario.state.game_id,
            battle_round=scenario.state.battle_round,
            active_player_id=scenario.state.active_player_id,
            phase=phase_kind,
        ),
        eligible_player_ids=(scenario.enemy_army.player_id,),
    )
    reaction_queue = ReactionQueue.from_payload(
        {
            "frames": [
                ReactionQueueFrame(
                    reaction_window=reaction_window,
                    parent_phase=phase_kind,
                    parent_step="fight",
                    resume_token="resume:fight-interrupt:horror-split",
                    request_id=split_request.request_id,
                ).to_payload()
            ]
        }
    )
    lifecycle = GameLifecycle(
        state=scenario.state,
        decision_controller=scenario.decisions,
        reaction_queue=reaction_queue,
    )
    _configure_phase_lifecycle(lifecycle=lifecycle, scenario=scenario)
    restored = _restored_phase_lifecycle(lifecycle=lifecycle, scenario=scenario)
    restored_state = restored.state
    assert restored_state is not None
    restored_fight_state = restored_state.fight_phase_state
    assert restored_fight_state is not None
    assert restored_fight_state.pending_completed_attack_sequence is not None
    restored_request = restored.decision_controller.queue.peek_next()
    session = LocalGameSession(lifecycle=restored)

    status = session.submit_parameterized_payload(
        request_id=restored_request.request_id,
        payload=_placement_payload(
            request=restored_request,
            army=scenario.source_army,
            unit=scenario.bodyguard,
        ),
        result_id="result:fight-interrupt:horror-split:placement",
    )

    assert status.status_kind is not LifecycleStatusKind.INVALID
    assert restored.reaction_queue.frames == ()
    completed_fight_state = restored_state.fight_phase_state
    assert completed_fight_state is not None
    assert completed_fight_state.active_activation is None
    assert completed_fight_state.pending_completed_attack_sequence is None
    assert _unit_by_id(restored_state, scenario.bodyguard.unit_instance_id).datasheet_id == (
        "000002583"
    )
    assert (
        sum(
            record.event_type == "unit_has_fought"
            for record in restored.decision_controller.event_log.records
        )
        == 1
    )
    assert (
        sum(
            record.event_type == CATALOG_UNIT_DATASHEET_REPLACED_EVENT
            for record in restored.decision_controller.event_log.records
        )
        == 1
    )


@pytest.mark.parametrize(
    "tamper_kind",
    [
        "source_rule",
        "clause",
        "descriptor",
        "roll",
        "result_count",
        "model_profile",
        "wargear",
        "model_ids",
    ],
)
def test_restored_split_request_revalidates_authoritative_catalog_and_roll_evidence(
    tamper_kind: str,
) -> None:
    scenario = _split_scenario(
        pink_datasheet_id="000002584",
        blue_datasheet_id="000002583",
        destruction_kind="attack",
    )
    assert scenario.runtime.resolve_completed_attack_sequence(scenario.context) is not None
    lifecycle_payload = copy.deepcopy(
        GameLifecycle(
            state=scenario.state,
            decision_controller=scenario.decisions,
        ).to_payload()
    )
    _tamper_materialization_lifecycle_payload(lifecycle_payload, tamper_kind=tamper_kind)
    restored = GameLifecycle.from_payload(lifecycle_payload)
    restored_state = restored.state
    assert restored_state is not None
    request = restored.decision_controller.queue.peek_next()
    result = _parameterized_result(
        request=request,
        payload=_placement_payload(
            request=request,
            army=scenario.source_army,
            unit=scenario.bodyguard,
        ),
        result_id=f"result:split:tampered:{tamper_kind}",
    )

    invalid = invalid_catalog_model_materialization_placement_status(
        state=restored_state,
        request=request,
        result=result,
        decisions=restored.decision_controller,
        ability_indexes_by_player_id=scenario.runtime.ability_indexes_by_player_id,
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(),
        army_catalog=scenario.package.army_catalog,
    )

    assert invalid is not None
    assert invalid.status_kind is LifecycleStatusKind.INVALID
    assert restored.decision_controller.queue.peek_next() == request


@pytest.mark.parametrize(
    ("tamper_kind", "expected_error"),
    [
        ("materialized_game_id", "Catalog materialization game identity drift"),
        ("missing_request_id", "Catalog materialization request_id must be a string"),
        (
            "missing_decision_record",
            "Catalog materialization lacks one accepted decision record",
        ),
        ("malformed_request_payload", "Catalog materialization request payload is malformed"),
        (
            "inactive_source",
            "Catalog materialization does not resolve to one active source provider",
        ),
        ("decision_identity", "Catalog materialization decision identity drift"),
        ("request_payload", "Catalog materialization request payload drift"),
        ("malformed_result_payload", "Catalog materialization result payload is malformed"),
        ("accepted_placement", "Catalog materialization accepted placement drift"),
        ("accepted_model_set", "Catalog materialization accepted model set drift"),
        ("roll_identity", "Catalog materialization roll identity drift"),
        ("roll_context", "Catalog materialization roll context drift"),
        (
            "completion_sequence",
            "Catalog materialization attack completion sequence drift",
        ),
        ("roll_before_completion", "Catalog materialization roll precedes its attack completion"),
        ("destroyed_model_source", "Catalog materialization destroyed model source drift"),
        ("destruction_evidence", "Catalog materialization destruction evidence drift"),
        ("malformed_roll_payload", "Catalog materialization roll payload is malformed"),
        ("roll_specification", "Catalog materialization roll specification drift"),
        ("unsuccessful_roll", "Catalog materialization successful roll result drift"),
        ("evidence_order", "Catalog materialization evidence order drift"),
        ("missing_terminal", "Catalog materialization lacks its placement terminal event"),
        ("terminal_payload", "Catalog materialization placement terminal payload drift"),
        (
            "request_provenance",
            "Catalog materialization decision request provenance drift",
        ),
        (
            "record_provenance",
            "Catalog materialization decision record provenance drift",
        ),
        ("malformed_materialized_event", "catalog materialization event payload is malformed"),
        (
            "malformed_completion_event",
            "catalog materialization attack completion event payload is malformed",
        ),
        ("completion_payload", "Catalog materialization completion payload drift"),
        ("invalid_battle_round", "Catalog materialization battle_round must be an integer"),
    ],
)
def test_authenticated_materialization_rejects_corrupted_evidence_graph(
    tamper_kind: str,
    expected_error: str,
) -> None:
    scenario, event_records, decision_records = _authenticated_materialization_evidence(
        destruction_kind="attack"
    )
    tampered_events, tampered_records = _corrupt_authenticated_materialization_evidence(
        scenario=scenario,
        event_records=event_records,
        decision_records=decision_records,
        tamper_kind=tamper_kind,
    )

    with pytest.raises(GameLifecycleError, match=expected_error):
        authenticated_catalog_materialized_model_payloads_by_unit_id(
            game_id=scenario.state.game_id,
            catalog=scenario.package.army_catalog,
            expected_armies=(scenario.source_army, scenario.enemy_army),
            event_records=tampered_events,
            decision_records=tampered_records,
        )


@pytest.mark.parametrize(
    ("tamper_kind", "expected_error"),
    [
        (
            "malformed_application",
            "Catalog materialization Hazardous evidence is malformed",
        ),
        (
            "malformed_applications",
            "Catalog materialization Hazardous evidence is malformed",
        ),
        (
            "malformed_application_item",
            "Catalog materialization Hazardous evidence is malformed",
        ),
        (
            "missing_destroyed_model_id",
            "Catalog materialization model_instance_id must be a string",
        ),
        ("wrong_sequence", "Catalog materialization destruction evidence drift"),
    ],
)
def test_authenticated_hazardous_materialization_rejects_corrupted_provenance(
    tamper_kind: str,
    expected_error: str,
) -> None:
    scenario, event_records, decision_records = _authenticated_materialization_evidence(
        destruction_kind="hazardous"
    )
    events = list(event_records)
    hazardous_index = _unique_event_index(events, "hazardous_mortal_wounds_applied")
    hazardous_payload = copy.deepcopy(cast(dict[str, JsonValue], events[hazardous_index].payload))
    if tamper_kind == "malformed_application":
        hazardous_payload["mortal_wound_application"] = None
    elif tamper_kind == "malformed_applications":
        application = cast(dict[str, JsonValue], hazardous_payload["mortal_wound_application"])
        application["applications"] = None
    elif tamper_kind == "malformed_application_item":
        application = cast(dict[str, JsonValue], hazardous_payload["mortal_wound_application"])
        application["applications"] = [None]
    elif tamper_kind == "missing_destroyed_model_id":
        application = cast(dict[str, JsonValue], hazardous_payload["mortal_wound_application"])
        applications = cast(list[JsonValue], application["applications"])
        cast(dict[str, JsonValue], applications[0])["model_instance_id"] = None
    elif tamper_kind == "wrong_sequence":
        hazardous_payload["sequence_id"] = "attack-sequence:unrelated"
    else:
        raise AssertionError(f"Unsupported Hazardous evidence tamper: {tamper_kind}")
    events[hazardous_index] = replace(events[hazardous_index], payload=hazardous_payload)

    with pytest.raises(GameLifecycleError, match=expected_error):
        authenticated_catalog_materialized_model_payloads_by_unit_id(
            game_id=scenario.state.game_id,
            catalog=scenario.package.army_catalog,
            expected_armies=(scenario.source_army, scenario.enemy_army),
            event_records=tuple(events),
            decision_records=decision_records,
        )


def test_authenticated_materialization_rejects_duplicate_event_identity() -> None:
    scenario, event_records, decision_records = _authenticated_materialization_evidence(
        destruction_kind="attack"
    )

    with pytest.raises(
        GameLifecycleError,
        match="Catalog materialization event identities are duplicated",
    ):
        authenticated_catalog_materialized_model_payloads_by_unit_id(
            game_id=scenario.state.game_id,
            catalog=scenario.package.army_catalog,
            expected_armies=(scenario.source_army, scenario.enemy_army),
            event_records=(*event_records, event_records[0]),
            decision_records=decision_records,
        )


def test_authenticated_materialization_rejects_reused_roll_and_decision_evidence() -> None:
    scenario, event_records, decision_records = _authenticated_materialization_evidence(
        destruction_kind="attack"
    )
    events = list(event_records)
    materialized_index = _unique_event_index(events, CATALOG_MODELS_MATERIALIZED_EVENT)
    materialized = events[materialized_index]
    terminal = events[materialized_index + 1]
    cloned_materialized = replace(
        materialized,
        event_id="event:catalog-materialization:reused-evidence",
    )
    terminal_payload = copy.deepcopy(cast(dict[str, JsonValue], terminal.payload))
    terminal_payload["source_event_id"] = cloned_materialized.event_id
    cloned_terminal = replace(
        terminal,
        event_id="event:catalog-materialization:reused-evidence:terminal",
        payload=terminal_payload,
    )

    with pytest.raises(GameLifecycleError, match="Catalog materialization evidence is reused"):
        authenticated_catalog_materialized_model_payloads_by_unit_id(
            game_id=scenario.state.game_id,
            catalog=scenario.package.army_catalog,
            expected_armies=(scenario.source_army, scenario.enemy_army),
            event_records=(*events, cloned_materialized, cloned_terminal),
            decision_records=decision_records,
        )


def test_authenticated_materialization_requires_active_provider_binding(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scenario, event_records, decision_records = _authenticated_materialization_evidence(
        destruction_kind="attack"
    )

    def no_bindings(_runtime: CatalogModelMaterializationRuntime) -> tuple[Any, ...]:
        return ()

    monkeypatch.setattr(CatalogModelMaterializationRuntime, "bindings", no_bindings)

    with pytest.raises(
        GameLifecycleError,
        match="Catalog materialization has no active runtime provider binding",
    ):
        authenticated_catalog_materialized_model_payloads_by_unit_id(
            game_id=scenario.state.game_id,
            catalog=scenario.package.army_catalog,
            expected_armies=(scenario.source_army, scenario.enemy_army),
            event_records=event_records,
            decision_records=decision_records,
        )


def test_authenticated_second_split_rejects_missing_required_model_source() -> None:
    scenario, event_records, decision_records = _authenticated_materialization_evidence(
        destruction_kind="attack",
        destroyed_horror_kinds=("blue",),
    )
    source_model = scenario.source_army.units[0].own_models[0]
    assert "horror-materialization:blue-horror" in source_model.source_ids
    tampered_model = replace(
        source_model,
        source_ids=tuple(
            source_id
            for source_id in source_model.source_ids
            if source_id != "horror-materialization:blue-horror"
        ),
    )
    tampered_unit = replace(scenario.source_army.units[0], own_models=(tampered_model,))
    tampered_army = replace(
        scenario.source_army,
        units=(tampered_unit, *scenario.source_army.units[1:]),
    )

    with pytest.raises(
        GameLifecycleError,
        match="Catalog materialization destroyed model source drift",
    ):
        authenticated_catalog_materialized_model_payloads_by_unit_id(
            game_id=scenario.state.game_id,
            catalog=scenario.package.army_catalog,
            expected_armies=(tampered_army, scenario.enemy_army),
            event_records=event_records,
            decision_records=decision_records,
        )


@pytest.mark.parametrize(
    ("invalid_model_ids", "expected_error"),
    [
        (None, "Catalog materialization model_instance_ids must be a string list"),
        ([""], "Catalog materialization model_instance_ids must be a string list"),
        (
            ["duplicate", "duplicate"],
            "Catalog materialization model_instance_ids contains duplicates",
        ),
    ],
)
def test_catalog_materialization_required_model_ids_fail_closed(
    invalid_model_ids: JsonValue,
    expected_error: str,
) -> None:
    _scenario, _event_records, decision_records = _authenticated_materialization_evidence(
        destruction_kind="attack"
    )
    request_payload = copy.deepcopy(cast(dict[str, JsonValue], decision_records[0].request.payload))
    request_payload["model_instance_ids"] = invalid_model_ids

    with pytest.raises(GameLifecycleError, match=expected_error):
        _required_string_list(request_payload, "model_instance_ids")


def test_horror_catalog_keeps_materialized_profiles_out_of_mustering() -> None:
    package = horrors_package()
    for pink_datasheet_id, blue_datasheet_id in (
        ("000002584", "000002583"),
        ("000004127", "000004128"),
    ):
        pink = package.army_catalog.datasheet_by_id(pink_datasheet_id)
        assert tuple(profile.model_profile_id for profile in pink.composition) == (
            f"{pink_datasheet_id}:pink-horrors",
        )
        materialized = pink.model_profile_by_id(f"{pink_datasheet_id}:blue-horror-brimstone-horror")
        assert materialized.base_size.diameter_mm == 25.0
        pink_unit = _single_model_unit(
            package=package,
            army_id="army-catalog",
            unit_selection_id=f"pink-{pink_datasheet_id}",
            datasheet_id=pink_datasheet_id,
            model_profile_id=f"{pink_datasheet_id}:pink-horrors",
        )
        blue_unit = _single_model_unit(
            package=package,
            army_id="army-catalog",
            unit_selection_id=f"blue-{blue_datasheet_id}",
            datasheet_id=blue_datasheet_id,
            model_profile_id=f"{blue_datasheet_id}:blue-horrors",
        )
        assert pink_unit.own_models[0].wargear_ids == (
            f"{pink_datasheet_id}:coruscating-pink-flames",
            f"{pink_datasheet_id}:pink-claws",
        )
        assert blue_unit.own_models[0].wargear_ids == (
            f"{blue_datasheet_id}:coruscating-blue-flames",
            f"{blue_datasheet_id}:blue-claws",
        )


def _split_scenario(
    *,
    pink_datasheet_id: str,
    blue_datasheet_id: str,
    destruction_kind: str,
    source_phase: BattlePhase = BattlePhase.SHOOTING,
    parent_battle_phase: BattlePhase | None = None,
    attached: bool = True,
    pink_model_count: int = 1,
    roll_values: tuple[int, ...] = (6,),
    destroyed_horror_kinds: tuple[str, ...] = (),
    retained_horror_kinds: tuple[str, ...] = (),
    event_sequence_matches: bool = False,
    non_attack_source_step: str = "ability_resolution",
    models_start_destroyed: bool = True,
    emit_destruction_events: bool = True,
) -> _SplitScenario:
    package = horrors_package()
    bodyguard = _model_count_unit(
        package=package,
        army_id="army-horrors",
        unit_selection_id="pink-bodyguard",
        datasheet_id=pink_datasheet_id,
        model_profile_id=f"{pink_datasheet_id}:pink-horrors",
        model_count=pink_model_count,
    )
    models_to_destroy = (
        tuple(
            _retained_horror_model(
                package=package,
                pink_datasheet_id=pink_datasheet_id,
                bodyguard=bodyguard,
                horror_kind=horror_kind,
                index=index,
            )
            for index, horror_kind in enumerate(destroyed_horror_kinds, start=1)
        )
        if destroyed_horror_kinds
        else bodyguard.own_models
    )
    destroyed_models = tuple(
        replace(model, wounds_remaining=0) if models_start_destroyed else model
        for model in models_to_destroy
    )
    retained_models = tuple(
        _retained_horror_model(
            package=package,
            pink_datasheet_id=pink_datasheet_id,
            bodyguard=bodyguard,
            horror_kind=horror_kind,
            index=index,
        )
        for index, horror_kind in enumerate(
            retained_horror_kinds,
            start=len(destroyed_horror_kinds) + 1,
        )
    )
    bodyguard = replace(bodyguard, own_models=(*destroyed_models, *retained_models))
    leader = _single_model_unit(
        package=package,
        army_id="army-horrors",
        unit_selection_id="blue-leader",
        datasheet_id=blue_datasheet_id,
        model_profile_id=f"{blue_datasheet_id}:blue-horrors",
    )
    attacker = _single_model_unit(
        package=package,
        army_id="army-enemy",
        unit_selection_id="blue-attacker",
        datasheet_id=blue_datasheet_id,
        model_profile_id=f"{blue_datasheet_id}:blue-horrors",
    )
    attached_unit_id = "attached-unit:army-horrors:pink-and-leader"
    formation = (
        AttachedUnitFormation(
            attached_unit_instance_id=attached_unit_id,
            bodyguard_unit_instance_id=bodyguard.unit_instance_id,
            leader_unit_instance_ids=(leader.unit_instance_id,),
            component_unit_instance_ids=tuple(
                sorted((bodyguard.unit_instance_id, leader.unit_instance_id))
            ),
            source_id="test:horrors:attached",
            attachment_source_ids=("test:horrors:attached:eligibility",),
        )
        if attached
        else None
    )
    source_army = _army(
        package=package,
        army_id="army-horrors",
        player_id="player-horrors",
        force_disposition_id="take-and-hold",
        units=(bodyguard, leader),
        attached_units=(() if formation is None else (formation,)),
    )
    enemy_army = _army(
        package=package,
        army_id="army-enemy",
        player_id="player-enemy",
        force_disposition_id="purge-the-foe",
        units=(attacker,),
    )
    battlefield = BattlefieldRuntimeState(
        battlefield_id="horror-split-battlefield",
        battlefield_width_inches=60.0,
        battlefield_depth_inches=44.0,
        placed_armies=(
            PlacedArmy(
                army_id=source_army.army_id,
                player_id=source_army.player_id,
                unit_placements=tuple(
                    placement
                    for placement in (
                        _alive_unit_placement_or_none(
                            source_army,
                            bodyguard,
                            origin=Pose.at(10.0, 10.0),
                        ),
                        _unit_placement(source_army, leader, Pose.at(10.0, 11.6)),
                    )
                    if placement is not None
                ),
            ),
            PlacedArmy(
                army_id=enemy_army.army_id,
                player_id=enemy_army.player_id,
                unit_placements=(_unit_placement(enemy_army, attacker, Pose.at(30.0, 10.0)),),
            ),
        ),
        removed_model_ids=tuple(
            model.model_instance_id for model in destroyed_models if not model.is_alive
        ),
    )
    attack_sequence = _attack_sequence(
        package=package,
        attacker=(bodyguard if destruction_kind == "hazardous" else attacker),
        attacker_player_id=(
            source_army.player_id if destruction_kind == "hazardous" else enemy_army.player_id
        ),
        target=(attacker if destruction_kind == "hazardous" else bodyguard),
        target_unit_instance_id=(
            attacker.unit_instance_id
            if destruction_kind == "hazardous"
            else (attached_unit_id if attached else bodyguard.unit_instance_id)
        ),
        source_phase=source_phase,
    )
    resolved_parent_battle_phase = (
        source_phase if parent_battle_phase is None else parent_battle_phase
    )
    state = battle_state_with_armies(
        armies=(source_army, enemy_army),
        battlefield=battlefield,
        active_player_id=attack_sequence.attacker_player_id,
        phase=resolved_parent_battle_phase,
    )
    decisions = DecisionController()
    if destruction_kind == "hazardous" and emit_destruction_events:
        decisions.event_log.append(
            "hazardous_mortal_wounds_applied",
            {
                "sequence_id": attack_sequence.sequence_id,
                "mortal_wound_application": {
                    "applications": [
                        {
                            "model_instance_id": model.model_instance_id,
                            "destroyed": True,
                        }
                        for model in destroyed_models
                    ]
                },
            },
        )
    elif emit_destruction_events:
        for model in destroyed_models:
            source_kind = DestructionSourceKind(destruction_kind)
            attribution = (
                ModelDestructionAttribution.for_attack(
                    destroying_player_id=enemy_army.player_id,
                    attacking_unit_instance_id=attacker.unit_instance_id,
                    attacking_model_instance_id=attacker.own_models[0].model_instance_id,
                    weapon_profile=attack_sequence.attack_pools[0].weapon_profile,
                    attack_context_id=f"{attack_sequence.sequence_id}:pool-001:attack-001",
                )
                if source_kind is DestructionSourceKind.ATTACK
                else ModelDestructionAttribution.for_non_attack(
                    destroying_player_id=enemy_army.player_id,
                    source_kind=source_kind,
                    source_rules_unit_instance_id=attacker.unit_instance_id,
                    source_model_instance_id=None,
                )
            )
            removal_record = ModelRemovalRecord(
                model_instance_id=model.model_instance_id,
                removal_kind=BattlefieldRemovalKind.DESTROYED,
                source_phase=source_phase.value,
                source_step=(
                    "damage"
                    if source_kind is DestructionSourceKind.ATTACK
                    else non_attack_source_step
                ),
                source_rule_id="test:horrors:destruction",
                source_event_id=f"test:horrors:destruction:{model.model_instance_id}",
            )
            destroyed_event = decisions.event_log.append(
                "model_destroyed",
                validate_json_value(
                    {
                        "phase": source_phase.value,
                        **attribution.to_payload(),
                        "sequence_id": (
                            attack_sequence.sequence_id
                            if source_kind is DestructionSourceKind.ATTACK or event_sequence_matches
                            else None
                        ),
                        "target_unit_instance_id": (
                            attached_unit_id
                            if source_kind is DestructionSourceKind.ATTACK and attached
                            else bodyguard.unit_instance_id
                        ),
                        "model_instance_id": model.model_instance_id,
                        "removal_record": removal_record.to_payload(),
                    }
                ),
            )
            if source_kind is not DestructionSourceKind.ATTACK:
                decisions.event_log.append(
                    RULE_MODEL_DESTRUCTION_FINALIZED_EVENT,
                    {
                        "model_destroyed_event_id": destroyed_event.event_id,
                        "model_instance_id": model.model_instance_id,
                    },
                )
    completed_event = decisions.event_log.append(
        "attack_sequence_completed",
        {
            "sequence_id": attack_sequence.sequence_id,
            "attacker_player_id": attack_sequence.attacker_player_id,
            "attacking_unit_instance_id": attack_sequence.attacking_unit_instance_id,
        },
    )
    dice_manager = DiceRollManager(
        state.game_id,
        event_log=decisions.event_log,
        injected_results=tuple(
            DiceRollResult.from_values(
                roll_id=f"roll:split:{pink_datasheet_id}:{destruction_kind}:{index}",
                spec=DiceRollSpec(
                    expression=DiceExpression(quantity=1, sides=6),
                    reason=f"Model materialization for {model.model_instance_id}",
                    roll_type="catalog.model_materialization.trigger",
                    actor_id=source_army.player_id,
                ),
                values=(roll_value,),
                source="fixed",
            )
            for index, (model, roll_value) in enumerate(
                zip(destroyed_models, roll_values, strict=True), start=1
            )
        ),
    )
    runtime = CatalogModelMaterializationRuntime(
        ability_indexes_by_player_id={
            source_army.player_id: player_ability_index(package=package, army=source_army),
            enemy_army.player_id: player_ability_index(package=package, army=enemy_army),
        },
        armies=(source_army, enemy_army),
        army_catalog=package.army_catalog,
    )
    context = AttackSequenceCompletedContext(
        state=state,
        decisions=decisions,
        dice_manager=dice_manager,
        runtime_modifier_registry=RuntimeModifierRegistry.empty(),
        source_phase=source_phase,
        attack_sequence=attack_sequence,
        attack_sequence_completed_event_id=completed_event.event_id,
    )
    return _SplitScenario(
        package=package,
        state=state,
        decisions=decisions,
        runtime=runtime,
        context=context,
        source_army=source_army,
        enemy_army=enemy_army,
        bodyguard=bodyguard,
        leader=leader,
        attack_sequence=attack_sequence,
        destroyed_model_instance_id=destroyed_models[0].model_instance_id,
        destroyed_model_instance_ids=tuple(model.model_instance_id for model in destroyed_models),
        attached_unit_instance_id=(attached_unit_id if attached else bodyguard.unit_instance_id),
    )


def _single_model_unit(
    *,
    package: CanonicalCatalogPackage,
    army_id: str,
    unit_selection_id: str,
    datasheet_id: str,
    model_profile_id: str,
) -> UnitInstance:
    return _model_count_unit(
        package=package,
        army_id=army_id,
        unit_selection_id=unit_selection_id,
        datasheet_id=datasheet_id,
        model_profile_id=model_profile_id,
        model_count=1,
    )


def _model_count_unit(
    *,
    package: CanonicalCatalogPackage,
    army_id: str,
    unit_selection_id: str,
    datasheet_id: str,
    model_profile_id: str,
    model_count: int,
) -> UnitInstance:
    datasheet = package.army_catalog.datasheet_by_id(datasheet_id)
    unit = UnitFactory(
        package.army_catalog,
        package.model_geometries,
    ).instantiate_unit(
        army_id=army_id,
        selection=UnitMusterSelection(
            unit_selection_id=unit_selection_id,
            datasheet_id=datasheet_id,
            model_profile_selections=(
                ModelProfileSelection(model_profile_id=model_profile_id, model_count=10),
            ),
        ),
        datasheet=datasheet,
    )
    return replace(unit, own_models=unit.own_models[:model_count])


def _retained_horror_model(
    *,
    package: CanonicalCatalogPackage,
    pink_datasheet_id: str,
    bodyguard: UnitInstance,
    horror_kind: str,
    index: int,
) -> ModelInstance:
    if horror_kind == "blue":
        name = "Blue Horror"
        wargear_ids = (
            f"{pink_datasheet_id}:coruscating-blue-flames",
            f"{pink_datasheet_id}:blue-claws",
        )
        descriptor_id = "horror-materialization:blue-horror"
    elif horror_kind == "brimstone":
        name = "Brimstone Horror"
        wargear_ids = (
            f"{pink_datasheet_id}:coruscating-yellow-flames",
            f"{pink_datasheet_id}:yellow-claws",
        )
        descriptor_id = "horror-materialization:brimstone-horror"
    else:
        raise AssertionError("Unsupported retained Horror kind.")
    return UnitFactory(package.army_catalog).instantiate_materialized_model(
        datasheet_id=pink_datasheet_id,
        model_profile_id=f"{pink_datasheet_id}:blue-horror-brimstone-horror",
        model_instance_id=f"{bodyguard.unit_instance_id}:retained:{horror_kind}:{index}",
        model_name=name,
        wargear_ids=wargear_ids,
        source_id="test:horrors:prior-split",
        materialization_descriptor_id=descriptor_id,
    )


def _army(
    *,
    package: CanonicalCatalogPackage,
    army_id: str,
    player_id: str,
    force_disposition_id: str,
    units: tuple[UnitInstance, ...],
    attached_units: tuple[AttachedUnitFormation, ...] = (),
) -> ArmyDefinition:
    return ArmyDefinition(
        army_id=army_id,
        player_id=player_id,
        catalog_id=package.army_catalog.catalog_id,
        source_package_id=package.army_catalog.source_package_id,
        ruleset_id=package.army_catalog.ruleset_id,
        detachment_selection=DetachmentSelection(
            faction_id=package.army_catalog.factions[0].faction_id,
            detachment_ids=("test:horrors:detachment",),
        ),
        force_disposition_id=force_disposition_id,
        units=units,
        attached_units=attached_units,
    )


def _unit_placement(army: ArmyDefinition, unit: UnitInstance, pose: Pose) -> UnitPlacement:
    return UnitPlacement(
        army_id=army.army_id,
        player_id=army.player_id,
        unit_instance_id=unit.unit_instance_id,
        model_placements=(
            ModelPlacement(
                army_id=army.army_id,
                player_id=army.player_id,
                unit_instance_id=unit.unit_instance_id,
                model_instance_id=unit.own_models[0].model_instance_id,
                pose=pose,
            ),
        ),
    )


def _alive_unit_placement_or_none(
    army: ArmyDefinition,
    unit: UnitInstance,
    *,
    origin: Pose,
) -> UnitPlacement | None:
    alive_models = tuple(model for model in unit.own_models if model.is_alive)
    if not alive_models:
        return None
    return UnitPlacement(
        army_id=army.army_id,
        player_id=army.player_id,
        unit_instance_id=unit.unit_instance_id,
        model_placements=tuple(
            ModelPlacement(
                army_id=army.army_id,
                player_id=army.player_id,
                unit_instance_id=unit.unit_instance_id,
                model_instance_id=model.model_instance_id,
                pose=Pose.at(origin.position.x + index * 1.2, origin.position.y),
            )
            for index, model in enumerate(alive_models)
        ),
    )


def _attack_sequence(
    *,
    package: CanonicalCatalogPackage,
    attacker: UnitInstance,
    attacker_player_id: str,
    target: UnitInstance,
    target_unit_instance_id: str,
    source_phase: BattlePhase = BattlePhase.SHOOTING,
) -> AttackSequence:
    wargear_id = attacker.own_models[0].wargear_ids[0]
    wargear = next(item for item in package.army_catalog.wargear if item.wargear_id == wargear_id)
    profile = wargear.weapon_profiles[0]
    pool = RangedAttackPool(
        attacker_model_instance_id=attacker.own_models[0].model_instance_id,
        weapon_instance_id=f"weapon-instance:test:{attacker.own_models[0].model_instance_id}",
        wargear_id=wargear.wargear_id,
        weapon_profile_id=profile.profile_id,
        weapon_profile=profile,
        target_unit_instance_id=target_unit_instance_id,
        shooting_type=ShootingType.NORMAL,
        attacks=1,
        target_visible_model_ids=target.own_model_ids(),
        target_in_range_model_ids=target.own_model_ids(),
    )
    return AttackSequence(
        sequence_id=f"attack-sequence:horror-split:{attacker.unit_instance_id}",
        attacker_player_id=attacker_player_id,
        attacking_unit_instance_id=attacker.unit_instance_id,
        attack_pools=(pool,),
        source_phase=source_phase,
        used_pool_indices=(0,),
        pool_index=1,
    )


def _placement_payload(
    *,
    request: Any,
    army: ArmyDefinition,
    unit: UnitInstance,
    y_offset: float = 0.0,
) -> dict[str, JsonValue]:
    request_payload = cast(dict[str, JsonValue], request.payload)
    model_ids = cast(list[str], request_payload["model_instance_ids"])
    poses = (
        Pose.at(10.0, 10.0 + y_offset),
        Pose.at(11.2, 10.0 + y_offset),
    )
    assert 0 < len(model_ids) <= len(poses)
    placements = tuple(
        ModelPlacement(
            army_id=army.army_id,
            player_id=army.player_id,
            unit_instance_id=unit.unit_instance_id,
            model_instance_id=model_id,
            pose=pose,
        )
        for model_id, pose in zip(
            model_ids,
            poses[: len(model_ids)],
            strict=True,
        )
    )
    return cast(
        dict[str, JsonValue],
        PlacementProposalPayload(
            proposal_request_id=request.request_id,
            proposal_kind=ProposalKind.MODEL_MATERIALIZATION,
            unit_instance_id=unit.unit_instance_id,
            placement_kind=BattlefieldPlacementKind.SPLIT_UNIT,
            attempted_placement=UnitPlacement(
                army_id=army.army_id,
                player_id=army.player_id,
                unit_instance_id=unit.unit_instance_id,
                model_placements=placements,
            ),
        ).to_payload(),
    )


def _parameterized_result(*, request: Any, payload: JsonValue, result_id: str) -> DecisionResult:
    return DecisionResult(
        result_id=result_id,
        request_id=request.request_id,
        decision_type=request.decision_type,
        actor_id=request.actor_id,
        selected_option_id=request.options[0].option_id,
        payload=payload,
    )


def _authenticated_materialization_evidence(
    *,
    destruction_kind: str,
    destroyed_horror_kinds: tuple[str, ...] = (),
) -> tuple[_SplitScenario, tuple[EventRecord, ...], tuple[DecisionRecord, ...]]:
    scenario = _split_scenario(
        pink_datasheet_id="000002584",
        blue_datasheet_id="000002583",
        destruction_kind=destruction_kind,
        destroyed_horror_kinds=destroyed_horror_kinds,
    )
    status = scenario.runtime.resolve_completed_attack_sequence(scenario.context)
    assert status is not None
    assert status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    request = scenario.decisions.queue.peek_next()
    result = _parameterized_result(
        request=request,
        payload=_placement_payload(
            request=request,
            army=scenario.source_army,
            unit=scenario.bodyguard,
        ),
        result_id=f"result:authenticated-materialization:{destruction_kind}",
    )
    scenario.decisions.submit_result(result)
    placements = apply_recorded_catalog_model_materialization_placement(
        state=scenario.state,
        decisions=scenario.decisions,
        request=request,
        result=result,
        ability_indexes_by_player_id=scenario.runtime.ability_indexes_by_player_id,
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(),
        army_catalog=scenario.package.army_catalog,
    )
    assert placements
    event_records = scenario.decisions.event_log.records
    decision_records = scenario.decisions.records
    authenticated = authenticated_catalog_materialized_model_payloads_by_unit_id(
        game_id=scenario.state.game_id,
        catalog=scenario.package.army_catalog,
        expected_armies=(scenario.source_army, scenario.enemy_army),
        event_records=event_records,
        decision_records=decision_records,
    )
    assert set(authenticated) == {scenario.bodyguard.unit_instance_id}
    return scenario, event_records, decision_records


def _unique_event_index(events: list[EventRecord], event_type: str) -> int:
    matches = tuple(index for index, event in enumerate(events) if event.event_type == event_type)
    assert len(matches) == 1
    return matches[0]


def _corrupt_authenticated_materialization_evidence(
    *,
    scenario: _SplitScenario,
    event_records: tuple[EventRecord, ...],
    decision_records: tuple[DecisionRecord, ...],
    tamper_kind: str,
) -> tuple[tuple[EventRecord, ...], tuple[DecisionRecord, ...]]:
    events = list(event_records)
    records = list(decision_records)
    materialized_index = _unique_event_index(events, CATALOG_MODELS_MATERIALIZED_EVENT)
    roll_index = _unique_event_index(events, CATALOG_MODEL_MATERIALIZATION_ROLL_EVENT)
    completion_index = _unique_event_index(events, "attack_sequence_completed")
    requested_index = _unique_event_index(events, "decision_requested")
    recorded_index = _unique_event_index(events, "decision_recorded")

    if tamper_kind == "materialized_game_id":
        payload = copy.deepcopy(cast(dict[str, JsonValue], events[materialized_index].payload))
        payload["game_id"] = "game:unrelated"
        events[materialized_index] = replace(events[materialized_index], payload=payload)
    elif tamper_kind == "missing_request_id":
        payload = copy.deepcopy(cast(dict[str, JsonValue], events[materialized_index].payload))
        payload["request_id"] = None
        events[materialized_index] = replace(events[materialized_index], payload=payload)
    elif tamper_kind == "missing_decision_record":
        payload = copy.deepcopy(cast(dict[str, JsonValue], events[materialized_index].payload))
        payload["result_id"] = "result:unrelated"
        events[materialized_index] = replace(events[materialized_index], payload=payload)
    elif tamper_kind == "malformed_request_payload":
        record = records[0]
        records[0] = replace(record, request=replace(record.request, payload=None))
    elif tamper_kind in {"inactive_source", "request_payload", "roll_identity"}:
        record = records[0]
        request_payload = copy.deepcopy(cast(dict[str, JsonValue], record.request.payload))
        if tamper_kind == "inactive_source":
            request_payload["catalog_record_id"] = "catalog-record:unrelated"
        elif tamper_kind == "request_payload":
            request_payload["submission_kind"] = "submission:unrelated"
        else:
            request_payload["roll_event_id"] = events[completion_index].event_id
        records[0] = replace(record, request=replace(record.request, payload=request_payload))
    elif tamper_kind == "decision_identity":
        record = records[0]
        request = replace(record.request, decision_type="decision:unrelated")
        result = replace(record.result, decision_type=request.decision_type)
        records[0] = replace(record, request=request, result=result)
    elif tamper_kind == "malformed_result_payload":
        record = records[0]
        records[0] = replace(record, result=replace(record.result, payload=None))
    elif tamper_kind in {"accepted_placement", "accepted_model_set"}:
        record = records[0]
        result_payload = copy.deepcopy(cast(dict[str, JsonValue], record.result.payload))
        if tamper_kind == "accepted_placement":
            result_payload["placement_kind"] = BattlefieldPlacementKind.DEPLOYMENT.value
        else:
            placement = cast(dict[str, JsonValue], result_payload["attempted_placement"])
            model_placements = cast(list[JsonValue], placement["model_placements"])
            model_placement = cast(dict[str, JsonValue], model_placements[0])
            model_placement["model_instance_id"] = (
                f"{scenario.bodyguard.unit_instance_id}:unrelated-model"
            )
        records[0] = replace(record, result=replace(record.result, payload=result_payload))
    elif tamper_kind in {
        "roll_context",
        "destroyed_model_source",
        "malformed_roll_payload",
        "roll_specification",
        "unsuccessful_roll",
        "invalid_battle_round",
    }:
        roll_payload = copy.deepcopy(cast(dict[str, JsonValue], events[roll_index].payload))
        if tamper_kind == "roll_context":
            roll_payload["result_count"] = 3
        elif tamper_kind == "destroyed_model_source":
            roll_payload["destroyed_model_instance_id"] = scenario.leader.own_models[
                0
            ].model_instance_id
        elif tamper_kind == "malformed_roll_payload":
            roll_payload["roll"] = None
        elif tamper_kind == "roll_specification":
            raw_roll = cast(dict[str, JsonValue], roll_payload["roll"])
            original_result = cast(dict[str, JsonValue], raw_roll["original_result"])
            spec = cast(dict[str, JsonValue], original_result["spec"])
            spec["reason"] = "Unrelated roll"
        elif tamper_kind == "unsuccessful_roll":
            raw_roll = cast(dict[str, JsonValue], roll_payload["roll"])
            original_result = cast(dict[str, JsonValue], raw_roll["original_result"])
            original_result["values"] = [1]
            original_result["total"] = 1
            raw_roll["current_values"] = [1]
            raw_roll["current_total"] = 1
        else:
            roll_payload["battle_round"] = "1"
        events[roll_index] = replace(events[roll_index], payload=roll_payload)
    elif tamper_kind == "completion_sequence":
        payload = copy.deepcopy(cast(dict[str, JsonValue], events[completion_index].payload))
        payload["sequence_id"] = "attack-sequence:unrelated"
        events[completion_index] = replace(events[completion_index], payload=payload)
    elif tamper_kind == "roll_before_completion":
        events[completion_index], events[roll_index] = events[roll_index], events[completion_index]
    elif tamper_kind == "destruction_evidence":
        destroyed_index = _unique_event_index(events, "model_destroyed")
        events.pop(destroyed_index)
    elif tamper_kind == "evidence_order":
        events[requested_index], events[recorded_index] = (
            events[recorded_index],
            events[requested_index],
        )
    elif tamper_kind == "missing_terminal":
        events.pop(materialized_index + 1)
    elif tamper_kind == "terminal_payload":
        terminal_index = materialized_index + 1
        payload = copy.deepcopy(cast(dict[str, JsonValue], events[terminal_index].payload))
        payload["source_rule_id"] = "source-rule:unrelated"
        events[terminal_index] = replace(events[terminal_index], payload=payload)
    elif tamper_kind in {"request_provenance", "record_provenance"}:
        provenance_index = (
            requested_index if tamper_kind == "request_provenance" else recorded_index
        )
        payload = copy.deepcopy(cast(dict[str, JsonValue], events[provenance_index].payload))
        payload["tampered"] = True
        events[provenance_index] = replace(events[provenance_index], payload=payload)
    elif tamper_kind == "malformed_materialized_event":
        events[materialized_index] = replace(events[materialized_index], payload=None)
    elif tamper_kind == "malformed_completion_event":
        events[completion_index] = replace(events[completion_index], payload=None)
    elif tamper_kind == "completion_payload":
        payload = copy.deepcopy(cast(dict[str, JsonValue], events[materialized_index].payload))
        payload["action_phase"] = BattlePhase.MOVEMENT.value
        events[materialized_index] = replace(events[materialized_index], payload=payload)
    else:
        raise AssertionError(f"Unsupported authenticated evidence tamper: {tamper_kind}")
    return tuple(events), tuple(records)


def _tamper_materialization_lifecycle_payload(
    lifecycle_payload: Any,
    *,
    tamper_kind: str,
) -> None:
    decisions_payload = cast(dict[str, Any], lifecycle_payload["decisions"])
    queue_payload = cast(dict[str, Any], decisions_payload["queue"])
    request_payload = cast(
        dict[str, Any],
        cast(list[dict[str, Any]], queue_payload["pending_requests"])[0]["payload"],
    )
    if tamper_kind == "source_rule":
        request_payload["source_rule_id"] = "tampered:source-rule"
        return
    if tamper_kind == "clause":
        request_payload["clause_id"] = "tampered:clause"
        return
    if tamper_kind == "descriptor":
        request_payload["materialization_descriptor_id"] = "tampered:descriptor"
        return
    if tamper_kind == "model_profile":
        cast(list[dict[str, Any]], request_payload["models"])[0]["model_profile_id"] = (
            "tampered:model-profile"
        )
        return
    if tamper_kind == "wargear":
        model = cast(list[dict[str, Any]], request_payload["models"])[0]
        cast(list[str], model["wargear_ids"])[0] = "tampered:wargear"
        return
    if tamper_kind == "model_ids":
        model_ids = cast(list[str], request_payload["model_instance_ids"])
        model_ids[0] = f"{model_ids[0]}:tampered"
        return
    event_payloads = cast(list[dict[str, Any]], decisions_payload["event_log"])
    roll_payload = next(
        cast(dict[str, Any], event["payload"])
        for event in event_payloads
        if event["event_type"] == CATALOG_MODEL_MATERIALIZATION_ROLL_EVENT
    )
    if tamper_kind == "roll":
        cast(dict[str, Any], roll_payload["roll"])["current_total"] = 1
        return
    if tamper_kind == "result_count":
        roll_payload["result_count"] = 3
        return
    raise AssertionError(f"Unsupported tamper kind: {tamper_kind}")


def _unit_by_id(state: GameState, unit_instance_id: str) -> UnitInstance:
    matches = tuple(
        unit
        for army in state.army_definitions
        for unit in army.units
        if unit.unit_instance_id == unit_instance_id
    )
    assert len(matches) == 1
    return matches[0]


def _record_successful_materialization_rolls(scenario: _SplitScenario) -> None:
    source = next(
        source
        for source in scenario.runtime.sources(armies=tuple(scenario.state.army_definitions))
        if source.source_unit_instance_id == scenario.bodyguard.unit_instance_id
        and source.materialization is not None
        and scenario.bodyguard.own_models[0].model_profile_id
        in source.materialization.destroyed_model_profile_ids
    )
    descriptor = source.materialization
    assert descriptor is not None
    parent_battle_phase = scenario.state.current_battle_phase
    assert parent_battle_phase is not None
    manager = DiceRollManager(
        scenario.state.game_id,
        event_log=scenario.decisions.event_log,
    )
    for model_instance_id in scenario.destroyed_model_instance_ids:
        roll = manager.roll_fixed(
            DiceRollSpec(
                expression=DiceExpression(quantity=1, sides=6),
                reason=f"Model materialization for {model_instance_id}",
                roll_type="catalog.model_materialization.trigger",
                actor_id=source.player_id,
            ),
            [6],
        )
        scenario.decisions.event_log.append(
            CATALOG_MODEL_MATERIALIZATION_ROLL_EVENT,
            validate_json_value(
                {
                    "game_id": scenario.state.game_id,
                    "battle_round": scenario.state.battle_round,
                    "phase": parent_battle_phase.value,
                    "action_phase": scenario.attack_sequence.source_phase.value,
                    "parent_battle_phase": parent_battle_phase.value,
                    "attack_sequence_id": scenario.attack_sequence.sequence_id,
                    "attack_sequence_completed_event_id": (
                        scenario.context.attack_sequence_completed_event_id
                    ),
                    "catalog_record_id": source.record.record_id,
                    "clause_id": source.clause.clause_id,
                    "source_rule_id": source.source_rule_id,
                    "source_unit_instance_id": source.source_unit_instance_id,
                    "destroyed_model_instance_id": model_instance_id,
                    "success_threshold": descriptor.success_threshold,
                    "roll": roll.to_payload(),
                    "successful": True,
                    "result_count": descriptor.result_count,
                }
            ),
        )


def _configure_phase_lifecycle(
    *,
    lifecycle: GameLifecycle,
    scenario: _SplitScenario,
) -> None:
    state = lifecycle.state
    assert state is not None
    config = _game_config(scenario)
    fixture_subscription = RuntimeContentEventSubscription(
        subscription_id="test:phase-owned-split:placement",
        source_rule_id="test:phase-owned-split:placement-rule",
        trigger_kind=TimingTriggerKind.MODEL_PLACED_ON_BATTLEFIELD,
        handler_id="test:phase-owned-split:placement-handler",
        filters={"player_id": scenario.source_army.player_id},
    )

    def detach_fixture_bundle(
        context: RuntimeContentEventContext,
    ) -> RuntimeContentEventResult:
        del context
        lifecycle._runtime_content_bundle = None
        return RuntimeContentEventResult.applied(fixture_subscription)

    armies = tuple(state.army_definitions)
    bundle = RuntimeContentBundle.from_contributions(
        activation=RuntimeContentActivation.from_armies(
            armies=armies,
            catalog=config.army_catalog,
        ),
        armies=armies,
        catalog=config.army_catalog,
        contributions=(
            RuntimeContentContribution(
                contribution_id="test:phase-owned-split:placement-contribution",
                event_subscriptions=(fixture_subscription,),
                event_handler_bindings=(
                    RuntimeContentEventHandlerBinding(
                        handler_id=fixture_subscription.handler_id,
                        handler=detach_fixture_bundle,
                    ),
                ),
            ),
        ),
        base_ability_records=catalog_ability_records_from_catalog(config.army_catalog),
    )
    lifecycle._config = config
    lifecycle._runtime_content_bundle = bundle
    lifecycle._runtime_content_activation_input_hash = (
        lifecycle_module._runtime_content_activation_input_hash(
            config=config,
            armies=tuple(state.army_definitions),
        )
    )
    lifecycle._movement_phase_handler = MovementPhaseHandler(
        ruleset_descriptor=config.ruleset_descriptor,
        army_catalog=config.army_catalog,
    )
    lifecycle._shooting_phase_handler = ShootingPhaseHandler(
        ruleset_descriptor=config.ruleset_descriptor,
        army_catalog=config.army_catalog,
        attack_sequence_completed_hooks=bundle.attack_sequence_completed_hook_registry,
        ability_indexes_by_player_id=bundle.ability_indexes_by_player_id,
        runtime_modifier_registry=bundle.runtime_modifier_registry,
    )
    lifecycle._fight_phase_handler = FightPhaseHandler(
        ruleset_descriptor=config.ruleset_descriptor,
        army_catalog=config.army_catalog,
        attack_sequence_completed_hooks=bundle.attack_sequence_completed_hook_registry,
        runtime_modifier_registry=bundle.runtime_modifier_registry,
    )
    lifecycle._battle_round_flow = BattleRoundFlow(
        phase_handlers=lifecycle._phase_handlers(),
        runtime_modifier_registry=bundle.runtime_modifier_registry,
        runtime_event_index=bundle.event_index,
        ruleset_descriptor=config.ruleset_descriptor,
        army_catalog=config.army_catalog,
    )


def _restored_phase_lifecycle(
    *,
    lifecycle: GameLifecycle,
    scenario: _SplitScenario,
) -> GameLifecycle:
    payload = lifecycle.to_payload()
    payload["config"] = None
    restored = GameLifecycle.from_payload(payload)
    _configure_phase_lifecycle(lifecycle=restored, scenario=scenario)
    assert restored._config == _game_config(scenario)
    assert restored._runtime_content_bundle is not None
    return restored


def _game_config(scenario: _SplitScenario) -> GameConfig:
    requests = tuple(
        ArmyMusterRequest(
            army_id=army.army_id,
            player_id=army.player_id,
            catalog_id=army.catalog_id,
            source_package_id=army.source_package_id,
            ruleset_id=army.ruleset_id,
            detachment_selection=army.detachment_selection,
            force_disposition_id=army.force_disposition_id,
            unit_selections=tuple(
                UnitMusterSelection(
                    unit_selection_id=unit.unit_instance_id.removeprefix(f"{army.army_id}:"),
                    datasheet_id=unit.datasheet_id,
                    model_profile_selections=(
                        ModelProfileSelection(
                            model_profile_id=unit.own_models[0].model_profile_id,
                            model_count=len(unit.own_models),
                        ),
                    ),
                )
                for unit in army.units
            ),
        )
        for army in (scenario.source_army, scenario.enemy_army)
    )
    return GameConfig(
        game_id=scenario.state.game_id,
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(),
        army_catalog=scenario.package.army_catalog,
        army_muster_requests=requests,
        player_ids=scenario.state.player_ids,
        turn_order=scenario.state.turn_order,
        fixed_secondary_mission_ids=("assassination", "bring_it_down"),
        mission_setup=scenario.state.mission_setup,
        allow_legacy_non_strict_rosters=True,
    )


def _runtime_content_bundle(scenario: _SplitScenario) -> RuntimeContentBundle:
    armies = (scenario.source_army, scenario.enemy_army)
    return RuntimeContentBundle.from_contributions(
        activation=RuntimeContentActivation.from_armies(
            armies=armies,
            catalog=scenario.package.army_catalog,
        ),
        armies=armies,
        catalog=scenario.package.army_catalog,
        contributions=(),
        base_ability_records=catalog_ability_records_from_catalog(scenario.package.army_catalog),
    )
