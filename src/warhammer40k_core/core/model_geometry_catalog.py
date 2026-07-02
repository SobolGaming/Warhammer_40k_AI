from __future__ import annotations

import math
from dataclasses import dataclass
from enum import StrEnum
from typing import Self, TypedDict

from warhammer40k_core.core.validation import IdentifierValidator


class ModelGeometryCatalogError(ValueError):
    """Raised when model geometry catalog data violates CORE V2 invariants."""


class GeometrySourceUnits(StrEnum):
    MILLIMETERS = "millimeters"
    INCHES = "inches"


class CanonicalGeometryUnits(StrEnum):
    INCHES = "inches"


class GeometryCoordinateFrame(StrEnum):
    MODEL_CENTERED_Z_UP = "model_centered_z_up"


class GeometryOrigin(StrEnum):
    FOOTPRINT_CENTER_TABLE_SURFACE = "footprint_center_table_surface"
    SUPPORT_BASE_CENTER_TABLE_SURFACE = "support_base_center_table_surface"


class GeometryEvidenceKind(StrEnum):
    OFFICIAL_BASE_SIZE = "official_base_size"
    OFFICIAL_MODEL_PROFILE = "official_model_profile"
    MANUAL_MEASUREMENT = "manual_measurement"
    CROWD_SOURCED_MEASUREMENT = "crowd_sourced_measurement"


class GeometryMeasurementKind(StrEnum):
    FOOTPRINT = "footprint"
    SUPPORT_BASE = "support_base"
    Z_OFFSET = "z_offset"
    HEIGHT = "height"


class GeometryReviewStatus(StrEnum):
    ACCEPTED = "accepted"
    NEEDS_REVIEW = "needs_review"


class GeometryRulesFootprintPolicy(StrEnum):
    USE_FOOTPRINT = "use_footprint"
    USE_SUPPORT_BASE = "use_support_base"
    USE_HULL = "use_hull"


class ModelGeometryDiagnosticReason(StrEnum):
    INVALID_BASE_SIZE = "invalid_base_size"
    MISSING_BASE_SIZE = "missing_base_size"
    MISSING_HEIGHT = "missing_height"
    MISSING_OVERRIDE = "missing_override"
    NON_DERIVABLE_FOOTPRINT = "non_derivable_footprint"
    UNREVIEWED_EVIDENCE = "unreviewed_evidence"


class ModelFootprintKind(StrEnum):
    CIRCULAR = "circular"
    OVAL = "oval"
    RECTANGULAR = "rectangular"
    HULL = "hull"


class ModelGeometrySourceEvidencePayload(TypedDict):
    evidence_id: str
    evidence_kind: str
    measurement_kind: str
    source_id: str
    source_units: str
    source_dimensions: dict[str, float]
    canonical_units: str
    canonical_dimensions: dict[str, float]
    coordinate_frame: str
    origin: str
    document_reference: str | None
    url: str | None
    reviewer_status: str


class ModelFootprintPartDefinitionPayload(TypedDict):
    part_id: str
    footprint_kind: str
    radius_x_inches: float
    radius_y_inches: float
    offset_x_inches: float
    offset_y_inches: float
    source_units: str
    canonical_units: str
    coordinate_frame: str
    origin: str
    evidence_id: str


class ModelFootprintDefinitionPayload(TypedDict):
    footprint_id: str
    footprint_kind: str
    parts: list[ModelFootprintPartDefinitionPayload]
    source_units: str
    canonical_units: str
    coordinate_frame: str
    origin: str
    evidence_id: str


class ModelHeightDefinitionPayload(TypedDict):
    height_inches: float
    source_units: str
    canonical_units: str
    coordinate_frame: str
    origin: str
    evidence_id: str


class ModelZOffsetDefinitionPayload(TypedDict):
    z_offset_inches: float
    source_units: str
    canonical_units: str
    coordinate_frame: str
    origin: str
    evidence_id: str


class ModelGeometryCatalogRecordPayload(TypedDict):
    model_geometry_id: str
    model_profile_id: str
    rules_footprint_policy: str
    footprint: ModelFootprintDefinitionPayload
    support_base: ModelFootprintDefinitionPayload | None
    z_offset: ModelZOffsetDefinitionPayload | None
    height: ModelHeightDefinitionPayload
    evidence: list[ModelGeometrySourceEvidencePayload]
    source_ids: list[str]


class ModelGeometryImportDiagnosticPayload(TypedDict):
    model_profile_id: str
    source_id: str
    reason: str
    message: str
    blocking: bool


