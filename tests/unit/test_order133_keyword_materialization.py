"""Raw catalog ownership survives canonical runtime number identities."""

# pyright: reportPrivateUsage=false

from __future__ import annotations

import json
from dataclasses import replace

import pytest
from tests.model_keyword_helpers import mixed_keyword_catalog

from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.core.datasheet import (
    DatasheetMusteringOption,
    DatasheetMusteringOptionEffect,
    DatasheetMusteringOptionEffectKind,
)
from warhammer40k_core.engine.army_mustering import (
    _effective_unit_keywords,
    datasheet_has_keyword,
)
from warhammer40k_core.engine.catalog_model_scope import scoped_roll_model_ids_for_effect
from warhammer40k_core.engine.list_validation import MusteringOptionSelection, UnitMusterSelection
from warhammer40k_core.engine.model_keyword_grants import (
    grant_unit_keywords,
    unit_with_attached_role_evidence,
)
from warhammer40k_core.engine.rules_units import RulesUnitComponent, RulesUnitView
from warhammer40k_core.engine.unit_factory import ModelInstance, UnitFactory, UnitInstance
from warhammer40k_core.engine.unit_keyword_queries import unit_has_keyword
from warhammer40k_core.engine.wargear_selections import ModelProfileSelection
from warhammer40k_core.rules.rule_keyword_sequences import keyword_sequence_tokens


def selection_for_catalog(catalog: ArmyCatalog) -> UnitMusterSelection:
    sheet = catalog.datasheet_by_id("core-intercessor-like-infantry")
    return UnitMusterSelection(
        unit_selection_id="number-ownership",
        datasheet_id=sheet.datasheet_id,
        model_profile_selections=tuple(
            ModelProfileSelection(model_profile_id=row.model_profile_id, model_count=row.min_models)
            for row in sheet.composition
        ),
    )


def catalog_with_specialist_keyword(token: str) -> ArmyCatalog:
    catalog = mixed_keyword_catalog()
    sheet = catalog.datasheet_by_id("core-intercessor-like-infantry")
    sheet = replace(
        sheet,
        keywords=replace(
            sheet.keywords,
            keywords=tuple(token if k == "PSYKER" else k for k in sheet.keywords.keywords),
        ),
    )
    return replace(
        catalog,
        datasheets=tuple(
            sheet if row.datasheet_id == sheet.datasheet_id else row for row in catalog.datasheets
        ),
        model_keyword_assignments=tuple(
            replace(row, keywords=tuple(token if k == "PSYKER" else k for k in row.keywords))
            for row in catalog.model_keyword_assignments
        ),
    )


@pytest.mark.parametrize(
    ("plural", "canonical"),
    [
        ("PSYKERS", "PSYKER"),
        ("DAEMONS", "DAEMON"),
        ("BATTLESUITS", "BATTLESUIT"),
        ("DEDICATED TRANSPORTS", "DEDICATED TRANSPORT"),
        ("EPIC HEROES", "EPIC HERO"),
        ("FORTIFICATIONS", "FORTIFICATION"),
        ("ASPECT WARRIORS", "ASPECT WARRIOR"),
        ("HELLFLAYERS", "HELLFLAYER"),
        ("TERMINATORS", "TERMINATOR"),
        ("JUMP PACKS", "JUMP PACK"),
        ("BURROWERS", "BURROWER"),
        ("WARLOCKS", "WARLOCK"),
        ("BEASTS", "BEAST"),
    ],
)
def test_plural_raw_catalog_keeps_model_ownership_and_rederives_on_load(
    plural: str, canonical: str
) -> None:
    catalog = catalog_with_specialist_keyword(plural)
    raw = catalog.to_payload()
    restored_catalog = ArmyCatalog.from_payload(json.loads(json.dumps(raw)))
    assert restored_catalog.to_payload() == raw
    sheet = restored_catalog.datasheet_by_id("core-intercessor-like-infantry")
    assert plural in sheet.keywords.keywords
    assert canonical in sheet.effective_keywords
    assert keyword_sequence_tokens(plural, source_keyword_sequence_parts=(canonical,)) == (
        canonical.replace(" ", "_"),
    )
    assert datasheet_has_keyword(sheet, plural)
    assert datasheet_has_keyword(sheet, canonical)
    factory = UnitFactory(catalog=restored_catalog)
    unit = factory.instantiate_unit(
        army_id="order133-keywords", datasheet=sheet, selection=selection_for_catalog(catalog)
    )
    specialist = next(m for m in unit.own_models if m.model_profile_id == "core-keyword-specialist")
    assert plural in specialist.keyword_assignment.keywords
    assert canonical in specialist.keywords
    assert plural not in specialist.keywords
    assert all(canonical not in m.keywords for m in unit.own_models if m != specialist)
    assert unit_has_keyword(unit, plural)
    assert unit_has_keyword(unit, canonical)
    view = RulesUnitView(
        unit_instance_id=unit.unit_instance_id,
        owner_player_id="player-a",
        components=(RulesUnitComponent(unit=unit, role="unit"),),
    )
    for spelling in (plural, canonical, plural.replace(" ", "_")):
        assert scoped_roll_model_ids_for_effect(
            source_rules_unit=view,
            current_roll_model_instance_ids=tuple(m.model_instance_id for m in unit.own_models),
            effect_parameters={"required_model_keyword": spelling},
        ) == (specialist.model_instance_id,)
    loaded = UnitInstance.from_payload(json.loads(json.dumps(unit.to_payload())))
    assert loaded == unit
    assert loaded.to_payload() == unit.to_payload()
    assert loaded.own_models == unit.own_models


