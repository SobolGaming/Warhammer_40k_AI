from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import cast

from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.core.attributes import Characteristic, CharacteristicValue
from warhammer40k_core.core.content_scope import (
    CatalogContentScope,
    catalog_content_scope_from_token,
)
from warhammer40k_core.core.datasheet import (
    AttachmentEligibility,
    AttachmentRole,
    BaseSizeDefinition,
    CatalogAbilitySourceKind,
    CatalogAbilitySupport,
    CatalogJsonObject,
    DamagedEffectDefinition,
    DamagedEffectDefinitionPayload,
    DatasheetAbilityDescriptor,
    DatasheetDefinition,
    DatasheetKeywordSet,
    DatasheetMusteringOption,
    DatasheetMusteringOptionEffect,
    DatasheetMusteringOptionEffectKind,
    DatasheetWargearOption,
    DatasheetWargearOptionCondition,
    DatasheetWargearOptionEffect,
    ModelProfileDefinition,
    UnitCompositionDefinition,
    WargearOptionConditionKind,
    WargearOptionEffectKind,
    catalog_ability_source_kind_from_token,
)
from warhammer40k_core.core.detachment import (
    DetachmentDefinition,
    EnhancementDefinition,
    EnhancementSubtype,
    StratagemDefinition,
)
from warhammer40k_core.core.dice import DiceExpression, DiceRollSpecError
from warhammer40k_core.core.faction import ArmyRuleDefinition, FactionDefinition
from warhammer40k_core.core.model_geometry_catalog import (
    GeometryEvidenceKind,
    GeometryMeasurementKind,
    GeometryReviewStatus,
    GeometryRulesFootprintPolicy,
    GeometrySourceUnits,
    ModelFootprintDefinition,
    ModelFootprintKind,
    ModelFootprintPartDefinition,
    ModelGeometryCatalogRecord,
    ModelGeometryDiagnosticReason,
    ModelGeometryImportDiagnostic,
    ModelGeometrySourceEvidence,
    ModelHeightDefinition,
)
from warhammer40k_core.core.ruleset import RulesetId
from warhammer40k_core.core.wargear import Wargear
from warhammer40k_core.core.weapon_profiles import (
    AbilityDescriptor,
    AbilityDescriptorPayload,
    AttackProfile,
    DamageProfile,
    RangeProfile,
    WeaponKeyword,
    WeaponProfile,
    WeaponProfileError,
)
from warhammer40k_core.rules.catalog_package import CanonicalCatalogPackage
from warhammer40k_core.rules.data_package import CatalogVersion, DataPackageId
from warhammer40k_core.rules.rule_ir import RuleIR, RuleIRError, RuleIRPayload
from warhammer40k_core.rules.source_catalog import SourceArtifactHash
from warhammer40k_core.rules.source_overlay import OverlaySourceArtifact
from warhammer40k_core.rules.source_patch import PatchedSourceArtifact
from warhammer40k_core.rules.wahapedia_schema import NormalizedSourceRow, WahapediaJsonArtifact
from warhammer40k_core.rules.weapon_profile_names import WEAPON_PROFILE_SUFFIX_RE


class CatalogGenerationError(ValueError):
    """Raised when Phase 17B catalog generation violates strict source invariants."""


SourceArtifact = WahapediaJsonArtifact | PatchedSourceArtifact | OverlaySourceArtifact

_BASE_SIZE_BLOCKERS = frozenset(
    {
        "",
        "use model",
        "no official base size",
        "hull",
        "bare hull",
        "unique",
    }
)
_ENHANCEMENT_UPGRADE_NAME_SUFFIX = re.compile(r"\s+upgrade\s*\Z", re.IGNORECASE)
_CIRCULAR_BASE_RE = re.compile(r"^(?P<diameter>\d+(?:\.\d+)?)\s*mm$", re.IGNORECASE)
_OVAL_BASE_RE = re.compile(
    r"^(?P<length>\d+(?:\.\d+)?)\s*x\s*(?P<width>\d+(?:\.\d+)?)\s*mm(?:\s*oval)?$",
    re.IGNORECASE,
)
_DICE_CHARACTERISTIC_RE = re.compile(
    r"^(?P<quantity>\d*)D(?P<sides>\d+)(?P<modifier>[+-]\d+)?$",
    re.IGNORECASE,
)
_INTEGER_CHARACTERISTIC_RE = re.compile(r"^[+-]?\d+$")


@dataclass(frozen=True, slots=True)
class CanonicalCatalogBuildReport:
    package: CanonicalCatalogPackage | None
    diagnostics: tuple[ModelGeometryImportDiagnostic, ...]

    def __post_init__(self) -> None:
        if self.package is not None and type(self.package) is not CanonicalCatalogPackage:
            raise CatalogGenerationError("CanonicalCatalogBuildReport package is invalid.")
        object.__setattr__(
            self,
            "diagnostics",
            _validate_diagnostics(self.diagnostics),
        )

    def blocking_diagnostics(self) -> tuple[ModelGeometryImportDiagnostic, ...]:
        return tuple(diagnostic for diagnostic in self.diagnostics if diagnostic.blocking)

    def require_success(self) -> CanonicalCatalogPackage:
        blocking = self.blocking_diagnostics()
        if blocking or self.package is None:
            reasons = ", ".join(sorted({diagnostic.reason.value for diagnostic in blocking}))
            raise CatalogGenerationError(
                f"Canonical catalog generation failed with diagnostics: {reasons}."
            )
        return self.package


def build_canonical_catalog_package(
    *,
    package_id: DataPackageId,
    catalog_version: CatalogVersion,
    source_artifacts: tuple[SourceArtifact, ...],
    geometry_overrides: tuple[ModelGeometryCatalogRecord, ...] = (),
) -> CanonicalCatalogPackage:
    return build_canonical_catalog_report(
        package_id=package_id,
        catalog_version=catalog_version,
        source_artifacts=source_artifacts,
        geometry_overrides=geometry_overrides,
    ).require_success()


def build_canonical_catalog_report(
    *,
    package_id: DataPackageId,
    catalog_version: CatalogVersion,
    source_artifacts: tuple[SourceArtifact, ...],
    geometry_overrides: tuple[ModelGeometryCatalogRecord, ...] = (),
) -> CanonicalCatalogBuildReport:
    if type(package_id) is not DataPackageId:
        raise CatalogGenerationError("package_id must be DataPackageId.")
    if type(catalog_version) is not CatalogVersion:
        raise CatalogGenerationError("catalog_version must be CatalogVersion.")
    rows_by_table = _rows_by_table(source_artifacts)
    model_rows = _required_rows(rows_by_table=rows_by_table, table_name="Datasheets_models")
    overrides_by_profile_id = _geometry_overrides_by_profile_id(geometry_overrides)
    geometry_records: list[ModelGeometryCatalogRecord] = []
    diagnostics: list[ModelGeometryImportDiagnostic] = []

    for row in model_rows:
        model_profile_id = _required_field(row=row, column_name="model_profile_id")
        override = overrides_by_profile_id.get(model_profile_id)
        if override is not None:
            geometry_records.append(override)
            continue
        generated_record = _geometry_record_from_model_row(
            row=row, model_profile_id=model_profile_id
        )
        if isinstance(generated_record, ModelGeometryImportDiagnostic):
            diagnostics.append(generated_record)
            continue
        geometry_records.append(generated_record)

    if diagnostics:
        return CanonicalCatalogBuildReport(package=None, diagnostics=tuple(diagnostics))

    army_catalog = _army_catalog_from_rows(
        package_id=package_id,
        catalog_version=catalog_version,
        rows_by_table=rows_by_table,
        geometry_records=tuple(geometry_records),
    )
    package = CanonicalCatalogPackage(
        package_id=package_id,
        catalog_version=catalog_version,
        source_edition="warhammer-40000-11th",
        source_artifacts=_source_artifact_hashes(source_artifacts),
        army_catalog=army_catalog,
        model_geometries=tuple(geometry_records),
    )
    return CanonicalCatalogBuildReport(package=package, diagnostics=())


