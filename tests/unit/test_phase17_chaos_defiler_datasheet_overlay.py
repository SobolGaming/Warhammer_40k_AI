from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import cast

import pytest

from warhammer40k_core.core.attributes import Characteristic
from warhammer40k_core.core.datasheet import (
    CatalogAbilitySupport,
    DatasheetAbilityDescriptor,
)
from warhammer40k_core.engine.list_validation import (
    UnitMusterSelection,
)
from warhammer40k_core.engine.unit_factory import UnitFactory, UnitFactoryError, UnitInstance
from warhammer40k_core.engine.wargear_selections import (
    ModelProfileSelection,
    WargearSelection,
)
from warhammer40k_core.rules.catalog_generation import build_canonical_catalog_package
from warhammer40k_core.rules.catalog_package import CanonicalCatalogPackage
from warhammer40k_core.rules.data_package import DataPackageId
from warhammer40k_core.rules.source_overlay import (
    OverlaySourceArtifact,
    SourceOverlayPack,
    apply_source_release_overlays,
)
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    chaos_defiler_datasheet_overlay_2026_06 as defiler_overlay,
)
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    thousand_sons_defiler_datasheet_overlay_2026_07 as july_defiler_overlay,
)
from warhammer40k_core.rules.wahapedia_bridge import (
    build_wahapedia_canonical_bridge_artifacts,
)
from warhammer40k_core.rules.wahapedia_bridge_defaults import CHAOS_DEFILER_HEIGHT_OVERRIDES
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
_EXPECTED_BLANK_KEYWORD_SUPERSEDES = {
    "000001030:blank-keyword:global:true:4079": (
        "chaos-defiler-thousand-sons-remove-empty-keyword"
    ),
    "000004207:blank-keyword:global:true:15727": (
        "chaos-defiler-world-eaters-remove-empty-keyword"
    ),
    "000004208:blank-keyword:global:true:15734": (
        "chaos-defiler-emperors-children-remove-empty-keyword"
    ),
    "000004209:blank-keyword:global:true:15742": ("chaos-defiler-death-guard-remove-empty-keyword"),
}
_EXPECTED_DEFILER_ROWS = {
    defiler_overlay.DEATH_GUARD_DEFILER_DATASHEET_ID: (
        "DG",
        "DEATH GUARD",
        "NURGLE",
        12,
        "000008396",
        "Nurgle's Gift (Aura)",
        "Barrage of Filth",
    ),
    defiler_overlay.WORLD_EATERS_DEFILER_DATASHEET_ID: (
        "WE",
        "WORLD EATERS",
        "KHORNE",
        14,
        "000008428",
        "Blessings of Khorne",
        "Unleash Wrath",
    ),
    defiler_overlay.THOUSAND_SONS_DEFILER_DATASHEET_ID: (
        "TS",
        "THOUSAND SONS",
        "TZEENTCH",
        12,
        "000008424",
        "Cabal of Sorcerers",
        "Destroyer of Futures",
    ),
    defiler_overlay.EMPERORS_CHILDREN_DEFILER_DATASHEET_ID: (
        "EC",
        "EMPEROR'S CHILDREN",
        "SLAANESH",
        12,
        "000009994",
        "Thrill Seekers",
        "Revel in Desecration",
    ),
}
_DEFAULT_WARGEAR_SLUGS = (
    "excruciator-cannon",
    "hades-battle-cannon",
    "heavy-baleflamer",
    "heavy-missile-launcher",
    "shearing-claws",
)


def test_chaos_defiler_overlay_supersedes_blank_keyword_rows() -> None:
    keywords = _artifact_by_table(_overlay_artifacts(), "Datasheets_keywords")

    for source_row_id, expected_operation_id in _EXPECTED_BLANK_KEYWORD_SUPERSEDES.items():
        assert _fields(keywords, source_row_id)["core_v2_superseded_by"] == (expected_operation_id)


def test_july_thousand_sons_defiler_overlay_removes_stale_abilities_and_rule_ir() -> None:
    june_datasheet = _defiler_catalog_package().army_catalog.datasheet_by_id(
        defiler_overlay.THOUSAND_SONS_DEFILER_DATASHEET_ID
    )
    july_datasheet = _july_defiler_catalog_package().army_catalog.datasheet_by_id(
        july_defiler_overlay.THOUSAND_SONS_DEFILER_DATASHEET_ID
    )
    june_by_name = {ability.name: ability for ability in june_datasheet.abilities}
    july_by_name = {ability.name: ability for ability in july_datasheet.abilities}

    assert "Feel No Pain" in june_by_name
    assert "Feel No Pain" not in july_by_name
    assert june_by_name["Destroyer of Futures"].support is CatalogAbilitySupport.GENERIC_RULE_IR
    assert june_by_name["Destroyer of Futures"].rule_ir_payload is not None
    destroyer = july_by_name["Destroyer of Futures"]
    assert destroyer.ability_id == "000001030:destroyer-of-futures"
    assert destroyer.support is CatalogAbilitySupport.UNSUPPORTED
    assert destroyer.rule_ir_payload is None
    assert destroyer.effect_description == (
        "Once per phase, per unit: You can target this unit with the Counteroffensive "
        "stratagem, regardless of any other uses of that stratagem this phase. If you do: "
        "That use is -1 CP. That use does not prevent any uses of that stratagem on other "
        "units this phase."
    )

    abilities = _artifact_by_table(_july_overlay_artifacts(), "Datasheets_abilities")
    assert _fields(abilities, "000001030:2")["core_v2_superseded_by"] == (
        "july-thousand-sons-defiler-remove-feel-no-pain"
    )


