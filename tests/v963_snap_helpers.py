"""Canonical source-effect consumers for current Snap and ordinary Shooting."""

from dataclasses import replace
from typing import cast

from tests.fire_overwatch_helpers import SHOOTER, overwatch_session
from tests.generic_modifier_helpers import generic_effect
from tests.phase13b_shooting_declaration_helpers import (
    _canonical_catalog,
    _compact_intercessor_catalog,
    _compact_shooting_lifecycle,
)
from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.core.attributes import Characteristic, CharacteristicValue
from warhammer40k_core.core.dice import DiceExpression
from warhammer40k_core.core.weapon_profiles import AbilityDescriptor, AttackProfile, WeaponKeyword
from warhammer40k_core.engine.event_log import JsonValue
from warhammer40k_core.engine.lifecycle import GameLifecycle
from warhammer40k_core.engine.weapon_abilities import SNAP_SHOOTING_RULE_ID


def snap_consumer_session(
    *, snap: bool, random_attacks: bool, sustained: int | str, wound_source: str
) -> LocalGameSession:
    catalog = _compact_intercessor_catalog(_canonical_catalog())
    catalog = replace(
        catalog,
        wargear=tuple(
            replace(
                item,
                weapon_profiles=tuple(
                    replace(
                        weapon,
                        attack_profile=AttackProfile.dice(DiceExpression(1, 6, 18))
                        if random_attacks
                        else AttackProfile.fixed(24),
                        skill=CharacteristicValue.from_raw(weapon.skill.characteristic, 6),
                        strength=CharacteristicValue.from_raw(Characteristic.STRENGTH, 1),
                        keywords=(
                            WeaponKeyword.LETHAL_HITS,
                            WeaponKeyword.SUSTAINED_HITS,
                            WeaponKeyword.DEVASTATING_WOUNDS,
                        ),
                        abilities=(
                            AbilityDescriptor.lethal_hits(),
                            AbilityDescriptor.sustained_hits(sustained),
                            AbilityDescriptor.devastating_wounds(),
                            *(
                                (AbilityDescriptor.anti_keyword("INFANTRY", 3),)
                                if wound_source == "anti"
                                else ()
                            ),
                        ),
                    )
                    for weapon in item.weapon_profiles
                ),
            )
            for item in catalog.wargear
        ),
    )
    if snap:
        session = overwatch_session(catalog=catalog, attacks=None, enemy_models=5)
        unit_id = SHOOTER
    else:
        lifecycle, _ = _compact_shooting_lifecycle(catalog=catalog, enemy_model_count=5)
        session = LocalGameSession(lifecycle=GameLifecycle.from_payload(lifecycle.to_payload()))
        unit_id = "army-alpha:intercessor-1"
    state = session.lifecycle.state
    assert state is not None
    for name, parameters in (
        (
            "hit-critical",
            {
                "attack_role": "attacker",
                "roll_type": "hit",
                "status": "critical_hit_threshold",
                "critical_threshold": 2,
                **({"required_targeting_rule_id": SNAP_SHOOTING_RULE_ID} if snap else {}),
            },
        ),
        *(
            (
                (
                    "wound-critical",
                    {
                        "attack_role": "attacker",
                        "roll_type": "wound",
                        "status": "critical_wound_threshold",
                        "critical_threshold": 3,
                    },
                ),
            )
            if wound_source == "generic"
            else ()
        ),
    ):
        state.record_persisting_effect(
            generic_effect(
                effect_id=f"v963-snap:{name}",
                owner_player_id="player-a",
                target_unit_instance_ids=(unit_id,),
                target_kind="this_unit",
                effect_kind="set_contextual_status",
                parameters=cast(dict[str, JsonValue], parameters),
            )
        )
    # The source effects enter through the same persisted typed boundary.
    return LocalGameSession.from_persistence_payload(session.to_persistence_payload())