def _army_catalog_from_rows(
    *,
    package_id: DataPackageId,
    catalog_version: CatalogVersion,
    rows_by_table: dict[str, tuple[NormalizedSourceRow, ...]],
    geometry_records: tuple[ModelGeometryCatalogRecord, ...],
) -> ArmyCatalog:
    datasheet_rows = _required_rows(rows_by_table=rows_by_table, table_name="Datasheets")
    faction_rows = _required_rows(rows_by_table=rows_by_table, table_name="Factions")
    wargear_rows = _required_rows(rows_by_table=rows_by_table, table_name="Datasheets_wargear")
    model_rows = _required_rows(rows_by_table=rows_by_table, table_name="Datasheets_models")
    option_rows = rows_by_table.get("Datasheets_options", ())
    mustering_option_rows = rows_by_table.get("Datasheets_mustering_options", ())
    ability_rows = rows_by_table.get("Datasheets_abilities", ())
    leader_rows = rows_by_table.get("Datasheets_leader", ())
    wargear = _wargear_from_rows(wargear_rows)
    army_rules = tuple(_army_rule_from_faction_row(row) for row in faction_rows)
    factions = tuple(_faction_from_row(row) for row in faction_rows)
    geometry_by_profile_id = {record.model_profile_id: record for record in geometry_records}
    datasheets = tuple(
        _datasheet_from_row(
            row=row,
            model_rows=_rows_matching(model_rows, "datasheet_id", row.source_row_id),
            wargear_rows=_rows_matching(wargear_rows, "datasheet_id", row.source_row_id),
            option_rows=_rows_matching(option_rows, "datasheet_id", row.source_row_id),
            mustering_option_rows=_rows_matching(
                mustering_option_rows,
                "datasheet_id",
                row.source_row_id,
            ),
            ability_rows=_rows_matching(ability_rows, "datasheet_id", row.source_row_id),
            leader_rows=leader_rows,
            geometry_by_profile_id=geometry_by_profile_id,
        )
        for row in datasheet_rows
    )
    enhancements = tuple(
        _enhancement_from_row(row) for row in rows_by_table.get("Enhancements", ())
    )
    stratagems = tuple(_stratagem_from_row(row) for row in rows_by_table.get("Stratagems", ()))
    detachments = tuple(_detachment_from_row(row) for row in rows_by_table.get("Detachments", ()))
    return ArmyCatalog(
        catalog_id=package_id.package_name,
        ruleset_id=RulesetId.warhammer_40000_eleventh(version=catalog_version.version_id),
        source_package_id=package_id.stable_identity(),
        datasheets=datasheets,
        wargear=wargear,
        factions=factions,
        army_rules=army_rules,
        detachments=detachments,
        enhancements=enhancements,
        stratagems=stratagems,
        source_ids=_source_ids_from_rows((*datasheet_rows, *faction_rows)),
    )


def _datasheet_from_row(
    *,
    row: NormalizedSourceRow,
    model_rows: tuple[NormalizedSourceRow, ...],
    wargear_rows: tuple[NormalizedSourceRow, ...],
    option_rows: tuple[NormalizedSourceRow, ...],
    mustering_option_rows: tuple[NormalizedSourceRow, ...],
    ability_rows: tuple[NormalizedSourceRow, ...],
    leader_rows: tuple[NormalizedSourceRow, ...],
    geometry_by_profile_id: dict[str, ModelGeometryCatalogRecord],
) -> DatasheetDefinition:
    if not model_rows:
        raise CatalogGenerationError("Datasheet source row has no model profiles.")
    model_profiles = tuple(
        _model_profile_from_row(row=model_row, geometry_by_profile_id=geometry_by_profile_id)
        for model_row in model_rows
    )
    composition = tuple(_composition_from_model_row(model_row) for model_row in model_rows)
    return DatasheetDefinition(
        datasheet_id=row.source_row_id,
        name=_required_field(row=row, column_name="name"),
        content_scope=_content_scope_from_row(row),
        keywords=DatasheetKeywordSet(
            keywords=_required_split_field(row=row, column_name="keywords"),
            faction_keywords=_required_split_field(row=row, column_name="faction_keywords"),
        ),
        model_profiles=model_profiles,
        composition=composition,
        wargear_options=(
            *tuple(
                option
                for wargear_row in wargear_rows
                for option in _default_wargear_options_from_row(wargear_row)
            ),
            *_structured_wargear_options_from_rows(option_rows),
        ),
        mustering_options=_mustering_options_from_rows(mustering_option_rows),
        abilities=tuple(_ability_descriptor_from_row(row) for row in ability_rows),
        damaged_effects=_damaged_effects_from_row(row),
        attachment_eligibilities=_attachment_eligibilities_from_rows(
            row=row,
            ability_rows=ability_rows,
            leader_rows=leader_rows,
        ),
        source_ids=_source_ids_from_row(row),
    )


def _model_profile_from_row(
    *,
    row: NormalizedSourceRow,
    geometry_by_profile_id: dict[str, ModelGeometryCatalogRecord],
) -> ModelProfileDefinition:
    model_profile_id = _required_field(row=row, column_name="model_profile_id")
    geometry_record = geometry_by_profile_id[model_profile_id]
    return ModelProfileDefinition(
        model_profile_id=model_profile_id,
        name=_required_field(row=row, column_name="name"),
        characteristics=(
            _characteristic_from_row(
                row=row, column_name="bs", characteristic=Characteristic.BALLISTIC_SKILL
            ),
            _characteristic_from_row(
                row=row, column_name="ld", characteristic=Characteristic.LEADERSHIP
            ),
            _characteristic_from_row(
                row=row, column_name="m", characteristic=Characteristic.MOVEMENT
            ),
            _characteristic_from_row(
                row=row,
                column_name="oc",
                characteristic=Characteristic.OBJECTIVE_CONTROL,
            ),
            _characteristic_from_row(row=row, column_name="sv", characteristic=Characteristic.SAVE),
            _optional_characteristic_from_row(
                row=row,
                column_name="inv_sv",
                characteristic=Characteristic.INVULNERABLE_SAVE,
            ),
            _characteristic_from_row(
                row=row, column_name="t", characteristic=Characteristic.TOUGHNESS
            ),
            _characteristic_from_row(
                row=row, column_name="ws", characteristic=Characteristic.WEAPON_SKILL
            ),
            _characteristic_from_row(
                row=row, column_name="w", characteristic=Characteristic.WOUNDS
            ),
        ),
        base_size=_base_size_from_geometry_record(geometry_record),
        source_ids=_deduplicated_ids(
            (*_source_ids_from_row(row), geometry_record.stable_identity())
        ),
    )


