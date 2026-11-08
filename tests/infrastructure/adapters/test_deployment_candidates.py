from __future__ import annotations

import json
from dataclasses import FrozenInstanceError, replace
from typing import cast

import pytest

from tests.shared.ai_training_admission_helpers import DeploymentCase, DeploymentTrainingProof
from tests.shared.ai_training_admission_helpers import deployment as deployment
from tests.shared.ai_training_admission_helpers import deployment_training as deployment_training
from tests.shared.category_migration.phase18f_session_commands import (
    _compact_terminal_config,
    _deployment_payload_from_proposal,
    _terminal_progress_option_id,
)
from warhammer40k_core.adapters.access_control import ViewerContext
from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.adapters.projection import GameViewPayload
from warhammer40k_core.ai.deployment_candidate_ranking import (
    DeploymentCandidateScore,
    RankedDeploymentCandidates,
)
from warhammer40k_core.ai.deployment_candidate_search import (
    DeploymentCandidateExhaustedError,
    DeploymentCandidateSet,
    DeploymentSearchStop,
)
from warhammer40k_core.ai.deployment_candidate_validation import ValidatedDeploymentCandidates
from warhammer40k_core.ai.deployment_candidates import (
    DeploymentCandidatePayload,
    DeploymentPlacementCandidate,
)
from warhammer40k_core.ai.parameterized_training import DeploymentTrainingCandidateLink
from warhammer40k_core.ai.player_policy import PlayerDecisionContext, PolicyError
from warhammer40k_core.ai.policy_contracts import TrainingRow
from warhammer40k_core.ai.training_admission import (
    COMMAND_POINT_BALANCE_TARGET,
    LOCAL_REFERENCE_PRODUCER,
    AdmittedTrainingTarget,
    MixedEpisodeAdmission,
    TrainingAdmissionError,
    VerifiedEpisodeOrigin,
    VerifiedLocalReference,
)
from warhammer40k_core.ai.training_candidates import TrainingCandidateLinkError
from warhammer40k_core.ai.training_targets import (
    LinkedTrainingTarget,
    NamedTrainingTarget,
    TargetEpisodeEnd,
    TargetHorizon,
    TargetMeaning,
    TargetValidity,
)
from warhammer40k_core.ai.training_transitions import ParameterizedAcceptedTransition
from warhammer40k_core.engine.event_log import JsonValue, canonical_json
from warhammer40k_core.engine.phase import LifecycleStatusKind
from warhammer40k_core.engine.replay import ReplayRunner


def _setup(
    *, hidden_result_suffix: str = "", private_rng_seed: str | None = None
) -> LocalGameSession:
    session = LocalGameSession()
    config = _compact_terminal_config(game_id="deployment-candidate-search")
    if private_rng_seed is not None:
        config = replace(config, private_rng_seed=private_rng_seed)
    session.start(config)
    status = session.advance_until_decision_or_terminal()
    for index in range(30):
        request = status.decision_request
        assert request is not None
        assert request.actor_id is not None
        if request.decision_type == "submit_deployment_placement":
            return session
        context = PlayerDecisionContext.from_view(
            session.view(viewer_player_id=request.actor_id), choice_seed=7
        )
        choice = _terminal_progress_option_id(cast(dict[str, JsonValue], context.request))
        status = session.submit_viewer_option(
            viewer=ViewerContext.for_player(request.actor_id),
            request_id=context.request["request_id"],
            option_id=choice,
            result_id=f"candidate-prefix-{index}" + (hidden_result_suffix if index == 0 else ""),
        )
        if status.status_kind is LifecycleStatusKind.ADVANCED:
            status = session.advance_until_decision_or_terminal()
        assert status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    pytest.fail("Ordinary deployment exceeded the explicit setup decision budget.")


def _context_seed(
    session: LocalGameSession,
) -> tuple[PlayerDecisionContext, DeploymentPlacementCandidate]:
    pending = session.lifecycle.pending_decision_request()
    assert pending is not None
    assert pending.actor_id is not None
    context = PlayerDecisionContext.from_view(
        session.view(viewer_player_id=pending.actor_id), choice_seed=7
    )
    seed = DeploymentPlacementCandidate.from_action(
        context.propose(_deployment_payload_from_proposal(context.observation["pending_proposal"])),
        context=context,
    )
    return context, seed


@pytest.fixture(scope="module")
def deployment_session() -> LocalGameSession:
    return _setup()


def test_deployment_generation_has_distinct_geometry_and_stable_detached_roundtrip(
    deployment_session: LocalGameSession,
) -> None:
    context, seed = _context_seed(deployment_session)
    original_seed = seed.to_payload()
    candidate_set = DeploymentCandidateSet.generate(seed, context=context)
    assert len(candidate_set.candidates) == 5
    assert len({candidate.candidate_id for candidate in candidate_set.candidates}) == 5
    positions: list[str] = []
    for candidate in candidate_set.candidates:
        proposal = cast(dict[str, JsonValue], candidate.to_payload()["proposal"])
        placements = cast(list[dict[str, JsonValue]], proposal["model_placements"])
        positions.append(canonical_json([placement["pose"] for placement in placements]))
    assert len(set(positions)) == 5
    assert seed.to_payload() == original_seed
    assert candidate_set == DeploymentCandidateSet.generate(seed, context=context)
    assert candidate_set == DeploymentCandidateSet.from_payload(
        json.loads(canonical_json(candidate_set.to_payload())), context=context
    )
    detached = candidate_set.to_payload()
    detached["candidates"] = []
    assert candidate_set.to_payload()["candidates"]
    with pytest.raises(FrozenInstanceError):
        candidate_set.candidates = ()  # type: ignore[misc]


