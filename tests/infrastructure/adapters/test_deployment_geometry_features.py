from __future__ import annotations

import json
import math
from dataclasses import FrozenInstanceError, replace
from typing import cast

import pytest

from tests.shared.ai_training_admission_helpers import DeploymentCase, deployment_row
from tests.shared.ai_training_admission_helpers import deployment as deployment
from tests.shared.category_migration.phase18f_session_commands import (
    _compact_terminal_config,
    _deployment_payload_from_proposal,
    _terminal_progress_option_id,
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
from warhammer40k_core.ai.deployment_geometry_features import (
    DEPLOYMENT_GEOMETRY_FEATURES,
    DeploymentGeometryError,
    DeploymentGeometryObservation,
    DeploymentTrainingGeometry,
)
from warhammer40k_core.ai.parameterized_training import (
    DeploymentTrainingCandidateLink,
    RankedDeploymentTrainingLink,
)
from warhammer40k_core.ai.player_policy import PlayerDecisionContext, PolicyError
from warhammer40k_core.ai.policy_contracts import TrainingFeatureSourceKind, TrainingRow
from warhammer40k_core.ai.training_transitions import ParameterizedAcceptedTransition
from warhammer40k_core.engine.event_log import JsonValue, canonical_json
from warhammer40k_core.engine.phase import LifecycleStatusKind
from warhammer40k_core.engine.replay import ReplayRunner


def _candidate(deployment: DeploymentCase) -> DeploymentPlacementCandidate:
    return DeploymentPlacementCandidate.from_action(deployment.action, context=deployment.context)


def test_deployment_geometry_derivation_translation_and_closed_roundtrip(
    deployment: DeploymentCase,
) -> None:
    context, seed = deployment.context, _candidate(deployment)
    original = DeploymentGeometryObservation.from_candidate(seed, context=context)
    candidates = DeploymentCandidateSet.generate(seed, context=context, translations=((2.0, -3.0),))
    translated = DeploymentGeometryObservation.from_candidate(
        candidates.candidates[0], context=context
    )
    assert translated.model_inputs[0] == original.model_inputs[0]
    expected = (
        original.model_inputs[1] + 2,
        original.model_inputs[2] - 3,
        original.model_inputs[3],
        *original.model_inputs[4:],
    )
    for observed, value in zip(translated.model_inputs[1:], expected, strict=True):
        assert math.isclose(observed, value, rel_tol=1e-12, abs_tol=1e-12)
    payload = original.to_payload()
    features = cast(list[dict[str, JsonValue]], payload["features"])
    assert [feature["definition"] for feature in features] == [
        definition.to_payload() for definition in DEPLOYMENT_GEOMETRY_FEATURES
    ]
    assert all(type(value) in (int, float) for value in original.model_inputs)
    assert (
        DeploymentGeometryObservation.from_payload(
            json.loads(canonical_json(payload)), candidate=seed, context=context
        )
        == original
    )
    payload["features"] = []
    assert original.to_payload()["features"]
    with pytest.raises(FrozenInstanceError):
        original.model_inputs = ()  # type: ignore[misc]


def test_deployment_geometry_uses_all_origins_and_ignores_ids_order_and_facing(
    deployment: DeploymentCase,
) -> None:
    context = deployment.context
    proposal = cast(dict[str, JsonValue], _candidate(deployment).to_payload()["proposal"])
    source = cast(list[dict[str, JsonValue]], proposal["model_placements"])[0]
    placements: list[JsonValue] = []
    for index, position in enumerate(((1, 2, 3), (5, 8, 9), (3, 5, 6))):
        placement = json.loads(canonical_json(source))
        placement["model_instance_id"] = f"model-{index}"
        placement["unit_instance_id"] = f"component-{index}"
        placement["pose"]["position"] = dict(zip(("x", "y", "z"), position, strict=True))
        placements.append(placement)
    proposal["model_placements"] = placements
    candidate = DeploymentPlacementCandidate.from_action(context.propose(proposal), context=context)
    observation = DeploymentGeometryObservation.from_candidate(candidate, context=context)
    assert observation.model_inputs == (3, 3.0, 5.0, 6.0, 4.0, 6.0, 6.0)
    for index, item in enumerate(placements):
        placement = cast(dict[str, JsonValue], item)
        placement["model_instance_id"] = f"renamed-{index}"
        placement["unit_instance_id"] = f"renamed-component-{index}"
        cast(dict[str, JsonValue], placement["pose"])["facing"] = {"degrees": 180.0}
    proposal["model_placements"] = list(reversed(placements))
    relabeled = DeploymentPlacementCandidate.from_action(context.propose(proposal), context=context)
    other = DeploymentGeometryObservation.from_candidate(relabeled, context=context)
    assert relabeled.candidate_id != candidate.candidate_id
    assert other.model_inputs == observation.model_inputs
    proposal["model_placements"] = placements[:1]
    singleton = DeploymentPlacementCandidate.from_action(context.propose(proposal), context=context)
    assert DeploymentGeometryObservation.from_candidate(
        singleton, context=context
    ).model_inputs == (1, 1.0, 2.0, 3.0, 0.0, 0.0, 0.0)
    with pytest.raises(DeploymentGeometryError, match="drifted"):
        DeploymentGeometryObservation.from_payload(
            observation.to_payload(), candidate=relabeled, context=context
        )


@pytest.mark.parametrize(
    "change",
    [
        "schema_version",
        "registry_version",
        "candidate_id",
        "candidate_hash",
        "actor_id",
        "request_id",
        "observation_hash",
        "extra",
        "value",
        "unit",
        "dimensions",
        "scope",
        "unknown-feature",
        "boolean",
    ],
)
def test_deployment_geometry_loader_rejects_binding_definition_and_value_drift(
    deployment: DeploymentCase,
    change: str,
) -> None:
    candidate = _candidate(deployment)
    payload = DeploymentGeometryObservation.from_candidate(
        candidate, context=deployment.context
    ).to_payload()
    features = cast(list[dict[str, JsonValue]], payload["features"])
    definition = cast(dict[str, JsonValue], features[0]["definition"])
    if change in ("value", "boolean"):
        features[0]["value"] = True if change == "boolean" else 999
    elif change in ("unit", "dimensions", "scope", "unknown-feature"):
        field = {"scope": "information_scope", "unknown-feature": "feature_id"}.get(change, change)
        definition[field] = "drift"
    else:
        payload[change] = "drift"
    with pytest.raises(DeploymentGeometryError, match="drifted"):
        DeploymentGeometryObservation.from_payload(
            payload, candidate=candidate, context=deployment.context
        )


@pytest.mark.parametrize(
    "change",
    ["empty", "placement", "pose", "position", "bool", "text", "duplicate", "span-overflow"],
)
def test_deployment_geometry_rejects_unsupported_numeric_inputs(
    deployment: DeploymentCase, change: str
) -> None:
    context = deployment.context
    proposal = cast(dict[str, JsonValue], _candidate(deployment).to_payload()["proposal"])
    placements = cast(list[dict[str, JsonValue]], proposal["model_placements"])
    pose = cast(dict[str, JsonValue], placements[0]["pose"])
    if change == "empty":
        proposal["model_placements"] = []
    elif change == "placement":
        proposal["model_placements"] = [None]
    elif change == "pose":
        placements[0]["pose"] = None
    elif change == "position":
        pose["position"] = {"x": 1}
    elif change == "duplicate":
        placements.append(placements[0])
    elif change == "span-overflow":
        cast(dict[str, JsonValue], pose["position"])["x"] = -1e308
        extra = json.loads(canonical_json(placements[0]))
        extra["model_instance_id"] = "extra"
        extra["pose"]["position"]["x"] = 1e308
        placements.append(extra)
    else:
        cast(dict[str, JsonValue], pose["position"])["x"] = True if change == "bool" else "bad"
    candidate = DeploymentPlacementCandidate.from_action(context.propose(proposal), context=context)
    with pytest.raises(DeploymentGeometryError):
        DeploymentGeometryObservation.from_candidate(candidate, context=context)


class _OriginXRanker:
    def score(
        self,
        context: PlayerDecisionContext,
        candidates: tuple[DeploymentCandidatePayload, ...],
        *,
        parameters: dict[str, JsonValue],
    ) -> tuple[DeploymentCandidateScore, ...]:
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


@pytest.fixture(scope="module")
def geometry_training(
    deployment: DeploymentCase,
) -> tuple[TrainingRow, RankedDeploymentTrainingLink]:
    context, seed = deployment.context, _candidate(deployment)
    before = deployment.first.after
    snapshot = before.to_persistence_payload()
    candidates = DeploymentCandidateSet.generate(
        seed, context=context, translations=((1000.0, 0.0), (0.0, 0.0), (1.0, 0.0))
    )
    validated = ValidatedDeploymentCandidates.validate(candidates, context=context, session=before)
    assert len(validated.accepted_ids) == 2
    row = deployment_row(deployment, seed)
    ranking = RankedDeploymentCandidates.rank(
        validated,
        context=context,
        session=before,
        ranker=_OriginXRanker(),
        configuration=DeploymentRankerConfiguration(row.policy_provenance),
        reward_profile_version=row.reward_profile_version,
    )
    assert ranking.selected_candidate_id == candidates.candidates[2].candidate_id
    after = before.fork()
    action = ranking.select(context, session=after)
    status = after.submit_viewer_parameterized_payload(
        viewer=ViewerContext.for_player(action.actor_id),
        request_id=action.request_id,
        payload=json.loads(cast(str, action.proposal_json)),
        result_id="geometry-ranked-placement",
    )
    assert status.status_kind is not LifecycleStatusKind.INVALID
    if status.status_kind is LifecycleStatusKind.ADVANCED:
        after.advance_until_decision_or_terminal()
    assert (
        ReplayRunner.from_payload(after.replay_artifact(artifact_id="geometry"))
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
    observation = DeploymentGeometryObservation.from_candidate(
        candidates.candidates[2], context=context
    )
    row = replace(
        row,
        input_features=observation.training_features(),
        chosen_action_id=ranking.selected_candidate_id,
        legal_action_mask=(False, True, True),
        decision_record_id=transition.authoritative_record_id,
    )
    candidate_link = DeploymentTrainingCandidateLink.from_row(
        row, validated=validated, context=context, transition=transition
    )
    link = RankedDeploymentTrainingLink.from_row(
        row, ranking=ranking, candidate_link=candidate_link, context=context
    )
    assert before.to_persistence_payload() == snapshot
    return row, link


def test_deployment_geometry_drives_accepted_rank_commit_and_exact_training_join(
    deployment: DeploymentCase, geometry_training: tuple[TrainingRow, RankedDeploymentTrainingLink]
) -> None:
    row, link = geometry_training
    result = DeploymentTrainingGeometry.from_link(link, row=row, context=deployment.context)
    assert result.observation.training_features() == row.input_features
    assert (
        DeploymentTrainingGeometry.from_payload(
            json.loads(canonical_json(result.to_payload())),
            link=link,
            row=row,
            context=deployment.context,
        )
        == result
    )
    detached = result.to_payload()
    detached["observation"] = None
    assert result.to_payload()["observation"]
    for field in ("schema_version", "ranked_training_link_hash", "observation", "extra"):
        changed = result.to_payload()
        changed[field] = "drift"
        with pytest.raises(DeploymentGeometryError):
            DeploymentTrainingGeometry.from_payload(
                changed, link=link, row=row, context=deployment.context
            )


@pytest.mark.parametrize(
    "change",
    ["value", "source", "descriptor", "extra", "missing", "other-candidate", "row", "context"],
)
def test_deployment_geometry_training_rejects_semantic_or_full_row_drift(
    deployment: DeploymentCase,
    geometry_training: tuple[TrainingRow, RankedDeploymentTrainingLink],
    change: str,
) -> None:
    row, link = geometry_training
    context = deployment.context
    if change in ("row", "context"):
        if change == "row":
            row = replace(row, row_id="drift")
        else:
            context = replace(context, choice_seed=context.choice_seed + 1)
    else:
        features = row.input_features
        if change == "value":
            features = (replace(features[0], value=999), *features[1:])
        elif change == "source":
            features = (
                replace(features[0], source_kind=TrainingFeatureSourceKind.BOARD_STATE),
                *features[1:],
            )
        elif change == "descriptor":
            features = (replace(features[0], source_descriptor_ids=("unrelated",)), *features[1:])
        elif change == "other-candidate":
            features = DeploymentGeometryObservation.from_candidate(
                _candidate(deployment), context=context
            ).training_features()
        elif change == "missing":
            features = features[:-1]
        else:
            features = (*features, replace(features[0], feature_id="unknown-required-feature"))
        row = replace(row, input_features=features)
        candidate_link = DeploymentTrainingCandidateLink.from_row(
            row,
            validated=link.candidate_link.validated,
            context=context,
            transition=link.candidate_link.transition,
        )
        link = RankedDeploymentTrainingLink.from_row(
            row, ranking=link.ranking, candidate_link=candidate_link, context=context
        )
    with pytest.raises(DeploymentGeometryError):
        DeploymentTrainingGeometry.from_link(link, row=row, context=context)


def _hidden_context(
    seed: str, suffix: str
) -> tuple[PlayerDecisionContext, DeploymentPlacementCandidate]:
    session = LocalGameSession()
    session.start(
        replace(_compact_terminal_config(game_id="geometry-hidden"), private_rng_seed=seed)
    )
    status = session.advance_until_decision_or_terminal()
    for index in range(30):
        request = status.decision_request
        assert request is not None
        assert request.actor_id is not None
        context = PlayerDecisionContext.from_view(
            session.view(viewer_player_id=request.actor_id), choice_seed=7
        )
        if request.decision_type == "submit_deployment_placement":
            action = context.propose(
                _deployment_payload_from_proposal(context.observation["pending_proposal"])
            )
            return context, DeploymentPlacementCandidate.from_action(action, context=context)
        if index == 0:
            assert cast(dict[str, JsonValue], request.payload)["secret"] is True
        status = session.submit_viewer_option(
            viewer=ViewerContext.for_player(request.actor_id),
            request_id=context.request["request_id"],
            option_id=_terminal_progress_option_id(cast(dict[str, JsonValue], context.request)),
            result_id=f"geometry-prefix-{index}" + (suffix if index == 0 else ""),
        )
        if status.status_kind is LifecycleStatusKind.ADVANCED:
            status = session.advance_until_decision_or_terminal()
    pytest.fail("Ordinary deployment exceeded the explicit setup decision budget.")


def test_deployment_geometry_hidden_work_and_private_rng_noninterference() -> None:
    context, candidate = _hidden_context("1" * 64, "-first")
    other_context, other_candidate = _hidden_context("2" * 64, "-second")
    assert context == other_context
    assert candidate == other_candidate
    assert DeploymentGeometryObservation.from_candidate(
        candidate, context=context
    ) == DeploymentGeometryObservation.from_candidate(other_candidate, context=other_context)


def test_deployment_geometry_rejects_stale_context_and_direct_construction(
    deployment: DeploymentCase,
) -> None:
    candidate = _candidate(deployment)
    view = deployment.context.observation
    assert view["pending_decision"] is not None
    view["pending_decision"]["request_id"] = "stale"
    context = PlayerDecisionContext.from_view(view, choice_seed=7)
    with pytest.raises(PolicyError):
        DeploymentGeometryObservation.from_candidate(candidate, context=context)
    with pytest.raises(DeploymentGeometryError):
        DeploymentGeometryObservation()
    with pytest.raises(DeploymentGeometryError):
        DeploymentTrainingGeometry()
