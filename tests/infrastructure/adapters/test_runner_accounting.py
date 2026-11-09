from __future__ import annotations

import json
from dataclasses import FrozenInstanceError, replace
from typing import cast

import pytest

from tests.shared.ai_training_admission_helpers import step
from tests.shared.category_migration.phase18f_session_commands import (
    _compact_terminal_config,
    _deployment_payload_from_proposal,
    _invalid_distance_witness,
    _terminal_progress_option_id,
)
from warhammer40k_core.adapters.access_control import ViewerContext
from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.adapters.setup_smoke import canonical_setup_prebattle_smoke_config
from warhammer40k_core.ai.deployment_dataset_split import (
    DeploymentDatasetPartition,
    DeploymentDatasetSplit,
    DeploymentSplitAssignment,
)
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
from warhammer40k_core.ai.runner_admission import DeploymentDatasetAdmission, RunnerAdmission
from warhammer40k_core.ai.training_admission import (
    FiniteEpisodeAdmission,
    TrainingAdmissionError,
    VerifiedEpisodeOrigin,
)
from warhammer40k_core.ai.training_candidates import FiniteTrainingCandidateLink
from warhammer40k_core.ai.training_targets import TargetEpisodeEnd
from warhammer40k_core.ai.training_transitions import FiniteAcceptedTransition
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
    prefix_session: LocalGameSession | None = None
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
                prefix_session = session.fork()
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

    checkpoint = session.fork()
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
    admission = admit(caught.value.report, checkpoint, session)
    dataset = DeploymentDatasetAdmission.from_runs((admission,)).to_payload()
    assert dataset["counts"] == {
        "attempted_runs": 1,
        "failed_runs": 1,
        "attempted_choices": 1,
        "submission_outcomes": {"accepted": 0, "rejected": 1, "unverified": 0, "not_submitted": 0},
        "admitted_rows": 0,
        "eligible_rows": 0,
    }
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

    # Repeat the ordinary final selection and rejection as one run so the
    # accepted episode ends before the rejection's extra engine record.
    assert prefix_session is not None
    initial = prefix_session
    before_move = initial.fork()
    selection_request = initial.lifecycle.pending_decision_request()
    assert selection_request is not None
    assert selection_request.actor_id is not None
    selection_view = initial.view(viewer_player_id=selection_request.actor_id)
    selection_pending = selection_view["pending_decision"]
    assert selection_pending is not None
    choice_hash = payload_digest(
        [
            "player-policy-choice-v1",
            13,
            selection_view["game_id"],
            selection_request.actor_id,
            selection_pending["request_id"],
        ]
    )
    selection_context = PlayerDecisionContext.from_view(
        selection_view, choice_seed=int(choice_hash, 16)
    )
    before_move.submit_viewer_option(
        viewer=ViewerContext.for_player(selection_request.actor_id),
        request_id=selection_pending["request_id"],
        option_id="normal_move",
        result_id=f"ai:{choice_hash}",
    )
    before_move.advance_until_decision_or_terminal()

    class SelectMovementPolicy:
        def choose(self, context: PlayerDecisionContext) -> PolicyAction:
            return context.select_option("normal_move")

    final = initial.fork()
    with pytest.raises(RunnerError, match="invalid submission") as failed_run:
        BoundedPolicyRunner(
            session=final,
            router=PolicyRouter(
                (
                    PolicyRegistration(
                        selection_context.route, "select-move-v1", "{}", SelectMovementPolicy()
                    ),
                    PolicyRegistration(
                        context.route, "invalid-move-v1", "{}", InvalidMovementPolicy()
                    ),
                )
            ),
            limits=RunLimits(13, 3, 120),
        ).run()
    prefix_row = replace(
        step(initial, "normal_move").row,
        decision_record_id=before_move.lifecycle.decision_controller.records[
            initial.decision_record_count()
        ].record_id,
    )
    prefix_transition = FiniteAcceptedTransition.from_sessions(
        FiniteTrainingCandidateLink.from_row(prefix_row, context=selection_context),
        row=prefix_row,
        context=selection_context,
        before=initial,
        after=before_move,
        trajectory_id="rejected-movement-prefix",
        perspective_player_id="player-a",
    )
    origin = VerifiedEpisodeOrigin.from_session(initial, config=initial.lifecycle.config)
    prefix_episode = FiniteEpisodeAdmission.from_transitions(
        origin,
        transitions=(prefix_transition,),
        final_session=before_move,
        episode_end=TargetEpisodeEnd.TRUNCATED,
        stop_reason="accepted-prefix-before-runner-failure",
    )
    joined = RunnerAdmission.from_report(
        failed_run.value.report,
        origin=origin,
        initial_session=initial,
        final_session=final,
        attempt_sessions=(initial, before_move),
        transitions=(prefix_transition,),
        episode=prefix_episode,
    )
    assert (
        prefix_episode.to_payload()["final_checkpoint_hash"]
        != failed_run.value.report.final_checkpoint_hash
    )
    counts = cast(
        dict[str, JsonValue], DeploymentDatasetAdmission.from_runs((joined,)).to_payload()["counts"]
    )
    assert counts["submission_outcomes"] == {
        "accepted": 1,
        "rejected": 1,
        "unverified": 0,
        "not_submitted": 0,
    }
    assert counts["failed_runs"] == 1


