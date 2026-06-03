from __future__ import annotations

import json
from typing import cast

import pytest

from warhammer40k_core.core.attributes import Characteristic, CharacteristicValue
from warhammer40k_core.core.dice import DiceExpression
from warhammer40k_core.core.wargear import Wargear, WargearError, WargearPayload
from warhammer40k_core.core.weapon_profiles import (
    AbilityCondition,
    AbilityDescriptor,
    AbilityKind,
    AbilityParameter,
    AbilityTiming,
    AttackProfile,
    DamageProfile,
    RangeProfile,
    RangeProfileKind,
    WeaponKeyword,
    WeaponProfile,
    WeaponProfileError,
    WeaponProfilePayload,
    ability_condition_from_token,
    ability_kind_from_token,
    ability_timing_from_token,
    canonical_weapon_keyword_tokens,
    range_profile_kind_from_token,
    weapon_keyword_from_token,
)
from warhammer40k_core.rules.keywords import canonical_rule_keyword_tokens
from warhammer40k_core.rules.text_normalization import canonical_keyword_forms


def _bolt_rifle_profile() -> WeaponProfile:
    return WeaponProfile(
        profile_id="bolt-rifle:standard",
        name="Bolt rifle",
        range_profile=RangeProfile.distance(24),
        attack_profile=AttackProfile.fixed(2),
        skill=CharacteristicValue.from_raw(Characteristic.BALLISTIC_SKILL, 3),
        strength=CharacteristicValue.from_raw(Characteristic.STRENGTH, 4),
        armor_penetration=CharacteristicValue.from_raw(Characteristic.ARMOR_PENETRATION, -1),
        damage_profile=DamageProfile.fixed(1),
        keywords=(WeaponKeyword.RAPID_FIRE, WeaponKeyword.ASSAULT),
    )


def test_weapon_keywords_are_canonical_tokens_shared_with_rule_normalization() -> None:
    assert canonical_keyword_forms() == (
        *canonical_weapon_keyword_tokens(),
        *canonical_rule_keyword_tokens(),
    )
    assert "Feel No Pain" in canonical_rule_keyword_tokens()
    assert "Feel No Pain" not in canonical_weapon_keyword_tokens()
    assert weapon_keyword_from_token("Rapid Fire") is WeaponKeyword.RAPID_FIRE
    assert weapon_keyword_from_token("Close-quarters") is WeaponKeyword.CLOSE_QUARTERS
    assert weapon_keyword_from_token("Cleave") is WeaponKeyword.CLEAVE

    with pytest.raises(WeaponProfileError):
        weapon_keyword_from_token("rapid fire")
    with pytest.raises(WeaponProfileError):
        weapon_keyword_from_token("Feel No Pain")


def test_weapon_profile_rejects_non_weapon_rule_keywords() -> None:
    with pytest.raises(WeaponProfileError):
        WeaponProfile(
            profile_id="bad-keyword",
            name="Bad keyword",
            range_profile=RangeProfile.distance(24),
            attack_profile=AttackProfile.fixed(1),
            skill=CharacteristicValue.from_raw(Characteristic.BALLISTIC_SKILL, 3),
            strength=CharacteristicValue.from_raw(Characteristic.STRENGTH, 4),
            armor_penetration=CharacteristicValue.from_raw(Characteristic.ARMOR_PENETRATION, 0),
            damage_profile=DamageProfile.fixed(1),
            keywords=(cast(WeaponKeyword, "Feel No Pain"),),
        )


def test_range_attack_and_damage_profiles_consume_parsed_values() -> None:
    range_profile = RangeProfile.distance(18)
    melee_profile = RangeProfile.melee()
    attack_profile = AttackProfile.dice(DiceExpression(quantity=1, sides=6, modifier=3))
    damage_profile = DamageProfile.dice(DiceExpression(quantity=1, sides=3))

    assert range_profile.to_payload() == {"kind": "distance", "distance_inches": 18}
    assert melee_profile.to_payload() == {"kind": "melee", "distance_inches": None}
    assert attack_profile.to_payload()["dice_expression"] == {
        "quantity": 1,
        "sides": 6,
        "modifier": 3,
    }
    assert damage_profile.to_payload()["dice_expression"] == {
        "quantity": 1,
        "sides": 3,
        "modifier": 0,
    }


