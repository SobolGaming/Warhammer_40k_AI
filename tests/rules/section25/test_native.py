"""Unmodified retained real datasheets: faction, equipment and physical construction.

This package deliberately has no detachments; no native roster/provider admission
is inferred from these selected source definitions or analytical Core scenarios.
"""

from dataclasses import replace

import pytest

from tests.support.section02_fixtures import Section02Definitions
from tests.support.section25_fixtures import NATIVE_IDS, selection
from warhammer40k_core.engine.list_validation import (
    BattleSizeMusteringPolicy,
    DetachmentSelection,
    resolve_model_profile_selections,
    validate_detachment_selection,
    validate_unit_selection_for_faction,
)
from warhammer40k_core.engine.list_validation_errors import ListValidationError
from warhammer40k_core.engine.roster_unit_limits import datasheet_unit_limit
from warhammer40k_core.engine.unit_factory import UnitFactoryError, UnitInstance
from warhammer40k_core.engine.wargear_selections import ModelProfileSelection, WargearSelection


@pytest.mark.parametrize("datasheet_id", NATIVE_IDS)
def test_real_faction_composition_and_equipment_reach_physical_models(
    section25_definitions: Section02Definitions, datasheet_id: str
) -> None:
    d = section25_definitions
    c = d.package.army_catalog
    sheet = c.datasheet_by_id(datasheet_id)
    faction = c.faction_by_id("EC" if datasheet_id in NATIVE_IDS[:2] else "AE")
    other = c.faction_by_id("AE" if faction.faction_id == "EC" else "EC")
    selected = selection(c, "physical", datasheet_id)
    assert (
        validate_unit_selection_for_faction(catalog=c, selection=selected, faction=faction) is sheet
    )
    with pytest.raises(ListValidationError, match="not legal for faction"):
        validate_unit_selection_for_faction(catalog=c, selection=selected, faction=other)
    partial = replace(
        faction, faction_keywords=("CHILDREN" if faction.faction_id == "EC" else "URYANI",)
    )
    with pytest.raises(ListValidationError, match="not legal for faction"):
        validate_unit_selection_for_faction(catalog=c, selection=selected, faction=partial)
    unit = d.unit(datasheet_id, identity="physical")
    assert len(unit.own_models) == sum(p.min_models for p in sheet.composition)
    assert all(m.wargear_ids for m in unit.own_models)
    assert set(unit.faction_keywords) & set(faction.faction_keywords)
    assert UnitInstance.from_payload(unit.to_payload()).to_payload() == unit.to_payload()
    invalid_count = (
        ModelProfileSelection(
            sheet.composition[0].model_profile_id, sheet.composition[0].max_models + 1
        ),
        *selected.model_profile_selections[1:],
    )
    with pytest.raises(ListValidationError):
        resolve_model_profile_selections(datasheet=sheet, selections=invalid_count)
    with pytest.raises(UnitFactoryError):
        d.unit(
            datasheet_id,
            wargear=(
                WargearSelection(
                    "not-advertised", sheet.composition[0].model_profile_id, ("not-equipped",)
                ),
            ),
        )


def test_real_battleline_transport_and_epic_keywords_have_distinct_limit_roles(
    section25_definitions: Section02Definitions,
) -> None:
    c = section25_definitions.package.army_catalog
    for policy, limit in [
        (BattleSizeMusteringPolicy.incursion(), 2),
        (BattleSizeMusteringPolicy.strike_force(), 3),
    ]:
        assert datasheet_unit_limit(c.datasheet_by_id("000004080"), policy=policy) == limit * 2
        assert datasheet_unit_limit(c.datasheet_by_id("000000599"), policy=policy) == limit * 2
        # Epic uniqueness is a separate report consumer, covered with physical roster copies.
        assert datasheet_unit_limit(c.datasheet_by_id("000004193"), policy=policy) == limit
    assert c.detachments == ()
    with pytest.raises(ListValidationError, match="was not found"):
        validate_detachment_selection(
            catalog=c, selection=DetachmentSelection("EC", ("not-admitted",))
        )


def test_native_mutable_instance_payload_isolation(
    section25_definitions: Section02Definitions,
) -> None:
    d = section25_definitions
    left, right = d.unit(NATIVE_IDS[0]), d.unit(NATIVE_IDS[0])
    assert left.to_payload() == right.to_payload()
    assert left is not right
    assert left.own_models[0] is not right.own_models[0]
    changed = replace(left, own_models=(replace(left.own_models[0], wounds_remaining=0),))
    assert changed.own_models[0].wounds_remaining == 0
    assert right.own_models[0].wounds_remaining == right.own_models[0].initial_wounds
