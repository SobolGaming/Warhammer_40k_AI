from __future__ import annotations

import json
from dataclasses import FrozenInstanceError, dataclass, replace
from typing import cast

import pytest

from tests.shared.ai_training_admission_helpers import DeploymentCase, deployment_row
from tests.shared.ai_training_admission_helpers import deployment as deployment
from tests.shared.category_migration.phase18f_session_commands import (
    _deployment_payload_from_proposal,
)
from warhammer40k_core.adapters.access_control import ViewerContext
from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.ai.deployment_candidate_ranking import (
    DeploymentCandidateScore,
    DeploymentRankerConfiguration,
    RankedDeploymentCandidates,
)
from warhammer40k_core.ai.deployment_candidate_search import DeploymentCandidateSet
from warhammer40k_core.ai.deployment_candidate_validation import ValidatedDeploymentCandidates
from warhammer40k_core.ai.deployment_candidates import (
    DeploymentCandidatePayload,
    DeploymentPlacementCandidate,
)
from warhammer40k_core.ai.deployment_dataset_split import (
    DeploymentDatasetPartition,
    DeploymentDatasetSplit,
    DeploymentSplitAssignment,
)
from warhammer40k_core.ai.deployment_experiment import (
    DeploymentExperimentError,
    DeploymentExperimentProvenance,
)
from warhammer40k_core.ai.deployment_geometry_features import DeploymentGeometryObservation
from warhammer40k_core.ai.parameterized_training import (
    DeploymentTrainingCandidateLink,
    RankedDeploymentTrainingLink,
)
from warhammer40k_core.ai.player_policy import (
    PlayerDecisionContext,
    PolicyAction,
    PolicyRegistration,
    PolicyRouter,
    payload_digest,
)
from warhammer40k_core.ai.policy_contracts import TrainingRow
from warhammer40k_core.ai.runner import BoundedPolicyRunner, RunLimits, RunnerError
from warhammer40k_core.ai.runner_admission import DeploymentDatasetAdmission, RunnerAdmission
from warhammer40k_core.ai.training_admission import (
    COMMAND_POINT_BALANCE_TARGET,
    LOCAL_REFERENCE_PRODUCER,
    MISSING_TARGET_PRODUCER,
    AdmittedTrainingTarget,
    FiniteEpisodeAdmission,
    MixedEpisodeAdmission,
    TrainingAdmissionError,
    VerifiedEpisodeOrigin,
    VerifiedLocalReference,
)
from warhammer40k_core.ai.training_candidates import FiniteTrainingCandidateLink
from warhammer40k_core.ai.training_targets import (
    LinkedTrainingTarget,
    NamedTrainingTarget,
    TargetEpisodeEnd,
    TargetHorizon,
    TargetMeaning,
    TargetValidity,
)
from warhammer40k_core.ai.training_transitions import (
    FiniteAcceptedTransition,
    ParameterizedAcceptedTransition,
)
from warhammer40k_core.engine.event_log import JsonValue, canonical_json
from warhammer40k_core.engine.phase import LifecycleStatusKind
from warhammer40k_core.engine.replay import ReplayRunner


class _GeometryRanker:
    def score(
        self,
        context: PlayerDecisionContext,
        candidates: tuple[DeploymentCandidatePayload, ...],
        *,
        parameters: dict[str, JsonValue],
    ) -> tuple[DeploymentCandidateScore, ...]:
        assert parameters == {"axis": "x"}
        return tuple(
            DeploymentCandidateScore(
                candidate["candidate_id"],
                DeploymentGeometryObservation.from_candidate(
                    DeploymentPlacementCandidate.from_payload(candidate, context=context),
                    context=context,
                ).model_inputs[1],
            )
            for candidate in candidates
        )


