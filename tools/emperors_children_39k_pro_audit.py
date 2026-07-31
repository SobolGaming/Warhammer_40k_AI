from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from functools import cache
from pathlib import Path
from typing import Any, cast
from urllib.parse import urlsplit

from warhammer40k_core.rules.external_reference_lookup import (
    THIRTY_NINE_K_PRO_TARGET_EDITION,
    ExternalReferenceKind,
    verify_thirty_nine_k_pro_reference_url,
)
from warhammer40k_core.rules.source_overlay import (
    SourceOverlayOperation,
    SourceOverlayOperationKind,
)
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    emperors_children_datasheet_overlay_2026_06 as source_overlay,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
AUDIT_PATH = (
    REPO_ROOT / "data" / "source_audits" / "39k_pro" / "emperors_children_2026_07_31.audit.json"
)
SOURCE_DIR = (
    REPO_ROOT
    / "data"
    / "source_snapshots"
    / "wahapedia"
    / ("1" + "0" + "th-edition")
    / "2026-06-14"
    / "json"
)
AUDIT_SCHEMA_VERSION = "2"

_PROVIDER_IDENTIFIER_PATTERN = re.compile(r"[A-Za-z0-9_-]{1,128}\Z")
_SHA256_PATTERN = re.compile(r"[0-9a-f]{64}\Z")
_QUALIFIER_PATTERN = re.compile(r"^(?P<name>.+) \((?P<qualifier>Aura|Psychic)\)$")
_CATEGORY_BY_SOURCE_TYPE = {
    "Core": "Core",
    "Faction": "Faction",
    "Datasheet": "Datasheet",
    "Wargear": "Wargear",
    "Primarch": "Daemon Primarch choice",
    "Fortification (левая колонка)": "Datasheet sidebar rule",
}
_SURFACE_BY_SOURCE_TYPE = {
    "Core": "datasheet_ability",
    "Faction": "datasheet_ability",
    "Datasheet": "datasheet_ability",
    "Wargear": "wargear_item",
    "Primarch": "datasheet_sub_ability",
    "Fortification (левая колонка)": "datasheet_rule",
}


@dataclass(frozen=True, slots=True)
class ThirtyNineKProProviderObservation:
    target_edition: str
    audit_date: date
    faction_url: str
    faction_name: str
    publication_id: str
    publication_name: str
    publication_errata_date: str
    asset_url: str
    asset_sha256: str
    home_sha256: str


@dataclass(frozen=True, slots=True)
class ThirtyNineKProDatasheetObservation:
    source_datasheet_id: str
    source_datasheet_name: str
    observed_provider_url: str
    observed_provider_name: str
    evidence_sha256: str
    comparison_result: str
    discrepancy_assignment_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ThirtyNineKProAssignmentObservation:
    source_assignment_id: str
    source_datasheet_id: str
    source_ability_id: str | None
    source_assignment_name: str
    source_base_name: str
    source_qualifiers: tuple[str, ...]
    source_category: str
    audit_category: str
    observed_provider_datasheet_id: str
    observed_provider_surface: str
    observed_provider_assignment_id: str | None
    observed_provider_definition_id: str
    observed_provider_name: str
    observed_provider_qualifiers: tuple[str, ...]
    evidence_sha256: str
    match_status: str
    discrepancy_reason: str | None

    @property
    def observed_provider_identity(self) -> str:
        return _qualified_name(self.observed_provider_name, self.observed_provider_qualifiers)


@dataclass(frozen=True, slots=True)
class ThirtyNineKProDeltaObservation:
    source_operation_id: str
    subject: str
    field: str
    expected_value: str
    observed_provider_record_kind: str
    observed_provider_record_id: str
    observed_provider_datasheet_id: str
    observed_provider_value: str
    evidence_sha256: str
    comparison_result: str