def test_deployment_validation_preserves_live_state_and_commits_alternatives_with_replay(
    deployment_session: LocalGameSession,
) -> None:
    context, seed = _context_seed(deployment_session)
    candidate_set = DeploymentCandidateSet.generate(seed, context=context)
    before = deployment_session.to_persistence_payload()
    validated = ValidatedDeploymentCandidates.validate(
        candidate_set, context=context, session=deployment_session
    )
    assert len(validated.accepted_ids) >= 2
    assert validated.to_payload()["validation_attempts"] == 5
    assert validated == ValidatedDeploymentCandidates.from_payload(
        json.loads(canonical_json(validated.to_payload())),
        candidate_set=candidate_set,
        context=context,
        session=deployment_session,
    )
    assert deployment_session.to_persistence_payload() == before
    outcomes: list[GameViewPayload] = []
    for candidate_id in validated.accepted_ids[:2]:
        live = deployment_session.fork()
        action = validated.select(context, candidate_id, session=live)
        status = live.submit_viewer_parameterized_payload(
            viewer=ViewerContext.for_player(action.actor_id),
            request_id=action.request_id,
            payload=json.loads(cast(str, action.proposal_json)),
            result_id="commit-candidate",
        )
        assert status.status_kind is not LifecycleStatusKind.INVALID
        assert live.decision_record_count() > deployment_session.decision_record_count()
        assert (
            ReplayRunner.from_payload(live.replay_artifact(artifact_id="candidate"))
            .run()
            .reproduced_exactly
        )
        restored = LocalGameSession.from_persistence_payload(live.to_persistence_payload())
        assert restored.view(viewer_player_id=context.route.actor_id) == live.view(
            viewer_player_id=context.route.actor_id
        )
        outcomes.append(live.view(viewer_player_id=context.route.actor_id))
        with pytest.raises(PolicyError, match="checkpoint"):
            validated.select(context, candidate_id, session=live)
        with pytest.raises(PolicyError, match="observation"):
            ValidatedDeploymentCandidates.validate(candidate_set, context=context, session=live)
    assert outcomes[0] != outcomes[1]
    assert deployment_session.to_persistence_payload() == before


def test_deployment_rule_rejection_is_internal_and_does_not_replace_live_request(
    deployment_session: LocalGameSession,
) -> None:
    context, seed = _context_seed(deployment_session)
    candidates = DeploymentCandidateSet.generate(
        seed, context=context, translations=((1000.0, 0.0), (0.0, 0.0), (1.0, 0.0))
    )
    before = deployment_session.to_persistence_payload()
    result = ValidatedDeploymentCandidates.validate(
        candidates, context=context, session=deployment_session
    )
    receipt = result.to_payload()
    entries = cast(list[dict[str, JsonValue]], receipt["results"])
    assert entries[0]["accepted"] is False
    assert entries[0]["status"] == "invalid"
    assert entries[0]["diagnostics"]
    assert entries[1]["accepted"] is True
    assert cast(int, receipt["rejected_count"]) >= 1
    assert deployment_session.to_persistence_payload() == before
    with pytest.raises(PolicyError, match="not validated"):
        result.select(context, candidates.candidates[0].candidate_id, session=deployment_session)


def test_deployment_generation_duplicate_and_raw_budget_accounting(
    deployment_session: LocalGameSession,
) -> None:
    context, seed = _context_seed(deployment_session)
    candidates = DeploymentCandidateSet.generate(
        seed,
        context=context,
        translations=((0.0, 0.0), (-0.0, 0.0), (1.0, 0.0), (2.0, 0.0)),
        raw_budget=3,
    )
    assert len(candidates.candidates) == 2
    assert candidates.to_payload()["duplicates"] == 1
    assert candidates.to_payload()["raw_attempts"] == 3
    assert candidates.to_payload()["stop_reason"] == "raw_budget"


@pytest.mark.parametrize(
    ("budget", "limit", "stop"), [(1, 16, "validation_budget"), (64, 1, "accepted_limit")]
)
def test_deployment_validation_budget_returns_explicit_partial_valid_set(
    deployment_session: LocalGameSession,
    budget: int,
    limit: int,
    stop: str,
) -> None:
    context, seed = _context_seed(deployment_session)
    candidates = DeploymentCandidateSet.generate(seed, context=context)
    result = ValidatedDeploymentCandidates.validate(
        candidates,
        context=context,
        session=deployment_session,
        validation_budget=budget,
        accepted_limit=limit,
    )
    receipt = result.to_payload()
    assert receipt["stop_reason"] == stop
    assert receipt["validation_attempts"] == 1
    assert receipt["accepted_count"] == 1
    assert receipt["unvalidated_count"] == 4
    with pytest.raises(PolicyError, match="not validated"):
        result.select(context, candidates.candidates[-1].candidate_id, session=deployment_session)


