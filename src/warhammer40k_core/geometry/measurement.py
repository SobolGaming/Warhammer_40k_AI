from __future__ import annotations

import math
from dataclasses import dataclass
from enum import StrEnum
from typing import NotRequired, Self, TypedDict, cast

from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.geometry import shapely_backend
from warhammer40k_core.geometry.base import (
    BaseShape,
    BaseShapePayload,
    CircularBase,
    base_distance,
    base_shape_from_payload,
    bases_overlap,
    validate_base_shape,
)
from warhammer40k_core.geometry.pose import (
    GeometryError,
    Pose,
    PosePayload,
    contact_planes_coincide,
    validate_finite_number,
    validate_pose,
)
from warhammer40k_core.geometry.volume import Model, ModelPayload

MILLIMETERS_PER_INCH = 25.4
OBJECTIVE_MARKER_DIAMETER_INCHES = 40.0 / MILLIMETERS_PER_INCH
OBJECTIVE_CONTROL_HORIZONTAL_INCHES = 3.0
OBJECTIVE_CONTROL_VERTICAL_INCHES = 5.0


class DistanceComparison(StrEnum):
    WITHIN = "within"
    MORE_THAN = "more_than"
    AT_LEAST = "at_least"
    AT_MOST = "at_most"
    EXACTLY = "exactly"


class DistanceMeasurementContextPayload(TypedDict):
    source_id: str
    source_pose: PosePayload
    source_base: BaseShapePayload | None
    source_contact_radius_inches: float | None
    source_height_inches: float
    source_subjects: NotRequired[list[ModelPayload]]
    target_id: str
    target_pose: PosePayload
    target_base: BaseShapePayload | None
    target_contact_radius_inches: float | None
    target_height_inches: float
    target_subjects: NotRequired[list[ModelPayload]]


class DistancePredicatePayload(TypedDict):
    predicate_type: str
    comparison: str | None
    distance_inches: float