@dataclass(frozen=True, slots=True)
class EmperorsChildrenThirtyNineKProAudit:
    provider: ThirtyNineKProProviderObservation
    datasheets: tuple[ThirtyNineKProDatasheetObservation, ...]
    assignments: tuple[ThirtyNineKProAssignmentObservation, ...]
    datasheet_deltas: tuple[ThirtyNineKProDeltaObservation, ...]

    def ability_category_rows(self) -> tuple[tuple[str, int, str], ...]:
        counts = Counter(row.audit_category for row in self.assignments)
        discrepancies = Counter(
            row.audit_category for row in self.assignments if row.match_status != "matched"
        )
        rows: list[tuple[str, int, str]] = []
        for category in _CATEGORY_BY_SOURCE_TYPE.values():
            count = counts[category]
            discrepancy_count = discrepancies[category]
            if discrepancy_count == 0:
                result = f"{count} assignments matched"
            else:
                result = (
                    f"{count - discrepancy_count} assignments matched; "
                    f"{discrepancy_count} retained provider relationship discrepancy"
                )
            rows.append((category, count, result))
        return tuple(rows)

    @property
    def assignment_discrepancies(self) -> tuple[ThirtyNineKProAssignmentObservation, ...]:
        return tuple(row for row in self.assignments if row.match_status != "matched")


@cache
def emperors_children_thirty_nine_k_pro_audit() -> EmperorsChildrenThirtyNineKProAudit:
    return load_emperors_children_thirty_nine_k_pro_audit(AUDIT_PATH)


def load_emperors_children_thirty_nine_k_pro_audit(
    path: Path,
) -> EmperorsChildrenThirtyNineKProAudit:
    payload = _load_json_object(path)
    _require_exact_keys(
        payload,
        {
            "schema_version",
            "provider",
            "source_snapshot",
            "datasheets",
            "assignments",
            "datasheet_deltas",
        },
        "39k PRO audit",
    )
    if payload["schema_version"] != AUDIT_SCHEMA_VERSION:
        raise ValueError("Emperor's Children 39k PRO audit has an unsupported schema version.")

    provider = _parse_provider(payload["provider"])
    _validate_source_snapshot(payload["source_snapshot"])
    datasheets = tuple(_parse_datasheet(row) for row in _required_list(payload, "datasheets"))
    assignments = tuple(_parse_assignment(row) for row in _required_list(payload, "assignments"))
    datasheet_deltas = tuple(
        _parse_delta(row) for row in _required_list(payload, "datasheet_deltas")
    )
    _validate_datasheets(datasheets, assignments)
    _validate_source_assignments(datasheets, assignments)
    _validate_provider_assignments(datasheets, assignments)
    _validate_deltas(datasheets, assignments, datasheet_deltas)
    return EmperorsChildrenThirtyNineKProAudit(
        provider=provider,
        datasheets=datasheets,
        assignments=assignments,
        datasheet_deltas=datasheet_deltas,
    )


def _parse_provider(raw: object) -> ThirtyNineKProProviderObservation:
    payload = _object(raw, "provider")
    _require_exact_keys(
        payload,
        {
            "target_edition",
            "audit_date",
            "faction_url",
            "faction_name",
            "publication_id",
            "publication_name",
            "publication_errata_date",
            "asset_url",
            "asset_sha256",
            "home_sha256",
        },
        "provider",
    )
    target_edition = _required_text(payload, "target_edition")
    if target_edition != THIRTY_NINE_K_PRO_TARGET_EDITION:
        raise ValueError("39k PRO audit target edition drifted.")
    faction_reference = verify_thirty_nine_k_pro_reference_url(
        target_edition=target_edition,
        expected_kind=ExternalReferenceKind.FACTION,
        reference_url=_required_text(payload, "faction_url"),
    )
    asset_url = _required_text(payload, "asset_url")
    parsed_asset_url = urlsplit(asset_url)
    if (
        parsed_asset_url.scheme != "https"
        or parsed_asset_url.netloc != "39k.pro"
        or not parsed_asset_url.path.startswith("/assets/")
        or parsed_asset_url.query
        or parsed_asset_url.fragment
    ):
        raise ValueError("39k PRO audit asset URL is not a canonical HTTPS provider asset URL.")
    try:
        audit_date = date.fromisoformat(_required_text(payload, "audit_date"))
    except ValueError as exc:
        raise ValueError("39k PRO audit date must be ISO-8601.") from exc
    return ThirtyNineKProProviderObservation(
        target_edition=target_edition,
        audit_date=audit_date,
        faction_url=faction_reference.reference_url,
        faction_name=_required_text(payload, "faction_name"),
        publication_id=_provider_identifier(payload, "publication_id"),
        publication_name=_required_text(payload, "publication_name"),
        publication_errata_date=_required_text(payload, "publication_errata_date"),
        asset_url=asset_url,
        asset_sha256=_required_sha256(payload, "asset_sha256"),
        home_sha256=_required_sha256(payload, "home_sha256"),
    )