@pytest.mark.parametrize("kind", ["raw", "empty", "validation", "accepted", "invalid"])
def test_deployment_typed_exhaustion_reports_attempts_without_live_changes(
    deployment_session: LocalGameSession,
    kind: str,
) -> None:
    context, seed = _context_seed(deployment_session)
    before = deployment_session.to_persistence_payload()

    def exhaust() -> None:
        candidates = DeploymentCandidateSet.generate(
            seed,
            context=context,
            raw_budget=0 if kind == "raw" else 64,
            translations=() if kind == "empty" else ((1000.0, 0.0),),
        )
        ValidatedDeploymentCandidates.validate(
            candidates,
            context=context,
            session=deployment_session,
            validation_budget=0 if kind == "validation" else 64,
            accepted_limit=0 if kind == "accepted" else 16,
        )

    with pytest.raises(DeploymentCandidateExhaustedError) as caught:
        exhaust()
    error = caught.value
    assert error.raw_attempts == (0 if kind in ("raw", "empty") else 1)
    assert error.validation_attempts == (1 if kind == "invalid" else 0)
    assert error.duplicates == 0
    assert (
        error.stop_reason
        is {
            "raw": DeploymentSearchStop.RAW_BUDGET,
            "empty": DeploymentSearchStop.COMPLETE,
            "validation": DeploymentSearchStop.VALIDATION_BUDGET,
            "accepted": DeploymentSearchStop.ACCEPTED_LIMIT,
            "invalid": DeploymentSearchStop.COMPLETE,
        }[kind]
    )
    assert deployment_session.to_persistence_payload() == before


def test_deployment_generator_ignores_hidden_history_and_private_rng() -> None:
    first = _setup(hidden_result_suffix="-one", private_rng_seed="1" * 64)
    second = _setup(hidden_result_suffix="-two", private_rng_seed="2" * 64)
    assert first.to_persistence_payload() != second.to_persistence_payload()
    first_record = first.lifecycle.decision_controller.records[0]
    second_record = second.lifecycle.decision_controller.records[0]
    assert first_record.request.actor_id == "player-a"
    assert cast(dict[str, JsonValue], first_record.request.payload)["secret"] is True
    assert first_record.result.result_id != second_record.result.result_id
    assert first.lifecycle.config.private_rng_seed != second.lifecycle.config.private_rng_seed
    context_a, seed_a = _context_seed(first)
    context_b, seed_b = _context_seed(second)
    assert context_a.observation_json == context_b.observation_json
    a = DeploymentCandidateSet.generate(seed_a, context=context_a)
    b = DeploymentCandidateSet.generate(seed_b, context=context_b)
    assert a == b
    assert a.content_hash == b.content_hash
    assert "checkpoint_hash" not in a.to_payload()
    validated = ValidatedDeploymentCandidates.validate(
        a, context=context_a, session=first, accepted_limit=1
    )
    with pytest.raises(PolicyError, match="checkpoint"):
        validated.select(context_b, validated.accepted_ids[0], session=second)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("schema_version", "future"),
        ("generator_id", "other"),
        ("raw_attempts", 64),
        ("duplicates", 9),
        ("candidates", []),
        ("translations", [[0]]),
        ("extra", "secret"),
    ],
)
def test_deployment_set_loader_rejects_drift(
    deployment_session: LocalGameSession,
    field: str,
    value: JsonValue,
) -> None:
    context, seed = _context_seed(deployment_session)
    payload = DeploymentCandidateSet.generate(seed, context=context).to_payload()
    payload[field] = value
    with pytest.raises(PolicyError):
        DeploymentCandidateSet.from_payload(payload, context=context)


@pytest.mark.parametrize("value", [-1, 65, True, 1.5])
def test_deployment_generation_rejects_invalid_budget(
    deployment_session: LocalGameSession,
    value: object,
) -> None:
    context, seed = _context_seed(deployment_session)
    with pytest.raises(PolicyError, match="budget"):
        DeploymentCandidateSet.generate(seed, context=context, raw_budget=cast(int, value))


@pytest.mark.parametrize("value", [float("nan"), float("inf"), True, "1"])
def test_deployment_generation_rejects_nonfinite_or_untyped_offsets(
    deployment_session: LocalGameSession,
    value: object,
) -> None:
    context, seed = _context_seed(deployment_session)
    with pytest.raises(PolicyError, match="finite numbers"):
        DeploymentCandidateSet.generate(
            seed, context=context, translations=((cast(float, value), 0.0),)
        )


def test_deployment_binding_and_receipt_tampering_fail_closed(
    deployment_session: LocalGameSession,
) -> None:
    context, seed = _context_seed(deployment_session)
    candidates = DeploymentCandidateSet.generate(seed, context=context)
    view = context.observation
    pending = view["pending_decision"]
    assert pending is not None
    pending["request_id"] = "stale"
    drifted = PlayerDecisionContext.from_view(view, choice_seed=7)
    with pytest.raises(PolicyError, match="binding"):
        candidates.require_context(drifted)
    with pytest.raises(PolicyError, match="binding"):
        DeploymentCandidateSet.from_payload(candidates.to_payload(), context=drifted)
    result = ValidatedDeploymentCandidates.validate(
        candidates,
        context=context,
        session=deployment_session,
        accepted_limit=1,
    )
    original = result.to_payload()
    changed = result.to_payload()
    changed["accepted_count"] = 9
    with pytest.raises(PolicyError, match="drifted"):
        ValidatedDeploymentCandidates.from_payload(
            changed,
            candidate_set=candidates,
            context=context,
            session=deployment_session,
        )
    assert result.to_payload() == original
    with pytest.raises(FrozenInstanceError):
        result.accepted_ids = ()  # type: ignore[misc]


