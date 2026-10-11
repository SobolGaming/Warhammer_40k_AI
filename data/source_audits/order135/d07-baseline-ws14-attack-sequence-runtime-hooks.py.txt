from __future__ import annotations

from dataclasses import replace

import pytest
from tests.fight_on_death_helpers import retain_destroyed_model_for_fixture
from tests.generic_modifier_helpers import generic_effect as _generic_effect
from tests.unit_keyword_helpers import with_unit_keywords

from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.core.ruleset_descriptor import BattlePhaseKind, RulesetDescriptor
from warhammer40k_core.core.weapon_profiles import (
    AbilityKind,
    RangeProfile,
    WeaponKeyword,
    WeaponProfile,
)
from warhammer40k_core.engine.army_mustering import ArmyDefinition
from warhammer40k_core.engine.attached_unit_formation import AttachedUnitFormation
from warhammer40k_core.engine.critical_wounds import (
    WoundRollCriticalThresholdContext,
    generic_rule_critical_wound_threshold,
)
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.effects import (
    GENERIC_RULE_EFFECT_KIND,
    EffectExpirationBoundary,
)
from warhammer40k_core.engine.event_log import JsonValue
from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.generic_rule_attack_conditions import (
    generic_rule_target_proximity_keyword_gate_applies,
)
from warhammer40k_core.engine.list_validation import (
    DetachmentSelection,
    UnitMusterSelection,
)
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError, GameLifecycleStage
from warhammer40k_core.engine.placement import create_deterministic_battlefield_scenario
from warhammer40k_core.engine.runtime_modifiers import (
    DamageRollModifierContext,
    HitRollMinimumUnmodifiedSuccessContext,
    HitRollModifierContext,
    RuntimeModifierRegistry,
    SaveOptionModifierContext,
    WeaponProfileModifierContext,
    WoundRollModifierContext,
)
from warhammer40k_core.engine.saves import SaveKind, SaveOption
from warhammer40k_core.engine.source_backed_rerolls import (
    source_backed_reroll_permission_context_for_unit,
)
from warhammer40k_core.engine.unit_factory import UnitFactory, UnitInstance
from warhammer40k_core.engine.wargear_selections import (
    ModelProfileSelection,
    WargearSelection,
)
from warhammer40k_core.engine.weapon_abilities import FIRE_OVERWATCH_RULE_ID
from warhammer40k_core.geometry.pose import Pose


def test_ws14_generic_attack_roll_hooks_bind_attacker_and_target_roles() -> None:
    catalog = ArmyCatalog.phase9a_canonical_content_pack()
    attacker = _unit(catalog=catalog, army_id="army-a", unit_selection_id="attacker-unit")
    defender = _unit(catalog=catalog, army_id="army-b", unit_selection_id="defender-unit")
    state = _state(
        _army(catalog=catalog, player_id="player-a", army_id="army-a", unit=attacker),
        _army(catalog=catalog, player_id="player-b", army_id="army-b", unit=defender),
    )
    profile = _weapon_profile(catalog, attacker.own_models[0].wargear_ids[0])
    registry = RuntimeModifierRegistry.empty()

    state.record_persisting_effect(
        _generic_effect(
            effect_id="ws14:attacker-hit-bonus",
            owner_player_id="player-a",
            target_unit_instance_ids=(attacker.unit_instance_id,),
            target_kind="this_unit",
            effect_kind="modify_dice_roll",
            parameters={"roll_type": "hit", "delta": 1},
        )
    )
    state.record_persisting_effect(
        _generic_effect(
            effect_id="ws14:defender-hit-penalty",
            owner_player_id="player-b",
            target_unit_instance_ids=(defender.unit_instance_id,),
            target_kind="this_unit",
            effect_kind="modify_dice_roll",
            parameters={"roll_type": "hit", "delta": -1},
        )
    )

    assert (
        registry.hit_roll_modifier(
            HitRollModifierContext(
                state=state,
                attacking_unit_instance_id=attacker.unit_instance_id,
                attacker_model_instance_id=attacker.own_models[0].model_instance_id,
                target_unit_instance_id=defender.unit_instance_id,
                weapon_profile=profile,
                source_phase=BattlePhase.SHOOTING,
            )
        )
        == 0
    )
    assert (
        registry.hit_roll_modifier(
            HitRollModifierContext(
                state=state,
                attacking_unit_instance_id=defender.unit_instance_id,
                attacker_model_instance_id=defender.own_models[0].model_instance_id,
                target_unit_instance_id=attacker.unit_instance_id,
                weapon_profile=profile,
                source_phase=BattlePhase.SHOOTING,
            )
        )
        == 0
    )


def test_ws14_generic_selected_target_wound_and_damage_hooks_use_explicit_attack_role() -> None:
    catalog = ArmyCatalog.phase9a_canonical_content_pack()
    attacker = _unit(catalog=catalog, army_id="army-a", unit_selection_id="attacker-unit")
    defender = _unit(catalog=catalog, army_id="army-b", unit_selection_id="defender-unit")
    state = _state(
        _army(catalog=catalog, player_id="player-a", army_id="army-a", unit=attacker),
        _army(catalog=catalog, player_id="player-b", army_id="army-b", unit=defender),
    )
    profile = _weapon_profile(catalog, attacker.own_models[0].wargear_ids[0])
    registry = RuntimeModifierRegistry.empty()

    state.record_persisting_effect(
        _generic_effect(
            effect_id="ws14:selected-target-wound",
            owner_player_id="player-a",
            target_unit_instance_ids=(defender.unit_instance_id,),
            target_kind="selected_target",
            effect_kind="modify_dice_roll",
            parameters={"roll_type": "wound", "delta": 1, "attack_role": "target"},
        )
    )
    state.record_persisting_effect(
        _generic_effect(
            effect_id="ws14:selected-target-damage",
            owner_player_id="player-a",
            target_unit_instance_ids=(defender.unit_instance_id,),
            target_kind="selected_target",
            effect_kind="modify_dice_roll",
            parameters={"roll_type": "damage", "delta": 2, "attack_role": "target"},
        )
    )

    assert (
        registry.wound_roll_modifier(
            WoundRollModifierContext(
                state=state,
                source_phase=BattlePhase.SHOOTING,
                attacking_unit_instance_id=attacker.unit_instance_id,
                attacker_model_instance_id=attacker.own_models[0].model_instance_id,
                target_unit_instance_id=defender.unit_instance_id,
                weapon_profile=profile,
                strength=4,
                toughness=4,
            )
        )
        == 1
    )
    assert (
        registry.damage_roll_modifier(
            DamageRollModifierContext(
                state=state,
                source_phase=BattlePhase.SHOOTING,
                attacking_unit_instance_id=attacker.unit_instance_id,
                attacker_model_instance_id=attacker.own_models[0].model_instance_id,
                target_unit_instance_id=defender.unit_instance_id,
                weapon_profile=profile,
                current_value=3,
            )
        )
        == 2
    )


@pytest.mark.parametrize("roll_type", ["wound", "damage"])
def test_order93_opposing_attack_roll_sources_survive_net_zero(roll_type: str) -> None:
    catalog = ArmyCatalog.phase9a_canonical_content_pack()
    attacker = _unit(catalog=catalog, army_id="army-a", unit_selection_id="attacker-unit")
    defender = _unit(catalog=catalog, army_id="army-b", unit_selection_id="defender-unit")
    state = _state(
        _army(catalog=catalog, player_id="player-a", army_id="army-a", unit=attacker),
        _army(catalog=catalog, player_id="player-b", army_id="army-b", unit=defender),
    )
    profile = _weapon_profile(catalog, attacker.own_models[0].wargear_ids[0])
    for identity, delta in (("bonus", 1), ("penalty", -1)):
        state.record_persisting_effect(
            _generic_effect(
                effect_id=f"order93:{identity}",
                owner_player_id="player-a",
                target_unit_instance_ids=(attacker.unit_instance_id,),
                target_kind="this_unit",
                effect_kind="modify_dice_roll",
                parameters={"roll_type": roll_type, "delta": delta, "attack_role": "attacker"},
            )
        )
    registry = RuntimeModifierRegistry.empty()
    if roll_type == "wound":
        terms = registry.wound_roll_modifiers(
            WoundRollModifierContext(
                state=state,
                source_phase=BattlePhase.SHOOTING,
                attacking_unit_instance_id=attacker.unit_instance_id,
                attacker_model_instance_id=attacker.own_models[0].model_instance_id,
                target_unit_instance_id=defender.unit_instance_id,
                weapon_profile=profile,
                strength=4,
                toughness=4,
            )
        )
    else:
        terms = registry.damage_roll_modifiers(
            DamageRollModifierContext(
                state=state,
                source_phase=BattlePhase.SHOOTING,
                attacking_unit_instance_id=attacker.unit_instance_id,
                attacker_model_instance_id=attacker.own_models[0].model_instance_id,
                target_unit_instance_id=defender.unit_instance_id,
                weapon_profile=profile,
                current_value=3,
            )
        )
    assert len(terms) == 2
    assert {term.operand for term in terms} == {-1, 1}
    assert sum(term.operand for term in terms) == 0
    assert len({term.modifier_id for term in terms}) == 2
    assert all(term.source_id is not None for term in terms)


def test_order93_save_roll_operations_do_not_change_characteristic_and_survive_ap() -> None:
    from warhammer40k_core.engine.generic_rule_save_modifiers import (
        generic_rule_save_option_with_roll_modifier,
    )
    from warhammer40k_core.engine.saves import save_option_with_armor_penetration_modifier

    original = SaveOption(SaveKind.ARMOUR, 5, 3, -2)
    bonus = generic_rule_save_option_with_roll_modifier(original, 1, "source:save-bonus")
    cancelled = generic_rule_save_option_with_roll_modifier(bonus, -1, "source:save-penalty")
    assert cancelled.characteristic_target_number == 3
    assert cancelled.target_number == 5
    assert tuple(term.operand for term in cancelled.roll_modifiers) == (1, -1)
    assert SaveOption.from_payload(cancelled.to_payload()) == cancelled
    ap_changed = save_option_with_armor_penetration_modifier(
        bonus, delta=1, source_rule_id="source:ap-bonus"
    )
    assert ap_changed.characteristic_target_number == 3
    assert ap_changed.armor_penetration == -1
    assert ap_changed.target_number == 3
    assert ap_changed.roll_modifiers == bonus.roll_modifiers
    assert ap_changed.armor_penetration_trace is not None
    assert ap_changed.armor_penetration_trace.source_value == -2
    assert ap_changed.armor_penetration_trace.modifiers[0].source_id == "source:ap-bonus"


def test_order93_save_operations_bound_once_and_resolve_independent_subsets() -> None:
    from warhammer40k_core.core.attributes import Characteristic
    from warhammer40k_core.core.modifiers import ModifierOperation, ModifierTerm
    from warhammer40k_core.engine.save_modifier_operations import (
        save_option_ignoring_modifiers,
        save_option_with_characteristic_terms,
    )
    from warhammer40k_core.engine.saves import save_option_with_armor_penetration_modifier

    option = SaveOption(SaveKind.ARMOUR, 5, 3, -2)
    for identity, delta in (("bonus", -2), ("penalty", 2)):
        option = save_option_with_characteristic_terms(
            option,
            characteristic=Characteristic.SAVE,
            terms=(ModifierTerm(ModifierOperation.ADD, delta),),
            source_id=f"source:{identity}",
            modifier_id=f"save:{identity}",
        )
    assert option.characteristic_target_number == 3
    assert (
        save_option_ignoring_modifiers(option, ("save:penalty",)).characteristic_target_number == 2
    )
    assert save_option_ignoring_modifiers(option, ("save:bonus",)).characteristic_target_number == 5
    for identity, delta in (("improve", 3), ("worsen", -2)):
        option = save_option_with_armor_penetration_modifier(
            option, delta=delta, source_rule_id=f"source:{identity}", modifier_id=f"ap:{identity}"
        )
    assert option.armor_penetration == -1
    assert save_option_ignoring_modifiers(option, ("ap:improve",)).armor_penetration == -4
    assert SaveOption.from_payload(option.to_payload()) == option
    payload = option.to_payload()
    payload["target_number"] = 99
    with pytest.raises(GameLifecycleError, match="arithmetic"):
        SaveOption.from_payload(payload)
    with pytest.raises(GameLifecycleError, match="unknown or duplicated"):
        save_option_ignoring_modifiers(option, ("invented",))