def _parse_datasheet(raw: object) -> ThirtyNineKProDatasheetObservation:
    payload = _object(raw, "datasheet observation")
    _require_exact_keys(
        payload,
        {
            "source_datasheet_id",
            "source_datasheet_name",
            "observed_provider_url",
            "observed_provider_name",
            "evidence_sha256",
            "comparison_result",
            "discrepancy_assignment_ids",
        },
        "datasheet observation",
    )
    reference = verify_thirty_nine_k_pro_reference_url(
        target_edition=THIRTY_NINE_K_PRO_TARGET_EDITION,
        expected_kind=ExternalReferenceKind.DATASHEET,
        reference_url=_required_text(payload, "observed_provider_url"),
    )
    discrepancy_assignment_ids = tuple(
        _text(value, "discrepancy assignment ID")
        for value in _required_list(payload, "discrepancy_assignment_ids")
    )
    row = ThirtyNineKProDatasheetObservation(
        source_datasheet_id=_required_text(payload, "source_datasheet_id"),
        source_datasheet_name=_required_text(payload, "source_datasheet_name"),
        observed_provider_url=reference.reference_url,
        observed_provider_name=_required_text(payload, "observed_provider_name"),
        evidence_sha256=_required_sha256(payload, "evidence_sha256"),
        comparison_result=_required_text(payload, "comparison_result"),
        discrepancy_assignment_ids=discrepancy_assignment_ids,
    )
    evidence = {
        "observed_provider_name": row.observed_provider_name,
        "observed_provider_url": row.observed_provider_url,
    }
    if row.evidence_sha256 != _canonical_sha256(evidence):
        raise ValueError(f"39k PRO datasheet evidence hash drifted for {row.source_datasheet_id}.")
    return row


def _parse_assignment(raw: object) -> ThirtyNineKProAssignmentObservation:
    payload = _object(raw, "assignment observation")
    _require_exact_keys(
        payload,
        {
            "source_assignment_id",
            "source_datasheet_id",
            "source_ability_id",
            "source_assignment_name",
            "source_base_name",
            "source_qualifiers",
            "source_category",
            "audit_category",
            "observed_provider_datasheet_id",
            "observed_provider_surface",
            "observed_provider_assignment_id",
            "observed_provider_definition_id",
            "observed_provider_name",
            "observed_provider_qualifiers",
            "evidence_sha256",
            "match_status",
            "discrepancy_reason",
        },
        "assignment observation",
    )
    source_ability_id = _optional_text(payload, "source_ability_id")
    provider_assignment_id = _optional_provider_identifier(
        payload, "observed_provider_assignment_id"
    )
    discrepancy_reason = _optional_text(payload, "discrepancy_reason")
    row = ThirtyNineKProAssignmentObservation(
        source_assignment_id=_required_text(payload, "source_assignment_id"),
        source_datasheet_id=_required_text(payload, "source_datasheet_id"),
        source_ability_id=source_ability_id,
        source_assignment_name=_required_text(payload, "source_assignment_name"),
        source_base_name=_required_text(payload, "source_base_name"),
        source_qualifiers=_qualifiers(payload, "source_qualifiers"),
        source_category=_required_text(payload, "source_category"),
        audit_category=_required_text(payload, "audit_category"),
        observed_provider_datasheet_id=_provider_identifier(
            payload, "observed_provider_datasheet_id"
        ),
        observed_provider_surface=_required_text(payload, "observed_provider_surface"),
        observed_provider_assignment_id=provider_assignment_id,
        observed_provider_definition_id=_provider_identifier(
            payload, "observed_provider_definition_id"
        ),
        observed_provider_name=_required_text(payload, "observed_provider_name"),
        observed_provider_qualifiers=_qualifiers(payload, "observed_provider_qualifiers"),
        evidence_sha256=_required_sha256(payload, "evidence_sha256"),
        match_status=_required_text(payload, "match_status"),
        discrepancy_reason=discrepancy_reason,
    )
    evidence = {
        "observed_provider_assignment_id": row.observed_provider_assignment_id,
        "observed_provider_datasheet_id": row.observed_provider_datasheet_id,
        "observed_provider_definition_id": row.observed_provider_definition_id,
        "observed_provider_name": row.observed_provider_name,
        "observed_provider_qualifiers": list(row.observed_provider_qualifiers),
        "observed_provider_surface": row.observed_provider_surface,
    }
    if row.evidence_sha256 != _canonical_sha256(evidence):
        raise ValueError(
            f"39k PRO assignment evidence hash drifted for {row.source_assignment_id}."
        )
    return row


