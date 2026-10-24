"""02.02.01 algebra and bounds, using unaltered real profile starting values.

Core modifier terms are explicit rule inputs, not invented datasheet abilities.
Choice/permission and live-consumer coverage are tracked separately in coverage.json.
"""

from __future__ import annotations

from fractions import Fraction

import pytest

from tests.support.section02_fixtures import AVENGERS, INFRACTORS, Section02Definitions
from warhammer40k_core.core.attributes import Characteristic as C
from warhammer40k_core.core.attributes import CharacteristicValue, CharacteristicValueKind
from warhammer40k_core.core.modifiers import (
    ModifierError,
    ModifierStack,
    ModifierTerm,
    RollModifier,
    RollModifierOperation,
    resolve_characteristic_value,
    resolve_roll_modifiers,
    resolve_stratagem_cost,
    resolve_targeting_range,
)
from warhammer40k_core.core.modifiers import (
    ModifierOperation as O,
)
from warhammer40k_core.rules.rule_characteristic_parser import (
    _directional_characteristic_delta,  # pyright: ignore[reportPrivateUsage]
)


@pytest.mark.parametrize(
    ("base", "change", "expected"),
    [
        (0, -1, 0),
        (0, 0, 0),
        (0, 1, 1),
        (0, 2, 1),
        (1, -2, 0),
        (1, -1, 0),
        (1, 0, 1),
        (1, 1, 2),
        (1, 2, 2),
        (2, -3, 0),
        (2, 0, 2),
        (2, 2, 3),
    ],
)
def test_02_02_01_cp_cost_bounds_use_each_stratagem_base(
    base: int, change: int, expected: int
) -> None:
    modifier = ModifierTerm(O.ADD, change).bind(modifier_id="cost", source_id="core:02.02.01")
    actual, steps = resolve_stratagem_cost(base, (modifier,))
    assert actual == expected
    assert steps[-1].after == base + change


def test_02_02_01_accumulates_in_source_order_and_rounds_only_at_end(
    section02_definitions: Section02Definitions,
) -> None:
    base = section02_definitions.characteristic(C.TOUGHNESS)
    terms = ((O.SUBTRACT, 1), (O.DIVIDE, 2), (O.ADD, 3), (O.MULTIPLY, 2), (O.SET, 4))
    modifiers = tuple(
        ModifierTerm(op, n).bind(
            modifier_id=f"step-{op.value}", source_id="core:02.02.01", characteristic=C.TOUGHNESS
        )
        for op, n in terms
    )
    stack = ModifierStack(C.TOUGHNESS, base.raw, modifiers)
    assert tuple(step.after for step in stack.arithmetic_steps()) == (
        Fraction(4),
        Fraction(8),
        Fraction(11),
        Fraction(11, 2),
        Fraction(9, 2),
    )
    assert stack.resolve().final == 5
    assert resolve_characteristic_value(base, tuple(reversed(modifiers))).final == 5
    assert base.raw == 3


@pytest.mark.parametrize(
    ("operation", "kind"),
    [
        (O.SET, CharacteristicValueKind.REPLACEMENT_ZERO),
        (O.SET_DASH, CharacteristicValueKind.REPLACEMENT_DASH),
        (O.SET_STAR, CharacteristicValueKind.REPLACEMENT_STAR),
    ],
)
def test_02_02_01_terminal_replacement_blocks_later_arithmetic(
    section02_definitions: Section02Definitions,
    operation: O,
    kind: CharacteristicValueKind,
) -> None:
    base = section02_definitions.characteristic(C.MOVEMENT)
    terms = tuple(
        ModifierTerm(op, n).bind(
            modifier_id=name, source_id="core:02.02.01", characteristic=C.MOVEMENT
        )
        for name, op, n in (("bonus", O.ADD, 9), ("replacement", operation, 0))
    )
    actual = resolve_characteristic_value(base, terms)
    assert actual.value_kind is kind
    assert actual.final == 0
    assert actual.applied_modifier_ids == ("replacement",)


def test_02_02_01_absent_real_invulnerable_save_cannot_be_modified(
    section02_definitions: Section02Definitions,
) -> None:
    value = section02_definitions.unit(INFRACTORS).own_models[0].characteristic(C.INVULNERABLE_SAVE)
    assert isinstance(value, CharacteristicValue)
    assert value.is_dash
    modifier = ModifierTerm(O.ADD, 2).bind(
        modifier_id="bonus", source_id="core:02.02.01", characteristic=C.INVULNERABLE_SAVE
    )
    with pytest.raises(ModifierError, match="dash"):
        resolve_characteristic_value(value, (modifier,))


