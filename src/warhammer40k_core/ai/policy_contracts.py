from __future__ import annotations

import hashlib
from dataclasses import dataclass
from enum import StrEnum
from typing import Self, TypedDict, cast

from warhammer40k_core import __version__ as ENGINE_VERSION
from warhammer40k_core.core.ruleset import RulesetId, RulesetIdPayload
from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine.event_log import (
    EventLogError,
    JsonValue,
    canonical_json,
    validate_json_value,
)
from warhammer40k_core.engine.game_state import GameConfig

POLICY_PROVENANCE_SCHEMA_VERSION = "policy-provenance-v1-phase19e"
TRAINING_ROW_SCHEMA_VERSION = "training-row-v1-phase19e"

_IDENTITY_FEATURE_TOKENS = frozenset(
    {
        "army_id",
        "datasheet_id",
        "datasheet_identity",
        "detachment_id",
        "faction_id",
        "model_id",
        "source_unit_id",
        "unit_id",
        "unit_instance_id",
        "unit_name",
    }
)


class PolicyProvenanceError(ValueError):
    """Raised when a Phase 19 policy contract is invalid or stale."""


class PolicyArtifactKind(StrEnum):
    GENERAL = "general"
    COMMANDER = "commander"
    RANKER = "ranker"
    EVALUATION_FUNCTION = "evaluation_function"


class TrainingFeatureSourceKind(StrEnum):
    STATLINE = "statline"
    KEYWORD = "keyword"
    WEAPON_PROFILE = "weapon_profile"
    POINTS = "points"
    ABILITY_IR = "ability_ir"
    BOARD_STATE = "board_state"
    DECISION_CONTEXT = "decision_context"
    MISSION_STATE = "mission_state"
    RULES_STATE = "rules_state"


class CatalogPackageProvenancePayload(TypedDict):
    catalog_id: str
    source_package_id: str
    catalog_hash: str


class PolicyProvenancePayload(TypedDict):
    schema_version: str
    artifact_id: str
    artifact_kind: str
    catalog_packages: list[CatalogPackageProvenancePayload]
    ruleset_id: RulesetIdPayload
    ruleset_descriptor_hash: str
    engine_version: str
    reward_profile_version: str


class PolicyCompatibilityRecordPayload(TypedDict):
    policy_artifact_id: str
    allow_cross_version: bool
    mismatch_fields: list[str]
    expected: PolicyProvenancePayload
    actual: PolicyProvenancePayload


class TrainingFeaturePayload(TypedDict):
    feature_id: str
    source_kind: str
    value: JsonValue
    source_descriptor_ids: list[str]


class TrainingRowPayload(TypedDict):
    schema_version: str
    row_id: str
    game_id: str
    decision_record_id: str
    policy_artifact_id: str
    policy_provenance: PolicyProvenancePayload
    reward_profile_version: str
    input_features: list[TrainingFeaturePayload]
    legal_action_mask: list[bool]
    chosen_action_id: str
    target_value: float
    debug_metadata: dict[str, JsonValue]


@dataclass(frozen=True, slots=True)
class CatalogPackageProvenance:
    catalog_id: str
    source_package_id: str
    catalog_hash: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "catalog_id",
            _validate_identifier("CatalogPackageProvenance catalog_id", self.catalog_id),
        )
        object.__setattr__(
            self,
            "source_package_id",
            _validate_identifier(
                "CatalogPackageProvenance source_package_id",
                self.source_package_id,
            ),
        )
        object.__setattr__(
            self,
            "catalog_hash",
            _validate_sha256("CatalogPackageProvenance catalog_hash", self.catalog_hash),
        )

    @classmethod
    def from_game_config(cls, config: GameConfig) -> Self:
        if type(config) is not GameConfig:
            raise PolicyProvenanceError("Catalog package provenance requires a GameConfig.")
        catalog = config.army_catalog
        return cls(
            catalog_id=catalog.catalog_id,
            source_package_id=catalog.source_package_id,
            catalog_hash=_payload_hash(catalog.to_payload()),
        )

    def to_payload(self) -> CatalogPackageProvenancePayload:
        return {
            "catalog_id": self.catalog_id,
            "source_package_id": self.source_package_id,
            "catalog_hash": self.catalog_hash,
        }

    @classmethod
    def from_payload(cls, payload: CatalogPackageProvenancePayload) -> Self:
        return cls(
            catalog_id=payload["catalog_id"],
            source_package_id=payload["source_package_id"],
            catalog_hash=payload["catalog_hash"],
        )