def _parse_delta(raw: object) -> ThirtyNineKProDeltaObservation:
    payload = _object(raw, "datasheet delta observation")
    _require_exact_keys(
        payload,
        {
            "source_operation_id",
            "subject",
            "field",
            "expected_value",
            "observed_provider_record_kind",
            "observed_provider_record_id",
            "observed_provider_datasheet_id",
            "observed_provider_value",
            "evidence_sha256",
            "comparison_result",
        },
        "datasheet delta observation",
    )
    row = ThirtyNineKProDeltaObservation(
        source_operation_id=_required_text(payload, "source_operation_id"),
        subject=_required_text(payload, "subject"),
        field=_required_text(payload, "field"),
        expected_value=_required_text(payload, "expected_value"),
        observed_provider_record_kind=_required_text(payload, "observed_provider_record_kind"),
        observed_provider_record_id=_provider_identifier(payload, "observed_provider_record_id"),
        observed_provider_datasheet_id=_provider_identifier(
            payload, "observed_provider_datasheet_id"
        ),
        observed_provider_value=_required_text(payload, "observed_provider_value"),
        evidence_sha256=_required_sha256(payload, "evidence_sha256"),
        comparison_result=_required_text(payload, "comparison_result"),
    )
    evidence = {
        "field": row.field,
        "observed_provider_datasheet_id": row.observed_provider_datasheet_id,
        "observed_provider_record_id": row.observed_provider_record_id,
        "observed_provider_record_kind": row.observed_provider_record_kind,
        "observed_provider_value": row.observed_provider_value,
    }
    if row.evidence_sha256 != _canonical_sha256(evidence):
        raise ValueError(
            f"39k PRO delta evidence hash drifted for {row.source_operation_id}:{row.field}."
        )
    return row


def _validate_source_snapshot(raw: object) -> None:
    payload = _object(raw, "source_snapshot")
    _require_exact_keys(
        payload,
        {"source_package_id", "artifacts"},
        "source_snapshot",
    )
    package_id = _object(payload["source_package_id"], "source package ID")
    _require_exact_keys(package_id, {"namespace", "package_name", "version"}, "source package ID")
    artifacts = _object(payload["artifacts"], "source artifacts")
    expected_filenames = {"Datasheets.json", "Datasheets_abilities.json", "Abilities.json"}
    if set(artifacts) != expected_filenames:
        raise ValueError("39k PRO audit source artifact inventory drifted.")
    for filename in sorted(expected_filenames):
        record = _object(artifacts[filename], f"source artifact {filename}")
        _require_exact_keys(record, {"artifact_hash", "file_sha256"}, f"source artifact {filename}")
        source_path = SOURCE_DIR / filename
        source_payload = _load_json_object(source_path)
        if source_payload.get("source_package_id") != package_id:
            raise ValueError(f"39k PRO audit source package drifted for {filename}.")
        if source_payload.get("artifact_hash") != _required_sha256(record, "artifact_hash"):
            raise ValueError(f"39k PRO audit source artifact hash drifted for {filename}.")
        if _sha256(source_path) != _required_sha256(record, "file_sha256"):
            raise ValueError(f"39k PRO audit source file hash drifted for {filename}.")


