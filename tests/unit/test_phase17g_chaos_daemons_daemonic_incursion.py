# pyright: reportPrivateUsage=false
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, replace
from typing import cast

import pytest
from tests.phase10p_reserves_helpers import (
    base_radius_inches,
    battle_state_with_reserve,
    decision_request,
    last_event_payload,
    reserve_placement,
    single_model_reserve_placement,
    south_edge_touching_pose,
    submit_handler_decision,
    submit_reserve_placement_payload,
    with_model_pose,
)
from tests.setup_completion_helpers import enter_battle_for_fixture

from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.core.attributes import Characteristic, CharacteristicValue
from warhammer40k_core.core.datasheet import (
    BaseSizeDefinition,
    CatalogAbilitySourceKind,
    CatalogAbilitySupport,
    DatasheetAbilityDescriptor,
    DatasheetKeywordSet,
)
from warhammer40k_core.core.detachment import DetachmentDefinition
from warhammer40k_core.core.dice import (
    DiceExpression,
    DiceRollResult,
    DiceRollSpec,
    DiceRollState,
    RerollComponentSelectionPolicy,
    RerollPermission,
)
from warhammer40k_core.core.faction import FactionDefinition
from warhammer40k_core.core.ruleset_descriptor import RulesetDescriptor
from warhammer40k_core.core.weapon_profiles import (
    AttackProfile,
    DamageProfile,
    RangeProfile,
    WeaponProfile,
)
from warhammer40k_core.engine import (
    generic_rule_lifecycle_ability_sources,
    reserve_arrival_requirements,
    stratagems_generic_rule_ir,
    stratagems_targeting,
)
from warhammer40k_core.engine import stratagems_generic_metadata as generic_metadata
from warhammer40k_core.engine import stratagems_generic_persisted as generic_persisted
from warhammer40k_core.engine.army_mustering import (
    ArmyDefinition,
    ArmyMusterRequest,
    EnhancementAssignment,
    muster_army,
)
from warhammer40k_core.engine.attack_sequence import AttackSequence
from warhammer40k_core.engine.attack_sequence_completion_hooks import (
    AttackSequenceCompletedContext,
)
from warhammer40k_core.engine.attack_sequence_dice_rerolls import (
    _source_backed_save_permission_for_attack,
    _source_backed_wound_permission_for_attack,
)
from warhammer40k_core.engine.battlefield_state import (
    BattlefieldPlacementKind,
    BattlefieldScenario,
    ModelPlacement,
    UnitPlacement,
)
from warhammer40k_core.engine.charge_effects import (
    CHARGE_AFTER_ADVANCE_EFFECT_KIND,
    charge_after_advance_allowed_by_effects,
)
from warhammer40k_core.engine.command_points import CommandPointSourceKind
from warhammer40k_core.engine.decision import DiceRollManager
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_record import DecisionRecordPayload
from warhammer40k_core.engine.decision_request import PARAMETERIZED_DECISION_OPTION_ID
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.effects import (
    GENERIC_RULE_EFFECT_KIND,
    EffectExpiration,
    EffectExpirationKind,
    PersistingEffect,
)
from warhammer40k_core.engine.enhancement_effects import apply_enhancement_effects
from warhammer40k_core.engine.event_log import (
    EventRecord,
    EventRecordPayload,
    JsonValue,
    validate_json_value,
)
from warhammer40k_core.engine.faction_content.activation import RuntimeContentActivation
from warhammer40k_core.engine.faction_content.bundle import RuntimeContentBundle
from warhammer40k_core.engine.faction_content.runtime import (
    build_runtime_content_bundle,
    build_runtime_content_bundle_for_armies,
)
from warhammer40k_core.engine.faction_content.warhammer_40000_11th.chaos_daemons import (
    datasheets,
)
from warhammer40k_core.engine.faction_content.warhammer_40000_11th.chaos_daemons import (
    july_2026_updates as july_updates,
)
from warhammer40k_core.engine.faction_content.warhammer_40000_11th.chaos_daemons.detachments.daemonic_incursion import (  # noqa: E501  # noqa: E501
    enhancements,
    rule,
)
from warhammer40k_core.engine.faction_content.warhammer_40000_11th.chaos_daemons.detachments.daemonic_incursion import (  # noqa: E501
    stratagems as daemonic_stratagems,
)
from warhammer40k_core.engine.game_state import GameConfig, GameState
from warhammer40k_core.engine.lifecycle import GameLifecycle, GameLifecyclePayload
from warhammer40k_core.engine.list_validation import (
    DetachmentSelection,
    UnitMusterSelection,
)
from warhammer40k_core.engine.mission_setup import MissionSetup
from warhammer40k_core.engine.movement_proposals import (
    PLACEMENT_PROPOSAL_DECISION_TYPE,
    MovementProposalRequest,
    PlacementProposalPayload,
)
from warhammer40k_core.engine.phase import (
    BattlePhase,
    GameLifecycleError,
    GameLifecycleStage,
    LifecycleStatusKind,
)
from warhammer40k_core.engine.phases.movement import (
    COMPLETE_REINFORCEMENTS_OPTION_ID,
    MovementPhaseHandler,
    MovementPhaseState,
)
from warhammer40k_core.engine.placement import create_deterministic_battlefield_scenario
from warhammer40k_core.engine.primary_reserve_entry_lifecycle_integrity import (
    validate_primary_reserve_entry_lifecycle_integrity,
)
from warhammer40k_core.engine.reserve_arrival_hooks import (
    ReserveArrivalDistanceContext,
    ReserveArrivalDistanceHookRegistry,
)
from warhammer40k_core.engine.reserves import (
    ReserveDestructionTimingPolicy,
    ReserveKind,
    ReserveOrigin,
    ReservePlacementViolationCode,
    ReserveState,
    ReserveStatus,
)
from warhammer40k_core.engine.rule_execution import RuleExecutionResult
from warhammer40k_core.engine.rules_unit_placement import RulesUnitPlacement
from warhammer40k_core.engine.rules_units import rules_unit_view_by_id
from warhammer40k_core.engine.runtime_modifiers import (
    RuntimeModifierRegistry,
    WeaponProfileModifierContext,
)
from warhammer40k_core.engine.shooting_types import ShootingType
from warhammer40k_core.engine.source_backed_rerolls import (
    SourceBackedRerollPermissionContext,
    source_backed_reroll_permission_context_for_unit,
)
from warhammer40k_core.engine.stratagem_catalog import eleventh_edition_core_stratagem_index
from warhammer40k_core.engine.stratagems_eligibility import derive_stratagem_use_unit_ids
from warhammer40k_core.engine.stratagems_generic_metadata import (
    objective_marker_effect_selection,
)
from warhammer40k_core.engine.stratagems_model import (
    StratagemCatalogIndex,
    StratagemCatalogRecord,
    StratagemDefinition,
    StratagemEligibilityContext,
    StratagemTargetBinding,
    StratagemTargetKind,
    StratagemTargetProposal,
    StratagemUseRecord,
)
from warhammer40k_core.engine.stratagems_requests import (
    create_stratagem_use_decision_request,
    request_stratagem_target_proposal,
)
from warhammer40k_core.engine.stratagems_selection import _stratagem_decision_option
from warhammer40k_core.engine.timing_windows import TimingTriggerKind
from warhammer40k_core.engine.unit_factory import ModelInstance, UnitInstance
from warhammer40k_core.engine.wargear_selections import (
    ModelProfileSelection,
)
from warhammer40k_core.engine.weapon_declaration import RangedAttackPool
from warhammer40k_core.geometry.model_geometry import ModelGeometry
from warhammer40k_core.geometry.pose import Pose
from warhammer40k_core.rules.mission_pack_import import chapter_approved_2026_27_mission_pack
from warhammer40k_core.rules.rule_ir import RuleIR
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    faction_daemonic_incursion_ir_support_2026_27 as daemonic_incursion_ir,
)
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    faction_execution_2026_27,
    faction_generic_ir_support_2026_27,
)
from warhammer40k_core.rules.source_packages.warhammer_40000_11th.faction_execution_2026_27 import (
    Phase17FExecutionStatus,
)

_DAEMONIC_INCURSION_DATASHEET_ID = "phase17g-daemonic-incursion-daemon"
_OTHER_DAEMON_DETACHMENT_ID = "warptide"
_RESERVE_UNIT_ID = "army-alpha:intercessor-unit-1"
_ANCHOR_UNIT_ID = "army-alpha:intercessor-unit-2"
_RESERVE_BASE_DIAMETER_MM = 32.0


def test_daemonic_incursion_runtime_hook_materializes_only_for_selected_detachment() -> None:
    direct_contribution = rule.runtime_contribution()
    summary = build_runtime_content_bundle(_daemonic_incursion_config()).to_summary_payload()

    assert direct_contribution.contribution_id == rule.CONTRIBUTION_ID
    assert not direct_contribution.contribution_id.endswith(":scaffold")
    assert direct_contribution.reserve_arrival_distance_hook_bindings == ()
    assert rule.WARP_RIFTS_HOOK_ID in summary["reserve_arrival_distance_hook_ids"]
    assert rule.SOURCE_RULE_ID in summary["selected_execution_record_ids"]
    assert any(
        path.endswith(".chaos_daemons.detachments.daemonic_incursion.manifest")
        for path in summary["selected_module_paths"]
    )

    other_summary = build_runtime_content_bundle(
        _daemonic_incursion_config(
            daemon_detachment_id=_OTHER_DAEMON_DETACHMENT_ID,
            game_id="phase17g-daemonic-incursion-not-selected",
        )
    ).to_summary_payload()

    assert rule.WARP_RIFTS_HOOK_ID not in other_summary["reserve_arrival_distance_hook_ids"]
    assert (
        daemonic_incursion_ir.DENIZENS_OF_THE_WARP_HOOK_ID
        in summary["reserve_arrival_distance_hook_ids"]
    )
    assert (
        daemonic_incursion_ir.DENIZENS_OF_THE_WARP_HOOK_ID
        not in other_summary["reserve_arrival_distance_hook_ids"]
    )


def test_daemonic_incursion_enhancement_runtime_bindings_materialize_for_assignments() -> None:
    argath_state, _reserve_state, _reserve_unit = _daemonic_incursion_reserve_state()
    _assign_daemonic_enhancement(
        argath_state,
        unit=_unit_by_id(argath_state, _ANCHOR_UNIT_ID),
        enhancement_id=enhancements.ARGATH_ENHANCEMENT_ID,
        source_id=enhancements.ARGATH_SOURCE_RULE_ID,
    )
    argath_bundle = _daemonic_incursion_runtime_bundle(argath_state)

    assert enhancements.ARGATH_WEAPON_PROFILE_MODIFIER_ID in {
        binding.modifier_id
        for binding in argath_bundle.runtime_modifier_registry.all_weapon_profile_bindings()
    }

    soulstealer_state, _reserve_state, _reserve_unit = _daemonic_incursion_reserve_state(
        anchor_god_keyword="Slaanesh"
    )
    _assign_daemonic_enhancement(
        soulstealer_state,
        unit=_unit_by_id(soulstealer_state, _ANCHOR_UNIT_ID),
        enhancement_id=enhancements.SOULSTEALER_ENHANCEMENT_ID,
        source_id=enhancements.SOULSTEALER_SOURCE_RULE_ID,
    )
    soulstealer_bundle = _daemonic_incursion_runtime_bundle(soulstealer_state)

    assert enhancements.SOULSTEALER_HOOK_ID in {
        binding.hook_id
        for binding in soulstealer_bundle.attack_sequence_completed_hook_registry.all_bindings()
    }

    endless_state, _reserve_state, _reserve_unit = _daemonic_incursion_reserve_state(
        anchor_god_keyword="Nurgle"
    )
    _assign_daemonic_enhancement(
        endless_state,
        unit=_unit_by_id(endless_state, _ANCHOR_UNIT_ID),
        enhancement_id=enhancements.ENDLESS_GIFT_ENHANCEMENT_ID,
        source_id=enhancements.ENDLESS_GIFT_SOURCE_RULE_ID,
    )
    endless_bundle = _daemonic_incursion_runtime_bundle(endless_state)

    assert enhancements.ENDLESS_GIFT_EFFECT_ID in {
        binding.effect_id for binding in endless_bundle.enhancement_effect_registry.all_bindings()
    }

    everstave_state, _reserve_state, _reserve_unit = _daemonic_incursion_reserve_state(
        anchor_god_keyword="Tzeentch"
    )
    _assign_daemonic_enhancement(
        everstave_state,
        unit=_unit_by_id(everstave_state, _ANCHOR_UNIT_ID),
        enhancement_id=enhancements.EVERSTAVE_ENHANCEMENT_ID,
        source_id=enhancements.EVERSTAVE_SOURCE_RULE_ID,
    )
    everstave_bundle = _daemonic_incursion_runtime_bundle(everstave_state)

    assert enhancements.EVERSTAVE_WEAPON_PROFILE_MODIFIER_ID in {
        binding.modifier_id
        for binding in everstave_bundle.runtime_modifier_registry.all_weapon_profile_bindings()
    }


def test_argath_adds_shadow_bonus_to_bearer_melee_attacks_and_strength() -> None:
    state, _reserve_state, _reserve_unit = _daemonic_incursion_reserve_state()
    bearer = _unit_by_id(state, _ANCHOR_UNIT_ID)
    enemy_unit_id = _enemy_unit_id(state)
    _assign_daemonic_enhancement(
        state,
        unit=bearer,
        enhancement_id=enhancements.ARGATH_ENHANCEMENT_ID,
        source_id=enhancements.ARGATH_SOURCE_RULE_ID,
    )
    _place_model(
        state=state,
        model_instance_id=bearer.own_models[0].model_instance_id,
        pose=Pose.at(x=16.0, y=4.25, z=0.0, facing_degrees=0.0),
    )
    profile = _weapon_profile(melee=True)

    modified = _daemonic_incursion_runtime_bundle(
        state
    ).runtime_modifier_registry.modified_weapon_profile(
        WeaponProfileModifierContext(
            state=state,
            source_phase=BattlePhase.FIGHT,
            attacking_unit_instance_id=bearer.unit_instance_id,
            attacker_model_instance_id=bearer.own_models[0].model_instance_id,
            target_unit_instance_id=enemy_unit_id,
            weapon_profile=profile,
        )
    )

    assert modified.attack_profile.fixed_attacks == 3
    assert modified.strength.final == profile.strength.final + 2
    assert enhancements.ARGATH_SOURCE_RULE_ID in modified.source_ids


def test_everstave_adds_non_shadow_bonus_to_bearer_ranged_strength_and_range() -> None:
    state, _reserve_state, _reserve_unit = _daemonic_incursion_reserve_state(
        anchor_god_keyword="Tzeentch"
    )
    bearer = _unit_by_id(state, _ANCHOR_UNIT_ID)
    enemy_unit_id = _enemy_unit_id(state)
    _assign_daemonic_enhancement(
        state,
        unit=bearer,
        enhancement_id=enhancements.EVERSTAVE_ENHANCEMENT_ID,
        source_id=enhancements.EVERSTAVE_SOURCE_RULE_ID,
    )
    assert state.battlefield_state is not None
    state.replace_battlefield_state(
        state.battlefield_state.without_unit_placement(bearer.unit_instance_id)
    )
    profile = _weapon_profile()

    modified = _daemonic_incursion_runtime_bundle(
        state
    ).runtime_modifier_registry.modified_weapon_profile(
        WeaponProfileModifierContext(
            state=state,
            source_phase=BattlePhase.SHOOTING,
            attacking_unit_instance_id=bearer.unit_instance_id,
            attacker_model_instance_id=bearer.own_models[0].model_instance_id,
            target_unit_instance_id=enemy_unit_id,
            weapon_profile=profile,
        )
    )

    assert modified.strength.final == profile.strength.final + 1
    assert modified.range_profile.distance_inches == 27
    assert enhancements.EVERSTAVE_SOURCE_RULE_ID in modified.source_ids


def test_endless_gift_registers_model_feel_no_pain_once() -> None:
    state, _reserve_state, _reserve_unit = _daemonic_incursion_reserve_state(
        anchor_god_keyword="Nurgle"
    )
    bearer = _unit_by_id(state, _ANCHOR_UNIT_ID)
    _assign_daemonic_enhancement(
        state,
        unit=bearer,
        enhancement_id=enhancements.ENDLESS_GIFT_ENHANCEMENT_ID,
        source_id=enhancements.ENDLESS_GIFT_SOURCE_RULE_ID,
    )
    bundle = _daemonic_incursion_runtime_bundle(state)
    decisions = DecisionController()

    apply_enhancement_effects(
        state=state,
        registry=bundle.enhancement_effect_registry,
        decisions=decisions,
    )
    apply_enhancement_effects(
        state=state,
        registry=bundle.enhancement_effect_registry,
        decisions=decisions,
    )

    model_id = bearer.own_models[0].model_instance_id
    sources = state.feel_no_pain_sources_for_model(model_instance_id=model_id)
    assert len(sources) == 1
    assert sources[0].threshold == 5
    assert (
        sources[0].source_id
        == f"{enhancements.ENDLESS_GIFT_SOURCE_RULE_ID}:{model_id}:feel-no-pain"
    )
    assert [
        record.event_type
        for record in decisions.event_log.records
        if record.event_type == "enhancement_effects_applied"
    ] == ["enhancement_effects_applied"]


def test_soulstealer_heals_bearer_after_destroying_enemy_model_with_melee_attack() -> None:
    state, _reserve_state, _reserve_unit = _daemonic_incursion_reserve_state(
        anchor_god_keyword="Slaanesh"
    )
    _set_current_battle_phase(state, BattlePhase.FIGHT)
    bearer = _unit_by_id(state, _ANCHOR_UNIT_ID)
    target = _unit_by_id(state, _enemy_unit_id(state))
    bearer_model = bearer.own_models[0]
    target_model = target.own_models[0]
    _set_model_wounds(
        state,
        model_instance_id=bearer_model.model_instance_id,
        wounds_remaining=bearer_model.starting_wounds - 1,
    )
    _assign_daemonic_enhancement(
        state,
        unit=bearer,
        enhancement_id=enhancements.SOULSTEALER_ENHANCEMENT_ID,
        source_id=enhancements.SOULSTEALER_SOURCE_RULE_ID,
    )
    profile = _weapon_profile(melee=True)
    attack_pool = _attack_pool(
        attacker=bearer,
        target=target,
        weapon_profile=profile,
    )
    attack_sequence = AttackSequence(
        sequence_id="phase17g-soulstealer-sequence",
        attacker_player_id="player-a",
        attacking_unit_instance_id=bearer.unit_instance_id,
        attack_pools=(attack_pool,),
        source_phase=BattlePhase.FIGHT,
        used_pool_indices=(0,),
        pool_index=1,
    )
    decisions = DecisionController()
    destroyed_event = decisions.event_log.append(
        "model_destroyed",
        {
            "game_id": state.game_id,
            "battle_round": state.battle_round,
            "active_player_id": state.active_player_id,
            "phase": BattlePhase.FIGHT.value,
            "destroying_player_id": "player-a",
            "attacking_unit_instance_id": bearer.unit_instance_id,
            "attacking_model_instance_id": bearer_model.model_instance_id,
            "sequence_id": attack_sequence.sequence_id,
            "attack_context_id": "phase17g-soulstealer-sequence:pool-001:attack-001",
            "target_unit_instance_id": target.unit_instance_id,
            "model_instance_id": target_model.model_instance_id,
            "damage_kind": "normal",
            "damage_event_id": "phase17g-soulstealer-damage-event",
            "destroyed_model_rules_triggered": True,
        },
    )
    completed_event = decisions.event_log.append(
        "attack_sequence_completed",
        {
            "sequence_id": attack_sequence.sequence_id,
            "attacker_player_id": "player-a",
            "attacking_unit_instance_id": bearer.unit_instance_id,
        },
    )
    roll_spec = DiceRollSpec(
        expression=DiceExpression(quantity=1, sides=6),
        reason="Soulstealer",
        roll_type=enhancements.SOULSTEALER_D6_ROLL_TYPE,
        actor_id=bearer_model.model_instance_id,
    )
    dice_manager = DiceRollManager(
        state.game_id,
        event_log=decisions.event_log,
        injected_results=(
            DiceRollResult.from_values(
                roll_id="phase17g-soulstealer-injected-roll",
                spec=roll_spec,
                values=(4,),
                source="injected",
            ),
        ),
    )

    status = _daemonic_incursion_runtime_bundle(
        state
    ).attack_sequence_completed_hook_registry.resolve_completed_sequence(
        AttackSequenceCompletedContext(
            state=state,
            decisions=decisions,
            dice_manager=dice_manager,
            runtime_modifier_registry=RuntimeModifierRegistry.empty(),
            source_phase=BattlePhase.FIGHT,
            attack_sequence=attack_sequence,
            attack_sequence_completed_event_id=completed_event.event_id,
        )
    )

    assert status is None
    healed_bearer = _unit_by_id(state, bearer.unit_instance_id)
    assert healed_bearer.own_models[0].wounds_remaining == bearer_model.starting_wounds
    payload = last_event_payload(decisions, enhancements.SOULSTEALER_RESOLVED_EVENT)
    assert payload["destroyed_model_event_id"] == destroyed_event.event_id
    assert payload["roll_total"] == 5
    assert payload["heal_succeeded"] is True
    assert payload["healed_wounds"] == 1


def test_daemonic_incursion_execution_record_is_generic_rule_ir() -> None:
    record = _daemonic_incursion_execution_record()

    assert record.execution_status is Phase17FExecutionStatus.EXECUTABLE_GENERIC_IR
    assert record.handler_id is None
    assert record.rule_ir_hash == (
        faction_generic_ir_support_2026_27.generic_rule_ir_hash_by_coverage_descriptor_id(
            daemonic_incursion_ir.DAEMONIC_INCURSION_DETACHMENT_RULE_DESCRIPTOR_ID
        )
    )


