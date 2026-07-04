from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import cast

from warhammer40k_core.core.model_geometry_catalog import GeometrySourceUnits
from warhammer40k_core.rules.data_package import DataPackageId
from warhammer40k_core.rules.source_overlay import (
    OverlaySourceArtifact,
    apply_source_release_overlays,
)
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    emperors_children_datasheet_overlay_2026_06 as ec_overlay,
)
from warhammer40k_core.rules.wahapedia_bridge import (
    ModelHeightOverride,
    build_wahapedia_canonical_bridge_artifacts,
)
from warhammer40k_core.rules.wahapedia_schema import (
    NormalizedSourceRow,
    WahapediaJsonArtifact,
    WahapediaJsonArtifactPayload,
)

_WAHAPEDIA_10E_JSON = (
    Path(__file__).resolve().parents[2]
    / "data"
    / "source_snapshots"
    / "wahapedia"
    / ("".join(("1", "0", "th")) + "-edition")
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
_EC_DATASHEET_IDS = (
    "000004077",
    "000004079",
    "000004080",
    "000004081",
    "000004082",
    "000004089",
    "000004090",
    "000004092",
    "000004093",
)
_BRIDGE_SUPPORTED_EC_DATASHEET_IDS = (
    "000004077",
    "000004089",
    "000004090",
    "000004092",
)


def test_emperors_children_datasheet_overlay_updates_source_rows() -> None:
    artifacts = _overlay_artifacts()
    abilities = _artifact_by_table(artifacts, "Datasheets_abilities")
    models = _artifact_by_table(artifacts, "Datasheets_models")
    wargear = _artifact_by_table(artifacts, "Datasheets_wargear")
    keywords = _artifact_by_table(artifacts, "Datasheets_keywords")

    assert _fields(abilities, "000004090:3")["description"] == (
        ec_overlay.SCUTTLING_HORRORS_DESCRIPTION
    )
    assert _fields(abilities, "000004081:3")["description"] == (
        ec_overlay.LETHAL_OBSESSION_DESCRIPTION
    )
    assert _fields(abilities, "000004077:6")["description"] == (ec_overlay.SERPENTINE_DESCRIPTION)
    assert _fields(models, "000004092:1")["M"] == '12"'
    assert _fields(models, "000004092:1")["Sv"] == "3+"
    assert _fields(models, "000004092:1")["OC"] == "-"
    assert _fields(wargear, "000004089:2:1:8694")["A"] == "4"
    assert _fields(wargear, "000004079:9:1:8650")["S"] == "5"
    assert _fields(wargear, "000004080:5:1:8656")["S"] == "5"

    aircraft = _fields(keywords, "000004092:Aircraft:global:false:14821")
    land_raider_frame = _fields(keywords, "000004082:Frame:global:false:212")
    rhino_frame = _fields(keywords, "000004093:Frame:global:false:222")

    assert aircraft["core_v2_superseded_by"] == "ec-heldrake-remove-aircraft"
    assert land_raider_frame["keyword"] == "Frame"
    assert rhino_frame["keyword"] == "Frame"


def test_emperors_children_overlay_feeds_active_bridge_rows() -> None:
    bridge_artifacts = build_wahapedia_canonical_bridge_artifacts(
        source_artifacts=_overlay_artifacts(),
        bridge_package_id=DataPackageId(
            namespace="core-v2",
            package_name="emperors-children-11e-bridge-test",
            version="2026-06-10",
        ),
        datasheet_ids=_BRIDGE_SUPPORTED_EC_DATASHEET_IDS,
        height_overrides=_ec_height_overrides(),
    )
    datasheets = _artifact_by_table(bridge_artifacts, "Datasheets")
    abilities = _artifact_by_table(bridge_artifacts, "Datasheets_abilities")
    models = _artifact_by_table(bridge_artifacts, "Datasheets_models")
    wargear = _artifact_by_table(bridge_artifacts, "Datasheets_wargear")
    heldrake_keywords = _keyword_set(_fields(datasheets, "000004092")["keywords"])

    assert "Aircraft" not in heldrake_keywords
    assert _model_fields(models, datasheet_id="000004092", name="Heldrake")["m"] == '12"'
    assert _model_fields(models, datasheet_id="000004092", name="Heldrake")["sv"] == "3+"
    assert _model_fields(models, datasheet_id="000004092", name="Heldrake")["oc"] == "-"
    assert _wargear_fields(wargear, datasheet_id="000004089", name="Blissblade")["a"] == "4"
    assert (
        _ability_fields(abilities, datasheet_id="000004090", name="Scuttling Horrors")[
            "description"
        ]
        == ec_overlay.SCUTTLING_HORRORS_DESCRIPTION
    )
    assert (
        _ability_fields(abilities, datasheet_id="000004077", name="Serpentine")["description"]
        == ec_overlay.SERPENTINE_DESCRIPTION
    )


@lru_cache(maxsize=1)
def _overlay_artifacts() -> tuple[OverlaySourceArtifact, ...]:
    return apply_source_release_overlays(
        source_artifacts=_wahapedia_source_artifacts(),
        release_manifest=ec_overlay.source_release_manifest(),
        overlay_packs=(ec_overlay.overlay_pack(),),
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
    artifacts: tuple[WahapediaJsonArtifact | OverlaySourceArtifact, ...],
    table_name: str,
) -> WahapediaJsonArtifact | OverlaySourceArtifact:
    for artifact in artifacts:
        if artifact.source_table == table_name:
            return artifact
    raise AssertionError(f"Missing artifact table: {table_name}.")


def _fields(
    artifact: WahapediaJsonArtifact | OverlaySourceArtifact,
    row_id: str,
) -> dict[str, str]:
    return _row_by_id(artifact, row_id).runtime_fields_payload()


def _row_by_id(
    artifact: WahapediaJsonArtifact | OverlaySourceArtifact,
    row_id: str,
) -> NormalizedSourceRow:
    for row in artifact.rows:
        if row.source_row_id == row_id:
            return row
    raise AssertionError(f"Missing source row: {row_id}.")


def _model_fields(
    artifact: WahapediaJsonArtifact | OverlaySourceArtifact,
    *,
    datasheet_id: str,
    name: str,
) -> dict[str, str]:
    return _row_fields_by_values(artifact, {"datasheet_id": datasheet_id, "name": name})


def _wargear_fields(
    artifact: WahapediaJsonArtifact | OverlaySourceArtifact,
    *,
    datasheet_id: str,
    name: str,
) -> dict[str, str]:
    return _row_fields_by_values(artifact, {"datasheet_id": datasheet_id, "name": name})


def _ability_fields(
    artifact: WahapediaJsonArtifact | OverlaySourceArtifact,
    *,
    datasheet_id: str,
    name: str,
) -> dict[str, str]:
    return _row_fields_by_values(artifact, {"datasheet_id": datasheet_id, "name": name})


def _row_fields_by_values(
    artifact: WahapediaJsonArtifact | OverlaySourceArtifact,
    expected: dict[str, str],
) -> dict[str, str]:
    for row in artifact.rows:
        fields = row.runtime_fields_payload()
        if all(fields.get(key) == value for key, value in expected.items()):
            return fields
    raise AssertionError(f"Missing row matching: {expected}.")


def _keyword_set(value: str) -> set[str]:
    return {keyword.strip() for keyword in value.split(",") if keyword.strip()}


def _ec_height_overrides() -> tuple[ModelHeightOverride, ...]:
    return (
        _height_override("000004077", "Fulgrim - EPIC HERO", 5.5),
        _height_override("000004079", "Obsessionist", 1.75),
        _height_override("000004079", "Tormentors", 1.75),
        _height_override("000004080", "Obsessionist", 1.75),
        _height_override("000004080", "Infractors", 1.75),
        _height_override("000004081", "Terminator Champion", 2.0),
        _height_override("000004081", "Chaos Terminators", 2.0),
        _height_override("000004082", "Chaos Land Raider", 3.0),
        _height_override("000004089", "Flawless Blades", 2.0),
        _height_override("000004090", "Chaos Spawn", 2.25),
        _height_override("000004092", "Heldrake", 6.0),
        _height_override("000004093", "Chaos Rhino", 2.5),
    )


def _height_override(datasheet_id: str, model_name: str, height: float) -> ModelHeightOverride:
    return ModelHeightOverride(
        datasheet_id=datasheet_id,
        model_name=model_name,
        height=height,
        height_units=GeometrySourceUnits.INCHES,
        height_source_id=f"geometry-review:emperors-children:{datasheet_id}:height",
        height_document_reference="Emperor's Children datasheet overlay bridge regression fixture",
    )
