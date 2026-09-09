from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from functools import lru_cache
from typing import Self, TypedDict, cast

from warhammer40k_core.core.ruleset_descriptor import (
    LineOfSightPolicy,
    RulesetDescriptor,
    TerrainFeatureVisibilityPolicy,
    TerrainVisibilityPolicyDescriptor,
    TerrainVisibilityPolicyDescriptorPayload,
)
from warhammer40k_core.core.validation import canonical_keyword_token
from warhammer40k_core.core.visibility_records import (
    BenefitOfCoverResult as BenefitOfCoverResult,
)
from warhammer40k_core.core.visibility_records import (
    BenefitOfCoverResultPayload as BenefitOfCoverResultPayload,
)
from warhammer40k_core.core.visibility_records import (
    CoverEvidenceRecord as CoverEvidenceRecord,
)
from warhammer40k_core.core.visibility_records import (
    CoverSourceReason as CoverSourceReason,
)
from warhammer40k_core.core.visibility_records import (
    CoverSourceRecord as CoverSourceRecord,
)
from warhammer40k_core.core.visibility_records import (
    CoverSourceRecordPayload as CoverSourceRecordPayload,
)
from warhammer40k_core.core.visibility_records import (
    LineOfSightWitness as LineOfSightWitness,
)
from warhammer40k_core.core.visibility_records import (
    LineOfSightWitnessPayload as LineOfSightWitnessPayload,
)
from warhammer40k_core.core.visibility_records import (
    ModelLineOfSightRecord as ModelLineOfSightRecord,
)
from warhammer40k_core.core.visibility_records import (
    ModelLineOfSightRecordPayload as ModelLineOfSightRecordPayload,
)
from warhammer40k_core.core.visibility_records import (
    TerrainAreaCoverSourceRecord as TerrainAreaCoverSourceRecord,
)
from warhammer40k_core.core.visibility_records import (
    TerrainAreaCoverSourceRecordPayload as TerrainAreaCoverSourceRecordPayload,
)
from warhammer40k_core.core.visibility_records import (
    VisibilityBlockerKind as VisibilityBlockerKind,
)
from warhammer40k_core.core.visibility_records import (
    VisibilityBlockerRecord as VisibilityBlockerRecord,
)
from warhammer40k_core.core.visibility_records import (
    VisibilityBlockerRecordPayload as VisibilityBlockerRecordPayload,
)
from warhammer40k_core.core.visibility_records import (
    cover_source_reason_from_token as cover_source_reason_from_token,
)
from warhammer40k_core.core.visibility_records import (
    cover_source_record_sort_key,
    feature_visibility_policy,
    validate_visibility_identifier,
    visibility_blocker_record_sort_key,
)
from warhammer40k_core.core.visibility_records import (
    visibility_blocker_kind_from_token as visibility_blocker_kind_from_token,
)
from warhammer40k_core.geometry.continuous_visibility import (
    resolve_visibility_pair,
    resolve_visibility_pair_uncached,
)
from warhammer40k_core.geometry.pose import (
    GeometryError,
)
from warhammer40k_core.geometry.terrain import (
    TerrainFeatureDefinition,
    TerrainFeatureDefinitionPayload,
    TerrainVolume,
    TerrainVolumePayload,
    terrain_volume_from_payload,
)
from warhammer40k_core.geometry.terrain_area_visibility import (
    TerrainVisibilityArea,
    TerrainVisibilityAreaPayload,
    classification_has_visibility_semantics,
    feature_ids_associated_with_terrain_areas,
    model_intersects_terrain_area,
    validate_terrain_visibility_areas,
)
from warhammer40k_core.geometry.visibility_certificates import corridors_clear_by_enclosure
from warhammer40k_core.geometry.visibility_exact import VisibilityPrism
from warhammer40k_core.geometry.visibility_footprints import (
    model_intersects_visibility_polygon,
    model_within_visibility_polygons,
    polygon_visibility_prism,
)
from warhammer40k_core.geometry.visibility_occlusion import source_group_obscures
from warhammer40k_core.geometry.visibility_query import (
    VisibilityMetrics as VisibilityMetrics,
)
from warhammer40k_core.geometry.visibility_query import (
    VisibilityMetricsPayload as VisibilityMetricsPayload,
)
from warhammer40k_core.geometry.visibility_query import VisibilityQuery as VisibilityQuery
from warhammer40k_core.geometry.visibility_query import (
    VisibilityQueryPayload as VisibilityQueryPayload,
)
from warhammer40k_core.geometry.visibility_query import VisibilityRay as VisibilityRay
from warhammer40k_core.geometry.visibility_query import (
    VisibilityRayPayload as VisibilityRayPayload,
)
from warhammer40k_core.geometry.visibility_query import VisibilityResult as VisibilityResult
from warhammer40k_core.geometry.visibility_query import (
    VisibilityResultPayload as VisibilityResultPayload,
)
from warhammer40k_core.geometry.visibility_shapes import (
    model_visibility_prism,
    terrain_visibility_prism,
)
from warhammer40k_core.geometry.volume import Model, ModelPayload


