from __future__ import annotations

import json
import re
from collections.abc import Mapping
from functools import cache
from pathlib import Path
from typing import cast

from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.rules.rule_compiler import compile_rule_source_text
from warhammer40k_core.rules.rule_ir import RuleEffectKind, RuleIR
from warhammer40k_core.rules.rule_templates import (
    CHARACTERISTIC_MODIFIER_TEMPLATE_ID,
    GRANT_ABILITY_TEMPLATE_ID,
    KEYWORD_GATE_TEMPLATE_ID,
    WEAPON_ABILITY_GRANT_TEMPLATE_ID,
)
from warhammer40k_core.rules.source_data import RuleSourceText
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    datasheet_keyword_lexicon_2026_06_14,
    faction_subrules_2026_27,
)

SOURCE_PACKAGE_ID = "gw-11e-phase17e-faction-coverage-2026-27"
WAHAPEDIA_SOURCE_VERSION = "1" + "0" + "th-edition-2026-06-14"
_SOURCE_JSON_DIR = (
    Path(__file__).resolve().parents[5]
    / "data"
    / "source_snapshots"
    / "wahapedia"
    / ("1" + "0" + "th-edition")
    / "2026-06-14"
    / "json"
)
_BRIDGE_SOURCE_ROW_RE = re.compile(r"bridge-source-row:Enhancements:(?P<id>[^:]+)$")
_SOURCE_DESCRIPTION_COLUMN = "description"
_ENHANCEMENTS_TABLE = "Enhancements"
_SUPPORTED_CONDITIONAL_WEAPON_ABILITY_ENHANCEMENT_SOURCE_ROW_IDS = frozenset(
    {
        "enhancement:chaos-space-marines:renegade-warband:000010694003",
        "enhancement:imperial-knights:freeblade-company:000010755003",
        "enhancement:necrons:starshatter-arsenal:000009749003",
        "enhancement:orks:freebooter-krew:000010712003",
        "enhancement:orks:more-dakka:000009991003",
        "enhancement:space-marines:ceramite-sentinels:000010759004",
    }
)
_SUPPORTED_GRANT_ABILITY_ENHANCEMENT_SOURCE_ROW_IDS = frozenset(
    {
        "enhancement:genestealer-cults:outlander-claw:000009079002",
        "enhancement:orks:more-dakka:000009991005",
        "enhancement:tyranids:warrior-bioform-onslaught:000009737005",
    }
)
_SUPPORTED_CHARACTERISTIC_MODIFICATION_ENHANCEMENT_SOURCE_ROW_IDS = frozenset(
    {
        "enhancement:necrons:cryptek-conclave:000010664004",
    }
)
_SUPPORTED_CONDITIONAL_WEAPON_ABILITY_TEMPLATE_IDS = frozenset(
    {
        KEYWORD_GATE_TEMPLATE_ID,
        WEAPON_ABILITY_GRANT_TEMPLATE_ID,
    }
)
_SUPPORTED_GRANT_ABILITY_TEMPLATE_IDS = frozenset(
    {
        GRANT_ABILITY_TEMPLATE_ID,
        KEYWORD_GATE_TEMPLATE_ID,
    }
)
_SUPPORTED_CHARACTERISTIC_MODIFICATION_TEMPLATE_IDS = frozenset(
    {
        CHARACTERISTIC_MODIFIER_TEMPLATE_ID,
        KEYWORD_GATE_TEMPLATE_ID,
    }
)


class Phase17FGenericIrSupportError(ValueError):
    """Raised when Phase 17F generic IR support metadata is inconsistent."""


def generic_supported_enhancement_rule_ir(
    source_row: faction_subrules_2026_27.SourceEnhancementRow,
) -> RuleIR | None:
    if type(source_row) is not faction_subrules_2026_27.SourceEnhancementRow:
        raise Phase17FGenericIrSupportError("Generic enhancement support requires source row.")
    if source_row.source_row_id not in _supported_enhancement_source_row_ids():
        return None
    rule_ir = _compile_enhancement_rule_ir(source_row)
    _validate_supported_enhancement_ir(
        rule_ir=rule_ir,
        source_row=source_row,
    )
    return rule_ir


def generic_supported_enhancement_rule_ir_hash(
    source_row: faction_subrules_2026_27.SourceEnhancementRow,
) -> str | None:
    rule_ir = generic_supported_enhancement_rule_ir(source_row)
    if rule_ir is None:
        return None
    return rule_ir.ir_hash()


def generic_rule_ir_by_coverage_descriptor_id(coverage_descriptor_id: str) -> RuleIR:
    descriptor_id = _validate_identifier("coverage_descriptor_id", coverage_descriptor_id)
    source_row = _enhancement_source_row_by_coverage_descriptor_id().get(descriptor_id)
    if source_row is None:
        raise Phase17FGenericIrSupportError("Generic IR coverage descriptor is not registered.")
    rule_ir = generic_supported_enhancement_rule_ir(source_row)
    if rule_ir is None:
        raise Phase17FGenericIrSupportError("Generic IR coverage descriptor is not supported.")
    return rule_ir