@dataclass(frozen=True)
class ExperimentCase:
    row: TrainingRow
    link: RankedDeploymentTrainingLink
    episode: MixedEpisodeAdmission

    def evidence(self, deployment: DeploymentCase) -> DeploymentExperimentProvenance:
        return DeploymentExperimentProvenance.from_episode(
            self.link,
            episode=self.episode,
            row=self.row,
            context=deployment.context,
            config=deployment.first.before.lifecycle.config,
            reward_profile_version=self.row.reward_profile_version,
        )


@pytest.fixture(scope="module")
def experiment(deployment: DeploymentCase) -> ExperimentCase:
    context = deployment.context
    before = deployment.first.after
    checkpoint = before.to_persistence_payload()
    seed = DeploymentPlacementCandidate.from_action(deployment.action, context=context)
    candidates = DeploymentCandidateSet.generate(
        seed,
        context=context,
        translations=((1000.0, 0.0), (0.0, 0.0), (1.0, 0.0), (2.0, 0.0), (3.0, 0.0)),
        raw_budget=4,
    )
    validated = ValidatedDeploymentCandidates.validate(
        candidates, context=context, session=before, validation_budget=3, accepted_limit=2
    )
    row = deployment_row(deployment, seed)
    ranking = RankedDeploymentCandidates.rank(
        validated,
        context=context,
        session=before,
        ranker=_GeometryRanker(),
        configuration=DeploymentRankerConfiguration(row.policy_provenance, '{"axis":"x"}'),
        reward_profile_version=row.reward_profile_version,
    )
    assert ranking.selected_candidate_id == candidates.candidates[2].candidate_id
    after = before.fork()
    action = ranking.select(context, session=after)
    status = after.submit_viewer_parameterized_payload(
        viewer=ViewerContext.for_player(action.actor_id),
        request_id=action.request_id,
        payload=json.loads(cast(str, action.proposal_json)),
        result_id="experiment-placement",
    )
    assert status.status_kind is not LifecycleStatusKind.INVALID
    if status.status_kind is LifecycleStatusKind.ADVANCED:
        after.advance_until_decision_or_terminal()
    assert (
        ReplayRunner.from_payload(after.replay_artifact(artifact_id="experiment"))
        .run()
        .reproduced_exactly
    )
    assert LocalGameSession.from_persistence_payload(after.to_persistence_payload()).view(
        viewer_player_id=action.actor_id
    ) == after.view(viewer_player_id=action.actor_id)
    transition = ParameterizedAcceptedTransition.from_sessions(
        action,
        context=context,
        before=before,
        after=after,
        trajectory_id="admission-trajectory",
        perspective_player_id="player-a",
        previous=deployment.transitions[0],
    )
    row = replace(
        row,
        input_features=DeploymentGeometryObservation.from_candidate(
            candidates.candidates[2], context=context
        ).training_features(),
        chosen_action_id=ranking.selected_candidate_id,
        legal_action_mask=(False, True, True),
        decision_record_id=transition.authoritative_record_id,
    )
    link = RankedDeploymentTrainingLink.from_row(
        row,
        ranking=ranking,
        candidate_link=DeploymentTrainingCandidateLink.from_row(
            row, validated=validated, context=context, transition=transition
        ),
        context=context,
    )
    episode = MixedEpisodeAdmission.from_transitions(
        deployment.origin,
        transitions=(deployment.transitions[0], transition),
        final_session=after,
        episode_end=TargetEpisodeEnd.TRUNCATED,
        stop_reason="declared-experiment-end",
    )
    assert before.to_persistence_payload() == checkpoint
    return ExperimentCase(row, link, episode)


def _object(value: JsonValue) -> dict[str, JsonValue]:
    assert isinstance(value, dict)
    return value