def test_daemonic_incursion_stratagem_runtime_records_are_source_backed() -> None:
    contribution = daemonic_stratagems.runtime_contribution()
    records = contribution.stratagem_records

    assert contribution.contribution_id == daemonic_stratagems.CONTRIBUTION_ID
    assert not contribution.contribution_id.endswith(":scaffold")
    assert len(records) == 8
    assert {record.definition.stratagem_id for record in records} == {
        daemonic_incursion_ir.CORRUPT_REALSPACE_STRATAGEM_ID,
        daemonic_incursion_ir.WARP_SURGE_STRATAGEM_ID,
        daemonic_incursion_ir.DRAUGHT_OF_TERROR_STRATAGEM_ID,
        daemonic_incursion_ir.DENIZENS_OF_THE_WARP_STRATAGEM_ID,
        daemonic_incursion_ir.THE_REALM_OF_CHAOS_STRATAGEM_ID,
        daemonic_incursion_ir.DAEMONIC_INVULNERABILITY_STRATAGEM_ID,
    }
    assert all(
        record.detachment_id == rule.DAEMONIC_INCURSION_DETACHMENT_ID
        and record.definition.handler_id == "generic:rule-ir"
        and not record.disabled
        for record in records
    )
    realm_records = tuple(
        record
        for record in records
        if record.definition.stratagem_id == daemonic_incursion_ir.THE_REALM_OF_CHAOS_STRATAGEM_ID
    )
    assert len(realm_records) == 2
    assert any(
        isinstance(record.definition.effect_payload, dict)
        and record.definition.effect_payload.get("effect_selection_kind")
        == "selected_friendly_companion_unit"
        for record in realm_records
    )


def test_daemonic_incursion_stratagem_execution_records_are_generic_rule_ir() -> None:
    stratagem_descriptor_ids = (
        daemonic_incursion_ir.CORRUPT_REALSPACE_DESCRIPTOR_ID,
        daemonic_incursion_ir.WARP_SURGE_DESCRIPTOR_ID,
        daemonic_incursion_ir.DRAUGHT_OF_TERROR_DESCRIPTOR_ID,
        daemonic_incursion_ir.DENIZENS_OF_THE_WARP_DESCRIPTOR_ID,
        daemonic_incursion_ir.THE_REALM_OF_CHAOS_DESCRIPTOR_ID,
        daemonic_incursion_ir.DAEMONIC_INVULNERABILITY_DESCRIPTOR_ID,
    )

    for descriptor_id in stratagem_descriptor_ids:
        record = _execution_record_by_descriptor_id(descriptor_id)
        assert record.execution_status is Phase17FExecutionStatus.EXECUTABLE_GENERIC_IR
        assert record.handler_id is None
        assert record.rule_ir_hash == (
            faction_generic_ir_support_2026_27.generic_rule_ir_hash_by_coverage_descriptor_id(
                descriptor_id
            )
        )


def test_warp_surge_generic_stratagem_records_charge_after_advance_effect() -> None:
    state, _reserve_state, _reserve_unit = _daemonic_incursion_reserve_state()
    target_unit_id = _ANCHOR_UNIT_ID
    definition = _daemonic_stratagem_definition(daemonic_incursion_ir.WARP_SURGE_STRATAGEM_ID)
    decisions = DecisionController()
    use_record = _daemonic_stratagem_use_record(
        definition=definition,
        target_unit_id=target_unit_id,
        phase=BattlePhase.CHARGE,
    )

    _apply_daemonic_stratagem(
        state=state,
        decisions=decisions,
        definition=definition,
        use_record=use_record,
        context=_daemonic_stratagem_context(
            state=state,
            phase=BattlePhase.CHARGE,
            trigger_kind=TimingTriggerKind.START_PHASE,
        ),
    )

    assert charge_after_advance_allowed_by_effects(
        state=state,
        unit_instance_id=target_unit_id,
    )
    effect = _persisting_effect_by_kind(
        state,
        unit_instance_id=target_unit_id,
        effect_kind=CHARGE_AFTER_ADVANCE_EFFECT_KIND,
    )
    payload = cast(dict[str, JsonValue], effect.effect_payload)
    assert effect.source_rule_id == _rule_ir_source_id(
        daemonic_incursion_ir.WARP_SURGE_DESCRIPTOR_ID
    )
    assert payload["source_effect_kind"] == "warp_surge"
    assert payload["stratagem_id"] == daemonic_incursion_ir.WARP_SURGE_STRATAGEM_ID
    execution_payload = cast(dict[str, JsonValue], payload["generic_rule_execution_result"])
    assert execution_payload["status"] == "applied"
    event = last_event_payload(decisions, "generic_stratagem_charge_after_advance_registered")
    event_effect = cast(dict[str, JsonValue], event["persisting_effect"])
    assert event_effect["effect_id"] == effect.effect_id


def test_corrupt_realspace_generic_stratagem_records_sticky_objective_shadow_state() -> None:
    state, _reserve_state, _reserve_unit = _daemonic_incursion_reserve_state()
    if state.mission_setup is None:
        raise AssertionError("test state requires mission setup")
    target_unit_id = _ANCHOR_UNIT_ID
    objective_id = state.mission_setup.objective_markers[0].objective_marker_id
    definition = _daemonic_stratagem_definition(
        daemonic_incursion_ir.CORRUPT_REALSPACE_STRATAGEM_ID
    )
    decisions = DecisionController()
    use_record = _daemonic_stratagem_use_record(
        definition=definition,
        target_unit_id=target_unit_id,
        phase=BattlePhase.COMMAND,
        effect_selection=objective_marker_effect_selection(objective_id),
    )

    _apply_daemonic_stratagem(
        state=state,
        decisions=decisions,
        definition=definition,
        use_record=use_record,
        context=_daemonic_stratagem_context(
            state=state,
            phase=BattlePhase.COMMAND,
            trigger_kind=TimingTriggerKind.START_PHASE,
        ),
    )

    assert len(state.sticky_objective_control_states) == 1
    sticky_state = state.sticky_objective_control_states[0]
    assert sticky_state.objective_id == objective_id
    assert sticky_state.originating_unit_instance_id == target_unit_id
    assert sticky_state.source_rule_id == _rule_ir_source_id(
        daemonic_incursion_ir.CORRUPT_REALSPACE_DESCRIPTOR_ID
    )
    replay_payload = cast(dict[str, JsonValue], sticky_state.replay_payload)
    assert replay_payload["shadow_of_chaos_aura_inches"] == 6.0
    assert replay_payload["stratagem_id"] == daemonic_incursion_ir.CORRUPT_REALSPACE_STRATAGEM_ID
    event = last_event_payload(
        decisions,
        "generic_stratagem_sticky_objective_control_registered",
    )
    event_state = cast(dict[str, JsonValue], event["sticky_objective_control_state"])
    assert event_state["objective_id"] == objective_id


def test_corrupt_realspace_generic_stratagem_requires_objective_selection() -> None:
    state, _reserve_state, _reserve_unit = _daemonic_incursion_reserve_state()
    definition = _daemonic_stratagem_definition(
        daemonic_incursion_ir.CORRUPT_REALSPACE_STRATAGEM_ID
    )

    with pytest.raises(GameLifecycleError, match="requires objective selection"):
        _apply_daemonic_stratagem(
            state=state,
            decisions=DecisionController(),
            definition=definition,
            use_record=_daemonic_stratagem_use_record(
                definition=definition,
                target_unit_id=_ANCHOR_UNIT_ID,
                phase=BattlePhase.COMMAND,
            ),
            context=_daemonic_stratagem_context(
                state=state,
                phase=BattlePhase.COMMAND,
                trigger_kind=TimingTriggerKind.START_PHASE,
            ),
        )


def test_corrupt_realspace_target_policy_uses_controlled_objective_selection() -> None:
    state, _reserve_state, _reserve_unit = _daemonic_incursion_reserve_state()
    if state.mission_setup is None:
        raise AssertionError("test state requires mission setup")
    state.active_player_id = "player-a"
    target_unit = _unit_by_id(state, _ANCHOR_UNIT_ID)
    marker = state.mission_setup.objective_markers[0]
    _place_model(
        state=state,
        model_instance_id=target_unit.own_models[0].model_instance_id,
        pose=Pose.at(
            x=marker.x_inches,
            y=marker.y_inches,
            z=0.0,
            facing_degrees=0.0,
        ),
    )
    context = _daemonic_stratagem_context(
        state=state,
        phase=BattlePhase.COMMAND,
        trigger_kind=TimingTriggerKind.START_PHASE,
    )
    target_binding = _friendly_daemon_target_binding(_ANCHOR_UNIT_ID)
    definition = _daemonic_stratagem_definition(
        daemonic_incursion_ir.CORRUPT_REALSPACE_STRATAGEM_ID
    )

    selections = generic_metadata.controlled_objective_effect_selections_for_binding(
        state=state,
        context=context,
        target_binding=target_binding,
    )
    selected_marker = objective_marker_effect_selection(marker.objective_marker_id)

    assert selected_marker in selections
    assert (
        generic_metadata.objective_selection_error(
            state=state,
            context=context,
            target_binding=target_binding,
            effect_selection=selected_marker,
        )
        is None
    )
    assert (
        generic_metadata.objective_selection_error(
            state=state,
            context=context,
            target_binding=target_binding,
            effect_selection=None,
        )
        == "objective_marker_id_required"
    )
    assert (
        generic_metadata.objective_selection_error(
            state=state,
            context=context,
            target_binding=target_binding,
            effect_selection=objective_marker_effect_selection("uncontrolled-objective"),
        )
        == "objective_marker_not_controlled_by_target_unit"
    )
    assert (
        generic_metadata.objective_selection_error(
            state=state,
            context=context,
            target_binding=None,
            effect_selection=selected_marker,
        )
        == "target_unit_required"
    )
    assert (
        generic_metadata.objective_selection_error(
            state=state,
            context=context,
            target_binding=_friendly_daemon_target_binding(_RESERVE_UNIT_ID),
            effect_selection=selected_marker,
        )
        == "no_controlled_objective_marker"
    )
    assert (
        generic_metadata.objective_marker_id_or_none(
            {
                generic_metadata.EFFECT_SELECTION_KIND_KEY: "wrong-selection-kind",
                generic_metadata.OBJECTIVE_MARKER_CONTEXT_KEY: marker.objective_marker_id,
            }
        )
        is None
    )
    assert (
        generic_metadata.objective_marker_id_or_none(
            {
                generic_metadata.EFFECT_SELECTION_KIND_KEY: (
                    generic_metadata.CONTROLLED_OBJECTIVE_MARKER_EFFECT_SELECTION_KIND
                )
            }
        )
        is None
    )
    with pytest.raises(GameLifecycleError, match="must contain a marker ID"):
        generic_metadata.objective_marker_id_or_none(
            {
                generic_metadata.EFFECT_SELECTION_KIND_KEY: (
                    generic_metadata.CONTROLLED_OBJECTIVE_MARKER_EFFECT_SELECTION_KIND
                ),
                generic_metadata.OBJECTIVE_MARKER_CONTEXT_KEY: 1,
            }
        )
    with pytest.raises(GameLifecycleError, match="Unsupported contextual status"):
        generic_metadata.unit_has_contextual_status(
            state=state,
            player_id="player-a",
            unit_instance_id=_ANCHOR_UNIT_ID,
            status="unsupported-status",
        )
    with pytest.raises(GameLifecycleError, match="must be a string"):
        generic_metadata._payload_string("phase17g-metadata", 1)
    with pytest.raises(GameLifecycleError, match="must not be empty"):
        generic_metadata._payload_string("phase17g-metadata", "   ")
    assert (
        stratagems_targeting._target_binding_error(
            state=state,
            player_id="player-a",
            target_spec=definition.target_spec,
            policy=definition.restriction_policy,
            target_binding=target_binding,
            context=context,
            ruleset_descriptor=_ruleset(),
            army_catalog=_daemonic_incursion_catalog(),
        )
        is None
    )


def test_denizens_target_policy_requires_deep_strike_arriving_unit() -> None:
    state, reserve_state, _reserve_unit = _daemonic_incursion_reserve_state()
    context = _daemonic_stratagem_context(
        state=state,
        phase=BattlePhase.MOVEMENT,
        trigger_kind=TimingTriggerKind.START_PHASE,
    )
    target_binding = _friendly_daemon_target_binding(reserve_state.unit_instance_id)
    definition = _daemonic_stratagem_definition(
        daemonic_incursion_ir.DENIZENS_OF_THE_WARP_STRATAGEM_ID
    )

    assert stratagems_targeting._deep_strike_arriving_unit_ids(
        state=state,
        player_id="player-a",
    ) == (reserve_state.unit_instance_id,)
    assert (
        stratagems_targeting._target_binding_error(
            state=state,
            player_id="player-a",
            target_spec=definition.target_spec,
            policy=definition.restriction_policy,
            target_binding=target_binding,
            context=context,
            ruleset_descriptor=_ruleset(),
            army_catalog=_daemonic_incursion_catalog(),
        )
        is None
    )

    state.replace_reserve_state(
        replace(
            reserve_state,
            status=ReserveStatus.ARRIVED,
            arrived_battle_round=1,
            arrived_phase=BattlePhase.MOVEMENT.value,
        )
    )

    assert (
        stratagems_targeting._deep_strike_arriving_unit_ids(
            state=state,
            player_id="player-a",
        )
        == ()
    )
    assert (
        stratagems_targeting._target_binding_error(
            state=state,
            player_id="player-a",
            target_spec=definition.target_spec,
            policy=definition.restriction_policy,
            target_binding=target_binding,
            context=context,
            ruleset_descriptor=_ruleset(),
            army_catalog=_daemonic_incursion_catalog(),
        )
        == "unit_not_eligible_for_deep_strike_arrival"
    )


def test_daemonic_invulnerability_save_reroll_permission_filters_unmodified_ones() -> None:
    permission_context = _daemonic_invulnerability_permission_context(
        {"conditional_save_reroll": {"reroll_unmodified_values": [1]}}
    )
    failed_save = _save_roll_state(value=1)
    passed_save = _save_roll_state(value=2)

    permission = _source_backed_save_permission_for_attack(
        permission_context=permission_context,
        roll_state=failed_save,
    )

    assert permission is not None
    assert (
        permission.component_selection_policy is RerollComponentSelectionPolicy.COMPONENT_SELECTION
    )
    assert permission.allowed_component_selections == ((0,),)
    assert (
        _source_backed_save_permission_for_attack(
            permission_context=permission_context,
            roll_state=passed_save,
        )
        is None
    )
    with pytest.raises(GameLifecycleError, match="must be an object"):
        _source_backed_save_permission_for_attack(
            permission_context=_daemonic_invulnerability_permission_context(
                {"conditional_save_reroll": "bad-payload"}
            ),
            roll_state=failed_save,
        )
    with pytest.raises(GameLifecycleError, match="requires integer reroll values"):
        _source_backed_save_permission_for_attack(
            permission_context=_daemonic_invulnerability_permission_context(
                {"conditional_save_reroll": {"reroll_unmodified_values": [True]}}
            ),
            roll_state=failed_save,
        )


def test_draught_of_terror_exposes_battle_shocked_wound_reroll_permission() -> None:
    state, _reserve_state, _reserve_unit = _daemonic_incursion_reserve_state()
    target_unit_id = _ANCHOR_UNIT_ID
    enemy_unit_id = _enemy_unit_id(state)
    definition = _daemonic_stratagem_definition_for_phase(
        daemonic_incursion_ir.DRAUGHT_OF_TERROR_STRATAGEM_ID,
        phase=BattlePhase.SHOOTING,
    )
    decisions = DecisionController()

    _apply_daemonic_stratagem(
        state=state,
        decisions=decisions,
        definition=definition,
        use_record=_daemonic_stratagem_use_record(
            definition=definition,
            target_unit_id=target_unit_id,
            phase=BattlePhase.SHOOTING,
        ),
        context=_daemonic_stratagem_context(
            state=state,
            phase=BattlePhase.SHOOTING,
            trigger_kind=TimingTriggerKind.START_PHASE,
        ),
    )

    permission_context = source_backed_reroll_permission_context_for_unit(
        state=state,
        player_id="player-a",
        unit_instance_id=target_unit_id,
        roll_type="attack_sequence.wound",
        timing_window="attack_sequence.wound",
        target_unit_instance_id=enemy_unit_id,
    )

    assert permission_context is not None
    conditional = permission_context.source_payload["conditional_wound_reroll"]
    assert isinstance(conditional, dict)
    assert conditional["reroll_unmodified_values"] == []
    assert conditional["full_reroll_if_target_battle_shocked"] is True
    wound_roll = _wound_roll_state(value=2)
    assert (
        _source_backed_wound_permission_for_attack(
            state=state,
            permission_context=permission_context,
            roll_state=wound_roll,
            target_unit_instance_id=enemy_unit_id,
            attacker_keywords=_unit_by_id(state, target_unit_id).keywords,
        )
        is None
    )

    state.battle_shocked_unit_ids.append(enemy_unit_id)
    permission = _source_backed_wound_permission_for_attack(
        state=state,
        permission_context=permission_context,
        roll_state=wound_roll,
        target_unit_instance_id=enemy_unit_id,
        attacker_keywords=_unit_by_id(state, target_unit_id).keywords,
    )

    assert permission is not None
    assert permission.component_selection_policy is RerollComponentSelectionPolicy.WHOLE_ROLL
    assert permission.allowed_component_selections is None


def test_draught_of_terror_improves_weapon_ap_through_generic_attack_hook() -> None:
    state, _reserve_state, _reserve_unit = _daemonic_incursion_reserve_state()
    target_unit = _unit_by_id(state, _ANCHOR_UNIT_ID)
    enemy_unit_id = _enemy_unit_id(state)
    definition = _daemonic_stratagem_definition_for_phase(
        daemonic_incursion_ir.DRAUGHT_OF_TERROR_STRATAGEM_ID,
        phase=BattlePhase.SHOOTING,
    )
    profile = _weapon_profile()

    _apply_daemonic_stratagem(
        state=state,
        decisions=DecisionController(),
        definition=definition,
        use_record=_daemonic_stratagem_use_record(
            definition=definition,
            target_unit_id=target_unit.unit_instance_id,
            phase=BattlePhase.SHOOTING,
        ),
        context=_daemonic_stratagem_context(
            state=state,
            phase=BattlePhase.SHOOTING,
            trigger_kind=TimingTriggerKind.START_PHASE,
        ),
    )

    modified = RuntimeModifierRegistry.empty().modified_weapon_profile(
        WeaponProfileModifierContext(
            state=state,
            source_phase=BattlePhase.SHOOTING,
            attacking_unit_instance_id=target_unit.unit_instance_id,
            attacker_model_instance_id=target_unit.own_models[0].model_instance_id,
            target_unit_instance_id=enemy_unit_id,
            weapon_profile=profile,
        )
    )

    assert modified.armor_penetration.final == profile.armor_penetration.final - 1


def test_draught_of_terror_wound_reroll_payload_validation_is_fail_fast() -> None:
    state, _reserve_state, _reserve_unit = _daemonic_incursion_reserve_state()
    enemy_unit_id = _enemy_unit_id(state)
    wound_roll = _wound_roll_state(value=1)

    with pytest.raises(GameLifecycleError, match="must be an object"):
        _source_backed_wound_permission_for_attack(
            state=state,
            permission_context=_daemonic_wound_permission_context(
                {"conditional_wound_reroll": "bad-payload"}
            ),
            roll_state=wound_roll,
            target_unit_instance_id=enemy_unit_id,
            attacker_keywords=(),
        )
    with pytest.raises(GameLifecycleError, match="requires integer reroll values"):
        _source_backed_wound_permission_for_attack(
            state=state,
            permission_context=_daemonic_wound_permission_context(
                {"conditional_wound_reroll": {"reroll_unmodified_values": [True]}}
            ),
            roll_state=wound_roll,
            target_unit_instance_id=enemy_unit_id,
            attacker_keywords=(),
        )
    with pytest.raises(GameLifecycleError, match="battle-shock reroll must be bool"):
        _source_backed_wound_permission_for_attack(
            state=state,
            permission_context=_daemonic_wound_permission_context(
                {
                    "conditional_wound_reroll": {
                        "full_reroll_if_target_battle_shocked": "yes",
                        "reroll_unmodified_values": [1],
                    }
                }
            ),
            roll_state=wound_roll,
            target_unit_instance_id=enemy_unit_id,
            attacker_keywords=(),
        )


def test_daemonic_invulnerability_save_reroll_without_condition_uses_permission() -> None:
    permission_context = _daemonic_invulnerability_permission_context({})
    permission = _source_backed_save_permission_for_attack(
        permission_context=permission_context,
        roll_state=_save_roll_state(value=4),
    )

    assert permission is permission_context.permission


def test_the_realm_of_chaos_removes_unit_to_deep_strike_required_reserves() -> None:
    state, _reserve_state, _reserve_unit = _daemonic_incursion_reserve_state()
    definition = _daemonic_stratagem_definition_by_effect_selection_kind(
        daemonic_incursion_ir.THE_REALM_OF_CHAOS_STRATAGEM_ID,
        effect_selection_kind=None,
    )
    decisions = DecisionController()

    _apply_daemonic_stratagem(
        state=state,
        decisions=decisions,
        definition=definition,
        use_record=_daemonic_stratagem_use_record(
            definition=definition,
            target_unit_id=_ANCHOR_UNIT_ID,
            phase=BattlePhase.MOVEMENT,
        ),
        context=_daemonic_stratagem_context(
            state=state,
            phase=BattlePhase.MOVEMENT,
            trigger_kind=TimingTriggerKind.END_TURN,
        ),
    )

    reserve_state = state.reserve_state_for_unit(_ANCHOR_UNIT_ID)
    assert reserve_state is not None
    assert reserve_state.reserve_kind is ReserveKind.STRATEGIC_RESERVES
    assert reserve_state.required_arrival_battle_round == state.battle_round + 1
    assert reserve_state.required_arrival_phase == BattlePhase.MOVEMENT.value
    assert (
        reserve_state.required_arrival_placement_kind == BattlefieldPlacementKind.DEEP_STRIKE.value
    )
    assert (
        reserve_state.required_arrival_source_rule_id
        == daemonic_incursion_ir.THE_REALM_OF_CHAOS_SOURCE_RULE_ID
    )
    event = last_event_payload(decisions, "generic_stratagem_reserve_removal_resolved")
    reserve_payloads = cast(list[JsonValue], event["reserve_states"])
    assert len(reserve_payloads) == 1
    reserve_payload = cast(dict[str, JsonValue], reserve_payloads[0])
    assert reserve_payload["unit_instance_id"] == _ANCHOR_UNIT_ID
    assert reserve_payload["required_arrival_placement_kind"] == "deep_strike"


def test_realm_of_chaos_config_backed_replay_binds_active_runtime_catalog() -> None:
    lifecycle = _config_backed_realm_of_chaos_lifecycle()

    assert GameLifecycle.from_payload(lifecycle.to_payload()).to_payload() == lifecycle.to_payload()