def test_ability_descriptors_are_typed_payload_data_without_execution() -> None:
    abilities = (
        AbilityDescriptor.devastating_wounds(),
        AbilityDescriptor.sustained_hits(1),
        AbilityDescriptor.lethal_hits(target_keywords=("Vehicle",)),
        AbilityDescriptor.cleave(2),
        AbilityDescriptor.melta(2),
        AbilityDescriptor.rapid_fire(1),
        AbilityDescriptor.anti_keyword("Infantry", 4),
        AbilityDescriptor.sustained_hits(2, target_keywords=("INFANTRY/BEASTS",)),
        AbilityDescriptor.heavy(),
    )
    payloads = [ability.to_payload() for ability in abilities]
    blob = json.dumps(payloads, sort_keys=True)

    assert payloads[0]["ability_kind"] == AbilityKind.DEVASTATING_WOUNDS.value
    assert payloads[0]["parameters"] == [{"name": "effect", "value": "mortal_wounds"}]
    assert payloads[1]["ability_kind"] == AbilityKind.SUSTAINED_HITS.value
    assert payloads[1]["parameters"] == [{"name": "value", "value": 1}]
    assert payloads[2]["ability_kind"] == AbilityKind.LETHAL_HITS.value
    assert payloads[2]["target_keywords"] == ["VEHICLE"]
    assert payloads[3]["ability_kind"] == AbilityKind.CLEAVE.value
    assert payloads[3]["parameters"] == [{"name": "value", "value": 2}]
    assert payloads[6]["ability_kind"] == AbilityKind.ANTI_KEYWORD.value
    assert payloads[6]["parameters"] == [
        {"name": "keyword", "value": "INFANTRY"},
        {"name": "threshold", "value": 4},
    ]
    assert payloads[7]["target_keywords"] == ["INFANTRY", "BEASTS"]
    assert payloads[8]["condition"] == AbilityCondition.STATIONARY_OR_POLICY_DEFINED.value
    assert payloads[8]["timing"] == AbilityTiming.MOVEMENT_CONDITIONED.value
    assert "<" not in blob
    assert "object at 0x" not in blob
    assert tuple(AbilityDescriptor.from_payload(payload) for payload in payloads) == abilities


