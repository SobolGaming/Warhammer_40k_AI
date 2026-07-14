from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass
from typing import cast

from warhammer40k_core.core.datasheet import (
    MUSTERING_WARLORD_FORBIDDEN,
    MUSTERING_WARLORD_REQUIRED,
    MUSTERING_WARLORD_RULE_KEY,
    CatalogAbilitySourceKind,
    CatalogAbilitySupport,
    CatalogJsonObject,
    DatasheetAbilityDescriptor,
)
from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.rules.rule_compiler import compile_rule_source_text
from warhammer40k_core.rules.rule_ir import RuleIR, RuleIRPayload
from warhammer40k_core.rules.source_data import RuleSourceText
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    datasheet_keyword_lexicon_2026_06_14 as datasheet_keyword_lexicon_source,
)
from warhammer40k_core.rules.wahapedia_bridge_rows import (
    BridgeSourceArtifact,
    bridge_rows_by_table,
    resolve_bridge_ability_source_row,
)
from warhammer40k_core.rules.wahapedia_schema import NormalizedSourceRow
from warhammer40k_core.rules.wahapedia_static_rule_ir import payload_by_source_row_id


class WahapediaDatasheetAbilityBridgeError(ValueError):
    """Raised when exact datasheet ability source rows cannot be bridged."""


@dataclass(frozen=True, slots=True)
class BridgedDatasheetAbility:
    datasheet_id: str
    source_row_id: str
    ability_type: str
    raw_description: str
    normalized_description: str
    source_ids: tuple[str, ...]
    descriptor: DatasheetAbilityDescriptor


_SOURCE_KEYWORD_SEQUENCE_PARTS = (
    datasheet_keyword_lexicon_source.canonical_datasheet_keyword_sequence_parts()
)


def bridge_datasheet_abilities(
    *,
    source_artifacts: tuple[BridgeSourceArtifact, ...],
    datasheet_ids: tuple[str, ...],
) -> tuple[BridgedDatasheetAbility, ...]:
    if type(source_artifacts) is not tuple or not source_artifacts:
        raise WahapediaDatasheetAbilityBridgeError(
            "Datasheet ability bridge requires source artifacts."
        )
    selected_ids = _validate_identifier_tuple("datasheet_ids", datasheet_ids)
    if not selected_ids:
        raise WahapediaDatasheetAbilityBridgeError(
            "Datasheet ability bridge requires datasheet IDs."
        )
    rows_by_table = bridge_rows_by_table(
        source_artifacts,
        error_type=WahapediaDatasheetAbilityBridgeError,
    )
    datasheet_rows_by_id = {
        _required_field(row, "id"): row for row in rows_by_table.get("Datasheets", ())
    }
    bridged: list[BridgedDatasheetAbility] = []
    for datasheet_id in selected_ids:
        if datasheet_id not in datasheet_rows_by_id:
            raise WahapediaDatasheetAbilityBridgeError(
                "Datasheet ability bridge could not resolve a selected datasheet."
            )
        source_rows = _rows_matching(
            rows_by_table,
            "Datasheets_abilities",
            "datasheet_id",
            datasheet_id,
        )
        if not source_rows:
            raise WahapediaDatasheetAbilityBridgeError(
                "Datasheet ability bridge requires at least one ability row per datasheet."
            )
        initial_count = len(bridged)
        for source_row in source_rows:
            source_kind = _ability_source_kind(_required_field(source_row, "type"))
            if source_kind not in {
                CatalogAbilitySourceKind.DATASHEET,
                CatalogAbilitySourceKind.WARGEAR,
            }:
                continue
            bridged.append(
                _bridge_ability(
                    rows_by_table=rows_by_table,
                    source_row=source_row,
                    datasheet_id=datasheet_id,
                )
            )
        if len(bridged) == initial_count:
            raise WahapediaDatasheetAbilityBridgeError(
                "Datasheet ability bridge requires exact datasheet or wargear abilities."
            )
    return tuple(
        sorted(
            bridged,
            key=lambda row: (
                row.datasheet_id,
                row.descriptor.source_kind.value,
                row.descriptor.name.casefold(),
                row.descriptor.ability_id,
            ),
        )
    )


