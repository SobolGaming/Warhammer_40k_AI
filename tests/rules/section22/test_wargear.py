"""Core wargear grant lifetime on native attached physical components."""

import json
from collections import Counter
from dataclasses import replace
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


TERMINATORS = "000004081"


@pytest.fixture(scope="module")
def terminator_package(selected_army_source_index: Path | None) -> CanonicalCatalogPackage:
    return _ability_support_catalog_package(
        datasheet_ids=(TERMINATORS, "000004090", "000004083"),
        source_index_dir=selected_army_source_index,
    )


def _terminator_selection(
    ordinary: int, champion: int, *, model_count: int = 5
) -> UnitMusterSelection:
    return UnitMusterSelection(
        unit_selection_id="terminators",
        datasheet_id=TERMINATORS,
        model_profile_selections=(
            ModelProfileSelection(f"{TERMINATORS}:chaos-terminators", model_count - 1),
            ModelProfileSelection(f"{TERMINATORS}:terminator-champion", 1),
        ),
        wargear_selections=tuple(
            WargearSelection(
                option_id=f"{TERMINATORS}:power-fist-{role}:option-4",
                model_profile_id=f"{TERMINATORS}:{role}",
                wargear_ids=(f"{TERMINATORS}:power-fist",),
                selection_count=count,
            )
            for role, count in (("chaos-terminators", ordinary), ("terminator-champion", champion))
            if count
        ),
    )


@pytest.mark.parametrize(
    ("model_count", "ordinary", "champion"),
    [(5, 0, 0), (5, 1, 0), (5, 3, 0), (5, 0, 1), (5, 1, 1), (5, 2, 1)],
)
def test_native_terminator_role_caps_construct_and_roundtrip(
    terminator_package: CanonicalCatalogPackage,
    model_count: int,
    ordinary: int,
    champion: int,
) -> None:
    # Shared group capacity is 3/5 models; the role-local caps remain 3 and 1.
    package = terminator_package
    sheet = package.army_catalog.datasheet_by_id(TERMINATORS)
    options = tuple(o for o in sheet.wargear_options if o.option_id.endswith(":option-4"))
    assert len(options) == 2
    for option, cap in zip(options, (3, 1), strict=True):
        limit = option.selection_limit
        assert limit is not None
        assert (limit.models_per_increment, limit.max_group_selections_per_increment) == (5, 3)
        assert limit.max_option_selections_per_increment == cap
    chosen = _terminator_selection(ordinary, champion, model_count=model_count)
    saved_selection = json.loads(json.dumps(chosen.to_payload()))
    assert UnitMusterSelection.from_payload(saved_selection) == chosen
    factory = UnitFactory(catalog=package.army_catalog, model_geometries=package.model_geometries)
    unit = factory.instantiate_unit(army_id="scaled", datasheet=sheet, selection=chosen)
    assert len(unit.own_models) == model_count
    for role, expected in (("chaos-terminators", ordinary), ("terminator-champion", champion)):
        models = tuple(m for m in unit.own_models if m.model_profile_id == f"{TERMINATORS}:{role}")
        assert sum(f"{TERMINATORS}:power-fist" in m.wargear_ids for m in models) == expected
        assert sum(f"{TERMINATORS}:accursed-weapon" in m.wargear_ids for m in models) == (
            len(models) - expected
        )
        assert all(f"{TERMINATORS}:combi-bolter" in m.wargear_ids for m in models)
    assert UnitInstance.from_payload(json.loads(json.dumps(unit.to_payload()))) == unit
    assert (
        factory.instantiate_unit(
            army_id="scaled",
            datasheet=sheet,
            selection=UnitMusterSelection.from_payload(saved_selection),
        )
        == unit
    )


