from __future__ import annotations

from dataclasses import replace
from typing import cast

import pytest

from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.core.attributes import Characteristic, CharacteristicValue
from warhammer40k_core.core.datasheet import BaseSizeDefinition
from warhammer40k_core.core.ruleset_descriptor import RulesetDescriptor
from warhammer40k_core.core.weapon_profiles import WeaponKeyword
from warhammer40k_core.engine import (
    generic_detachment_rule_effects as generic_detachment_effects,
)
from warhammer40k_core.engine import (
    generic_rule_advance_move_lifecycle_hooks as advance_move_lifecycle_hooks,
)
from warhammer40k_core.engine.advance_eligibility_hooks import AdvanceEligibilityContext
from warhammer40k_core.engine.advance_hooks import AdvanceMoveContext, AdvanceMoveGrant
from warhammer40k_core.engine.army_mustering import (
    ArmyDefinition,
    ArmyMusterRequest,
)
from warhammer40k_core.engine.battle_formation_hooks import BattleFormationRequestContext
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.effects import (
    EffectExpiration,
    PersistingEffect,
    generic_rule_persisting_effect,
)
from warhammer40k_core.engine.event_log import validate_json_value
from warhammer40k_core.engine.faction_content.activation import RuntimeContentActivation
from warhammer40k_core.engine.faction_content.warhammer_40000_11th.aeldari.detachments.corsair_coterie import (  # noqa: E501
    enhancements as corsair_enhancements,
)
from warhammer40k_core.engine.faction_content.warhammer_40000_11th.chaos_space_marines import (
    army_rule as dark_pacts,
)
from warhammer40k_core.engine.faction_content.warhammer_40000_11th.emperors_children.detachments.court_of_the_phoenician import (  # noqa: E501
    rule as court_rule,
)
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
from warhammer40k_core.engine.list_validation import (
    DetachmentSelection,
    UnitMusterSelection,
)
from warhammer40k_core.engine.phase import (
    BattlePhase,
    GameLifecycleError,
    GameLifecycleStage,
    SetupStep,
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
from warhammer40k_core.engine.timing_windows import TimingTriggerKind
from warhammer40k_core.engine.unit_factory import ModelInstance, UnitInstance
from warhammer40k_core.engine.unit_state import StartingStrengthRecord
from warhammer40k_core.engine.wargear_selections import (
    ModelProfileSelection,
)
from warhammer40k_core.geometry.model_geometry import ModelGeometry
from warhammer40k_core.rules.rule_ir import RuleEffectKind, RuleTargetKind
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


def test_default_generic_rule_ability_registry_maps_shadow_legion_grants() -> None:
    source = _shadow_legion_source()
    registry = DEFAULT_GENERIC_RULE_ABILITY_REGISTRY

    advance = registry.advance_eligibility_abilities[0]
    assert advance.hook_family is GenericRuleAbilityHookFamily.ADVANCE_ELIGIBILITY
    assert advance.ability_ids() == (shadow_legion_ir.CAN_ADVANCE_AND_SHOOT_AND_CHARGE_ABILITY,)
    assert (
        advance.coverage_descriptor_id
        == shadow_legion_ir.SHADOW_LEGION_DETACHMENT_RULE_DESCRIPTOR_ID
    )
    assert advance.source_rule_id == dark_pacts.SHADOW_LEGION_SOURCE_RULE_ID
    assert advance.hook_id(source) == (
        "phase17f:phase17e:chaos-daemons:shadow-legion:rule:shadow-legion:advance-eligibility"
    )

    restriction = registry.shooting_target_restriction_abilities[0]
    assert restriction.hook_family is GenericRuleAbilityHookFamily.SHOOTING_TARGET_RESTRICTION
    assert restriction.ability_ids() == (shadow_legion_ir.SNAP_SHOOTING_TARGET_FORBIDDEN_ABILITY,)
    assert restriction.hook_id(source) == (
        "phase17f:phase17e:chaos-daemons:shadow-legion:rule:shadow-legion:snap-target-restriction"
    )

    shooting_grants = registry.shooting_unit_selected_grant_abilities
    assert {descriptor.hook_family for descriptor in shooting_grants} == {
        GenericRuleAbilityHookFamily.SHOOTING_UNIT_SELECTED_GRANT
    }
    assert {descriptor.ability_id for descriptor in shooting_grants} == {
        shadow_legion_ir.SHADOW_LEGION_DARK_PACT_LETHAL_HITS_CHOICE_ABILITY,
        shadow_legion_ir.SHADOW_LEGION_DARK_PACT_SUSTAINED_HITS_1_CHOICE_ABILITY,
    }
    assert {descriptor.hook_id(source) for descriptor in shooting_grants} == {
        "phase17f:phase17e:chaos-daemons:shadow-legion:rule:shadow-legion:shooting:lethal_hits",
        (
            "phase17f:phase17e:chaos-daemons:shadow-legion:rule:"
            "shadow-legion:shooting:sustained_hits_1"
        ),
    }

    fight_grants = registry.fight_unit_selected_grant_abilities
    assert {descriptor.hook_family for descriptor in fight_grants} == {
        GenericRuleAbilityHookFamily.FIGHT_UNIT_SELECTED_GRANT
    }
    assert {descriptor.hook_id(source) for descriptor in fight_grants} == {
        "phase17f:phase17e:chaos-daemons:shadow-legion:rule:shadow-legion:fight:lethal_hits",
        ("phase17f:phase17e:chaos-daemons:shadow-legion:rule:shadow-legion:fight:sustained_hits_1"),
    }

    attack_completion = registry.attack_sequence_completed_abilities[0]
    assert attack_completion.hook_family is GenericRuleAbilityHookFamily.ATTACK_SEQUENCE_COMPLETED
    assert set(attack_completion.ability_ids()) == {
        shadow_legion_ir.SHADOW_LEGION_DARK_PACT_LETHAL_HITS_CHOICE_ABILITY,
        shadow_legion_ir.SHADOW_LEGION_DARK_PACT_SUSTAINED_HITS_1_CHOICE_ABILITY,
    }
    assert attack_completion.hook_id(source) == (
        "phase17f:phase17e:chaos-daemons:shadow-legion:rule:shadow-legion:dark-pact-completion"
    )

    fnp = registry.mortal_wound_feel_no_pain_abilities[0]
    assert fnp.hook_family is GenericRuleAbilityHookFamily.MORTAL_WOUND_FEEL_NO_PAIN_CONTINUATION
    assert fnp.source_kind == dark_pacts.SHADOW_LEGION_DARK_PACT_MORTAL_WOUNDS_SOURCE_KIND

    weapon_profile = registry.weapon_profile_modifier_abilities[0]
    assert weapon_profile.hook_family is GenericRuleAbilityHookFamily.WEAPON_PROFILE_MODIFIER
    assert weapon_profile.modifier_id(source) == (
        "phase17f:phase17e:chaos-daemons:shadow-legion:rule:shadow-legion:dark-pact-weapon-profile"
    )


def test_default_generic_rule_ability_registry_maps_blood_legion_grants() -> None:
    source = _blood_legion_source()
    registry = DEFAULT_GENERIC_RULE_ABILITY_REGISTRY

    surge = registry.movement_end_surge_abilities[0]
    assert surge.hook_family is GenericRuleAbilityHookFamily.MOVEMENT_END_SURGE
    assert surge.ability_ids() == (blood_legion_ir.MURDERCALL_SURGE_ABILITY,)
    assert (
        surge.coverage_descriptor_id == blood_legion_ir.BLOOD_LEGION_DETACHMENT_RULE_DESCRIPTOR_ID
    )
    assert surge.source_rule_id == blood_legion_ir.BLOOD_LEGION_SOURCE_RULE_ID
    assert surge.hook_id(source) == blood_legion_ir.MURDERCALL_HOOK_ID

    sticky = registry.phase_end_objective_control_abilities[0]
    assert sticky.hook_family is GenericRuleAbilityHookFamily.PHASE_END_OBJECTIVE_CONTROL
    assert sticky.ability_ids() == (blood_legion_ir.BLOOD_TAINTED_STICKY_OBJECTIVE_ABILITY,)
    assert (
        sticky.coverage_descriptor_id == blood_legion_ir.BLOOD_LEGION_DETACHMENT_RULE_DESCRIPTOR_ID
    )
    assert sticky.source_rule_id == blood_legion_ir.BLOOD_LEGION_SOURCE_RULE_ID
    assert sticky.hook_id(source) == blood_legion_ir.BLOOD_TAINTED_HOOK_ID


def test_default_generic_rule_ability_registry_maps_warptide_grants() -> None:
    source = _warptide_source(warptide_ir.WARPTIDE_DETACHMENT_RULE_DESCRIPTOR_ID)
    registry = DEFAULT_GENERIC_RULE_ABILITY_REGISTRY

    advance_move = next(
        descriptor
        for descriptor in registry.advance_move_abilities
        if descriptor.ability_ids() == (warptide_ir.SHUDDERBLINK_ASSAULT_AFTER_ADVANCE_ABILITY,)
    )
    assert advance_move.hook_family is GenericRuleAbilityHookFamily.ADVANCE_MOVE
    assert advance_move.coverage_descriptor_id == warptide_ir.WARPTIDE_DETACHMENT_RULE_DESCRIPTOR_ID
    assert advance_move.source_rule_id == warptide_ir.WARPTIDE_SOURCE_RULE_ID
    assert advance_move.hook_id(source) == warptide_ir.SHUDDERBLINK_ADVANCE_MOVE_HOOK_ID

    advance_eligibility = next(
        descriptor
        for descriptor in registry.advance_eligibility_abilities
        if descriptor.ability_ids() == (warptide_ir.SHUDDERBLINK_CHARGE_AFTER_ADVANCE_ABILITY,)
    )
    assert advance_eligibility.hook_family is GenericRuleAbilityHookFamily.ADVANCE_ELIGIBILITY
    assert (
        advance_eligibility.coverage_descriptor_id
        == warptide_ir.WARPTIDE_DETACHMENT_RULE_DESCRIPTOR_ID
    )
    assert advance_eligibility.source_rule_id == warptide_ir.WARPTIDE_SOURCE_RULE_ID
    assert (
        advance_eligibility.hook_id(source) == warptide_ir.SHUDDERBLINK_ADVANCE_ELIGIBILITY_HOOK_ID
    )

    soul_hungry_source = _warptide_source(warptide_ir.SOUL_HUNGRY_SLAUGHTERERS_DESCRIPTOR_ID)
    soul_hungry = next(
        descriptor
        for descriptor in registry.stratagem_cost_modifier_abilities
        if descriptor.ability_ids() == (warptide_ir.SOUL_HUNGRY_SLAUGHTERERS_COST_ABILITY,)
    )
    assert soul_hungry.hook_family is GenericRuleAbilityHookFamily.STRATAGEM_COST_MODIFIER
    assert soul_hungry.coverage_descriptor_id == warptide_ir.SOUL_HUNGRY_SLAUGHTERERS_DESCRIPTOR_ID
    assert soul_hungry.source_rule_id == warptide_ir.SOUL_HUNGRY_SLAUGHTERERS_SOURCE_RULE_ID
    assert soul_hungry.modifier_id(soul_hungry_source) == (
        warptide_ir.SOUL_HUNGRY_SLAUGHTERERS_COST_MODIFIER_ID
    )


def test_warptide_shudderblink_advance_move_grant_is_automatic_assault() -> None:
    state = _warptide_state()
    source = _warptide_source(warptide_ir.WARPTIDE_DETACHMENT_RULE_DESCRIPTOR_ID)
    effect = _warptide_grant_ability_effect(
        source=source,
        effect_id="warptide:shudderblink:assault-after-advance",
        target_unit_instance_id=_WARPTIDE_UNIT_ID,
        ability=warptide_ir.SHUDDERBLINK_ASSAULT_AFTER_ADVANCE_ABILITY,
    )
    state.record_persisting_effect(effect)
    matching_effects = generic_rule_ability_effects_for_unit(
        state=state,
        source=source,
        unit_instance_id=_WARPTIDE_UNIT_ID,
        ability=warptide_ir.SHUDDERBLINK_ASSAULT_AFTER_ADVANCE_ABILITY,
    )
    descriptor = next(
        ability
        for ability in DEFAULT_GENERIC_RULE_ABILITY_REGISTRY.advance_move_abilities
        if ability.ability_ids() == (warptide_ir.SHUDDERBLINK_ASSAULT_AFTER_ADVANCE_ABILITY,)
    )
    context = AdvanceMoveContext(
        state=state,
        player_id="player-a",
        battle_round=1,
        unit_instance_id=_WARPTIDE_UNIT_ID,
        movement_phase_action="advance",
        movement_request_id="warptide-advance-request",
        movement_result_id="warptide-advance-result",
    )

    assert descriptor.context_predicate(context, source, matching_effects)

    grant = descriptor.grant_builder(context, source, matching_effects)
    assert grant.hook_id == warptide_ir.SHUDDERBLINK_ADVANCE_MOVE_HOOK_ID
    assert grant.source_id == warptide_ir.WARPTIDE_SOURCE_RULE_ID
    assert grant.automatic is True
    assert grant.granted_ranged_weapon_keywords == (WeaponKeyword.ASSAULT.value,)
    assert grant.unit_effect_expiration == "end_turn"
    assert isinstance(grant.unit_effect_payload, dict)
    assert grant.unit_effect_payload["granted_weapon_keywords"] == [WeaponKeyword.ASSAULT.value]


def test_warptide_shudderblink_advance_move_predicate_rejects_wrong_contexts() -> None:
    state = _warptide_state()
    source = _warptide_source(warptide_ir.WARPTIDE_DETACHMENT_RULE_DESCRIPTOR_ID)
    effect = _warptide_grant_ability_effect(
        source=source,
        effect_id="warptide:shudderblink:assault-after-advance",
        target_unit_instance_id=_WARPTIDE_UNIT_ID,
        ability=warptide_ir.SHUDDERBLINK_ASSAULT_AFTER_ADVANCE_ABILITY,
    )
    descriptor = next(
        ability
        for ability in DEFAULT_GENERIC_RULE_ABILITY_REGISTRY.advance_move_abilities
        if ability.ability_ids() == (warptide_ir.SHUDDERBLINK_ASSAULT_AFTER_ADVANCE_ABILITY,)
    )
    normal_move_context = AdvanceMoveContext(
        state=state,
        player_id="player-a",
        battle_round=1,
        unit_instance_id=_WARPTIDE_UNIT_ID,
        movement_phase_action="normal_move",
        movement_request_id="warptide-normal-request",
        movement_result_id="warptide-normal-result",
    )

    assert not descriptor.context_predicate(normal_move_context, source, ())
    assert not descriptor.context_predicate(normal_move_context, source, (effect,))
    with pytest.raises(GameLifecycleError, match="requires context"):
        descriptor.context_predicate(cast(AdvanceMoveContext, object()), source, (effect,))
    with pytest.raises(GameLifecycleError, match="requires source"):
        descriptor.context_predicate(
            normal_move_context,
            cast(GenericRuleAbilitySource, object()),
            (effect,),
        )
    with pytest.raises(GameLifecycleError, match="hook ID requires source"):
        descriptor.hook_id(cast(GenericRuleAbilitySource, object()))


def test_warptide_advance_move_lifecycle_binding_dispatches_generic_handler() -> None:
    state = _warptide_state()
    source = _warptide_source(warptide_ir.WARPTIDE_DETACHMENT_RULE_DESCRIPTOR_ID)
    record = source.record
    context = AdvanceMoveContext(
        state=state,
        player_id="player-a",
        battle_round=1,
        unit_instance_id=_WARPTIDE_UNIT_ID,
        movement_phase_action="advance",
        movement_request_id="warptide-advance-request",
        movement_result_id="warptide-advance-result",
    )
    bindings = advance_move_lifecycle_hooks.advance_move_hook_bindings(
        activation=_warptide_activation(),
        execution_records=(record,),
    )

    assert len(bindings) == 1
    assert bindings[0].handler(context) is None

    state.record_persisting_effect(
        _warptide_grant_ability_effect(
            source=source,
            effect_id="warptide:shudderblink:assault-after-advance",
            target_unit_instance_id=_WARPTIDE_UNIT_ID,
            ability=warptide_ir.SHUDDERBLINK_ASSAULT_AFTER_ADVANCE_ABILITY,
        )
    )
    grant = bindings[0].handler(context)
    assert grant is not None
    assert grant.automatic is True
    with pytest.raises(GameLifecycleError, match="requires context"):
        bindings[0].handler(cast(AdvanceMoveContext, object()))


def test_warptide_battle_formation_handler_records_generic_rule_effects() -> None:
    state = _warptide_setup_state()
    source = _warptide_source(warptide_ir.WARPTIDE_DETACHMENT_RULE_DESCRIPTOR_ID)
    bindings = generic_detachment_effects.generic_detachment_rule_battle_formation_hook_bindings(
        activation=_warptide_activation(),
        execution_records=(source.record,),
    )
    decisions = DecisionController()
    request_handler = bindings[0].request_handler

    assert request_handler is not None
    assert (
        request_handler(
            BattleFormationRequestContext(
                state=state,
                decisions=decisions,
                config=_minimal_warptide_game_config(),
            )
        )
        is None
    )

    effects = state.persisting_effects_for_unit(_WARPTIDE_UNIT_ID)
    effect_abilities: set[str] = set()
    for effect in effects:
        payload = effect.effect_payload
        assert isinstance(payload, dict)
        rule_effect = payload["effect"]
        assert isinstance(rule_effect, dict)
        parameters = rule_effect["parameters"]
        assert isinstance(parameters, list)
        for parameter in parameters:
            assert isinstance(parameter, dict)
            if parameter.get("key") == "ability":
                value = parameter.get("value")
                assert isinstance(value, str)
                effect_abilities.add(value)
    assert effect_abilities == {
        warptide_ir.SHUDDERBLINK_ASSAULT_AFTER_ADVANCE_ABILITY,
        warptide_ir.SHUDDERBLINK_CHARGE_AFTER_ADVANCE_ABILITY,
    }
    assert decisions.event_log.records[-1].event_type == "generic_detachment_rule_effects_applied"

    request_handler(
        BattleFormationRequestContext(
            state=state,
            decisions=decisions,
            config=_minimal_warptide_game_config(),
        )
    )
    assert len(state.persisting_effects_for_unit(_WARPTIDE_UNIT_ID)) == 2


def test_warptide_advance_move_lifecycle_bindings_are_fail_fast() -> None:
    record = _warptide_source(warptide_ir.WARPTIDE_DETACHMENT_RULE_DESCRIPTOR_ID).record

    with pytest.raises(GameLifecycleError, match="require activation"):
        advance_move_lifecycle_hooks.advance_move_hook_bindings(
            activation=cast(RuntimeContentActivation, object()),
            execution_records=(record,),
        )
    with pytest.raises(GameLifecycleError, match="require execution records"):
        advance_move_lifecycle_hooks.advance_move_hook_bindings(
            activation=_warptide_activation(),
            execution_records=cast(
                tuple[faction_execution_2026_27.Phase17FExecutionRecord, ...],
                object(),
            ),
        )
    with pytest.raises(GameLifecycleError, match="require execution records"):
        advance_move_lifecycle_hooks.advance_move_hook_bindings(
            activation=_warptide_activation(),
            execution_records=cast(
                tuple[faction_execution_2026_27.Phase17FExecutionRecord, ...],
                (object(),),
            ),
        )
    with pytest.raises(GameLifecycleError, match="stale RuleIR hash"):
        advance_move_lifecycle_hooks.advance_move_hook_bindings(
            activation=_warptide_activation(),
            execution_records=(replace(record, rule_ir_hash="0" * 64),),
        )
    assert (
        advance_move_lifecycle_hooks.advance_move_hook_bindings(
            activation=RuntimeContentActivation(
                selected_faction_ids=(warptide_ir.CHAOS_DAEMONS_FACTION_ID,),
                selected_detachment_ids=(),
                selected_enhancement_ids=(),
                selected_stratagem_ids=(),
                selected_datasheet_ids=(),
                selected_wargear_ids=(),
                selected_weapon_profile_ids=(),
                selected_weapon_keywords=(),
                loaded_unit_instance_ids=(),
            ),
            execution_records=(record,),
        )
        == ()
    )


def test_advance_move_grant_payload_round_trips_automatic_default() -> None:
    grant = AdvanceMoveGrant(
        hook_id="warptide:auto-advance",
        source_id=warptide_ir.WARPTIDE_SOURCE_RULE_ID,
        label="Shudderblink",
        granted_ranged_weapon_keywords=(WeaponKeyword.ASSAULT.value,),
        automatic=True,
        replay_payload={"source": "warptide-test"},
    )

    payload = grant.to_payload()
    assert payload.get("automatic") is True
    assert AdvanceMoveGrant.from_payload(payload).automatic is True

    payload.pop("automatic")
    assert AdvanceMoveGrant.from_payload(payload).automatic is False


def test_warptide_shudderblink_advance_eligibility_grants_charge_after_advance() -> None:
    state = _warptide_state()
    source = _warptide_source(warptide_ir.WARPTIDE_DETACHMENT_RULE_DESCRIPTOR_ID)
    effect = _warptide_grant_ability_effect(
        source=source,
        effect_id="warptide:shudderblink:charge-after-advance",
        target_unit_instance_id=_WARPTIDE_UNIT_ID,
        ability=warptide_ir.SHUDDERBLINK_CHARGE_AFTER_ADVANCE_ABILITY,
    )
    state.record_persisting_effect(effect)
    matching_effects = generic_rule_ability_effects_for_unit(
        state=state,
        source=source,
        unit_instance_id=_WARPTIDE_UNIT_ID,
        ability=warptide_ir.SHUDDERBLINK_CHARGE_AFTER_ADVANCE_ABILITY,
    )
    descriptor = next(
        ability
        for ability in DEFAULT_GENERIC_RULE_ABILITY_REGISTRY.advance_eligibility_abilities
        if ability.ability_ids() == (warptide_ir.SHUDDERBLINK_CHARGE_AFTER_ADVANCE_ABILITY,)
    )
    context = AdvanceEligibilityContext(
        state=state,
        player_id="player-a",
        battle_round=1,
        unit_instance_id=_WARPTIDE_UNIT_ID,
        movement_request_id="warptide-advance-request",
        movement_result_id="warptide-advance-result",
    )

    assert descriptor.context_predicate(context, source, matching_effects)

    grant = descriptor.grant_builder(context, source, matching_effects)
    assert grant.hook_id == warptide_ir.SHUDDERBLINK_ADVANCE_ELIGIBILITY_HOOK_ID
    assert grant.source_id == warptide_ir.WARPTIDE_SOURCE_RULE_ID
    assert grant.can_shoot is True
    assert grant.can_declare_charge is True
    assert isinstance(grant.replay_payload, dict)
    assert grant.replay_payload["effect_kind"] == "shudderblink_advance_eligibility"


def test_warptide_shudderblink_advance_eligibility_predicate_rejects_wrong_contexts() -> None:
    state = _warptide_state()
    source = _warptide_source(warptide_ir.WARPTIDE_DETACHMENT_RULE_DESCRIPTOR_ID)
    effect = _warptide_grant_ability_effect(
        source=source,
        effect_id="warptide:shudderblink:charge-after-advance",
        target_unit_instance_id=_WARPTIDE_UNIT_ID,
        ability=warptide_ir.SHUDDERBLINK_CHARGE_AFTER_ADVANCE_ABILITY,
    )
    descriptor = next(
        ability
        for ability in DEFAULT_GENERIC_RULE_ABILITY_REGISTRY.advance_eligibility_abilities
        if ability.ability_ids() == (warptide_ir.SHUDDERBLINK_CHARGE_AFTER_ADVANCE_ABILITY,)
    )
    context = AdvanceEligibilityContext(
        state=state,
        player_id="player-a",
        battle_round=1,
        unit_instance_id=_WARPTIDE_UNIT_ID,
        movement_request_id="warptide-advance-request",
        movement_result_id="warptide-advance-result",
    )

    assert not descriptor.context_predicate(context, source, ())
    with pytest.raises(GameLifecycleError, match="requires context"):
        descriptor.context_predicate(cast(AdvanceEligibilityContext, object()), source, (effect,))
    with pytest.raises(GameLifecycleError, match="requires source"):
        descriptor.context_predicate(
            context,
            cast(GenericRuleAbilitySource, object()),
            (effect,),
        )
    with pytest.raises(GameLifecycleError, match="hook ID requires source"):
        descriptor.hook_id(cast(GenericRuleAbilitySource, object()))


def test_warptide_soul_hungry_cost_modifier_reduces_core_reactive_stratagems() -> None:
    state = _warptide_state()
    source = _warptide_source(warptide_ir.SOUL_HUNGRY_SLAUGHTERERS_DESCRIPTOR_ID)
    effect = _warptide_grant_ability_effect(
        source=source,
        effect_id="warptide:soul-hungry:cost",
        target_unit_instance_id=_WARPTIDE_UNIT_ID,
        ability=warptide_ir.SOUL_HUNGRY_SLAUGHTERERS_COST_ABILITY,
    )
    state.record_persisting_effect(effect)
    descriptor = next(
        ability
        for ability in DEFAULT_GENERIC_RULE_ABILITY_REGISTRY.stratagem_cost_modifier_abilities
        if ability.ability_ids() == (warptide_ir.SOUL_HUNGRY_SLAUGHTERERS_COST_ABILITY,)
    )
    context = _warptide_cost_modifier_context(state=state, target_unit_id=_WARPTIDE_UNIT_ID)

    assert descriptor.context_predicate(context, source)
    assert descriptor.modifier_builder(context, source) == 0

    enemy_context = _warptide_cost_modifier_context(state=state, target_unit_id=_ENEMY_UNIT_ID)
    assert not descriptor.context_predicate(enemy_context, source)


def test_warptide_soul_hungry_cost_modifier_rejects_wrong_contexts() -> None:
    state = _warptide_state()
    source = _warptide_source(warptide_ir.SOUL_HUNGRY_SLAUGHTERERS_DESCRIPTOR_ID)
    descriptor = next(
        ability
        for ability in DEFAULT_GENERIC_RULE_ABILITY_REGISTRY.stratagem_cost_modifier_abilities
        if ability.ability_ids() == (warptide_ir.SOUL_HUNGRY_SLAUGHTERERS_COST_ABILITY,)
    )
    context = _warptide_cost_modifier_context(state=state, target_unit_id=_WARPTIDE_UNIT_ID)

    with pytest.raises(GameLifecycleError, match="requires context"):
        descriptor.context_predicate(cast(StratagemCostModifierContext, object()), source)
    with pytest.raises(GameLifecycleError, match="requires source"):
        descriptor.context_predicate(context, cast(GenericRuleAbilitySource, object()))
    with pytest.raises(GameLifecycleError, match="requires context"):
        descriptor.modifier_builder(cast(StratagemCostModifierContext, object()), source)
    with pytest.raises(GameLifecycleError, match="requires source"):
        descriptor.modifier_builder(context, cast(GenericRuleAbilitySource, object()))
    with pytest.raises(GameLifecycleError, match="modifier ID requires source"):
        descriptor.modifier_id(cast(GenericRuleAbilitySource, object()))
    assert descriptor.modifier_builder(replace(context, current_command_point_cost=0), source) == 0


def test_default_generic_rule_ability_registry_maps_shadow_legion_enhancement_grants() -> None:
    registry = DEFAULT_GENERIC_RULE_ABILITY_REGISTRY

    leaping_source = _shadow_legion_enhancement_source(
        shadow_legion_ir.LEAPING_SHADOWS_ENHANCEMENT_DESCRIPTOR_ID
    )
    leaping = next(
        ability
        for ability in registry.enhancement_effect_abilities
        if ability.ability_ids() == (shadow_legion_ir.LEAPING_SHADOWS_SCOUTS_ABILITY,)
    )
    assert leaping.hook_family is GenericRuleAbilityHookFamily.ENHANCEMENT_EFFECT
    assert leaping.ability_ids() == (shadow_legion_ir.LEAPING_SHADOWS_SCOUTS_ABILITY,)
    assert (
        leaping.coverage_descriptor_id == shadow_legion_ir.LEAPING_SHADOWS_ENHANCEMENT_DESCRIPTOR_ID
    )
    assert leaping.source_rule_id == shadow_legion_ir.LEAPING_SHADOWS_SOURCE_RULE_ID
    assert leaping.enhancement_id == shadow_legion_ir.LEAPING_SHADOWS_ENHANCEMENT_ID
    assert leaping.effect_id(leaping_source) == (
        "warhammer_40000_11th:chaos_daemons:detachment:shadow_legion:"
        "enhancement:leaping_shadows:scouts_9"
    )

    mantle_source = _shadow_legion_enhancement_source(
        shadow_legion_ir.MANTLE_OF_GLOOM_ENHANCEMENT_DESCRIPTOR_ID
    )
    mantle = registry.objective_control_modifier_abilities[0]
    assert mantle.hook_family is GenericRuleAbilityHookFamily.OBJECTIVE_CONTROL_MODIFIER
    assert mantle.ability_ids() == (shadow_legion_ir.MANTLE_OF_GLOOM_OBJECTIVE_CONTROL_ABILITY,)
    assert (
        mantle.coverage_descriptor_id == shadow_legion_ir.MANTLE_OF_GLOOM_ENHANCEMENT_DESCRIPTOR_ID
    )
    assert mantle.source_rule_id == shadow_legion_ir.MANTLE_OF_GLOOM_SOURCE_RULE_ID
    assert mantle.modifier_id(mantle_source) == (
        "warhammer_40000_11th:chaos_daemons:detachment:shadow_legion:"
        "enhancement:mantle_of_gloom:objective-control"
    )

    fade_source = _shadow_legion_enhancement_source(
        shadow_legion_ir.FADE_TO_DARKNESS_ENHANCEMENT_DESCRIPTOR_ID
    )
    unit_destroyed = registry.unit_destroyed_abilities[0]
    assert unit_destroyed.hook_family is GenericRuleAbilityHookFamily.UNIT_DESTROYED
    assert unit_destroyed.ability_ids() == (shadow_legion_ir.FADE_TO_DARKNESS_RESERVES_ABILITY,)
    assert (
        unit_destroyed.coverage_descriptor_id
        == shadow_legion_ir.FADE_TO_DARKNESS_ENHANCEMENT_DESCRIPTOR_ID
    )
    assert unit_destroyed.source_rule_id == shadow_legion_ir.FADE_TO_DARKNESS_SOURCE_RULE_ID
    assert unit_destroyed.hook_id(fade_source) == (
        "warhammer_40000_11th:chaos_daemons:detachment:shadow_legion:"
        "enhancement:fade_to_darkness:unit-destroyed"
    )

    turn_end = registry.turn_end_abilities[0]
    assert turn_end.hook_family is GenericRuleAbilityHookFamily.TURN_END
    assert turn_end.ability_ids() == (shadow_legion_ir.FADE_TO_DARKNESS_RESERVES_ABILITY,)
    assert (
        turn_end.coverage_descriptor_id
        == shadow_legion_ir.FADE_TO_DARKNESS_ENHANCEMENT_DESCRIPTOR_ID
    )
    assert turn_end.source_rule_id == shadow_legion_ir.FADE_TO_DARKNESS_SOURCE_RULE_ID
    assert turn_end.hook_id(fade_source) == (
        "warhammer_40000_11th:chaos_daemons:detachment:shadow_legion:"
        "enhancement:fade_to_darkness:turn-end-reserves"
    )

    malice_source = _shadow_legion_enhancement_source(
        shadow_legion_ir.MALICE_MADE_MANIFEST_ENHANCEMENT_DESCRIPTOR_ID
    )
    fight_start = registry.fight_phase_start_abilities[0]
    assert fight_start.hook_family is GenericRuleAbilityHookFamily.FIGHT_PHASE_START
    assert fight_start.ability_ids() == (
        shadow_legion_ir.MALICE_MADE_MANIFEST_MORTAL_WOUNDS_ABILITY,
    )
    assert (
        fight_start.coverage_descriptor_id
        == shadow_legion_ir.MALICE_MADE_MANIFEST_ENHANCEMENT_DESCRIPTOR_ID
    )
    assert fight_start.source_rule_id == shadow_legion_ir.MALICE_MADE_MANIFEST_SOURCE_RULE_ID
    assert fight_start.hook_id(malice_source) == (
        "warhammer_40000_11th:chaos_daemons:detachment:shadow_legion:"
        "enhancement:malice_made_manifest"
    )

    malice_fnp = next(
        descriptor
        for descriptor in registry.mortal_wound_feel_no_pain_abilities
        if descriptor.coverage_descriptor_id
        == shadow_legion_ir.MALICE_MADE_MANIFEST_ENHANCEMENT_DESCRIPTOR_ID
    )
    assert (
        malice_fnp.hook_family
        is GenericRuleAbilityHookFamily.MORTAL_WOUND_FEEL_NO_PAIN_CONTINUATION
    )
    assert malice_fnp.ability_ids() == (
        shadow_legion_ir.MALICE_MADE_MANIFEST_MORTAL_WOUNDS_ABILITY,
    )
    assert malice_fnp.source_rule_id == shadow_legion_ir.MALICE_MADE_MANIFEST_SOURCE_RULE_ID
    assert malice_fnp.source_kind == shadow_legion_ir.MALICE_MADE_MANIFEST_MORTAL_WOUNDS_SOURCE_KIND
    assert malice_fnp.hook_id(malice_source) == (
        "warhammer_40000_11th:chaos_daemons:detachment:shadow_legion:"
        "enhancement:malice_made_manifest:mortal-wound-fnp"
    )


def test_default_generic_rule_ability_registry_maps_corsair_coterie_enhancement_grants() -> None:
    registry = DEFAULT_GENERIC_RULE_ABILITY_REGISTRY

    archraider_source = _aeldari_corsair_coterie_source(
        corsair_ir.ARCHRAIDER_ENHANCEMENT_DESCRIPTOR_ID
    )
    archraider = next(
        descriptor
        for descriptor in registry.enhancement_effect_abilities
        if descriptor.ability_ids() == (corsair_ir.ARCHRAIDER_MARKER_ABILITY,)
    )
    assert archraider.hook_family is GenericRuleAbilityHookFamily.ENHANCEMENT_EFFECT
    assert archraider.source_rule_id == corsair_ir.ARCHRAIDER_SOURCE_RULE_ID
    assert archraider.enhancement_id == corsair_ir.ARCHRAIDER_ENHANCEMENT_ID
    assert archraider.effect_id(archraider_source) == corsair_enhancements.ARCHRAIDER_EFFECT_ID

    archraider_setup = next(
        descriptor
        for descriptor in registry.battle_formation_abilities
        if descriptor.ability_ids() == (corsair_ir.ARCHRAIDER_MODEL_SELECTION_ABILITY,)
    )
    assert archraider_setup.hook_family is GenericRuleAbilityHookFamily.BATTLE_FORMATION
    assert archraider_setup.source_rule_id == corsair_ir.ARCHRAIDER_SOURCE_RULE_ID
    assert (
        archraider_setup.hook_id(archraider_source) == corsair_enhancements.ARCHRAIDER_SETUP_HOOK_ID
    )

    archraider_cost_choice = next(
        descriptor
        for descriptor in registry.stratagem_cost_choice_abilities
        if descriptor.ability_ids() == (corsair_ir.ARCHRAIDER_STRATAGEM_COST_CHOICE_ABILITY,)
    )
    assert archraider_cost_choice.hook_family is GenericRuleAbilityHookFamily.STRATAGEM_COST_CHOICE
    assert archraider_cost_choice.source_rule_id == corsair_ir.ARCHRAIDER_SOURCE_RULE_ID
    assert (
        archraider_cost_choice.hook_id(archraider_source)
        == corsair_enhancements.ARCHRAIDER_COST_CHOICE_HOOK_ID
    )

    archraider_cost_modifier = next(
        descriptor
        for descriptor in registry.stratagem_cost_modifier_abilities
        if descriptor.ability_ids() == (corsair_ir.ARCHRAIDER_STRATAGEM_COST_MODIFIER_ABILITY,)
    )
    assert (
        archraider_cost_modifier.hook_family is GenericRuleAbilityHookFamily.STRATAGEM_COST_MODIFIER
    )
    assert archraider_cost_modifier.source_rule_id == corsair_ir.ARCHRAIDER_SOURCE_RULE_ID
    assert (
        archraider_cost_modifier.modifier_id(archraider_source)
        == corsair_enhancements.ARCHRAIDER_COST_MODIFIER_ID
    )

    infamy_source = _aeldari_corsair_coterie_source(corsair_ir.INFAMY_ENHANCEMENT_DESCRIPTOR_ID)
    infamy = next(
        descriptor
        for descriptor in registry.enhancement_effect_abilities
        if descriptor.ability_ids() == (corsair_ir.INFAMY_MARKER_ABILITY,)
    )
    assert infamy.source_rule_id == corsair_ir.INFAMY_SOURCE_RULE_ID
    assert infamy.enhancement_id == corsair_ir.INFAMY_ENHANCEMENT_ID
    assert infamy.effect_id(infamy_source) == corsair_enhancements.INFAMY_EFFECT_ID

    infamy_oc = next(
        descriptor
        for descriptor in registry.objective_control_modifier_abilities
        if descriptor.ability_ids() == (corsair_ir.INFAMY_OBJECTIVE_CONTROL_ABILITY,)
    )
    assert infamy_oc.hook_family is GenericRuleAbilityHookFamily.OBJECTIVE_CONTROL_MODIFIER
    assert infamy_oc.source_rule_id == corsair_ir.INFAMY_SOURCE_RULE_ID
    assert (
        infamy_oc.modifier_id(infamy_source)
        == corsair_enhancements.INFAMY_OBJECTIVE_CONTROL_MODIFIER_ID
    )

    voidstone_source = _aeldari_corsair_coterie_source(
        corsair_ir.VOIDSTONE_ENHANCEMENT_DESCRIPTOR_ID
    )
    voidstone = next(
        descriptor
        for descriptor in registry.enhancement_effect_abilities
        if descriptor.ability_ids() == (corsair_ir.VOIDSTONE_MARKER_ABILITY,)
    )
    assert voidstone.source_rule_id == corsair_ir.VOIDSTONE_SOURCE_RULE_ID
    assert voidstone.enhancement_id == corsair_ir.VOIDSTONE_ENHANCEMENT_ID
    assert voidstone.effect_id(voidstone_source) == corsair_enhancements.VOIDSTONE_EFFECT_ID

    voidstone_save = next(
        descriptor
        for descriptor in registry.save_option_modifier_abilities
        if descriptor.ability_ids() == (corsair_ir.VOIDSTONE_SAVE_OPTION_ABILITY,)
    )
    assert voidstone_save.hook_family is GenericRuleAbilityHookFamily.SAVE_OPTION_MODIFIER
    assert voidstone_save.source_rule_id == corsair_ir.VOIDSTONE_SOURCE_RULE_ID
    assert (
        voidstone_save.modifier_id(voidstone_source)
        == corsair_enhancements.VOIDSTONE_SAVE_MODIFIER_ID
    )

    webway_source = _aeldari_corsair_coterie_source(
        corsair_ir.WEBWAY_PATHSTONE_ENHANCEMENT_DESCRIPTOR_ID
    )
    webway = next(
        descriptor
        for descriptor in registry.enhancement_effect_abilities
        if descriptor.ability_ids() == (corsair_ir.WEBWAY_PATHSTONE_MARKER_ABILITY,)
    )
    assert webway.source_rule_id == corsair_ir.WEBWAY_PATHSTONE_SOURCE_RULE_ID
    assert webway.enhancement_id == corsair_ir.WEBWAY_PATHSTONE_ENHANCEMENT_ID
    assert webway.effect_id(webway_source) == corsair_enhancements.WEBWAY_PATHSTONE_EFFECT_ID

    webway_deep_strike = next(
        descriptor
        for descriptor in registry.enhancement_effect_abilities
        if descriptor.ability_ids() == (corsair_ir.WEBWAY_PATHSTONE_DEEP_STRIKE_ABILITY,)
    )
    assert webway_deep_strike.source_rule_id == corsair_ir.WEBWAY_PATHSTONE_SOURCE_RULE_ID
    assert webway_deep_strike.enhancement_id == corsair_ir.WEBWAY_PATHSTONE_ENHANCEMENT_ID
    assert (
        webway_deep_strike.effect_id(webway_source)
        == corsair_enhancements.WEBWAY_PATHSTONE_DEEP_STRIKE_EFFECT_ID
    )

    webway_turn_end = next(
        descriptor
        for descriptor in registry.turn_end_abilities
        if descriptor.ability_ids() == (corsair_ir.WEBWAY_PATHSTONE_RESERVES_ABILITY,)
    )
    assert webway_turn_end.hook_family is GenericRuleAbilityHookFamily.TURN_END
    assert webway_turn_end.source_rule_id == corsair_ir.WEBWAY_PATHSTONE_SOURCE_RULE_ID
    assert (
        webway_turn_end.hook_id(webway_source)
        == corsair_enhancements.WEBWAY_PATHSTONE_TURN_END_HOOK_ID
    )


def test_default_generic_rule_ability_registry_maps_court_detachment_cost_grant() -> None:
    registry = DEFAULT_GENERIC_RULE_ABILITY_REGISTRY
    source = _court_of_the_phoenician_source()

    master_of_the_pageant = next(
        descriptor
        for descriptor in registry.stratagem_cost_modifier_abilities
        if descriptor.ability_ids()
        == (court_ir.MASTER_OF_THE_PAGEANT_STRATAGEM_COST_REDUCTION_ABILITY,)
    )

    assert master_of_the_pageant.hook_family is GenericRuleAbilityHookFamily.STRATAGEM_COST_MODIFIER
    assert master_of_the_pageant.coverage_descriptor_id == (
        court_ir.COURT_OF_THE_PHOENICIAN_DETACHMENT_RULE_DESCRIPTOR_ID
    )
    assert master_of_the_pageant.source_rule_id == court_rule.COURT_OF_THE_PHOENICIAN_RULE_SOURCE_ID
    assert (
        master_of_the_pageant.modifier_id(source)
        == court_rule.MASTER_OF_THE_PAGEANT_COST_MODIFIER_ID
    )


def test_court_runtime_contribution_delegates_cost_modifier_to_generic_ir() -> None:
    contribution = court_rule.runtime_contribution()

    assert contribution.contribution_id == court_rule.CONTRIBUTION_ID
    assert contribution.stratagem_cost_modifier_bindings == ()


def test_generic_rule_ability_registry_rejects_duplicate_descriptors() -> None:
    descriptor = DEFAULT_GENERIC_RULE_ABILITY_REGISTRY.advance_eligibility_abilities[0]

    with pytest.raises(GameLifecycleError, match="descriptors must be unique"):
        GenericRuleAbilityRegistry(advance_eligibility_abilities=(descriptor, descriptor))


def test_generic_rule_ability_source_validates_rule_ir_hash() -> None:
    source = _shadow_legion_source()
    stale_record = replace(source.record, rule_ir_hash="0" * 64)

    with pytest.raises(GameLifecycleError, match="stale RuleIR hash"):
        GenericRuleAbilitySource(record=stale_record, rule_ir=source.rule_ir)


def test_rule_ir_grants_any_ability_uses_grant_ability_parameters() -> None:
    source = _shadow_legion_source()

    assert rule_ir_grants_any_ability(
        source.rule_ir,
        abilities=(shadow_legion_ir.SNAP_SHOOTING_TARGET_FORBIDDEN_ABILITY,),
    )
    assert not rule_ir_grants_any_ability(source.rule_ir, abilities=("missing_ability",))


def test_generic_rule_ability_effects_for_unit_enforces_required_keyword_any() -> None:
    state = _keyword_any_state()
    source = _aeldari_path_of_the_outcast_source(
        path_outcast_ir.ASSASSINS_EYE_ENHANCEMENT_DESCRIPTOR_ID
    )
    required_keywords = (path_outcast_ir.RANGERS_KEYWORD, path_outcast_ir.SHROUD_RUNNERS_KEYWORD)
    ranger_effect = _grant_ability_effect(
        source=source,
        effect_id="generic-keyword-any:rangers",
        target_unit_instance_id=_RANGERS_UNIT_ID,
        ability=path_outcast_ir.ASSASSINS_EYE_CHARACTER_AP_BONUS_ABILITY,
        required_keyword_any=required_keywords,
    )
    shroud_runner_effect = _grant_ability_effect(
        source=source,
        effect_id="generic-keyword-any:shroud-runners",
        target_unit_instance_id=_SHROUD_RUNNERS_UNIT_ID,
        ability=path_outcast_ir.ASSASSINS_EYE_CHARACTER_AP_BONUS_ABILITY,
        required_keyword_any=required_keywords,
    )
    enemy_effect = _grant_ability_effect(
        source=source,
        effect_id="generic-keyword-any:enemy",
        target_unit_instance_id=_ENEMY_UNIT_ID,
        ability=path_outcast_ir.ASSASSINS_EYE_CHARACTER_AP_BONUS_ABILITY,
        required_keyword_any=required_keywords,
    )
    for effect in (ranger_effect, shroud_runner_effect, enemy_effect):
        state.record_persisting_effect(effect)

    assert generic_rule_ability_effects_for_unit(
        state=state,
        source=source,
        unit_instance_id=_RANGERS_UNIT_ID,
        ability=path_outcast_ir.ASSASSINS_EYE_CHARACTER_AP_BONUS_ABILITY,
    ) == (ranger_effect,)
    assert generic_rule_ability_effects_for_unit(
        state=state,
        source=source,
        unit_instance_id=_SHROUD_RUNNERS_UNIT_ID,
        ability=path_outcast_ir.ASSASSINS_EYE_CHARACTER_AP_BONUS_ABILITY,
    ) == (shroud_runner_effect,)
    assert (
        generic_rule_ability_effects_for_unit(
            state=state,
            source=source,
            unit_instance_id=_ENEMY_UNIT_ID,
            ability=path_outcast_ir.ASSASSINS_EYE_CHARACTER_AP_BONUS_ABILITY,
        )
        == ()
    )


def test_generic_rule_ability_effects_for_unit_rejects_empty_required_keyword_any() -> None:
    state = _keyword_any_state()
    source = _aeldari_path_of_the_outcast_source(
        path_outcast_ir.ASSASSINS_EYE_ENHANCEMENT_DESCRIPTOR_ID
    )
    effect = _grant_ability_effect(
        source=source,
        effect_id="generic-keyword-any:empty",
        target_unit_instance_id=_RANGERS_UNIT_ID,
        ability=path_outcast_ir.ASSASSINS_EYE_CHARACTER_AP_BONUS_ABILITY,
        required_keyword_any=(),
    )
    state.record_persisting_effect(effect)

    with pytest.raises(GameLifecycleError, match="required_keyword_any must not be empty"):
        generic_rule_ability_effects_for_unit(
            state=state,
            source=source,
            unit_instance_id=_RANGERS_UNIT_ID,
            ability=path_outcast_ir.ASSASSINS_EYE_CHARACTER_AP_BONUS_ABILITY,
        )


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
        current_command_point_cost=1,
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