def test_ability_descriptors_fail_fast_for_unsupported_shapes() -> None:
    assert ability_kind_from_token(AbilityKind.MELTA) is AbilityKind.MELTA
    assert ability_timing_from_token(AbilityTiming.ATTACK_SEQUENCE) is AbilityTiming.ATTACK_SEQUENCE
    assert (
        ability_condition_from_token(AbilityCondition.STATIONARY_OR_POLICY_DEFINED)
        is AbilityCondition.STATIONARY_OR_POLICY_DEFINED
    )
    assert ability_timing_from_token(None) is None
    assert ability_condition_from_token(None) is None

    with pytest.raises(WeaponProfileError):
        AbilityDescriptor.sustained_hits(0)
    with pytest.raises(WeaponProfileError):
        AbilityDescriptor.lethal_hits(target_keywords=("Vehicle/",))
    with pytest.raises(WeaponProfileError):
        AbilityDescriptor.lethal_hits(target_keywords=("Vehicle/Vehicle",))
    with pytest.raises(WeaponProfileError):
        AbilityDescriptor.anti_keyword("Infantry", 1)
    with pytest.raises(WeaponProfileError):
        AbilityDescriptor(
            ability_id="bad-devastating-wounds",
            name="Bad Devastating Wounds",
            ability_kind=AbilityKind.DEVASTATING_WOUNDS,
            parameters=(AbilityParameter(name="effect", value="unsupported"),),
            timing=AbilityTiming.ATTACK_SEQUENCE,
        )
    with pytest.raises(WeaponProfileError):
        AbilityDescriptor(
            ability_id="bad-anti-keyword",
            name="Bad Anti",
            ability_kind=AbilityKind.ANTI_KEYWORD,
            parameters=(
                AbilityParameter(name="keyword", value="Infantry"),
                AbilityParameter(name="threshold", value=4),
            ),
            timing=AbilityTiming.ATTACK_SEQUENCE,
        )
    with pytest.raises(WeaponProfileError):
        AbilityDescriptor(
            ability_id="bad-heavy",
            name="Bad Heavy",
            ability_kind=AbilityKind.HEAVY,
        )
    with pytest.raises(WeaponProfileError):
        AbilityDescriptor(
            ability_id="conditioned-rapid-fire",
            name="Conditioned Rapid Fire",
            ability_kind=AbilityKind.RAPID_FIRE,
            parameters=(AbilityParameter.integer(1),),
            condition=AbilityCondition.STATIONARY_OR_POLICY_DEFINED,
        )
    with pytest.raises(WeaponProfileError):
        AbilityDescriptor(
            ability_id="bad-sustained-timing",
            name="Bad Sustained Hits",
            ability_kind=AbilityKind.SUSTAINED_HITS,
            parameters=(AbilityParameter.integer(1),),
            timing=None,
        )
    with pytest.raises(WeaponProfileError):
        AbilityDescriptor(
            ability_id="bad-heavy-timing",
            name="Bad Heavy",
            ability_kind=AbilityKind.HEAVY,
            timing=AbilityTiming.ATTACK_SEQUENCE,
            condition=AbilityCondition.STATIONARY_OR_POLICY_DEFINED,
        )
    with pytest.raises(WeaponProfileError):
        AbilityDescriptor(
            ability_id="ability:prefixed",
            name="Prefixed",
            ability_kind=AbilityKind.MELTA,
            parameters=(AbilityParameter.integer(2),),
        )
    with pytest.raises(WeaponProfileError):
        AbilityDescriptor(
            ability_id="duplicate-parameters",
            name="Duplicate parameters",
            ability_kind=AbilityKind.MELTA,
            parameters=(AbilityParameter.integer(2), AbilityParameter.integer(3)),
        )
    with pytest.raises(WeaponProfileError):
        AbilityParameter(name="value", value=float("inf"))
    with pytest.raises(WeaponProfileError):
        AbilityParameter(name="value", value="")
    with pytest.raises(WeaponProfileError):
        ability_kind_from_token(cast(str, 1))
    with pytest.raises(WeaponProfileError):
        ability_kind_from_token("unsupported")
    with pytest.raises(WeaponProfileError):
        ability_timing_from_token(cast(str, 1))
    with pytest.raises(WeaponProfileError):
        ability_timing_from_token("unsupported")
    with pytest.raises(WeaponProfileError):
        ability_condition_from_token(cast(str, 1))
    with pytest.raises(WeaponProfileError):
        ability_condition_from_token("unsupported")


def test_weapon_profile_identity_and_serialization_are_stable() -> None:
    profile = _bolt_rifle_profile()
    same_profile = _bolt_rifle_profile()
    payload = cast(
        WeaponProfilePayload,
        json.loads(json.dumps(profile.to_payload(), sort_keys=True)),
    )

    assert profile.stable_identity() == "weapon-profile:bolt-rifle:standard"
    assert profile.to_payload() == same_profile.to_payload()
    assert WeaponProfile.from_payload(payload).to_payload() == profile.to_payload()
    assert "<" not in json.dumps(profile.to_payload())
    assert "object at 0x" not in json.dumps(profile.to_payload())

    with pytest.raises(WeaponProfileError):
        WeaponProfile(
            profile_id="weapon-profile:bolt-rifle",
            name="Bolt rifle",
            range_profile=RangeProfile.distance(24),
            attack_profile=AttackProfile.fixed(2),
            skill=CharacteristicValue.from_raw(Characteristic.BALLISTIC_SKILL, 3),
            strength=CharacteristicValue.from_raw(Characteristic.STRENGTH, 4),
            armor_penetration=CharacteristicValue.from_raw(Characteristic.ARMOR_PENETRATION, -1),
            damage_profile=DamageProfile.fixed(1),
        )


