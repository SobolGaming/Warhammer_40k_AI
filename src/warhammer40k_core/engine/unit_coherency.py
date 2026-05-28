from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Self, TypedDict, cast

from warhammer40k_core.core.ruleset_descriptor import (
    CoherencyPolicyDescriptor,
    CoherencyPolicyDescriptorPayload,
    CoherencyPolicyKind,
    RulesetDescriptor,
    coherency_policy_kind_from_token,
)
from warhammer40k_core.engine.battlefield_state import (
    BattlefieldScenario,
    ModelDisplacementKind,
    PlacementError,
    UnitPlacement,
    UnitPlacementPayload,
    geometry_model_for_placement,
    model_displacement_kind_from_token,
)
from warhammer40k_core.geometry.volume import Model


class UnitCoherencyError(ValueError):
    """Raised when unit coherency validation inputs violate CORE V2 invariants."""


class UnitCoherencyStatus(StrEnum):
    COHERENT = "coherent"
    BROKEN = "broken"


class UnitCoherencyViolationPayload(TypedDict):
    model_instance_id: str
    violation_code: str
    neighbor_count: int | None
    required_neighbor_count: int | None
    max_horizontal_inches: float | None
    max_vertical_inches: float | None
    max_all_models_distance_inches: float | None
    related_model_instance_ids: list[str]


class UnitCoherencyContextPayload(TypedDict):
    ruleset_descriptor_hash: str
    unit_instance_id: str
    coherency_policy: CoherencyPolicyDescriptorPayload


class UnitCoherencyResultPayload(TypedDict):
    status: str
    ruleset_descriptor_hash: str
    unit_instance_id: str
    coherency_policy: CoherencyPolicyDescriptorPayload
    model_instance_ids: list[str]
    offending_model_instance_ids: list[str]
    violations: list[UnitCoherencyViolationPayload]


class MovementRollbackRecordPayload(TypedDict):
    unit_instance_id: str
    displacement_kind: str
    before_placement: UnitPlacementPayload
    attempted_placement: UnitPlacementPayload
    coherency_result: UnitCoherencyResultPayload


@dataclass(frozen=True, slots=True)
class UnitCoherencyViolation:
    model_instance_id: str
    violation_code: str
    neighbor_count: int | None = None
    required_neighbor_count: int | None = None
    max_horizontal_inches: float | None = None
    max_vertical_inches: float | None = None
    max_all_models_distance_inches: float | None = None
    related_model_instance_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "model_instance_id",
            _validate_identifier(
                "UnitCoherencyViolation model_instance_id",
                self.model_instance_id,
            ),
        )
        object.__setattr__(
            self,
            "violation_code",
            _validate_identifier("UnitCoherencyViolation violation_code", self.violation_code),
        )
        object.__setattr__(
            self,
            "neighbor_count",
            _validate_optional_non_negative_int(
                "UnitCoherencyViolation neighbor_count",
                self.neighbor_count,
            ),
        )
        object.__setattr__(
            self,
            "required_neighbor_count",
            _validate_optional_positive_int(
                "UnitCoherencyViolation required_neighbor_count",
                self.required_neighbor_count,
            ),
        )
        object.__setattr__(
            self,
            "max_horizontal_inches",
            _validate_optional_positive_number(
                "UnitCoherencyViolation max_horizontal_inches",
                self.max_horizontal_inches,
            ),
        )
        object.__setattr__(
            self,
            "max_vertical_inches",
            _validate_optional_positive_number(
                "UnitCoherencyViolation max_vertical_inches",
                self.max_vertical_inches,
            ),
        )
        object.__setattr__(
            self,
            "max_all_models_distance_inches",
            _validate_optional_positive_number(
                "UnitCoherencyViolation max_all_models_distance_inches",
                self.max_all_models_distance_inches,
            ),
        )
        object.__setattr__(
            self,
            "related_model_instance_ids",
            _validate_identifier_tuple(
                "UnitCoherencyViolation related_model_instance_ids",
                self.related_model_instance_ids,
            ),
        )

    def to_payload(self) -> UnitCoherencyViolationPayload:
        return {
            "model_instance_id": self.model_instance_id,
            "violation_code": self.violation_code,
            "neighbor_count": self.neighbor_count,
            "required_neighbor_count": self.required_neighbor_count,
            "max_horizontal_inches": self.max_horizontal_inches,
            "max_vertical_inches": self.max_vertical_inches,
            "max_all_models_distance_inches": self.max_all_models_distance_inches,
            "related_model_instance_ids": list(self.related_model_instance_ids),
        }

    @classmethod
    def from_payload(cls, payload: UnitCoherencyViolationPayload) -> Self:
        return cls(
            model_instance_id=payload["model_instance_id"],
            violation_code=payload["violation_code"],
            neighbor_count=payload["neighbor_count"],
            required_neighbor_count=payload["required_neighbor_count"],
            max_horizontal_inches=payload["max_horizontal_inches"],
            max_vertical_inches=payload["max_vertical_inches"],
            max_all_models_distance_inches=payload["max_all_models_distance_inches"],
            related_model_instance_ids=tuple(payload["related_model_instance_ids"]),
        )