def _bridge_ability(
    *,
    rows_by_table: dict[str, tuple[NormalizedSourceRow, ...]],
    source_row: NormalizedSourceRow,
    datasheet_id: str,
) -> BridgedDatasheetAbility:
    ability_id = _required_field(source_row, "ability_id")
    resolved_row = source_row
    source_rows: tuple[NormalizedSourceRow, ...] = (source_row,)
    if ability_id:
        resolved_row = resolve_bridge_ability_source_row(
            rows_by_table=rows_by_table,
            ability_row=source_row,
            error_type=WahapediaDatasheetAbilityBridgeError,
        )
        source_rows = (source_row, resolved_row)
    name = _raw_or_field(resolved_row, "name")
    if not ability_id:
        ability_id = f"{datasheet_id}:{_slug(name)}"
    ability_type = _required_field(source_row, "type")
    source_kind = _ability_source_kind(ability_type)
    source_text = _rule_source_text_from_row_field(row=resolved_row, column_name="description")
    support = CatalogAbilitySupport.DESCRIPTOR_ONLY
    rule_ir_payload: CatalogJsonObject | None = None
    diagnostics: tuple[CatalogJsonObject, ...] = ()
    if source_kind in {CatalogAbilitySourceKind.DATASHEET, CatalogAbilitySourceKind.WARGEAR}:
        mustering_value = (
            _mustering_warlord_value(source_text.normalized_text)
            if source_kind is CatalogAbilitySourceKind.DATASHEET
            else None
        )
        if mustering_value is not None:
            rule_ir_payload = {MUSTERING_WARLORD_RULE_KEY: mustering_value}
        else:
            static_payload = payload_by_source_row_id(resolved_row.source_row_id)
            if static_payload is not None:
                rule_ir_payload = cast(CatalogJsonObject, static_payload)
                support = CatalogAbilitySupport.GENERIC_RULE_IR
            else:
                compiled = compile_rule_source_text(
                    source_text,
                    source_keyword_sequence_parts=_SOURCE_KEYWORD_SEQUENCE_PARTS,
                )
                rule_ir_payload = cast(CatalogJsonObject, compiled.rule_ir.to_payload())
                diagnostics = _rule_ir_diagnostics(compiled.rule_ir)
                support = (
                    CatalogAbilitySupport.GENERIC_RULE_IR
                    if compiled.rule_ir.is_supported
                    else CatalogAbilitySupport.UNSUPPORTED
                )
    descriptor = DatasheetAbilityDescriptor(
        ability_id=ability_id,
        name=name,
        source_id=resolved_row.stable_source_id(),
        support=support,
        source_kind=source_kind,
        effect_description=source_text.normalized_text,
        timing_tags=(),
        parameter_tokens=(),
        source_wargear_id=(
            _source_wargear_id(
                rows_by_table=rows_by_table,
                datasheet_id=datasheet_id,
                ability_name=name,
                ability_type=ability_type,
            )
            if source_kind is CatalogAbilitySourceKind.WARGEAR
            else None
        ),
        rule_ir_payload=rule_ir_payload,
        rule_ir_diagnostics=diagnostics,
    )
    return BridgedDatasheetAbility(
        datasheet_id=datasheet_id,
        source_row_id=source_row.source_row_id,
        ability_type=ability_type,
        raw_description=source_text.raw_text,
        normalized_description=source_text.normalized_text,
        source_ids=_source_ids(*source_rows),
        descriptor=descriptor,
    )


def _source_wargear_id(
    *,
    rows_by_table: dict[str, tuple[NormalizedSourceRow, ...]],
    datasheet_id: str,
    ability_name: str,
    ability_type: str,
) -> str:
    if ability_type.casefold() != "wargear profile":
        return f"{datasheet_id}:{_slug(ability_name)}"
    ability_key = _slug(ability_name)
    owner_names: set[str] = set()
    for row in _rows_matching(
        rows_by_table,
        "Datasheets_wargear",
        "datasheet_id",
        datasheet_id,
    ):
        description = _required_field(row, "description")
        if ability_key not in {_slug(part) for part in description.split(",") if part.strip()}:
            continue
        owner_names.add(_required_field(row, "name").split(" - ", maxsplit=1)[0])
    if len(owner_names) != 1:
        raise WahapediaDatasheetAbilityBridgeError(
            "Wargear profile ability must map to exactly one wargear item."
        )
    return f"{datasheet_id}:{_slug(next(iter(owner_names)))}"


def _rule_ir_diagnostics(rule_ir: RuleIR) -> tuple[CatalogJsonObject, ...]:
    diagnostics: list[CatalogJsonObject] = []
    for diagnostic in rule_ir.diagnostics:
        diagnostics.append(
            {
                "scope": "rule",
                "reason": diagnostic.reason.value,
                "message": diagnostic.message,
                "source_span": cast(CatalogJsonObject, diagnostic.source_span.to_payload()),
                "blocking": diagnostic.blocking,
            }
        )
    for clause in rule_ir.clauses:
        for diagnostic in clause.diagnostics:
            diagnostics.append(
                {
                    "scope": "clause",
                    "clause_id": clause.clause_id,
                    "reason": diagnostic.reason.value,
                    "message": diagnostic.message,
                    "source_span": cast(CatalogJsonObject, diagnostic.source_span.to_payload()),
                    "blocking": diagnostic.blocking,
                }
            )
    return tuple(diagnostics)


