"""Operator-only episode and target admission through reproduced engine evidence."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import TypedDict, cast

from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.ai.player_policy import PlayerDecisionContext, payload_digest
from warhammer40k_core.ai.policy_contracts import PolicyProvenanceError, TrainingRow
from warhammer40k_core.ai.training_candidates import FiniteTrainingCandidateLink
from warhammer40k_core.ai.training_targets import (
    LinkedTrainingTarget,
    TargetEpisodeEnd,
    TargetMeaning,
    TargetValidity,
)
from warhammer40k_core.ai.training_transitions import (
    ACCEPTED_RECORD_TIME_CONVENTION,
    FiniteAcceptedTransition,
)
from warhammer40k_core.build_identity import current_engine_build_id
from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine.event_log import EventLogError, canonical_json, validate_json_value
from warhammer40k_core.engine.final_scoring import FinalScoringResult, FinalScoringResultPayload
from warhammer40k_core.engine.game_state import GameConfig
from warhammer40k_core.engine.phase import GameLifecycleError, GameLifecycleStage
from warhammer40k_core.engine.replay import ReplaySourceIdentityPayload

EPISODE_ORIGIN_SCHEMA_VERSION = "verified-episode-origin-v1"
EPISODE_ADMISSION_SCHEMA_VERSION = "finite-episode-admission-v1"
TARGET_ADMISSION_SCHEMA_VERSION = "finite-target-admission-v1"
TERMINAL_TARGET_PRODUCER = "engine-final-scoring-v1"
MISSING_TARGET_PRODUCER = "episode-boundary-v1"


class TrainingAdmissionError(PolicyProvenanceError):
    """Episode reachability, source identity or label eligibility failed."""


class EpisodeOriginPayload(TypedDict):
    schema_version: str
    engine_build_id: str
    source_identity: ReplaySourceIdentityPayload
    initial_checkpoint_hash: str
    origin_checkpoint_hash: str
    prefix_record_count: int


class FiniteEpisodePayload(TypedDict):
    schema_version: str
    time_convention: str
    origin: EpisodeOriginPayload
    trajectory_id: str
    perspective_player_id: str
    transition_hashes: list[str]
    final_checkpoint_hash: str
    accepted_record_stop: int
    episode_end: str
    stop_reason: str | None
    final_result: FinalScoringResultPayload | None


class AdmittedTargetPayload(TypedDict):
    schema_version: str
    episode_hash: str
    transition_hash: str
    linked_target_hash: str
    accepted_record_start: int
    accepted_record_stop: int
    eligible_for_learning: bool


@dataclass(frozen=True, slots=True, init=False)
class VerifiedEpisodeOrigin:
    """An ordinary startup and exactly replayed prefix, relative to trusted config.

    This verifies reachability, not the external correctness or workload support
    of the caller's separately supplied configuration. Private replay/build/source
    metadata must never be passed to a policy or model encoder.
    """

    _evidence_json: str

    def __init__(self) -> None:
        raise TrainingAdmissionError("Verify an episode origin through ordinary startup.")

    @classmethod
    def from_session(
        cls, session: LocalGameSession, *, config: GameConfig
    ) -> VerifiedEpisodeOrigin:
        if type(session) is not LocalGameSession or type(config) is not GameConfig:
            raise TrainingAdmissionError("Episode origin requires a local session and config.")
        try:
            fresh = LocalGameSession()
            fresh.start(config)
            fresh.advance_until_decision_or_terminal()
            initial = fresh.to_persistence_payload()
            artifact = session.replay_artifact(artifact_id="episode-origin")
            if payload_digest(session.lifecycle.config.to_payload()) != payload_digest(
                config.to_payload()
            ) or payload_digest(artifact["initial_lifecycle"]) != payload_digest(
                fresh.lifecycle.to_payload()
            ):
                raise TrainingAdmissionError("Episode origin does not start from ordinary config.")
            # Restore verifies the full lifecycle, decisions, events and private RNG
            # by replay. Hashes or a replay rooted in an arbitrary state are insufficient.
            checkpoint = session.to_persistence_payload()
            restored = LocalGameSession.from_persistence_payload(checkpoint)
            if restored.lifecycle.pending_decision_request() is None:
                raise TrainingAdmissionError("Episode origin requires a pending decision boundary.")
        except (GameLifecycleError, EventLogError) as exc:
            raise TrainingAdmissionError("Episode origin replay failed: " + str(exc)) from exc
        payload: EpisodeOriginPayload = {
            "schema_version": EPISODE_ORIGIN_SCHEMA_VERSION,
            "engine_build_id": current_engine_build_id(),
            "source_identity": artifact["source_identity"],
            "initial_checkpoint_hash": payload_digest(initial),
            "origin_checkpoint_hash": payload_digest(checkpoint),
            "prefix_record_count": restored.decision_record_count(),
        }
        result = object.__new__(cls)
        object.__setattr__(result, "_evidence_json", _json(payload))
        return result

    @classmethod
    def from_payload(
        cls, payload: object, *, session: LocalGameSession, config: GameConfig
    ) -> VerifiedEpisodeOrigin:
        expected = cls.from_session(session, config=config)
        _require_exact(payload, expected.to_payload())
        return expected

    def to_payload(self) -> EpisodeOriginPayload:
        return cast(EpisodeOriginPayload, json.loads(self._evidence_json))

    @property
    def content_hash(self) -> str:
        return payload_digest(self.to_payload())


@dataclass(frozen=True, slots=True, init=False)
class FiniteEpisodeAdmission:
    """A contiguous finite slice from a reachable origin to a declared boundary.

    Terminal results come from the engine. Truncation, abort and unsupported
    reasons are explicit operator declarations, not authenticated diagnoses.
    """

    _evidence_json: str

    def __init__(self) -> None:
        raise TrainingAdmissionError("Admit an episode through a verified finite chain.")

    @classmethod
    def from_transitions(
        cls,
        origin: VerifiedEpisodeOrigin,
        *,
        transitions: tuple[FiniteAcceptedTransition, ...],
        final_session: LocalGameSession,
        episode_end: TargetEpisodeEnd,
        stop_reason: str | None = None,
    ) -> FiniteEpisodeAdmission:
        if (
            type(origin) is not VerifiedEpisodeOrigin
            or type(final_session) is not LocalGameSession
            or type(episode_end) is not TargetEpisodeEnd
            or type(transitions) is not tuple
            or not transitions
            or any(type(item) is not FiniteAcceptedTransition for item in transitions)
        ):
            raise TrainingAdmissionError(
                "Episode admission requires typed nonempty finite evidence."
            )
        root = origin.to_payload()
        if root["engine_build_id"] != current_engine_build_id():
            raise TrainingAdmissionError("Episode engine build drifted.")
        previous: FiniteAcceptedTransition | None = None
        checkpoint_hash = root["origin_checkpoint_hash"]
        stop = 0
        first = transitions[0].to_payload()
        records = final_session.lifecycle.decision_controller.records
        for transition in transitions:
            item = transition.to_payload()
            if (
                item["time_convention"] != ACCEPTED_RECORD_TIME_CONVENTION
                or item["origin_checkpoint_hash"] != root["origin_checkpoint_hash"]
                or item["before_checkpoint_hash"] != checkpoint_hash
                or item["previous_transition_hash"]
                != (None if previous is None else previous.content_hash)
                or item["accepted_record_start"] != stop
                or item["trajectory_id"] != first["trajectory_id"]
                or item["perspective_player_id"] != first["perspective_player_id"]
                or (previous is not None and previous.to_payload()["outcome"] != "continuing")
            ):
                raise TrainingAdmissionError("Episode transition chain is discontinuous.")
            start_index = root["prefix_record_count"] + stop
            stop = item["accepted_record_stop"]
            if item["record_hashes"] != [
                payload_digest(record.to_payload())
                for record in records[start_index : root["prefix_record_count"] + stop]
            ]:
                raise TrainingAdmissionError("Episode accepted record sequence drifted.")
            checkpoint_hash = item["after_checkpoint_hash"]
            previous = transition
        if (
            checkpoint_hash != payload_digest(final_session.to_persistence_payload())
            or len(records) != root["prefix_record_count"] + stop
            or payload_digest(final_session.lifecycle.config.to_payload())
            != root["source_identity"]["game_config_hash"]
        ):
            raise TrainingAdmissionError("Episode endpoint or source config drifted.")
        state = final_session.lifecycle.state
        if state is None:
            raise TrainingAdmissionError("Episode endpoint requires an engine state.")
        terminal = state.stage is GameLifecycleStage.COMPLETE
        if terminal != (episode_end is TargetEpisodeEnd.TERMINAL):
            raise TrainingAdmissionError("Episode end classification contradicts engine state.")
        if (transitions[-1].to_payload()["outcome"] == "terminal") != terminal:
            raise TrainingAdmissionError("Episode terminal transition drifted.")
        final_result: FinalScoringResultPayload | None = None
        if terminal:
            if stop_reason is not None:
                raise TrainingAdmissionError("Terminal episodes cannot declare a stop reason.")
            final_result = FinalScoringResult.from_payload(
                cast(FinalScoringResultPayload, state.game_result_payload())
            ).to_payload()
        else:
            stop_reason = _identifier("Episode stop_reason", stop_reason)
        payload: FiniteEpisodePayload = {
            "schema_version": EPISODE_ADMISSION_SCHEMA_VERSION,
            "time_convention": ACCEPTED_RECORD_TIME_CONVENTION,
            "origin": root,
            "trajectory_id": first["trajectory_id"],
            "perspective_player_id": first["perspective_player_id"],
            "transition_hashes": [item.content_hash for item in transitions],
            "final_checkpoint_hash": checkpoint_hash,
            "accepted_record_stop": stop,
            "episode_end": episode_end.value,
            "stop_reason": stop_reason,
            "final_result": final_result,
        }
        result = object.__new__(cls)
        object.__setattr__(result, "_evidence_json", _json(payload))
        return result

    @classmethod
    def from_payload(
        cls,
        payload: object,
        *,
        origin: VerifiedEpisodeOrigin,
        transitions: tuple[FiniteAcceptedTransition, ...],
        final_session: LocalGameSession,
        episode_end: TargetEpisodeEnd,
        stop_reason: str | None = None,
    ) -> FiniteEpisodeAdmission:
        expected = cls.from_transitions(
            origin,
            transitions=transitions,
            final_session=final_session,
            episode_end=episode_end,
            stop_reason=stop_reason,
        )
        _require_exact(payload, expected.to_payload())
        return expected

    def to_payload(self) -> FiniteEpisodePayload:
        return cast(FiniteEpisodePayload, json.loads(self._evidence_json))

    @property
    def content_hash(self) -> str:
        return payload_digest(self.to_payload())


@dataclass(frozen=True, slots=True, init=False)
class AdmittedTrainingTarget:
    """Exact row/source/time join plus a verified terminal value or excluded missingness."""

    _evidence_json: str

    def __init__(self) -> None:
        raise TrainingAdmissionError("Admit a target through verified episode evidence.")

    @classmethod
    def from_episode(
        cls,
        linked: LinkedTrainingTarget,
        *,
        episode: FiniteEpisodeAdmission,
        transition: FiniteAcceptedTransition,
        link: FiniteTrainingCandidateLink,
        row: TrainingRow,
        context: PlayerDecisionContext,
        config: GameConfig,
        reward_profile_version: str,
    ) -> AdmittedTrainingTarget:
        if (
            type(linked) is not LinkedTrainingTarget
            or type(episode) is not FiniteEpisodeAdmission
            or type(transition) is not FiniteAcceptedTransition
            or type(config) is not GameConfig
            or type(row) is not TrainingRow
        ):
            raise TrainingAdmissionError(
                "Target admission requires typed episode and row evidence."
            )
        try:
            linked.require_matches(link, row=row, context=context)
            # Deliberately offers no cross-version override for historical labels.
            row.policy_provenance.require_compatible_game_config(
                game_config=config, reward_profile_version=reward_profile_version
            )
        except PolicyProvenanceError as exc:
            raise TrainingAdmissionError("Target source or row compatibility failed.") from exc
        boundary = episode.to_payload()
        item = transition.to_payload()
        target = linked.target
        if (
            boundary["origin"]["engine_build_id"] != current_engine_build_id()
            or boundary["origin"]["source_identity"]["game_config_hash"]
            != payload_digest(config.to_payload())
            or transition.content_hash not in boundary["transition_hashes"]
            or item["training_candidate_link_hash"] != payload_digest(link.to_payload())
            or item["authoritative_record_id"] != row.decision_record_id
            or boundary["perspective_player_id"] != target.perspective_player_id
            or boundary["episode_end"] != target.episode_end.value
        ):
            raise TrainingAdmissionError(
                "Target episode, transition, perspective or source drifted."
            )
        if target.validity is TargetValidity.MISSING:
            if (
                target.producer_id != MISSING_TARGET_PRODUCER
                or target.evidence_hash != episode.content_hash
                or target.missing_reason != boundary["stop_reason"]
                or target.episode_end is TargetEpisodeEnd.TERMINAL
            ):
                raise TrainingAdmissionError(
                    "Missing target requires the declared nonterminal boundary."
                )
        else:
            if target.meaning is TargetMeaning.LOCAL_REFERENCE:
                raise TrainingAdmissionError(
                    "Observed local references require a verified calculator."
                )
            result_payload = boundary["final_result"]
            if (
                result_payload is None
                or target.producer_id != TERMINAL_TARGET_PRODUCER
                or target.evidence_hash != payload_digest(result_payload)
            ):
                raise TrainingAdmissionError(
                    "Observed target requires engine final-scoring evidence."
                )
            result = FinalScoringResult.from_payload(result_payload)
            scores = {score.player_id: score.victory_points for score in result.final_scores}
            if set(scores) != set(config.player_ids) or len(scores) != 2:
                raise TrainingAdmissionError("Match targets require exactly two scored players.")
            if target.meaning is TargetMeaning.MATCH_UTILITY:
                expected = (
                    0.5
                    if result.is_draw
                    else float(target.perspective_player_id in result.winner_player_ids)
                )
            else:
                expected = float(
                    scores[target.perspective_player_id]
                    - sum(
                        value
                        for player, value in scores.items()
                        if player != target.perspective_player_id
                    )
                )
            if target.value != expected:
                raise TrainingAdmissionError(
                    "Observed target value contradicts engine final scoring."
                )
        payload: AdmittedTargetPayload = {
            "schema_version": TARGET_ADMISSION_SCHEMA_VERSION,
            "episode_hash": episode.content_hash,
            "transition_hash": transition.content_hash,
            "linked_target_hash": linked.content_hash,
            "accepted_record_start": item["accepted_record_start"],
            "accepted_record_stop": boundary["accepted_record_stop"],
            "eligible_for_learning": target.validity is TargetValidity.OBSERVED,
        }
        result_target = object.__new__(cls)
        object.__setattr__(result_target, "_evidence_json", _json(payload))
        return result_target

    @classmethod
    def from_payload(
        cls,
        payload: object,
        *,
        linked: LinkedTrainingTarget,
        episode: FiniteEpisodeAdmission,
        transition: FiniteAcceptedTransition,
        link: FiniteTrainingCandidateLink,
        row: TrainingRow,
        context: PlayerDecisionContext,
        config: GameConfig,
        reward_profile_version: str,
    ) -> AdmittedTrainingTarget:
        expected = cls.from_episode(
            linked,
            episode=episode,
            transition=transition,
            link=link,
            row=row,
            context=context,
            config=config,
            reward_profile_version=reward_profile_version,
        )
        _require_exact(payload, expected.to_payload())
        return expected

    def to_payload(self) -> AdmittedTargetPayload:
        return cast(AdmittedTargetPayload, json.loads(self._evidence_json))

    @property
    def content_hash(self) -> str:
        return payload_digest(self.to_payload())


def _json(payload: object) -> str:
    try:
        return canonical_json(validate_json_value(payload))
    except EventLogError as exc:
        raise TrainingAdmissionError("Admission evidence must be JSON-safe.") from exc


def _require_exact(payload: object, expected: object) -> None:
    if _json(payload) != _json(expected):
        raise TrainingAdmissionError("Admission evidence drifted from reproduction.")


_identifier = IdentifierValidator(TrainingAdmissionError)
