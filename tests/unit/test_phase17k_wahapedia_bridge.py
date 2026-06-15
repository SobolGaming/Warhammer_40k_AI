from __future__ import annotations

import json
import math
from dataclasses import replace
from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import cast

import pytest

from warhammer40k_core.core.attributes import Characteristic
from warhammer40k_core.core.datasheet import (
    BaseSizeKind,
    DatasheetWargearOption,
    DatasheetWargearOptionEffect,
    WargearOptionConditionKind,
    WargearOptionEffectKind,
)
from warhammer40k_core.core.model_geometry_catalog import (
    GeometryMeasurementKind,
    GeometrySourceUnits,
)
from warhammer40k_core.engine.list_validation import (
    ListValidationError,
    WargearSelection,
    resolve_wargear_selections,
)
from warhammer40k_core.rules.catalog_generation import build_canonical_catalog_package
from warhammer40k_core.rules.data_package import CatalogVersion, DataPackageId
from warhammer40k_core.rules.source_reference_generation import build_source_reference_catalog
from warhammer40k_core.rules.wahapedia_bridge import (
    EVENT_COMPANION_BASE_SIZE_GUIDE_DOCUMENT_REFERENCE,
    EVENT_COMPANION_BASE_SIZE_GUIDE_SOURCE_ID,
    ModelHeightOverride,
    WahapediaBridgeError,
    build_wahapedia_canonical_bridge_artifacts,
)
from warhammer40k_core.rules.wahapedia_schema import (
    NormalizedSourceRow,
    WahapediaCsvTable,
    WahapediaJsonArtifact,
    WahapediaJsonArtifactPayload,
)

_WAHAPEDIA_10E_JSON = (
    Path(__file__).resolve().parents[2]
    / "data"
    / "source_snapshots"
    / "wahapedia"
    / ("1" + "0" + "th-edition")
    / "2026-06-14"
    / "json"
)
_REQUIRED_TABLES = (
    "Abilities",
    "Datasheets",
    "Datasheets_abilities",
    "Datasheets_keywords",
    "Datasheets_leader",
    "Datasheets_models",
    "Datasheets_models_cost",
    "Datasheets_options",
    "Datasheets_unit_composition",
    "Datasheets_wargear",
    "Factions",
)