def _validate_datasheets(
    datasheets: tuple[ThirtyNineKProDatasheetObservation, ...],
    assignments: tuple[ThirtyNineKProAssignmentObservation, ...],
) -> None:
    if not datasheets:
        raise ValueError("39k PRO audit must retain datasheet observations.")
    source_ids = tuple(row.source_datasheet_id for row in datasheets)
    provider_urls = tuple(row.observed_provider_url for row in datasheets)
    if len(source_ids) != len(set(source_ids)):
        raise ValueError("39k PRO audit contains duplicate source datasheet IDs.")
    if len(provider_urls) != len(set(provider_urls)):
        raise ValueError("39k PRO audit contains duplicate provider datasheet URLs.")

    source_payload = _load_json_object(SOURCE_DIR / "Datasheets.json")
    names_by_id: dict[str, str] = {}
    for raw_source_row in _required_list(source_payload, "rows"):
        source_row = _object(raw_source_row, "source datasheet row")
        fields = _object(source_row.get("fields"), "source datasheet fields")
        names_by_id[_required_text(fields, "id")] = _required_text(fields, "name")
    assignments_by_datasheet: dict[str, list[str]] = {source_id: [] for source_id in source_ids}
    for assignment in assignments:
        if assignment.source_datasheet_id not in assignments_by_datasheet:
            raise ValueError("39k PRO assignment references an unobserved datasheet.")
        if assignment.match_status != "matched":
            assignments_by_datasheet[assignment.source_datasheet_id].append(
                assignment.source_assignment_id
            )
    for row in datasheets:
        if names_by_id.get(row.source_datasheet_id) != row.source_datasheet_name:
            raise ValueError(
                f"39k PRO source datasheet name drifted for {row.source_datasheet_id}."
            )
        if _normalized_identity(row.source_datasheet_name, ()) != _normalized_identity(
            row.observed_provider_name, ()
        ):
            raise ValueError(
                f"39k PRO provider datasheet name mismatched for {row.source_datasheet_id}."
            )
        discrepancy_ids = tuple(sorted(assignments_by_datasheet[row.source_datasheet_id]))
        if tuple(sorted(row.discrepancy_assignment_ids)) != discrepancy_ids:
            raise ValueError(
                f"39k PRO datasheet discrepancy inventory drifted for {row.source_datasheet_id}."
            )
        expected_result = (
            "matched" if not discrepancy_ids else "matched_with_assignment_discrepancies"
        )
        if row.comparison_result != expected_result:
            raise ValueError(
                f"39k PRO datasheet comparison result drifted for {row.source_datasheet_id}."
            )


