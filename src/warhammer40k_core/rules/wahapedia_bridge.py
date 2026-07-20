from __future__ import annotations

import csv
import io
import json
import re
import unicodedata
from dataclasses import dataclass

from warhammer40k_core.core.datasheet import (
    MUSTERING_WARLORD_FORBIDDEN,
    MUSTERING_WARLORD_REQUIRED,
    MUSTERING_WARLORD_RULE_KEY,
    CatalogAbilitySourceKind,
    CatalogAbilitySupport,
    DamagedEffectDefinition,
    DamagedEffectKind,
    DamagedWeaponScope,
    DatasheetMusteringOptionEffectKind,
    WargearOptionConditionKind,
    WargearOptionEffectKind,
)
from warhammer40k_core.core.model_geometry_catalog import GeometryReviewStatus
from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.core.weapon_profiles import (
    AbilityDescriptor,
    AntiKeywordMatchMode,
    WeaponKeyword,
    WeaponProfileError,
    validate_weapon_ability_descriptor_multiplicity,
)
from warhammer40k_core.rules import wahapedia_base_size_bridge as _base_size_bridge
from warhammer40k_core.rules import wahapedia_bridge_columns as _bridge_columns
from warhammer40k_core.rules import wahapedia_model_profile_mapping as _model_profiles
from warhammer40k_core.rules.attachment_wargear_requirements import (
    AttachmentWargearRequirement,
)
from warhammer40k_core.rules.data_package import DataPackageId
from warhammer40k_core.rules.rule_compiler import compile_rule_source_text
from warhammer40k_core.rules.source_data import RuleSourceText
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    datasheet_keyword_lexicon_2026_06_14 as datasheet_keyword_lexicon_source,
)
from warhammer40k_core.rules.wahapedia_base_size_bridge import (
    EventCompanionBaseSizesByKey,
    base_size_evidence,
    event_companion_base_sizes_by_key,
)
from warhammer40k_core.rules.wahapedia_bridge_defaults import (
    DEFAULT_HEIGHT_OVERRIDES,
    DEFAULT_PDF_CORRECTIONS,
)
from warhammer40k_core.rules.wahapedia_bridge_defaults import (
    ModelHeightOverride as ModelHeightOverride,
)
from warhammer40k_core.rules.wahapedia_bridge_defaults import (
    PdfDatasheetCorrection as PdfDatasheetCorrection,
)
from warhammer40k_core.rules.wahapedia_bridge_patterns import (
    COUNT_WORDS,
    DAEMONIC_ALLEGIANCE_ADDITIONAL_WARGEAR_RE,
    DAEMONIC_ALLEGIANCE_KEYWORDS,
    DAMAGED_ABILITY_SELECTION_LIMIT_RE,
    DAMAGED_ATTACKS_ADD_RE,
    DAMAGED_ATTACKS_HALVE_RE,
    DAMAGED_HEADER_RE,
    DAMAGED_HIT_RE,
    DAMAGED_IGNORABLE_REMAINDER_RE,
    DAMAGED_OC_RE,
    DAMAGED_RANGE_RE,
    DAMAGED_SHOOTING_WEAPON_SELECTION_LIMIT_RE,
    FACTION_ARMY_RULE_ABILITY_IDS_BY_FACTION_ID,
    OPTION_RE,
    REPLACEMENT_WITH_CHOICES_RE,
    REPLACEMENT_WITH_REQUIRED_CHOICES_RE,
    SINGLE_REPLACEMENT_RE,
    UNIT_COMPOSITION_MAX_MODELS_RE,
    UNIT_COMPOSITION_PART_RE,
    UNIT_COMPOSITION_SEPARATOR_RE,
)
from warhammer40k_core.rules.wahapedia_bridge_rows import (
    BridgeSourceArtifact,
    bridge_rows_by_table,
    resolve_bridge_ability_source_row,
)
from warhammer40k_core.rules.wahapedia_equipment_choice_bridge import append_choice_rows
from warhammer40k_core.rules.wahapedia_invulnerable_save_bridge import (
    ConditionalInvulnerableSaveBridge,
)
from warhammer40k_core.rules.wahapedia_loadout_bridge import (
    LoadoutAssignments,
    parse_loadout_assignments,
    uniform_loadout_wargear_count,
)
from warhammer40k_core.rules.wahapedia_replacement_option_bridge import (
    append_extended_replacement_rows,
    replacement_choices,
)
from warhammer40k_core.rules.wahapedia_schema import (
    NormalizedSourceRow,
    WahapediaCsvTable,
    WahapediaJsonArtifact,
)
from warhammer40k_core.rules.wahapedia_static_rule_ir import compact_json, payload_by_source_row_id
from warhammer40k_core.rules.wahapedia_unit_composition_bridge import (
    composition_count_range,
    composition_max_unit_models,
    optional_int_text,
)
from warhammer40k_core.rules.wahapedia_unit_wargear_option_bridge import (
    append_unit_wargear_option_rows,
)
from warhammer40k_core.rules.weapon_profile_names import WEAPON_PROFILE_SUFFIX_RE

EVENT_COMPANION_BASE_SIZE_GUIDE_DOCUMENT_REFERENCE = (
    _base_size_bridge.EVENT_COMPANION_BASE_SIZE_GUIDE_DOCUMENT_REFERENCE
)
EVENT_COMPANION_BASE_SIZE_GUIDE_SOURCE_ID = (
    _base_size_bridge.EVENT_COMPANION_BASE_SIZE_GUIDE_SOURCE_ID
)


class WahapediaBridgeError(ValueError):
    """Raised when Wahapedia rows cannot be bridged into canonical source rows."""


_SOURCE_KEYWORD_SEQUENCE_PARTS = (
    datasheet_keyword_lexicon_source.canonical_datasheet_keyword_sequence_parts()
)