@pytest.mark.parametrize(("ordinary", "champion"), [(4, 0), (3, 1), (0, 2), (4, 1)])
def test_native_terminator_excess_role_and_group_choices_reject(
    terminator_package: CanonicalCatalogPackage, ordinary: int, champion: int
) -> None:
    from warhammer40k_core.engine.list_validation_errors import ListValidationError

    package = terminator_package
    factory = UnitFactory(catalog=package.army_catalog, model_geometries=package.model_geometries)
    with pytest.raises(UnitFactoryError) as error:
        factory.instantiate_unit(
            army_id="scaled",
            datasheet=package.army_catalog.datasheet_by_id(TERMINATORS),
            selection=_terminator_selection(ordinary, champion),
        )
    assert isinstance(error.value.__cause__, ListValidationError)
    if (ordinary, champion) == (3, 1):
        assert "group exceeds its model-count-scaled limit" in str(error.value.__cause__)


def test_native_terminator_muster_and_army_persistence(
    terminator_package: CanonicalCatalogPackage,
) -> None:
    from warhammer40k_core.core.detachment import DetachmentDefinition
    from warhammer40k_core.engine.army_mustering import (
        ArmyDefinition,
        ArmyMusterRequest,
        muster_army,
    )
    from warhammer40k_core.engine.list_validation import DetachmentSelection
    from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
        faction_detachments_2026_27,
    )

    package = terminator_package
    source = next(
        d
        for d in faction_detachments_2026_27.detachment_rows()
        if d.detachment_id == "court-of-the-phoenician"
    )
    # Source detachment identity, bounded non-strict component roster; no full-army claim.
    detachment = DetachmentDefinition(
        detachment_id=source.detachment_id,
        canonical_detachment_id=source.detachment_id,
        name=source.name,
        faction_id="EC",
        detachment_point_cost=source.detachment_point_cost,
        unit_datasheet_ids=(TERMINATORS,),
        force_disposition_ids=(source.force_disposition_id,),
        source_ids=source.source_ids,
    )
    catalog = replace(package.army_catalog, detachments=(detachment,))
    request = ArmyMusterRequest(
        army_id="scaled",
        player_id="owner",
        catalog_id=catalog.catalog_id,
        source_package_id=catalog.source_package_id,
        ruleset_id=catalog.ruleset_id,
        detachment_selection=DetachmentSelection("EC", (detachment.detachment_id,)),
        force_disposition_id=source.force_disposition_id,
        unit_selections=(_terminator_selection(2, 1),),
    )
    restored_request = ArmyMusterRequest.from_payload(json.loads(json.dumps(request.to_payload())))
    assert restored_request == request
    army = muster_army(catalog=catalog, request=request, model_geometries=package.model_geometries)
    assert len(army.units[0].own_models) == 5
    assert ArmyDefinition.from_payload(json.loads(json.dumps(army.to_payload()))) == army
    assert (
        muster_army(
            catalog=catalog, request=restored_request, model_geometries=package.model_geometries
        )
        == army
    )


@pytest.mark.parametrize(
    ("sheet_id", "count"),
    [
        ("000004090", 2),
        ("000004083", 1),
    ],
)
def test_native_adjacent_unscaled_defaults_still_construct(
    terminator_package: CanonicalCatalogPackage, sheet_id: str, count: int
) -> None:
    package = terminator_package
    sheet = package.army_catalog.datasheet_by_id(sheet_id)
    chosen = UnitMusterSelection(
        unit_selection_id="adjacent",
        datasheet_id=sheet_id,
        model_profile_selections=tuple(
            ModelProfileSelection(c.model_profile_id, c.min_models) for c in sheet.composition
        ),
    )
    unit = UnitFactory(
        catalog=package.army_catalog, model_geometries=package.model_geometries
    ).instantiate_unit(army_id="scaled", datasheet=sheet, selection=chosen)
    assert len(unit.own_models) == count
    assert UnitInstance.from_payload(json.loads(json.dumps(unit.to_payload()))) == unit


