from __future__ import annotations

from dataclasses import dataclass

from warhammer40k_core.core.model_geometry_catalog import (
    GeometryEvidenceKind,
    GeometryReviewStatus,
    GeometrySourceUnits,
)
from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    july_faction_packs_2026_07 as july_source,
)


class WahapediaBridgeDefaultsError(ValueError):
    """Raised when bridge default correction data is malformed."""


@dataclass(frozen=True, slots=True)
class PdfDatasheetCorrection:
    datasheet_id: str
    source_id: str
    removed_keywords: tuple[str, ...] = ()
    replacement_keywords: tuple[str, ...] | None = None
    source_package_version: str = "2026-06-10"

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
        if self.replacement_keywords is not None:
            object.__setattr__(
                self,
                "replacement_keywords",
                _validate_identifier_tuple(
                    "replacement_keywords",
                    self.replacement_keywords,
                ),
            )
            if not self.replacement_keywords:
                raise WahapediaBridgeDefaultsError(
                    "replacement_keywords must not be empty when provided."
                )
        if self.removed_keywords and self.replacement_keywords is not None:
            raise WahapediaBridgeDefaultsError(
                "A PDF correction cannot remove and replace keywords simultaneously."
            )
        object.__setattr__(
            self,
            "source_package_version",
            _validate_identifier("source_package_version", self.source_package_version),
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


def _july_chaos_daemons_keyword_correction(datasheet_id: str) -> PdfDatasheetCorrection:
    row = july_source.chaos_daemons_keyword_overlay_for_datasheet(datasheet_id)
    if row is None:
        raise WahapediaBridgeDefaultsError(
            "Required July Chaos Daemons keyword overlay is unavailable."
        )
    return PdfDatasheetCorrection(
        datasheet_id=datasheet_id,
        source_id=row.source_row_id,
        replacement_keywords=tuple(row.replacement_keywords),
        source_package_version=july_source.SOURCE_VERSION,
    )


CHAOS_DAEMONS_SCREAMERS_PDF_CORRECTION = _july_chaos_daemons_keyword_correction("000001127")
CHAOS_DAEMONS_FECULENT_GNARLMAW_PDF_CORRECTION = PdfDatasheetCorrection(
    datasheet_id="000001470",
    source_id=("gw-11e-faction-packs-2026-07:datasheet-keywords:chaos-daemons:000001470"),
    replacement_keywords=(
        "FORTIFICATION",
        "CHAOS",
        "DAEMON",
        "FRAME",
        "NURGLE",
        "FECULENT GNARLMAW",
    ),
    source_package_version=july_source.SOURCE_VERSION,
)
CHAOS_DAEMONS_SKULL_ALTAR_PDF_CORRECTION = PdfDatasheetCorrection(
    datasheet_id="000001588",
    source_id=("gw-11e-faction-packs-2026-07:datasheet-keywords:chaos-daemons:000001588"),
    replacement_keywords=(
        "FORTIFICATION",
        "CHAOS",
        "DAEMON",
        "FRAME",
        "KHORNE",
        "SKULL ALTAR",
    ),
    source_package_version=july_source.SOURCE_VERSION,
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

AELDARI_RANGERS_HEIGHT_OVERRIDES = (
    ModelHeightOverride(
        datasheet_id="000000592",
        model_name="Rangers",
        height=2.0,
        height_units=GeometrySourceUnits.INCHES,
        height_source_id="geometry-review:aeldari:rangers:height",
        height_document_reference=(
            "Warhammer Community Aeldari Designers' Notes 2022-03-23 assembled Rangers "
            "imagery; Warhammer Event Companion 2026-06-12 p.59 (28.5mm base)"
        ),
    ),
)

AELDARI_NIGHT_SPINNER_HEIGHT_OVERRIDES = (
    ModelHeightOverride(
        datasheet_id="000000611",
        model_name="Night Spinner",
        height=2.75,
        height_units=GeometrySourceUnits.INCHES,
        height_source_id="geometry-review:aeldari:night-spinner:height",
        height_document_reference=(
            "Aeldari Night Spinner assembled miniature imagery; "
            "Warhammer Event Companion 2026-06-12 p.59 (60mm flying base)"
        ),
    ),
)

AELDARI_AUTARCHS_HEIGHT_OVERRIDES = (
    ModelHeightOverride(
        datasheet_id="000000577",
        model_name="Autarch",
        height=2.25,
        height_units=GeometrySourceUnits.INCHES,
        height_source_id="geometry-review:aeldari:autarch:height",
        height_document_reference=(
            "Aeldari Autarch assembled miniature imagery; "
            "Warhammer Event Companion 2026-06-12 p.59 (32mm base)"
        ),
    ),
    ModelHeightOverride(
        datasheet_id="000002759",
        model_name="Autarch Wayleaper",
        height=3.25,
        height_units=GeometrySourceUnits.INCHES,
        height_source_id="geometry-review:aeldari:autarch-wayleaper:height",
        height_document_reference=(
            "Aeldari Autarch Wayleaper assembled miniature imagery; "
            "Warhammer Event Companion 2026-06-12 p.59 (32mm base)"
        ),
    ),
)

AELDARI_BANSHEES_PHOENIX_LORDS_SPIRITSEER_HEIGHT_OVERRIDES = (
    ModelHeightOverride(
        datasheet_id="000000572",
        model_name="Jain Zar - EPIC HERO",
        height=2.5,
        height_units=GeometrySourceUnits.INCHES,
        height_source_id="geometry-review:aeldari:jain-zar:height",
        height_document_reference=(
            "Aeldari Jain Zar assembled miniature imagery; "
            "Warhammer Event Companion 2026-06-12 p.59 (40mm base)"
        ),
    ),
    ModelHeightOverride(
        datasheet_id="000000574",
        model_name="Fuegan - EPIC HERO",
        height=2.25,
        height_units=GeometrySourceUnits.INCHES,
        height_source_id="geometry-review:aeldari:fuegan:height",
        height_document_reference=(
            "Aeldari Fuegan assembled miniature imagery; "
            "Warhammer Event Companion 2026-06-12 p.59 (40mm base)"
        ),
    ),
    ModelHeightOverride(
        datasheet_id="000000588",
        model_name="Spiritseer",
        height=2.0,
        height_units=GeometrySourceUnits.INCHES,
        height_source_id="geometry-review:aeldari:spiritseer:height",
        height_document_reference=(
            "Aeldari Spiritseer assembled miniature imagery; "
            "Warhammer Event Companion 2026-06-12 p.59 (25mm base)"
        ),
    ),
    ModelHeightOverride(
        datasheet_id="000003909",
        model_name="Lhykhis - EPIC HERO",
        height=3.0,
        height_units=GeometrySourceUnits.INCHES,
        height_source_id="geometry-review:aeldari:lhykhis:height",
        height_document_reference=(
            "Aeldari Lhykhis assembled miniature imagery; "
            "Warhammer Event Companion 2026-06-12 p.59 (40mm base)"
        ),
    ),
)

AELDARI_ASPECT_WARRIORS_HEIGHT_OVERRIDES = (
    ModelHeightOverride(
        datasheet_id="000000594",
        model_name="Howling Banshees",
        height=2.0,
        height_units=GeometrySourceUnits.INCHES,
        height_source_id="geometry-review:aeldari:howling-banshee:height",
        height_document_reference=(
            "Aeldari Faction Pack assembled miniature imagery; "
            "Warhammer Event Companion 2026-06-12 p.59 (28.5mm base)"
        ),
    ),
    ModelHeightOverride(
        datasheet_id="000000594",
        model_name="Howling Banshee Exarch",
        height=2.0,
        height_units=GeometrySourceUnits.INCHES,
        height_source_id="geometry-review:aeldari:howling-banshee-exarch:height",
        height_document_reference=(
            "Aeldari Faction Pack assembled miniature imagery; "
            "Warhammer Event Companion 2026-06-12 p.59 (28.5mm base)"
        ),
    ),
    ModelHeightOverride(
        datasheet_id="000000595",
        model_name="Striking Scorpions",
        height=2.0,
        height_units=GeometrySourceUnits.INCHES,
        height_source_id="geometry-review:aeldari:striking-scorpion:height",
        height_document_reference=(
            "Aeldari Faction Pack assembled miniature imagery; "
            "Warhammer Event Companion 2026-06-12 p.60 (28.5mm base)"
        ),
    ),
    ModelHeightOverride(
        datasheet_id="000000595",
        model_name="Striking Scorpion Exarch",
        height=2.0,
        height_units=GeometrySourceUnits.INCHES,
        height_source_id="geometry-review:aeldari:striking-scorpion-exarch:height",
        height_document_reference=(
            "Aeldari Faction Pack assembled miniature imagery; "
            "Warhammer Event Companion 2026-06-12 p.60 (28.5mm base)"
        ),
    ),
    ModelHeightOverride(
        datasheet_id="000000596",
        model_name="Fire Dragons",
        height=2.0,
        height_units=GeometrySourceUnits.INCHES,
        height_source_id="geometry-review:aeldari:fire-dragons:height",
        height_document_reference=(
            "Aeldari Faction Pack assembled miniature imagery; "
            "Warhammer Event Companion 2026-06-12 p.59 (28.5mm base)"
        ),
    ),
    ModelHeightOverride(
        datasheet_id="000000596",
        model_name="Fire Dragon Exarch",
        height=2.0,
        height_units=GeometrySourceUnits.INCHES,
        height_source_id="geometry-review:aeldari:fire-dragon-exarch:height",
        height_document_reference=(
            "Aeldari Faction Pack assembled miniature imagery; "
            "Warhammer Event Companion 2026-06-12 p.59 (28.5mm base)"
        ),
    ),
    ModelHeightOverride(
        datasheet_id="000000600",
        model_name="Swooping Hawks",
        height=2.75,
        height_units=GeometrySourceUnits.INCHES,
        height_source_id="geometry-review:aeldari:swooping-hawks:height",
        height_document_reference=(
            "Aeldari Faction Pack assembled miniature imagery; "
            "Warhammer Event Companion 2026-06-12 p.59 (32mm base)"
        ),
    ),
    ModelHeightOverride(
        datasheet_id="000000600",
        model_name="Swooping Hawk Exarch",
        height=2.75,
        height_units=GeometrySourceUnits.INCHES,
        height_source_id="geometry-review:aeldari:swooping-hawk-exarch:height",
        height_document_reference=(
            "Aeldari Faction Pack assembled miniature imagery; "
            "Warhammer Event Companion 2026-06-12 p.59 (32mm base)"
        ),
    ),
    ModelHeightOverride(
        datasheet_id="000000601",
        model_name="Warp Spiders",
        height=2.0,
        height_units=GeometrySourceUnits.INCHES,
        height_source_id="geometry-review:aeldari:warp-spiders:height",
        height_document_reference=(
            "Aeldari Faction Pack assembled miniature imagery; "
            "Warhammer Event Companion 2026-06-12 p.59 (28.5mm base)"
        ),
    ),
    ModelHeightOverride(
        datasheet_id="000000601",
        model_name="Warp Spider Exarch",
        height=2.0,
        height_units=GeometrySourceUnits.INCHES,
        height_source_id="geometry-review:aeldari:warp-spider-exarch:height",
        height_document_reference=(
            "Aeldari Faction Pack assembled miniature imagery; "
            "Warhammer Event Companion 2026-06-12 p.59 (28.5mm base)"
        ),
    ),
)

AELDARI_SHROUD_RUNNERS_WRAITHBLADES_HEIGHT_OVERRIDES = (
    ModelHeightOverride(
        datasheet_id="000002533",
        model_name="Shroud Runners",
        height=3.25,
        height_units=GeometrySourceUnits.INCHES,
        height_source_id="geometry-review:aeldari:shroud-runners:height",
        height_document_reference=(
            "Aeldari Faction Pack assembled miniature imagery; "
            "Warhammer Event Companion 2026-06-12 p.59 (60mm base)"
        ),
    ),
    ModelHeightOverride(
        datasheet_id="000000598",
        model_name="Wraithblades",
        height=2.5,
        height_units=GeometrySourceUnits.INCHES,
        height_source_id="geometry-review:aeldari:wraithblades:height",
        height_document_reference=(
            "Aeldari Faction Pack assembled miniature imagery; "
            "Warhammer Event Companion 2026-06-12 p.59 (40mm base)"
        ),
    ),
)

AELDARI_WAR_WALKERS_WRAITHLORD_HEIGHT_OVERRIDES = (
    ModelHeightOverride(
        datasheet_id="000000612",
        model_name="War Walkers",
        height=3.25,
        height_units=GeometrySourceUnits.INCHES,
        height_source_id="geometry-review:aeldari:war-walkers:height",
        height_document_reference=(
            "Aeldari Faction Pack assembled miniature imagery; "
            "Warhammer Event Companion 2026-06-12 p.59 (60mm base)"
        ),
    ),
    ModelHeightOverride(
        datasheet_id="000000613",
        model_name="Wraithlord",
        height=4.75,
        height_units=GeometrySourceUnits.INCHES,
        height_source_id="geometry-review:aeldari:wraithlord:height",
        height_document_reference=(
            "Aeldari Faction Pack assembled miniature imagery; "
            "Warhammer Event Companion 2026-06-12 p.59 (60mm base)"
        ),
    ),
)

AELDARI_WAVE_SERPENT_SHINING_SPEARS_ELDRAD_DIRE_AVENGERS_HEIGHT_OVERRIDES = (
    ModelHeightOverride(
        datasheet_id="000000568",
        model_name="Eldrad Ulthran - EPIC HERO",
        height=2.25,
        height_units=GeometrySourceUnits.INCHES,
        height_source_id="geometry-review:aeldari:eldrad-ulthran:height",
        height_document_reference=(
            "Aeldari Faction Pack assembled miniature imagery; "
            "Warhammer Event Companion 2026-06-12 p.59 (32mm base)"
        ),
    ),
    ModelHeightOverride(
        datasheet_id="000000593",
        model_name="Dire Avenger Exarch",
        height=2.0,
        height_units=GeometrySourceUnits.INCHES,
        height_source_id="geometry-review:aeldari:dire-avengers:exarch:height",
        height_document_reference=(
            "Aeldari Faction Pack assembled miniature imagery; "
            "Warhammer Event Companion 2026-06-12 p.59 (28.5mm base)"
        ),
    ),
    ModelHeightOverride(
        datasheet_id="000000593",
        model_name="Dire Avengers",
        height=2.0,
        height_units=GeometrySourceUnits.INCHES,
        height_source_id="geometry-review:aeldari:dire-avengers:height",
        height_document_reference=(
            "Aeldari Faction Pack assembled miniature imagery; "
            "Warhammer Event Companion 2026-06-12 p.59 (28.5mm base)"
        ),
    ),
    ModelHeightOverride(
        datasheet_id="000000599",
        model_name="Wave Serpent",
        height=2.75,
        height_units=GeometrySourceUnits.INCHES,
        height_source_id="geometry-review:aeldari:wave-serpent:height",
        height_document_reference=(
            "Aeldari Faction Pack assembled miniature imagery; "
            "Warhammer Event Companion 2026-06-12 p.59 (60mm flying base)"
        ),
    ),
    ModelHeightOverride(
        datasheet_id="000000602",
        model_name="Shining Spear Exarch",
        height=3.25,
        height_units=GeometrySourceUnits.INCHES,
        height_source_id="geometry-review:aeldari:shining-spears:exarch:height",
        height_document_reference=(
            "Aeldari Faction Pack assembled miniature imagery; "
            "Warhammer Event Companion 2026-06-12 p.59 (60mm flying base)"
        ),
    ),
    ModelHeightOverride(
        datasheet_id="000000602",
        model_name="Shining Spears",
        height=3.25,
        height_units=GeometrySourceUnits.INCHES,
        height_source_id="geometry-review:aeldari:shining-spears:height",
        height_document_reference=(
            "Aeldari Faction Pack assembled miniature imagery; "
            "Warhammer Event Companion 2026-06-12 p.59 (60mm flying base)"
        ),
    ),
)

AELDARI_YRIEL_VYPERS_STARFANGS_HEIGHT_OVERRIDES = (
    ModelHeightOverride(
        datasheet_id="000004193",
        model_name="Prince Yriel - EPIC HERO",
        height=2.5,
        height_units=GeometrySourceUnits.INCHES,
        height_source_id="geometry-review:aeldari:prince-yriel:height",
        height_document_reference=(
            "Aeldari Faction Pack p.12-13 assembled miniature imagery; "
            "Warhammer Event Companion 2026-06-12 p.59 (40mm base)"
        ),
    ),
    ModelHeightOverride(
        datasheet_id="000000605",
        model_name="Vypers",
        height=2.75,
        height_units=GeometrySourceUnits.INCHES,
        height_source_id="geometry-review:aeldari:vypers:height",
        height_document_reference=(
            "Aeldari Faction Pack p.16-17 assembled miniature imagery; "
            "Warhammer Event Companion 2026-06-12 p.59 (105x70mm base)"
        ),
    ),
    ModelHeightOverride(
        datasheet_id="000004195",
        model_name="Starfangs",
        height=2.75,
        height_units=GeometrySourceUnits.INCHES,
        height_source_id="geometry-review:aeldari:starfangs:height",
        height_document_reference=(
            "Aeldari Faction Pack p.18-19 assembled miniature imagery; "
            "Warhammer Event Companion 2026-06-12 p.59 (105x70mm base)"
        ),
    ),
)

AELDARI_CORSAIR_SKYREAVERS_HEIGHT_OVERRIDES = (
    ModelHeightOverride(
        datasheet_id="000004196",
        model_name="Skyreaver Felarch",
        height=3.25,
        height_units=GeometrySourceUnits.INCHES,
        height_source_id="geometry-review:aeldari:corsair-skyreavers:felarch:height",
        height_document_reference=(
            "Warhammer Community Eldritch Raiders assembled promotional imagery; "
            "Warhammer Event Companion 2026-06-12 p.59 (28.5mm base)"
        ),
    ),
    ModelHeightOverride(
        datasheet_id="000004196",
        model_name="Skyreavers",
        height=3.25,
        height_units=GeometrySourceUnits.INCHES,
        height_source_id="geometry-review:aeldari:corsair-skyreavers:skyreavers:height",
        height_document_reference=(
            "Warhammer Community Eldritch Raiders assembled promotional imagery; "
            "Warhammer Event Companion 2026-06-12 p.59 (28.5mm base)"
        ),
    ),
)

AELDARI_CORSAIR_VOID_UNITS_HEIGHT_OVERRIDES = tuple(
    ModelHeightOverride(
        datasheet_id=datasheet_id,
        model_name=model_name,
        height=2.0,
        height_units=GeometrySourceUnits.INCHES,
        height_source_id=f"geometry-review:aeldari:corsair-void-units:{source_key}:height",
        height_document_reference=(
            "Aeldari Corsair Voidscarred assembled kit imagery; "
            "Warhammer Event Companion 2026-06-12 p.59 (28.5mm base)"
        ),
    )
    for datasheet_id, model_name, source_key in (
        ("000002531", "Voidreaver Felarch", "voidreaver-felarch"),
        ("000002531", "Corsair Voidreavers", "corsair-voidreavers"),
        ("000002532", "Voidscarred Felarch", "voidscarred-felarch"),
        ("000002532", "Corsair Voidscarred", "corsair-voidscarred"),
        ("000002532", "Shade Runner", "shade-runner"),
        ("000002532", "Soul Weaver", "soul-weaver"),
        ("000002532", "Way Seeker", "way-seeker"),
    )
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
EMPERORS_CHILDREN_FULGRIM_HEIGHT_OVERRIDES = (
    ModelHeightOverride(
        datasheet_id="000004077",
        model_name="Fulgrim - EPIC HERO",
        height=5.5,
        height_units=GeometrySourceUnits.INCHES,
        height_source_id="geometry-review:emperors-children:fulgrim:height",
        height_document_reference=(
            "Emperor's Children Faction Pack Fulgrim assembled miniature imagery; "
            "Warhammer Event Companion 2026-06-12 p.61 (130mm base)"
        ),
    ),
)
EMPERORS_CHILDREN_LUCIUS_HEIGHT_OVERRIDES = (
    ModelHeightOverride(
        datasheet_id="000004083",
        model_name="Lucius the Eternal - EPIC HERO",
        height=2.25,
        height_units=GeometrySourceUnits.INCHES,
        height_source_id="geometry-review:emperors-children:lucius-the-eternal:height",
        height_document_reference=(
            "Lucius the Eternal assembled miniature imagery; "
            "Warhammer Event Companion 2026-07-22 p.74 (50mm base)"
        ),
    ),
)
EMPERORS_CHILDREN_INFRACTORS_TORMENTORS_HEIGHT_OVERRIDES = tuple(
    ModelHeightOverride(
        datasheet_id=datasheet_id,
        model_name=model_name,
        height=1.75,
        height_units=GeometrySourceUnits.INCHES,
        height_source_id=f"geometry-review:emperors-children:{source_key}:height",
        height_document_reference=(
            f"Emperor's Children {model_name} assembled miniature imagery; "
            "Warhammer Event Companion 2026-07-22 p.74 (32mm base)"
        ),
    )
    for datasheet_id, model_name, source_key in (
        ("000004079", "Obsessionist", "tormentors-obsessionist"),
        ("000004079", "Tormentors", "tormentors"),
        ("000004080", "Obsessionist", "infractors-obsessionist"),
        ("000004080", "Infractors", "infractors"),
    )
)
EMPERORS_CHILDREN_CHAOS_TERMINATORS_HEIGHT_OVERRIDES = tuple(
    ModelHeightOverride(
        datasheet_id="000004081",
        model_name=model_name,
        height=2.0,
        height_units=GeometrySourceUnits.INCHES,
        height_source_id=f"geometry-review:emperors-children:{source_key}:height",
        height_document_reference=(
            f"Emperor's Children {model_name} assembled miniature imagery; "
            "Warhammer Event Companion 2026-07-22 p.74 (40mm base)"
        ),
    )
    for model_name, source_key in (
        ("Terminator Champion", "terminator-champion"),
        ("Chaos Terminators", "chaos-terminators"),
    )
)
EMPERORS_CHILDREN_LORD_KAKOPHONIST_NOISE_MARINES_HEIGHT_OVERRIDES = (
    ModelHeightOverride(
        datasheet_id="000004084",
        model_name="Lord Kakophonist",
        height=2.5,
        height_units=GeometrySourceUnits.INCHES,
        height_source_id="geometry-review:emperors-children:lord-kakophonist:height",
        height_document_reference=(
            "Lord Kakophonist assembled miniature imagery; "
            "Warhammer Event Companion 2026-07-22 p.74 (40mm base)"
        ),
    ),
    ModelHeightOverride(
        datasheet_id="000004088",
        model_name="Disharmonist",
        height=2.0,
        height_units=GeometrySourceUnits.INCHES,
        height_source_id="geometry-review:emperors-children:disharmonist:height",
        height_document_reference=(
            "Noise Marines Disharmonist assembled miniature imagery; "
            "Warhammer Event Companion 2026-07-22 p.74 (40mm base)"
        ),
    ),
    ModelHeightOverride(
        datasheet_id="000004088",
        model_name="Noise Marines",
        height=2.0,
        height_units=GeometrySourceUnits.INCHES,
        height_source_id="geometry-review:emperors-children:noise-marines:height",
        height_document_reference=(
            "Noise Marines assembled miniature imagery; "
            "Warhammer Event Companion 2026-07-22 p.74 (40mm base)"
        ),
    ),
)
EMPERORS_CHILDREN_FLAWLESS_BLADES_HEIGHT_OVERRIDES = (
    ModelHeightOverride(
        datasheet_id="000004089",
        model_name="Flawless Blades",
        height=2.0,
        height_units=GeometrySourceUnits.INCHES,
        height_source_id="geometry-review:emperors-children:flawless-blades:height",
        height_document_reference=(
            "Emperor's Children Faction Pack Flawless Blades assembled miniature imagery; "
            "Warhammer Event Companion 2026-07-22 p.74 (40mm base)"
        ),
    ),
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
HORRORS_HEIGHT_OVERRIDES = tuple(
    ModelHeightOverride(
        datasheet_id=datasheet_id,
        model_name=model_name,
        height=height,
        height_units=GeometrySourceUnits.INCHES,
        height_source_id=f"geometry-review:horrors:{datasheet_id}:{profile_kind}:height",
        height_document_reference=document_reference,
    )
    for datasheet_id, model_name, profile_kind, height, document_reference in (
        (
            "000002583",
            "Blue Horrors",
            "blue",
            1.0,
            "Chaos Daemons Faction Pack p.52-53",
        ),
        (
            "000002584",
            "Pink Horrors",
            "pink",
            1.25,
            "Chaos Daemons Faction Pack p.54-55",
        ),
        (
            "000002584",
            "BLUE HORROR/BRIMSTONE HORROR",
            "blue-brimstone",
            1.0,
            "Chaos Daemons Faction Pack p.54-55",
        ),
        (
            "000004127",
            "Pink Horrors",
            "pink",
            1.25,
            "Thousand Sons Faction Pack Pink Horrors datasheet",
        ),
        (
            "000004127",
            "BLUE HORROR/BRIMSTONE HORROR",
            "blue-brimstone",
            1.0,
            "Thousand Sons Faction Pack Pink Horrors datasheet",
        ),
        (
            "000004128",
            "Blue Horrors",
            "blue",
            1.0,
            "Thousand Sons Faction Pack Blue Horrors datasheet",
        ),
    )
)

DEFAULT_PDF_CORRECTIONS = (
    CHAOS_DAEMONS_BLOODCRUSHERS_PDF_CORRECTION,
    CHAOS_DAEMONS_SCREAMERS_PDF_CORRECTION,
    CHAOS_DAEMONS_FECULENT_GNARLMAW_PDF_CORRECTION,
    CHAOS_DAEMONS_SKULL_ALTAR_PDF_CORRECTION,
    *CHAOS_DEFILER_PDF_CORRECTIONS,
)
DEFAULT_HEIGHT_OVERRIDES = (
    *HORRORS_HEIGHT_OVERRIDES,
    *AELDARI_CORSAIR_SKYREAVERS_HEIGHT_OVERRIDES,
    *AELDARI_CORSAIR_VOID_UNITS_HEIGHT_OVERRIDES,
    *AELDARI_KHARSETH_HEIGHT_OVERRIDES,
    *AELDARI_WAVE_SERPENT_SHINING_SPEARS_ELDRAD_DIRE_AVENGERS_HEIGHT_OVERRIDES,
    *CHAOS_DAEMONS_BLOODCRUSHERS_HEIGHT_OVERRIDES,
    *CHAOS_DAEMONS_KAIROS_FATEWEAVER_HEIGHT_OVERRIDES,
    *CHAOS_DEFILER_HEIGHT_OVERRIDES,
    *EMPERORS_CHILDREN_CHAOS_TERMINATORS_HEIGHT_OVERRIDES,
    *EMPERORS_CHILDREN_FLAWLESS_BLADES_HEIGHT_OVERRIDES,
    *EMPERORS_CHILDREN_FULGRIM_HEIGHT_OVERRIDES,
    *EMPERORS_CHILDREN_INFRACTORS_TORMENTORS_HEIGHT_OVERRIDES,
    *EMPERORS_CHILDREN_LUCIUS_HEIGHT_OVERRIDES,
    *EMPERORS_CHILDREN_LORD_KAKOPHONIST_NOISE_MARINES_HEIGHT_OVERRIDES,
)