def test_july_thousand_sons_defiler_overlay_is_source_id_scoped() -> None:
    june_catalog = _defiler_catalog_package().army_catalog
    july_catalog = _july_defiler_catalog_package().army_catalog

    for datasheet_id in (
        defiler_overlay.DEATH_GUARD_DEFILER_DATASHEET_ID,
        defiler_overlay.WORLD_EATERS_DEFILER_DATASHEET_ID,
        defiler_overlay.EMPERORS_CHILDREN_DEFILER_DATASHEET_ID,
    ):
        june = june_catalog.datasheet_by_id(datasheet_id)
        july = july_catalog.datasheet_by_id(datasheet_id)
        assert tuple(_ability_semantics(ability) for ability in july.abilities) == tuple(
            _ability_semantics(ability) for ability in june.abilities
        )

    june_abilities = _artifact_by_table(_overlay_artifacts(), "Datasheets_abilities")
    july_abilities = _artifact_by_table(_july_overlay_artifacts(), "Datasheets_abilities")
    chaos_space_marines_rows = tuple(
        row
        for row in june_abilities.rows
        if row.runtime_fields_payload().get("datasheet_id")
        == july_defiler_overlay.CHAOS_SPACE_MARINES_DEFILER_DATASHEET_ID
    )
    assert chaos_space_marines_rows
    for row in chaos_space_marines_rows:
        assert _fields(july_abilities, row.source_row_id) == row.runtime_fields_payload()

    pack = july_defiler_overlay.overlay_pack()
    restored = SourceOverlayPack.from_payload(pack.to_payload())
    assert restored == pack
    assert pack.package_hash() == "9156857ed8457374a8da524a138222fea2e3e451b79fcc5394fc0ed142bd8d97"
    assert july_defiler_overlay.source_package_identity_payload() == {
        "source_package_id": (
            "data-package:gw:thousand-sons-defiler-datasheet-overlay:11th-2026-07-22"
        ),
        "source_payload_checksum_sha256": pack.package_hash(),
        "source_date": "2026-07-22",
        "source_edition": "warhammer-40000-11th",
    }


def test_chaos_defiler_overlay_builds_catalog_and_runtime_units() -> None:
    package = _defiler_catalog_package()

    for datasheet_id, expected in _EXPECTED_DEFILER_ROWS.items():
        (
            faction_id,
            faction_keyword,
            god_keyword,
            movement,
            army_rule_id,
            army_rule_name,
            ability,
        ) = expected
        datasheet = package.army_catalog.datasheet_by_id(datasheet_id)
        model_profile = datasheet.model_profile_by_id(f"{datasheet_id}:defiler")
        faction = package.army_catalog.faction_by_id(faction_id)
        default_wargear_ids = {
            wargear_id
            for option in datasheet.wargear_options
            for wargear_id in option.default_wargear_ids
        }

        assert datasheet.name == "Defiler"
        assert datasheet.keywords.faction_keywords == (faction_keyword,)
        assert god_keyword in datasheet.keywords.keywords
        assert model_profile.characteristic(Characteristic.MOVEMENT).raw == movement
        assert faction.army_rule_ids == (army_rule_id,)
        assert any(
            rule.rule_id == army_rule_id and rule.name == army_rule_name
            for rule in package.army_catalog.army_rules
        )
        assert ability in {descriptor.name for descriptor in datasheet.abilities}
        assert default_wargear_ids == {f"{datasheet_id}:{slug}" for slug in _DEFAULT_WARGEAR_SLUGS}

        unit = _instantiate_defiler(package=package, datasheet_id=datasheet_id)

        assert unit.datasheet_id == datasheet_id
        assert len(unit.own_models) == 1
        assert set(unit.own_models[0].wargear_ids) == default_wargear_ids
        assert UnitInstance.from_payload(unit.to_payload()) == unit

    thousand_sons_defiler = package.army_catalog.datasheet_by_id(
        defiler_overlay.THOUSAND_SONS_DEFILER_DATASHEET_ID
    )
    assert "Cabal of Sorcerers" not in {
        descriptor.name for descriptor in thousand_sons_defiler.abilities
    }


def test_chaos_defiler_runtime_supports_single_electroscourge_replacement() -> None:
    package = _defiler_catalog_package()
    datasheet_id = defiler_overlay.DEATH_GUARD_DEFILER_DATASHEET_ID
    unit = _instantiate_defiler(
        package=package,
        datasheet_id=datasheet_id,
        wargear_selections=(
            WargearSelection(
                option_id=f"{datasheet_id}:heavy-baleflamer-electroscourge:option-3",
                model_profile_id=f"{datasheet_id}:defiler",
                wargear_ids=(f"{datasheet_id}:electroscourge",),
            ),
        ),
    )

    model_wargear = set(unit.own_models[0].wargear_ids)

    assert f"{datasheet_id}:electroscourge" in model_wargear
    assert f"{datasheet_id}:heavy-baleflamer" not in model_wargear
    assert f"{datasheet_id}:heavy-missile-launcher" in model_wargear