@pytest.mark.parametrize("drift", ["stale", "wrong_player", "malformed"])
def test_deployment_invalid_seed_uses_engine_rejection_without_live_mutation(
    deployment_session: LocalGameSession,
    drift: str,
) -> None:
    context, seed = _context_seed(deployment_session)
    proposal = cast(dict[str, JsonValue], seed.to_payload()["proposal"])
    if drift == "stale":
        proposal["proposal_request_id"] = "stale"
    elif drift == "wrong_player":
        proposal["player_id"] = "player-a" if context.route.actor_id == "player-b" else "player-b"
    else:
        del proposal["game_id"]
    seed = DeploymentPlacementCandidate.from_action(context.propose(proposal), context=context)
    candidates = DeploymentCandidateSet.generate(seed, context=context, raw_budget=1)
    before = deployment_session.to_persistence_payload()
    with pytest.raises(DeploymentCandidateExhaustedError) as caught:
        ValidatedDeploymentCandidates.validate(
            candidates, context=context, session=deployment_session
        )
    assert caught.value.validation_attempts == 1
    assert deployment_session.to_persistence_payload() == before


@pytest.mark.parametrize("field", ["model_placements", "pose", "position", "coordinate"])
def test_deployment_generator_rejects_malformed_geometry(
    deployment_session: LocalGameSession,
    field: str,
) -> None:
    context, seed = _context_seed(deployment_session)
    proposal = cast(dict[str, JsonValue], seed.to_payload()["proposal"])
    placements = cast(list[dict[str, JsonValue]], proposal["model_placements"])
    pose = cast(dict[str, JsonValue], placements[0]["pose"])
    if field == "model_placements":
        proposal["model_placements"] = []
    elif field == "pose":
        placements[0]["pose"] = None
    elif field == "position":
        pose["position"] = {"x": 1.0}
    else:
        cast(dict[str, JsonValue], pose["position"])["x"] = "bad"
    seed = DeploymentPlacementCandidate.from_action(context.propose(proposal), context=context)
    with pytest.raises(PolicyError):
        DeploymentCandidateSet.generate(seed, context=context)


@pytest.fixture(scope="module")
def deployment_set_training(
    deployment: DeploymentCase, deployment_training: DeploymentTrainingProof
) -> tuple[TrainingRow, DeploymentTrainingCandidateLink]:
    candidates = DeploymentCandidateSet.generate(
        deployment_training.link.candidate,
        context=deployment.context,
        translations=((1000.0, 0.0), (0.0, 0.0), (1.0, 0.0), (2.0, 0.0)),
    )
    validated = ValidatedDeploymentCandidates.validate(
        candidates,
        context=deployment.context,
        session=deployment.first.after,
        validation_budget=3,
    )
    assert validated.to_payload()["accepted_count"] == 2
    row = replace(deployment_training.row, legal_action_mask=(False, True, True))
    return row, DeploymentTrainingCandidateLink.from_row(
        row,
        validated=validated,
        context=deployment.context,
        transition=deployment_training.link.transition,
    )


def test_deployment_set_training_preserves_full_search_and_validated_prefix(
    deployment: DeploymentCase,
    deployment_set_training: tuple[TrainingRow, DeploymentTrainingCandidateLink],
) -> None:
    row, link = deployment_set_training
    original = deployment.first.after.to_persistence_payload()
    payload = link.to_payload()
    assert payload["schema_version"] == "deployment-set-training-candidate-link-v1"
    assert link.chosen_action_index == 1
    assert link.chosen_action_id == row.chosen_action_id
    assert len(link.validated.candidate_set.candidates) == 4
    assert len(row.legal_action_mask) == 3
    assert payload["validation"]["unvalidated_count"] == 1
    assert payload["validation"]["stop_reason"] == "validation_budget"
    assert (
        payload["validation"]["checkpoint_hash"]
        == link.transition.to_payload()["before_checkpoint_hash"]
    )
    assert (
        DeploymentTrainingCandidateLink.from_payload(
            json.loads(canonical_json(payload)),
            row=row,
            context=deployment.context,
            session=deployment.first.after,
            transition=link.transition,
        )
        == link
    )
    assert original == deployment.first.after.to_persistence_payload()
    assert TrainingRow.from_payload(row.to_payload()) == row
    payload["candidate_set"]["candidates"] = []
    payload["validation"]["results"] = []
    assert link.to_payload()["candidate_set"]["candidates"]
    assert link.to_payload()["validation"]["results"]
    with pytest.raises(FrozenInstanceError):
        link._evidence_json = "{}"  # type: ignore[misc]
    with pytest.raises(TrainingCandidateLinkError):
        DeploymentTrainingCandidateLink()


