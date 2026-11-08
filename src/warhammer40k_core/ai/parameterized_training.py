"""Operator-only row linkage for one engine-accepted deployment candidate."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import TypedDict, cast

from warhammer40k_core.ai.deployment_candidates import (
    DeploymentCandidatePayload,
    DeploymentPlacementCandidate,
)
from warhammer40k_core.ai.player_policy import PlayerDecisionContext, PolicyError, payload_digest
from warhammer40k_core.ai.policy_contracts import TrainingRow
from warhammer40k_core.ai.training_candidates import (
    FiniteTrainingCandidateLink,
    TrainingCandidateLinkError,
)
from warhammer40k_core.ai.training_transitions import ParameterizedAcceptedTransition
from warhammer40k_core.engine.event_log import EventLogError, canonical_json, validate_json_value

PARAMETERIZED_TRAINING_LINK_SCHEMA_VERSION = "parameterized-training-candidate-link-v1"


class ParameterizedTrainingCandidateLinkPayload(TypedDict):
    schema_version: str
    row_id: str
    game_id: str
    training_row_hash: str
    candidate_hash: str
    candidate: DeploymentCandidatePayload
    chosen_action_id: str
    chosen_action_index: int
    accepted_transition_hash: str


@dataclass(frozen=True, slots=True, init=False)
class ParameterizedTrainingCandidateLink:
    """One accepted candidate in slot zero; no unexecuted alternatives or search mask.

    The immutable transition was independently reproduced by its engine verifier.
    This link keeps its detached evidence, never a session or authoritative state.
    """

    candidate: DeploymentPlacementCandidate
    transition: ParameterizedAcceptedTransition
    _evidence_json: str

    def __init__(self) -> None:
        raise TrainingCandidateLinkError("Link a deployment row through accepted evidence.")

    @classmethod
    def from_row(
        cls,
        row: TrainingRow,
        *,
        candidate: DeploymentPlacementCandidate,
        context: PlayerDecisionContext,
        transition: ParameterizedAcceptedTransition,
    ) -> ParameterizedTrainingCandidateLink:
        if (
            type(row) is not TrainingRow
            or type(candidate) is not DeploymentPlacementCandidate
            or type(context) is not PlayerDecisionContext
            or type(transition) is not ParameterizedAcceptedTransition
        ):
            raise TrainingCandidateLinkError("Deployment linkage requires typed accepted evidence.")
        try:
            action = candidate.select(context)
            row_payload = validate_json_value(row.to_payload())
        except (PolicyError, EventLogError) as exc:
            raise TrainingCandidateLinkError("Deployment candidate or row binding failed.") from exc
        evidence = transition.to_payload()
        if (
            row.game_id != context.observation["game_id"]
            or row.chosen_action_id != candidate.candidate_id
            or row.legal_action_mask != (True,)
            or row.decision_record_id != evidence["authoritative_record_id"]
            or evidence["actor_id"] != action.actor_id
            or evidence["before_observation_hash"] != action.observation_hash
            or evidence["proposal_kind"] != "deployment_placement"
            or canonical_json(evidence["viewer_action"])
            != canonical_json(
                {
                    "actor_id": action.actor_id,
                    "request_id": action.request_id,
                    "observation_hash": action.observation_hash,
                    "proposal": json.loads(cast(str, action.proposal_json)),
                }
            )
        ):
            raise TrainingCandidateLinkError(
                "Deployment row, selected candidate or acceptance drifted."
            )
        payload: ParameterizedTrainingCandidateLinkPayload = {
            "schema_version": PARAMETERIZED_TRAINING_LINK_SCHEMA_VERSION,
            "row_id": row.row_id,
            "game_id": row.game_id,
            "training_row_hash": payload_digest(row_payload),
            "candidate_hash": candidate.content_hash,
            "candidate": candidate.to_payload(),
            "chosen_action_id": candidate.candidate_id,
            "chosen_action_index": 0,
            "accepted_transition_hash": transition.content_hash,
        }
        result = object.__new__(cls)
        object.__setattr__(result, "candidate", candidate)
        object.__setattr__(result, "transition", transition)
        object.__setattr__(result, "_evidence_json", canonical_json(payload))
        return result

    @property
    def chosen_action_id(self) -> str:
        return self.candidate.candidate_id

    @property
    def chosen_action_index(self) -> int:
        return 0

    def require_matches(self, row: TrainingRow, *, context: PlayerDecisionContext) -> None:
        expected = type(self).from_row(
            row, candidate=self.candidate, context=context, transition=self.transition
        )
        if self != expected:
            raise TrainingCandidateLinkError("Complete deployment training row payload drifted.")

    def to_payload(self) -> ParameterizedTrainingCandidateLinkPayload:
        return cast(ParameterizedTrainingCandidateLinkPayload, json.loads(self._evidence_json))

    @classmethod
    def from_payload(
        cls,
        payload: object,
        *,
        row: TrainingRow,
        context: PlayerDecisionContext,
        transition: ParameterizedAcceptedTransition,
    ) -> ParameterizedTrainingCandidateLink:
        if (
            not isinstance(payload, dict)
            or payload.keys() != ParameterizedTrainingCandidateLinkPayload.__annotations__.keys()
        ):
            raise TrainingCandidateLinkError(
                "Deployment training link has missing or unknown fields."
            )
        value = cast(dict[str, object], payload)
        try:
            candidate = DeploymentPlacementCandidate.from_payload(
                value["candidate"], context=context
            )
            expected = cls.from_row(
                row, candidate=candidate, context=context, transition=transition
            )
            observed = canonical_json(validate_json_value(value))
        except (PolicyError, EventLogError) as exc:
            raise TrainingCandidateLinkError("Malformed deployment training linkage.") from exc
        if observed != canonical_json(expected.to_payload()):
            raise TrainingCandidateLinkError("Deployment training linkage evidence drifted.")
        return expected


type TrainingCandidateLink = FiniteTrainingCandidateLink | ParameterizedTrainingCandidateLink