def test_experiment_joins_real_producers_encoder_and_reachable_accepted_episode(
    deployment: DeploymentCase, experiment: ExperimentCase
) -> None:
    evidence = experiment.evidence(deployment)
    payload = evidence.to_payload()
    link = _object(payload["ranked_training_link"])
    candidate_link = _object(link["candidate_link"])
    generation = _object(candidate_link["candidate_set"])
    validation = _object(candidate_link["validation"])
    ranking = _object(link["ranking"])
    assert generation["raw_budget"] == generation["raw_attempts"] == 4
    assert generation["stop_reason"] == "raw_budget"
    assert validation["validation_budget"] == validation["validation_attempts"] == 3
    assert validation["accepted_limit"] == validation["accepted_count"] == 2
    assert validation["unvalidated_count"] == 1
    assert ranking["choice_seed"] == deployment.context.choice_seed
    assert _object(ranking["configuration"])["parameters"] == {"axis": "x"}
    assert payload["episode"] == experiment.episode.to_payload()
    assert payload["accepted_transition"] == experiment.link.candidate_link.transition.to_payload()
    assert _object(_object(payload["training_geometry"])["observation"])["registry_version"] == (
        "deployment-model-origin-features-v1"
    )
    assert evidence.content_hash == payload_digest(payload)
    assert (
        DeploymentExperimentProvenance.from_payload(
            json.loads(canonical_json(payload)),
            link=experiment.link,
            episode=experiment.episode,
            row=experiment.row,
            context=deployment.context,
            config=deployment.first.before.lifecycle.config,
            reward_profile_version=experiment.row.reward_profile_version,
        )
        == evidence
    )
    payload["episode"] = None
    assert evidence.to_payload()["episode"] is not None
    with pytest.raises(FrozenInstanceError):
        evidence._payload_json = "{}"  # type: ignore[misc]


@pytest.mark.parametrize(
    "path",
    [
        ("schema_version",),
        ("scope",),
        ("extra",),
        ("episode", "origin", "engine_build_id"),
        ("episode", "origin", "source_identity", "catalog_hash"),
        ("episode", "origin", "source_identity", "game_config_hash"),
        ("episode", "stop_reason"),
        ("accepted_transition", "after_checkpoint_hash"),
        ("ranked_training_link", "training_row_hash"),
        ("ranked_training_link", "ranking", "choice_seed"),
        ("ranked_training_link", "ranking", "configuration", "parameters"),
        ("ranked_training_link", "candidate_link", "candidate_set", "raw_budget"),
        ("ranked_training_link", "candidate_link", "candidate_set", "seed"),
        ("ranked_training_link", "candidate_link", "validation", "validation_budget"),
        ("ranked_training_link", "candidate_link", "validation", "accepted_limit"),
        ("training_geometry", "observation", "registry_version"),
        ("training_geometry", "observation", "features"),
    ],
)
def test_experiment_closed_loader_rejects_component_drift(
    deployment: DeploymentCase, experiment: ExperimentCase, path: tuple[str, ...]
) -> None:
    payload = experiment.evidence(deployment).to_payload()
    target = payload
    for key in path[:-1]:
        target = _object(target[key])
    target[path[-1]] = "drift"
    with pytest.raises(DeploymentExperimentError, match="drifted"):
        DeploymentExperimentProvenance.from_payload(
            payload,
            link=experiment.link,
            episode=experiment.episode,
            row=experiment.row,
            context=deployment.context,
            config=deployment.first.before.lifecycle.config,
            reward_profile_version=experiment.row.reward_profile_version,
        )


@pytest.mark.parametrize("change", ["episode", "private-seed", "source", "reward", "row", "choice"])
def test_experiment_rejects_incompatible_verified_inputs(
    deployment: DeploymentCase, experiment: ExperimentCase, change: str
) -> None:
    config = deployment.first.before.lifecycle.config
    row, context, episode = experiment.row, deployment.context, experiment.episode
    reward = row.reward_profile_version
    if change == "episode":
        episode = deployment.episode()  # Same origin/config, different actual accepted choice.
    elif change == "private-seed":
        config = replace(
            config,
            private_rng_seed=("0" if config.private_rng_seed[0] != "0" else "1")
            + config.private_rng_seed[1:],
        )
    elif change == "source":
        config = replace(
            config,
            ruleset_descriptor=replace(
                config.ruleset_descriptor, descriptor_version="different", descriptor_hash=""
            ),
        )
    elif change == "reward":
        reward = "different"
    elif change == "row":
        row = replace(row, row_id="different")
    else:
        context = replace(context, choice_seed=context.choice_seed + 1)
    with pytest.raises(DeploymentExperimentError):
        DeploymentExperimentProvenance.from_episode(
            experiment.link,
            episode=episode,
            row=row,
            context=context,
            config=config,
            reward_profile_version=reward,
        )


