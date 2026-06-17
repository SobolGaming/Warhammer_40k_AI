from __future__ import annotations

import csv
import io
import json
import re
import unicodedata
from dataclasses import dataclass

from warhammer40k_core.core.datasheet import (
    CatalogAbilitySourceKind,
    CatalogAbilitySupport,
    WargearOptionConditionKind,
    WargearOptionEffectKind,
)
from warhammer40k_core.core.model_geometry_catalog import (
    GeometryEvidenceKind,
    GeometryReviewStatus,
    GeometrySourceUnits,
)
from warhammer40k_core.core.weapon_profiles import WeaponKeyword
from warhammer40k_core.rules.data_package import DataPackageId
from warhammer40k_core.rules.rule_compiler import compile_rule_source_text
from warhammer40k_core.rules.source_data import RuleSourceText
from warhammer40k_core.rules.wahapedia_schema import (
    NormalizedSourceRow,
    WahapediaCsvTable,
    WahapediaJsonArtifact,
)


class WahapediaBridgeError(ValueError):
    """Raised when Wahapedia rows cannot be bridged into canonical source rows."""


@dataclass(frozen=True, slots=True)
class PdfDatasheetCorrection:
    datasheet_id: str
    source_id: str
    removed_keywords: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "datasheet_id", _validate_identifier("datasheet_id", self.datasheet_id)
        )
        object.__setattr__(self, "source_id", _validate_identifier("source_id", self.source_id))
        object.__setattr__(
            self,
            "removed_keywords",
            _validate_identifier_tuple("removed_keywords", self.removed_keywords),
        )


@dataclass(frozen=True, slots=True)
class ModelHeightOverride:
    datasheet_id: str
    model_name: str
    height: float
    height_units: GeometrySourceUnits
    height_source_id: str
    height_document_reference: str
    reviewer_status: GeometryReviewStatus = GeometryReviewStatus.ACCEPTED
    evidence_kind: GeometryEvidenceKind = GeometryEvidenceKind.MANUAL_MEASUREMENT

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "datasheet_id", _validate_identifier("datasheet_id", self.datasheet_id)
        )
        object.__setattr__(self, "model_name", _validate_identifier("model_name", self.model_name))
        object.__setattr__(self, "height", _validate_positive_float("height", self.height))
        object.__setattr__(self, "height_units", GeometrySourceUnits(self.height_units))
        object.__setattr__(
            self,
            "height_source_id",
            _validate_identifier("height_source_id", self.height_source_id),
        )
        object.__setattr__(
            self,
            "height_document_reference",
            _validate_identifier("height_document_reference", self.height_document_reference),
        )
        object.__setattr__(self, "reviewer_status", GeometryReviewStatus(self.reviewer_status))
        object.__setattr__(self, "evidence_kind", GeometryEvidenceKind(self.evidence_kind))


_UNIT_COMPOSITION_RE = re.compile(
    r"^(?P<min>\d+)(?:-(?P<max>\d+))?\s+(?P<name>.+?)$",
    re.IGNORECASE,
)
_MODEL_COST_RE = re.compile(r"^(?P<count>\d+)\s+models?$", re.IGNORECASE)
_OPTION_RE = re.compile(
    r"^1 (?P<model>.+?) that is not equipped with (?:a|an|1) "
    r"(?P<forbidden>.+?) can be equipped with 1 (?P<granted>.+?)\.$",
    re.IGNORECASE,
)


def build_wahapedia_canonical_bridge_artifacts(
    *,
    source_artifacts: tuple[WahapediaJsonArtifact, ...],
    bridge_package_id: DataPackageId,
    datasheet_ids: tuple[str, ...],
    pdf_corrections: tuple[PdfDatasheetCorrection, ...] | None = None,
    height_overrides: tuple[ModelHeightOverride, ...] | None = None,
) -> tuple[WahapediaJsonArtifact, ...]:
    if type(source_artifacts) is not tuple:
        raise WahapediaBridgeError("source_artifacts must be a tuple.")
    if not source_artifacts:
        raise WahapediaBridgeError("source_artifacts must not be empty.")
    if type(bridge_package_id) is not DataPackageId:
        raise WahapediaBridgeError("bridge_package_id must be DataPackageId.")
    selected_datasheet_ids = _validate_identifier_tuple("datasheet_ids", datasheet_ids)
    if not selected_datasheet_ids:
        raise WahapediaBridgeError("datasheet_ids must not be empty.")
    rows_by_table = _rows_by_table(source_artifacts)
    selected_pdf_corrections = (
        DEFAULT_PDF_CORRECTIONS if pdf_corrections is None else pdf_corrections
    )
    selected_height_overrides = (
        DEFAULT_HEIGHT_OVERRIDES if height_overrides is None else height_overrides
    )
    corrections_by_datasheet = _corrections_by_datasheet(selected_pdf_corrections)
    height_by_datasheet_and_model = _height_overrides_by_datasheet_and_model(
        selected_height_overrides
    )
    context = _BridgeContext(
        rows_by_table=rows_by_table,
        corrections_by_datasheet=corrections_by_datasheet,
        height_by_datasheet_and_model=height_by_datasheet_and_model,
    )
    bridged_rows = _empty_bridge_rows()
    for datasheet_id in selected_datasheet_ids:
        _bridge_datasheet(datasheet_id=datasheet_id, context=context, bridged_rows=bridged_rows)
    return _artifacts_from_bridge_rows(
        bridge_package_id=bridge_package_id,
        rows_by_table=bridged_rows,
    )


