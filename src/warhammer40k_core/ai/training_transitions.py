"""Operator-only finite transition evidence reproduced through ordinary engine commits."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import TypedDict, cast

from warhammer40k_core.adapters.access_control import ViewerContext
from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.adapters.projection import GameViewPayload
from warhammer40k_core.ai.player_policy import PlayerDecisionContext, payload_digest
from warhammer40k_core.ai.policy_contracts import PolicyProvenanceError, TrainingRow
from warhammer40k_core.ai.training_candidates import FiniteTrainingCandidateLink
from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine.decision_request import DecisionError
from warhammer40k_core.engine.event_log import (
    EventLogError,
    canonical_json,
    validate_json_value,
)
from warhammer40k_core.engine.phase import GameLifecycleError, LifecycleStatusKind

FINITE_TRANSITION_SCHEMA_VERSION = "finite-accepted-transition-v1"
ACCEPTED_RECORD_TIME_CONVENTION = "accepted-engine-records-from-origin-v1"


class TrainingTransitionError(PolicyProvenanceError):
    """A candidate/row/checkpoint join does not reproduce an accepted transition."""


class TransitionPositionPayload(TypedDict):
    stage: str
    setup_step: str | None
    battle_phase: str | None
    battle_round: int
    active_player_id: str | None


class FiniteAcceptedTransitionPayload(TypedDict):
    schema_version: str
    time_convention: str
    trajectory_id: str
    perspective_player_id: str
    actor_id: str
    training_candidate_link_hash: str
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


def _position(view: GameViewPayload) -> TransitionPositionPayload:
    return {
        "stage": view["stage"],
        "setup_step": view["current_setup_step"],
        "battle_phase": view["current_battle_phase"],
        "battle_round": view["battle_round"],
        "active_player_id": view["active_player_id"],
    }


@dataclass(frozen=True, slots=True, init=False)
class FiniteAcceptedTransition:
    """Immutable evidence created only by re-execution or its verifying loader.

    The trusted origin is supplied separately. Checkpoint commitments and engine
    identities are operator metadata, never policy model inputs. This proves a
    bounded transition from that origin, not origin reachability or label quality.
    """

    _evidence_json: str

    def __init__(self) -> None:
        raise TrainingTransitionError("Create accepted evidence through engine reproduction.")

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
        previous: FiniteAcceptedTransition | None = None,
    ) -> FiniteAcceptedTransition:
        if type(link) is not FiniteTrainingCandidateLink or (
            type(before) is not LocalGameSession
            or type(after) is not LocalGameSession
            or type(row) is not TrainingRow
            or type(context) is not PlayerDecisionContext
        ):
            raise TrainingTransitionError(
                "Finite transitions require typed links and local sessions."
            )
        if previous is not None and type(previous) is not cls:
            raise TrainingTransitionError("Previous transition must be typed accepted evidence.")
        trajectory_id = _identifier("Transition trajectory_id", trajectory_id)
        perspective_player_id = _identifier("Transition perspective", perspective_player_id)
        try:
            link.require_matches(row, context=context)
            actor = context.route.actor_id
            view = before.view(viewer_player_id=actor)
            if payload_digest(view) != context.observation_hash:
                raise TrainingTransitionError(
                    "Before checkpoint and historical observation drifted."
                )
            if perspective_player_id not in view["player_ids"]:
                raise TrainingTransitionError(
                    "Transition perspective is not an observation player."
                )
            before_hash = payload_digest(before.to_persistence_payload())
            after_hash = payload_digest(after.to_persistence_payload())
            offset = before.decision_record_count()
            actual_records = after.lifecycle.decision_controller.records
            if len(actual_records) <= offset:
                raise TrainingTransitionError("Transition has no new engine decision record.")
            selected = actual_records[offset]
            pending = before.lifecycle.pending_decision_request()
            if selected.record_id != row.decision_record_id or selected.request != pending:
                raise TrainingTransitionError(
                    "Training row does not name the submitted engine record."
                )
            # Reuse the viewer submission owner to resolve the chosen issued option.
            # A DecisionRecord alone may describe a recorded rejected attempt.
            probe = before.fork()
            status = probe.submit_viewer_option(
                viewer=ViewerContext.for_player(actor),
                request_id=context.request["request_id"],
                option_id=link.chosen_action_id,
                result_id=selected.result.result_id,
            )
            if status.status_kind is LifecycleStatusKind.ADVANCED:
                status = probe.advance_until_decision_or_terminal()
            if status.status_kind not in (
                LifecycleStatusKind.WAITING_FOR_DECISION,
                LifecycleStatusKind.TERMINAL,
            ):
                raise TrainingTransitionError(
                    f"Engine did not accept the finite transition: {status.status_kind}."
                )
            if payload_digest(probe.to_persistence_payload()) != after_hash:
                raise TrainingTransitionError(
                    "After checkpoint does not reproduce the engine outcome."
                )
            records = probe.lifecycle.decision_controller.records[offset:]
            if not records or records[0] != selected:
                raise TrainingTransitionError("Selected engine record failed exact reproduction.")
            after_view = probe.view(viewer_player_id=actor)
        except (PolicyProvenanceError, DecisionError, GameLifecycleError, EventLogError) as exc:
            raise TrainingTransitionError(
                "Finite accepted-transition join failed: " + str(exc)
            ) from exc

        prior = None if previous is None else previous.to_payload()
        if prior is not None and (
            prior["trajectory_id"] != trajectory_id
            or prior["perspective_player_id"] != perspective_player_id
            or prior["after_checkpoint_hash"] != before_hash
            or prior["outcome"] != "continuing"
        ):
            raise TrainingTransitionError(
                "Trajectory predecessor or checkpoint continuity drifted."
            )
        start = 0 if prior is None else prior["accepted_record_stop"]
        payload: FiniteAcceptedTransitionPayload = {
            "schema_version": FINITE_TRANSITION_SCHEMA_VERSION,
            "time_convention": ACCEPTED_RECORD_TIME_CONVENTION,
            "trajectory_id": trajectory_id,
            "perspective_player_id": perspective_player_id,
            "actor_id": actor,
            "training_candidate_link_hash": payload_digest(link.to_payload()),
            "previous_transition_hash": None if previous is None else previous.content_hash,
            "origin_checkpoint_hash": before_hash
            if prior is None
            else prior["origin_checkpoint_hash"],
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
        previous: FiniteAcceptedTransition | None = None,
    ) -> FiniteAcceptedTransition:
        if not isinstance(payload, dict) or (
            payload.keys() != FiniteAcceptedTransitionPayload.__annotations__.keys()
        ):
            raise TrainingTransitionError("Finite transition has missing or unknown fields.")
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
        try:
            observed = canonical_json(validate_json_value(cast(dict[str, object], payload)))
        except EventLogError as exc:
            raise TrainingTransitionError("Finite transition evidence must be JSON-safe.") from exc
        if observed != expected._evidence_json:
            raise TrainingTransitionError(
                "Finite transition evidence drifted from engine reproduction."
            )
        return expected

    def to_payload(self) -> FiniteAcceptedTransitionPayload:
        return cast(FiniteAcceptedTransitionPayload, json.loads(self._evidence_json))

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


_identifier = IdentifierValidator(TrainingTransitionError)
