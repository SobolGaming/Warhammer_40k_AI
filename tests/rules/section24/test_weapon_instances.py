"""Real equipped profile inputs, target gates and controlling-player occurrences."""

from dataclasses import replace

import pytest

from tests.support.section02_fixtures import Section02Definitions
from tests.support.section24_fixtures import bolt, profile_grant
from warhammer40k_core.core.weapon_ability_sources import (
    grant_weapon_ability,
    weapon_ability_sources,
)
from warhammer40k_core.core.weapon_profiles import (
    AbilityDescriptor,
    AntiKeywordMatchMode,
    WeaponKeyword,
    WeaponProfile,
    WeaponProfileError,
)
from warhammer40k_core.engine.ability_instance_selection import (
    selected_weapon_profile,
    weapon_instance_selection_requests,
)
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.weapon_abilities import (
    anti_keyword_critical_threshold,
    blast_attack_bonus_for_profile,
    cleave_attack_bonus,
    lethal_hits_applies,
    melta_damage_bonus,
    rapid_fire_attack_bonus,
    sustained_hits_generated_hits,
)


@pytest.mark.parametrize(
    "keywords", [("VEHICLE",), ("INFANTRY",), ("BEASTS",), ("INFANTRY BEASTS",)]
)
def test_keyword_suffixes_use_exact_any_keyword_membership_on_real_profile(
    section24_definitions: Section02Definitions, keywords: tuple[str, ...]
) -> None:
    p = profile_grant(
        bolt(section24_definitions),
        WeaponKeyword.LETHAL_HITS,
        AbilityDescriptor.lethal_hits(target_keywords=("VEHICLE",)),
    )
    p = profile_grant(
        p,
        WeaponKeyword.SUSTAINED_HITS,
        AbilityDescriptor.sustained_hits(1, target_keywords=("INFANTRY", "BEASTS")),
    )
    assert lethal_hits_applies(p, target_keywords=keywords) is (keywords == ("VEHICLE",))
    assert sustained_hits_generated_hits(p, critical_hit=True, target_keywords=keywords) == (
        2 if keywords in (("INFANTRY",), ("BEASTS",)) else 1
    )
    assert WeaponProfile.from_payload(p.to_payload()) == p


@pytest.mark.parametrize(
    "target", [("VEHICLE",), ("MONSTER",), ("INFANTRY",), ("PSYKER",), ("PSYKER LORD",)]
)
@pytest.mark.parametrize("negated", [False, True])
def test_anti_threshold_including_non_monster_vehicle_and_exact_psyker(
    section24_definitions: Section02Definitions, target: tuple[str, ...], negated: bool
) -> None:
    descriptor = AbilityDescriptor.anti_keyword(
        "MONSTER/VEHICLE" if negated else "PSYKER",
        4 if negated else 2,
        match_mode=AntiKeywordMatchMode.MISSING_KEYWORD
        if negated
        else AntiKeywordMatchMode.HAS_KEYWORD,
    )
    p = replace(bolt(section24_definitions), abilities=(descriptor,), ability_sources=())
    applies = not bool(set(target) & {"MONSTER", "VEHICLE"}) if negated else target == ("PSYKER",)
    assert anti_keyword_critical_threshold(profile=p, target_keywords=target) == (
        (4 if negated else 2) if applies else None
    )


@pytest.mark.parametrize("chosen", [1, 2])
def test_duplicate_values_require_one_source_and_never_stack(
    section24_definitions: Section02Definitions, chosen: int
) -> None:
    p = profile_grant(
        bolt(section24_definitions),
        WeaponKeyword.SUSTAINED_HITS,
        AbilityDescriptor.sustained_hits(1),
    )
    p = grant_weapon_ability(
        p,
        keyword=WeaponKeyword.SUSTAINED_HITS,
        ability=AbilityDescriptor.sustained_hits(2),
        source_id="constructed:s24:second",
        source_instance_id="constructed:s24:second:grant",
    )
    (request,) = weapon_instance_selection_requests(
        p, actor_id="owner", request_id="select-weapons"
    )
    assert len(request.options) == 2
    with pytest.raises(GameLifecycleError, match="exactly one"):
        selected_weapon_profile(p, ())
    source = next(
        s
        for s in weapon_ability_sources(p)
        if s.ability_id == AbilityDescriptor.sustained_hits(chosen).ability_id
    )
    selected = selected_weapon_profile(p, (source.instance_id,))
    assert sustained_hits_generated_hits(selected, critical_hit=True) == chosen + 1
    assert (
        len([a for a in selected.abilities if a == AbilityDescriptor.sustained_hits(chosen)]) == 1
    )
    with pytest.raises(GameLifecycleError, match="unavailable"):
        selected_weapon_profile(p, ("invented",))


@pytest.mark.parametrize("count", [0, 4, 5, 9, 10, 12, 16])
@pytest.mark.parametrize("value", [None, 2])
def test_blast_bare_and_parameterized_count_complete_groups_of_five(
    section24_definitions: Section02Definitions, count: int, value: int | None
) -> None:
    p = profile_grant(
        bolt(section24_definitions),
        WeaponKeyword.BLAST,
        None if value is None else AbilityDescriptor.blast(value),
    )
    assert blast_attack_bonus_for_profile(p, target_model_count=count) == (count // 5) * (
        value or 1
    )


@pytest.mark.parametrize("single", [False, True])
@pytest.mark.parametrize("count", [4, 5, 12, 16])
def test_cleave_requires_one_target_for_the_whole_physical_weapon(
    section24_definitions: Section02Definitions, single: bool, count: int
) -> None:
    p = profile_grant(
        bolt(section24_definitions), WeaponKeyword.CLEAVE, AbilityDescriptor.cleave(1)
    )
    assert cleave_attack_bonus(p, single_target=single, target_model_count=count) == (
        count // 5 if single else 0
    )


@pytest.mark.parametrize("within", [False, True])
def test_half_range_bonuses_are_separate_attack_and_damage_operations(
    section24_definitions: Section02Definitions, within: bool
) -> None:
    p = profile_grant(
        bolt(section24_definitions), WeaponKeyword.RAPID_FIRE, AbilityDescriptor.rapid_fire(1)
    )
    p = profile_grant(p, WeaponKeyword.MELTA, AbilityDescriptor.melta(2))
    assert rapid_fire_attack_bonus(p, target_within_half_range=within) == int(within)
    assert melta_damage_bonus(p, target_within_half_range=within) == 2 * int(within)
    assert p.attack_profile.fixed_attacks == 1
    assert p.damage_profile.fixed_damage == 1


@pytest.mark.parametrize("incompatible", [WeaponKeyword.INDIRECT_FIRE, WeaponKeyword.PRECISION])
def test_torrent_refuses_incompatible_core_keywords_at_profile_boundary(
    section24_definitions: Section02Definitions, incompatible: WeaponKeyword
) -> None:
    with pytest.raises(WeaponProfileError, match="Torrent"):
        replace(
            bolt(section24_definitions),
            keywords=(WeaponKeyword.TORRENT, incompatible),
            ability_sources=(),
        )
