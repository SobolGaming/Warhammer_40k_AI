"""Source-correct identical-attack assertions, including distinct native bearers."""

from dataclasses import replace

import pytest

from tests.support.section02_consumers import attack_pool
from tests.support.section02_fixtures import AVENGERS, INFRACTORS, Section02Definitions
from tests.support.section04_fixtures import combat_state
from warhammer40k_core.core.attributes import Characteristic, CharacteristicValue
from warhammer40k_core.core.modifiers import RollModifier
from warhammer40k_core.core.weapon_profiles import AttackProfile, DamageProfile, WeaponKeyword
from warhammer40k_core.engine.attack_sequence import (
    AttackSequence,
    gathered_attack_groups_for_target,
)
from warhammer40k_core.engine.native_attack_gathering import (
    native_gathered_attack_groups_for_target,
)
from warhammer40k_core.engine.phase import BattlePhase
from warhammer40k_core.engine.runtime_modifiers import RuntimeModifierRegistry
from warhammer40k_core.engine.weapon_instances import equipped_weapon_profile_instances_for_model


@pytest.mark.parametrize("models", [1, 2, 3])
def test_identical_native_weapons_gather_all_physical_dice(
    section04_definitions: Section02Definitions, models: int
) -> None:
    d = section04_definitions
    attacker = d.unit(AVENGERS)
    target = d.unit(INFRACTORS, army_id="enemy")
    weapon = d.weapon(f"{AVENGERS}:avenger-shuriken-catapult")
    first = attack_pool(attacker, target, weapon, f"{AVENGERS}:avenger-shuriken-catapult")
    instances = tuple(
        equipped_weapon_profile_instances_for_model(model=m, army_catalog=d.package.army_catalog)[0]
        for m in attacker.own_models[:models]
    )
    pools = tuple(
        replace(
            first,
            attacker_model_instance_id=w.model_instance_id,
            weapon_instance_id=w.weapon_instance_id,
        )
        for w in instances
    )
    sequence = AttackSequence("native-group", "owner", attacker.unit_instance_id, pools)
    groups = native_gathered_attack_groups_for_target(
        state=combat_state(d, attacker, target=target),
        registry=RuntimeModifierRegistry(),
        attack_sequence=sequence,
        target_unit_instance_id=target.unit_instance_id,
        target_has_character=False,
        has_custom_callbacks=False,
    )
    assert len(groups) == 1
    assert weapon.attack_profile.fixed_attacks is not None
    assert groups[0].total_attacks == models * weapon.attack_profile.fixed_attacks
    assert groups[0].pool_indices == tuple(range(models))
    assert tuple(c.weapon_instance_id for c in groups[0].contributions) == tuple(
        p.weapon_instance_id for p in pools
    )


@pytest.mark.parametrize(
    "field", ["skill", "strength", "armor_penetration", "damage", "ability", "rule", "hit_modifier"]
)
@pytest.mark.parametrize("phase", [BattlePhase.SHOOTING, BattlePhase.FIGHT])
def test_contract_different_applicable_characteristics_and_rules_split_groups(
    section04_definitions: Section02Definitions, field: str, phase: BattlePhase
) -> None:
    d = section04_definitions
    attacker = d.unit(INFRACTORS if phase is BattlePhase.FIGHT else AVENGERS)
    target = d.unit(INFRACTORS, army_id="enemy")
    wargear_id = (
        f"{INFRACTORS}:duelling-sabre"
        if phase is BattlePhase.FIGHT
        else f"{AVENGERS}:avenger-shuriken-catapult"
    )
    native = d.weapon(wargear_id)
    first = attack_pool(attacker, target, native, wargear_id)
    second = replace(first, weapon_instance_id="constructed:second-copy")
    if field in {"skill", "strength", "armor_penetration"}:
        characteristic = {
            "skill": Characteristic.WEAPON_SKILL
            if phase is BattlePhase.FIGHT
            else Characteristic.BALLISTIC_SKILL,
            "strength": Characteristic.STRENGTH,
            "armor_penetration": Characteristic.ARMOR_PENETRATION,
        }[field]
        value = {"skill": 4, "strength": 8, "armor_penetration": -3}[field]
        changed = CharacteristicValue.from_raw(characteristic, value)
        profile = (
            replace(native, skill=changed)
            if field == "skill"
            else replace(native, strength=changed)
            if field == "strength"
            else replace(native, armor_penetration=changed)
        )
        second = replace(second, weapon_profile=profile)
    elif field == "damage":
        second = replace(
            second, weapon_profile=replace(native, damage_profile=DamageProfile.fixed(2))
        )
    elif field == "ability":
        second = replace(
            second,
            weapon_profile=replace(
                native, keywords=(*native.keywords, WeaponKeyword.IGNORES_COVER)
            ),
        )
    elif field == "rule":
        second = replace(second, targeting_rule_ids=("constructed:applicable-rule",))
    else:
        second = replace(
            second,
            hit_roll_modifier=1,
            hit_roll_modifiers=(
                RollModifier("constructed:hit", 1, source_id="constructed:section04"),
            ),
        )
    sequence = AttackSequence(
        "contract-group", "owner", attacker.unit_instance_id, (first, second), source_phase=phase
    )
    groups = gathered_attack_groups_for_target(
        attack_sequence=sequence,
        target_unit_instance_id=target.unit_instance_id,
        target_has_character=False,
    )
    assert len(groups) == 2
    assert {g.pool_indices for g in groups} == {(0,), (1,)}