@pytest.mark.parametrize("save_kind", [SaveKind.ARMOUR, SaveKind.INVULNERABLE])
@pytest.mark.parametrize("assigned", [1, 2, 6, 7])
def test_order93_save_roll_modifiers_preserve_unmodified_one_and_assigned_results(
    save_kind: SaveKind,
    assigned: int,
) -> None:
    from warhammer40k_core.core.dice import DiceRollResult, DiceRollState
    from warhammer40k_core.engine.generic_rule_save_modifiers import (
        generic_rule_save_option_with_roll_modifier,
    )
    from warhammer40k_core.engine.saves import resolve_saving_throw, saving_throw_roll_spec

    spec = saving_throw_roll_spec(
        save_kind=save_kind,
        player_id="defender",
        allocated_model_id="model",
        attack_context_id="order93:save",
    )
    roll = DiceRollState.from_result(
        DiceRollResult.from_values(
            roll_id="order93:save",
            spec=spec,
            values=(2,),
            source="fixed",
        )
    ).with_result_override(
        decision_id="assigned-result",
        request_id="assigned-request",
        source_rule_id="gw-11e-core-dice-results:treated-as-set-to",
        replacement_value=assigned,
    )
    option = generic_rule_save_option_with_roll_modifier(
        SaveOption(save_kind, 3, 3, 0),
        1,
        "source:save-bonus",
    )
    resolved = resolve_saving_throw(roll_state=roll, option=option)
    assert resolved.successful is (assigned != 1)
    assert resolved.unmodified_roll == assigned
    assert resolved.final_roll == assigned + 1
    assert resolved.target_number == 3


def test_order93_damage_keeps_profile_melta_and_allocated_operations_until_bound() -> None:
    from warhammer40k_core.core.attributes import Characteristic
    from warhammer40k_core.core.modifiers import ModifierOperation, ModifierTerm
    from warhammer40k_core.core.weapon_profiles import DamageProfile
    from warhammer40k_core.engine.allocated_attack_damage_modifiers import (
        AllocatedAttackDamageModifierBinding,
        AllocatedAttackDamageModifierContext,
    )
    from warhammer40k_core.engine.attack_sequence_geometry_targets import _damage_value
    from warhammer40k_core.engine.dice import DiceRollManager

    catalog = ArmyCatalog.phase9a_canonical_content_pack()
    attacker = _unit(catalog=catalog, army_id="army-a", unit_selection_id="attacker-unit")
    defender = _unit(catalog=catalog, army_id="army-b", unit_selection_id="defender-unit")
    state = _state(
        _army(catalog=catalog, player_id="player-a", army_id="army-a", unit=attacker),
        _army(catalog=catalog, player_id="player-b", army_id="army-b", unit=defender),
    )
    observed: list[int] = []

    def allocated(context: AllocatedAttackDamageModifierContext) -> int:
        observed.append(context.current_value)
        return 1

    registry = RuntimeModifierRegistry.from_bindings(
        allocated_attack_damage_modifier_bindings=(
            AllocatedAttackDamageModifierBinding("allocated:bonus", "source:allocated", allocated),
        )
    )
    profile = DamageProfile.fixed(1).with_modifier(
        ModifierTerm(ModifierOperation.ADD, -3).bind(
            modifier_id="damage:penalty",
            source_id="source:penalty",
            characteristic=Characteristic.DAMAGE,
        )
    )
    weapon = replace(
        _weapon_profile(catalog, attacker.own_models[0].wargear_ids[0]), damage_profile=profile
    )
    result, status = _damage_value(
        state=state,
        decisions=DecisionController(),
        manager=DiceRollManager("order93-damage"),
        profile=profile,
        attack_context_id="order93:damage",
        attacker_player_id="player-a",
        affected_unit_instance_id=attacker.unit_instance_id,
        attacking_unit_instance_id=attacker.unit_instance_id,
        attacker_model_instance_id=attacker.own_models[0].model_instance_id,
        target_unit_instance_id=defender.unit_instance_id,
        weapon_profile=weapon,
        attack_strength=None,
        target_toughness=None,
        source_phase=BattlePhase.SHOOTING,
        stratagem_index=None,
        runtime_modifier_registry=registry,
        melta_bonus=2,
        allocated_model_instance_id=defender.own_models[0].model_instance_id,
    )
    assert status is None
    assert observed == [1]
    assert result == 1  # 1 - 3 + 2 + 1, with the bound applied once after all sources.


def test_order93_invulnerable_grants_preserve_prior_save_roll_and_ap_sources() -> None:
    from warhammer40k_core.engine.generic_rule_save_modifiers import (
        generic_rule_save_option_with_roll_modifier,
    )
    from warhammer40k_core.engine.save_modifier_operations import (
        save_options_with_invulnerable_characteristic,
    )
    from warhammer40k_core.engine.saves import save_option_with_armor_penetration_modifier

    armour = generic_rule_save_option_with_roll_modifier(
        SaveOption(SaveKind.ARMOUR, 5, 3, -2),
        1,
        "source:roll",
    )
    armour = save_option_with_armor_penetration_modifier(
        armour, delta=1, source_rule_id="source:ap"
    )
    options = save_options_with_invulnerable_characteristic(
        (armour,),
        target_number=5,
        source_id="source:invul",
        only_if_better=True,
    )
    invulnerable = next(option for option in options if option.save_kind is SaveKind.INVULNERABLE)
    assert invulnerable.characteristic_target_number == 5
    assert invulnerable.target_number == 4
    assert invulnerable.roll_modifiers == armour.roll_modifiers
    assert invulnerable.armor_penetration_trace == armour.armor_penetration_trace
    improved = save_options_with_invulnerable_characteristic(
        options,
        target_number=4,
        source_id="source:better-invul",
        only_if_better=True,
    )
    invulnerable = next(option for option in improved if option.save_kind is SaveKind.INVULNERABLE)
    assert invulnerable.target_number == 3
    assert invulnerable.characteristic_trace is not None
    assert invulnerable.characteristic_trace.source_value == 5


def test_ws14_generic_contextual_status_lowers_critical_wound_threshold() -> None:
    catalog = ArmyCatalog.phase9a_canonical_content_pack()
    attacker = _unit(catalog=catalog, army_id="army-a", unit_selection_id="attacker-unit")
    defender = _unit(catalog=catalog, army_id="army-b", unit_selection_id="defender-unit")
    state = _state(
        _army(catalog=catalog, player_id="player-a", army_id="army-a", unit=attacker),
        _army(catalog=catalog, player_id="player-b", army_id="army-b", unit=defender),
    )
    profile = _weapon_profile(catalog, attacker.own_models[0].wargear_ids[0])
    state.record_persisting_effect(
        _generic_effect(
            effect_id="ws14:critical-wound-threshold",
            owner_player_id="player-a",
            target_unit_instance_ids=(attacker.unit_instance_id,),
            target_kind="this_unit",
            effect_kind="set_contextual_status",
            parameters={
                "attack_role": "attacker",
                "critical_threshold": 3,
                "roll_type": "wound",
                "status": "critical_wound_threshold",
            },
        )
    )
    context = WoundRollCriticalThresholdContext(
        state=state,
        source_phase=BattlePhase.SHOOTING,
        attacking_unit_instance_id=attacker.unit_instance_id,
        attacker_model_instance_id=attacker.own_models[0].model_instance_id,
        target_unit_instance_id=defender.unit_instance_id,
        weapon_profile=profile,
        current_critical_threshold=6,
    )
    assert generic_rule_critical_wound_threshold(context).value == 3
    assert (
        generic_rule_critical_wound_threshold(
            replace(context, current_critical_threshold=2, current_critical_is_threshold=True)
        ).value
        == 2
    )
    assert (
        generic_rule_critical_wound_threshold(
            replace(
                context,
                attacking_unit_instance_id=defender.unit_instance_id,
                attacker_model_instance_id=defender.own_models[0].model_instance_id,
                target_unit_instance_id=attacker.unit_instance_id,
            )
        ).value
        == 6
    )


def test_ws14_generic_save_and_weapon_profile_hooks_execute_from_persisted_payloads() -> None:
    catalog = ArmyCatalog.phase9a_canonical_content_pack()
    attacker = _unit(catalog=catalog, army_id="army-a", unit_selection_id="attacker-unit")
    defender = _unit(catalog=catalog, army_id="army-b", unit_selection_id="defender-unit")
    state = _state(
        _army(catalog=catalog, player_id="player-a", army_id="army-a", unit=attacker),
        _army(catalog=catalog, player_id="player-b", army_id="army-b", unit=defender),
    )
    model = attacker.own_models[0]
    profile = _weapon_profile(catalog, model.wargear_ids[0])
    registry = RuntimeModifierRegistry.empty()

    state.record_persisting_effect(
        _generic_effect(
            effect_id="ws14:attacker-lethal-hits",
            owner_player_id="player-a",
            target_unit_instance_ids=(attacker.unit_instance_id,),
            target_kind="this_unit",
            effect_kind="grant_weapon_ability",
            parameters={
                "weapon_ability": WeaponKeyword.LETHAL_HITS.value,
                "weapon_scope": "all",
            },
        )
    )
    state.record_persisting_effect(
        _generic_effect(
            effect_id="ws14:attacker-strength",
            owner_player_id="player-a",
            target_unit_instance_ids=(attacker.unit_instance_id,),
            target_kind="this_unit",
            effect_kind="modify_characteristic",
            parameters={"characteristic": "strength", "delta": 1},
        )
    )
    state.record_persisting_effect(
        _generic_effect(
            effect_id="ws14:target-save-bonus",
            owner_player_id="player-b",
            target_unit_instance_ids=(defender.unit_instance_id,),
            target_kind="selected_target",
            effect_kind="modify_dice_roll",
            parameters={"roll_type": "save", "delta": 1, "attack_role": "target"},
        )
    )

    modified_profile = registry.modified_weapon_profile(
        WeaponProfileModifierContext(
            state=state,
            source_phase=BattlePhase.SHOOTING,
            attacking_unit_instance_id=attacker.unit_instance_id,
            attacker_model_instance_id=model.model_instance_id,
            target_unit_instance_id=defender.unit_instance_id,
            weapon_profile=profile,
        )
    )
    modified_saves = registry.modified_save_options(
        SaveOptionModifierContext(
            state=state,
            source_phase=BattlePhase.SHOOTING,
            attacking_unit_instance_id=attacker.unit_instance_id,
            attacker_model_instance_id=model.model_instance_id,
            target_unit_instance_id=defender.unit_instance_id,
            weapon_profile=profile,
            save_options=(
                SaveOption(
                    save_kind=SaveKind.ARMOUR,
                    target_number=4,
                    characteristic_target_number=4,
                    armor_penetration=0,
                ),
            ),
        )
    )

    assert WeaponKeyword.LETHAL_HITS in modified_profile.keywords
    assert any(
        ability.ability_kind is AbilityKind.LETHAL_HITS for ability in modified_profile.abilities
    )
    assert modified_profile.strength.final == profile.strength.final + 1
    assert modified_saves[0].target_number == 3
    assert modified_saves[0].characteristic_target_number == 4
    assert len(modified_saves[0].roll_modifiers) == 1


