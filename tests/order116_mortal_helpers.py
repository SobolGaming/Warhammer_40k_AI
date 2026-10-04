"""Canonical source permission; no named faction or Hallowed Ground support claim."""

from __future__ import annotations

from dataclasses import replace

from tests.phase13b_shooting_declaration_helpers import (
    _canonical_catalog,
    _compact_intercessor_catalog,
    _compact_shooting_lifecycle,
    _grant_command_reroll_cp,
)
from tests.phase15c_fight_order_helpers import fight_lifecycle
from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.core.attributes import Characteristic, CharacteristicValue
from warhammer40k_core.core.dice import DiceExpression
from warhammer40k_core.core.weapon_profiles import (
    AbilityDescriptor,
    AttackProfile,
    DamageProfile,
    WeaponKeyword,
)
from warhammer40k_core.engine.additional_attack_mortal_permissions import (
    additional_attack_mortal_permission_effect,
)
from warhammer40k_core.engine.damage_allocation import FeelNoPainAttackCondition, FeelNoPainSource
from warhammer40k_core.engine.lifecycle import GameLifecycle
from warhammer40k_core.engine.phase import BattlePhase
from warhammer40k_core.geometry.pose import Pose

SOURCE_ID = (
    "gw-11e-phase17e-exact-faction-subrules-2026-27:bridge-source-row:Enhancements:000009777003"
)


def additional_mortal_session(
    phase: BattlePhase,
    *,
    mortal_wounds: int = 1,
    scope: str = "all",
    optional_fnp: bool = False,
    devastating: bool = False,
    attacks: int = 3,
    strength: int = 20,
    enemy_models: int = 2,
    armor_penetration: int = -6,
    psychic: bool = False,
    psychic_fnp: bool = False,
    random_devastating_damage: bool = False,
    command_reroll_player_id: str | None = None,
    second_permission: bool = False,
) -> LocalGameSession:
    catalog = _compact_intercessor_catalog(_canonical_catalog())
    catalog = replace(
        catalog,
        wargear=tuple(
            replace(
                row,
                weapon_profiles=tuple(
                    replace(
                        weapon,
                        keywords=((WeaponKeyword.TORRENT,) if phase is BattlePhase.SHOOTING else ())
                        + ((WeaponKeyword.DEVASTATING_WOUNDS,) if devastating else ())
                        + ((WeaponKeyword.PSYCHIC,) if psychic else ()),
                        abilities=((AbilityDescriptor.devastating_wounds(),) if devastating else ())
                        + (
                            (AbilityDescriptor.anti_keyword("INFANTRY", 2),)
                            if random_devastating_damage
                            else ()
                        ),
                        attack_profile=AttackProfile.fixed(attacks),
                        damage_profile=(
                            DamageProfile.dice(DiceExpression(quantity=1, sides=3))
                            if random_devastating_damage
                            else DamageProfile.fixed(1)
                        ),
                        armor_penetration=CharacteristicValue.from_raw(
                            Characteristic.ARMOR_PENETRATION, armor_penetration
                        ),
                        skill=CharacteristicValue.from_raw(weapon.skill.characteristic, 2),
                        strength=CharacteristicValue.from_raw(Characteristic.STRENGTH, strength),
                    )
                    for weapon in row.weapon_profiles
                ),
            )
            for row in catalog.wargear
        ),
    )
    if phase is BattlePhase.SHOOTING:
        lifecycle, units = _compact_shooting_lifecycle(
            catalog=catalog, game_id="order116-shooting", enemy_model_count=enemy_models
        )
    else:
        lifecycle, units = fight_lifecycle(
            alpha_unit_ids=("intercessor-1",),
            enemy_unit_ids=("enemy",),
            origins={"intercessor-1": Pose.at(10, 10), "enemy": Pose.at(12, 10)},
            game_id="order116-fight-2",
            model_count=1,
            catalog=catalog,
            datasheet_id="core-character-leader",
            model_profile_id="core-character-leader",
            fights_first_unit_keys=("intercessor-1",),
        )
    state = lifecycle.state
    assert state is not None
    attacker, target = units["intercessor-1"], units["enemy"]
    if command_reroll_player_id is not None:
        _grant_command_reroll_cp(state, player_id=command_reroll_player_id)
    state.record_persisting_effect(
        additional_attack_mortal_permission_effect(
            state=state,
            effect_id="order116:source-permission",
            source_rule_id=SOURCE_ID,
            source_model_instance_id=attacker.own_models[0].model_instance_id,
            occasion_id="order116:source-occasion",
            weapon_scope=scope,
            mortal_wounds=mortal_wounds,
        )
    )
    if second_permission:
        state.record_persisting_effect(
            additional_attack_mortal_permission_effect(
                state=state,
                effect_id="order116:second-permission",
                source_rule_id=SOURCE_ID,
                source_model_instance_id=attacker.own_models[0].model_instance_id,
                occasion_id="order116:second-occasion",
                weapon_scope=scope,
                mortal_wounds=mortal_wounds,
            )
        )
    if optional_fnp or psychic_fnp:
        for model in target.own_models:
            state.record_model_feel_no_pain_sources(
                model_instance_id=model.model_instance_id,
                sources=(
                    FeelNoPainSource(
                        source_id="order116:fnp",
                        threshold=6,
                        attack_condition=(
                            FeelNoPainAttackCondition.PSYCHIC_ATTACK if psychic_fnp else None
                        ),
                    ),
                ),
                decline_allowed=True,
            )
    return LocalGameSession(lifecycle=GameLifecycle.from_payload(lifecycle.to_payload()))


