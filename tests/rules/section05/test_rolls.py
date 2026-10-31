"""Native attack profiles at production roll evaluators; no game startup."""

from dataclasses import replace

import pytest

from tests.support.section02_consumers import attack_pool
from tests.support.section02_fixtures import AVENGERS, LORD_EXULTANT, Section02Definitions
from tests.support.section04_fixtures import combat_state
from warhammer40k_core.core.modifiers import RollModifier
from warhammer40k_core.engine.attack_sequence import (
    attack_sequence_hit_roll_spec,
    attack_sequence_wound_roll_spec,
)
from warhammer40k_core.engine.attack_sequence_hit_wound import _roll_hit, _roll_wound
from warhammer40k_core.engine.dice import DiceRollManager
from warhammer40k_core.engine.interpreted_dice import CriticalRollThreshold
from warhammer40k_core.engine.phase import BattlePhase


@pytest.mark.parametrize("melee", [False, True])
@pytest.mark.parametrize("raw", range(1, 7))
@pytest.mark.parametrize("modifier", [-1, 0, 1])
def test_native_hit_faces_and_skill(
    section05_definitions: Section02Definitions, melee: bool, raw: int, modifier: int
) -> None:
    d = section05_definitions
    unit = d.unit(LORD_EXULTANT)
    target = d.unit(LORD_EXULTANT, army_id="enemy", identity="target")
    # Both profiles are authentic equipped Lord Exultant weapons.
    wargear = f"{LORD_EXULTANT}:" + ("close-combat-weapon" if melee else "bolt-pistol")
    weapon = d.weapon(wargear)
    pool = replace(
        attack_pool(unit, target, weapon, wargear),
        hit_roll_modifier=modifier,
        hit_roll_modifiers=(
            RollModifier("constructed:s05:hit", modifier, source_id="constructed:s05:modifier"),
        )
        if modifier
        else (),
    )
    spec = attack_sequence_hit_roll_spec(
        weapon_profile_id=weapon.profile_id,
        attack_context_id="s05:hit",
        attacker_player_id="owner",
    )
    assert (spec.expression.quantity, spec.expression.sides) == (1, 6)
    result = DiceRollManager("physical").roll_fixed(spec, (raw,)).original_result
    hit = _roll_hit(
        state=combat_state(d, unit, target=target),
        manager=DiceRollManager("hit", injected_results=(result,)),
        pool=pool,
        attacker_player_id="owner",
        attack_context_id="s05:hit",
        source_phase=BattlePhase.FIGHT if melee else BattlePhase.SHOOTING,
    )
    assert weapon.skill is not None
    assert hit.successful is (raw == 6 or (raw != 1 and raw + modifier >= weapon.skill.final))
    assert hit.critical is (raw == 6)
    assert hit.unmodified_roll == raw


@pytest.mark.parametrize(
    ("toughness", "expected"),
    [(1, 2), (2, 2), (3, 3), (4, 4), (5, 5), (7, 5), (8, 6), (9, 6)],
)
@pytest.mark.parametrize("raw", range(1, 7))
@pytest.mark.parametrize("modifier", [-1, 0, 1])
def test_strength_four_wound_table_contract(
    section05_definitions: Section02Definitions,
    toughness: int,
    expected: int,
    raw: int,
    modifier: int,
) -> None:
    d = section05_definitions
    unit = d.unit(AVENGERS)
    target = d.unit(LORD_EXULTANT, army_id="enemy", identity="target")
    # Keep this S4 boundary contract on an unchanged native profile, owned by its unit.
    wargear = f"{AVENGERS}:avenger-shuriken-catapult"
    weapon = d.weapon(wargear)
    assert weapon.strength_for_interaction() == 4
    pool = attack_pool(unit, target, weapon, wargear)
    # Constructed target Toughness boundary values, not claims about this datasheet.
    spec = attack_sequence_wound_roll_spec(
        weapon_profile_id=weapon.profile_id,
        attack_context_id="s05:wound",
        attacker_player_id="owner",
    )
    assert (spec.expression.quantity, spec.expression.sides) == (1, 6)
    result = DiceRollManager("physical").roll_fixed(spec, (raw,)).original_result
    wound = _roll_wound(
        manager=DiceRollManager("wound", injected_results=(result,)),
        pool=pool,
        toughness=toughness,
        attacker_player_id="owner",
        attack_context_id="s05:wound",
        critical_threshold=CriticalRollThreshold(6, True),
        wound_modifier=modifier,
    )
    assert wound.target_number == expected
    assert wound.successful is (raw == 6 or (raw != 1 and raw + modifier >= expected))
    assert wound.critical is (raw == 6)
