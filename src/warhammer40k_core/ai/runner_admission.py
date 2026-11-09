"""Bounded operator-only runner, episode and deployment dataset joins."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from typing import cast

from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.ai.deployment_experiment import DeploymentExperimentProvenance
from warhammer40k_core.ai.player_policy import PlayerDecisionContext, PolicyRoute, payload_digest
from warhammer40k_core.ai.runner import DecisionTiming, RunLimits, RunManifest, RunReport
from warhammer40k_core.ai.training_admission import (
    AdmittedTrainingTarget,
    FiniteEpisodeAdmission,
    MixedEpisodeAdmission,
    TrainingAdmissionError,
    VerifiedEpisodeOrigin,
)
from warhammer40k_core.ai.training_targets import LinkedTrainingTarget
from warhammer40k_core.ai.training_transitions import (
    AcceptedTransition,
    FiniteAcceptedTransition,
    ParameterizedAcceptedTransition,
)
from warhammer40k_core.build_identity import current_engine_build_id
from warhammer40k_core.engine.event_log import JsonValue, canonical_json, validate_json_value
from warhammer40k_core.engine.phase import GameLifecycleStage


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise TrainingAdmissionError(message)


def _record_hashes(session: LocalGameSession) -> list[str]:
    return [
        payload_digest(record.to_payload())
        for record in session.lifecycle.decision_controller.records
    ]


def _seconds(value: object) -> bool:
    return (
        type(value) in (int, float)
        and math.isfinite(cast(float, value))
        and cast(float, value) >= 0
    )


@dataclass(frozen=True, slots=True, init=False)
class RunnerAdmission:
    """Join an entire reported run; only a reproduced accepted prefix may train.

    Checkpoints are trusted operator snapshots before each dispatch. Their replay
    and complete record-prefix joins are checked, never exposed to the policy.
    Timing, callback identity and diagnoses remain producer declarations. This
    is not callback authentication or a durable ledger of unreported crashes.
    """

    _payload_json: str

    def __init__(self) -> None:
        raise TrainingAdmissionError("Admit runner evidence through its complete boundaries.")

    @classmethod
    def from_report(
        cls,
        report: RunReport,
        *,
        origin: VerifiedEpisodeOrigin,
        initial_session: LocalGameSession,
        final_session: LocalGameSession,
        attempt_sessions: tuple[LocalGameSession, ...],
        transitions: tuple[AcceptedTransition, ...] = (),
        episode: FiniteEpisodeAdmission | MixedEpisodeAdmission | None = None,
    ) -> RunnerAdmission:
        _require(
            type(report) is RunReport
            and type(report.manifest) is RunManifest
            and type(origin) is VerifiedEpisodeOrigin
            and type(initial_session) is LocalGameSession
            and type(final_session) is LocalGameSession
            and type(attempt_sessions) is tuple
            and all(type(s) is LocalGameSession for s in attempt_sessions)
            and type(transitions) is tuple
            and all(
                type(t) in (FiniteAcceptedTransition, ParameterizedAcceptedTransition)
                for t in transitions
            )
            and (
                episode is None or type(episode) in (FiniteEpisodeAdmission, MixedEpisodeAdmission)
            ),
            "Runner admission requires typed complete evidence.",
        )
        assert report.manifest is not None
        manifest = report.manifest.to_payload()
        root = origin.to_payload()
        initial_hash = payload_digest(initial_session.to_persistence_payload())
        final_hash = payload_digest(final_session.to_persistence_payload())
        _require(
            set(manifest)
            == {
                "schema",
                "engine_build_id",
                "initial_checkpoint",
                "initial_record_count",
                "session_identity",
                "router_identity",
                "declared_registrations",
                "registration_evidence",
                "time_limit_enforcement",
                "policy_seed",
                "max_decisions",
                "max_seconds",
                "stop_at",
            }
            and manifest["schema"] == "bounded-player-policy-run-v3"
            and manifest["engine_build_id"] == root["engine_build_id"] == current_engine_build_id()
            and manifest["initial_checkpoint"] == root["origin_checkpoint_hash"] == initial_hash
            and manifest["initial_record_count"]
            == root["prefix_record_count"]
            == initial_session.decision_record_count()
            and manifest["session_identity"] == initial_session.authoritative_identity_payload()
            and manifest["registration_evidence"] == "declared-unverified"
            and manifest["time_limit_enforcement"] == "cooperative-between-calls"
            and report.run_id == report.manifest.run_id
            and report.final_checkpoint_hash == final_hash
            and type(report.final_record_count) is int
            and report.final_record_count == final_session.decision_record_count(),
            "Runner source, origin or final checkpoint drifted.",
        )
        RunLimits(
            cast(int, manifest["policy_seed"]),
            cast(int, manifest["max_decisions"]),
            cast(float, manifest["max_seconds"]),
        )
        registrations = manifest["declared_registrations"]
        _require(
            isinstance(registrations, list)
            and manifest["router_identity"] == payload_digest(registrations),
            "Runner registration identity drifted.",
        )
        assert isinstance(registrations, list)
        declared: dict[PolicyRoute, str] = {}
        for registration in registrations:
            _require(
                isinstance(registration, dict)
                and set(registration) == {"route", "policy_id", "configuration"},
                "Malformed runner registration.",
            )
            assert isinstance(registration, dict)
            route = registration["route"]
            _require(
                isinstance(route, list)
                and len(route) == 6
                and isinstance(registration["configuration"], dict)
                and type(registration["policy_id"]) is str
                and bool(registration["policy_id"].strip()),
                "Malformed declared runner policy.",
            )
            assert isinstance(route, list)
            key = PolicyRoute(
                cast(str, route[0]),
                cast(str, route[1]),
                cast(str, route[2]),
                cast(str | None, route[3]),
                cast(str | None, route[4]),
                cast(str | None, route[5]),
            )
            _require(key not in declared, "Duplicate declared runner route.")
            declared[key] = cast(str, registration["policy_id"])
        _require(
            type(report.decisions) is tuple
            and len(attempt_sessions) == len(report.decisions)
            and len(transitions) <= len(report.decisions) <= cast(int, manifest["max_decisions"])
            and _seconds(report.elapsed_seconds),
            "Runner attempt inventory or elapsed time drifted.",
        )
        final_records = _record_hashes(final_session)
        sessions = (initial_session, *attempt_sessions, final_session)
        for session in sessions:
            checkpoint = session.to_persistence_payload()
            restored = LocalGameSession.from_persistence_payload(checkpoint)
            _require(
                restored.to_persistence_payload() == checkpoint
                and session.lifecycle.config.to_payload()
                == initial_session.lifecycle.config.to_payload()
                and _record_hashes(session) == final_records[: session.decision_record_count()],
                "Runner checkpoint replay or record prefix drifted.",
            )
        _require(
            not attempt_sessions
            or payload_digest(attempt_sessions[0].to_persistence_payload()) == initial_hash,
            "Runner first attempt skipped its origin.",
        )
        if not attempt_sessions:
            _require(initial_hash == final_hash, "Runner without attempts changed its endpoint.")
        for index, (attempt, before) in enumerate(
            zip(report.decisions, attempt_sessions, strict=True)
        ):
            after = (
                attempt_sessions[index + 1] if index + 1 < len(attempt_sessions) else final_session
            )
            cls._check_attempt(
                attempt, before=before, after=after, manifest=manifest, declared=declared
            )
            _require(
                index == len(report.decisions) - 1 or attempt.failure_stage is None,
                "Runner continued after a failed attempt.",
            )
            if index < len(transitions):
                item = transitions[index].to_payload()
                _require(
                    attempt.accepted
                    and attempt.failure_stage is None
                    and item["origin_checkpoint_hash"] == initial_hash
                    and item["before_checkpoint_hash"]
                    == payload_digest(before.to_persistence_payload())
                    and item["after_checkpoint_hash"]
                    == payload_digest(after.to_persistence_payload())
                    and item["authoritative_request_id"] == attempt.request_id
                    and item["actor_id"] == attempt.route.actor_id
                    and item["before_observation_hash"] == attempt.observation_hash
                    and item["result_id"] == f"ai:{attempt.choice_seed:064x}"
                    and item["accepted_record_start"]
                    == before.decision_record_count() - root["prefix_record_count"]
                    and item["accepted_record_stop"]
                    == after.decision_record_count() - root["prefix_record_count"]
                    and item["record_hashes"]
                    == final_records[before.decision_record_count() : after.decision_record_count()]
                    and item["previous_transition_hash"]
                    == (None if index == 0 else transitions[index - 1].content_hash),
                    "Runner accepted transition or choice binding drifted.",
                )
        cls._check_stop(report, final_session, manifest)
        if episode is not None:
            boundary = episode.to_payload()
            _require(
                bool(transitions)
                and boundary["origin"] == root
                and boundary["transition_hashes"] == [t.content_hash for t in transitions]
                and boundary["final_checkpoint_hash"]
                == transitions[-1].to_payload()["after_checkpoint_hash"],
                "Runner episode does not cover the reproduced prefix.",
            )
            # An interrupted suffix may change the checkpoint (a recorded rejection).
            # Only a full-run endpoint can claim the runner's stop classification.
            if boundary["final_checkpoint_hash"] == final_hash:
                expected = (
                    "terminal"
                    if report.stop_reason == "terminal"
                    else "truncated"
                    if report.stop_reason == "requested_boundary"
                    else "unsupported"
                    if report.failure_reason in ("unsupported_route", "unsupported_engine")
                    else "aborted"
                )
                _require(
                    boundary["episode_end"] == expected
                    and boundary["stop_reason"]
                    == (
                        None
                        if expected == "terminal"
                        else report.failure_reason or report.stop_reason
                    ),
                    "Episode end contradicts the runner stop.",
                )
            else:
                _require(
                    report.stop_reason == "error"
                    and boundary["episode_end"] == "truncated"
                    and boundary["stop_reason"] == "accepted-prefix-before-runner-failure",
                    "Failed suffix requires an explicitly truncated accepted prefix.",
                )
        result = object.__new__(cls)
        object.__setattr__(
            result,
            "_payload_json",
            canonical_json(
                validate_json_value(
                    {
                        "schema_version": "runner-admission-v1",
                        "report": report.to_payload(),
                        "origin": root,
                        "attempt_checkpoint_hashes": [
                            payload_digest(s.to_persistence_payload()) for s in attempt_sessions
                        ],
                        "transitions": [t.to_payload() for t in transitions],
                        "transition_hashes": [t.content_hash for t in transitions],
                        "episode": None if episode is None else episode.to_payload(),
                        "episode_hash": None if episode is None else episode.content_hash,
                    }
                )
            ),
        )
        return result

    @staticmethod
    def _check_attempt(
        attempt: DecisionTiming,
        *,
        before: LocalGameSession,
        after: LocalGameSession,
        manifest: dict[str, JsonValue],
        declared: dict[PolicyRoute, str],
    ) -> None:
        _require(
            type(attempt) is DecisionTiming and type(attempt.route) is PolicyRoute,
            "Malformed runner attempt.",
        )
        request = before.lifecycle.pending_decision_request()
        _require(
            request is not None
            and request.request_id == attempt.request_id
            and request.actor_id == attempt.route.actor_id,
            "Runner authoritative request drifted.",
        )
        view = before.view(viewer_player_id=attempt.route.actor_id)
        pending = view["pending_decision"]
        assert pending is not None
        seed = int(
            payload_digest(
                [
                    "player-policy-choice-v1",
                    manifest["policy_seed"],
                    view["game_id"],
                    attempt.route.actor_id,
                    pending["request_id"],
                ]
            ),
            16,
        )
        context = PlayerDecisionContext.from_view(view, choice_seed=seed)
        _require(
            attempt.route == context.route
            and attempt.viewer_request_id == context.request["request_id"]
            and attempt.observation_hash == context.observation_hash
            and type(attempt.choice_seed) is int
            and attempt.choice_seed == seed
            and attempt.policy_id == declared.get(context.route)
            and type(attempt.accepted) is bool
            and attempt.accepted == (attempt.submission_outcome == "accepted")
            and attempt.submission_outcome
            in ("accepted", "rejected", "unverified", "not_submitted")
            and type(attempt.recorded_decisions) is int
            and attempt.recorded_decisions >= 0
            and attempt.recorded_decisions
            == after.decision_record_count() - before.decision_record_count()
            and _seconds(attempt.choice_seconds)
            and _seconds(attempt.submit_seconds),
            "Runner context, registration or record accounting drifted.",
        )
        stages = {
            "not_submitted": ("routing", "choice", "validation"),
            "unverified": ("submission",),
            "rejected": ("submission",),
            "accepted": (None, "progress"),
        }
        _require(
            attempt.failure_stage in stages[attempt.submission_outcome]
            and (not attempt.accepted or attempt.recorded_decisions > 0)
            and ((attempt.policy_id is None) == (attempt.failure_stage == "routing")),
            "Runner submission classification drifted.",
        )
        if attempt.submission_outcome == "not_submitted":
            _require(
                before.to_persistence_payload() == after.to_persistence_payload()
                and attempt.submit_seconds == 0,
                "Unsubmitted runner attempt changed engine state.",
            )
        if attempt.policy_id is None:
            _require(attempt.choice_seconds == 0, "Unrouted attempt cannot report policy time.")

    @staticmethod
    def _check_stop(
        report: RunReport, session: LocalGameSession, manifest: dict[str, JsonValue]
    ) -> None:
        state = session.lifecycle.state
        assert state is not None
        terminal = state.stage is GameLifecycleStage.COMPLETE
        _require(
            report.stop_reason in ("terminal", "requested_boundary", "error"),
            "Unknown runner stop.",
        )
        if report.stop_reason == "error":
            _require(
                type(report.failure_reason) is str and bool(report.failure_reason.strip()),
                "Runner error requires its diagnosis.",
            )
        else:
            _require(
                report.failure_reason is None
                and all(t.failure_stage is None for t in report.decisions),
                "Successful runner stop contains failure evidence.",
            )
            if report.stop_reason == "terminal":
                _require(terminal, "Runner terminal stop lacks engine completion.")
            else:
                boundary = manifest["stop_at"]
                actor = session.lifecycle.pending_decision_request()
                _require(
                    isinstance(boundary, list)
                    and len(boundary) == 2
                    and actor is not None
                    and actor.actor_id is not None,
                    "Runner requested boundary is missing.",
                )
                assert actor is not None
                assert actor.actor_id is not None
                assert isinstance(boundary, list)
                view = session.view(viewer_player_id=actor.actor_id)
                _require(
                    boundary[0] in ("setup", "battle")
                    and view["stage"] == boundary[0]
                    and (
                        view["current_setup_step"]
                        if boundary[0] == "setup"
                        else view["current_battle_phase"]
                    )
                    == boundary[1],
                    "Runner requested boundary drifted.",
                )
        if report.failure_reason == "decision_limit":
            _require(
                len(report.decisions) == manifest["max_decisions"],
                "Runner decision limit was not reached.",
            )

    @classmethod
    def from_payload(
        cls,
        payload: object,
        *,
        report: RunReport,
        origin: VerifiedEpisodeOrigin,
        initial_session: LocalGameSession,
        final_session: LocalGameSession,
        attempt_sessions: tuple[LocalGameSession, ...],
        transitions: tuple[AcceptedTransition, ...] = (),
        episode: FiniteEpisodeAdmission | MixedEpisodeAdmission | None = None,
    ) -> RunnerAdmission:
        expected = cls.from_report(
            report,
            origin=origin,
            initial_session=initial_session,
            final_session=final_session,
            attempt_sessions=attempt_sessions,
            transitions=transitions,
            episode=episode,
        )
        _require(
            canonical_json(validate_json_value(payload)) == expected._payload_json,
            "Runner admission payload drifted.",
        )
        return expected

    def to_payload(self) -> dict[str, JsonValue]:
        return cast(dict[str, JsonValue], json.loads(self._payload_json))

    @property
    def content_hash(self) -> str:
        return payload_digest(self.to_payload())


@dataclass(frozen=True, slots=True, init=False)
class DeploymentDatasetAdmission:
    """Explicit run inventory plus bounded, already verified deployment rows.

    Run tuple positions identify occurrences: deterministic run IDs may repeat.
    Completeness is relative to the supplied inventory, not all external runs.
    No learning algorithm, data split or workload qualification is implied.
    """

    _payload_json: str

    def __init__(self) -> None:
        raise TrainingAdmissionError("Admit a dataset through its complete run inventory.")

    @classmethod
    def from_runs(
        cls,
        runs: tuple[RunnerAdmission, ...],
        *,
        choices: tuple[
            tuple[
                int, DeploymentExperimentProvenance, LinkedTrainingTarget, AdmittedTrainingTarget
            ],
            ...,
        ] = (),
    ) -> DeploymentDatasetAdmission:
        _require(
            type(runs) is tuple
            and bool(runs)
            and all(type(r) is RunnerAdmission for r in runs)
            and type(choices) is tuple,
            "Dataset requires a typed nonempty run inventory.",
        )
        entries: list[dict[str, JsonValue]] = []
        seen: set[tuple[int, str]] = set()
        for occurrence, experiment, linked, target in choices:
            _require(
                type(occurrence) is int
                and 0 <= occurrence < len(runs)
                and type(experiment) is DeploymentExperimentProvenance
                and type(target) is AdmittedTrainingTarget
                and type(linked) is LinkedTrainingTarget,
                "Dataset choice requires typed run, experiment and target evidence.",
            )
            run = runs[occurrence].to_payload()
            proof = experiment.to_payload()
            admitted = target.to_payload()
            transition = cast(dict[str, JsonValue], proof["accepted_transition"])
            transition_hash = payload_digest(transition)
            ranked = cast(dict[str, JsonValue], proof["ranked_training_link"])
            ranking = cast(dict[str, JsonValue], ranked["ranking"])
            report = cast(dict[str, JsonValue], run["report"])
            attempts = cast(list[dict[str, JsonValue]], report["decisions"])
            hashes = cast(list[str], run["transition_hashes"])
            _require(
                run["episode"] is not None
                and proof["episode"] == run["episode"]
                and transition_hash in hashes
                and admitted["episode_hash"] == run["episode_hash"]
                and admitted["transition_hash"] == transition_hash
                and admitted["linked_target_hash"] == linked.content_hash
                and linked.training_candidate_link_hash == payload_digest(ranked["candidate_link"]),
                "Dataset experiment, target or run episode drifted.",
            )
            attempt = attempts[hashes.index(transition_hash)]
            _require(
                ranking["choice_seed"] == attempt["choice_seed"]
                and transition["before_observation_hash"] == attempt["observation_hash"],
                "Dataset ranker choice does not match its runner attempt.",
            )
            manifest = cast(dict[str, JsonValue], report["manifest"])
            registrations = cast(list[dict[str, JsonValue]], manifest["declared_registrations"])
            route = cast(dict[str, JsonValue], attempt["route"])
            route_key = [
                route[name]
                for name in (
                    "actor_id",
                    "decision_type",
                    "stage",
                    "setup_step",
                    "battle_phase",
                    "proposal_kind",
                )
            ]
            registration = next(entry for entry in registrations if entry["route"] == route_key)
            configuration = cast(dict[str, JsonValue], registration["configuration"])
            _require(
                configuration.get("deployment_ranking_hash") == payload_digest(ranking),
                "Dataset ranking differs from the declared runner registration.",
            )
            key = (occurrence, transition_hash)
            _require(key not in seen, "Dataset repeats a choice within one run occurrence.")
            seen.add(key)
            entries.append(
                {
                    "run_occurrence": occurrence,
                    "experiment": proof,
                    "target_admission": cast(JsonValue, admitted),
                    "eligible_for_learning": admitted["eligible_for_learning"]
                    and report["stop_reason"] != "error",
                    "linked_target": cast(JsonValue, linked.to_payload()),
                }
            )
        reports = [cast(dict[str, JsonValue], r.to_payload()["report"]) for r in runs]
        attempts = [
            cast(dict[str, JsonValue], a)
            for r in reports
            for a in cast(list[JsonValue], r["decisions"])
        ]
        result = object.__new__(cls)
        object.__setattr__(
            result,
            "_payload_json",
            canonical_json(
                validate_json_value(
                    {
                        "schema_version": "deployment-dataset-admission-v1",
                        "runs": [r.to_payload() for r in runs],
                        "choices": entries,
                        "counts": {
                            "attempted_runs": len(runs),
                            "failed_runs": sum(r["stop_reason"] == "error" for r in reports),
                            "attempted_choices": len(attempts),
                            "submission_outcomes": {
                                outcome: sum(a["submission_outcome"] == outcome for a in attempts)
                                for outcome in (
                                    "accepted",
                                    "rejected",
                                    "unverified",
                                    "not_submitted",
                                )
                            },
                            "admitted_rows": len(entries),
                            "eligible_rows": sum(
                                e["eligible_for_learning"] is True for e in entries
                            ),
                        },
                    }
                )
            ),
        )
        return result

    @classmethod
    def from_payload(
        cls,
        payload: object,
        *,
        runs: tuple[RunnerAdmission, ...],
        choices: tuple[
            tuple[
                int, DeploymentExperimentProvenance, LinkedTrainingTarget, AdmittedTrainingTarget
            ],
            ...,
        ] = (),
    ) -> DeploymentDatasetAdmission:
        expected = cls.from_runs(runs, choices=choices)
        _require(
            canonical_json(validate_json_value(payload)) == expected._payload_json,
            "Dataset admission payload drifted.",
        )
        return expected

    def to_payload(self) -> dict[str, JsonValue]:
        return cast(dict[str, JsonValue], json.loads(self._payload_json))

    @property
    def content_hash(self) -> str:
        return payload_digest(self.to_payload())