def _composition_from_model_row(row: NormalizedSourceRow) -> UnitCompositionDefinition:
    return UnitCompositionDefinition(
        model_profile_id=_required_field(row=row, column_name="model_profile_id"),
        min_models=_required_positive_int(row=row, column_name="min_models"),
        max_models=_required_positive_int(row=row, column_name="max_models"),
    )


def _default_wargear_options_from_row(
    row: NormalizedSourceRow,
) -> tuple[DatasheetWargearOption, ...]:
    default_loadout = _optional_field(row=row, column_name="default_loadout")
    if default_loadout == "false":
        return ()
    if default_loadout not in {None, "true"}:
        raise CatalogGenerationError("Wargear default_loadout must be true or false.")
    wargear_id = _required_field(row=row, column_name="wargear_id")
    profile_ids = _optional_split_field(row, "model_profile_ids")
    if not profile_ids:
        profile_ids = (_required_field(row=row, column_name="model_profile_id"),)
    options: list[DatasheetWargearOption] = []
    for model_profile_id in profile_ids:
        option_id = (
            f"{row.source_row_id}:default"
            if len(profile_ids) == 1
            else f"{row.source_row_id}:{model_profile_id}:default"
        )
        options.append(
            DatasheetWargearOption(
                option_id=option_id,
                model_profile_id=model_profile_id,
                default_wargear_ids=(wargear_id,),
                allowed_wargear_ids=(wargear_id,),
                min_selections=1,
                max_selections=1,
                source_ids=_source_ids_from_row(row),
            )
        )
    return tuple(options)


def _structured_wargear_options_from_rows(
    rows: tuple[NormalizedSourceRow, ...],
) -> tuple[DatasheetWargearOption, ...]:
    rows_by_option_id: dict[str, list[NormalizedSourceRow]] = {}
    for row in rows:
        option_id = _required_field(row=row, column_name="option_id")
        rows_by_option_id.setdefault(option_id, []).append(row)
    return tuple(
        _structured_wargear_option_from_rows(tuple(option_rows))
        for option_rows in rows_by_option_id.values()
    )


def _structured_wargear_option_from_rows(
    rows: tuple[NormalizedSourceRow, ...],
) -> DatasheetWargearOption:
    if not rows:
        raise CatalogGenerationError("Structured wargear option row group must not be empty.")
    row = rows[0]
    _validate_grouped_option_rows(rows)
    allowed_wargear_ids = _required_split_field(row=row, column_name="allowed_wargear_ids")
    conditions = _wargear_option_conditions_from_row(row)
    effects = tuple(
        effect for grouped_row in rows for effect in _wargear_option_effects_from_row(grouped_row)
    )
    return DatasheetWargearOption(
        option_id=_required_field(row=row, column_name="option_id"),
        model_profile_id=_required_field(row=row, column_name="model_profile_id"),
        default_wargear_ids=_optional_split_field(row, "default_wargear_ids"),
        allowed_wargear_ids=allowed_wargear_ids,
        min_selections=_required_non_negative_int(row=row, column_name="min_selections"),
        max_selections=_required_positive_int(row=row, column_name="max_selections"),
        source_ids=_deduplicated_ids(
            tuple(
                source_id for grouped_row in rows for source_id in _source_ids_from_row(grouped_row)
            )
        ),
        conditions=conditions,
        effects=effects,
    )


def _mustering_options_from_rows(
    rows: tuple[NormalizedSourceRow, ...],
) -> tuple[DatasheetMusteringOption, ...]:
    rows_by_option_id: dict[str, list[NormalizedSourceRow]] = {}
    for row in rows:
        option_id = _required_field(row=row, column_name="option_id")
        rows_by_option_id.setdefault(option_id, []).append(row)
    return tuple(
        _mustering_option_from_rows(tuple(option_rows))
        for option_rows in rows_by_option_id.values()
    )


def _mustering_option_from_rows(
    rows: tuple[NormalizedSourceRow, ...],
) -> DatasheetMusteringOption:
    if not rows:
        raise CatalogGenerationError("Mustering option row group must not be empty.")
    row = rows[0]
    _validate_grouped_mustering_option_rows(rows)
    return DatasheetMusteringOption(
        option_id=_required_field(row=row, column_name="option_id"),
        selection_group_id=_required_field(row=row, column_name="selection_group_id"),
        label=_required_field(row=row, column_name="label"),
        model_profile_id=_optional_field(row=row, column_name="model_profile_id"),
        required=_required_bool(row=row, column_name="required"),
        source_ids=_deduplicated_ids(
            tuple(
                source_id for grouped_row in rows for source_id in _source_ids_from_row(grouped_row)
            )
        ),
        effects=tuple(_mustering_option_effect_from_row(grouped_row) for grouped_row in rows),
    )


def _validate_grouped_mustering_option_rows(rows: tuple[NormalizedSourceRow, ...]) -> None:
    first = rows[0]
    grouped_columns = (
        "option_id",
        "selection_group_id",
        "label",
        "model_profile_id",
        "required",
    )
    expected = {
        column_name: _optional_field(row=first, column_name=column_name)
        for column_name in grouped_columns
    }
    for row in rows[1:]:
        for column_name, expected_value in expected.items():
            if _optional_field(row=row, column_name=column_name) != expected_value:
                raise CatalogGenerationError(
                    "Grouped mustering option rows must share option metadata."
                )


def _mustering_option_effect_from_row(
    row: NormalizedSourceRow,
) -> DatasheetMusteringOptionEffect:
    try:
        kind = DatasheetMusteringOptionEffectKind(
            _required_field(row=row, column_name="effect_kind")
        )
    except ValueError as exc:
        raise CatalogGenerationError("Unsupported mustering option effect kind.") from exc
    return DatasheetMusteringOptionEffect(
        kind=kind,
        keyword=_optional_field(row=row, column_name="effect_keyword"),
        wargear_id=_optional_field(row=row, column_name="effect_wargear_id"),
        model_count=_optional_positive_int(row=row, column_name="effect_model_count"),
        wargear_count=_optional_positive_int(row=row, column_name="effect_wargear_count"),
    )


def _wargear_from_rows(rows: tuple[NormalizedSourceRow, ...]) -> tuple[Wargear, ...]:
    rows_by_wargear_id: dict[str, list[NormalizedSourceRow]] = {}
    for row in rows:
        wargear_id = _required_field(row=row, column_name="wargear_id")
        rows_by_wargear_id.setdefault(wargear_id, []).append(row)
    return tuple(
        _wargear_from_row_group(tuple(wargear_rows)) for wargear_rows in rows_by_wargear_id.values()
    )