@dataclass(frozen=True, slots=True)
class _BridgeContext:
    rows_by_table: dict[str, tuple[NormalizedSourceRow, ...]]
    corrections_by_datasheet: dict[str, PdfDatasheetCorrection]
    height_by_datasheet_and_model: dict[tuple[str, str], ModelHeightOverride]


@dataclass(frozen=True, slots=True)
class _CompositionEntry:
    line: str
    model_name: str
    model_profile_id: str
    min_models: int
    max_models: int
    source_row: NormalizedSourceRow


EVENT_COMPANION_BASE_SIZE_GUIDE_SOURCE_ID = (
    "pdf:warhammer40000-event-companion:2026-06-12:base-size-guide"
)
EVENT_COMPANION_BASE_SIZE_GUIDE_DOCUMENT_REFERENCE = (
    "docs/source_rules/eng_12-06_warhammer40000_event_companion-s3bfb5f9s1-ivswuij3fo.pdf"
)


def _bridge_datasheet(
    *,
    datasheet_id: str,
    context: _BridgeContext,
    bridged_rows: dict[str, list[dict[str, str]]],
) -> None:
    datasheet_row = _required_row_by_id(context.rows_by_table, "Datasheets", datasheet_id)
    faction_id = _required_field(datasheet_row, "faction_id")
    faction_row = _required_row_by_id(context.rows_by_table, "Factions", faction_id)
    model_source_rows = _rows_matching(
        context.rows_by_table, "Datasheets_models", "datasheet_id", datasheet_id
    )
    if len(model_source_rows) != 1:
        raise WahapediaBridgeError(
            "Bridge currently requires one Wahapedia model stat row per datasheet."
        )
    model_source_row = model_source_rows[0]
    composition_entries = _composition_entries(context=context, datasheet_id=datasheet_id)
    cost_rows = _rows_matching(
        context.rows_by_table, "Datasheets_models_cost", "datasheet_id", datasheet_id
    )
    keywords, faction_keywords, keyword_source_ids = _keywords_for_datasheet(
        context=context,
        datasheet_id=datasheet_id,
    )
    faction_ability_row = _faction_ability_row(context=context, datasheet_id=datasheet_id)
    faction_ability_source = _ability_source_row(context=context, ability_row=faction_ability_row)
    faction_source_ids = _source_ids(faction_row, faction_ability_row, faction_ability_source)
    _append_or_merge_faction_row(
        bridged_rows=bridged_rows,
        row={
            "id": faction_id,
            "name": _raw_or_field(faction_row, "name"),
            "content_scope": "matched_play",
            "faction_keywords": _joined(faction_keywords),
            "army_rule_id": _required_field(faction_ability_row, "ability_id"),
            "army_rule_name": _raw_or_field(faction_ability_source, "name"),
            "source_ids": _joined(faction_source_ids),
        },
    )
    model_source_ids = tuple(
        _deduplicated(
            [
                *_source_ids(model_source_row, *cost_rows),
                EVENT_COMPANION_BASE_SIZE_GUIDE_SOURCE_ID,
            ]
        )
    )
    bridged_rows["Datasheets"].append(
        {
            "id": datasheet_id,
            "name": _raw_or_field(datasheet_row, "name"),
            "content_scope": "matched_play",
            "keywords": _joined(keywords),
            "faction_keywords": _joined(faction_keywords),
            "legend": _raw_or_field(datasheet_row, "legend"),
            "loadout": _raw_or_field(datasheet_row, "loadout"),
            "transport": _raw_or_field(datasheet_row, "transport"),
            "leader_head": _raw_or_field(datasheet_row, "leader_head"),
            "leader_footer": _raw_or_field(datasheet_row, "leader_footer"),
            "damaged_description": _raw_or_field(datasheet_row, "damaged_description"),
            "source_ids": _joined(_source_ids(datasheet_row, *keyword_source_ids)),
        }
    )
    for entry in composition_entries:
        height = _required_height_override(
            context=context,
            datasheet_id=datasheet_id,
            model_name=entry.model_name,
        )
        bridged_rows["Datasheets_models"].append(
            {
                "datasheet_id": datasheet_id,
                "line": entry.line,
                "name": entry.model_name,
                "model_profile_id": entry.model_profile_id,
                "content_scope": "matched_play",
                "m": _required_field(model_source_row, "M"),
                "t": _required_field(model_source_row, "T"),
                "sv": _required_field(model_source_row, "Sv"),
                "inv_sv": _required_field(model_source_row, "inv_sv"),
                "w": _required_field(model_source_row, "W"),
                "ld": _required_field(model_source_row, "Ld"),
                "oc": _required_field(model_source_row, "OC"),
                "ws": "-",
                "bs": "-",
                "min_models": str(entry.min_models),
                "max_models": str(entry.max_models),
                "base_size": _required_field(model_source_row, "base_size"),
                "base_size_source_id": EVENT_COMPANION_BASE_SIZE_GUIDE_SOURCE_ID,
                "base_size_document_reference": EVENT_COMPANION_BASE_SIZE_GUIDE_DOCUMENT_REFERENCE,
                "height": str(height.height),
                "height_units": height.height_units.value,
                "height_source_id": height.height_source_id,
                "height_document_reference": height.height_document_reference,
                "height_reviewer_status": height.reviewer_status.value,
                "height_evidence_kind": height.evidence_kind.value,
                "source_ids": _joined(
                    tuple(_deduplicated([*model_source_ids, entry.source_row.stable_source_id()]))
                ),
            }
        )
    _bridge_unit_composition(
        context=context,
        datasheet_id=datasheet_id,
        bridged_rows=bridged_rows,
    )
    wargear_ids_by_name = _bridge_wargear(
        context=context,
        datasheet_id=datasheet_id,
        composition_entries=composition_entries,
        bridged_rows=bridged_rows,
    )
    _bridge_abilities(
        context=context,
        datasheet_id=datasheet_id,
        wargear_ids_by_name=wargear_ids_by_name,
        bridged_rows=bridged_rows,
    )
    _bridge_options(
        context=context,
        datasheet_id=datasheet_id,
        composition_entries=composition_entries,
        wargear_ids_by_name=wargear_ids_by_name,
        bridged_rows=bridged_rows,
    )
    _bridge_leader_links(context=context, datasheet_id=datasheet_id, bridged_rows=bridged_rows)


