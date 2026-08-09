from __future__ import annotations

import json
from functools import cache
from typing import Final, cast

from warhammer40k_core.rules.catalog_package import (
    CanonicalCatalogPackage,
    CanonicalCatalogPackagePayload,
)
from warhammer40k_core.rules.source_packages.artifact_loader import (
    SourcePackageArtifactError,
    package_artifact_bytes,
)

from . import _reconciliation

ChaosDaemonsRosterReconciliationError = _reconciliation.ChaosDaemonsRosterReconciliationError
ExactRosterReconciliation = _reconciliation.ExactRosterReconciliation
OFFICIAL_PDF_SHA256 = _reconciliation.OFFICIAL_PDF_SHA256
REVIEWED_SOURCE_PACKAGE_ID = _reconciliation.REVIEWED_SOURCE_PACKAGE_ID
catalog_datasheet_gameplay_hash = _reconciliation.catalog_datasheet_gameplay_hash
raw_reconciliation_artifact_hash = _reconciliation.raw_reconciliation_artifact_hash
reconciliation_from_json_bytes = _reconciliation.reconciliation_from_json_bytes
validate_catalog_against_reconciliation = _reconciliation.validate_catalog_against_reconciliation

ARTIFACT_PATH: Final = "artifacts/catalog.json"
RECONCILIATION_ARTIFACT_PATH: Final = "artifacts/official-pdf-reconciliation.json"
EXPECTED_PACKAGE_ID: Final = "data-package:core-v2:chaos-daemons-roster:2026-07"
EXPECTED_CATALOG_ID: Final = "core-v2:chaos-daemons-roster:2026-07"
EXPECTED_DATASHEET_IDS: Final = (
    "000001115",
    "000001120",
    "000001132",
    "000001148",
    "000002582",
)
EXPECTED_DETACHMENT_IDS: Final = ("cavalcade-of-chaos", "shadow-legion")
EXPECTED_GEOMETRY_PROFILE_IDS: Final = (
    "000001115:bloodcrushers",
    "000001115:bloodhunter",
    "000001148:belakor-epic-hero",
)
EXPECTED_GEOMETRY_BLOCKED_PROFILE_IDS: Final = (
    "000001120:lord-of-change",
    "000001132:plaguebearers",
    "000001132:plagueridden",
    "000002582:bloodthirster",
)
EXPECTED_CURRENT_FACTION_SOURCE_PACKAGE_ID: Final = "gw-11e-chaos-daemons-faction-pack-2026-07"
EXPECTED_CURRENT_FACTION_SOURCE_ARTIFACT: Final = (
    "official-current-chaos-daemons-faction-pack.pdf",
    "818f7ef144691b9eef6b3c5b5d0a39793690af5a958037b7055215e6675e6a2c",
)
EXPECTED_RECONCILIATION_SOURCE_ARTIFACT: Final = (
    "official-pdf-exact-five-reconciliation.json",
    "942c399ad980d78fb4e5413d16cd3a487ef6e5cf7c69bacc54366e3f3b200a12",
)
EXPECTED_GENERATOR_INPUT_ARTIFACT_HASHES: Final = (
    ("Abilities", "5d2718402066eecc33195e14f98d44900e374e8450ef246c2b766dd08e833990"),
    ("Datasheets", "1722c3e070c45594aefe86f70250415e7f42774b79b3eaab4a10702129f6252c"),
    (
        "Datasheets_abilities",
        "2cf705d43ab06ba0345438d9104a8cf4dc6eff2d8c13e19f230ec8aa6169b693",
    ),
    (
        "Datasheets_keywords",
        "91081f23391dc9cc8a39eb9ee90c3cedb1d09439ecd16c0bd9390b48af4c3a14",
    ),
    (
        "Datasheets_leader",
        "581c60f74358aed92c927d93b4c1abcac1b7047cca8c3dcef768708b6a761b62",
    ),
    (
        "Datasheets_models",
        "1917ca16ffac89b5920eb134bb64d981cdc4f07cb439271a858e50299b3d919a",
    ),
    (
        "Datasheets_models_cost",
        "3cd3af1cd8c97cbbc83a9831cfdbe9d493b63f8f78bb27aff3b1f1d0322dc53e",
    ),
    (
        "Datasheets_options",
        "869b21016b1ce7904351c6671e00ab963bd8a536b39872c52524b00abf14bd38",
    ),
    (
        "Datasheets_unit_composition",
        "80335a2bceb155f1c8de2618e5a7ec78acd2ed792859e5af4d1518d27d6e059d",
    ),
    (
        "Datasheets_wargear",
        "21a0f8444e15a20f3481df4a83f52f7eb676e682e89ab08757556b48949f1b93",
    ),
    ("Factions", "3677d904916c2ebf57a2369995b8ee2a6d35e25d8026f958cc35f4e699995646"),
)