def _validate_source_assignments(
    datasheets: tuple[ThirtyNineKProDatasheetObservation, ...],
    assignments: tuple[ThirtyNineKProAssignmentObservation, ...],
) -> None:
    datasheet_ids = {row.source_datasheet_id for row in datasheets}
    abilities_payload = _load_json_object(SOURCE_DIR / "Abilities.json")
    ability_names: dict[str, str] = {}
    for raw_ability_row in _required_list(abilities_payload, "rows"):
        ability_row = _object(raw_ability_row, "source ability row")
        fields = _object(ability_row.get("fields"), "source ability fields")
        ability_names[_required_text(fields, "id")] = _required_text(fields, "name")
    source_payload = _load_json_object(SOURCE_DIR / "Datasheets_abilities.json")
    expected: dict[str, tuple[str, str | None, str, str, tuple[str, ...], str, str]] = {}
    for raw_row in _required_list(source_payload, "rows"):
        row = _object(raw_row, "source assignment row")
        fields = _object(row.get("fields"), "source assignment fields")
        datasheet_id = _required_text(fields, "datasheet_id")
        if datasheet_id not in datasheet_ids:
            continue
        source_assignment_id = _required_text(row, "source_row_id")
        ability_id = _source_optional_text(fields, "ability_id")
        name = _source_optional_text(fields, "name")
        if name is None:
            if ability_id is None or ability_id not in ability_names:
                raise ValueError(
                    f"Source assignment {source_assignment_id} has no resolvable name."
                )
            name = ability_names[ability_id]
        parameter = _source_optional_text(fields, "parameter")
        if parameter is not None:
            name = f"{name} {parameter}"
        base_name, qualifiers = _split_qualified_name(name)
        source_category = _required_text(fields, "type")
        audit_category = _CATEGORY_BY_SOURCE_TYPE.get(source_category)
        if audit_category is None:
            raise ValueError(f"Unknown 39k PRO audit source category {source_category!r}.")
        expected[source_assignment_id] = (
            datasheet_id,
            ability_id,
            name,
            base_name,
            qualifiers,
            source_category,
            audit_category,
        )

    actual_ids = tuple(row.source_assignment_id for row in assignments)
    if len(actual_ids) != len(set(actual_ids)):
        raise ValueError("39k PRO audit contains duplicate source assignment IDs.")
    if set(actual_ids) != set(expected):
        raise ValueError("39k PRO audit must retain every source assignment exactly once.")
    for audit_row in assignments:
        actual = (
            audit_row.source_datasheet_id,
            audit_row.source_ability_id,
            audit_row.source_assignment_name,
            audit_row.source_base_name,
            audit_row.source_qualifiers,
            audit_row.source_category,
            audit_row.audit_category,
        )
        if actual != expected[audit_row.source_assignment_id]:
            raise ValueError(
                f"39k PRO source assignment identity drifted for {audit_row.source_assignment_id}."
            )


def _validate_provider_assignments(
    datasheets: tuple[ThirtyNineKProDatasheetObservation, ...],
    assignments: tuple[ThirtyNineKProAssignmentObservation, ...],
) -> None:
    provider_datasheet_ids_by_source = _provider_datasheet_ids_by_source(datasheets)
    relationship_ids = tuple(
        row.observed_provider_assignment_id
        for row in assignments
        if row.observed_provider_assignment_id is not None
    )
    if len(relationship_ids) != len(set(relationship_ids)):
        raise ValueError("39k PRO audit contains duplicate provider relationship IDs.")
    for row in assignments:
        if (
            provider_datasheet_ids_by_source.get(row.source_datasheet_id)
            != row.observed_provider_datasheet_id
        ):
            raise ValueError(
                f"Provider parent datasheet mismatched for {row.source_assignment_id}."
            )
        expected_surface = _SURFACE_BY_SOURCE_TYPE[row.source_category]
        if row.match_status == "matched":
            if row.observed_provider_assignment_id is None:
                raise ValueError(
                    f"Matched assignment {row.source_assignment_id} has no relationship ID."
                )
            if row.observed_provider_surface != expected_surface:
                raise ValueError(f"Provider surface drifted for {row.source_assignment_id}.")
            if row.discrepancy_reason is not None:
                raise ValueError(
                    f"Matched assignment {row.source_assignment_id} has a discrepancy."
                )
        elif row.match_status == "provider_definition_unassigned":
            if row.source_category != "Datasheet":
                raise ValueError("Only datasheet abilities may retain an unassigned definition.")
            if row.observed_provider_assignment_id is not None:
                raise ValueError("Unassigned provider definitions cannot have relationship IDs.")
            if row.observed_provider_surface != "datasheet_ability_definition":
                raise ValueError("Unassigned provider definitions require the definition surface.")
            if row.discrepancy_reason is None:
                raise ValueError("Unassigned provider definitions require a discrepancy reason.")
        else:
            raise ValueError(f"Unknown provider assignment match status {row.match_status!r}.")
        if _normalized_identity(
            row.source_base_name, row.source_qualifiers
        ) != _normalized_identity(row.observed_provider_name, row.observed_provider_qualifiers):
            raise ValueError(
                f"Provider assignment identity mismatched for {row.source_assignment_id}."
            )