@dataclass(frozen=True, slots=True)
class UnitCoherencyResult:
    status: UnitCoherencyStatus
    ruleset_descriptor_hash: str
    unit_instance_id: str
    coherency_policy: CoherencyPolicyDescriptor
    model_instance_ids: tuple[str, ...]
    violations: tuple[UnitCoherencyViolation, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "status", unit_coherency_status_from_token(self.status))
        object.__setattr__(
            self,
            "ruleset_descriptor_hash",
            _validate_identifier(
                "UnitCoherencyResult ruleset_descriptor_hash",
                self.ruleset_descriptor_hash,
            ),
        )
        object.__setattr__(
            self,
            "unit_instance_id",
            _validate_identifier("UnitCoherencyResult unit_instance_id", self.unit_instance_id),
        )
        if type(self.coherency_policy) is not CoherencyPolicyDescriptor:
            raise UnitCoherencyError(
                "UnitCoherencyResult coherency_policy must be a CoherencyPolicyDescriptor."
            )
        object.__setattr__(
            self,
            "model_instance_ids",
            _validate_identifier_tuple(
                "UnitCoherencyResult model_instance_ids",
                self.model_instance_ids,
            ),
        )
        violations = _validate_violation_tuple(
            "UnitCoherencyResult violations",
            self.violations,
        )
        model_ids = set(self.model_instance_ids)
        for violation in violations:
            if violation.model_instance_id not in model_ids:
                raise UnitCoherencyError(
                    "UnitCoherencyResult violation model_instance_id must be in model_instance_ids."
                )
        if self.status is UnitCoherencyStatus.COHERENT and violations:
            raise UnitCoherencyError("Coherent UnitCoherencyResult must not include violations.")
        if self.status is UnitCoherencyStatus.BROKEN and not violations:
            raise UnitCoherencyError("Broken UnitCoherencyResult requires violations.")
        object.__setattr__(self, "violations", violations)

    @property
    def is_coherent(self) -> bool:
        return self.status is UnitCoherencyStatus.COHERENT

    @property
    def offending_model_instance_ids(self) -> tuple[str, ...]:
        return tuple(sorted({violation.model_instance_id for violation in self.violations}))

    def to_payload(self) -> UnitCoherencyResultPayload:
        return {
            "status": self.status.value,
            "ruleset_descriptor_hash": self.ruleset_descriptor_hash,
            "unit_instance_id": self.unit_instance_id,
            "coherency_policy": self.coherency_policy.to_payload(),
            "model_instance_ids": list(self.model_instance_ids),
            "offending_model_instance_ids": list(self.offending_model_instance_ids),
            "violations": [violation.to_payload() for violation in self.violations],
        }

    @classmethod
    def from_payload(cls, payload: UnitCoherencyResultPayload) -> Self:
        result = cls(
            status=unit_coherency_status_from_token(payload["status"]),
            ruleset_descriptor_hash=payload["ruleset_descriptor_hash"],
            unit_instance_id=payload["unit_instance_id"],
            coherency_policy=CoherencyPolicyDescriptor.from_payload(payload["coherency_policy"]),
            model_instance_ids=tuple(payload["model_instance_ids"]),
            violations=tuple(
                UnitCoherencyViolation.from_payload(violation)
                for violation in payload["violations"]
            ),
        )
        if tuple(payload["offending_model_instance_ids"]) != result.offending_model_instance_ids:
            raise UnitCoherencyError(
                "UnitCoherencyResult offending_model_instance_ids do not match violations."
            )
        return result


