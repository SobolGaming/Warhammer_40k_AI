"""Core wargear grant lifetime on native attached physical components."""

from collections import Counter
from pathlib import Path

import pytest
from tools.generate_ability_support_matrix import (
    _ability_support_catalog_package,  # pyright: ignore[reportPrivateUsage]
)

from tests.support.section02_fixtures import Section02Definitions
from tests.support.section19_fixtures import attached_scene, destroy, grant_definitions, has_lethal
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.list_validation import UnitMusterSelection
from warhammer40k_core.engine.unit_factory import UnitFactory, UnitFactoryError, UnitInstance
from warhammer40k_core.engine.wargear_selections import ModelProfileSelection, WargearSelection
from warhammer40k_core.rules.catalog_package import CanonicalCatalogPackage
from warhammer40k_core.rules.data_package import DataPackageId
from warhammer40k_core.rules.wahapedia_bridge_patterns import SINGLE_REPLACEMENT_RE
from warhammer40k_core.rules.wahapedia_loadout_bridge import LoadoutAssignments
from warhammer40k_core.rules.wahapedia_replacement_option_bridge import (
    append_single_replacement_rows,
)
from warhammer40k_core.rules.wahapedia_schema import NormalizedSourceRow


def test_bearer_owned_item_survives_other_casualty_but_stops_after_bearer_loss(
    section22_definitions: Section02Definitions,
) -> None:
    # The selected native Lord carries a real bolt pistol; this generic unit-wide
    # keyword grant is an explicit Core Wargear input, not its native pistol rule.
    s = attached_scene(grant_definitions(section22_definitions, "leader", wargear=True))
    decisions = DecisionController()
    assert all(has_lethal(s, m.model_instance_id) for m in s.view.alive_models())
    destroy(s, decisions, s.body.own_model_ids()[0])
    assert all(has_lethal(s, m.model_instance_id) for m in s.view.alive_models())
    destroy(s, decisions, s.leader.own_model_ids()[0])
    assert len(s.view.alive_models()) == len(s.body.own_models) - 1
    assert all(not has_lethal(s, m.model_instance_id) for m in s.view.alive_models())


DEFILER_IDS = ("000000969", "000004209", "000004208", "000001030", "000004207")


@pytest.fixture(scope="module")
def replacement_package(selected_army_source_index: Path | None) -> CanonicalCatalogPackage:
    return _ability_support_catalog_package(
        datasheet_ids=(*DEFILER_IDS, "000000968", "000000612", "000000613"),
        source_index_dir=selected_army_source_index,
    )


def _selected_unit(
    package: CanonicalCatalogPackage,
    datasheet_id: str,
    profile: str,
    options: tuple[tuple[str, str], ...] = (),
) -> UnitInstance:
    selection = UnitMusterSelection(
        unit_selection_id="replacement-control",
        datasheet_id=datasheet_id,
        model_profile_selections=(
            ModelProfileSelection(model_profile_id=f"{datasheet_id}:{profile}", model_count=1),
        ),
        wargear_selections=tuple(
            WargearSelection(
                option_id=f"{datasheet_id}:{option}",
                model_profile_id=f"{datasheet_id}:{profile}",
                wargear_ids=(f"{datasheet_id}:{weapon}",),
            )
            for option, weapon in options
        ),
    )
    restored_selection = UnitMusterSelection.from_payload(selection.to_payload())
    assert restored_selection == selection
    factory = UnitFactory(catalog=package.army_catalog, model_geometries=package.model_geometries)
    unit = factory.instantiate_unit(
        army_id="replacement-control",
        selection=restored_selection,
        datasheet=package.army_catalog.datasheet_by_id(datasheet_id),
    )
    assert UnitInstance.from_payload(unit.to_payload()) == unit
    assert (
        factory.instantiate_unit(
            army_id="replacement-control",
            selection=selection,
            datasheet=package.army_catalog.datasheet_by_id(datasheet_id),
        )
        == unit
    )
    return unit


@pytest.mark.parametrize("datasheet_id", DEFILER_IDS)
def test_native_plural_replacement_removes_all_named_source_copies(
    replacement_package: CanonicalCatalogPackage, datasheet_id: str
) -> None:
    # Invariant: replace the complete source-named loadout on the physical model.
    cutter = "pyraflux-magma-cutters" if datasheet_id == "000001030" else "magma-cutters"
    unit = _selected_unit(
        replacement_package, datasheet_id, "defiler", ((f"{cutter}:option-2", cutter),)
    )
    counts = Counter(unit.own_models[0].wargear_ids)
    assert counts[f"{datasheet_id}:excruciator-cannon"] == 0
    assert counts[f"{datasheet_id}:{cutter}"] == 2
    assert sum(counts.values()) == 6