def _validate_deltas(
    datasheets: tuple[ThirtyNineKProDatasheetObservation, ...],
    assignments: tuple[ThirtyNineKProAssignmentObservation, ...],
    deltas: tuple[ThirtyNineKProDeltaObservation, ...],
) -> None:
    if not deltas:
        raise ValueError("39k PRO audit must retain datasheet delta observations.")
    operation_fields = tuple((row.source_operation_id, row.field) for row in deltas)
    if len(operation_fields) != len(set(operation_fields)):
        raise ValueError("39k PRO audit contains duplicate datasheet delta fields.")
    operations = {
        operation.op_id: operation for operation in source_overlay.overlay_pack().operations
    }
    assignments_by_id = {row.source_assignment_id: row for row in assignments}
    provider_datasheet_ids_by_source = _provider_datasheet_ids_by_source(datasheets)
    for row in deltas:
        operation = operations.get(row.source_operation_id)
        if operation is None:
            raise ValueError(
                f"Unknown source operation in 39k PRO audit: {row.source_operation_id}."
            )
        operation_fields_by_name = dict(operation.fields)
        source_datasheet_id = operation.source_row_id.split(":", 1)[0]
        expected_provider_datasheet_id = provider_datasheet_ids_by_source.get(source_datasheet_id)
        if expected_provider_datasheet_id is None:
            raise ValueError(
                f"39k PRO delta references an unaudited source datasheet: {source_datasheet_id}."
            )
        if row.observed_provider_datasheet_id != expected_provider_datasheet_id:
            raise ValueError(
                f"Provider parent datasheet mismatched for delta {row.source_operation_id}."
            )
        expected_record_kind = _provider_record_kind_for_delta(operation)
        if row.observed_provider_record_kind != expected_record_kind:
            raise ValueError(f"Provider record kind drifted for delta {row.source_operation_id}.")
        if operation.source_table == "Datasheets_abilities":
            assignment = assignments_by_id.get(operation.source_row_id)
            if assignment is None:
                raise ValueError(
                    f"39k PRO ability delta has no assignment evidence: {operation.source_row_id}."
                )
            if (
                row.observed_provider_record_id != assignment.observed_provider_definition_id
                or row.observed_provider_datasheet_id != assignment.observed_provider_datasheet_id
            ):
                raise ValueError(
                    f"Provider ability evidence drifted for delta {row.source_operation_id}."
                )
        if (
            operation.operation_kind is SourceOverlayOperationKind.UPDATE_ROW
            and operation_fields_by_name.get(row.field) != row.expected_value
        ):
            raise ValueError(f"39k PRO delta source value drifted for {row.source_operation_id}.")
        if operation.operation_kind is SourceOverlayOperationKind.ADD_ROW and (
            row.field != "presence" or row.expected_value != "present"
        ):
            raise ValueError("Added keyword observations must record expected presence.")
        if operation.operation_kind is SourceOverlayOperationKind.SUPERSEDE_ROW and (
            row.field != "presence" or row.expected_value != "absent"
        ):
            raise ValueError("Superseded keyword observations must record expected absence.")
        expected_result = (
            "matched" if row.expected_value == row.observed_provider_value else "mismatched"
        )
        if row.comparison_result != expected_result:
            raise ValueError(
                f"39k PRO datasheet delta result drifted for {row.source_operation_id}."
            )


def _provider_record_kind_for_delta(
    operation: SourceOverlayOperation,
) -> str:
    if operation.source_table == "Datasheets_abilities":
        return "datasheet_ability"
    if operation.source_table == "Datasheets_wargear":
        return "wargear_item_profile"
    if operation.source_table == "Datasheets_models":
        return "miniature"
    if (
        operation.source_table == "Datasheets_keywords"
        and operation.operation_kind is SourceOverlayOperationKind.ADD_ROW
    ):
        return "miniature_keyword"
    if (
        operation.source_table == "Datasheets_keywords"
        and operation.operation_kind is SourceOverlayOperationKind.SUPERSEDE_ROW
    ):
        return "miniature_keyword_inventory"
    raise ValueError(f"Unsupported source operation for 39k PRO delta: {operation.op_id}.")