@dataclass(frozen=True, slots=True)
class PolicyProvenance:
    artifact_id: str
    artifact_kind: PolicyArtifactKind
    catalog_packages: tuple[CatalogPackageProvenance, ...]
    ruleset_id: RulesetId
    ruleset_descriptor_hash: str
    engine_version: str
    reward_profile_version: str
    schema_version: str = POLICY_PROVENANCE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "schema_version",
            _validate_policy_schema_version(self.schema_version),
        )
        object.__setattr__(
            self,
            "artifact_id",
            _validate_identifier("PolicyProvenance artifact_id", self.artifact_id),
        )
        object.__setattr__(
            self,
            "artifact_kind",
            policy_artifact_kind_from_token(self.artifact_kind),
        )
        object.__setattr__(
            self,
            "catalog_packages",
            _validate_catalog_package_tuple(self.catalog_packages),
        )
        if type(self.ruleset_id) is not RulesetId:
            raise PolicyProvenanceError("PolicyProvenance ruleset_id must be a RulesetId.")
        object.__setattr__(
            self,
            "ruleset_descriptor_hash",
            _validate_sha256(
                "PolicyProvenance ruleset_descriptor_hash",
                self.ruleset_descriptor_hash,
            ),
        )
        object.__setattr__(
            self,
            "engine_version",
            _validate_identifier("PolicyProvenance engine_version", self.engine_version),
        )
        object.__setattr__(
            self,
            "reward_profile_version",
            _validate_identifier(
                "PolicyProvenance reward_profile_version",
                self.reward_profile_version,
            ),
        )

    @classmethod
    def from_game_config(
        cls,
        *,
        artifact_id: str,
        artifact_kind: PolicyArtifactKind | str,
        game_config: GameConfig,
        reward_profile_version: str,
        engine_version: str = ENGINE_VERSION,
    ) -> Self:
        if type(game_config) is not GameConfig:
            raise PolicyProvenanceError("Policy provenance requires a GameConfig.")
        return cls(
            artifact_id=artifact_id,
            artifact_kind=policy_artifact_kind_from_token(artifact_kind),
            catalog_packages=(CatalogPackageProvenance.from_game_config(game_config),),
            ruleset_id=game_config.ruleset_descriptor.ruleset_id,
            ruleset_descriptor_hash=game_config.ruleset_descriptor.descriptor_hash,
            engine_version=engine_version,
            reward_profile_version=reward_profile_version,
        )

    def to_payload(self) -> PolicyProvenancePayload:
        return {
            "schema_version": self.schema_version,
            "artifact_id": self.artifact_id,
            "artifact_kind": self.artifact_kind.value,
            "catalog_packages": [catalog.to_payload() for catalog in self.catalog_packages],
            "ruleset_id": self.ruleset_id.to_payload(),
            "ruleset_descriptor_hash": self.ruleset_descriptor_hash,
            "engine_version": self.engine_version,
            "reward_profile_version": self.reward_profile_version,
        }

    @classmethod
    def from_payload(cls, payload: PolicyProvenancePayload) -> Self:
        return cls(
            schema_version=payload["schema_version"],
            artifact_id=payload["artifact_id"],
            artifact_kind=policy_artifact_kind_from_token(payload["artifact_kind"]),
            catalog_packages=tuple(
                CatalogPackageProvenance.from_payload(catalog)
                for catalog in payload["catalog_packages"]
            ),
            ruleset_id=RulesetId.from_payload(payload["ruleset_id"]),
            ruleset_descriptor_hash=payload["ruleset_descriptor_hash"],
            engine_version=payload["engine_version"],
            reward_profile_version=payload["reward_profile_version"],
        )

    def require_compatible_game_config(
        self,
        *,
        game_config: GameConfig,
        reward_profile_version: str,
        engine_version: str = ENGINE_VERSION,
        allow_cross_version: bool = False,
    ) -> PolicyCompatibilityRecord:
        actual = PolicyProvenance.from_game_config(
            artifact_id=self.artifact_id,
            artifact_kind=self.artifact_kind,
            game_config=game_config,
            reward_profile_version=reward_profile_version,
            engine_version=engine_version,
        )
        mismatch_fields = self.mismatch_fields_against(actual)
        if mismatch_fields and not allow_cross_version:
            raise PolicyProvenanceError(
                "Policy provenance does not match the requested game config: "
                + ", ".join(mismatch_fields)
            )
        return PolicyCompatibilityRecord(
            policy_artifact_id=self.artifact_id,
            allow_cross_version=allow_cross_version,
            mismatch_fields=mismatch_fields,
            expected=self,
            actual=actual,
        )

    def mismatch_fields_against(self, actual: PolicyProvenance) -> tuple[str, ...]:
        if type(actual) is not PolicyProvenance:
            raise PolicyProvenanceError(
                "PolicyProvenance mismatch comparison requires PolicyProvenance."
            )
        mismatches: list[str] = []
        if self.catalog_packages != actual.catalog_packages:
            mismatches.append("catalog_packages")
        if self.ruleset_id != actual.ruleset_id:
            mismatches.append("ruleset_id")
        if self.ruleset_descriptor_hash != actual.ruleset_descriptor_hash:
            mismatches.append("ruleset_descriptor_hash")
        if self.engine_version != actual.engine_version:
            mismatches.append("engine_version")
        if self.reward_profile_version != actual.reward_profile_version:
            mismatches.append("reward_profile_version")
        return tuple(mismatches)