def build_wahapedia_canonical_bridge_artifacts(
    *,
    source_artifacts: tuple[BridgeSourceArtifact, ...],
    bridge_package_id: DataPackageId,
    datasheet_ids: tuple[str, ...],
    pdf_corrections: tuple[PdfDatasheetCorrection, ...] | None = None,
    height_overrides: tuple[ModelHeightOverride, ...] | None = None,
    attachment_wargear_requirements: tuple[AttachmentWargearRequirement, ...] = (),
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
    rows_by_table = bridge_rows_by_table(source_artifacts, error_type=WahapediaBridgeError)
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
    attachment_wargear_requirements_by_target = _attachment_wargear_requirements_by_target(
        attachment_wargear_requirements
    )
    context = _BridgeContext(
        rows_by_table=rows_by_table,
        selected_datasheet_ids=frozenset(selected_datasheet_ids),
        corrections_by_datasheet=corrections_by_datasheet,
        height_by_datasheet_and_model=height_by_datasheet_and_model,
        attachment_wargear_requirements_by_target=attachment_wargear_requirements_by_target,
        event_companion_base_sizes_by_key=event_companion_base_sizes_by_key(
            error_type=WahapediaBridgeError
        ),
    )
    bridged_rows = _empty_bridge_rows()
    for datasheet_id in selected_datasheet_ids:
        _bridge_datasheet(datasheet_id=datasheet_id, context=context, bridged_rows=bridged_rows)
    _validate_active_attachment_wargear_requirements(
        context=context,
        bridged_rows=bridged_rows,
    )
    return _artifacts_from_bridge_rows(
        bridge_package_id=bridge_package_id,
        rows_by_table=bridged_rows,
    )


@dataclass(frozen=True, slots=True)
class _BridgeContext:
    rows_by_table: dict[str, tuple[NormalizedSourceRow, ...]]
    selected_datasheet_ids: frozenset[str]
    corrections_by_datasheet: dict[str, PdfDatasheetCorrection]
    height_by_datasheet_and_model: dict[tuple[str, str], ModelHeightOverride]
    attachment_wargear_requirements_by_target: dict[tuple[str, str], AttachmentWargearRequirement]
    event_companion_base_sizes_by_key: EventCompanionBaseSizesByKey


@dataclass(frozen=True, slots=True)
class _CompositionEntry:
    line: str
    model_name: str
    model_profile_id: str
    min_models: int
    max_models: int
    source_rows: tuple[NormalizedSourceRow, ...]


@dataclass(frozen=True, slots=True)
class _CompositionPart:
    model_name: str
    min_models: int
    max_models: int
    source_row: NormalizedSourceRow


@dataclass(slots=True)
class _CompositionEntryAccumulator:
    line: str
    model_name: str
    model_profile_id: str
    min_models: int
    max_models: int
    source_rows: list[NormalizedSourceRow]


@dataclass(frozen=True, slots=True)
class _WeaponKeywordEntry:
    keyword: WeaponKeyword | None
    ability: AbilityDescriptor | None = None


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
    if not model_source_rows:
        raise WahapediaBridgeError("Datasheet has no Wahapedia model stat rows.")
    composition_entries = _composition_entries(context=context, datasheet_id=datasheet_id)
    model_source_rows_by_profile_id = _model_profiles.model_source_rows_by_profile_id(
        composition_profiles=composition_entries,
        model_source_rows=model_source_rows,
        error_type=WahapediaBridgeError,
    )
    conditional_invulnerable_save = _model_profiles.conditional_invulnerable_save_for_model_rows(
        datasheet_id=datasheet_id,
        model_source_rows=model_source_rows,
        error_type=WahapediaBridgeError,
    )
    loadout_assignments = parse_loadout_assignments(
        loadout=_normalized_or_field(datasheet_row, "loadout"),
        model_profile_by_name=_model_profiles_by_name(composition_entries),
        all_model_profile_ids=tuple(entry.model_profile_id for entry in composition_entries),
        error_type=WahapediaBridgeError,
    )
    cost_rows = _rows_matching(
        context.rows_by_table, "Datasheets_models_cost", "datasheet_id", datasheet_id
    )
    keywords, faction_keywords, keyword_source_ids = _keywords_for_datasheet(
        context=context,
        datasheet_id=datasheet_id,
    )
    faction_ability_row, faction_ability_source = _faction_catalog_ability_rows(
        context=context,
        datasheet_id=datasheet_id,
        faction_id=faction_id,
    )
    faction_source_rows = (
        (faction_row, faction_ability_source)
        if faction_ability_row is None
        else (faction_row, faction_ability_row, faction_ability_source)
    )
    faction_source_ids = _source_ids(*faction_source_rows)
    _append_or_merge_faction_row(
        bridged_rows=bridged_rows,
        row={
            "id": faction_id,
            "name": _raw_or_field(faction_row, "name"),
            "content_scope": "matched_play",
            "faction_keywords": _joined(faction_keywords),
            "army_rule_id": _required_field(faction_ability_source, "id"),
            "army_rule_name": _raw_or_field(faction_ability_source, "name"),
            "source_ids": _joined(faction_source_ids),
        },
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
            "damaged_effects": _damaged_effects_json(
                datasheet_id=datasheet_id,
                damaged_description=_normalized_or_field(datasheet_row, "damaged_description"),
                composition_entries=composition_entries,
                source_id=datasheet_row.stable_source_id(),
            ),
            "max_unit_models": optional_int_text(
                _composition_max_unit_models(context=context, datasheet_id=datasheet_id)
            ),
            "source_ids": _joined(_source_ids(datasheet_row, *keyword_source_ids)),
        }
    )
    for entry in composition_entries:
        model_source_row = model_source_rows_by_profile_id[entry.model_profile_id]
        model_source_ids = _source_ids(model_source_row, *cost_rows)
        height = _required_height_override(
            context=context,
            datasheet_id=datasheet_id,
            model_name=entry.model_name,
        )
        base_size = base_size_evidence(
            faction_name=_required_field(faction_row, "name"),
            datasheet_name=_required_field(datasheet_row, "name"),
            model_name=entry.model_name,
            model_source_row=model_source_row,
            event_companion_base_sizes=context.event_companion_base_sizes_by_key,
            error_type=WahapediaBridgeError,
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
                "inv_sv": (
                    _required_field(model_source_row, "inv_sv")
                    if conditional_invulnerable_save is None
                    else conditional_invulnerable_save.base_invulnerable_save
                ),
                "w": _required_field(model_source_row, "W"),
                "ld": _required_field(model_source_row, "Ld"),
                "oc": _required_field(model_source_row, "OC"),
                "ws": "-",
                "bs": "-",
                "min_models": str(entry.min_models),
                "max_models": str(entry.max_models),
                "allows_zero_models": "true" if entry.min_models == 0 else "",
                "base_size": base_size.base_size_text,
                "base_size_source_id": base_size.source_id,
                "base_size_document_reference": base_size.document_reference,
                "height": str(height.height),
                "height_units": height.height_units.value,
                "height_source_id": height.height_source_id,
                "height_document_reference": height.height_document_reference,
                "height_reviewer_status": height.reviewer_status.value,
                "height_evidence_kind": height.evidence_kind.value,
                "source_ids": _joined(
                    tuple(
                        _deduplicated(
                            [
                                *model_source_ids,
                                *_source_ids(*entry.source_rows),
                                *base_size.source_ids,
                            ]
                        )
                    )
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
        loadout_assignments=loadout_assignments,
        bridged_rows=bridged_rows,
    )
    _bridge_abilities(
        context=context,
        datasheet_id=datasheet_id,
        composition_entries=composition_entries,
        loadout_assignments=loadout_assignments,
        wargear_ids_by_name=wargear_ids_by_name,
        bridged_rows=bridged_rows,
    )
    if conditional_invulnerable_save is not None:
        _append_conditional_invulnerable_save_ability(
            datasheet_id=datasheet_id,
            bridge=conditional_invulnerable_save,
            bridged_rows=bridged_rows,
        )
    _bridge_daemonic_allegiance_options(
        context=context,
        datasheet_id=datasheet_id,
        composition_entries=composition_entries,
        wargear_ids_by_name=wargear_ids_by_name,
        bridged_rows=bridged_rows,
    )
    _bridge_options(
        context=context,
        datasheet_id=datasheet_id,
        composition_entries=composition_entries,
        loadout_assignments=loadout_assignments,
        wargear_ids_by_name=wargear_ids_by_name,
        resource_namespace=_required_field(faction_row, "name"),
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
    accumulators: dict[str, _CompositionEntryAccumulator] = {}
    for row in rows:
        for part in _composition_parts_from_row(row):
            key = _name_key(part.model_name)
            accumulator = accumulators.get(key)
            if accumulator is None:
                accumulators[key] = _CompositionEntryAccumulator(
                    line=str(len(accumulators) + 1),
                    model_name=part.model_name,
                    model_profile_id=f"{datasheet_id}:{_slug(part.model_name)}",
                    min_models=part.min_models,
                    max_models=part.max_models,
                    source_rows=[part.source_row],
                )
                continue
            accumulator.min_models = min(accumulator.min_models, part.min_models)
            accumulator.max_models = max(accumulator.max_models, part.max_models)
            if not any(
                source_row.stable_source_id() == part.source_row.stable_source_id()
                for source_row in accumulator.source_rows
            ):
                accumulator.source_rows.append(part.source_row)
    if not accumulators:
        raise WahapediaBridgeError("Datasheet has no model composition entries.")
    return tuple(
        _CompositionEntry(
            line=accumulator.line,
            model_name=accumulator.model_name,
            model_profile_id=accumulator.model_profile_id,
            min_models=accumulator.min_models,
            max_models=accumulator.max_models,
            source_rows=tuple(accumulator.source_rows),
        )
        for accumulator in accumulators.values()
    )


def _composition_parts_from_row(row: NormalizedSourceRow) -> tuple[_CompositionPart, ...]:
    description = _required_field(row, "description").strip()
    if description.casefold() == "or:":
        return ()
    if UNIT_COMPOSITION_MAX_MODELS_RE.fullmatch(description) is not None:
        return ()
    parts: list[_CompositionPart] = []
    position = 0
    for match in UNIT_COMPOSITION_PART_RE.finditer(description):
        separator = description[position : match.start()]
        if separator and UNIT_COMPOSITION_SEPARATOR_RE.fullmatch(separator) is None:
            raise WahapediaBridgeError("Unsupported unit composition row shape.")
        minimum, maximum = composition_count_range(
            match.group("count"),
            error_type=WahapediaBridgeError,
        )
        parts.append(
            _CompositionPart(
                model_name=match.group("name").strip(),
                min_models=minimum,
                max_models=maximum,
                source_row=row,
            )
        )
        position = match.end()
    if not parts or position != len(description):
        raise WahapediaBridgeError("Unsupported unit composition row shape.")
    return tuple(parts)


def _composition_max_unit_models(*, context: _BridgeContext, datasheet_id: str) -> int | None:
    return composition_max_unit_models(
        rows=_rows_matching(
            context.rows_by_table,
            "Datasheets_unit_composition",
            "datasheet_id",
            datasheet_id,
        ),
        error_type=WahapediaBridgeError,
    )


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
        keyword = _raw_or_field(row, "keyword").strip()
        if not keyword:
            if _required_field(row, "is_faction_keyword") != "true":
                raise WahapediaBridgeError(
                    "Empty datasheet keyword rows must be faction-keyword placeholders."
                )
            source_rows.append(row)
            continue
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


def _faction_catalog_ability_rows(
    *,
    context: _BridgeContext,
    datasheet_id: str,
    faction_id: str,
) -> tuple[NormalizedSourceRow | None, NormalizedSourceRow]:
    rows = tuple(
        row
        for row in _rows_matching(
            context.rows_by_table, "Datasheets_abilities", "datasheet_id", datasheet_id
        )
        if _required_field(row, "type") == "Faction"
    )
    if len(rows) == 1:
        ability_source = _ability_source_row(context=context, ability_row=rows[0])
        return rows[0], ability_source
    if not rows:
        ability_id = FACTION_ARMY_RULE_ABILITY_IDS_BY_FACTION_ID.get(faction_id)
        if ability_id is None:
            raise WahapediaBridgeError("Datasheet has no faction ability fallback.")
        return None, _ability_source_row_by_id_and_faction(
            context=context,
            ability_id=ability_id,
            faction_id=faction_id,
        )
    if len(rows) != 1:
        raise WahapediaBridgeError("Datasheet must link exactly one faction ability.")
    raise WahapediaBridgeError("Datasheet faction ability lookup failed.")


def _ability_source_row(
    *, context: _BridgeContext, ability_row: NormalizedSourceRow
) -> NormalizedSourceRow:
    return resolve_bridge_ability_source_row(
        rows_by_table=context.rows_by_table,
        ability_row=ability_row,
        error_type=WahapediaBridgeError,
    )


def _ability_source_row_by_id_and_faction(
    *,
    context: _BridgeContext,
    ability_id: str,
    faction_id: str,
) -> NormalizedSourceRow:
    candidates = tuple(
        row
        for row in context.rows_by_table.get("Abilities", ())
        if _required_field(row, "id") == ability_id
        and _required_field(row, "faction_id") == faction_id
    )
    if len(candidates) != 1:
        raise WahapediaBridgeError("Faction ability fallback did not resolve one source row.")
    return candidates[0]


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
    loadout_assignments: LoadoutAssignments | None,
    bridged_rows: dict[str, list[dict[str, str]]],
) -> dict[str, str]:
    wargear_ids_by_name: dict[str, str] = {}
    model_profile_ids = tuple(entry.model_profile_id for entry in composition_entries)
    emitted_default_wargear_ids: set[str] = set()
    non_weapon_keyword_name_keys = _wargear_profile_ability_name_keys(
        context=context,
        datasheet_id=datasheet_id,
    )
    source_rows = _rows_matching(
        context.rows_by_table, "Datasheets_wargear", "datasheet_id", datasheet_id
    )
    prepared_rows: list[tuple[NormalizedSourceRow, str]] = []
    profile_count_by_wargear_id: dict[str, int] = {}
    for row in source_rows:
        name = _required_wargear_name(
            row=row,
            default_wargear_name_keys=(
                None if loadout_assignments is None else loadout_assignments.wargear_name_keys()
            ),
        )
        if name is None:
            continue
        prepared_rows.append((row, name))
        wargear_id = f"{datasheet_id}:{_slug(_base_wargear_name(name))}"
        profile_count_by_wargear_id[wargear_id] = profile_count_by_wargear_id.get(wargear_id, 0) + 1
    for row, name in prepared_rows:
        base_name = _base_wargear_name(name)
        profile_name = _weapon_profile_name(name)
        wargear_id = f"{datasheet_id}:{_slug(base_name)}"
        wargear_ids_by_name[_name_key(base_name)] = wargear_id
        wargear_ids_by_name[_name_key(name)] = wargear_id
        default_model_profile_ids = (
            model_profile_ids
            if loadout_assignments is None
            else loadout_assignments.profile_ids_for(base_name)
        )
        is_default_loadout = bool(default_model_profile_ids) and (
            wargear_id not in emitted_default_wargear_ids
        )
        if is_default_loadout:
            emitted_default_wargear_ids.add(wargear_id)
        description = _required_field(row, "description")
        bridged_rows["Datasheets_wargear"].append(
            {
                "datasheet_id": datasheet_id,
                "line": _required_field(row, "line"),
                "line_in_wargear": _required_field(row, "line_in_wargear"),
                "name": _raw_or_field(row, "name"),
                "wargear_id": wargear_id,
                "weapon_profile_id": (
                    f"{wargear_id}:{_slug(profile_name)}"
                    if profile_name is not None
                    else (
                        f"{wargear_id}:{_slug(_required_field(row, 'type'))}"
                        if profile_count_by_wargear_id[wargear_id] > 1
                        else f"{wargear_id}:standard"
                    )
                ),
                "model_profile_ids": _joined(
                    default_model_profile_ids if is_default_loadout else model_profile_ids
                ),
                "range": _required_field(row, "range"),
                "a": _required_field(row, "A"),
                "skill_characteristic": _skill_characteristic(row),
                "skill": _skill_value(row),
                "s": _required_field(row, "S"),
                "ap": _required_field(row, "AP"),
                "d": _required_field(row, "D"),
                "weapon_keywords": _joined(
                    _weapon_keywords(
                        description,
                        ignored_name_keys=non_weapon_keyword_name_keys,
                    )
                ),
                "weapon_abilities": _weapon_abilities_payload(
                    description,
                    ignored_name_keys=non_weapon_keyword_name_keys,
                ),
                "default_loadout": "true" if is_default_loadout else "false",
                "default_wargear_count": (
                    str(
                        uniform_loadout_wargear_count(
                            loadout_assignments=loadout_assignments,
                            wargear_name=base_name,
                            model_profile_ids=default_model_profile_ids,
                            error_type=WahapediaBridgeError,
                        )
                    )
                    if is_default_loadout
                    else ""
                ),
                "source_ids": _joined(_source_ids(row)),
            }
        )
    return wargear_ids_by_name


def _bridge_abilities(
    *,
    context: _BridgeContext,
    datasheet_id: str,
    composition_entries: tuple[_CompositionEntry, ...],
    loadout_assignments: LoadoutAssignments | None,
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
        description_source_row = row
        ability_type = _required_field(row, "type")
        if ability_id:
            ability_source = _ability_source_row(context=context, ability_row=row)
            source_rows = (row, ability_source)
            name = _raw_or_field(ability_source, "name")
            description = _raw_or_field(ability_source, "description")
            description_source_row = ability_source
        else:
            ability_id = f"{datasheet_id}:{_slug(name)}"
        parameter = _raw_or_field(row, "parameter")
        source_kind = _ability_source_kind(ability_type)
        source_wargear_id = ""
        rule_ir_payload = ""
        rule_ir_diagnostics = ""
        support = CatalogAbilitySupport.DESCRIPTOR_ONLY
        if source_kind is CatalogAbilitySourceKind.WARGEAR:
            source_wargear_id = (
                _wargear_profile_ability_source_wargear_id(
                    context=context,
                    datasheet_id=datasheet_id,
                    ability_name=name,
                )
                if _is_wargear_profile_ability_type(ability_type)
                else f"{datasheet_id}:{_slug(name)}"
            )
        if source_kind in {CatalogAbilitySourceKind.DATASHEET, CatalogAbilitySourceKind.WARGEAR}:
            source_text = _rule_source_text_from_row_field(
                row=description_source_row,
                column_name="description",
            )
            mustering_warlord_value = (
                _mustering_warlord_value(
                    normalized_description=source_text.normalized_text,
                )
                if source_kind is CatalogAbilitySourceKind.DATASHEET
                else None
            )
            if mustering_warlord_value is not None:
                rule_ir_payload = compact_json(
                    {MUSTERING_WARLORD_RULE_KEY: mustering_warlord_value}
                )
            else:
                static_rule_ir_payload = None
                if source_kind in {
                    CatalogAbilitySourceKind.DATASHEET,
                    CatalogAbilitySourceKind.WARGEAR,
                }:
                    static_rule_ir_payload = payload_by_source_row_id(
                        description_source_row.source_row_id
                    )
                if static_rule_ir_payload is not None:
                    rule_ir_payload = compact_json(static_rule_ir_payload)
                    rule_ir_diagnostics = compact_json([])
                    support = CatalogAbilitySupport.GENERIC_RULE_IR
                else:
                    compiled = compile_rule_source_text(
                        source_text,
                        source_keyword_sequence_parts=_SOURCE_KEYWORD_SEQUENCE_PARTS,
                    )
                    rule_ir_diagnostics = compact_json(_rule_ir_diagnostics(compiled.rule_ir))
                    if compiled.rule_ir.is_supported:
                        rule_ir_payload = compact_json(compiled.rule_ir.to_payload())
                        support = CatalogAbilitySupport.GENERIC_RULE_IR
                    else:
                        if source_kind is CatalogAbilitySourceKind.WARGEAR:
                            rule_ir_payload = compact_json(compiled.rule_ir.to_payload())
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
        if source_kind is CatalogAbilitySourceKind.WARGEAR and not _is_wargear_profile_ability_type(
            ability_type
        ):
            wargear_id = source_wargear_id
            wargear_ids_by_name[_name_key(name)] = wargear_id
            model_profile_ids = tuple(entry.model_profile_id for entry in composition_entries)
            default_model_profile_ids = (
                () if loadout_assignments is None else loadout_assignments.profile_ids_for(name)
            )
            bridged_rows["Datasheets_wargear"].append(
                {
                    "datasheet_id": datasheet_id,
                    "line": f"ability-{_required_field(row, 'line')}",
                    "line_in_wargear": "1",
                    "name": name,
                    "wargear_id": wargear_id,
                    "weapon_profile_id": "",
                    "model_profile_ids": _joined(
                        default_model_profile_ids
                        if default_model_profile_ids
                        else model_profile_ids
                    ),
                    "range": "",
                    "a": "",
                    "skill_characteristic": "",
                    "skill": "",
                    "s": "",
                    "ap": "",
                    "d": "",
                    "weapon_keywords": "",
                    "weapon_abilities": "",
                    "default_loadout": "true" if default_model_profile_ids else "false",
                    "default_wargear_count": "1" if default_model_profile_ids else "",
                    "source_ids": _joined(_source_ids(row)),
                }
            )


def _append_conditional_invulnerable_save_ability(
    *,
    datasheet_id: str,
    bridge: ConditionalInvulnerableSaveBridge,
    bridged_rows: dict[str, list[dict[str, str]]],
) -> None:
    bridged_rows["Datasheets_abilities"].append(
        {
            "datasheet_id": datasheet_id,
            "line": "model-invulnerable-save",
            "ability_id": bridge.ability_id,
            "name": bridge.ability_name,
            "description": bridge.normalized_text,
            "parameter": "",
            "type": "Datasheet",
            "support": CatalogAbilitySupport.GENERIC_RULE_IR.value,
            "source_kind": CatalogAbilitySourceKind.DATASHEET.value,
            "effect_description": bridge.normalized_text,
            "source_wargear_id": "",
            "rule_ir_payload": compact_json(bridge.rule_ir.to_payload()),
            "rule_ir_diagnostics": compact_json([]),
            "timing_tags": "passive_query",
            "parameter_tokens": "",
            "source_ids": _joined(bridge.source_ids),
        }
    )


def _bridge_options(
    *,
    context: _BridgeContext,
    datasheet_id: str,
    composition_entries: tuple[_CompositionEntry, ...],
    loadout_assignments: LoadoutAssignments | None,
    wargear_ids_by_name: dict[str, str],
    resource_namespace: str,
    bridged_rows: dict[str, list[dict[str, str]]],
) -> None:
    model_profile_by_name = _model_profiles_by_name(composition_entries)
    profile_ids = tuple(entry.model_profile_id for entry in composition_entries)
    option_rows = _rows_matching(
        context.rows_by_table, "Datasheets_options", "datasheet_id", datasheet_id
    )
    max_models_by_profile_id = {
        entry.model_profile_id: entry.max_models for entry in composition_entries
    }
    maximum_unit_models = _composition_max_unit_models(
        context=context, datasheet_id=datasheet_id
    ) or sum(entry.max_models for entry in composition_entries)
    minimum_unit_models = sum(entry.min_models for entry in composition_entries)
    for row in option_rows:
        description = _required_field(row, "description")
        if description == "None":
            continue
        if append_unit_wargear_option_rows(
            row=row,
            datasheet_id=datasheet_id,
            model_profile_by_name=model_profile_by_name,
            max_models_by_profile_id=max_models_by_profile_id,
            required_model_profile_ids=tuple(
                entry.model_profile_id for entry in composition_entries if entry.min_models > 0
            ),
            minimum_unit_models=minimum_unit_models,
            maximum_unit_models=maximum_unit_models,
            resource_namespace=resource_namespace,
            loadout_assignments=loadout_assignments,
            wargear_ids_by_name=wargear_ids_by_name,
            bridged_rows=bridged_rows,
            error_type=WahapediaBridgeError,
        ):
            continue
        if append_choice_rows(
            row, datasheet_id, profile_ids, wargear_ids_by_name, bridged_rows, WahapediaBridgeError
        ):
            continue
        if append_extended_replacement_rows(
            row=row,
            option_rows=option_rows,
            datasheet_id=datasheet_id,
            model_profile_by_name=model_profile_by_name,
            wargear_ids_by_name=wargear_ids_by_name,
            bridged_rows=bridged_rows,
            error_type=WahapediaBridgeError,
        ):
            continue
        replacement_match = REPLACEMENT_WITH_REQUIRED_CHOICES_RE.fullmatch(description)
        if replacement_match is not None:
            _bridge_replacement_with_required_choices_option(
                row=row,
                datasheet_id=datasheet_id,
                model_profile_id=_single_model_profile_id(composition_entries),
                wargear_ids_by_name=wargear_ids_by_name,
                match=replacement_match,
                bridged_rows=bridged_rows,
            )
            continue
        replacement_choices_match = REPLACEMENT_WITH_CHOICES_RE.fullmatch(description)
        if replacement_choices_match is not None:
            _bridge_replacement_with_choices_option(
                row=row,
                datasheet_id=datasheet_id,
                model_profile_id=_single_model_profile_id(composition_entries),
                wargear_ids_by_name=wargear_ids_by_name,
                match=replacement_choices_match,
                bridged_rows=bridged_rows,
            )
            continue
        single_replacement_match = SINGLE_REPLACEMENT_RE.fullmatch(description)
        if single_replacement_match is not None:
            _bridge_single_replacement_option(
                row=row,
                datasheet_id=datasheet_id,
                model_profile_id=_single_model_profile_id(composition_entries),
                wargear_ids_by_name=wargear_ids_by_name,
                match=single_replacement_match,
                bridged_rows=bridged_rows,
            )
            continue
        match = OPTION_RE.fullmatch(description)
        if match is None:
            raise WahapediaBridgeError(
                f"Unsupported wargear option row shape: {row.source_row_id}."
            )
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
                "effect_replaced_wargear_id": "",
                "effect_model_count": "1",
                "effect_wargear_count": "1",
                "source_ids": _joined(_source_ids(row)),
            }
        )