def _wargear_from_row_group(rows: tuple[NormalizedSourceRow, ...]) -> Wargear:
    if not rows:
        raise CatalogGenerationError("Wargear row group must not be empty.")
    row = rows[0]
    _validate_grouped_wargear_rows(rows)
    return Wargear(
        wargear_id=_required_field(row=row, column_name="wargear_id"),
        name=_base_wargear_name(_required_field(row=row, column_name="name")),
        weapon_profiles=tuple(
            _weapon_profile_from_row(grouped_row)
            for grouped_row in rows
            if _optional_field(row=grouped_row, column_name="weapon_profile_id") is not None
        ),
        source_ids=_deduplicated_ids(
            tuple(
                source_id for grouped_row in rows for source_id in _source_ids_from_row(grouped_row)
            )
        ),
    )


def _validate_grouped_wargear_rows(rows: tuple[NormalizedSourceRow, ...]) -> None:
    first = rows[0]
    expected_wargear_id = _required_field(row=first, column_name="wargear_id")
    expected_name = _base_wargear_name(_required_field(row=first, column_name="name"))
    for row in rows[1:]:
        if _required_field(row=row, column_name="wargear_id") != expected_wargear_id:
            raise CatalogGenerationError("Grouped wargear rows must share wargear_id.")
        if _base_wargear_name(_required_field(row=row, column_name="name")) != expected_name:
            raise CatalogGenerationError("Grouped wargear rows must share base wargear name.")


def _validate_grouped_option_rows(rows: tuple[NormalizedSourceRow, ...]) -> None:
    first = rows[0]
    grouped_columns = (
        "option_id",
        "model_profile_id",
        "default_wargear_ids",
        "allowed_wargear_ids",
        "min_selections",
        "max_selections",
        "condition_kind",
        "condition_wargear_ids",
    )
    expected = {
        column_name: _optional_field(row=first, column_name=column_name)
        for column_name in grouped_columns
    }
    for row in rows[1:]:
        for column_name, expected_value in expected.items():
            if _optional_field(row=row, column_name=column_name) != expected_value:
                raise CatalogGenerationError(
                    "Grouped wargear option rows must share option metadata."
                )


def _base_wargear_name(name: str) -> str:
    match = WEAPON_PROFILE_SUFFIX_RE.fullmatch(name)
    return name if match is None else match.group("base")


def _weapon_profile_from_row(row: NormalizedSourceRow) -> WeaponProfile:
    skill_characteristic = _characteristic_token_from_field(
        _required_field(row=row, column_name="skill_characteristic")
    )
    return WeaponProfile(
        profile_id=_required_field(row=row, column_name="weapon_profile_id"),
        name=_required_field(row=row, column_name="name"),
        range_profile=_range_profile_from_token(_required_field(row=row, column_name="range")),
        attack_profile=_attack_profile_from_raw_text(_required_field(row=row, column_name="a")),
        skill=_characteristic_value_from_raw_text(
            characteristic=skill_characteristic,
            raw_text=_required_field(row=row, column_name="skill"),
        ),
        strength=_characteristic_from_row(
            row=row,
            column_name="s",
            characteristic=Characteristic.STRENGTH,
        ),
        armor_penetration=_characteristic_from_row(
            row=row,
            column_name="ap",
            characteristic=Characteristic.ARMOR_PENETRATION,
        ),
        damage_profile=_damage_profile_from_raw_text(_required_field(row=row, column_name="d")),
        keywords=_weapon_keywords_from_field(
            _optional_field(row=row, column_name="weapon_keywords") or ""
        ),
        abilities=_weapon_abilities_from_field(
            _optional_field(row=row, column_name="weapon_abilities") or ""
        ),
        source_ids=_source_ids_from_row(row),
    )


def _wargear_option_conditions_from_row(
    row: NormalizedSourceRow,
) -> tuple[DatasheetWargearOptionCondition, ...]:
    condition_kind = _optional_field(row=row, column_name="condition_kind")
    if condition_kind is None:
        return ()
    try:
        parsed_kind = WargearOptionConditionKind(condition_kind)
    except ValueError as exc:
        raise CatalogGenerationError("Unsupported wargear option condition kind.") from exc
    return (
        DatasheetWargearOptionCondition(
            kind=parsed_kind,
            wargear_ids=_required_split_field(row=row, column_name="condition_wargear_ids"),
        ),
    )


def _wargear_option_effects_from_row(
    row: NormalizedSourceRow,
) -> tuple[DatasheetWargearOptionEffect, ...]:
    effect_kind = _optional_field(row=row, column_name="effect_kind")
    if effect_kind is None:
        return ()
    try:
        parsed_kind = WargearOptionEffectKind(effect_kind)
    except ValueError as exc:
        raise CatalogGenerationError("Unsupported wargear option effect kind.") from exc
    return (
        DatasheetWargearOptionEffect(
            kind=parsed_kind,
            wargear_id=_required_field(row=row, column_name="effect_wargear_id"),
            model_count=_required_positive_int(row=row, column_name="effect_model_count"),
            wargear_count=_required_positive_int(row=row, column_name="effect_wargear_count"),
            replaced_wargear_id=_optional_field(row=row, column_name="effect_replaced_wargear_id"),
        ),
    )


def _ability_descriptor_from_row(row: NormalizedSourceRow) -> DatasheetAbilityDescriptor:
    support = _optional_field(row=row, column_name="support")
    try:
        ability_support = (
            CatalogAbilitySupport.DESCRIPTOR_ONLY
            if support is None
            else CatalogAbilitySupport(support)
        )
    except ValueError as exc:
        raise CatalogGenerationError("Unsupported datasheet ability support.") from exc
    return DatasheetAbilityDescriptor(
        ability_id=_required_field(row=row, column_name="ability_id"),
        name=_required_field(row=row, column_name="name"),
        source_id=_source_ids_from_row(row)[0],
        support=ability_support,
        source_kind=_ability_source_kind_from_row(row),
        effect_description=_required_field(row=row, column_name="effect_description"),
        timing_tags=_optional_split_field(row, "timing_tags"),
        parameter_tokens=_optional_split_field(row, "parameter_tokens"),
        source_wargear_id=_optional_field(row=row, column_name="source_wargear_id"),
        rule_ir_payload=_rule_ir_payload_from_row(row, ability_support=ability_support),
        rule_ir_diagnostics=_rule_ir_diagnostics_from_row(row),
    )


def _ability_source_kind_from_row(row: NormalizedSourceRow) -> CatalogAbilitySourceKind:
    source_kind = _optional_field(row=row, column_name="source_kind")
    if source_kind is not None:
        try:
            return catalog_ability_source_kind_from_token(source_kind)
        except ValueError as exc:
            raise CatalogGenerationError("Unsupported datasheet ability source kind.") from exc
    ability_type = _required_field(row=row, column_name="type").strip().lower()
    if ability_type == "core":
        return CatalogAbilitySourceKind.CORE
    if ability_type == "faction":
        return CatalogAbilitySourceKind.FACTION
    if ability_type in {"datasheet", "primarch"}:
        return CatalogAbilitySourceKind.DATASHEET
    if ability_type == "wargear":
        return CatalogAbilitySourceKind.WARGEAR
    raise CatalogGenerationError("Unsupported datasheet ability type.")