@dataclass(frozen=True, slots=True)
class UnitCoherencyContext:
    ruleset_descriptor_hash: str
    unit_instance_id: str
    coherency_policy: CoherencyPolicyDescriptor

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "ruleset_descriptor_hash",
            _validate_identifier(
                "UnitCoherencyContext ruleset_descriptor_hash",
                self.ruleset_descriptor_hash,
            ),
        )
        object.__setattr__(
            self,
            "unit_instance_id",
            _validate_identifier("UnitCoherencyContext unit_instance_id", self.unit_instance_id),
        )
        if type(self.coherency_policy) is not CoherencyPolicyDescriptor:
            raise UnitCoherencyError(
                "UnitCoherencyContext coherency_policy must be a CoherencyPolicyDescriptor."
            )

    @classmethod
    def from_ruleset_descriptor(
        cls,
        ruleset_descriptor: RulesetDescriptor,
        *,
        unit_instance_id: str,
    ) -> Self:
        if type(ruleset_descriptor) is not RulesetDescriptor:
            raise UnitCoherencyError("UnitCoherencyContext requires an explicit RulesetDescriptor.")
        return cls(
            ruleset_descriptor_hash=ruleset_descriptor.descriptor_hash,
            unit_instance_id=unit_instance_id,
            coherency_policy=ruleset_descriptor.coherency_policy,
        )

    def validate_models(self, models: tuple[Model, ...]) -> UnitCoherencyResult:
        validated_models = _validate_model_tuple("UnitCoherencyContext models", models)
        if len(validated_models) <= 1:
            return self._result(models=validated_models, violations=())
        policy_kind = coherency_policy_kind_from_token(self.coherency_policy.policy_kind)
        if policy_kind is CoherencyPolicyKind.NEIGHBOR_COUNT:
            return self._validate_neighbor_count_policy(validated_models)
        if policy_kind is CoherencyPolicyKind.ALL_MODELS_WITHIN_DISTANCE:
            return self._validate_all_models_within_distance_policy(validated_models)
        raise UnitCoherencyError(f"Unsupported coherency policy kind: {policy_kind.value}.")

    def _validate_neighbor_count_policy(
        self,
        models: tuple[Model, ...],
    ) -> UnitCoherencyResult:
        required_neighbors = _required_neighbor_count(
            policy=self.coherency_policy,
            model_count=len(models),
        )
        max_horizontal = _required_policy_number(
            self.coherency_policy.max_horizontal_inches,
            "max_horizontal_inches",
        )
        max_vertical = _required_policy_number(
            self.coherency_policy.max_vertical_inches,
            "max_vertical_inches",
        )
        violations: list[UnitCoherencyViolation] = []
        adjacency = _coherency_adjacency(
            models,
            max_horizontal_inches=max_horizontal,
            max_vertical_inches=max_vertical,
        )
        for model in models:
            coherent_neighbors = tuple(sorted(adjacency[model.model_id]))
            if len(coherent_neighbors) >= required_neighbors:
                continue
            violations.append(
                UnitCoherencyViolation(
                    model_instance_id=model.model_id,
                    violation_code="insufficient_coherency_neighbors",
                    neighbor_count=len(coherent_neighbors),
                    required_neighbor_count=required_neighbors,
                    max_horizontal_inches=max_horizontal,
                    max_vertical_inches=max_vertical,
                    related_model_instance_ids=coherent_neighbors,
                )
            )
        violations.extend(
            _single_group_violations(
                adjacency,
                max_horizontal_inches=max_horizontal,
                max_vertical_inches=max_vertical,
            )
        )
        return self._result(models=models, violations=tuple(violations))

    def _validate_all_models_within_distance_policy(
        self,
        models: tuple[Model, ...],
    ) -> UnitCoherencyResult:
        max_distance = _required_policy_number(
            self.coherency_policy.max_all_models_distance_inches,
            "max_all_models_distance_inches",
        )
        violations: list[UnitCoherencyViolation] = []
        for model in models:
            distant_model_ids = tuple(
                other.model_id
                for other in models
                if other.model_id != model.model_id and model.range_to(other) > max_distance
            )
            if not distant_model_ids:
                continue
            violations.append(
                UnitCoherencyViolation(
                    model_instance_id=model.model_id,
                    violation_code="all_models_distance_exceeded",
                    max_all_models_distance_inches=max_distance,
                    related_model_instance_ids=distant_model_ids,
                )
            )
        return self._result(models=models, violations=tuple(violations))

    def _result(
        self,
        *,
        models: tuple[Model, ...],
        violations: tuple[UnitCoherencyViolation, ...],
    ) -> UnitCoherencyResult:
        return UnitCoherencyResult(
            status=(UnitCoherencyStatus.COHERENT if not violations else UnitCoherencyStatus.BROKEN),
            ruleset_descriptor_hash=self.ruleset_descriptor_hash,
            unit_instance_id=self.unit_instance_id,
            coherency_policy=self.coherency_policy,
            model_instance_ids=tuple(model.model_id for model in models),
            violations=violations,
        )

    def to_payload(self) -> UnitCoherencyContextPayload:
        return {
            "ruleset_descriptor_hash": self.ruleset_descriptor_hash,
            "unit_instance_id": self.unit_instance_id,
            "coherency_policy": self.coherency_policy.to_payload(),
        }

    @classmethod
    def from_payload(cls, payload: UnitCoherencyContextPayload) -> Self:
        return cls(
            ruleset_descriptor_hash=payload["ruleset_descriptor_hash"],
            unit_instance_id=payload["unit_instance_id"],
            coherency_policy=CoherencyPolicyDescriptor.from_payload(payload["coherency_policy"]),
        )