@pytest.mark.parametrize(
    ("characteristic", "boundary", "direction"),
    [
        (C.MOVEMENT, 1, -1),
        (C.TOUGHNESS, 1, -1),
        (C.SAVE, 2, -1),
        (C.INVULNERABLE_SAVE, 2, -1),
        (C.LEADERSHIP, 5, -1),
        (C.LEADERSHIP, 8, 1),
        (C.OBJECTIVE_CONTROL, 0, -1),
        (C.RANGE, 1, -1),
        (C.ATTACKS, 1, -1),
        (C.WEAPON_SKILL, 2, -1),
        (C.WEAPON_SKILL, 6, 1),
        (C.BALLISTIC_SKILL, 2, -1),
        (C.BALLISTIC_SKILL, 6, 1),
        (C.STRENGTH, 1, -1),
        (C.ARMOR_PENETRATION, 0, 1),
        (C.DAMAGE, 1, -1),
    ],
)
@pytest.mark.parametrize("offset", [-1, 0, 1])
def test_02_02_01_characteristic_boundaries(
    section02_definitions: Section02Definitions,
    characteristic: C,
    boundary: int,
    direction: int,
    offset: int,
) -> None:
    base = section02_definitions.characteristic(characteristic)
    proposed = boundary + direction * offset
    delta = proposed - base.raw
    modifier = ModifierTerm(O.ADD, delta).bind(
        modifier_id="boundary", source_id="core:02.02.01", characteristic=characteristic
    )
    actual = resolve_characteristic_value(base, (modifier,))
    assert actual.final == (boundary if offset >= 0 else proposed)
    assert base.final == base.raw


@pytest.mark.parametrize(
    "characteristic",
    [
        C.WEAPON_SKILL,
        C.BALLISTIC_SKILL,
        C.SAVE,
        C.LEADERSHIP,
        C.ARMOR_PENETRATION,
        C.MOVEMENT,
        C.TOUGHNESS,
        C.ATTACKS,
        C.STRENGTH,
    ],
)
@pytest.mark.parametrize("verb", ["improve", "worsen"])
def test_02_02_01_direction_matches_characteristic_meaning(characteristic: C, verb: str) -> None:
    lower_is_better = characteristic in {
        C.WEAPON_SKILL,
        C.BALLISTIC_SKILL,
        C.SAVE,
        C.LEADERSHIP,
        C.ARMOR_PENETRATION,
    }
    expected = -2 if (verb == "improve") == lower_is_better else 2
    assert (
        _directional_characteristic_delta(characteristic=characteristic, verb=verb, value=2)
        == expected
    )


@pytest.mark.parametrize(
    ("raw", "deltas", "limit", "maximum", "expected"),
    [
        (6, (2,), None, None, 8),
        (1, (-3,), None, None, 1),
        (3, (3, -1), 1, None, 4),
        (3, (1, -3), 1, None, 2),
        (3, (3, -3), 1, None, 3),
        (11, (1,), None, 12, 12),
        (11, (2,), None, 12, 12),
        (11, (0,), None, 12, 11),
    ],
)
def test_02_02_01_roll_limits_follow_cumulative_modifiers(
    raw: int,
    deltas: tuple[int, ...],
    limit: int | None,
    maximum: int | None,
    expected: int,
) -> None:
    modifiers = tuple(
        RollModifier(
            modifier_id=f"roll-{i}",
            source_id="core:02.02.01",
            operation=RollModifierOperation.ADD,
            operand=delta,
        )
        for i, delta in enumerate(deltas)
    )
    assert (
        resolve_roll_modifiers(raw, modifiers, maximum=maximum, maximum_modifier=limit).final
        == expected
    )


@pytest.mark.parametrize(
    ("value", "expected"), [(8, 9), (9, 9), (10, 10), (29, 29), (30, 30), (31, 30)]
)
def test_02_02_01_detection_and_lone_operative_range_bounds(value: int, expected: int) -> None:
    assert resolve_targeting_range(value) == expected


def test_02_02_01_faq_66be_bonus_applies_once_per_weapon(
    section02_definitions: Section02Definitions,
) -> None:
    for identifier, base_attacks in [
        (f"{AVENGERS}:avenger-shuriken-catapult", 4),
        (f"{INFRACTORS}:bolt-pistol", 1),
    ]:
        profile = section02_definitions.weapon(identifier).attack_profile
        assert profile.fixed_attacks == base_attacks
        bonus = ModifierTerm(O.ADD, 1).bind(
            modifier_id="ranged-A",
            source_id="faq:66be2ad9-24af-4edf-890a-c0e55004bf76",
            characteristic=C.ATTACKS,
        )
        assert profile.with_modifier(bonus).resolve_value(base_attacks) == base_attacks + 1
        assert profile.fixed_attacks == base_attacks


@pytest.mark.parametrize("symbol", ["-", "*", "N/A"])
@pytest.mark.parametrize("operation", [O.ADD, O.MULTIPLY])
def test_02_02_01_non_numeric_source_tokens_cannot_enter_arithmetic(
    symbol: str, operation: O
) -> None:
    # Literal Core tokens at the numeric modifier boundary; no real model is altered.
    from typing import cast

    from warhammer40k_core.core.attributes import CharacteristicError
    from warhammer40k_core.core.modifiers import ModifierStack

    modifier = ModifierTerm(operation, 2).bind(
        modifier_id="symbol-arithmetic", source_id="rule:02:02.02.01:1", characteristic=C.STRENGTH
    )
    with pytest.raises(CharacteristicError, match="integer"):
        ModifierStack(C.STRENGTH, cast(int, symbol), (modifier,)).resolve()
