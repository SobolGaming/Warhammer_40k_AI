"""Explicit offline target declarations; no labels are inferred from legacy scalars."""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import StrEnum
from typing import TypedDict, cast

from warhammer40k_core.ai.player_policy import PlayerDecisionContext, payload_digest
from warhammer40k_core.ai.policy_contracts import PolicyProvenanceError, TrainingRow
from warhammer40k_core.ai.training_candidates import (
    FiniteTrainingCandidateLink,
    TrainingCandidateLinkError,
)
from warhammer40k_core.core.validation import IdentifierValidator

TARGET_SCHEMA_VERSION = "named-training-target-v1"
TARGET_LINK_SCHEMA_VERSION = "named-training-target-link-v1"


class TrainingTargetError(PolicyProvenanceError):
    """A named target declaration or its exact training-row join is invalid."""


class TargetMeaning(StrEnum):
    MATCH_UTILITY = "match_utility"
    VP_MARGIN = "vp_margin"
    LOCAL_REFERENCE = "local_reference"


class TargetHorizon(StrEnum):
    MATCH_END = "match_end"
    DECISION_COUNT = "decision_count"


class TargetEpisodeEnd(StrEnum):
    TERMINAL = "terminal"
    TRUNCATED = "truncated"
    ABORTED = "aborted"
    UNSUPPORTED = "unsupported"


class TargetValidity(StrEnum):
    OBSERVED = "observed"
    MISSING = "missing"


class NamedTrainingTargetPayload(TypedDict):
    schema_version: str
    target_id: str
    meaning: str
    perspective_player_id: str
    horizon: str
    horizon_decisions: int | None
    episode_end: str
    validity: str
    value: float | int | None
    value_unit: str
    missing_reason: str | None
    producer_id: str
    evidence_hash: str
    reward_profile_version: str
    discount_convention: str


@dataclass(frozen=True, slots=True)
class NamedTrainingTarget:
    """An immutable producer declaration, not independently authenticated evidence.

    Match utility is win=1/draw=0.5/loss=0; VP margin is own minus opponent
    terminal VP. A local reference uses its target_id as the external versioned
    definition and declares its units and decision horizon. All are undiscounted.
    """

    target_id: str
    meaning: TargetMeaning
    perspective_player_id: str
    horizon: TargetHorizon
    horizon_decisions: int | None
    episode_end: TargetEpisodeEnd
    validity: TargetValidity
    value: float | int | None
    value_unit: str
    missing_reason: str | None
    producer_id: str
    evidence_hash: str
    reward_profile_version: str

    def __post_init__(self) -> None:
        for field in (
            "target_id",
            "perspective_player_id",
            "value_unit",
            "producer_id",
            "reward_profile_version",
        ):
            object.__setattr__(
                self, field, _identifier("Training target " + field, getattr(self, field))
            )
        for enum_value, kind in (
            (self.meaning, TargetMeaning),
            (self.horizon, TargetHorizon),
            (self.episode_end, TargetEpisodeEnd),
            (self.validity, TargetValidity),
        ):
            if type(enum_value) is not kind:
                raise TrainingTargetError("Training target requires typed enum fields.")
        _sha256(self.evidence_hash)
        if self.meaning is TargetMeaning.LOCAL_REFERENCE:
            if (
                self.horizon is not TargetHorizon.DECISION_COUNT
                or type(self.horizon_decisions) is not int
                or self.horizon_decisions < 1
            ):
                raise TrainingTargetError("Local references require a positive decision horizon.")
        else:
            if self.horizon is not TargetHorizon.MATCH_END or self.horizon_decisions is not None:
                raise TrainingTargetError("Match targets require the complete match horizon.")
            unit = (
                "unit_interval" if self.meaning is TargetMeaning.MATCH_UTILITY else "victory_points"
            )
            if self.value_unit != unit:
                raise TrainingTargetError("Match target units do not match their meaning.")
        if self.validity is TargetValidity.MISSING:
            if self.value is not None:
                raise TrainingTargetError("Missing targets must have no numeric value.")
            object.__setattr__(
                self,
                "missing_reason",
                _identifier("Training target missing_reason", self.missing_reason),
            )
            return
        if self.missing_reason is not None:
            raise TrainingTargetError("Observed targets cannot carry a missing reason.")
        if self.episode_end in (TargetEpisodeEnd.ABORTED, TargetEpisodeEnd.UNSUPPORTED):
            raise TrainingTargetError("Aborted and unsupported episodes require missing targets.")
        if (
            self.meaning is not TargetMeaning.LOCAL_REFERENCE
            and self.episode_end is not TargetEpisodeEnd.TERMINAL
        ):
            raise TrainingTargetError("Observed match targets require a terminal episode.")
        if type(self.value) not in (int, float):
            raise TrainingTargetError("Observed targets require a finite number.")
        try:
            value = float(cast(float, self.value))
        except OverflowError as exc:
            raise TrainingTargetError("Observed targets require a finite number.") from exc
        if not math.isfinite(value) or (type(self.value) is int and int(value) != self.value):
            raise TrainingTargetError("Observed targets require a finite number.")
        if self.meaning is TargetMeaning.MATCH_UTILITY and value not in (0.0, 0.5, 1.0):
            raise TrainingTargetError("Match utility must be win=1, draw=0.5 or loss=0.")
        if self.meaning is TargetMeaning.VP_MARGIN and not value.is_integer():
            raise TrainingTargetError("Terminal VP margin must be an integer.")
        object.__setattr__(self, "value", value)

    def to_payload(self) -> NamedTrainingTargetPayload:
        return {
            "schema_version": TARGET_SCHEMA_VERSION,
            "target_id": self.target_id,
            "meaning": self.meaning.value,
            "perspective_player_id": self.perspective_player_id,
            "horizon": self.horizon.value,
            "horizon_decisions": self.horizon_decisions,
            "episode_end": self.episode_end.value,
            "validity": self.validity.value,
            "value": self.value,
            "value_unit": self.value_unit,
            "missing_reason": self.missing_reason,
            "producer_id": self.producer_id,
            "evidence_hash": self.evidence_hash,
            "reward_profile_version": self.reward_profile_version,
            "discount_convention": "undiscounted",
        }

    @classmethod
    def from_payload(cls, payload: object) -> NamedTrainingTarget:
        value = _object(payload, NamedTrainingTargetPayload.__annotations__)
        if (
            value["schema_version"] != TARGET_SCHEMA_VERSION
            or value["discount_convention"] != "undiscounted"
        ):
            raise TrainingTargetError("Unsupported target schema or discount convention.")
        for field, kind in (
            ("meaning", TargetMeaning),
            ("horizon", TargetHorizon),
            ("episode_end", TargetEpisodeEnd),
            ("validity", TargetValidity),
        ):
            token = value[field]
            if type(token) is not str or token not in {member.value for member in kind}:
                raise TrainingTargetError("Unsupported target enum token.")
        return cls(
            target_id=_identifier("Training target target_id", value["target_id"]),
            meaning=TargetMeaning(cast(str, value["meaning"])),
            perspective_player_id=_identifier(
                "Training target perspective", value["perspective_player_id"]
            ),
            horizon=TargetHorizon(cast(str, value["horizon"])),
            horizon_decisions=cast(int | None, value["horizon_decisions"]),
            episode_end=TargetEpisodeEnd(cast(str, value["episode_end"])),
            validity=TargetValidity(cast(str, value["validity"])),
            value=cast(float | None, value["value"]),
            value_unit=_identifier("Training target value_unit", value["value_unit"]),
            missing_reason=cast(str | None, value["missing_reason"]),
            producer_id=_identifier("Training target producer_id", value["producer_id"]),
            evidence_hash=_sha256(value["evidence_hash"]),
            reward_profile_version=_identifier(
                "Training target reward version", value["reward_profile_version"]
            ),
        )


