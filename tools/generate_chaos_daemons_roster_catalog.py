from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import replace
from datetime import date
from pathlib import Path
from typing import cast

from warhammer40k_core.core.detachment import (
    DetachmentDefinition,
    EnhancementDefinition,
    EnhancementSubtype,
    StratagemDefinition,
)
from warhammer40k_core.core.model_geometry_catalog import ModelGeometryDiagnosticReason
from warhammer40k_core.engine.army_points import catalog_with_mfm_points
from warhammer40k_core.rules.catalog_generation import build_canonical_catalog_report
from warhammer40k_core.rules.catalog_package import CanonicalCatalogPackage
from warhammer40k_core.rules.data_package import CatalogVersion, DataPackageId
from warhammer40k_core.rules.mfm_source import MfmEnhancementRecord, source_label_slug
from warhammer40k_core.rules.source_catalog import SourceArtifactHash
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    chaos_daemons_roster_2026_07 as roster_catalog,
)
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    faction_detachments_2026_27,
    faction_source_promotion_2026_07,
    faction_subrules_2026_27,
    mfm_2026_07,
)
from warhammer40k_core.rules.wahapedia_bridge import (
    build_wahapedia_canonical_bridge_artifacts,
)
from warhammer40k_core.rules.wahapedia_bridge_defaults import PdfDatasheetCorrection
from warhammer40k_core.rules.wahapedia_schema import (
    NormalizedSourceRow,
    NormalizedSourceRowPayload,
    WahapediaCsvRow,
    WahapediaJsonArtifact,
    WahapediaJsonArtifactPayload,
    schema_for_table,
)