def admit(report: RunReport, before: LocalGameSession, after: LocalGameSession) -> RunnerAdmission:
    return RunnerAdmission.from_report(
        report,
        origin=VerifiedEpisodeOrigin.from_session(before, config=before.lifecycle.config),
        initial_session=before,
        final_session=after,
        attempt_sessions=() if not report.decisions else (before,),
    )


@pytest.fixture(scope="module")
def split_datasets() -> tuple[DeploymentDatasetAdmission, ...]:
    datasets: list[DeploymentDatasetAdmission] = []
    for index in range(4):
        session = LocalGameSession()
        session.start(
            replace(
                canonical_setup_prebattle_smoke_config(),
                private_rng_seed=f"{index % 3 + 1:02x}" * 32,
            )
        )
        session.advance_until_decision_or_terminal()
        if index == 3:
            # Same ordinary startup as dataset 0, but a different replayed prefix.
            session = step(session).after
        before = session.fork()
        with pytest.raises(RunnerError) as caught:
            BoundedPolicyRunner(
                session=session,
                router=PolicyRouter(()),
                limits=RunLimits(13 + index, 1, 1e-12 if index == 2 else 120),
            ).run()
        receipt = admit(caught.value.report, before, session)
        datasets.append(DeploymentDatasetAdmission.from_runs((receipt,)))
    return tuple(datasets)


def _split_assignments() -> tuple[DeploymentSplitAssignment, ...]:
    return tuple(
        DeploymentSplitAssignment(index, 0, partition, f"family-{index}", f"geometry-{index}")
        for index, partition in enumerate(DeploymentDatasetPartition)
    )


def test_split_preserves_duplicate_occurrences_and_zero_row_failure_denominators(
    split_datasets: tuple[DeploymentDatasetAdmission, ...],
) -> None:
    datasets = (*split_datasets[:3], split_datasets[0])
    assignments = (*_split_assignments(), replace(_split_assignments()[0], dataset_occurrence=3))
    split = DeploymentDatasetSplit.from_datasets(datasets, assignments=assignments)
    payload = split.to_payload()
    assert payload["datasets"] == [dataset.to_payload() for dataset in datasets]
    assert payload["dataset_hashes"] == [dataset.content_hash for dataset in datasets]
    assert payload["group_evidence"] == "declared-unverified"
    counts = cast(dict[str, JsonValue], payload["counts"])
    assert counts == {
        "attempted_runs": 4,
        "failed_runs": 4,
        "attempted_choices": 3,
        "submission_outcomes": {"accepted": 0, "rejected": 0, "unverified": 0, "not_submitted": 3},
        "admitted_rows": 0,
        "eligible_rows": 0,
        "excluded_rows": 0,
    }
    partitions = cast(dict[str, dict[str, JsonValue]], payload["partitions"])
    assert partitions["train"]["run_occurrences"] == [[0, 0], [3, 0]]
    assert partitions["validation"]["run_occurrences"] == [[1, 0]]
    assert partitions["test"]["run_occurrences"] == [[2, 0]]
    for name in counts:
        if name == "submission_outcomes":
            for outcome, count in cast(dict[str, int], counts[name]).items():
                assert count == sum(
                    cast(dict[str, int], cast(dict[str, JsonValue], part["counts"])[name])[outcome]
                    for part in partitions.values()
                )
        else:
            assert counts[name] == sum(
                cast(int, cast(dict[str, JsonValue], part["counts"])[name])
                for part in partitions.values()
            )
    assert split.content_hash == payload_digest(payload)
    assert (
        DeploymentDatasetSplit.from_payload(
            json.loads(json.dumps(payload)), datasets=datasets, assignments=assignments
        )
        == split
    )
    assert (
        DeploymentDatasetSplit.from_datasets(datasets, assignments=tuple(reversed(assignments)))
        == split
    )
    payload["datasets"] = []
    assert split.to_payload()["datasets"] != []
    with pytest.raises(FrozenInstanceError):
        split._payload_json = "{}"  # type: ignore[misc]


