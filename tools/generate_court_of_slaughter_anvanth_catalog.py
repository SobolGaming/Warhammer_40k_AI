from __future__ import annotations

import argparse
from dataclasses import replace
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING, cast

if TYPE_CHECKING or __package__:
    from tools.generate_ability_support_matrix import (
        _ability_support_catalog_package,  # pyright: ignore[reportPrivateUsage]
    )
else:
    from generate_ability_support_matrix import (  # pyright: ignore[reportMissingImports]
        _ability_support_catalog_package,  # pyright: ignore[reportPrivateUsage]
    )
from warhammer40k_core.core.army_catalog import ArmyCatalog, ArmyCatalogPayload
from warhammer40k_core.core.datasheet import DatasheetDefinition
from warhammer40k_core.core.detachment import (
    DetachmentDefinition,
    EnhancementDefinition,
    EnhancementSubtype,
    StratagemDefinition,
)
from warhammer40k_core.core.faction import FactionDefinition
from warhammer40k_core.core.model_geometry_catalog import (
    ModelGeometryCatalogRecord,
    ModelGeometryCatalogRecordPayload,
)
from warhammer40k_core.engine.army_points import catalog_with_mfm_points
from warhammer40k_core.rules.catalog_package import CanonicalCatalogPackage
from warhammer40k_core.rules.data_package import CatalogVersion, DataPackageId
from warhammer40k_core.rules.mfm_source import MfmEnhancementRecord, source_label_slug
from warhammer40k_core.rules.rule_ir import (
    RuleClause,
    RuleIR,
    RuleIRPayload,
    RuleParseDiagnostic,
)
from warhammer40k_core.rules.source_catalog import SourceArtifactHash
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    court_of_slaughter_anvanth_2026_08 as roster_catalog,
)
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    faction_detachments_2026_27,
    faction_subrules_2026_27,
    mfm_2026_07,
)

ROOT = Path(__file__).resolve().parents[1]
OUTPUT_PATH = (
    ROOT
    / "src"
    / "warhammer40k_core"
    / "rules"
    / "source_packages"
    / "warhammer_40000_11th"
    / "court_of_slaughter_anvanth_2026_08"
    / roster_catalog.ARTIFACT_PATH
)
PACKAGE_ID = DataPackageId(
    namespace="core-v2",
    package_name="court-of-slaughter-anvanth",
    version="2026-08",
)
BRIDGE_PACKAGE_ID = DataPackageId(
    namespace="core-v2",
    package_name="court-of-slaughter-anvanth-bridge",
    version="2026-08",
)
REVIEWED_SOURCE_PACKAGE_ID = DataPackageId(
    namespace="core-v2",
    package_name="court-of-slaughter-anvanth-current-source-review",
    version="2026-08",
)
CATALOG_VERSION = CatalogVersion.dated(
    version_id="warhammer-40000-11th-court-of-slaughter-anvanth-2026-08",
    source_date=date(2026, 8, 24),
)
SELECTED_FACTION_IDS = frozenset(roster_catalog.EXPECTED_FACTION_IDS)
SELECTED_DETACHMENT_IDS = frozenset(roster_catalog.EXPECTED_DETACHMENT_IDS)


