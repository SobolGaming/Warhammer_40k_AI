"""Operator-only singleton and validated-set deployment training linkage."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import TypedDict, cast

from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.ai.deployment_candidate_ranking import RankedDeploymentCandidates
from warhammer40k_core.ai.deployment_candidate_search import DeploymentCandidateSet
from warhammer40k_core.ai.deployment_candidate_validation import ValidatedDeploymentCandidates
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
from warhammer40k_core.build_identity import current_engine_build_id
from warhammer40k_core.engine.event_log import (
    EventLogError,
    JsonValue,
    canonical_json,
    validate_json_value,
)

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
        row_payload = _require_accepted_candidate(
            row, candidate=candidate, context=context, transition=transition
        )
        if row.legal_action_mask != (True,):
            raise TrainingCandidateLinkError("Singleton deployment row requires slot zero only.")
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


DEPLOYMENT_TRAINING_LINK_SCHEMA_VERSION = "deployment-set-training-candidate-link-v1"


class DeploymentTrainingCandidateLinkPayload(TypedDict):
    schema_version: str
    row_id: str
    game_id: str
    training_row_hash: str
    candidate_set_hash: str
    candidate_set: dict[str, JsonValue]
    validation_hash: str
    validation: dict[str, JsonValue]
    chosen_action_id: str
    chosen_action_index: int
    accepted_transition_hash: str


@dataclass(frozen=True, slots=True, init=False)
class DeploymentTrainingCandidateLink:
    """Full search evidence with a row mask over the ordered validated prefix.

    Rejected validated slots are False. Unvalidated candidates have no mask slot;
    their geometry, count and budget stop remain in the operator-only receipt.
    The selected slot must be accepted and reproduced at the same checkpoint.
    """

    validated: ValidatedDeploymentCandidates
    transition: ParameterizedAcceptedTransition
    _evidence_json: str

    def __init__(self) -> None:
        raise TrainingCandidateLinkError("Link a deployment set through validated evidence.")

    @classmethod
    def from_row(
        cls,
        row: TrainingRow,
        *,
        validated: ValidatedDeploymentCandidates,
        context: PlayerDecisionContext,
        transition: ParameterizedAcceptedTransition,
    ) -> DeploymentTrainingCandidateLink:
        if (
            type(row) is not TrainingRow
            or type(validated) is not ValidatedDeploymentCandidates
            or type(transition) is not ParameterizedAcceptedTransition
        ):
            raise TrainingCandidateLinkError("Deployment set linkage requires typed evidence.")
        if row.chosen_action_id not in validated.accepted_ids:
            raise TrainingCandidateLinkError("Selected deployment slot was not accepted.")
        candidates = validated.candidate_set.candidates
        chosen_index = next(
            index
            for index, candidate in enumerate(candidates)
            if candidate.candidate_id == row.chosen_action_id
        )
        row_payload = _require_accepted_candidate(
            row, candidate=candidates[chosen_index], context=context, transition=transition
        )
        receipt = validated.to_payload()
        results = cast(list[dict[str, JsonValue]], receipt["results"])
        mask = tuple(cast(bool, result["accepted"]) for result in results)
        if (
            row.legal_action_mask != mask
            or receipt["checkpoint_hash"] != transition.to_payload()["before_checkpoint_hash"]
        ):
            raise TrainingCandidateLinkError("Deployment validated mask or checkpoint drifted.")
        payload: DeploymentTrainingCandidateLinkPayload = {
            "schema_version": DEPLOYMENT_TRAINING_LINK_SCHEMA_VERSION,
            "row_id": row.row_id,
            "game_id": row.game_id,
            "training_row_hash": payload_digest(row_payload),
            "candidate_set_hash": validated.candidate_set.content_hash,
            "candidate_set": validated.candidate_set.to_payload(),
            "validation_hash": validated.content_hash,
            "validation": receipt,
            "chosen_action_id": row.chosen_action_id,
            "chosen_action_index": chosen_index,
            "accepted_transition_hash": transition.content_hash,
        }
        result = object.__new__(cls)
        object.__setattr__(result, "validated", validated)
        object.__setattr__(result, "transition", transition)
        object.__setattr__(result, "_evidence_json", canonical_json(payload))
        return result

    @property
    def chosen_action_id(self) -> str:
        return self.to_payload()["chosen_action_id"]

    @property
    def chosen_action_index(self) -> int:
        return self.to_payload()["chosen_action_index"]

    def require_matches(self, row: TrainingRow, *, context: PlayerDecisionContext) -> None:
        expected = type(self).from_row(
            row, validated=self.validated, context=context, transition=self.transition
        )
        if self != expected:
            raise TrainingCandidateLinkError("Complete deployment set training row drifted.")

    def to_payload(self) -> DeploymentTrainingCandidateLinkPayload:
        return cast(DeploymentTrainingCandidateLinkPayload, json.loads(self._evidence_json))

    @classmethod
    def from_payload(
        cls,
        payload: object,
        *,
        row: TrainingRow,
        context: PlayerDecisionContext,
        session: LocalGameSession,
        transition: ParameterizedAcceptedTransition,
    ) -> DeploymentTrainingCandidateLink:
        if (
            not isinstance(payload, dict)
            or payload.keys() != DeploymentTrainingCandidateLinkPayload.__annotations__.keys()
        ):
            raise TrainingCandidateLinkError("Deployment set link has missing or unknown fields.")
        value = cast(dict[str, object], payload)
        try:
            candidate_set = DeploymentCandidateSet.from_payload(
                value["candidate_set"], context=context
            )
            validated = ValidatedDeploymentCandidates.from_payload(
                value["validation"], candidate_set=candidate_set, context=context, session=session
            )
            expected = cls.from_row(
                row, validated=validated, context=context, transition=transition
            )
            observed = canonical_json(validate_json_value(value))
        except (PolicyError, EventLogError) as exc:
            raise TrainingCandidateLinkError("Malformed deployment set training linkage.") from exc
        if observed != canonical_json(expected.to_payload()):
            raise TrainingCandidateLinkError("Deployment set training linkage evidence drifted.")
        return expected


@dataclass(frozen=True, slots=True, init=False)
class RankedDeploymentTrainingLink:
    """Operator-only deterministic behavior evidence for an existing accepted row.

    Targets continue to use candidate_link; this companion does not admit datasets
    or infer behavior probabilities from deterministic scores.
    """

    ranking: RankedDeploymentCandidates
    candidate_link: DeploymentTrainingCandidateLink
    _evidence_json: str

    def __init__(self) -> None:
        raise TrainingCandidateLinkError("Link ranked behavior through accepted row evidence.")

    @classmethod
    def from_row(
        cls,
        row: TrainingRow,
        *,
        ranking: RankedDeploymentCandidates,
        candidate_link: DeploymentTrainingCandidateLink,
        context: PlayerDecisionContext,
    ) -> RankedDeploymentTrainingLink:
        if (
            type(row) is not TrainingRow
            or type(ranking) is not RankedDeploymentCandidates
            or type(candidate_link) is not DeploymentTrainingCandidateLink
            or type(context) is not PlayerDecisionContext
        ):
            raise TrainingCandidateLinkError("Ranked training linkage requires typed evidence.")
        candidate_link.require_matches(row, context=context)
        receipt = ranking.to_payload()
        if (
            ranking.validated != candidate_link.validated
            or ranking.selected_candidate_id != candidate_link.chosen_action_id
            or receipt["choice_seed"] != context.choice_seed
            or receipt["engine_build_id"] != current_engine_build_id()
            or row.policy_provenance != ranking.configuration.provenance
        ):
            raise TrainingCandidateLinkError(
                "Ranking provenance, selection, validation, build or choice seed drifted."
            )
        payload = {
            "schema_version": "ranked-deployment-training-link-v1",
            "training_row_hash": payload_digest(row.to_payload()),
            "ranking_hash": ranking.content_hash,
            "ranking": receipt,
            "candidate_link_hash": payload_digest(candidate_link.to_payload()),
            "candidate_link": candidate_link.to_payload(),
        }
        result = object.__new__(cls)
        object.__setattr__(result, "ranking", ranking)
        object.__setattr__(result, "candidate_link", candidate_link)
        object.__setattr__(result, "_evidence_json", canonical_json(payload))
        return result

    def to_payload(self) -> dict[str, JsonValue]:
        return cast(dict[str, JsonValue], json.loads(self._evidence_json))

    def require_matches(self, row: TrainingRow, *, context: PlayerDecisionContext) -> None:
        expected = type(self).from_row(
            row, ranking=self.ranking, candidate_link=self.candidate_link, context=context
        )
        if self != expected:
            raise TrainingCandidateLinkError("Complete ranked deployment training row drifted.")

    @classmethod
    def from_payload(
        cls,
        payload: object,
        *,
        row: TrainingRow,
        ranking: RankedDeploymentCandidates,
        candidate_link: DeploymentTrainingCandidateLink,
        context: PlayerDecisionContext,
    ) -> RankedDeploymentTrainingLink:
        expected = cls.from_row(
            row, ranking=ranking, candidate_link=candidate_link, context=context
        )
        try:
            observed = canonical_json(validate_json_value(payload))
        except EventLogError as exc:
            raise TrainingCandidateLinkError("Ranked training linkage must be JSON-safe.") from exc
        if observed != expected._evidence_json:
            raise TrainingCandidateLinkError("Ranked training linkage evidence drifted.")
        return expected


type TrainingCandidateLink = (
    FiniteTrainingCandidateLink
    | ParameterizedTrainingCandidateLink
    | DeploymentTrainingCandidateLink
)


def _require_accepted_candidate(
    row: TrainingRow,
    *,
    candidate: DeploymentPlacementCandidate,
    context: PlayerDecisionContext,
    transition: ParameterizedAcceptedTransition,
) -> JsonValue:
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
    return row_payload