def _composition_entries(
    *, context: _BridgeContext, datasheet_id: str
) -> tuple[_CompositionEntry, ...]:
    rows = _rows_matching(
        context.rows_by_table, "Datasheets_unit_composition", "datasheet_id", datasheet_id
    )
    if not rows:
        raise WahapediaBridgeError("Datasheet has no unit composition rows.")
    entries: list[_CompositionEntry] = []
    for row in rows:
        description = _required_field(row, "description")
        match = _UNIT_COMPOSITION_RE.fullmatch(description)
        if match is None:
            raise WahapediaBridgeError("Unsupported unit composition row shape.")
        minimum = _int_from_text(match.group("min"))
        maximum_text = match.group("max")
        maximum = minimum if maximum_text is None else _int_from_text(maximum_text)
        model_name = match.group("name").strip()
        entries.append(
            _CompositionEntry(
                line=_required_field(row, "line"),
                model_name=model_name,
                model_profile_id=f"{datasheet_id}:{_slug(model_name)}",
                min_models=minimum,
                max_models=maximum,
                source_row=row,
            )
        )
    return tuple(entries)


def _keywords_for_datasheet(
    *,
    context: _BridgeContext,
    datasheet_id: str,
) -> tuple[tuple[str, ...], tuple[str, ...], tuple[NormalizedSourceRow, ...]]:
    keyword_rows = _rows_matching(
        context.rows_by_table, "Datasheets_keywords", "datasheet_id", datasheet_id
    )
    if not keyword_rows:
        raise WahapediaBridgeError("Datasheet has no keyword rows.")
    correction = context.corrections_by_datasheet.get(datasheet_id)
    removed = set(correction.removed_keywords if correction is not None else ())
    keywords: list[str] = []
    faction_keywords: list[str] = []
    source_rows: list[NormalizedSourceRow] = []
    for row in keyword_rows:
        keyword = _required_field(row, "keyword")
        if keyword in removed:
            if correction is not None:
                source_rows.append(row)
            continue
        if _required_field(row, "is_faction_keyword") == "true":
            faction_keywords.append(keyword)
        else:
            keywords.append(keyword)
        source_rows.append(row)
    if correction is not None:
        source_rows.append(_correction_source_row(correction))
    return (
        tuple(sorted(_deduplicated(keywords))),
        tuple(sorted(_deduplicated(faction_keywords))),
        tuple(source_rows),
    )


def _faction_ability_row(*, context: _BridgeContext, datasheet_id: str) -> NormalizedSourceRow:
    rows = tuple(
        row
        for row in _rows_matching(
            context.rows_by_table, "Datasheets_abilities", "datasheet_id", datasheet_id
        )
        if _required_field(row, "type") == "Faction"
    )
    if len(rows) != 1:
        raise WahapediaBridgeError("Datasheet must link exactly one faction ability.")
    return rows[0]


def _ability_source_row(
    *, context: _BridgeContext, ability_row: NormalizedSourceRow
) -> NormalizedSourceRow:
    ability_id = _required_field(ability_row, "ability_id")
    candidate_rows = tuple(
        row
        for row in context.rows_by_table.get("Abilities", ())
        if _required_field(row, "id") == ability_id
    )
    if not candidate_rows:
        raise WahapediaBridgeError("Datasheet ability link references a missing ability row.")
    if len(candidate_rows) == 1:
        return candidate_rows[0]
    for row in candidate_rows:
        if not _required_field(row, "faction_id"):
            return row
    raise WahapediaBridgeError("Datasheet ability link is ambiguous.")


def _bridge_unit_composition(
    *,
    context: _BridgeContext,
    datasheet_id: str,
    bridged_rows: dict[str, list[dict[str, str]]],
) -> None:
    for row in _rows_matching(
        context.rows_by_table, "Datasheets_unit_composition", "datasheet_id", datasheet_id
    ):
        bridged_rows["Datasheets_unit_composition"].append(
            {
                "datasheet_id": datasheet_id,
                "line": _required_field(row, "line"),
                "description": _raw_or_field(row, "description"),
                "source_ids": _joined(_source_ids(row)),
            }
        )