def build_catalog_package() -> CanonicalCatalogPackage:
    base_package = _ability_support_catalog_package(
        datasheet_ids=roster_catalog.EXPECTED_DATASHEET_IDS
    )
    base_catalog = base_package.army_catalog
    factions = _canonical_factions(base_catalog.factions)
    enhancements = _enhancement_definitions()
    stratagems = _stratagem_definitions()
    detachments = _detachment_definitions(
        datasheet_ids_by_faction=_datasheet_ids_by_faction(
            datasheets=base_catalog.datasheets,
            factions=factions,
        ),
        enhancements=enhancements,
        stratagems=stratagems,
    )
    source_ids = tuple(
        sorted(
            {
                *base_catalog.source_ids,
                PACKAGE_ID.stable_identity(),
                faction_detachments_2026_27.SOURCE_PACKAGE_ID,
                faction_subrules_2026_27.SOURCE_PACKAGE_ID,
                mfm_2026_07.SOURCE_PACKAGE_ID,
            }
        )
    )
    catalog = replace(
        base_catalog,
        catalog_id=roster_catalog.EXPECTED_CATALOG_ID,
        source_package_id=PACKAGE_ID.stable_identity(),
        factions=factions,
        detachments=detachments,
        enhancements=enhancements,
        stratagems=stratagems,
        source_ids=source_ids,
    )
    for faction_id in roster_catalog.EXPECTED_FACTION_IDS:
        catalog = catalog_with_mfm_points(
            catalog=catalog,
            faction_id=faction_id,
            source_package=mfm_2026_07.source_package(),
        )
    package = replace(
        base_package,
        package_id=PACKAGE_ID,
        catalog_version=CATALOG_VERSION,
        army_catalog=catalog,
        source_artifacts=(
            *base_package.source_artifacts,
            SourceArtifactHash(
                artifact_name="faction-detachments-2026-27.json",
                artifact_hash=faction_detachments_2026_27.source_payload_checksum_sha256(),
            ),
            SourceArtifactHash(
                artifact_name="faction-subrules-2026-27.json",
                artifact_hash=faction_subrules_2026_27.source_payload_checksum_sha256(),
            ),
            SourceArtifactHash(
                artifact_name="mfm-2026-07.json",
                artifact_hash=mfm_2026_07.SOURCE_PAYLOAD_CHECKSUM_SHA256,
            ),
        ),
    )
    package = _promote_runtime_source_identities(package)
    roster_catalog.validate_catalog_package(package)
    return package


def _promote_runtime_source_identities(
    package: CanonicalCatalogPackage,
) -> CanonicalCatalogPackage:
    identity_replacements = (
        (
            "data-package:core-v2:wahapedia-10e-bridge:phase17k-generated",
            BRIDGE_PACKAGE_ID.stable_identity(),
        ),
        (
            "data-package:wahapedia:source-mirror:10th-edition-2026-06-14",
            REVIEWED_SOURCE_PACKAGE_ID.stable_identity(),
        ),
    )
    catalog_payload = cast(
        ArmyCatalogPayload,
        _promote_identity_value(
            package.army_catalog.to_payload(),
            identity_replacements=identity_replacements,
        ),
    )
    catalog = ArmyCatalog.from_payload(
        cast(ArmyCatalogPayload, _rehash_rule_ir_payloads(catalog_payload))
    )
    geometries = tuple(
        ModelGeometryCatalogRecord.from_payload(
            cast(
                ModelGeometryCatalogRecordPayload,
                _promote_identity_value(
                    record.to_payload(),
                    identity_replacements=identity_replacements,
                ),
            )
        )
        for record in package.model_geometries
    )
    promoted = replace(package, army_catalog=catalog, model_geometries=geometries)
    serialized = promoted.to_json_bytes().decode("utf-8")
    stale_identities = tuple(
        old_identity
        for old_identity, _new_identity in identity_replacements
        if old_identity in serialized
    )
    if stale_identities:
        raise ValueError("Paired-roster runtime source identity promotion was incomplete.")
    return promoted


def _promote_identity_value(
    value: object,
    *,
    identity_replacements: tuple[tuple[str, str], ...],
) -> object:
    if type(value) is str:
        for old_identity, new_identity in identity_replacements:
            if value.startswith(old_identity):
                return new_identity + value.removeprefix(old_identity)
        return value
    if type(value) is list:
        return [
            _promote_identity_value(
                item,
                identity_replacements=identity_replacements,
            )
            for item in cast(list[object], value)
        ]
    if type(value) is dict:
        return {
            cast(str, key): _promote_identity_value(
                item,
                identity_replacements=identity_replacements,
            )
            for key, item in cast(dict[object, object], value).items()
        }
    return value