@pytest.mark.parametrize("selected_count", [0, 1])
@pytest.mark.parametrize("field", ["models_per_increment", "max_group_selections_per_increment"])
def test_native_scaled_group_metadata_drift_rejects_even_without_choices(
    terminator_package: CanonicalCatalogPackage, selected_count: int, field: str
) -> None:
    from warhammer40k_core.engine.list_validation_errors import ListValidationError

    package = terminator_package
    sheet = package.army_catalog.datasheet_by_id(TERMINATORS)
    option = next(o for o in sheet.wargear_options if o.option_id.endswith("champion:option-4"))
    limit = option.selection_limit
    assert limit is not None
    drifted = (
        replace(limit, models_per_increment=10)
        if field == "models_per_increment"
        else replace(limit, max_group_selections_per_increment=4)
    )
    invalid_sheet = replace(
        sheet,
        wargear_options=tuple(
            replace(o, selection_limit=drifted) if o == option else o for o in sheet.wargear_options
        ),
    )
    catalog = replace(
        package.army_catalog,
        datasheets=tuple(
            invalid_sheet if s == sheet else s for s in package.army_catalog.datasheets
        ),
    )
    with pytest.raises(UnitFactoryError) as error:
        UnitFactory(catalog=catalog, model_geometries=package.model_geometries).instantiate_unit(
            army_id="scaled",
            datasheet=invalid_sheet,
            selection=_terminator_selection(selected_count, 0),
        )
    assert isinstance(error.value.__cause__, ListValidationError)
    assert "share limit metadata" in str(error.value.__cause__)


@pytest.mark.parametrize(
    ("ordinary", "champion", "message"),
    [
        (4, 0, "scaled option limit"),
        (0, 2, "scaled option limit"),
        (3, 1, "group exceeds"),
    ],
)
def test_shared_scaled_owner_enforces_each_role_cap_before_group_total(
    ordinary: int,
    champion: int,
    message: str,
) -> None:
    from warhammer40k_core.engine.scaled_wargear_limits import (
        ScaledWargearSelection,
        validate_scaled_wargear_selections,
    )

    with pytest.raises(ValueError, match=message):
        validate_scaled_wargear_selections(
            unit_model_count=5,
            selections=(
                ScaledWargearSelection("ordinary", "group", 5, 3, 3, ordinary),
                ScaledWargearSelection("champion", "group", 5, 3, 1, champion),
            ),
            error_type=ValueError,
        )


@pytest.mark.parametrize(("ordinary", "champion"), [(0, 0), (2, 1)])
def test_native_terminator_session_persistence_and_replay(
    terminator_package: CanonicalCatalogPackage, ordinary: int, champion: int
) -> None:
    from tests.support.faction_batch01 import anchor, scene, selection
    from warhammer40k_core.adapters.local_session import LocalGameSession
    from warhammer40k_core.core.detachment import DetachmentDefinition
    from warhammer40k_core.engine.replay import ReplayRunner
    from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
        faction_detachments_2026_27 as identities,
    )

    package = terminator_package
    source = next(
        d for d in identities.detachment_rows() if d.detachment_id == "court-of-the-phoenician"
    )
    faction = next(f for f in package.army_catalog.factions if f.faction_id == "EC")
    native_faction = next(
        f for f in identities.faction_rows() if f.faction_id == "emperors-children"
    )
    catalog = replace(
        package.army_catalog,
        factions=(
            replace(
                faction,
                faction_id=native_faction.faction_id,
                source_ids=(*native_faction.source_ids, *faction.source_ids),
            ),
        ),
        detachments=(
            DetachmentDefinition(
                detachment_id=source.detachment_id,
                canonical_detachment_id=source.detachment_id,
                name=source.name,
                faction_id=native_faction.faction_id,
                detachment_point_cost=source.detachment_point_cost,
                unit_datasheet_ids=tuple(s.datasheet_id for s in package.army_catalog.datasheets),
                force_disposition_ids=tuple(
                    sorted({source.force_disposition_id, "take-and-hold", "purge-the-foe"})
                ),
                source_ids=source.source_ids,
            ),
        ),
    )
    d = Section02Definitions(replace(package, army_catalog=catalog), 0.0)
    # Normal muster/factory and engine-generated valid checkpoint; earlier phases/full roster
    # legality are outside this component test, as in the shared scene fixture.
    s = scene(
        d,
        (_terminator_selection(ordinary, champion),),
        (selection(d, "000004090", "spawn"),),
        seed="terminator-scaled-persistence",
    )
    anchor(s)
    saved = s.session.to_persistence_payload()
    restored = LocalGameSession.from_persistence_payload(json.loads(json.dumps(saved)))
    assert restored.to_persistence_payload() == saved
    assert (
        ReplayRunner.from_payload(s.session.replay_artifact(artifact_id="scaled"))
        .run()
        .reproduced_exactly
    )