def generic_rule_ir_hash_by_coverage_descriptor_id(coverage_descriptor_id: str) -> str:
    return generic_rule_ir_by_coverage_descriptor_id(coverage_descriptor_id).ir_hash()


def supported_conditional_weapon_ability_enhancement_source_row_ids() -> tuple[str, ...]:
    return tuple(sorted(_SUPPORTED_CONDITIONAL_WEAPON_ABILITY_ENHANCEMENT_SOURCE_ROW_IDS))


def supported_grant_ability_enhancement_source_row_ids() -> tuple[str, ...]:
    return tuple(sorted(_SUPPORTED_GRANT_ABILITY_ENHANCEMENT_SOURCE_ROW_IDS))


def supported_characteristic_modification_enhancement_source_row_ids() -> tuple[str, ...]:
    return tuple(sorted(_SUPPORTED_CHARACTERISTIC_MODIFICATION_ENHANCEMENT_SOURCE_ROW_IDS))


def supported_generic_enhancement_source_row_ids() -> tuple[str, ...]:
    return tuple(sorted(_supported_enhancement_source_row_ids()))


def _compile_enhancement_rule_ir(
    source_row: faction_subrules_2026_27.SourceEnhancementRow,
) -> RuleIR:
    bridge_source_row_id = _bridge_source_row_id(source_row)
    raw_text = _enhancement_raw_description_by_bridge_id().get(bridge_source_row_id)
    if raw_text is None:
        raise Phase17FGenericIrSupportError(
            "Generic enhancement support row lacks Wahapedia bridge text."
        )
    source = RuleSourceText.from_raw(
        source_id=f"{SOURCE_PACKAGE_ID}:phase17e:{source_row.source_row_id}:source-text",
        raw_text=raw_text,
    )
    return compile_rule_source_text(
        source,
        source_keyword_sequence_parts=(
            datasheet_keyword_lexicon_2026_06_14.canonical_datasheet_keyword_sequence_parts()
        ),
    ).rule_ir


def _validate_supported_enhancement_ir(
    *,
    rule_ir: RuleIR,
    source_row: faction_subrules_2026_27.SourceEnhancementRow,
) -> None:
    if source_row.source_row_id in _SUPPORTED_CONDITIONAL_WEAPON_ABILITY_ENHANCEMENT_SOURCE_ROW_IDS:
        _validate_supported_effect_family_ir(
            rule_ir=rule_ir,
            source_row=source_row,
            expected_template_ids=_SUPPORTED_CONDITIONAL_WEAPON_ABILITY_TEMPLATE_IDS,
            effect_kind=RuleEffectKind.GRANT_WEAPON_ABILITY,
            effect_family_name="weapon ability",
        )
    elif source_row.source_row_id in _SUPPORTED_GRANT_ABILITY_ENHANCEMENT_SOURCE_ROW_IDS:
        _validate_supported_effect_family_ir(
            rule_ir=rule_ir,
            source_row=source_row,
            expected_template_ids=_SUPPORTED_GRANT_ABILITY_TEMPLATE_IDS,
            effect_kind=RuleEffectKind.GRANT_ABILITY,
            effect_family_name="ability",
        )
    elif (
        source_row.source_row_id
        in _SUPPORTED_CHARACTERISTIC_MODIFICATION_ENHANCEMENT_SOURCE_ROW_IDS
    ):
        _validate_supported_effect_family_ir(
            rule_ir=rule_ir,
            source_row=source_row,
            expected_template_ids=_SUPPORTED_CHARACTERISTIC_MODIFICATION_TEMPLATE_IDS,
            effect_kind=RuleEffectKind.MODIFY_CHARACTERISTIC,
            effect_family_name="characteristic modifier",
        )
    else:
        raise Phase17FGenericIrSupportError("Generic enhancement support row is not registered.")


def _validate_supported_effect_family_ir(
    *,
    rule_ir: RuleIR,
    source_row: faction_subrules_2026_27.SourceEnhancementRow,
    expected_template_ids: frozenset[str],
    effect_kind: RuleEffectKind,
    effect_family_name: str,
) -> None:
    if not rule_ir.is_supported:
        raise Phase17FGenericIrSupportError(
            "Generic enhancement support row must compile to supported RuleIR."
        )
    template_ids = frozenset(
        clause.template_id for clause in rule_ir.clauses if clause.template_id is not None
    )
    if template_ids != expected_template_ids:
        raise Phase17FGenericIrSupportError(
            "Generic enhancement support row must use only its registered template family."
        )
    effect_count = 0
    for clause in rule_ir.clauses:
        if clause.unsupported_reason is not None or clause.diagnostics:
            raise Phase17FGenericIrSupportError(
                "Generic enhancement support row includes unsupported clause diagnostics."
            )
        for effect in clause.effects:
            if effect.kind is effect_kind:
                effect_count += 1
    if effect_count != 1:
        raise Phase17FGenericIrSupportError(
            f"Generic enhancement support row must include one {effect_family_name} effect."
        )
    expected_source_id = f"{SOURCE_PACKAGE_ID}:phase17e:{source_row.source_row_id}:source-text"
    if rule_ir.source_id != expected_source_id:
        raise Phase17FGenericIrSupportError(
            "Generic enhancement support row produced an unexpected source ID."
        )


