# pyright: reportPrivateUsage=false
from __future__ import annotations

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
from warhammer40k_core.engine.decision import DiceRollManager
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.effects import (
    GENERIC_RULE_EFFECT_KIND,
    EffectExpiration,
    EffectExpirationKind,
    PersistingEffect,
)
from warhammer40k_core.engine.enhancement_effects import apply_enhancement_effects
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
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
from warhammer40k_core.engine.list_validation import (
    DetachmentSelection,
    UnitMusterSelection,
)
from warhammer40k_core.engine.mission_setup import MissionSetup
from warhammer40k_core.engine.phase import (
    BattlePhase,
    GameLifecycleError,
    GameLifecycleStage,
    LifecycleStatusKind,
)
from warhammer40k_core.engine.phases.movement import (
    MovementPhaseHandler,
    MovementPhaseState,
)
from warhammer40k_core.engine.reserve_arrival_hooks import (
    ReserveArrivalDistanceContext,
    ReserveArrivalDistanceHookRegistry,
)
from warhammer40k_core.engine.reserves import (
    ReserveDestructionTimingPolicy,
    ReserveKind,
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
from warhammer40k_core.engine.stratagems_generic_metadata import (
    objective_marker_effect_selection,
)
from warhammer40k_core.engine.stratagems_model import (
    StratagemDefinition,
    StratagemEligibilityContext,
    StratagemTargetBinding,
    StratagemTargetKind,
    StratagemUseRecord,
)
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
        _daemonic_stratagem_use_record(
            definition=definition,
            target_unit_id=target_unit.unit_instance_id,
            phase=BattlePhase.MOVEMENT,
            effect_selection=companion_selection,
        )
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
                    _datasheet_ability(datasheets.BLOODTHIRSTER_GREATER_DAEMON_SOURCE_ID),
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


def _datasheet_ability(source_id: str) -> DatasheetAbilityDescriptor:
    ability_id_suffix = source_id.split("Datasheets_abilities:", maxsplit=1)[1].replace(":", "-")
    return DatasheetAbilityDescriptor(
        ability_id=f"phase17g-daemonic-incursion:{ability_id_suffix}",
        name="Source Backed Datasheet Ability",
        source_id=source_id,
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
                force_disposition_ids=("phase17g-force",),
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
                force_disposition_ids=("phase17g-force",),
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
            "purge-the-foe" if faction_id == "core-marine-force" else "phase17g-force"
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
        defender_player_id="player-b",
    )


def _ruleset() -> RulesetDescriptor:
    return RulesetDescriptor.warhammer_40000_eleventh(
        descriptor_version="core-v2-phase17g-daemonic-incursion-test"
    )
