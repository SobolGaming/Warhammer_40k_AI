from __future__ import annotations

from typing import Final

import msgspec

from warhammer40k_core.core.missions import MissionPackError
from warhammer40k_core.rules.source_packages.artifact_loader import (
    SourcePackageArtifactError,
    package_artifact_bytes,
)

_ARTIFACT_SCHEMA: Final = "core-v2-event-companion-base-size-rows-v1"
_ARTIFACT_PACKAGE: Final = "warhammer40k_core.rules.source_packages.warhammer_40000_11th"
_ARTIFACT_PATH: Final = "event_companion_base_size_rows.json"
_SOURCE_PACKAGE_ID: Final = "gw-11e-warhammer-event-companion-v1-1-2026-07"
_SOURCE_VERSION: Final = "1.1"


class _BaseSizeSourceRowArtifact(msgspec.Struct, frozen=True):
    record_id: str
    source_page: int
    faction_name: str
    source_section_name: str | None
    unit_name: str
    source_base_text: str

    def to_source_row(self) -> tuple[str, int, str, str | None, str, str]:
        return (
            self.record_id,
            self.source_page,
            self.faction_name,
            self.source_section_name,
            self.unit_name,
            self.source_base_text,
        )


class _BaseSizeRowsArtifact(msgspec.Struct, frozen=True):
    artifact_schema: str
    source_package_id: str
    source_version: str
    rows: list[_BaseSizeSourceRowArtifact]


def _load_base_size_source_rows() -> tuple[tuple[str, int, str, str | None, str, str], ...]:
    try:
        raw = package_artifact_bytes(_ARTIFACT_PACKAGE, _ARTIFACT_PATH)
    except SourcePackageArtifactError as exc:
        raise MissionPackError("Event Companion base-size artifact could not be loaded.") from exc
    try:
        artifact = msgspec.json.decode(raw, type=_BaseSizeRowsArtifact)
    except msgspec.DecodeError as exc:
        raise MissionPackError("Event Companion base-size artifact is invalid.") from exc
    _validate_artifact(artifact)
    return tuple(row.to_source_row() for row in artifact.rows)


def _validate_artifact(artifact: _BaseSizeRowsArtifact) -> None:
    if artifact.artifact_schema != _ARTIFACT_SCHEMA:
        raise MissionPackError("Event Companion base-size artifact schema is unsupported.")
    if artifact.source_package_id != _SOURCE_PACKAGE_ID:
        raise MissionPackError("Event Companion base-size artifact source package drifted.")
    if artifact.source_version != _SOURCE_VERSION:
        raise MissionPackError("Event Companion base-size artifact source version drifted.")
    if not artifact.rows:
        raise MissionPackError("Event Companion base-size artifact must contain rows.")
    seen_record_ids: set[str] = set()
    for row in artifact.rows:
        _validate_row(row)
        if row.record_id in seen_record_ids:
            raise MissionPackError("Event Companion base-size record IDs must not duplicate.")
        seen_record_ids.add(row.record_id)


def _validate_row(row: _BaseSizeSourceRowArtifact) -> None:
    _validate_text("record_id", row.record_id)
    if row.source_page <= 0:
        raise MissionPackError("Event Companion base-size source_page must be positive.")
    _validate_text("faction_name", row.faction_name)
    if row.source_section_name is not None:
        _validate_text("source_section_name", row.source_section_name)
    _validate_text("unit_name", row.unit_name)
    _validate_text("source_base_text", row.source_base_text)


def _validate_text(field_name: str, value: str) -> None:
    if not value.strip():
        raise MissionPackError(f"Event Companion base-size {field_name} must not be empty.")


BASE_SIZE_SOURCE_ROWS: tuple[tuple[str, int, str, str | None, str, str], ...] = (
    _load_base_size_source_rows()
)
