"""Accepted-only actor ranking, with separate operator reproducibility evidence."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from enum import StrEnum
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
from warhammer40k_core.ai.policy_contracts import (
    PolicyArtifactKind,
    PolicyProvenance,
    PolicyProvenanceError,
)
from warhammer40k_core.build_identity import current_engine_build_id
from warhammer40k_core.engine.event_log import (
    EventLogError,
    JsonValue,
    canonical_json,
    validate_json_value,
)

DEPLOYMENT_RANKING_SCHEMA = "deployment-candidate-ranking-v2"
DEPLOYMENT_RANKING_TIE_BREAK = "first-generated-accepted-v1"


class DeploymentRankingBehavior(StrEnum):
    DETERMINISTIC = "deterministic-given-actor-inputs-and-parameters-v1"


@dataclass(frozen=True, slots=True)
class DeploymentRankerConfiguration:
    """Operator provenance plus explicitly actor-visible scoring parameters.

    Artifact identity is a declaration, not authentication of arbitrary Python
    code or model weights. Private run/configuration evidence must not be put in
    parameters: those bytes are deliberately supplied to the scorer.
    """

    provenance: PolicyProvenance
    parameters_json: str = "{}"
    behavior: DeploymentRankingBehavior = DeploymentRankingBehavior.DETERMINISTIC

    def __post_init__(self) -> None:
        if (
            type(self.provenance) is not PolicyProvenance
            or self.provenance.artifact_kind is not PolicyArtifactKind.RANKER
        ):
            raise PolicyError("Deployment configuration requires typed ranker provenance.")
        if self.behavior is not DeploymentRankingBehavior.DETERMINISTIC:
            raise PolicyError("Deployment configuration requires declared deterministic behavior.")
        if type(self.parameters_json) is not str:
            raise PolicyError("Deployment scoring parameters must be a JSON object string.")
        try:
            parameters = validate_json_value(json.loads(self.parameters_json))
        except (json.JSONDecodeError, EventLogError) as exc:
            raise PolicyError("Deployment scoring parameters must be JSON-safe.") from exc
        if not isinstance(parameters, dict):
            raise PolicyError("Deployment scoring parameters must be an object.")
        object.__setattr__(self, "parameters_json", canonical_json(parameters))

    @property
    def parameters(self) -> dict[str, JsonValue]:
        return cast(dict[str, JsonValue], json.loads(self.parameters_json))

    def to_payload(self) -> dict[str, JsonValue]:
        return {
            "schema_version": "deployment-ranker-configuration-v1",
            "policy_provenance": validate_json_value(self.provenance.to_payload()),
            "parameters": self.parameters,
            "behavior": self.behavior.value,
        }


@dataclass(frozen=True, slots=True)
class DeploymentCandidateScore:
    candidate_id: str
    value: int | float

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
        # Float conversion checks the admitted range, never the comparison value.
        # Native int/float comparison and canonical JSON preserve exact integers.
        if type(self.value) is float and number == 0:
            object.__setattr__(self, "value", 0.0)


class DeploymentCandidateRanker(Protocol):
    def score(
        self,
        context: PlayerDecisionContext,
        candidates: tuple[DeploymentCandidatePayload, ...],
        *,
        parameters: dict[str, JsonValue],
    ) -> tuple[DeploymentCandidateScore, ...]:
        """Score every accepted candidate exactly once; larger values rank first.

        Inputs contain only detached actor context and accepted proposals in
        generated order, plus detached declared actor-visible parameters. This
        cooperative API is not a Python security sandbox.
        """
        ...


@dataclass(frozen=True, slots=True, init=False)
class RankedDeploymentCandidates:
    """Operator-only evidence; never a ranker argument or proof of live execution.

    The retained validation receipt owns rejected/unvalidated geometry and private
    checkpoint evidence. Only accepted payloads cross the actor ranking boundary.
    """

    validated: ValidatedDeploymentCandidates
    configuration: DeploymentRankerConfiguration
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
        configuration: DeploymentRankerConfiguration,
        reward_profile_version: str,
    ) -> RankedDeploymentCandidates:
        if type(validated) is not ValidatedDeploymentCandidates:
            raise PolicyError("Deployment ranking requires typed validated candidates.")
        if type(configuration) is not DeploymentRankerConfiguration:
            raise PolicyError("Deployment ranking requires typed configuration.")
        # Reject stale actor/checkpoint evidence before calling user ranker code.
        validated.select(context, validated.accepted_ids[0], session=session)
        try:
            configuration.provenance.require_compatible_game_config(
                game_config=session.lifecycle.config,
                reward_profile_version=reward_profile_version,
            )
        except PolicyProvenanceError as exc:
            raise PolicyError(
                "Deployment ranker provenance is incompatible with this run."
            ) from exc
        engine_build_id = current_engine_build_id()
        game_config_hash = payload_digest(session.lifecycle.config.to_payload())
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
                "parameters": configuration.parameters,
            }
        )
        scores = ranker.score(actor_context, accepted, parameters=configuration.parameters)
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
            "engine_build_id": engine_build_id,
            "game_config_hash": game_config_hash,
            "configuration": configuration.to_payload(),
            "tie_break": DEPLOYMENT_RANKING_TIE_BREAK,
            "scores": [
                {"candidate_id": candidate_id, "value": by_id[candidate_id]}
                for candidate_id in validated.accepted_ids
            ],
            "selected_candidate_id": selected,
        }
        result = object.__new__(cls)
        object.__setattr__(result, "validated", validated)
        object.__setattr__(result, "configuration", configuration)
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
        configuration: DeploymentRankerConfiguration,
        reward_profile_version: str,
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
            configuration=configuration,
            reward_profile_version=reward_profile_version,
        )
        if observed != expected._payload_json:
            raise PolicyError("Deployment ranking evidence drifted from reproduction.")
        return expected