def test_realm_of_chaos_replay_requires_active_runtime_catalog() -> None:
    lifecycle = _config_backed_realm_of_chaos_lifecycle()
    payload: GameLifecyclePayload = deepcopy(lifecycle.to_payload())
    payload["config"] = None

    with pytest.raises(
        GameLifecycleError,
        match="requires active runtime Stratagem catalog authority",
    ):
        GameLifecycle.from_payload(payload)


def test_realm_of_chaos_replay_rejects_coordinated_carried_catalog_drift() -> None:
    lifecycle = _config_backed_realm_of_chaos_lifecycle()
    payload: GameLifecyclePayload = deepcopy(lifecycle.to_payload())

    _rewrite_realm_of_chaos_catalog_source(payload, source_id="forged:catalog-source")

    with pytest.raises(
        GameLifecycleError,
        match="active catalog authority drift",
    ):
        GameLifecycle.from_payload(payload)


def test_realm_of_chaos_replay_binds_full_rule_execution_context() -> None:
    lifecycle = _config_backed_realm_of_chaos_lifecycle()
    payload: GameLifecyclePayload = deepcopy(lifecycle.to_payload())
    execution_events = tuple(
        event
        for event in payload["decisions"]["event_log"]
        if event["event_type"] == "rule_execution_effect_applied"
    )
    if len(execution_events) != 1:
        raise AssertionError("test requires one Realm of Chaos RuleIR effect event")
    execution_payload = execution_events[0]["payload"]
    assert isinstance(execution_payload, dict)
    execution_context = execution_payload["context"]
    assert isinstance(execution_context, dict)
    execution_context["active_player_id"] = "player-b"

    with pytest.raises(
        GameLifecycleError,
        match="Stratagem reserve provider execution event drift",
    ):
        GameLifecycle.from_payload(payload)


def test_realm_of_chaos_provider_rejects_coordinated_disabled_catalog_record() -> None:
    lifecycle = _config_backed_realm_of_chaos_lifecycle()
    payload: GameLifecyclePayload = deepcopy(lifecycle.to_payload())
    _rewrite_realm_of_chaos_catalog_disabled(payload)
    decisions = DecisionController.from_payload(payload["decisions"])
    state = GameState.from_payload(payload["state"])
    runtime_bundle = lifecycle._runtime_content_bundle
    if runtime_bundle is None:
        raise AssertionError("test requires runtime content")
    original_index = runtime_bundle.stratagem_indexes_by_player_id["player-a"]
    disabled_index = StratagemCatalogIndex.from_records(
        tuple(
            replace(record, disabled=True)
            if record.definition.stratagem_id
            == daemonic_incursion_ir.THE_REALM_OF_CHAOS_STRATAGEM_ID
            else record
            for record in original_index.all_records()
        )
    )

    with pytest.raises(GameLifecycleError, match="active catalog authority drift"):
        validate_primary_reserve_entry_lifecycle_integrity(
            state=state,
            event_records=decisions.event_log.records,
            decision_records=decisions.records,
            stratagem_indexes_by_player_id={"player-a": disabled_index},
        )


def test_realm_of_chaos_replay_rejects_orphan_empty_source_terminal() -> None:
    lifecycle = _config_backed_realm_of_chaos_lifecycle()
    payload: GameLifecyclePayload = deepcopy(lifecycle.to_payload())
    event_log = payload["decisions"]["event_log"]
    source_terminal = next(
        event
        for event in event_log
        if event["event_type"] == "generic_stratagem_reserve_removal_resolved"
    )
    orphan_payload = deepcopy(source_terminal["payload"])
    assert isinstance(orphan_payload, dict)
    orphan_use = orphan_payload["stratagem_use"]
    assert isinstance(orphan_use, dict)
    orphan_use["use_id"] = "orphan-realm-of-chaos-use"
    orphan_payload["primary_reserve_entry_bindings"] = []
    orphan_payload["reserve_states"] = []
    event_log.append(
        {
            "event_id": f"event-{len(event_log) + 1:06d}",
            "event_type": "generic_stratagem_reserve_removal_resolved",
            "payload": orphan_payload,
        }
    )

    with pytest.raises(
        GameLifecycleError,
        match="requires non-empty bindings",
    ):
        GameLifecycle.from_payload(payload)


def test_realm_of_chaos_replay_rejects_altered_duplicate_source_binding() -> None:
    lifecycle = _config_backed_realm_of_chaos_lifecycle()
    payload: GameLifecyclePayload = deepcopy(lifecycle.to_payload())
    source_terminal = next(
        event
        for event in payload["decisions"]["event_log"]
        if event["event_type"] == "generic_stratagem_reserve_removal_resolved"
    )
    source_payload = source_terminal["payload"]
    assert isinstance(source_payload, dict)
    bindings = source_payload["primary_reserve_entry_bindings"]
    assert isinstance(bindings, list)
    assert len(bindings) == 1
    altered = deepcopy(bindings[0])
    assert isinstance(altered, dict)
    provider = altered["provider"]
    reserve_entry = altered["reserve_entry_state"]
    assert isinstance(provider, dict)
    assert isinstance(reserve_entry, dict)
    provider["source_rule_id"] = "forged:rule-ir-source"
    reserve_entry["source_rule_ids"] = ["forged:rule-ir-source"]
    bindings.append(altered)

    with pytest.raises(
        GameLifecycleError,
        match="source terminal occurrence is duplicated",
    ):
        GameLifecycle.from_payload(payload)


def test_realm_of_chaos_replay_rejects_provider_with_mismatched_stratagem_use() -> None:
    lifecycle = _config_backed_realm_of_chaos_lifecycle()
    payload: GameLifecyclePayload = deepcopy(lifecycle.to_payload())

    _rewrite_realm_of_chaos_provider_use_id(
        payload,
        stratagem_use_id="forged:realm-of-chaos-use",
    )

    with pytest.raises(
        GameLifecycleError,
        match=(
            r"authoritative reserve mutation event|source terminal use is missing|"
            r"use identity is missing"
        ),
    ):
        GameLifecycle.from_payload(payload)


def test_realm_of_chaos_replay_rejects_forged_arrived_status() -> None:
    lifecycle = _config_backed_realm_of_chaos_lifecycle()
    state = lifecycle.state
    if state is None or state.battlefield_state is None:
        raise AssertionError("test lifecycle requires battlefield state")
    reserve_state = state.reserve_states[0]
    reserve_unit = state.army_definitions[0].unit_by_id(reserve_state.unit_instance_id)
    placement = reserve_placement(
        reserve_unit=reserve_unit,
        poses=tuple(
            Pose.at(x=10.0 + 2.0 * index, y=30.0, z=0.0, facing_degrees=0.0)
            for index in range(len(reserve_unit.own_models))
        ),
    )
    state.replace_battlefield_state(state.battlefield_state.with_added_unit_placement(placement))
    state.replace_reserve_state(
        reserve_state.mark_arrived(
            battle_round=2,
            phase=BattlePhase.MOVEMENT,
            large_model_exception_used=False,
            post_arrival_restrictions=(),
        )
    )

    with pytest.raises(
        GameLifecycleError,
        match="Arrived ReserveState lacks one authenticated arrival",
    ):
        GameLifecycle.from_payload(lifecycle.to_payload())


def test_realm_of_chaos_replay_rejects_forged_destroyed_status() -> None:
    lifecycle = _config_backed_realm_of_chaos_lifecycle()
    state = lifecycle.state
    if state is None or state.battlefield_state is None:
        raise AssertionError("test lifecycle requires battlefield state")
    reserve_state = state.reserve_states[0]
    reserve_unit = state.army_definitions[0].unit_by_id(reserve_state.unit_instance_id)
    state.replace_battlefield_state(
        state.battlefield_state.with_unplaced_models_marked_removed(
            tuple(model.model_instance_id for model in reserve_unit.own_models)
        )
    )
    state.replace_reserve_state(reserve_state.mark_destroyed(battle_round=3))

    with pytest.raises(
        GameLifecycleError,
        match="lacks one authenticated reserve-deadline destruction",
    ):
        GameLifecycle.from_payload(lifecycle.to_payload())


def test_realm_of_chaos_real_reinforcement_arrival_replays_and_rejects_clone() -> None:
    lifecycle = _config_backed_realm_of_chaos_lifecycle()
    state = lifecycle.state
    if state is None:
        raise AssertionError("test lifecycle requires state")
    _arrive_realm_target_from_reserves(
        lifecycle=lifecycle,
        battle_round=2,
        result_id_prefix="phase17g-realm-arrival",
    )

    restored = GameLifecycle.from_payload(lifecycle.to_payload())

    assert restored.state is not None
    assert restored.state.reserve_states[0].status is ReserveStatus.ARRIVED
    assert restored.state.reserve_states[0].arrived_battle_round == 2
    cloned_payload: GameLifecyclePayload = deepcopy(lifecycle.to_payload())
    event_log = cloned_payload["decisions"]["event_log"]
    arrival_event = next(
        event for event in event_log if event["event_type"] == "reinforcement_unit_arrived"
    )
    event_log.append(
        {
            "event_id": f"event-{len(event_log) + 1:06d}",
            "event_type": "reinforcement_unit_arrived",
            "payload": deepcopy(arrival_event["payload"]),
        }
    )
    with pytest.raises(GameLifecycleError, match="Reserve arrival decision record is reused"):
        GameLifecycle.from_payload(cloned_payload)


@pytest.fixture(scope="module")
def phase17n_realm_retry_payload() -> GameLifecyclePayload:
    lifecycle = _config_backed_realm_of_chaos_lifecycle()
    _arrive_realm_target_from_reserves(
        lifecycle=lifecycle,
        battle_round=2,
        result_id_prefix="phase17n-realm-arrival-retry",
        invalid_first=True,
    )
    return lifecycle.to_payload()


def test_realm_of_chaos_invalid_placement_retry_then_valid_arrival_replays(
    phase17n_realm_retry_payload: GameLifecyclePayload,
) -> None:
    payload = deepcopy(phase17n_realm_retry_payload)

    restored = GameLifecycle.from_payload(deepcopy(payload))

    assert restored.to_payload() == payload
    assert restored.state is not None
    assert restored.state.reserve_states[0].status is ReserveStatus.ARRIVED
    assert any(
        event.event_type == "reinforcement_placement_invalid"
        for event in restored.decision_controller.event_log.records
    )


@pytest.fixture(scope="module")
def phase17n_realm_arrival_payload() -> GameLifecyclePayload:
    lifecycle = _config_backed_realm_of_chaos_lifecycle()
    _arrive_realm_target_from_reserves(
        lifecycle=lifecycle,
        battle_round=2,
        result_id_prefix="phase17n-realm-authority",
    )
    return lifecycle.to_payload()


def test_realm_of_chaos_replay_rejects_coordinated_arrival_placement_kind_tamper(
    phase17n_realm_arrival_payload: GameLifecyclePayload,
) -> None:
    result_id = "phase17n-realm-authority-place"
    payload: GameLifecyclePayload = deepcopy(phase17n_realm_arrival_payload)
    decision = _decision_record_payload_for_result(payload, result_id=result_id)
    result_payload = _json_object_for_test(decision["result"]["payload"])
    result_payload["placement_kind"] = BattlefieldPlacementKind.STRATEGIC_RESERVES.value
    _sync_decision_recorded_event(payload, decision=decision)

    arrival_payload = _arrival_event_payload_for_result(payload, result_id=result_id)
    arrival_payload["placement_kind"] = BattlefieldPlacementKind.STRATEGIC_RESERVES.value
    transition_payload = _json_object_for_test(arrival_payload["transition_batch"])
    transition_placements = _json_object_list_for_test(transition_payload["placements"])
    for placement in transition_placements:
        placement["placement_kind"] = BattlefieldPlacementKind.STRATEGIC_RESERVES.value

    with pytest.raises(
        GameLifecycleError,
        match="Reserve arrival request/result proposal authority drift",
    ):
        GameLifecycle.from_payload(payload)


@pytest.mark.parametrize(
    ("field_name", "forged_value"),
    [
        ("source_rule_id", "forged:arrival-source-rule"),
        ("source_phase", BattlePhase.SHOOTING.value),
        ("source_step", "forged_arrival_step"),
        ("source_event_id", "forged:arrival-source-event"),
    ],
)
def test_realm_of_chaos_replay_rejects_transition_source_authority_tamper(
    phase17n_realm_arrival_payload: GameLifecyclePayload,
    field_name: str,
    forged_value: str,
) -> None:
    result_id = "phase17n-realm-authority-place"
    payload: GameLifecyclePayload = deepcopy(phase17n_realm_arrival_payload)
    arrival_payload = _arrival_event_payload_for_result(payload, result_id=result_id)
    transition_payload = _json_object_for_test(arrival_payload["transition_batch"])
    transition_placements = _json_object_list_for_test(transition_payload["placements"])
    for placement in transition_placements:
        placement[field_name] = forged_value

    with pytest.raises(
        GameLifecycleError,
        match="Reserve arrival transition source authority drift",
    ):
        GameLifecycle.from_payload(payload)


def test_realm_of_chaos_replay_rejects_invented_arrival_model_identity(
    phase17n_realm_arrival_payload: GameLifecyclePayload,
) -> None:
    result_id = "phase17n-realm-authority-place"
    payload: GameLifecyclePayload = deepcopy(phase17n_realm_arrival_payload)
    invented_model_id = "army-alpha:daemon-unit:invented-model"

    decision = _decision_record_payload_for_result(payload, result_id=result_id)
    result_payload = _json_object_for_test(decision["result"]["payload"])
    attempted_placement = _json_object_for_test(result_payload["attempted_placement"])
    attempted_models = _json_object_list_for_test(attempted_placement["model_placements"])
    attempted_models[0]["model_instance_id"] = invented_model_id
    _sync_decision_recorded_event(payload, decision=decision)

    arrival_payload = _arrival_event_payload_for_result(payload, result_id=result_id)
    rules_unit_placement = _json_object_for_test(arrival_payload["rules_unit_placement"])
    component_placements = _json_object_list_for_test(
        rules_unit_placement["component_unit_placements"]
    )
    arrived_models = _json_object_list_for_test(component_placements[0]["model_placements"])
    arrived_models[0]["model_instance_id"] = invented_model_id
    transition_payload = _json_object_for_test(arrival_payload["transition_batch"])
    transition_placements = _json_object_list_for_test(transition_payload["placements"])
    transition_placements[0]["model_instance_id"] = invented_model_id

    with pytest.raises(
        GameLifecycleError,
        match="Reserve arrival request/result proposal authority drift",
    ):
        GameLifecycle.from_payload(payload)


@pytest.mark.parametrize(
    ("tamper_kind", "error_match"),
    [
        ("arrival_phase_body_status", "Reserve arrival route event authority drift"),
        ("arrival_component_ids", "Reserve arrival route event authority drift"),
        ("predecessor_ids", "Reserve arrival placement request predecessor drift"),
        ("proposal_kind", "Reserve arrival request ReserveState authority drift"),
        ("context_model_ids", "Reserve arrival request/result proposal authority drift"),
        ("context_reserve_source", "Reserve arrival request ReserveState source drift"),
        ("context_reserve_missing", "Reserve arrival request lacks ReserveState source authority"),
    ],
)
def test_realm_of_chaos_replay_rejects_arrival_route_contract_tamper(
    phase17n_realm_arrival_payload: GameLifecyclePayload,
    tamper_kind: str,
    error_match: str,
) -> None:
    result_id = "phase17n-realm-authority-place"
    payload: GameLifecyclePayload = deepcopy(phase17n_realm_arrival_payload)
    decision = _decision_record_payload_for_result(payload, result_id=result_id)
    request_payload = _placement_proposal_request_payload_for_test(decision)
    result_payload = _json_object_for_test(decision["result"]["payload"])
    arrival_payload = _arrival_event_payload_for_result(payload, result_id=result_id)
    proposal_event_payload = _placement_proposal_requested_payload_for_test(
        payload,
        request_id=decision["request"]["request_id"],
    )

    if tamper_kind == "arrival_phase_body_status":
        arrival_payload["phase_body_status"] = "forged_arrival_status"
    elif tamper_kind == "arrival_component_ids":
        arrival_payload["component_unit_instance_ids"] = ["army-alpha:forged-component"]
    elif tamper_kind == "predecessor_ids":
        request_payload["source_decision_request_id"] = "forged:selection-request"
        request_payload["source_decision_result_id"] = "forged:selection-result"
        proposal_event_payload["source_decision_request_id"] = "forged:selection-request"
        proposal_event_payload["source_decision_result_id"] = "forged:selection-result"
    elif tamper_kind == "proposal_kind":
        forged_kind = "strategic_reserves_placement"
        request_payload["proposal_kind"] = forged_kind
        result_payload["proposal_kind"] = forged_kind
        proposal_event_payload["proposal_kind"] = forged_kind
    elif tamper_kind == "context_model_ids":
        context = _json_object_for_test(request_payload["context"])
        context["model_instance_ids"] = ["army-alpha:daemon-unit:invented-model"]
    elif tamper_kind == "context_reserve_source":
        context = _json_object_for_test(request_payload["context"])
        reserve_state_payload = _json_object_for_test(context["reserve_state"])
        reserve_state_payload["source_rule_ids"] = ["forged:reserve-source"]
    elif tamper_kind == "context_reserve_missing":
        context = _json_object_for_test(request_payload["context"])
        context.pop("reserve_state")
    else:
        raise AssertionError(f"unsupported arrival route tamper: {tamper_kind}")

    if tamper_kind not in {"arrival_phase_body_status", "arrival_component_ids"}:
        _sync_decision_requested_event(payload, decision=decision)
        _sync_decision_recorded_event(payload, decision=decision)
    with pytest.raises(GameLifecycleError, match=error_match):
        GameLifecycle.from_payload(payload)


@pytest.mark.parametrize(
    ("tamper_kind", "error_match"),
    [
        ("missing_source", "Reserve arrival lacks one placement source event"),
        ("spatial_authority", "placement request spatial authority drift"),
        ("source_authority", "placement source event authority drift"),
        ("source_order", "placement source event ordering drift"),
        ("selection_authority", "reinforcement selection authority drift"),
        ("selection_event", "reinforcement selection event closure drift"),
        ("selection_order", "reinforcement selection ordering drift"),
        ("arrival_order", "Reserve arrival decision ordering drift"),
    ],
)
def test_realm_of_chaos_replay_rejects_arrival_source_and_event_order_tamper(
    phase17n_realm_arrival_payload: GameLifecyclePayload,
    tamper_kind: str,
    error_match: str,
) -> None:
    payload: GameLifecyclePayload = deepcopy(phase17n_realm_arrival_payload)
    placement_result_id = "phase17n-realm-authority-place"
    placement_decision = _decision_record_payload_for_result(
        payload,
        result_id=placement_result_id,
    )
    placement_request_id = placement_decision["request"]["request_id"]
    placement_source_event = _event_record_for_request_id(
        payload,
        event_type="placement_proposal_requested",
        request_id=placement_request_id,
    )
    placement_requested_event = _event_record_for_request_id(
        payload,
        event_type="decision_requested",
        request_id=placement_request_id,
    )
    selection_decision = _decision_record_payload_for_result(
        payload,
        result_id="phase17n-realm-authority-select",
    )
    selection_terminal_event = _event_record_for_request_id(
        payload,
        event_type="reinforcement_unit_selected",
        request_id=selection_decision["request"]["request_id"],
    )

    if tamper_kind == "missing_source":
        placement_source_event["event_type"] = "forged_placement_proposal_requested"
    elif tamper_kind == "spatial_authority":
        _json_object_for_test(placement_source_event["payload"])["spatial_context_hash"] = (
            "forged:spatial-context"
        )
    elif tamper_kind == "source_authority":
        _json_object_for_test(placement_source_event["payload"])["phase_body_status"] = (
            "forged_placement_status"
        )
    elif tamper_kind == "source_order":
        _swap_event_contents(placement_requested_event, placement_source_event)
    elif tamper_kind == "selection_authority":
        selection_request_payload = _json_object_for_test(selection_decision["request"]["payload"])
        selection_request_payload["active_player_id"] = "player-b"
        _sync_decision_requested_event(payload, decision=selection_decision)
        _sync_decision_recorded_event(payload, decision=selection_decision)
    elif tamper_kind == "selection_event":
        _json_object_for_test(selection_terminal_event["payload"])["phase_body_status"] = (
            "forged_selection_status"
        )
    elif tamper_kind == "selection_order":
        _swap_event_contents(selection_terminal_event, placement_requested_event)
    elif tamper_kind == "arrival_order":
        arrival_event = _event_record_for_result_id(
            payload,
            event_type="reinforcement_unit_arrived",
            result_id=placement_result_id,
        )
        placement_recorded_event = _event_record_for_result_id(
            payload,
            event_type="decision_recorded",
            result_id=placement_result_id,
        )
        _swap_event_contents(arrival_event, placement_recorded_event)
    else:
        raise AssertionError(f"unsupported source/order tamper: {tamper_kind}")

    with pytest.raises(GameLifecycleError, match=error_match):
        GameLifecycle.from_payload(payload)


@pytest.mark.parametrize(
    ("tamper_kind", "error_match"),
    [
        ("missing_predecessor", "retry lacks one rejected predecessor"),
        ("predecessor_authority", "retry predecessor authority drift"),
        ("predecessor_order", "retry predecessor ordering drift"),
        ("missing_invalid_event", "retry lacks one invalid predecessor event"),
        ("invalid_event_authority", "retry invalid event authority drift"),
        ("invalid_event_order", "retry invalid event ordering drift"),
    ],
)
def test_realm_of_chaos_replay_rejects_arrival_retry_chain_tamper(
    phase17n_realm_retry_payload: GameLifecyclePayload,
    tamper_kind: str,
    error_match: str,
) -> None:
    payload: GameLifecyclePayload = deepcopy(phase17n_realm_retry_payload)
    final_decision = _decision_record_payload_for_result(
        payload,
        result_id="phase17n-realm-arrival-retry-place",
    )
    rejected_decision = _decision_record_payload_for_result(
        payload,
        result_id="phase17n-realm-arrival-retry-invalid",
    )
    final_request_id = final_decision["request"]["request_id"]
    rejected_request_id = rejected_decision["request"]["request_id"]
    final_source_event = _event_record_for_request_id(
        payload,
        event_type="placement_proposal_requested",
        request_id=final_request_id,
    )
    invalid_event = _event_record_for_result_id(
        payload,
        event_type="reinforcement_placement_invalid",
        result_id=rejected_decision["result"]["result_id"],
    )

    if tamper_kind == "missing_predecessor":
        final_source_payload = _json_object_for_test(final_source_event["payload"])
        final_source_payload["previous_proposal_request_id"] = "forged:previous-request"
        final_source_payload["rejected_result_id"] = "forged:rejected-result"
    elif tamper_kind == "predecessor_authority":
        previous_request = _placement_proposal_request_payload_for_test(rejected_decision)
        previous_context = _json_object_for_test(previous_request["context"])
        previous_context["forged_authority"] = True
        _sync_decision_requested_event(payload, decision=rejected_decision)
        _sync_decision_recorded_event(payload, decision=rejected_decision)
    elif tamper_kind == "predecessor_order":
        predecessor_requested = _event_record_for_request_id(
            payload,
            event_type="decision_requested",
            request_id=rejected_request_id,
        )
        predecessor_recorded = _event_record_for_result_id(
            payload,
            event_type="decision_recorded",
            result_id=rejected_decision["result"]["result_id"],
        )
        _swap_event_contents(predecessor_requested, predecessor_recorded)
    elif tamper_kind == "missing_invalid_event":
        invalid_event["event_type"] = "forged_reinforcement_placement_invalid"
    elif tamper_kind == "invalid_event_authority":
        _json_object_for_test(invalid_event["payload"])["violations"] = []
    elif tamper_kind == "invalid_event_order":
        final_requested = _event_record_for_request_id(
            payload,
            event_type="decision_requested",
            request_id=final_request_id,
        )
        _swap_event_contents(invalid_event, final_requested)
    else:
        raise AssertionError(f"unsupported retry tamper: {tamper_kind}")

    with pytest.raises(GameLifecycleError, match=error_match):
        GameLifecycle.from_payload(payload)


