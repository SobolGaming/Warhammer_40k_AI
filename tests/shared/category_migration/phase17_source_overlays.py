from __future__ import annotations

import hashlib
import json
from datetime import date
from pathlib import Path
from typing import cast

import pytest
from tools.apply_source_overlays import apply_source_overlays
from tools.fetch_official_sources import load_official_source_manifest

from warhammer40k_core.engine.catalog_command_point_support import (
    CATALOG_IR_STRATAGEM_COST_MODIFIER_CONSUMER_ID,
    command_point_consumer_ids_for_clause,
)
from warhammer40k_core.engine.catalog_rule_consumption import catalog_rule_clauses_from_record
from warhammer40k_core.engine.faction_content.manifest import RuntimeContentModuleFamily
from warhammer40k_core.engine.faction_content.warhammer_40000_11th import generated_manifest
from warhammer40k_core.engine.faction_content.warhammer_40000_11th.chaos_daemons import (
    july_2026 as chaos_daemons_july,
)
from warhammer40k_core.engine.faction_content.warhammer_40000_11th.chaos_daemons import (
    july_2026_updates as chaos_daemons_july_updates,
)
from warhammer40k_core.engine.faction_content.warhammer_40000_11th.chaos_daemons import (
    manifest as chaos_daemons_june_manifest,
)
from warhammer40k_core.engine.faction_content.warhammer_40000_11th.chaos_space_marines import (
    army_rule as chaos_space_marines_army_rule,
)
from warhammer40k_core.engine.faction_content.warhammer_40000_11th.emperors_children import (
    july_2026 as emperors_children_july,
)
from warhammer40k_core.engine.faction_content.warhammer_40000_11th.emperors_children import (
    manifest as emperors_children_june_manifest,
)
from warhammer40k_core.engine.faction_content.warhammer_40000_11th.thousand_sons import (
    july_2026 as thousand_sons_july,
)
from warhammer40k_core.engine.faction_content.warhammer_40000_11th.thousand_sons import (
    manifest as thousand_sons_june_manifest,
)
from warhammer40k_core.engine.stratagem_phase_use_exceptions import stratagem_phase_use_exception
from warhammer40k_core.rules.data_package import CatalogVersion, DataPackageId
from warhammer40k_core.rules.external_reference_lookup import (
    THIRTY_NINE_K_PRO_TARGET_EDITION,
    ExternalReferenceDiscoveryMethod,
    ExternalReferenceKind,
    ExternalReferenceLookupError,
    build_thirty_nine_k_pro_reference_lookup,
)
from warhammer40k_core.rules.rule_ir import RuleEffectKind, parameter_payload
from warhammer40k_core.rules.source_overlay import (
    OverlaySourceArtifact,
    OverlaySourceArtifactPayload,
    SourceOverlayError,
    SourceOverlayOperation,
    SourceOverlayOperationKind,
    SourceOverlayPack,
    SourceOverlayPackPayload,
    SourceReleaseManifest,
    SourceReleaseManifestPayload,
    apply_source_release_overlays,
    build_source_release_overlay_report,
)
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    faction_coverage_2026_27,
    faction_execution_2026_27,
    faction_source_promotion_2026_07,
    faction_subrules_2026_27,
    july_faction_packs_2026_07,
)
from warhammer40k_core.rules.source_patch import source_row_hash
from warhammer40k_core.rules.source_reference_generation import (
    SourceReferenceCatalog,
    SourceReferenceCatalogPayload,
    build_source_reference_catalog,
)
from warhammer40k_core.rules.wahapedia_schema import (
    NormalizedSourceRow,
    WahapediaCsvTable,
    WahapediaJsonArtifact,
)


def _official_source_identities(path: Path) -> dict[str, tuple[str, str]]:
    identities: dict[str, tuple[str, str]] = {}
    for entry in load_official_source_manifest(path):
        if entry.local_cache_path is None:
            raise AssertionError("Faction-pack manifest entry must declare a local cache path.")
        identities[entry.package_id] = (entry.sha256, entry.local_cache_path)
    return identities


def _source_row_ids(path: Path) -> set[str]:
    raw_payload = json.loads(path.read_text(encoding="utf-8"))
    if type(raw_payload) is not dict:
        raise AssertionError("Source artifact must contain a JSON object.")
    rows = cast(dict[str, object], raw_payload)["rows"]
    if type(rows) is not list:
        raise AssertionError("Source artifact rows must be a list.")
    source_row_ids: set[str] = set()
    for raw_row in cast(list[object], rows):
        if type(raw_row) is not dict:
            raise AssertionError("Source artifact row must be a JSON object.")
        source_row_id = cast(dict[str, object], raw_row)["source_row_id"]
        if type(source_row_id) is not str:
            raise AssertionError("Source artifact row ID must be a string.")
        source_row_ids.add(source_row_id)
    return source_row_ids


def _updated_row_after_first_operation(
    artifact: WahapediaJsonArtifact,
    *,
    package_hash_placeholder: bool,
) -> NormalizedSourceRow:
    package = _overlay_pack(
        operations=(
            _operation(
                op_id="update-angels-fury",
                order_index=1,
                kind=SourceOverlayOperationKind.UPDATE_ROW,
                source_row_id="ability-1:SM",
                expected_preimage_hash=source_row_hash(artifact.rows[0]),
                fields=(("description", "<p>Roll D6 within 12 inches.</p>"),),
            ),
        )
    )
    if package_hash_placeholder:
        assert package.package_hash()
    return apply_source_release_overlays(
        source_artifacts=(artifact,),
        release_manifest=_release_manifest(overlay_package_ids=(package.package_id,)),
        overlay_packs=(package,),
    )[0].rows[0]