@pytest.mark.parametrize("character", [False, True])
@pytest.mark.parametrize("precision_first", [False, True])
def test_faq21_precision_is_applicable_only_against_character(
    section04_definitions: Section02Definitions, character: bool, precision_first: bool
) -> None:
    d = section04_definitions
    attacker = d.unit(INFRACTORS)
    target = d.unit(INFRACTORS, army_id="enemy")
    native = d.weapon(f"{INFRACTORS}:duelling-sabre")
    precision = attack_pool(attacker, target, native, f"{INFRACTORS}:duelling-sabre")
    # Explicit comparison contract: second physical copy removes only PRECISION.
    plain = replace(
        precision,
        weapon_instance_id="constructed:plain-copy",
        weapon_profile=replace(
            native, keywords=tuple(k for k in native.keywords if k is not WeaponKeyword.PRECISION)
        ),
    )
    pools = (precision, plain) if precision_first else (plain, precision)
    sequence = AttackSequence("precision", "owner", attacker.unit_instance_id, pools)
    groups = gathered_attack_groups_for_target(
        attack_sequence=sequence,
        target_unit_instance_id=target.unit_instance_id,
        target_has_character=character,
    )
    assert len(groups) == (2 if character else 1)
    assert sum(g.total_attacks for g in groups) == 8
    assert sequence.attack_pools == pools


def test_gather_ignores_resolved_weapons_and_other_targets(
    section04_definitions: Section02Definitions,
) -> None:
    d = section04_definitions
    attacker = d.unit(AVENGERS)
    target = d.unit(INFRACTORS, army_id="enemy")
    native = d.weapon(f"{AVENGERS}:avenger-shuriken-catapult")
    first = attack_pool(attacker, target, native, f"{AVENGERS}:avenger-shuriken-catapult")
    pools = (
        first,
        replace(first, weapon_instance_id="constructed:copy-2"),
        replace(
            first, weapon_instance_id="constructed:copy-3", target_unit_instance_id="enemy:other"
        ),
    )
    sequence = AttackSequence(
        "unresolved", "owner", attacker.unit_instance_id, pools, used_pool_indices=(0,)
    )
    groups = gathered_attack_groups_for_target(
        attack_sequence=sequence,
        target_unit_instance_id=target.unit_instance_id,
        target_has_character=False,
    )
    assert len(groups) == 1
    assert groups[0].pool_indices == (1,)
    assert groups[0].total_attacks == native.attack_profile.fixed_attacks


def test_attack_count_is_contribution_not_identical_attack_characteristic(
    section04_definitions: Section02Definitions,
) -> None:
    d = section04_definitions
    attacker = d.unit(AVENGERS)
    target = d.unit(INFRACTORS, army_id="enemy")
    weapon = d.weapon(f"{AVENGERS}:avenger-shuriken-catapult")
    first = attack_pool(attacker, target, weapon, f"{AVENGERS}:avenger-shuriken-catapult")
    second = replace(
        first,
        weapon_instance_id="constructed:A7",
        attacks=7,
        weapon_profile=replace(weapon, attack_profile=AttackProfile.fixed(7)),
    )
    sequence = AttackSequence("counts", "owner", attacker.unit_instance_id, (first, second))
    groups = gathered_attack_groups_for_target(
        attack_sequence=sequence,
        target_unit_instance_id=target.unit_instance_id,
        target_has_character=False,
    )
    assert len(groups) == 1
    assert groups[0].total_attacks == first.attacks + 7