def test_chaos_defiler_runtime_rejects_duplicate_electroscourge_replacement() -> None:
    package = _defiler_catalog_package()
    datasheet_id = defiler_overlay.DEATH_GUARD_DEFILER_DATASHEET_ID

    with pytest.raises(UnitFactoryError, match="UnitMusterSelection is invalid"):
        _instantiate_defiler(
            package=package,
            datasheet_id=datasheet_id,
            wargear_selections=(
                WargearSelection(
                    option_id=f"{datasheet_id}:heavy-baleflamer-electroscourge:option-3",
                    model_profile_id=f"{datasheet_id}:defiler",
                    wargear_ids=(f"{datasheet_id}:electroscourge",),
                ),
                WargearSelection(
                    option_id=f"{datasheet_id}:heavy-missile-launcher-electroscourge:option-4",
                    model_profile_id=f"{datasheet_id}:defiler",
                    wargear_ids=(f"{datasheet_id}:electroscourge",),
                ),
            ),
        )


@lru_cache(maxsize=1)
def _defiler_catalog_package() -> CanonicalCatalogPackage:
    bridge_artifacts = build_wahapedia_canonical_bridge_artifacts(
        source_artifacts=_overlay_artifacts(),
        bridge_package_id=DataPackageId(
            namespace="core-v2",
            package_name="chaos-defiler-11e-bridge-test",
            version="2026-06-10",
        ),
        datasheet_ids=defiler_overlay.DEFILER_DATASHEET_IDS,
        height_overrides=CHAOS_DEFILER_HEIGHT_OVERRIDES,
    )
    return build_canonical_catalog_package(
        package_id=DataPackageId(
            namespace="core-v2",
            package_name="chaos-defiler-11e-catalog-test",
            version="2026-06-10",
        ),
        catalog_version=defiler_overlay.CATALOG_VERSION,
        source_artifacts=bridge_artifacts,
    )


@lru_cache(maxsize=1)
def _july_defiler_catalog_package() -> CanonicalCatalogPackage:
    bridge_artifacts = build_wahapedia_canonical_bridge_artifacts(
        source_artifacts=_july_overlay_artifacts(),
        bridge_package_id=DataPackageId(
            namespace="core-v2",
            package_name="july-thousand-sons-defiler-11e-bridge-test",
            version="2026-07-22",
        ),
        datasheet_ids=july_defiler_overlay.ALIGNED_DEFILER_DATASHEET_IDS,
        height_overrides=CHAOS_DEFILER_HEIGHT_OVERRIDES,
    )
    return build_canonical_catalog_package(
        package_id=DataPackageId(
            namespace="core-v2",
            package_name="july-thousand-sons-defiler-11e-catalog-test",
            version="2026-07-22",
        ),
        catalog_version=july_defiler_overlay.CATALOG_VERSION,
        source_artifacts=bridge_artifacts,
    )


def _instantiate_defiler(
    *,
    package: CanonicalCatalogPackage,
    datasheet_id: str,
    wargear_selections: tuple[WargearSelection, ...] = (),
) -> UnitInstance:
    datasheet = package.army_catalog.datasheet_by_id(datasheet_id)
    return UnitFactory(
        catalog=package.army_catalog,
        model_geometries=package.model_geometries,
    ).instantiate_unit(
        army_id="chaos-defiler-test-army",
        selection=UnitMusterSelection(
            unit_selection_id=f"defiler-{datasheet_id}",
            datasheet_id=datasheet_id,
            model_profile_selections=(
                ModelProfileSelection(
                    model_profile_id=f"{datasheet_id}:defiler",
                    model_count=1,
                ),
            ),
            wargear_selections=wargear_selections,
        ),
        datasheet=datasheet,
    )


@lru_cache(maxsize=1)
def _overlay_artifacts() -> tuple[OverlaySourceArtifact, ...]:
    return apply_source_release_overlays(
        source_artifacts=_wahapedia_source_artifacts(),
        release_manifest=defiler_overlay.source_release_manifest(),
        overlay_packs=(defiler_overlay.overlay_pack(),),
    )


@lru_cache(maxsize=1)
def _july_overlay_artifacts() -> tuple[OverlaySourceArtifact, ...]:
    return apply_source_release_overlays(
        source_artifacts=_wahapedia_source_artifacts(),
        release_manifest=july_defiler_overlay.source_release_manifest(),
        overlay_packs=(july_defiler_overlay.overlay_pack(),),
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


def _ability_semantics(ability: DatasheetAbilityDescriptor) -> tuple[object, ...]:
    payload = ability.to_payload()
    return tuple((key, value) for key, value in payload.items() if key not in {"source_id"})