def test_ws14_incoming_ap_modifier_is_bounded_and_scoped_to_triggering_attacker() -> None:
    catalog = ArmyCatalog.phase9a_canonical_content_pack()
    attacker = _unit(catalog=catalog, army_id="army-a", unit_selection_id="attacker-unit")
    defender = _unit(catalog=catalog, army_id="army-b", unit_selection_id="defender-unit")
    state = _state(
        _army(catalog=catalog, player_id="player-a", army_id="army-a", unit=attacker),
        _army(catalog=catalog, player_id="player-b", army_id="army-b", unit=defender),
    )
    profile = _weapon_profile(catalog, attacker.own_models[0].wargear_ids[0])
    registry = RuntimeModifierRegistry.empty()
    state.record_persisting_effect(
        _generic_effect(
            effect_id="ws14:incoming-ap",
            owner_player_id="player-b",
            target_unit_instance_ids=(defender.unit_instance_id,),
            target_kind="selected_target",
            effect_kind="modify_characteristic",
            parameters={
                "attack_role": "target",
                "attacker_scope": "triggering_attacking_unit",
                "characteristic": "armor_penetration",
                "delta": 1,
            },
            trigger_payload={
                "attacking_unit_instance_id": attacker.unit_instance_id,
                "attack_sequence_id": "ws14:incoming-ap:sequence",
            },
        )
    )
    options = (
        SaveOption(
            save_kind=SaveKind.ARMOUR,
            target_number=6,
            characteristic_target_number=4,
            armor_penetration=-2,
        ),
        SaveOption(
            save_kind=SaveKind.INVULNERABLE,
            target_number=5,
            characteristic_target_number=5,
            armor_penetration=-2,
        ),
    )
    context = SaveOptionModifierContext(
        state=state,
        source_phase=BattlePhase.SHOOTING,
        attacking_unit_instance_id=attacker.unit_instance_id,
        attacker_model_instance_id=attacker.own_models[0].model_instance_id,
        target_unit_instance_id=defender.unit_instance_id,
        weapon_profile=profile,
        save_options=options,
    )

    modified = registry.modified_save_options(context)
    ap_zero = registry.modified_save_options(
        replace(
            context,
            save_options=(SaveOption(SaveKind.ARMOUR, 4, 4, 0),),
        )
    )
    wrong_attacker = registry.modified_save_options(
        replace(
            context,
            attacking_unit_instance_id=defender.unit_instance_id,
            attacker_model_instance_id=defender.own_models[0].model_instance_id,
        )
    )

    assert tuple(option.armor_penetration for option in modified) == (-1, -1)
    assert tuple(option.target_number for option in modified) == (5, 5)
    assert all(
        any(
            source_id.startswith("source:ws14:incoming-ap:") for source_id in option.source_rule_ids
        )
        for option in modified
    )
    assert ap_zero[0].armor_penetration == 0
    assert ap_zero[0].target_number == 4
    assert wrong_attacker == options


def test_ws14_generic_reroll_permission_uses_source_backed_attack_path() -> None:
    catalog = ArmyCatalog.phase9a_canonical_content_pack()
    attacker = _unit(catalog=catalog, army_id="army-a", unit_selection_id="attacker-unit")
    defender = _unit(catalog=catalog, army_id="army-b", unit_selection_id="defender-unit")
    state = _state(
        _army(catalog=catalog, player_id="player-a", army_id="army-a", unit=attacker),
        _army(catalog=catalog, player_id="player-b", army_id="army-b", unit=defender),
    )
    state.record_persisting_effect(
        _generic_effect(
            effect_id="ws14:attacker-hit-reroll",
            owner_player_id="player-a",
            target_unit_instance_ids=(attacker.unit_instance_id,),
            target_kind="this_unit",
            effect_kind="reroll_permission",
            parameters={
                "roll_type": "hit",
                "attack_role": "attacker",
                "reroll_unmodified_value": 1,
            },
        )
    )

    context = source_backed_reroll_permission_context_for_unit(
        state=state,
        player_id="player-a",
        unit_instance_id=attacker.unit_instance_id,
        model_instance_id=attacker.own_models[0].model_instance_id,
        roll_type="attack_sequence.hit",
        timing_window="attack_sequence.hit",
        attack_kind="ranged",
        target_unit_instance_id=defender.unit_instance_id,
    )

    assert context is not None
    assert context.permission.eligible_roll_type == "attack_sequence.hit"
    assert context.permission.timing_window == "attack_sequence.hit"
    assert context.source_payload["effect_kind"] == GENERIC_RULE_EFFECT_KIND
    assert context.source_payload["conditional_hit_reroll"] == {
        "reroll_unmodified_values": [1],
    }


def test_ws14_attacker_scoped_generic_hooks_use_canonical_attached_rules_unit() -> None:
    catalog = ArmyCatalog.phase9a_canonical_content_pack()
    bodyguard = _unit(catalog=catalog, army_id="army-a", unit_selection_id="bodyguard")
    leader = _unit(catalog=catalog, army_id="army-a", unit_selection_id="leader")
    defender = _unit(catalog=catalog, army_id="army-b", unit_selection_id="defender")
    formation = AttachedUnitFormation(
        attached_unit_instance_id="attached-unit:army-a:bodyguard-leader",
        bodyguard_unit_instance_id=bodyguard.unit_instance_id,
        leader_unit_instance_ids=(leader.unit_instance_id,),
        component_unit_instance_ids=tuple(
            sorted((bodyguard.unit_instance_id, leader.unit_instance_id))
        ),
        source_id="ws14:attached-rules-unit",
        attachment_source_ids=("ws14:leader-attachment",),
    )
    state = _state(
        _attached_army(
            catalog=catalog,
            player_id="player-a",
            army_id="army-a",
            units=(bodyguard, leader),
            formation=formation,
        ),
        _army(catalog=catalog, player_id="player-b", army_id="army-b", unit=defender),
    )
    canonical_attacker_id = formation.attached_unit_instance_id
    registry = RuntimeModifierRegistry.empty()

    effect_specs: tuple[tuple[str, str, dict[str, JsonValue]], ...] = (
        (
            "ws14:attached-wound",
            "modify_dice_roll",
            {"roll_type": "wound", "delta": 1, "attack_role": "attacker"},
        ),
        (
            "ws14:attached-damage",
            "modify_dice_roll",
            {"roll_type": "damage", "delta": 2, "attack_role": "attacker"},
        ),
        (
            "ws14:attached-save",
            "modify_dice_roll",
            {"roll_type": "save", "delta": -1, "attack_role": "attacker"},
        ),
        (
            "ws14:attached-strength",
            "modify_characteristic",
            {"characteristic": "strength", "delta": 1, "attack_role": "attacker"},
        ),
        (
            "ws14:attached-hit-reroll",
            "reroll_permission",
            {
                "roll_type": "hit",
                "attack_role": "attacker",
                "reroll_unmodified_value": 1,
            },
        ),
    )
    for effect_id, effect_kind, parameters in effect_specs:
        state.record_persisting_effect(
            _generic_effect(
                effect_id=effect_id,
                owner_player_id="player-a",
                target_unit_instance_ids=(canonical_attacker_id,),
                target_kind="this_unit",
                effect_kind=effect_kind,
                parameters=parameters,
            )
        )

    for component in (bodyguard, leader):
        model = component.own_models[0]
        profile = _weapon_profile(catalog, model.wargear_ids[0])
        assert (
            registry.wound_roll_modifier(
                WoundRollModifierContext(
                    state=state,
                    source_phase=BattlePhase.SHOOTING,
                    attacking_unit_instance_id=component.unit_instance_id,
                    attacker_model_instance_id=model.model_instance_id,
                    target_unit_instance_id=defender.unit_instance_id,
                    weapon_profile=profile,
                    strength=4,
                    toughness=4,
                )
            )
            == 1
        )
        assert (
            registry.damage_roll_modifier(
                DamageRollModifierContext(
                    state=state,
                    source_phase=BattlePhase.SHOOTING,
                    attacking_unit_instance_id=component.unit_instance_id,
                    attacker_model_instance_id=model.model_instance_id,
                    target_unit_instance_id=defender.unit_instance_id,
                    weapon_profile=profile,
                    current_value=1,
                )
            )
            == 2
        )
        assert (
            registry.modified_weapon_profile(
                WeaponProfileModifierContext(
                    state=state,
                    source_phase=BattlePhase.SHOOTING,
                    attacking_unit_instance_id=component.unit_instance_id,
                    attacker_model_instance_id=model.model_instance_id,
                    target_unit_instance_id=defender.unit_instance_id,
                    weapon_profile=profile,
                )
            ).strength.final
            == profile.strength.final + 1
        )
        assert (
            registry.modified_save_options(
                SaveOptionModifierContext(
                    state=state,
                    source_phase=BattlePhase.SHOOTING,
                    attacking_unit_instance_id=component.unit_instance_id,
                    attacker_model_instance_id=model.model_instance_id,
                    target_unit_instance_id=defender.unit_instance_id,
                    weapon_profile=profile,
                    save_options=(
                        SaveOption(
                            save_kind=SaveKind.ARMOUR,
                            target_number=4,
                            characteristic_target_number=4,
                            armor_penetration=0,
                        ),
                    ),
                )
            )[0].target_number
            == 5
        )
        reroll_context = source_backed_reroll_permission_context_for_unit(
            state=state,
            player_id="player-a",
            unit_instance_id=component.unit_instance_id,
            model_instance_id=model.model_instance_id,
            roll_type="attack_sequence.hit",
            timing_window="attack_sequence.hit",
            attack_kind="ranged",
            target_unit_instance_id=defender.unit_instance_id,
        )
        assert reroll_context is not None
        assert reroll_context.permission.eligible_roll_type == "attack_sequence.hit"


def test_ws14_attached_attacker_conditions_use_rules_unit_ownership_and_keywords() -> None:
    catalog = ArmyCatalog.phase9a_canonical_content_pack()
    bodyguard, leader, formation = _attached_units(catalog)
    leader = with_unit_keywords(leader, keywords=(*leader.keywords, "LEADER_GATE"))
    defender = _unit(catalog=catalog, army_id="army-b", unit_selection_id="defender")
    state = _state(
        _attached_army(
            catalog=catalog,
            player_id="player-a",
            army_id="army-a",
            units=(bodyguard, leader),
            formation=formation,
        ),
        _army(catalog=catalog, player_id="player-b", army_id="army-b", unit=defender),
    )
    state.record_persisting_effect(
        _generic_effect(
            effect_id="ws14:attached-allegiance-keyword",
            owner_player_id="player-a",
            target_unit_instance_ids=(formation.attached_unit_instance_id,),
            target_kind="this_unit",
            effect_kind="modify_dice_roll",
            parameters={
                "roll_type": "hit",
                "delta": 1,
                "attack_role": "attacker",
                "target_allegiance": "enemy",
                "required_keyword": "LEADER_GATE",
            },
        )
    )

    assert (
        _hit_modifier(
            catalog=catalog,
            state=state,
            attacker=bodyguard,
            target=defender,
        )
        == 1
    )


