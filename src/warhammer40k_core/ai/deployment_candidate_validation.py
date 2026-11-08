"""Operator-only deployment validation on disposable ordinary session forks."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import cast

from warhammer40k_core.adapters.access_control import ViewerContext
from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.ai.deployment_candidate_search import (
    DeploymentCandidateExhaustedError,
    DeploymentCandidateSet,
    DeploymentSearchStop,
    require_budget,
)
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
from warhammer40k_core.engine.phase import LifecycleStatusKind

DEPLOYMENT_VALIDATION_SCHEMA = "deployment-candidate-validation-v1"


@dataclass(frozen=True, slots=True, init=False)
class ValidatedDeploymentCandidates:
    """Bounded receipts, not actor inputs or proof of an executed live transition.

    Each candidate starts from the same authoritative checkpoint on its own fork.
    Only ordinary INVALID results are rejected candidates; unsupported behavior
    and engine errors stop the operation. The live session is never submitted to.
    """

    candidate_set: DeploymentCandidateSet
    accepted_ids: tuple[str, ...]
    _payload_json: str

    def __init__(self) -> None:
        raise PolicyError("Validate deployment candidates through an ordinary session fork.")

    @classmethod
    def validate(
        cls,
        candidate_set: DeploymentCandidateSet,
        *,
        context: PlayerDecisionContext,
        session: LocalGameSession,
        validation_budget: int = 64,
        accepted_limit: int = 16,
    ) -> ValidatedDeploymentCandidates:
        if (
            type(candidate_set) is not DeploymentCandidateSet
            or type(session) is not LocalGameSession
        ):
            raise PolicyError("Deployment validation requires a typed set and local session.")
        candidate_set.require_context(context)
        require_budget(validation_budget, maximum=64)
        require_budget(accepted_limit, maximum=16)
        if (
            payload_digest(session.view(viewer_player_id=context.route.actor_id))
            != context.observation_hash
        ):
            raise PolicyError("Deployment validation session and actor observation drifted.")
        checkpoint_hash = payload_digest(session.to_persistence_payload())
        results: list[dict[str, JsonValue]] = []
        accepted: list[str] = []
        stop = DeploymentSearchStop.COMPLETE
        for candidate in candidate_set.candidates:
            if len(accepted) == accepted_limit:
                stop = DeploymentSearchStop.ACCEPTED_LIMIT
                break
            if len(results) == validation_budget:
                stop = DeploymentSearchStop.VALIDATION_BUDGET
                break
            action = candidate.select(context)
            probe = session.fork()
            status = probe.submit_viewer_parameterized_payload(
                viewer=ViewerContext.for_player(action.actor_id),
                request_id=action.request_id,
                payload=json.loads(cast(str, action.proposal_json)),
                result_id="deployment-probe:" + candidate.content_hash,
            )
            if status.status_kind not in (
                LifecycleStatusKind.ADVANCED,
                LifecycleStatusKind.WAITING_FOR_DECISION,
                LifecycleStatusKind.TERMINAL,
                LifecycleStatusKind.INVALID,
            ):
                raise PolicyError(f"Deployment validation unsupported: {status.status_kind}.")
            valid = status.status_kind is not LifecycleStatusKind.INVALID
            if valid:
                accepted.append(candidate.candidate_id)
            results.append(
                {
                    "candidate_id": candidate.candidate_id,
                    "accepted": valid,
                    "status": status.status_kind.value,
                    "message": status.message,
                    "diagnostics": status.payload,
                }
            )
        if payload_digest(session.to_persistence_payload()) != checkpoint_hash:
            raise PolicyError("Live deployment checkpoint changed during validation.")
        generation = candidate_set.to_payload()
        if not accepted:
            raise DeploymentCandidateExhaustedError(
                stop_reason=stop,
                raw_attempts=cast(int, generation["raw_attempts"]),
                duplicates=cast(int, generation["duplicates"]),
                validation_attempts=len(results),
            )
        payload = {
            "schema_version": DEPLOYMENT_VALIDATION_SCHEMA,
            "validation_id": "ordinary-viewer-submission-on-fresh-fork-v1",
            "candidate_set_hash": candidate_set.content_hash,
            "checkpoint_hash": checkpoint_hash,
            "validation_budget": validation_budget,
            "accepted_limit": accepted_limit,
            "validation_attempts": len(results),
            "accepted_count": len(accepted),
            "rejected_count": len(results) - len(accepted),
            "unvalidated_count": len(candidate_set.candidates) - len(results),
            "stop_reason": stop.value,
            "results": results,
        }
        result = object.__new__(cls)
        object.__setattr__(result, "candidate_set", candidate_set)
        object.__setattr__(result, "accepted_ids", tuple(accepted))
        object.__setattr__(result, "_payload_json", canonical_json(payload))
        return result

    @property
    def content_hash(self) -> str:
        return payload_digest(self.to_payload())

    def to_payload(self) -> dict[str, JsonValue]:
        return cast(dict[str, JsonValue], json.loads(self._payload_json))

    def select(
        self, context: PlayerDecisionContext, candidate_id: str, *, session: LocalGameSession
    ) -> PolicyAction:
        if type(session) is not LocalGameSession:
            raise PolicyError("Deployment selection requires its validated local session.")
        self.candidate_set.require_context(context)
        if payload_digest(session.to_persistence_payload()) != self.to_payload()["checkpoint_hash"]:
            raise PolicyError("Deployment validation checkpoint drifted before selection.")
        if candidate_id not in self.accepted_ids:
            raise PolicyError("Selected deployment candidate was not validated as accepted.")
        return next(
            candidate.select(context)
            for candidate in self.candidate_set.candidates
            if candidate.candidate_id == candidate_id
        )

    @classmethod
    def from_payload(
        cls,
        payload: object,
        *,
        candidate_set: DeploymentCandidateSet,
        context: PlayerDecisionContext,
        session: LocalGameSession,
    ) -> ValidatedDeploymentCandidates:
        if (
            not isinstance(payload, dict)
            or not {"validation_budget", "accepted_limit"} <= payload.keys()
        ):
            raise PolicyError("Deployment validation receipt requires its budgets.")
        value = cast(dict[str, object], payload)
        expected = cls.validate(
            candidate_set,
            context=context,
            session=session,
            validation_budget=require_budget(value["validation_budget"], maximum=64),
            accepted_limit=require_budget(value["accepted_limit"], maximum=16),
        )
        try:
            observed = canonical_json(validate_json_value(value))
        except EventLogError as exc:
            raise PolicyError("Deployment validation receipt must be JSON-safe.") from exc
        if observed != expected._payload_json:
            raise PolicyError("Deployment validation receipt drifted from engine reproduction.")
        return expected