def _bridge_source_row_id(source_row: faction_subrules_2026_27.SourceEnhancementRow) -> str:
    matches = tuple(
        match.group("id")
        for source_id in source_row.all_source_ids
        for match in (_BRIDGE_SOURCE_ROW_RE.search(source_id),)
        if match is not None
    )
    if len(matches) != 1:
        raise Phase17FGenericIrSupportError(
            "Generic enhancement support row requires one Enhancements bridge source row."
        )
    return _validate_identifier("bridge_source_row_id", matches[0])


@cache
def _enhancement_source_row_by_coverage_descriptor_id() -> Mapping[
    str,
    faction_subrules_2026_27.SourceEnhancementRow,
]:
    rows: dict[str, faction_subrules_2026_27.SourceEnhancementRow] = {}
    for source_row in faction_subrules_2026_27.enhancement_rows():
        if source_row.source_row_id not in _supported_enhancement_source_row_ids():
            continue
        descriptor_id = f"phase17e:{source_row.source_row_id}"
        if descriptor_id in rows:
            raise Phase17FGenericIrSupportError(
                "Generic enhancement coverage descriptor IDs must be unique."
            )
        rows[descriptor_id] = source_row
    return rows


@cache
def _enhancement_raw_description_by_bridge_id() -> Mapping[str, str]:
    artifact = _load_source_json_artifact(_ENHANCEMENTS_TABLE)
    descriptions: dict[str, str] = {}
    for row in _artifact_rows(artifact, table=_ENHANCEMENTS_TABLE):
        row_id = _source_row_id(row, table=_ENHANCEMENTS_TABLE)
        fields = _row_fields(row, table=_ENHANCEMENTS_TABLE)
        descriptions[row_id] = _required_field_text(
            fields,
            field_name=_SOURCE_DESCRIPTION_COLUMN,
            table=_ENHANCEMENTS_TABLE,
        )
    return descriptions


def _supported_enhancement_source_row_ids() -> frozenset[str]:
    return frozenset(
        {
            *_SUPPORTED_CONDITIONAL_WEAPON_ABILITY_ENHANCEMENT_SOURCE_ROW_IDS,
            *_SUPPORTED_GRANT_ABILITY_ENHANCEMENT_SOURCE_ROW_IDS,
            *_SUPPORTED_CHARACTERISTIC_MODIFICATION_ENHANCEMENT_SOURCE_ROW_IDS,
        }
    )


def _load_source_json_artifact(table: str) -> Mapping[str, object]:
    path = _SOURCE_JSON_DIR / f"{table}.json"
    if not path.is_file():
        raise Phase17FGenericIrSupportError(f"Generic IR source artifact is missing: {path}.")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise Phase17FGenericIrSupportError(
            f"Generic IR source artifact {table} must be a JSON object."
        )
    return cast(Mapping[str, object], payload)


def _artifact_rows(
    artifact: Mapping[str, object], *, table: str
) -> tuple[Mapping[str, object], ...]:
    rows = artifact.get("rows")
    if not isinstance(rows, list):
        raise Phase17FGenericIrSupportError(
            f"Generic IR source artifact {table} rows must be a list."
        )
    validated: list[Mapping[str, object]] = []
    row_values = cast(list[object], rows)
    for row in row_values:
        if not isinstance(row, dict):
            raise Phase17FGenericIrSupportError(
                f"Generic IR source artifact {table} rows must contain objects."
            )
        validated.append(cast(Mapping[str, object], row))
    return tuple(validated)


def _source_row_id(row: Mapping[str, object], *, table: str) -> str:
    value = row.get("source_row_id")
    if type(value) is not str:
        raise Phase17FGenericIrSupportError(
            f"Generic IR source row in {table} lacks source_row_id."
        )
    return _validate_identifier("source_row_id", value)


def _row_fields(row: Mapping[str, object], *, table: str) -> Mapping[str, str]:
    fields = row.get("fields")
    if not isinstance(fields, dict):
        raise Phase17FGenericIrSupportError(f"Generic IR source row in {table} lacks fields.")
    validated: dict[str, str] = {}
    field_values = cast(dict[object, object], fields)
    for key, value in field_values.items():
        if type(key) is not str or type(value) is not str:
            raise Phase17FGenericIrSupportError(
                f"Generic IR source row in {table} fields must be strings."
            )
        validated[key] = value
    return validated


def _required_field_text(fields: Mapping[str, str], *, field_name: str, table: str) -> str:
    value = fields.get(field_name)
    if value is None:
        raise Phase17FGenericIrSupportError(f"Generic IR source row in {table} lacks {field_name}.")
    return _validate_text(field_name, value)


def _validate_text(field_name: str, value: object) -> str:
    if type(value) is not str:
        raise Phase17FGenericIrSupportError(f"{field_name} must be text.")
    stripped = value.strip()
    if not stripped:
        raise Phase17FGenericIrSupportError(f"{field_name} must not be empty.")
    return stripped


_validate_identifier = IdentifierValidator(Phase17FGenericIrSupportError)