@pytest.mark.parametrize("change", ["missing", "duplicate", "conflicting", "dataset", "run"])
def test_split_rejects_incomplete_or_ambiguous_occurrence_assignments(
    split_datasets: tuple[DeploymentDatasetAdmission, ...], change: str
) -> None:
    assignments = _split_assignments()
    if change == "missing":
        assignments = assignments[:-1]
    elif change in ("duplicate", "conflicting"):
        assignments += (
            replace(
                assignments[0],
                partition=(
                    DeploymentDatasetPartition.TEST
                    if change == "conflicting"
                    else assignments[0].partition
                ),
            ),
        )
    elif change == "dataset":
        assignments = (replace(assignments[0], dataset_occurrence=9), *assignments[1:])
    else:
        assignments = (replace(assignments[0], run_occurrence=1), *assignments[1:])
    with pytest.raises(TrainingAdmissionError, match="assignment"):
        DeploymentDatasetSplit.from_datasets(split_datasets[:3], assignments=assignments)


@pytest.mark.parametrize("group", ["scenario_family", "geometry_group"])
def test_split_rejects_independent_declared_group_leakage(
    split_datasets: tuple[DeploymentDatasetAdmission, ...], group: str
) -> None:
    assignments = _split_assignments()
    second = (
        replace(assignments[1], scenario_family=assignments[0].scenario_family)
        if group == "scenario_family"
        else replace(assignments[1], geometry_group=assignments[0].geometry_group)
    )
    with pytest.raises(TrainingAdmissionError, match="declared group leaks"):
        DeploymentDatasetSplit.from_datasets(
            split_datasets[:3], assignments=(assignments[0], second, assignments[2])
        )


@pytest.mark.parametrize("prefix", [False, True])
@pytest.mark.parametrize("change", ["partition", "family", "geometry"])
def test_split_keeps_duplicate_and_replayed_prefix_trajectories_together(
    split_datasets: tuple[DeploymentDatasetAdmission, ...], prefix: bool, change: str
) -> None:
    datasets = (split_datasets[0], split_datasets[3 if prefix else 0])
    first = _split_assignments()[0]
    second = replace(first, dataset_occurrence=1)
    positive = DeploymentDatasetSplit.from_datasets(datasets, assignments=(first, second))
    members = cast(list[dict[str, JsonValue]], positive.to_payload()["assignments"])
    assert members[0]["startup_trajectory_hash"] == members[1]["startup_trajectory_hash"]
    if prefix:
        sources = [
            cast(list[dict[str, JsonValue]], dataset.to_payload()["runs"]) for dataset in datasets
        ]
        assert sources[0][0]["origin"] != sources[1][0]["origin"]
    if change == "partition":
        second = replace(second, partition=DeploymentDatasetPartition.TEST)
    elif change == "family":
        second = replace(second, scenario_family="different-family")
    else:
        second = replace(second, geometry_group="different-geometry")
    with pytest.raises(TrainingAdmissionError, match="trajectory"):
        DeploymentDatasetSplit.from_datasets(datasets, assignments=(first, second))