ROOT = Path(__file__).resolve().parents[1]
SOURCE_JSON_DIR = (
    ROOT / "data" / "source_snapshots" / "wahapedia" / "10th-edition" / "2026-06-14" / "json"
)
OUTPUT_PATH = (
    ROOT
    / "src"
    / "warhammer40k_core"
    / "rules"
    / "source_packages"
    / "warhammer_40000_11th"
    / "chaos_daemons_roster_2026_07"
    / roster_catalog.ARTIFACT_PATH
)
RECONCILIATION_PATH = OUTPUT_PATH.parent / "official-pdf-reconciliation.json"
REQUIRED_TABLES = (
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
PACKAGE_ID = DataPackageId(
    namespace="core-v2",
    package_name="chaos-daemons-roster",
    version="2026-07",
)
BRIDGE_PACKAGE_ID = DataPackageId(
    namespace="core-v2",
    package_name="chaos-daemons-roster-bridge",
    version="2026-07",
)
EXPECTED_GENERATOR_INPUT_PACKAGE_ID = DataPackageId(
    namespace="wahapedia",
    package_name="source-mirror",
    version="10th-edition-2026-06-14",
)
CATALOG_VERSION = CatalogVersion.dated(
    version_id="warhammer-40000-11th-chaos-daemons-roster-2026-07",
    source_date=date(2026, 7, 22),
)


def build_catalog_package() -> CanonicalCatalogPackage:
    reconciliation = roster_catalog.reconciliation_manifest()
    source_artifacts, generator_input_hashes = _source_artifacts_and_provenance(
        reconciliation=reconciliation
    )
    current_faction_source = _current_faction_source()
    bridge_artifacts = build_wahapedia_canonical_bridge_artifacts(
        source_artifacts=source_artifacts,
        bridge_package_id=BRIDGE_PACKAGE_ID,
        datasheet_ids=roster_catalog.EXPECTED_DATASHEET_IDS,
        pdf_corrections=_official_pdf_keyword_corrections(reconciliation),
    )
    build_report = build_canonical_catalog_report(
        package_id=PACKAGE_ID,
        catalog_version=CATALOG_VERSION,
        source_artifacts=bridge_artifacts,
    )
    base_package = build_report.package
    if base_package is None:
        raise ValueError("Chaos Daemons roster catalog could not preserve its model profiles.")
    expected_geometry_blockers = tuple(
        sorted(
            (
                model_profile_id,
                ModelGeometryDiagnosticReason.UNREVIEWED_EVIDENCE,
            )
            for model_profile_id in roster_catalog.EXPECTED_GEOMETRY_BLOCKED_PROFILE_IDS
        )
    )
    actual_geometry_blockers = tuple(
        sorted((row.model_profile_id, row.reason) for row in build_report.blocking_diagnostics())
    )
    if actual_geometry_blockers != expected_geometry_blockers:
        raise ValueError("Chaos Daemons roster geometry review blockers drifted.")
    base_catalog = base_package.army_catalog
    faction = replace(base_catalog.factions[0], faction_id="chaos-daemons")
    enhancements = _enhancement_definitions()
    stratagems = _stratagem_definitions()
    datasheet_ids = tuple(datasheet.datasheet_id for datasheet in base_catalog.datasheets)
    detachments = _detachment_definitions(
        datasheet_ids=datasheet_ids,
        enhancements=enhancements,
        stratagems=stratagems,
    )
    source_ids = tuple(
        sorted(
            {
                *base_catalog.source_ids,
                faction_detachments_2026_27.SOURCE_PACKAGE_ID,
                faction_subrules_2026_27.SOURCE_PACKAGE_ID,
                mfm_2026_07.SOURCE_PACKAGE_ID,
                current_faction_source.package_id,
            }
        )
    )
    catalog = replace(
        base_catalog,
        catalog_id=roster_catalog.EXPECTED_CATALOG_ID,
        factions=(faction,),
        detachments=detachments,
        enhancements=enhancements,
        stratagems=stratagems,
        source_ids=source_ids,
    )
    current_catalog = catalog_with_mfm_points(
        catalog=catalog,
        faction_id="chaos-daemons",
        source_package=mfm_2026_07.source_package(),
    )
    source_artifacts_with_provenance = (
        *base_package.source_artifacts,
        *generator_input_hashes,
        SourceArtifactHash(
            artifact_name="official-current-chaos-daemons-faction-pack.pdf",
            artifact_hash=current_faction_source.sha256,
        ),
        SourceArtifactHash(
            artifact_name=roster_catalog.EXPECTED_RECONCILIATION_SOURCE_ARTIFACT[0],
            artifact_hash=roster_catalog.raw_reconciliation_artifact_hash(
                RECONCILIATION_PATH.read_bytes()
            ),
        ),
    )
    package = replace(
        base_package,
        army_catalog=current_catalog,
        source_artifacts=source_artifacts_with_provenance,
    )
    roster_catalog.validate_catalog_against_reconciliation(
        catalog=package.army_catalog,
        reconciliation=reconciliation,
    )
    return package


def _source_artifacts_and_provenance(
    *,
    reconciliation: roster_catalog.ExactRosterReconciliation,
) -> tuple[
    tuple[WahapediaJsonArtifact, ...],
    tuple[SourceArtifactHash, ...],
]:
    generator_inputs = tuple(
        WahapediaJsonArtifact.from_payload(
            cast(
                WahapediaJsonArtifactPayload,
                json.loads((SOURCE_JSON_DIR / f"{table_name}.json").read_text(encoding="utf-8")),
            )
        )
        for table_name in REQUIRED_TABLES
    )
    for artifact in generator_inputs:
        if artifact.source_package_id != EXPECTED_GENERATOR_INPUT_PACKAGE_ID:
            raise ValueError("Chaos Daemons generator input source identity drifted.")
    expected_input_hashes = dict(roster_catalog.EXPECTED_GENERATOR_INPUT_ARTIFACT_HASHES)
    if tuple(sorted(expected_input_hashes)) != tuple(sorted(REQUIRED_TABLES)):
        raise ValueError("Chaos Daemons generator input provenance table closure drifted.")
    if reconciliation.generator_inputs.artifact_hashes != tuple(
        sorted(expected_input_hashes.items())
    ):
        raise ValueError("Chaos Daemons reconciliation generator input hashes drifted.")
    for artifact in generator_inputs:
        if artifact.artifact_hash() != expected_input_hashes[artifact.source_table]:
            raise ValueError("Chaos Daemons generator input artifact hash drifted.")
    for review in reconciliation.datasheets:
        if (
            _generator_input_datasheet_payload_hash(
                source_artifacts=generator_inputs,
                datasheet_id=review.datasheet_id,
            )
            != review.generator_input_payload_hash
        ):
            raise ValueError("Chaos Daemons generator input datasheet payload drifted.")
    linked_ability_ids = _selected_linked_ability_ids(generator_inputs)
    source_artifacts = tuple(
        _promote_reviewed_source_artifact(
            artifact=artifact,
            linked_ability_ids=linked_ability_ids,
        )
        for artifact in generator_inputs
    )
    input_hashes = tuple(
        SourceArtifactHash(
            artifact_name=f"generator-input-{artifact.source_table}.json",
            artifact_hash=artifact.artifact_hash(),
        )
        for artifact in generator_inputs
    )
    return source_artifacts, input_hashes


def _generator_input_datasheet_payload_hash(
    *,
    source_artifacts: tuple[WahapediaJsonArtifact, ...],
    datasheet_id: str,
) -> str:
    rows = [row for artifact in source_artifacts for row in artifact.rows]
    linked_ability_ids = {
        str(row.runtime_fields_payload().get("ability_id", ""))
        for row in rows
        if row.source_table == "Datasheets_abilities"
        and row.runtime_fields_payload().get("datasheet_id") == datasheet_id
        and row.runtime_fields_payload().get("ability_id")
    }
    selected_rows = tuple(
        sorted(
            (
                row.to_payload()
                for row in rows
                if _generator_input_row_belongs_to_datasheet(
                    row=row,
                    datasheet_id=datasheet_id,
                    linked_ability_ids=linked_ability_ids,
                )
            ),
            key=lambda payload: (
                str(payload["source_table"]),
                str(payload["source_row_id"]),
            ),
        )
    )
    if not selected_rows:
        raise ValueError("Chaos Daemons generator input datasheet payload is empty.")
    return hashlib.sha256(
        json.dumps(selected_rows, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _generator_input_row_belongs_to_datasheet(
    *,
    row: NormalizedSourceRow,
    datasheet_id: str,
    linked_ability_ids: set[str],
) -> bool:
    fields = row.runtime_fields_payload()
    if row.source_table == "Datasheets":
        return fields.get("id") == datasheet_id
    if row.source_table == "Abilities":
        return fields.get("id") in linked_ability_ids
    if row.source_table == "Datasheets_leader":
        return fields.get("leader_id") == datasheet_id
    return fields.get("datasheet_id") == datasheet_id


def _promote_reviewed_source_artifact(
    *,
    artifact: WahapediaJsonArtifact,
    linked_ability_ids: frozenset[str],
) -> WahapediaJsonArtifact:
    if artifact.source_package_id != EXPECTED_GENERATOR_INPUT_PACKAGE_ID:
        raise ValueError("Chaos Daemons generator input source identity drifted.")
    old_identity = EXPECTED_GENERATOR_INPUT_PACKAGE_ID.stable_identity()
    new_identity = roster_catalog.REVIEWED_SOURCE_PACKAGE_ID.stable_identity()
    selected_rows = tuple(
        row
        for row in artifact.rows
        if _source_row_is_in_reviewed_roster_closure(
            row=row,
            linked_ability_ids=linked_ability_ids,
        )
    )
    promoted_rows = tuple(
        _apply_official_row_corrections(
            NormalizedSourceRow.from_payload(
                cast(
                    NormalizedSourceRowPayload,
                    _promote_identity_value(
                        row.to_payload(),
                        old_identity=old_identity,
                        new_identity=new_identity,
                    ),
                )
            )
        )
        for row in selected_rows
    )
    promoted = WahapediaJsonArtifact(
        source_package_id=roster_catalog.REVIEWED_SOURCE_PACKAGE_ID,
        source_table=artifact.source_table,
        source_checksum_sha256=roster_catalog.OFFICIAL_PDF_SHA256,
        rows=promoted_rows,
    )
    if old_identity in promoted.to_json_bytes().decode():
        raise ValueError("Chaos Daemons reviewed source identity promotion was incomplete.")
    return promoted


def _promote_identity_value(
    value: object,
    *,
    old_identity: str,
    new_identity: str,
) -> object:
    if type(value) is str:
        if value.startswith(old_identity):
            return new_identity + value.removeprefix(old_identity)
        return value
    if type(value) is list:
        return [
            _promote_identity_value(
                item,
                old_identity=old_identity,
                new_identity=new_identity,
            )
            for item in cast(list[object], value)
        ]
    if type(value) is dict:
        promoted = {
            cast(str, key): _promote_identity_value(
                item,
                old_identity=old_identity,
                new_identity=new_identity,
            )
            for key, item in cast(dict[object, object], value).items()
        }
        if "source_package_id" in promoted:
            promoted["source_package_id"] = roster_catalog.REVIEWED_SOURCE_PACKAGE_ID.to_payload()
        return promoted
    return value


def _selected_linked_ability_ids(
    source_artifacts: tuple[WahapediaJsonArtifact, ...],
) -> frozenset[str]:
    selected_ids = frozenset(roster_catalog.EXPECTED_DATASHEET_IDS)
    ability_ids = {
        str(row.runtime_fields_payload().get("ability_id", ""))
        for artifact in source_artifacts
        if artifact.source_table == "Datasheets_abilities"
        for row in artifact.rows
        if row.runtime_fields_payload().get("datasheet_id") in selected_ids
        and row.runtime_fields_payload().get("ability_id")
    }
    if not ability_ids:
        raise ValueError("Chaos Daemons reviewed ability closure is empty.")
    return frozenset(ability_ids)


def _source_row_is_in_reviewed_roster_closure(
    *,
    row: NormalizedSourceRow,
    linked_ability_ids: frozenset[str],
) -> bool:
    selected_ids = frozenset(roster_catalog.EXPECTED_DATASHEET_IDS)
    fields = row.runtime_fields_payload()
    if row.source_table == "Abilities":
        return fields.get("id") in linked_ability_ids
    if row.source_table == "Factions":
        return fields.get("id") == "CD"
    if row.source_table == "Datasheets":
        return fields.get("id") in selected_ids
    if row.source_table == "Datasheets_leader":
        return fields.get("leader_id") in selected_ids and fields.get("attached_id") in selected_ids
    if fields.get("datasheet_id") not in selected_ids:
        return False
    return not (
        row.source_table == "Datasheets_keywords"
        and fields.get("keyword", "").upper() == "SHADOW LEGION"
    )


def _apply_official_row_corrections(row: NormalizedSourceRow) -> NormalizedSourceRow:
    fields = row.runtime_fields_payload()
    if row.source_table != "Datasheets" or fields.get("id") != "000001148":
        return row
    corrected_fields = {
        **fields,
        "damaged_w": "1-7",
        "damaged_description": (
            "While this model has 1-7 wounds remaining, each time this model makes an "
            "attack, subtract 1 from the Hit roll."
        ),
    }
    corrected = NormalizedSourceRow.from_csv_row(
        source_package_id=roster_catalog.REVIEWED_SOURCE_PACKAGE_ID,
        schema=schema_for_table(row.source_table),
        row=WahapediaCsvRow(
            row_number=row.source_row_number,
            values=tuple(corrected_fields.items()),
        ),
    )
    if corrected.source_row_id != row.source_row_id:
        raise ValueError("Chaos Daemons official PDF correction changed source row identity.")
    return corrected


def _official_pdf_keyword_corrections(
    reconciliation: roster_catalog.ExactRosterReconciliation,
) -> tuple[PdfDatasheetCorrection, ...]:
    return tuple(
        PdfDatasheetCorrection(
            datasheet_id=review.datasheet_id,
            source_id=review.official_source_id,
            replacement_keywords=review.expected_keywords,
            source_package_version="2026-07",
        )
        for review in reconciliation.datasheets
    )


def _current_faction_source() -> faction_source_promotion_2026_07.CurrentFactionSourceRecord:
    matches = tuple(
        record
        for record in faction_source_promotion_2026_07.current_source_records()
        if record.faction_id == "chaos-daemons"
    )
    if len(matches) != 1:
        raise ValueError("Chaos Daemons current faction source must resolve exactly once.")
    source = matches[0]
    expected_artifact_name, expected_sha256 = (
        roster_catalog.EXPECTED_CURRENT_FACTION_SOURCE_ARTIFACT
    )
    if (
        source.package_id != roster_catalog.EXPECTED_CURRENT_FACTION_SOURCE_PACKAGE_ID
        or expected_artifact_name != "official-current-chaos-daemons-faction-pack.pdf"
        or source.sha256 != expected_sha256
    ):
        raise ValueError("Chaos Daemons current faction source package identity drifted.")
    return source


def _enhancement_definitions() -> tuple[EnhancementDefinition, ...]:
    definitions: list[EnhancementDefinition] = []
    for row in _selected_enhancement_rows():
        is_cavalcade_upgrade = row.detachment_id == "cavalcade-of-chaos"
        mfm_enhancement = _mfm_enhancement_for_source_row(row)
        definitions.append(
            EnhancementDefinition(
                enhancement_id=row.enhancement_id,
                name=row.name,
                source_id=mfm_enhancement.source_id,
                subtypes=(EnhancementSubtype.UPGRADE,) if is_cavalcade_upgrade else (),
                points=row.points,
                target_required_keywords=(("MOUNTED",) if is_cavalcade_upgrade else ("CHARACTER",)),
                target_required_faction_keywords=("LEGIONES DAEMONICA",),
            )
        )
    return tuple(definitions)


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
    datasheet_ids: tuple[str, ...],
    enhancements: tuple[EnhancementDefinition, ...],
    stratagems: tuple[StratagemDefinition, ...],
) -> tuple[DetachmentDefinition, ...]:
    enhancement_ids_by_detachment = {
        detachment_id: tuple(
            definition.enhancement_id
            for row, definition in zip(_selected_enhancement_rows(), enhancements, strict=True)
            if row.detachment_id == detachment_id
        )
        for detachment_id in roster_catalog.EXPECTED_DETACHMENT_IDS
    }
    stratagem_ids_by_detachment = {
        detachment_id: tuple(
            definition.stratagem_id
            for row, definition in zip(_selected_stratagem_rows(), stratagems, strict=True)
            if row.detachment_id == detachment_id
        )
        for detachment_id in roster_catalog.EXPECTED_DETACHMENT_IDS
    }
    rows = {
        row.detachment_id: row
        for row in faction_detachments_2026_27.detachment_rows()
        if row.faction_id == "chaos-daemons"
        and row.detachment_id in roster_catalog.EXPECTED_DETACHMENT_IDS
    }
    if tuple(sorted(rows)) != tuple(sorted(roster_catalog.EXPECTED_DETACHMENT_IDS)):
        raise ValueError("Chaos Daemons roster detachment source closure drifted.")
    return tuple(
        DetachmentDefinition(
            detachment_id=row.detachment_id,
            name=row.name,
            faction_id=row.faction_id,
            detachment_point_cost=row.detachment_point_cost,
            unit_datasheet_ids=datasheet_ids,
            force_disposition_ids=(row.force_disposition_id,),
            rule_source_ids=row.source_ids,
            enhancement_ids=enhancement_ids_by_detachment[row.detachment_id],
            stratagem_ids=stratagem_ids_by_detachment[row.detachment_id],
            source_ids=row.source_ids,
        )
        for row in sorted(rows.values(), key=lambda value: value.detachment_id)
    )


def _selected_enhancement_rows() -> tuple[faction_subrules_2026_27.SourceEnhancementRow, ...]:
    return tuple(
        sorted(
            (
                row
                for row in faction_subrules_2026_27.enhancement_rows()
                if row.faction_id == "chaos-daemons"
                and row.detachment_id in roster_catalog.EXPECTED_DETACHMENT_IDS
            ),
            key=lambda row: (row.detachment_id, row.enhancement_id),
        )
    )


def _selected_stratagem_rows() -> tuple[faction_subrules_2026_27.SourceStratagemRow, ...]:
    return tuple(
        sorted(
            (
                row
                for row in faction_subrules_2026_27.stratagem_rows()
                if row.faction_id == "chaos-daemons"
                and row.detachment_id in roster_catalog.EXPECTED_DETACHMENT_IDS
            ),
            key=lambda row: (row.detachment_id, row.stratagem_id),
        )
    )


def _mfm_enhancement_for_source_row(
    row: faction_subrules_2026_27.SourceEnhancementRow,
) -> MfmEnhancementRecord:
    faction = next(
        record
        for record in mfm_2026_07.source_package().factions
        if record.faction_id == row.faction_id
    )
    detachment = next(
        record for record in faction.detachments if record.detachment_id == row.detachment_id
    )
    source_slug = source_label_slug(row.name)
    for suffix in ("-aura", "-upgrade"):
        source_slug = source_slug.removesuffix(suffix)
    matches = tuple(
        record for record in detachment.enhancements if record.enhancement_id == source_slug
    )
    if len(matches) != 1:
        raise ValueError("Chaos Daemons Enhancement did not resolve to exact July MFM source.")
    return matches[0]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--check",
        action="store_true",
        help="Fail if the committed catalog artifact is stale.",
    )
    args = parser.parse_args()
    generated = build_catalog_package().to_json_bytes()
    if args.check:
        if not OUTPUT_PATH.is_file() or OUTPUT_PATH.read_bytes() != generated:
            raise SystemExit("Chaos Daemons roster catalog artifact is stale.")
        return
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_bytes(generated)


if __name__ == "__main__":
    main()