@dataclass(frozen=True, slots=True)
class ModelGeometrySourceEvidence:
    evidence_id: str
    evidence_kind: GeometryEvidenceKind
    measurement_kind: GeometryMeasurementKind
    source_id: str
    source_units: GeometrySourceUnits
    source_dimensions: tuple[tuple[str, float], ...]
    canonical_units: CanonicalGeometryUnits
    canonical_dimensions: tuple[tuple[str, float], ...]
    coordinate_frame: GeometryCoordinateFrame
    origin: GeometryOrigin
    document_reference: str | None = None
    url: str | None = None
    reviewer_status: GeometryReviewStatus = GeometryReviewStatus.ACCEPTED

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "evidence_id",
            _validate_identifier("ModelGeometrySourceEvidence evidence_id", self.evidence_id),
        )
        object.__setattr__(
            self,
            "evidence_kind",
            geometry_evidence_kind_from_token(self.evidence_kind),
        )
        object.__setattr__(
            self,
            "measurement_kind",
            geometry_measurement_kind_from_token(self.measurement_kind),
        )
        object.__setattr__(
            self,
            "source_id",
            _validate_identifier("ModelGeometrySourceEvidence source_id", self.source_id),
        )
        object.__setattr__(
            self,
            "source_units",
            geometry_source_units_from_token(self.source_units),
        )
        object.__setattr__(
            self,
            "source_dimensions",
            _validate_dimensions(
                "ModelGeometrySourceEvidence source_dimensions",
                self.source_dimensions,
                allow_zero=False,
            ),
        )
        object.__setattr__(
            self,
            "canonical_units",
            canonical_geometry_units_from_token(self.canonical_units),
        )
        object.__setattr__(
            self,
            "canonical_dimensions",
            _validate_dimensions(
                "ModelGeometrySourceEvidence canonical_dimensions",
                self.canonical_dimensions,
                allow_zero=False,
            ),
        )
        _validate_canonical_dimensions_match_source(
            source_units=self.source_units,
            source_dimensions=self.source_dimensions,
            canonical_dimensions=self.canonical_dimensions,
        )
        object.__setattr__(
            self,
            "coordinate_frame",
            geometry_coordinate_frame_from_token(self.coordinate_frame),
        )
        object.__setattr__(self, "origin", geometry_origin_from_token(self.origin))
        if self.document_reference is not None:
            object.__setattr__(
                self,
                "document_reference",
                _validate_identifier(
                    "ModelGeometrySourceEvidence document_reference",
                    self.document_reference,
                ),
            )
        if self.url is not None:
            object.__setattr__(
                self,
                "url",
                _validate_identifier("ModelGeometrySourceEvidence url", self.url),
            )
        if self.document_reference is None and self.url is None:
            raise ModelGeometryCatalogError(
                "ModelGeometrySourceEvidence requires document_reference or url."
            )
        object.__setattr__(
            self,
            "reviewer_status",
            geometry_review_status_from_token(self.reviewer_status),
        )

    @classmethod
    def from_source_dimensions(
        cls,
        *,
        evidence_id: str,
        evidence_kind: GeometryEvidenceKind,
        measurement_kind: GeometryMeasurementKind,
        source_id: str,
        source_units: GeometrySourceUnits,
        source_dimensions: tuple[tuple[str, float], ...],
        coordinate_frame: GeometryCoordinateFrame = GeometryCoordinateFrame.MODEL_CENTERED_Z_UP,
        origin: GeometryOrigin = GeometryOrigin.FOOTPRINT_CENTER_TABLE_SURFACE,
        document_reference: str | None = None,
        url: str | None = None,
        reviewer_status: GeometryReviewStatus = GeometryReviewStatus.ACCEPTED,
    ) -> Self:
        source_unit = geometry_source_units_from_token(source_units)
        source = _validate_dimensions(
            "ModelGeometrySourceEvidence source_dimensions",
            source_dimensions,
            allow_zero=False,
        )
        canonical = tuple(
            (name, convert_dimension_to_inches(value=value, source_units=source_unit))
            for name, value in source
        )
        return cls(
            evidence_id=evidence_id,
            evidence_kind=evidence_kind,
            measurement_kind=measurement_kind,
            source_id=source_id,
            source_units=source_unit,
            source_dimensions=source,
            canonical_units=CanonicalGeometryUnits.INCHES,
            canonical_dimensions=canonical,
            coordinate_frame=coordinate_frame,
            origin=origin,
            document_reference=document_reference,
            url=url,
            reviewer_status=reviewer_status,
        )

    def dimension_inches(self, name: str) -> float:
        requested_name = _validate_identifier("dimension name", name)
        for dimension_name, value in self.canonical_dimensions:
            if dimension_name == requested_name:
                return value
        raise ModelGeometryCatalogError("ModelGeometrySourceEvidence dimension was not found.")

    def require_accepted(self) -> None:
        if self.reviewer_status is not GeometryReviewStatus.ACCEPTED:
            raise ModelGeometryCatalogError("ModelGeometrySourceEvidence is not accepted.")

    def to_payload(self) -> ModelGeometrySourceEvidencePayload:
        return {
            "evidence_id": self.evidence_id,
            "evidence_kind": self.evidence_kind.value,
            "measurement_kind": self.measurement_kind.value,
            "source_id": self.source_id,
            "source_units": self.source_units.value,
            "source_dimensions": dict(self.source_dimensions),
            "canonical_units": self.canonical_units.value,
            "canonical_dimensions": dict(self.canonical_dimensions),
            "coordinate_frame": self.coordinate_frame.value,
            "origin": self.origin.value,
            "document_reference": self.document_reference,
            "url": self.url,
            "reviewer_status": self.reviewer_status.value,
        }

    @classmethod
    def from_payload(cls, payload: ModelGeometrySourceEvidencePayload) -> Self:
        return cls(
            evidence_id=payload["evidence_id"],
            evidence_kind=geometry_evidence_kind_from_token(payload["evidence_kind"]),
            measurement_kind=geometry_measurement_kind_from_token(payload["measurement_kind"]),
            source_id=payload["source_id"],
            source_units=geometry_source_units_from_token(payload["source_units"]),
            source_dimensions=tuple(payload["source_dimensions"].items()),
            canonical_units=canonical_geometry_units_from_token(payload["canonical_units"]),
            canonical_dimensions=tuple(payload["canonical_dimensions"].items()),
            coordinate_frame=geometry_coordinate_frame_from_token(payload["coordinate_frame"]),
            origin=geometry_origin_from_token(payload["origin"]),
            document_reference=payload["document_reference"],
            url=payload["url"],
            reviewer_status=geometry_review_status_from_token(payload["reviewer_status"]),
        )