@pytest.mark.parametrize("datasheet_id", DEFILER_IDS)
def test_native_defiler_default_and_independent_slot_controls(
    replacement_package: CanonicalCatalogPackage, datasheet_id: str
) -> None:
    default = _selected_unit(replacement_package, datasheet_id, "defiler")
    assert Counter(default.own_models[0].wargear_ids)[f"{datasheet_id}:excruciator-cannon"] == 2
    single = (("heavy-baleflamer-electroscourge:option-3", "electroscourge"),)
    unit = _selected_unit(replacement_package, datasheet_id, "defiler", single)
    counts = Counter(unit.own_models[0].wargear_ids)
    assert counts[f"{datasheet_id}:heavy-baleflamer"] == 0
    assert counts[f"{datasheet_id}:electroscourge"] == 1
    assert counts[f"{datasheet_id}:heavy-missile-launcher"] == 1
    with pytest.raises(UnitFactoryError):
        _selected_unit(
            replacement_package,
            datasheet_id,
            "defiler",
            (*single, ("heavy-missile-launcher-electroscourge:option-4", "electroscourge")),
        )
    lascannons = _selected_unit(
        replacement_package,
        datasheet_id,
        "defiler",
        (
            ("heavy-baleflamer-hades-lascannon:option-3", "hades-lascannon"),
            ("heavy-missile-launcher-hades-lascannon:option-4", "hades-lascannon"),
        ),
    )
    assert Counter(lascannons.own_models[0].wargear_ids)[f"{datasheet_id}:hades-lascannon"] == 2


def test_native_singular_item_replaced_with_two_copies(
    replacement_package: CanonicalCatalogPackage,
) -> None:
    unit = _selected_unit(
        replacement_package,
        "000000968",
        "maulerfiend",
        (("magma-cutters:option-1", "magma-cutters"),),
    )
    counts = Counter(unit.own_models[0].wargear_ids)
    assert counts["000000968:lasher-tendrils"] == 0
    assert counts["000000968:magma-cutters"] == 2


@pytest.mark.parametrize(
    ("datasheet_id", "profile", "option", "original", "replacement"),
    [
        (
            "000000612",
            "war-walkers",
            "shuriken-cannon-bright-lance:option-1",
            "shuriken-cannon",
            "bright-lance",
        ),
        (
            "000000613",
            "wraithlord",
            "shuriken-catapults-flamer:option-1",
            "shuriken-catapult",
            "flamer",
        ),
    ],
)
def test_native_single_copy_option_preserves_other_default_copy(
    replacement_package: CanonicalCatalogPackage,
    datasheet_id: str,
    profile: str,
    option: str,
    original: str,
    replacement: str,
) -> None:
    unit = _selected_unit(replacement_package, datasheet_id, profile, ((option, replacement),))
    counts = Counter(unit.own_models[0].wargear_ids)
    assert counts[f"{datasheet_id}:{original}"] == 1
    assert counts[f"{datasheet_id}:{replacement}"] == 1


@pytest.mark.parametrize("count", [None, 0, 3])
def test_plural_source_boundary_requires_and_preserves_explicit_removal_count(
    count: int | None,
) -> None:
    # Pure source-boundary input: no synthetic engine state or support admission.
    description = "This model's cannons can be replaced with 2 cutters."
    row = NormalizedSourceRow(
        source_package_id=DataPackageId("test", "replacement", "1"),
        source_table="Datasheets_options",
        source_row_id="model:2",
        source_row_number=2,
        fields=(("line", "2"), ("description", description)),
        text_fields=(),
    )
    match = SINGLE_REPLACEMENT_RE.fullmatch(description)
    assert match is not None
    loadout = (
        None
        if count is None
        else LoadoutAssignments(
            profile_ids_by_wargear_name={"cannons": ("model",)},
            wargear_count_by_name_and_profile_id={("cannons", "model"): count},
        )
    )
    rows: dict[str, list[dict[str, str]]] = {"Datasheets_options": []}

    def translate() -> None:
        append_single_replacement_rows(
            row=row,
            datasheet_id="sheet",
            model_profile_id="model",
            wargear_ids_by_name={"cannon": "cannon", "cutters": "cutters"},
            match=match,
            loadout_assignments=loadout,
            bridged_rows=rows,
            error_type=ValueError,
        )

    if count is None or count == 0:
        with pytest.raises(ValueError, match="Plural replacement"):
            translate()
        assert rows["Datasheets_options"] == []
    else:
        translate()
        assert [row["effect_kind"] for row in rows["Datasheets_options"]] == [
            "replace_wargear",
            "remove_wargear_if_selected",
            "remove_wargear_if_selected",
        ]
        assert [row["effect_wargear_count"] for row in rows["Datasheets_options"]] == [
            "2",
            "0",
            "0",
        ]
        assert {row["source_ids"] for row in rows["Datasheets_options"]} == {row.stable_source_id()}