@pytest.mark.parametrize(
    "field",
    [
        "schema_version",
        "scope",
        "group_evidence",
        "trajectory_grouping",
        "datasets",
        "dataset_hashes",
        "assignments",
        "partitions",
        "counts",
        "extra",
    ],
)
def test_split_closed_loader_rejects_changed_evidence_or_accounting(
    split_datasets: tuple[DeploymentDatasetAdmission, ...], field: str
) -> None:
    assignments = _split_assignments()
    datasets = split_datasets[:3]
    split = DeploymentDatasetSplit.from_datasets(datasets, assignments=assignments)
    payload = split.to_payload()
    payload[field] = "drift"
    with pytest.raises(TrainingAdmissionError, match="drifted"):
        DeploymentDatasetSplit.from_payload(payload, datasets=datasets, assignments=assignments)


@pytest.mark.parametrize(
    "change", ["dataset-bool", "run-negative", "partition", "family-empty", "geometry-space"]
)
def test_split_assignment_rejects_inexact_or_missing_declarations(change: str) -> None:
    item = _split_assignments()[0]
    dataset_occurrence = True if change == "dataset-bool" else item.dataset_occurrence
    run_occurrence = -1 if change == "run-negative" else item.run_occurrence
    partition = (
        cast(DeploymentDatasetPartition, "train") if change == "partition" else item.partition
    )
    scenario_family = "" if change == "family-empty" else item.scenario_family
    geometry_group = " " if change == "geometry-space" else item.geometry_group
    with pytest.raises(TrainingAdmissionError, match="assignment"):
        replace(
            item,
            dataset_occurrence=dataset_occurrence,
            run_occurrence=run_occurrence,
            partition=partition,
            scenario_family=scenario_family,
            geometry_group=geometry_group,
        )


def test_split_requires_typed_admitted_inputs(
    split_datasets: tuple[DeploymentDatasetAdmission, ...],
) -> None:
    with pytest.raises(TrainingAdmissionError):
        DeploymentDatasetSplit()
    for datasets, assignments in (
        ((), ()),
        ((cast(DeploymentDatasetAdmission, split_datasets[0].to_payload()),), ()),
        (split_datasets[:3], (cast(DeploymentSplitAssignment, {}),)),
    ):
        with pytest.raises(TrainingAdmissionError, match="typed"):
            DeploymentDatasetSplit.from_datasets(datasets, assignments=assignments)


def test_split_binds_declared_trajectory_ids_across_distinct_verified_startups() -> None:
    datasets: list[DeploymentDatasetAdmission] = []
    for seed in ("a1", "a2"):
        session = LocalGameSession()
        session.start(replace(canonical_setup_prebattle_smoke_config(), private_rng_seed=seed * 32))
        session.advance_until_decision_or_terminal()
        before = session.fork()
        policy = ChoicePolicy()
        route = PolicyRoute.from_view(session.view(viewer_player_id="player-a"))
        with pytest.raises(RunnerError) as caught:
            BoundedPolicyRunner(
                session=session,
                router=PolicyRouter((PolicyRegistration(route, "split-test", "{}", policy),)),
                limits=RunLimits(13, 1, 120),
            ).run()
        row = replace(
            step(before).row,
            decision_record_id=session.lifecycle.decision_controller.records[
                before.decision_record_count()
            ].record_id,
        )
        transition = FiniteAcceptedTransition.from_sessions(
            FiniteTrainingCandidateLink.from_row(row, context=policy.contexts[0]),
            row=row,
            context=policy.contexts[0],
            before=before,
            after=session,
            trajectory_id="declared-common-trajectory",
            perspective_player_id="player-a" if seed == "a1" else "player-b",
        )
        receipt = RunnerAdmission.from_report(
            caught.value.report,
            origin=VerifiedEpisodeOrigin.from_session(before, config=before.lifecycle.config),
            initial_session=before,
            final_session=session,
            attempt_sessions=(before,),
            transitions=(transition,),
        )
        datasets.append(DeploymentDatasetAdmission.from_runs((receipt,)))
    first = _split_assignments()[0]
    second = replace(first, dataset_occurrence=1)
    split = DeploymentDatasetSplit.from_datasets(tuple(datasets), assignments=(first, second))
    members = cast(list[dict[str, JsonValue]], split.to_payload()["assignments"])
    assert members[0]["startup_trajectory_hash"] != members[1]["startup_trajectory_hash"]
    assert (
        members[0]["declared_trajectory_ids"]
        == members[1]["declared_trajectory_ids"]
        == ["declared-common-trajectory"]
    )
    with pytest.raises(TrainingAdmissionError, match="trajectory leaks"):
        DeploymentDatasetSplit.from_datasets(
            tuple(datasets),
            assignments=(
                first,
                replace(
                    second,
                    partition=DeploymentDatasetPartition.TEST,
                    scenario_family="different",
                    geometry_group="different",
                ),
            ),
        )