def test_weapon_profile_keywords_are_deduplicated_and_sorted_deterministically() -> None:
    profile = WeaponProfile(
        profile_id="deterministic-keywords",
        name="Deterministic keywords",
        range_profile=RangeProfile.distance(12),
        attack_profile=AttackProfile.fixed(1),
        skill=CharacteristicValue.from_raw(Characteristic.BALLISTIC_SKILL, 3),
        strength=CharacteristicValue.from_raw(Characteristic.STRENGTH, 4),
        armor_penetration=CharacteristicValue.from_raw(Characteristic.ARMOR_PENETRATION, 0),
        damage_profile=DamageProfile.fixed(1),
        keywords=(WeaponKeyword.TORRENT, WeaponKeyword.ASSAULT),
    )

    assert profile.keywords == (WeaponKeyword.ASSAULT, WeaponKeyword.TORRENT)

    with pytest.raises(WeaponProfileError):
        WeaponProfile(
            profile_id="duplicate-keywords",
            name="Duplicate keywords",
            range_profile=RangeProfile.distance(12),
            attack_profile=AttackProfile.fixed(1),
            skill=CharacteristicValue.from_raw(Characteristic.BALLISTIC_SKILL, 3),
            strength=CharacteristicValue.from_raw(Characteristic.STRENGTH, 4),
            armor_penetration=CharacteristicValue.from_raw(Characteristic.ARMOR_PENETRATION, 0),
            damage_profile=DamageProfile.fixed(1),
            keywords=(WeaponKeyword.ASSAULT, WeaponKeyword.ASSAULT),
        )


def test_weapon_profile_abilities_are_deduplicated_and_sorted_deterministically() -> None:
    rapid_fire = AbilityDescriptor.rapid_fire(1)
    sustained_hits = AbilityDescriptor.sustained_hits(1)
    profile = WeaponProfile(
        profile_id="deterministic-abilities",
        name="Deterministic abilities",
        range_profile=RangeProfile.distance(12),
        attack_profile=AttackProfile.fixed(1),
        skill=CharacteristicValue.from_raw(Characteristic.BALLISTIC_SKILL, 3),
        strength=CharacteristicValue.from_raw(Characteristic.STRENGTH, 4),
        armor_penetration=CharacteristicValue.from_raw(Characteristic.ARMOR_PENETRATION, 0),
        damage_profile=DamageProfile.fixed(1),
        abilities=(sustained_hits, rapid_fire),
    )
    payload = cast(
        WeaponProfilePayload,
        json.loads(json.dumps(profile.to_payload(), sort_keys=True)),
    )

    assert profile.abilities == (rapid_fire, sustained_hits)
    assert WeaponProfile.from_payload(payload).to_payload() == profile.to_payload()

    with pytest.raises(WeaponProfileError):
        WeaponProfile(
            profile_id="duplicate-abilities",
            name="Duplicate abilities",
            range_profile=RangeProfile.distance(12),
            attack_profile=AttackProfile.fixed(1),
            skill=CharacteristicValue.from_raw(Characteristic.BALLISTIC_SKILL, 3),
            strength=CharacteristicValue.from_raw(Characteristic.STRENGTH, 4),
            armor_penetration=CharacteristicValue.from_raw(Characteristic.ARMOR_PENETRATION, 0),
            damage_profile=DamageProfile.fixed(1),
            abilities=(rapid_fire, rapid_fire),
        )
    with pytest.raises(WeaponProfileError):
        WeaponProfile(
            profile_id="bad-ability",
            name="Bad ability",
            range_profile=RangeProfile.distance(12),
            attack_profile=AttackProfile.fixed(1),
            skill=CharacteristicValue.from_raw(Characteristic.BALLISTIC_SKILL, 3),
            strength=CharacteristicValue.from_raw(Characteristic.STRENGTH, 4),
            armor_penetration=CharacteristicValue.from_raw(Characteristic.ARMOR_PENETRATION, 0),
            damage_profile=DamageProfile.fixed(1),
            abilities=(cast(AbilityDescriptor, "rapid-fire"),),
        )