def test_rapid_ingress_retry_rejects_invalid_event_player_authority(
    phase17n_rapid_ingress_retry_payload: GameLifecyclePayload,
) -> None:
    payload: GameLifecyclePayload = deepcopy(phase17n_rapid_ingress_retry_payload)
    invalid_event = _event_record_for_result_id(
        payload,
        event_type="rapid_ingress_placement_invalid",
        result_id="phase17n-rapid-ingress-retry:invalid",
    )
    _json_object_for_test(invalid_event["payload"])["player_id"] = "player-b"

    with pytest.raises(GameLifecycleError, match="retry invalid event authority drift"):
        GameLifecycle.from_payload(payload)


@pytest.mark.parametrize(
    ("tamper_kind", "error_match"),
    [
        ("missing_terminal", "source/provider terminal closure drift"),
        ("binding", "provider terminal binding drift"),
        ("ordering", "source/provider terminal ordering drift"),
        ("occurrence", "provider terminal occurrence drift"),
        ("duplicate", "provider terminal occurrence is duplicated"),
        ("empty_evidence", "provider terminal reserve evidence is empty"),
        ("extra_field", "provider terminal fields are malformed"),
    ],
)
def test_realm_of_chaos_replay_rejects_provider_terminal_integrity_tamper(
    phase17n_realm_arrival_payload: GameLifecyclePayload,
    tamper_kind: str,
    error_match: str,
) -> None:
    payload: GameLifecyclePayload = deepcopy(phase17n_realm_arrival_payload)
    source_terminal = _event_record_for_type(
        payload,
        event_type="generic_stratagem_reserve_removal_resolved",
    )
    provider_terminal = _event_record_for_type(
        payload,
        event_type="primary_reserve_entry_provider_resolved",
    )
    provider_payload = _json_object_for_test(provider_terminal["payload"])

    if tamper_kind == "missing_terminal":
        provider_terminal["event_type"] = "forged_provider_terminal"
    elif tamper_kind == "binding":
        provider_payload["source_terminal_event_id"] = "event:forged"
    elif tamper_kind == "ordering":
        _swap_event_contents(source_terminal, provider_terminal)
        swapped_provider_payload = _json_object_for_test(source_terminal["payload"])
        swapped_provider_payload["source_terminal_event_id"] = provider_terminal["event_id"]
    elif tamper_kind == "occurrence":
        provider_payload["occurrence_id"] = "occurrence:forged"
    elif tamper_kind == "duplicate":
        event_log = payload["decisions"]["event_log"]
        event_log.append(
            {
                "event_id": f"event-{len(event_log) + 1:06d}",
                "event_type": provider_terminal["event_type"],
                "payload": deepcopy(provider_terminal["payload"]),
            }
        )
    elif tamper_kind == "empty_evidence":
        provider_payload["reserve_entry_state"] = {}
    elif tamper_kind == "extra_field":
        provider_payload["forged"] = True
    else:
        raise AssertionError(f"unsupported provider-terminal tamper: {tamper_kind}")

    state = GameState.from_payload(payload["state"])
    decisions = DecisionController.from_payload(payload["decisions"])
    runtime_bundle = _daemonic_incursion_runtime_bundle(state)
    with pytest.raises(GameLifecycleError, match=error_match):
        validate_primary_reserve_entry_lifecycle_integrity(
            state=state,
            event_records=decisions.event_log.records,
            decision_records=decisions.records,
            stratagem_indexes_by_player_id=runtime_bundle.stratagem_indexes_by_player_id,
        )


def test_declared_reserve_arrival_realm_reentry_and_second_arrival_replay() -> None:
    lifecycle = _config_backed_realm_of_chaos_lifecycle(prior_declared_arrival=True)
    state = lifecycle.state
    if state is None:
        raise AssertionError("test lifecycle requires state")
    assert (
        sum(
            event.event_type == "reinforcement_unit_arrived"
            for event in lifecycle.decision_controller.event_log.records
        )
        == 1
    )

    _arrive_realm_target_from_reserves(
        lifecycle=lifecycle,
        battle_round=3,
        result_id_prefix="phase17n-realm-second-arrival",
    )

    payload = lifecycle.to_payload()
    restored = GameLifecycle.from_payload(deepcopy(payload))
    assert restored.to_payload() == payload
    assert restored.state is not None
    assert restored.state.reserve_states[0].status is ReserveStatus.ARRIVED
    assert (
        sum(
            event.event_type == "reinforcement_unit_arrived"
            for event in restored.decision_controller.event_log.records
        )
        == 2
    )


def test_realm_reentry_rapid_ingress_binds_opponent_active_player() -> None:
    lifecycle = _config_backed_realm_of_chaos_lifecycle(prior_declared_arrival=True)
    record = _active_ingress_record(lifecycle, stratagem_id="rapid-ingress")
    _submit_config_backed_ingress(
        lifecycle=lifecycle,
        record=record,
        active_player_id="player-b",
        placement_kind=BattlefieldPlacementKind.DEEP_STRIKE,
        result_id_prefix="phase17n-rapid-ingress-reentry",
    )

    payload = lifecycle.to_payload()
    restored = GameLifecycle.from_payload(deepcopy(payload))
    assert restored.to_payload() == payload
    assert restored.state is not None
    assert restored.state.active_player_id == "player-b"

    forged_payload: GameLifecyclePayload = deepcopy(payload)
    matching_events = tuple(
        event
        for event in forged_payload["decisions"]["event_log"]
        if event["event_type"] in {"reinforcement_unit_arrived", "rapid_ingress_resolved"}
        and isinstance(event["payload"], dict)
        and event["payload"].get("step") == "rapid_ingress"
    )
    if len(matching_events) != 2:
        raise AssertionError("test requires one Rapid Ingress arrival/terminal pair")
    for event in matching_events:
        _json_object_for_test(event["payload"])["active_player_id"] = "player-a"
    with pytest.raises(GameLifecycleError, match="Reserve arrival placement identity drift"):
        GameLifecycle.from_payload(forged_payload)


@pytest.fixture(scope="module")
def phase17n_rapid_ingress_retry_payload() -> GameLifecyclePayload:
    lifecycle = _config_backed_realm_of_chaos_lifecycle(prior_declared_arrival=True)
    record = _active_ingress_record(lifecycle, stratagem_id="rapid-ingress")
    _submit_config_backed_ingress(
        lifecycle=lifecycle,
        record=record,
        active_player_id="player-b",
        placement_kind=BattlefieldPlacementKind.DEEP_STRIKE,
        result_id_prefix="phase17n-rapid-ingress-retry",
        invalid_first=True,
    )
    return lifecycle.to_payload()


def test_realm_reentry_rapid_ingress_invalid_retry_replays(
    phase17n_rapid_ingress_retry_payload: GameLifecyclePayload,
) -> None:
    payload = deepcopy(phase17n_rapid_ingress_retry_payload)

    restored = GameLifecycle.from_payload(deepcopy(payload))

    assert restored.to_payload() == payload
    assert restored.state is not None
    assert restored.state.reserve_states[0].status is ReserveStatus.ARRIVED
    assert any(
        event.event_type == "rapid_ingress_placement_invalid"
        for event in restored.decision_controller.event_log.records
    )


def test_realm_of_chaos_occurrence_requires_persisted_reserve_state() -> None:
    lifecycle = _config_backed_realm_of_chaos_lifecycle()
    state = lifecycle.state
    if state is None:
        raise AssertionError("test lifecycle requires state")
    state.reserve_states.clear()
    runtime_bundle = _daemonic_incursion_runtime_bundle(state)

    with pytest.raises(
        GameLifecycleError,
        match="occurrence lacks its persisted ReserveState",
    ):
        validate_primary_reserve_entry_lifecycle_integrity(
            state=state,
            event_records=lifecycle.decision_controller.event_log.records,
            decision_records=lifecycle.decision_controller.records,
            stratagem_indexes_by_player_id=runtime_bundle.stratagem_indexes_by_player_id,
        )


def test_realm_of_chaos_no_mission_audit_rejects_forged_requested_event() -> None:
    lifecycle = _config_backed_realm_of_chaos_lifecycle()
    state = lifecycle.state
    if state is None:
        raise AssertionError("test lifecycle requires state")
    state.mission_setup = None
    requested_event = next(
        event
        for event in lifecycle.decision_controller.event_log.records
        if event.event_type == "decision_requested"
    )
    requested_payload = cast(dict[str, JsonValue], requested_event.payload)
    forged_event = EventRecord(
        event_id=requested_event.event_id,
        event_type=requested_event.event_type,
        payload={**requested_payload, "request_id": "forged:request"},
    )
    events = tuple(
        forged_event if event.event_id == requested_event.event_id else event
        for event in lifecycle.decision_controller.event_log.records
    )
    runtime_bundle = _daemonic_incursion_runtime_bundle(state)

    with pytest.raises(
        GameLifecycleError,
        match="exact requested and recorded decision events",
    ):
        validate_primary_reserve_entry_lifecycle_integrity(
            state=state,
            event_records=events,
            decision_records=lifecycle.decision_controller.records,
            stratagem_indexes_by_player_id=runtime_bundle.stratagem_indexes_by_player_id,
        )


def test_realm_of_chaos_provider_audit_rejects_source_terminal_round_drift() -> None:
    lifecycle = _config_backed_realm_of_chaos_lifecycle()
    state = lifecycle.state
    if state is None:
        raise AssertionError("test lifecycle requires state")
    events = tuple(
        EventRecord(
            event_id=event.event_id,
            event_type=event.event_type,
            payload={**cast(dict[str, JsonValue], event.payload), "battle_round": 99},
        )
        if event.event_type == "generic_stratagem_reserve_removal_resolved"
        else event
        for event in lifecycle.decision_controller.event_log.records
    )
    runtime_bundle = _daemonic_incursion_runtime_bundle(state)

    with pytest.raises(GameLifecycleError, match="source terminal timing drift"):
        validate_primary_reserve_entry_lifecycle_integrity(
            state=state,
            event_records=events,
            decision_records=lifecycle.decision_controller.records,
            stratagem_indexes_by_player_id=runtime_bundle.stratagem_indexes_by_player_id,
        )


def test_realm_of_chaos_provider_audit_recomputes_required_arrival() -> None:
    lifecycle = _config_backed_realm_of_chaos_lifecycle()
    state = lifecycle.state
    if state is None:
        raise AssertionError("test lifecycle requires state")
    events: list[EventRecord] = []
    for event in lifecycle.decision_controller.event_log.records:
        if event.event_type != "generic_stratagem_reserve_removal_resolved":
            events.append(event)
            continue
        payload = deepcopy(cast(dict[str, JsonValue], event.payload))
        bindings = cast(list[JsonValue], payload["primary_reserve_entry_bindings"])
        binding = cast(dict[str, JsonValue], bindings[0])
        binding_reserve = cast(dict[str, JsonValue], binding["reserve_entry_state"])
        reserve_states = cast(list[JsonValue], payload["reserve_states"])
        terminal_reserve = cast(dict[str, JsonValue], reserve_states[0])
        binding_reserve["required_arrival_battle_round"] = 3
        terminal_reserve["required_arrival_battle_round"] = 3
        events.append(
            EventRecord(
                event_id=event.event_id,
                event_type=event.event_type,
                payload=payload,
            )
        )
    runtime_bundle = _daemonic_incursion_runtime_bundle(state)

    with pytest.raises(GameLifecycleError, match="source requirements drift"):
        validate_primary_reserve_entry_lifecycle_integrity(
            state=state,
            event_records=tuple(events),
            decision_records=lifecycle.decision_controller.records,
            stratagem_indexes_by_player_id=runtime_bundle.stratagem_indexes_by_player_id,
        )


@pytest.mark.parametrize(
    "reserve_origin",
    [
        ReserveOrigin.DURING_BATTLE_ABILITY,
        ReserveOrigin.DURING_BATTLE_STRATAGEM,
        ReserveOrigin.DURING_BATTLE_OTHER,
    ],
)
def test_replay_rejects_standalone_during_battle_reserve_state(
    reserve_origin: ReserveOrigin,
) -> None:
    lifecycle = _config_backed_realm_of_chaos_lifecycle()
    state = lifecycle.state
    if state is None:
        raise AssertionError("test lifecycle requires state")
    if len(state.reserve_states) != 1:
        raise AssertionError("test lifecycle requires Realm of Chaos ReserveState")
    authoritative_reserve = state.reserve_states[0]
    enemy_unit = next(
        unit
        for army in state.army_definitions
        if army.player_id == "player-b"
        for unit in army.units
    )
    fabricated = ReserveState.entered_during_battle(
        player_id="player-b",
        unit_instance_id=enemy_unit.unit_instance_id,
        reserve_kind=ReserveKind.STRATEGIC_RESERVES,
        battle_round=state.battle_round,
        phase=BattlePhase.MOVEMENT,
        reserve_origin=reserve_origin,
        destruction_deadline_policy=authoritative_reserve.destruction_deadline_policy,
        source_rule_ids=(f"forged:{reserve_origin.value}",),
    ).mark_arrived(
        battle_round=state.battle_round,
        phase=BattlePhase.MOVEMENT,
        large_model_exception_used=False,
        post_arrival_restrictions=(),
    )
    payload: GameLifecyclePayload = deepcopy(lifecycle.to_payload())
    payload["state"]["reserve_states"].append(fabricated.to_payload())

    with pytest.raises(
        GameLifecycleError,
        match="lacks an authoritative entry occurrence",
    ):
        GameLifecycle.from_payload(payload)


def test_staged_realm_of_chaos_requires_first_turn_generic_ingress() -> None:
    state, _reserve_state, _reserve_unit = _daemonic_incursion_reserve_state()
    state.active_player_id = "player-b"
    state.turn_order = ("player-b", "player-a")
    definition = next(
        record.definition
        for record in july_updates.runtime_contribution().stratagem_records
        if isinstance(record.definition.effect_payload, dict)
        and record.definition.effect_payload.get("effect_selection_kind") is None
    )
    decisions = DecisionController()
    use_record = replace(
        _daemonic_stratagem_use_record(
            definition=definition,
            target_unit_id=_ANCHOR_UNIT_ID,
            phase=BattlePhase.MOVEMENT,
        ),
        active_player_id="player-b",
    )
    context = replace(
        _daemonic_stratagem_context(
            state=state,
            phase=BattlePhase.MOVEMENT,
            trigger_kind=TimingTriggerKind.END_TURN,
        ),
        active_player_id="player-b",
    )

    _apply_daemonic_stratagem(
        state=state,
        decisions=decisions,
        definition=definition,
        use_record=use_record,
        context=context,
    )

    reserve_state = state.reserve_state_for_unit(_ANCHOR_UNIT_ID)
    assert reserve_state is not None
    assert reserve_state.arrival_is_required_at(
        battle_round=1,
        phase=BattlePhase.MOVEMENT,
    )
    assert (
        reserve_state.required_arrival_placement_kind
        == BattlefieldPlacementKind.STRATEGIC_RESERVES.value
    )
    assert reserve_state.required_arrival_source_rule_id == definition.source_id
    event = last_event_payload(decisions, "generic_stratagem_reserve_removal_resolved")
    generic_effect = cast(dict[str, JsonValue], event["generic_rule_effect"])
    effect = cast(dict[str, JsonValue], generic_effect["effect"])
    parameters = cast(list[dict[str, JsonValue]], effect["parameters"])
    assert {cast(str, parameter["key"]): parameter["value"] for parameter in parameters}[
        "required_arrival_timing"
    ] == "next_owner_movement_phase"


def test_the_realm_of_chaos_companion_selection_requires_shadow_units() -> None:
    state, _reserve_state, reserve_unit = _daemonic_incursion_reserve_state()
    if state.mission_setup is None:
        raise AssertionError("test state requires mission setup")
    target_unit = _unit_by_id(state, _ANCHOR_UNIT_ID)
    marker = state.mission_setup.objective_markers[0]
    marker_pose = Pose.at(
        x=marker.x_inches,
        y=marker.y_inches,
        z=0.0,
        facing_degrees=0.0,
    )
    _place_model(
        state=state,
        model_instance_id=target_unit.own_models[0].model_instance_id,
        pose=marker_pose,
    )
    _place_unit_on_battlefield(state=state, unit=reserve_unit, pose=marker_pose)
    corrupt_definition = _daemonic_stratagem_definition(
        daemonic_incursion_ir.CORRUPT_REALSPACE_STRATAGEM_ID
    )
    _apply_daemonic_stratagem(
        state=state,
        decisions=DecisionController(),
        definition=corrupt_definition,
        use_record=_daemonic_stratagem_use_record(
            definition=corrupt_definition,
            target_unit_id=target_unit.unit_instance_id,
            phase=BattlePhase.COMMAND,
            effect_selection=objective_marker_effect_selection(marker.objective_marker_id),
        ),
        context=_daemonic_stratagem_context(
            state=state,
            phase=BattlePhase.COMMAND,
            trigger_kind=TimingTriggerKind.START_PHASE,
        ),
    )
    definition = _daemonic_stratagem_definition_by_effect_selection_kind(
        daemonic_incursion_ir.THE_REALM_OF_CHAOS_STRATAGEM_ID,
        effect_selection_kind=generic_metadata.SELECTED_FRIENDLY_COMPANION_UNIT_EFFECT_SELECTION_KIND,
    )
    context = _daemonic_stratagem_context(
        state=state,
        phase=BattlePhase.MOVEMENT,
        trigger_kind=TimingTriggerKind.END_TURN,
    )
    target_binding = _friendly_daemon_target_binding(target_unit.unit_instance_id)
    companion_selection = generic_metadata.companion_unit_effect_selection(
        reserve_unit.unit_instance_id
    )

    selections = generic_metadata.companion_effect_selections_for_binding(
        state=state,
        definition=definition,
        context=context,
        target_binding=target_binding,
    )

    assert companion_selection in selections
    assert (
        generic_metadata.companion_selection_error(
            state=state,
            definition=definition,
            context=context,
            target_binding=target_binding,
            effect_selection=companion_selection,
        )
        is None
    )
    assert generic_metadata.generic_rule_ir_execution_target_unit_ids(
        state=state,
        use_record=_daemonic_stratagem_use_record(
            definition=definition,
            target_unit_id=target_unit.unit_instance_id,
            phase=BattlePhase.MOVEMENT,
            effect_selection=companion_selection,
        ),
    ) == tuple(sorted((target_unit.unit_instance_id, reserve_unit.unit_instance_id)))


def test_denizens_lifecycle_ability_sources_filter_selected_daemonic_incursion() -> None:
    execution_records = faction_execution_2026_27.phase17f_execution_package().execution_records
    selected_sources = generic_rule_lifecycle_ability_sources.generic_rule_ability_sources(
        activation=_runtime_activation(
            selected_detachment_ids=(rule.DAEMONIC_INCURSION_DETACHMENT_ID,),
        ),
        execution_records=execution_records,
        coverage_descriptor_id=daemonic_incursion_ir.DENIZENS_OF_THE_WARP_DESCRIPTOR_ID,
        ability_ids=(daemonic_incursion_ir.DENIZENS_OF_THE_WARP_DEEP_STRIKE_DISTANCE_ABILITY,),
    )

    assert len(selected_sources) == 1
    assert (
        selected_sources[0].record.coverage_descriptor_id
        == daemonic_incursion_ir.DENIZENS_OF_THE_WARP_DESCRIPTOR_ID
    )
    assert (
        generic_rule_lifecycle_ability_sources.generic_rule_ability_sources(
            activation=_runtime_activation(selected_detachment_ids=(_OTHER_DAEMON_DETACHMENT_ID,)),
            execution_records=execution_records,
            coverage_descriptor_id=daemonic_incursion_ir.DENIZENS_OF_THE_WARP_DESCRIPTOR_ID,
            ability_ids=(daemonic_incursion_ir.DENIZENS_OF_THE_WARP_DEEP_STRIKE_DISTANCE_ABILITY,),
        )
        == ()
    )
    assert (
        generic_rule_lifecycle_ability_sources.generic_rule_ability_sources(
            activation=_runtime_activation(
                selected_detachment_ids=(rule.DAEMONIC_INCURSION_DETACHMENT_ID,),
            ),
            execution_records=execution_records,
            coverage_descriptor_id=daemonic_incursion_ir.DENIZENS_OF_THE_WARP_DESCRIPTOR_ID,
            ability_ids=("phase17g-daemonic-incursion:missing-ability",),
        )
        == ()
    )

    with pytest.raises(GameLifecycleError, match="require activation"):
        generic_rule_lifecycle_ability_sources.generic_rule_ability_sources(
            activation=cast(RuntimeContentActivation, object()),
            execution_records=execution_records,
            coverage_descriptor_id=daemonic_incursion_ir.DENIZENS_OF_THE_WARP_DESCRIPTOR_ID,
            ability_ids=(daemonic_incursion_ir.DENIZENS_OF_THE_WARP_DEEP_STRIKE_DISTANCE_ABILITY,),
        )
    with pytest.raises(GameLifecycleError, match="require execution records"):
        generic_rule_lifecycle_ability_sources.generic_rule_ability_sources(
            activation=_runtime_activation(
                selected_detachment_ids=(rule.DAEMONIC_INCURSION_DETACHMENT_ID,),
            ),
            execution_records=cast(
                tuple[faction_execution_2026_27.Phase17FExecutionRecord, ...],
                [],
            ),
            coverage_descriptor_id=daemonic_incursion_ir.DENIZENS_OF_THE_WARP_DESCRIPTOR_ID,
            ability_ids=(daemonic_incursion_ir.DENIZENS_OF_THE_WARP_DEEP_STRIKE_DISTANCE_ABILITY,),
        )
    with pytest.raises(GameLifecycleError, match="require execution records"):
        generic_rule_lifecycle_ability_sources.generic_rule_ability_sources(
            activation=_runtime_activation(
                selected_detachment_ids=(rule.DAEMONIC_INCURSION_DETACHMENT_ID,),
            ),
            execution_records=(cast(faction_execution_2026_27.Phase17FExecutionRecord, object()),),
            coverage_descriptor_id=daemonic_incursion_ir.DENIZENS_OF_THE_WARP_DESCRIPTOR_ID,
            ability_ids=(daemonic_incursion_ir.DENIZENS_OF_THE_WARP_DEEP_STRIKE_DISTANCE_ABILITY,),
        )
    with pytest.raises(GameLifecycleError, match="requires RuleIR"):
        generic_rule_lifecycle_ability_sources._validate_record_rule_ir_hash(
            record=selected_sources[0].record,
            rule_ir=cast(RuleIR, object()),
        )
    missing_hash_record = replace(selected_sources[0].record)
    object.__setattr__(missing_hash_record, "rule_ir_hash", None)
    with pytest.raises(GameLifecycleError, match="requires rule_ir_hash"):
        generic_rule_lifecycle_ability_sources._validate_record_rule_ir_hash(
            record=missing_hash_record,
            rule_ir=_rule_ir_by_descriptor_id(
                daemonic_incursion_ir.DENIZENS_OF_THE_WARP_DESCRIPTOR_ID
            ),
        )
    with pytest.raises(GameLifecycleError, match="hash drift"):
        generic_rule_lifecycle_ability_sources.generic_rule_ability_sources(
            activation=_runtime_activation(
                selected_detachment_ids=(rule.DAEMONIC_INCURSION_DETACHMENT_ID,),
            ),
            execution_records=(replace(selected_sources[0].record, rule_ir_hash="0" * 64),),
            coverage_descriptor_id=daemonic_incursion_ir.DENIZENS_OF_THE_WARP_DESCRIPTOR_ID,
            ability_ids=(daemonic_incursion_ir.DENIZENS_OF_THE_WARP_DEEP_STRIKE_DISTANCE_ABILITY,),
        )