def _operation(
    *,
    op_id: str,
    order_index: int,
    kind: SourceOverlayOperationKind,
    source_row_id: str,
    expected_preimage_hash: str | None,
    fields: tuple[tuple[str, str], ...],
) -> SourceOverlayOperation:
    return SourceOverlayOperation(
        op_id=op_id,
        order_index=order_index,
        operation_kind=kind,
        target_edition="warhammer-40000-11th",
        source_table="Abilities",
        source_row_id=source_row_id,
        source_reference="gw-11e-transition-update:p1",
        effective_date="2026-06-01",
        reason="Apply 11e transition update.",
        expected_preimage_hash=expected_preimage_hash,
        fields=fields,
    )


def _overlay_pack(
    *,
    operations: tuple[SourceOverlayOperation, ...],
    package_id: DataPackageId | None = None,
) -> SourceOverlayPack:
    return SourceOverlayPack(
        package_id=package_id if package_id is not None else _overlay_package_id(),
        catalog_version=_catalog_version(),
        base_source_package_id=_source_package_id(),
        target_edition="warhammer-40000-11th",
        effective_date="2026-06-01",
        operations=operations,
    )


def _release_manifest(
    *,
    overlay_package_ids: tuple[DataPackageId, ...],
) -> SourceReleaseManifest:
    return SourceReleaseManifest(
        release_id="core-11-from-wahapedia-bridge-test",
        catalog_version=_catalog_version(),
        base_source_package_id=_source_package_id(),
        base_source_edition=_previous_source_edition(),
        target_edition="warhammer-40000-11th",
        overlay_package_ids=overlay_package_ids,
    )


def _abilities_artifact() -> WahapediaJsonArtifact:
    return WahapediaJsonArtifact.from_csv_table(
        source_package_id=_source_package_id(),
        table=WahapediaCsvTable.from_csv_text(
            table_name="Abilities",
            csv_text='id,faction_id,name,description\nability-1,SM,Angels Fury,"Roll D3."\n',
        ),
    )


def _row_by_id(artifact: OverlaySourceArtifact, source_row_id: str) -> NormalizedSourceRow:
    for row in artifact.rows:
        if row.source_row_id == source_row_id:
            return row
    raise AssertionError(f"Missing row {source_row_id}.")


def _source_package_id() -> DataPackageId:
    return DataPackageId(
        namespace="wahapedia",
        package_name="source-mirror",
        version="bridge-2026-06-01",
    )


def _overlay_package_id() -> DataPackageId:
    return DataPackageId(
        namespace="core-v2",
        package_name="core-11-source-overlay",
        version="2026-06-01",
    )


def _reference_package_id() -> DataPackageId:
    return DataPackageId(
        namespace="core-v2",
        package_name="core-11-source-reference",
        version="2026-06-01",
    )


def _catalog_version() -> CatalogVersion:
    return CatalogVersion.dated(
        version_id="core-11-from-wahapedia-bridge-test",
        source_date=date(2026, 6, 1),
    )


def _previous_source_edition() -> str:
    return "warhammer-40000-" + "1" + "0th"


__all__: list[str] = []
__all__ += ["CATALOG_IR_STRATAGEM_COST_MODIFIER_CONSUMER_ID", "CatalogVersion", "DataPackageId"]
__all__ += ["ExternalReferenceDiscoveryMethod", "ExternalReferenceKind"]
__all__ += ["ExternalReferenceLookupError", "NormalizedSourceRow", "OverlaySourceArtifact"]
__all__ += ["OverlaySourceArtifactPayload", "Path", "RuleEffectKind"]
__all__ += ["RuntimeContentModuleFamily", "SourceOverlayError", "SourceOverlayOperation"]
__all__ += ["SourceOverlayOperationKind", "SourceOverlayPack", "SourceOverlayPackPayload"]
__all__ += ["SourceReferenceCatalog", "SourceReferenceCatalogPayload", "SourceReleaseManifest"]
__all__ += ["THIRTY_NINE_K_PRO_TARGET_EDITION", "SourceReleaseManifestPayload"]
__all__ += ["WahapediaCsvTable", "WahapediaJsonArtifact", "_abilities_artifact"]
__all__ += ["_catalog_version", "_official_source_identities", "_operation", "_overlay_pack"]
__all__ += ["_overlay_package_id", "_previous_source_edition", "_reference_package_id"]
__all__ += ["_release_manifest", "_row_by_id", "_source_package_id", "_source_row_ids"]
__all__ += ["_updated_row_after_first_operation", "apply_source_overlays"]
__all__ += ["apply_source_release_overlays", "build_source_reference_catalog"]
__all__ += ["build_source_release_overlay_report", "build_thirty_nine_k_pro_reference_lookup"]
__all__ += ["cast", "catalog_rule_clauses_from_record", "chaos_daemons_july"]
__all__ += ["chaos_daemons_july_updates", "chaos_daemons_june_manifest"]
__all__ += ["chaos_space_marines_army_rule", "command_point_consumer_ids_for_clause", "date"]
__all__ += ["emperors_children_july", "emperors_children_june_manifest"]
__all__ += ["faction_coverage_2026_27", "faction_execution_2026_27"]
__all__ += ["faction_source_promotion_2026_07", "faction_subrules_2026_27", "generated_manifest"]
__all__ += ["hashlib", "json", "july_faction_packs_2026_07", "load_official_source_manifest"]
__all__ += ["parameter_payload", "pytest", "source_row_hash", "stratagem_phase_use_exception"]
__all__ += ["thousand_sons_july", "thousand_sons_june_manifest"]