@dataclass(frozen=True, slots=True)
class PolicyCompatibilityRecord:
    policy_artifact_id: str
    allow_cross_version: bool
    mismatch_fields: tuple[str, ...]
    expected: PolicyProvenance
    actual: PolicyProvenance

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "policy_artifact_id",
            _validate_identifier(
                "PolicyCompatibilityRecord policy_artifact_id",
                self.policy_artifact_id,
            ),
        )
        if type(self.allow_cross_version) is not bool:
            raise PolicyProvenanceError(
                "PolicyCompatibilityRecord allow_cross_version must be a bool."
            )
        object.__setattr__(
            self,
            "mismatch_fields",
            _validate_identifier_tuple(
                "PolicyCompatibilityRecord mismatch_fields",
                self.mismatch_fields,
                allow_empty=True,
            ),
        )
        if type(self.expected) is not PolicyProvenance:
            raise PolicyProvenanceError("PolicyCompatibilityRecord expected is invalid.")
        if type(self.actual) is not PolicyProvenance:
            raise PolicyProvenanceError("PolicyCompatibilityRecord actual is invalid.")
        if self.policy_artifact_id != self.expected.artifact_id:
            raise PolicyProvenanceError(
                "PolicyCompatibilityRecord policy_artifact_id must match expected."
            )
        if self.policy_artifact_id != self.actual.artifact_id:
            raise PolicyProvenanceError(
                "PolicyCompatibilityRecord policy_artifact_id must match actual."
            )
        expected_mismatches = _validate_identifier_tuple(
            "PolicyCompatibilityRecord expected mismatch_fields",
            self.expected.mismatch_fields_against(self.actual),
            allow_empty=True,
        )
        if self.mismatch_fields != expected_mismatches:
            raise PolicyProvenanceError(
                "PolicyCompatibilityRecord mismatch_fields must match expected/actual provenance."
            )
        if self.mismatch_fields and not self.allow_cross_version:
            raise PolicyProvenanceError(
                "PolicyCompatibilityRecord provenance mismatch requires cross-version override."
            )

    def to_payload(self) -> PolicyCompatibilityRecordPayload:
        return {
            "policy_artifact_id": self.policy_artifact_id,
            "allow_cross_version": self.allow_cross_version,
            "mismatch_fields": list(self.mismatch_fields),
            "expected": self.expected.to_payload(),
            "actual": self.actual.to_payload(),
        }

    @property
    def has_mismatch(self) -> bool:
        return bool(self.mismatch_fields)