def _bridge_daemonic_allegiance_options(
    *,
    context: _BridgeContext,
    datasheet_id: str,
    composition_entries: tuple[_CompositionEntry, ...],
    wargear_ids_by_name: dict[str, str],
    bridged_rows: dict[str, list[dict[str, str]]],
) -> None:
    rows: list[NormalizedSourceRow] = []
    for row in _rows_matching(
        context.rows_by_table,
        "Datasheets_abilities",
        "datasheet_id",
        datasheet_id,
    ):
        if _name_key(_resolved_ability_name(context=context, ability_row=row)) == (
            "daemonic-allegiance"
        ):
            rows.append(row)
    if not rows:
        return
    if len(rows) != 1:
        raise WahapediaBridgeError("Datasheet has multiple Daemonic Allegiance rows.")
    row = rows[0]
    source_rows: tuple[NormalizedSourceRow, ...] = (row,)
    description_source_row = row
    if _required_field(row, "ability_id"):
        ability_source = _ability_source_row(context=context, ability_row=row)
        source_rows = (row, ability_source)
        description_source_row = ability_source
    description = _normalized_or_field(description_source_row, "description")
    _validate_daemonic_allegiance_keywords(description)
    additional_wargear_by_keyword = _daemonic_allegiance_additional_wargear_by_keyword(description)
    model_profile_id = _single_model_profile_id(composition_entries)
    selection_group_id = f"{datasheet_id}:daemonic-allegiance"
    source_line = _required_field(row, "line")
    for index, keyword in enumerate(DAEMONIC_ALLEGIANCE_KEYWORDS, start=1):
        option_id = f"{selection_group_id}:{_slug(keyword)}"
        common_fields = {
            "datasheet_id": datasheet_id,
            "description": _raw_or_field(description_source_row, "description"),
            "option_id": option_id,
            "selection_group_id": selection_group_id,
            "label": keyword,
            "model_profile_id": model_profile_id,
            "required": "true",
            "source_ids": _joined(_source_ids(*source_rows)),
        }
        bridged_rows["Datasheets_mustering_options"].append(
            {
                **common_fields,
                "line": f"{source_line}.{index}.1",
                "effect_kind": DatasheetMusteringOptionEffectKind.ADD_KEYWORD.value,
                "effect_keyword": keyword,
                "effect_wargear_id": "",
                "effect_model_count": "",
                "effect_wargear_count": "",
            }
        )
        additional_wargear_name = additional_wargear_by_keyword.get(keyword)
        if additional_wargear_name is None:
            continue
        bridged_rows["Datasheets_mustering_options"].append(
            {
                **common_fields,
                "line": f"{source_line}.{index}.2",
                "effect_kind": DatasheetMusteringOptionEffectKind.ADD_WARGEAR.value,
                "effect_keyword": "",
                "effect_wargear_id": _required_wargear_id(
                    wargear_ids_by_name,
                    additional_wargear_name,
                ),
                "effect_model_count": "1",
                "effect_wargear_count": "1",
            }
        )


