"""Small real attacks with context-restricted persisted modifier permissions."""

from __future__ import annotations

from dataclasses import replace

from tests.generic_modifier_helpers import generic_effect
from tests.phase13b_shooting_declaration_helpers import (
    _canonical_catalog,
    _compact_intercessor_catalog,
    _shooting_lifecycle,
)
from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.core.attributes import Characteristic, CharacteristicValue
from warhammer40k_core.core.weapon_profiles import AttackProfile, DamageProfile, WeaponKeyword
from warhammer40k_core.engine.event_log import JsonValue
from warhammer40k_core.engine.lifecycle import GameLifecycle
from warhammer40k_core.engine.profile_modifiers import profile_with_delta
from warhammer40k_core.geometry.pose import Pose

ATTACKER_ID = "army-alpha:intercessor-1"
TARGET_ID = "army-beta:enemy"
OTHER_TARGET_ID = "army-beta:other-enemy"


def attack_permission_session(
    *,
    kind: str,
    role: str,
    selected_target_matches: bool | None = None,
    strength_gate: bool = False,
    strength: int = 20,
) -> LocalGameSession:
    catalog = _compact_intercessor_catalog(_canonical_catalog())
    catalog = replace(
        catalog,
        datasheets=tuple(
            replace(
                sheet,
                model_profiles=tuple(
                    replace(
                        profile,
                        characteristics=tuple(
                            profile_with_delta(
                                value,
                                1,
                                source_id="source:permission-save-penalty",
                                modifier_id="permission-save-penalty",
                            )
                            if kind == "save_characteristic"
                            and value.characteristic is Characteristic.SAVE
                            else value
                            for value in profile.characteristics
                        ),
                    )
                    for profile in sheet.model_profiles
                ),
            )
            for sheet in catalog.datasheets
        ),
        wargear=tuple(
            replace(
                item,
                weapon_profiles=tuple(
                    replace(
                        profile,
                        attack_profile=AttackProfile.fixed(2),
                        strength=CharacteristicValue.from_raw(Characteristic.STRENGTH, strength),
                        damage_profile=DamageProfile.fixed(1),
                        armor_penetration=CharacteristicValue.from_raw(
                            Characteristic.ARMOR_PENETRATION, 0
                        ),
                        keywords=() if kind == "hit_roll" else (WeaponKeyword.TORRENT,),
                        abilities=(),
                    )
                    for profile in item.weapon_profiles
                ),
            )
            for item in catalog.wargear
        ),
    )
    lifecycle, _units = _shooting_lifecycle(
        alpha_unit_ids=("intercessor-1",),
        alpha_unit_specs=(
            ("intercessor-1", "core-intercessor-like-infantry", "core-intercessor-like", 1),
        ),
        enemy_unit_specs=(
            ("enemy", "core-intercessor-like-infantry", "core-intercessor-like", 1),
            ("other-enemy", "core-intercessor-like-infantry", "core-intercessor-like", 1),
        ),
        enemy_pose=Pose.at(30, 35),
        catalog=catalog,
        game_id="order93-permission-context",
    )
    state = lifecycle.state
    assert state is not None
    defensive = kind in {"save_characteristic", "save_roll"}
    owner_id = "player-b" if defensive else "player-a"
    subject_unit_id = TARGET_ID if defensive else ATTACKER_ID
    parameters: dict[str, JsonValue] = {
        "ability": "modifier_ignore_permission",
        "selection": "any_or_all",
        "modifier_kinds": [kind],
        "attack_role": role,
        "source_phase": "shooting",
    }
    if selected_target_matches is not None:
        parameters["selected_target_unit_instance_id"] = (
            TARGET_ID if selected_target_matches else OTHER_TARGET_ID
        )
    if strength_gate:
        parameters["target_constraint"] = "attack_strength_greater_than_target_toughness"
    state.record_persisting_effect(
        generic_effect(
            effect_id="permission:restricted",
            owner_player_id=owner_id,
            target_unit_instance_ids=(subject_unit_id,),
            target_kind="this_unit",
            effect_kind="grant_ability",
            parameters=parameters,
        )
    )
    if kind != "save_characteristic":
        state.record_persisting_effect(
            generic_effect(
                effect_id="permission:roll-penalty",
                owner_player_id=owner_id,
                target_unit_instance_ids=(subject_unit_id,),
                target_kind="this_unit",
                effect_kind="modify_dice_roll",
                parameters={
                    "roll_type": kind.removesuffix("_roll"),
                    "delta": -1,
                    "attack_role": "target" if defensive else "attacker",
                },
            )
        )
    # Grants are part of the initial snapshot, before any attack or modifier origin.
    return LocalGameSession(lifecycle=GameLifecycle.from_payload(lifecycle.to_payload()))