class ModelVisibilityKeywordsPayload(TypedDict):
    model_id: str
    keywords: list[str]


class TerrainVisibilityContextPayload(TypedDict):
    ruleset_descriptor_hash: str
    los_cache_key: str
    observer_model: ModelPayload
    target_models: list[ModelPayload]
    terrain_features: list[TerrainFeatureDefinitionPayload]
    terrain_areas: list[TerrainVisibilityAreaPayload]
    terrain_volumes: list[TerrainVolumePayload]
    dynamic_model_blockers: list[ModelPayload]
    observer_keywords: list[str]
    target_model_keywords: list[ModelVisibilityKeywordsPayload]
    terrain_visibility_policy: TerrainVisibilityPolicyDescriptorPayload


@dataclass(frozen=True, slots=True)
class TerrainVisibilityContext:
    ruleset_descriptor_hash: str
    los_cache_key: str
    terrain_visibility_policy: TerrainVisibilityPolicyDescriptor
    observer_model: Model
    target_models: tuple[Model, ...]
    target_model_keywords: tuple[tuple[str, tuple[str, ...]], ...]
    terrain_features: tuple[TerrainFeatureDefinition, ...] = ()
    terrain_areas: tuple[TerrainVisibilityArea, ...] = ()
    terrain_volumes: tuple[TerrainVolume, ...] = ()
    dynamic_model_blockers: tuple[Model, ...] = ()
    observer_keywords: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "ruleset_descriptor_hash",
            validate_visibility_identifier(
                "TerrainVisibilityContext ruleset_descriptor_hash",
                self.ruleset_descriptor_hash,
            ),
        )
        object.__setattr__(
            self,
            "los_cache_key",
            validate_visibility_identifier(
                "TerrainVisibilityContext los_cache_key", self.los_cache_key
            ),
        )
        if type(self.terrain_visibility_policy) is not TerrainVisibilityPolicyDescriptor:
            raise GeometryError(
                "TerrainVisibilityContext terrain_visibility_policy must be "
                "TerrainVisibilityPolicyDescriptor."
            )
        _validate_keyword_tuple(
            "TerrainVisibilityContext policy hidden_requires_keywords",
            self.terrain_visibility_policy.hidden_requires_keywords,
        )
        observer_model = _validate_model(
            "TerrainVisibilityContext observer_model",
            self.observer_model,
        )
        object.__setattr__(self, "observer_model", observer_model)
        target_models = _validate_model_tuple(
            "TerrainVisibilityContext target_models",
            self.target_models,
            allow_empty=False,
        )
        if any(target.model_id == observer_model.model_id for target in target_models):
            raise GeometryError("TerrainVisibilityContext target_models must not include observer.")
        object.__setattr__(self, "target_models", target_models)
        object.__setattr__(
            self,
            "target_model_keywords",
            _validate_target_model_keywords(
                self.target_model_keywords,
                target_model_ids=tuple(model.model_id for model in target_models),
            ),
        )
        terrain_features = _validate_terrain_feature_tuple(
            "TerrainVisibilityContext terrain_features",
            self.terrain_features,
        )
        object.__setattr__(self, "terrain_features", terrain_features)
        object.__setattr__(
            self,
            "terrain_areas",
            validate_terrain_visibility_areas(
                "TerrainVisibilityContext terrain_areas",
                self.terrain_areas,
            ),
        )
        terrain_volumes = self.terrain_volumes
        if not terrain_volumes:
            terrain_volumes = tuple(
                volume for feature in terrain_features for volume in feature.terrain_volumes()
            )
        object.__setattr__(
            self,
            "terrain_volumes",
            _validate_terrain_volume_tuple(
                "TerrainVisibilityContext terrain_volumes",
                terrain_volumes,
            ),
        )
        blocker_models = _validate_model_tuple(
            "TerrainVisibilityContext dynamic_model_blockers",
            self.dynamic_model_blockers,
            allow_empty=True,
        )
        target_model_ids = {target.model_id for target in target_models}
        if any(
            blocker.model_id == observer_model.model_id or blocker.model_id in target_model_ids
            for blocker in blocker_models
        ):
            raise GeometryError(
                "TerrainVisibilityContext dynamic_model_blockers must exclude observer and target."
            )
        object.__setattr__(self, "dynamic_model_blockers", blocker_models)
        object.__setattr__(
            self,
            "observer_keywords",
            _validate_keyword_tuple(
                "TerrainVisibilityContext observer_keywords",
                self.observer_keywords,
            ),
        )

    @classmethod
    def from_ruleset_descriptor(
        cls,
        *,
        ruleset_descriptor: RulesetDescriptor,
        los_cache_key: str,
        observer_model: Model,
        target_models: tuple[Model, ...],
        target_model_keywords: tuple[tuple[str, tuple[str, ...]], ...],
        terrain_features: tuple[TerrainFeatureDefinition, ...] = (),
        terrain_areas: tuple[TerrainVisibilityArea, ...] = (),
        terrain_volumes: tuple[TerrainVolume, ...] = (),
        dynamic_model_blockers: tuple[Model, ...] = (),
        observer_keywords: tuple[str, ...] = (),
    ) -> Self:
        descriptor = _validate_ruleset_descriptor(ruleset_descriptor)
        return cls(
            ruleset_descriptor_hash=descriptor.descriptor_hash,
            los_cache_key=los_cache_key,
            terrain_visibility_policy=descriptor.terrain_visibility_policy,
            observer_model=observer_model,
            target_models=target_models,
            target_model_keywords=target_model_keywords,
            terrain_features=terrain_features,
            terrain_areas=terrain_areas,
            terrain_volumes=terrain_volumes,
            dynamic_model_blockers=dynamic_model_blockers,
            observer_keywords=observer_keywords,
        )

    def context_fingerprint(self) -> str:
        return _context_fingerprint(self)

    def resolve_line_of_sight(self) -> LineOfSightWitness:
        return _resolve_context(self)

    def resolve_line_of_sight_uncached(self) -> LineOfSightWitness:
        return self._resolve_line_of_sight(use_result_cache=False)

    def _resolve_line_of_sight(self, *, use_result_cache: bool) -> LineOfSightWitness:
        terrain_area_feature_ids = feature_ids_associated_with_terrain_areas(
            self.terrain_features,
            self.terrain_areas,
        )
        records = tuple(
            self._resolve_model_line_of_sight(
                target_model,
                terrain_area_feature_ids=terrain_area_feature_ids,
                use_result_cache=use_result_cache,
            )
            for target_model in self.target_models
        )
        return LineOfSightWitness.from_records(
            context_fingerprint=self.context_fingerprint(),
            ruleset_descriptor_hash=self.ruleset_descriptor_hash,
            los_cache_key=self.los_cache_key,
            observer_model_id=self.observer_model.model_id,
            model_records=records,
        )

    def benefit_of_cover(self, witness: LineOfSightWitness) -> BenefitOfCoverResult:
        self._validate_witness(witness)
        return BenefitOfCoverResult.from_cover_sources(
            witness=witness,
            terrain_visibility_policy=self.terrain_visibility_policy,
            source_records=self._cover_source_records(witness),
        )

    def _validate_witness(self, witness: LineOfSightWitness) -> None:
        if type(witness) is not LineOfSightWitness:
            raise GeometryError("benefit_of_cover requires a LineOfSightWitness.")
        if witness.ruleset_descriptor_hash != self.ruleset_descriptor_hash:
            raise GeometryError("LineOfSightWitness ruleset hash does not match context.")
        if witness.los_cache_key != self.los_cache_key:
            raise GeometryError("LineOfSightWitness los_cache_key does not match context.")
        if witness.observer_model_id != self.observer_model.model_id:
            raise GeometryError("LineOfSightWitness observer does not match context.")
        target_model_ids = tuple(target_model.model_id for target_model in self.target_models)
        if witness.target_model_ids != target_model_ids:
            raise GeometryError("LineOfSightWitness targets do not match context.")
        if witness.context_fingerprint != self.context_fingerprint():
            raise GeometryError(
                "LineOfSightWitness geometry, keywords or policy do not match context."
            )
        if witness != self.resolve_line_of_sight():
            raise GeometryError("LineOfSightWitness evidence does not match authoritative context.")

    def not_fully_visible_because_of(
        self,
        witness: LineOfSightWitness,
        *,
        target_model_id: str,
        sources: tuple[VisibilityBlockerRecord, ...],
    ) -> bool:
        """Evaluate a source GROUP's causal contribution through the shared authority."""
        self._validate_witness(witness)
        if type(sources) is not tuple or any(
            type(s) is not VisibilityBlockerRecord for s in sources
        ):
            raise GeometryError("Visibility source group requires typed blocker records.")
        if len(set(sources)) != len(sources):
            raise GeometryError("Visibility source group must not contain duplicate records.")
        record = next(
            (r for r in witness.model_records if r.target_model_id == target_model_id), None
        )
        if record is None or any(source not in record.blocker_records for source in sources):
            raise GeometryError(
                "Visibility source group must belong to the target's current witness."
            )
        if record.model_fully_visible or not sources:
            return False
        target = next(model for model in self.target_models if model.model_id == target_model_id)
        entries = self._obstacle_entries(
            target,
            feature_ids_associated_with_terrain_areas(self.terrain_features, self.terrain_areas),
        )
        selected = tuple(
            prism
            for prism, source in entries
            if source.blocks_full_visibility and source in sources
        )
        remaining = tuple(
            prism
            for prism, source in entries
            if source.blocks_full_visibility and source not in sources
        )
        return source_group_obscures(
            model_visibility_prism(self.observer_model),
            model_visibility_prism(target),
            selected,
            remaining,
        )

    def to_payload(self) -> TerrainVisibilityContextPayload:
        return {
            "ruleset_descriptor_hash": self.ruleset_descriptor_hash,
            "los_cache_key": self.los_cache_key,
            "observer_model": self.observer_model.to_payload(),
            "target_models": [model.to_payload() for model in self.target_models],
            "terrain_features": [feature.to_payload() for feature in self.terrain_features],
            "terrain_areas": [area.to_payload() for area in self.terrain_areas],
            "terrain_volumes": [volume.to_payload() for volume in self.terrain_volumes],
            "dynamic_model_blockers": [model.to_payload() for model in self.dynamic_model_blockers],
            "observer_keywords": list(self.observer_keywords),
            "target_model_keywords": [
                {"model_id": model_id, "keywords": list(keywords)}
                for model_id, keywords in self.target_model_keywords
            ],
            "terrain_visibility_policy": self.terrain_visibility_policy.to_payload(),
        }

    @classmethod
    def from_payload(cls, payload: TerrainVisibilityContextPayload) -> Self:
        return cls(
            ruleset_descriptor_hash=payload["ruleset_descriptor_hash"],
            los_cache_key=payload["los_cache_key"],
            terrain_visibility_policy=TerrainVisibilityPolicyDescriptor.from_payload(
                payload["terrain_visibility_policy"]
            ),
            observer_model=Model.from_payload(payload["observer_model"]),
            target_models=tuple(Model.from_payload(model) for model in payload["target_models"]),
            terrain_features=tuple(
                TerrainFeatureDefinition.from_payload(feature)
                for feature in payload["terrain_features"]
            ),
            terrain_areas=tuple(
                TerrainVisibilityArea.from_payload(area) for area in payload["terrain_areas"]
            ),
            terrain_volumes=tuple(
                terrain_volume_from_payload(volume) for volume in payload["terrain_volumes"]
            ),
            dynamic_model_blockers=tuple(
                Model.from_payload(model) for model in payload["dynamic_model_blockers"]
            ),
            observer_keywords=tuple(payload["observer_keywords"]),
            target_model_keywords=tuple(
                (row["model_id"], tuple(row["keywords"]))
                for row in payload["target_model_keywords"]
            ),
        )

    def _resolve_model_line_of_sight(
        self,
        target_model: Model,
        *,
        terrain_area_feature_ids: frozenset[str],
        use_result_cache: bool = True,
    ) -> ModelLineOfSightRecord:
        entries = self._obstacle_entries(target_model, terrain_area_feature_ids)
        resolver = resolve_visibility_pair if use_result_cache else resolve_visibility_pair_uncached
        evidence = resolver(
            model_visibility_prism(self.observer_model),
            model_visibility_prism(target_model),
            tuple(prism for prism, record in entries if record.blocks_model_visibility),
            tuple(prism for prism, record in entries if record.blocks_full_visibility),
        )
        records = tuple(
            sorted({record for _, record in entries}, key=visibility_blocker_record_sort_key)
        )
        return ModelLineOfSightRecord(
            target_model_id=target_model.model_id,
            model_visible=evidence.model_visible,
            model_fully_visible=evidence.model_fully_visible,
            evidence=evidence,
            blocker_records=records,
        )

    def _obstacle_entries(
        self, target_model: Model, terrain_area_feature_ids: frozenset[str]
    ) -> tuple[tuple[VisibilityPrism, VisibilityBlockerRecord], ...]:
        entries = list(
            _physical_obstacle_entries(
                self.terrain_features, self.terrain_volumes, self.dynamic_model_blockers
            )
        )
        observer, target = (
            model_visibility_prism(self.observer_model),
            model_visibility_prism(target_model),
        )
        lower, upper = min(observer.lower, target.lower), max(observer.upper, target.upper)
        for feature in self.terrain_features:
            if feature.feature_id in terrain_area_feature_ids:
                continue
            policy = feature_visibility_policy(self.terrain_visibility_policy, feature.feature_kind)
            if not (
                policy.blocks_model_visibility_through_footprint
                or policy.blocks_full_visibility_through_footprint
            ):
                continue
            exception = _terrain_feature_visibility_exception(
                policy=policy,
                feature=feature,
                observer_model=self.observer_model,
                target_model=target_model,
                observer_keywords=self.observer_keywords,
                target_keywords=self._keywords_for_target_model(target_model.model_id),
            )
            entries.append(
                (
                    polygon_visibility_prism(feature.rules_footprint_points(), lower, upper),
                    VisibilityBlockerRecord(
                        blocker_kind=VisibilityBlockerKind.TERRAIN_FEATURE,
                        blocker_id=feature.feature_id,
                        terrain_feature_id=feature.feature_id,
                        terrain_feature_kind=feature.feature_kind,
                        line_of_sight_policy=policy.line_of_sight_policy,
                        blocks_model_visibility=exception is None
                        and policy.blocks_model_visibility_through_footprint,
                        blocks_full_visibility=exception is None
                        and policy.blocks_full_visibility_through_footprint,
                        exception_applied=exception,
                    ),
                )
            )
        for area in self.terrain_areas:
            if not classification_has_visibility_semantics(area.classification):
                continue
            observer_intersects = model_intersects_terrain_area(self.observer_model, area)
            target_intersects = model_intersects_terrain_area(target_model, area)
            exception = None
            if observer_intersects and target_intersects:
                exception = "observer_and_target_intersect_area"
            elif observer_intersects:
                exception = "observer_intersects_area"
            elif target_intersects:
                exception = "target_intersects_area"
            record = VisibilityBlockerRecord(
                blocker_kind=VisibilityBlockerKind.TERRAIN_AREA,
                blocker_id=area.terrain_area_id,
                terrain_area_id=area.terrain_area_id,
                terrain_area_classification=area.classification,
                line_of_sight_policy=LineOfSightPolicy.AREA_OBSCURING,
                blocks_model_visibility=exception is None,
                blocks_full_visibility=exception is None,
                exception_applied=exception,
            )
            entries.extend(
                (polygon_visibility_prism(polygon, lower, upper), record)
                for polygon in area.footprint_polygons
            )
        return tuple(
            (prism, record)
            for prism, record in entries
            if not corridors_clear_by_enclosure(observer, target, (prism,))
        )

    def _cover_source_records(self, witness: LineOfSightWitness) -> tuple[CoverEvidenceRecord, ...]:
        records: set[CoverEvidenceRecord] = set()
        model_record_by_id = {record.target_model_id: record for record in witness.model_records}
        area_keyword_gate = set(self.terrain_visibility_policy.hidden_requires_keywords)
        area_grants_cover = self.terrain_visibility_policy.cover_policy.grants_benefit_of_cover
        for target_model in self.target_models:
            model_records: set[CoverEvidenceRecord] = set()
            model_keywords = set(self._keywords_for_target_model(target_model.model_id))
            matching_areas = tuple(
                area
                for area in self.terrain_areas
                if model_intersects_terrain_area(target_model, area)
            )
            if area_grants_cover and (
                not area_keyword_gate or area_keyword_gate.intersection(model_keywords)
            ):
                model_records.update(
                    TerrainAreaCoverSourceRecord(
                        terrain_area_id=area.terrain_area_id,
                        classification=area.classification,
                        policy_kind=(
                            LineOfSightPolicy.AREA_OBSCURING
                            if classification_has_visibility_semantics(area.classification)
                            else LineOfSightPolicy.TRUE_LINE_OF_SIGHT
                        ),
                        reason=CoverSourceReason.WITHIN_TERRAIN_AREA,
                    )
                    for area in matching_areas
                )
            eligible = tuple(
                source
                for source in model_record_by_id[target_model.model_id].blocker_records
                if source.blocks_full_visibility
                and (
                    (source.terrain_area_id is not None and area_grants_cover)
                    or (
                        source.terrain_feature_kind is not None
                        and feature_visibility_policy(
                            self.terrain_visibility_policy, source.terrain_feature_kind
                        ).cover_policy.grants_benefit_of_cover
                    )
                )
            )
            terrain_obscures = not model_records and self.not_fully_visible_because_of(
                witness, target_model_id=target_model.model_id, sources=eligible
            )
            for blocker_record in eligible if terrain_obscures else ():
                if not blocker_record.blocks_full_visibility:
                    continue
                if (
                    blocker_record.terrain_feature_id is not None
                    and blocker_record.terrain_feature_kind is not None
                ):
                    feature_policy = feature_visibility_policy(
                        self.terrain_visibility_policy,
                        blocker_record.terrain_feature_kind,
                    )
                    if feature_policy.cover_policy.grants_benefit_of_cover:
                        model_records.add(
                            CoverSourceRecord(
                                feature_id=blocker_record.terrain_feature_id,
                                feature_kind=blocker_record.terrain_feature_kind,
                                policy_kind=feature_policy.line_of_sight_policy,
                                reason=(CoverSourceReason.NOT_FULLY_VISIBLE_BECAUSE_OF_FEATURE),
                            )
                        )
                if (
                    blocker_record.terrain_area_id is not None
                    and blocker_record.terrain_area_classification is not None
                ):
                    model_records.add(
                        TerrainAreaCoverSourceRecord(
                            terrain_area_id=blocker_record.terrain_area_id,
                            classification=blocker_record.terrain_area_classification,
                            policy_kind=blocker_record.line_of_sight_policy,
                            reason=(CoverSourceReason.NOT_FULLY_VISIBLE_BECAUSE_OF_TERRAIN_AREA),
                        )
                    )
            if not model_records:
                return ()
            records.update(model_records)
        return tuple(sorted(records, key=cover_source_record_sort_key))

    def _keywords_for_target_model(self, model_id: str) -> tuple[str, ...]:
        for target_model_id, keywords in self.target_model_keywords:
            if target_model_id == model_id:
                return keywords
        raise GeometryError("Target model keyword context is incomplete.")


