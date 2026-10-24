"""Native source classifications and selected equipment admission are independent."""

from dataclasses import replace

import pytest

from tests.support.section01_fixtures import minimal_state
from tests.support.section02_fixtures import Section02Definitions
from tests.support.section22_fixtures import AVENGERS, CRUSHERS, LORD, PSYKER
from warhammer40k_core.core.datasheet import CatalogAbilitySourceKind
from warhammer40k_core.engine.abilities import AbilitySourceKind
from warhammer40k_core.engine.ability_catalog import (
    build_player_ability_index,
    catalog_ability_records_from_catalog,
    eleventh_edition_core_ability_catalog_records,
)
from warhammer40k_core.engine.list_validation import DetachmentSelection
from warhammer40k_core.engine.wargear_selections import WargearSelection


@pytest.mark.parametrize("sheet", [LORD, PSYKER, AVENGERS, CRUSHERS])
def test_real_datasheet_section_preserves_faction_and_wargear_ownership(
    section22_definitions: Section02Definitions, sheet: str
) -> None:
    datasheet = section22_definitions.package.army_catalog.datasheet_by_id(sheet)
    factions = [a for a in datasheet.abilities if a.source_kind is CatalogAbilitySourceKind.FACTION]
    assert len(factions) == 1
    assert factions[0].source_wargear_id is None
    assert "Army Faction" in factions[0].effect_description
    for ability in datasheet.abilities:
        if ability.source_kind is CatalogAbilitySourceKind.WARGEAR:
            assert ability.source_wargear_id is not None
            assert ability.source_wargear_id.startswith(sheet + ":")


@pytest.mark.parametrize("equipped", [False, True])
def test_actual_optional_instrument_admits_only_its_equipped_ability(
    section22_definitions: Section02Definitions, equipped: bool
) -> None:
    selection = WargearSelection(
        option_id=f"{CRUSHERS}:instrument-of-chaos:option-1",
        model_profile_id=f"{CRUSHERS}:bloodcrushers",
        wargear_ids=(f"{CRUSHERS}:instrument-of-chaos",),
    )
    unit = section22_definitions.unit(CRUSHERS, wargear=(selection,) if equipped else ())
    state = minimal_state(section22_definitions, unit)
    catalog = section22_definitions.package.army_catalog
    index = build_player_ability_index(
        catalog_ability_records_from_catalog(catalog),
        army=state.army_definitions[0],
        catalog=catalog,
    )
    names = {r.definition.name for r in index.all_records()}
    assert ("Instrument of Chaos" in names) is equipped
    assert "Daemonic Icon" not in names
    owners = [m for m in unit.own_models if f"{CRUSHERS}:instrument-of-chaos" in m.wargear_ids]
    assert len(owners) == int(equipped)


@pytest.mark.parametrize("matching", [False, True])
def test_faction_activation_index_requires_selected_faction_identity(
    section22_definitions: Section02Definitions, matching: bool
) -> None:
    state = minimal_state(section22_definitions)
    army = state.army_definitions[0]
    # Explicit generic faction-record input tests the shared gate; it does not
    # turn a native load-only army rule into an executable named provider.
    template = next(
        r
        for r in eleventh_edition_core_ability_catalog_records()
        if r.record_id.endswith("keyword:keyword-infantry")
    )
    record = replace(
        template,
        record_id="constructed:s22:faction",
        source_kind=AbilitySourceKind.FACTION,
        faction_id="EC",
    )
    army = replace(
        army,
        detachment_selection=DetachmentSelection(
            "EC" if matching else "ASURYANI", army.detachment_selection.detachment_ids
        ),
    )
    index = build_player_ability_index(
        (record,), army=army, catalog=section22_definitions.package.army_catalog
    )
    assert bool(index.all_records()) is matching