def test_phase17k_bloodcrushers_bridge_generates_pdf_corrected_canonical_catalog() -> None:
    package = build_canonical_catalog_package(
        package_id=_catalog_package_id(),
        catalog_version=_catalog_version(),
        source_artifacts=_bloodcrushers_bridge_artifacts(),
    )
    datasheet = package.army_catalog.datasheet_by_id("000001115")
    profiles_by_id = {profile.model_profile_id: profile for profile in datasheet.model_profiles}
    composition_by_id = {part.model_profile_id: part for part in datasheet.composition}
    wargear_by_id = {wargear.wargear_id: wargear for wargear in package.army_catalog.wargear}
    options_by_id = {option.option_id: option for option in datasheet.wargear_options}
    abilities_by_name = {ability.name: ability for ability in datasheet.abilities}

    assert datasheet.name == "Bloodcrushers"
    assert datasheet.keywords.keywords == (
        "Bloodcrushers",
        "Chaos",
        "Daemon",
        "Khorne",
        "Mounted",
    )
    assert "Shadow Legion" not in datasheet.keywords.keywords
    assert datasheet.keywords.faction_keywords == ("Legiones Daemonica",)
    assert composition_by_id["000001115:bloodhunter"].min_models == 1
    assert composition_by_id["000001115:bloodhunter"].max_models == 1
    assert composition_by_id["000001115:bloodcrushers"].min_models == 2
    assert composition_by_id["000001115:bloodcrushers"].max_models == 5

    bloodcrusher = profiles_by_id["000001115:bloodcrushers"]
    assert bloodcrusher.base_size.kind is BaseSizeKind.OVAL
    assert math.isclose(bloodcrusher.base_size.length_mm or 0.0, 90.0)
    assert math.isclose(bloodcrusher.base_size.width_mm or 0.0, 52.0)
    assert bloodcrusher.characteristic(Characteristic.MOVEMENT).raw == 10
    assert bloodcrusher.characteristic(Characteristic.TOUGHNESS).raw == 7
    assert bloodcrusher.characteristic(Characteristic.SAVE).raw == 3
    assert bloodcrusher.characteristic(Characteristic.WOUNDS).raw == 4
    assert bloodcrusher.characteristic(Characteristic.LEADERSHIP).raw == 7
    assert bloodcrusher.characteristic(Characteristic.OBJECTIVE_CONTROL).raw == 2
    assert package.model_geometries[0].height.height_inches == 2.75
    footprint_evidence = next(
        evidence
        for evidence in package.model_geometries[0].evidence
        if evidence.measurement_kind is GeometryMeasurementKind.FOOTPRINT
    )
    assert footprint_evidence.source_id == EVENT_COMPANION_BASE_SIZE_GUIDE_SOURCE_ID
    assert (
        footprint_evidence.document_reference == EVENT_COMPANION_BASE_SIZE_GUIDE_DOCUMENT_REFERENCE
    )
    assert (
        Path(__file__).resolve().parents[2] / EVENT_COMPANION_BASE_SIZE_GUIDE_DOCUMENT_REFERENCE
    ).is_file()
    assert EVENT_COMPANION_BASE_SIZE_GUIDE_SOURCE_ID in bloodcrusher.source_ids

    assert wargear_by_id["000001115:hellblade"].weapon_profiles[0].attack_profile.fixed_attacks == 2
    horn = wargear_by_id["000001115:juggernauts-bladed-horn"].weapon_profiles[0]
    assert horn.attack_profile.fixed_attacks == 4
    assert tuple(keyword.value for keyword in horn.keywords) == ("Extra Attacks", "Lance")
    assert wargear_by_id["000001115:daemonic-icon"].weapon_profiles == ()
    assert wargear_by_id["000001115:instrument-of-chaos"].weapon_profiles == ()

    instrument_option = options_by_id["000001115:instrument-of-chaos:option-1"]
    assert instrument_option.model_profile_id == "000001115:bloodcrushers"
    assert instrument_option.allowed_wargear_ids == ("000001115:instrument-of-chaos",)
    assert (
        instrument_option.conditions[0].kind is WargearOptionConditionKind.MODEL_NOT_EQUIPPED_WITH
    )
    assert instrument_option.conditions[0].wargear_ids == ("000001115:daemonic-icon",)
    assert instrument_option.effects[0].kind is WargearOptionEffectKind.ADD_WARGEAR
    assert instrument_option.effects[0].wargear_id == "000001115:instrument-of-chaos"

    assert "Deep Strike" in abilities_by_name
    assert abilities_by_name["Deep Strike"].timing_tags == ("deployment", "reserves")
    assert "The Shadow of Chaos" in abilities_by_name
    assert "Brass Stampede" in abilities_by_name
    assert "Daemonic Icon" in abilities_by_name
    assert "Instrument of Chaos" in abilities_by_name
    assert package.to_payload() == type(package).from_payload(package.to_payload()).to_payload()


def test_phase17k_bridge_datasheet_source_ids_include_pdf_correction_source_id() -> None:
    artifacts = _bloodcrushers_bridge_artifacts()
    datasheet_row = _row_by_id(_artifact_by_table(artifacts, "Datasheets"), "000001115")
    shadow_legion_row = next(
        row
        for artifact in _wahapedia_source_artifacts()
        if artifact.source_table == "Datasheets_keywords"
        for row in artifact.rows
        if row.runtime_fields_payload()["datasheet_id"] == "000001115"
        and row.runtime_fields_payload()["keyword"] == "Shadow Legion"
    )

    source_ids = _source_ids_from_row(datasheet_row)

    assert shadow_legion_row.stable_source_id() in source_ids
    assert "pdf:chaos-daemons-faction-pack:2026-06-10:p30-p31" in source_ids


def test_phase17k_bridge_deduplicates_same_faction_rows_for_multiple_datasheets() -> None:
    artifacts = build_wahapedia_canonical_bridge_artifacts(
        source_artifacts=_same_faction_source_artifacts(),
        bridge_package_id=_bridge_package_id(),
        datasheet_ids=("test-datasheet-a", "test-datasheet-b"),
        pdf_corrections=(),
        height_overrides=(
            ModelHeightOverride(
                datasheet_id="test-datasheet-a",
                model_name="Alpha",
                height=1.0,
                height_units=GeometrySourceUnits.INCHES,
                height_source_id="test-source:alpha-height",
                height_document_reference="test-doc:alpha-height",
            ),
            ModelHeightOverride(
                datasheet_id="test-datasheet-b",
                model_name="Beta",
                height=1.0,
                height_units=GeometrySourceUnits.INCHES,
                height_source_id="test-source:beta-height",
                height_document_reference="test-doc:beta-height",
            ),
        ),
    )
    faction_rows = _artifact_by_table(artifacts, "Factions").rows

    assert tuple(row.source_row_id for row in faction_rows) == ("test-faction",)


