from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from warhammer40k_core.rules.source_packages.warhammer_40000_11th import tacoma_open_2026

_WAHAPEDIA_SNAPSHOT = Path("data/source_snapshots/wahapedia/10th-edition/2026-06-14/json")


class Tacoma2026SourceAuditError(ValueError):
    """Raised when the event overlay's committed provenance or source assumption drifts."""


@dataclass(frozen=True, slots=True)
class Tacoma2026SourceAuditResult:
    source_pdf_sha256: str
    cult_ambush_datasheet_ids: tuple[str, ...]
    eligible_attaching_datasheet_ids: tuple[str, ...]


def audit_tacoma_2026_sources(repository_root: Path) -> Tacoma2026SourceAuditResult:
    root = repository_root.resolve()
    manifest = _json_object(
        _read_json(root / "docs/source_rules/tacoma-open-2026-source-package.json"),
        "Tacoma source-package manifest",
    )
    _verify_manifest_identity(manifest)
    pdf_path = root / "docs/source_rules" / _required_string(manifest, "source_pdf_filename")
    actual_pdf_hash = hashlib.sha256(pdf_path.read_bytes()).hexdigest()
    expected_pdf_hash = _required_string(manifest, "source_pdf_sha256")
    if actual_pdf_hash != expected_pdf_hash:
        raise Tacoma2026SourceAuditError(
            "Tacoma source PDF SHA-256 drifted from the committed source-package manifest."
        )

    snapshot_root = root / _WAHAPEDIA_SNAPSHOT
    datasheets = _artifact_rows(snapshot_root / "Datasheets.json")
    abilities = _artifact_rows(snapshot_root / "Abilities.json")
    datasheet_abilities = _artifact_rows(snapshot_root / "Datasheets_abilities.json")
    leader_rows = _artifact_rows(snapshot_root / "Datasheets_leader.json")
    keyword_rows = _artifact_rows(snapshot_root / "Datasheets_keywords.json")

    cult_ambush_ability_ids = {
        _required_string(fields, "id")
        for fields in abilities
        if fields.get("faction_id") == "GC" and fields.get("name") == "Cult Ambush"
    }
    if len(cult_ambush_ability_ids) != 1:
        raise Tacoma2026SourceAuditError(
            "Tacoma attachment audit requires exactly one Genestealer Cults Cult Ambush ability."
        )
    cult_ambush_datasheet_ids = {
        _required_string(fields, "datasheet_id")
        for fields in datasheet_abilities
        if fields.get("ability_id") in cult_ambush_ability_ids
    }
    if not cult_ambush_datasheet_ids:
        raise Tacoma2026SourceAuditError("Tacoma attachment audit found no Cult Ambush datasheets.")
    datasheet_by_id = {
        _required_string(fields, "id"): fields
        for fields in datasheets
        if fields.get("faction_id") == "GC"
    }
    unknown_cult_ambush_datasheets = cult_ambush_datasheet_ids - set(datasheet_by_id)
    if unknown_cult_ambush_datasheets:
        raise Tacoma2026SourceAuditError(
            "Tacoma attachment audit found Cult Ambush datasheets outside the Genestealer "
            "Cults source inventory: " + ", ".join(sorted(unknown_cult_ambush_datasheets))
        )
    attaching_datasheet_ids = {
        _required_string(fields, "leader_id")
        for fields in leader_rows
        if fields.get("attached_id") in cult_ambush_datasheet_ids
    }
    if not attaching_datasheet_ids:
        raise Tacoma2026SourceAuditError(
            "Tacoma attachment audit found no datasheets eligible to attach to Cult Ambush units."
        )
    character_datasheet_ids = {
        _required_string(fields, "datasheet_id")
        for fields in keyword_rows
        if str(fields.get("keyword", "")).upper() == "CHARACTER"
    }
    unknown_attachers = attaching_datasheet_ids - set(datasheet_by_id)
    if unknown_attachers:
        raise Tacoma2026SourceAuditError(
            "Tacoma attachment audit found attaching datasheets outside the Genestealer Cults "
            "source inventory: " + ", ".join(sorted(unknown_attachers))
        )
    non_character_attachers = attaching_datasheet_ids - character_datasheet_ids
    if non_character_attachers:
        raise Tacoma2026SourceAuditError(
            "Tacoma Cult Ambush replacement does not support non-CHARACTER attached components; "
            "source coverage drifted for datasheets: " + ", ".join(sorted(non_character_attachers))
        )
    return Tacoma2026SourceAuditResult(
        source_pdf_sha256=actual_pdf_hash,
        cult_ambush_datasheet_ids=tuple(sorted(cult_ambush_datasheet_ids)),
        eligible_attaching_datasheet_ids=tuple(sorted(attaching_datasheet_ids)),
    )


def _verify_manifest_identity(manifest: dict[str, object]) -> None:
    expected = {
        "rules_overlay_id": tacoma_open_2026.RULES_OVERLAY_ID,
        "source_package_id": tacoma_open_2026.SOURCE_PACKAGE_ID,
        "cult_ambush_attached_character_exclusion_source_id": (
            tacoma_open_2026.CULT_AMBUSH_ATTACHED_CHARACTER_EXCLUSION_SOURCE_ID
        ),
        "source_pdf_filename": tacoma_open_2026.SOURCE_PDF_FILENAME,
        "source_pdf_sha256": tacoma_open_2026.SOURCE_PDF_SHA256,
        "scope": "warhammer_open_tacoma_2026_only",
    }
    for field_name, expected_value in expected.items():
        if manifest.get(field_name) != expected_value:
            raise Tacoma2026SourceAuditError(
                f"Tacoma source-package manifest {field_name} drifted."
            )


def _artifact_rows(path: Path) -> tuple[dict[str, object], ...]:
    artifact = _json_object(_read_json(path), str(path))
    rows = artifact.get("rows")
    if type(rows) is not list:
        raise Tacoma2026SourceAuditError(f"{path} rows must be a list.")
    fields: list[dict[str, object]] = []
    for index, row in enumerate(cast(list[object], rows)):
        row_object = _json_object(row, f"{path} row {index}")
        fields.append(_json_object(row_object.get("fields"), f"{path} row {index} fields"))
    return tuple(fields)


def _read_json(path: Path) -> object:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        message = f"Required Tacoma audit source is missing: {path}"
        raise Tacoma2026SourceAuditError(message) from exc
    except json.JSONDecodeError as exc:
        raise Tacoma2026SourceAuditError(f"Tacoma audit source is malformed JSON: {path}") from exc


def _json_object(value: object, label: str) -> dict[str, object]:
    if type(value) is not dict:
        raise Tacoma2026SourceAuditError(f"{label} must be a JSON object.")
    return cast(dict[str, object], value)


def _required_string(payload: dict[str, object], field_name: str) -> str:
    value = payload.get(field_name)
    if type(value) is not str or not value:
        raise Tacoma2026SourceAuditError(f"Tacoma audit field {field_name} must be a string.")
    return value
