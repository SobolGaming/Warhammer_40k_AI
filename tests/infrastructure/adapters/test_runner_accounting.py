from __future__ import annotations

import json
from dataclasses import replace
from typing import cast

import pytest

from tests.shared.category_migration.phase18f_session_commands import (
    _compact_terminal_config,
    _deployment_payload_from_proposal,
    _invalid_distance_witness,
    _terminal_progress_option_id,
)
from warhammer40k_core.adapters.access_control import ViewerContext
from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.adapters.setup_smoke import canonical_setup_prebattle_smoke_config
from warhammer40k_core.ai.player_policy import (
    CandidateExhaustedError,
    PlayerDecisionContext,
    PolicyAction,
    PolicyRegistration,
    PolicyRoute,
    PolicyRouter,
    payload_digest,
)
from warhammer40k_core.ai.runner import (
    BoundedPolicyRunner,
    RunBoundary,
    RunLimits,
    RunnerError,
    RunReport,
)
from warhammer40k_core.core.ruleset_descriptor import RulesetDescriptor
from warhammer40k_core.engine.event_log import JsonValue
from warhammer40k_core.engine.phase import LifecycleStatusKind
from warhammer40k_core.engine.replay import ReplayRunner


class ChoicePolicy:
    def __init__(self, mode: str = "valid") -> None:
        self.mode = mode
        self.contexts: list[PlayerDecisionContext] = []

    def choose(self, context: PlayerDecisionContext) -> PolicyAction:
        self.contexts.append(context)
        if self.mode == "exhausted":
            raise CandidateExhaustedError("Declared candidates exhausted.")
        if self.mode == "invalid":
            return context.select_option("absent-option")
        if self.mode == "drift":
            return replace(
                context.select_option(context.request["options"][0]["option_id"]),
                observation_hash="drift",
            )
        return context.select_option(context.request["options"][0]["option_id"])


def session_and_route() -> tuple[LocalGameSession, PolicyRoute]:
    session = LocalGameSession()
    session.start(replace(canonical_setup_prebattle_smoke_config(), private_rng_seed="c1" * 32))
    session.advance_until_decision_or_terminal()
    return session, PolicyRoute.from_view(session.view(viewer_player_id="player-a"))


def test_manifest_preserves_declared_routing_seeds_limits_and_detaches_payloads() -> None:
    session, route = session_and_route()
    policy = ChoicePolicy()
    router = PolicyRouter((PolicyRegistration(route, "declared-v1", '{"x": 7}', policy),))
    limits = RunLimits(policy_seed=91, max_decisions=2, max_seconds=120)
    checkpoint = payload_digest(session.to_persistence_payload())
    report = BoundedPolicyRunner(session=session, router=router, limits=limits).run(
        stop_at=RunBoundary("setup", route.setup_step or "missing")
    )
    assert report.manifest is not None
    manifest = report.manifest.to_payload()
    assert manifest["initial_checkpoint"] == checkpoint
    assert manifest["registration_evidence"] == "declared-unverified"
    assert manifest["time_limit_enforcement"] == "cooperative-between-calls"
    assert manifest["policy_seed"] == 91
    assert manifest["max_decisions"] == 2
    assert manifest["max_seconds"] == 120
    assert manifest["declared_registrations"] == router.to_manifest_payload()
    assert manifest["router_identity"] == payload_digest(router.to_manifest_payload())
    assert report.run_id == payload_digest(manifest)
    assert report.failure_reason is None
    assert report.decisions == ()
    assert policy.contexts == []
    assert "c1" * 32 not in json.dumps(manifest)
    payload = report.to_payload()
    assert json.loads(json.dumps(payload)) == payload
    manifest["policy_seed"] = 0
    router.to_manifest_payload().clear()
    assert report.manifest.to_payload()["policy_seed"] == 91
    assert len(router.to_manifest_payload()) == 1
    assert report.to_payload() == payload


def test_missing_route_is_a_failed_attempt_without_a_policy_call() -> None:
    session, route = session_and_route()
    before = session.to_persistence_payload()
    with pytest.raises(RunnerError, match="Unsupported exact") as caught:
        BoundedPolicyRunner(
            session=session, router=PolicyRouter(()), limits=RunLimits(13, 1, 120)
        ).run()
    report = caught.value.report
    assert report.manifest is not None
    assert report.failure_reason == "unsupported_route"
    assert len(report.decisions) == 1
    attempt = report.decisions[0]
    assert attempt.route == route
    assert attempt.policy_id is None
    assert attempt.failure_stage == "routing"
    assert attempt.submission_outcome == "not_submitted"
    assert attempt.choice_seconds == attempt.submit_seconds == attempt.recorded_decisions == 0
    assert not attempt.accepted
    assert session.to_persistence_payload() == before


@pytest.mark.parametrize(
    ("mode", "stage", "outcome"),
    [
        ("exhausted", "choice", "not_submitted"),
        ("drift", "validation", "not_submitted"),
        ("invalid", "submission", "unverified"),
    ],
)
def test_failed_choice_retains_actual_seed_binding_and_stage(
    mode: str, stage: str, outcome: str
) -> None:
    session, route = session_and_route()
    policy = ChoicePolicy(mode)
    with pytest.raises(RunnerError) as caught:
        BoundedPolicyRunner(
            session=session,
            router=PolicyRouter((PolicyRegistration(route, "failure-v1", "{}", policy),)),
            limits=RunLimits(13, 2, 120),
        ).run()
    (attempt,) = caught.value.report.decisions
    (context,) = policy.contexts
    assert attempt.choice_seed == context.choice_seed
    assert attempt.viewer_request_id == context.request["request_id"]
    assert attempt.observation_hash == context.observation_hash
    assert attempt.failure_stage == stage
    assert attempt.submission_outcome == outcome
    assert not attempt.accepted
    assert attempt.recorded_decisions == 0
    assert session.decision_record_count() == 0


