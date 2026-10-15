from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from datetime import date
from pathlib import Path
from typing import cast

import pytest
from tools.apply_transition_patches import apply_transition_patches
from tools.build_transition_patch import build_transition_patch_package

from warhammer40k_core.rules.data_package import CatalogVersion, DataPackageId
from warhammer40k_core.rules.html_sanitizer import contains_html_markup
from warhammer40k_core.rules.parsed_tokens import parse_normalized_tokens
from warhammer40k_core.rules.source_patch import (
    PatchedSourceArtifact,
    PatchedSourceArtifactPayload,
    SourceFaqClassification,
    SourcePatchDiagnostic,
    SourcePatchDiagnosticPayload,
    SourcePatchDiagnosticReason,
    SourcePatchError,
    SourcePatchTarget,
    SourceTransitionPatchOperation,
    SourceTransitionPatchOperationFamily,
    SourceTransitionPatchPackage,
    SourceTransitionPatchPackagePayload,
    apply_transition_patch_package,
    source_row_hash,
)
from warhammer40k_core.rules.wahapedia_schema import (
    NormalizedSourceRow,
    SourceTextField,
    WahapediaCsvTable,
    WahapediaJsonArtifact,
)


def _operation(
    *,
    operation_id: str,
    order_index: int,
    family: SourceTransitionPatchOperationFamily,
    target: SourcePatchTarget,
    instruction_text: str,
    payload: tuple[tuple[str, str], ...],
    faq_classification: SourceFaqClassification | None = None,
) -> SourceTransitionPatchOperation:
    return SourceTransitionPatchOperation.from_instruction(
        operation_id=operation_id,
        order_index=order_index,
        operation_family=family,
        target=target,
        instruction_text=instruction_text,
        source_ids=("gw:death-guard:2026-06-01:page-1",),
        payload=payload,
        faq_classification=faq_classification,
    )


def _patch_package(
    *,
    operations: tuple[SourceTransitionPatchOperation, ...],
) -> SourceTransitionPatchPackage:
    return SourceTransitionPatchPackage(
        package_id=_patch_package_id(),
        catalog_version=_catalog_version(),
        official_source_package_id=DataPackageId(
            namespace="gw",
            package_name="death-guard-faction-pack",
            version="11th-2026-06-01",
        ),
        source_date="2026-06-01",
        source_edition="warhammer-40000-11th",
        faction_id="death-guard",
        operations=operations,
    )


def _text_replace_package(
    *,
    artifact: WahapediaJsonArtifact,
    text: str,
) -> SourceTransitionPatchPackage:
    return _patch_package(
        operations=(
            _operation(
                operation_id="dg-text-replace",
                order_index=1,
                family=SourceTransitionPatchOperationFamily.REPLACE_RULE_TEXT,
                target=SourcePatchTarget.from_rows(
                    source_table="Abilities",
                    rows=(_row_by_id(artifact, "dg-aura:DG"),),
                ),
                instruction_text="Replace the source rule text.",
                payload=(("column_name", "description"), ("text", text)),
            ),
        )
    )


def _abilities_artifact(csv_text: str) -> WahapediaJsonArtifact:
    return WahapediaJsonArtifact.from_csv_table(
        source_package_id=_source_package_id(),
        table=WahapediaCsvTable.from_csv_text(table_name="Abilities", csv_text=csv_text),
    )


def _datasheets_artifact(csv_text: str) -> WahapediaJsonArtifact:
    return WahapediaJsonArtifact.from_csv_table(
        source_package_id=_source_package_id(),
        table=WahapediaCsvTable.from_csv_text(table_name="Datasheets", csv_text=csv_text),
    )


def _wargear_artifact(csv_text: str) -> WahapediaJsonArtifact:
    return WahapediaJsonArtifact.from_csv_table(
        source_package_id=_source_package_id(),
        table=WahapediaCsvTable.from_csv_text(
            table_name="Datasheets_wargear",
            csv_text=csv_text,
        ),
    )


def _row_by_id(artifact: WahapediaJsonArtifact, source_row_id: str) -> NormalizedSourceRow:
    for row in artifact.rows:
        if row.source_row_id == source_row_id:
            return row
    raise AssertionError(f"Missing row {source_row_id}.")


def _patched_row_by_id(
    artifact: PatchedSourceArtifact,
    source_row_id: str,
) -> NormalizedSourceRow:
    for row in artifact.rows:
        if row.source_row_id == source_row_id:
            return row
    raise AssertionError(f"Missing row {source_row_id}.")


def _text_field(row: NormalizedSourceRow, column_name: str) -> SourceTextField:
    for text_field in row.text_fields:
        if text_field.column_name == column_name:
            return text_field
    raise AssertionError(f"Missing text field {column_name}.")


def _source_package_id() -> DataPackageId:
    return DataPackageId(
        namespace="wahapedia",
        package_name="source-mirror",
        version="11th-transition",
    )


def _patch_package_id() -> DataPackageId:
    return DataPackageId(
        namespace="gw",
        package_name="death-guard-transition-patches",
        version="11th-2026-06-01",
    )


def _catalog_version() -> CatalogVersion:
    return CatalogVersion.dated(
        version_id="phase17a1-test",
        source_date=date(2026, 6, 1),
    )


__all__: list[str] = []
__all__ += ["CatalogVersion", "DataPackageId", "NormalizedSourceRow", "PatchedSourceArtifact"]
__all__ += ["PatchedSourceArtifactPayload", "Path", "SourceFaqClassification"]
__all__ += ["SourcePatchDiagnostic", "SourcePatchDiagnosticPayload"]
__all__ += ["SourcePatchDiagnosticReason", "SourcePatchError", "SourcePatchTarget"]
__all__ += ["SourceTextField", "SourceTransitionPatchOperation"]
__all__ += ["SourceTransitionPatchOperationFamily", "SourceTransitionPatchPackage"]
__all__ += ["SourceTransitionPatchPackagePayload", "WahapediaCsvTable", "WahapediaJsonArtifact"]
__all__ += ["_abilities_artifact", "_catalog_version", "_datasheets_artifact", "_operation"]
__all__ += ["_patch_package", "_patch_package_id", "_patched_row_by_id", "_row_by_id"]
__all__ += ["_source_package_id", "_text_field", "_text_replace_package", "_wargear_artifact"]
__all__ += ["apply_transition_patch_package", "apply_transition_patches"]
__all__ += ["build_transition_patch_package", "cast", "contains_html_markup", "date", "hashlib"]
__all__ += ["json", "parse_normalized_tokens", "pytest", "replace", "source_row_hash"]