def gathered_additional_mortal_session() -> LocalGameSession:
    """Two distinct, equivalent physical weapons that the engine legally gathers."""
    from typing import cast

    from tests.phase13b_shooting_declaration_helpers import (
        _catalog_with_same_profile_id_target_cache_collision_weapons,
        _proposal_from_request,
    )
    from tests.psychic_modifier_helpers import pending_request, submit_fixture_request
    from warhammer40k_core.core.weapon_profiles import RangeProfile
    from warhammer40k_core.engine.event_log import validate_json_value
    from warhammer40k_core.engine.weapon_declaration import WeaponDeclaration

    catalog = _catalog_with_same_profile_id_target_cache_collision_weapons()
    common = replace(
        catalog.wargear[-2].weapon_profiles[0],
        keywords=(WeaponKeyword.TORRENT,),
        abilities=(),
        attack_profile=AttackProfile.fixed(3),
        range_profile=RangeProfile.distance(36),
        damage_profile=DamageProfile.fixed(1),
        strength=CharacteristicValue.from_raw(Characteristic.STRENGTH, 20),
        armor_penetration=CharacteristicValue.from_raw(Characteristic.ARMOR_PENETRATION, 0),
    )
    catalog = replace(
        catalog,
        wargear=(
            *catalog.wargear[:-2],
            *(
                replace(
                    row, weapon_profiles=(replace(common, profile_id=f"order116-physical-{i}"),)
                )
                for i, row in enumerate(catalog.wargear[-2:])
            ),
        ),
    )
    lifecycle, units = _compact_shooting_lifecycle(
        alpha_unit_ids=("shooter",),
        enemy_model_count=5,
        catalog=catalog,
        game_id="review116-weapons",
    )
    state = lifecycle.state
    assert state is not None
    state.record_persisting_effect(
        additional_attack_mortal_permission_effect(
            state=state,
            effect_id="order116:gathered-permission",
            source_rule_id=SOURCE_ID,
            source_model_instance_id=units["shooter"].own_models[0].model_instance_id,
            occasion_id="order116:gathered-occasion",
            mortal_wounds=2,
            weapon_scope="ranged",
        )
    )
    for model in units["enemy"].own_models:
        state.record_model_feel_no_pain_sources(
            model_instance_id=model.model_instance_id,
            sources=(FeelNoPainSource(source_id="order116:gathered-fnp", threshold=6),),
            decline_allowed=True,
        )
    session = LocalGameSession(lifecycle=GameLifecycle.from_payload(lifecycle.to_payload()))
    for _ in range(20):
        request = pending_request(session)
        if request.decision_type == "submit_shooting_declaration":
            break
        submit_fixture_request(session, request)
    else:
        raise AssertionError("Gathered physical weapon fixture did not reach declaration.")
    proposal = _proposal_from_request(request=request, target_unit_id="army-beta:enemy")
    assert isinstance(request.payload, dict)
    raw = request.payload["proposal_request"]
    assert isinstance(raw, dict)
    weapons = raw["available_weapons"]
    assert isinstance(weapons, list)
    declarations = []
    for weapon in weapons:
        assert isinstance(weapon, dict)
        declarations.append(
            WeaponDeclaration(
                attacker_model_instance_id=cast(str, weapon["model_instance_id"]),
                weapon_instance_id=cast(str, weapon["weapon_instance_id"]),
                wargear_id=cast(str, weapon["wargear_id"]),
                weapon_profile_id=cast(str, weapon["weapon_profile_id"]),
                target_unit_instance_id="army-beta:enemy",
                shooting_type=proposal.declarations[0].shooting_type,
            )
        )
    proposal = replace(proposal, declarations=tuple(declarations))
    session.submit_parameterized_payload(
        request_id=request.request_id,
        result_id="order116:gathered-declare",
        payload=validate_json_value(proposal.to_payload()),
    )
    return session