class ChaosDaemonsRosterCatalogError(ValueError):
    """Raised when the committed Chaos Daemons roster catalog is invalid."""


@cache
def catalog_package() -> CanonicalCatalogPackage:
    try:
        raw = package_artifact_bytes(__name__, ARTIFACT_PATH)
    except SourcePackageArtifactError as exc:
        raise ChaosDaemonsRosterCatalogError(
            "Chaos Daemons roster catalog artifact could not be loaded."
        ) from exc
    try:
        decoded = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ChaosDaemonsRosterCatalogError(
            "Chaos Daemons roster catalog artifact is not valid JSON."
        ) from exc
    if not isinstance(decoded, dict):
        raise ChaosDaemonsRosterCatalogError(
            "Chaos Daemons roster catalog artifact must be a JSON object."
        )
    package = CanonicalCatalogPackage.from_payload(cast(CanonicalCatalogPackagePayload, decoded))
    _validate_catalog_package(package)
    return package


@cache
def reconciliation_manifest() -> _reconciliation.ExactRosterReconciliation:
    try:
        raw = package_artifact_bytes(__name__, RECONCILIATION_ARTIFACT_PATH)
    except SourcePackageArtifactError as exc:
        raise ChaosDaemonsRosterCatalogError(
            "Chaos Daemons exact-roster reconciliation artifact could not be loaded."
        ) from exc
    if (
        _reconciliation.raw_reconciliation_artifact_hash(raw)
        != EXPECTED_RECONCILIATION_SOURCE_ARTIFACT[1]
    ):
        raise ChaosDaemonsRosterCatalogError(
            "Chaos Daemons exact-roster reconciliation raw artifact hash drifted."
        )
    try:
        reconciliation = _reconciliation.reconciliation_from_json_bytes(raw)
    except _reconciliation.ChaosDaemonsRosterReconciliationError as exc:
        raise ChaosDaemonsRosterCatalogError(
            "Chaos Daemons exact-roster reconciliation artifact is invalid."
        ) from exc
    if reconciliation.generator_inputs.artifact_hashes != tuple(
        sorted(EXPECTED_GENERATOR_INPUT_ARTIFACT_HASHES)
    ):
        raise ChaosDaemonsRosterCatalogError(
            "Chaos Daemons exact-roster generator input provenance drifted."
        )
    return reconciliation