@dataclass(frozen=True, slots=True)
class DistanceMeasurementContext:
    source_id: str
    source_pose: Pose
    source_base: BaseShape | None
    source_contact_radius_inches: float | None
    source_height_inches: float
    target_id: str
    target_pose: Pose
    target_base: BaseShape | None
    target_contact_radius_inches: float | None
    target_height_inches: float
    source_subjects: tuple[Model, ...] = ()
    target_subjects: tuple[Model, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "source_id", _validate_identifier("source_id", self.source_id))
        object.__setattr__(self, "source_pose", validate_pose("source_pose", self.source_pose))
        object.__setattr__(
            self,
            "source_base",
            _validate_optional_base_shape("source_base", self.source_base),
        )
        object.__setattr__(
            self,
            "source_contact_radius_inches",
            _validate_contact_radius(
                "source_contact_radius_inches",
                self.source_base,
                self.source_contact_radius_inches,
            ),
        )
        object.__setattr__(
            self,
            "source_height_inches",
            _validate_non_negative_inches("source_height_inches", self.source_height_inches),
        )
        object.__setattr__(self, "target_id", _validate_identifier("target_id", self.target_id))
        object.__setattr__(self, "target_pose", validate_pose("target_pose", self.target_pose))
        object.__setattr__(
            self,
            "target_base",
            _validate_optional_base_shape("target_base", self.target_base),
        )
        object.__setattr__(
            self,
            "target_contact_radius_inches",
            _validate_contact_radius(
                "target_contact_radius_inches",
                self.target_base,
                self.target_contact_radius_inches,
            ),
        )
        object.__setattr__(
            self,
            "target_height_inches",
            _validate_non_negative_inches("target_height_inches", self.target_height_inches),
        )
        object.__setattr__(
            self,
            "source_subjects",
            _validate_measurement_subjects("source_subjects", self.source_subjects),
        )
        object.__setattr__(
            self,
            "target_subjects",
            _validate_measurement_subjects("target_subjects", self.target_subjects),
        )

    @classmethod
    def from_models(cls, source: Model, target: Model) -> Self:
        source_model = _validate_model("source", source)
        target_model = _validate_model("target", target)
        return cls(
            source_id=source_model.model_id,
            source_pose=source_model.pose,
            source_base=source_model.base,
            source_contact_radius_inches=None,
            source_height_inches=source_model.volume.height,
            target_id=target_model.model_id,
            target_pose=target_model.pose,
            target_base=target_model.base,
            target_contact_radius_inches=None,
            target_height_inches=target_model.volume.height,
            source_subjects=_measurement_subjects(source_model),
            target_subjects=_measurement_subjects(target_model),
        )

    @classmethod
    def from_baseless_source_to_model(
        cls,
        *,
        source_id: str,
        source_pose: Pose,
        source_contact_radius_inches: float,
        source_height_inches: float,
        target: Model,
    ) -> Self:
        target_model = _validate_model("target", target)
        return cls(
            source_id=source_id,
            source_pose=source_pose,
            source_base=None,
            source_contact_radius_inches=source_contact_radius_inches,
            source_height_inches=source_height_inches,
            target_id=target_model.model_id,
            target_pose=target_model.pose,
            target_base=target_model.base,
            target_contact_radius_inches=None,
            target_height_inches=target_model.volume.height,
            target_subjects=_measurement_subjects(target_model),
        )

    @classmethod
    def from_objective_marker_to_model(
        cls,
        *,
        marker_id: str,
        marker_pose: Pose,
        model: Model,
        marker_diameter_inches: float = OBJECTIVE_MARKER_DIAMETER_INCHES,
    ) -> Self:
        target_model = _validate_model("model", model)
        diameter = _validate_positive_inches("marker_diameter_inches", marker_diameter_inches)
        return cls(
            source_id=marker_id,
            source_pose=marker_pose,
            source_base=CircularBase(radius=diameter / 2.0),
            source_contact_radius_inches=None,
            source_height_inches=0.0,
            target_id=target_model.model_id,
            target_pose=target_model.pose,
            target_base=target_model.base,
            target_contact_radius_inches=None,
            target_height_inches=target_model.volume.height,
            target_subjects=_measurement_subjects(target_model),
        )

    def horizontal_distance_inches(self) -> float:
        if not self._measures_parts():
            return base_distance(
                self._source_footprint(),
                self.source_pose,
                self._target_footprint(),
                self.target_pose,
            )
        return min(pair[0] for pair in self._part_separations())

    def vertical_gap_inches(self) -> float:
        if not self._measures_parts():
            return _vertical_gap(
                self.source_pose.position.z,
                self.source_pose.position.z + self.source_height_inches,
                self.target_pose.position.z,
                self.target_pose.position.z + self.target_height_inches,
            )
        return min(pair[1] for pair in self._part_separations())

    def closest_distance_inches(self) -> float:
        if not self._measures_parts():
            return math.hypot(self.horizontal_distance_inches(), self.vertical_gap_inches())
        return min(
            math.hypot(horizontal, vertical) for horizontal, vertical in self._part_separations()
        )

    def within_axis_limits(self, horizontal_inches: float, vertical_inches: float) -> bool:
        horizontal_limit = _validate_non_negative_inches("horizontal_inches", horizontal_inches)
        vertical_limit = _validate_non_negative_inches("vertical_inches", vertical_inches)
        if not self._measures_parts():
            return (
                self.horizontal_distance_inches() <= horizontal_limit
                and self.vertical_gap_inches() <= vertical_limit
            )
        return any(
            horizontal <= horizontal_limit and vertical <= vertical_limit
            for horizontal, vertical in self._part_separations()
        )

    def footprints_overlap(self) -> bool:
        if not self._measures_parts():
            return bases_overlap(
                self._source_footprint(),
                self.source_pose,
                self._target_footprint(),
                self.target_pose,
            )
        return any(
            bases_overlap(source_base, source_pose, target_base, target_pose)
            for (
                source_base,
                source_pose,
                _source_height,
                target_base,
                target_pose,
                _target_height,
            ) in self._part_footprints()
        )

    def contact_plane_footprints_overlap(self) -> bool:
        if not self._measures_parts():
            return self.footprints_overlap() and contact_planes_coincide(
                self.target_pose.position.z,
                self.source_pose.position.z,
            )
        return any(
            bases_overlap(source_base, source_pose, target_base, target_pose)
            and contact_planes_coincide(target_pose.position.z, source_pose.position.z)
            for (
                source_base,
                source_pose,
                _source_height,
                target_base,
                target_pose,
                _target_height,
            ) in self._part_footprints()
        )

    def target_wholly_within_distance(
        self,
        distance_inches: float,
        *,
        horizontal_only: bool = False,
    ) -> bool:
        distance = _validate_positive_inches("distance_inches", distance_inches)
        if not self._measures_parts():
            vertical_gap = 0.0 if horizontal_only else self.vertical_gap_inches()
            if vertical_gap > distance:
                return False
            horizontal_allowance = math.sqrt((distance * distance) - (vertical_gap * vertical_gap))
            source_area = shapely_backend.footprint_for_base(
                self._source_footprint(),
                self.source_pose,
            ).buffer(horizontal_allowance)
            target_area = shapely_backend.footprint_for_base(
                self._target_footprint(),
                self.target_pose,
            )
            return source_area.covers(target_area)
        sources = self._source_measurements()
        return all(
            _buffered_sources_cover_target(
                sources=sources,
                target=target,
                distance_inches=distance,
                horizontal_only=horizontal_only,
            )
            for target in self._target_measurements()
        )

    def _measures_parts(self) -> bool:
        return bool(self.source_subjects or self.target_subjects)

    def _source_measurements(self) -> tuple[_MeasurementPart, ...]:
        if self.source_subjects:
            return tuple(_part_from_model(subject) for subject in self.source_subjects)
        return (
            _MeasurementPart(
                self._source_footprint(),
                self.source_pose,
                self.source_pose.position.z,
                self.source_pose.position.z + self.source_height_inches,
            ),
        )

    def _target_measurements(self) -> tuple[_MeasurementPart, ...]:
        if self.target_subjects:
            return tuple(_part_from_model(subject) for subject in self.target_subjects)
        return (
            _MeasurementPart(
                self._target_footprint(),
                self.target_pose,
                self.target_pose.position.z,
                self.target_pose.position.z + self.target_height_inches,
            ),
        )

    def _part_separations(self) -> tuple[tuple[float, float], ...]:
        return tuple(
            (
                base_distance(source.base, source.pose, target.base, target.pose),
                _vertical_gap(source.bottom, source.top, target.bottom, target.top),
            )
            for source in self._source_measurements()
            for target in self._target_measurements()
        )

    def _part_footprints(
        self,
    ) -> tuple[tuple[BaseShape, Pose, float, BaseShape, Pose, float], ...]:
        return tuple(
            (
                source.base,
                source.pose,
                source.top - source.bottom,
                target.base,
                target.pose,
                target.top - target.bottom,
            )
            for source in self._source_measurements()
            for target in self._target_measurements()
        )

    def to_payload(self) -> DistanceMeasurementContextPayload:
        payload: DistanceMeasurementContextPayload = {
            "source_id": self.source_id,
            "source_pose": self.source_pose.to_payload(),
            "source_base": None if self.source_base is None else self.source_base.to_payload(),
            "source_contact_radius_inches": self.source_contact_radius_inches,
            "source_height_inches": self.source_height_inches,
            "target_id": self.target_id,
            "target_pose": self.target_pose.to_payload(),
            "target_base": None if self.target_base is None else self.target_base.to_payload(),
            "target_contact_radius_inches": self.target_contact_radius_inches,
            "target_height_inches": self.target_height_inches,
        }
        if self.source_subjects:
            payload["source_subjects"] = [subject.to_payload() for subject in self.source_subjects]
        if self.target_subjects:
            payload["target_subjects"] = [subject.to_payload() for subject in self.target_subjects]
        return payload

    @classmethod
    def from_payload(cls, payload: DistanceMeasurementContextPayload) -> Self:
        source_base_payload = payload["source_base"]
        target_base_payload = payload["target_base"]
        source_subjects = payload.get("source_subjects")
        target_subjects = payload.get("target_subjects")
        return cls(
            source_id=payload["source_id"],
            source_pose=Pose.from_payload(payload["source_pose"]),
            source_base=None
            if source_base_payload is None
            else base_shape_from_payload(source_base_payload),
            source_contact_radius_inches=payload["source_contact_radius_inches"],
            source_height_inches=payload["source_height_inches"],
            target_id=payload["target_id"],
            target_pose=Pose.from_payload(payload["target_pose"]),
            target_base=None
            if target_base_payload is None
            else base_shape_from_payload(target_base_payload),
            target_contact_radius_inches=payload["target_contact_radius_inches"],
            target_height_inches=payload["target_height_inches"],
            source_subjects=()
            if source_subjects is None
            else tuple(Model.from_payload(subject) for subject in source_subjects),
            target_subjects=()
            if target_subjects is None
            else tuple(Model.from_payload(subject) for subject in target_subjects),
        )

    def _source_footprint(self) -> BaseShape:
        return _contact_footprint(self.source_base, self.source_contact_radius_inches)

    def _target_footprint(self) -> BaseShape:
        return _contact_footprint(self.target_base, self.target_contact_radius_inches)


