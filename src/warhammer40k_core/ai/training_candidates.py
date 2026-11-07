"""Offline integrity joins between finite candidate snapshots and existing training rows."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TypedDict, cast

from warhammer40k_core.ai.finite_candidates import FiniteCandidateSet, FiniteCandidateSetPayload
from warhammer40k_core.ai.player_policy import PlayerDecisionContext, PolicyError, payload_digest
from warhammer40k_core.ai.policy_contracts import PolicyProvenanceError, TrainingRow
from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine.event_log import EventLogError, validate_json_value

TRAINING_CANDIDATE_LINK_SCHEMA_VERSION = "finite-training-candidate-link-v1"


class TrainingCandidateLinkError(PolicyProvenanceError):
    """A training row and its finite candidate snapshot do not form an exact join."""


class FiniteTrainingCandidateLinkPayload(TypedDict):
    schema_version: str
    row_id: str
    game_id: str
    training_row_hash: str
    candidate_set_hash: str
    candidate_set: FiniteCandidateSetPayload
    chosen_action_id: str
    chosen_action_index: int


def _sha256(value: object) -> str:
    if type(value) is not str or len(value) != 64 or set(value) - set("0123456789abcdef"):
        raise TrainingCandidateLinkError(
            "Training candidate link hashes must be lowercase SHA-256."
        )
    return value


def _row_hash(row: TrainingRow) -> str:
    if type(row) is not TrainingRow:
        raise TrainingCandidateLinkError("Training candidate linkage requires a TrainingRow.")
    try:
        payload = validate_json_value(row.to_payload())
    except EventLogError as exc:
        raise TrainingCandidateLinkError("Linked training row must be JSON-safe.") from exc
    return payload_digest(payload)


@dataclass(frozen=True, slots=True)
class FiniteTrainingCandidateLink:
    """Immutable offline linkage, not evidence of acceptance or target eligibility.

    The row commitment covers its complete canonical payload, including provenance
    and diagnostic metadata. No mutable row or authoritative session is retained.
    """

    row_id: str
    game_id: str
    training_row_hash: str
    candidate_set: FiniteCandidateSet
    chosen_action_id: str

    def __post_init__(self) -> None:
        for field, value in (
            ("row_id", self.row_id),
            ("game_id", self.game_id),
            ("chosen_action_id", self.chosen_action_id),
        ):
            object.__setattr__(self, field, _identifier("Training candidate link " + field, value))
        _sha256(self.training_row_hash)
        if type(self.candidate_set) is not FiniteCandidateSet:
            raise TrainingCandidateLinkError("Training linkage requires a finite candidate set.")
        if self.chosen_action_id not in self.candidate_set.candidate_ids:
            raise TrainingCandidateLinkError(
                "Training row chosen_action_id is not in the candidate set."
            )

    @classmethod
    def from_row(
        cls, row: TrainingRow, *, context: PlayerDecisionContext
    ) -> FiniteTrainingCandidateLink:
        digest = _row_hash(row)
        try:
            candidates = FiniteCandidateSet.from_context(context)
        except PolicyError as exc:
            raise TrainingCandidateLinkError(
                "Training linkage requires a finite decision context."
            ) from exc
        link = cls(row.row_id, row.game_id, digest, candidates, row.chosen_action_id)
        link.require_matches(row, context=context)
        return link

    @property
    def chosen_action_index(self) -> int:
        return self.candidate_set.candidate_ids.index(self.chosen_action_id)

    def require_matches(self, row: TrainingRow, *, context: PlayerDecisionContext) -> None:
        digest = _row_hash(row)
        if (self.row_id, self.game_id, self.chosen_action_id) != (
            row.row_id,
            row.game_id,
            row.chosen_action_id,
        ) or self.training_row_hash != digest:
            raise TrainingCandidateLinkError(
                "Training row identity or complete row payload drifted."
            )
        if row.game_id != context.observation["game_id"]:
            raise TrainingCandidateLinkError("Training row game does not match its observation.")
        if row.legal_action_mask != tuple(True for _ in self.candidate_set.candidates):
            raise TrainingCandidateLinkError(
                "Training row mask must match the complete ordered legal finite candidate set."
            )
        try:
            self.candidate_set.select(context, self.chosen_action_id)
        except PolicyError as exc:
            raise TrainingCandidateLinkError(
                "Training candidate snapshot binding drifted."
            ) from exc

    def to_payload(self) -> FiniteTrainingCandidateLinkPayload:
        return {
            "schema_version": TRAINING_CANDIDATE_LINK_SCHEMA_VERSION,
            "row_id": self.row_id,
            "game_id": self.game_id,
            "training_row_hash": self.training_row_hash,
            "candidate_set_hash": self.candidate_set.content_hash,
            "candidate_set": self.candidate_set.to_payload(),
            "chosen_action_id": self.chosen_action_id,
            "chosen_action_index": self.chosen_action_index,
        }

    @classmethod
    def from_payload(
        cls, payload: object, *, row: TrainingRow, context: PlayerDecisionContext
    ) -> FiniteTrainingCandidateLink:
        if (
            not isinstance(payload, dict)
            or payload.keys() != FiniteTrainingCandidateLinkPayload.__annotations__.keys()
        ):
            raise TrainingCandidateLinkError(
                "Training candidate link has missing or unknown fields."
            )
        value = cast(dict[str, object], payload)
        if value["schema_version"] != TRAINING_CANDIDATE_LINK_SCHEMA_VERSION:
            raise TrainingCandidateLinkError("Unsupported training candidate link schema.")
        try:
            candidates = FiniteCandidateSet.from_payload(value["candidate_set"])
        except PolicyError as exc:
            raise TrainingCandidateLinkError("Malformed linked finite candidate set.") from exc
        link = cls(
            row_id=_identifier("Training candidate link row_id", value["row_id"]),
            game_id=_identifier("Training candidate link game_id", value["game_id"]),
            training_row_hash=_sha256(value["training_row_hash"]),
            candidate_set=candidates,
            chosen_action_id=_identifier(
                "Training candidate link chosen_action_id", value["chosen_action_id"]
            ),
        )
        if _sha256(value["candidate_set_hash"]) != candidates.content_hash:
            raise TrainingCandidateLinkError("Training candidate set hash drifted.")
        index = value["chosen_action_index"]
        if type(index) is not int or index != link.chosen_action_index:
            raise TrainingCandidateLinkError("Training candidate chosen action index drifted.")
        link.require_matches(row, context=context)
        return link


_identifier = IdentifierValidator(TrainingCandidateLinkError)