def _bridge_wargear(
    *,
    context: _BridgeContext,
    datasheet_id: str,
    composition_entries: tuple[_CompositionEntry, ...],
    bridged_rows: dict[str, list[dict[str, str]]],
) -> dict[str, str]:
    wargear_ids_by_name: dict[str, str] = {}
    model_profile_ids = tuple(entry.model_profile_id for entry in composition_entries)
    for row in _rows_matching(
        context.rows_by_table, "Datasheets_wargear", "datasheet_id", datasheet_id
    ):
        name = _required_field(row, "name")
        wargear_id = f"{datasheet_id}:{_slug(name)}"
        wargear_ids_by_name[_name_key(name)] = wargear_id
        bridged_rows["Datasheets_wargear"].append(
            {
                "datasheet_id": datasheet_id,
                "line": _required_field(row, "line"),
                "line_in_wargear": _required_field(row, "line_in_wargear"),
                "name": _raw_or_field(row, "name"),
                "wargear_id": wargear_id,
                "weapon_profile_id": f"{wargear_id}:standard",
                "model_profile_ids": _joined(model_profile_ids),
                "range": _required_field(row, "range"),
                "a": _required_field(row, "A"),
                "skill_characteristic": _skill_characteristic(row),
                "skill": f"{_required_field(row, 'BS_WS')}+",
                "s": _required_field(row, "S"),
                "ap": _required_field(row, "AP"),
                "d": _required_field(row, "D"),
                "weapon_keywords": _joined(_weapon_keywords(_required_field(row, "description"))),
                "default_loadout": "true",
                "source_ids": _joined(_source_ids(row)),
            }
        )
    return wargear_ids_by_name


def _bridge_abilities(
    *,
    context: _BridgeContext,
    datasheet_id: str,
    wargear_ids_by_name: dict[str, str],
    bridged_rows: dict[str, list[dict[str, str]]],
) -> None:
    rows = _rows_matching(
        context.rows_by_table, "Datasheets_abilities", "datasheet_id", datasheet_id
    )
    for row in rows:
        ability_id = _required_field(row, "ability_id")
        source_rows: tuple[NormalizedSourceRow, ...] = (row,)
        name = _raw_or_field(row, "name")
        description = _raw_or_field(row, "description")
        if ability_id:
            ability_source = _ability_source_row(context=context, ability_row=row)
            source_rows = (row, ability_source)
            name = _raw_or_field(ability_source, "name")
            description = _raw_or_field(ability_source, "description")
        else:
            ability_id = f"{datasheet_id}:{_slug(name)}"
        parameter = _raw_or_field(row, "parameter")
        source_kind = _ability_source_kind(_required_field(row, "type"))
        source_wargear_id = ""
        rule_ir_payload = ""
        rule_ir_diagnostics = ""
        support = CatalogAbilitySupport.DESCRIPTOR_ONLY
        if source_kind is CatalogAbilitySourceKind.WARGEAR:
            source_wargear_id = f"{datasheet_id}:{_slug(name)}"
            compiled = compile_rule_source_text(
                RuleSourceText.from_raw(
                    source_id=_source_text_id(row=row, column_name="description"),
                    raw_text=description,
                )
            )
            rule_ir_payload = json.dumps(
                compiled.rule_ir.to_payload(),
                sort_keys=True,
                separators=(",", ":"),
            )
            rule_ir_diagnostics = json.dumps(
                _rule_ir_diagnostics(compiled.rule_ir),
                sort_keys=True,
                separators=(",", ":"),
            )
            if compiled.rule_ir.is_supported:
                support = CatalogAbilitySupport.GENERIC_RULE_IR
            else:
                support = CatalogAbilitySupport.UNSUPPORTED
        bridged_rows["Datasheets_abilities"].append(
            {
                "datasheet_id": datasheet_id,
                "line": _required_field(row, "line"),
                "ability_id": ability_id,
                "name": name,
                "description": description,
                "parameter": parameter,
                "type": _required_field(row, "type"),
                "support": support.value,
                "source_kind": source_kind.value,
                "effect_description": description,
                "source_wargear_id": source_wargear_id,
                "rule_ir_payload": rule_ir_payload,
                "rule_ir_diagnostics": rule_ir_diagnostics,
                "timing_tags": _ability_timing_tags(name),
                "parameter_tokens": _ability_parameter_tokens(name=name, parameter=parameter),
                "source_ids": _joined(_source_ids(*source_rows)),
            }
        )
        if source_kind is CatalogAbilitySourceKind.WARGEAR:
            wargear_id = source_wargear_id
            wargear_ids_by_name[_name_key(name)] = wargear_id
            bridged_rows["Datasheets_wargear"].append(
                {
                    "datasheet_id": datasheet_id,
                    "line": f"ability-{_required_field(row, 'line')}",
                    "line_in_wargear": "1",
                    "name": name,
                    "wargear_id": wargear_id,
                    "weapon_profile_id": "",
                    "model_profile_ids": "",
                    "range": "",
                    "a": "",
                    "skill_characteristic": "",
                    "skill": "",
                    "s": "",
                    "ap": "",
                    "d": "",
                    "weapon_keywords": "",
                    "default_loadout": "false",
                    "source_ids": _joined(_source_ids(row)),
                }
            )