@dataclass(frozen=True, slots=True)
class WithinPredicate:
    distance_inches: float

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "distance_inches",
            _validate_positive_inches("WithinPredicate distance_inches", self.distance_inches),
        )

    def to_payload(self) -> DistancePredicatePayload:
        return {
            "predicate_type": "within",
            "comparison": None,
            "distance_inches": self.distance_inches,
        }

    @classmethod
    def from_payload(cls, payload: DistancePredicatePayload) -> Self:
        _validate_predicate_payload_type(payload, "within")
        if payload["comparison"] is not None:
            raise GeometryError("WithinPredicate payload comparison must be null.")
        return cls(distance_inches=payload["distance_inches"])


@dataclass(frozen=True, slots=True)
class WhollyWithinPredicate:
    distance_inches: float

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "distance_inches",
            _validate_positive_inches(
                "WhollyWithinPredicate distance_inches",
                self.distance_inches,
            ),
        )

    def to_payload(self) -> DistancePredicatePayload:
        return {
            "predicate_type": "wholly_within",
            "comparison": None,
            "distance_inches": self.distance_inches,
        }

    @classmethod
    def from_payload(cls, payload: DistancePredicatePayload) -> Self:
        _validate_predicate_payload_type(payload, "wholly_within")
        if payload["comparison"] is not None:
            raise GeometryError("WhollyWithinPredicate payload comparison must be null.")
        return cls(distance_inches=payload["distance_inches"])


