from __future__ import annotations

import json
from dataclasses import FrozenInstanceError, replace
from typing import cast

import pytest

from tests.shared.category_migration.phase18f_session_commands import (
    _compact_terminal_config,
    _deployment_payload_from_proposal,
    _terminal_progress_option_id,
)
from warhammer40k_core.adapters.access_control import ViewerContext
from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.adapters.projection import GameViewPayload
from warhammer40k_core.ai.deployment_candidate_search import (
    DeploymentCandidateExhaustedError,
    DeploymentCandidateSet,
    DeploymentSearchStop,
)
from warhammer40k_core.ai.deployment_candidate_validation import ValidatedDeploymentCandidates
from warhammer40k_core.ai.deployment_candidates import DeploymentPlacementCandidate
from warhammer40k_core.ai.player_policy import PlayerDecisionContext, PolicyError
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