@dataclass(frozen=True, slots=True)
class TrainingFeature:
    feature_id: str
    source_kind: TrainingFeatureSourceKind
    value: JsonValue
    source_descriptor_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        feature_id = _validate_identifier("TrainingFeature feature_id", self.feature_id)
        _reject_identity_feature_identifier("TrainingFeature feature_id", feature_id)
        object.__setattr__(self, "feature_id", feature_id)
        object.__setattr__(
            self,
            "source_kind",
            training_feature_source_kind_from_token(self.source_kind),
        )
        object.__setattr__(self, "value", _validate_feature_value(self.value))
        object.__setattr__(
            self,
            "source_descriptor_ids",
            _validate_identifier_tuple(
                "TrainingFeature source_descriptor_ids",
                self.source_descriptor_ids,
                allow_empty=True,
            ),
        )

    def to_payload(self) -> TrainingFeaturePayload:
        return {
            "feature_id": self.feature_id,
            "source_kind": self.source_kind.value,
            "value": self.value,
            "source_descriptor_ids": list(self.source_descriptor_ids),
        }

    @classmethod
    def from_payload(cls, payload: TrainingFeaturePayload) -> Self:
        return cls(
            feature_id=payload["feature_id"],
            source_kind=training_feature_source_kind_from_token(payload["source_kind"]),
            value=payload["value"],
            source_descriptor_ids=tuple(payload["source_descriptor_ids"]),
        )


@dataclass(frozen=True, slots=True)
class TrainingRow:
    row_id: str
    game_id: str
    decision_record_id: str
    policy_artifact_id: str
    policy_provenance: PolicyProvenance
    reward_profile_version: str
    input_features: tuple[TrainingFeature, ...]
    legal_action_mask: tuple[bool, ...]
    chosen_action_id: str
    target_value: float
    debug_metadata: dict[str, JsonValue]
    schema_version: str = TRAINING_ROW_SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "schema_version",
            _validate_training_row_schema_version(self.schema_version),
        )
        object.__setattr__(self, "row_id", _validate_identifier("TrainingRow row_id", self.row_id))
        object.__setattr__(
            self,
            "game_id",
            _validate_identifier("TrainingRow game_id", self.game_id),
        )
        object.__setattr__(
            self,
            "decision_record_id",
            _validate_identifier("TrainingRow decision_record_id", self.decision_record_id),
        )
        object.__setattr__(
            self,
            "policy_artifact_id",
            _validate_identifier("TrainingRow policy_artifact_id", self.policy_artifact_id),
        )
        if type(self.policy_provenance) is not PolicyProvenance:
            raise PolicyProvenanceError("TrainingRow policy_provenance is invalid.")
        if self.policy_artifact_id != self.policy_provenance.artifact_id:
            raise PolicyProvenanceError(
                "TrainingRow policy_artifact_id must match policy provenance."
            )
        reward_profile_version = _validate_identifier(
            "TrainingRow reward_profile_version",
            self.reward_profile_version,
        )
        if reward_profile_version != self.policy_provenance.reward_profile_version:
            raise PolicyProvenanceError(
                "TrainingRow reward_profile_version must match policy provenance."
            )
        object.__setattr__(self, "reward_profile_version", reward_profile_version)
        object.__setattr__(
            self,
            "input_features",
            _validate_training_feature_tuple(self.input_features),
        )
        object.__setattr__(
            self,
            "legal_action_mask",
            _validate_bool_tuple("TrainingRow legal_action_mask", self.legal_action_mask),
        )
        object.__setattr__(
            self,
            "chosen_action_id",
            _validate_identifier("TrainingRow chosen_action_id", self.chosen_action_id),
        )
        if type(self.target_value) not in {float, int}:
            raise PolicyProvenanceError("TrainingRow target_value must be numeric.")
        object.__setattr__(self, "target_value", float(self.target_value))
        object.__setattr__(
            self,
            "debug_metadata",
            _validate_debug_metadata(self.debug_metadata),
        )

    def to_payload(self) -> TrainingRowPayload:
        return {
            "schema_version": self.schema_version,
            "row_id": self.row_id,
            "game_id": self.game_id,
            "decision_record_id": self.decision_record_id,
            "policy_artifact_id": self.policy_artifact_id,
            "policy_provenance": self.policy_provenance.to_payload(),
            "reward_profile_version": self.reward_profile_version,
            "input_features": [feature.to_payload() for feature in self.input_features],
            "legal_action_mask": list(self.legal_action_mask),
            "chosen_action_id": self.chosen_action_id,
            "target_value": self.target_value,
            "debug_metadata": self.debug_metadata,
        }

    @classmethod
    def from_payload(cls, payload: TrainingRowPayload) -> Self:
        return cls(
            schema_version=payload["schema_version"],
            row_id=payload["row_id"],
            game_id=payload["game_id"],
            decision_record_id=payload["decision_record_id"],
            policy_artifact_id=payload["policy_artifact_id"],
            policy_provenance=PolicyProvenance.from_payload(payload["policy_provenance"]),
            reward_profile_version=payload["reward_profile_version"],
            input_features=tuple(
                TrainingFeature.from_payload(feature) for feature in payload["input_features"]
            ),
            legal_action_mask=tuple(payload["legal_action_mask"]),
            chosen_action_id=payload["chosen_action_id"],
            target_value=payload["target_value"],
            debug_metadata=payload["debug_metadata"],
        )