def test_native_terminator_composition_remains_five_models(
    terminator_package: CanonicalCatalogPackage,
) -> None:
    from warhammer40k_core.engine.list_validation_errors import ListValidationError

    package = terminator_package
    with pytest.raises(UnitFactoryError) as error:
        UnitFactory(
            catalog=package.army_catalog, model_geometries=package.model_geometries
        ).instantiate_unit(
            army_id="scaled",
            datasheet=package.army_catalog.datasheet_by_id(TERMINATORS),
            selection=_terminator_selection(0, 0, model_count=10),
        )
    assert isinstance(error.value.__cause__, ListValidationError)
    assert "model_count exceeds datasheet maximum" in str(error.value.__cause__)


@pytest.mark.parametrize(
    ("model_count", "ordinary", "champion"), [(5, 2, 1), (10, 4, 2), (10, 6, 0)]
)
def test_shared_scaled_owner_preserves_multiple_increment_arithmetic(
    model_count: int,
    ordinary: int,
    champion: int,
) -> None:
    from warhammer40k_core.engine.scaled_wargear_limits import (
        ScaledWargearSelection,
        validate_scaled_wargear_selections,
    )

    # Pure owner arithmetic; the native Terminator source admits only five models.
    validate_scaled_wargear_selections(
        unit_model_count=model_count,
        selections=(
            ScaledWargearSelection("ordinary", "group", 5, 3, 3, ordinary),
            ScaledWargearSelection("champion", "group", 5, 3, 1, champion),
        ),
        error_type=ValueError,
    )


@pytest.mark.parametrize("option_cap", [0, -1, True])
def test_shared_scaled_owner_validates_unselected_role_metadata(option_cap: int) -> None:
    from warhammer40k_core.engine.scaled_wargear_limits import (
        ScaledWargearSelection,
        validate_scaled_wargear_selections,
    )

    with pytest.raises(
        ValueError, match="max_option_selections_per_increment must be a positive integer"
    ):
        validate_scaled_wargear_selections(
            unit_model_count=5,
            selections=(
                ScaledWargearSelection("ordinary", "group", 5, 3, 3, 0),
                ScaledWargearSelection("champion", "group", 5, 3, option_cap, 0),
            ),
            error_type=ValueError,
        )


@pytest.mark.parametrize(("ordinary", "champion"), [(1, 0), (0, 1), (1, 1)])
def test_native_equal_role_caps_keep_shared_chainfist_limit(
    terminator_package: CanonicalCatalogPackage, ordinary: int, champion: int
) -> None:
    from warhammer40k_core.engine.list_validation_errors import ListValidationError

    package = terminator_package
    chosen = replace(
        _terminator_selection(0, 0),
        wargear_selections=tuple(
            WargearSelection(
                option_id=f"{TERMINATORS}:chainfist-{role}:option-5",
                model_profile_id=f"{TERMINATORS}:{role}",
                wargear_ids=(f"{TERMINATORS}:chainfist",),
            )
            for role, count in (("chaos-terminators", ordinary), ("terminator-champion", champion))
            if count
        ),
    )
    factory = UnitFactory(catalog=package.army_catalog, model_geometries=package.model_geometries)
    sheet = package.army_catalog.datasheet_by_id(TERMINATORS)
    if ordinary + champion > 1:
        with pytest.raises(UnitFactoryError) as error:
            factory.instantiate_unit(army_id="scaled", datasheet=sheet, selection=chosen)
        assert isinstance(error.value.__cause__, ListValidationError)
        assert "group exceeds its model-count-scaled limit" in str(error.value.__cause__)
    else:
        unit = factory.instantiate_unit(army_id="scaled", datasheet=sheet, selection=chosen)
        assert sum(f"{TERMINATORS}:chainfist" in m.wargear_ids for m in unit.own_models) == 1
        assert UnitInstance.from_payload(json.loads(json.dumps(unit.to_payload()))) == unit