@dataclass(frozen=True, slots=True)
class MovementRollbackRecord:
    unit_instance_id: str
    displacement_kind: ModelDisplacementKind
    before_placement: UnitPlacement
    attempted_placement: UnitPlacement
    coherency_result: UnitCoherencyResult

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "unit_instance_id",
            _validate_identifier("MovementRollbackRecord unit_instance_id", self.unit_instance_id),
        )
        object.__setattr__(
            self,
            "displacement_kind",
            model_displacement_kind_from_token(self.displacement_kind),
        )
        if type(self.before_placement) is not UnitPlacement:
            raise UnitCoherencyError(
                "MovementRollbackRecord before_placement must be a UnitPlacement."
            )
        if type(self.attempted_placement) is not UnitPlacement:
            raise UnitCoherencyError(
                "MovementRollbackRecord attempted_placement must be a UnitPlacement."
            )
        if type(self.coherency_result) is not UnitCoherencyResult:
            raise UnitCoherencyError(
                "MovementRollbackRecord coherency_result must be a UnitCoherencyResult."
            )
        if self.coherency_result.is_coherent:
            raise UnitCoherencyError("MovementRollbackRecord coherency_result must be broken.")
        if self.before_placement.unit_instance_id != self.unit_instance_id:
            raise UnitCoherencyError(
                "MovementRollbackRecord before_placement must match unit_instance_id."
            )
        if self.attempted_placement.unit_instance_id != self.unit_instance_id:
            raise UnitCoherencyError(
                "MovementRollbackRecord attempted_placement must match unit_instance_id."
            )
        if self.coherency_result.unit_instance_id != self.unit_instance_id:
            raise UnitCoherencyError(
                "MovementRollbackRecord coherency_result must match unit_instance_id."
            )
        if _model_ids_for_unit_placement(self.before_placement) != _model_ids_for_unit_placement(
            self.attempted_placement
        ):
            raise UnitCoherencyError(
                "MovementRollbackRecord placements must contain the same model_instance_ids."
            )

    def to_payload(self) -> MovementRollbackRecordPayload:
        return {
            "unit_instance_id": self.unit_instance_id,
            "displacement_kind": self.displacement_kind.value,
            "before_placement": self.before_placement.to_payload(),
            "attempted_placement": self.attempted_placement.to_payload(),
            "coherency_result": self.coherency_result.to_payload(),
        }

    @classmethod
    def from_payload(cls, payload: MovementRollbackRecordPayload) -> Self:
        return cls(
            unit_instance_id=payload["unit_instance_id"],
            displacement_kind=model_displacement_kind_from_token(payload["displacement_kind"]),
            before_placement=UnitPlacement.from_payload(payload["before_placement"]),
            attempted_placement=UnitPlacement.from_payload(payload["attempted_placement"]),
            coherency_result=UnitCoherencyResult.from_payload(payload["coherency_result"]),
        )