def _validate_catalog_package(package: CanonicalCatalogPackage) -> None:
    if package.package_id.stable_identity() != EXPECTED_PACKAGE_ID:
        raise ChaosDaemonsRosterCatalogError(
            "Chaos Daemons roster catalog package identity drifted."
        )
    catalog = package.army_catalog
    if catalog.catalog_id != EXPECTED_CATALOG_ID:
        raise ChaosDaemonsRosterCatalogError("Chaos Daemons roster ArmyCatalog identity drifted.")
    if EXPECTED_CURRENT_FACTION_SOURCE_PACKAGE_ID not in catalog.source_ids:
        raise ChaosDaemonsRosterCatalogError(
            "Chaos Daemons roster current faction source identity is missing."
        )
    if tuple(datasheet.datasheet_id for datasheet in catalog.datasheets) != (
        EXPECTED_DATASHEET_IDS
    ):
        raise ChaosDaemonsRosterCatalogError(
            "Chaos Daemons roster catalog datasheet closure drifted."
        )
    if tuple(detachment.detachment_id for detachment in catalog.detachments) != (
        EXPECTED_DETACHMENT_IDS
    ):
        raise ChaosDaemonsRosterCatalogError(
            "Chaos Daemons roster catalog detachment closure drifted."
        )
    geometry_ids = tuple(record.model_profile_id for record in package.model_geometries)
    if geometry_ids != EXPECTED_GEOMETRY_PROFILE_IDS:
        raise ChaosDaemonsRosterCatalogError(
            "Chaos Daemons roster catalog geometry closure drifted."
        )
    geometry_blockers = tuple(
        diagnostic.model_profile_id
        for diagnostic in package.diagnostics
        if diagnostic.blocking and diagnostic.reason.value == "unreviewed_evidence"
    )
    if geometry_blockers != EXPECTED_GEOMETRY_BLOCKED_PROFILE_IDS:
        raise ChaosDaemonsRosterCatalogError(
            "Chaos Daemons roster catalog geometry review blockers drifted."
        )
    source_artifact_hashes = {
        artifact.artifact_name: artifact.artifact_hash for artifact in package.source_artifacts
    }
    expected_provenance_hashes = {
        **{
            f"generator-input-{table_name}.json": artifact_hash
            for table_name, artifact_hash in EXPECTED_GENERATOR_INPUT_ARTIFACT_HASHES
        },
        EXPECTED_CURRENT_FACTION_SOURCE_ARTIFACT[0]: (EXPECTED_CURRENT_FACTION_SOURCE_ARTIFACT[1]),
        EXPECTED_RECONCILIATION_SOURCE_ARTIFACT[0]: (EXPECTED_RECONCILIATION_SOURCE_ARTIFACT[1]),
    }
    if any(
        source_artifact_hashes.get(artifact_name) != artifact_hash
        for artifact_name, artifact_hash in expected_provenance_hashes.items()
    ):
        raise ChaosDaemonsRosterCatalogError(
            "Chaos Daemons roster catalog source provenance drifted."
        )
    reconciliation = reconciliation_manifest()
    try:
        _reconciliation.validate_catalog_against_reconciliation(
            catalog=catalog,
            reconciliation=reconciliation,
        )
    except _reconciliation.ChaosDaemonsRosterReconciliationError as exc:
        raise ChaosDaemonsRosterCatalogError(
            "Chaos Daemons roster catalog official-PDF reconciliation drifted."
        ) from exc


__all__ = (
    "ARTIFACT_PATH",
    "EXPECTED_CATALOG_ID",
    "EXPECTED_CURRENT_FACTION_SOURCE_ARTIFACT",
    "EXPECTED_CURRENT_FACTION_SOURCE_PACKAGE_ID",
    "EXPECTED_DATASHEET_IDS",
    "EXPECTED_DETACHMENT_IDS",
    "EXPECTED_GENERATOR_INPUT_ARTIFACT_HASHES",
    "EXPECTED_GEOMETRY_BLOCKED_PROFILE_IDS",
    "EXPECTED_GEOMETRY_PROFILE_IDS",
    "EXPECTED_PACKAGE_ID",
    "EXPECTED_RECONCILIATION_SOURCE_ARTIFACT",
    "OFFICIAL_PDF_SHA256",
    "RECONCILIATION_ARTIFACT_PATH",
    "REVIEWED_SOURCE_PACKAGE_ID",
    "ChaosDaemonsRosterCatalogError",
    "ChaosDaemonsRosterReconciliationError",
    "ExactRosterReconciliation",
    "catalog_datasheet_gameplay_hash",
    "catalog_package",
    "raw_reconciliation_artifact_hash",
    "reconciliation_from_json_bytes",
    "reconciliation_manifest",
    "validate_catalog_against_reconciliation",
)