def test_reserve_arrival_requirement_helpers_are_fail_fast() -> None:
    _state, reserve_state, _reserve_unit = _daemonic_incursion_reserve_state()
    assert reserve_arrival_requirements.kind_token(None) is None
    assert (
        reserve_arrival_requirements.kind_token(BattlefieldPlacementKind.DEEP_STRIKE)
        == BattlefieldPlacementKind.DEEP_STRIKE.value
    )
    assert (
        reserve_arrival_requirements.kind_token("deep_strike")
        == BattlefieldPlacementKind.DEEP_STRIKE.value
    )
    with pytest.raises(GameLifecycleError, match="fields must be complete"):
        reserve_arrival_requirements.validate_fields(
            battle_round=2,
            phase=None,
            source_rule_id=daemonic_incursion_ir.THE_REALM_OF_CHAOS_SOURCE_RULE_ID,
            placement_kind=None,
        )
    with pytest.raises(GameLifecycleError, match="placement kind requires required arrival"):
        reserve_arrival_requirements.validate_fields(
            battle_round=None,
            phase=None,
            source_rule_id=None,
            placement_kind=BattlefieldPlacementKind.DEEP_STRIKE.value,
        )
    with pytest.raises(GameLifecycleError, match="satisfy required arrival"):
        reserve_arrival_requirements.validate_status_fields(
            replace(
                reserve_state,
                status=ReserveStatus.ARRIVED,
                arrived_battle_round=3,
                arrived_phase=BattlePhase.MOVEMENT.value,
                required_arrival_battle_round=2,
                required_arrival_phase=BattlePhase.MOVEMENT.value,
                required_arrival_source_rule_id=(
                    daemonic_incursion_ir.THE_REALM_OF_CHAOS_SOURCE_RULE_ID
                ),
                required_arrival_placement_kind=BattlefieldPlacementKind.DEEP_STRIKE.value,
            )
        )
    assert (
        reserve_arrival_requirements.reposition_destruction_policy(
            mission_setup=None,
            destruction_deadline_policy=None,
        )
        == ReserveDestructionTimingPolicy.core_rules_default()
    )
    explicit_policy = ReserveDestructionTimingPolicy.core_rules_default()
    assert (
        reserve_arrival_requirements.reposition_destruction_policy(
            mission_setup=None,
            destruction_deadline_policy=explicit_policy,
        )
        is explicit_policy
    )
    with pytest.raises(GameLifecycleError, match="must be a policy"):
        reserve_arrival_requirements.reposition_destruction_policy(
            mission_setup=None,
            destruction_deadline_policy="invalid-policy",
        )


def test_warp_surge_persisted_duration_validation_is_fail_fast() -> None:
    state, _reserve_state, _reserve_unit = _daemonic_incursion_reserve_state()
    context = _daemonic_stratagem_context(
        state=state,
        phase=BattlePhase.CHARGE,
        trigger_kind=TimingTriggerKind.START_PHASE,
    )
    use_record = _daemonic_stratagem_use_record(
        definition=_daemonic_stratagem_definition(daemonic_incursion_ir.WARP_SURGE_STRATAGEM_ID),
        target_unit_id=_ANCHOR_UNIT_ID,
        phase=BattlePhase.CHARGE,
    )
    rule_ir = _rule_ir_by_descriptor_id(daemonic_incursion_ir.WARP_SURGE_DESCRIPTOR_ID)
    effect_payload = _single_rule_effect_payload(
        descriptor_id=daemonic_incursion_ir.WARP_SURGE_DESCRIPTOR_ID,
        effect_kind="grant_ability",
    )
    decisions = DecisionController()

    generic_persisted.record_generic_charge_after_advance_effect(
        state=state,
        decisions=decisions,
        context=context,
        use_record=use_record,
        rule_result=_rule_result(rule_ir, effect_payload),
        effect_payload={
            **effect_payload,
            "duration": {"kind": "permanent", "parameters": []},
        },
    )

    effect = _persisting_effect_by_kind(
        state,
        unit_instance_id=_ANCHOR_UNIT_ID,
        effect_kind=CHARGE_AFTER_ADVANCE_EFFECT_KIND,
    )
    assert effect.expiration.expiration_kind is EffectExpirationKind.END_OF_BATTLE
    with pytest.raises(GameLifecycleError, match="requires duration"):
        generic_persisted.record_generic_charge_after_advance_effect(
            state=state,
            decisions=DecisionController(),
            context=context,
            use_record=use_record,
            rule_result=_rule_result(rule_ir, effect_payload),
            effect_payload={
                key: value for key, value in effect_payload.items() if key != "duration"
            },
        )
    with pytest.raises(GameLifecycleError, match="endpoint is unsupported"):
        generic_persisted.record_generic_charge_after_advance_effect(
            state=state,
            decisions=DecisionController(),
            context=context,
            use_record=use_record,
            rule_result=_rule_result(rule_ir, effect_payload),
            effect_payload={
                **effect_payload,
                "duration": {
                    "kind": "until_timing_endpoint",
                    "parameters": [{"key": "endpoint", "value": "unsupported-endpoint"}],
                },
            },
        )


def test_warp_surge_persisted_payload_validation_is_fail_fast() -> None:
    _state, _reserve_state, _reserve_unit = _daemonic_incursion_reserve_state()
    definition = _daemonic_stratagem_definition(daemonic_incursion_ir.WARP_SURGE_STRATAGEM_ID)
    use_record = _daemonic_stratagem_use_record(
        definition=definition,
        target_unit_id=_ANCHOR_UNIT_ID,
        phase=BattlePhase.CHARGE,
    )

    with pytest.raises(GameLifecycleError, match="requires use record"):
        generic_persisted._single_target_unit_id(cast(StratagemUseRecord, object()))
    with pytest.raises(GameLifecycleError, match="requires one target unit"):
        generic_persisted._single_target_unit_id(replace(use_record, targeted_unit_instance_ids=()))
    with pytest.raises(GameLifecycleError, match="requires source_id"):
        generic_persisted._rule_effect_source_id({})

    with pytest.raises(GameLifecycleError, match="requires effect object"):
        generic_persisted._rule_effect_parameter({}, "source_effect_kind")
    with pytest.raises(GameLifecycleError, match="parameters must be a list"):
        generic_persisted._rule_effect_parameter(
            {"effect": {"parameters": "not-a-list"}},
            "source_effect_kind",
        )
    with pytest.raises(GameLifecycleError, match="parameter must be an object"):
        generic_persisted._rule_effect_parameter(
            {"effect": {"parameters": ["not-an-object"]}},
            "source_effect_kind",
        )

    missing_parameter_payload: dict[str, JsonValue] = {
        "effect": {"parameters": [{"key": "other", "value": "ignored"}]}
    }
    assert (
        generic_persisted._optional_rule_effect_string_parameter(
            missing_parameter_payload,
            "source_effect_kind",
        )
        is None
    )
    bad_string_payload: dict[str, JsonValue] = {
        "effect": {"parameters": [{"key": "source_effect_kind", "value": 1}]}
    }
    with pytest.raises(GameLifecycleError, match="must be a string"):
        generic_persisted._required_rule_effect_string_parameter(
            bad_string_payload,
            "source_effect_kind",
        )
    with pytest.raises(GameLifecycleError, match="must be a string"):
        generic_persisted._optional_rule_effect_string_parameter(
            bad_string_payload,
            "source_effect_kind",
        )


def test_warp_surge_persisted_duration_helper_supports_turn_and_battle_endpoints() -> None:
    state, _reserve_state, _reserve_unit = _daemonic_incursion_reserve_state()
    context = _daemonic_stratagem_context(
        state=state,
        phase=BattlePhase.CHARGE,
        trigger_kind=TimingTriggerKind.START_PHASE,
    )
    use_record = _daemonic_stratagem_use_record(
        definition=_daemonic_stratagem_definition(daemonic_incursion_ir.WARP_SURGE_STRATAGEM_ID),
        target_unit_id=_ANCHOR_UNIT_ID,
        phase=BattlePhase.CHARGE,
    )
    effect_payload = _single_rule_effect_payload(
        descriptor_id=daemonic_incursion_ir.WARP_SURGE_DESCRIPTOR_ID,
        effect_kind="grant_ability",
    )

    turn_expiration = generic_persisted._expiration_for_rule_effect_payload(
        effect_payload={
            **effect_payload,
            "duration": {
                "kind": "until_timing_endpoint",
                "parameters": [{"key": "endpoint", "value": "turn"}],
            },
        },
        context=context,
        use_record=use_record,
    )
    assert turn_expiration.expiration_kind is EffectExpirationKind.END_TURN
    assert turn_expiration.player_id == "player-a"
    battle_expiration = generic_persisted._expiration_for_rule_effect_payload(
        effect_payload={
            **effect_payload,
            "duration": {
                "kind": "until_timing_endpoint",
                "parameters": [{"key": "endpoint", "value": "battle"}],
            },
        },
        context=context,
        use_record=use_record,
    )
    assert battle_expiration.expiration_kind is EffectExpirationKind.END_OF_BATTLE

    with pytest.raises(GameLifecycleError, match="duration is unsupported"):
        generic_persisted._expiration_for_rule_effect_payload(
            effect_payload={**effect_payload, "duration": {"kind": "unsupported"}},
            context=context,
            use_record=use_record,
        )
    with pytest.raises(GameLifecycleError, match="parameters must be a list"):
        generic_persisted._duration_parameter({"parameters": "not-a-list"}, "endpoint")
    with pytest.raises(GameLifecycleError, match="parameter must be an object"):
        generic_persisted._duration_parameter({"parameters": ["bad"]}, "endpoint")
    assert (
        generic_persisted._duration_parameter(
            {
                "parameters": [
                    {"key": "other", "value": "ignored"},
                    {"key": "endpoint", "value": "turn"},
                ]
            },
            "endpoint",
        )
        == "turn"
    )
    with pytest.raises(GameLifecycleError, match="must be a string"):
        generic_persisted._duration_parameter(
            {"parameters": [{"key": "endpoint", "value": 1}]},
            "endpoint",
        )
    with pytest.raises(GameLifecycleError, match="parameter is missing"):
        generic_persisted._duration_parameter(
            {"parameters": [{"key": "other", "value": "turn"}]},
            "endpoint",
        )


def test_corrupt_realspace_persisted_payload_validation_is_fail_fast() -> None:
    state, _reserve_state, _reserve_unit = _daemonic_incursion_reserve_state()
    if state.mission_setup is None:
        raise AssertionError("test state requires mission setup")
    objective_id = state.mission_setup.objective_markers[0].objective_marker_id
    definition = _daemonic_stratagem_definition(
        daemonic_incursion_ir.CORRUPT_REALSPACE_STRATAGEM_ID
    )
    use_record = _daemonic_stratagem_use_record(
        definition=definition,
        target_unit_id=_ANCHOR_UNIT_ID,
        phase=BattlePhase.COMMAND,
        effect_selection=objective_marker_effect_selection(objective_id),
    )
    context = _daemonic_stratagem_context(
        state=state,
        phase=BattlePhase.COMMAND,
        trigger_kind=TimingTriggerKind.START_PHASE,
    )
    rule_ir = _rule_ir_by_descriptor_id(daemonic_incursion_ir.CORRUPT_REALSPACE_DESCRIPTOR_ID)
    effect_payload = _single_rule_effect_payload(
        descriptor_id=daemonic_incursion_ir.CORRUPT_REALSPACE_DESCRIPTOR_ID,
        effect_kind="set_contextual_status",
    )
    rule_result = _rule_result(rule_ir, effect_payload)

    with pytest.raises(GameLifecycleError, match="requires active player"):
        generic_persisted.record_generic_sticky_objective_control_state(
            state=state,
            decisions=DecisionController(),
            context=replace(context, active_player_id=None),
            use_record=use_record,
            rule_result=rule_result,
            effect_payload=effect_payload,
        )
    with pytest.raises(GameLifecycleError, match="requires objective selection"):
        generic_persisted.record_generic_sticky_objective_control_state(
            state=state,
            decisions=DecisionController(),
            context=context,
            use_record=use_record,
            rule_result=rule_result,
            effect_payload=_with_rule_effect_parameter(
                effect_payload,
                key="objective_selection",
                value="wrong-selection",
            ),
        )
    with pytest.raises(GameLifecycleError, match="must be a string"):
        generic_persisted.record_generic_sticky_objective_control_state(
            state=state,
            decisions=DecisionController(),
            context=context,
            use_record=use_record,
            rule_result=rule_result,
            effect_payload=_with_rule_effect_parameter(
                effect_payload,
                key="sticky_effect_kind",
                value=1,
            ),
        )
    with pytest.raises(GameLifecycleError, match="must be numeric"):
        generic_persisted.record_generic_sticky_objective_control_state(
            state=state,
            decisions=DecisionController(),
            context=context,
            use_record=use_record,
            rule_result=rule_result,
            effect_payload=_with_rule_effect_parameter(
                effect_payload,
                key="shadow_of_chaos_aura_inches",
                value="six",
            ),
        )


def test_charge_after_advance_effect_helper_ignores_non_object_payloads() -> None:
    state, _reserve_state, _reserve_unit = _daemonic_incursion_reserve_state()
    state.record_persisting_effect(
        PersistingEffect(
            effect_id="phase17g-daemonic-incursion:list-payload-effect",
            source_rule_id=daemonic_incursion_ir.WARP_SURGE_SOURCE_RULE_ID,
            owner_player_id="player-a",
            target_unit_instance_ids=(_ANCHOR_UNIT_ID,),
            started_battle_round=1,
            started_phase=BattlePhase.CHARGE,
            expiration=EffectExpiration.end_phase(
                battle_round=1,
                phase=BattlePhase.CHARGE,
                player_id="player-a",
            ),
            effect_payload=["not-an-object"],
        )
    )

    assert not charge_after_advance_allowed_by_effects(
        state=state,
        unit_instance_id=_ANCHOR_UNIT_ID,
    )


def test_warp_rifts_shadow_allows_deep_strike_more_than_six_from_enemy() -> None:
    state, reserve_state, reserve_unit = _daemonic_incursion_reserve_state()
    target_pose = Pose.at(x=16.0, y=4.25, z=0.0, facing_degrees=0.0)
    _place_enemy_at_base_distance(state=state, target_pose=target_pose, distance_inches=7.0)

    status = _submit_deep_strike_arrival(
        state=state,
        reserve_state=reserve_state,
        reserve_unit=reserve_unit,
        target_pose=target_pose,
        result_id="phase17g-warp-rifts-shadow-arrival",
    )

    assert status.status_kind is LifecycleStatusKind.ADVANCED
    arrived_state = state.reserve_state_for_unit(reserve_state.unit_instance_id)
    assert arrived_state is not None
    assert arrived_state.status is ReserveStatus.ARRIVED
    arrival_event = last_event_payload(status.decisions, "reinforcement_unit_arrived")
    assert arrival_event["placement_kind"] == BattlefieldPlacementKind.DEEP_STRIKE.value


def test_warp_rifts_matching_greater_daemon_anchor_allows_deep_strike_outside_shadow() -> None:
    state, reserve_state, reserve_unit = _daemonic_incursion_reserve_state()
    target_pose = Pose.at(x=30.0, y=22.0, z=0.0, facing_degrees=0.0)
    _place_enemy_at_base_distance(state=state, target_pose=target_pose, distance_inches=7.0)
    _place_anchor_at_base_distance(
        state=state,
        target_pose=target_pose,
        distance_inches=4.0,
    )

    status = _submit_deep_strike_arrival(
        state=state,
        reserve_state=reserve_state,
        reserve_unit=reserve_unit,
        target_pose=target_pose,
        result_id="phase17g-warp-rifts-anchor-arrival",
    )

    assert status.status_kind is LifecycleStatusKind.ADVANCED
    arrived_state = state.reserve_state_for_unit(reserve_state.unit_instance_id)
    assert arrived_state is not None
    assert arrived_state.status is ReserveStatus.ARRIVED


def test_warp_rifts_requires_shared_god_keyword_for_greater_daemon_anchor() -> None:
    state, reserve_state, reserve_unit = _daemonic_incursion_reserve_state(
        reserve_god_keyword="Tzeentch",
        anchor_god_keyword="Khorne",
    )
    target_pose = Pose.at(x=30.0, y=22.0, z=0.0, facing_degrees=0.0)
    _place_enemy_at_base_distance(state=state, target_pose=target_pose, distance_inches=7.0)
    _place_anchor_at_base_distance(
        state=state,
        target_pose=target_pose,
        distance_inches=4.0,
    )

    status = _submit_deep_strike_arrival(
        state=state,
        reserve_state=reserve_state,
        reserve_unit=reserve_unit,
        target_pose=target_pose,
        result_id="phase17g-warp-rifts-nonmatching-anchor",
    )

    assert status.status_kind is LifecycleStatusKind.INVALID
    violations = cast(list[dict[str, JsonValue]], status.payload["violations"])
    assert ReservePlacementViolationCode.RESERVE_ENEMY_DISTANCE.value in {
        cast(str, violation["violation_code"]) for violation in violations
    }
    remaining_state = state.reserve_state_for_unit(reserve_state.unit_instance_id)
    assert remaining_state is not None
    assert remaining_state.status is ReserveStatus.IN_RESERVES


def test_warp_rifts_does_not_reduce_strategic_reserves_enemy_distance() -> None:
    state, reserve_state, reserve_unit = _daemonic_incursion_reserve_state(
        reserve_kind=ReserveKind.STRATEGIC_RESERVES
    )
    target_pose = south_edge_touching_pose(base_diameter_mm=_RESERVE_BASE_DIAMETER_MM, x=16.0)
    _place_enemy_at_base_distance(state=state, target_pose=target_pose, distance_inches=7.0)

    status = _submit_reserve_arrival(
        state=state,
        reserve_state=reserve_state,
        reserve_unit=reserve_unit,
        target_pose=target_pose,
        placement_kind=BattlefieldPlacementKind.STRATEGIC_RESERVES,
        battle_round=3,
        result_id="phase17g-warp-rifts-strategic-reserves",
    )

    assert status.status_kind is LifecycleStatusKind.INVALID
    violations = cast(list[dict[str, JsonValue]], status.payload["violations"])
    assert ReservePlacementViolationCode.RESERVE_ENEMY_DISTANCE.value in {
        cast(str, violation["violation_code"]) for violation in violations
    }
    remaining_state = state.reserve_state_for_unit(reserve_state.unit_instance_id)
    assert remaining_state is not None
    assert remaining_state.status is ReserveStatus.IN_RESERVES


def test_warp_rifts_requires_attempted_placement_to_match_reserve_unit() -> None:
    state, reserve_state, reserve_unit = _daemonic_incursion_reserve_state()
    target_pose = Pose.at(x=16.0, y=4.25, z=0.0, facing_degrees=0.0)
    anchor_unit = _unit_by_id(state, _ANCHOR_UNIT_ID)
    drifted_placement = UnitPlacement(
        army_id="army-alpha",
        player_id="player-a",
        unit_instance_id=anchor_unit.unit_instance_id,
        model_placements=(
            ModelPlacement(
                army_id="army-alpha",
                player_id="player-a",
                unit_instance_id=anchor_unit.unit_instance_id,
                model_instance_id=anchor_unit.own_models[0].model_instance_id,
                pose=target_pose,
            ),
        ),
    )

    with pytest.raises(GameLifecycleError, match="rules-unit identity drift"):
        _reserve_arrival_distance_context(
            state=state,
            reserve_state=reserve_state,
            reserve_unit=reserve_unit,
            attempted_placement=drifted_placement,
            placement_kind=BattlefieldPlacementKind.DEEP_STRIKE,
        )