@dataclass(frozen=True, slots=True)
class ModelFootprintPartDefinition:
    part_id: str
    footprint_kind: ModelFootprintKind
    radius_x_inches: float
    radius_y_inches: float
    offset_x_inches: float
    offset_y_inches: float
    source_units: GeometrySourceUnits
    canonical_units: CanonicalGeometryUnits
    coordinate_frame: GeometryCoordinateFrame
    origin: GeometryOrigin
    evidence_id: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "part_id",
            _validate_identifier("ModelFootprintPartDefinition part_id", self.part_id),
        )
        footprint_kind = model_footprint_kind_from_token(self.footprint_kind)
        object.__setattr__(self, "footprint_kind", footprint_kind)
        radius_x_inches = _validate_positive_number(
            "ModelFootprintPartDefinition radius_x_inches",
            self.radius_x_inches,
        )
        radius_y_inches = _validate_positive_number(
            "ModelFootprintPartDefinition radius_y_inches",
            self.radius_y_inches,
        )
        if footprint_kind is ModelFootprintKind.CIRCULAR and radius_x_inches != radius_y_inches:
            raise ModelGeometryCatalogError(
                "Circular ModelFootprintPartDefinition radii must match."
            )
        if footprint_kind is ModelFootprintKind.OVAL and radius_x_inches < radius_y_inches:
            raise ModelGeometryCatalogError(
                "Oval ModelFootprintPartDefinition radius_x_inches must be at least "
                "radius_y_inches."
            )
        object.__setattr__(self, "radius_x_inches", radius_x_inches)
        object.__setattr__(self, "radius_y_inches", radius_y_inches)
        object.__setattr__(
            self,
            "offset_x_inches",
            _validate_finite_number(
                "ModelFootprintPartDefinition offset_x_inches",
                self.offset_x_inches,
            ),
        )
        object.__setattr__(
            self,
            "offset_y_inches",
            _validate_finite_number(
                "ModelFootprintPartDefinition offset_y_inches",
                self.offset_y_inches,
            ),
        )
        object.__setattr__(
            self,
            "source_units",
            geometry_source_units_from_token(self.source_units),
        )
        object.__setattr__(
            self,
            "canonical_units",
            canonical_geometry_units_from_token(self.canonical_units),
        )
        object.__setattr__(
            self,
            "coordinate_frame",
            geometry_coordinate_frame_from_token(self.coordinate_frame),
        )
        object.__setattr__(self, "origin", geometry_origin_from_token(self.origin))
        object.__setattr__(
            self,
            "evidence_id",
            _validate_identifier("ModelFootprintPartDefinition evidence_id", self.evidence_id),
        )

    @classmethod
    def from_evidence(
        cls,
        *,
        part_id: str,
        footprint_kind: ModelFootprintKind,
        evidence: ModelGeometrySourceEvidence,
        offset_x_inches: float = 0.0,
        offset_y_inches: float = 0.0,
    ) -> Self:
        if type(evidence) is not ModelGeometrySourceEvidence:
            raise ModelGeometryCatalogError("ModelFootprintPartDefinition evidence is invalid.")
        if evidence.measurement_kind not in {
            GeometryMeasurementKind.FOOTPRINT,
            GeometryMeasurementKind.SUPPORT_BASE,
        }:
            raise ModelGeometryCatalogError(
                "ModelFootprintPartDefinition evidence must be footprint or support-base."
            )
        evidence.require_accepted()
        footprint = model_footprint_kind_from_token(footprint_kind)
        radius_x_inches, radius_y_inches = _footprint_radii_from_evidence(
            footprint_kind=footprint,
            evidence=evidence,
        )
        return cls(
            part_id=part_id,
            footprint_kind=footprint,
            radius_x_inches=radius_x_inches,
            radius_y_inches=radius_y_inches,
            offset_x_inches=offset_x_inches,
            offset_y_inches=offset_y_inches,
            source_units=evidence.source_units,
            canonical_units=evidence.canonical_units,
            coordinate_frame=evidence.coordinate_frame,
            origin=evidence.origin,
            evidence_id=evidence.evidence_id,
        )

    def to_payload(self) -> ModelFootprintPartDefinitionPayload:
        return {
            "part_id": self.part_id,
            "footprint_kind": self.footprint_kind.value,
            "radius_x_inches": self.radius_x_inches,
            "radius_y_inches": self.radius_y_inches,
            "offset_x_inches": self.offset_x_inches,
            "offset_y_inches": self.offset_y_inches,
            "source_units": self.source_units.value,
            "canonical_units": self.canonical_units.value,
            "coordinate_frame": self.coordinate_frame.value,
            "origin": self.origin.value,
            "evidence_id": self.evidence_id,
        }

    @classmethod
    def from_payload(cls, payload: ModelFootprintPartDefinitionPayload) -> Self:
        return cls(
            part_id=payload["part_id"],
            footprint_kind=model_footprint_kind_from_token(payload["footprint_kind"]),
            radius_x_inches=payload["radius_x_inches"],
            radius_y_inches=payload["radius_y_inches"],
            offset_x_inches=payload["offset_x_inches"],
            offset_y_inches=payload["offset_y_inches"],
            source_units=geometry_source_units_from_token(payload["source_units"]),
            canonical_units=canonical_geometry_units_from_token(payload["canonical_units"]),
            coordinate_frame=geometry_coordinate_frame_from_token(payload["coordinate_frame"]),
            origin=geometry_origin_from_token(payload["origin"]),
            evidence_id=payload["evidence_id"],
        )


