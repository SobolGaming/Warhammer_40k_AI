"""Actor-only model-origin summaries for supplied deployment proposals."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from typing import cast

from warhammer40k_core.ai.deployment_candidates import DeploymentPlacementCandidate
from warhammer40k_core.ai.parameterized_training import RankedDeploymentTrainingLink
from warhammer40k_core.ai.player_policy import PlayerDecisionContext, PolicyError, payload_digest
from warhammer40k_core.ai.policy_contracts import (
    TrainingFeature,
    TrainingFeatureSourceKind,
    TrainingRow,
)
from warhammer40k_core.ai.training_candidates import TrainingCandidateLinkError
from warhammer40k_core.engine.event_log import (
    EventLogError,
    JsonValue,
    canonical_json,
    validate_json_value,
)

DEPLOYMENT_GEOMETRY_REGISTRY = "deployment-model-origin-features-v1"
DEPLOYMENT_GEOMETRY_SCHEMA = "deployment-model-origin-observation-v1"
DEPLOYMENT_GEOMETRY_SOURCE = "encoder:" + DEPLOYMENT_GEOMETRY_REGISTRY


class DeploymentGeometryError(PolicyError):
    """Geometry inputs or their exact candidate/row bindings are unsupported."""


@dataclass(frozen=True, slots=True)
class DeploymentGeometryDefinition:
    feature_id: str
    value_kind: str
    unit: str
    dimensions: tuple[int, ...]
    aggregation: str

    def to_payload(self) -> dict[str, JsonValue]:
        return {
            "feature_id": self.feature_id,
            "source_kind": TrainingFeatureSourceKind.DECISION_CONTEXT.value,
            "value_kind": self.value_kind,
            "unit": self.unit,
            "dimensions": list(self.dimensions),
            "aggregation": self.aggregation,
            "coordinate_frame": "battlefield-world-xyz",
            "information_scope": "actor_view",
            "vocabulary_version": None,
        }


DEPLOYMENT_GEOMETRY_FEATURES = (
    DeploymentGeometryDefinition("deployment-model-count", "integer", "count", (), "count"),
    DeploymentGeometryDefinition(
        "deployment-origin-centroid", "real", "inches", (3,), "unweighted-model-origin-mean"
    ),
    DeploymentGeometryDefinition(
        "deployment-origin-span", "real", "inches", (3,), "model-origin-max-minus-min"
    ),
)


def _number(value: object) -> float:
    if type(value) not in (int, float):
        raise DeploymentGeometryError("Model-origin coordinates require finite numbers.")
    try:
        result = float(cast(int | float, value))
    except OverflowError as exc:
        raise DeploymentGeometryError("Model-origin coordinates exceed numeric range.") from exc
    if not math.isfinite(result):
        raise DeploymentGeometryError("Model-origin coordinates require finite numbers.")
    return 0.0 if result == 0 else result


def _positions(proposal: JsonValue) -> tuple[tuple[float, float, float], ...]:
    if not isinstance(proposal, dict):
        raise DeploymentGeometryError("Deployment geometry requires a proposal object.")
    placements = proposal.get("model_placements")
    if not isinstance(placements, list) or not placements:
        raise DeploymentGeometryError("Deployment geometry requires model placements.")
    positions: list[tuple[float, float, float]] = []
    seen: set[str] = set()
    for placement in placements:
        if not isinstance(placement, dict):
            raise DeploymentGeometryError("Deployment geometry requires model placement objects.")
        model_id = placement.get("model_instance_id")
        if type(model_id) is not str or not model_id.strip() or model_id in seen:
            raise DeploymentGeometryError("Deployment geometry requires distinct model references.")
        seen.add(model_id)
        pose = placement.get("pose")
        if not isinstance(pose, dict):
            raise DeploymentGeometryError("Deployment geometry requires model poses.")
        position = pose.get("position")
        if not isinstance(position, dict) or set(position) != {"x", "y", "z"}:
            raise DeploymentGeometryError("Deployment geometry requires XYZ model origins.")
        positions.append((_number(position["x"]), _number(position["y"]), _number(position["z"])))
    # Numerical reduction order is geometric, never model identity or proposal order.
    return tuple(sorted(positions))


@dataclass(frozen=True, slots=True, init=False)
class DeploymentGeometryObservation:
    """Numeric proposal summaries, not physical footprints or acceptance evidence.

    All proposed models contribute once, including attached components. Absolute
    world XYZ origins are retained without actor-relative rotation, normalization,
    base sizes, facing, terrain or objective assumptions. Unknown required feature
    definitions fail on loading. Only the pinned numeric values are model inputs.
    """

    _payload_json: str
    model_inputs: tuple[int | float, ...]

    def __init__(self) -> None:
        raise DeploymentGeometryError("Derive geometry from a bound deployment candidate.")

    @classmethod
    def from_candidate(
        cls, candidate: DeploymentPlacementCandidate, *, context: PlayerDecisionContext
    ) -> DeploymentGeometryObservation:
        if type(candidate) is not DeploymentPlacementCandidate:
            raise DeploymentGeometryError("Deployment geometry requires a typed candidate.")
        candidate.select(context)
        payload = candidate.to_payload()
        positions = _positions(payload["proposal"])
        count = len(positions)
        try:
            centroid = [
                _number(math.fsum(point[axis] / count for point in positions)) for axis in range(3)
            ]
            span = [
                _number(max(p[axis] for p in positions) - min(p[axis] for p in positions))
                for axis in range(3)
            ]
        except OverflowError as exc:
            raise DeploymentGeometryError("Model-origin summary exceeds numeric range.") from exc
        values: list[JsonValue] = [count, list(centroid), list(span)]
        result = object.__new__(cls)
        object.__setattr__(result, "model_inputs", (count, *centroid, *span))
        object.__setattr__(
            result,
            "_payload_json",
            canonical_json(
                {
                    "schema_version": DEPLOYMENT_GEOMETRY_SCHEMA,
                    "registry_version": DEPLOYMENT_GEOMETRY_REGISTRY,
                    "actor_id": payload["actor_id"],
                    "request_id": payload["request_id"],
                    "observation_hash": payload["observation_hash"],
                    "candidate_id": payload["candidate_id"],
                    "candidate_hash": candidate.content_hash,
                    "features": [
                        {"definition": definition.to_payload(), "value": value}
                        for definition, value in zip(
                            DEPLOYMENT_GEOMETRY_FEATURES, values, strict=True
                        )
                    ],
                }
            ),
        )
        return result

    def to_payload(self) -> dict[str, JsonValue]:
        return cast(dict[str, JsonValue], json.loads(self._payload_json))

    def training_features(self) -> tuple[TrainingFeature, ...]:
        features = cast(list[dict[str, JsonValue]], self.to_payload()["features"])
        return tuple(
            TrainingFeature(
                definition.feature_id,
                TrainingFeatureSourceKind.DECISION_CONTEXT,
                feature["value"],
                (DEPLOYMENT_GEOMETRY_SOURCE,),
            )
            for definition, feature in zip(DEPLOYMENT_GEOMETRY_FEATURES, features, strict=True)
        )

    @classmethod
    def from_payload(
        cls,
        payload: object,
        *,
        candidate: DeploymentPlacementCandidate,
        context: PlayerDecisionContext,
    ) -> DeploymentGeometryObservation:
        expected = cls.from_candidate(candidate, context=context)
        _require_payload(payload, expected.to_payload())
        return expected


@dataclass(frozen=True, slots=True, init=False)
class DeploymentTrainingGeometry:
    """Operator-only exact selected-row semantic join; no dataset eligibility claim."""

    observation: DeploymentGeometryObservation
    _payload_json: str

    def __init__(self) -> None:
        raise DeploymentGeometryError("Join geometry through ranked accepted row evidence.")

    @classmethod
    def from_link(
        cls, link: RankedDeploymentTrainingLink, *, row: TrainingRow, context: PlayerDecisionContext
    ) -> DeploymentTrainingGeometry:
        if type(link) is not RankedDeploymentTrainingLink:
            raise DeploymentGeometryError(
                "Deployment geometry requires a typed ranked training link."
            )
        try:
            link.require_matches(row, context=context)
        except TrainingCandidateLinkError as exc:
            raise DeploymentGeometryError("Deployment geometry training binding drifted.") from exc
        candidate_link = link.candidate_link
        candidate = candidate_link.validated.candidate_set.candidates[
            candidate_link.chosen_action_index
        ]
        observation = DeploymentGeometryObservation.from_candidate(candidate, context=context)
        # Canonical bytes distinguish booleans from numbers and scalar/vector shape.
        if canonical_json(
            [feature.to_payload() for feature in row.input_features]
        ) != canonical_json([feature.to_payload() for feature in observation.training_features()]):
            raise DeploymentGeometryError("Deployment row feature semantics or provenance drifted.")
        result = object.__new__(cls)
        object.__setattr__(result, "observation", observation)
        object.__setattr__(
            result,
            "_payload_json",
            canonical_json(
                {
                    "schema_version": "deployment-training-geometry-v1",
                    "ranked_training_link_hash": payload_digest(link.to_payload()),
                    "observation": observation.to_payload(),
                }
            ),
        )
        return result

    def to_payload(self) -> dict[str, JsonValue]:
        return cast(dict[str, JsonValue], json.loads(self._payload_json))

    @classmethod
    def from_payload(
        cls,
        payload: object,
        *,
        link: RankedDeploymentTrainingLink,
        row: TrainingRow,
        context: PlayerDecisionContext,
    ) -> DeploymentTrainingGeometry:
        expected = cls.from_link(link, row=row, context=context)
        _require_payload(payload, expected.to_payload())
        return expected


def _require_payload(payload: object, expected: dict[str, JsonValue]) -> None:
    try:
        observed = canonical_json(validate_json_value(payload))
    except EventLogError as exc:
        raise DeploymentGeometryError("Deployment geometry evidence must be JSON-safe.") from exc
    if observed != canonical_json(expected):
        raise DeploymentGeometryError("Deployment geometry evidence or definitions drifted.")
