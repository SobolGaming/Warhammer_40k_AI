"""Constructed absent-S Core contract, not a native datasheet profile claim."""

from dataclasses import replace

from tests.support.section02_fixtures import INFRACTORS, Section02Definitions
from warhammer40k_core.core.attributes import Characteristic as C
from warhammer40k_core.core.attributes import CharacteristicValue

CONTRACT_SOURCE = "rule:02:constructed-contract"


def test_02_04_01_absent_strength_is_one_only_for_interaction(
    section02_definitions: Section02Definitions,
) -> None:
    original = section02_definitions.weapon(f"{INFRACTORS}:bolt-pistol")
    contract = replace(
        original,
        profile_id="core-contract:absent-strength",
        name="Constructed absent-S weapon",
        strength=CharacteristicValue.source_dash(C.STRENGTH),
        source_ids=(CONTRACT_SOURCE,),
    )
    assert contract.strength_for_interaction() == 1
    assert contract.strength.is_dash
    assert contract.strength.final == 0
    assert original.strength_for_interaction() == 4
