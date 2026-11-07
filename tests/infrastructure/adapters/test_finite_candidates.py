from __future__ import annotations

from dataclasses import FrozenInstanceError, replace
from typing import cast

import pytest

from warhammer40k_core.adapters.access_control import ViewerContext
from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.adapters.setup_smoke import canonical_setup_prebattle_smoke_config
from warhammer40k_core.ai.finite_candidates import FiniteCandidate, FiniteCandidateSet
from warhammer40k_core.ai.player_policy import (
    CandidateExhaustedError,
    PlayerDecisionContext,
    PolicyError,
    payload_digest,
)
from warhammer40k_core.engine.replay import ReplayRunner


# Finite candidates are linked by opaque option IDs; their complete payloads
# remain detached from engine authority and are checked against the live view.
def _finite_context() -> tuple[LocalGameSession, PlayerDecisionContext]:
    session = LocalGameSession()
    session.start(canonical_setup_prebattle_smoke_config())
    session.advance_until_decision_or_terminal()
    context = PlayerDecisionContext.from_view(
        session.view(viewer_player_id="player-a"), choice_seed=7
    )
    return session, context


def test_finite_candidates_preserve_order_payloads_hashes_and_detachment() -> None:
    _, context = _finite_context()
    candidates = FiniteCandidateSet.from_context(context)
    options = context.request["options"]
    assert candidates.candidate_ids == tuple(option["option_id"] for option in options)
    assert [candidate.option for candidate in candidates.candidates] == options
    assert candidates.content_hash == FiniteCandidateSet.from_context(context).content_hash
    assert all(
        candidate.content_hash == payload_digest(candidate.option)
        for candidate in candidates.candidates
    )
    assert FiniteCandidateSet.from_payload(candidates.to_payload()) == candidates
    detached = candidates.to_payload()
    detached["options"][0]["payload"] = {"changed": True}
    assert candidates.to_payload()["options"] == options
    option = candidates.candidates[0].option
    option["label"] = "changed"
    assert candidates.candidates[0].option == options[0]
    with pytest.raises(FrozenInstanceError):
        candidates.actor_id = "player-b"  # type: ignore[misc]


def test_finite_candidate_selection_uses_ordinary_commit_and_replay() -> None:
    session, context = _finite_context()
    candidates = FiniteCandidateSet.from_context(context)
    option_id = candidates.candidate_ids[0]
    action = candidates.select(context, option_id)
    assert action == context.select_option(option_id)
    session.submit_viewer_option(
        viewer=ViewerContext.for_player(action.actor_id),
        request_id=action.request_id,
        option_id=option_id,
        result_id="candidate-contract-commit",
    )
    assert (
        ReplayRunner.from_payload(session.replay_artifact(artifact_id="finite-candidate-contract"))
        .run()
        .reproduced_exactly
    )
    restored = LocalGameSession.from_persistence_payload(session.to_persistence_payload())
    assert restored.view(viewer_player_id="player-a") == session.view(viewer_player_id="player-a")
    with pytest.raises(PolicyError, match="binding"):
        candidates.select(
            PlayerDecisionContext.from_view(
                session.view(viewer_player_id="player-b"), choice_seed=7
            ),
            option_id,
        )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("actor_id", "player-b"),
        ("request_id", "other-request"),
        ("observation_hash", "0" * 64),
    ],
)
def test_finite_candidate_selection_rejects_wrong_bindings(field: str, value: str) -> None:
    _, context = _finite_context()
    candidates = FiniteCandidateSet.from_context(context)
    payload: dict[str, object] = dict(candidates.to_payload())
    payload[field] = value
    drifted = FiniteCandidateSet.from_payload(payload)
    with pytest.raises(PolicyError, match="binding"):
        drifted.select(context, candidates.candidate_ids[0])


def test_finite_candidate_selection_rejects_payload_and_order_drift() -> None:
    _, context = _finite_context()
    candidates = FiniteCandidateSet.from_context(context)
    option = candidates.candidates[0].option
    option["payload"] = {"changed": True}
    modified = replace(
        candidates, candidates=(FiniteCandidate.from_payload(option), *candidates.candidates[1:])
    )
    reordered = replace(candidates, candidates=tuple(reversed(candidates.candidates)))
    for drifted in (modified, reordered):
        with pytest.raises(PolicyError, match="binding"):
            drifted.select(context, candidates.candidate_ids[0])
        assert drifted.content_hash != candidates.content_hash
    with pytest.raises(PolicyError, match="not in"):
        candidates.select(context, "invented-option")


@pytest.mark.parametrize("change", ["parameterized", "empty", "duplicate"])
def test_finite_candidate_generation_rejects_unsupported_sets(change: str) -> None:
    _, context = _finite_context()
    view = context.observation
    request = view["pending_decision"]
    assert request is not None
    if change == "parameterized":
        request["is_parameterized"] = True
        assert request["interaction"] is not None
        request["interaction"]["proposal_kind"] = "deployment_placement"
    elif change == "empty":
        request["options"] = []
    else:
        request["options"].append(request["options"][0])
    error = CandidateExhaustedError if change == "empty" else PolicyError
    with pytest.raises(error):
        FiniteCandidateSet.from_context(PlayerDecisionContext.from_view(view, choice_seed=7))


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("schema_version", "future"),
        ("generator_id", "invented"),
        ("validation_id", "invented"),
        ("observation_hash", "bad"),
        ("actor_id", ""),
        ("request_id", None),
        ("options", []),
        ("options", {}),
        ("options", [object()]),
        ("options", [1]),
        ("extra", "hidden-input"),
    ],
)
def test_finite_candidate_loader_rejects_malformed_contract(field: str, value: object) -> None:
    _, context = _finite_context()
    payload: dict[str, object] = dict(FiniteCandidateSet.from_context(context).to_payload())
    payload[field] = value
    with pytest.raises(PolicyError):
        FiniteCandidateSet.from_payload(payload)


@pytest.mark.parametrize(
    "value", ["{}", "[]", '{"option_id":"x","label":"x","payload":null,"extra":1}', "bad"]
)
def test_finite_candidate_rejects_malformed_option(value: str) -> None:
    with pytest.raises(PolicyError):
        FiniteCandidate(value)


def test_finite_candidate_identity_ignores_hidden_opponent_selection() -> None:
    sets: list[FiniteCandidateSet] = []
    for selected in ("fixed:assassination:bring_it_down", "fixed:assassination:cleanse"):
        session, context = _finite_context()
        action = FiniteCandidateSet.from_context(context).select(context, selected)
        session.submit_viewer_option(
            viewer=ViewerContext.for_player(action.actor_id),
            request_id=action.request_id,
            option_id=selected,
            result_id="hidden-selection",
        )
        session.advance_until_decision_or_terminal()
        other = PlayerDecisionContext.from_view(
            session.view(viewer_player_id="player-b"), choice_seed=9
        )
        sets.append(FiniteCandidateSet.from_context(other))
    assert sets[0] == sets[1]
    assert sets[0].content_hash == sets[1].content_hash


@pytest.mark.parametrize("candidates", [[], ("invalid",)])
def test_finite_candidate_set_rejects_mutable_or_untyped_entries(candidates: object) -> None:
    _, context = _finite_context()
    with pytest.raises(PolicyError, match="immutable typed tuple"):
        FiniteCandidateSet(
            actor_id=context.route.actor_id,
            request_id=context.request["request_id"],
            observation_hash=context.observation_hash,
            candidates=cast(tuple[FiniteCandidate, ...], candidates),
        )