def _rule_ir_payload_from_row(
    row: NormalizedSourceRow,
    *,
    ability_support: CatalogAbilitySupport,
) -> CatalogJsonObject | None:
    value = _optional_field(row=row, column_name="rule_ir_payload")
    if value is None:
        return None
    try:
        payload = json.loads(value)
    except json.JSONDecodeError as exc:
        raise CatalogGenerationError(
            "Datasheet ability rule_ir_payload is malformed JSON."
        ) from exc
    if type(payload) is not dict:
        raise CatalogGenerationError("Datasheet ability rule_ir_payload must be a JSON object.")
    catalog_payload = cast(CatalogJsonObject, payload)
    if ability_support is CatalogAbilitySupport.GENERIC_RULE_IR:
        try:
            RuleIR.from_payload(cast(RuleIRPayload, catalog_payload))
        except (KeyError, TypeError, RuleIRError) as exc:
            raise CatalogGenerationError("Datasheet ability rule_ir_payload is invalid.") from exc
    return catalog_payload


def _rule_ir_diagnostics_from_row(row: NormalizedSourceRow) -> tuple[CatalogJsonObject, ...]:
    value = _optional_field(row=row, column_name="rule_ir_diagnostics")
    if value is None:
        return ()
    try:
        payload = json.loads(value)
    except json.JSONDecodeError as exc:
        raise CatalogGenerationError(
            "Datasheet ability rule_ir_diagnostics is malformed JSON."
        ) from exc
    if type(payload) is not list:
        raise CatalogGenerationError("Datasheet ability rule_ir_diagnostics must be a JSON list.")
    diagnostics: list[CatalogJsonObject] = []
    for diagnostic in cast(list[object], payload):
        if type(diagnostic) is not dict:
            raise CatalogGenerationError(
                "Datasheet ability rule_ir_diagnostics entries must be JSON objects."
            )
        diagnostics.append(cast(CatalogJsonObject, diagnostic))
    return tuple(diagnostics)


def _damaged_effects_from_row(row: NormalizedSourceRow) -> tuple[DamagedEffectDefinition, ...]:
    value = _optional_field(row=row, column_name="damaged_effects")
    if value is None:
        return ()
    try:
        payload = json.loads(value)
    except json.JSONDecodeError as exc:
        raise CatalogGenerationError("Datasheet damaged_effects is malformed JSON.") from exc
    if type(payload) is not list:
        raise CatalogGenerationError("Datasheet damaged_effects must be a JSON list.")
    effects: list[DamagedEffectDefinition] = []
    for raw_effect in cast(list[object], payload):
        if type(raw_effect) is not dict:
            raise CatalogGenerationError("Datasheet damaged_effects entries must be JSON objects.")
        effects.append(
            DamagedEffectDefinition.from_payload(cast(DamagedEffectDefinitionPayload, raw_effect))
        )
    return tuple(effects)


def _attachment_eligibilities_from_rows(
    *,
    row: NormalizedSourceRow,
    ability_rows: tuple[NormalizedSourceRow, ...],
    leader_rows: tuple[NormalizedSourceRow, ...],
) -> tuple[AttachmentEligibility, ...]:
    bodyguard_ids = tuple(
        _required_field(row=leader_row, column_name="attached_id")
        for leader_row in leader_rows
        if _required_field(row=leader_row, column_name="leader_id") == row.source_row_id
    )
    if not bodyguard_ids:
        return ()
    role = _attachment_role_from_ability_rows(ability_rows)
    matching_rows = tuple(
        leader_row
        for leader_row in leader_rows
        if _required_field(row=leader_row, column_name="leader_id") == row.source_row_id
    )
    return (
        AttachmentEligibility(
            role=role,
            allowed_bodyguard_datasheet_ids=_deduplicated_ids(bodyguard_ids),
            source_id=_source_ids_from_rows(matching_rows)[0],
        ),
    )


def _attachment_role_from_ability_rows(
    ability_rows: tuple[NormalizedSourceRow, ...],
) -> AttachmentRole:
    has_leader = any(_ability_row_matches_family(row, "LEADER") for row in ability_rows)
    has_support = any(_ability_row_matches_family(row, "SUPPORT") for row in ability_rows)
    if has_leader and has_support:
        raise CatalogGenerationError("Datasheet cannot declare both Leader and Support roles.")
    if has_support:
        return AttachmentRole.SUPPORT
    return AttachmentRole.LEADER


def _ability_row_matches_family(row: NormalizedSourceRow, family: str) -> bool:
    fields = row.runtime_fields_payload()
    ability_id = fields.get("ability_id", "")
    name = fields.get("name", "")
    family_token = _canonical_ability_token(family)
    return _canonical_ability_token(ability_id).removeprefix("CORE_") == family_token or (
        _canonical_ability_name_words(name) == ("CORE", family_token)
        or _canonical_ability_name_words(name) == (family_token,)
    )


def _canonical_ability_token(value: str) -> str:
    return value.strip().upper().replace("-", "_").replace(" ", "_")


def _canonical_ability_name_words(value: str) -> tuple[str, ...]:
    token = _canonical_ability_token(value)
    return tuple(part for part in token.split("_") if part)


def _faction_from_row(row: NormalizedSourceRow) -> FactionDefinition:
    return FactionDefinition(
        faction_id=row.source_row_id,
        name=_required_field(row=row, column_name="name"),
        content_scope=_content_scope_from_row(row),
        faction_keywords=_required_split_field(row=row, column_name="faction_keywords"),
        army_rule_ids=(_required_field(row=row, column_name="army_rule_id"),),
        source_ids=_source_ids_from_row(row),
    )


def _army_rule_from_faction_row(row: NormalizedSourceRow) -> ArmyRuleDefinition:
    return ArmyRuleDefinition(
        rule_id=_required_field(row=row, column_name="army_rule_id"),
        name=_required_field(row=row, column_name="army_rule_name"),
        source_id=_source_ids_from_row(row)[0],
        content_scope=_content_scope_from_row(row),
    )


def _detachment_from_row(row: NormalizedSourceRow) -> DetachmentDefinition:
    return DetachmentDefinition(
        detachment_id=row.source_row_id,
        name=_required_field(row=row, column_name="name"),
        faction_id=_required_field(row=row, column_name="faction_id"),
        content_scope=_content_scope_from_row(row),
        detachment_point_cost=_required_non_negative_int(
            row=row, column_name="detachment_point_cost"
        ),
        unit_datasheet_ids=_required_split_field(row=row, column_name="unit_datasheet_ids"),
        force_disposition_ids=_required_split_field(row=row, column_name="force_disposition_ids"),
        rule_source_ids=_source_ids_from_row(row),
        enhancement_ids=_required_split_field(row=row, column_name="enhancement_ids"),
        stratagem_ids=_required_split_field(row=row, column_name="stratagem_ids"),
        source_ids=_source_ids_from_row(row),
    )


def _enhancement_from_row(row: NormalizedSourceRow) -> EnhancementDefinition:
    name = _required_field(row=row, column_name="name")
    return EnhancementDefinition(
        enhancement_id=row.source_row_id,
        name=name,
        source_id=_source_ids_from_row(row)[0],
        content_scope=_content_scope_from_row(row),
        subtypes=_enhancement_subtypes_from_row(row=row, name=name),
        points=_required_non_negative_int(row=row, column_name="points"),
    )


