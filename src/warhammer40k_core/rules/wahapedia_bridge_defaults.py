from __future__ import annotations

from dataclasses import dataclass

from warhammer40k_core.core.model_geometry_catalog import (
    GeometryEvidenceKind,
    GeometryReviewStatus,
    GeometrySourceUnits,
)
from warhammer40k_core.core.validation import IdentifierValidator


class WahapediaBridgeDefaultsError(ValueError):
    """Raised when bridge default correction data is malformed."""


@dataclass(frozen=True, slots=True)
class PdfDatasheetCorrection:
    datasheet_id: str
    source_id: str
    removed_keywords: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "datasheet_id",
            _validate_identifier("datasheet_id", self.datasheet_id),
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
            self,
            "datasheet_id",
            _validate_identifier("datasheet_id", self.datasheet_id),
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


def _validate_identifier_tuple(field_name: str, values: tuple[str, ...]) -> tuple[str, ...]:
    if type(values) is not tuple:
        raise WahapediaBridgeDefaultsError(f"{field_name} must be a tuple.")
    seen: set[str] = set()
    validated: list[str] = []
    for value in values:
        identifier = _validate_identifier(f"{field_name} value", value)
        if identifier in seen:
            raise WahapediaBridgeDefaultsError(f"{field_name} must not contain duplicates.")
        seen.add(identifier)
        validated.append(identifier)
    return tuple(validated)


def _validate_positive_float(field_name: str, value: object) -> float:
    if not isinstance(value, int | float) or type(value) is bool:
        raise WahapediaBridgeDefaultsError(f"{field_name} must be a number.")
    number = float(value)
    if number <= 0.0:
        raise WahapediaBridgeDefaultsError(f"{field_name} must be greater than 0.")
    return number


_validate_identifier = IdentifierValidator(WahapediaBridgeDefaultsError)

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

CHAOS_DAEMONS_KAIROS_FATEWEAVER_HEIGHT_OVERRIDES = (
    ModelHeightOverride(
        datasheet_id="000001117",
        model_name="Kairos Fateweaver - EPIC HERO",
        height=7.0,
        height_units=GeometrySourceUnits.INCHES,
        height_source_id="geometry-review:chaos-daemons:kairos-fateweaver:height",
        height_document_reference="https://www.adeptusars.com/miniatures/kairos-fateweaver",
        evidence_kind=GeometryEvidenceKind.CROWD_SOURCED_MEASUREMENT,
    ),
)

AELDARI_KHARSETH_HEIGHT_OVERRIDES = (
    ModelHeightOverride(
        datasheet_id="000004194",
        model_name="Kharseth - EPIC HERO",
        height=2.5,
        height_units=GeometrySourceUnits.INCHES,
        height_source_id="geometry-review:aeldari:kharseth:height",
        height_document_reference=(
            "Warhammer Community Kharseth assembled and sprue imagery; "
            "Warhammer Event Companion 2026-06-12 p.59 (32mm base)"
        ),
    ),
)

DEATH_GUARD_DEFILER_PDF_CORRECTION = PdfDatasheetCorrection(
    datasheet_id="000004209",
    source_id="pdf:death-guard-faction-pack:2026-06-10:p5-p6",
)
WORLD_EATERS_DEFILER_PDF_CORRECTION = PdfDatasheetCorrection(
    datasheet_id="000004207",
    source_id="pdf:world-eaters-faction-pack:2026-06-10:p5-p6",
)
THOUSAND_SONS_DEFILER_PDF_CORRECTION = PdfDatasheetCorrection(
    datasheet_id="000001030",
    source_id="pdf:thousand-sons-faction-pack:2026-06-10:p7-p8",
)
EMPERORS_CHILDREN_DEFILER_PDF_CORRECTION = PdfDatasheetCorrection(
    datasheet_id="000004208",
    source_id="pdf:emperors-children-faction-pack:2026-06-10:p7-p8",
)
CHAOS_DEFILER_PDF_CORRECTIONS = (
    DEATH_GUARD_DEFILER_PDF_CORRECTION,
    WORLD_EATERS_DEFILER_PDF_CORRECTION,
    THOUSAND_SONS_DEFILER_PDF_CORRECTION,
    EMPERORS_CHILDREN_DEFILER_PDF_CORRECTION,
)
CHAOS_DEFILER_HEIGHT_OVERRIDES = (
    ModelHeightOverride(
        datasheet_id="000004209",
        model_name="Defiler",
        height=4.5,
        height_units=GeometrySourceUnits.INCHES,
        height_source_id="geometry-review:death-guard:defiler:height",
        height_document_reference="Death Guard Faction Pack p.5-6",
    ),
    ModelHeightOverride(
        datasheet_id="000004207",
        model_name="Defiler",
        height=4.5,
        height_units=GeometrySourceUnits.INCHES,
        height_source_id="geometry-review:world-eaters:defiler:height",
        height_document_reference="World Eaters Faction Pack p.5-6",
    ),
    ModelHeightOverride(
        datasheet_id="000001030",
        model_name="Defiler",
        height=4.5,
        height_units=GeometrySourceUnits.INCHES,
        height_source_id="geometry-review:thousand-sons:defiler:height",
        height_document_reference="Thousand Sons Faction Pack p.7-8",
    ),
    ModelHeightOverride(
        datasheet_id="000004208",
        model_name="Defiler",
        height=4.5,
        height_units=GeometrySourceUnits.INCHES,
        height_source_id="geometry-review:emperors-children:defiler:height",
        height_document_reference="Emperor's Children Faction Pack p.7-8",
    ),
)

DEFAULT_PDF_CORRECTIONS = (
    CHAOS_DAEMONS_BLOODCRUSHERS_PDF_CORRECTION,
    *CHAOS_DEFILER_PDF_CORRECTIONS,
)
DEFAULT_HEIGHT_OVERRIDES = (
    *AELDARI_KHARSETH_HEIGHT_OVERRIDES,
    *CHAOS_DAEMONS_BLOODCRUSHERS_HEIGHT_OVERRIDES,
    *CHAOS_DAEMONS_KAIROS_FATEWEAVER_HEIGHT_OVERRIDES,
    *CHAOS_DEFILER_HEIGHT_OVERRIDES,
)
