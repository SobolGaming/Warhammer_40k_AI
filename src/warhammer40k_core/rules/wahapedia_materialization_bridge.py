from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass

from warhammer40k_core.rules import wahapedia_bridge_patterns as _patterns
from warhammer40k_core.rules.rule_ir import RuleEffectKind, RuleIR, parameter_payload
from warhammer40k_core.rules.wahapedia_schema import NormalizedSourceRow
from warhammer40k_core.rules.wahapedia_static_rule_ir import payload_by_source_row_id


@dataclass(frozen=True, slots=True)
class MaterializationOnlyProfileSpec:
    line: str
    model_name: str
    model_profile_id: str
    base_size_datasheet_id: str
    source_rows: tuple[NormalizedSourceRow, ...]


def materialization_profile_source(
    *,
    rows_by_table: dict[str, tuple[NormalizedSourceRow, ...]],
    datasheet_id: str,
    error_type: type[ValueError],
) -> tuple[set[str], dict[str, str], tuple[NormalizedSourceRow, ...]]:
    referenced_profile_ids: set[str] = set()
    base_size_datasheet_ids: dict[str, str] = {}
    source_rows: list[NormalizedSourceRow] = []
    for row in rows_by_table.get("Datasheets_abilities", ()):
        fields = row.runtime_fields_payload()
        if fields.get("datasheet_id", "").strip() != datasheet_id:
            continue
        payload = payload_by_source_row_id(row.source_row_id)
        if payload is None:
            continue
        rule_ir = RuleIR.from_payload(payload)
        row_references_materialization = False
        for clause in rule_ir.clauses:
            for effect in clause.effects:
                if effect.kind is not RuleEffectKind.MATERIALIZE_MODELS:
                    continue
                result_profile_id = parameter_payload(effect.parameters).get(
                    "result_model_profile_id"
                )
                if type(result_profile_id) is not str:
                    raise error_type("Materialization RuleIR requires result_model_profile_id.")
                if not result_profile_id.startswith(f"{datasheet_id}:"):
                    continue
                referenced_profile_ids.add(result_profile_id)
                base_size_datasheet_id = parameter_payload(effect.parameters).get(
                    "result_base_size_datasheet_id"
                )
                if type(base_size_datasheet_id) is not str:
                    raise error_type(
                        "Materialization RuleIR requires result_base_size_datasheet_id."
                    )
                existing_base_size_id = base_size_datasheet_ids.get(result_profile_id)
                if existing_base_size_id not in {None, base_size_datasheet_id}:
                    raise error_type("Materialization base-size datasheet identity drift.")
                base_size_datasheet_ids[result_profile_id] = base_size_datasheet_id
                row_references_materialization = True
        if row_references_materialization:
            source_rows.append(row)
    return referenced_profile_ids, base_size_datasheet_ids, tuple(source_rows)


def mustering_loadout(
    *,
    rows_by_table: dict[str, tuple[NormalizedSourceRow, ...]],
    datasheet_id: str,
    loadout: str,
    error_type: type[ValueError],
) -> str:
    normalization = _patterns.LOADOUT_SEPARATOR_NORMALIZATION_BY_DATASHEET_ID.get(datasheet_id)
    if normalization is not None:
        expected_source_loadout, normalized_loadout = normalization
        if loadout != expected_source_loadout:
            raise error_type("Source-linked loadout separator normalization preimage drifted.")
        loadout = normalized_loadout
    referenced_profile_ids, _base_size_ids, _source_rows = materialization_profile_source(
        rows_by_table=rows_by_table,
        datasheet_id=datasheet_id,
        error_type=error_type,
    )
    if not referenced_profile_ids:
        return loadout
    return re.sub(
        r"Every [^.]+ added to this unit using [^.]+ ability is equipped with: [^.]+\.?",
        "",
        loadout,
        flags=re.IGNORECASE,
    ).strip()


def materialization_only_profile_specs(
    *,
    rows_by_table: dict[str, tuple[NormalizedSourceRow, ...]],
    datasheet_id: str,
    existing_profile_ids: frozenset[str],
    model_source_rows: tuple[NormalizedSourceRow, ...],
    profile_id_for_model_name: Callable[[str], str],
    error_type: type[ValueError],
) -> tuple[MaterializationOnlyProfileSpec, ...]:
    referenced_profile_ids, base_size_datasheet_ids, source_rows = materialization_profile_source(
        rows_by_table=rows_by_table,
        datasheet_id=datasheet_id,
        error_type=error_type,
    )
    if not referenced_profile_ids:
        return ()
    supplemental: list[MaterializationOnlyProfileSpec] = []
    for model_source_row in model_source_rows:
        fields = model_source_row.runtime_fields_payload()
        model_name = fields.get("name", "").strip()
        line = fields.get("line", "").strip()
        if not model_name or not line:
            raise error_type("Materialization model source row is incomplete.")
        model_profile_id = profile_id_for_model_name(model_name)
        if model_profile_id not in referenced_profile_ids or model_profile_id in (
            existing_profile_ids
        ):
            continue
        supplemental.append(
            MaterializationOnlyProfileSpec(
                line=f"materialization-{line}",
                model_name=model_name,
                model_profile_id=model_profile_id,
                base_size_datasheet_id=base_size_datasheet_ids[model_profile_id],
                source_rows=(model_source_row, *source_rows),
            )
        )
    resolved_profile_ids = existing_profile_ids | frozenset(
        spec.model_profile_id for spec in supplemental
    )
    if referenced_profile_ids - resolved_profile_ids:
        raise error_type(
            "Materialization RuleIR references model profiles without source stat rows."
        )
    return tuple(supplemental)


__all__ = (
    "MaterializationOnlyProfileSpec",
    "materialization_only_profile_specs",
    "materialization_profile_source",
    "mustering_loadout",
)