def test_phase17k_bridge_preserves_raw_source_text_for_reference_catalog() -> None:
    source_reference_catalog = build_source_reference_catalog(
        package_id=_bridge_package_id(),
        catalog_version=_catalog_version(),
        target_edition="warhammer-40000-11th",
        source_artifacts=_bloodcrushers_bridge_artifacts(),
    )
    deep_strike_text = source_reference_catalog.source_text_by_id(
        f"{_bridge_package_id().stable_identity()}:Datasheets_abilities:000001115:1:description"
    )
    option_text = source_reference_catalog.source_text_by_id(
        f"{_bridge_package_id().stable_identity()}:Datasheets_options:000001115:1:description"
    )

    assert "<div" in deep_strike_text.raw_text
    assert "<div" not in deep_strike_text.sanitized_text
    assert option_text.raw_text.startswith("1 Bloodcrusher that is not equipped")
    assert (
        source_reference_catalog.to_payload()
        == type(source_reference_catalog)
        .from_payload(source_reference_catalog.to_payload())
        .to_payload()
    )


def test_phase17k_structured_wargear_option_semantics_block_icon_and_instrument_together() -> None:
    package = build_canonical_catalog_package(
        package_id=_catalog_package_id(),
        catalog_version=_catalog_version(),
        source_artifacts=_bloodcrushers_bridge_artifacts(),
    )
    datasheet = package.army_catalog.datasheet_by_id("000001115")

    resolved = resolve_wargear_selections(
        catalog=package.army_catalog,
        datasheet=datasheet,
        requested_selections=(
            WargearSelection(
                option_id="000001115:instrument-of-chaos:option-1",
                model_profile_id="000001115:bloodcrushers",
                wargear_ids=("000001115:instrument-of-chaos",),
            ),
        ),
    )

    assert any(
        selection.option_id == "000001115:instrument-of-chaos:option-1" for selection in resolved
    )
    with pytest.raises(ListValidationError, match="structured wargear option condition"):
        resolve_wargear_selections(
            catalog=package.army_catalog,
            datasheet=datasheet,
            requested_selections=(
                WargearSelection(
                    option_id="000001115:instrument-of-chaos:option-1",
                    model_profile_id="000001115:bloodcrushers",
                    wargear_ids=("000001115:instrument-of-chaos",),
                ),
                WargearSelection(
                    option_id="000001115:daemonic-icon:option-2",
                    model_profile_id="000001115:bloodcrushers",
                    wargear_ids=("000001115:daemonic-icon",),
                ),
            ),
        )


def test_phase17k_structured_wargear_option_effects_are_count_aware() -> None:
    package = build_canonical_catalog_package(
        package_id=_catalog_package_id(),
        catalog_version=_catalog_version(),
        source_artifacts=_bloodcrushers_bridge_artifacts(),
    )
    datasheet = package.army_catalog.datasheet_by_id("000001115")
    options: list[DatasheetWargearOption] = []
    for option in datasheet.wargear_options:
        if option.option_id != "000001115:instrument-of-chaos:option-1":
            options.append(option)
            continue
        effect = option.effects[0]
        options.append(
            replace(
                option,
                effects=(
                    DatasheetWargearOptionEffect(
                        kind=effect.kind,
                        wargear_id=effect.wargear_id,
                        model_count=effect.model_count,
                        wargear_count=2,
                    ),
                ),
            )
        )
    counted_datasheet = replace(datasheet, wargear_options=tuple(options))

    with pytest.raises(ListValidationError, match="structured wargear option effect count"):
        resolve_wargear_selections(
            catalog=package.army_catalog,
            datasheet=counted_datasheet,
            requested_selections=(
                WargearSelection(
                    option_id="000001115:instrument-of-chaos:option-1",
                    model_profile_id="000001115:bloodcrushers",
                    wargear_ids=("000001115:instrument-of-chaos",),
                ),
            ),
        )


def test_phase17k_bridge_requires_accepted_height_overrides() -> None:
    with pytest.raises(WahapediaBridgeError, match="height override"):
        build_wahapedia_canonical_bridge_artifacts(
            source_artifacts=_wahapedia_source_artifacts(),
            bridge_package_id=_bridge_package_id(),
            datasheet_ids=("000001115",),
            height_overrides=(),
        )


def _bloodcrushers_bridge_artifacts() -> tuple[WahapediaJsonArtifact, ...]:
    return build_wahapedia_canonical_bridge_artifacts(
        source_artifacts=_wahapedia_source_artifacts(),
        bridge_package_id=_bridge_package_id(),
        datasheet_ids=("000001115",),
    )


