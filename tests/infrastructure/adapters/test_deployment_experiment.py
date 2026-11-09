from __future__ import annotations

import json
from dataclasses import FrozenInstanceError, dataclass, replace
from typing import cast

import pytest

from tests.shared.ai_training_admission_helpers import DeploymentCase, deployment_row
from tests.shared.ai_training_admission_helpers import deployment as deployment
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
from warhammer40k_core.ai.deployment_experiment import (
    DeploymentExperimentError,
    DeploymentExperimentProvenance,
)
from warhammer40k_core.ai.deployment_geometry_features import DeploymentGeometryObservation
from warhammer40k_core.ai.parameterized_training import (
    DeploymentTrainingCandidateLink,
    RankedDeploymentTrainingLink,
)
from warhammer40k_core.ai.player_policy import PlayerDecisionContext, payload_digest
from warhammer40k_core.ai.policy_contracts import TrainingRow
from warhammer40k_core.ai.training_admission import MixedEpisodeAdmission
from warhammer40k_core.ai.training_targets import TargetEpisodeEnd
from warhammer40k_core.ai.training_transitions import ParameterizedAcceptedTransition
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
