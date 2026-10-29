"""02.01 / 02.01.01: identity is a keyword, not a name substring."""

import pytest

from tests.support.section02_fixtures import (
    AVENGERS,
    INFRACTORS,
    MAULERFIEND,
    RANGERS,
    Section02Definitions,
)
from warhammer40k_core.engine.unit_keyword_queries import unit_has_keyword


@pytest.mark.parametrize(
    ("datasheet", "name", "unrelated"),
    [
        (INFRACTORS, "Infractors", "INFR"),
        (AVENGERS, "Dire Avengers", "AVENGERS"),
        (MAULERFIEND, "Maulerfiend", "FIEND"),
        (RANGERS, "Rangers", "RANGE"),
    ],
)
def test_02_01_01_datasheet_identity_is_an_exact_additional_keyword(
    section02_definitions: Section02Definitions,
    datasheet: str,
    name: str,
    unrelated: str,
) -> None:
    unit = section02_definitions.unit(datasheet)
    assert unit.name == name
    assert unit_has_keyword(unit, name)
    assert not unit_has_keyword(unit, unrelated)
    assert all(name.upper() in model.keywords for model in unit.own_models)


def test_definition_reuse_keeps_new_units_models_and_ability_payloads_independent(
    section02_definitions: Section02Definitions,
) -> None:
    first = section02_definitions.unit()
    second = section02_definitions.unit()
    assert first == second
    assert first is not second
    assert all(a is not b for a, b in zip(first.own_models, second.own_models, strict=True))
    assert all(
        a is not b
        for a, b in zip(first.datasheet_abilities, second.datasheet_abilities, strict=True)
    )
    payload = first.datasheet_abilities[0].rule_ir_payload
    assert payload is not None
    assert payload is not second.datasheet_abilities[0].rule_ir_payload
    original = second.to_payload()
    payload["isolation_probe"] = True
    assert second.to_payload() == original
    assert section02_definitions.unit().to_payload() == original