@dataclass(frozen=True, slots=True)
class HorizontalDistancePredicate:
    distance_inches: float
    comparison: DistanceComparison = DistanceComparison.WITHIN

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "distance_inches",
            _validate_positive_inches(
                "HorizontalDistancePredicate distance_inches",
                self.distance_inches,
            ),
        )
        object.__setattr__(
            self,
            "comparison",
            distance_comparison_from_token(self.comparison),
        )

    def to_payload(self) -> DistancePredicatePayload:
        return {
            "predicate_type": "horizontal",
            "comparison": self.comparison.value,
            "distance_inches": self.distance_inches,
        }

    @classmethod
    def from_payload(cls, payload: DistancePredicatePayload) -> Self:
        _validate_predicate_payload_type(payload, "horizontal")
        comparison = payload["comparison"]
        if comparison is None:
            raise GeometryError("HorizontalDistancePredicate payload comparison is required.")
        return cls(
            distance_inches=payload["distance_inches"],
            comparison=distance_comparison_from_token(comparison),
        )


type DistancePredicate = WithinPredicate | WhollyWithinPredicate | HorizontalDistancePredicate


@dataclass(frozen=True, slots=True)
class DistancePredicateEvaluator:
    context: DistanceMeasurementContext

    def __post_init__(self) -> None:
        if type(self.context) is not DistanceMeasurementContext:
            raise GeometryError(
                "DistancePredicateEvaluator context must be a DistanceMeasurementContext."
            )

    def evaluate(self, predicate: DistancePredicate) -> bool:
        if type(predicate) is WithinPredicate:
            return self.context.closest_distance_inches() <= predicate.distance_inches
        if type(predicate) is WhollyWithinPredicate:
            return self.context.target_wholly_within_distance(predicate.distance_inches)
        if type(predicate) is HorizontalDistancePredicate:
            return _compare_distance(
                self.context.horizontal_distance_inches(),
                predicate.comparison,
                predicate.distance_inches,
            )
        raise GeometryError("Unsupported distance predicate.")

    def more_than(self, distance_inches: float) -> bool:
        distance = _validate_positive_inches("distance_inches", distance_inches)
        return self.context.closest_distance_inches() > distance