def test_ws14_attached_target_proximity_uses_keywords_and_geometry_from_all_components() -> None:
    catalog = ArmyCatalog.phase9a_canonical_content_pack()
    bodyguard, leader, formation = _attached_units(catalog)
    leader = with_unit_keywords(leader, keywords=(*leader.keywords, "PROXIMITY_GATE"))
    defender = _unit(catalog=catalog, army_id="army-b", unit_selection_id="defender")
    armies = (
        _attached_army(
            catalog=catalog,
            player_id="player-a",
            army_id="army-a",
            units=(bodyguard, leader),
            formation=formation,
        ),
        _army(catalog=catalog, player_id="player-b", army_id="army-b", unit=defender),
    )
    state = _state(*armies)
    _place_armies(state, armies=armies)
    _move_unit_to(state, unit_instance_id=bodyguard.unit_instance_id, x=40.0, y=10.0)
    _move_unit_to(state, unit_instance_id=leader.unit_instance_id, x=10.0, y=10.0)
    _move_unit_to(state, unit_instance_id=defender.unit_instance_id, x=12.0, y=10.0)
    state.record_persisting_effect(
        _generic_effect(
            effect_id="ws14:attached-target-proximity",
            owner_player_id="player-a",
            target_unit_instance_ids=(formation.attached_unit_instance_id,),
            target_kind="this_unit",
            effect_kind="modify_dice_roll",
            parameters={
                "roll_type": "hit",
                "delta": 1,
                "attack_role": "attacker",
                "target_proximity_distance_inches": 3,
                "target_proximity_required_keyword_sequence": ["PROXIMITY_GATE"],
                "target_proximity_unit_allegiance": "friendly",
            },
        )
    )

    assert (
        _hit_modifier(
            catalog=catalog,
            state=state,
            attacker=bodyguard,
            target=defender,
        )
        == 1
    )


def test_ws14_attached_attacker_closest_target_constraint_uses_rules_unit_geometry() -> None:
    catalog = ArmyCatalog.phase9a_canonical_content_pack()
    bodyguard, leader, formation = _attached_units(catalog)
    defender = _unit(catalog=catalog, army_id="army-b", unit_selection_id="defender")
    farther_enemy = _unit(catalog=catalog, army_id="army-b", unit_selection_id="farther-enemy")
    enemy_army = replace(
        _army(catalog=catalog, player_id="player-b", army_id="army-b", unit=defender),
        units=(defender, farther_enemy),
    )
    armies = (
        _attached_army(
            catalog=catalog,
            player_id="player-a",
            army_id="army-a",
            units=(bodyguard, leader),
            formation=formation,
        ),
        enemy_army,
    )
    state = _state(*armies)
    _place_armies(state, armies=armies)
    _move_unit_to(state, unit_instance_id=bodyguard.unit_instance_id, x=40.0, y=40.0)
    _move_unit_to(state, unit_instance_id=leader.unit_instance_id, x=10.0, y=10.0)
    _move_unit_to(state, unit_instance_id=defender.unit_instance_id, x=15.0, y=10.0)
    _move_unit_to(state, unit_instance_id=farther_enemy.unit_instance_id, x=25.0, y=10.0)
    state.record_persisting_effect(
        _generic_effect(
            effect_id="ws14:attached-closest-target",
            owner_player_id="player-a",
            target_unit_instance_ids=(formation.attached_unit_instance_id,),
            target_kind="this_unit",
            effect_kind="modify_dice_roll",
            parameters={
                "roll_type": "hit",
                "delta": 1,
                "attack_role": "attacker",
                "target_constraint": "closest_eligible_target_within_18",
            },
        )
    )

    assert (
        _hit_modifier(
            catalog=catalog,
            state=state,
            attacker=bodyguard,
            target=defender,
        )
        == 1
    )
    assert (
        _hit_modifier(
            catalog=catalog,
            state=state,
            attacker=bodyguard,
            target=farther_enemy,
        )
        == 0
    )


@pytest.mark.parametrize(
    ("target_constraint", "maximum_distance_inches"),
    [
        ("closest_eligible_target_within_18", 18.0),
        ("eligible_unit_within_12", 12.0),
    ],
)
def test_ws14_unit_distance_constraint_uses_retained_member_for_all_unit_attacks(
    target_constraint: str,
    maximum_distance_inches: float,
) -> None:
    retention_decisions = DecisionController()
    catalog = ArmyCatalog.phase9a_canonical_content_pack()
    attacker = _unit(
        catalog=catalog,
        army_id="army-a",
        unit_selection_id="attacker",
        datasheet_id="core-intercessor-like-infantry",
        model_count=5,
    )
    defender = _unit(catalog=catalog, army_id="army-b", unit_selection_id="defender")
    armies = (
        _army(catalog=catalog, player_id="player-a", army_id="army-a", unit=attacker),
        _army(catalog=catalog, player_id="player-b", army_id="army-b", unit=defender),
    )
    state = _state(*armies)
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.FIGHT)
    _place_armies(state, armies=armies)
    _move_unit_to(state, unit_instance_id=defender.unit_instance_id, x=20.0, y=10.0)
    battlefield = state.battlefield_state
    assert battlefield is not None
    attacker_placement = battlefield.unit_placement_by_id(attacker.unit_instance_id)
    retained_model_id = attacker.own_models[0].model_instance_id
    living_attacker_model = attacker.own_models[1]
    separated_attacker_placement = replace(
        attacker_placement,
        model_placements=tuple(
            replace(
                placement,
                pose=Pose.at(
                    x=(
                        10.0
                        if placement.model_instance_id == retained_model_id
                        else 22.0 + maximum_distance_inches
                    ),
                    y=10.0,
                ),
            )
            for placement in attacker_placement.model_placements
        ),
    )
    separated_battlefield = battlefield.with_unit_placement(separated_attacker_placement)
    state.replace_battlefield_state(separated_battlefield)
    retained_placement = separated_battlefield.model_placement_by_id(retained_model_id)
    attacker_with_retained_dead_model = _unit_with_model_wounds(
        attacker,
        wounds_remaining=0,
    )
    _replace_unit(state, attacker_with_retained_dead_model)
    state.replace_battlefield_state(separated_battlefield.with_removed_models((retained_model_id,)))
    retain_destroyed_model_for_fixture(
        decisions=retention_decisions,
        state=state,
        placement=retained_placement,
        effect_id=f"ws14:retained-attacker:{target_constraint}",
        source_rule_id=f"ws14:retained-attacker-rule:{target_constraint}",
        source_phase=BattlePhaseKind.FIGHT,
    )
    state.record_persisting_effect(
        _generic_effect(
            effect_id=f"ws14:actual-attacker-distance:{target_constraint}",
            owner_player_id="player-a",
            target_unit_instance_ids=(attacker.unit_instance_id,),
            target_kind="this_unit",
            effect_kind="modify_dice_roll",
            parameters={
                "roll_type": "hit",
                "delta": 1,
                "attack_role": "attacker",
                "target_constraint": target_constraint,
            },
        )
    )
    registry = RuntimeModifierRegistry.empty()

    def modifier_for_model(model_index: int) -> int:
        model = attacker_with_retained_dead_model.own_models[model_index]
        return registry.hit_roll_modifier(
            HitRollModifierContext(
                state=state,
                source_phase=BattlePhase.FIGHT,
                attacking_unit_instance_id=attacker.unit_instance_id,
                attacker_model_instance_id=model.model_instance_id,
                target_unit_instance_id=defender.unit_instance_id,
                weapon_profile=_weapon_profile(catalog, model.wargear_ids[0]),
            )
        )

    assert modifier_for_model(1) == 1
    assert living_attacker_model.is_alive
    assert modifier_for_model(0) == 1


def test_ws14_attached_target_half_strength_uses_complete_rules_unit_strength() -> None:
    catalog = ArmyCatalog.phase9a_canonical_content_pack()
    attacker = _unit(catalog=catalog, army_id="army-a", unit_selection_id="attacker")
    bodyguard, leader, formation = _attached_units(catalog, army_id="army-b")
    state = _state(
        _army(catalog=catalog, player_id="player-a", army_id="army-a", unit=attacker),
        _attached_army(
            catalog=catalog,
            player_id="player-b",
            army_id="army-b",
            units=(bodyguard, leader),
            formation=formation,
        ),
    )
    state.record_persisting_effect(
        _generic_effect(
            effect_id="ws14:attached-target-half-strength",
            owner_player_id="player-a",
            target_unit_instance_ids=(attacker.unit_instance_id,),
            target_kind="this_unit",
            effect_kind="modify_dice_roll",
            parameters={
                "roll_type": "hit",
                "delta": 1,
                "attack_role": "attacker",
                "target_constraint": "target_not_below_half_strength",
            },
        )
    )

    assert (
        _hit_modifier(
            catalog=catalog,
            state=state,
            attacker=attacker,
            target=bodyguard,
        )
        == 1
    )
    _replace_unit(state, _unit_with_model_wounds(bodyguard, wounds_remaining=0))
    assert (
        _hit_modifier(
            catalog=catalog,
            state=state,
            attacker=attacker,
            target=leader,
        )
        == 1
    )
    _replace_unit(state, _unit_with_model_wounds(leader, wounds_remaining=0))
    assert (
        _hit_modifier(
            catalog=catalog,
            state=state,
            attacker=attacker,
            target=leader,
        )
        == 0
    )


def test_ws14_attached_component_targeted_this_model_effect_is_group_aware() -> None:
    catalog = ArmyCatalog.phase9a_canonical_content_pack()
    bodyguard, leader, formation = _attached_units(catalog)
    defender = _unit(catalog=catalog, army_id="army-b", unit_selection_id="defender")
    state = _state(
        _attached_army(
            catalog=catalog,
            player_id="player-a",
            army_id="army-a",
            units=(bodyguard, leader),
            formation=formation,
        ),
        _army(catalog=catalog, player_id="player-b", army_id="army-b", unit=defender),
    )
    state.record_persisting_effect(
        _generic_effect(
            effect_id="ws14:attached-this-model",
            owner_player_id="player-a",
            target_unit_instance_ids=(leader.unit_instance_id,),
            target_kind="this_model",
            effect_kind="modify_dice_roll",
            parameters={"roll_type": "hit", "delta": 1, "attack_role": "attacker"},
            source_model_instance_id=leader.own_models[0].model_instance_id,
        )
    )
    assert not state.persisting_effects_for_unit(formation.attached_unit_instance_id)

    assert (
        _hit_modifier(
            catalog=catalog,
            state=state,
            attacker=leader,
            target=defender,
        )
        == 1
    )
    assert (
        _hit_modifier(
            catalog=catalog,
            state=state,
            attacker=bodyguard,
            target=defender,
        )
        == 0
    )