def test_weapon_ability_descriptors_reject_invalid_phase13d_shapes() -> None:
    with pytest.raises(WeaponProfileError, match="attack timing"):
        AbilityDescriptor(
            ability_id="rapid-fire:bad-timing",
            name="Rapid Fire bad timing",
            ability_kind=AbilityKind.RAPID_FIRE,
            parameters=(AbilityParameter.integer(1),),
        )
    with pytest.raises(WeaponProfileError, match="must not include a condition"):
        AbilityDescriptor(
            ability_id="melta:bad-condition",
            name="Melta bad condition",
            ability_kind=AbilityKind.MELTA,
            parameters=(AbilityParameter.integer(1),),
            timing=AbilityTiming.ATTACK_SEQUENCE,
            condition=AbilityCondition.STATIONARY_OR_POLICY_DEFINED,
        )
    with pytest.raises(WeaponProfileError, match="must include one value parameter"):
        AbilityDescriptor(
            ability_id="sustained-hits:bad-parameters",
            name="Sustained Hits bad parameters",
            ability_kind=AbilityKind.SUSTAINED_HITS,
            parameters=(),
            timing=AbilityTiming.ATTACK_SEQUENCE,
        )
    with pytest.raises(WeaponProfileError, match="must include keyword and threshold"):
        AbilityDescriptor(
            ability_id="anti-keyword:bad-parameters",
            name="Anti bad parameters",
            ability_kind=AbilityKind.ANTI_KEYWORD,
            parameters=(AbilityParameter(name="keyword", value="INFANTRY"),),
            timing=AbilityTiming.ATTACK_SEQUENCE,
        )
    with pytest.raises(WeaponProfileError, match="must be canonical"):
        AbilityDescriptor(
            ability_id="anti-keyword:bad-keyword",
            name="Anti bad keyword",
            ability_kind=AbilityKind.ANTI_KEYWORD,
            parameters=(
                AbilityParameter(name="keyword", value="infantry"),
                AbilityParameter(name="threshold", value=4),
            ),
            timing=AbilityTiming.ATTACK_SEQUENCE,
        )
    with pytest.raises(WeaponProfileError, match="must be between 2 and 6"):
        AbilityDescriptor.anti_keyword("INFANTRY", 7)
    with pytest.raises(WeaponProfileError, match="must use movement-conditioned timing"):
        AbilityDescriptor(
            ability_id="heavy:bad-timing",
            name="Heavy bad timing",
            ability_kind=AbilityKind.HEAVY,
            timing=AbilityTiming.ATTACK_SEQUENCE,
            condition=AbilityCondition.STATIONARY_OR_POLICY_DEFINED,
        )
    with pytest.raises(WeaponProfileError, match="stationary policy condition"):
        AbilityDescriptor(
            ability_id="heavy:bad-condition",
            name="Heavy bad condition",
            ability_kind=AbilityKind.HEAVY,
            timing=AbilityTiming.MOVEMENT_CONDITIONED,
        )


def test_weapon_profile_rejects_unparsed_or_mismatched_profile_data() -> None:
    with pytest.raises(WeaponProfileError):
        AttackProfile()
    with pytest.raises(WeaponProfileError):
        AttackProfile(fixed_attacks=1, dice_expression=DiceExpression(quantity=1, sides=6))
    with pytest.raises(WeaponProfileError):
        AttackProfile.dice(cast(DiceExpression, "D6"))
    with pytest.raises(WeaponProfileError):
        DamageProfile.fixed(0)
    with pytest.raises(WeaponProfileError):
        RangeProfile.distance(0)
    with pytest.raises(WeaponProfileError):
        RangeProfile(kind=RangeProfileKind.MELEE, distance_inches=1)
    with pytest.raises(WeaponProfileError):
        range_profile_kind_from_token("unsupported")
    with pytest.raises(WeaponProfileError):
        WeaponProfile(
            profile_id="bad-skill",
            name="Bad skill",
            range_profile=RangeProfile.distance(12),
            attack_profile=AttackProfile.fixed(1),
            skill=CharacteristicValue.from_raw(Characteristic.STRENGTH, 3),
            strength=CharacteristicValue.from_raw(Characteristic.STRENGTH, 4),
            armor_penetration=CharacteristicValue.from_raw(Characteristic.ARMOR_PENETRATION, 0),
            damage_profile=DamageProfile.fixed(1),
        )


