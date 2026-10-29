"""Actual native attack Hit/Wound resolution with fixed physical dice."""

from dataclasses import replace
from typing import cast

import pytest

from tests.support.section02_fixtures import Section02Definitions
from tests.support.section05_sequence import (
    fixed_sequence_dice,
    native_sequence,
    payloads,
    resolve,
)
from tests.support.section24_fixtures import profile_grant
from warhammer40k_core.core.weapon_profiles import AbilityDescriptor, WeaponKeyword
from warhammer40k_core.engine.damage_allocation import model_by_id
from warhammer40k_core.engine.event_log import JsonValue


@pytest.mark.parametrize("match", [False, True])
def test_anti_changes_actual_unmodified_wound_critical_threshold(
    section24_definitions: Section02Definitions, match: bool
) -> None:
    state, target, sequence = native_sequence(section24_definitions)
    (pool,) = sequence.attack_pools
    p = replace(
        pool.weapon_profile,
        abilities=(AbilityDescriptor.anti_keyword("INFANTRY" if match else "VEHICLE", 4),),
    )
    sequence = replace(sequence, attack_pools=(replace(pool, weapon_profile=p),))
    decisions, remaining, status = resolve(
        state, sequence, fixed_sequence_dice(sequence, target, (6,), (4,), (6,))
    )
    assert remaining is None
    assert status is None
    (wound,) = [p for p in payloads(decisions, "attack_sequence_step") if p["step"] == "wound"]
    result = cast(dict[str, JsonValue], wound["payload"])
    assert result["successful"] is True
    assert result["critical"] is match


@pytest.mark.parametrize("torrent", [False, True])
def test_torrent_automatically_hits_without_hit_roll_or_critical(
    section24_definitions: Section02Definitions, torrent: bool
) -> None:
    state, target, sequence = native_sequence(section24_definitions)
    (pool,) = sequence.attack_pools
    if torrent:
        sequence = replace(
            sequence,
            attack_pools=(
                replace(
                    pool, weapon_profile=profile_grant(pool.weapon_profile, WeaponKeyword.TORRENT)
                ),
            ),
        )
    dice = fixed_sequence_dice(sequence, target, (6,), (1,), ())
    decisions, remaining, status = resolve(state, sequence, dice[1:] if torrent else dice)
    assert remaining is None
    assert status is None
    (hit,) = [p for p in payloads(decisions, "attack_sequence_step") if p["step"] == "hit"]
    result = cast(dict[str, JsonValue], hit["payload"])
    assert result["successful"] is True
    assert result["critical"] is (not torrent)
    assert (result["roll_state"] is None) is torrent
    rolls = [
        p for p in payloads(decisions, "dice_rolled") if p.get("roll_type") == "attack_sequence.hit"
    ]
    if torrent:
        assert rolls == []


@pytest.mark.parametrize("matching_target", [False, True])
def test_conditional_lethal_hit_waits_for_player_before_any_wound_roll(
    section24_definitions: Section02Definitions, matching_target: bool
) -> None:
    state, target, sequence = native_sequence(section24_definitions)
    (pool,) = sequence.attack_pools
    p = profile_grant(
        pool.weapon_profile,
        WeaponKeyword.LETHAL_HITS,
        AbilityDescriptor.lethal_hits(
            target_keywords=("INFANTRY" if matching_target else "VEHICLE",)
        ),
    )
    sequence = replace(sequence, attack_pools=(replace(pool, weapon_profile=p),))
    decisions, remaining, status = resolve(
        state, sequence, fixed_sequence_dice(sequence, target, (6,), (1,), ())
    )
    if matching_target:
        assert remaining is not None
        assert status is not None
        assert status.decision_request is not None
        assert {o.option_id for o in status.decision_request.options} == {
            "auto-wound",
            "roll-to-wound",
        }
        assert not any(p["step"] == "wound" for p in payloads(decisions, "attack_sequence_step"))
    else:
        assert remaining is None
        assert status is None
        assert (
            len([p for p in payloads(decisions, "attack_sequence_step") if p["step"] == "wound"])
            == 1
        )


@pytest.mark.parametrize("damage", [1, 3])
def test_devastating_wound_ends_attack_omits_save_and_caps_one_model(
    section24_definitions: Section02Definitions, damage: int
) -> None:
    from warhammer40k_core.core.weapon_profiles import DamageProfile

    target = section24_definitions.unit("000004080", army_id="enemy", identity="target")
    # A uniquely wounded first model fixes mandatory allocation without adding
    # an unrelated player-choice traversal to this one-critical-wound kernel.
    target = replace(
        target,
        own_models=(replace(target.own_models[0], wounds_remaining=1), *target.own_models[1:]),
    )
    state, target, sequence = native_sequence(section24_definitions, target=target)
    (pool,) = sequence.attack_pools
    p = profile_grant(
        pool.weapon_profile,
        WeaponKeyword.DEVASTATING_WOUNDS,
        AbilityDescriptor.devastating_wounds(),
    )
    # Explicit Core D input on the same real equipped physical weapon.
    p = replace(p, damage_profile=DamageProfile.fixed(damage))
    sequence = replace(sequence, attack_pools=(replace(pool, weapon_profile=p),))
    decisions, remaining, status = resolve(
        state, sequence, fixed_sequence_dice(sequence, target, (6,), (6,), (1,))[:2]
    )
    assert remaining is None
    assert status is None
    assert not any(p["step"] == "save" for p in payloads(decisions, "attack_sequence_step"))
    (applied,) = payloads(decisions, "devastating_wounds_mortal_wounds_applied")
    assert applied["mortal_wounds"] == damage
    models = [
        model_by_id(state=state, model_instance_id=m.model_instance_id) for m in target.own_models
    ]
    assert models[0].current_wounds == max(0, target.own_models[0].current_wounds - damage)
    assert [m.current_wounds for m in models[1:]] == [
        m.current_wounds for m in target.own_models[1:]
    ]


@pytest.mark.parametrize("twin_linked", [False, True])
@pytest.mark.parametrize("wound", [1, 6])
def test_twin_linked_offers_optional_reroll_of_success_or_failure(
    section24_definitions: Section02Definitions, twin_linked: bool, wound: int
) -> None:
    state, target, sequence = native_sequence(section24_definitions)
    (pool,) = sequence.attack_pools
    if twin_linked:
        sequence = replace(
            sequence,
            attack_pools=(
                replace(
                    pool,
                    weapon_profile=profile_grant(pool.weapon_profile, WeaponKeyword.TWIN_LINKED),
                ),
            ),
        )
    decisions, remaining, status = resolve(
        state,
        sequence,
        fixed_sequence_dice(sequence, target, (6,), (wound,), (6,) if wound == 6 else ()),
    )
    if twin_linked:
        assert remaining is not None
        assert status is not None
        assert status.decision_request is not None
        assert status.decision_request.decision_type == "select_dice_reroll"
        assert {o.option_id for o in status.decision_request.options} == {"decline", "reroll:0"}
        assert not any(
            p["step"] in {"save", "damage"} for p in payloads(decisions, "attack_sequence_step")
        )
    else:
        assert remaining is None
        assert status is None
