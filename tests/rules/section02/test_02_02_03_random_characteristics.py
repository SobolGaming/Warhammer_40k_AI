"""02.02.03 intrinsic random Damage on actual Maulerfiend fists.

This covers the profile semantics; allocation/roll timing remains a separate obligation.
"""

import pytest

from tests.support.section02_fixtures import MAULERFIEND, Section02Definitions
from warhammer40k_core.core.attributes import Characteristic
from warhammer40k_core.core.dice import DiceExpression
from warhammer40k_core.core.modifiers import ModifierOperation, ModifierTerm


@pytest.mark.parametrize(("die", "expected"), [(1, 2), (3, 4), (6, 7)])
def test_02_02_03_intrinsic_damage_constant_is_not_an_ignorable_modifier(
    section02_definitions: Section02Definitions,
    die: int,
    expected: int,
) -> None:
    profile = section02_definitions.weapon(f"{MAULERFIEND}:maulerfiend-fists").damage_profile
    assert profile.dice_expression is not None
    assert profile.dice_expression == DiceExpression(1, 6, 1)
    base = die + profile.dice_expression.modifier
    penalty = ModifierTerm(ModifierOperation.SUBTRACT, 1).bind(
        modifier_id="damage-penalty",
        source_id="core:02.02.03",
        characteristic=Characteristic.DAMAGE,
    )
    affected = profile.with_modifier(penalty)
    assert affected.resolve_value(base) == max(1, expected - 1)
    assert affected.resolve_value(base, ignored_modifier_ids=("damage-penalty",)) == expected
    assert profile.dice_expression == affected.dice_expression