@pytest.mark.parametrize(
    "change",
    [
        "rejected",
        "unvalidated",
        "other-accepted",
        "mask",
        "tail-mask",
        "short-mask",
        "row",
        "record",
        "game",
        "feature",
        "scalar",
        "context",
        "transition",
    ],
)
def test_deployment_set_training_rejects_inexact_row_or_selection(
    deployment: DeploymentCase,
    deployment_set_training: tuple[TrainingRow, DeploymentTrainingCandidateLink],
    change: str,
) -> None:
    row, link = deployment_set_training
    context, transition = deployment.context, link.transition
    if change in ("rejected", "unvalidated", "other-accepted"):
        slot = {"rejected": 0, "unvalidated": 3, "other-accepted": 2}[change]
        row = replace(
            row, chosen_action_id=link.validated.candidate_set.candidates[slot].candidate_id
        )
    elif change == "mask":
        row = replace(row, legal_action_mask=(True, True, True))
    elif change == "tail-mask":
        row = replace(row, legal_action_mask=(False, True, True, False))
    elif change == "short-mask":
        row = replace(row, legal_action_mask=(False, True))
    elif change == "row":
        row = replace(row, row_id="changed")
    elif change == "record":
        row = replace(row, decision_record_id=deployment.transitions[0].authoritative_record_id)
    elif change == "game":
        row = replace(row, game_id="changed")
    elif change == "feature":
        row = replace(row, input_features=(replace(row.input_features[0], value=4),))
    elif change == "scalar":
        row = replace(row, target_value=0.75)
    elif change == "context":
        context = deployment.last.context
    else:
        transition = cast(ParameterizedAcceptedTransition, deployment.transitions[0])
    if change == "transition":
        with pytest.raises(TrainingCandidateLinkError):
            DeploymentTrainingCandidateLink.from_row(
                row, validated=link.validated, context=context, transition=transition
            )
    else:
        with pytest.raises(TrainingCandidateLinkError):
            link.require_matches(row, context=context)


@pytest.mark.parametrize(
    "change",
    [
        "schema_version",
        "training_row_hash",
        "candidate_set_hash",
        "validation_hash",
        "accepted_transition_hash",
        "chosen_action_id",
        "chosen_action_index",
        "bool-index",
        "unknown",
        "missing",
        "receipt",
        "set",
        "session",
    ],
)
def test_deployment_set_training_loader_reproduces_complete_evidence(
    deployment: DeploymentCase,
    deployment_set_training: tuple[TrainingRow, DeploymentTrainingCandidateLink],
    change: str,
) -> None:
    row, link = deployment_set_training
    payload: dict[str, object] = dict(link.to_payload())
    session = deployment.first.after
    if change == "receipt":
        cast(dict[str, object], payload["validation"])["rejected_count"] = 0
    elif change == "set":
        cast(dict[str, object], payload["candidate_set"])["duplicates"] = 99
    elif change == "session":
        session = deployment.after
    elif change == "bool-index":
        payload["chosen_action_index"] = True
    elif change == "missing":
        payload.pop("validation")
    else:
        payload[change] = "changed"
    with pytest.raises(TrainingCandidateLinkError):
        DeploymentTrainingCandidateLink.from_payload(
            payload,
            row=row,
            context=deployment.context,
            session=session,
            transition=link.transition,
        )


def test_deployment_set_training_commits_nonseed_alternative_and_binds_targets(
    deployment: DeploymentCase,
    deployment_set_training: tuple[TrainingRow, DeploymentTrainingCandidateLink],
) -> None:
    row, original = deployment_set_training
    validated = original.validated
    candidate_id = validated.candidate_set.candidates[2].candidate_id
    before = deployment.first.after
    after = before.fork()
    action = validated.select(deployment.context, candidate_id, session=after)
    status = after.submit_viewer_parameterized_payload(
        viewer=ViewerContext.for_player(action.actor_id),
        request_id=action.request_id,
        payload=json.loads(cast(str, action.proposal_json)),
        result_id="training-alternative",
    )
    if status.status_kind is LifecycleStatusKind.ADVANCED:
        status = after.advance_until_decision_or_terminal()
    assert status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    transition = ParameterizedAcceptedTransition.from_sessions(
        action,
        context=deployment.context,
        before=before,
        after=after,
        trajectory_id="alternative",
        perspective_player_id=action.actor_id,
    )
    row = replace(
        row, chosen_action_id=candidate_id, decision_record_id=transition.authoritative_record_id
    )
    link = DeploymentTrainingCandidateLink.from_row(
        row, validated=validated, context=deployment.context, transition=transition
    )
    assert link.chosen_action_index == 2
    assert (
        LocalGameSession.from_persistence_payload(
            after.to_persistence_payload()
        ).to_persistence_payload()
        == after.to_persistence_payload()
    )
    episode = MixedEpisodeAdmission.from_transitions(
        VerifiedEpisodeOrigin.from_session(before, config=before.lifecycle.config),
        transitions=(transition,),
        final_session=after,
        episode_end=TargetEpisodeEnd.TRUNCATED,
        stop_reason="alternative-boundary",
    )
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
        perspective_player_id=action.actor_id,
        horizon=TargetHorizon.DECISION_COUNT,
        horizon_decisions=transition.accepted_record_stop,
        episode_end=TargetEpisodeEnd.TRUNCATED,
        validity=TargetValidity.OBSERVED,
        value=reference.to_payload()["value"],
        value_unit="command_points",
        missing_reason=None,
        producer_id=LOCAL_REFERENCE_PRODUCER,
        evidence_hash=reference.content_hash,
        reward_profile_version=row.reward_profile_version,
    )
    linked = LinkedTrainingTarget.from_link(
        link, row=row, context=deployment.context, target=target
    )
    assert (
        LinkedTrainingTarget.from_payload(
            linked.to_payload(), link=link, row=row, context=deployment.context
        )
        == linked
    )
    admitted = AdmittedTrainingTarget.from_episode(
        linked,
        episode=episode,
        transition=transition,
        link=link,
        row=row,
        context=deployment.context,
        config=before.lifecycle.config,
        reward_profile_version=row.reward_profile_version,
        final_session=after,
    )
    assert admitted.to_payload()["eligible_for_learning"]
    assert (
        AdmittedTrainingTarget.from_payload(
            admitted.to_payload(),
            linked=linked,
            episode=episode,
            transition=transition,
            link=link,
            row=row,
            context=deployment.context,
            config=before.lifecycle.config,
            reward_profile_version=row.reward_profile_version,
            final_session=after,
        )
        == admitted
    )
    with pytest.raises(TrainingAdmissionError):
        AdmittedTrainingTarget.from_episode(
            linked,
            episode=episode,
            transition=original.transition,
            link=link,
            row=row,
            context=deployment.context,
            config=before.lifecycle.config,
            reward_profile_version=row.reward_profile_version,
            final_session=after,
        )


