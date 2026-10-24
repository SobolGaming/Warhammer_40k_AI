"""Canonical fixtures and full-source reference for the selected-source index."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import cast

import pytest
from tests.shared.repository_root import REPOSITORY_ROOT
from tests.support.wahapedia_source_fixtures import unit_resource_wargear_source_artifacts
from tools.ability_support_sources import (
    REQUIRED_TABLES,
    ability_support_index_inputs,
    load_ability_support_sources,
)
from tools.generate_ability_support_matrix import (
    DEFAULT_SOURCE_JSON_DIR,
    _ability_support_catalog_package,  # pyright: ignore[reportPrivateUsage]
)

from warhammer40k_core.engine.list_validation import UnitMusterSelection
from warhammer40k_core.engine.unit_factory import UnitFactory, UnitInstance
from warhammer40k_core.engine.wargear_selections import ModelProfileSelection
from warhammer40k_core.rules.catalog_package import CanonicalCatalogPackage
from warhammer40k_core.rules.selected_source_index import (
    build_selected_source_index,
    load_selected_source_rows,
)
from warhammer40k_core.rules.wahapedia_bridge_rows import SelectedSourceRows
from warhammer40k_core.rules.wahapedia_schema import (
    WahapediaJsonArtifact,
    WahapediaJsonArtifactPayload,
)

# Representative selections, not certified legal 2000-point rosters.
SELECTED_ARMIES = (
    (
        "000004080",
        "000004079",
        "000004078",
        "000004083",
        "000004084",
        "000004088",
        "000004089",
        "000004081",
        "000004080",
        "000004080",
        "000004079",
        "000004088",
    ),
    (
        "000000592",
        "000000596",
        "000000598",
        "000000600",
        "000000601",
        "000000611",
        "000000612",
        "000002759",
        "000000592",
        "000000596",
        "000000598",
        "000000600",
    ),
)
MIXED_SOURCE_CONTROLS = ("000000968", "000001029", "000002639", "000004091", "000001114")
SELECTED_SLOTS = (*SELECTED_ARMIES[0], *SELECTED_ARMIES[1], *MIXED_SOURCE_CONTROLS)
SELECTED_IDS = tuple(sorted(set(SELECTED_SLOTS)))
POSITIVE_SLOTS = tuple(value for value in SELECTED_SLOTS if value != "000004081")
SMALL_DATASHEET_ID = "test-aspect-warriors"


@dataclass(frozen=True)
class SmallSourceIndex:
    directory: Path
    source: Path

    def artifacts(self) -> tuple[WahapediaJsonArtifact, ...]:
        payloads = cast(list[WahapediaJsonArtifactPayload], json.loads(self.source.read_bytes()))
        return tuple(WahapediaJsonArtifact.from_payload(payload) for payload in payloads)

    def build(self, directory: Path) -> None:
        build_selected_source_index(
            directory, input_files=(self.source,), load_sources=self.artifacts
        )

    def load(self, ids: tuple[str, ...] = (SMALL_DATASHEET_ID,)) -> SelectedSourceRows:
        return load_selected_source_rows(
            self.directory, input_files=(self.source,), datasheet_ids=ids
        )


@pytest.fixture
def small_selected_source_index(tmp_path: Path) -> SmallSourceIndex:
    # Reuse an existing canonical source fixture. Missing child tables are empty;
    # this adds no invented units and does not stub any source/index operation.
    artifacts = list(unit_resource_wargear_source_artifacts())
    tables = {artifact.source_table for artifact in artifacts}
    artifacts.extend(
        WahapediaJsonArtifact(
            source_package_id=artifacts[0].source_package_id,
            source_table=table,
            source_checksum_sha256=hashlib.sha256(b"").hexdigest(),
            rows=(),
        )
        for table in REQUIRED_TABLES
        if table not in tables
    )
    source = tmp_path / "source.json"
    source.write_text(
        json.dumps([artifact.to_payload() for artifact in artifacts]), encoding="utf8"
    )
    case = SmallSourceIndex(tmp_path / "index", source)
    case.build(case.directory)
    return case


@dataclass(frozen=True)
class RealSourceIndex:
    directory: Path
    reference: CanonicalCatalogPackage

    def load(self, ids: tuple[str, ...] = SELECTED_IDS) -> CanonicalCatalogPackage:
        return _ability_support_catalog_package(datasheet_ids=ids, source_index_dir=self.directory)


@pytest.fixture(scope="module")
def real_selected_source_index(
    tmp_path_factory: pytest.TempPathFactory, selected_army_source_index: Path | None
) -> RealSourceIndex:
    # The reference always executes the unchanged full provider. A supplied index
    # must already be valid; the tests never silently regenerate it on failure.
    reference = _ability_support_catalog_package(datasheet_ids=SELECTED_IDS)
    directory = selected_army_source_index
    if directory is None:
        directory = tmp_path_factory.mktemp("selected-source") / "index"
        source = REPOSITORY_ROOT / DEFAULT_SOURCE_JSON_DIR
        build_selected_source_index(
            directory,
            input_files=ability_support_index_inputs(source),
            load_sources=lambda: load_ability_support_sources(source),
        )
    return RealSourceIndex(directory, reference)


def selected_units(
    package: CanonicalCatalogPackage, ids: tuple[str, ...] = POSITIVE_SLOTS
) -> tuple[UnitInstance, ...]:
    factory = UnitFactory(catalog=package.army_catalog, model_geometries=package.model_geometries)
    return tuple(
        factory.instantiate_unit(
            army_id="selected-source-test",
            datasheet=package.army_catalog.datasheet_by_id(datasheet_id),
            selection=UnitMusterSelection(
                unit_selection_id=f"unit-{index}",
                datasheet_id=datasheet_id,
                model_profile_selections=tuple(
                    ModelProfileSelection(entry.model_profile_id, entry.min_models)
                    for entry in package.army_catalog.datasheet_by_id(datasheet_id).composition
                ),
            ),
        )
        for index, datasheet_id in enumerate(ids)
    )
