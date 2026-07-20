from __future__ import annotations

from dataclasses import replace

import pytest

from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.core.ruleset_descriptor import RulesetDescriptor
from warhammer40k_core.core.weapon_profiles import AbilityKind, WeaponKeyword, WeaponProfile
from warhammer40k_core.engine.army_mustering import ArmyDefinition
from warhammer40k_core.engine.attached_unit_formation import AttachedUnitFormation
from warhammer40k_core.engine.effects import (
    GENERIC_RULE_EFFECT_KIND,
    EffectExpiration,
    EffectExpirationBoundary,
    PersistingEffect,
)
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
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
    assert modified_saves[0].characteristic_target_number == 3


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
    leader = replace(leader, keywords=(*leader.keywords, "LEADER_GATE"))
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
    leader = replace(leader, keywords=(*leader.keywords, "PROXIMITY_GATE"))
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
    _move_unit_to(state, unit_instance_id=bodyguard.unit_instance_id, x=40.0, y=40.0)
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


def test_ws14_attached_this_model_effect_does_not_leak_between_components() -> None:
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
            target_unit_instance_ids=(formation.attached_unit_instance_id,),
            target_kind="this_model",
            effect_kind="modify_dice_roll",
            parameters={"roll_type": "hit", "delta": 1, "attack_role": "attacker"},
            source_model_instance_id=leader.own_models[0].model_instance_id,
        )
    )

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

    below_half_wounds = _below_half_wounds(defender.own_models[0].starting_wounds)
    _replace_unit(state, _unit_with_model_wounds(defender, wounds_remaining=below_half_wounds))

    assert registry.hit_roll_modifier(context) == 0


def _unit(*, catalog: ArmyCatalog, army_id: str, unit_selection_id: str) -> UnitInstance:
    datasheet = catalog.datasheet_by_id("core-character-leader")
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
                    model_count=1,
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


def _generic_effect(
    *,
    effect_id: str,
    owner_player_id: str,
    target_unit_instance_ids: tuple[str, ...],
    target_kind: str,
    effect_kind: str,
    parameters: dict[str, JsonValue],
    conditions: tuple[dict[str, JsonValue], ...] = (),
    source_model_instance_id: str | None = None,
) -> PersistingEffect:
    parameter_payloads: list[dict[str, JsonValue]] = [
        {"key": key, "value": value} for key, value in sorted(parameters.items())
    ]
    return PersistingEffect(
        effect_id=effect_id,
        source_rule_id=f"source:{effect_id}",
        owner_player_id=owner_player_id,
        target_unit_instance_ids=target_unit_instance_ids,
        started_battle_round=1,
        started_phase=BattlePhase.SHOOTING,
        expiration=EffectExpiration.end_phase(
            battle_round=1,
            phase=BattlePhase.SHOOTING,
            player_id="player-a",
        ),
        effect_payload=validate_json_value(
            {
                "effect_kind": GENERIC_RULE_EFFECT_KIND,
                "rule_id": f"rule:{effect_id}",
                "source_id": f"source:{effect_id}",
                "rule_ir_hash": "0" * 64,
                "clause_id": f"clause:{effect_id}",
                "effect_index": 0,
                "source_span": {"start": 0, "end": 1, "text": "x"},
                "target": {
                    "kind": target_kind,
                    "source_span": {"start": 0, "end": 1, "text": "x"},
                    "parameters": [],
                },
                "target_unit_instance_ids": list(target_unit_instance_ids),
                "duration": None,
                "conditions": list(conditions),
                "effect": {
                    "kind": effect_kind,
                    "source_span": {"start": 0, "end": 1, "text": "x"},
                    "parameters": parameter_payloads,
                },
                "context": {
                    "state": None,
                    "player_id": owner_player_id,
                    "phase": BattlePhase.SHOOTING.value,
                    "source_model_instance_id": source_model_instance_id,
                },
            }
        ),
    )


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