def test_deployment_set_link_rejects_same_view_different_authoritative_checkpoint(
    deployment_set_training: tuple[TrainingRow, DeploymentTrainingCandidateLink],
) -> None:
    first = _setup(hidden_result_suffix="-first", private_rng_seed="1" * 64)
    second = _setup(hidden_result_suffix="-second", private_rng_seed="2" * 64)
    context, seed = _context_seed(first)
    second_context, second_seed = _context_seed(second)
    assert context.observation_json == second_context.observation_json
    assert seed == second_seed
    candidates = DeploymentCandidateSet.generate(seed, context=context)
    validated = ValidatedDeploymentCandidates.validate(
        candidates, context=context, session=first, accepted_limit=1
    )
    action = seed.select(second_context)
    after = second.fork()
    status = after.submit_viewer_parameterized_payload(
        viewer=ViewerContext.for_player(action.actor_id),
        request_id=action.request_id,
        payload=json.loads(cast(str, action.proposal_json)),
        result_id="same-view-deployment",
    )
    if status.status_kind is LifecycleStatusKind.ADVANCED:
        status = after.advance_until_decision_or_terminal()
    assert status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    transition = ParameterizedAcceptedTransition.from_sessions(
        action,
        context=second_context,
        before=second,
        after=after,
        trajectory_id="same-view",
        perspective_player_id=action.actor_id,
    )
    row = replace(
        deployment_set_training[0],
        game_id=context.observation["game_id"],
        chosen_action_id=seed.candidate_id,
        legal_action_mask=(True,),
        decision_record_id=transition.authoritative_record_id,
    )
    with pytest.raises(TrainingCandidateLinkError, match="checkpoint"):
        DeploymentTrainingCandidateLink.from_row(
            row, validated=validated, context=second_context, transition=transition
        )
    correct = ValidatedDeploymentCandidates.validate(
        candidates, context=second_context, session=second, accepted_limit=1
    )
    link = DeploymentTrainingCandidateLink.from_row(
        row, validated=correct, context=second_context, transition=transition
    )
    assert link.chosen_action_index == 0
    assert link.to_payload()["validation"]["stop_reason"] == "accepted_limit"
    assert link.to_payload()["validation"]["unvalidated_count"] == 4
    assert link.validated.candidate_set == validated.candidate_set
    assert "checkpoint_hash" not in candidates.to_payload()


class _LastDeploymentRanker:
    def __init__(self, *, tied: bool = False, mutate: bool = False) -> None:
        self.tied = tied
        self.mutate = mutate
        self.calls: list[tuple[PlayerDecisionContext, tuple[DeploymentCandidatePayload, ...]]] = []

    def score(
        self, context: PlayerDecisionContext, candidates: tuple[DeploymentCandidatePayload, ...]
    ) -> tuple[DeploymentCandidateScore, ...]:
        self.calls.append((context, candidates))
        scores = tuple(
            DeploymentCandidateScore(candidate["candidate_id"], 0.0 if self.tied else float(index))
            for index, candidate in enumerate(candidates)
        )
        if self.mutate:
            context.observation["game_id"] = "changed"
            candidates[0]["proposal"] = None
        return tuple(reversed(scores))


@pytest.fixture(scope="module")
def ranking_case(
    deployment_session: LocalGameSession,
) -> tuple[PlayerDecisionContext, ValidatedDeploymentCandidates]:
    context, seed = _context_seed(deployment_session)
    candidates = DeploymentCandidateSet.generate(
        seed,
        context=context,
        translations=((1000.0, 0.0), (0.0, 0.0), (1.0, 0.0), (2.0, 0.0)),
    )
    validated = ValidatedDeploymentCandidates.validate(
        candidates,
        context=context,
        session=deployment_session,
        validation_budget=3,
    )
    assert len(validated.accepted_ids) == 2
    return context, validated