def distance_comparison_from_token(token: object) -> DistanceComparison:
    if type(token) is DistanceComparison:
        return token
    if type(token) is not str:
        raise GeometryError("DistanceComparison token must be a string.")
    try:
        return DistanceComparison(token)
    except ValueError as exc:
        raise GeometryError(f"Unsupported DistanceComparison token: {token}.") from exc


def distance_predicate_from_payload(payload: DistancePredicatePayload) -> DistancePredicate:
    predicate_type = payload["predicate_type"]
    if predicate_type == "within":
        return WithinPredicate.from_payload(payload)
    if predicate_type == "wholly_within":
        return WhollyWithinPredicate.from_payload(payload)
    if predicate_type == "horizontal":
        return HorizontalDistancePredicate.from_payload(payload)
    raise GeometryError(f"Unsupported distance predicate payload type: {predicate_type}.")


def objective_marker_controls_model(
    marker_pose: Pose,
    model: Model,
    *,
    marker_id: str = "objective-marker",
    horizontal_inches: float = OBJECTIVE_CONTROL_HORIZONTAL_INCHES,
    vertical_inches: float = OBJECTIVE_CONTROL_VERTICAL_INCHES,
    marker_diameter_inches: float = OBJECTIVE_MARKER_DIAMETER_INCHES,
) -> bool:
    context = DistanceMeasurementContext.from_objective_marker_to_model(
        marker_id=marker_id,
        marker_pose=marker_pose,
        model=model,
        marker_diameter_inches=marker_diameter_inches,
    )
    horizontal_limit = _validate_non_negative_inches("horizontal_inches", horizontal_inches)
    vertical_limit = _validate_non_negative_inches("vertical_inches", vertical_inches)
    return context.within_axis_limits(horizontal_limit, vertical_limit)


def objective_marker_endpoint_is_clear(
    marker_pose: Pose,
    model: Model,
    *,
    marker_id: str = "objective-marker",
    marker_diameter_inches: float = OBJECTIVE_MARKER_DIAMETER_INCHES,
) -> bool:
    context = DistanceMeasurementContext.from_objective_marker_to_model(
        marker_id=marker_id,
        marker_pose=marker_pose,
        model=model,
        marker_diameter_inches=marker_diameter_inches,
    )
    return not context.contact_plane_footprints_overlap()


def millimeters_to_inches(value_mm: object) -> float:
    millimeters = validate_finite_number("millimeters", value_mm)
    if millimeters <= 0.0:
        raise GeometryError("millimeters must be greater than 0.")
    return millimeters / MILLIMETERS_PER_INCH


_validate_identifier = IdentifierValidator(GeometryError)


def _validate_optional_base_shape(field_name: str, value: object | None) -> BaseShape | None:
    if value is None:
        return None
    return validate_base_shape(field_name, value)


def _validate_contact_radius(
    field_name: str,
    base: BaseShape | None,
    value: object | None,
) -> float | None:
    if base is not None:
        if value is not None:
            raise GeometryError(f"{field_name} must be null when a base is supplied.")
        return None
    if value is None:
        raise GeometryError(f"{field_name} is required for baseless measurement.")
    return _validate_positive_inches(field_name, value)