def unit_placement_coherency_result(
    *,
    scenario: BattlefieldScenario,
    ruleset_descriptor: RulesetDescriptor,
    unit_placement: UnitPlacement,
) -> UnitCoherencyResult:
    if type(scenario) is not BattlefieldScenario:
        raise UnitCoherencyError("unit_placement_coherency_result scenario must be a scenario.")
    if type(ruleset_descriptor) is not RulesetDescriptor:
        raise UnitCoherencyError(
            "unit_placement_coherency_result requires an explicit RulesetDescriptor."
        )
    if type(unit_placement) is not UnitPlacement:
        raise UnitCoherencyError(
            "unit_placement_coherency_result unit_placement must be a UnitPlacement."
        )
    context = UnitCoherencyContext.from_ruleset_descriptor(
        ruleset_descriptor,
        unit_instance_id=unit_placement.unit_instance_id,
    )
    models: list[Model] = []
    for placement in unit_placement.model_placements:
        model_instance = scenario.model_instance_for_placement(placement)
        if model_instance.is_alive:
            models.append(geometry_model_for_placement(model=model_instance, placement=placement))
    return context.validate_models(tuple(models))


def assert_battlefield_units_in_coherency(
    *,
    scenario: BattlefieldScenario,
    ruleset_descriptor: RulesetDescriptor,
) -> None:
    if type(scenario) is not BattlefieldScenario:
        raise UnitCoherencyError(
            "assert_battlefield_units_in_coherency scenario must be a scenario."
        )
    if type(ruleset_descriptor) is not RulesetDescriptor:
        raise UnitCoherencyError(
            "assert_battlefield_units_in_coherency requires an explicit RulesetDescriptor."
        )
    broken_results: list[UnitCoherencyResult] = []
    for placed_army in scenario.battlefield_state.placed_armies:
        for unit_placement in placed_army.unit_placements:
            result = unit_placement_coherency_result(
                scenario=scenario,
                ruleset_descriptor=ruleset_descriptor,
                unit_placement=unit_placement,
            )
            if not result.is_coherent:
                broken_results.append(result)
    if not broken_results:
        return
    offending_model_ids = tuple(
        model_id for result in broken_results for model_id in result.offending_model_instance_ids
    )
    raise PlacementError(
        f"Units must be set up in coherency; offending model IDs: {', '.join(offending_model_ids)}"
    )


