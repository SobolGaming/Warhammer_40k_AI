"""Deterministic workload counters and execution reports for Phase 10U profiling.

`report_id` includes measured elapsed time and identifies one profiler execution. Use
`scenario_hash` and `workload_digest` for deterministic workload comparison across runs.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from hashlib import sha256
from time import perf_counter_ns
from typing import Self, TypedDict, cast

from warhammer40k_core.core.rng import RandomSource
from warhammer40k_core.core.ruleset_descriptor import (
    MovementMode,
    RulesetDescriptor,
    TerrainFeatureKind,
)
from warhammer40k_core.core.terrain_display import TerrainDisplayGeometry
from warhammer40k_core.core.unit import Unit, UnitMember
from warhammer40k_core.core.unit_group import UnitGroup
from warhammer40k_core.engine.movement_legality import MovementLegalityContext
from warhammer40k_core.geometry.base import BaseShape, CircularBase, RectangularBase
from warhammer40k_core.geometry.collision import CollisionSet
from warhammer40k_core.geometry.movement_envelope import MovementEnvelope
from warhammer40k_core.geometry.pathing import (
    PathQuery,
    PathWitness,
    TerrainPathLegalityContext,
)
from warhammer40k_core.geometry.pose import Pose
from warhammer40k_core.geometry.spatial_index import SpatialIndex
from warhammer40k_core.geometry.terrain import (
    TerrainFeatureDefinition,
    TerrainFloorDefinition,
    TerrainVolume,
    TerrainWallDefinition,
)
from warhammer40k_core.geometry.volume import Model, ModelVolume

type BenchmarkTimer = Callable[[], int]

_REPORT_SCHEMA_VERSION = "phase10u-hotspot-report-v2"
_NORMAL_MOVE_TOKEN = "normal_move"


class ProfilingError(ValueError):
    """Raised when profiling inputs or payloads violate CORE V2 invariants."""


class PerformanceScenarioKind(StrEnum):
    CROWDED_INFANTRY = "crowded_infantry"
    VEHICLE_BLOCKERS = "vehicle_blockers"
    RUINS_TERRAIN = "ruins_terrain"
    RESERVE_LIKE_PLACEMENT = "reserve_like_placement"
    FLY_PATHS = "fly_paths"


class PerformanceScenarioPayload(TypedDict):
    scenario_id: str
    scenario_kind: str
    seed: int
    iteration_count: int
    model_count: int
    blocker_count: int
    terrain_feature_count: int
    sample_interval_inches: float


class PathingBenchmarkResultPayload(TypedDict):
    scenario_id: str
    scenario_kind: str
    seed: int
    iteration_count: int
    elapsed_ns: int
    path_validation_runs: int
    terrain_legality_runs: int
    valid_path_count: int
    invalid_path_count: int
    path_sampled_pose_count: int
    model_collision_broadphase_check_count: int
    model_collision_check_count: int
    model_collision_broadphase_rejection_count: int
    terrain_collision_broadphase_check_count: int
    terrain_collision_check_count: int
    terrain_collision_broadphase_rejection_count: int
    engagement_broadphase_check_count: int
    engagement_check_count: int
    engagement_broadphase_rejection_count: int
    terrain_sampled_pose_count: int
    terrain_segment_count: int
    terrain_violation_count: int
    dominant_work_counter: str
    dominant_work_count: int
    scenario_hash: str
    workload_digest: str


class PerformanceBudgetPayload(TypedDict):
    budget_id: str
    max_elapsed_ns: int | None
    max_path_sampled_pose_count: int | None
    max_model_collision_check_count: int | None
    max_terrain_collision_check_count: int | None
    max_engagement_check_count: int | None
    max_terrain_sampled_pose_count: int | None


class HotspotReportPayload(TypedDict):
    schema_version: str
    report_id: str
    results: list[PathingBenchmarkResultPayload]
    budget: PerformanceBudgetPayload | None
    budget_violations: list[str]


@dataclass(frozen=True, slots=True)
class PerformanceScenario:
    scenario_id: str
    scenario_kind: PerformanceScenarioKind
    seed: int
    iteration_count: int
    model_count: int
    blocker_count: int
    terrain_feature_count: int
    sample_interval_inches: float = 0.5

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "scenario_id",
            _validate_identifier("PerformanceScenario scenario_id", self.scenario_id),
        )
        object.__setattr__(
            self,
            "scenario_kind",
            performance_scenario_kind_from_token(self.scenario_kind),
        )
        object.__setattr__(
            self,
            "seed",
            _validate_int("PerformanceScenario seed", self.seed),
        )
        object.__setattr__(
            self,
            "iteration_count",
            _validate_positive_int(
                "PerformanceScenario iteration_count",
                self.iteration_count,
            ),
        )
        object.__setattr__(
            self,
            "model_count",
            _validate_positive_int("PerformanceScenario model_count", self.model_count),
        )
        object.__setattr__(
            self,
            "blocker_count",
            _validate_non_negative_int("PerformanceScenario blocker_count", self.blocker_count),
        )
        object.__setattr__(
            self,
            "terrain_feature_count",
            _validate_non_negative_int(
                "PerformanceScenario terrain_feature_count",
                self.terrain_feature_count,
            ),
        )
        object.__setattr__(
            self,
            "sample_interval_inches",
            _validate_positive_number(
                "PerformanceScenario sample_interval_inches",
                self.sample_interval_inches,
            ),
        )

    @classmethod
    def for_kind(
        cls,
        scenario_kind: PerformanceScenarioKind | str,
        *,
        seed: int,
        iteration_count: int,
        profile_size: str = "smoke",
    ) -> Self:
        kind = performance_scenario_kind_from_token(scenario_kind)
        size = _profile_size_from_token(profile_size)
        scale = 4 if size == "nightly" else 1
        settings = _scenario_settings(kind=kind, scale=scale)
        return cls(
            scenario_id=f"phase10u:{kind.value}:{size}",
            scenario_kind=kind,
            seed=seed,
            iteration_count=iteration_count * scale,
            model_count=settings.model_count,
            blocker_count=settings.blocker_count,
            terrain_feature_count=settings.terrain_feature_count,
            sample_interval_inches=settings.sample_interval_inches,
        )

    def scenario_hash(self) -> str:
        return _digest_payload("phase10u-scenario-v1", self.to_payload())

    def to_payload(self) -> PerformanceScenarioPayload:
        return {
            "scenario_id": self.scenario_id,
            "scenario_kind": self.scenario_kind.value,
            "seed": self.seed,
            "iteration_count": self.iteration_count,
            "model_count": self.model_count,
            "blocker_count": self.blocker_count,
            "terrain_feature_count": self.terrain_feature_count,
            "sample_interval_inches": self.sample_interval_inches,
        }

    @classmethod
    def from_payload(cls, payload: PerformanceScenarioPayload) -> Self:
        return cls(
            scenario_id=payload["scenario_id"],
            scenario_kind=performance_scenario_kind_from_token(payload["scenario_kind"]),
            seed=payload["seed"],
            iteration_count=payload["iteration_count"],
            model_count=payload["model_count"],
            blocker_count=payload["blocker_count"],
            terrain_feature_count=payload["terrain_feature_count"],
            sample_interval_inches=payload["sample_interval_inches"],
        )


@dataclass(frozen=True, slots=True)
class PathingBenchmarkResult:
    scenario_id: str
    scenario_kind: PerformanceScenarioKind
    seed: int
    iteration_count: int
    elapsed_ns: int
    path_validation_runs: int
    terrain_legality_runs: int
    valid_path_count: int
    invalid_path_count: int
    path_sampled_pose_count: int
    model_collision_broadphase_check_count: int
    model_collision_check_count: int
    terrain_collision_broadphase_check_count: int
    terrain_collision_check_count: int
    engagement_broadphase_check_count: int
    engagement_check_count: int
    terrain_sampled_pose_count: int
    terrain_segment_count: int
    terrain_violation_count: int
    scenario_hash: str
    workload_digest: str

    def __post_init__(self) -> None:
        for text_field_name, text_value in (
            ("scenario_id", self.scenario_id),
            ("scenario_hash", self.scenario_hash),
            ("workload_digest", self.workload_digest),
        ):
            object.__setattr__(
                self,
                text_field_name,
                _validate_identifier(text_field_name, text_value),
            )
        object.__setattr__(
            self,
            "scenario_kind",
            performance_scenario_kind_from_token(self.scenario_kind),
        )
        for int_field_name, int_value in (
            ("seed", self.seed),
            ("elapsed_ns", self.elapsed_ns),
            ("path_validation_runs", self.path_validation_runs),
            ("terrain_legality_runs", self.terrain_legality_runs),
            ("valid_path_count", self.valid_path_count),
            ("invalid_path_count", self.invalid_path_count),
            ("path_sampled_pose_count", self.path_sampled_pose_count),
            (
                "model_collision_broadphase_check_count",
                self.model_collision_broadphase_check_count,
            ),
            ("model_collision_check_count", self.model_collision_check_count),
            (
                "terrain_collision_broadphase_check_count",
                self.terrain_collision_broadphase_check_count,
            ),
            ("terrain_collision_check_count", self.terrain_collision_check_count),
            ("engagement_broadphase_check_count", self.engagement_broadphase_check_count),
            ("engagement_check_count", self.engagement_check_count),
            ("terrain_sampled_pose_count", self.terrain_sampled_pose_count),
            ("terrain_segment_count", self.terrain_segment_count),
            ("terrain_violation_count", self.terrain_violation_count),
        ):
            object.__setattr__(
                self,
                int_field_name,
                _validate_non_negative_int(int_field_name, int_value),
            )
        object.__setattr__(
            self,
            "iteration_count",
            _validate_positive_int("iteration_count", self.iteration_count),
        )
        if self.valid_path_count + self.invalid_path_count != self.path_validation_runs:
            raise ProfilingError(
                "PathingBenchmarkResult path counts must equal path_validation_runs."
            )
        if self.model_collision_check_count > self.model_collision_broadphase_check_count:
            raise ProfilingError("Model exact checks cannot exceed broadphase checks.")
        if self.terrain_collision_check_count > self.terrain_collision_broadphase_check_count:
            raise ProfilingError("Terrain exact checks cannot exceed broadphase checks.")
        if self.engagement_check_count > self.engagement_broadphase_check_count:
            raise ProfilingError("Engagement exact checks cannot exceed broadphase checks.")
        expected_digest = _pathing_workload_digest(self)
        if self.workload_digest != expected_digest:
            raise ProfilingError("PathingBenchmarkResult workload_digest drift.")

    @classmethod
    def build(
        cls,
        *,
        scenario: PerformanceScenario,
        elapsed_ns: int,
        path_validation_runs: int,
        terrain_legality_runs: int,
        valid_path_count: int,
        invalid_path_count: int,
        path_sampled_pose_count: int,
        model_collision_broadphase_check_count: int,
        model_collision_check_count: int,
        terrain_collision_broadphase_check_count: int,
        terrain_collision_check_count: int,
        engagement_broadphase_check_count: int,
        engagement_check_count: int,
        terrain_sampled_pose_count: int,
        terrain_segment_count: int,
        terrain_violation_count: int,
    ) -> Self:
        scenario_hash = scenario.scenario_hash()
        provisional = _PathingWorkloadDigestInput(
            scenario_id=scenario.scenario_id,
            scenario_kind=scenario.scenario_kind,
            seed=scenario.seed,
            iteration_count=scenario.iteration_count,
            path_validation_runs=path_validation_runs,
            terrain_legality_runs=terrain_legality_runs,
            valid_path_count=valid_path_count,
            invalid_path_count=invalid_path_count,
            path_sampled_pose_count=path_sampled_pose_count,
            model_collision_broadphase_check_count=model_collision_broadphase_check_count,
            model_collision_check_count=model_collision_check_count,
            terrain_collision_broadphase_check_count=terrain_collision_broadphase_check_count,
            terrain_collision_check_count=terrain_collision_check_count,
            engagement_broadphase_check_count=engagement_broadphase_check_count,
            engagement_check_count=engagement_check_count,
            terrain_sampled_pose_count=terrain_sampled_pose_count,
            terrain_segment_count=terrain_segment_count,
            terrain_violation_count=terrain_violation_count,
            scenario_hash=scenario_hash,
        )
        return cls(
            scenario_id=scenario.scenario_id,
            scenario_kind=scenario.scenario_kind,
            seed=scenario.seed,
            iteration_count=scenario.iteration_count,
            elapsed_ns=elapsed_ns,
            path_validation_runs=path_validation_runs,
            terrain_legality_runs=terrain_legality_runs,
            valid_path_count=valid_path_count,
            invalid_path_count=invalid_path_count,
            path_sampled_pose_count=path_sampled_pose_count,
            model_collision_broadphase_check_count=model_collision_broadphase_check_count,
            model_collision_check_count=model_collision_check_count,
            terrain_collision_broadphase_check_count=terrain_collision_broadphase_check_count,
            terrain_collision_check_count=terrain_collision_check_count,
            engagement_broadphase_check_count=engagement_broadphase_check_count,
            engagement_check_count=engagement_check_count,
            terrain_sampled_pose_count=terrain_sampled_pose_count,
            terrain_segment_count=terrain_segment_count,
            terrain_violation_count=terrain_violation_count,
            scenario_hash=scenario_hash,
            workload_digest=_digest_payload(
                "phase10u-pathing-workload-v1",
                provisional.to_payload(),
            ),
        )

    @property
    def model_collision_broadphase_rejection_count(self) -> int:
        return self.model_collision_broadphase_check_count - self.model_collision_check_count

    @property
    def terrain_collision_broadphase_rejection_count(self) -> int:
        return self.terrain_collision_broadphase_check_count - self.terrain_collision_check_count

    @property
    def engagement_broadphase_rejection_count(self) -> int:
        return self.engagement_broadphase_check_count - self.engagement_check_count

    @property
    def dominant_work_counter(self) -> str:
        counter_name, _counter_value = self._dominant_work_counter()
        return counter_name

    @property
    def dominant_work_count(self) -> int:
        _counter_name, counter_value = self._dominant_work_counter()
        return counter_value

    def to_payload(self) -> PathingBenchmarkResultPayload:
        return {
            "scenario_id": self.scenario_id,
            "scenario_kind": self.scenario_kind.value,
            "seed": self.seed,
            "iteration_count": self.iteration_count,
            "elapsed_ns": self.elapsed_ns,
            "path_validation_runs": self.path_validation_runs,
            "terrain_legality_runs": self.terrain_legality_runs,
            "valid_path_count": self.valid_path_count,
            "invalid_path_count": self.invalid_path_count,
            "path_sampled_pose_count": self.path_sampled_pose_count,
            "model_collision_broadphase_check_count": (self.model_collision_broadphase_check_count),
            "model_collision_check_count": self.model_collision_check_count,
            "model_collision_broadphase_rejection_count": (
                self.model_collision_broadphase_rejection_count
            ),
            "terrain_collision_broadphase_check_count": (
                self.terrain_collision_broadphase_check_count
            ),
            "terrain_collision_check_count": self.terrain_collision_check_count,
            "terrain_collision_broadphase_rejection_count": (
                self.terrain_collision_broadphase_rejection_count
            ),
            "engagement_broadphase_check_count": self.engagement_broadphase_check_count,
            "engagement_check_count": self.engagement_check_count,
            "engagement_broadphase_rejection_count": (self.engagement_broadphase_rejection_count),
            "terrain_sampled_pose_count": self.terrain_sampled_pose_count,
            "terrain_segment_count": self.terrain_segment_count,
            "terrain_violation_count": self.terrain_violation_count,
            "dominant_work_counter": self.dominant_work_counter,
            "dominant_work_count": self.dominant_work_count,
            "scenario_hash": self.scenario_hash,
            "workload_digest": self.workload_digest,
        }

    @classmethod
    def from_payload(cls, payload: PathingBenchmarkResultPayload) -> Self:
        result = cls(
            scenario_id=payload["scenario_id"],
            scenario_kind=performance_scenario_kind_from_token(payload["scenario_kind"]),
            seed=payload["seed"],
            iteration_count=payload["iteration_count"],
            elapsed_ns=payload["elapsed_ns"],
            path_validation_runs=payload["path_validation_runs"],
            terrain_legality_runs=payload["terrain_legality_runs"],
            valid_path_count=payload["valid_path_count"],
            invalid_path_count=payload["invalid_path_count"],
            path_sampled_pose_count=payload["path_sampled_pose_count"],
            model_collision_broadphase_check_count=payload[
                "model_collision_broadphase_check_count"
            ],
            model_collision_check_count=payload["model_collision_check_count"],
            terrain_collision_broadphase_check_count=payload[
                "terrain_collision_broadphase_check_count"
            ],
            terrain_collision_check_count=payload["terrain_collision_check_count"],
            engagement_broadphase_check_count=payload["engagement_broadphase_check_count"],
            engagement_check_count=payload["engagement_check_count"],
            terrain_sampled_pose_count=payload["terrain_sampled_pose_count"],
            terrain_segment_count=payload["terrain_segment_count"],
            terrain_violation_count=payload["terrain_violation_count"],
            scenario_hash=payload["scenario_hash"],
            workload_digest=payload["workload_digest"],
        )
        _validate_derived_counter(
            "model_collision_broadphase_rejection_count",
            payload["model_collision_broadphase_rejection_count"],
            result.model_collision_broadphase_rejection_count,
        )
        _validate_derived_counter(
            "terrain_collision_broadphase_rejection_count",
            payload["terrain_collision_broadphase_rejection_count"],
            result.terrain_collision_broadphase_rejection_count,
        )
        _validate_derived_counter(
            "engagement_broadphase_rejection_count",
            payload["engagement_broadphase_rejection_count"],
            result.engagement_broadphase_rejection_count,
        )
        if payload["dominant_work_counter"] != result.dominant_work_counter:
            raise ProfilingError("PathingBenchmarkResult dominant_work_counter drift.")
        _validate_derived_counter(
            "dominant_work_count",
            payload["dominant_work_count"],
            result.dominant_work_count,
        )
        return result

    def _dominant_work_counter(self) -> tuple[str, int]:
        counters = (
            ("model_collision_broadphase_check_count", self.model_collision_broadphase_check_count),
            ("model_collision_check_count", self.model_collision_check_count),
            (
                "terrain_collision_broadphase_check_count",
                self.terrain_collision_broadphase_check_count,
            ),
            ("terrain_collision_check_count", self.terrain_collision_check_count),
            ("engagement_broadphase_check_count", self.engagement_broadphase_check_count),
            ("engagement_check_count", self.engagement_check_count),
            ("terrain_sampled_pose_count", self.terrain_sampled_pose_count),
            ("path_sampled_pose_count", self.path_sampled_pose_count),
        )
        return max(counters, key=lambda item: (item[1], item[0]))


@dataclass(frozen=True, slots=True)
class PerformanceBudget:
    budget_id: str
    max_elapsed_ns: int | None = None
    max_path_sampled_pose_count: int | None = None
    max_model_collision_check_count: int | None = None
    max_terrain_collision_check_count: int | None = None
    max_engagement_check_count: int | None = None
    max_terrain_sampled_pose_count: int | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "budget_id",
            _validate_identifier("PerformanceBudget budget_id", self.budget_id),
        )
        for field_name, value in (
            ("max_elapsed_ns", self.max_elapsed_ns),
            ("max_path_sampled_pose_count", self.max_path_sampled_pose_count),
            ("max_model_collision_check_count", self.max_model_collision_check_count),
            ("max_terrain_collision_check_count", self.max_terrain_collision_check_count),
            ("max_engagement_check_count", self.max_engagement_check_count),
            ("max_terrain_sampled_pose_count", self.max_terrain_sampled_pose_count),
        ):
            object.__setattr__(self, field_name, _validate_optional_non_negative_int(value))

    def evaluate(self, result: PathingBenchmarkResult) -> tuple[str, ...]:
        violations: list[str] = []
        for metric_name, actual, maximum in (
            ("elapsed_ns", result.elapsed_ns, self.max_elapsed_ns),
            (
                "path_sampled_pose_count",
                result.path_sampled_pose_count,
                self.max_path_sampled_pose_count,
            ),
            (
                "model_collision_check_count",
                result.model_collision_check_count,
                self.max_model_collision_check_count,
            ),
            (
                "terrain_collision_check_count",
                result.terrain_collision_check_count,
                self.max_terrain_collision_check_count,
            ),
            (
                "engagement_check_count",
                result.engagement_check_count,
                self.max_engagement_check_count,
            ),
            (
                "terrain_sampled_pose_count",
                result.terrain_sampled_pose_count,
                self.max_terrain_sampled_pose_count,
            ),
        ):
            if maximum is not None and actual > maximum:
                violations.append(
                    f"{result.scenario_id} {metric_name} {actual} exceeds budget {maximum}."
                )
        return tuple(violations)

    def evaluate_all(self, results: tuple[PathingBenchmarkResult, ...]) -> tuple[str, ...]:
        violations: list[str] = []
        for result in results:
            violations.extend(self.evaluate(result))
        return tuple(violations)

    def to_payload(self) -> PerformanceBudgetPayload:
        return {
            "budget_id": self.budget_id,
            "max_elapsed_ns": self.max_elapsed_ns,
            "max_path_sampled_pose_count": self.max_path_sampled_pose_count,
            "max_model_collision_check_count": self.max_model_collision_check_count,
            "max_terrain_collision_check_count": self.max_terrain_collision_check_count,
            "max_engagement_check_count": self.max_engagement_check_count,
            "max_terrain_sampled_pose_count": self.max_terrain_sampled_pose_count,
        }

    @classmethod
    def from_payload(cls, payload: PerformanceBudgetPayload) -> Self:
        return cls(
            budget_id=payload["budget_id"],
            max_elapsed_ns=payload["max_elapsed_ns"],
            max_path_sampled_pose_count=payload["max_path_sampled_pose_count"],
            max_model_collision_check_count=payload["max_model_collision_check_count"],
            max_terrain_collision_check_count=payload["max_terrain_collision_check_count"],
            max_engagement_check_count=payload["max_engagement_check_count"],
            max_terrain_sampled_pose_count=payload["max_terrain_sampled_pose_count"],
        )


@dataclass(frozen=True, slots=True)
class HotspotReport:
    report_id: str
    results: tuple[PathingBenchmarkResult, ...]
    budget: PerformanceBudget | None = None
    budget_violations: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "report_id",
            _validate_identifier("HotspotReport report_id", self.report_id),
        )
        object.__setattr__(self, "results", _validate_result_tuple(self.results))
        if self.budget is not None and type(self.budget) is not PerformanceBudget:
            raise ProfilingError("HotspotReport budget must be a PerformanceBudget.")
        object.__setattr__(
            self,
            "budget_violations",
            _validate_identifier_tuple("HotspotReport budget_violations", self.budget_violations),
        )
        expected_violations = () if self.budget is None else self.budget.evaluate_all(self.results)
        if self.budget_violations != expected_violations:
            raise ProfilingError("HotspotReport budget_violations drift.")
        if self.report_id != _hotspot_report_id(
            results=self.results,
            budget=self.budget,
            budget_violations=self.budget_violations,
        ):
            raise ProfilingError("HotspotReport report_id drift.")

    @classmethod
    def build(
        cls,
        *,
        results: tuple[PathingBenchmarkResult, ...],
        budget: PerformanceBudget | None = None,
    ) -> Self:
        valid_results = _validate_result_tuple(results)
        violations = () if budget is None else budget.evaluate_all(valid_results)
        report_id = _hotspot_report_id(
            results=valid_results,
            budget=budget,
            budget_violations=violations,
        )
        return cls(
            report_id=report_id,
            results=valid_results,
            budget=budget,
            budget_violations=violations,
        )

    def to_payload(self) -> HotspotReportPayload:
        return {
            "schema_version": _REPORT_SCHEMA_VERSION,
            "report_id": self.report_id,
            "results": [result.to_payload() for result in self.results],
            "budget": None if self.budget is None else self.budget.to_payload(),
            "budget_violations": list(self.budget_violations),
        }

    def to_json(self) -> str:
        return json.dumps(self.to_payload(), indent=2, sort_keys=True)

    @classmethod
    def from_payload(cls, payload: HotspotReportPayload) -> Self:
        if payload["schema_version"] != _REPORT_SCHEMA_VERSION:
            raise ProfilingError("Unsupported HotspotReport schema_version.")
        budget_payload = payload["budget"]
        return cls(
            report_id=payload["report_id"],
            results=tuple(
                PathingBenchmarkResult.from_payload(result) for result in payload["results"]
            ),
            budget=(
                None if budget_payload is None else PerformanceBudget.from_payload(budget_payload)
            ),
            budget_violations=tuple(payload["budget_violations"]),
        )

    @classmethod
    def from_json(cls, value: str) -> Self:
        payload = cast(HotspotReportPayload, json.loads(value))
        return cls.from_payload(payload)


def phase10u_smoke_scenarios(
    *,
    seed: int = 10_001,
    iteration_count: int = 1,
) -> tuple[PerformanceScenario, ...]:
    return tuple(
        PerformanceScenario.for_kind(
            kind,
            seed=seed,
            iteration_count=iteration_count,
            profile_size="smoke",
        )
        for kind in PerformanceScenarioKind
    )


def phase10u_nightly_scenarios(
    *,
    seed: int = 10_001,
    iteration_count: int = 3,
) -> tuple[PerformanceScenario, ...]:
    return tuple(
        PerformanceScenario.for_kind(
            kind,
            seed=seed,
            iteration_count=iteration_count,
            profile_size="nightly",
        )
        for kind in PerformanceScenarioKind
    )


def run_hotspot_profile(
    scenarios: tuple[PerformanceScenario, ...],
    *,
    budget: PerformanceBudget | None = None,
    timer: BenchmarkTimer = perf_counter_ns,
) -> HotspotReport:
    valid_scenarios = _validate_scenario_tuple(scenarios)
    results = tuple(run_performance_scenario(scenario, timer=timer) for scenario in valid_scenarios)
    return HotspotReport.build(results=results, budget=budget)


def run_performance_scenario(
    scenario: PerformanceScenario,
    *,
    timer: BenchmarkTimer = perf_counter_ns,
) -> PathingBenchmarkResult:
    valid_scenario = _validate_scenario(scenario)
    path_query, terrain_contexts = _workload_for_scenario(valid_scenario)
    path_validation_runs = 0
    terrain_legality_runs = 0
    valid_path_count = 0
    invalid_path_count = 0
    path_sampled_pose_count = 0
    model_collision_broadphase_check_count = 0
    model_collision_check_count = 0
    terrain_collision_broadphase_check_count = 0
    terrain_collision_check_count = 0
    engagement_broadphase_check_count = 0
    engagement_check_count = 0
    terrain_sampled_pose_count = 0
    terrain_segment_count = 0
    terrain_violation_count = 0

    start_ns = timer()
    for _index in range(valid_scenario.iteration_count):
        path_result = path_query.evaluate()
        path_validation_runs += 1
        if path_result.is_valid:
            valid_path_count += 1
        else:
            invalid_path_count += 1
        path_sampled_pose_count += path_result.metrics.sampled_pose_count
        model_collision_broadphase_check_count += (
            path_result.metrics.model_collision_broadphase_check_count
        )
        model_collision_check_count += path_result.metrics.model_collision_check_count
        terrain_collision_broadphase_check_count += (
            path_result.metrics.terrain_collision_broadphase_check_count
        )
        terrain_collision_check_count += path_result.metrics.terrain_collision_check_count
        engagement_broadphase_check_count += path_result.metrics.engagement_broadphase_check_count
        engagement_check_count += path_result.metrics.engagement_check_count

        for terrain_context in terrain_contexts:
            terrain_result = terrain_context.validate()
            terrain_legality_runs += 1
            terrain_sampled_pose_count += terrain_result.sampled_pose_count
            terrain_segment_count += len(terrain_result.segments)
            terrain_violation_count += len(terrain_result.violations)
    elapsed_ns = timer() - start_ns

    return PathingBenchmarkResult.build(
        scenario=valid_scenario,
        elapsed_ns=elapsed_ns,
        path_validation_runs=path_validation_runs,
        terrain_legality_runs=terrain_legality_runs,
        valid_path_count=valid_path_count,
        invalid_path_count=invalid_path_count,
        path_sampled_pose_count=path_sampled_pose_count,
        model_collision_broadphase_check_count=model_collision_broadphase_check_count,
        model_collision_check_count=model_collision_check_count,
        terrain_collision_broadphase_check_count=terrain_collision_broadphase_check_count,
        terrain_collision_check_count=terrain_collision_check_count,
        engagement_broadphase_check_count=engagement_broadphase_check_count,
        engagement_check_count=engagement_check_count,
        terrain_sampled_pose_count=terrain_sampled_pose_count,
        terrain_segment_count=terrain_segment_count,
        terrain_violation_count=terrain_violation_count,
    )


def performance_scenario_kind_from_token(
    token: PerformanceScenarioKind | str,
) -> PerformanceScenarioKind:
    if type(token) is PerformanceScenarioKind:
        return token
    if type(token) is not str:
        raise ProfilingError("PerformanceScenarioKind token must be a string.")
    try:
        return PerformanceScenarioKind(token)
    except ValueError as exc:
        raise ProfilingError(f"Unsupported PerformanceScenarioKind token: {token}.") from exc


@dataclass(frozen=True, slots=True)
class _ScenarioSettings:
    model_count: int
    blocker_count: int
    terrain_feature_count: int
    sample_interval_inches: float


@dataclass(frozen=True, slots=True)
class _PathingWorkloadDigestInput:
    scenario_id: str
    scenario_kind: PerformanceScenarioKind
    seed: int
    iteration_count: int
    path_validation_runs: int
    terrain_legality_runs: int
    valid_path_count: int
    invalid_path_count: int
    path_sampled_pose_count: int
    model_collision_broadphase_check_count: int
    model_collision_check_count: int
    terrain_collision_broadphase_check_count: int
    terrain_collision_check_count: int
    engagement_broadphase_check_count: int
    engagement_check_count: int
    terrain_sampled_pose_count: int
    terrain_segment_count: int
    terrain_violation_count: int
    scenario_hash: str

    def to_payload(self) -> dict[str, int | str]:
        return {
            "scenario_id": self.scenario_id,
            "scenario_kind": self.scenario_kind.value,
            "seed": self.seed,
            "iteration_count": self.iteration_count,
            "path_validation_runs": self.path_validation_runs,
            "terrain_legality_runs": self.terrain_legality_runs,
            "valid_path_count": self.valid_path_count,
            "invalid_path_count": self.invalid_path_count,
            "path_sampled_pose_count": self.path_sampled_pose_count,
            "model_collision_broadphase_check_count": (self.model_collision_broadphase_check_count),
            "model_collision_check_count": self.model_collision_check_count,
            "terrain_collision_broadphase_check_count": (
                self.terrain_collision_broadphase_check_count
            ),
            "terrain_collision_check_count": self.terrain_collision_check_count,
            "engagement_broadphase_check_count": self.engagement_broadphase_check_count,
            "engagement_check_count": self.engagement_check_count,
            "terrain_sampled_pose_count": self.terrain_sampled_pose_count,
            "terrain_segment_count": self.terrain_segment_count,
            "terrain_violation_count": self.terrain_violation_count,
            "scenario_hash": self.scenario_hash,
        }


def _scenario_settings(*, kind: PerformanceScenarioKind, scale: int) -> _ScenarioSettings:
    if kind is PerformanceScenarioKind.CROWDED_INFANTRY:
        return _ScenarioSettings(10 * scale, 12 * scale, 0, 0.5)
    if kind is PerformanceScenarioKind.VEHICLE_BLOCKERS:
        return _ScenarioSettings(5 * scale, 10 * scale, 0, 0.5)
    if kind is PerformanceScenarioKind.RUINS_TERRAIN:
        return _ScenarioSettings(3 * scale, 0, 2 * scale, 0.5)
    if kind is PerformanceScenarioKind.RESERVE_LIKE_PLACEMENT:
        return _ScenarioSettings(1, 12 * scale, 0, 0.5)
    if kind is PerformanceScenarioKind.FLY_PATHS:
        return _ScenarioSettings(1, 0, 2 * scale, 0.5)
    raise ProfilingError(f"Unsupported PerformanceScenarioKind: {kind.value}.")


def _workload_for_scenario(
    scenario: PerformanceScenario,
) -> tuple[PathQuery, tuple[TerrainPathLegalityContext, ...]]:
    if scenario.scenario_kind is PerformanceScenarioKind.CROWDED_INFANTRY:
        return (
            _path_query_for_group(scenario, model_prefix="crowded-infantry", model_y_step=1.2),
            (),
        )
    if scenario.scenario_kind is PerformanceScenarioKind.VEHICLE_BLOCKERS:
        return (
            _path_query_for_group(
                scenario,
                model_prefix="vehicle-blocker",
                model_y_step=1.4,
                vehicle_blockers=True,
            ),
            (),
        )
    if scenario.scenario_kind is PerformanceScenarioKind.RUINS_TERRAIN:
        return (
            _path_query_for_group(
                scenario,
                model_prefix="ruins-terrain",
                model_y_step=1.3,
                terrain_blockers=True,
            ),
            _ruins_terrain_contexts(scenario, has_fly=False),
        )
    if scenario.scenario_kind is PerformanceScenarioKind.RESERVE_LIKE_PLACEMENT:
        return (
            _reserve_like_path_query(scenario),
            (),
        )
    if scenario.scenario_kind is PerformanceScenarioKind.FLY_PATHS:
        return (
            _path_query_for_group(
                scenario,
                model_prefix="fly-path",
                model_y_step=1.3,
                has_fly=True,
            ),
            _ruins_terrain_contexts(scenario, has_fly=True),
        )
    raise ProfilingError(f"Unsupported PerformanceScenarioKind: {scenario.scenario_kind.value}.")


def _path_query_for_group(
    scenario: PerformanceScenario,
    *,
    model_prefix: str,
    model_y_step: float,
    vehicle_blockers: bool = False,
    terrain_blockers: bool = False,
    has_fly: bool = False,
) -> PathQuery:
    rng = RandomSource(scenario.seed, history=(scenario.scenario_id, "path-query"))
    model_ids = tuple(f"{model_prefix}-mover-{index}" for index in range(scenario.model_count))
    models = tuple(
        _model(
            model_id,
            x=2.0,
            y=2.0 + (index * model_y_step),
            base=CircularBase(radius=0.5),
        )
        for index, model_id in enumerate(model_ids)
    )
    witness = PathWitness.for_paths(
        tuple(
            (
                model.model_id,
                (
                    model.pose,
                    Pose.at(4.0, model.pose.position.y, facing_degrees=15.0 if has_fly else 0.0),
                    Pose.at(6.0, model.pose.position.y, facing_degrees=30.0 if has_fly else 0.0),
                ),
            )
            for model in models
        )
    )
    blockers = _model_blockers(
        rng=rng.fork("model-blockers"),
        count=scenario.blocker_count,
        vehicle_blockers=vehicle_blockers,
        y_origin=30.0,
    )
    terrain = (
        _terrain_blockers(rng=rng.fork("terrain-blockers"), count=scenario.terrain_feature_count)
        if terrain_blockers
        else ()
    )
    return PathQuery(
        unit_group=UnitGroup.single(_unit(f"{model_prefix}-unit", *model_ids)),
        spatial_index=SpatialIndex(models=models),
        witness=witness,
        movement_envelope=MovementEnvelope(
            max_distance_inches=10.0,
            sample_interval_inches=scenario.sample_interval_inches,
        ),
        collision_set=CollisionSet(
            model_blockers=blockers,
            terrain_blockers=terrain,
        ),
    )


def _reserve_like_path_query(scenario: PerformanceScenario) -> PathQuery:
    mover = _model(
        "reserve-like-mover",
        x=0.75,
        y=22.0,
        base=CircularBase(radius=0.5),
    )
    rng = RandomSource(scenario.seed, history=(scenario.scenario_id, "reserve-screen"))
    screen = _model_blockers(
        rng=rng,
        count=scenario.blocker_count,
        vehicle_blockers=False,
        y_origin=30.0,
    )
    witness = PathWitness.for_paths(
        (
            (
                mover.model_id,
                (
                    mover.pose,
                    Pose.at(3.0, 22.0),
                    Pose.at(6.0, 22.0),
                ),
            ),
        )
    )
    return PathQuery(
        unit_group=UnitGroup.single(_unit("reserve-like-unit", mover.model_id)),
        spatial_index=SpatialIndex(models=(mover,)),
        witness=witness,
        movement_envelope=MovementEnvelope(
            max_distance_inches=8.0,
            sample_interval_inches=scenario.sample_interval_inches,
        ),
        collision_set=CollisionSet(engagement_blockers=screen),
    )


def _ruins_terrain_contexts(
    scenario: PerformanceScenario,
    *,
    has_fly: bool,
) -> tuple[TerrainPathLegalityContext, ...]:
    model = _model(
        f"{scenario.scenario_kind.value}-terrain-mover",
        x=1.0,
        y=1.0,
        base=CircularBase(radius=0.5),
    )
    witness = PathWitness.for_paths(
        (
            (
                model.model_id,
                (
                    model.pose,
                    Pose.at(3.0, 1.0, 3.0) if has_fly else Pose.at(3.0, 1.0),
                    Pose.at(5.0, 1.0),
                ),
            ),
        )
    )
    legality = MovementLegalityContext.from_keywords(
        keywords=("FLY", "INFANTRY") if has_fly else ("INFANTRY",),
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(),
        movement_mode=MovementMode.NORMAL,
        movement_phase_action=_NORMAL_MOVE_TOKEN,
        displacement_kind=_NORMAL_MOVE_TOKEN,
    )
    return (
        legality.to_terrain_path_legality_context(
            moving_model=model,
            witness=witness,
            terrain_features=_ruins_features(scenario.terrain_feature_count),
            sample_interval_inches=scenario.sample_interval_inches,
        ),
    )


def _ruins_features(count: int) -> tuple[TerrainFeatureDefinition, ...]:
    return tuple(
        TerrainFeatureDefinition(
            feature_id=f"phase10u-ruin-{index}",
            feature_kind=TerrainFeatureKind.RUINS,
            footprint_center_x_inches=3.0,
            footprint_center_y_inches=1.0 + (index * 8.0),
            footprint_width_inches=6.0,
            footprint_depth_inches=6.0,
            display_geometry=TerrainDisplayGeometry.axis_aligned_rectangle(
                center_x_inches=3.0,
                center_y_inches=1.0 + (index * 8.0),
                width_inches=6.0,
                depth_inches=6.0,
                display_template_id="profiling_ruins_rect_6x6",
            ),
            walls=(
                TerrainWallDefinition(
                    wall_id="center-wall",
                    center_x_inches=3.0,
                    center_y_inches=1.0 + (index * 8.0),
                    bottom_z_inches=0.0,
                    width_inches=1.0,
                    depth_inches=1.0,
                    height_inches=3.0,
                ),
            ),
            floors=(
                TerrainFloorDefinition(
                    floor_id="ground",
                    center_x_inches=3.0,
                    center_y_inches=1.0 + (index * 8.0),
                    bottom_z_inches=0.0,
                    width_inches=6.0,
                    depth_inches=6.0,
                    thickness_inches=0.12,
                ),
            ),
        )
        for index in range(count)
    )


def _terrain_blockers(
    *,
    rng: RandomSource,
    count: int,
) -> tuple[TerrainVolume, ...]:
    return tuple(
        TerrainVolume(
            terrain_id=f"phase10u-terrain-blocker-{index}",
            bottom_center=Pose.at(
                18.0 + _jitter(rng, f"x-{index}", span=2.0),
                28.0 + index,
            ).position,
            width=1.0,
            depth=1.0,
            height=3.0,
        )
        for index in range(count)
    )


def _model_blockers(
    *,
    rng: RandomSource,
    count: int,
    vehicle_blockers: bool,
    y_origin: float,
) -> tuple[Model, ...]:
    return tuple(
        _model(
            f"phase10u-blocker-{index}",
            x=16.0 + _jitter(rng, f"x-{index}", span=3.0),
            y=y_origin + index,
            base=RectangularBase(length=3.0, width=2.0)
            if vehicle_blockers
            else CircularBase(radius=0.5),
        )
        for index in range(count)
    )


def _model(model_id: str, *, x: float, y: float, base: BaseShape) -> Model:
    return Model(
        model_id=model_id,
        pose=Pose.at(x, y),
        base=base,
        volume=ModelVolume(height=2.0),
    )


def _unit(unit_id: str, *model_ids: str) -> Unit:
    return Unit(
        unit_id=unit_id,
        name=unit_id.title(),
        own_models=tuple(
            UnitMember.ready(model_id=model_id, name=model_id.title()) for model_id in model_ids
        ),
    )


def _jitter(rng: RandomSource, label: str, *, span: float) -> float:
    value = rng.randint_inclusive(0, 1_000, stream_label=label)
    return ((value / 1_000.0) - 0.5) * span


def _pathing_workload_digest(result: PathingBenchmarkResult) -> str:
    digest_input = _PathingWorkloadDigestInput(
        scenario_id=result.scenario_id,
        scenario_kind=result.scenario_kind,
        seed=result.seed,
        iteration_count=result.iteration_count,
        path_validation_runs=result.path_validation_runs,
        terrain_legality_runs=result.terrain_legality_runs,
        valid_path_count=result.valid_path_count,
        invalid_path_count=result.invalid_path_count,
        path_sampled_pose_count=result.path_sampled_pose_count,
        model_collision_broadphase_check_count=result.model_collision_broadphase_check_count,
        model_collision_check_count=result.model_collision_check_count,
        terrain_collision_broadphase_check_count=result.terrain_collision_broadphase_check_count,
        terrain_collision_check_count=result.terrain_collision_check_count,
        engagement_broadphase_check_count=result.engagement_broadphase_check_count,
        engagement_check_count=result.engagement_check_count,
        terrain_sampled_pose_count=result.terrain_sampled_pose_count,
        terrain_segment_count=result.terrain_segment_count,
        terrain_violation_count=result.terrain_violation_count,
        scenario_hash=result.scenario_hash,
    )
    return _digest_payload("phase10u-pathing-workload-v1", digest_input.to_payload())


def _hotspot_report_id(
    *,
    results: tuple[PathingBenchmarkResult, ...],
    budget: PerformanceBudget | None,
    budget_violations: tuple[str, ...],
) -> str:
    payload = {
        "schema_version": _REPORT_SCHEMA_VERSION,
        "results": [result.to_payload() for result in results],
        "budget": None if budget is None else budget.to_payload(),
        "budget_violations": list(budget_violations),
    }
    return f"hotspot-report-{_digest_payload('phase10u-hotspot-report-id-v1', payload)[:16]}"


def _digest_payload(label: str, payload: object) -> str:
    digest = sha256()
    digest.update(label.encode("utf-8"))
    digest.update(b"\x00")
    digest.update(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8"))
    return digest.hexdigest()


def _validate_scenario_tuple(values: object) -> tuple[PerformanceScenario, ...]:
    if type(values) is not tuple:
        raise ProfilingError("Performance scenarios must be a tuple.")
    scenarios = tuple(_validate_scenario(value) for value in cast(tuple[object, ...], values))
    if not scenarios:
        raise ProfilingError("Performance scenarios must not be empty.")
    return scenarios


def _validate_scenario(value: object) -> PerformanceScenario:
    if type(value) is not PerformanceScenario:
        raise ProfilingError("Performance scenario must be a PerformanceScenario.")
    return value


def _validate_result_tuple(values: object) -> tuple[PathingBenchmarkResult, ...]:
    if type(values) is not tuple:
        raise ProfilingError("HotspotReport results must be a tuple.")
    results = tuple(
        _validate_result("HotspotReport result", value)
        for value in cast(tuple[object, ...], values)
    )
    if not results:
        raise ProfilingError("HotspotReport results must not be empty.")
    return results


def _validate_result(field_name: str, value: object) -> PathingBenchmarkResult:
    if type(value) is not PathingBenchmarkResult:
        raise ProfilingError(f"{field_name} must be a PathingBenchmarkResult.")
    return value


def _validate_identifier_tuple(field_name: str, values: object) -> tuple[str, ...]:
    if type(values) is not tuple:
        raise ProfilingError(f"{field_name} must be a tuple.")
    return tuple(
        _validate_identifier(f"{field_name} value", value)
        for value in cast(tuple[object, ...], values)
    )


def _validate_identifier(field_name: str, value: object) -> str:
    if type(value) is not str:
        raise ProfilingError(f"{field_name} must be a string.")
    stripped = value.strip()
    if not stripped:
        raise ProfilingError(f"{field_name} must not be empty.")
    if "<" in stripped or "object at 0x" in stripped:
        raise ProfilingError(f"{field_name} must be JSON-safe and not an object repr.")
    return stripped


def _validate_int(field_name: str, value: object) -> int:
    if type(value) is not int:
        raise ProfilingError(f"{field_name} must be an integer.")
    return value


def _validate_positive_int(field_name: str, value: object) -> int:
    number = _validate_int(field_name, value)
    if number < 1:
        raise ProfilingError(f"{field_name} must be at least 1.")
    return number


def _validate_non_negative_int(field_name: str, value: object) -> int:
    number = _validate_int(field_name, value)
    if number < 0:
        raise ProfilingError(f"{field_name} must not be negative.")
    return number


def _validate_derived_counter(field_name: str, actual: object, expected: int) -> None:
    actual_count = _validate_non_negative_int(field_name, actual)
    if actual_count != expected:
        raise ProfilingError(f"PathingBenchmarkResult {field_name} drift.")


def _validate_optional_non_negative_int(value: object | None) -> int | None:
    if value is None:
        return None
    return _validate_non_negative_int("PerformanceBudget limit", value)


def _validate_positive_number(field_name: str, value: object) -> float:
    if not isinstance(value, int | float) or type(value) is bool:
        raise ProfilingError(f"{field_name} must be a number.")
    number = float(value)
    if number <= 0.0:
        raise ProfilingError(f"{field_name} must be greater than 0.")
    return number


def _profile_size_from_token(token: str) -> str:
    size = _validate_identifier("profile_size", token)
    if size not in {"smoke", "nightly"}:
        raise ProfilingError("profile_size must be smoke or nightly.")
    return size