def test_ws14_generic_attack_hooks_observe_persisting_effect_expiry() -> None:
    catalog = ArmyCatalog.phase9a_canonical_content_pack()
    attacker = _unit(catalog=catalog, army_id="army-a", unit_selection_id="attacker-unit")
    defender = _unit(catalog=catalog, army_id="army-b", unit_selection_id="defender-unit")
    state = _state(
        _army(catalog=catalog, player_id="player-a", army_id="army-a", unit=attacker),
        _army(catalog=catalog, player_id="player-b", army_id="army-b", unit=defender),
    )
    profile = _weapon_profile(catalog, attacker.own_models[0].wargear_ids[0])
    registry = RuntimeModifierRegistry.empty()
    state.record_persisting_effect(
        _generic_effect(
            effect_id="ws14:expiring-hit-bonus",
            owner_player_id="player-a",
            target_unit_instance_ids=(attacker.unit_instance_id,),
            target_kind="this_unit",
            effect_kind="modify_dice_roll",
            parameters={"roll_type": "hit", "delta": 1, "attack_role": "attacker"},
        )
    )
    context = HitRollModifierContext(
        state=state,
        attacking_unit_instance_id=attacker.unit_instance_id,
        attacker_model_instance_id=attacker.own_models[0].model_instance_id,
        target_unit_instance_id=defender.unit_instance_id,
        weapon_profile=profile,
        source_phase=BattlePhase.SHOOTING,
    )

    assert registry.hit_roll_modifier(context) == 1

    state.expire_persisting_effects_at_boundary(
        EffectExpirationBoundary.phase_end(
            battle_round=1,
            phase=BattlePhase.SHOOTING,
            player_id="player-a",
        )
    )

    assert registry.hit_roll_modifier(context) == 0


def test_ws14_generic_minimum_unmodified_hit_success_status_is_targeting_rule_gated() -> None:
    catalog = ArmyCatalog.phase9a_canonical_content_pack()
    attacker = _unit(catalog=catalog, army_id="army-a", unit_selection_id="attacker-unit")
    defender = _unit(catalog=catalog, army_id="army-b", unit_selection_id="defender-unit")
    state = _state(
        _army(catalog=catalog, player_id="player-a", army_id="army-a", unit=attacker),
        _army(catalog=catalog, player_id="player-b", army_id="army-b", unit=defender),
    )
    profile = _weapon_profile(catalog, attacker.own_models[0].wargear_ids[0])
    registry = RuntimeModifierRegistry.empty()
    state.record_persisting_effect(
        _generic_effect(
            effect_id="ws14:fire-overwatch-hit-threshold",
            owner_player_id="player-a",
            target_unit_instance_ids=(attacker.unit_instance_id,),
            target_kind="this_unit",
            effect_kind="set_contextual_status",
            parameters={
                "status": "minimum_unmodified_hit_success",
                "roll_type": "hit",
                "attack_role": "attacker",
                "required_targeting_rule_id": FIRE_OVERWATCH_RULE_ID,
                "minimum_unmodified_success": 5,
            },
        )
    )
    context = HitRollMinimumUnmodifiedSuccessContext(
        state=state,
        source_phase=BattlePhase.SHOOTING,
        attacking_unit_instance_id=attacker.unit_instance_id,
        attacker_model_instance_id=attacker.own_models[0].model_instance_id,
        target_unit_instance_id=defender.unit_instance_id,
        weapon_profile=profile,
        targeting_rule_ids=(FIRE_OVERWATCH_RULE_ID,),
        current_minimum_unmodified_success=6,
    )

    assert registry.minimum_unmodified_hit_success(context) == 5
    assert registry.minimum_unmodified_hit_success(replace(context, targeting_rule_ids=())) == 6
    assert (
        registry.minimum_unmodified_hit_success(
            replace(context, current_minimum_unmodified_success=4)
        )
        == 4
    )


def test_ws14_target_proximity_keyword_gate_is_ignored_when_not_configured() -> None:
    assert (
        generic_rule_target_proximity_keyword_gate_applies(
            state=object(),
            parameters={},
            attacking_unit_instance_id="attacker",
            target_unit_instance_id=None,
        )
        is True
    )


def test_ws14_target_proximity_keyword_gate_requires_target_unit() -> None:
    assert (
        generic_rule_target_proximity_keyword_gate_applies(
            state=object(),
            parameters={
                "target_proximity_distance_inches": 9,
                "target_proximity_required_keyword_sequence": ["THOUSAND_SONS", "PSYKER"],
                "target_proximity_unit_allegiance": "friendly",
            },
            attacking_unit_instance_id="attacker",
            target_unit_instance_id=None,
        )
        is False
    )


@pytest.mark.parametrize(
    ("parameters", "error"),
    [
        (
            {
                "target_proximity_distance_inches": "9",
                "target_proximity_required_keyword_sequence": ["THOUSAND_SONS", "PSYKER"],
                "target_proximity_unit_allegiance": "friendly",
            },
            "target_proximity_distance_inches must be numeric",
        ),
        (
            {
                "target_proximity_distance_inches": -1,
                "target_proximity_required_keyword_sequence": ["THOUSAND_SONS", "PSYKER"],
                "target_proximity_unit_allegiance": "friendly",
            },
            "target_proximity_distance_inches must not be negative",
        ),
        (
            {
                "target_proximity_distance_inches": 9,
                "target_proximity_required_keyword_sequence": ["THOUSAND_SONS", "PSYKER"],
                "target_proximity_unit_allegiance": 1,
            },
            "target_proximity_unit_allegiance must be a string",
        ),
        (
            {
                "target_proximity_distance_inches": 9,
                "target_proximity_required_keyword_sequence": ["THOUSAND_SONS", "PSYKER"],
                "target_proximity_unit_allegiance": "neutral",
            },
            "Unsupported generic RuleIR target proximity allegiance",
        ),
        (
            {
                "target_proximity_distance_inches": 9,
                "target_proximity_required_keyword_sequence": "THOUSAND_SONS",
                "target_proximity_unit_allegiance": "friendly",
            },
            "target_proximity_required_keyword_sequence must be a list",
        ),
        (
            {
                "target_proximity_distance_inches": 9,
                "target_proximity_required_keyword_sequence": ["THOUSAND_SONS", 1],
                "target_proximity_unit_allegiance": "friendly",
            },
            "target_proximity_required_keyword_sequence must contain strings",
        ),
        (
            {
                "target_proximity_distance_inches": 9,
                "target_proximity_required_keyword_sequence": [],
                "target_proximity_unit_allegiance": "friendly",
            },
            "target_proximity_required_keyword_sequence must not be empty",
        ),
    ],
)
def test_ws14_target_proximity_keyword_gate_rejects_malformed_descriptor_parameters(
    *,
    parameters: dict[str, JsonValue],
    error: str,
) -> None:
    with pytest.raises(GameLifecycleError, match=error):
        generic_rule_target_proximity_keyword_gate_applies(
            state=object(),
            parameters=parameters,
            attacking_unit_instance_id="attacker",
            target_unit_instance_id="target",
        )


def test_ws14_generic_this_model_half_strength_hit_modifier_gates_target() -> None:
    catalog = ArmyCatalog.phase9a_canonical_content_pack()
    attacker = _unit(catalog=catalog, army_id="army-a", unit_selection_id="attacker-unit")
    defender = _unit(catalog=catalog, army_id="army-b", unit_selection_id="defender-unit")
    state = _state(
        _army(catalog=catalog, player_id="player-a", army_id="army-a", unit=attacker),
        _army(catalog=catalog, player_id="player-b", army_id="army-b", unit=defender),
    )
    profile = _weapon_profile(catalog, attacker.own_models[0].wargear_ids[0])
    registry = RuntimeModifierRegistry.empty()
    source_model_id = attacker.own_models[0].model_instance_id

    state.record_persisting_effect(
        _generic_effect(
            effect_id="ws14:this-model-half-strength-hit-bonus",
            owner_player_id="player-a",
            target_unit_instance_ids=(attacker.unit_instance_id,),
            target_kind="this_model",
            effect_kind="modify_dice_roll",
            parameters={"roll_type": "hit", "delta": 1},
            conditions=(
                {
                    "kind": "target_constraint",
                    "parameters": [
                        {"key": "gate_subject", "value": "attack_target"},
                        {"key": "relationship", "value": "this_model_makes_attack"},
                        {"key": "target_allegiance", "value": "enemy"},
                        {
                            "key": "target_constraint",
                            "value": "target_not_below_half_strength",
                        },
                    ],
                },
            ),
            source_model_instance_id=source_model_id,
        )
    )
    context = HitRollModifierContext(
        state=state,
        attacking_unit_instance_id=attacker.unit_instance_id,
        attacker_model_instance_id=source_model_id,
        target_unit_instance_id=defender.unit_instance_id,
        weapon_profile=profile,
        source_phase=BattlePhase.SHOOTING,
    )

    assert registry.hit_roll_modifier(context) == 1
    with pytest.raises(
        GameLifecycleError,
        match="model_instance_id is not in the rules unit",
    ):
        registry.hit_roll_modifier(
            replace(
                context,
                attacker_model_instance_id=defender.own_models[0].model_instance_id,
            )
        )
    assert (
        registry.hit_roll_modifier(
            replace(context, target_unit_instance_id=attacker.unit_instance_id)
        )
        == 0
    )

    below_half_wounds = _below_half_wounds(defender.own_models[0].initial_wounds)
    _replace_unit(state, _unit_with_model_wounds(defender, wounds_remaining=below_half_wounds))

    assert registry.hit_roll_modifier(context) == 0


def test_ws14_generic_this_model_attack_modifiers_use_source_rules_unit_strength() -> None:
    catalog = ArmyCatalog.phase9a_canonical_content_pack()
    attacker = _unit(catalog=catalog, army_id="army-a", unit_selection_id="attacker-unit")
    defender = _unit(catalog=catalog, army_id="army-b", unit_selection_id="defender-unit")
    state = _state(
        _army(catalog=catalog, player_id="player-a", army_id="army-a", unit=attacker),
        _army(catalog=catalog, player_id="player-b", army_id="army-b", unit=defender),
    )
    profile = _weapon_profile(catalog, attacker.own_models[0].wargear_ids[0])
    registry = RuntimeModifierRegistry.empty()
    source_model_id = attacker.own_models[0].model_instance_id

    for roll_type, strength_constraint in (
        ("hit", "source_unit_below_starting_strength"),
        ("wound", "source_unit_below_half_strength"),
    ):
        state.record_persisting_effect(
            _generic_effect(
                effect_id=f"ws14:this-model-source-strength-{roll_type}-bonus",
                owner_player_id="player-a",
                target_unit_instance_ids=(attacker.unit_instance_id,),
                target_kind="this_model",
                effect_kind="modify_dice_roll",
                parameters={"roll_type": roll_type, "delta": 1},
                conditions=(
                    {
                        "kind": "target_constraint",
                        "parameters": [
                            {"key": "gate_subject", "value": "source_unit"},
                            {"key": "relationship", "value": "this_model_makes_attack"},
                            {"key": "target_constraint", "value": strength_constraint},
                        ],
                    },
                ),
                source_model_instance_id=source_model_id,
            )
        )

    hit_context = HitRollModifierContext(
        state=state,
        attacking_unit_instance_id=attacker.unit_instance_id,
        attacker_model_instance_id=source_model_id,
        target_unit_instance_id=defender.unit_instance_id,
        weapon_profile=profile,
        source_phase=BattlePhase.SHOOTING,
    )
    wound_context = WoundRollModifierContext(
        state=state,
        attacking_unit_instance_id=attacker.unit_instance_id,
        attacker_model_instance_id=source_model_id,
        target_unit_instance_id=defender.unit_instance_id,
        weapon_profile=profile,
        source_phase=BattlePhase.SHOOTING,
        strength=profile.strength.final,
        toughness=4,
    )

    assert registry.hit_roll_modifier(hit_context) == 0
    assert registry.wound_roll_modifier(wound_context) == 0

    attacker = _unit_with_model_wounds(
        attacker,
        wounds_remaining=attacker.own_models[0].initial_wounds - 1,
    )
    _replace_unit(state, attacker)
    assert registry.hit_roll_modifier(hit_context) == 1
    assert registry.wound_roll_modifier(wound_context) == 0

    attacker = _unit_with_model_wounds(
        attacker,
        wounds_remaining=_below_half_wounds(attacker.own_models[0].initial_wounds),
    )
    _replace_unit(state, attacker)
    assert registry.hit_roll_modifier(hit_context) == 1
    assert registry.wound_roll_modifier(wound_context) == 1