def _bridge_options(
    *,
    context: _BridgeContext,
    datasheet_id: str,
    composition_entries: tuple[_CompositionEntry, ...],
    wargear_ids_by_name: dict[str, str],
    bridged_rows: dict[str, list[dict[str, str]]],
) -> None:
    model_profile_by_name = _model_profiles_by_name(composition_entries)
    for row in _rows_matching(
        context.rows_by_table, "Datasheets_options", "datasheet_id", datasheet_id
    ):
        description = _required_field(row, "description")
        match = _OPTION_RE.fullmatch(description)
        if match is None:
            raise WahapediaBridgeError("Unsupported wargear option row shape.")
        model_profile_id = _required_model_profile_id(model_profile_by_name, match.group("model"))
        forbidden_wargear_id = _required_wargear_id(wargear_ids_by_name, match.group("forbidden"))
        granted_wargear_id = _required_wargear_id(wargear_ids_by_name, match.group("granted"))
        option_id = (
            f"{datasheet_id}:{_slug(match.group('granted'))}:option-{_required_field(row, 'line')}"
        )
        bridged_rows["Datasheets_options"].append(
            {
                "datasheet_id": datasheet_id,
                "line": _required_field(row, "line"),
                "description": _raw_or_field(row, "description"),
                "option_id": option_id,
                "model_profile_id": model_profile_id,
                "default_wargear_ids": "",
                "allowed_wargear_ids": granted_wargear_id,
                "min_selections": "0",
                "max_selections": "1",
                "condition_kind": WargearOptionConditionKind.MODEL_NOT_EQUIPPED_WITH.value,
                "condition_wargear_ids": forbidden_wargear_id,
                "effect_kind": WargearOptionEffectKind.ADD_WARGEAR.value,
                "effect_wargear_id": granted_wargear_id,
                "effect_model_count": "1",
                "effect_wargear_count": "1",
                "source_ids": _joined(_source_ids(row)),
            }
        )


def _bridge_leader_links(
    *,
    context: _BridgeContext,
    datasheet_id: str,
    bridged_rows: dict[str, list[dict[str, str]]],
) -> None:
    for row in context.rows_by_table.get("Datasheets_leader", ()):
        if (
            _required_field(row, "leader_id") != datasheet_id
            and _required_field(row, "attached_id") != datasheet_id
        ):
            continue
        bridged_rows["Datasheets_leader"].append(
            {
                "leader_id": _required_field(row, "leader_id"),
                "attached_id": _required_field(row, "attached_id"),
                "source_ids": _joined(_source_ids(row)),
            }
        )


def _rows_by_table(
    source_artifacts: tuple[WahapediaJsonArtifact, ...],
) -> dict[str, tuple[NormalizedSourceRow, ...]]:
    rows_by_table: dict[str, tuple[NormalizedSourceRow, ...]] = {}
    for artifact in source_artifacts:
        if type(artifact) is not WahapediaJsonArtifact:
            raise WahapediaBridgeError(
                "source_artifacts must contain WahapediaJsonArtifact values."
            )
        existing = rows_by_table.get(artifact.source_table, ())
        rows_by_table[artifact.source_table] = (*existing, *artifact.rows)
    return rows_by_table


def _empty_bridge_rows() -> dict[str, list[dict[str, str]]]:
    return {
        "Factions": [],
        "Datasheets": [],
        "Datasheets_models": [],
        "Datasheets_wargear": [],
        "Datasheets_options": [],
        "Datasheets_abilities": [],
        "Datasheets_leader": [],
        "Datasheets_unit_composition": [],
    }


def _artifacts_from_bridge_rows(
    *,
    bridge_package_id: DataPackageId,
    rows_by_table: dict[str, list[dict[str, str]]],
) -> tuple[WahapediaJsonArtifact, ...]:
    artifacts: list[WahapediaJsonArtifact] = []
    for table_name, rows in rows_by_table.items():
        if not rows:
            continue
        columns = _columns_for_table(table_name)
        csv_text = _csv_text(columns=columns, rows=tuple(rows))
        artifacts.append(
            WahapediaJsonArtifact.from_csv_table(
                source_package_id=bridge_package_id,
                table=WahapediaCsvTable.from_csv_text(table_name=table_name, csv_text=csv_text),
            )
        )
    return tuple(sorted(artifacts, key=lambda artifact: artifact.source_table))


