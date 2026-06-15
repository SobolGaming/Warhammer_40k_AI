from __future__ import annotations

from dataclasses import replace

from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.core.datasheet import CatalogAbilitySupport, DatasheetAbilityDescriptor
from warhammer40k_core.engine.list_validation import ModelProfileSelection, UnitMusterSelection
from warhammer40k_core.engine.unit_abilities import (
    deadly_demise_profile_for_unit,
    firing_deck_value_for_unit,
    scouts_ability_descriptors_for_unit,
    scouts_distance_inches_from_descriptor,
    unit_has_deadly_demise,
    unit_has_deep_strike,
    unit_has_firing_deck,
    unit_has_infiltrators,
    unit_has_leader,
    unit_has_scouts,
    unit_has_support,
)
from warhammer40k_core.engine.unit_factory import UnitFactory, UnitInstance


def test_core_keyword_ability_descriptors_enable_boolean_families_without_keywords() -> None:
    unit = _unit_with_abilities(
        _ability(ability_id="source-deep-strike", name="Core Deep Strike"),
        _ability(ability_id="source-infiltrators", name="Infiltrators"),
        _ability(ability_id="source-leader", name="Leader"),
        _ability(ability_id="source-support", name="Support"),
    )

    assert unit_has_deep_strike(unit)
    assert unit_has_infiltrators(unit)
    assert unit_has_leader(unit)
    assert unit_has_support(unit)


def test_parameterized_core_keyword_ability_descriptors_parse_values_without_keywords() -> None:
    unit = _unit_with_abilities(
        _ability(
            ability_id="source-scouts",
            name='Scouts 6"',
            parameter_tokens=('6"',),
        ),
        _ability(
            ability_id="source-firing-deck",
            name="Firing Deck 2",
            parameter_tokens=("2",),
        ),
        _ability(
            ability_id="source-deadly-demise",
            name="Deadly Demise D3",
            parameter_tokens=("d3",),
        ),
    )

    scouts_descriptors = scouts_ability_descriptors_for_unit(unit)
    deadly_demise = deadly_demise_profile_for_unit(unit)

    assert unit_has_scouts(unit)
    assert unit_has_firing_deck(unit)
    assert unit_has_deadly_demise(unit)
    assert len(scouts_descriptors) == 1
    assert scouts_distance_inches_from_descriptor(scouts_descriptors[0]) == 6.0
    assert firing_deck_value_for_unit(unit) == 2
    assert deadly_demise is not None
    assert deadly_demise.mortal_wounds_token == "D3"


def _unit_with_abilities(*abilities: DatasheetAbilityDescriptor) -> UnitInstance:
    catalog = ArmyCatalog.phase9a_canonical_content_pack()
    datasheet = catalog.datasheet_by_id("core-intercessor-like-infantry")
    unit = UnitFactory(catalog=catalog).instantiate_unit(
        army_id="army-alpha",
        selection=UnitMusterSelection(
            unit_selection_id="ability-unit",
            datasheet_id=datasheet.datasheet_id,
            model_profile_selections=(
                ModelProfileSelection(
                    model_profile_id="core-intercessor-like",
                    model_count=5,
                ),
            ),
        ),
        datasheet=datasheet,
    )
    return replace(unit, datasheet_abilities=abilities)


def _ability(
    *,
    ability_id: str,
    name: str,
    parameter_tokens: tuple[str, ...] = (),
) -> DatasheetAbilityDescriptor:
    return DatasheetAbilityDescriptor(
        ability_id=ability_id,
        name=name,
        source_id=f"datasheet:core-intercessor-like-infantry:ability:{ability_id}",
        support=CatalogAbilitySupport.DESCRIPTOR_ONLY,
        timing_tags=(),
        parameter_tokens=parameter_tokens,
    )