def test_ws14_generic_this_model_melee_modifiers_use_target_rules_unit_strength() -> None:
    catalog = ArmyCatalog.phase9a_canonical_content_pack()
    attacker = _unit(catalog=catalog, army_id="army-a", unit_selection_id="attacker-unit")
    defender = _unit(
        catalog=catalog,
        army_id="army-b",
        unit_selection_id="defender-unit",
        datasheet_id="core-character-support",
    )
    state = _state(
        _army(catalog=catalog, player_id="player-a", army_id="army-a", unit=attacker),
        _army(catalog=catalog, player_id="player-b", army_id="army-b", unit=defender),
    )
    base_profile = _weapon_profile(catalog, attacker.own_models[0].wargear_ids[0])
    melee_profile = replace(base_profile, range_profile=RangeProfile.melee())
    ranged_profile = replace(base_profile, range_profile=RangeProfile.distance(24))
    registry = RuntimeModifierRegistry.empty()
    source_model_id = attacker.own_models[0].model_instance_id

    for roll_type, strength_constraint in (
        ("hit", "target_unit_below_starting_strength"),
        ("wound", "target_unit_below_half_strength"),
    ):
        state.record_persisting_effect(
            _generic_effect(
                effect_id=f"ws14:this-model-target-strength-{roll_type}-bonus",
                owner_player_id="player-a",
                target_unit_instance_ids=(attacker.unit_instance_id,),
                target_kind="this_model",
                effect_kind="modify_dice_roll",
                parameters={"roll_type": roll_type, "delta": 1, "weapon_scope": "melee"},
                conditions=(
                    {
                        "kind": "target_constraint",
                        "parameters": [
                            {"key": "gate_subject", "value": "attack_target"},
                            {"key": "relationship", "value": "this_model_makes_attack"},
                            {"key": "target_allegiance", "value": "enemy"},
                            {"key": "target_constraint", "value": strength_constraint},
                        ],
                    },
                ),
                source_model_instance_id=source_model_id,
            )
        )

    hit_context = HitRollModifierContext(
        state=state,
        attacking_unit_instance_id=attacker.unit_instance_id,
        attacker_model_instance_id=source_model_id,
        target_unit_instance_id=defender.unit_instance_id,
        weapon_profile=melee_profile,
        source_phase=BattlePhase.FIGHT,
    )
    wound_context = WoundRollModifierContext(
        state=state,
        attacking_unit_instance_id=attacker.unit_instance_id,
        attacker_model_instance_id=source_model_id,
        target_unit_instance_id=defender.unit_instance_id,
        weapon_profile=melee_profile,
        source_phase=BattlePhase.FIGHT,
        strength=melee_profile.strength.final,
        toughness=4,
    )

    assert registry.hit_roll_modifier(hit_context) == 0
    assert registry.wound_roll_modifier(wound_context) == 0

    defender = _unit_with_model_wounds(
        defender,
        wounds_remaining=defender.own_models[0].initial_wounds - 1,
    )
    _replace_unit(state, defender)
    assert registry.hit_roll_modifier(hit_context) == 1
    assert registry.wound_roll_modifier(wound_context) == 0

    defender = _unit_with_model_wounds(
        defender,
        wounds_remaining=defender.own_models[0].initial_wounds // 2,
    )
    _replace_unit(state, defender)
    assert registry.hit_roll_modifier(hit_context) == 1
    assert registry.wound_roll_modifier(wound_context) == 0

    defender = _unit_with_model_wounds(
        defender,
        wounds_remaining=_below_half_wounds(defender.own_models[0].initial_wounds),
    )
    _replace_unit(state, defender)
    assert registry.hit_roll_modifier(hit_context) == 1
    assert registry.wound_roll_modifier(wound_context) == 1
    assert registry.hit_roll_modifier(replace(hit_context, weapon_profile=ranged_profile)) == 0
    assert registry.wound_roll_modifier(replace(wound_context, weapon_profile=ranged_profile)) == 0


def test_ws14_generic_source_strength_constraint_rejects_unknown_state() -> None:
    catalog = ArmyCatalog.phase9a_canonical_content_pack()
    attacker = _unit(catalog=catalog, army_id="army-a", unit_selection_id="attacker-unit")
    defender = _unit(catalog=catalog, army_id="army-b", unit_selection_id="defender-unit")
    state = _state(
        _army(catalog=catalog, player_id="player-a", army_id="army-a", unit=attacker),
        _army(catalog=catalog, player_id="player-b", army_id="army-b", unit=defender),
    )
    source_model_id = attacker.own_models[0].model_instance_id
    state.record_persisting_effect(
        _generic_effect(
            effect_id="ws14:this-model-source-strength-drift",
            owner_player_id="player-a",
            target_unit_instance_ids=(attacker.unit_instance_id,),
            target_kind="this_model",
            effect_kind="modify_dice_roll",
            parameters={"roll_type": "hit", "delta": 1},
            conditions=(
                {
                    "kind": "target_constraint",
                    "parameters": [
                        {"key": "gate_subject", "value": "source_unit"},
                        {"key": "relationship", "value": "this_model_makes_attack"},
                        {"key": "target_constraint", "value": "source_unit_unknown_state"},
                    ],
                },
            ),
            source_model_instance_id=source_model_id,
        )
    )

    with pytest.raises(GameLifecycleError, match="Unsupported generic RuleIR target_constraint"):
        RuntimeModifierRegistry.empty().hit_roll_modifier(
            HitRollModifierContext(
                state=state,
                attacking_unit_instance_id=attacker.unit_instance_id,
                attacker_model_instance_id=source_model_id,
                target_unit_instance_id=defender.unit_instance_id,
                weapon_profile=_weapon_profile(catalog, attacker.own_models[0].wargear_ids[0]),
                source_phase=BattlePhase.SHOOTING,
            )
        )


def _unit(
    *,
    catalog: ArmyCatalog,
    army_id: str,
    unit_selection_id: str,
    datasheet_id: str = "core-character-leader",
    model_count: int = 1,
) -> UnitInstance:
    datasheet = catalog.datasheet_by_id(datasheet_id)
    profile = datasheet.model_profiles[0]
    option = datasheet.wargear_options[0]
    return UnitFactory(catalog=catalog).instantiate_unit(
        army_id=army_id,
        selection=UnitMusterSelection(
            unit_selection_id=unit_selection_id,
            datasheet_id=datasheet.datasheet_id,
            model_profile_selections=(
                ModelProfileSelection(
                    model_profile_id=profile.model_profile_id,
                    model_count=model_count,
                ),
            ),
            wargear_selections=(
                WargearSelection(
                    option_id=option.option_id,
                    model_profile_id=profile.model_profile_id,
                    wargear_ids=option.default_wargear_ids,
                ),
            ),
        ),
        datasheet=datasheet,
    )


def _army(
    *,
    catalog: ArmyCatalog,
    player_id: str,
    army_id: str,
    unit: UnitInstance,
) -> ArmyDefinition:
    detachment = catalog.detachments[0]
    return ArmyDefinition(
        army_id=army_id,
        player_id=player_id,
        catalog_id=catalog.catalog_id,
        source_package_id=catalog.source_package_id,
        ruleset_id=catalog.ruleset_id,
        detachment_selection=DetachmentSelection(
            faction_id=detachment.faction_id,
            detachment_ids=(detachment.detachment_id,),
        ),
        force_disposition_id="purge-the-foe",
        units=(unit,),
    )


def _attached_army(
    *,
    catalog: ArmyCatalog,
    player_id: str,
    army_id: str,
    units: tuple[UnitInstance, ...],
    formation: AttachedUnitFormation,
) -> ArmyDefinition:
    detachment = catalog.detachments[0]
    return ArmyDefinition(
        army_id=army_id,
        player_id=player_id,
        catalog_id=catalog.catalog_id,
        source_package_id=catalog.source_package_id,
        ruleset_id=catalog.ruleset_id,
        detachment_selection=DetachmentSelection(
            faction_id=detachment.faction_id,
            detachment_ids=(detachment.detachment_id,),
        ),
        force_disposition_id="purge-the-foe",
        units=units,
        attached_units=(formation,),
    )


def _attached_units(
    catalog: ArmyCatalog,
    *,
    army_id: str = "army-a",
) -> tuple[UnitInstance, UnitInstance, AttachedUnitFormation]:
    bodyguard = _unit(
        catalog=catalog,
        army_id=army_id,
        unit_selection_id="bodyguard",
    )
    leader = _unit(
        catalog=catalog,
        army_id=army_id,
        unit_selection_id="leader",
    )
    formation = AttachedUnitFormation(
        attached_unit_instance_id=f"attached-unit:{army_id}:bodyguard-leader",
        bodyguard_unit_instance_id=bodyguard.unit_instance_id,
        leader_unit_instance_ids=(leader.unit_instance_id,),
        component_unit_instance_ids=tuple(
            sorted((bodyguard.unit_instance_id, leader.unit_instance_id))
        ),
        source_id="ws14:attached-rules-unit",
        attachment_source_ids=("ws14:leader-attachment",),
    )
    return bodyguard, leader, formation


def _state(*armies: ArmyDefinition) -> GameState:
    descriptor = RulesetDescriptor.warhammer_40000_eleventh()
    state = GameState(
        game_id="ws14-attack-hooks-game",
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
    )
    for army in armies:
        state.record_army_definition(army)
    return state


def _place_armies(state: GameState, *, armies: tuple[ArmyDefinition, ...]) -> None:
    state.battlefield_state = create_deterministic_battlefield_scenario(
        battlefield_id="ws14-attack-hooks-battlefield",
        armies=armies,
    ).battlefield_state


def _move_unit_to(
    state: GameState,
    *,
    unit_instance_id: str,
    x: float,
    y: float,
) -> None:
    battlefield = state.battlefield_state
    if battlefield is None:
        raise AssertionError("Expected battlefield_state.")
    placement = battlefield.unit_placement_by_id(unit_instance_id)
    state.replace_battlefield_state(
        battlefield.with_unit_placement(
            replace(
                placement,
                model_placements=tuple(
                    replace(model_placement, pose=Pose.at(x=x, y=y))
                    for model_placement in placement.model_placements
                ),
            )
        )
    )


def _hit_modifier(
    *,
    catalog: ArmyCatalog,
    state: GameState,
    attacker: UnitInstance,
    target: UnitInstance,
) -> int:
    model = attacker.own_models[0]
    return RuntimeModifierRegistry.empty().hit_roll_modifier(
        HitRollModifierContext(
            state=state,
            source_phase=BattlePhase.SHOOTING,
            attacking_unit_instance_id=attacker.unit_instance_id,
            attacker_model_instance_id=model.model_instance_id,
            target_unit_instance_id=target.unit_instance_id,
            weapon_profile=_weapon_profile(catalog, model.wargear_ids[0]),
        )
    )


def _weapon_profile(catalog: ArmyCatalog, wargear_id: str) -> WeaponProfile:
    for wargear in catalog.wargear:
        if wargear.wargear_id == wargear_id:
            return wargear.weapon_profiles[0]
    raise AssertionError(f"Unknown wargear id: {wargear_id}")


def _unit_with_model_wounds(unit: UnitInstance, *, wounds_remaining: int) -> UnitInstance:
    return replace(
        unit,
        own_models=(
            replace(unit.own_models[0], wounds_remaining=wounds_remaining),
            *unit.own_models[1:],
        ),
    )