def _rehash_rule_ir_payloads(value: object) -> object:
    if type(value) is list:
        return [_rehash_rule_ir_payloads(item) for item in cast(list[object], value)]
    if type(value) is not dict:
        return value
    updated = {
        cast(str, key): _rehash_rule_ir_payloads(item)
        for key, item in cast(dict[object, object], value).items()
    }
    if updated.get("schema_version") != "phase17c-rule-ir-v1":
        return updated
    payload = cast(RuleIRPayload, updated)
    rule_ir = RuleIR(
        rule_id=payload["rule_id"],
        source_id=payload["source_id"],
        normalized_text=payload["normalized_text"],
        parser_version=payload["parser_version"],
        schema_version=payload["schema_version"],
        clauses=tuple(RuleClause.from_payload(clause) for clause in payload["clauses"]),
        diagnostics=tuple(
            RuleParseDiagnostic.from_payload(diagnostic) for diagnostic in payload["diagnostics"]
        ),
    )
    return rule_ir.to_payload()


def _canonical_factions(
    factions: tuple[FactionDefinition, ...],
) -> tuple[FactionDefinition, ...]:
    source_rows_by_name = {
        row.name: row
        for row in faction_detachments_2026_27.faction_rows()
        if row.faction_id in SELECTED_FACTION_IDS
    }
    if tuple(sorted(source_rows_by_name)) != ("Aeldari", "Emperor's Children"):
        raise ValueError("Paired-roster faction source closure drifted.")
    canonical: list[FactionDefinition] = []
    for faction in factions:
        row = source_rows_by_name.get(faction.name)
        if row is None:
            raise ValueError("Paired-roster bridge emitted an unexpected faction.")
        canonical.append(
            replace(
                faction,
                faction_id=row.faction_id,
                source_ids=tuple(sorted({*faction.source_ids, *row.source_ids})),
            )
        )
    if {faction.faction_id for faction in canonical} != set(SELECTED_FACTION_IDS):
        raise ValueError("Paired-roster bridge faction closure is incomplete.")
    return tuple(canonical)


def _datasheet_ids_by_faction(
    *,
    datasheets: tuple[DatasheetDefinition, ...],
    factions: tuple[FactionDefinition, ...],
) -> dict[str, tuple[str, ...]]:
    result: dict[str, tuple[str, ...]] = {}
    for faction in factions:
        faction_keywords = set(faction.faction_keywords)
        datasheet_ids = tuple(
            sorted(
                datasheet.datasheet_id
                for datasheet in datasheets
                if faction_keywords.intersection(datasheet.keywords.faction_keywords)
            )
        )
        if not datasheet_ids:
            raise ValueError("Paired-roster faction has no selected datasheet closure.")
        result[faction.faction_id] = datasheet_ids
    return result


def _enhancement_definitions() -> tuple[EnhancementDefinition, ...]:
    return tuple(
        EnhancementDefinition(
            enhancement_id=row.enhancement_id,
            name=row.name,
            source_id=mfm_enhancement.source_id,
            subtypes=(EnhancementSubtype.UPGRADE,) if mfm_enhancement.is_upgrade else (),
            points=mfm_enhancement.points,
        )
        for row in _selected_enhancement_rows()
        for mfm_enhancement in (_mfm_enhancement_for_source_row(row),)
    )


def _stratagem_definitions() -> tuple[StratagemDefinition, ...]:
    return tuple(
        StratagemDefinition(
            stratagem_id=row.stratagem_id,
            name=row.name,
            source_id=row.source_id,
            command_point_cost=row.command_point_cost,
            timing_tags=(row.timing_descriptor,),
        )
        for row in _selected_stratagem_rows()
    )