def test_deployment_ranking_selects_nonfirst_and_preserves_ordinary_commit_replay(
    deployment_session: LocalGameSession,
    ranking_case: tuple[PlayerDecisionContext, ValidatedDeploymentCandidates],
) -> None:
    context, validated = ranking_case
    ranker = _LastDeploymentRanker()
    before = deployment_session.to_persistence_payload()
    ranked = RankedDeploymentCandidates.rank(
        validated,
        context=context,
        session=deployment_session,
        ranker=ranker,
        ranker_id="last-position-v1",
        configuration_json='{"test":true}',
    )
    assert ranked.selected_candidate_id == validated.accepted_ids[1]
    payload = ranked.to_payload()
    assert payload["tie_break"] == "first-generated-accepted-v1"
    assert [
        entry["candidate_id"] for entry in cast(list[dict[str, JsonValue]], payload["scores"])
    ] == list(validated.accepted_ids)
    assert (
        RankedDeploymentCandidates.from_payload(
            json.loads(canonical_json(payload)),
            validated=validated,
            context=context,
            session=deployment_session,
            ranker=ranker,
            ranker_id="last-position-v1",
            configuration_json='{"test":true}',
        )
        == ranked
    )
    payload["scores"] = []
    assert ranked.to_payload()["scores"]
    live = deployment_session.fork()
    action = ranked.select(context, session=live)
    assert action == validated.select(context, validated.accepted_ids[1], session=live)
    status = live.submit_viewer_parameterized_payload(
        viewer=ViewerContext.for_player(action.actor_id),
        request_id=action.request_id,
        payload=json.loads(cast(str, action.proposal_json)),
        result_id="ranked-candidate",
    )
    assert status.status_kind is not LifecycleStatusKind.INVALID
    assert (
        ReplayRunner.from_payload(live.replay_artifact(artifact_id="ranked"))
        .run()
        .reproduced_exactly
    )
    assert (
        LocalGameSession.from_persistence_payload(
            live.to_persistence_payload()
        ).to_persistence_payload()
        == live.to_persistence_payload()
    )
    with pytest.raises(PolicyError, match="checkpoint"):
        ranked.select(context, session=live)
    with pytest.raises(PolicyError, match="choice seed"):
        ranked.select(replace(context, choice_seed=8), session=deployment_session)
    assert deployment_session.to_persistence_payload() == before
    with pytest.raises(FrozenInstanceError):
        ranked._payload_json = "{}"  # type: ignore[misc]


def test_deployment_ranker_receives_only_detached_accepted_actor_payloads(
    deployment_session: LocalGameSession,
    ranking_case: tuple[PlayerDecisionContext, ValidatedDeploymentCandidates],
) -> None:
    context, validated = ranking_case
    before = deployment_session.to_persistence_payload()
    original = validated.to_payload()
    ranker = _LastDeploymentRanker(mutate=True)
    ranked = RankedDeploymentCandidates.rank(
        validated,
        context=context,
        session=deployment_session,
        ranker=ranker,
        ranker_id="last-v1",
    )
    actor, candidates = ranker.calls[0]
    assert actor == context
    assert actor is not context
    assert [candidate["candidate_id"] for candidate in candidates] == list(validated.accepted_ids)
    assert all(
        candidate.keys() == DeploymentCandidatePayload.__annotations__.keys()
        for candidate in candidates
    )
    assert len(candidates) == 2
    assert validated.to_payload() == original
    assert validated.candidate_set.candidates[1].to_payload()["proposal"] is not None
    assert ranked.select(context, session=deployment_session).proposal_json is not None
    assert deployment_session.to_persistence_payload() == before


def test_deployment_ranking_ties_follow_generation_not_score_order(
    deployment_session: LocalGameSession,
    ranking_case: tuple[PlayerDecisionContext, ValidatedDeploymentCandidates],
) -> None:
    context, validated = ranking_case
    ranked = RankedDeploymentCandidates.rank(
        validated,
        context=context,
        session=deployment_session,
        ranker=_LastDeploymentRanker(tied=True),
        ranker_id="tie-v1",
    )
    assert ranked.selected_candidate_id == validated.accepted_ids[0]


@pytest.mark.parametrize(
    "value", [True, "1", None, float("nan"), float("inf"), -float("inf"), 10**1000]
)
def test_deployment_score_rejects_nonfinite_and_untyped_values(value: object) -> None:
    with pytest.raises(PolicyError, match="finite"):
        DeploymentCandidateScore("candidate", cast(float, value))