def _validate_daemonic_allegiance_keywords(description: str) -> None:
    present = {
        match.group(0).upper()
        for match in re.finditer(
            r"\b(?:KHORNE|TZEENTCH|NURGLE|SLAANESH)\b",
            description,
            re.IGNORECASE,
        )
    }
    if present != set(DAEMONIC_ALLEGIANCE_KEYWORDS):
        raise WahapediaBridgeError("Daemonic Allegiance row must declare all four allegiances.")


def _daemonic_allegiance_additional_wargear_by_keyword(description: str) -> dict[str, str]:
    matches = tuple(DAEMONIC_ALLEGIANCE_ADDITIONAL_WARGEAR_RE.finditer(description))
    if not matches:
        if "additionally equipped with" in description.casefold():
            raise WahapediaBridgeError("Unsupported Daemonic Allegiance additional wargear shape.")
        return {}
    by_keyword: dict[str, str] = {}
    for match in matches:
        keyword = match.group("keyword").upper()
        if keyword in by_keyword:
            raise WahapediaBridgeError("Daemonic Allegiance additional wargear duplicates keyword.")
        by_keyword[keyword] = match.group("wargear").strip().removesuffix(".").strip()
    if set(by_keyword) != set(DAEMONIC_ALLEGIANCE_KEYWORDS):
        raise WahapediaBridgeError(
            "Daemonic Allegiance additional wargear must define all allegiances."
        )
    return by_keyword


