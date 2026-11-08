"""Operator-only accepted transition evidence reproduced through ordinary engine commits."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import TypedDict, cast

from warhammer40k_core.adapters.access_control import ViewerContext
from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.adapters.projection import GameViewPayload
from warhammer40k_core.ai.player_policy import (
    PlayerDecisionContext,
    PolicyAction,
    PolicyError,
    payload_digest,
)
from warhammer40k_core.ai.policy_contracts import PolicyProvenanceError, TrainingRow
from warhammer40k_core.ai.training_candidates import FiniteTrainingCandidateLink
from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine.decision_request import DecisionError
from warhammer40k_core.engine.event_log import (
    EventLogError,
    JsonValue,
    canonical_json,
    validate_json_value,
)
from warhammer40k_core.engine.phase import GameLifecycleError, LifecycleStatusKind

FINITE_TRANSITION_SCHEMA_VERSION = "finite-accepted-transition-v1"
PARAMETERIZED_TRANSITION_SCHEMA_VERSION = "parameterized-accepted-transition-v1"
ACCEPTED_RECORD_TIME_CONVENTION = "accepted-engine-records-from-origin-v1"


class TrainingTransitionError(PolicyProvenanceError):
    """A candidate/row/checkpoint join does not reproduce an accepted transition."""


class TransitionPositionPayload(TypedDict):
    stage: str
    setup_step: str | None
    battle_phase: str | None
    battle_round: int
    active_player_id: str | None


class AcceptedTransitionPayload(TypedDict):
    schema_version: str
    time_convention: str
    trajectory_id: str
    perspective_player_id: str
    actor_id: str
    previous_transition_hash: str | None
    origin_checkpoint_hash: str
    before_checkpoint_hash: str
    after_checkpoint_hash: str
    before_observation_hash: str
    after_observation_hash: str
    accepted_record_start: int
    accepted_record_stop: int
    authoritative_record_id: str
    authoritative_request_id: str
    authoritative_option_id: str
    result_id: str
    record_hashes: list[str]
    before_position: TransitionPositionPayload
    after_position: TransitionPositionPayload
    outcome: str


class FiniteAcceptedTransitionPayload(AcceptedTransitionPayload):
    training_candidate_link_hash: str


class ParameterizedAcceptedTransitionPayload(AcceptedTransitionPayload):
    proposal_kind: str
    viewer_action: ParameterizedActionPayload


class ParameterizedActionPayload(TypedDict):
    actor_id: str
    request_id: str
    observation_hash: str
    proposal: JsonValue


def _position(view: GameViewPayload) -> TransitionPositionPayload:
    return {
        "stage": view["stage"],
        "setup_step": view["current_setup_step"],
        "battle_phase": view["current_battle_phase"],
        "battle_round": view["battle_round"],
        "active_player_id": view["active_player_id"],
    }


@dataclass(frozen=True, slots=True, init=False)
class _AcceptedTransition:
    """Shared immutable evidence storage; only concrete verifying factories create it."""

    _evidence_json: str

    def __init__(self) -> None:
        raise TrainingTransitionError("Create accepted evidence through engine reproduction.")

    def to_payload(self) -> AcceptedTransitionPayload:
        return cast(AcceptedTransitionPayload, json.loads(self._evidence_json))

    @property
    def content_hash(self) -> str:
        return payload_digest(self.to_payload())

    @property
    def accepted_record_start(self) -> int:
        return self.to_payload()["accepted_record_start"]

    @property
    def accepted_record_stop(self) -> int:
        return self.to_payload()["accepted_record_stop"]

    @property
    def actor_id(self) -> str:
        return self.to_payload()["actor_id"]

    @property
    def perspective_player_id(self) -> str:
        return self.to_payload()["perspective_player_id"]

    @property
    def authoritative_record_id(self) -> str:
        return self.to_payload()["authoritative_record_id"]

    @property
    def authoritative_request_id(self) -> str:
        return self.to_payload()["authoritative_request_id"]


@dataclass(frozen=True, slots=True, init=False)
class FiniteAcceptedTransition(_AcceptedTransition):
    """Finite row/link evidence reproduced through the ordinary viewer adapter.

    The trusted origin is supplied separately. Checkpoint commitments and engine
    identities are operator metadata, never policy model inputs. This proves a
    bounded transition from that origin, not origin reachability or label quality.
    A predecessor may be a verified bounded proposal in a mixed episode.
    """

    @classmethod
    def from_sessions(
        cls,
        link: FiniteTrainingCandidateLink,
        *,
        row: TrainingRow,
        context: PlayerDecisionContext,
        before: LocalGameSession,
        after: LocalGameSession,
        trajectory_id: str,
        perspective_player_id: str,
        previous: AcceptedTransition | None = None,
    ) -> FiniteAcceptedTransition:
        if (
            type(link) is not FiniteTrainingCandidateLink
            or type(row) is not TrainingRow
            or type(context) is not PlayerDecisionContext
        ):
            raise TrainingTransitionError("Finite transitions require typed links and rows.")
        try:
            link.require_matches(row, context=context)
            payload: FiniteAcceptedTransitionPayload = {
                **_reproduce(
                    context.select_option(link.chosen_action_id),
                    context=context,
                    before=before,
                    after=after,
                    trajectory_id=trajectory_id,
                    perspective_player_id=perspective_player_id,
                    previous=previous,
                    schema_version=FINITE_TRANSITION_SCHEMA_VERSION,
                    expected_record_id=row.decision_record_id,
                ),
                "training_candidate_link_hash": payload_digest(link.to_payload()),
            }
        except (PolicyProvenanceError, PolicyError) as exc:
            raise TrainingTransitionError(
                "Finite accepted-transition join failed: " + str(exc)
            ) from exc
        result = object.__new__(cls)
        object.__setattr__(result, "_evidence_json", canonical_json(validate_json_value(payload)))
        return result

    @classmethod
    def from_payload(
        cls,
        payload: object,
        *,
        link: FiniteTrainingCandidateLink,
        row: TrainingRow,
        context: PlayerDecisionContext,
        before: LocalGameSession,
        after: LocalGameSession,
        trajectory_id: str,
        perspective_player_id: str,
        previous: AcceptedTransition | None = None,
    ) -> FiniteAcceptedTransition:
        expected = cls.from_sessions(
            link,
            row=row,
            context=context,
            before=before,
            after=after,
            trajectory_id=trajectory_id,
            perspective_player_id=perspective_player_id,
            previous=previous,
        )
        _require_exact(payload, expected)
        return expected

    def to_payload(self) -> FiniteAcceptedTransitionPayload:
        return cast(FiniteAcceptedTransitionPayload, json.loads(self._evidence_json))


@dataclass(frozen=True, slots=True, init=False)
class ParameterizedAcceptedTransition(_AcceptedTransition):
    """Accepted deployment placement only, without candidate/row eligibility claims.

    The supplied action contains the actor-view proposal, never reconstructed
    authoritative IDs. Replay resolves it through the ordinary viewer adapter.
    """

    @classmethod
    def from_sessions(
        cls,
        action: PolicyAction,
        *,
        context: PlayerDecisionContext,
        before: LocalGameSession,
        after: LocalGameSession,
        trajectory_id: str,
        perspective_player_id: str,
        previous: AcceptedTransition | None = None,
    ) -> ParameterizedAcceptedTransition:
        if type(context) is not PlayerDecisionContext or type(action) is not PolicyAction:
            raise TrainingTransitionError(
                "Parameterized transitions require a typed context/action."
            )
        if (
            context.route.decision_type != "submit_deployment_placement"
            or context.route.proposal_kind != "deployment_placement"
            or context.route.stage != "setup"
            or context.route.setup_step != "deploy_armies"
            or action.proposal_json is None
            or action.option_id is not None
        ):
            raise TrainingTransitionError(
                "Only deployment placement proposal evidence is supported."
            )
        payload: ParameterizedAcceptedTransitionPayload = {
            **_reproduce(
                action,
                context=context,
                before=before,
                after=after,
                trajectory_id=trajectory_id,
                perspective_player_id=perspective_player_id,
                previous=previous,
                schema_version=PARAMETERIZED_TRANSITION_SCHEMA_VERSION,
            ),
            "proposal_kind": context.route.proposal_kind,
            "viewer_action": {
                "actor_id": action.actor_id,
                "request_id": action.request_id,
                "observation_hash": action.observation_hash,
                "proposal": json.loads(action.proposal_json),
            },
        }
        result = object.__new__(cls)
        object.__setattr__(result, "_evidence_json", canonical_json(validate_json_value(payload)))
        return result

    @classmethod
    def from_payload(
        cls,
        payload: object,
        *,
        action: PolicyAction,
        context: PlayerDecisionContext,
        before: LocalGameSession,
        after: LocalGameSession,
        trajectory_id: str,
        perspective_player_id: str,
        previous: AcceptedTransition | None = None,
    ) -> ParameterizedAcceptedTransition:
        expected = cls.from_sessions(
            action,
            context=context,
            before=before,
            after=after,
            trajectory_id=trajectory_id,
            perspective_player_id=perspective_player_id,
            previous=previous,
        )
        _require_exact(payload, expected)
        return expected

    def to_payload(self) -> ParameterizedAcceptedTransitionPayload:
        return cast(ParameterizedAcceptedTransitionPayload, json.loads(self._evidence_json))


type AcceptedTransition = FiniteAcceptedTransition | ParameterizedAcceptedTransition


def _reproduce(
    action: PolicyAction,
    *,
    context: PlayerDecisionContext,
    before: LocalGameSession,
    after: LocalGameSession,
    trajectory_id: str,
    perspective_player_id: str,
    previous: AcceptedTransition | None,
    schema_version: str,
    expected_record_id: str | None = None,
) -> AcceptedTransitionPayload:
    if (
        type(before) is not LocalGameSession
        or type(after) is not LocalGameSession
        or type(context) is not PlayerDecisionContext
        or type(action) is not PolicyAction
    ):
        raise TrainingTransitionError(
            "Transitions require typed actions, contexts and local sessions."
        )
    if previous is not None and type(previous) not in (
        FiniteAcceptedTransition,
        ParameterizedAcceptedTransition,
    ):
        raise TrainingTransitionError("Previous transition must be typed accepted evidence.")
    trajectory_id = _identifier("Transition trajectory_id", trajectory_id)
    perspective_player_id = _identifier("Transition perspective", perspective_player_id)
    try:
        actor = context.route.actor_id
        view = before.view(viewer_player_id=actor)
        if payload_digest(view) != context.observation_hash:
            raise TrainingTransitionError("Before checkpoint and historical observation drifted.")
        if (action.actor_id, action.request_id, action.observation_hash) != (
            actor,
            context.request["request_id"],
            context.observation_hash,
        ):
            raise TrainingTransitionError("Submitted action actor, request or observation drifted.")
        if perspective_player_id not in view["player_ids"]:
            raise TrainingTransitionError("Transition perspective is not an observation player.")
        before_hash = payload_digest(before.to_persistence_payload())
        after_hash = payload_digest(after.to_persistence_payload())
        offset = before.decision_record_count()
        actual_records = after.lifecycle.decision_controller.records
        if len(actual_records) <= offset:
            raise TrainingTransitionError("Transition has no new engine decision record.")
        selected = actual_records[offset]
        if selected.request != before.lifecycle.pending_decision_request() or (
            expected_record_id is not None and selected.record_id != expected_record_id
        ):
            raise TrainingTransitionError(
                "Training evidence does not name the submitted engine record."
            )
        # A recorded rule-rejected attempt is not an accepted transition. Reproduce
        # through the viewer owner, then require success before any advancement.
        probe = before.fork()
        if action.proposal_json is not None:
            status = probe.submit_viewer_parameterized_payload(
                viewer=ViewerContext.for_player(actor),
                request_id=action.request_id,
                payload=json.loads(action.proposal_json),
                result_id=selected.result.result_id,
            )
        else:
            status = probe.submit_viewer_option(
                viewer=ViewerContext.for_player(actor),
                request_id=action.request_id,
                option_id=cast(str, action.option_id),
                result_id=selected.result.result_id,
            )
        if status.status_kind is LifecycleStatusKind.ADVANCED:
            status = probe.advance_until_decision_or_terminal()
        if status.status_kind not in (
            LifecycleStatusKind.WAITING_FOR_DECISION,
            LifecycleStatusKind.TERMINAL,
        ):
            raise TrainingTransitionError(
                f"Engine did not accept the transition: {status.status_kind}."
            )
        if payload_digest(probe.to_persistence_payload()) != after_hash:
            raise TrainingTransitionError("After checkpoint does not reproduce the engine outcome.")
        records = probe.lifecycle.decision_controller.records[offset:]
        if not records or records[0] != selected:
            raise TrainingTransitionError("Selected engine record failed exact reproduction.")
        after_view = probe.view(viewer_player_id=actor)
    except (PolicyError, DecisionError, GameLifecycleError, EventLogError) as exc:
        raise TrainingTransitionError("Accepted-transition join failed: " + str(exc)) from exc
    prior = None if previous is None else previous.to_payload()
    if prior is not None and (
        prior["trajectory_id"] != trajectory_id
        or prior["perspective_player_id"] != perspective_player_id
        or prior["after_checkpoint_hash"] != before_hash
        or prior["outcome"] != "continuing"
    ):
        raise TrainingTransitionError("Trajectory predecessor or checkpoint continuity drifted.")
    start = 0 if prior is None else prior["accepted_record_stop"]
    return {
        "schema_version": schema_version,
        "time_convention": ACCEPTED_RECORD_TIME_CONVENTION,
        "trajectory_id": trajectory_id,
        "perspective_player_id": perspective_player_id,
        "actor_id": actor,
        "previous_transition_hash": None if previous is None else previous.content_hash,
        "origin_checkpoint_hash": before_hash if prior is None else prior["origin_checkpoint_hash"],
        "before_checkpoint_hash": before_hash,
        "after_checkpoint_hash": after_hash,
        "before_observation_hash": context.observation_hash,
        "after_observation_hash": payload_digest(after_view),
        "accepted_record_start": start,
        "accepted_record_stop": start + len(records),
        "authoritative_record_id": selected.record_id,
        "authoritative_request_id": selected.request.request_id,
        "authoritative_option_id": selected.result.selected_option_id,
        "result_id": selected.result.result_id,
        "record_hashes": [payload_digest(record.to_payload()) for record in records],
        "before_position": _position(view),
        "after_position": _position(after_view),
        "outcome": "terminal"
        if status.status_kind is LifecycleStatusKind.TERMINAL
        else "continuing",
    }


def _require_exact(payload: object, expected: AcceptedTransition) -> None:
    try:
        observed = canonical_json(validate_json_value(payload))
    except EventLogError as exc:
        raise TrainingTransitionError("Transition evidence must be JSON-safe.") from exc
    if observed != expected._evidence_json:
        raise TrainingTransitionError("Transition evidence drifted from engine reproduction.")


_identifier = IdentifierValidator(TrainingTransitionError)