def test_experiment_rejects_untyped_or_non_json_evidence(
    deployment: DeploymentCase, experiment: ExperimentCase
) -> None:
    with pytest.raises(DeploymentExperimentError):
        DeploymentExperimentProvenance()
    with pytest.raises(DeploymentExperimentError, match="typed"):
        DeploymentExperimentProvenance.from_episode(
            experiment.link,
            episode=cast(MixedEpisodeAdmission, experiment.episode.to_payload()),
            row=experiment.row,
            context=deployment.context,
            config=deployment.first.before.lifecycle.config,
            reward_profile_version=experiment.row.reward_profile_version,
        )
    with pytest.raises(DeploymentExperimentError, match="JSON-safe"):
        DeploymentExperimentProvenance.from_payload(
            {"bad": object()},
            link=experiment.link,
            episode=experiment.episode,
            row=experiment.row,
            context=deployment.context,
            config=deployment.first.before.lifecycle.config,
            reward_profile_version=experiment.row.reward_profile_version,
        )


@pytest.mark.parametrize("failure", [False, True])
def test_runner_dataset_joins_ranked_choice_and_keeps_failed_run_rows_excluded(
    deployment: DeploymentCase, failure: bool
) -> None:
    before = (deployment.first.after if failure else deployment.last.after).fork()
    request = before.lifecycle.pending_decision_request()
    assert request is not None
    assert request.actor_id is not None
    view = before.view(viewer_player_id=request.actor_id)
    pending = view["pending_decision"]
    assert pending is not None
    choice_seed = int(
        payload_digest(
            [
                "player-policy-choice-v1",
                13,
                view["game_id"],
                request.actor_id,
                pending["request_id"],
            ]
        ),
        16,
    )
    context = PlayerDecisionContext.from_view(view, choice_seed=choice_seed)
    action = context.propose(
        _deployment_payload_from_proposal(context.observation["pending_proposal"])
    )
    seed = DeploymentPlacementCandidate.from_action(action, context=context)
    candidates = DeploymentCandidateSet.generate(
        seed, context=context, translations=((0.0, 0.0),), raw_budget=1
    )
    validated = ValidatedDeploymentCandidates.validate(
        candidates, context=context, session=before, validation_budget=1, accepted_limit=1
    )
    row = deployment_row(deployment, seed)
    ranking = RankedDeploymentCandidates.rank(
        validated,
        context=context,
        session=before,
        ranker=_GeometryRanker(),
        configuration=DeploymentRankerConfiguration(row.policy_provenance, '{"axis":"x"}'),
        reward_profile_version=row.reward_profile_version,
    )
    selected = ranking.select(context, session=before)

    expected_context = context

    class PreparedPolicy:
        def choose(self, context: PlayerDecisionContext) -> PolicyAction:
            assert context == expected_context
            assert set(context.__slots__) == {"route", "observation_json", "choice_seed"}
            return selected

    after = before.fork()
    runner = BoundedPolicyRunner(
        session=after,
        router=PolicyRouter(
            (
                PolicyRegistration(
                    context.route,
                    "prepared-geometry-v1",
                    canonical_json({"deployment_ranking_hash": ranking.content_hash}),
                    PreparedPolicy(),
                ),
            )
        ),
        limits=RunLimits(13, 1, 120),
    )
    if failure:
        with pytest.raises(RunnerError) as caught:
            runner.run()
        report = caught.value.report
    else:
        report = runner.run()
        assert report.stop_reason == "terminal"
    transition = ParameterizedAcceptedTransition.from_sessions(
        selected,
        context=context,
        before=before,
        after=after,
        trajectory_id="runner-deployment",
        perspective_player_id="player-a",
    )
    row = replace(
        row,
        decision_record_id=transition.authoritative_record_id,
        chosen_action_id=ranking.selected_candidate_id,
        input_features=DeploymentGeometryObservation.from_candidate(
            seed, context=context
        ).training_features(),
        legal_action_mask=(True,),
    )
    candidate_link = DeploymentTrainingCandidateLink.from_row(
        row, validated=validated, context=context, transition=transition
    )
    link = RankedDeploymentTrainingLink.from_row(
        row, ranking=ranking, candidate_link=candidate_link, context=context
    )
    origin = VerifiedEpisodeOrigin.from_session(before, config=before.lifecycle.config)
    end = TargetEpisodeEnd.ABORTED if failure else TargetEpisodeEnd.TERMINAL
    reason = report.failure_reason if failure else None
    episode = MixedEpisodeAdmission.from_transitions(
        origin, transitions=(transition,), final_session=after, episode_end=end, stop_reason=reason
    )
    experiment = DeploymentExperimentProvenance.from_episode(
        link,
        episode=episode,
        row=row,
        context=context,
        config=before.lifecycle.config,
        reward_profile_version=row.reward_profile_version,
    )
    if failure:
        target = NamedTrainingTarget(
            target_id=COMMAND_POINT_BALANCE_TARGET,
            meaning=TargetMeaning.LOCAL_REFERENCE,
            perspective_player_id="player-a",
            horizon=TargetHorizon.DECISION_COUNT,
            horizon_decisions=transition.accepted_record_stop,
            episode_end=end,
            validity=TargetValidity.MISSING,
            value=None,
            value_unit="command_points",
            missing_reason=reason,
            producer_id=MISSING_TARGET_PRODUCER,
            evidence_hash=episode.content_hash,
            reward_profile_version=row.reward_profile_version,
        )
    else:
        reference = VerifiedLocalReference.from_episode(
            episode,
            transition=transition,
            final_session=after,
            target_id=COMMAND_POINT_BALANCE_TARGET,
            horizon_decisions=transition.accepted_record_stop,
        )
        target = NamedTrainingTarget(
            target_id=COMMAND_POINT_BALANCE_TARGET,
            meaning=TargetMeaning.LOCAL_REFERENCE,
            perspective_player_id="player-a",
            horizon=TargetHorizon.DECISION_COUNT,
            horizon_decisions=transition.accepted_record_stop,
            episode_end=end,
            validity=TargetValidity.OBSERVED,
            value=reference.to_payload()["value"],
            value_unit="command_points",
            missing_reason=None,
            producer_id=LOCAL_REFERENCE_PRODUCER,
            evidence_hash=reference.content_hash,
            reward_profile_version=row.reward_profile_version,
        )
    linked = LinkedTrainingTarget.from_link(candidate_link, row=row, context=context, target=target)
    admitted = AdmittedTrainingTarget.from_episode(
        linked,
        episode=episode,
        transition=transition,
        link=candidate_link,
        row=row,
        context=context,
        config=before.lifecycle.config,
        reward_profile_version=row.reward_profile_version,
        final_session=after,
    )
    receipt = RunnerAdmission.from_report(
        report,
        origin=origin,
        initial_session=before,
        final_session=after,
        attempt_sessions=(before,),
        transitions=(transition,),
        episode=episode,
    )
    choices = ((0, experiment, linked, admitted),)
    dataset = DeploymentDatasetAdmission.from_runs((receipt,), choices=choices)
    counts = _object(dataset.to_payload()["counts"])
    assert counts["attempted_runs"] == counts["attempted_choices"] == counts["admitted_rows"] == 1
    assert counts["failed_runs"] == int(failure)
    assert counts["eligible_rows"] == int(not failure)
    assert (
        DeploymentDatasetAdmission.from_payload(
            dataset.to_payload(), runs=(receipt,), choices=choices
        )
        == dataset
    )
    repeated = DeploymentDatasetAdmission.from_runs(
        (receipt, receipt), choices=(*choices, (1, experiment, linked, admitted))
    )
    datasets = (dataset, repeated)
    assignments = tuple(
        DeploymentSplitAssignment(
            dataset_index, run_index, DeploymentDatasetPartition.TRAIN, "setup", "layout-a"
        )
        for dataset_index, run_index in ((0, 0), (1, 0), (1, 1))
    )
    split = DeploymentDatasetSplit.from_datasets(datasets, assignments=assignments)
    split_payload = split.to_payload()
    split_counts = _object(split_payload["counts"])
    assert split_counts["attempted_runs"] == split_counts["admitted_rows"] == 3
    assert split_counts["failed_runs"] == split_counts["excluded_rows"] == 3 * int(failure)
    assert split_counts["eligible_rows"] == 3 * int(not failure)
    partitions = _object(split_payload["partitions"])
    assert _object(partitions["train"])["choice_occurrences"] == [[0, 0], [1, 0], [1, 1]]
    assert _object(partitions["train"])["counts"] == split_counts
    assert _object(partitions["validation"])["choice_occurrences"] == []
    assert _object(partitions["test"])["run_occurrences"] == []
    assert split_payload["datasets"] == [item.to_payload() for item in datasets]
    assert (
        DeploymentDatasetSplit.from_payload(
            json.loads(json.dumps(split_payload)), datasets=datasets, assignments=assignments
        )
        == split
    )
    # A split cannot promote an excluded row, discard occurrences or relabel a
    # supplied partition while retaining the original typed assignment evidence.
    _object(_object(split_payload["partitions"])["train"])["choice_occurrences"] = [[0, 0]]
    with pytest.raises(TrainingAdmissionError, match="drifted"):
        DeploymentDatasetSplit.from_payload(
            split_payload, datasets=datasets, assignments=assignments
        )
    with pytest.raises(TrainingAdmissionError, match="trajectory"):
        DeploymentDatasetSplit.from_datasets(
            datasets,
            assignments=(
                *assignments[:2],
                replace(assignments[2], partition=DeploymentDatasetPartition.TEST),
            ),
        )
    assert before.to_persistence_payload() != after.to_persistence_payload()
    assert (
        LocalGameSession.from_persistence_payload(
            after.to_persistence_payload()
        ).to_persistence_payload()
        == after.to_persistence_payload()
    )
    with pytest.raises(TrainingAdmissionError, match="repeats"):
        DeploymentDatasetAdmission.from_runs((receipt,), choices=choices + choices)
    with pytest.raises(TrainingAdmissionError, match="drifted"):
        DeploymentDatasetAdmission.from_runs(
            (receipt,),
            choices=(
                (0, experiment, replace(linked, training_candidate_link_hash="0" * 64), admitted),
            ),
        )
    without_transitions = RunnerAdmission.from_report(
        report,
        origin=origin,
        initial_session=before,
        final_session=after,
        attempt_sessions=(before,),
    )
    with pytest.raises(TrainingAdmissionError, match="drifted"):
        DeploymentDatasetAdmission.from_runs((without_transitions,), choices=choices)
    with pytest.raises(TrainingAdmissionError, match="request drifted"):
        RunnerAdmission.from_report(
            replace(report, decisions=(replace(report.decisions[0], request_id="wrong"),)),
            origin=origin,
            initial_session=before,
            final_session=after,
            attempt_sessions=(before,),
            transitions=(transition,),
            episode=episode,
        )