def test_warp_rifts_requires_legiones_daemonica() -> None:
    state, reserve_state, reserve_unit = _daemonic_incursion_reserve_state()
    reserve_unit = replace(reserve_unit, faction_keywords=())
    state.army_definitions = [
        replace(
            army,
            units=tuple(
                reserve_unit if unit.unit_instance_id == reserve_unit.unit_instance_id else unit
                for unit in army.units
            ),
        )
        if army.player_id == reserve_state.player_id
        else army
        for army in state.army_definitions
    ]
    target_pose = Pose.at(x=16.0, y=4.25, z=0.0, facing_degrees=0.0)

    grants = _runtime_reserve_arrival_registry(state).grants_for(
        _reserve_arrival_distance_context(
            state=state,
            reserve_state=reserve_state,
            reserve_unit=reserve_unit,
            attempted_placement=single_model_reserve_placement(
                reserve_unit=reserve_unit,
                pose=target_pose,
            ),
            placement_kind=BattlefieldPlacementKind.DEEP_STRIKE,
        )
    )

    assert grants == ()


def test_warp_rifts_requires_greater_daemon_shadow_aura_source_anchor() -> None:
    state, reserve_state, reserve_unit = _daemonic_incursion_reserve_state()
    _replace_unit_datasheet_abilities(
        state,
        unit_instance_id=_ANCHOR_UNIT_ID,
        datasheet_abilities=(),
    )
    target_pose = Pose.at(x=30.0, y=22.0, z=0.0, facing_degrees=0.0)
    _place_anchor_at_base_distance(
        state=state,
        target_pose=target_pose,
        distance_inches=4.0,
    )

    grants = _runtime_reserve_arrival_registry(state).grants_for(
        _reserve_arrival_distance_context(
            state=state,
            reserve_state=reserve_state,
            reserve_unit=reserve_unit,
            attempted_placement=single_model_reserve_placement(
                reserve_unit=reserve_unit,
                pose=target_pose,
            ),
            placement_kind=BattlefieldPlacementKind.DEEP_STRIKE,
        )
    )

    assert grants == ()


def test_warp_rifts_requires_every_arriving_model_within_anchor_range() -> None:
    state, _scenario, reserve_state, _reserve_unit = battle_state_with_reserve(
        reserve_base_diameter_mm=_RESERVE_BASE_DIAMETER_MM,
        reserve_model_count=2,
    )
    state.army_definitions = list(
        _with_daemonic_incursion_units(
            tuple(state.army_definitions),
            reserve_god_keyword="Khorne",
            anchor_god_keyword="Khorne",
        )
    )
    updated_reserve_state = replace(reserve_state, reserve_kind=ReserveKind.DEEP_STRIKE)
    state.replace_reserve_state(updated_reserve_state)
    reserve_unit = _unit_by_id(state, _RESERVE_UNIT_ID)
    near_pose = Pose.at(x=30.0, y=22.0, z=0.0, facing_degrees=0.0)
    far_pose = Pose.at(x=42.0, y=22.0, z=0.0, facing_degrees=0.0)
    _place_anchor_at_base_distance(
        state=state,
        target_pose=near_pose,
        distance_inches=4.0,
    )

    grants = _runtime_reserve_arrival_registry(state).grants_for(
        _reserve_arrival_distance_context(
            state=state,
            reserve_state=updated_reserve_state,
            reserve_unit=reserve_unit,
            attempted_placement=reserve_placement(
                reserve_unit=reserve_unit,
                poses=(near_pose, far_pose),
            ),
            placement_kind=BattlefieldPlacementKind.DEEP_STRIKE,
        )
    )

    assert grants == ()


def test_warp_rifts_replay_payload_preserves_generic_rule_ir_source_context() -> None:
    state, reserve_state, reserve_unit = _daemonic_incursion_reserve_state()
    target_pose = Pose.at(x=16.0, y=4.25, z=0.0, facing_degrees=0.0)

    grants = _runtime_reserve_arrival_registry(state).grants_for(
        _reserve_arrival_distance_context(
            state=state,
            reserve_state=reserve_state,
            reserve_unit=reserve_unit,
            attempted_placement=single_model_reserve_placement(
                reserve_unit=reserve_unit,
                pose=target_pose,
            ),
            placement_kind=BattlefieldPlacementKind.DEEP_STRIKE,
        )
    )

    assert len(grants) == 1
    payload = grants[0].replay_payload
    assert isinstance(payload, dict)
    assert payload["source_rule_id"] == rule.SOURCE_RULE_ID
    assert payload["rule_ir_hash"] == _daemonic_incursion_execution_record().rule_ir_hash
    assert payload["placement_kind"] == BattlefieldPlacementKind.DEEP_STRIKE.value
    assert payload["base_enemy_horizontal_distance_inches"] == 9.0
    assert payload["enemy_horizontal_distance_inches"] == 6.0
    assert payload["shadow_of_chaos"] is True
    assert payload["greater_daemon_anchor"] is False
    assert payload["shared_god_keywords"] == ["KHORNE"]


def test_denizens_of_the_warp_effect_allows_deep_strike_more_than_six_from_enemy() -> None:
    state, reserve_state, reserve_unit = _daemonic_incursion_reserve_state()
    _set_movement_ready_for_reinforcements(state, battle_round=1)
    target_pose = Pose.at(x=30.0, y=22.0, z=0.0, facing_degrees=0.0)
    _place_enemy_at_base_distance(state=state, target_pose=target_pose, distance_inches=7.0)
    context = _reserve_arrival_distance_context(
        state=state,
        reserve_state=reserve_state,
        reserve_unit=reserve_unit,
        attempted_placement=single_model_reserve_placement(
            reserve_unit=reserve_unit,
            pose=target_pose,
        ),
        placement_kind=BattlefieldPlacementKind.DEEP_STRIKE,
    )

    assert _runtime_reserve_arrival_registry(state).grants_for(context) == ()

    state.record_persisting_effect(
        _denizens_of_the_warp_effect(
            state=state,
            unit_instance_id=reserve_state.unit_instance_id,
        )
    )
    grants = _runtime_reserve_arrival_registry(state).grants_for(context)

    assert len(grants) == 1
    grant = grants[0]
    assert grant.hook_id == daemonic_incursion_ir.DENIZENS_OF_THE_WARP_HOOK_ID
    assert grant.source_id == daemonic_incursion_ir.DENIZENS_OF_THE_WARP_SOURCE_RULE_ID
    assert grant.enemy_horizontal_distance_inches == 6.0
    payload = grant.replay_payload
    assert isinstance(payload, dict)
    assert payload["effect_kind"] == "denizens_of_the_warp"
    assert payload["persisting_effect_ids"] == [
        f"phase17g-denizens:{reserve_state.unit_instance_id}"
    ]


def test_daemonic_invulnerability_exposes_target_save_reroll_permission() -> None:
    state, reserve_state, _reserve_unit = _daemonic_incursion_reserve_state()
    state.record_persisting_effect(
        _generic_stratagem_persisting_effect(
            descriptor_id=daemonic_incursion_ir.DAEMONIC_INVULNERABILITY_DESCRIPTOR_ID,
            source_rule_id=daemonic_incursion_ir.DAEMONIC_INVULNERABILITY_SOURCE_RULE_ID,
            effect_kind="reroll_permission",
            effect_id=f"phase17g-invulnerability:{reserve_state.unit_instance_id}",
            target_unit_instance_id=reserve_state.unit_instance_id,
        )
    )

    context = source_backed_reroll_permission_context_for_unit(
        state=state,
        player_id="player-a",
        unit_instance_id=_ANCHOR_UNIT_ID,
        roll_type="attack_sequence.save.invulnerable",
        timing_window="attack_sequence.save.invulnerable",
        target_unit_instance_id=reserve_state.unit_instance_id,
    )

    assert context is not None
    assert context.permission.owning_player_id == "player-a"
    assert context.permission.eligible_roll_type == "attack_sequence.save.invulnerable"
    assert context.source_payload["conditional_save_reroll"] == {
        "reroll_unmodified_values": [1],
    }


def _daemonic_stratagem_definition(stratagem_id: str) -> StratagemDefinition:
    matches = tuple(
        record.definition
        for record in daemonic_stratagems.runtime_contribution().stratagem_records
        if record.definition.stratagem_id == stratagem_id
    )
    if len(matches) != 1:
        raise AssertionError("test requires exactly one Daemonic Incursion Stratagem definition")
    return matches[0]


def _daemonic_stratagem_definition_for_phase(
    stratagem_id: str,
    *,
    phase: BattlePhase,
) -> StratagemDefinition:
    matches = tuple(
        record.definition
        for record in daemonic_stratagems.runtime_contribution().stratagem_records
        if record.definition.stratagem_id == stratagem_id
        and record.definition.timing.phase is phase
    )
    if len(matches) != 1:
        raise AssertionError("test requires exactly one phase-specific Daemonic stratagem")
    return matches[0]


def _daemonic_stratagem_definition_by_effect_selection_kind(
    stratagem_id: str,
    *,
    effect_selection_kind: str | None,
) -> StratagemDefinition:
    matches: list[StratagemDefinition] = []
    for record in daemonic_stratagems.runtime_contribution().stratagem_records:
        definition = record.definition
        if definition.stratagem_id != stratagem_id:
            continue
        payload = definition.effect_payload
        if not isinstance(payload, dict):
            continue
        if payload.get("effect_selection_kind") == effect_selection_kind:
            matches.append(definition)
    if len(matches) != 1:
        raise AssertionError("test requires exactly one effect-selection Daemonic stratagem")
    return matches[0]


def _daemonic_stratagem_context(
    *,
    state: GameState,
    phase: BattlePhase,
    trigger_kind: TimingTriggerKind,
) -> StratagemEligibilityContext:
    return StratagemEligibilityContext(
        game_id=state.game_id,
        player_id="player-a",
        battle_round=state.battle_round,
        phase=phase,
        active_player_id="player-a",
        trigger_kind=trigger_kind,
        timing_window_id=f"phase17g-daemonic-incursion:{phase.value}:window",
    )


def _daemonic_stratagem_use_record(
    *,
    definition: StratagemDefinition,
    target_unit_id: str,
    phase: BattlePhase,
    effect_selection: JsonValue = None,
) -> StratagemUseRecord:
    target_binding = _friendly_daemon_target_binding(target_unit_id)
    return StratagemUseRecord(
        use_id=f"phase17g-daemonic-incursion:{definition.stratagem_id}:use",
        player_id="player-a",
        stratagem_id=definition.stratagem_id,
        source_id=definition.source_id,
        battle_round=1,
        phase=phase,
        active_player_id="player-a",
        timing_window_id=f"phase17g-daemonic-incursion:{definition.stratagem_id}:window",
        request_id=f"phase17g-daemonic-incursion:{definition.stratagem_id}:request",
        result_id=f"phase17g-daemonic-incursion:{definition.stratagem_id}:result",
        selected_option_id=f"phase17g-daemonic-incursion:{definition.stratagem_id}:option",
        target_binding=target_binding,
        targeted_unit_instance_ids=(target_unit_id,),
        affected_unit_instance_ids=(target_unit_id,),
        command_point_cost=1,
        command_point_transaction_id=None,
        handler_id=definition.handler_id,
        effect_selection=effect_selection,
        effect_payload=definition.effect_payload,
    )


def _friendly_daemon_target_binding(unit_instance_id: str) -> StratagemTargetBinding:
    return StratagemTargetBinding(
        target_kind=StratagemTargetKind.FRIENDLY_UNIT,
        target_player_id="player-a",
        target_unit_instance_id=unit_instance_id,
    )


def _apply_daemonic_stratagem(
    *,
    state: GameState,
    decisions: DecisionController,
    definition: StratagemDefinition,
    use_record: StratagemUseRecord,
    context: StratagemEligibilityContext,
) -> None:
    records = tuple(
        record
        for contribution in (
            daemonic_stratagems.runtime_contribution(),
            july_updates.runtime_contribution(),
        )
        for record in contribution.stratagem_records
        if record.definition == definition
    )
    if len(records) != 1:
        raise AssertionError("test requires one exact Stratagem catalog record")
    option = _stratagem_decision_option(
        context=context,
        record=records[0],
        target_binding=use_record.target_binding,
        effect_selection=use_record.effect_selection,
    )
    request = create_stratagem_use_decision_request(
        state=state,
        context=context,
        options=(option,),
        request_id=use_record.request_id,
    )
    result = DecisionResult.for_request(
        result_id=use_record.result_id,
        request=request,
        selected_option_id=option.option_id,
    )
    decisions.request_decision(request)
    decisions.submit_result(result)
    targeted_ids, affected_ids = derive_stratagem_use_unit_ids(
        state=state,
        definition=definition,
        context=context,
        target_binding=use_record.target_binding,
        effect_selection=use_record.effect_selection,
    )
    use_record = replace(
        use_record,
        battle_round=context.battle_round,
        phase=context.phase,
        active_player_id=context.active_player_id,
        timing_window_id=context.timing_window_id,
        selected_option_id=option.option_id,
        targeted_unit_instance_ids=targeted_ids,
        affected_unit_instance_ids=affected_ids,
    )
    state.battle_phase_index = state.battle_phase_sequence.index(context.phase)
    state.record_stratagem_use(use_record)
    decisions.event_log.append("stratagem_used", use_record.to_payload())
    stratagems_generic_rule_ir._apply_generic_rule_ir_stratagem_handler(
        state=state,
        decisions=decisions,
        context=context,
        target_binding=use_record.target_binding,
        definition=definition,
        use_record=use_record,
        ruleset_descriptor=_ruleset(),
        army_catalog=_daemonic_incursion_catalog(),
        shooting_unit_selected_grant_hooks=None,
    )


def _persisting_effect_by_kind(
    state: GameState,
    *,
    unit_instance_id: str,
    effect_kind: str,
) -> PersistingEffect:
    for effect in state.persisting_effects_for_unit(unit_instance_id):
        payload = effect.effect_payload
        if isinstance(payload, dict) and payload.get("effect_kind") == effect_kind:
            return effect
    raise AssertionError(f"effect not found: {effect_kind}")


def _daemonic_invulnerability_permission_context(
    source_payload: dict[str, JsonValue],
) -> SourceBackedRerollPermissionContext:
    return SourceBackedRerollPermissionContext(
        permission=RerollPermission(
            source_id=daemonic_incursion_ir.DAEMONIC_INVULNERABILITY_SOURCE_RULE_ID,
            timing_window="attack_sequence.save.invulnerable",
            owning_player_id="player-a",
            eligible_roll_type="attack_sequence.save.invulnerable",
            component_selection_policy=RerollComponentSelectionPolicy.WHOLE_ROLL,
        ),
        source_payload=source_payload,
    )


def _daemonic_wound_permission_context(
    source_payload: dict[str, JsonValue],
) -> SourceBackedRerollPermissionContext:
    return SourceBackedRerollPermissionContext(
        permission=RerollPermission(
            source_id=daemonic_incursion_ir.DRAUGHT_OF_TERROR_SOURCE_RULE_ID,
            timing_window="attack_sequence.wound",
            owning_player_id="player-a",
            eligible_roll_type="attack_sequence.wound",
            component_selection_policy=RerollComponentSelectionPolicy.WHOLE_ROLL,
        ),
        source_payload=source_payload,
    )


def _save_roll_state(*, value: int) -> DiceRollState:
    return DiceRollManager("phase17g-daemonic-invulnerability-save").roll_fixed(
        DiceRollSpec(
            expression=DiceExpression(quantity=1, sides=6),
            reason="phase17g daemonic invulnerability save",
            roll_type="attack_sequence.save.invulnerable",
            actor_id="player-a",
        ),
        [value],
    )


def _wound_roll_state(*, value: int) -> DiceRollState:
    return DiceRollManager("phase17g-draught-of-terror-wound").roll_fixed(
        DiceRollSpec(
            expression=DiceExpression(quantity=1, sides=6),
            reason="phase17g draught of terror wound",
            roll_type="attack_sequence.wound",
            actor_id="player-a",
        ),
        [value],
    )


def _weapon_profile(*, melee: bool = False) -> WeaponProfile:
    return WeaponProfile(
        profile_id=(
            "phase17g-daemonic-incursion-melee-profile"
            if melee
            else "phase17g-daemonic-incursion-ranged-profile"
        ),
        name="Daemonic Incursion melee weapon" if melee else "Daemonic Incursion ranged weapon",
        range_profile=RangeProfile.melee() if melee else RangeProfile.distance(24),
        attack_profile=AttackProfile.fixed(1),
        skill=CharacteristicValue.from_raw(
            Characteristic.WEAPON_SKILL if melee else Characteristic.BALLISTIC_SKILL,
            3,
        ),
        strength=CharacteristicValue.from_raw(Characteristic.STRENGTH, 4),
        armor_penetration=CharacteristicValue.from_raw(Characteristic.ARMOR_PENETRATION, 0),
        damage_profile=DamageProfile.fixed(1),
        source_ids=("phase17g-daemonic-incursion-test-profile",),
    )


def _runtime_activation(
    *,
    selected_detachment_ids: tuple[str, ...],
) -> RuntimeContentActivation:
    return RuntimeContentActivation(
        selected_faction_ids=(rule.CHAOS_DAEMONS_FACTION_ID,),
        selected_detachment_ids=selected_detachment_ids,
        selected_enhancement_ids=(),
        selected_stratagem_ids=(),
        selected_datasheet_ids=(),
        selected_wargear_ids=(),
        selected_weapon_profile_ids=(),
        selected_weapon_keywords=(),
        loaded_unit_instance_ids=(),
    )


def _config_backed_realm_of_chaos_lifecycle(
    *,
    prior_declared_arrival: bool = False,
) -> GameLifecycle:
    config = _daemonic_incursion_config(game_id="phase17g-daemonic-incursion-realm-authority")
    armies = tuple(
        muster_army(catalog=config.army_catalog, request=request)
        for request in config.army_muster_requests
    )
    state = GameState.from_config(config)
    for army in armies:
        state.record_army_definition(army)
    scenario = create_deterministic_battlefield_scenario(
        battlefield_id="phase17g-daemonic-incursion-realm-authority-battlefield",
        armies=armies,
    )
    state.record_battlefield_state(scenario.battlefield_state)
    decisions = DecisionController()
    enter_battle_for_fixture(state, decisions=decisions)
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.MOVEMENT)
    state.active_player_id = "player-a"
    runtime_bundle = build_runtime_content_bundle_for_armies(
        config=config,
        armies=armies,
    )
    realm_records = tuple(
        record
        for record in runtime_bundle.stratagem_indexes_by_player_id["player-a"].all_records()
        if record.definition.stratagem_id == daemonic_incursion_ir.THE_REALM_OF_CHAOS_STRATAGEM_ID
        and record.definition.source_id == daemonic_incursion_ir.THE_REALM_OF_CHAOS_SOURCE_RULE_ID
        and isinstance(record.definition.effect_payload, dict)
        and record.definition.effect_payload.get("effect_selection_kind") is None
    )
    if len(realm_records) != 1:
        raise AssertionError("test requires one active Realm of Chaos single-target record")
    definition = realm_records[0].definition
    target_unit_id = armies[0].units[0].unit_instance_id
    lifecycle = GameLifecycle(
        state=state,
        decision_controller=decisions,
        _config=config,
        _runtime_content_bundle=runtime_bundle,
    )
    if prior_declared_arrival:
        if state.battlefield_state is None:
            raise AssertionError("test requires a battlefield state")
        state.replace_battlefield_state(
            state.battlefield_state.without_unit_placement(target_unit_id)
        )
        declared_state = ReserveState.declared_before_battle(
            player_id="player-a",
            unit_instance_id=target_unit_id,
            reserve_kind=ReserveKind.STRATEGIC_RESERVES,
            destruction_deadline_policy=(
                reserve_arrival_requirements.reposition_destruction_policy(
                    mission_setup=state.mission_setup,
                    destruction_deadline_policy=None,
                )
            ),
        )
        state.record_reserve_state(declared_state)
        decisions.event_log.append(
            "reserve_unit_declared",
            {
                "game_id": state.game_id,
                "player_id": "player-a",
                "unit_instance_id": target_unit_id,
                "reserve_state": declared_state.to_payload(),
            },
        )
        _arrive_realm_target_from_reserves(
            lifecycle=lifecycle,
            battle_round=2,
            result_id_prefix="phase17n-realm-prior-declared-arrival",
        )
        state.movement_phase_state = None
    context = _daemonic_stratagem_context(
        state=state,
        phase=BattlePhase.MOVEMENT,
        trigger_kind=TimingTriggerKind.END_TURN,
    )
    _apply_daemonic_stratagem(
        state=state,
        decisions=decisions,
        definition=definition,
        use_record=_daemonic_stratagem_use_record(
            definition=definition,
            target_unit_id=target_unit_id,
            phase=BattlePhase.MOVEMENT,
        ),
        context=context,
    )
    return GameLifecycle.from_payload(lifecycle.to_payload())


def _arrive_realm_target_from_reserves(
    *,
    lifecycle: GameLifecycle,
    battle_round: int,
    result_id_prefix: str,
    invalid_first: bool = False,
) -> None:
    state = lifecycle.state
    if state is None:
        raise AssertionError("test lifecycle requires state")
    reserve_state = state.reserve_states[0]
    reserve_unit = state.army_definitions[0].unit_by_id(reserve_state.unit_instance_id)
    state.battle_round = battle_round
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.MOVEMENT)
    state.active_player_id = "player-a"
    state.movement_phase_state = MovementPhaseState(
        battle_round=battle_round,
        active_player_id="player-a",
        selected_unit_ids=(),
        moved_unit_ids=(),
    )
    handler = MovementPhaseHandler(
        ruleset_descriptor=_ruleset(),
        reserve_arrival_distance_hooks=_runtime_reserve_arrival_registry(state),
    )
    decisions = lifecycle.decision_controller
    selection_request = decision_request(handler.begin_phase(state=state, decisions=decisions))
    placement_request = decision_request(
        submit_handler_decision(
            handler=handler,
            state=state,
            decisions=decisions,
            request=selection_request,
            option_id=reserve_state.unit_instance_id,
            result_id=f"{result_id_prefix}-select",
        )
    )
    placement_kind = (
        BattlefieldPlacementKind.DEEP_STRIKE
        if reserve_state.required_arrival_placement_kind
        == BattlefieldPlacementKind.DEEP_STRIKE.value
        else BattlefieldPlacementKind.STRATEGIC_RESERVES
    )
    if invalid_first:
        invalid_status = submit_reserve_placement_payload(
            handler=handler,
            state=state,
            decisions=decisions,
            request=placement_request,
            reserve_unit=reserve_unit,
            placement_kind=placement_kind,
            attempted_placement=reserve_placement(
                reserve_unit=reserve_unit,
                poses=tuple(
                    Pose.at(
                        x=10.0 + 2.0 * index,
                        y=-10.0,
                        z=0.0,
                        facing_degrees=0.0,
                    )
                    for index in range(len(reserve_unit.own_models))
                ),
            ),
            result_id=f"{result_id_prefix}-invalid",
        )
        if invalid_status is None or invalid_status.status_kind is not LifecycleStatusKind.INVALID:
            raise AssertionError("test requires one rejected reserve placement")
        placement_request = decisions.queue.peek_next()
        if placement_request.decision_type != PLACEMENT_PROPOSAL_DECISION_TYPE:
            raise AssertionError("test requires one retry placement request")
    completion_status = submit_reserve_placement_payload(
        handler=handler,
        state=state,
        decisions=decisions,
        request=placement_request,
        reserve_unit=reserve_unit,
        placement_kind=placement_kind,
        attempted_placement=reserve_placement(
            reserve_unit=reserve_unit,
            poses=tuple(
                Pose.at(
                    x=10.0 + 2.0 * index,
                    y=(
                        30.0
                        if placement_kind is BattlefieldPlacementKind.DEEP_STRIKE
                        else base_radius_inches(_RESERVE_BASE_DIAMETER_MM)
                    ),
                    z=0.0,
                    facing_degrees=0.0,
                )
                for index in range(len(reserve_unit.own_models))
            ),
        ),
        result_id=f"{result_id_prefix}-place",
    )
    if completion_status is not None and completion_status.decision_request is not None:
        completion_request = decision_request(completion_status)
        submit_handler_decision(
            handler=handler,
            state=state,
            decisions=decisions,
            request=completion_request,
            option_id=COMPLETE_REINFORCEMENTS_OPTION_ID,
            result_id=f"{result_id_prefix}-complete",
        )