def _validate_positive_inches(field_name: str, value: object) -> float:
    inches = validate_finite_number(field_name, value)
    if inches <= 0.0:
        raise GeometryError(f"{field_name} must be greater than 0.")
    return inches


def _validate_non_negative_inches(field_name: str, value: object) -> float:
    inches = validate_finite_number(field_name, value)
    if inches < 0.0:
        raise GeometryError(f"{field_name} must not be negative.")
    return inches


@dataclass(frozen=True, slots=True)
class _MeasurementPart:
    base: BaseShape
    pose: Pose
    bottom: float
    top: float


def _measurement_subjects(model: Model) -> tuple[Model, ...]:
    if not model.measures_every_part or not model.body_parts:
        return ()
    return model.rules_distance_subjects()


def _part_from_model(model: Model) -> _MeasurementPart:
    bottom = model.pose.position.z
    return _MeasurementPart(model.base, model.pose, bottom, bottom + model.volume.height)


def _buffered_sources_cover_target(
    *,
    sources: tuple[_MeasurementPart, ...],
    target: _MeasurementPart,
    distance_inches: float,
    horizontal_only: bool,
) -> bool:
    covered = None
    for source in sources:
        vertical_gap = (
            0.0
            if horizontal_only
            else _vertical_gap(source.bottom, source.top, target.bottom, target.top)
        )
        if vertical_gap > distance_inches:
            continue
        allowance = math.sqrt((distance_inches * distance_inches) - (vertical_gap * vertical_gap))
        area = shapely_backend.footprint_for_base(source.base, source.pose).buffer(allowance)
        covered = area if covered is None else covered.union(area)
    if covered is None:
        return False
    return covered.covers(shapely_backend.footprint_for_base(target.base, target.pose))


def _validate_measurement_subjects(field_name: str, value: object) -> tuple[Model, ...]:
    if type(value) is not tuple:
        raise GeometryError(f"{field_name} must be a tuple.")
    subjects: list[Model] = []
    for subject in cast(tuple[object, ...], value):
        if type(subject) is not Model:
            raise GeometryError(f"{field_name} must contain Model values.")
        if subject.measures_every_part:
            raise GeometryError(f"{field_name} must contain individual measurement parts.")
        subjects.append(subject)
    return tuple(subjects)


def _validate_model(field_name: str, value: object) -> Model:
    if type(value) is not Model:
        raise GeometryError(f"{field_name} must be a Model.")
    return value


def _contact_footprint(base: BaseShape | None, contact_radius_inches: float | None) -> BaseShape:
    if base is not None:
        return base
    if contact_radius_inches is None:
        raise GeometryError("Baseless measurement requires a contact radius.")
    return CircularBase(radius=contact_radius_inches)


def _vertical_gap(
    first_bottom: float,
    first_top: float,
    second_bottom: float,
    second_top: float,
) -> float:
    if first_top < second_bottom:
        return second_bottom - first_top
    if second_top < first_bottom:
        return first_bottom - second_top
    return 0.0


def _compare_distance(
    actual_inches: float,
    comparison: DistanceComparison,
    expected_inches: float,
) -> bool:
    if comparison is DistanceComparison.WITHIN or comparison is DistanceComparison.AT_MOST:
        return actual_inches <= expected_inches
    if comparison is DistanceComparison.MORE_THAN:
        return actual_inches > expected_inches
    if comparison is DistanceComparison.AT_LEAST:
        return actual_inches >= expected_inches
    if comparison is DistanceComparison.EXACTLY:
        return math.isclose(actual_inches, expected_inches, rel_tol=0.0, abs_tol=1e-9)
    raise GeometryError("Unsupported distance comparison.")


def _validate_predicate_payload_type(
    payload: DistancePredicatePayload,
    expected_type: str,
) -> None:
    if payload["predicate_type"] != expected_type:
        raise GeometryError("Distance predicate payload type does not match class.")