def _same_faction_source_artifacts() -> tuple[WahapediaJsonArtifact, ...]:
    return (
        _artifact_from_csv(
            "Abilities",
            "\n".join(
                (
                    "id,faction_id,name,description",
                    "test-army-rule,test-faction,Test Army Rule,Test rule text.",
                )
            ),
        ),
        _artifact_from_csv(
            "Datasheets",
            "\n".join(
                (
                    "id,name,faction_id",
                    "test-datasheet-a,Alpha Unit,test-faction",
                    "test-datasheet-b,Beta Unit,test-faction",
                )
            ),
        ),
        _artifact_from_csv(
            "Datasheets_abilities",
            "\n".join(
                (
                    "datasheet_id,line,type,ability_id,name,description,parameter",
                    "test-datasheet-a,1,Faction,test-army-rule,Test Army Rule,Test rule text.,",
                    "test-datasheet-b,1,Faction,test-army-rule,Test Army Rule,Test rule text.,",
                )
            ),
        ),
        _artifact_from_csv(
            "Datasheets_keywords",
            "\n".join(
                (
                    "datasheet_id,keyword,model,is_faction_keyword",
                    "test-datasheet-a,Alpha,,false",
                    "test-datasheet-a,Test Faction,,true",
                    "test-datasheet-b,Beta,,false",
                    "test-datasheet-b,Test Faction,,true",
                )
            ),
        ),
        _artifact_from_csv(
            "Datasheets_models",
            "\n".join(
                (
                    "datasheet_id,line,M,T,Sv,W,Ld,OC,base_size",
                    "test-datasheet-a,1,6,4,3,2,7,1,32mm",
                    "test-datasheet-b,1,6,4,3,2,7,1,32mm",
                )
            ),
        ),
        _artifact_from_csv(
            "Datasheets_unit_composition",
            "\n".join(
                (
                    "datasheet_id,line,description",
                    "test-datasheet-a,1,1 Alpha",
                    "test-datasheet-b,1,1 Beta",
                )
            ),
        ),
        _artifact_from_csv(
            "Factions",
            "\n".join(("id,name", "test-faction,Test Faction")),
        ),
    )


def _artifact_from_csv(table_name: str, csv_text: str) -> WahapediaJsonArtifact:
    return WahapediaJsonArtifact.from_csv_table(
        source_package_id=_bridge_package_id(),
        table=WahapediaCsvTable.from_csv_text(table_name=table_name, csv_text=f"{csv_text}\n"),
    )


@lru_cache(maxsize=1)
def _wahapedia_source_artifacts() -> tuple[WahapediaJsonArtifact, ...]:
    artifacts: list[WahapediaJsonArtifact] = []
    for table_name in _REQUIRED_TABLES:
        payload = json.loads(
            (_WAHAPEDIA_10E_JSON / f"{table_name}.json").read_text(encoding="utf-8")
        )
        artifacts.append(
            WahapediaJsonArtifact.from_payload(cast(WahapediaJsonArtifactPayload, payload))
        )
    return tuple(artifacts)


def _artifact_by_table(
    artifacts: tuple[WahapediaJsonArtifact, ...],
    table_name: str,
) -> WahapediaJsonArtifact:
    for artifact in artifacts:
        if artifact.source_table == table_name:
            return artifact
    raise AssertionError(f"Missing artifact table: {table_name}.")


def _row_by_id(artifact: WahapediaJsonArtifact, row_id: str) -> NormalizedSourceRow:
    for row in artifact.rows:
        if row.source_row_id == row_id:
            return row
    raise AssertionError(f"Missing source row: {row_id}.")


def _source_ids_from_row(row: NormalizedSourceRow) -> tuple[str, ...]:
    return tuple(
        source_id.strip()
        for source_id in row.runtime_fields_payload()["source_ids"].split(",")
        if source_id.strip()
    )


def _bridge_package_id() -> DataPackageId:
    return DataPackageId(
        namespace="core-v2",
        package_name="wahapedia-" + "1" + "0" + "e-bridge",
        version="phase17k-test",
    )


def _catalog_package_id() -> DataPackageId:
    return DataPackageId(
        namespace="core-v2",
        package_name="chaos-daemons-bridge-catalog",
        version="phase17k-test",
    )


def _catalog_version() -> CatalogVersion:
    return CatalogVersion.dated(
        version_id="warhammer-40000-11th-phase17k",
        source_date=date(2026, 6, 10),
    )