@pytest.mark.parametrize(
    "mode", ["valid", "exhausted", "drift", "invalid", "missing", "no-dispatch"]
)
def test_runner_admission_preserves_complete_supplied_run_denominators(mode: str) -> None:
    session, route = session_and_route()
    before = session.fork()
    policy = ChoicePolicy(mode)
    router = (
        PolicyRouter(())
        if mode == "missing"
        else PolicyRouter((PolicyRegistration(route, "admitted-v1", "{}", policy),))
    )
    with pytest.raises(RunnerError) as caught:
        BoundedPolicyRunner(
            session=session,
            router=router,
            limits=RunLimits(13, 1, 1e-12 if mode == "no-dispatch" else 120),
        ).run()
    report = caught.value.report
    receipt = admit(report, before, session)
    payload = receipt.to_payload()
    assert payload["report"] == report.to_payload()
    assert report.final_checkpoint_hash == payload_digest(session.to_persistence_payload())
    assert report.final_record_count == session.decision_record_count()
    assert (
        RunnerAdmission.from_payload(
            json.loads(json.dumps(payload)),
            report=report,
            origin=VerifiedEpisodeOrigin.from_session(before, config=before.lifecycle.config),
            initial_session=before,
            final_session=session,
            attempt_sessions=() if not report.decisions else (before,),
        )
        == receipt
    )
    dataset = DeploymentDatasetAdmission.from_runs((receipt, receipt))
    counts = cast(dict[str, JsonValue], dataset.to_payload()["counts"])
    assert counts["attempted_runs"] == counts["failed_runs"] == 2
    assert counts["attempted_choices"] == 2 * len(report.decisions)
    assert counts["eligible_rows"] == counts["admitted_rows"] == 0
    assert (
        DeploymentDatasetAdmission.from_payload(dataset.to_payload(), runs=(receipt, receipt))
        == dataset
    )
    payload["report"] = None
    assert receipt.to_payload()["report"] is not None
    assert all(
        set(c.__slots__) == {"route", "observation_json", "choice_seed"} for c in policy.contexts
    )


@pytest.mark.parametrize(
    "change", ["seed", "request", "route", "count", "outcome", "checkpoint", "manifest", "omitted"]
)
def test_runner_admission_rejects_report_or_boundary_drift(change: str) -> None:
    session, route = session_and_route()
    before = session.fork()
    with pytest.raises(RunnerError) as caught:
        BoundedPolicyRunner(
            session=session,
            router=PolicyRouter((PolicyRegistration(route, "test-v1", "{}", ChoicePolicy()),)),
            limits=RunLimits(13, 1, 120),
        ).run()
    report = caught.value.report
    attempt = report.decisions[0]
    if change == "seed":
        report = replace(report, decisions=(replace(attempt, choice_seed=attempt.choice_seed + 1),))
    elif change == "request":
        report = replace(report, decisions=(replace(attempt, viewer_request_id="other"),))
    elif change == "route":
        report = replace(
            report, decisions=(replace(attempt, route=replace(route, actor_id="player-b")),)
        )
    elif change == "count":
        report = replace(report, decisions=(replace(attempt, recorded_decisions=0),))
    elif change == "outcome":
        report = replace(report, decisions=(replace(attempt, accepted=False),))
    elif change == "checkpoint":
        report = replace(report, final_checkpoint_hash="other")
    elif change == "manifest":
        report = replace(report, manifest=None)
    else:
        report = replace(report, decisions=())
    with pytest.raises(TrainingAdmissionError):
        admit(report, before, session)