def test_weapon_profile_rejects_modified_characteristic_values() -> None:
    with pytest.raises(WeaponProfileError):
        WeaponProfile(
            profile_id="modified-ap",
            name="Modified AP",
            range_profile=RangeProfile.distance(24),
            attack_profile=AttackProfile.fixed(2),
            skill=CharacteristicValue.from_raw(Characteristic.BALLISTIC_SKILL, 3),
            strength=CharacteristicValue.from_raw(Characteristic.STRENGTH, 4),
            armor_penetration=CharacteristicValue(
                characteristic=Characteristic.ARMOR_PENETRATION,
                raw=-1,
                base=-1,
                final=-2,
                applied_modifier_ids=("storm-doctrine",),
            ),
            damage_profile=DamageProfile.fixed(1),
        )

    with pytest.raises(WeaponProfileError):
        WeaponProfile(
            profile_id="modified-skill",
            name="Modified skill",
            range_profile=RangeProfile.distance(24),
            attack_profile=AttackProfile.fixed(2),
            skill=CharacteristicValue(
                characteristic=Characteristic.BALLISTIC_SKILL,
                raw=4,
                base=4,
                final=3,
                applied_modifier_ids=(),
            ),
            strength=CharacteristicValue.from_raw(Characteristic.STRENGTH, 4),
            armor_penetration=CharacteristicValue.from_raw(Characteristic.ARMOR_PENETRATION, -1),
            damage_profile=DamageProfile.fixed(1),
        )


def test_weapon_profile_payload_errors_stay_in_weapon_profile_domain() -> None:
    profile_payload = _bolt_rifle_profile().to_payload()
    profile_payload["skill"]["raw"] = -1

    with pytest.raises(WeaponProfileError):
        WeaponProfile.from_payload(profile_payload)

    attack_payload = AttackProfile.dice(DiceExpression(quantity=1, sides=6)).to_payload()
    dice_payload = attack_payload["dice_expression"]
    assert dice_payload is not None
    dice_payload["sides"] = 1

    with pytest.raises(WeaponProfileError):
        AttackProfile.from_payload(attack_payload)


def test_wargear_groups_profiles_with_stable_ids_and_payloads() -> None:
    profile = _bolt_rifle_profile()
    wargear = Wargear(
        wargear_id="bolt-rifle",
        name="Bolt rifle",
        weapon_profiles=(profile,),
    )
    payload = cast(
        WargearPayload,
        json.loads(json.dumps(wargear.to_payload(), sort_keys=True)),
    )

    assert wargear.stable_identity() == "wargear:bolt-rifle"
    assert wargear.weapon_profile_by_id(profile.profile_id) == profile
    assert Wargear.from_payload(payload).to_payload() == wargear.to_payload()
    assert "<" not in json.dumps(wargear.to_payload())
    assert "object at 0x" not in json.dumps(wargear.to_payload())


def test_wargear_rejects_invalid_or_ambiguous_profiles() -> None:
    profile = _bolt_rifle_profile()

    with pytest.raises(WargearError):
        Wargear(wargear_id=" ", name="Bad")
    with pytest.raises(WargearError):
        Wargear(wargear_id="wargear:bolt-rifle", name="Bolt rifle")
    with pytest.raises(WargearError):
        Wargear(
            wargear_id="duplicate-profile",
            name="Duplicate profile",
            weapon_profiles=(profile, profile),
        )
    with pytest.raises(WargearError):
        Wargear(
            wargear_id="bad-profile",
            name="Bad profile",
            weapon_profiles=(cast(WeaponProfile, "profile-id"),),
        )
    with pytest.raises(WargearError):
        Wargear(
            wargear_id="bolt-rifle",
            name="Bolt rifle",
            weapon_profiles=(profile,),
        ).weapon_profile_by_id("missing")


def test_wargear_payload_errors_stay_in_wargear_domain() -> None:
    payload = Wargear(
        wargear_id="bolt-rifle",
        name="Bolt rifle",
        weapon_profiles=(_bolt_rifle_profile(),),
    ).to_payload()
    payload["weapon_profiles"][0]["skill"]["raw"] = -1

    with pytest.raises(WargearError):
        Wargear.from_payload(payload)