def _provider_datasheet_ids_by_source(
    datasheets: tuple[ThirtyNineKProDatasheetObservation, ...],
) -> dict[str, str]:
    return {
        row.source_datasheet_id: urlsplit(row.observed_provider_url).path.rsplit("/", 1)[-1]
        for row in datasheets
    }


def _split_qualified_name(value: str) -> tuple[str, tuple[str, ...]]:
    match = _QUALIFIER_PATTERN.fullmatch(value)
    if match is None:
        return value, ()
    return match.group("name"), (match.group("qualifier"),)


def _qualified_name(base_name: str, qualifiers: tuple[str, ...]) -> str:
    if not qualifiers:
        return base_name
    return f"{base_name} ({', '.join(qualifiers)})"


def _normalized_identity(
    base_name: str, qualifiers: tuple[str, ...]
) -> tuple[str, tuple[str, ...]]:
    return (
        base_name.replace("\u2019", "'").casefold(),
        tuple(qualifier.casefold() for qualifier in qualifiers),
    )


def _qualifiers(payload: dict[str, Any], key: str) -> tuple[str, ...]:
    qualifiers = tuple(_text(value, key) for value in _required_list(payload, key))
    if len(qualifiers) != len(set(qualifiers)) or any(
        qualifier not in {"Aura", "Psychic"} for qualifier in qualifiers
    ):
        raise ValueError(f"39k PRO audit {key} contains invalid qualifiers.")
    return qualifiers


def _provider_identifier(payload: dict[str, Any], key: str) -> str:
    value = _required_text(payload, key)
    if _PROVIDER_IDENTIFIER_PATTERN.fullmatch(value) is None:
        raise ValueError(f"39k PRO audit {key} is not a provider identifier.")
    return value


def _optional_provider_identifier(payload: dict[str, Any], key: str) -> str | None:
    value = _optional_text(payload, key)
    if value is not None and _PROVIDER_IDENTIFIER_PATTERN.fullmatch(value) is None:
        raise ValueError(f"39k PRO audit {key} is not a provider identifier.")
    return value


def _required_sha256(payload: dict[str, Any], key: str) -> str:
    value = _required_text(payload, key)
    if _SHA256_PATTERN.fullmatch(value) is None:
        raise ValueError(f"39k PRO audit {key} must be a lowercase SHA-256 digest.")
    return value


def _canonical_sha256(payload: Mapping[str, object]) -> str:
    encoded = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_json_object(path: Path) -> dict[str, Any]:
    return _object(json.loads(path.read_text(encoding="utf-8")), str(path))


def _object(value: object, context: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise TypeError(f"{context} must be a JSON object with string keys.")
    untyped = cast(dict[object, object], value)
    if not all(isinstance(key, str) for key in untyped):
        raise ValueError(f"{context} must be a JSON object with string keys.")
    return cast(dict[str, Any], value)


def _required_list(payload: dict[str, Any], key: str) -> list[object]:
    value = payload.get(key)
    if not isinstance(value, list):
        raise TypeError(f"39k PRO audit {key} must be a list.")
    return cast(list[object], value)


def _required_text(payload: dict[str, Any], key: str) -> str:
    if key not in payload:
        raise ValueError(f"39k PRO audit is missing {key}.")
    return _text(payload[key], key)


def _optional_text(payload: dict[str, Any], key: str) -> str | None:
    if key not in payload:
        raise ValueError(f"39k PRO audit is missing {key}.")
    value = payload[key]
    return None if value is None else _text(value, key)


def _source_optional_text(payload: dict[str, Any], key: str) -> str | None:
    if key not in payload:
        raise ValueError(f"39k PRO audit source row is missing {key}.")
    value = payload[key]
    return None if value is None or value == "" else _text(value, key)


def _text(value: object, context: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise ValueError(f"39k PRO audit {context} must be non-empty trimmed text.")
    return value


def _require_exact_keys(payload: dict[str, Any], expected: set[str], context: str) -> None:
    if set(payload) != expected:
        raise ValueError(f"39k PRO audit {context} fields drifted.")