def _columns_for_table(table_name: str) -> tuple[str, ...]:
    columns_by_table = {
        "Factions": (
            "id",
            "name",
            "content_scope",
            "faction_keywords",
            "army_rule_id",
            "army_rule_name",
            "source_ids",
        ),
        "Datasheets": (
            "id",
            "name",
            "content_scope",
            "keywords",
            "faction_keywords",
            "legend",
            "loadout",
            "transport",
            "leader_head",
            "leader_footer",
            "damaged_description",
            "source_ids",
        ),
        "Datasheets_models": (
            "datasheet_id",
            "line",
            "name",
            "model_profile_id",
            "content_scope",
            "m",
            "t",
            "sv",
            "inv_sv",
            "w",
            "ld",
            "oc",
            "ws",
            "bs",
            "min_models",
            "max_models",
            "base_size",
            "base_size_source_id",
            "base_size_document_reference",
            "height",
            "height_units",
            "height_source_id",
            "height_document_reference",
            "height_reviewer_status",
            "height_evidence_kind",
            "source_ids",
        ),
        "Datasheets_wargear": (
            "datasheet_id",
            "line",
            "line_in_wargear",
            "name",
            "wargear_id",
            "weapon_profile_id",
            "model_profile_ids",
            "range",
            "a",
            "skill_characteristic",
            "skill",
            "s",
            "ap",
            "d",
            "weapon_keywords",
            "default_loadout",
            "source_ids",
        ),
        "Datasheets_options": (
            "datasheet_id",
            "line",
            "description",
            "option_id",
            "model_profile_id",
            "default_wargear_ids",
            "allowed_wargear_ids",
            "min_selections",
            "max_selections",
            "condition_kind",
            "condition_wargear_ids",
            "effect_kind",
            "effect_wargear_id",
            "effect_model_count",
            "effect_wargear_count",
            "source_ids",
        ),
        "Datasheets_abilities": (
            "datasheet_id",
            "line",
            "ability_id",
            "name",
            "description",
            "parameter",
            "type",
            "support",
            "source_kind",
            "effect_description",
            "source_wargear_id",
            "rule_ir_payload",
            "rule_ir_diagnostics",
            "timing_tags",
            "parameter_tokens",
            "source_ids",
        ),
        "Datasheets_leader": ("leader_id", "attached_id", "source_ids"),
        "Datasheets_unit_composition": ("datasheet_id", "line", "description", "source_ids"),
    }
    columns = columns_by_table.get(table_name)
    if columns is None:
        raise WahapediaBridgeError("Unsupported bridge output table.")
    return columns


def _csv_text(*, columns: tuple[str, ...], rows: tuple[dict[str, str], ...]) -> str:
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=columns, lineterminator="\n")
    writer.writeheader()
    for row in rows:
        writer.writerow({column: row.get(column, "") for column in columns})
    return output.getvalue()


def _required_row_by_id(
    rows_by_table: dict[str, tuple[NormalizedSourceRow, ...]],
    table_name: str,
    source_row_id: str,
) -> NormalizedSourceRow:
    for row in rows_by_table.get(table_name, ()):
        if row.source_row_id == source_row_id:
            return row
    raise WahapediaBridgeError(f"Required source row was not found: {table_name}.")


def _rows_matching(
    rows_by_table: dict[str, tuple[NormalizedSourceRow, ...]],
    table_name: str,
    column_name: str,
    value: str,
) -> tuple[NormalizedSourceRow, ...]:
    return tuple(
        row
        for row in rows_by_table.get(table_name, ())
        if _required_field(row, column_name) == value
    )


def _required_field(row: NormalizedSourceRow, column_name: str) -> str:
    fields = row.runtime_fields_payload()
    if column_name not in fields:
        raise WahapediaBridgeError(f"Required source column is missing: {column_name}.")
    value = fields[column_name].strip()
    if not value and column_name not in {"ability_id", "description", "parameter", "faction_id"}:
        raise WahapediaBridgeError(f"Required source column is empty: {column_name}.")
    return value


def _raw_or_field(row: NormalizedSourceRow, column_name: str) -> str:
    for text_field in row.text_fields:
        if text_field.column_name == column_name:
            return text_field.raw_text
    return row.runtime_fields_payload().get(column_name, "")


def _source_text_id(*, row: NormalizedSourceRow, column_name: str) -> str:
    for text_field in row.text_fields:
        if text_field.column_name == column_name:
            return text_field.source_text_id
    return f"{row.stable_source_id()}:{column_name}"


def _ability_source_kind(ability_type: str) -> CatalogAbilitySourceKind:
    normalized = _validate_identifier("ability_type", ability_type).lower()
    if normalized == "core":
        return CatalogAbilitySourceKind.CORE
    if normalized == "faction":
        return CatalogAbilitySourceKind.FACTION
    if normalized == "datasheet":
        return CatalogAbilitySourceKind.DATASHEET
    if normalized == "wargear":
        return CatalogAbilitySourceKind.WARGEAR
    raise WahapediaBridgeError("Unsupported datasheet ability type.")


def _rule_ir_diagnostics(rule_ir: object) -> list[dict[str, object]]:
    from warhammer40k_core.rules.rule_ir import RuleIR

    if type(rule_ir) is not RuleIR:
        raise WahapediaBridgeError("Rule IR diagnostics require a RuleIR.")
    diagnostics: list[dict[str, object]] = [
        {
            "scope": "rule",
            "reason": diagnostic.reason.value,
            "message": diagnostic.message,
            "source_span": diagnostic.source_span.to_payload(),
            "blocking": diagnostic.blocking,
        }
        for diagnostic in rule_ir.diagnostics
    ]
    for clause in rule_ir.clauses:
        if clause.unsupported_reason is not None:
            diagnostics.append(
                {
                    "scope": "clause",
                    "clause_id": clause.clause_id,
                    "reason": clause.unsupported_reason.value,
                    "message": "Unsupported rule clause.",
                    "source_span": clause.source_span.to_payload(),
                    "blocking": True,
                }
            )
        for diagnostic in clause.diagnostics:
            diagnostics.append(
                {
                    "scope": "clause",
                    "clause_id": clause.clause_id,
                    "reason": diagnostic.reason.value,
                    "message": diagnostic.message,
                    "source_span": diagnostic.source_span.to_payload(),
                    "blocking": diagnostic.blocking,
                }
            )
    return diagnostics


