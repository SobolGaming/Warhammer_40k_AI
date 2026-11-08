"""Detached actor-view snapshot of one proposed deployment placement, without legality claims."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import TypedDict, cast

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

DEPLOYMENT_CANDIDATE_SCHEMA_VERSION = "deployment-placement-candidate-v1"


class DeploymentCandidatePayload(TypedDict):
    schema_version: str
    candidate_id: str
    actor_id: str
    request_id: str
    observation_hash: str
    proposal: JsonValue


@dataclass(frozen=True, slots=True, init=False)
class DeploymentPlacementCandidate:
    """One supplied proposal, not a generated search set or proof of legality.

    The canonical snapshot contains only the bound actor-view action. Acceptance
    and authoritative record evidence belong in the separate operator row link.
    """

    _action_json: str

    def __init__(self) -> None:
        raise PolicyError("Capture a deployment candidate from a bound player action.")

    @classmethod
    def from_action(
        cls, action: PolicyAction, *, context: PlayerDecisionContext
    ) -> DeploymentPlacementCandidate:
        if type(action) is not PolicyAction or type(context) is not PlayerDecisionContext:
            raise PolicyError("Deployment candidates require a typed action and player context.")
        if (
            context.route.decision_type != "submit_deployment_placement"
            or context.route.proposal_kind != "deployment_placement"
            or context.route.stage != "setup"
            or context.route.setup_step != "deploy_armies"
            or action.proposal_json is None
            or action.option_id is not None
        ):
            raise PolicyError("Only deployment placement proposal candidates are supported.")
        if (action.actor_id, action.request_id, action.observation_hash) != (
            context.route.actor_id,
            context.request["request_id"],
            context.observation_hash,
        ):
            raise PolicyError("Deployment candidate actor, request or observation drifted.")
        proposal = json.loads(action.proposal_json)
        if proposal.get("proposal_kind") != "deployment_placement":
            raise PolicyError("Deployment candidate proposal kind drifted.")
        action_payload = {
            "actor_id": action.actor_id,
            "request_id": action.request_id,
            "observation_hash": action.observation_hash,
            "proposal": proposal,
        }
        try:
            encoded = canonical_json(validate_json_value(action_payload))
        except EventLogError as exc:
            raise PolicyError("Deployment candidate must be JSON-safe.") from exc
        result = object.__new__(cls)
        object.__setattr__(result, "_action_json", encoded)
        return result

    @property
    def candidate_id(self) -> str:
        return "deployment-placement:" + payload_digest(json.loads(self._action_json))

    @property
    def content_hash(self) -> str:
        return payload_digest(self.to_payload())

    def select(self, context: PlayerDecisionContext) -> PolicyAction:
        if type(context) is not PlayerDecisionContext:
            raise PolicyError("Deployment candidates require a typed player context.")
        value = self.to_payload()
        action = context.propose(value["proposal"])
        if self != type(self).from_action(action, context=context):
            raise PolicyError("Deployment candidate context or proposal binding drifted.")
        return action

    def to_payload(self) -> DeploymentCandidatePayload:
        return cast(
            DeploymentCandidatePayload,
            {
                "schema_version": DEPLOYMENT_CANDIDATE_SCHEMA_VERSION,
                "candidate_id": self.candidate_id,
                **json.loads(self._action_json),
            },
        )

    @classmethod
    def from_payload(
        cls, payload: object, *, context: PlayerDecisionContext
    ) -> DeploymentPlacementCandidate:
        if type(context) is not PlayerDecisionContext:
            raise PolicyError("Deployment candidates require a typed player context.")
        if (
            not isinstance(payload, dict)
            or payload.keys() != DeploymentCandidatePayload.__annotations__.keys()
        ):
            raise PolicyError("Deployment candidate has missing or unknown fields.")
        value = cast(dict[str, object], payload)
        try:
            proposal = validate_json_value(value["proposal"])
            action = context.propose(proposal)
            expected = cls.from_action(action, context=context)
            observed = canonical_json(validate_json_value(value))
        except EventLogError as exc:
            raise PolicyError("Deployment candidate must be JSON-safe.") from exc
        if observed != canonical_json(expected.to_payload()):
            raise PolicyError("Deployment candidate payload or context binding drifted.")
        return expected