@dataclass(frozen=True, slots=True)
class ModelFootprintDefinition:
    footprint_id: str
    footprint_kind: ModelFootprintKind
    parts: tuple[ModelFootprintPartDefinition, ...]
    source_units: GeometrySourceUnits
    canonical_units: CanonicalGeometryUnits
    coordinate_frame: GeometryCoordinateFrame
    origin: GeometryOrigin
    evidence_id: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "footprint_id",
            _validate_identifier("ModelFootprintDefinition footprint_id", self.footprint_id),
        )
        footprint_kind = model_footprint_kind_from_token(self.footprint_kind)
        object.__setattr__(self, "footprint_kind", footprint_kind)
        parts = _validate_footprint_parts(self.parts)
        if any(part.footprint_kind is not footprint_kind for part in parts):
            raise ModelGeometryCatalogError("ModelFootprintDefinition parts must match kind.")
        object.__setattr__(self, "parts", parts)
        object.__setattr__(
            self,
            "source_units",
            geometry_source_units_from_token(self.source_units),
        )
        object.__setattr__(
            self,
            "canonical_units",
            canonical_geometry_units_from_token(self.canonical_units),
        )
        object.__setattr__(
            self,
            "coordinate_frame",
            geometry_coordinate_frame_from_token(self.coordinate_frame),
        )
        object.__setattr__(self, "origin", geometry_origin_from_token(self.origin))
        object.__setattr__(
            self,
            "evidence_id",
            _validate_identifier("ModelFootprintDefinition evidence_id", self.evidence_id),
        )

    @classmethod
    def single_part(
        cls,
        *,
        footprint_id: str,
        footprint_kind: ModelFootprintKind,
        part: ModelFootprintPartDefinition,
    ) -> Self:
        if type(part) is not ModelFootprintPartDefinition:
            raise ModelGeometryCatalogError("ModelFootprintDefinition part is invalid.")
        return cls(
            footprint_id=footprint_id,
            footprint_kind=footprint_kind,
            parts=(part,),
            source_units=part.source_units,
            canonical_units=part.canonical_units,
            coordinate_frame=part.coordinate_frame,
            origin=part.origin,
            evidence_id=part.evidence_id,
        )

    def to_payload(self) -> ModelFootprintDefinitionPayload:
        return {
            "footprint_id": self.footprint_id,
            "footprint_kind": self.footprint_kind.value,
            "parts": [part.to_payload() for part in self.parts],
            "source_units": self.source_units.value,
            "canonical_units": self.canonical_units.value,
            "coordinate_frame": self.coordinate_frame.value,
            "origin": self.origin.value,
            "evidence_id": self.evidence_id,
        }

    @classmethod
    def from_payload(cls, payload: ModelFootprintDefinitionPayload) -> Self:
        return cls(
            footprint_id=payload["footprint_id"],
            footprint_kind=model_footprint_kind_from_token(payload["footprint_kind"]),
            parts=tuple(
                ModelFootprintPartDefinition.from_payload(part) for part in payload["parts"]
            ),
            source_units=geometry_source_units_from_token(payload["source_units"]),
            canonical_units=canonical_geometry_units_from_token(payload["canonical_units"]),
            coordinate_frame=geometry_coordinate_frame_from_token(payload["coordinate_frame"]),
            origin=geometry_origin_from_token(payload["origin"]),
            evidence_id=payload["evidence_id"],
        )


@dataclass(frozen=True, slots=True)
class ModelHeightDefinition:
    height_inches: float
    source_units: GeometrySourceUnits
    canonical_units: CanonicalGeometryUnits
    coordinate_frame: GeometryCoordinateFrame
    origin: GeometryOrigin
    evidence_id: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "height_inches",
            _validate_positive_number("ModelHeightDefinition height_inches", self.height_inches),
        )
        object.__setattr__(
            self,
            "source_units",
            geometry_source_units_from_token(self.source_units),
        )
        object.__setattr__(
            self,
            "canonical_units",
            canonical_geometry_units_from_token(self.canonical_units),
        )
        object.__setattr__(
            self,
            "coordinate_frame",
            geometry_coordinate_frame_from_token(self.coordinate_frame),
        )
        object.__setattr__(self, "origin", geometry_origin_from_token(self.origin))
        object.__setattr__(
            self,
            "evidence_id",
            _validate_identifier("ModelHeightDefinition evidence_id", self.evidence_id),
        )

    @classmethod
    def from_evidence(cls, evidence: ModelGeometrySourceEvidence) -> Self:
        if type(evidence) is not ModelGeometrySourceEvidence:
            raise ModelGeometryCatalogError("ModelHeightDefinition evidence is invalid.")
        if evidence.measurement_kind is not GeometryMeasurementKind.HEIGHT:
            raise ModelGeometryCatalogError("ModelHeightDefinition evidence must be height.")
        evidence.require_accepted()
        return cls(
            height_inches=evidence.dimension_inches("height"),
            source_units=evidence.source_units,
            canonical_units=evidence.canonical_units,
            coordinate_frame=evidence.coordinate_frame,
            origin=evidence.origin,
            evidence_id=evidence.evidence_id,
        )

    def to_payload(self) -> ModelHeightDefinitionPayload:
        return {
            "height_inches": self.height_inches,
            "source_units": self.source_units.value,
            "canonical_units": self.canonical_units.value,
            "coordinate_frame": self.coordinate_frame.value,
            "origin": self.origin.value,
            "evidence_id": self.evidence_id,
        }

    @classmethod
    def from_payload(cls, payload: ModelHeightDefinitionPayload) -> Self:
        return cls(
            height_inches=payload["height_inches"],
            source_units=geometry_source_units_from_token(payload["source_units"]),
            canonical_units=canonical_geometry_units_from_token(payload["canonical_units"]),
            coordinate_frame=geometry_coordinate_frame_from_token(payload["coordinate_frame"]),
            origin=geometry_origin_from_token(payload["origin"]),
            evidence_id=payload["evidence_id"],
        )