def policy_artifact_kind_from_token(token: PolicyArtifactKind | str) -> PolicyArtifactKind:
    if type(token) is PolicyArtifactKind:
        return token
    if type(token) is not str:
        raise PolicyProvenanceError("PolicyArtifactKind token must be a string.")
    try:
        return PolicyArtifactKind(token)
    except ValueError as exc:
        raise PolicyProvenanceError(f"Unsupported PolicyArtifactKind token: {token}.") from exc


def training_feature_source_kind_from_token(
    token: TrainingFeatureSourceKind | str,
) -> TrainingFeatureSourceKind:
    if type(token) is TrainingFeatureSourceKind:
        return token
    if type(token) is not str:
        raise PolicyProvenanceError("TrainingFeatureSourceKind token must be a string.")
    try:
        return TrainingFeatureSourceKind(token)
    except ValueError as exc:
        raise PolicyProvenanceError(
            f"Unsupported TrainingFeatureSourceKind token: {token}."
        ) from exc


def validate_training_row_payload(payload: TrainingRowPayload) -> TrainingRowPayload:
    return TrainingRow.from_payload(payload).to_payload()


def _payload_hash(payload: object) -> str:
    return hashlib.sha256(canonical_json(_validate_json(payload)).encode("utf-8")).hexdigest()


def _validate_policy_schema_version(value: object) -> str:
    schema_version = _validate_identifier("PolicyProvenance schema_version", value)
    if schema_version != POLICY_PROVENANCE_SCHEMA_VERSION:
        raise PolicyProvenanceError("PolicyProvenance schema_version is unsupported.")
    return schema_version


def _validate_training_row_schema_version(value: object) -> str:
    schema_version = _validate_identifier("TrainingRow schema_version", value)
    if schema_version != TRAINING_ROW_SCHEMA_VERSION:
        raise PolicyProvenanceError("TrainingRow schema_version is unsupported.")
    return schema_version


def _validate_catalog_package_tuple(
    values: object,
) -> tuple[CatalogPackageProvenance, ...]:
    if type(values) is not tuple:
        raise PolicyProvenanceError("PolicyProvenance catalog_packages must be a tuple.")
    validated: list[CatalogPackageProvenance] = []
    seen: set[tuple[str, str]] = set()
    for value in cast(tuple[object, ...], values):
        if type(value) is not CatalogPackageProvenance:
            raise PolicyProvenanceError(
                "PolicyProvenance catalog_packages must contain catalog provenance."
            )
        key = (value.catalog_id, value.source_package_id)
        if key in seen:
            raise PolicyProvenanceError("PolicyProvenance catalog_packages must be unique.")
        seen.add(key)
        validated.append(value)
    if not validated:
        raise PolicyProvenanceError("PolicyProvenance catalog_packages must not be empty.")
    return tuple(sorted(validated, key=lambda item: (item.catalog_id, item.source_package_id)))