def _resolved_ability_name(*, context: _BridgeContext, ability_row: NormalizedSourceRow) -> str:
    if _required_field(ability_row, "ability_id"):
        return _raw_or_field(_ability_source_row(context=context, ability_row=ability_row), "name")
    return _raw_or_field(ability_row, "name")


def _bridge_replacement_with_required_choices_option(
    *,
    row: NormalizedSourceRow,
    datasheet_id: str,
    model_profile_id: str,
    wargear_ids_by_name: dict[str, str],
    match: re.Match[str],
    bridged_rows: dict[str, list[dict[str, str]]],
) -> None:
    replaced_wargear_id = _required_wargear_id(wargear_ids_by_name, match.group("replaced"))
    required_wargear_id = _required_wargear_id(wargear_ids_by_name, match.group("required"))
    choices = replacement_choices(match.group("choices"), error_type=WahapediaBridgeError)
    choice_wargear_ids = tuple(
        _required_wargear_id(wargear_ids_by_name, choice.name) for choice in choices
    )
    source_line = _required_field(row, "line")
    for choice_index, (choice, choice_wargear_id) in enumerate(
        zip(choices, choice_wargear_ids, strict=True),
        start=1,
    ):
        other_choice_ids = tuple(
            other_id for other_id in choice_wargear_ids if other_id != choice_wargear_id
        )
        option_id = (
            f"{datasheet_id}:{_slug(match.group('required'))}-{_slug(choice.name)}:"
            f"option-{source_line}"
        )
        common_fields = {
            "datasheet_id": datasheet_id,
            "description": _raw_or_field(row, "description"),
            "option_id": option_id,
            "model_profile_id": model_profile_id,
            "default_wargear_ids": "",
            "allowed_wargear_ids": _joined((required_wargear_id, choice_wargear_id)),
            "min_selections": "0",
            "max_selections": "2",
            "condition_kind": (
                WargearOptionConditionKind.MODEL_NOT_EQUIPPED_WITH.value if other_choice_ids else ""
            ),
            "condition_wargear_ids": _joined(other_choice_ids),
            "effect_model_count": "1",
            "effect_wargear_count": "1",
            "source_ids": _joined(_source_ids(row)),
        }
        bridged_rows["Datasheets_options"].append(
            {
                **common_fields,
                "line": f"{source_line}.{choice_index}.1",
                "effect_kind": WargearOptionEffectKind.REPLACE_WARGEAR.value,
                "effect_wargear_id": required_wargear_id,
                "effect_replaced_wargear_id": replaced_wargear_id,
            }
        )
        bridged_rows["Datasheets_options"].append(
            {
                **common_fields,
                "line": f"{source_line}.{choice_index}.2",
                "effect_kind": WargearOptionEffectKind.ADD_WARGEAR.value,
                "effect_wargear_id": choice_wargear_id,
                "effect_replaced_wargear_id": "",
            }
        )


def _bridge_replacement_with_choices_option(
    *,
    row: NormalizedSourceRow,
    datasheet_id: str,
    model_profile_id: str,
    wargear_ids_by_name: dict[str, str],
    match: re.Match[str],
    bridged_rows: dict[str, list[dict[str, str]]],
) -> None:
    replaced_wargear_id = _required_wargear_id(wargear_ids_by_name, match.group("replaced"))
    choices = replacement_choices(match.group("choices"), error_type=WahapediaBridgeError)
    source_line = _required_field(row, "line")
    for choice_index, choice in enumerate(choices, start=1):
        choice_wargear_id = _required_wargear_id(wargear_ids_by_name, choice.name)
        duplicate_limited_wargear_id = (
            ""
            if choice.duplicate_limited_name is None
            else _required_wargear_id(wargear_ids_by_name, choice.duplicate_limited_name)
        )
        bridged_rows["Datasheets_options"].append(
            {
                "datasheet_id": datasheet_id,
                "line": f"{source_line}.{choice_index}",
                "description": _raw_or_field(row, "description"),
                "option_id": (
                    f"{datasheet_id}:{_slug(match.group('replaced'))}-{_slug(choice.name)}:"
                    f"option-{source_line}"
                ),
                "model_profile_id": model_profile_id,
                "default_wargear_ids": "",
                "allowed_wargear_ids": choice_wargear_id,
                "min_selections": "0",
                "max_selections": "1",
                "condition_kind": (
                    WargearOptionConditionKind.MODEL_NOT_EQUIPPED_WITH.value
                    if duplicate_limited_wargear_id
                    else ""
                ),
                "condition_wargear_ids": duplicate_limited_wargear_id,
                "effect_kind": WargearOptionEffectKind.REPLACE_WARGEAR.value,
                "effect_wargear_id": choice_wargear_id,
                "effect_replaced_wargear_id": replaced_wargear_id,
                "effect_model_count": "1",
                "effect_wargear_count": "1",
                "source_ids": _joined(_source_ids(row)),
            }
        )