@dataclass(frozen=True, slots=True)
class ModelZOffsetDefinition:
    z_offset_inches: float
    source_units: GeometrySourceUnits
    canonical_units: CanonicalGeometryUnits
    coordinate_frame: GeometryCoordinateFrame
    origin: GeometryOrigin
    evidence_id: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "z_offset_inches",
            _validate_non_negative_number(
                "ModelZOffsetDefinition z_offset_inches",
                self.z_offset_inches,
            ),
        )
        object.__setattr__(
            self,
            "source_units",
            geometry_source_units_from_token(self.source_units),
        )
        object.__setattr__(
            self,
            "canonical_units",
            canonical_geometry_units_from_token(self.canonical_units),
        )
        object.__setattr__(
            self,
            "coordinate_frame",
            geometry_coordinate_frame_from_token(self.coordinate_frame),
        )
        object.__setattr__(self, "origin", geometry_origin_from_token(self.origin))
        object.__setattr__(
            self,
            "evidence_id",
            _validate_identifier("ModelZOffsetDefinition evidence_id", self.evidence_id),
        )

    @classmethod
    def from_evidence(cls, evidence: ModelGeometrySourceEvidence) -> Self:
        if type(evidence) is not ModelGeometrySourceEvidence:
            raise ModelGeometryCatalogError("ModelZOffsetDefinition evidence is invalid.")
        if evidence.measurement_kind is not GeometryMeasurementKind.Z_OFFSET:
            raise ModelGeometryCatalogError("ModelZOffsetDefinition evidence must be z-offset.")
        evidence.require_accepted()
        return cls(
            z_offset_inches=evidence.dimension_inches("z_offset"),
            source_units=evidence.source_units,
            canonical_units=evidence.canonical_units,
            coordinate_frame=evidence.coordinate_frame,
            origin=evidence.origin,
            evidence_id=evidence.evidence_id,
        )

    def to_payload(self) -> ModelZOffsetDefinitionPayload:
        return {
            "z_offset_inches": self.z_offset_inches,
            "source_units": self.source_units.value,
            "canonical_units": self.canonical_units.value,
            "coordinate_frame": self.coordinate_frame.value,
            "origin": self.origin.value,
            "evidence_id": self.evidence_id,
        }

    @classmethod
    def from_payload(cls, payload: ModelZOffsetDefinitionPayload) -> Self:
        return cls(
            z_offset_inches=payload["z_offset_inches"],
            source_units=geometry_source_units_from_token(payload["source_units"]),
            canonical_units=canonical_geometry_units_from_token(payload["canonical_units"]),
            coordinate_frame=geometry_coordinate_frame_from_token(payload["coordinate_frame"]),
            origin=geometry_origin_from_token(payload["origin"]),
            evidence_id=payload["evidence_id"],
        )


@dataclass(frozen=True, slots=True)
class ModelGeometryCatalogRecord:
    model_geometry_id: str
    model_profile_id: str
    rules_footprint_policy: GeometryRulesFootprintPolicy
    footprint: ModelFootprintDefinition
    support_base: ModelFootprintDefinition | None
    z_offset: ModelZOffsetDefinition | None
    height: ModelHeightDefinition
    evidence: tuple[ModelGeometrySourceEvidence, ...]
    source_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "model_geometry_id",
            _validate_identifier(
                "ModelGeometryCatalogRecord model_geometry_id", self.model_geometry_id
            ),
        )
        object.__setattr__(
            self,
            "model_profile_id",
            _validate_identifier(
                "ModelGeometryCatalogRecord model_profile_id", self.model_profile_id
            ),
        )
        object.__setattr__(
            self,
            "rules_footprint_policy",
            geometry_rules_footprint_policy_from_token(self.rules_footprint_policy),
        )
        if type(self.footprint) is not ModelFootprintDefinition:
            raise ModelGeometryCatalogError(
                "ModelGeometryCatalogRecord footprint must be ModelFootprintDefinition."
            )
        if (
            self.support_base is not None
            and type(self.support_base) is not ModelFootprintDefinition
        ):
            raise ModelGeometryCatalogError(
                "ModelGeometryCatalogRecord support_base must be ModelFootprintDefinition."
            )
        if self.z_offset is not None and type(self.z_offset) is not ModelZOffsetDefinition:
            raise ModelGeometryCatalogError(
                "ModelGeometryCatalogRecord z_offset must be ModelZOffsetDefinition."
            )
        if type(self.height) is not ModelHeightDefinition:
            raise ModelGeometryCatalogError(
                "ModelGeometryCatalogRecord height must be ModelHeightDefinition."
            )
        evidence = _validate_evidence_tuple(self.evidence)
        _validate_record_evidence_links(
            footprint=self.footprint,
            support_base=self.support_base,
            z_offset=self.z_offset,
            height=self.height,
            evidence=evidence,
        )
        if (
            self.rules_footprint_policy is GeometryRulesFootprintPolicy.USE_SUPPORT_BASE
            and self.support_base is None
        ):
            raise ModelGeometryCatalogError(
                "ModelGeometryCatalogRecord support-base policy requires support_base."
            )
        object.__setattr__(self, "evidence", evidence)
        object.__setattr__(
            self,
            "source_ids",
            _validate_identifier_tuple("ModelGeometryCatalogRecord source_ids", self.source_ids),
        )

    def stable_identity(self) -> str:
        return f"model-geometry:{self.model_geometry_id}"

    def rules_footprint(self) -> ModelFootprintDefinition:
        if self.rules_footprint_policy is GeometryRulesFootprintPolicy.USE_SUPPORT_BASE:
            if self.support_base is None:
                raise ModelGeometryCatalogError("Support-base rules footprint is missing.")
            return self.support_base
        return self.footprint

    def to_payload(self) -> ModelGeometryCatalogRecordPayload:
        return {
            "model_geometry_id": self.model_geometry_id,
            "model_profile_id": self.model_profile_id,
            "rules_footprint_policy": self.rules_footprint_policy.value,
            "footprint": self.footprint.to_payload(),
            "support_base": None if self.support_base is None else self.support_base.to_payload(),
            "z_offset": None if self.z_offset is None else self.z_offset.to_payload(),
            "height": self.height.to_payload(),
            "evidence": [evidence.to_payload() for evidence in self.evidence],
            "source_ids": list(self.source_ids),
        }

    @classmethod
    def from_payload(cls, payload: ModelGeometryCatalogRecordPayload) -> Self:
        support_base_payload = payload["support_base"]
        z_offset_payload = payload["z_offset"]
        return cls(
            model_geometry_id=payload["model_geometry_id"],
            model_profile_id=payload["model_profile_id"],
            rules_footprint_policy=geometry_rules_footprint_policy_from_token(
                payload["rules_footprint_policy"]
            ),
            footprint=ModelFootprintDefinition.from_payload(payload["footprint"]),
            support_base=(
                None
                if support_base_payload is None
                else ModelFootprintDefinition.from_payload(support_base_payload)
            ),
            z_offset=(
                None
                if z_offset_payload is None
                else ModelZOffsetDefinition.from_payload(z_offset_payload)
            ),
            height=ModelHeightDefinition.from_payload(payload["height"]),
            evidence=tuple(
                ModelGeometrySourceEvidence.from_payload(evidence)
                for evidence in payload["evidence"]
            ),
            source_ids=tuple(payload["source_ids"]),
        )


