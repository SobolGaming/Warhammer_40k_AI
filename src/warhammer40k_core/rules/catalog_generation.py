from __future__ import annotations

import re
from dataclasses import dataclass

from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.core.attributes import Characteristic, CharacteristicValue
from warhammer40k_core.core.content_scope import (
    CatalogContentScope,
    catalog_content_scope_from_token,
)
from warhammer40k_core.core.datasheet import (
    BaseSizeDefinition,
    DatasheetDefinition,
    DatasheetKeywordSet,
    DatasheetWargearOption,
    ModelProfileDefinition,
    UnitCompositionDefinition,
)
from warhammer40k_core.core.detachment import (
    DetachmentDefinition,
    EnhancementDefinition,
    StratagemDefinition,
)
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
    AttackProfile,
    DamageProfile,
    RangeProfile,
    WeaponKeyword,
    WeaponProfile,
)
from warhammer40k_core.rules.catalog_package import CanonicalCatalogPackage
from warhammer40k_core.rules.data_package import CatalogVersion, DataPackageId
from warhammer40k_core.rules.source_catalog import SourceArtifactHash
from warhammer40k_core.rules.source_patch import PatchedSourceArtifact
from warhammer40k_core.rules.wahapedia_schema import NormalizedSourceRow, WahapediaJsonArtifact


class CatalogGenerationError(ValueError):
    """Raised when Phase 17B catalog generation violates strict source invariants."""


SourceArtifact = WahapediaJsonArtifact | PatchedSourceArtifact

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
_CIRCULAR_BASE_RE = re.compile(r"^(?P<diameter>\d+(?:\.\d+)?)\s*mm$", re.IGNORECASE)
_OVAL_BASE_RE = re.compile(
    r"^(?P<length>\d+(?:\.\d+)?)\s*x\s*(?P<width>\d+(?:\.\d+)?)\s*mm(?:\s*oval)?$",
    re.IGNORECASE,
)


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
    wargear = tuple(_wargear_from_row(row) for row in wargear_rows)
    army_rules = tuple(_army_rule_from_faction_row(row) for row in faction_rows)
    factions = tuple(_faction_from_row(row) for row in faction_rows)
    geometry_by_profile_id = {record.model_profile_id: record for record in geometry_records}
    datasheets = tuple(
        _datasheet_from_row(
            row=row,
            model_rows=_rows_matching(model_rows, "datasheet_id", row.source_row_id),
            wargear_rows=_rows_matching(wargear_rows, "datasheet_id", row.source_row_id),
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
        source_ids=tuple(row.stable_source_id() for row in (*datasheet_rows, *faction_rows)),
    )


def _datasheet_from_row(
    *,
    row: NormalizedSourceRow,
    model_rows: tuple[NormalizedSourceRow, ...],
    wargear_rows: tuple[NormalizedSourceRow, ...],
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
        wargear_options=tuple(_wargear_option_from_row(row) for row in wargear_rows),
        source_ids=(row.stable_source_id(),),
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
        source_ids=(row.stable_source_id(), geometry_record.stable_identity()),
    )


def _composition_from_model_row(row: NormalizedSourceRow) -> UnitCompositionDefinition:
    return UnitCompositionDefinition(
        model_profile_id=_required_field(row=row, column_name="model_profile_id"),
        min_models=_required_positive_int(row=row, column_name="min_models"),
        max_models=_required_positive_int(row=row, column_name="max_models"),
    )


def _wargear_option_from_row(row: NormalizedSourceRow) -> DatasheetWargearOption:
    wargear_id = _required_field(row=row, column_name="wargear_id")
    model_profile_id = _required_field(row=row, column_name="model_profile_id")
    return DatasheetWargearOption(
        option_id=f"{row.source_row_id}:default",
        model_profile_id=model_profile_id,
        default_wargear_ids=(wargear_id,),
        allowed_wargear_ids=(wargear_id,),
        min_selections=1,
        max_selections=1,
    )


def _wargear_from_row(row: NormalizedSourceRow) -> Wargear:
    return Wargear(
        wargear_id=_required_field(row=row, column_name="wargear_id"),
        name=_required_field(row=row, column_name="name"),
        weapon_profiles=(_weapon_profile_from_row(row),),
    )


def _weapon_profile_from_row(row: NormalizedSourceRow) -> WeaponProfile:
    skill_characteristic = _characteristic_token_from_field(
        _required_field(row=row, column_name="skill_characteristic")
    )
    return WeaponProfile(
        profile_id=_required_field(row=row, column_name="weapon_profile_id"),
        name=_required_field(row=row, column_name="name"),
        range_profile=_range_profile_from_token(_required_field(row=row, column_name="range")),
        attack_profile=AttackProfile.fixed(_required_positive_int(row=row, column_name="a")),
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
        damage_profile=DamageProfile.fixed(_required_int(row=row, column_name="d")),
        keywords=_weapon_keywords_from_field(
            _required_field(row=row, column_name="weapon_keywords")
        ),
    )


def _faction_from_row(row: NormalizedSourceRow) -> FactionDefinition:
    return FactionDefinition(
        faction_id=row.source_row_id,
        name=_required_field(row=row, column_name="name"),
        content_scope=_content_scope_from_row(row),
        faction_keywords=_required_split_field(row=row, column_name="faction_keywords"),
        army_rule_ids=(_required_field(row=row, column_name="army_rule_id"),),
        source_ids=(row.stable_source_id(),),
    )


def _army_rule_from_faction_row(row: NormalizedSourceRow) -> ArmyRuleDefinition:
    return ArmyRuleDefinition(
        rule_id=_required_field(row=row, column_name="army_rule_id"),
        name=_required_field(row=row, column_name="army_rule_name"),
        source_id=row.stable_source_id(),
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
        rule_source_ids=(row.stable_source_id(),),
        enhancement_ids=_required_split_field(row=row, column_name="enhancement_ids"),
        stratagem_ids=_required_split_field(row=row, column_name="stratagem_ids"),
        source_ids=(row.stable_source_id(),),
    )


def _enhancement_from_row(row: NormalizedSourceRow) -> EnhancementDefinition:
    return EnhancementDefinition(
        enhancement_id=row.source_row_id,
        name=_required_field(row=row, column_name="name"),
        source_id=row.stable_source_id(),
        content_scope=_content_scope_from_row(row),
        points=_required_non_negative_int(row=row, column_name="points"),
    )


def _stratagem_from_row(row: NormalizedSourceRow) -> StratagemDefinition:
    return StratagemDefinition(
        stratagem_id=row.source_row_id,
        name=_required_field(row=row, column_name="name"),
        source_id=row.stable_source_id(),
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
        source_id=row.stable_source_id(),
        source_units=GeometrySourceUnits.MILLIMETERS,
        source_dimensions=source_dimensions,
        document_reference=row.stable_source_id(),
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
        source_ids=(row.stable_source_id(),),
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
        if type(artifact) not in {WahapediaJsonArtifact, PatchedSourceArtifact}:
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
        elif type(artifact) is PatchedSourceArtifact:
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


def _required_int(row: NormalizedSourceRow, column_name: str) -> int:
    return _int_from_text(_required_field(row=row, column_name=column_name))


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