class LinkedTrainingTargetPayload(TypedDict):
    schema_version: str
    training_candidate_link_hash: str
    target: NamedTrainingTargetPayload


@dataclass(frozen=True, slots=True)
class LinkedTrainingTarget:
    """Exact offline linkage; record acceptance and label authenticity remain external."""

    training_candidate_link_hash: str
    target: NamedTrainingTarget

    def __post_init__(self) -> None:
        _sha256(self.training_candidate_link_hash)
        if type(self.target) is not NamedTrainingTarget:
            raise TrainingTargetError("Target linkage requires a typed named target.")

    @classmethod
    def from_link(
        cls,
        link: FiniteTrainingCandidateLink,
        *,
        row: TrainingRow,
        context: PlayerDecisionContext,
        target: NamedTrainingTarget,
    ) -> LinkedTrainingTarget:
        _require_link(link, row=row, context=context)
        result = cls(payload_digest(link.to_payload()), target)
        result.require_matches(link, row=row, context=context)
        return result

    def require_matches(
        self,
        link: FiniteTrainingCandidateLink,
        *,
        row: TrainingRow,
        context: PlayerDecisionContext,
    ) -> None:
        _require_link(link, row=row, context=context)
        if self.training_candidate_link_hash != payload_digest(link.to_payload()):
            raise TrainingTargetError("Named target training candidate link drifted.")
        if self.target.reward_profile_version != row.reward_profile_version:
            raise TrainingTargetError("Named target reward version does not match its row.")
        if self.target.perspective_player_id not in context.observation["player_ids"]:
            raise TrainingTargetError(
                "Named target perspective is not a player in its observation."
            )

    def to_payload(self) -> LinkedTrainingTargetPayload:
        return {
            "schema_version": TARGET_LINK_SCHEMA_VERSION,
            "training_candidate_link_hash": self.training_candidate_link_hash,
            "target": self.target.to_payload(),
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
    ) -> LinkedTrainingTarget:
        value = _object(payload, LinkedTrainingTargetPayload.__annotations__)
        if value["schema_version"] != TARGET_LINK_SCHEMA_VERSION:
            raise TrainingTargetError("Unsupported named target linkage schema.")
        result = cls(
            _sha256(value["training_candidate_link_hash"]),
            NamedTrainingTarget.from_payload(value["target"]),
        )
        result.require_matches(link, row=row, context=context)
        return result


def _require_link(
    link: FiniteTrainingCandidateLink,
    *,
    row: TrainingRow,
    context: PlayerDecisionContext,
) -> None:
    if type(link) is not FiniteTrainingCandidateLink:
        raise TrainingTargetError("Named targets require a finite training candidate link.")
    try:
        link.require_matches(row, context=context)
    except TrainingCandidateLinkError as exc:
        raise TrainingTargetError("Named target row or candidate binding drifted.") from exc


def _object(payload: object, fields: dict[str, object]) -> dict[str, object]:
    if not isinstance(payload, dict) or payload.keys() != fields.keys():
        raise TrainingTargetError("Target payload has missing or unknown fields.")
    return cast(dict[str, object], payload)


def _sha256(value: object) -> str:
    if type(value) is not str or len(value) != 64 or set(value) - set("0123456789abcdef"):
        raise TrainingTargetError("Target evidence and linkage hashes must be lowercase SHA-256.")
    return value


_identifier = IdentifierValidator(TrainingTargetError)