@dataclass(frozen=True, slots=True)
class ModelGeometryImportDiagnostic:
    model_profile_id: str
    source_id: str
    reason: ModelGeometryDiagnosticReason
    message: str
    blocking: bool = True

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "model_profile_id",
            _validate_identifier(
                "ModelGeometryImportDiagnostic model_profile_id", self.model_profile_id
            ),
        )
        object.__setattr__(
            self,
            "source_id",
            _validate_identifier("ModelGeometryImportDiagnostic source_id", self.source_id),
        )
        object.__setattr__(
            self,
            "reason",
            model_geometry_diagnostic_reason_from_token(self.reason),
        )
        object.__setattr__(
            self,
            "message",
            _validate_identifier("ModelGeometryImportDiagnostic message", self.message),
        )
        if type(self.blocking) is not bool:
            raise ModelGeometryCatalogError("ModelGeometryImportDiagnostic blocking must be bool.")

    def to_payload(self) -> ModelGeometryImportDiagnosticPayload:
        return {
            "model_profile_id": self.model_profile_id,
            "source_id": self.source_id,
            "reason": self.reason.value,
            "message": self.message,
            "blocking": self.blocking,
        }

    @classmethod
    def from_payload(cls, payload: ModelGeometryImportDiagnosticPayload) -> Self:
        return cls(
            model_profile_id=payload["model_profile_id"],
            source_id=payload["source_id"],
            reason=model_geometry_diagnostic_reason_from_token(payload["reason"]),
            message=payload["message"],
            blocking=payload["blocking"],
        )


def convert_dimension_to_inches(*, value: float, source_units: GeometrySourceUnits) -> float:
    number = _validate_positive_number("dimension value", value)
    units = geometry_source_units_from_token(source_units)
    if units is GeometrySourceUnits.INCHES:
        return number
    if units is GeometrySourceUnits.MILLIMETERS:
        return number / 25.4
    raise ModelGeometryCatalogError("Unsupported source units.")


def geometry_source_units_from_token(token: object) -> GeometrySourceUnits:
    if type(token) is GeometrySourceUnits:
        return token
    if type(token) is not str:
        raise ModelGeometryCatalogError("GeometrySourceUnits token must be a string.")
    try:
        return GeometrySourceUnits(token)
    except ValueError as exc:
        raise ModelGeometryCatalogError(f"Unsupported GeometrySourceUnits token: {token}.") from exc


def canonical_geometry_units_from_token(token: object) -> CanonicalGeometryUnits:
    if type(token) is CanonicalGeometryUnits:
        return token
    if type(token) is not str:
        raise ModelGeometryCatalogError("CanonicalGeometryUnits token must be a string.")
    try:
        return CanonicalGeometryUnits(token)
    except ValueError as exc:
        raise ModelGeometryCatalogError(
            f"Unsupported CanonicalGeometryUnits token: {token}."
        ) from exc


def geometry_coordinate_frame_from_token(token: object) -> GeometryCoordinateFrame:
    if type(token) is GeometryCoordinateFrame:
        return token
    if type(token) is not str:
        raise ModelGeometryCatalogError("GeometryCoordinateFrame token must be a string.")
    try:
        return GeometryCoordinateFrame(token)
    except ValueError as exc:
        raise ModelGeometryCatalogError(
            f"Unsupported GeometryCoordinateFrame token: {token}."
        ) from exc


def geometry_origin_from_token(token: object) -> GeometryOrigin:
    if type(token) is GeometryOrigin:
        return token
    if type(token) is not str:
        raise ModelGeometryCatalogError("GeometryOrigin token must be a string.")
    try:
        return GeometryOrigin(token)
    except ValueError as exc:
        raise ModelGeometryCatalogError(f"Unsupported GeometryOrigin token: {token}.") from exc