def _stratagem_from_row(row: NormalizedSourceRow) -> StratagemDefinition:
    return StratagemDefinition(
        stratagem_id=row.source_row_id,
        name=_required_field(row=row, column_name="name"),
        source_id=_source_ids_from_row(row)[0],
        content_scope=_content_scope_from_row(row),
        command_point_cost=_required_non_negative_int(row=row, column_name="command_point_cost"),
        timing_tags=_required_split_field(row=row, column_name="timing_tags"),
    )


def _geometry_record_from_model_row(
    *,
    row: NormalizedSourceRow,
    model_profile_id: str,
) -> ModelGeometryCatalogRecord | ModelGeometryImportDiagnostic:
    fields = row.runtime_fields_payload()
    if "base_size" not in fields:
        raise CatalogGenerationError("Model profile source row is missing base_size.")
    base_size_text = fields["base_size"].strip()
    normalized_base_size = base_size_text.strip().lower()
    if normalized_base_size in _BASE_SIZE_BLOCKERS:
        return _geometry_diagnostic(
            row=row,
            model_profile_id=model_profile_id,
            reason=(
                ModelGeometryDiagnosticReason.MISSING_BASE_SIZE
                if not normalized_base_size
                else ModelGeometryDiagnosticReason.MISSING_OVERRIDE
            ),
            message="Model profile requires an explicit geometry override.",
        )
    footprint_kind: ModelFootprintKind
    source_dimensions: tuple[tuple[str, float], ...]
    circular_match = _CIRCULAR_BASE_RE.fullmatch(base_size_text.strip())
    oval_match = _OVAL_BASE_RE.fullmatch(base_size_text.strip())
    if circular_match is not None:
        footprint_kind = ModelFootprintKind.CIRCULAR
        source_dimensions = (("diameter", float(circular_match.group("diameter"))),)
    elif oval_match is not None:
        footprint_kind = ModelFootprintKind.OVAL
        source_dimensions = (
            ("length", float(oval_match.group("length"))),
            ("width", float(oval_match.group("width"))),
        )
    else:
        return _geometry_diagnostic(
            row=row,
            model_profile_id=model_profile_id,
            reason=ModelGeometryDiagnosticReason.NON_DERIVABLE_FOOTPRINT,
            message="Model profile base size is not a circular or oval source footprint.",
        )
    base_size_source_id = _optional_field(row=row, column_name="base_size_source_id")
    if base_size_source_id is None:
        base_size_source_id = row.stable_source_id()
    base_size_document_reference = _optional_field(
        row=row,
        column_name="base_size_document_reference",
    )
    if base_size_document_reference is None:
        base_size_document_reference = row.stable_source_id()
    if not _has_required_height_fields(row):
        return _geometry_diagnostic(
            row=row,
            model_profile_id=model_profile_id,
            reason=ModelGeometryDiagnosticReason.MISSING_HEIGHT,
            message="Model profile requires representative height evidence.",
        )
    footprint_evidence = ModelGeometrySourceEvidence.from_source_dimensions(
        evidence_id=f"{model_profile_id}:footprint",
        evidence_kind=GeometryEvidenceKind.OFFICIAL_BASE_SIZE,
        measurement_kind=GeometryMeasurementKind.FOOTPRINT,
        source_id=base_size_source_id,
        source_units=GeometrySourceUnits.MILLIMETERS,
        source_dimensions=source_dimensions,
        document_reference=base_size_document_reference,
    )
    height_evidence = ModelGeometrySourceEvidence.from_source_dimensions(
        evidence_id=f"{model_profile_id}:height",
        evidence_kind=_geometry_evidence_kind_from_field(
            _required_field(row=row, column_name="height_evidence_kind")
        ),
        measurement_kind=GeometryMeasurementKind.HEIGHT,
        source_id=_required_field(row=row, column_name="height_source_id"),
        source_units=_source_units_from_field(_required_field(row=row, column_name="height_units")),
        source_dimensions=(("height", _required_number(row=row, column_name="height")),),
        document_reference=_required_field(row=row, column_name="height_document_reference"),
        reviewer_status=_review_status_from_field(
            _required_field(row=row, column_name="height_reviewer_status")
        ),
    )
    if height_evidence.reviewer_status is not GeometryReviewStatus.ACCEPTED:
        return _geometry_diagnostic(
            row=row,
            model_profile_id=model_profile_id,
            reason=ModelGeometryDiagnosticReason.UNREVIEWED_EVIDENCE,
            message="Representative height evidence must be accepted before catalog emission.",
        )
    part = ModelFootprintPartDefinition.from_evidence(
        part_id="base",
        footprint_kind=footprint_kind,
        evidence=footprint_evidence,
    )
    footprint = ModelFootprintDefinition.single_part(
        footprint_id=f"{model_profile_id}:footprint",
        footprint_kind=footprint_kind,
        part=part,
    )
    return ModelGeometryCatalogRecord(
        model_geometry_id=model_profile_id,
        model_profile_id=model_profile_id,
        rules_footprint_policy=GeometryRulesFootprintPolicy.USE_FOOTPRINT,
        footprint=footprint,
        support_base=None,
        z_offset=None,
        height=ModelHeightDefinition.from_evidence(height_evidence),
        evidence=(footprint_evidence, height_evidence),
        source_ids=_deduplicated_ids((*_source_ids_from_row(row), base_size_source_id)),
    )


def _geometry_diagnostic(
    *,
    row: NormalizedSourceRow,
    model_profile_id: str,
    reason: ModelGeometryDiagnosticReason,
    message: str,
) -> ModelGeometryImportDiagnostic:
    return ModelGeometryImportDiagnostic(
        model_profile_id=model_profile_id,
        source_id=row.stable_source_id(),
        reason=reason,
        message=message,
        blocking=True,
    )


def _base_size_from_geometry_record(record: ModelGeometryCatalogRecord) -> BaseSizeDefinition:
    footprint = record.support_base if record.support_base is not None else record.footprint
    part = footprint.parts[0]
    length_mm = part.radius_x_inches * 2.0 * 25.4
    width_mm = part.radius_y_inches * 2.0 * 25.4
    if footprint.footprint_kind is ModelFootprintKind.CIRCULAR:
        return BaseSizeDefinition.circular(length_mm)
    if footprint.footprint_kind is ModelFootprintKind.OVAL:
        return BaseSizeDefinition.oval(length_mm=length_mm, width_mm=width_mm)
    return BaseSizeDefinition.rectangular(length_mm=length_mm, width_mm=width_mm)


def _rows_by_table(
    source_artifacts: tuple[SourceArtifact, ...],
) -> dict[str, tuple[NormalizedSourceRow, ...]]:
    if type(source_artifacts) is not tuple:
        raise CatalogGenerationError("source_artifacts must be a tuple.")
    if not source_artifacts:
        raise CatalogGenerationError("source_artifacts must not be empty.")
    rows_by_table: dict[str, tuple[NormalizedSourceRow, ...]] = {}
    for artifact in source_artifacts:
        if type(artifact) not in {
            WahapediaJsonArtifact,
            PatchedSourceArtifact,
            OverlaySourceArtifact,
        }:
            raise CatalogGenerationError("source_artifacts must contain normalized artifacts.")
        existing = rows_by_table.get(artifact.source_table, ())
        rows_by_table[artifact.source_table] = (*existing, *artifact.rows)
    return rows_by_table