def test_successful_terminal_run_cannot_claim_an_earlier_prefix_preceded_failure(
    deployment: DeploymentCase,
) -> None:
    initial = deployment.first.before.fork()
    planned = initial.fork()
    snapshots: list[LocalGameSession] = []
    contexts: list[PlayerDecisionContext] = []
    actions: dict[str, PolicyAction] = {}
    for _ in range(8):
        pending = planned.lifecycle.pending_decision_request()
        assert pending is not None
        assert pending.actor_id is not None
        view = planned.view(viewer_player_id=pending.actor_id)
        viewer_request = view["pending_decision"]
        assert viewer_request is not None
        choice_hash = payload_digest(
            [
                "player-policy-choice-v1",
                13,
                view["game_id"],
                pending.actor_id,
                viewer_request["request_id"],
            ]
        )
        context = PlayerDecisionContext.from_view(view, choice_seed=int(choice_hash, 16))
        snapshots.append(planned.fork())
        contexts.append(context)
        if context.request["is_parameterized"]:
            action = context.propose(
                _deployment_payload_from_proposal(context.observation["pending_proposal"])
            )
            status = planned.submit_viewer_parameterized_payload(
                viewer=ViewerContext.for_player(action.actor_id),
                request_id=action.request_id,
                payload=json.loads(cast(str, action.proposal_json)),
                result_id=f"ai:{choice_hash}",
            )
        else:
            action = context.select_option(context.request["options"][0]["option_id"])
            assert action.option_id is not None
            status = planned.submit_viewer_option(
                viewer=ViewerContext.for_player(action.actor_id),
                request_id=action.request_id,
                option_id=action.option_id,
                result_id=f"ai:{choice_hash}",
            )
        actions[context.observation_hash] = action
        if status.status_kind is LifecycleStatusKind.ADVANCED:
            status = planned.advance_until_decision_or_terminal()
        if status.status_kind is LifecycleStatusKind.TERMINAL:
            break
        assert status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    else:
        pytest.fail("Ordinary deployment did not reach the compact terminal boundary.")

    class PreparedSequence:
        def choose(self, context: PlayerDecisionContext) -> PolicyAction:
            return actions[context.observation_hash]

    policy = PreparedSequence()
    final = initial.fork()
    routes = tuple(dict.fromkeys(context.route for context in contexts))
    report = BoundedPolicyRunner(
        session=final,
        router=PolicyRouter(
            tuple(
                PolicyRegistration(route, "prepared-sequence-v1", "{}", policy) for route in routes
            )
        ),
        limits=RunLimits(13, 8, 120),
    ).run()
    assert report.stop_reason == "terminal"
    assert final.to_persistence_payload() == planned.to_persistence_payload()
    assert len(report.decisions) > 1
    prefix_after = snapshots[1]
    row = replace(
        deployment.first.row,
        decision_record_id=prefix_after.lifecycle.decision_controller.records[
            initial.decision_record_count()
        ].record_id,
    )
    transition = FiniteAcceptedTransition.from_sessions(
        FiniteTrainingCandidateLink.from_row(row, context=contexts[0]),
        row=row,
        context=contexts[0],
        before=initial,
        after=prefix_after,
        trajectory_id="successful-prefix",
        perspective_player_id="player-a",
    )
    origin = VerifiedEpisodeOrigin.from_session(initial, config=initial.lifecycle.config)
    episode = FiniteEpisodeAdmission.from_transitions(
        origin,
        transitions=(transition,),
        final_session=prefix_after,
        episode_end=TargetEpisodeEnd.TRUNCATED,
        stop_reason="accepted-prefix-before-runner-failure",
    )
    with pytest.raises(TrainingAdmissionError, match="Failed suffix"):
        RunnerAdmission.from_report(
            report,
            origin=origin,
            initial_session=initial,
            final_session=final,
            attempt_sessions=tuple(snapshots),
            transitions=(transition,),
            episode=episode,
        )