def _validate_training_feature_tuple(values: object) -> tuple[TrainingFeature, ...]:
    if type(values) is not tuple:
        raise PolicyProvenanceError("TrainingRow input_features must be a tuple.")
    validated: list[TrainingFeature] = []
    seen: set[str] = set()
    for value in cast(tuple[object, ...], values):
        if type(value) is not TrainingFeature:
            raise PolicyProvenanceError("TrainingRow input_features must contain features.")
        if value.feature_id in seen:
            raise PolicyProvenanceError("TrainingRow input_features must be unique.")
        seen.add(value.feature_id)
        validated.append(value)
    if not validated:
        raise PolicyProvenanceError("TrainingRow input_features must not be empty.")
    return tuple(sorted(validated, key=lambda feature: feature.feature_id))


def _validate_bool_tuple(field_name: str, values: object) -> tuple[bool, ...]:
    if type(values) is not tuple:
        raise PolicyProvenanceError(f"{field_name} must be a tuple.")
    validated: list[bool] = []
    for value in cast(tuple[object, ...], values):
        if type(value) is not bool:
            raise PolicyProvenanceError(f"{field_name} must contain bool values.")
        validated.append(value)
    if not validated:
        raise PolicyProvenanceError(f"{field_name} must not be empty.")
    if not any(validated):
        raise PolicyProvenanceError(f"{field_name} must contain at least one legal action.")
    return tuple(validated)


def _validate_feature_value(value: object) -> JsonValue:
    json_value = _validate_json(value)
    _reject_identity_feature_value(json_value)
    return json_value


def _validate_debug_metadata(value: object) -> dict[str, JsonValue]:
    json_value = _validate_json(value)
    if not isinstance(json_value, dict):
        raise PolicyProvenanceError("TrainingRow debug_metadata must be a JSON object.")
    return json_value


def _validate_json(value: object) -> JsonValue:
    try:
        return validate_json_value(value)
    except EventLogError as exc:
        raise PolicyProvenanceError("Policy contract payload must be JSON-safe.") from exc


def _reject_identity_feature_identifier(field_name: str, value: str) -> None:
    normalised = value.lower().replace("-", "_").replace(":", "_")
    for token in _IDENTITY_FEATURE_TOKENS:
        if token in normalised:
            raise PolicyProvenanceError(f"{field_name} must not encode identity IDs.")


def _reject_identity_feature_value(value: JsonValue) -> None:
    if isinstance(value, list):
        for item in value:
            _reject_identity_feature_value(item)
        return
    if isinstance(value, dict):
        for key, item in value.items():
            _reject_identity_feature_identifier("TrainingFeature value key", key)
            _reject_identity_feature_value(item)


def _validate_identifier_tuple(
    field_name: str,
    values: object,
    *,
    allow_empty: bool = False,
) -> tuple[str, ...]:
    if type(values) is not tuple:
        raise PolicyProvenanceError(f"{field_name} must be a tuple.")
    validated: list[str] = []
    seen: set[str] = set()
    for value in cast(tuple[object, ...], values):
        identifier = _validate_identifier(f"{field_name} value", value)
        if identifier in seen:
            raise PolicyProvenanceError(f"{field_name} must not contain duplicates.")
        seen.add(identifier)
        validated.append(identifier)
    if not allow_empty and not validated:
        raise PolicyProvenanceError(f"{field_name} must not be empty.")
    return tuple(sorted(validated))


def _validate_sha256(field_name: str, value: object) -> str:
    digest = _validate_identifier(field_name, value)
    if len(digest) != 64:
        raise PolicyProvenanceError(f"{field_name} must be a SHA-256 digest.")
    if any(character not in "0123456789abcdef" for character in digest):
        raise PolicyProvenanceError(f"{field_name} must be a lowercase SHA-256 digest.")
    return digest


_validate_identifier = IdentifierValidator(PolicyProvenanceError)