def geometry_evidence_kind_from_token(token: object) -> GeometryEvidenceKind:
    if type(token) is GeometryEvidenceKind:
        return token
    if type(token) is not str:
        raise ModelGeometryCatalogError("GeometryEvidenceKind token must be a string.")
    try:
        return GeometryEvidenceKind(token)
    except ValueError as exc:
        raise ModelGeometryCatalogError(
            f"Unsupported GeometryEvidenceKind token: {token}."
        ) from exc


def geometry_measurement_kind_from_token(token: object) -> GeometryMeasurementKind:
    if type(token) is GeometryMeasurementKind:
        return token
    if type(token) is not str:
        raise ModelGeometryCatalogError("GeometryMeasurementKind token must be a string.")
    try:
        return GeometryMeasurementKind(token)
    except ValueError as exc:
        raise ModelGeometryCatalogError(
            f"Unsupported GeometryMeasurementKind token: {token}."
        ) from exc


def geometry_review_status_from_token(token: object) -> GeometryReviewStatus:
    if type(token) is GeometryReviewStatus:
        return token
    if type(token) is not str:
        raise ModelGeometryCatalogError("GeometryReviewStatus token must be a string.")
    try:
        return GeometryReviewStatus(token)
    except ValueError as exc:
        raise ModelGeometryCatalogError(
            f"Unsupported GeometryReviewStatus token: {token}."
        ) from exc


def geometry_rules_footprint_policy_from_token(token: object) -> GeometryRulesFootprintPolicy:
    if type(token) is GeometryRulesFootprintPolicy:
        return token
    if type(token) is not str:
        raise ModelGeometryCatalogError("GeometryRulesFootprintPolicy token must be a string.")
    try:
        return GeometryRulesFootprintPolicy(token)
    except ValueError as exc:
        raise ModelGeometryCatalogError(
            f"Unsupported GeometryRulesFootprintPolicy token: {token}."
        ) from exc


def model_geometry_diagnostic_reason_from_token(token: object) -> ModelGeometryDiagnosticReason:
    if type(token) is ModelGeometryDiagnosticReason:
        return token
    if type(token) is not str:
        raise ModelGeometryCatalogError("ModelGeometryDiagnosticReason token must be a string.")
    try:
        return ModelGeometryDiagnosticReason(token)
    except ValueError as exc:
        raise ModelGeometryCatalogError(
            f"Unsupported ModelGeometryDiagnosticReason token: {token}."
        ) from exc


def model_footprint_kind_from_token(token: object) -> ModelFootprintKind:
    if type(token) is ModelFootprintKind:
        return token
    if type(token) is not str:
        raise ModelGeometryCatalogError("ModelFootprintKind token must be a string.")
    try:
        return ModelFootprintKind(token)
    except ValueError as exc:
        raise ModelGeometryCatalogError(f"Unsupported ModelFootprintKind token: {token}.") from exc


def _footprint_radii_from_evidence(
    *,
    footprint_kind: ModelFootprintKind,
    evidence: ModelGeometrySourceEvidence,
) -> tuple[float, float]:
    if footprint_kind is ModelFootprintKind.CIRCULAR:
        radius = evidence.dimension_inches("diameter") / 2.0
        return radius, radius
    if footprint_kind in {
        ModelFootprintKind.OVAL,
        ModelFootprintKind.RECTANGULAR,
        ModelFootprintKind.HULL,
    }:
        return evidence.dimension_inches("length") / 2.0, evidence.dimension_inches("width") / 2.0
    raise ModelGeometryCatalogError("Unsupported footprint kind.")


def _validate_record_evidence_links(
    *,
    footprint: ModelFootprintDefinition,
    support_base: ModelFootprintDefinition | None,
    z_offset: ModelZOffsetDefinition | None,
    height: ModelHeightDefinition,
    evidence: tuple[ModelGeometrySourceEvidence, ...],
) -> None:
    evidence_by_id = {item.evidence_id: item for item in evidence}
    _validate_footprint_evidence_links(
        footprint=footprint,
        measurement_kind=GeometryMeasurementKind.FOOTPRINT,
        evidence_by_id=evidence_by_id,
    )
    if support_base is not None:
        _validate_footprint_evidence_links(
            footprint=support_base,
            measurement_kind=GeometryMeasurementKind.SUPPORT_BASE,
            evidence_by_id=evidence_by_id,
        )
    if z_offset is not None:
        _validate_linked_evidence(
            evidence_id=z_offset.evidence_id,
            measurement_kind=GeometryMeasurementKind.Z_OFFSET,
            evidence_by_id=evidence_by_id,
        )
    _validate_linked_evidence(
        evidence_id=height.evidence_id,
        measurement_kind=GeometryMeasurementKind.HEIGHT,
        evidence_by_id=evidence_by_id,
    )


def _validate_footprint_evidence_links(
    *,
    footprint: ModelFootprintDefinition,
    measurement_kind: GeometryMeasurementKind,
    evidence_by_id: dict[str, ModelGeometrySourceEvidence],
) -> None:
    _validate_linked_evidence(
        evidence_id=footprint.evidence_id,
        measurement_kind=measurement_kind,
        evidence_by_id=evidence_by_id,
    )
    for part in footprint.parts:
        _validate_linked_evidence(
            evidence_id=part.evidence_id,
            measurement_kind=measurement_kind,
            evidence_by_id=evidence_by_id,
        )