def _required_rows(
    *,
    rows_by_table: dict[str, tuple[NormalizedSourceRow, ...]],
    table_name: str,
) -> tuple[NormalizedSourceRow, ...]:
    rows = rows_by_table.get(table_name, ())
    if not rows:
        raise CatalogGenerationError(f"Source artifact table is required: {table_name}.")
    return rows


def _source_artifact_hashes(
    source_artifacts: tuple[SourceArtifact, ...],
) -> tuple[SourceArtifactHash, ...]:
    hashes: list[SourceArtifactHash] = []
    for artifact in source_artifacts:
        if type(artifact) is WahapediaJsonArtifact:
            hashes.append(artifact.source_artifact_hash())
        elif type(artifact) is PatchedSourceArtifact or type(artifact) is OverlaySourceArtifact:
            hashes.append(artifact.source_artifact_hash_record())
        else:
            raise CatalogGenerationError("Unsupported source artifact type.")
    return tuple(sorted(hashes, key=lambda item: item.artifact_name))


def _rows_matching(
    rows: tuple[NormalizedSourceRow, ...],
    column_name: str,
    value: str,
) -> tuple[NormalizedSourceRow, ...]:
    return tuple(row for row in rows if _required_field(row=row, column_name=column_name) == value)


def _geometry_overrides_by_profile_id(
    records: tuple[ModelGeometryCatalogRecord, ...],
) -> dict[str, ModelGeometryCatalogRecord]:
    if type(records) is not tuple:
        raise CatalogGenerationError("geometry_overrides must be a tuple.")
    by_profile_id: dict[str, ModelGeometryCatalogRecord] = {}
    for record in records:
        if type(record) is not ModelGeometryCatalogRecord:
            raise CatalogGenerationError("geometry_overrides must contain geometry records.")
        if record.model_profile_id in by_profile_id:
            raise CatalogGenerationError("geometry_overrides must not duplicate model profiles.")
        by_profile_id[record.model_profile_id] = record
    return by_profile_id


def _content_scope_from_row(row: NormalizedSourceRow) -> CatalogContentScope:
    try:
        return catalog_content_scope_from_token(
            _required_field(row=row, column_name="content_scope")
        )
    except ValueError as exc:
        raise CatalogGenerationError("Source row content_scope is invalid.") from exc


def _characteristic_from_row(
    *,
    row: NormalizedSourceRow,
    column_name: str,
    characteristic: Characteristic,
) -> CharacteristicValue:
    return _characteristic_value_from_raw_text(
        characteristic=characteristic,
        raw_text=_required_field(row=row, column_name=column_name),
    )


def _optional_characteristic_from_row(
    *,
    row: NormalizedSourceRow,
    column_name: str,
    characteristic: Characteristic,
) -> CharacteristicValue:
    return _characteristic_value_from_raw_text(
        characteristic=characteristic,
        raw_text=_optional_field(row=row, column_name=column_name) or "-",
    )


def _characteristic_value_from_raw_text(
    *,
    characteristic: Characteristic,
    raw_text: str,
) -> CharacteristicValue:
    text = raw_text.strip()
    if text == "-":
        return CharacteristicValue.source_dash(characteristic)
    return CharacteristicValue.from_raw(characteristic, _int_from_text(text))


def _characteristic_token_from_field(value: str) -> Characteristic:
    if value == Characteristic.BALLISTIC_SKILL.value:
        return Characteristic.BALLISTIC_SKILL
    if value == Characteristic.WEAPON_SKILL.value:
        return Characteristic.WEAPON_SKILL
    raise CatalogGenerationError(
        "Weapon skill_characteristic must be weapon_skill or ballistic_skill."
    )


def _range_profile_from_token(value: str) -> RangeProfile:
    if value.strip().lower() == "melee":
        return RangeProfile.melee()
    return RangeProfile.distance(_int_from_text(value))


def _attack_profile_from_raw_text(value: str) -> AttackProfile:
    fixed = _optional_int_from_text(value)
    if fixed is not None:
        if fixed < 1:
            raise CatalogGenerationError("Attack profile fixed attacks must be at least 1.")
        return AttackProfile.fixed(fixed)
    return AttackProfile.dice(_dice_expression_from_text(value))


def _damage_profile_from_raw_text(value: str) -> DamageProfile:
    fixed = _optional_int_from_text(value)
    if fixed is not None:
        if fixed < 1:
            raise CatalogGenerationError("Damage profile fixed damage must be at least 1.")
        return DamageProfile.fixed(fixed)
    return DamageProfile.dice(_dice_expression_from_text(value))


def _dice_expression_from_text(value: str) -> DiceExpression:
    match = _DICE_CHARACTERISTIC_RE.fullmatch(value.strip().replace(" ", ""))
    if match is None:
        raise CatalogGenerationError(
            f"Source value must be fixed integer or dice expression: {value}."
        )
    quantity_token = match.group("quantity")
    quantity = 1 if not quantity_token else _int_from_text(quantity_token)
    sides = _int_from_text(match.group("sides"))
    modifier_token = match.group("modifier")
    modifier = 0 if modifier_token is None else _int_from_text(modifier_token)
    try:
        return DiceExpression(quantity=quantity, sides=sides, modifier=modifier)
    except DiceRollSpecError as exc:
        raise CatalogGenerationError("Source dice expression is invalid.") from exc


def _weapon_keywords_from_field(value: str) -> tuple[WeaponKeyword, ...]:
    if not value.strip():
        return ()
    keywords: list[WeaponKeyword] = []
    for item in _split_field_value(value):
        try:
            keywords.append(WeaponKeyword(item))
        except ValueError as exc:
            raise CatalogGenerationError("Unsupported weapon keyword in source row.") from exc
    return tuple(sorted(keywords, key=lambda keyword: keyword.value))


def _weapon_abilities_from_field(value: str) -> tuple[AbilityDescriptor, ...]:
    if not value.strip():
        return ()
    try:
        raw_payload: object = json.loads(value)
    except json.JSONDecodeError as exc:
        raise CatalogGenerationError("Weapon ability descriptor payload must be JSON.") from exc
    if type(raw_payload) is not list:
        raise CatalogGenerationError("Weapon ability descriptor payload must be a list.")
    abilities: list[AbilityDescriptor] = []
    for item in cast(list[object], raw_payload):
        payload = _weapon_ability_payload(item)
        try:
            abilities.append(AbilityDescriptor.from_payload(payload))
        except WeaponProfileError as exc:
            raise CatalogGenerationError("Weapon ability descriptor payload is invalid.") from exc
    return tuple(abilities)


def _weapon_ability_payload(value: object) -> AbilityDescriptorPayload:
    if type(value) is not dict:
        raise CatalogGenerationError("Weapon ability descriptor item must be an object.")
    mapping = cast(dict[str, object], value)
    required_keys = {
        "ability_id",
        "name",
        "ability_kind",
        "parameters",
        "target_keywords",
        "timing",
        "condition",
    }
    if set(mapping) != required_keys:
        raise CatalogGenerationError("Weapon ability descriptor item has invalid keys.")
    return cast(AbilityDescriptorPayload, mapping)


def _has_required_height_fields(row: NormalizedSourceRow) -> bool:
    fields = row.runtime_fields_payload()
    return all(
        fields.get(column_name, "").strip()
        for column_name in (
            "height",
            "height_units",
            "height_source_id",
            "height_document_reference",
            "height_reviewer_status",
            "height_evidence_kind",
        )
    )