def _rule_source_text_from_row_field(
    *,
    row: NormalizedSourceRow,
    column_name: str,
) -> RuleSourceText:
    for text_field in row.text_fields:
        if text_field.column_name == column_name:
            return RuleSourceText(
                source_id=text_field.source_text_id,
                raw_text=text_field.sanitized_text,
                normalized_text=text_field.normalized_text,
                parsed_tokens=text_field.parsed_tokens,
            )
    return RuleSourceText.from_raw(
        source_id=f"{row.stable_source_id()}:{column_name}",
        raw_text=row.runtime_fields_payload().get(column_name, ""),
    )


def _mustering_warlord_value(normalized_description: str) -> str | None:
    upper = normalized_description.upper()
    if "CANNOT BE YOUR WARLORD" in upper:
        return MUSTERING_WARLORD_FORBIDDEN
    if "MUST BE YOUR WARLORD" in upper:
        return MUSTERING_WARLORD_REQUIRED
    return None


def _ability_source_kind(ability_type: str) -> CatalogAbilitySourceKind:
    normalized = ability_type.strip().casefold()
    if normalized == "core":
        return CatalogAbilitySourceKind.CORE
    if normalized == "faction":
        return CatalogAbilitySourceKind.FACTION
    if normalized == "datasheet":
        return CatalogAbilitySourceKind.DATASHEET
    if normalized in {"wargear", "wargear profile"}:
        return CatalogAbilitySourceKind.WARGEAR
    if normalized == "primarch" or normalized.startswith(("special", "fortification")):
        return CatalogAbilitySourceKind.DATASHEET
    raise WahapediaDatasheetAbilityBridgeError("Unsupported datasheet ability type.")


def _rows_matching(
    rows_by_table: dict[str, tuple[NormalizedSourceRow, ...]],
    table_name: str,
    column_name: str,
    value: str,
) -> tuple[NormalizedSourceRow, ...]:
    return tuple(
        row
        for row in rows_by_table.get(table_name, ())
        if row.runtime_fields_payload().get(column_name) == value
    )


def _required_field(row: NormalizedSourceRow, column_name: str) -> str:
    fields = row.runtime_fields_payload()
    if column_name not in fields:
        raise WahapediaDatasheetAbilityBridgeError(
            f"Required source column is missing: {column_name}."
        )
    value = fields[column_name].strip()
    if not value and column_name not in {"ability_id", "description", "parameter"}:
        raise WahapediaDatasheetAbilityBridgeError(
            f"Required source column is empty: {column_name}."
        )
    return value


def _raw_or_field(row: NormalizedSourceRow, column_name: str) -> str:
    for text_field in row.text_fields:
        if text_field.column_name == column_name:
            return text_field.raw_text
    return row.runtime_fields_payload().get(column_name, "")


def _source_ids(*rows: NormalizedSourceRow) -> tuple[str, ...]:
    values: list[str] = []
    for row in rows:
        values.append(row.stable_source_id())
        explicit = row.runtime_fields_payload().get("source_ids", "")
        values.extend(value.strip() for value in explicit.split(",") if value.strip())
    return tuple(dict.fromkeys(values))


def _validate_identifier_tuple(field_name: str, values: tuple[str, ...]) -> tuple[str, ...]:
    if type(values) is not tuple:
        raise WahapediaDatasheetAbilityBridgeError(f"{field_name} must be a tuple.")
    validator = IdentifierValidator(WahapediaDatasheetAbilityBridgeError)
    validated = tuple(validator(f"{field_name} value", value) for value in values)
    if len(validated) != len(set(validated)):
        raise WahapediaDatasheetAbilityBridgeError(f"{field_name} must not contain duplicates.")
    return validated


def _slug(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    lowered = normalized.casefold().replace("'", "").replace("&", " and ")
    slug = re.sub(r"[^a-z0-9]+", "-", lowered).strip("-")
    if not slug:
        raise WahapediaDatasheetAbilityBridgeError("Could not derive a stable slug.")
    return slug


def compact_rule_ir_payload(rule_ir: RuleIRPayload) -> str:
    return json.dumps(rule_ir, sort_keys=True, separators=(",", ":"))