def test_plural_beast_uses_native_geometry_on_muster_and_materialization() -> None:
    plural_catalog = catalog_with_specialist_keyword("BEASTS")
    canonical_catalog = catalog_with_specialist_keyword("BEAST")
    units: list[UnitInstance] = []
    materialized: list[ModelInstance] = []
    for catalog in (plural_catalog, canonical_catalog):
        sheet = catalog.datasheet_by_id("core-intercessor-like-infantry")
        factory = UnitFactory(catalog=catalog)
        units.append(
            factory.instantiate_unit(
                army_id="order133-beasts", datasheet=sheet, selection=selection_for_catalog(catalog)
            )
        )
        materialized.append(
            factory.instantiate_materialized_model(
                datasheet_id=sheet.datasheet_id,
                model_profile_id="core-keyword-specialist",
                model_instance_id="order133-beast-materialization",
                model_name="Source specialist",
                wargear_ids=(),
                source_id="order133:materialization-source",
                materialization_descriptor_id="order133:materialization-descriptor",
            )
        )
    geometry = tuple(
        next(m.geometry for m in unit.own_models if m.model_profile_id == "core-keyword-specialist")
        for unit in units
    )
    assert geometry[0] == geometry[1]
    assert geometry[0].height_source_id == "keyword:beast_or_cavalry"
    assert materialized[0].geometry == materialized[1].geometry
    assert "BEAST" in materialized[0].keywords
    assert "BEASTS" in materialized[0].keyword_assignment.keywords
    assert (
        ModelInstance.from_payload(materialized[0].to_payload()).keywords
        == materialized[0].keywords
    )


def test_runtime_grants_and_mustering_preserve_raw_provenance() -> None:
    catalog = catalog_with_specialist_keyword("PSYKERS")
    sheet = catalog.datasheet_by_id("core-intercessor-like-infantry")
    unit = UnitFactory(catalog=catalog).instantiate_unit(
        army_id="order133-grants", datasheet=sheet, selection=selection_for_catalog(catalog)
    )
    granted = grant_unit_keywords(unit, keywords=("TERMINATORS",), source_id="order133:grant")
    granted = unit_with_attached_role_evidence(granted, role="bodyguard")
    for model in granted.own_models:
        assert "TERMINATORS" in model.keyword_assignment.keywords
        assert "TERMINATOR" in model.keywords
        assert "order133:grant" in model.keyword_assignment.source_ids
    specialist = next(
        m for m in granted.own_models if m.model_profile_id == "core-keyword-specialist"
    )
    assert "PSYKERS" in specialist.keyword_assignment.keywords
    assert "PSYKER" in specialist.keywords
    assert UnitInstance.from_payload(granted.to_payload()).to_payload() == granted.to_payload()
    option = DatasheetMusteringOption(
        option_id="order133-number-option",
        selection_group_id="order133-number-group",
        label="Source number option",
        effects=(
            DatasheetMusteringOptionEffect(
                kind=DatasheetMusteringOptionEffectKind.ADD_KEYWORD, keyword="TERMINATORS"
            ),
        ),
        source_ids=("order133:mustering-source",),
    )
    sheet = replace(sheet, mustering_options=(option,))
    catalog = replace(
        catalog,
        datasheets=tuple(
            sheet if row.datasheet_id == sheet.datasheet_id else row for row in catalog.datasheets
        ),
    )
    selection = replace(
        selection_for_catalog(catalog),
        mustering_option_selections=(MusteringOptionSelection(option_id=option.option_id),),
    )
    assert "TERMINATOR" in _effective_unit_keywords(datasheet=sheet, selection=selection)
    mustered = UnitFactory(catalog=catalog).instantiate_unit(
        army_id="order133-mustering", datasheet=sheet, selection=selection
    )
    assert all("TERMINATOR" in model.keywords for model in mustered.own_models)
    assert all("TERMINATORS" in model.keyword_assignment.keywords for model in mustered.own_models)
    assert UnitInstance.from_payload(mustered.to_payload()) == mustered


def test_distinct_owner_labels_do_not_acquire_inferred_number_aliases() -> None:
    catalog = catalog_with_specialist_keyword("CRUSADER")
    sheet = catalog.datasheet_by_id("core-intercessor-like-infantry")
    unit = UnitFactory(catalog=catalog).instantiate_unit(
        army_id="order133-owners", datasheet=sheet, selection=selection_for_catalog(catalog)
    )
    assert unit_has_keyword(unit, "CRUSADER")
    assert not unit_has_keyword(unit, "CRUSADERS")
    assert not datasheet_has_keyword(sheet, "CRUSADERS")