def _active_ingress_record(
    lifecycle: GameLifecycle,
    *,
    stratagem_id: str,
) -> StratagemCatalogRecord:
    if stratagem_id == "rapid-ingress":
        indexes = (eleventh_edition_core_stratagem_index(),)
    else:
        indexes = (
            lifecycle._require_runtime_content_bundle().stratagem_indexes_by_player_id["player-a"],
        )
    records = tuple(
        record
        for index in indexes
        for record in index.all_records()
        if record.definition.stratagem_id == stratagem_id
    )
    if len(records) != 1:
        all_ids = tuple(
            record.definition.stratagem_id for index in indexes for record in index.all_records()
        )
        raise AssertionError(f"test requires one active ingress Stratagem record: {all_ids}")
    return records[0]


def _submit_config_backed_ingress(
    *,
    lifecycle: GameLifecycle,
    record: StratagemCatalogRecord,
    active_player_id: str,
    placement_kind: BattlefieldPlacementKind,
    result_id_prefix: str,
    invalid_first: bool = False,
) -> None:
    state = lifecycle.state
    if state is None:
        raise AssertionError("test lifecycle requires state")
    reserve_state = state.reserve_states[0]
    reserve_unit = state.army_definitions[0].unit_by_id(reserve_state.unit_instance_id)
    state.active_player_id = active_player_id
    state.battle_round = 3
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.MOVEMENT)
    state.movement_phase_state = MovementPhaseState(
        battle_round=3,
        active_player_id=active_player_id,
    )
    state.gain_command_points(
        player_id="player-a",
        amount=1,
        source_id=f"{result_id_prefix}:command-point",
        source_kind=CommandPointSourceKind.OTHER,
        cap_exempt=True,
    )
    context = StratagemEligibilityContext(
        game_id=state.game_id,
        player_id="player-a",
        battle_round=state.battle_round,
        phase=BattlePhase.MOVEMENT,
        active_player_id=active_player_id,
        trigger_kind=TimingTriggerKind.END_PHASE,
        timing_window_id=f"{result_id_prefix}:end-movement",
    )
    proposal = StratagemTargetProposal.for_request(
        context=context,
        catalog_record=record,
    )
    waiting = request_stratagem_target_proposal(
        state=state,
        decisions=lifecycle.decision_controller,
        proposal_request=proposal,
    )
    target_request = decision_request(waiting)
    placement_status = lifecycle.submit_decision(
        DecisionResult(
            result_id=f"{result_id_prefix}:target",
            request_id=target_request.request_id,
            decision_type=target_request.decision_type,
            actor_id=target_request.actor_id,
            selected_option_id=PARAMETERIZED_DECISION_OPTION_ID,
            payload=validate_json_value(
                {
                    "proposal": proposal.with_binding(
                        _friendly_daemon_target_binding(reserve_state.unit_instance_id)
                    ).to_payload()
                }
            ),
        )
    )
    placement_request = decision_request(placement_status)
    movement_request = MovementProposalRequest.from_decision_request_payload(
        placement_request.payload
    )
    if invalid_first:
        invalid_status = lifecycle.submit_decision(
            DecisionResult(
                result_id=f"{result_id_prefix}:invalid",
                request_id=placement_request.request_id,
                decision_type=PLACEMENT_PROPOSAL_DECISION_TYPE,
                actor_id=placement_request.actor_id,
                selected_option_id=PARAMETERIZED_DECISION_OPTION_ID,
                payload=validate_json_value(
                    PlacementProposalPayload(
                        proposal_request_id=movement_request.request_id,
                        proposal_kind=movement_request.proposal_kind,
                        unit_instance_id=reserve_state.unit_instance_id,
                        placement_kind=placement_kind,
                        attempted_placement=reserve_placement(
                            reserve_unit=reserve_unit,
                            poses=tuple(
                                Pose.at(
                                    x=10.0 + 2.0 * index,
                                    y=-10.0,
                                    z=0.0,
                                    facing_degrees=0.0,
                                )
                                for index in range(len(reserve_unit.own_models))
                            ),
                        ),
                    ).to_payload()
                ),
            )
        )
        if invalid_status.status_kind is not LifecycleStatusKind.INVALID:
            raise AssertionError("test ingress requires one rejected placement")
        placement_request = lifecycle.decision_controller.queue.peek_next()
        movement_request = MovementProposalRequest.from_decision_request_payload(
            placement_request.payload
        )
    y_inches = (
        30.0
        if placement_kind is BattlefieldPlacementKind.RETURN_TO_BATTLEFIELD
        else base_radius_inches(_RESERVE_BASE_DIAMETER_MM)
    )
    attempted_placement = reserve_placement(
        reserve_unit=reserve_unit,
        poses=tuple(
            Pose.at(x=10.0 + 2.0 * index, y=y_inches, z=0.0, facing_degrees=0.0)
            for index in range(len(reserve_unit.own_models))
        ),
    )
    final_status = lifecycle.submit_decision(
        DecisionResult(
            result_id=f"{result_id_prefix}:placement",
            request_id=placement_request.request_id,
            decision_type=PLACEMENT_PROPOSAL_DECISION_TYPE,
            actor_id=placement_request.actor_id,
            selected_option_id=PARAMETERIZED_DECISION_OPTION_ID,
            payload=validate_json_value(
                PlacementProposalPayload(
                    proposal_request_id=movement_request.request_id,
                    proposal_kind=movement_request.proposal_kind,
                    unit_instance_id=reserve_state.unit_instance_id,
                    placement_kind=placement_kind,
                    attempted_placement=attempted_placement,
                ).to_payload()
            ),
        )
    )
    if final_status.status_kind is LifecycleStatusKind.INVALID:
        raise AssertionError(f"test ingress placement must be valid: {final_status.payload}")
    ingress_events = tuple(
        event
        for event in lifecycle.decision_controller.event_log.records
        if event.event_type in {"reinforcement_unit_arrived", "rapid_ingress_resolved"}
        and isinstance(event.payload, dict)
        and event.payload.get("result_id") == f"{result_id_prefix}:placement"
    )
    if len(ingress_events) != 2:
        raise AssertionError("test ingress must emit one arrival and one terminal event")


def _decision_record_payload_for_result(
    payload: GameLifecyclePayload,
    *,
    result_id: str,
) -> DecisionRecordPayload:
    matches = tuple(
        decision
        for decision in payload["decisions"]["records"]
        if decision["result"]["result_id"] == result_id
    )
    if len(matches) != 1:
        raise AssertionError("test requires one accepted placement decision")
    return matches[0]


def _arrival_event_payload_for_result(
    payload: GameLifecyclePayload,
    *,
    result_id: str,
) -> dict[str, JsonValue]:
    matches = tuple(
        event_payload
        for event in payload["decisions"]["event_log"]
        if event["event_type"] == "reinforcement_unit_arrived"
        and isinstance((event_payload := event["payload"]), dict)
        and event_payload.get("result_id") == result_id
    )
    if len(matches) != 1:
        raise AssertionError("test requires one reinforcement arrival event")
    return matches[0]


def _event_record_for_type(
    payload: GameLifecyclePayload,
    *,
    event_type: str,
) -> EventRecordPayload:
    matches = tuple(
        event for event in payload["decisions"]["event_log"] if event["event_type"] == event_type
    )
    if len(matches) != 1:
        raise AssertionError(f"test requires one {event_type} event")
    return matches[0]


def _event_record_for_request_id(
    payload: GameLifecyclePayload,
    *,
    event_type: str,
    request_id: str,
) -> EventRecordPayload:
    matches = tuple(
        event
        for event in payload["decisions"]["event_log"]
        if event["event_type"] == event_type
        and isinstance(event["payload"], dict)
        and event["payload"].get("request_id") == request_id
    )
    if len(matches) != 1:
        raise AssertionError(f"test requires one {event_type} event for {request_id}")
    return matches[0]


def _event_record_for_result_id(
    payload: GameLifecyclePayload,
    *,
    event_type: str,
    result_id: str,
) -> EventRecordPayload:
    matches: list[EventRecordPayload] = []
    for event in payload["decisions"]["event_log"]:
        if event["event_type"] != event_type or not isinstance(event["payload"], dict):
            continue
        event_payload = event["payload"]
        recorded_result = event_payload.get("result")
        if event_payload.get("result_id") == result_id or (
            isinstance(recorded_result, dict) and recorded_result.get("result_id") == result_id
        ):
            matches.append(event)
    if len(matches) != 1:
        raise AssertionError(f"test requires one {event_type} event for {result_id}")
    return matches[0]


def _swap_event_contents(first: EventRecordPayload, second: EventRecordPayload) -> None:
    first["event_type"], second["event_type"] = second["event_type"], first["event_type"]
    first["payload"], second["payload"] = second["payload"], first["payload"]


def _placement_proposal_request_payload_for_test(
    decision: DecisionRecordPayload,
) -> dict[str, JsonValue]:
    request_wrapper = _json_object_for_test(decision["request"]["payload"])
    return _json_object_for_test(request_wrapper["proposal_request"])


def _placement_proposal_requested_payload_for_test(
    payload: GameLifecyclePayload,
    *,
    request_id: str,
) -> dict[str, JsonValue]:
    matches = tuple(
        event_payload
        for event in payload["decisions"]["event_log"]
        if event["event_type"] == "placement_proposal_requested"
        and isinstance((event_payload := event["payload"]), dict)
        and event_payload.get("request_id") == request_id
    )
    if len(matches) != 1:
        raise AssertionError("test requires one placement proposal requested event")
    return matches[0]


def _sync_decision_requested_event(
    payload: GameLifecyclePayload,
    *,
    decision: DecisionRecordPayload,
) -> None:
    request_id = decision["request"]["request_id"]
    matches = tuple(
        event
        for event in payload["decisions"]["event_log"]
        if event["event_type"] == "decision_requested"
        and isinstance(event["payload"], dict)
        and event["payload"].get("request_id") == request_id
    )
    if len(matches) != 1:
        raise AssertionError("test requires one requested placement decision event")
    matches[0]["payload"] = validate_json_value(deepcopy(decision["request"]))


def _sync_decision_recorded_event(
    payload: GameLifecyclePayload,
    *,
    decision: DecisionRecordPayload,
) -> None:
    result_id = decision["result"]["result_id"]
    matches: list[EventRecordPayload] = []
    for event in payload["decisions"]["event_log"]:
        event_payload = event["payload"]
        if event["event_type"] != "decision_recorded" or not isinstance(event_payload, dict):
            continue
        recorded_result = event_payload.get("result")
        if isinstance(recorded_result, dict) and recorded_result.get("result_id") == result_id:
            matches.append(event)
    if len(matches) != 1:
        raise AssertionError("test requires one recorded placement decision event")
    matches[0]["payload"] = validate_json_value(deepcopy(decision))


def _json_object_for_test(value: JsonValue) -> dict[str, JsonValue]:
    if not isinstance(value, dict):
        pytest.fail("test payload must be an object")
    return value


def _json_object_list_for_test(value: JsonValue) -> list[dict[str, JsonValue]]:
    if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
        raise AssertionError("test payload must be a list of objects")
    return cast(list[dict[str, JsonValue]], value)


def _rewrite_realm_of_chaos_catalog_disabled(payload: GameLifecyclePayload) -> None:
    records = payload["decisions"]["records"]
    if len(records) != 1:
        raise AssertionError("test requires one accepted Realm of Chaos decision")
    decision = records[0]
    selected_option_id = decision["result"]["selected_option_id"]
    selected_options = tuple(
        option
        for option in decision["request"]["options"]
        if option["option_id"] == selected_option_id
    )
    if len(selected_options) != 1:
        raise AssertionError("test requires one selected Realm of Chaos option")
    option_payload = selected_options[0]["payload"]
    result_payload = decision["result"]["payload"]
    assert isinstance(option_payload, dict)
    assert isinstance(result_payload, dict)
    option_record = option_payload.get("catalog_record")
    result_record = result_payload.get("catalog_record")
    assert isinstance(option_record, dict)
    assert isinstance(result_record, dict)
    option_record["disabled"] = True
    result_record["disabled"] = True
    request_id = decision["request"]["request_id"]
    result_id = decision["result"]["result_id"]
    for event in payload["decisions"]["event_log"]:
        event_payload = event["payload"]
        if event["event_type"] == "decision_requested" and isinstance(event_payload, dict):
            if event_payload.get("request_id") == request_id:
                event["payload"] = validate_json_value(deepcopy(decision["request"]))
        elif event["event_type"] == "decision_recorded" and isinstance(event_payload, dict):
            result = event_payload.get("result")
            if isinstance(result, dict) and result.get("result_id") == result_id:
                event["payload"] = validate_json_value(deepcopy(decision))


def _rewrite_realm_of_chaos_catalog_source(
    payload: GameLifecyclePayload,
    *,
    source_id: str,
) -> None:
    records = payload["decisions"]["records"]
    if len(records) != 1:
        raise AssertionError("test requires one accepted Realm of Chaos decision")
    decision = records[0]
    selected_option_id = decision["result"]["selected_option_id"]
    selected_options = tuple(
        option
        for option in decision["request"]["options"]
        if option["option_id"] == selected_option_id
    )
    if len(selected_options) != 1:
        raise AssertionError("test requires one selected Realm of Chaos option")
    option_payload = selected_options[0]["payload"]
    result_payload = decision["result"]["payload"]
    assert isinstance(option_payload, dict)
    assert isinstance(result_payload, dict)
    option_record = option_payload.get("catalog_record")
    result_record = result_payload.get("catalog_record")
    assert isinstance(option_record, dict)
    assert isinstance(result_record, dict)
    option_definition = option_record.get("definition")
    result_definition = result_record.get("definition")
    assert isinstance(option_definition, dict)
    assert isinstance(result_definition, dict)
    option_definition["source_id"] = source_id
    result_definition["source_id"] = source_id

    use_payloads = payload["state"]["stratagem_use_records"]
    if len(use_payloads) != 1:
        raise AssertionError("test requires one Realm of Chaos use")
    use_payloads[0]["source_id"] = source_id
    request_id = decision["request"]["request_id"]
    result_id = decision["result"]["result_id"]
    for event in payload["decisions"]["event_log"]:
        event_payload = event["payload"]
        if event["event_type"] == "decision_requested" and isinstance(event_payload, dict):
            if event_payload.get("request_id") == request_id:
                event["payload"] = validate_json_value(deepcopy(decision["request"]))
        elif event["event_type"] == "decision_recorded" and isinstance(event_payload, dict):
            result = event_payload.get("result")
            if isinstance(result, dict) and result.get("result_id") == result_id:
                event["payload"] = validate_json_value(deepcopy(decision))
        elif event["event_type"] == "stratagem_used" and isinstance(event_payload, dict):
            event_payload["source_id"] = source_id
        elif event["event_type"] == "generic_stratagem_reserve_removal_resolved" and isinstance(
            event_payload, dict
        ):
            terminal_use = event_payload.get("stratagem_use")
            if not isinstance(terminal_use, dict):
                raise AssertionError("test requires source-terminal Realm of Chaos use")
            terminal_use["source_id"] = source_id


def _rewrite_realm_of_chaos_provider_use_id(
    payload: GameLifecyclePayload,
    *,
    stratagem_use_id: str,
) -> None:
    target_unit_id: str | None = None
    for event in payload["decisions"]["event_log"]:
        event_payload = event["payload"]
        if not isinstance(event_payload, dict):
            continue
        providers: list[dict[str, JsonValue]] = []
        provider_payload = event_payload.get("provider")
        if isinstance(provider_payload, dict):
            providers.append(provider_payload)
        bindings = event_payload.get("primary_reserve_entry_bindings")
        if isinstance(bindings, list):
            for binding in bindings:
                if not isinstance(binding, dict):
                    continue
                binding_provider = binding.get("provider")
                if not isinstance(binding_provider, dict):
                    continue
                providers.append(binding_provider)
        for provider in providers:
            candidate_target_id = provider.get("target_rules_unit_instance_id")
            if type(candidate_target_id) is not str:
                raise AssertionError("test requires provider target identity")
            if target_unit_id is not None and target_unit_id != candidate_target_id:
                raise AssertionError("test requires one provider target identity")
            target_unit_id = candidate_target_id
            provider["stratagem_use_id"] = stratagem_use_id
        if target_unit_id is None:
            continue
        occurrence_id = f"{stratagem_use_id}:reserve-entry:{target_unit_id}"
        if "occurrence_id" in event_payload:
            event_payload["occurrence_id"] = occurrence_id
        if isinstance(bindings, list):
            for binding in bindings:
                if isinstance(binding, dict):
                    binding["occurrence_id"] = occurrence_id
    if target_unit_id is None:
        raise AssertionError("test requires Realm of Chaos provider evidence")


def _enemy_unit_id(state: GameState) -> str:
    for army in state.army_definitions:
        if army.player_id != "player-b":
            continue
        for unit in army.units:
            return unit.unit_instance_id
    raise AssertionError("test state requires enemy unit")


def _place_unit_on_battlefield(
    *,
    state: GameState,
    unit: UnitInstance,
    pose: Pose,
) -> None:
    if state.battlefield_state is None:
        raise AssertionError("test state requires battlefield_state")
    placement = UnitPlacement(
        army_id="army-alpha",
        player_id="player-a",
        unit_instance_id=unit.unit_instance_id,
        model_placements=tuple(
            ModelPlacement(
                army_id="army-alpha",
                player_id="player-a",
                unit_instance_id=unit.unit_instance_id,
                model_instance_id=model.model_instance_id,
                pose=pose,
            )
            for model in unit.own_models
        ),
    )
    state.replace_battlefield_state(state.battlefield_state.with_added_unit_placement(placement))


def _daemonic_incursion_reserve_state(
    *,
    reserve_god_keyword: str = "Khorne",
    anchor_god_keyword: str = "Khorne",
    reserve_kind: ReserveKind = ReserveKind.DEEP_STRIKE,
) -> tuple[GameState, ReserveState, UnitInstance]:
    state, _scenario, reserve_state, _reserve_unit = battle_state_with_reserve(
        reserve_base_diameter_mm=_RESERVE_BASE_DIAMETER_MM
    )
    state.army_definitions = list(
        _with_daemonic_incursion_units(
            tuple(state.army_definitions),
            reserve_god_keyword=reserve_god_keyword,
            anchor_god_keyword=anchor_god_keyword,
        )
    )
    updated_reserve_state = replace(reserve_state, reserve_kind=reserve_kind)
    state.replace_reserve_state(updated_reserve_state)
    reserve_unit = _unit_by_id(state, _RESERVE_UNIT_ID)
    return state, updated_reserve_state, reserve_unit


def _submit_deep_strike_arrival(
    *,
    state: GameState,
    reserve_state: ReserveState,
    reserve_unit: UnitInstance,
    target_pose: Pose,
    result_id: str,
) -> _ResolvedArrivalStatus:
    return _submit_reserve_arrival(
        state=state,
        reserve_state=reserve_state,
        reserve_unit=reserve_unit,
        target_pose=target_pose,
        placement_kind=BattlefieldPlacementKind.DEEP_STRIKE,
        battle_round=1,
        result_id=result_id,
    )


def _submit_reserve_arrival(
    *,
    state: GameState,
    reserve_state: ReserveState,
    reserve_unit: UnitInstance,
    target_pose: Pose,
    placement_kind: BattlefieldPlacementKind,
    battle_round: int,
    result_id: str,
) -> _ResolvedArrivalStatus:
    _set_movement_ready_for_reinforcements(state, battle_round=battle_round)
    handler = MovementPhaseHandler(
        ruleset_descriptor=_ruleset(),
        reserve_arrival_distance_hooks=_runtime_reserve_arrival_registry(state),
    )
    decisions = DecisionController()
    selection_status = handler.begin_phase(state=state, decisions=decisions)
    selection_request = decision_request(selection_status)
    placement_status = submit_handler_decision(
        handler=handler,
        state=state,
        decisions=decisions,
        request=selection_request,
        option_id=reserve_state.unit_instance_id,
        result_id=f"{result_id}:select",
    )
    placement_request = decision_request(placement_status)
    result_status = submit_reserve_placement_payload(
        handler=handler,
        state=state,
        decisions=decisions,
        request=placement_request,
        reserve_unit=reserve_unit,
        placement_kind=placement_kind,
        attempted_placement=single_model_reserve_placement(
            reserve_unit=reserve_unit,
            pose=target_pose,
        ),
        result_id=result_id,
    )
    if result_status is None:
        result_status = handler.begin_phase(state=state, decisions=decisions)
    assert result_status is not None
    assert isinstance(result_status.payload, dict)
    return _ResolvedArrivalStatus(
        status_kind=result_status.status_kind,
        payload=result_status.payload,
        decisions=decisions,
    )


def _runtime_reserve_arrival_registry(state: GameState) -> ReserveArrivalDistanceHookRegistry:
    bundle = build_runtime_content_bundle_for_armies(
        config=_daemonic_incursion_config(game_id=f"{state.game_id}:runtime-content"),
        armies=tuple(state.army_definitions),
    )
    return bundle.reserve_arrival_distance_hook_registry


