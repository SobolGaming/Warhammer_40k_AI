from __future__ import annotations

from typing import cast

import pytest

from warhammer40k_core.core.attributes import Characteristic, CharacteristicValue
from warhammer40k_core.core.ruleset_descriptor import BattlePhaseKind
from warhammer40k_core.core.weapon_profiles import (
    AbilityDescriptor,
    AbilityKind,
    AttackProfile,
    DamageProfile,
    RangeProfile,
    WeaponKeyword,
    WeaponProfile,
)
from warhammer40k_core.engine.core_stratagem_effects import (
    FIRE_OVERWATCH_EFFECT_KIND,
    GO_TO_GROUND_EFFECT_KIND,
    GO_TO_GROUND_INVULNERABLE_SAVE,
    SMOKESCREEN_EFFECT_KIND,
    SMOKESCREEN_HIT_ROLL_MODIFIER,
    effect_kind,
    effect_payload_bool,
    effect_payload_int,
    unit_effect_hit_roll_modifier,
    unit_effect_invulnerable_save,
    unit_effects_grant_benefit_of_cover,
)
from warhammer40k_core.engine.effects import EffectExpiration, PersistingEffect
from warhammer40k_core.engine.event_log import JsonValue
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.weapon_abilities import (
    BLAST_RULE_ID,
    CLEAVE_RULE_ID,
    HEAVY_RULE_ID,
    MELTA_RULE_ID,
    RAPID_FIRE_RULE_ID,
    DevastatingWoundsResolution,
    anti_keyword_critical_threshold,
    blast_attack_bonus,
    blast_rule_id,
    cleave_attack_bonus,
    cleave_rule_id,
    devastating_wounds_resolution,
    has_weapon_keyword,
    heavy_rule_id,
    melta_damage_bonus,
    melta_rule_id,
    rapid_fire_attack_bonus,
    rapid_fire_rule_id,
    sustained_hits_generated_hits,
    weapon_ability_int_value,
)


def test_phase13d_weapon_ability_helpers_use_structured_descriptors() -> None:
    profile = _profile(
        keywords=(
            WeaponKeyword.ASSAULT,
            WeaponKeyword.BLAST,
            WeaponKeyword.CLEAVE,
            WeaponKeyword.DEVASTATING_WOUNDS,
            WeaponKeyword.MELTA,
            WeaponKeyword.RAPID_FIRE,
            WeaponKeyword.SUSTAINED_HITS,
        ),
        abilities=(
            AbilityDescriptor.devastating_wounds(),
            AbilityDescriptor.cleave(2),
            AbilityDescriptor.rapid_fire(2),
            AbilityDescriptor.melta(3),
            AbilityDescriptor.sustained_hits(2),
        ),
    )

    assert has_weapon_keyword(profile, WeaponKeyword.ASSAULT)
    assert weapon_ability_int_value(profile, AbilityKind.CLEAVE) == 2
    assert weapon_ability_int_value(profile, AbilityKind.RAPID_FIRE) == 2
    assert devastating_wounds_resolution(profile) is DevastatingWoundsResolution.MORTAL_WOUNDS
    assert cleave_attack_bonus(profile, single_target=True, target_model_count=11) == 4
    assert cleave_attack_bonus(profile, single_target=False, target_model_count=11) == 0
    assert rapid_fire_attack_bonus(profile, target_within_half_range=True) == 2
    assert rapid_fire_attack_bonus(profile, target_within_half_range=False) == 0
    assert melta_damage_bonus(profile, target_within_half_range=True) == 3
    assert melta_damage_bonus(profile, target_within_half_range=False) == 0
    assert sustained_hits_generated_hits(profile, critical_hit=True) == 3
    assert sustained_hits_generated_hits(profile, critical_hit=False) == 1
    assert blast_attack_bonus(target_model_count=11) == 2
    assert rapid_fire_rule_id(2) == f"{RAPID_FIRE_RULE_ID}:2"
    assert blast_rule_id(2) == f"{BLAST_RULE_ID}:2"
    assert cleave_rule_id(2) == f"{CLEAVE_RULE_ID}:2"
    assert melta_rule_id(3) == f"{MELTA_RULE_ID}:3"
    assert heavy_rule_id() == HEAVY_RULE_ID