def test_runner_admission_keeps_successful_zero_choice_boundary() -> None:
    session, route = session_and_route()
    before = session.fork()
    report = BoundedPolicyRunner(
        session=session, router=PolicyRouter(()), limits=RunLimits(13, 1, 120)
    ).run(stop_at=RunBoundary("setup", route.setup_step or "missing"))
    receipt = admit(report, before, session)
    counts = cast(
        dict[str, JsonValue],
        DeploymentDatasetAdmission.from_runs((receipt,)).to_payload()["counts"],
    )
    assert counts["attempted_runs"] == 1
    assert counts["failed_runs"] == counts["attempted_choices"] == 0
    payload = receipt.to_payload()
    payload["unexpected"] = 1
    with pytest.raises(TrainingAdmissionError, match="payload drifted"):
        RunnerAdmission.from_payload(
            payload,
            report=report,
            origin=VerifiedEpisodeOrigin.from_session(before, config=before.lifecycle.config),
            initial_session=before,
            final_session=session,
            attempt_sessions=(),
        )


def test_runner_admission_keeps_failed_suffix_with_verified_accepted_prefix() -> None:
    session, route = session_and_route()
    before = session.fork()
    policy = ChoicePolicy()
    with pytest.raises(RunnerError, match="Unsupported exact") as caught:
        BoundedPolicyRunner(
            session=session,
            router=PolicyRouter((PolicyRegistration(route, "prefix-v1", "{}", policy),)),
            limits=RunLimits(13, 5, 120),
        ).run()
    report = caught.value.report
    assert len(report.decisions) == 2
    context = policy.contexts[0]
    chosen = context.request["options"][0]["option_id"]
    row = replace(
        step(before, chosen).row,
        decision_record_id=session.lifecycle.decision_controller.records[
            before.decision_record_count()
        ].record_id,
    )
    transition = FiniteAcceptedTransition.from_sessions(
        FiniteTrainingCandidateLink.from_row(row, context=context),
        row=row,
        context=context,
        before=before,
        after=session,
        trajectory_id="runner-prefix",
        perspective_player_id="player-a",
    )
    origin = VerifiedEpisodeOrigin.from_session(before, config=before.lifecycle.config)
    episode = FiniteEpisodeAdmission.from_transitions(
        origin,
        transitions=(transition,),
        final_session=session,
        episode_end=TargetEpisodeEnd.UNSUPPORTED,
        stop_reason="unsupported_route",
    )
    receipt = RunnerAdmission.from_report(
        report,
        origin=origin,
        initial_session=before,
        final_session=session,
        attempt_sessions=(before, session),
        transitions=(transition,),
        episode=episode,
    )
    payload = receipt.to_payload()
    assert payload["episode_hash"] == episode.content_hash
    assert payload["transition_hashes"] == [transition.content_hash]
    counts = cast(
        dict[str, JsonValue],
        DeploymentDatasetAdmission.from_runs((receipt,)).to_payload()["counts"],
    )
    assert counts["attempted_choices"] == 2
    assert counts["submission_outcomes"] == {
        "accepted": 1,
        "rejected": 0,
        "unverified": 0,
        "not_submitted": 1,
    }
    with pytest.raises(TrainingAdmissionError, match="episode"):
        RunnerAdmission.from_report(
            report,
            origin=origin,
            initial_session=before,
            final_session=session,
            attempt_sessions=(before, session),
            transitions=(),
            episode=episode,
        )
    with pytest.raises(TrainingAdmissionError, match="end contradicts"):
        RunnerAdmission.from_report(
            report,
            origin=origin,
            initial_session=before,
            final_session=session,
            attempt_sessions=(before, session),
            transitions=(transition,),
            episode=FiniteEpisodeAdmission.from_transitions(
                origin,
                transitions=(transition,),
                final_session=session,
                episode_end=TargetEpisodeEnd.TRUNCATED,
                stop_reason="unsupported_route",
            ),
        )
