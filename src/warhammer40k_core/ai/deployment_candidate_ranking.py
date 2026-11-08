"""Accepted-only actor ranking, with separate operator reproducibility evidence."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from typing import Protocol, cast

from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.ai.deployment_candidate_validation import ValidatedDeploymentCandidates
from warhammer40k_core.ai.deployment_candidates import DeploymentCandidatePayload
from warhammer40k_core.ai.player_policy import (
    PlayerDecisionContext,
    PolicyAction,
    PolicyError,
    payload_digest,
)
from warhammer40k_core.engine.event_log import (
    EventLogError,
    JsonValue,
    canonical_json,
    validate_json_value,
)

DEPLOYMENT_RANKING_SCHEMA = "deployment-candidate-ranking-v1"
DEPLOYMENT_RANKING_TIE_BREAK = "first-generated-accepted-v1"


@dataclass(frozen=True, slots=True)
class DeploymentCandidateScore:
    candidate_id: str
    value: float

    def __post_init__(self) -> None:
        if type(self.candidate_id) is not str or not self.candidate_id.strip():
            raise PolicyError("Deployment scores require nonempty candidate identifiers.")
        if type(self.value) not in (int, float):
            raise PolicyError("Deployment scores require finite numeric values.")
        try:
            number = float(self.value)
        except OverflowError as exc:
            raise PolicyError("Deployment scores require finite numeric values.") from exc
        if not math.isfinite(number):
            raise PolicyError("Deployment scores require finite numeric values.")
        object.__setattr__(self, "value", 0.0 if number == 0 else number)


class DeploymentCandidateRanker(Protocol):
    def score(
        self,
        context: PlayerDecisionContext,
        candidates: tuple[DeploymentCandidatePayload, ...],
    ) -> tuple[DeploymentCandidateScore, ...]:
        """Score every accepted candidate exactly once; larger values rank first.

        Inputs contain only detached actor context and accepted proposals in
        generated order. This cooperative API is not a Python security sandbox.
        """
        ...


@dataclass(frozen=True, slots=True, init=False)
class RankedDeploymentCandidates:
    """Operator-only evidence; never a ranker argument or proof of live execution.

    The retained validation receipt owns rejected/unvalidated geometry and private
    checkpoint evidence. Only accepted payloads cross the actor ranking boundary.
    """

    validated: ValidatedDeploymentCandidates
    _payload_json: str

    def __init__(self) -> None:
        raise PolicyError("Rank validated deployment candidates against their live checkpoint.")

    @classmethod
    def rank(
        cls,
        validated: ValidatedDeploymentCandidates,
        *,
        context: PlayerDecisionContext,
        session: LocalGameSession,
        ranker: DeploymentCandidateRanker,
        ranker_id: str,
        configuration_json: str = "{}",
    ) -> RankedDeploymentCandidates:
        if type(validated) is not ValidatedDeploymentCandidates:
            raise PolicyError("Deployment ranking requires typed validated candidates.")
        if type(ranker_id) is not str or not ranker_id.strip():
            raise PolicyError("Deployment ranking requires a versioned ranker identifier.")
        try:
            configuration = validate_json_value(json.loads(configuration_json))
        except (TypeError, json.JSONDecodeError, EventLogError) as exc:
            raise PolicyError("Deployment ranking configuration must be JSON-safe.") from exc
        if not isinstance(configuration, dict):
            raise PolicyError("Deployment ranking configuration must be an object.")
        # Reject stale actor/checkpoint evidence before calling user ranker code.
        validated.select(context, validated.accepted_ids[0], session=session)
        actor_context = PlayerDecisionContext.from_view(
            context.observation, choice_seed=context.choice_seed
        )
        accepted = tuple(
            candidate.to_payload()
            for candidate in validated.candidate_set.candidates
            if candidate.candidate_id in validated.accepted_ids
        )
        actor_input_hash = payload_digest(
            {
                "observation": actor_context.observation,
                "choice_seed": actor_context.choice_seed,
                "candidates": accepted,
            }
        )
        scores = ranker.score(actor_context, accepted)
        if type(scores) is not tuple or any(
            type(score) is not DeploymentCandidateScore for score in scores
        ):
            raise PolicyError("Deployment scores must be a typed immutable tuple.")
        by_id = {score.candidate_id: score.value for score in scores}
        if len(by_id) != len(scores) or set(by_id) != set(validated.accepted_ids):
            raise PolicyError("Deployment scores must cover exactly the accepted set once.")
        # max retains the first generated accepted ID on equal scores, regardless
        # of the ranker's output order. No rejected or unvalidated fallback exists.
        selected = max(validated.accepted_ids, key=by_id.__getitem__)
        validated.select(context, selected, session=session)
        payload = {
            "schema_version": DEPLOYMENT_RANKING_SCHEMA,
            "candidate_set_hash": validated.candidate_set.content_hash,
            "validation_hash": validated.content_hash,
            "actor_input_hash": actor_input_hash,
            "choice_seed": context.choice_seed,
            "ranker_id": ranker_id,
            "configuration": configuration,
            "tie_break": DEPLOYMENT_RANKING_TIE_BREAK,
            "scores": [
                {"candidate_id": candidate_id, "value": by_id[candidate_id]}
                for candidate_id in validated.accepted_ids
            ],
            "selected_candidate_id": selected,
        }
        result = object.__new__(cls)
        object.__setattr__(result, "validated", validated)
        object.__setattr__(result, "_payload_json", canonical_json(payload))
        return result

    @property
    def selected_candidate_id(self) -> str:
        return cast(str, self.to_payload()["selected_candidate_id"])

    @property
    def content_hash(self) -> str:
        return payload_digest(self.to_payload())

    def to_payload(self) -> dict[str, JsonValue]:
        return cast(dict[str, JsonValue], json.loads(self._payload_json))

    def select(self, context: PlayerDecisionContext, *, session: LocalGameSession) -> PolicyAction:
        if type(context) is not PlayerDecisionContext:
            raise PolicyError("Deployment ranking selection requires a typed actor context.")
        if context.choice_seed != self.to_payload()["choice_seed"]:
            raise PolicyError("Deployment ranking choice seed drifted before selection.")
        return self.validated.select(context, self.selected_candidate_id, session=session)

    @classmethod
    def from_payload(
        cls,
        payload: object,
        *,
        validated: ValidatedDeploymentCandidates,
        context: PlayerDecisionContext,
        session: LocalGameSession,
        ranker: DeploymentCandidateRanker,
        ranker_id: str,
        configuration_json: str = "{}",
    ) -> RankedDeploymentCandidates:
        try:
            observed = canonical_json(validate_json_value(payload))
        except EventLogError as exc:
            raise PolicyError("Deployment ranking evidence must be JSON-safe.") from exc
        expected = cls.rank(
            validated,
            context=context,
            session=session,
            ranker=ranker,
            ranker_id=ranker_id,
            configuration_json=configuration_json,
        )
        if observed != expected._payload_json:
            raise PolicyError("Deployment ranking evidence drifted from reproduction.")
        return expected