def test_successful_choice_and_budget_stop_keep_separate_record_accounting() -> None:
    session, route = session_and_route()
    saved = session.to_persistence_payload()
    reports: list[RunReport] = []
    for current in (session, LocalGameSession.from_persistence_payload(saved)):
        policy = ChoicePolicy()
        with pytest.raises(RunnerError, match="decision progress limit") as caught:
            BoundedPolicyRunner(
                session=current,
                router=PolicyRouter((PolicyRegistration(route, "valid-v1", "{}", policy),)),
                limits=RunLimits(13, 1, 120),
            ).run()
        report = caught.value.report
        reports.append(report)
        (attempt,) = report.decisions
        assert report.failure_reason == "decision_limit"
        assert attempt.accepted
        assert attempt.submission_outcome == "accepted"
        assert attempt.failure_stage is None
        assert attempt.recorded_decisions == current.decision_record_count() == 1
        assert set(policy.contexts[0].__slots__) == {"route", "observation_json", "choice_seed"}
        assert (
            ReplayRunner.from_payload(current.replay_artifact(artifact_id="accounting"))
            .run()
            .reproduced_exactly
        )
    assert reports[0].run_id == reports[1].run_id
    assert reports[0].decisions[0].choice_seed == reports[1].decisions[0].choice_seed


def test_time_limit_before_dispatch_preserves_manifest_without_invented_attempt() -> None:
    session, route = session_and_route()
    policy = ChoicePolicy()
    with pytest.raises(RunnerError, match="elapsed-time") as caught:
        BoundedPolicyRunner(
            session=session,
            router=PolicyRouter((PolicyRegistration(route, "valid-v1", "{}", policy),)),
            limits=RunLimits(13, 1, 1e-12),
        ).run()
    assert caught.value.report.manifest is not None
    assert caught.value.report.failure_reason == "time_limit"
    assert caught.value.report.decisions == ()
    assert policy.contexts == []


def test_ordinary_recorded_movement_rejection_is_not_an_accepted_choice() -> None:
    session = LocalGameSession()
    session.start(
        replace(
            _compact_terminal_config(game_id="runner-recorded-rejection"),
            ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(),
        )
    )
    status = session.advance_until_decision_or_terminal()
    for index in range(40):
        request = status.decision_request
        assert request is not None
        assert request.actor_id is not None
        context = PlayerDecisionContext.from_view(
            session.view(viewer_player_id=request.actor_id), choice_seed=7
        )
        if context.route.proposal_kind == "normal_move":
            break
        if context.route.proposal_kind is not None:
            assert context.route.proposal_kind == "deployment_placement"
            status = session.submit_viewer_parameterized_payload(
                viewer=ViewerContext.for_player(request.actor_id),
                request_id=context.request["request_id"],
                payload=_deployment_payload_from_proposal(context.observation["pending_proposal"]),
                result_id=f"prefix-{index}",
            )
        else:
            chosen = _terminal_progress_option_id(cast(dict[str, JsonValue], context.request))
            if context.route.decision_type == "select_movement_unit":
                chosen = context.request["options"][0]["option_id"]
            elif context.route.decision_type == "select_movement_action":
                chosen = "normal_move"
            status = session.submit_viewer_option(
                viewer=ViewerContext.for_player(request.actor_id),
                request_id=context.request["request_id"],
                option_id=chosen,
                result_id=f"prefix-{index}",
            )
        if status.status_kind is LifecycleStatusKind.ADVANCED:
            status = session.advance_until_decision_or_terminal()
        assert status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    else:
        pytest.fail("Ordinary setup did not reach movement within the declared budget.")

    class InvalidMovementPolicy:
        def choose(self, context: PlayerDecisionContext) -> PolicyAction:
            proposal = context.observation["pending_proposal"]
            assert isinstance(proposal, dict)
            return context.propose(
                {
                    "proposal_request_id": proposal["request_id"],
                    "proposal_kind": proposal["proposal_kind"],
                    "unit_instance_id": proposal["unit_instance_id"],
                    "movement_phase_action": "normal_move",
                    "movement_mode": "normal",
                    "witness": _invalid_distance_witness(
                        projection=cast(dict[str, JsonValue], context.observation),
                        unit_instance_id=cast(str, proposal["unit_instance_id"]),
                    ),
                }
            )

    before = session.decision_record_count()
    with pytest.raises(RunnerError, match="invalid submission") as caught:
        BoundedPolicyRunner(
            session=session,
            router=PolicyRouter(
                (
                    PolicyRegistration(
                        context.route, "invalid-move-v1", "{}", InvalidMovementPolicy()
                    ),
                )
            ),
            limits=RunLimits(13, 2, 120),
        ).run()
    (attempt,) = caught.value.report.decisions
    assert caught.value.report.failure_reason == "submission_rejected"
    assert attempt.submission_outcome == "rejected"
    assert not attempt.accepted
    assert attempt.recorded_decisions == session.decision_record_count() - before == 1
    assert attempt.failure_stage == "submission"
    assert session.lifecycle.pending_decision_request() is not None
    assert session.lifecycle.pending_decision_request() != request
    restored = LocalGameSession.from_persistence_payload(session.to_persistence_payload())
    assert restored.to_persistence_payload() == session.to_persistence_payload()
    assert (
        ReplayRunner.from_payload(session.replay_artifact(artifact_id="rejected-accounting"))
        .run()
        .reproduced_exactly
    )
