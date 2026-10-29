"""Explicit Core critical-keyword contracts on a native weapon and real resolver."""

from dataclasses import replace

from tests.support.section02_fixtures import Section02Definitions
from tests.support.section05_sequence import (
    fixed_sequence_dice,
    native_sequence,
    payloads,
    resolve,
)
from warhammer40k_core.core.weapon_profiles import AbilityDescriptor, WeaponKeyword
from warhammer40k_core.engine.attack_sequence import attack_sequence_hit_roll_spec
from warhammer40k_core.engine.dice import DiceRollManager


def test_critical_lethal_hit_opens_wound_choice(
    section05_definitions: Section02Definitions,
) -> None:
    state, _target, sequence = native_sequence(section05_definitions)
    pool = sequence.attack_pools[0]
    profile = replace(
        pool.weapon_profile,
        keywords=(*pool.weapon_profile.keywords, WeaponKeyword.LETHAL_HITS),
        abilities=(*pool.weapon_profile.abilities, AbilityDescriptor.lethal_hits()),
    )
    sequence = replace(sequence, attack_pools=(replace(pool, weapon_profile=profile),))
    spec = attack_sequence_hit_roll_spec(
        weapon_profile_id=profile.profile_id,
        attack_context_id="s05:pool-001:attack-001",
        attacker_player_id="owner",
    )
    decisions, remaining, status = resolve(
        state,
        sequence,
        (DiceRollManager("physical").roll_fixed(spec, (6,)).original_result,),
    )
    assert remaining is not None
    assert status is not None
    assert status.decision_request is not None
    assert {o.option_id for o in status.decision_request.options} == {
        "auto-wound",
        "roll-to-wound",
    }
    assert not any(p["step"] == "wound" for p in payloads(decisions, "attack_sequence_step"))


def test_critical_devastating_wound_applies_mortals(
    section05_definitions: Section02Definitions,
) -> None:
    state, target, sequence = native_sequence(section05_definitions)
    pool = sequence.attack_pools[0]
    profile = replace(
        pool.weapon_profile,
        keywords=(*pool.weapon_profile.keywords, WeaponKeyword.DEVASTATING_WOUNDS),
        abilities=(
            *pool.weapon_profile.abilities,
            AbilityDescriptor.devastating_wounds(),
        ),
    )
    sequence = replace(sequence, attack_pools=(replace(pool, weapon_profile=profile),))
    # Only hit and wound are consumed before the actual optional critical consumer choice.
    results = fixed_sequence_dice(sequence, target, (6,), (6,), (1,))[:2]
    decisions, remaining, status = resolve(state, sequence, results)
    assert remaining is None
    assert status is None
    assert not any(p["step"] == "save" for p in payloads(decisions, "attack_sequence_step"))
    damage = [p for p in payloads(decisions, "attack_sequence_step") if p["step"] == "damage"]
    assert len(damage) == 1
    applied = payloads(decisions, "devastating_wounds_mortal_wounds_applied")
    assert len(applied) == 1
    assert applied[0]["mortal_wounds"] == 1
    from warhammer40k_core.engine.damage_allocation import model_by_id

    assert (
        model_by_id(state=state, model_instance_id=target.own_model_ids()[0]).current_wounds
        == target.own_models[0].current_wounds - 1
    )