def test_phase13d_weapon_ability_helpers_fail_fast_on_incomplete_profiles() -> None:
    profile = _profile(keywords=(WeaponKeyword.RAPID_FIRE,), abilities=())
    cleave_profile = _profile(keywords=(WeaponKeyword.CLEAVE,), abilities=())
    valid_cleave_profile = _profile(
        keywords=(WeaponKeyword.CLEAVE,),
        abilities=(AbilityDescriptor.cleave(1),),
    )
    devastating_profile = _profile(keywords=(WeaponKeyword.DEVASTATING_WOUNDS,), abilities=())
    orphan_devastating_profile = _profile(
        keywords=(),
        abilities=(AbilityDescriptor.devastating_wounds(),),
    )
    duplicate_profile = _profile(
        keywords=(),
        abilities=(AbilityDescriptor.rapid_fire(1), AbilityDescriptor.rapid_fire(2)),
    )
    no_descriptor_profile = _profile(keywords=(), abilities=())

    with pytest.raises(GameLifecycleError, match="requires a structured ability descriptor"):
        weapon_ability_int_value(profile, AbilityKind.RAPID_FIRE)
    with pytest.raises(GameLifecycleError, match="requires a structured ability descriptor"):
        cleave_attack_bonus(cleave_profile, single_target=True, target_model_count=5)
    with pytest.raises(GameLifecycleError, match="requires a structured ability descriptor"):
        devastating_wounds_resolution(devastating_profile)
    with pytest.raises(GameLifecycleError, match="descriptor requires the weapon keyword"):
        devastating_wounds_resolution(orphan_devastating_profile)
    with pytest.raises(GameLifecycleError, match="duplicate ability descriptors"):
        weapon_ability_int_value(duplicate_profile, AbilityKind.RAPID_FIRE)
    assert weapon_ability_int_value(no_descriptor_profile, AbilityKind.HEAVY) is None
    assert melta_damage_bonus(no_descriptor_profile, target_within_half_range=True) == 0
    assert sustained_hits_generated_hits(no_descriptor_profile, critical_hit=True) == 1
    with pytest.raises(GameLifecycleError, match="Weapon ability helpers require a WeaponProfile"):
        has_weapon_keyword(cast(WeaponProfile, object()), WeaponKeyword.ASSAULT)
    with pytest.raises(GameLifecycleError, match="Weapon ability helpers require WeaponKeyword"):
        has_weapon_keyword(profile, cast(WeaponKeyword, "Assault"))
    with pytest.raises(GameLifecycleError, match="Weapon ability helpers require AbilityKind"):
        weapon_ability_int_value(profile, cast(AbilityKind, "rapid_fire"))
    with pytest.raises(GameLifecycleError, match="Blast target_model_count must be an integer"):
        blast_attack_bonus(target_model_count=cast(int, 1.5))
    with pytest.raises(GameLifecycleError, match="Blast target_model_count must not be negative"):
        blast_attack_bonus(target_model_count=-1)
    with pytest.raises(GameLifecycleError, match="Cleave target_model_count must be an integer"):
        cleave_attack_bonus(
            valid_cleave_profile,
            single_target=True,
            target_model_count=cast(int, 1.5),
        )
    with pytest.raises(GameLifecycleError, match="Cleave target_model_count must not be negative"):
        cleave_attack_bonus(valid_cleave_profile, single_target=True, target_model_count=-1)
    with pytest.raises(GameLifecycleError, match="Rapid Fire value must be an integer"):
        rapid_fire_rule_id(cast(int, "2"))
    with pytest.raises(GameLifecycleError, match="Cleave value must be at least 1"):
        cleave_rule_id(0)
    with pytest.raises(GameLifecycleError, match="Melta value must be at least 1"):
        melta_rule_id(0)
    with pytest.raises(GameLifecycleError, match="Weapon ability keyword must be a string"):
        anti_keyword_critical_threshold(
            profile=no_descriptor_profile,
            target_keywords=(cast(str, 1),),
        )
    with pytest.raises(GameLifecycleError, match="Weapon ability keyword must not be empty"):
        anti_keyword_critical_threshold(profile=no_descriptor_profile, target_keywords=("",))


def test_phase13d_anti_keyword_threshold_matches_canonical_target_keywords() -> None:
    profile = _profile(
        keywords=(),
        abilities=(
            AbilityDescriptor.anti_keyword("INFANTRY", 4),
            AbilityDescriptor.anti_keyword("monster", 5),
        ),
    )

    assert (
        anti_keyword_critical_threshold(
            profile=profile,
            target_keywords=("infantry", "character"),
        )
        == 4
    )
    assert anti_keyword_critical_threshold(profile=profile, target_keywords=("MONSTER",)) == 5
    assert anti_keyword_critical_threshold(profile=profile, target_keywords=("vehicle",)) is None


def test_phase13d_core_stratagem_effect_helpers_read_typed_payloads() -> None:
    go_to_ground = _effect(
        effect_id="phase13d-effect-go-to-ground",
        effect_kind_value=GO_TO_GROUND_EFFECT_KIND,
        payload={
            "benefit_of_cover": True,
            "invulnerable_save": GO_TO_GROUND_INVULNERABLE_SAVE,
        },
    )
    smokescreen = _effect(
        effect_id="phase13d-effect-smokescreen",
        effect_kind_value=SMOKESCREEN_EFFECT_KIND,
        payload={
            "benefit_of_cover": True,
            "hit_roll_modifier": SMOKESCREEN_HIT_ROLL_MODIFIER,
        },
    )
    overwatch = _effect(
        effect_id="phase13d-effect-overwatch",
        effect_kind_value=FIRE_OVERWATCH_EFFECT_KIND,
        payload={},
    )

    assert effect_kind(go_to_ground) == GO_TO_GROUND_EFFECT_KIND
    assert effect_payload_bool(go_to_ground, "benefit_of_cover")
    assert not effect_payload_bool(overwatch, "benefit_of_cover")
    assert effect_payload_int(overwatch, "hit_roll_modifier", 3) == 3
    assert unit_effects_grant_benefit_of_cover((go_to_ground, smokescreen, overwatch))
    assert unit_effect_hit_roll_modifier((go_to_ground, smokescreen, overwatch)) == -1
    assert unit_effect_invulnerable_save((go_to_ground, smokescreen, overwatch)) == 6
    assert unit_effect_invulnerable_save((smokescreen, overwatch)) is None