@lru_cache(maxsize=128)
def _context_fingerprint(context: TerrainVisibilityContext) -> str:
    return hashlib.sha256(
        json.dumps(
            context.to_payload(), sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode("utf-8")
    ).hexdigest()


@lru_cache(maxsize=128)
def _resolve_context(context: TerrainVisibilityContext) -> LineOfSightWitness:
    return context._resolve_line_of_sight(use_result_cache=True)  # pyright: ignore[reportPrivateUsage]


@lru_cache(maxsize=128)
def _physical_obstacle_entries(
    features: tuple[TerrainFeatureDefinition, ...],
    volumes: tuple[TerrainVolume, ...],
    models: tuple[Model, ...],
) -> tuple[tuple[VisibilityPrism, VisibilityBlockerRecord], ...]:
    index = _terrain_volume_feature_index(features)
    return (
        *(
            (
                terrain_visibility_prism(volume),
                _terrain_volume_blocker_record(
                    terrain_id=volume.terrain_id, volume_feature_index=index
                ),
            )
            for volume in volumes
            if volume.blocks_line_of_sight
        ),
        *(
            (
                model_visibility_prism(model),
                VisibilityBlockerRecord(
                    blocker_kind=VisibilityBlockerKind.MODEL,
                    blocker_id=model.model_id,
                    line_of_sight_policy=LineOfSightPolicy.TRUE_LINE_OF_SIGHT,
                    blocks_model_visibility=True,
                    blocks_full_visibility=True,
                ),
            )
            for model in models
        ),
    )


def _validate_ruleset_descriptor(value: object) -> RulesetDescriptor:
    if type(value) is not RulesetDescriptor:
        raise GeometryError("Terrain visibility requires an explicit RulesetDescriptor.")
    return value


def _validate_terrain(field_name: str, value: object) -> TerrainVolume:
    if not isinstance(value, TerrainVolume):
        raise GeometryError(f"{field_name} must be a TerrainVolume.")
    return value


def _validate_model(field_name: str, value: object) -> Model:
    if type(value) is not Model:
        raise GeometryError(f"{field_name} must be a Model.")
    return value


def _validate_model_tuple(
    field_name: str,
    values: object,
    *,
    allow_empty: bool,
) -> tuple[Model, ...]:
    if type(values) is not tuple:
        raise GeometryError(f"{field_name} must be a tuple.")
    raw_values = cast(tuple[object, ...], values)
    models = tuple(_validate_model(f"{field_name} value", value) for value in raw_values)
    if not allow_empty and not models:
        raise GeometryError(f"{field_name} must not be empty.")
    _validate_unique_model_ids(models)
    return tuple(sorted(models, key=lambda model: model.model_id))


def _validate_terrain_feature_tuple(
    field_name: str,
    values: object,
) -> tuple[TerrainFeatureDefinition, ...]:
    if type(values) is not tuple:
        raise GeometryError(f"{field_name} must be a tuple.")
    features: list[TerrainFeatureDefinition] = []
    seen: set[str] = set()
    for value in cast(tuple[object, ...], values):
        if type(value) is not TerrainFeatureDefinition:
            raise GeometryError(f"{field_name} must contain TerrainFeatureDefinition values.")
        if value.feature_id in seen:
            raise GeometryError(f"{field_name} must not contain duplicate IDs.")
        seen.add(value.feature_id)
        features.append(value)
    return tuple(sorted(features, key=lambda feature: feature.feature_id))


def _validate_terrain_volume_tuple(
    field_name: str,
    values: object,
) -> tuple[TerrainVolume, ...]:
    if type(values) is not tuple:
        raise GeometryError(f"{field_name} must be a tuple.")
    raw_values = cast(tuple[object, ...], values)
    terrain = tuple(_validate_terrain(f"{field_name} value", value) for value in raw_values)
    _validate_unique_terrain_ids(terrain)
    return tuple(sorted(terrain, key=lambda volume: volume.terrain_id))


def _validate_unique_terrain_ids(terrain: tuple[TerrainVolume, ...]) -> None:
    seen: set[str] = set()
    for volume in terrain:
        if volume.terrain_id in seen:
            raise GeometryError("VisibilityQuery static_terrain must not contain duplicate IDs.")
        seen.add(volume.terrain_id)


def _validate_unique_model_ids(models: tuple[Model, ...]) -> None:
    seen: set[str] = set()
    for model in models:
        if model.model_id in seen:
            raise GeometryError(
                "VisibilityQuery dynamic_model_blockers must not contain duplicate IDs."
            )
        seen.add(model.model_id)


def _validate_keyword_tuple(field_name: str, values: object) -> tuple[str, ...]:
    if type(values) is not tuple:
        raise GeometryError(f"{field_name} must be a tuple.")
    keywords: list[str] = []
    seen: set[str] = set()
    for value in cast(tuple[object, ...], values):
        keyword = validate_visibility_identifier(f"{field_name} value", value)
        if keyword != value or keyword != canonical_keyword_token(keyword):
            raise GeometryError(f"{field_name} must contain canonical catalog keyword tokens.")
        if keyword in seen:
            raise GeometryError(f"{field_name} must not contain duplicate keywords.")
        seen.add(keyword)
        keywords.append(keyword)
    return tuple(sorted(keywords))


def _validate_target_model_keywords(
    values: object,
    *,
    target_model_ids: tuple[str, ...],
) -> tuple[tuple[str, tuple[str, ...]], ...]:
    if type(values) is not tuple:
        raise GeometryError("TerrainVisibilityContext target_model_keywords must be a tuple.")
    rows: list[tuple[str, tuple[str, ...]]] = []
    seen: set[str] = set()
    for value in cast(tuple[object, ...], values):
        if type(value) is not tuple:
            raise GeometryError("Target model keyword rows must be (model_id, keywords) tuples.")
        row = cast(tuple[object, ...], value)
        if len(row) != 2:
            raise GeometryError("Target model keyword rows must be (model_id, keywords) tuples.")
        model_id = validate_visibility_identifier("Target model keyword model_id", row[0])
        if model_id in seen:
            raise GeometryError("Target model keyword rows must not duplicate model IDs.")
        seen.add(model_id)
        rows.append((model_id, _validate_keyword_tuple("Target model keyword keywords", row[1])))
    if seen != set(target_model_ids):
        raise GeometryError("Target model keyword rows must exactly match target_models.")
    return tuple(sorted(rows))


def _terrain_volume_feature_index(
    features: tuple[TerrainFeatureDefinition, ...],
) -> dict[str, TerrainFeatureDefinition]:
    index: dict[str, TerrainFeatureDefinition] = {}
    for feature in features:
        for volume in feature.terrain_volumes():
            if volume.terrain_id in index:
                raise GeometryError("Terrain feature volumes must not contain duplicate IDs.")
            index[volume.terrain_id] = feature
    return index


def _terrain_volume_blocker_record(
    *,
    terrain_id: str,
    volume_feature_index: dict[str, TerrainFeatureDefinition],
) -> VisibilityBlockerRecord:
    feature = volume_feature_index.get(terrain_id)
    return VisibilityBlockerRecord(
        blocker_kind=VisibilityBlockerKind.TERRAIN_VOLUME,
        blocker_id=terrain_id,
        terrain_feature_id=None if feature is None else feature.feature_id,
        terrain_feature_kind=None if feature is None else feature.feature_kind,
        line_of_sight_policy=LineOfSightPolicy.TRUE_LINE_OF_SIGHT,
        blocks_model_visibility=True,
        blocks_full_visibility=True,
    )


def _terrain_feature_visibility_exception(
    *,
    policy: TerrainFeatureVisibilityPolicy,
    feature: TerrainFeatureDefinition,
    observer_model: Model,
    target_model: Model,
    observer_keywords: tuple[str, ...],
    target_keywords: tuple[str, ...],
) -> str | None:
    observer_wholly_within = _model_footprint_wholly_within_feature(observer_model, feature)
    target_wholly_within = _model_footprint_wholly_within_feature(target_model, feature)
    target_intersects = _model_footprint_intersects_feature(target_model, feature)
    observer_keyword_set = set(observer_keywords)
    target_keyword_set = set(target_keywords)
    has_towering = "TOWERING" in observer_keyword_set or "TOWERING" in target_keyword_set
    if policy.aircraft_uses_true_los_through_feature and (
        "AIRCRAFT" in observer_keyword_set or "AIRCRAFT" in target_keyword_set
    ):
        return "aircraft"
    if policy.towering_uses_true_los_through_feature and has_towering:
        return "towering"
    if policy.towering_uses_true_los_when_wholly_within_feature and (
        ("TOWERING" in observer_keyword_set and observer_wholly_within)
        or ("TOWERING" in target_keyword_set and target_wholly_within)
    ):
        return "towering_wholly_within"
    if (
        policy.uses_true_los_when_observer_wholly_within_feature
        and observer_wholly_within
        and not (
            target_wholly_within
            and policy.blocks_full_visibility_through_footprint
            and not policy.blocks_model_visibility_through_footprint
        )
    ):
        return "observer_wholly_within"
    if policy.uses_true_los_when_target_intersects_feature and target_intersects:
        return "target_intersects"
    return None


def _model_footprint_intersects_feature(
    model: Model,
    feature: TerrainFeatureDefinition,
) -> bool:
    valid_model = _validate_model("model", model)
    if type(feature) is not TerrainFeatureDefinition:
        raise GeometryError("feature must be a TerrainFeatureDefinition.")
    return model_intersects_visibility_polygon(valid_model, feature.rules_footprint_points())


def _model_footprint_wholly_within_feature(
    model: Model,
    feature: TerrainFeatureDefinition,
) -> bool:
    valid_model = _validate_model("model", model)
    if type(feature) is not TerrainFeatureDefinition:
        raise GeometryError("feature must be a TerrainFeatureDefinition.")
    if not _model_footprint_intersects_feature(valid_model, feature):
        return False
    return model_within_visibility_polygons(valid_model, (feature.rules_footprint_points(),))