def _bridge_single_replacement_option(
    *,
    row: NormalizedSourceRow,
    datasheet_id: str,
    model_profile_id: str,
    wargear_ids_by_name: dict[str, str],
    match: re.Match[str],
    bridged_rows: dict[str, list[dict[str, str]]],
) -> None:
    _positive_int_from_text("replacement_count", match.group("replacement_count"))
    replaced_wargear_id = _required_wargear_id(wargear_ids_by_name, match.group("replaced"))
    replacement_wargear_id = _required_wargear_id(wargear_ids_by_name, match.group("replacement"))
    bridged_rows["Datasheets_options"].append(
        {
            "datasheet_id": datasheet_id,
            "line": _required_field(row, "line"),
            "description": _raw_or_field(row, "description"),
            "option_id": (
                f"{datasheet_id}:{_slug(match.group('replacement'))}:option-"
                f"{_required_field(row, 'line')}"
            ),
            "model_profile_id": model_profile_id,
            "default_wargear_ids": "",
            "allowed_wargear_ids": replacement_wargear_id,
            "min_selections": "0",
            "max_selections": "1",
            "condition_kind": "",
            "condition_wargear_ids": "",
            "effect_kind": WargearOptionEffectKind.REPLACE_WARGEAR.value,
            "effect_wargear_id": replacement_wargear_id,
            "effect_replaced_wargear_id": replaced_wargear_id,
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
        leader_id = _required_field(row, "leader_id")
        attached_id = _required_field(row, "attached_id")
        if leader_id != datasheet_id or attached_id not in context.selected_datasheet_ids:
            continue
        requirement = context.attachment_wargear_requirements_by_target.get(
            (leader_id, attached_id)
        )
        bridged_rows["Datasheets_leader"].append(
            {
                "leader_id": leader_id,
                "attached_id": attached_id,
                "required_wargear_ids": (
                    "" if requirement is None else _joined(requirement.required_wargear_ids)
                ),
                "source_ids": _joined(
                    _source_ids(row)
                    if requirement is None
                    else tuple(_deduplicated([*_source_ids(row), *requirement.source_ids]))
                ),
            }
        )


def _damaged_effects_json(
    *,
    datasheet_id: str,
    damaged_description: str,
    composition_entries: tuple[_CompositionEntry, ...],
    source_id: str,
) -> str:
    effects = _damaged_effects_from_description(
        datasheet_id=datasheet_id,
        damaged_description=damaged_description,
        composition_entries=composition_entries,
        source_id=source_id,
    )
    if not effects:
        return ""
    return json.dumps([effect.to_payload() for effect in effects], sort_keys=True)


def _damaged_effects_from_description(
    *,
    datasheet_id: str,
    damaged_description: str,
    composition_entries: tuple[_CompositionEntry, ...],
    source_id: str,
) -> tuple[DamagedEffectDefinition, ...]:
    description = _normalize_damaged_description(damaged_description)
    if not description:
        return ()
    range_match = DAMAGED_RANGE_RE.search(description)
    if range_match is None:
        raise WahapediaBridgeError("DAMAGED section is missing a wounds-remaining range.")
    model_profile_id = _damaged_model_profile_id(
        model_name=range_match.group("model_name"),
        composition_entries=composition_entries,
    )
    wounds_min = _positive_int_from_text(
        "DAMAGED wounds_min",
        range_match.group("wounds_min"),
    )
    wounds_max = _positive_int_from_text(
        "DAMAGED wounds_max",
        range_match.group("wounds_max"),
    )
    effects: list[DamagedEffectDefinition] = []
    consumed_spans = [range_match.span()]
    for match in DAMAGED_OC_RE.finditer(description):
        effects.append(
            _damaged_effect(
                datasheet_id=datasheet_id,
                index=len(effects) + 1,
                model_profile_id=model_profile_id,
                wounds_min=wounds_min,
                wounds_max=wounds_max,
                effect_kind=DamagedEffectKind.OBJECTIVE_CONTROL_MODIFIER,
                source_id=source_id,
                modifier=-_positive_int_from_text(
                    "DAMAGED Objective Control modifier",
                    match.group("value"),
                ),
            )
        )
        consumed_spans.append(match.span())
    for match in DAMAGED_HIT_RE.finditer(description):
        effects.append(
            _damaged_effect(
                datasheet_id=datasheet_id,
                index=len(effects) + 1,
                model_profile_id=model_profile_id,
                wounds_min=wounds_min,
                wounds_max=wounds_max,
                effect_kind=DamagedEffectKind.HIT_ROLL_MODIFIER,
                source_id=source_id,
                modifier=-_positive_int_from_text(
                    "DAMAGED Hit roll modifier",
                    match.group("value"),
                ),
            )
        )
        consumed_spans.append(match.span())
    for match in DAMAGED_ATTACKS_ADD_RE.finditer(description):
        weapon_scope_text = match.group("weapon_scope")
        weapon_scope = (
            DamagedWeaponScope.MELEE
            if _canonical_text(weapon_scope_text) == "melee weapons"
            else DamagedWeaponScope.NAMED
        )
        weapon_names = () if weapon_scope is DamagedWeaponScope.MELEE else (weapon_scope_text,)
        effects.append(
            _damaged_effect(
                datasheet_id=datasheet_id,
                index=len(effects) + 1,
                model_profile_id=model_profile_id,
                wounds_min=wounds_min,
                wounds_max=wounds_max,
                effect_kind=DamagedEffectKind.WEAPON_ATTACKS_MODIFIER,
                source_id=source_id,
                modifier=_positive_int_from_text(
                    "DAMAGED Attacks modifier",
                    match.group("value"),
                ),
                weapon_scope=weapon_scope,
                weapon_names=weapon_names,
            )
        )
        consumed_spans.append(match.span())
    for match in DAMAGED_ATTACKS_HALVE_RE.finditer(description):
        effects.append(
            _damaged_effect(
                datasheet_id=datasheet_id,
                index=len(effects) + 1,
                model_profile_id=model_profile_id,
                wounds_min=wounds_min,
                wounds_max=wounds_max,
                effect_kind=DamagedEffectKind.WEAPON_ATTACKS_HALVE,
                source_id=source_id,
                weapon_scope=DamagedWeaponScope.ALL,
            )
        )
        consumed_spans.append(match.span())
    for match in DAMAGED_SHOOTING_WEAPON_SELECTION_LIMIT_RE.finditer(description):
        effects.append(
            _damaged_effect(
                datasheet_id=datasheet_id,
                index=len(effects) + 1,
                model_profile_id=model_profile_id,
                wounds_min=wounds_min,
                wounds_max=wounds_max,
                effect_kind=DamagedEffectKind.SHOOTING_WEAPON_SELECTION_LIMIT,
                source_id=source_id,
                max_selections=_positive_int_from_count_text(
                    "DAMAGED shooting weapon max selections",
                    match.group("max"),
                ),
                baseline_max_selections=_positive_int_from_count_text(
                    "DAMAGED shooting weapon baseline max selections",
                    match.group("baseline"),
                ),
                selection_group=_canonical_selection_group(match.group("selection_group")),
            )
        )
        consumed_spans.append(match.span())
    for match in DAMAGED_ABILITY_SELECTION_LIMIT_RE.finditer(description):
        effects.append(
            _damaged_effect(
                datasheet_id=datasheet_id,
                index=len(effects) + 1,
                model_profile_id=model_profile_id,
                wounds_min=wounds_min,
                wounds_max=wounds_max,
                effect_kind=DamagedEffectKind.ABILITY_SELECTION_LIMIT,
                source_id=source_id,
                max_selections=_positive_int_from_count_text(
                    "DAMAGED ability max selections",
                    match.group("max"),
                ),
                baseline_max_selections=_positive_int_from_count_text(
                    "DAMAGED ability baseline max selections",
                    match.group("baseline"),
                ),
                selection_group=_canonical_selection_group(match.group("selection_group")),
            )
        )
        consumed_spans.append(match.span())
    if not effects:
        raise WahapediaBridgeError("DAMAGED section has no supported effects.")
    _raise_for_unparsed_damaged_text(description=description, consumed_spans=tuple(consumed_spans))
    return tuple(effects)


def _damaged_effect(
    *,
    datasheet_id: str,
    index: int,
    model_profile_id: str | None,
    wounds_min: int,
    wounds_max: int,
    effect_kind: DamagedEffectKind,
    source_id: str,
    modifier: int | None = None,
    weapon_scope: DamagedWeaponScope | None = None,
    weapon_names: tuple[str, ...] = (),
    max_selections: int | None = None,
    baseline_max_selections: int | None = None,
    selection_group: str | None = None,
) -> DamagedEffectDefinition:
    return DamagedEffectDefinition(
        damaged_effect_id=f"{datasheet_id}:damaged:{index:03d}",
        model_profile_id=model_profile_id,
        wounds_min=wounds_min,
        wounds_max=wounds_max,
        effect_kind=effect_kind,
        modifier=modifier,
        weapon_scope=weapon_scope,
        weapon_names=weapon_names,
        max_selections=max_selections,
        baseline_max_selections=baseline_max_selections,
        selection_group=selection_group,
        source_id=source_id,
    )


def _damaged_model_profile_id(
    *,
    model_name: str | None,
    composition_entries: tuple[_CompositionEntry, ...],
) -> str | None:
    if model_name is None:
        return None
    requested_key = _name_key(model_name)
    for entry in composition_entries:
        if _name_key(entry.model_name) == requested_key:
            return entry.model_profile_id
    raise WahapediaBridgeError("DAMAGED section references an unknown model name.")


def _normalize_damaged_description(value: str) -> str:
    if type(value) is not str:
        raise WahapediaBridgeError("DAMAGED description must be a string.")
    without_header = DAMAGED_HEADER_RE.sub("", value.strip())
    return re.sub(r"\s+", " ", without_header).strip()


def _raise_for_unparsed_damaged_text(
    *,
    description: str,
    consumed_spans: tuple[tuple[int, int], ...],
) -> None:
    unconsumed_parts: list[str] = []
    cursor = 0
    for start, end in sorted(consumed_spans):
        if start < cursor:
            cursor = max(cursor, end)
            continue
        unconsumed_parts.append(description[cursor:start])
        cursor = end
    unconsumed_parts.append(description[cursor:])
    remainder = "".join(unconsumed_parts)
    stripped = DAMAGED_IGNORABLE_REMAINDER_RE.sub("", remainder)
    if stripped:
        raise WahapediaBridgeError("DAMAGED section contains unsupported effect text.")


def _empty_bridge_rows() -> dict[str, list[dict[str, str]]]:
    return {
        "Factions": [],
        "Datasheets": [],
        "Datasheets_models": [],
        "Datasheets_wargear": [],
        "Datasheets_options": [],
        "Datasheets_mustering_options": [],
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
        columns = _bridge_columns.bridge_columns_for_table(
            table_name,
            error_type=WahapediaBridgeError,
        )
        csv_text = _csv_text(columns=columns, rows=tuple(rows))
        artifacts.append(
            WahapediaJsonArtifact.from_csv_table(
                source_package_id=bridge_package_id,
                table=WahapediaCsvTable.from_csv_text(table_name=table_name, csv_text=csv_text),
            )
        )
    return tuple(sorted(artifacts, key=lambda artifact: artifact.source_table))


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


def _normalized_or_field(row: NormalizedSourceRow, column_name: str) -> str:
    for text_field in row.text_fields:
        if text_field.column_name == column_name:
            return text_field.normalized_text
    return row.runtime_fields_payload().get(column_name, "")


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
        source_id=_source_text_id(row=row, column_name=column_name),
        raw_text=row.runtime_fields_payload().get(column_name, ""),
    )


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
    if normalized in {"wargear", "wargear profile"}:
        return CatalogAbilitySourceKind.WARGEAR
    if normalized == "primarch" or normalized.startswith(("special", "fortification")):
        return CatalogAbilitySourceKind.DATASHEET
    raise WahapediaBridgeError("Unsupported datasheet ability type.")


def _is_wargear_profile_ability_type(ability_type: str) -> bool:
    return _validate_identifier("ability_type", ability_type).lower() == "wargear profile"


def _mustering_warlord_value(*, normalized_description: str) -> str | None:
    normalized = _validate_identifier("normalized_description", normalized_description).upper()
    if "CANNOT BE YOUR WARLORD" in normalized:
        return MUSTERING_WARLORD_FORBIDDEN
    if "MUST BE YOUR WARLORD" in normalized:
        return MUSTERING_WARLORD_REQUIRED
    return None


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


def _attachment_wargear_requirements_by_target(
    requirements: tuple[AttachmentWargearRequirement, ...],
) -> dict[tuple[str, str], AttachmentWargearRequirement]:
    if type(requirements) is not tuple:
        raise WahapediaBridgeError("attachment_wargear_requirements must be a tuple.")
    by_target: dict[tuple[str, str], AttachmentWargearRequirement] = {}
    for requirement in requirements:
        if type(requirement) is not AttachmentWargearRequirement:
            raise WahapediaBridgeError(
                "attachment_wargear_requirements must contain requirement values."
            )
        key = (requirement.leader_datasheet_id, requirement.bodyguard_datasheet_id)
        if key in by_target:
            raise WahapediaBridgeError(
                "attachment_wargear_requirements must not duplicate attachment targets."
            )
        by_target[key] = requirement
    return by_target


def _validate_active_attachment_wargear_requirements(
    *,
    context: _BridgeContext,
    bridged_rows: dict[str, list[dict[str, str]]],
) -> None:
    active_requirements = tuple(
        requirement
        for requirement in context.attachment_wargear_requirements_by_target.values()
        if requirement.leader_datasheet_id in context.selected_datasheet_ids
        and requirement.bodyguard_datasheet_id in context.selected_datasheet_ids
    )
    bridged_wargear_ids = {row["wargear_id"] for row in bridged_rows["Datasheets_wargear"]}
    for requirement in active_requirements:
        matching_rows = tuple(
            row
            for row in bridged_rows["Datasheets_leader"]
            if row["leader_id"] == requirement.leader_datasheet_id
            and row["attached_id"] == requirement.bodyguard_datasheet_id
        )
        if len(matching_rows) != 1:
            raise WahapediaBridgeError(
                "Attachment wargear requirement did not resolve to one source leader link."
            )
        if not set(requirement.required_wargear_ids).issubset(bridged_wargear_ids):
            raise WahapediaBridgeError(
                "Attachment wargear requirement references unknown bridged wargear."
            )


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


def _skill_value(row: NormalizedSourceRow) -> str:
    raw_skill = _required_field(row, "BS_WS").strip()
    if raw_skill.casefold() == "n/a":
        return "-"
    return f"{raw_skill}+"


def _weapon_keywords(
    description: str,
    *,
    ignored_name_keys: frozenset[str],
) -> tuple[str, ...]:
    return tuple(
        sorted(
            _deduplicated(
                [
                    entry.keyword.value
                    for entry in _weapon_keyword_entries(
                        description,
                        ignored_name_keys=ignored_name_keys,
                    )
                    if entry.keyword is not None
                ]
            )
        )
    )


def _weapon_abilities_payload(
    description: str,
    *,
    ignored_name_keys: frozenset[str],
) -> str:
    abilities = tuple(
        entry.ability
        for entry in _weapon_keyword_entries(
            description,
            ignored_name_keys=ignored_name_keys,
        )
        if entry.ability is not None
    )
    if not abilities:
        return ""
    seen: set[str] = set()
    for ability in abilities:
        if ability.ability_id in seen:
            raise WahapediaBridgeError("Wahapedia weapon abilities must not duplicate.")
        seen.add(ability.ability_id)
    try:
        validate_weapon_ability_descriptor_multiplicity(abilities)
    except WeaponProfileError as exc:
        raise WahapediaBridgeError(
            "Wahapedia weapon abilities must not duplicate non-Anti ability kinds."
        ) from exc
    return json.dumps(
        [ability.to_payload() for ability in sorted(abilities, key=lambda item: item.ability_id)],
        sort_keys=True,
        separators=(",", ":"),
    )


def _weapon_keyword_entries(
    description: str,
    *,
    ignored_name_keys: frozenset[str],
) -> tuple[_WeaponKeywordEntry, ...]:
    if not description.strip():
        return ()
    entries: list[_WeaponKeywordEntry] = []
    for raw_item in _weapon_keyword_items(description):
        if _name_key(raw_item) in ignored_name_keys:
            continue
        entries.append(_weapon_keyword_entry(raw_item))
    return tuple(entries)


def _weapon_keyword_items(description: str) -> tuple[str, ...]:
    body = _weapon_keyword_body(description)
    items = tuple(item.strip() for item in body.split(",") if item.strip())
    if not items:
        raise WahapediaBridgeError("Wahapedia weapon keyword list must not be empty.")
    return items


def _weapon_keyword_body(description: str) -> str:
    stripped = description.strip()
    if stripped.startswith("[") and stripped.endswith("]"):
        stripped = stripped[1:-1].strip()
    return stripped


def _weapon_keyword_entry(raw_item: str) -> _WeaponKeywordEntry:
    ability_text, target_condition = _weapon_keyword_condition(raw_item)
    try:
        return _weapon_keyword_entry_from_parts(
            ability_text=ability_text,
            target_keywords=() if target_condition is None else (target_condition,),
        )
    except WeaponProfileError as exc:
        raise WahapediaBridgeError("Invalid Wahapedia weapon ability descriptor.") from exc


def _weapon_keyword_condition(raw_item: str) -> tuple[str, str | None]:
    parts = raw_item.split(":", maxsplit=1)
    ability_text = parts[0].strip()
    if not ability_text:
        raise WahapediaBridgeError("Wahapedia weapon keyword must not be empty.")
    if len(parts) == 1:
        return ability_text, None
    condition = parts[1].strip()
    if not condition:
        raise WahapediaBridgeError("Wahapedia weapon keyword condition must not be empty.")
    return ability_text, condition


def _weapon_keyword_entry_from_parts(
    *,
    ability_text: str,
    target_keywords: tuple[str, ...],
) -> _WeaponKeywordEntry:
    valued = _valued_weapon_ability_entry(ability_text, target_keywords=target_keywords)
    if valued is not None:
        return valued
    anti = _anti_weapon_ability_entry(ability_text)
    if anti is not None:
        if target_keywords:
            raise WahapediaBridgeError("Anti weapon keywords do not support target conditions.")
        return anti
    canonical_by_key = {_name_key(keyword.value): keyword for keyword in WeaponKeyword}
    keyword = canonical_by_key.get(_name_key(ability_text))
    if keyword is None:
        raise WahapediaBridgeError("Unsupported Wahapedia weapon keyword.")
    ability = _unvalued_weapon_ability(keyword=keyword, target_keywords=target_keywords)
    if target_keywords and ability is None:
        raise WahapediaBridgeError("Unsupported conditioned Wahapedia weapon keyword.")
    return _WeaponKeywordEntry(keyword=keyword, ability=ability)


def _valued_weapon_ability_entry(
    ability_text: str,
    *,
    target_keywords: tuple[str, ...],
) -> _WeaponKeywordEntry | None:
    match = re.fullmatch(
        r"(?P<name>rapid[\s-]+fire|sustained[\s-]+hits|melta|cleave)\s+"
        r"(?P<value>\d+)\+?",
        ability_text.strip(),
        re.IGNORECASE,
    )
    if match is None:
        return None
    value = _int_from_text(match.group("value"))
    key = _name_key(match.group("name"))
    if key == "rapid-fire":
        return _WeaponKeywordEntry(
            keyword=WeaponKeyword.RAPID_FIRE,
            ability=AbilityDescriptor.rapid_fire(value, target_keywords=target_keywords),
        )
    if key == "sustained-hits":
        return _WeaponKeywordEntry(
            keyword=WeaponKeyword.SUSTAINED_HITS,
            ability=AbilityDescriptor.sustained_hits(value, target_keywords=target_keywords),
        )
    if key == "melta":
        return _WeaponKeywordEntry(
            keyword=WeaponKeyword.MELTA,
            ability=AbilityDescriptor.melta(value, target_keywords=target_keywords),
        )
    if key == "cleave":
        return _WeaponKeywordEntry(
            keyword=WeaponKeyword.CLEAVE,
            ability=AbilityDescriptor.cleave(value, target_keywords=target_keywords),
        )
    raise WahapediaBridgeError("Unsupported valued Wahapedia weapon keyword.")


def _anti_weapon_ability_entry(ability_text: str) -> _WeaponKeywordEntry | None:
    match = re.fullmatch(
        r"anti[\s-]+(?P<keyword>.+?)\s+(?P<threshold>[2-6])\+?",
        ability_text.strip(),
        re.IGNORECASE,
    )
    if match is None:
        return None
    keyword = match.group("keyword").strip()
    match_mode = AntiKeywordMatchMode.HAS_KEYWORD
    for prefix in ("non-", "non_", "non "):
        if keyword.casefold().startswith(prefix):
            keyword = keyword[len(prefix) :].strip()
            match_mode = AntiKeywordMatchMode.MISSING_KEYWORD
            break
    return _WeaponKeywordEntry(
        keyword=None,
        ability=AbilityDescriptor.anti_keyword(
            keyword,
            _int_from_text(match.group("threshold")),
            match_mode=match_mode,
        ),
    )


def _unvalued_weapon_ability(
    *,
    keyword: WeaponKeyword,
    target_keywords: tuple[str, ...],
) -> AbilityDescriptor | None:
    if keyword is WeaponKeyword.LETHAL_HITS:
        return AbilityDescriptor.lethal_hits(target_keywords=target_keywords)
    if keyword is WeaponKeyword.DEVASTATING_WOUNDS:
        return AbilityDescriptor.devastating_wounds(target_keywords=target_keywords)
    if keyword is WeaponKeyword.HEAVY:
        if target_keywords:
            raise WahapediaBridgeError("Heavy does not support target conditions.")
        return AbilityDescriptor.heavy()
    if keyword is WeaponKeyword.HUNTER:
        if not target_keywords:
            raise WahapediaBridgeError("Hunter requires target keywords.")
        return AbilityDescriptor.hunter(target_keywords=target_keywords)
    if keyword in {
        WeaponKeyword.CLEAVE,
        WeaponKeyword.MELTA,
        WeaponKeyword.RAPID_FIRE,
        WeaponKeyword.SUSTAINED_HITS,
    }:
        raise WahapediaBridgeError("Valued Wahapedia weapon keyword is missing its value.")
    return None


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
    key = _name_key(wargear_name)
    wargear_id = wargear_ids_by_name.get(key)
    if wargear_id is None and key.endswith("s"):
        wargear_id = wargear_ids_by_name.get(key[:-1])
    if wargear_id is None:
        raise WahapediaBridgeError("Wargear option references an unknown wargear item.")
    return wargear_id


def _wargear_profile_ability_name_keys(
    *,
    context: _BridgeContext,
    datasheet_id: str,
) -> frozenset[str]:
    return frozenset(
        _name_key(_required_field(row, "name"))
        for row in _rows_matching(
            context.rows_by_table,
            "Datasheets_abilities",
            "datasheet_id",
            datasheet_id,
        )
        if _required_field(row, "type") == "Wargear profile"
    )


def _wargear_profile_ability_source_wargear_id(
    *,
    context: _BridgeContext,
    datasheet_id: str,
    ability_name: str,
) -> str:
    ability_key = _name_key(ability_name)
    candidate_ids: list[str] = []
    for row in _rows_matching(
        context.rows_by_table,
        "Datasheets_wargear",
        "datasheet_id",
        datasheet_id,
    ):
        wargear_name = row.runtime_fields_payload().get("name", "").strip()
        if not wargear_name:
            continue
        description = _required_field(row, "description")
        if ability_key not in _weapon_description_item_name_keys(description):
            continue
        candidate_ids.append(f"{datasheet_id}:{_slug(_base_wargear_name(wargear_name))}")
    owners = tuple(_deduplicated(candidate_ids))
    if len(owners) != 1:
        raise WahapediaBridgeError("Wargear profile ability must map to exactly one wargear item.")
    return owners[0]


def _required_wargear_name(
    *,
    row: NormalizedSourceRow,
    default_wargear_name_keys: frozenset[str] | None,
) -> str | None:
    name = row.runtime_fields_payload().get("name", "").strip()
    if name:
        return name
    if default_wargear_name_keys == frozenset():
        return None
    raise WahapediaBridgeError("Required source column is empty: name.")


def _single_model_profile_id(composition_entries: tuple[_CompositionEntry, ...]) -> str:
    if len(composition_entries) != 1:
        raise WahapediaBridgeError("This-model wargear replacement requires one model profile.")
    return composition_entries[0].model_profile_id


def _weapon_description_item_name_keys(description: str) -> frozenset[str]:
    if not description.strip():
        return frozenset()
    return frozenset(_name_key(item) for item in _weapon_keyword_items(description))


def _base_wargear_name(name: str) -> str:
    match = WEAPON_PROFILE_SUFFIX_RE.fullmatch(name)
    return name if match is None else match.group("base")


def _weapon_profile_name(name: str) -> str | None:
    match = WEAPON_PROFILE_SUFFIX_RE.fullmatch(name)
    return None if match is None else match.group("profile")


def _joined(values: tuple[str, ...]) -> str:
    return ",".join(values)


def _name_key(value: str) -> str:
    return _slug(value)


def _slug(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    lowered = normalized.casefold().replace("'", "").replace("&", " and ")
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


def _canonical_text(value: str) -> str:
    return " ".join(value.casefold().strip().split())


def _canonical_selection_group(value: str) -> str:
    return " ".join(value.strip().split())


def _int_from_text(value: str) -> int:
    try:
        return int(value)
    except ValueError as exc:
        raise WahapediaBridgeError("Source value must be an integer.") from exc


def _positive_int_from_text(field_name: str, value: str) -> int:
    integer = _int_from_text(value)
    if integer < 1:
        raise WahapediaBridgeError(f"{field_name} must be at least 1.")
    return integer


def _positive_int_from_count_text(field_name: str, value: str) -> int:
    count = COUNT_WORDS.get(_canonical_text(value))
    if count is not None:
        return count
    return _positive_int_from_text(field_name, value)


_validate_identifier = IdentifierValidator(WahapediaBridgeError)


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


def _deduplicated(values: list[str]) -> list[str]:
    seen: set[str] = set()
    deduplicated: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        deduplicated.append(value)
    return deduplicated