def _source_ids(*rows: NormalizedSourceRow) -> tuple[str, ...]:
    source_ids: list[str] = []
    for row in rows:
        source_ids.append(row.stable_source_id())
        fields = row.runtime_fields_payload()
        if row.source_table == "PdfCorrections":
            correction_source_id = fields.get("source_id")
            if correction_source_id is not None and correction_source_id.strip():
                source_ids.append(correction_source_id.strip())
        explicit_source_ids = fields.get("source_ids")
        if explicit_source_ids is not None:
            source_ids.extend(_split_source_ids(explicit_source_ids))
    return tuple(_deduplicated(source_ids))


def _append_or_merge_faction_row(
    *,
    bridged_rows: dict[str, list[dict[str, str]]],
    row: dict[str, str],
) -> None:
    for existing in bridged_rows["Factions"]:
        if existing["id"] != row["id"]:
            continue
        for key, value in row.items():
            if key == "source_ids":
                continue
            if existing[key] != value:
                raise WahapediaBridgeError("Conflicting faction rows were produced.")
        merged_source_ids = _deduplicated(
            [*_split_source_ids(existing["source_ids"]), *_split_source_ids(row["source_ids"])]
        )
        existing["source_ids"] = _joined(tuple(merged_source_ids))
        return
    bridged_rows["Factions"].append(row)


