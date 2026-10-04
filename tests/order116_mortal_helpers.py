"""Canonical source permission; no named faction or Hallowed Ground support claim."""

from __future__ import annotations

from dataclasses import replace

from tests.phase13b_shooting_declaration_helpers import (
    _canonical_catalog,
    _compact_intercessor_catalog,
    _compact_shooting_lifecycle,
)
from tests.phase15c_fight_order_helpers import fight_lifecycle
from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.core.attributes import Characteristic, CharacteristicValue
from warhammer40k_core.core.weapon_profiles import (
    AbilityDescriptor,
    AttackProfile,
    DamageProfile,
    WeaponKeyword,
)
from warhammer40k_core.engine.additional_attack_mortal_permissions import (
    additional_attack_mortal_permission_effect,
)
from warhammer40k_core.engine.damage_allocation import FeelNoPainSource
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
                        + ((WeaponKeyword.DEVASTATING_WOUNDS,) if devastating else ()),
                        abilities=(
                            (AbilityDescriptor.devastating_wounds(),) if devastating else ()
                        ),
                        attack_profile=AttackProfile.fixed(attacks),
                        damage_profile=DamageProfile.fixed(1),
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
    if optional_fnp:
        for model in target.own_models:
            state.record_model_feel_no_pain_sources(
                model_instance_id=model.model_instance_id,
                sources=(FeelNoPainSource(source_id="order116:fnp", threshold=6),),
                decline_allowed=True,
            )
    return LocalGameSession(lifecycle=GameLifecycle.from_payload(lifecycle.to_payload()))