def _geometry_evidence_kind_from_field(value: str) -> GeometryEvidenceKind:
    try:
        return GeometryEvidenceKind(value)
    except ValueError as exc:
        raise CatalogGenerationError("Geometry evidence kind is invalid.") from exc


def _source_units_from_field(value: str) -> GeometrySourceUnits:
    try:
        return GeometrySourceUnits(value)
    except ValueError as exc:
        raise CatalogGenerationError("Geometry source units are invalid.") from exc


def _review_status_from_field(value: str) -> GeometryReviewStatus:
    try:
        return GeometryReviewStatus(value)
    except ValueError as exc:
        raise CatalogGenerationError("Geometry review status is invalid.") from exc


def _required_split_field(row: NormalizedSourceRow, column_name: str) -> tuple[str, ...]:
    value = _required_field(row=row, column_name=column_name)
    return _split_field_value(value)


def _optional_split_field(row: NormalizedSourceRow, column_name: str) -> tuple[str, ...]:
    value = row.runtime_fields_payload().get(column_name)
    if value is None or not value.strip():
        return ()
    return _split_field_value(value)


def _optional_field(*, row: NormalizedSourceRow, column_name: str) -> str | None:
    value = row.runtime_fields_payload().get(column_name)
    if value is None:
        return None
    stripped = value.strip()
    return stripped if stripped else None


def _source_ids_from_row(row: NormalizedSourceRow) -> tuple[str, ...]:
    explicit_source_ids = _optional_split_field(row, "source_ids")
    return _deduplicated_ids((row.stable_source_id(), *explicit_source_ids))


def _source_ids_from_rows(rows: tuple[NormalizedSourceRow, ...]) -> tuple[str, ...]:
    return _deduplicated_ids(
        tuple(source_id for row in rows for source_id in _source_ids_from_row(row))
    )


def _deduplicated_ids(values: tuple[str, ...]) -> tuple[str, ...]:
    seen: set[str] = set()
    deduplicated: list[str] = []
    for value in values:
        identifier = value.strip()
        if not identifier:
            raise CatalogGenerationError("Source identifier must not be empty.")
        if identifier in seen:
            continue
        seen.add(identifier)
        deduplicated.append(identifier)
    return tuple(deduplicated)


def _split_field_value(value: str) -> tuple[str, ...]:
    items = tuple(item.strip() for item in value.split(",") if item.strip())
    if not items:
        raise CatalogGenerationError("Required list field must not be empty.")
    seen: set[str] = set()
    unique: list[str] = []
    for item in items:
        if item in seen:
            raise CatalogGenerationError("Required list field must not contain duplicates.")
        seen.add(item)
        unique.append(item)
    return tuple(unique)


def _enhancement_subtypes_from_row(
    *,
    row: NormalizedSourceRow,
    name: str,
) -> tuple[EnhancementSubtype, ...]:
    subtypes = _enhancement_subtypes_from_tokens(_optional_split_field(row, "subtypes"))
    if _ENHANCEMENT_UPGRADE_NAME_SUFFIX.search(name) is None:
        return subtypes
    if EnhancementSubtype.UPGRADE in subtypes:
        return subtypes
    return tuple(sorted((*subtypes, EnhancementSubtype.UPGRADE), key=lambda subtype: subtype.value))


def _enhancement_subtypes_from_tokens(tokens: tuple[str, ...]) -> tuple[EnhancementSubtype, ...]:
    seen: set[EnhancementSubtype] = set()
    subtypes: list[EnhancementSubtype] = []
    for token in tokens:
        normalized = token.strip().casefold().replace(" ", "_")
        try:
            subtype = EnhancementSubtype(normalized)
        except ValueError as exc:
            raise CatalogGenerationError("Enhancement subtype source token is invalid.") from exc
        if subtype in seen:
            raise CatalogGenerationError("Enhancement subtype source tokens must not duplicate.")
        seen.add(subtype)
        subtypes.append(subtype)
    return tuple(sorted(subtypes, key=lambda subtype: subtype.value))


def _required_positive_int(row: NormalizedSourceRow, column_name: str) -> int:
    value = _required_int(row=row, column_name=column_name)
    if value < 1:
        raise CatalogGenerationError(f"Source row {column_name} must be at least 1.")
    return value


def _required_non_negative_int(row: NormalizedSourceRow, column_name: str) -> int:
    value = _required_int(row=row, column_name=column_name)
    if value < 0:
        raise CatalogGenerationError(f"Source row {column_name} must not be negative.")
    return value


def _optional_positive_int(row: NormalizedSourceRow, column_name: str) -> int | None:
    value = _optional_field(row=row, column_name=column_name)
    if value is None:
        return None
    integer = _int_from_text(value)
    if integer < 1:
        raise CatalogGenerationError(f"Source row {column_name} must be at least 1.")
    return integer


def _required_int(row: NormalizedSourceRow, column_name: str) -> int:
    return _int_from_text(_required_field(row=row, column_name=column_name))


def _required_bool(row: NormalizedSourceRow, column_name: str) -> bool:
    value = _required_field(row=row, column_name=column_name).casefold()
    if value == "true":
        return True
    if value == "false":
        return False
    raise CatalogGenerationError(f"Source row {column_name} must be true or false.")


def _required_number(row: NormalizedSourceRow, column_name: str) -> float:
    value = _required_field(row=row, column_name=column_name)
    try:
        return float(value)
    except ValueError as exc:
        raise CatalogGenerationError(f"Source row {column_name} must be numeric.") from exc


def _int_from_text(value: str) -> int:
    normalized = value.strip().removesuffix('"').removesuffix("+")
    try:
        return int(normalized)
    except ValueError as exc:
        raise CatalogGenerationError(f"Source value must be an integer: {value}.") from exc


def _optional_int_from_text(value: str) -> int | None:
    normalized = value.strip().removesuffix('"').removesuffix("+")
    if _INTEGER_CHARACTERISTIC_RE.fullmatch(normalized) is None:
        return None
    return int(normalized)


def _required_field(*, row: NormalizedSourceRow, column_name: str) -> str:
    fields = row.runtime_fields_payload()
    if column_name not in fields:
        raise CatalogGenerationError(
            f"Required source column {column_name} is missing from {row.stable_source_id()}."
        )
    value = fields[column_name].strip()
    if not value:
        raise CatalogGenerationError(
            f"Required source column {column_name} is empty in {row.stable_source_id()}."
        )
    return value


def _validate_diagnostics(
    diagnostics: tuple[ModelGeometryImportDiagnostic, ...],
) -> tuple[ModelGeometryImportDiagnostic, ...]:
    if type(diagnostics) is not tuple:
        raise CatalogGenerationError("diagnostics must be a tuple.")
    for diagnostic in diagnostics:
        if type(diagnostic) is not ModelGeometryImportDiagnostic:
            raise CatalogGenerationError("diagnostics must contain geometry diagnostics.")
    return tuple(
        sorted(
            diagnostics,
            key=lambda diagnostic: (
                diagnostic.model_profile_id,
                diagnostic.source_id,
                diagnostic.reason.value,
            ),
        )
    )