def resolve_unit_movement_endpoint_coherency(
    *,
    scenario: BattlefieldScenario,
    ruleset_descriptor: RulesetDescriptor,
    before: UnitPlacement,
    attempted: UnitPlacement,
    displacement_kind: ModelDisplacementKind,
) -> tuple[UnitPlacement, UnitCoherencyResult, MovementRollbackRecord | None]:
    if type(before) is not UnitPlacement:
        raise UnitCoherencyError("Movement coherency before placement must be a UnitPlacement.")
    if type(attempted) is not UnitPlacement:
        raise UnitCoherencyError("Movement coherency attempted placement must be a UnitPlacement.")
    if (
        before.army_id != attempted.army_id
        or before.player_id != attempted.player_id
        or before.unit_instance_id != attempted.unit_instance_id
    ):
        raise UnitCoherencyError("Movement coherency placements must reference the same unit.")
    if _model_ids_for_unit_placement(before) != _model_ids_for_unit_placement(attempted):
        raise UnitCoherencyError(
            "Movement coherency before and attempted placements must contain the same "
            "model_instance_ids."
        )
    displacement = model_displacement_kind_from_token(displacement_kind)
    result = unit_placement_coherency_result(
        scenario=scenario,
        ruleset_descriptor=ruleset_descriptor,
        unit_placement=attempted,
    )
    if result.is_coherent:
        return attempted, result, None
    rollback = MovementRollbackRecord(
        unit_instance_id=before.unit_instance_id,
        displacement_kind=displacement,
        before_placement=before,
        attempted_placement=attempted,
        coherency_result=result,
    )
    return before, result, rollback


def unit_coherency_status_from_token(token: object) -> UnitCoherencyStatus:
    if type(token) is UnitCoherencyStatus:
        return token
    if type(token) is not str:
        raise UnitCoherencyError("UnitCoherencyStatus token must be a string.")
    try:
        return UnitCoherencyStatus(token)
    except ValueError as exc:
        raise UnitCoherencyError(f"Unsupported UnitCoherencyStatus token: {token}.") from exc


def _models_are_neighbor_coherent(
    *,
    first: Model,
    second: Model,
    max_horizontal_inches: float,
    max_vertical_inches: float,
) -> bool:
    return (
        first.base_distance_to(second) <= max_horizontal_inches
        and first.volume.vertical_gap_to(first.pose, second.volume, second.pose)
        <= max_vertical_inches
    )


def _coherency_adjacency(
    models: tuple[Model, ...],
    *,
    max_horizontal_inches: float,
    max_vertical_inches: float,
) -> dict[str, set[str]]:
    adjacency = {model.model_id: set[str]() for model in models}
    for index, first in enumerate(models):
        for second in models[index + 1 :]:
            if _models_are_neighbor_coherent(
                first=first,
                second=second,
                max_horizontal_inches=max_horizontal_inches,
                max_vertical_inches=max_vertical_inches,
            ):
                adjacency[first.model_id].add(second.model_id)
                adjacency[second.model_id].add(first.model_id)
    return adjacency


def _single_group_violations(
    adjacency: dict[str, set[str]],
    *,
    max_horizontal_inches: float,
    max_vertical_inches: float,
) -> tuple[UnitCoherencyViolation, ...]:
    components = _connected_components(adjacency)
    if len(components) <= 1:
        return ()
    retained_component = components[0]
    return tuple(
        UnitCoherencyViolation(
            model_instance_id=model_id,
            violation_code="unit_coherency_not_single_group",
            max_horizontal_inches=max_horizontal_inches,
            max_vertical_inches=max_vertical_inches,
            related_model_instance_ids=component,
        )
        for component in components
        if component != retained_component
        for model_id in component
    )


def _connected_components(adjacency: dict[str, set[str]]) -> tuple[tuple[str, ...], ...]:
    unvisited = set(adjacency)
    components: list[tuple[str, ...]] = []
    while unvisited:
        start = min(unvisited)
        unvisited.remove(start)
        stack = [start]
        component: list[str] = []
        while stack:
            model_id = stack.pop()
            component.append(model_id)
            for neighbor_id in sorted(adjacency[model_id], reverse=True):
                if neighbor_id not in unvisited:
                    continue
                unvisited.remove(neighbor_id)
                stack.append(neighbor_id)
        components.append(tuple(sorted(component)))
    return tuple(sorted(components, key=lambda component: (-len(component), component)))


def _required_neighbor_count(
    *,
    policy: CoherencyPolicyDescriptor,
    model_count: int,
) -> int:
    if model_count <= 1:
        return 0
    threshold = policy.large_unit_model_count_threshold
    if threshold is not None and model_count >= threshold:
        required_large = policy.required_neighbors_large_unit
        if required_large is None:
            raise UnitCoherencyError("Large-unit coherency policy is incomplete.")
        return required_large
    required_small = policy.required_neighbors_small_unit
    if required_small is None:
        raise UnitCoherencyError("Small-unit coherency policy is incomplete.")
    return required_small


