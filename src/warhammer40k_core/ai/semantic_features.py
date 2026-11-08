"""Closed semantic inputs derived only from detached finite actor observations."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TypedDict, cast

from warhammer40k_core.ai.finite_candidates import FiniteCandidateSet
from warhammer40k_core.ai.player_policy import PlayerDecisionContext, PolicyError, payload_digest
from warhammer40k_core.ai.policy_contracts import (
    PolicyProvenanceError,
    TrainingFeatureSourceKind,
    TrainingRow,
)
from warhammer40k_core.ai.training_candidates import (
    FiniteTrainingCandidateLink,
    TrainingCandidateLinkError,
)
from warhammer40k_core.core.validation import IdentifierValidator

FEATURE_REGISTRY_VERSION = "finite-semantic-features-v1"
OBSERVATION_SCHEMA_VERSION = "finite-semantic-observation-v1"
TRAINING_OBSERVATION_SCHEMA_VERSION = "finite-training-observation-v1"


class SemanticFeatureError(PolicyProvenanceError):
    """A required feature, information scope or observation join is unsupported."""


class FeatureValueKind(StrEnum):
    INTEGER = "integer"


class FeatureUnit(StrEnum):
    COUNT = "count"


class FeatureInformationScope(StrEnum):
    ACTOR_VIEW = "actor_view"


class SemanticFeatureDefinitionPayload(TypedDict):
    feature_id: str
    source_kind: str
    value_kind: str
    unit: str
    dimensions: list[int]
    information_scope: str
    vocabulary_version: str | None


@dataclass(frozen=True, slots=True)
class SemanticFeatureDefinition:
    """V1 admits one scalar count; no free-form strings or entity vocabularies.

    Dimensions describe tensor shape: an empty tuple is one scalar. Actor-view
    scope permits the actor's own information; it does not assert that their
    pending options are visible to opponents.
    """

    feature_id: str
    source_kind: TrainingFeatureSourceKind
    value_kind: FeatureValueKind
    unit: FeatureUnit
    dimensions: tuple[int, ...]
    information_scope: FeatureInformationScope
    vocabulary_version: str | None

    def __post_init__(self) -> None:
        if (
            type(self.feature_id) is not str
            or self.feature_id != "decision-option-count"
            or type(self.source_kind) is not TrainingFeatureSourceKind
            or self.source_kind is not TrainingFeatureSourceKind.DECISION_CONTEXT
            or type(self.value_kind) is not FeatureValueKind
            or self.value_kind is not FeatureValueKind.INTEGER
            or type(self.unit) is not FeatureUnit
            or self.unit is not FeatureUnit.COUNT
            or type(self.dimensions) is not tuple
            or self.dimensions != ()
            or type(self.information_scope) is not FeatureInformationScope
            or self.information_scope is not FeatureInformationScope.ACTOR_VIEW
            or self.vocabulary_version is not None
        ):
            raise SemanticFeatureError("Unsupported semantic feature definition.")

    def to_payload(self) -> SemanticFeatureDefinitionPayload:
        return {
            "feature_id": self.feature_id,
            "source_kind": self.source_kind.value,
            "value_kind": self.value_kind.value,
            "unit": self.unit.value,
            "dimensions": list(self.dimensions),
            "information_scope": self.information_scope.value,
            "vocabulary_version": self.vocabulary_version,
        }

    @classmethod
    def from_payload(cls, payload: object) -> SemanticFeatureDefinition:
        value = _object(payload, SemanticFeatureDefinitionPayload.__annotations__)
        # Compare to the entire pinned definition, not just an identifier. No
        # caller-supplied replacement of units, scope, dimensions or vocabulary.
        expected = FINITE_FEATURE_REGISTRY[0]
        if value != expected.to_payload():
            raise SemanticFeatureError("Unsupported semantic feature definition.")
        return expected


FINITE_FEATURE_REGISTRY = (
    SemanticFeatureDefinition(
        feature_id="decision-option-count",
        source_kind=TrainingFeatureSourceKind.DECISION_CONTEXT,
        value_kind=FeatureValueKind.INTEGER,
        unit=FeatureUnit.COUNT,
        dimensions=(),
        information_scope=FeatureInformationScope.ACTOR_VIEW,
        vocabulary_version=None,
    ),
)


class SemanticFeatureValuePayload(TypedDict):
    definition: SemanticFeatureDefinitionPayload
    value: int


@dataclass(frozen=True, slots=True)
class SemanticFeatureValue:
    definition: SemanticFeatureDefinition
    value: int

    def __post_init__(self) -> None:
        if type(self.definition) is not SemanticFeatureDefinition:
            raise SemanticFeatureError("Semantic values require a typed definition.")
        if type(self.value) is not int or self.value < 1:
            raise SemanticFeatureError("Finite option counts require a positive integer.")

    def to_payload(self) -> SemanticFeatureValuePayload:
        return {"definition": self.definition.to_payload(), "value": self.value}

    @classmethod
    def from_payload(cls, payload: object) -> SemanticFeatureValue:
        value = _object(payload, SemanticFeatureValuePayload.__annotations__)
        return cls(
            SemanticFeatureDefinition.from_payload(value["definition"]),
            cast(int, value["value"]),
        )


class SemanticObservationPayload(TypedDict):
    schema_version: str
    registry_version: str
    actor_id: str
    request_id: str
    observation_hash: str
    features: list[SemanticFeatureValuePayload]


@dataclass(frozen=True, slots=True)
class SemanticObservation:
    """Immutable inputs plus separately named linkage, never raw option payloads."""

    actor_id: str
    request_id: str
    observation_hash: str
    features: tuple[SemanticFeatureValue, ...]

    def __post_init__(self) -> None:
        _identifier("Semantic observation actor", self.actor_id)
        _identifier("Semantic observation request", self.request_id)
        _sha256(self.observation_hash)
        if (
            type(self.features) is not tuple
            or any(type(feature) is not SemanticFeatureValue for feature in self.features)
            or tuple(feature.definition for feature in self.features) != FINITE_FEATURE_REGISTRY
        ):
            raise SemanticFeatureError("Semantic observation requires the exact registry.")

    @classmethod
    def from_context(cls, context: PlayerDecisionContext) -> SemanticObservation:
        if type(context) is not PlayerDecisionContext:
            raise SemanticFeatureError("Semantic observation requires a player context.")
        try:
            candidates = FiniteCandidateSet.from_context(context)
        except PolicyError as exc:
            raise SemanticFeatureError("Semantic observation requires a finite view.") from exc
        return cls(
            candidates.actor_id,
            candidates.request_id,
            candidates.observation_hash,
            (SemanticFeatureValue(FINITE_FEATURE_REGISTRY[0], len(candidates.candidates)),),
        )

    @property
    def model_inputs(self) -> tuple[int, ...]:
        """Only registered numeric values, in pinned registry order."""
        return tuple(feature.value for feature in self.features)

    def to_payload(self) -> SemanticObservationPayload:
        return {
            "schema_version": OBSERVATION_SCHEMA_VERSION,
            "registry_version": FEATURE_REGISTRY_VERSION,
            "actor_id": self.actor_id,
            "request_id": self.request_id,
            "observation_hash": self.observation_hash,
            "features": [feature.to_payload() for feature in self.features],
        }

    @classmethod
    def from_payload(
        cls, payload: object, *, context: PlayerDecisionContext
    ) -> SemanticObservation:
        value = _object(payload, SemanticObservationPayload.__annotations__)
        if (
            value["schema_version"] != OBSERVATION_SCHEMA_VERSION
            or value["registry_version"] != FEATURE_REGISTRY_VERSION
            or type(value["features"]) is not list
        ):
            raise SemanticFeatureError("Unsupported semantic observation schema or registry.")
        result = cls(
            actor_id=_identifier("Semantic observation actor", value["actor_id"]),
            request_id=_identifier("Semantic observation request", value["request_id"]),
            observation_hash=_sha256(value["observation_hash"]),
            features=tuple(
                SemanticFeatureValue.from_payload(feature)
                for feature in cast(list[object], value["features"])
            ),
        )
        if result != cls.from_context(context):
            raise SemanticFeatureError("Semantic observation binding or derived values drifted.")
        return result


class FiniteTrainingObservationPayload(TypedDict):
    schema_version: str
    training_candidate_link_hash: str
    observation: SemanticObservationPayload


@dataclass(frozen=True, slots=True)
class FiniteTrainingObservation:
    """Offline semantic join; no accepted-transition or dataset admission claim."""

    training_candidate_link_hash: str
    observation: SemanticObservation

    def __post_init__(self) -> None:
        _sha256(self.training_candidate_link_hash)
        if type(self.observation) is not SemanticObservation:
            raise SemanticFeatureError("Training observation requires a typed observation.")

    @classmethod
    def from_link(
        cls, link: FiniteTrainingCandidateLink, *, row: TrainingRow, context: PlayerDecisionContext
    ) -> FiniteTrainingObservation:
        if type(link) is not FiniteTrainingCandidateLink:
            raise SemanticFeatureError("Semantic linkage requires a finite training link.")
        observation = SemanticObservation.from_context(context)
        result = cls(payload_digest(link.to_payload()), observation)
        result.require_matches(link, row=row, context=context)
        return result

    def require_matches(
        self, link: FiniteTrainingCandidateLink, *, row: TrainingRow, context: PlayerDecisionContext
    ) -> None:
        if type(link) is not FiniteTrainingCandidateLink:
            raise SemanticFeatureError("Semantic linkage requires a finite training link.")
        try:
            link.require_matches(row, context=context)
        except TrainingCandidateLinkError as exc:
            raise SemanticFeatureError("Semantic training row/candidate binding drifted.") from exc
        if self.training_candidate_link_hash != payload_digest(link.to_payload()):
            raise SemanticFeatureError("Semantic training candidate link drifted.")
        if self.observation != SemanticObservation.from_context(context):
            raise SemanticFeatureError("Semantic observation binding or derived values drifted.")
        # Legacy rows are read, never rewritten. All required inputs must match
        # this encoder; an unknown operator or extra identity feature fails.
        if len(row.input_features) != len(self.observation.features):
            raise SemanticFeatureError("Unsupported required training features.")
        for legacy, feature in zip(row.input_features, self.observation.features, strict=True):
            if (
                legacy.feature_id != feature.definition.feature_id
                or legacy.source_kind is not feature.definition.source_kind
                or type(legacy.value) is not int
                or legacy.value != feature.value
                or legacy.source_descriptor_ids != ("decision:" + context.route.decision_type,)
            ):
                raise SemanticFeatureError("Training feature semantics or provenance drifted.")

    def to_payload(self) -> FiniteTrainingObservationPayload:
        return {
            "schema_version": TRAINING_OBSERVATION_SCHEMA_VERSION,
            "training_candidate_link_hash": self.training_candidate_link_hash,
            "observation": self.observation.to_payload(),
        }

    @property
    def content_hash(self) -> str:
        return payload_digest(self.to_payload())

    @classmethod
    def from_payload(
        cls,
        payload: object,
        *,
        link: FiniteTrainingCandidateLink,
        row: TrainingRow,
        context: PlayerDecisionContext,
    ) -> FiniteTrainingObservation:
        value = _object(payload, FiniteTrainingObservationPayload.__annotations__)
        if value["schema_version"] != TRAINING_OBSERVATION_SCHEMA_VERSION:
            raise SemanticFeatureError("Unsupported training observation schema.")
        result = cls(
            _sha256(value["training_candidate_link_hash"]),
            SemanticObservation.from_payload(value["observation"], context=context),
        )
        result.require_matches(link, row=row, context=context)
        return result


def _object(payload: object, fields: dict[str, object]) -> dict[str, object]:
    if not isinstance(payload, dict) or payload.keys() != fields.keys():
        raise SemanticFeatureError("Semantic contract has missing or unknown fields.")
    return cast(dict[str, object], payload)


def _sha256(value: object) -> str:
    if type(value) is not str or len(value) != 64 or set(value) - set("0123456789abcdef"):
        raise SemanticFeatureError("Semantic observation hashes must be lowercase SHA-256.")
    return value


_identifier = IdentifierValidator(SemanticFeatureError)
