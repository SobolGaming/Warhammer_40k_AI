"""Numeric Core families keep identity and require explicit duplicated selection."""

from dataclasses import replace

import pytest

from tests.support.section02_fixtures import Section02Definitions
from tests.support.section24_fixtures import BODY, core_ability, with_core
from warhammer40k_core.core.core_ability_family import CoreAbilityFamily
from warhammer40k_core.engine.core_ability_state import (
    CoreAbilitySelection,
    active_core_descriptors,
    core_instance_groups,
)
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.unit_abilities import (
    deadly_demise_profiles_for_unit,
    feel_no_pain_profiles_for_unit,
    firing_deck_value_for_unit,
    unit_has_deadly_demise,
)


@pytest.mark.parametrize("token", ["1", "D3", "D6"])
def test_with_deadly_demise_family_ignores_parameter_but_execution_retains_it(
    section24_definitions: Section02Definitions, token: str
) -> None:
    unit = with_core(section24_definitions.unit(BODY), "deadly-demise", token)
    assert unit_has_deadly_demise(unit)
    (profile,) = deadly_demise_profiles_for_unit(unit)
    assert profile.mortal_wounds_token == token
    assert profile.source_id == unit.datasheet_abilities[0].source_id


@pytest.mark.parametrize(
    ("family", "tokens"),
    [
        (CoreAbilityFamily.FEEL_NO_PAIN, ("5+", "6+")),
        (CoreAbilityFamily.FIRING_DECK, ("1", "2")),
    ],
)
@pytest.mark.parametrize("index", [0, 1])
def test_duplicate_core_numeric_instances_require_controller_choice(
    section24_definitions: Section02Definitions,
    family: CoreAbilityFamily,
    tokens: tuple[str, str],
    index: int,
) -> None:
    name = "feel-no-pain" if family is CoreAbilityFamily.FEEL_NO_PAIN else "firing-deck"
    first, second = (core_ability(name, token) for token in tokens)
    second = replace(second, ability_id=first.ability_id + "-second")
    # Both descriptors explicitly belong to this canonical family, independent
    # of their display text and numeric token.
    unit = replace(section24_definitions.unit(BODY), datasheet_abilities=(first, second))
    with pytest.raises(GameLifecycleError, match="selection"):
        active_core_descriptors(unit, family)
    groups = dict(core_instance_groups(unit))
    assert len(groups[family]) == 2
    selected_source = next(
        s for s in groups[family] if s.source_id == (first, second)[index].source_id
    )
    unit = replace(
        unit,
        core_ability_selections=(
            CoreAbilitySelection(
                family,
                selected_source.instance_id,
                "s24:chosen",
                "s24:opportunity",
            ),
        ),
    )
    (active,) = active_core_descriptors(unit, family)
    assert active.parameter_tokens == (tokens[index],)
    if family is CoreAbilityFamily.FEEL_NO_PAIN:
        # Damage-time FNP chooses among retained sources at each lost wound;
        # the inventory owner must preserve both original occurrences.
        profiles = feel_no_pain_profiles_for_unit(unit)
        assert {p.threshold for p in profiles} == {5, 6}
        assert next(p for p in profiles if p.source_id == active.source_id).threshold == int(
            tokens[index][0]
        )
    else:
        assert firing_deck_value_for_unit(unit) == int(tokens[index])