def _required_policy_number(value: float | None, field_name: str) -> float:
    if value is None:
        raise UnitCoherencyError(f"Coherency policy requires {field_name}.")
    return value


def _validate_model_tuple(field_name: str, values: object) -> tuple[Model, ...]:
    if type(values) is not tuple:
        raise UnitCoherencyError(f"{field_name} must be a tuple.")
    raw_values = cast(tuple[object, ...], values)
    if not raw_values:
        raise UnitCoherencyError(f"{field_name} must not be empty.")
    models: list[Model] = []
    seen: set[str] = set()
    for value in raw_values:
        if type(value) is not Model:
            raise UnitCoherencyError(f"{field_name} must contain Model values.")
        if value.model_id in seen:
            raise UnitCoherencyError(f"{field_name} must not contain duplicate model_ids.")
        seen.add(value.model_id)
        models.append(value)
    return tuple(sorted(models, key=lambda model: model.model_id))


def _validate_violation_tuple(
    field_name: str,
    values: object,
) -> tuple[UnitCoherencyViolation, ...]:
    if type(values) is not tuple:
        raise UnitCoherencyError(f"{field_name} must be a tuple.")
    violations: list[UnitCoherencyViolation] = []
    seen: set[tuple[str, str]] = set()
    for value in cast(tuple[object, ...], values):
        if type(value) is not UnitCoherencyViolation:
            raise UnitCoherencyError(f"{field_name} must contain UnitCoherencyViolation values.")
        violation_key = (value.model_instance_id, value.violation_code)
        if violation_key in seen:
            raise UnitCoherencyError(f"{field_name} must not contain duplicate violations.")
        seen.add(violation_key)
        violations.append(value)
    return tuple(
        sorted(
            violations,
            key=lambda violation: (
                violation.model_instance_id,
                violation.violation_code,
                violation.related_model_instance_ids,
            ),
        )
    )


def _model_ids_for_unit_placement(unit_placement: UnitPlacement) -> tuple[str, ...]:
    return tuple(placement.model_instance_id for placement in unit_placement.model_placements)


def _validate_identifier_tuple(field_name: str, values: object) -> tuple[str, ...]:
    if type(values) is not tuple:
        raise UnitCoherencyError(f"{field_name} must be a tuple.")
    identifiers: list[str] = []
    seen: set[str] = set()
    for value in cast(tuple[object, ...], values):
        identifier = _validate_identifier(f"{field_name} value", value)
        if identifier in seen:
            raise UnitCoherencyError(f"{field_name} must not contain duplicates.")
        seen.add(identifier)
        identifiers.append(identifier)
    return tuple(sorted(identifiers))


def _validate_identifier(field_name: str, value: object) -> str:
    if type(value) is not str:
        raise UnitCoherencyError(f"{field_name} must be a string.")
    stripped = value.strip()
    if not stripped:
        raise UnitCoherencyError(f"{field_name} must not be empty.")
    return stripped


def _validate_optional_positive_int(field_name: str, value: object | None) -> int | None:
    if value is None:
        return None
    if type(value) is not int:
        raise UnitCoherencyError(f"{field_name} must be an integer.")
    if value < 1:
        raise UnitCoherencyError(f"{field_name} must be at least 1.")
    return value


def _validate_optional_non_negative_int(field_name: str, value: object | None) -> int | None:
    if value is None:
        return None
    if type(value) is not int:
        raise UnitCoherencyError(f"{field_name} must be an integer.")
    if value < 0:
        raise UnitCoherencyError(f"{field_name} must not be negative.")
    return value


def _validate_optional_positive_number(
    field_name: str,
    value: object | None,
) -> float | None:
    if value is None:
        return None
    if not isinstance(value, int | float) or type(value) is bool:
        raise UnitCoherencyError(f"{field_name} must be a number.")
    number = float(value)
    if number <= 0.0:
        raise UnitCoherencyError(f"{field_name} must be greater than 0.")
    return number
