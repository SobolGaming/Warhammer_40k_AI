"""Native source materialization and model-complete numeric selection boundaries."""

import pytest

from tests.support.section02_fixtures import Section02Definitions
from tests.support.section03_fixtures import native_state
from tests.support.section24_fixtures import BODY, HAWKS, SERPENT, SPAWN
from warhammer40k_core.engine.core_ability_materialization import (
    record_core_deadly_demise_sources_for_unit,
    record_core_feel_no_pain_sources_for_unit,
)
from warhammer40k_core.engine.deployment_ability_queries import rules_unit_has_infiltrators
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.prebattle_instance_selection import (
    scout_distance_inches_for_model_ids,
    scout_distance_options_for_model_ids,
)
from warhammer40k_core.engine.rules_units import rules_unit_view_by_id
from warhammer40k_core.engine.scout_abilities import (
    ScoutAbilityInstance,
    scout_ability_instances_for_rules_unit,
)
from warhammer40k_core.engine.unit_abilities import unit_has_deep_strike


def test_native_deadly_demise_materializes_one_d6_trigger_six_inch_random_source(
    section24_definitions: Section02Definitions,
) -> None:
    unit = section24_definitions.unit(SERPENT)
    state = native_state(section24_definitions, unit)
    rows = record_core_deadly_demise_sources_for_unit(state=state, unit=unit)
    assert len(rows) == len(unit.own_models) == 1
    mid, source = rows[0]
    assert mid == unit.own_model_ids()[0]
    assert source.payload == {
        "trigger_roll_threshold": 6,
        "range_inches": 6.0,
        "mortal_wounds": {"kind": "d3"},
    }
    assert not source.optional
    assert record_core_deadly_demise_sources_for_unit(state=state, unit=unit) == rows
    assert state.destruction_reaction_sources_for_model(model_instance_id=mid) == (source,)


def test_native_feel_no_pain_materializes_each_physical_bearer_once(
    section24_definitions: Section02Definitions,
) -> None:
    unit = section24_definitions.unit(SPAWN)
    state = native_state(section24_definitions, unit)
    rows = record_core_feel_no_pain_sources_for_unit(state=state, unit=unit)
    assert {mid for mid, _ in rows} == set(unit.own_model_ids())
    assert len(rows) == len(unit.own_models)
    assert all(source.threshold == 5 for _, source in rows)
    assert record_core_feel_no_pain_sources_for_unit(state=state, unit=unit) == rows
    assert all(
        state.feel_no_pain_sources_for_model(model_instance_id=mid) == (source,)
        for mid, source in rows
    )


@pytest.mark.parametrize("common", [False, True])
def test_scouts_native_model_inventory_keeps_common_choices_or_lowest_unshared_value(
    section24_definitions: Section02Definitions, common: bool
) -> None:
    d = section24_definitions
    unit = d.unit(BODY)
    state = native_state(d, unit)
    view = rules_unit_view_by_id(state=state, unit_instance_id=unit.unit_instance_id)
    native = scout_ability_instances_for_rules_unit(
        state=state, view=view, army_catalog=d.package.army_catalog
    )
    assert {i.model_instance_id for i in native} == set(unit.own_model_ids())
    assert {i.distance_inches for i in native} == {6}
    # Explicit per-model second-source inventory reproduces both Core examples
    # without attributing Scouts 8 to the native Infractor datasheet.
    second = tuple(
        ScoutAbilityInstance(mid, 8, "constructed:s24:scouts-eight") for mid in unit.own_model_ids()
    )
    instances = (*native, *second) if common else (native[0], *second[1:])
    options = scout_distance_options_for_model_ids(
        model_instance_ids=unit.own_model_ids(), ability_instances=instances
    )
    assert options == ((6.0, 8.0) if common else (6.0,))
    if common:
        with pytest.raises(GameLifecycleError, match="selection"):
            scout_distance_inches_for_model_ids(
                model_instance_ids=unit.own_model_ids(), ability_instances=instances
            )
    assert (
        scout_distance_inches_for_model_ids(
            model_instance_ids=unit.own_model_ids(),
            ability_instances=instances,
            selected_distance_inches=6,
        )
        == 6
    )
    with pytest.raises(GameLifecycleError, match="unavailable"):
        scout_distance_inches_for_model_ids(
            model_instance_ids=unit.own_model_ids(),
            ability_instances=instances,
            selected_distance_inches=9,
        )


def test_native_deep_strike_and_infiltrator_identity_survives_fresh_units(
    section24_definitions: Section02Definitions,
) -> None:
    from tests.support.section24_fixtures import RANGERS

    d = section24_definitions
    hawks = d.unit(HAWKS)
    assert unit_has_deep_strike(hawks)
    rangers = d.unit(RANGERS)
    state = native_state(d, rangers)
    assert rules_unit_has_infiltrators(
        state=state,
        view=rules_unit_view_by_id(state=state, unit_instance_id=rangers.unit_instance_id),
    )
    assert not unit_has_deep_strike(d.unit(BODY))
    assert d.unit(HAWKS).own_models[0] is not hawks.own_models[0]


@pytest.mark.parametrize("complete", [False, True])
def test_fights_first_registry_requires_all_present_native_models(
    section24_definitions: Section02Definitions, complete: bool
) -> None:
    from dataclasses import replace

    from tests.unit_keyword_helpers import with_model_keywords
    from warhammer40k_core.engine.core_ability_materialization import (
        record_core_fights_first_sources_for_unit,
    )
    from warhammer40k_core.engine.fights_first import FightsFirstRegistry

    unit = section24_definitions.unit(BODY)
    unit = replace(
        unit,
        datasheet_abilities=(),
        own_models=tuple(
            with_model_keywords(m, keywords=(*m.keywords, "FIGHTS_FIRST"))
            if complete or index
            else m
            for index, m in enumerate(unit.own_models)
        ),
    )
    state = native_state(section24_definitions, unit)
    record_core_fights_first_sources_for_unit(state=state, unit=unit)
    registry = FightsFirstRegistry.from_state(state)
    assert registry.has_unit(unit.unit_instance_id) is complete
