from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from warhammer40k_core.core.datasheet import BaseSizeDefinition, BaseSizeKind
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    event_companion_2026_06 as event_companion_source,
)
from warhammer40k_core.rules.wahapedia_schema import NormalizedSourceRow

EVENT_COMPANION_BASE_SIZE_GUIDE_SOURCE_ID = (
    "pdf:warhammer40000-event-companion:2026-06-12:base-size-guide"
)
EVENT_COMPANION_BASE_SIZE_GUIDE_DOCUMENT_REFERENCE = (
    "docs/source_rules/eng_12-06_warhammer40000_event_companion-s3bfb5f9s1-ivswuij3fo.pdf"
)


@dataclass(frozen=True, slots=True)
class BaseSizeBridgeEvidence:
    base_size_text: str
    source_id: str
    document_reference: str
    source_ids: tuple[str, ...]


type EventCompanionBaseSizesByKey = dict[
    tuple[str, str], event_companion_source.BaseSizeSourceRecord
]


def event_companion_base_sizes_by_key(
    *,
    error_type: type[ValueError],
) -> EventCompanionBaseSizesByKey:
    rows_by_key: dict[tuple[str, str], event_companion_source.BaseSizeSourceRecord] = {}
    for row in event_companion_source.base_size_source_rows():
        key = (_name_key(row.faction_name), _name_key(row.unit_name))
        if key in rows_by_key:
            raise error_type("Duplicate Event Companion base size row key.")
        rows_by_key[key] = row
    return rows_by_key


def base_size_evidence(
    *,
    faction_name: str,
    datasheet_name: str,
    model_name: str,
    model_source_row: NormalizedSourceRow,
    event_companion_base_sizes: dict[tuple[str, str], event_companion_source.BaseSizeSourceRecord],
    error_type: type[ValueError],
) -> BaseSizeBridgeEvidence:
    faction_key = _name_key(faction_name)
    record = event_companion_base_sizes.get(
        (faction_key, _name_key(f"{datasheet_name}: {model_name}"))
    )
    if record is None:
        record = event_companion_base_sizes.get((faction_key, _name_key(datasheet_name)))
    if record is None:
        fallback_source_id = model_source_row.stable_source_id()
        return BaseSizeBridgeEvidence(
            base_size_text=_required_field(model_source_row, "base_size", error_type=error_type),
            source_id=fallback_source_id,
            document_reference=fallback_source_id,
            source_ids=(fallback_source_id,),
        )
    if record.canonical_base_size is not None:
        return BaseSizeBridgeEvidence(
            base_size_text=_bridge_base_size_text(
                record.canonical_base_size, error_type=error_type
            ),
            source_id=record.source_id,
            document_reference=EVENT_COMPANION_BASE_SIZE_GUIDE_DOCUMENT_REFERENCE,
            source_ids=(EVENT_COMPANION_BASE_SIZE_GUIDE_SOURCE_ID, record.source_id),
        )
    source_base_size = _required_field(model_source_row, "base_size", error_type=error_type)
    flying_match = re.fullmatch(
        r"(?P<diameter>\d+(?:\.\d+)?)\s*mm\s+flying\s+base",
        source_base_size,
        re.IGNORECASE,
    )
    if flying_match is None:
        return BaseSizeBridgeEvidence(
            base_size_text=record.source_base_text,
            source_id=record.source_id,
            document_reference=EVENT_COMPANION_BASE_SIZE_GUIDE_DOCUMENT_REFERENCE,
            source_ids=(EVENT_COMPANION_BASE_SIZE_GUIDE_SOURCE_ID, record.source_id),
        )
    fallback_source_id = model_source_row.stable_source_id()
    return BaseSizeBridgeEvidence(
        base_size_text=f"{flying_match.group('diameter')}mm",
        source_id=fallback_source_id,
        document_reference=fallback_source_id,
        source_ids=(
            EVENT_COMPANION_BASE_SIZE_GUIDE_SOURCE_ID,
            record.source_id,
            fallback_source_id,
        ),
    )


def _bridge_base_size_text(
    base_size: BaseSizeDefinition,
    *,
    error_type: type[ValueError],
) -> str:
    if base_size.kind is BaseSizeKind.CIRCULAR:
        if base_size.diameter_mm is None:
            raise error_type("Circular base size record is missing diameter.")
        return f"{_millimeter_text(base_size.diameter_mm)}mm"
    if base_size.kind is BaseSizeKind.OVAL:
        if base_size.length_mm is None or base_size.width_mm is None:
            raise error_type("Oval base size record is missing dimensions.")
        return f"{_millimeter_text(base_size.length_mm)} x {_millimeter_text(base_size.width_mm)}mm"
    raise error_type("Unsupported Event Companion canonical base size kind.")


def _millimeter_text(value: float) -> str:
    return str(int(value)) if value.is_integer() else f"{value:g}"


def _required_field(
    row: NormalizedSourceRow,
    column_name: str,
    *,
    error_type: type[ValueError],
) -> str:
    fields = row.runtime_fields_payload()
    value = fields.get(column_name, "").strip()
    if not value:
        raise error_type(f"Required source column is empty: {column_name}.")
    return value


def _name_key(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    ascii_value = "".join(
        character for character in normalized if not unicodedata.combining(character)
    )
    return " ".join(ascii_value.casefold().replace("\N{RIGHT SINGLE QUOTATION MARK}", "'").split())