def _daemonic_incursion_runtime_bundle(state: GameState) -> RuntimeContentBundle:
    return build_runtime_content_bundle_for_armies(
        config=_daemonic_incursion_config(game_id=f"{state.game_id}:runtime-content"),
        armies=tuple(state.army_definitions),
    )


def _assign_daemonic_enhancement(
    state: GameState,
    *,
    unit: UnitInstance,
    enhancement_id: str,
    source_id: str,
) -> None:
    updated_armies: list[ArmyDefinition] = []
    for army in state.army_definitions:
        if army.player_id != "player-a":
            updated_armies.append(army)
            continue
        prefix = f"{army.army_id}:"
        if not unit.unit_instance_id.startswith(prefix):
            raise AssertionError(f"Unit {unit.unit_instance_id} is not owned by {army.army_id}.")
        updated_armies.append(
            replace(
                army,
                enhancement_assignments=(
                    EnhancementAssignment(
                        enhancement_id=enhancement_id,
                        target_unit_selection_id=unit.unit_instance_id.removeprefix(prefix),
                        source_id=source_id,
                    ),
                ),
            )
        )
    state.army_definitions = updated_armies


def _set_current_battle_phase(state: GameState, phase: BattlePhase) -> None:
    state.stage = GameLifecycleStage.BATTLE
    state.setup_step_index = None
    state.battle_phase_index = state.battle_phase_sequence.index(phase)
    state.battle_round = 1
    state.active_player_id = "player-a"


def _set_model_wounds(
    state: GameState,
    *,
    model_instance_id: str,
    wounds_remaining: int,
) -> None:
    updated_armies: list[ArmyDefinition] = []
    found_model = False
    for army in state.army_definitions:
        updated_units: list[UnitInstance] = []
        for unit in army.units:
            updated_models: list[ModelInstance] = []
            for model in unit.own_models:
                if model.model_instance_id != model_instance_id:
                    updated_models.append(model)
                    continue
                updated_models.append(replace(model, wounds_remaining=wounds_remaining))
                found_model = True
            updated_units.append(replace(unit, own_models=tuple(updated_models)))
        updated_armies.append(replace(army, units=tuple(updated_units)))
    if not found_model:
        raise AssertionError(f"Missing model {model_instance_id}.")
    state.army_definitions = updated_armies


def _attack_pool(
    *,
    attacker: UnitInstance,
    target: UnitInstance,
    weapon_profile: WeaponProfile,
) -> RangedAttackPool:
    target_model_ids = tuple(model.model_instance_id for model in target.own_models)
    return RangedAttackPool(
        attacker_model_instance_id=attacker.own_models[0].model_instance_id,
        wargear_id="phase17g-daemonic-incursion-test-wargear",
        weapon_profile_id=weapon_profile.profile_id,
        weapon_profile=weapon_profile,
        target_unit_instance_id=target.unit_instance_id,
        shooting_type=ShootingType.NORMAL,
        attacks=1,
        target_visible_model_ids=target_model_ids,
        target_in_range_model_ids=target_model_ids,
    )


def _reserve_arrival_distance_context(
    *,
    state: GameState,
    reserve_state: ReserveState,
    reserve_unit: UnitInstance,
    attempted_placement: UnitPlacement,
    placement_kind: BattlefieldPlacementKind,
) -> ReserveArrivalDistanceContext:
    if state.battlefield_state is None:
        raise AssertionError("test context requires battlefield_state")
    if state.mission_setup is None:
        raise AssertionError("test context requires mission_setup")
    scenario = BattlefieldScenario(
        armies=tuple(state.army_definitions),
        battlefield_state=state.battlefield_state,
    )
    return ReserveArrivalDistanceContext(
        state=state,
        scenario=scenario,
        ruleset_descriptor=_ruleset(),
        reserve_state=reserve_state,
        rules_unit=rules_unit_view_by_id(
            state=state,
            unit_instance_id=reserve_unit.unit_instance_id,
        ),
        attempted_rules_unit_placement=RulesUnitPlacement.single(attempted_placement),
        placement_kind=placement_kind,
        battle_round=state.battle_round,
        battlefield_width_inches=state.battlefield_state.battlefield_width_inches,
        battlefield_depth_inches=state.battlefield_state.battlefield_depth_inches,
        terrain_features=state.battlefield_state.terrain_features,
        objective_markers=tuple(
            marker.to_objective_marker() for marker in state.mission_setup.objective_markers
        ),
        enemy_deployment_zones=tuple(
            zone
            for zone in state.mission_setup.deployment_zones
            if zone.player_id != reserve_state.player_id
        ),
        base_enemy_horizontal_distance_inches=9.0,
    )


def _daemonic_incursion_execution_record() -> faction_execution_2026_27.Phase17FExecutionRecord:
    return _execution_record_by_descriptor_id(
        daemonic_incursion_ir.DAEMONIC_INCURSION_DETACHMENT_RULE_DESCRIPTOR_ID
    )


def _execution_record_by_descriptor_id(
    descriptor_id: str,
) -> faction_execution_2026_27.Phase17FExecutionRecord:
    return next(
        record
        for record in faction_execution_2026_27.phase17f_execution_package().execution_records
        if record.coverage_descriptor_id == descriptor_id
    )


def _rule_ir_source_id(descriptor_id: str) -> str:
    return faction_generic_ir_support_2026_27.generic_rule_ir_by_coverage_descriptor_id(
        descriptor_id
    ).source_id


def _rule_ir_by_descriptor_id(descriptor_id: str) -> RuleIR:
    return faction_generic_ir_support_2026_27.generic_rule_ir_by_coverage_descriptor_id(
        descriptor_id
    )


def _single_rule_effect_payload(
    *,
    descriptor_id: str,
    effect_kind: str,
) -> dict[str, JsonValue]:
    rule_ir = _rule_ir_by_descriptor_id(descriptor_id)
    matching_effects = tuple(
        (clause, effect_index, effect)
        for clause in rule_ir.clauses
        for effect_index, effect in enumerate(clause.effects)
        if effect.kind.value == effect_kind
    )
    if len(matching_effects) != 1:
        raise AssertionError("Generic stratagem test requires exactly one matching effect.")
    clause, effect_index, effect = matching_effects[0]
    return {
        "rule_id": rule_ir.rule_id,
        "source_id": rule_ir.source_id,
        "rule_ir_hash": rule_ir.ir_hash(),
        "clause_id": clause.clause_id,
        "effect_index": effect_index,
        "target": validate_json_value(
            None if clause.target is None else clause.target.to_payload()
        ),
        "target_unit_instance_ids": [_ANCHOR_UNIT_ID],
        "duration": validate_json_value(
            None if clause.duration is None else clause.duration.to_payload()
        ),
        "effect": validate_json_value(effect.to_payload()),
    }


def _with_rule_effect_parameter(
    effect_payload: dict[str, JsonValue],
    *,
    key: str,
    value: JsonValue,
) -> dict[str, JsonValue]:
    effect_value = effect_payload.get("effect")
    if not isinstance(effect_value, dict):
        raise TypeError("test effect payload requires effect object")
    effect = effect_value
    parameters_value = effect.get("parameters")
    if not isinstance(parameters_value, list):
        raise TypeError("test effect payload requires parameter list")
    updated_parameters: list[JsonValue] = []
    replaced = False
    for parameter_value in parameters_value:
        if not isinstance(parameter_value, dict):
            raise TypeError("test effect payload requires parameter objects")
        parameter = parameter_value
        if parameter.get("key") == key:
            updated_parameters.append({**parameter, "value": value})
            replaced = True
            continue
        updated_parameters.append(parameter)
    if not replaced:
        raise AssertionError(f"test effect payload missing parameter: {key}")
    updated_effect: dict[str, JsonValue] = {**effect, "parameters": updated_parameters}
    return {**effect_payload, "effect": updated_effect}


def _rule_result(
    rule_ir: RuleIR,
    effect_payload: dict[str, JsonValue],
) -> RuleExecutionResult:
    clause_id = effect_payload.get("clause_id")
    if type(clause_id) is not str:
        raise AssertionError("test effect payload requires clause_id")
    return RuleExecutionResult.applied(
        rule_ir,
        applied_clause_ids=(clause_id,),
        effect_payloads=(effect_payload,),
    )


def _denizens_of_the_warp_effect(
    *,
    state: GameState,
    unit_instance_id: str,
) -> PersistingEffect:
    rule_ir = faction_generic_ir_support_2026_27.generic_rule_ir_by_coverage_descriptor_id(
        daemonic_incursion_ir.DENIZENS_OF_THE_WARP_DESCRIPTOR_ID
    )
    grant_effects = tuple(
        effect.to_payload()
        for clause in rule_ir.clauses
        for effect in clause.effects
        if effect.kind.value == "grant_ability"
    )
    if len(grant_effects) != 1:
        raise AssertionError("Denizens test requires exactly one grant ability effect.")
    return PersistingEffect(
        effect_id=f"phase17g-denizens:{unit_instance_id}",
        source_rule_id=daemonic_incursion_ir.DENIZENS_OF_THE_WARP_SOURCE_RULE_ID,
        owner_player_id="player-a",
        target_unit_instance_ids=(unit_instance_id,),
        started_battle_round=state.battle_round,
        started_phase=BattlePhase.MOVEMENT,
        expiration=EffectExpiration.end_phase(
            battle_round=state.battle_round,
            phase=BattlePhase.MOVEMENT,
            player_id="player-a",
        ),
        effect_payload={
            "effect_kind": GENERIC_RULE_EFFECT_KIND,
            "coverage_descriptor_id": daemonic_incursion_ir.DENIZENS_OF_THE_WARP_DESCRIPTOR_ID,
            "execution_id": _execution_record_by_descriptor_id(
                daemonic_incursion_ir.DENIZENS_OF_THE_WARP_DESCRIPTOR_ID
            ).execution_id,
            "rule_ir_source_id": rule_ir.source_id,
            "rule_ir_hash": rule_ir.ir_hash(),
            "target": {"kind": "this_unit"},
            "effect": validate_json_value(grant_effects[0]),
        },
    )


def _generic_stratagem_persisting_effect(
    *,
    descriptor_id: str,
    source_rule_id: str,
    effect_kind: str,
    effect_id: str,
    target_unit_instance_id: str,
) -> PersistingEffect:
    rule_ir = faction_generic_ir_support_2026_27.generic_rule_ir_by_coverage_descriptor_id(
        descriptor_id
    )
    matching_effects = tuple(
        (clause, effect_index, effect)
        for clause in rule_ir.clauses
        for effect_index, effect in enumerate(clause.effects)
        if effect.kind.value == effect_kind
    )
    if len(matching_effects) != 1:
        raise AssertionError("Generic stratagem test requires exactly one matching effect.")
    clause, effect_index, effect = matching_effects[0]
    return PersistingEffect(
        effect_id=effect_id,
        source_rule_id=source_rule_id,
        owner_player_id="player-a",
        target_unit_instance_ids=(target_unit_instance_id,),
        started_battle_round=1,
        started_phase=BattlePhase.SHOOTING,
        expiration=EffectExpiration.end_phase(
            battle_round=1,
            phase=BattlePhase.SHOOTING,
            player_id="player-a",
        ),
        effect_payload={
            "effect_kind": GENERIC_RULE_EFFECT_KIND,
            "rule_id": rule_ir.rule_id,
            "source_id": rule_ir.source_id,
            "rule_ir_hash": rule_ir.ir_hash(),
            "clause_id": clause.clause_id,
            "effect_index": effect_index,
            "target": validate_json_value(
                None if clause.target is None else clause.target.to_payload()
            ),
            "target_unit_instance_ids": [target_unit_instance_id],
            "duration": validate_json_value(
                None if clause.duration is None else clause.duration.to_payload()
            ),
            "effect": validate_json_value(effect.to_payload()),
        },
    )


@dataclass(frozen=True, slots=True)
class _ResolvedArrivalStatus:
    status_kind: LifecycleStatusKind
    payload: dict[str, JsonValue]
    decisions: DecisionController


def _set_movement_ready_for_reinforcements(state: GameState, *, battle_round: int) -> None:
    state.stage = GameLifecycleStage.BATTLE
    state.setup_step_index = None
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.MOVEMENT)
    state.battle_round = battle_round
    state.active_player_id = "player-a"
    state.movement_phase_state = MovementPhaseState(
        battle_round=battle_round,
        active_player_id="player-a",
        selected_unit_ids=(_ANCHOR_UNIT_ID,),
        moved_unit_ids=(_ANCHOR_UNIT_ID,),
    )


def _with_daemonic_incursion_units(
    armies: tuple[ArmyDefinition, ...],
    *,
    reserve_god_keyword: str,
    anchor_god_keyword: str,
) -> tuple[ArmyDefinition, ...]:
    updated_armies: list[ArmyDefinition] = []
    for army in armies:
        if army.army_id == "army-alpha":
            reserve_unit = _as_daemon_unit(
                army.unit_by_id(_RESERVE_UNIT_ID),
                name="Bloodletters",
                keywords=("Infantry", reserve_god_keyword, "DEEP_STRIKE"),
            )
            anchor_unit = _as_daemon_unit(
                army.unit_by_id(_ANCHOR_UNIT_ID),
                name="Renamed Greater Daemon Anchor",
                keywords=("Monster", anchor_god_keyword),
                datasheet_abilities=(
                    _datasheet_ability(datasheets.BLOODTHIRSTER_GREATER_DAEMON_ABILITY_ID),
                ),
            )
            updated_armies.append(
                replace(
                    army,
                    detachment_selection=DetachmentSelection(
                        faction_id=rule.CHAOS_DAEMONS_FACTION_ID,
                        detachment_ids=(rule.DAEMONIC_INCURSION_DETACHMENT_ID,),
                    ),
                    units=tuple(
                        reserve_unit
                        if unit.unit_instance_id == reserve_unit.unit_instance_id
                        else anchor_unit
                        if unit.unit_instance_id == anchor_unit.unit_instance_id
                        else unit
                        for unit in army.units
                    ),
                )
            )
            continue
        updated_armies.append(army)
    return tuple(updated_armies)


def _as_daemon_unit(
    unit: UnitInstance,
    *,
    name: str,
    keywords: tuple[str, ...],
    datasheet_abilities: tuple[DatasheetAbilityDescriptor, ...] = (),
) -> UnitInstance:
    return replace(
        unit,
        name=name,
        keywords=keywords,
        faction_keywords=(rule.LEGIONES_DAEMONICA,),
        datasheet_abilities=datasheet_abilities,
        own_models=tuple(
            _with_base_size(model, base_diameter_mm=_RESERVE_BASE_DIAMETER_MM)
            for model in unit.own_models
        ),
    )


def _datasheet_ability(ability_id: str) -> DatasheetAbilityDescriptor:
    return DatasheetAbilityDescriptor(
        ability_id=ability_id,
        name="Source Backed Datasheet Ability",
        source_id=f"data-package:core-v2:phase17g-daemonic-incursion-test:{ability_id}",
        support=CatalogAbilitySupport.DESCRIPTOR_ONLY,
        source_kind=CatalogAbilitySourceKind.DATASHEET,
        effect_description="source-backed datasheet test ability",
    )


def _place_enemy_at_base_distance(
    *,
    state: GameState,
    target_pose: Pose,
    distance_inches: float,
) -> None:
    enemy_unit = next(
        unit
        for army in state.army_definitions
        if army.player_id == "player-b"
        for unit in army.units
    )
    enemy_model_id = enemy_unit.own_models[0].model_instance_id
    radius = base_radius_inches(_RESERVE_BASE_DIAMETER_MM)
    _place_model(
        state=state,
        model_instance_id=enemy_model_id,
        pose=Pose.at(
            x=target_pose.position.x + (radius * 2.0) + distance_inches,
            y=target_pose.position.y,
            z=0.0,
            facing_degrees=0.0,
        ),
    )


def _place_anchor_at_base_distance(
    *,
    state: GameState,
    target_pose: Pose,
    distance_inches: float,
) -> None:
    anchor_unit = _unit_by_id(state, _ANCHOR_UNIT_ID)
    anchor_model_id = anchor_unit.own_models[0].model_instance_id
    radius = base_radius_inches(_RESERVE_BASE_DIAMETER_MM)
    _place_model(
        state=state,
        model_instance_id=anchor_model_id,
        pose=Pose.at(
            x=target_pose.position.x,
            y=target_pose.position.y - (radius * 2.0) - distance_inches,
            z=0.0,
            facing_degrees=0.0,
        ),
    )


def _place_model(
    *,
    state: GameState,
    model_instance_id: str,
    pose: Pose,
) -> None:
    if state.battlefield_state is None:
        raise AssertionError("test state requires battlefield_state")
    scenario = BattlefieldScenario(
        armies=tuple(state.army_definitions),
        battlefield_state=state.battlefield_state,
    )
    updated_scenario = with_model_pose(
        scenario,
        model_instance_id=model_instance_id,
        pose=pose,
    )
    state.replace_battlefield_state(updated_scenario.battlefield_state)


def _unit_by_id(state: GameState, unit_instance_id: str) -> UnitInstance:
    for army in state.army_definitions:
        for unit in army.units:
            if unit.unit_instance_id == unit_instance_id:
                return unit
    raise AssertionError(f"unit not found: {unit_instance_id}")


def _replace_unit_datasheet_abilities(
    state: GameState,
    *,
    unit_instance_id: str,
    datasheet_abilities: tuple[DatasheetAbilityDescriptor, ...],
) -> None:
    state.army_definitions = [
        replace(
            army,
            units=tuple(
                replace(unit, datasheet_abilities=datasheet_abilities)
                if unit.unit_instance_id == unit_instance_id
                else unit
                for unit in army.units
            ),
        )
        for army in state.army_definitions
    ]


def _with_base_size(model: ModelInstance, *, base_diameter_mm: float) -> ModelInstance:
    if type(model) is not ModelInstance:
        raise AssertionError("test base-size helper requires ModelInstance")
    base_size = BaseSizeDefinition.circular(base_diameter_mm)
    return replace(
        model,
        base_size=base_size,
        geometry=ModelGeometry.from_base_size(
            base_size,
            geometry_source_id="phase17g-daemonic-incursion-base",
            keywords=(),
        ),
    )


def _daemonic_incursion_config(
    *,
    game_id: str = "phase17g-daemonic-incursion-game",
    daemon_detachment_id: str = rule.DAEMONIC_INCURSION_DETACHMENT_ID,
) -> GameConfig:
    catalog = _daemonic_incursion_catalog()
    return GameConfig(
        game_id=game_id,
        allow_legacy_non_strict_rosters=True,
        ruleset_descriptor=_ruleset(),
        army_catalog=catalog,
        army_muster_requests=(
            _army_muster_request(
                catalog=catalog,
                army_id="army-alpha",
                player_id="player-a",
                faction_id=rule.CHAOS_DAEMONS_FACTION_ID,
                detachment_id=daemon_detachment_id,
                unit_selection_id="daemon-unit",
                datasheet_id=_DAEMONIC_INCURSION_DATASHEET_ID,
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
        turn_order=("player-a", "player-b"),
        fixed_secondary_mission_ids=("assassination", "bring_it_down", "cleanse"),
        mission_setup=_mission_setup(),
    )


def _daemonic_incursion_catalog() -> ArmyCatalog:
    base_catalog = ArmyCatalog.phase9a_canonical_content_pack()
    base_datasheet = base_catalog.datasheet_by_id("core-intercessor-like-infantry")
    daemon_datasheet = replace(
        base_datasheet,
        datasheet_id=_DAEMONIC_INCURSION_DATASHEET_ID,
        name="Daemonic Incursion Daemon",
        keywords=DatasheetKeywordSet(
            keywords=("Infantry", "Khorne", "Deep Strike"),
            faction_keywords=(rule.LEGIONES_DAEMONICA,),
        ),
        source_ids=("phase17g:test:chaos-daemons:daemonic-incursion-daemon",),
    )
    return replace(
        base_catalog,
        datasheets=(*base_catalog.datasheets, daemon_datasheet),
        factions=(
            *base_catalog.factions,
            FactionDefinition(
                faction_id=rule.CHAOS_DAEMONS_FACTION_ID,
                name="Chaos Daemons",
                faction_keywords=(rule.LEGIONES_DAEMONICA,),
                source_ids=("gw-11e-faction-detachments-2026-27:faction:chaos-daemons",),
            ),
        ),
        detachments=(
            *base_catalog.detachments,
            DetachmentDefinition(
                detachment_id=rule.DAEMONIC_INCURSION_DETACHMENT_ID,
                name="Daemonic Incursion",
                faction_id=rule.CHAOS_DAEMONS_FACTION_ID,
                detachment_point_cost=1,
                unit_datasheet_ids=(_DAEMONIC_INCURSION_DATASHEET_ID,),
                force_disposition_ids=("phase17g-force", "take-and-hold"),
                source_ids=(
                    "gw-11e-faction-detachments-2026-27:detachment:"
                    "chaos-daemons:daemonic-incursion",
                ),
            ),
            DetachmentDefinition(
                detachment_id=_OTHER_DAEMON_DETACHMENT_ID,
                name="Warptide",
                faction_id=rule.CHAOS_DAEMONS_FACTION_ID,
                detachment_point_cost=1,
                unit_datasheet_ids=(_DAEMONIC_INCURSION_DATASHEET_ID,),
                force_disposition_ids=("phase17g-force", "take-and-hold"),
                source_ids=(
                    "gw-11e-faction-detachments-2026-27:detachment:chaos-daemons:warptide",
                ),
            ),
        ),
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
) -> ArmyMusterRequest:
    return ArmyMusterRequest(
        army_id=army_id,
        player_id=player_id,
        catalog_id=catalog.catalog_id,
        source_package_id=catalog.source_package_id,
        ruleset_id=catalog.ruleset_id,
        detachment_selection=DetachmentSelection(
            faction_id=faction_id,
            detachment_ids=(detachment_id,),
        ),
        force_disposition_id=(
            "purge-the-foe" if faction_id == "core-marine-force" else "take-and-hold"
        ),
        unit_selections=(
            UnitMusterSelection(
                unit_selection_id=unit_selection_id,
                datasheet_id=datasheet_id,
                model_profile_selections=(
                    ModelProfileSelection(
                        model_profile_id="core-intercessor-like",
                        model_count=5,
                    ),
                ),
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


def _ruleset() -> RulesetDescriptor:
    return RulesetDescriptor.warhammer_40000_eleventh(
        descriptor_version="core-v2-phase17g-daemonic-incursion-test"
    )