def test_phase13d_core_stratagem_effect_helpers_fail_fast_on_bad_payloads() -> None:
    smokescreen = _effect(
        effect_id="phase13d-effect-bad-smokescreen",
        effect_kind_value=SMOKESCREEN_EFFECT_KIND,
        payload={"hit_roll_modifier": "minus-one"},
    )
    missing_kind = PersistingEffect(
        effect_id="phase13d-effect-missing-kind",
        source_rule_id="core-stratagem:bad",
        owner_player_id="player-a",
        target_unit_instance_ids=("army-alpha:intercessor-unit-1",),
        started_battle_round=1,
        started_phase=BattlePhaseKind.SHOOTING,
        expiration=EffectExpiration.end_phase(
            battle_round=1,
            phase=BattlePhaseKind.SHOOTING,
            player_id="player-a",
        ),
        effect_payload={},
    )
    non_object_payload = PersistingEffect(
        effect_id="phase13d-effect-missing-kind",
        source_rule_id="core-stratagem:bad",
        owner_player_id="player-a",
        target_unit_instance_ids=("army-alpha:intercessor-unit-1",),
        started_battle_round=1,
        started_phase=BattlePhaseKind.SHOOTING,
        expiration=EffectExpiration.end_phase(
            battle_round=1,
            phase=BattlePhaseKind.SHOOTING,
            player_id="player-a",
        ),
        effect_payload=None,
    )
    wrong_bool = _effect(
        effect_id="phase13d-effect-bad-cover",
        effect_kind_value=GO_TO_GROUND_EFFECT_KIND,
        payload={"benefit_of_cover": "yes"},
    )

    with pytest.raises(GameLifecycleError, match="requires PersistingEffect"):
        effect_kind(cast(PersistingEffect, object()))
    with pytest.raises(GameLifecycleError, match="requires effect_kind"):
        effect_kind(missing_kind)
    with pytest.raises(GameLifecycleError, match="payload must be an object"):
        effect_kind(non_object_payload)
    with pytest.raises(GameLifecycleError, match="requires PersistingEffect"):
        effect_payload_bool(cast(PersistingEffect, object()), "benefit_of_cover")
    with pytest.raises(GameLifecycleError, match="payload must be an object"):
        effect_payload_int(non_object_payload, "hit_roll_modifier", 0)
    with pytest.raises(GameLifecycleError, match="must be a bool"):
        effect_payload_bool(wrong_bool, "benefit_of_cover")
    with pytest.raises(GameLifecycleError, match="must be an int"):
        unit_effect_hit_roll_modifier((smokescreen,))
    with pytest.raises(GameLifecycleError, match="must be a tuple"):
        unit_effects_grant_benefit_of_cover(cast(tuple[PersistingEffect, ...], []))
    with pytest.raises(GameLifecycleError, match="must contain PersistingEffect"):
        unit_effect_invulnerable_save((cast(PersistingEffect, object()),))


def _profile(
    *,
    keywords: tuple[WeaponKeyword, ...],
    abilities: tuple[AbilityDescriptor, ...],
) -> WeaponProfile:
    return WeaponProfile(
        profile_id="phase13d:test-profile",
        name="Phase 13D test profile",
        range_profile=RangeProfile.distance(24),
        attack_profile=AttackProfile.fixed(1),
        skill=CharacteristicValue.from_raw(Characteristic.BALLISTIC_SKILL, 3),
        strength=CharacteristicValue.from_raw(Characteristic.STRENGTH, 4),
        armor_penetration=CharacteristicValue.from_raw(Characteristic.ARMOR_PENETRATION, 0),
        damage_profile=DamageProfile.fixed(1),
        keywords=keywords,
        abilities=abilities,
    )


def _effect(
    *,
    effect_id: str,
    effect_kind_value: str,
    payload: dict[str, JsonValue],
) -> PersistingEffect:
    return PersistingEffect(
        effect_id=effect_id,
        source_rule_id="core-stratagem:test",
        owner_player_id="player-a",
        target_unit_instance_ids=("army-alpha:intercessor-unit-1",),
        started_battle_round=1,
        started_phase=BattlePhaseKind.SHOOTING,
        expiration=EffectExpiration.end_phase(
            battle_round=1,
            phase=BattlePhaseKind.SHOOTING,
            player_id="player-a",
        ),
        effect_payload={"effect_kind": effect_kind_value, **payload},
    )