def _validate_linked_evidence(
    *,
    evidence_id: str,
    measurement_kind: GeometryMeasurementKind,
    evidence_by_id: dict[str, ModelGeometrySourceEvidence],
) -> None:
    linked_evidence = evidence_by_id.get(evidence_id)
    if linked_evidence is None:
        raise ModelGeometryCatalogError(
            "ModelGeometryCatalogRecord references unknown geometry evidence."
        )
    if linked_evidence.measurement_kind is not measurement_kind:
        raise ModelGeometryCatalogError(
            "ModelGeometryCatalogRecord references geometry evidence with wrong measurement kind."
        )
    linked_evidence.require_accepted()


def _validate_evidence_tuple(
    values: tuple[ModelGeometrySourceEvidence, ...],
) -> tuple[ModelGeometrySourceEvidence, ...]:
    if type(values) is not tuple:
        raise ModelGeometryCatalogError("ModelGeometryCatalogRecord evidence must be a tuple.")
    if not values:
        raise ModelGeometryCatalogError("ModelGeometryCatalogRecord evidence must not be empty.")
    seen: set[str] = set()
    validated: list[ModelGeometrySourceEvidence] = []
    for value in values:
        if type(value) is not ModelGeometrySourceEvidence:
            raise ModelGeometryCatalogError(
                "ModelGeometryCatalogRecord evidence must contain source evidence."
            )
        if value.evidence_id in seen:
            raise ModelGeometryCatalogError(
                "ModelGeometryCatalogRecord evidence must not contain duplicates."
            )
        seen.add(value.evidence_id)
        validated.append(value)
    return tuple(sorted(validated, key=lambda evidence: evidence.evidence_id))


def _validate_footprint_parts(
    values: tuple[ModelFootprintPartDefinition, ...],
) -> tuple[ModelFootprintPartDefinition, ...]:
    if type(values) is not tuple:
        raise ModelGeometryCatalogError("ModelFootprintDefinition parts must be a tuple.")
    if not values:
        raise ModelGeometryCatalogError("ModelFootprintDefinition parts must not be empty.")
    seen: set[str] = set()
    validated: list[ModelFootprintPartDefinition] = []
    for value in values:
        if type(value) is not ModelFootprintPartDefinition:
            raise ModelGeometryCatalogError(
                "ModelFootprintDefinition parts must contain footprint parts."
            )
        if value.part_id in seen:
            raise ModelGeometryCatalogError(
                "ModelFootprintDefinition parts must not contain duplicates."
            )
        seen.add(value.part_id)
        validated.append(value)
    return tuple(sorted(validated, key=lambda part: part.part_id))


def _validate_dimensions(
    field_name: str,
    values: tuple[tuple[str, float], ...],
    *,
    allow_zero: bool,
) -> tuple[tuple[str, float], ...]:
    if type(values) is not tuple:
        raise ModelGeometryCatalogError(f"{field_name} must be a tuple.")
    if not values:
        raise ModelGeometryCatalogError(f"{field_name} must not be empty.")
    seen: set[str] = set()
    validated: list[tuple[str, float]] = []
    for name, value in values:
        dimension_name = _validate_identifier(f"{field_name} name", name)
        if dimension_name in seen:
            raise ModelGeometryCatalogError(f"{field_name} must not contain duplicates.")
        seen.add(dimension_name)
        number = (
            _validate_non_negative_number(f"{field_name} value", value)
            if allow_zero
            else _validate_positive_number(f"{field_name} value", value)
        )
        validated.append((dimension_name, number))
    return tuple(sorted(validated))


def _validate_canonical_dimensions_match_source(
    *,
    source_units: GeometrySourceUnits,
    source_dimensions: tuple[tuple[str, float], ...],
    canonical_dimensions: tuple[tuple[str, float], ...],
) -> None:
    expected = tuple(
        (name, convert_dimension_to_inches(value=value, source_units=source_units))
        for name, value in source_dimensions
    )
    expected_by_name = dict(expected)
    canonical_by_name = dict(canonical_dimensions)
    if expected_by_name.keys() != canonical_by_name.keys() or any(
        not math.isclose(canonical_by_name[name], expected_value)
        for name, expected_value in expected_by_name.items()
    ):
        raise ModelGeometryCatalogError(
            "ModelGeometrySourceEvidence canonical_dimensions must match source "
            "dimensions converted to canonical units."
        )


def _validate_identifier_tuple(field_name: str, values: tuple[str, ...]) -> tuple[str, ...]:
    if type(values) is not tuple:
        raise ModelGeometryCatalogError(f"{field_name} must be a tuple.")
    seen: set[str] = set()
    validated: list[str] = []
    for value in values:
        identifier = _validate_identifier(f"{field_name} value", value)
        if identifier in seen:
            raise ModelGeometryCatalogError(f"{field_name} must not contain duplicates.")
        seen.add(identifier)
        validated.append(identifier)
    return tuple(sorted(validated))


def _validate_positive_number(field_name: str, value: object) -> float:
    number = _validate_finite_number(field_name, value)
    if number <= 0.0:
        raise ModelGeometryCatalogError(f"{field_name} must be greater than 0.")
    return number


def _validate_non_negative_number(field_name: str, value: object) -> float:
    number = _validate_finite_number(field_name, value)
    if number < 0.0:
        raise ModelGeometryCatalogError(f"{field_name} must not be negative.")
    return number


def _validate_finite_number(field_name: str, value: object) -> float:
    if not isinstance(value, int | float) or type(value) is bool:
        raise ModelGeometryCatalogError(f"{field_name} must be a number.")
    number = float(value)
    if not math.isfinite(number):
        raise ModelGeometryCatalogError(f"{field_name} must be finite.")
    return number


_validate_identifier = IdentifierValidator(ModelGeometryCatalogError)