def _below_half_wounds(starting_wounds: int) -> int:
    if starting_wounds <= 2:
        return 0
    return max(1, (starting_wounds - 1) // 2)


def _replace_unit(state: GameState, replacement: UnitInstance) -> None:
    updated_armies: list[ArmyDefinition] = []
    did_update = False
    for army in state.army_definitions:
        updated_units: list[UnitInstance] = []
        for unit in army.units:
            if unit.unit_instance_id == replacement.unit_instance_id:
                updated_units.append(replacement)
                did_update = True
            else:
                updated_units.append(unit)
        updated_armies.append(replace(army, units=tuple(updated_units)))
    if not did_update:
        raise AssertionError(f"Unknown unit id: {replacement.unit_instance_id}")
    state.army_definitions = updated_armies


@pytest.mark.parametrize("random_damage", [False, True])
def test_order93_save_damage_subsets_use_facade_restore_and_exact_replay(
    random_damage: bool,
) -> None:
    from typing import cast

    from tests.order93_save_damage_helpers import save_damage_session
    from tests.psychic_modifier_helpers import pending_request, submit_fixture_request

    from warhammer40k_core.engine.lifecycle import GameLifecycle
    from warhammer40k_core.engine.phase import LifecycleStatusKind
    from warhammer40k_core.engine.replay import ReplayRunner

    session = save_damage_session(random_damage=random_damage)
    kinds: set[str] = set()
    save_models: set[str] = set()
    for _ in range(80):
        request = pending_request(session)
        if request.decision_type != "select_modifier_ignores":
            submit_fixture_request(session, request)
            continue
        payload = cast(dict[str, JsonValue], request.payload)
        subject = cast(dict[str, JsonValue], payload["subject"])
        kind = cast(str, subject["kind"])
        kinds.add(kind)
        assert request.actor_id == ("player-b" if kind == "save_roll" else "player-a")
        if kind == "save_roll":
            save_models.add(cast(str, subject["model_instance_id"]))
        restored = GameLifecycle.from_payload(session.lifecycle.to_payload())
        assert restored.to_payload() == session.lifecycle.to_payload()
        inventory = cast(list[dict[str, JsonValue]], payload["modifiers"])
        decided = cast(list[str], payload["decided_modifier_ids"])
        operation = cast(dict[str, JsonValue], inventory[len(decided)]["operation"])
        # Retain each penalty and discard its opposing bonus, proving source-level selection.
        prefix = "ignore:" if cast(int, operation["operand"]) > 0 else "keep:"
        option = next(
            (option for option in request.options if option.option_id.startswith(prefix)),
            next(
                option
                for option in request.options
                if option.option_id
                == ("ignore-remaining" if prefix == "ignore:" else "keep-remaining")
            ),
        )
        status = session.submit_option(
            request_id=request.request_id,
            result_id=f"{request.request_id}:subset",
            option_id=option.option_id,
        )
        assert status.status_kind is not LifecycleStatusKind.INVALID, status
        events = session.lifecycle.decision_controller.event_log.records
        if any(
            event.event_type == "attack_sequence_step"
            and isinstance(event.payload, dict)
            and event.payload.get("step") == "damage"
            for event in events
        ):
            break
    else:
        raise AssertionError("Save/Damage evaluation did not reach Damage mutation.")
    assert {"save_roll", "damage_characteristic"} <= kinds
    assert ("damage_roll" in kinds) is random_damage
    assert len(save_models) == 2
    assert (
        GameLifecycle.from_payload(session.lifecycle.to_payload()).to_payload()
        == session.lifecycle.to_payload()
    )
    assert (
        ReplayRunner.from_payload(session.replay_artifact(artifact_id="save-damage-subsets"))
        .run()
        .reproduced_exactly
    )


@pytest.mark.parametrize("kind", ["save_roll", "damage_characteristic", "damage_roll"])
def test_order93_save_damage_rejects_stale_state_before_queue_pop(kind: str) -> None:
    from tests.order93_save_damage_helpers import reach_save_damage_request, save_damage_session

    from warhammer40k_core.engine.phase import LifecycleStatusKind

    session = save_damage_session(random_damage=True)
    request = reach_save_damage_request(session, kind=kind)
    state = session.lifecycle.state
    assert state is not None
    state.record_persisting_effect(
        _generic_effect(
            effect_id="source-drift",
            owner_player_id="player-b",
            target_unit_instance_ids=("army-beta:enemy",),
            target_kind="this_unit",
            effect_kind="modify_dice_roll",
            parameters={"roll_type": "save", "delta": 1, "attack_role": "target"},
        )
    )
    before = session.lifecycle.decision_controller.to_payload()
    status = session.submit_option(
        request_id=request.request_id,
        result_id=f"{request.request_id}:stale",
        option_id="keep-remaining",
    )
    assert status.status_kind is LifecycleStatusKind.INVALID
    assert session.lifecycle.decision_controller.to_payload() == before


def test_order93_save_choice_rejects_tampered_source_restore_and_scopes_model_permission() -> None:
    from copy import deepcopy
    from typing import cast

    from tests.order93_save_damage_helpers import reach_save_damage_request, save_damage_session
    from tests.psychic_modifier_helpers import pending_request, submit_fixture_request

    from warhammer40k_core.engine.lifecycle import GameLifecycle
    from warhammer40k_core.engine.phase import LifecycleStatusKind

    session = save_damage_session(model_scoped_save=True)
    request = reach_save_damage_request(session)
    payload = cast(dict[str, JsonValue], request.payload)
    subject = cast(dict[str, JsonValue], payload["subject"])
    permitted_model = subject["model_instance_id"]
    saved = deepcopy(session.lifecycle.to_payload())
    # The source inventory and its finite choices are engine evidence, not adapter input.
    queued = cast(list[dict[str, JsonValue]], saved["decisions"]["queue"]["pending_requests"])
    pending_payload = cast(dict[str, JsonValue], queued[0]["payload"])
    inventory = cast(list[dict[str, JsonValue]], pending_payload["modifiers"])
    cast(dict[str, JsonValue], inventory[0]["operation"])["operand"] = 91
    with pytest.raises(
        (GameLifecycleError, ValueError), match=r"[Dd]rift|[Ii]nventory|[Oo]ption|[Rr]eplay"
    ):
        GameLifecycle.from_payload(saved)
    for _ in range(50):
        if request.decision_type == "select_modifier_ignores":
            body = cast(dict[str, JsonValue], request.payload)
            current_subject = cast(dict[str, JsonValue], body["subject"])
            if current_subject["kind"] == "save_roll":
                assert current_subject["model_instance_id"] == permitted_model
            status = session.submit_option(
                request_id=request.request_id,
                result_id=f"{request.request_id}:selected",
                option_id="ignore-remaining"
                if current_subject["kind"] == "save_roll"
                else "keep-remaining",
            )
            assert status.status_kind is not LifecycleStatusKind.INVALID, status
        else:
            submit_fixture_request(session, request)
        if any(
            event.event_type == "attack_sequence_step"
            and isinstance(event.payload, dict)
            and event.payload.get("step") == "allocate"
            for event in session.lifecycle.decision_controller.event_log.records
        ):
            break
        request = pending_request(session)
    else:
        raise AssertionError("Save choices did not produce allocation grouping.")
    allocations = [
        event.payload
        for event in session.lifecycle.decision_controller.event_log.records
        if event.event_type == "attack_sequence_step"
        and isinstance(event.payload, dict)
        and event.payload.get("step") == "allocate"
    ]
    groups = cast(
        list[dict[str, JsonValue]],
        cast(dict[str, JsonValue], allocations[-1]["payload"])["allocation_groups"],
    )
    assert len(groups) == 2


def test_order93_incoming_ap_is_independent_and_preserves_required_save_order() -> None:
    from warhammer40k_core.engine.save_modifier_operations import save_option_ignoring_modifiers
    from warhammer40k_core.engine.saves import mandatory_save_option

    armour = SaveOption(SaveKind.ARMOUR, 5, 3, -2)
    invulnerable = SaveOption(SaveKind.INVULNERABLE, 4, 4, -2)
    assert mandatory_save_option((armour, invulnerable)) == invulnerable
    ap_operation = armour.inherent_roll_modifiers[0]
    assert ap_operation.operand == -2
    assert ap_operation.source_id is not None
    selected = save_option_ignoring_modifiers(armour, (ap_operation.modifier_id,))
    assert selected.armor_penetration == -2
    assert selected.characteristic_target_number == 3
    assert selected.target_number == 3
    assert mandatory_save_option((selected, invulnerable)) == invulnerable
    from warhammer40k_core.core.dice import DiceRollResult, DiceRollState
    from warhammer40k_core.engine.saves import resolve_saving_throw, saving_throw_roll_spec

    roll = DiceRollState.from_result(
        DiceRollResult.from_values(
            roll_id="order93:ap-save",
            spec=saving_throw_roll_spec(
                save_kind=SaveKind.INVULNERABLE,
                player_id="player-b",
                allocated_model_id="model",
                attack_context_id="order93:ap-save",
            ),
            values=(3,),
            source="fixed",
        )
    )
    assert not resolve_saving_throw(options=(armour, invulnerable), roll_state=roll).successful
    resolved = resolve_saving_throw(options=(selected, invulnerable), roll_state=roll)
    assert resolved.successful
    assert resolved.save_kind is SaveKind.ARMOUR
    assert SaveOption.from_payload(selected.to_payload()) == selected
    payload = selected.to_payload()
    payload["inherent_roll_modifiers"][0]["operand"] = -4
    with pytest.raises(GameLifecycleError, match="inherent roll arithmetic"):
        SaveOption.from_payload(payload)


def test_order93_attacker_ap_selection_precedes_defender_incoming_ap_roll_inventory() -> None:
    from typing import cast

    from tests.order93_save_damage_helpers import reach_save_damage_request, save_damage_session
    from tests.psychic_modifier_helpers import pending_request

    from warhammer40k_core.engine.lifecycle import GameLifecycle
    from warhammer40k_core.engine.phase import LifecycleStatusKind

    session = save_damage_session(modified_ap=True)
    request = reach_save_damage_request(session, kind="armor_penetration_characteristic")
    for _ in range(8):
        payload = cast(dict[str, JsonValue], request.payload)
        subject = cast(dict[str, JsonValue], payload["subject"])
        inventory = cast(list[dict[str, JsonValue]], payload["modifiers"])
        if subject["kind"] == "save_roll":
            assert request.actor_id == "player-b"
            inherent = next(
                row
                for row in inventory
                if cast(str, cast(dict[str, JsonValue], row["operation"])["modifier_id"]).endswith(
                    ":saving-throw-ap"
                )
            )
            assert cast(dict[str, JsonValue], inherent["operation"])["operand"] == -4
            assert (
                GameLifecycle.from_payload(session.lifecycle.to_payload()).to_payload()
                == session.lifecycle.to_payload()
            )
            return
        assert subject["kind"] == "armor_penetration_characteristic"
        assert request.actor_id == "player-a"
        operation = cast(
            dict[str, JsonValue],
            inventory[len(cast(list[str], payload["decided_modifier_ids"]))]["operation"],
        )
        ignore = cast(int, operation["operand"]) < 0
        prefix = "ignore:" if ignore else "keep:"
        option = next(
            (option for option in request.options if option.option_id.startswith(prefix)),
            next(
                option
                for option in request.options
                if option.option_id == ("ignore-remaining" if ignore else "keep-remaining")
            ),
        )
        status = session.submit_option(
            request_id=request.request_id,
            result_id=f"{request.request_id}:ap-subset",
            option_id=option.option_id,
        )
        assert status.status_kind is not LifecycleStatusKind.INVALID, status
        request = pending_request(session)
    raise AssertionError("Did not reach the defender's selected AP inventory.")


def test_order93_weaker_invulnerable_source_survives_ignoring_stronger_grant() -> None:
    from warhammer40k_core.engine.save_modifier_operations import (
        save_option_ignoring_modifiers,
        save_options_with_invulnerable_characteristic,
    )

    options: tuple[SaveOption, ...] = (SaveOption(SaveKind.INVULNERABLE, 6, 6, 0),)
    for value, source in ((4, "source:stronger"), (5, "source:weaker")):
        options = save_options_with_invulnerable_characteristic(
            options,
            target_number=value,
            source_id=source,
            only_if_better=True,
        )
    option = options[0]
    assert option.characteristic_target_number == 4
    assert option.characteristic_trace is not None
    assert len(option.characteristic_trace.modifiers) == 2
    selected = save_option_ignoring_modifiers(option, ("source:stronger:invulnerable-save",))
    assert selected.characteristic_target_number == 5
    assert SaveOption.from_payload(selected.to_payload()) == selected


@pytest.mark.parametrize("ignore", [False, True])
def test_order93_failed_save_zero_replacement_is_selectable_after_save_and_consumed(
    ignore: bool,
) -> None:
    from typing import cast

    from tests.order93_save_damage_helpers import reach_save_damage_request, save_damage_session
    from tests.psychic_modifier_helpers import pending_request, submit_fixture_request

    from warhammer40k_core.engine.lifecycle import GameLifecycle
    from warhammer40k_core.engine.phase import LifecycleStatusKind
    from warhammer40k_core.engine.replay import ReplayRunner

    session = save_damage_session(damage_zero_replacement=True)
    request = reach_save_damage_request(
        session,
        kind="damage_characteristic",
        stage="failed-save-damage-replacement",
    )
    assert request.actor_id == "player-a"
    payload = cast(dict[str, JsonValue], request.payload)
    operation = cast(
        dict[str, JsonValue], cast(list[dict[str, JsonValue]], payload["modifiers"])[0]["operation"]
    )
    assert operation["operation"] == "set"
    assert operation["operand"] == 0
    before_events = session.lifecycle.decision_controller.event_log.records
    assert any(
        event.event_type == "attack_sequence_step"
        and isinstance(event.payload, dict)
        and event.payload.get("step") == "save"
        for event in before_events
    )
    assert not any(event.event_type.startswith("failed_save_damage") for event in before_events)
    assert (
        GameLifecycle.from_payload(session.lifecycle.to_payload()).to_payload()
        == session.lifecycle.to_payload()
    )
    status = session.submit_option(
        request_id=request.request_id,
        result_id=f"{request.request_id}:zero-subset",
        option_id="ignore-remaining" if ignore else "keep-remaining",
    )
    assert status.status_kind is not LifecycleStatusKind.INVALID, status
    event_type = (
        "failed_save_damage_replacement_ignored" if ignore else "failed_save_damage_replaced"
    )
    assert (
        sum(
            event.event_type == event_type
            for event in session.lifecycle.decision_controller.event_log.records
        )
        == 1
    )
    for _ in range(40):
        events = session.lifecycle.decision_controller.event_log.records
        damage_events = [
            event
            for event in events
            if event.event_type == "attack_sequence_step"
            and isinstance(event.payload, dict)
            and event.payload.get("step") == "damage"
        ]
        if len(damage_events) >= 2:
            break
        request = pending_request(session)
        if request.decision_type == "select_modifier_ignores":
            body = cast(dict[str, JsonValue], request.payload)
            assert (
                cast(dict[str, JsonValue], body["source_context"])["evaluation_stage"]
                != "failed-save-damage-replacement"
            )
            status = session.submit_option(
                request_id=request.request_id,
                result_id=f"{request.request_id}:keep",
                option_id="keep-remaining",
            )
            assert status.status_kind is not LifecycleStatusKind.INVALID, status
        else:
            submit_fixture_request(session, request)
    else:
        raise AssertionError("The two wounds did not resolve.")
    assert (
        sum(
            event.event_type.startswith("failed_save_damage")
            for event in session.lifecycle.decision_controller.event_log.records
        )
        == 1
    )
    assert (
        GameLifecycle.from_payload(session.lifecycle.to_payload()).to_payload()
        == session.lifecycle.to_payload()
    )
    assert (
        ReplayRunner.from_payload(session.replay_artifact(artifact_id="ignored-failed-save-zero"))
        .run()
        .reproduced_exactly
    )


def test_order93_cover_bonus_retains_source_when_ignored_without_double_ap_application() -> None:
    from tests.phase13b_shooting_declaration_helpers import _benefit_of_cover_result

    from warhammer40k_core.core.ruleset_descriptor import CoverEffect
    from warhammer40k_core.engine.save_modifier_operations import save_option_ignoring_modifiers

    cover = replace(_benefit_of_cover_result(), cover_effect=CoverEffect.SAVE_BONUS)
    option = SaveOption(SaveKind.ARMOUR, 4, 4, -1, cover_applied=True, cover_result=cover)
    ap_operation, cover_operation = option.inherent_roll_modifiers
    assert (ap_operation.operand, cover_operation.operand) == (-1, 1)
    without_cover = save_option_ignoring_modifiers(option, (cover_operation.modifier_id,))
    assert without_cover.target_number == 5
    assert not without_cover.cover_applied
    assert without_cover.inherent_roll_modifiers == option.inherent_roll_modifiers
    without_ap = save_option_ignoring_modifiers(option, (ap_operation.modifier_id,))
    assert without_ap.target_number == 3
    assert without_ap.cover_applied
    assert SaveOption.from_payload(without_cover.to_payload()) == without_cover


@pytest.mark.parametrize(("ignore_take_cover", "expected_save"), [(False, 3), (True, 4)])
def test_order93_take_cover_retains_atomic_limit_against_real_rattlejoint_provider(
    ignore_take_cover: bool,
    expected_save: int,
) -> None:
    from copy import deepcopy
    from typing import cast

    from tests.order93_save_damage_helpers import (
        reach_save_damage_request,
        take_cover_rattlejoint_session,
    )
    from tests.psychic_modifier_helpers import pending_request, submit_fixture_request

    from warhammer40k_core.engine.lifecycle import GameLifecycle
    from warhammer40k_core.engine.phase import LifecycleStatusKind
    from warhammer40k_core.engine.replay import ReplayRunner

    session = take_cover_rattlejoint_session()
    request = reach_save_damage_request(session, kind="save_characteristic")
    payload = cast(dict[str, JsonValue], request.payload)
    inventory = cast(list[dict[str, JsonValue]], payload["modifiers"])
    assert len(inventory) == 2
    operations = [cast(dict[str, JsonValue], row["operation"]) for row in inventory]
    # The registry's real Astra provider is evaluated before its Death Guard provider.
    assert [operation["operand"] for operation in operations] == [-1, 1]
    assert operations[0]["result_floor"] == 3
    assert "result_floor" not in operations[1]
    assert all(operation["operation"] == "add" for operation in operations)
    assert (
        GameLifecycle.from_payload(session.lifecycle.to_payload()).to_payload()
        == session.lifecycle.to_payload()
    )
    tampered = deepcopy(session.lifecycle.to_payload())
    pending = tampered["decisions"]["queue"]["pending_requests"][0]
    body = cast(dict[str, JsonValue], pending["payload"])
    rows = cast(list[dict[str, JsonValue]], body["modifiers"])
    cast(dict[str, JsonValue], rows[0]["operation"]).pop("result_floor")
    with pytest.raises(
        (GameLifecycleError, ValueError), match=r"[Dd]rift|[Ii]nventory|[Oo]ption|[Rr]eplay"
    ):
        GameLifecycle.from_payload(tampered)
    for _ in range(20):
        if request.decision_type == "select_modifier_ignores":
            body = cast(dict[str, JsonValue], request.payload)
            subject = cast(dict[str, JsonValue], body["subject"])
            if subject["kind"] == "save_characteristic":
                rows = cast(list[dict[str, JsonValue]], body["modifiers"])
                decided = cast(list[str], body["decided_modifier_ids"])
                operation = cast(dict[str, JsonValue], rows[len(decided)]["operation"])
                ignore = ignore_take_cover and "result_floor" in operation
                prefix = "ignore:" if ignore else "keep:"
                option = next(
                    (option for option in request.options if option.option_id.startswith(prefix)),
                    None,
                )
                option_id = (
                    option.option_id
                    if option is not None
                    else ("ignore-remaining" if ignore else "keep-remaining")
                )
            else:
                option_id = "keep-remaining"
            status = session.submit_option(
                request_id=request.request_id,
                result_id=f"{request.request_id}:bounded-source",
                option_id=option_id,
            )
            assert status.status_kind is not LifecycleStatusKind.INVALID, status
        else:
            submit_fixture_request(session, request)
        snapshots = [
            event.payload
            for event in session.lifecycle.decision_controller.event_log.records
            if event.event_type == "attack_save_modifiers_prepared"
        ]
        if snapshots:
            break
        request = pending_request(session)
    else:
        raise AssertionError("The bounded source selection did not complete.")
    snapshot = cast(dict[str, JsonValue], snapshots[0])
    options = cast(list[dict[str, JsonValue]], snapshot["selected_options"])
    assert options[0]["characteristic_target_number"] == expected_save
    assert (
        GameLifecycle.from_payload(session.lifecycle.to_payload()).to_payload()
        == session.lifecycle.to_payload()
    )
    assert (
        ReplayRunner.from_payload(
            session.replay_artifact(artifact_id=f"take-cover-source-limit-{ignore_take_cover}")
        )
        .run()
        .reproduced_exactly
    )


def test_order93_runtime_save_modifier_uses_raw_random_source_before_minimum() -> None:
    from warhammer40k_core.core.attributes import Characteristic
    from warhammer40k_core.core.dice import DiceExpression
    from warhammer40k_core.core.modifiers import ModifierOperation, ModifierTerm
    from warhammer40k_core.core.random_profile_values import RandomProfileValue
    from warhammer40k_core.engine.save_modifier_operations import (
        save_option_with_characteristic_terms,
    )
    from warhammer40k_core.engine.saves import save_options_for_model

    catalog = ArmyCatalog.phase9a_canonical_content_pack()
    unit = _unit(catalog=catalog, army_id="army-a", unit_selection_id="random-save")
    model = unit.own_models[0]
    random_save = RandomProfileValue(
        Characteristic.SAVE, DiceExpression(1, 6), "source:random-save"
    ).evaluate(
        raw=1, evaluation_id="source:random-save:evaluated", target_id=model.model_instance_id
    )
    assert random_save.final == 2
    model = replace(
        model,
        characteristics=tuple(
            random_save if value.characteristic is Characteristic.SAVE else value
            for value in model.characteristics
        ),
    )
    option = next(
        option
        for option in save_options_for_model(model=model, armor_penetration=0)
        if option.save_kind is SaveKind.ARMOUR
    )
    worsened = save_option_with_characteristic_terms(
        option,
        characteristic=Characteristic.SAVE,
        terms=(ModifierTerm(ModifierOperation.ADD, 1),),
        source_id="source:rattlejoint",
        modifier_id="rattlejoint",
    )
    assert worsened.characteristic_target_number == 2
    assert worsened.characteristic_trace is not None
    assert worsened.characteristic_trace.source_value == 1
    assert SaveOption.from_payload(worsened.to_payload()) == worsened
