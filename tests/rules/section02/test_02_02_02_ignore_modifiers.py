"""02.02.02 subset arithmetic; ability permission remains a separate obligation."""

import pytest

from tests.support.section02_fixtures import Section02Definitions
from warhammer40k_core.core.attributes import Characteristic, CharacteristicError
from warhammer40k_core.core.modifiers import ModifierOperation, ModifierTerm
from warhammer40k_core.core.profile_modifier_trace import CharacteristicModifierTrace


@pytest.mark.parametrize("characteristic", [Characteristic.TOUGHNESS, Characteristic.ATTACKS])
@pytest.mark.parametrize(
    ("ignored", "delta"),
    [
        ((), -1),
        (("penalty",), 2),
        (("bonus",), -3),
        (("penalty", "bonus"), 0),
    ],
)
def test_02_02_02_every_subset_preserves_the_real_source_value(
    section02_definitions: Section02Definitions,
    characteristic: Characteristic,
    ignored: tuple[str, ...],
    delta: int,
) -> None:
    base = section02_definitions.characteristic(characteristic)
    modifiers = tuple(
        ModifierTerm(ModifierOperation.ADD, amount).bind(
            modifier_id=name,
            source_id="core:02.02.02",
            characteristic=characteristic,
        )
        for name, amount in (("bonus", 2), ("penalty", -3))
    )
    trace = CharacteristicModifierTrace(characteristic, base.raw, modifiers)
    result = trace.resolve(ignored_modifier_ids=ignored)
    assert result.final == max(1, base.raw + delta)
    assert trace.source_value == base.raw
    assert trace.ignored_modifier_ids == ()
    assert result.applied_modifier_ids == tuple(
        m.modifier_id for m in modifiers if m.modifier_id not in ignored
    )


@pytest.mark.parametrize("ignored", [("foreign",), ("bonus", "bonus")])
def test_02_02_02_subset_cannot_name_unknown_or_duplicate_operations(
    section02_definitions: Section02Definitions,
    ignored: tuple[str, ...],
) -> None:
    base = section02_definitions.characteristic(Characteristic.TOUGHNESS)
    bonus = ModifierTerm(ModifierOperation.ADD, 1).bind(
        modifier_id="bonus", source_id="core:02.02.02", characteristic=Characteristic.TOUGHNESS
    )
    trace = CharacteristicModifierTrace(Characteristic.TOUGHNESS, base.raw, (bonus,))
    with pytest.raises(CharacteristicError, match=r"unknown|duplicated"):
        trace.resolve(ignored_modifier_ids=ignored)