def _detachment_definitions(
    *,
    datasheet_ids_by_faction: dict[str, tuple[str, ...]],
    enhancements: tuple[EnhancementDefinition, ...],
    stratagems: tuple[StratagemDefinition, ...],
) -> tuple[DetachmentDefinition, ...]:
    enhancement_rows = _selected_enhancement_rows()
    stratagem_rows = _selected_stratagem_rows()
    enhancement_ids_by_detachment = {
        detachment_id: tuple(
            definition.enhancement_id
            for row, definition in zip(enhancement_rows, enhancements, strict=True)
            if row.detachment_id == detachment_id
        )
        for detachment_id in SELECTED_DETACHMENT_IDS
    }
    stratagem_ids_by_detachment = {
        detachment_id: tuple(
            definition.stratagem_id
            for row, definition in zip(stratagem_rows, stratagems, strict=True)
            if row.detachment_id == detachment_id
        )
        for detachment_id in SELECTED_DETACHMENT_IDS
    }
    rows = tuple(
        row
        for row in faction_detachments_2026_27.detachment_rows()
        if row.faction_id in SELECTED_FACTION_IDS and row.detachment_id in SELECTED_DETACHMENT_IDS
    )
    if {row.detachment_id for row in rows} != set(SELECTED_DETACHMENT_IDS):
        raise ValueError("Paired-roster detachment source closure drifted.")
    return tuple(
        DetachmentDefinition(
            detachment_id=row.detachment_id,
            name=row.name,
            faction_id=row.faction_id,
            detachment_point_cost=row.detachment_point_cost,
            unit_datasheet_ids=datasheet_ids_by_faction[row.faction_id],
            force_disposition_ids=(row.force_disposition_id,),
            rule_source_ids=row.source_ids,
            enhancement_ids=enhancement_ids_by_detachment[row.detachment_id],
            stratagem_ids=stratagem_ids_by_detachment[row.detachment_id],
            source_ids=row.source_ids,
        )
        for row in rows
    )


def _selected_enhancement_rows() -> tuple[faction_subrules_2026_27.SourceEnhancementRow, ...]:
    rows = tuple(
        sorted(
            (
                row
                for row in faction_subrules_2026_27.enhancement_rows()
                if row.faction_id in SELECTED_FACTION_IDS
                and row.detachment_id in SELECTED_DETACHMENT_IDS
            ),
            key=lambda row: row.enhancement_id,
        )
    )
    if tuple(row.enhancement_id for row in rows) != roster_catalog.EXPECTED_ENHANCEMENT_IDS:
        raise ValueError("Paired-roster Enhancement source closure drifted.")
    return rows


def _selected_stratagem_rows() -> tuple[faction_subrules_2026_27.SourceStratagemRow, ...]:
    return tuple(
        row
        for row in faction_subrules_2026_27.stratagem_rows()
        if row.faction_id in SELECTED_FACTION_IDS and row.detachment_id in SELECTED_DETACHMENT_IDS
    )


def _mfm_enhancement_for_source_row(
    row: faction_subrules_2026_27.SourceEnhancementRow,
) -> MfmEnhancementRecord:
    faction = mfm_2026_07.faction_record(row.faction_id)
    detachments = tuple(
        detachment
        for detachment in faction.detachments
        if detachment.detachment_id == row.detachment_id
    )
    if len(detachments) != 1:
        raise ValueError("Paired-roster MFM detachment did not resolve exactly once.")
    requested_ids = (row.enhancement_id, source_label_slug(row.name))
    matches = tuple(
        enhancement
        for enhancement in detachments[0].enhancements
        if enhancement.source_id in row.source_ids or enhancement.enhancement_id in requested_ids
    )
    if len(matches) != 1:
        raise ValueError("Paired-roster MFM Enhancement did not resolve exactly once.")
    return matches[0]


def _write_artifact(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(build_catalog_package().to_json_bytes())


def _check_artifact(path: Path) -> None:
    if not path.is_file():
        raise ValueError("Paired-roster catalog artifact is missing.")
    if path.read_bytes() != build_catalog_package().to_json_bytes():
        raise ValueError("Paired-roster catalog artifact is stale.")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--output", type=Path, default=OUTPUT_PATH)
    args = parser.parse_args()
    if args.check:
        _check_artifact(args.output)
    else:
        _write_artifact(args.output)


if __name__ == "__main__":
    main()