def _split_source_ids(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def _correction_source_row(correction: PdfDatasheetCorrection) -> NormalizedSourceRow:
    return NormalizedSourceRow(
        source_package_id=DataPackageId(
            namespace="pdf", package_name="source-corrections", version="2026-06-10"
        ),
        source_table="PdfCorrections",
        source_row_id=f"{correction.datasheet_id}:keyword-correction",
        source_row_number=2,
        fields=(("source_id", correction.source_id),),
        text_fields=(),
    )


def _corrections_by_datasheet(
    corrections: tuple[PdfDatasheetCorrection, ...],
) -> dict[str, PdfDatasheetCorrection]:
    if type(corrections) is not tuple:
        raise WahapediaBridgeError("pdf_corrections must be a tuple.")
    by_datasheet: dict[str, PdfDatasheetCorrection] = {}
    for correction in corrections:
        if type(correction) is not PdfDatasheetCorrection:
            raise WahapediaBridgeError("pdf_corrections must contain correction values.")
        if correction.datasheet_id in by_datasheet:
            raise WahapediaBridgeError("pdf_corrections must not duplicate datasheets.")
        by_datasheet[correction.datasheet_id] = correction
    return by_datasheet


def _height_overrides_by_datasheet_and_model(
    overrides: tuple[ModelHeightOverride, ...],
) -> dict[tuple[str, str], ModelHeightOverride]:
    if type(overrides) is not tuple:
        raise WahapediaBridgeError("height_overrides must be a tuple.")
    by_key: dict[tuple[str, str], ModelHeightOverride] = {}
    for override in overrides:
        if type(override) is not ModelHeightOverride:
            raise WahapediaBridgeError("height_overrides must contain override values.")
        key = (override.datasheet_id, _name_key(override.model_name))
        if key in by_key:
            raise WahapediaBridgeError("height_overrides must not duplicate model names.")
        by_key[key] = override
    return by_key


def _required_height_override(
    *,
    context: _BridgeContext,
    datasheet_id: str,
    model_name: str,
) -> ModelHeightOverride:
    override = context.height_by_datasheet_and_model.get((datasheet_id, _name_key(model_name)))
    if override is None:
        raise WahapediaBridgeError("Representative model height override is required.")
    if override.reviewer_status is not GeometryReviewStatus.ACCEPTED:
        raise WahapediaBridgeError("Representative model height override must be accepted.")
    return override


def _skill_characteristic(row: NormalizedSourceRow) -> str:
    weapon_type = _required_field(row, "type").strip().casefold()
    if weapon_type == "melee":
        return "weapon_skill"
    return "ballistic_skill"


def _weapon_keywords(description: str) -> tuple[str, ...]:
    if not description.strip():
        return ()
    canonical_by_key = {_name_key(keyword.value): keyword.value for keyword in WeaponKeyword}
    keywords: list[str] = []
    for raw_keyword in description.split(","):
        key = _name_key(raw_keyword)
        keyword = canonical_by_key.get(key)
        if keyword is None:
            raise WahapediaBridgeError("Unsupported Wahapedia weapon keyword.")
        keywords.append(keyword)
    return tuple(sorted(_deduplicated(keywords)))


def _ability_timing_tags(name: str) -> str:
    key = _core_ability_name_key(name)
    if key == "deep-strike":
        return "deployment,reserves"
    if key == "infiltrators":
        return "deployment"
    if key == "leader":
        return "declare_battle_formations,attachments"
    if key == "support":
        return "declare_battle_formations,attachments"
    if key.startswith("scouts"):
        return "before_battle,scouts"
    if key.startswith("firing-deck"):
        return "shooting"
    if key.startswith("deadly-demise"):
        return "after_destroyed,deadly_demise"
    return ""


def _ability_parameter_tokens(*, name: str, parameter: str) -> str:
    stripped_parameter = _ability_parameter_token(parameter)
    if stripped_parameter:
        return stripped_parameter
    key = _core_ability_name_key(name)
    match = re.fullmatch(r"(scouts|firing-deck|deadly-demise)-(.+)", key)
    if match is None:
        return ""
    return _ability_parameter_token(match.group(2))


def _ability_parameter_token(value: str) -> str:
    stripped = value.strip().removesuffix('"').strip()
    if not stripped:
        return ""
    return stripped.upper()


def _core_ability_name_key(name: str) -> str:
    key = _name_key(name)
    if key.startswith("core-"):
        return key.removeprefix("core-")
    return key


def _model_profiles_by_name(entries: tuple[_CompositionEntry, ...]) -> dict[str, str]:
    by_name: dict[str, str] = {}
    for entry in entries:
        key = _name_key(entry.model_name)
        by_name[key] = entry.model_profile_id
        if key.endswith("s"):
            by_name[key[:-1]] = entry.model_profile_id
    return by_name


def _required_model_profile_id(model_profile_by_name: dict[str, str], model_name: str) -> str:
    model_profile_id = model_profile_by_name.get(_name_key(model_name))
    if model_profile_id is None:
        raise WahapediaBridgeError("Wargear option references an unknown model profile.")
    return model_profile_id


def _required_wargear_id(wargear_ids_by_name: dict[str, str], wargear_name: str) -> str:
    wargear_id = wargear_ids_by_name.get(_name_key(wargear_name))
    if wargear_id is None:
        raise WahapediaBridgeError("Wargear option references an unknown wargear item.")
    return wargear_id


def _joined(values: tuple[str, ...]) -> str:
    return ",".join(values)


def _name_key(value: str) -> str:
    return _slug(value)


def _slug(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    lowered = normalized.casefold().replace("&", " and ")
    characters: list[str] = []
    previous_dash = False
    for character in lowered:
        if character.isalnum():
            characters.append(character)
            previous_dash = False
        elif not previous_dash:
            characters.append("-")
            previous_dash = True
    slug = "".join(characters).strip("-")
    if not slug:
        raise WahapediaBridgeError("Could not derive a stable slug.")
    return slug


def _int_from_text(value: str) -> int:
    try:
        return int(value)
    except ValueError as exc:
        raise WahapediaBridgeError("Source value must be an integer.") from exc


def _validate_identifier(field_name: str, value: object) -> str:
    if type(value) is not str:
        raise WahapediaBridgeError(f"{field_name} must be a string.")
    stripped = value.strip()
    if not stripped:
        raise WahapediaBridgeError(f"{field_name} must not be empty.")
    return stripped


def _validate_identifier_tuple(field_name: str, values: tuple[str, ...]) -> tuple[str, ...]:
    if type(values) is not tuple:
        raise WahapediaBridgeError(f"{field_name} must be a tuple.")
    seen: set[str] = set()
    validated: list[str] = []
    for value in values:
        identifier = _validate_identifier(f"{field_name} value", value)
        if identifier in seen:
            raise WahapediaBridgeError(f"{field_name} must not contain duplicates.")
        seen.add(identifier)
        validated.append(identifier)
    return tuple(validated)


def _validate_positive_float(field_name: str, value: object) -> float:
    if not isinstance(value, int | float) or type(value) is bool:
        raise WahapediaBridgeError(f"{field_name} must be a number.")
    number = float(value)
    if number <= 0.0:
        raise WahapediaBridgeError(f"{field_name} must be greater than 0.")
    return number


def _deduplicated(values: list[str]) -> list[str]:
    seen: set[str] = set()
    deduplicated: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        deduplicated.append(value)
    return deduplicated


CHAOS_DAEMONS_BLOODCRUSHERS_PDF_CORRECTION = PdfDatasheetCorrection(
    datasheet_id="000001115",
    source_id="pdf:chaos-daemons-faction-pack:2026-06-10:p30-p31",
    removed_keywords=("Shadow Legion",),
)

CHAOS_DAEMONS_BLOODCRUSHERS_HEIGHT_OVERRIDES = (
    ModelHeightOverride(
        datasheet_id="000001115",
        model_name="Bloodhunter",
        height=2.75,
        height_units=GeometrySourceUnits.INCHES,
        height_source_id="geometry-review:chaos-daemons:bloodcrushers:bloodhunter:height",
        height_document_reference="Chaos Daemons Faction Pack p.30-31",
    ),
    ModelHeightOverride(
        datasheet_id="000001115",
        model_name="Bloodcrushers",
        height=2.75,
        height_units=GeometrySourceUnits.INCHES,
        height_source_id="geometry-review:chaos-daemons:bloodcrushers:bloodcrushers:height",
        height_document_reference="Chaos Daemons Faction Pack p.30-31",
    ),
)

DEFAULT_PDF_CORRECTIONS = (CHAOS_DAEMONS_BLOODCRUSHERS_PDF_CORRECTION,)
DEFAULT_HEIGHT_OVERRIDES = CHAOS_DAEMONS_BLOODCRUSHERS_HEIGHT_OVERRIDES