@pytest.mark.parametrize(
    "change", ["missing", "extra", "duplicate", "rejected", "unvalidated", "list", "dict", "none"]
)
def test_deployment_ranking_rejects_inexact_or_malformed_scores(
    deployment_session: LocalGameSession,
    ranking_case: tuple[PlayerDecisionContext, ValidatedDeploymentCandidates],
    change: str,
) -> None:
    context, validated = ranking_case

    class InvalidRanker:
        def score(
            self, context: PlayerDecisionContext, candidates: tuple[DeploymentCandidatePayload, ...]
        ) -> tuple[DeploymentCandidateScore, ...]:
            scores = tuple(
                DeploymentCandidateScore(candidate["candidate_id"], 1.0) for candidate in candidates
            )
            bad: object
            if change == "missing":
                bad = scores[:-1]
            elif change == "extra":
                bad = (*scores, DeploymentCandidateScore("unknown", 1.0))
            elif change == "duplicate":
                bad = (scores[0], scores[0])
            elif change in ("rejected", "unvalidated"):
                index = 0 if change == "rejected" else 3
                bad = (
                    scores[0],
                    DeploymentCandidateScore(
                        validated.candidate_set.candidates[index].candidate_id, 1.0
                    ),
                )
            elif change == "list":
                bad = list(scores)
            elif change == "dict":
                bad = tuple(
                    {"candidate_id": score.candidate_id, "value": score.value} for score in scores
                )
            else:
                bad = None
            return cast(tuple[DeploymentCandidateScore, ...], bad)

    before = deployment_session.to_persistence_payload()
    with pytest.raises(PolicyError, match="scores"):
        RankedDeploymentCandidates.rank(
            validated,
            context=context,
            session=deployment_session,
            ranker=InvalidRanker(),
            ranker_id="invalid-v1",
        )
    assert deployment_session.to_persistence_payload() == before


@pytest.mark.parametrize(
    "field",
    [
        "schema_version",
        "validation_hash",
        "candidate_set_hash",
        "actor_input_hash",
        "choice_seed",
        "ranker_id",
        "configuration",
        "tie_break",
        "selected_candidate_id",
        "scores",
        "extra",
    ],
)
def test_deployment_ranking_loader_rejects_drift(
    deployment_session: LocalGameSession,
    ranking_case: tuple[PlayerDecisionContext, ValidatedDeploymentCandidates],
    field: str,
) -> None:
    context, validated = ranking_case
    ranker = _LastDeploymentRanker()
    ranked = RankedDeploymentCandidates.rank(
        validated, context=context, session=deployment_session, ranker=ranker, ranker_id="last-v1"
    )
    payload = ranked.to_payload()
    payload[field] = "drift"
    with pytest.raises(PolicyError, match="drifted"):
        RankedDeploymentCandidates.from_payload(
            payload,
            validated=validated,
            context=context,
            session=deployment_session,
            ranker=ranker,
            ranker_id="last-v1",
        )


def test_deployment_ranking_hidden_work_and_private_rng_noninterference() -> None:
    first = _setup(hidden_result_suffix="-first", private_rng_seed="1" * 64)
    second = _setup(hidden_result_suffix="-second", private_rng_seed="2" * 64)
    context, seed = _context_seed(first)
    other_context, other_seed = _context_seed(second)
    assert context == other_context
    assert seed == other_seed
    candidates = DeploymentCandidateSet.generate(seed, context=context)
    a = ValidatedDeploymentCandidates.validate(candidates, context=context, session=first)
    b = ValidatedDeploymentCandidates.validate(candidates, context=other_context, session=second)
    assert a.accepted_ids == b.accepted_ids
    ranker = _LastDeploymentRanker()
    ranked_a = RankedDeploymentCandidates.rank(
        a, context=context, session=first, ranker=ranker, ranker_id="last-v1"
    )
    ranked_b = RankedDeploymentCandidates.rank(
        b, context=other_context, session=second, ranker=ranker, ranker_id="last-v1"
    )
    assert ranker.calls[0] == ranker.calls[1]
    assert ranked_a.selected_candidate_id == ranked_b.selected_candidate_id
    assert ranked_a.to_payload()["actor_input_hash"] == ranked_b.to_payload()["actor_input_hash"]
    assert ranked_a.to_payload()["validation_hash"] != ranked_b.to_payload()["validation_hash"]
    with pytest.raises(PolicyError, match="checkpoint"):
        RankedDeploymentCandidates.rank(
            a, context=other_context, session=second, ranker=ranker, ranker_id="last-v1"
        )
    assert len(ranker.calls) == 2
    view = context.observation
    assert view["pending_decision"] is not None
    view["pending_decision"]["request_id"] = "stale"
    stale = PlayerDecisionContext.from_view(view, choice_seed=7)
    with pytest.raises(PolicyError, match="binding"):
        RankedDeploymentCandidates.rank(
            a, context=stale, session=first, ranker=ranker, ranker_id="last-v1"
        )
    assert len(ranker.calls) == 2


def test_deployment_ranking_rechecks_checkpoint_after_callback(
    deployment_session: LocalGameSession,
    ranking_case: tuple[PlayerDecisionContext, ValidatedDeploymentCandidates],
) -> None:
    context, validated = ranking_case
    live = deployment_session.fork()

    class MutatingRanker(_LastDeploymentRanker):
        def score(
            self, context: PlayerDecisionContext, candidates: tuple[DeploymentCandidatePayload, ...]
        ) -> tuple[DeploymentCandidateScore, ...]:
            action = validated.select(context, validated.accepted_ids[0], session=live)
            live.submit_viewer_parameterized_payload(
                viewer=ViewerContext.for_player(action.actor_id),
                request_id=action.request_id,
                payload=json.loads(cast(str, action.proposal_json)),
                result_id="closure-commit",
            )
            return super().score(context, candidates)

    with pytest.raises(PolicyError, match="checkpoint"):
        RankedDeploymentCandidates.rank(
            validated,
            context=context,
            session=live,
            ranker=MutatingRanker(),
            ranker_id="mutating-v1",
        )
