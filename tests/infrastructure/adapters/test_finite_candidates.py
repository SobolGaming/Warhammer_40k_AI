from __future__ import annotations

import json
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
from warhammer40k_core.ai.policy_contracts import (
    TRAINING_ROW_SCHEMA_VERSION,
    PolicyArtifactKind,
    PolicyProvenance,
    TrainingFeature,
    TrainingFeatureSourceKind,
    TrainingRow,
)
from warhammer40k_core.ai.training_candidates import (
    FiniteTrainingCandidateLink,
    TrainingCandidateLinkError,
)
from warhammer40k_core.engine.event_log import canonical_json
from warhammer40k_core.engine.phase import LifecycleStatusKind
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


def _training_fixture(
    choice_index: int = 0,
) -> tuple[LocalGameSession, PlayerDecisionContext, TrainingRow]:
    session, before = _finite_context()
    candidates = FiniteCandidateSet.from_context(before)
    chosen = candidates.candidate_ids[choice_index]
    count = session.decision_record_count()
    status = session.submit_viewer_option(
        viewer=ViewerContext.for_player(before.route.actor_id),
        request_id=before.request["request_id"],
        option_id=chosen,
        result_id="training-link-commit",
    )
    assert status.status_kind in (
        LifecycleStatusKind.WAITING_FOR_DECISION,
        LifecycleStatusKind.ADVANCED,
    )
    assert session.decision_record_count() == count + 1
    provenance = PolicyProvenance.from_game_config(
        artifact_id="finite-link-policy-v1",
        artifact_kind=PolicyArtifactKind.RANKER,
        game_config=session.lifecycle.config,
        reward_profile_version="finite-link-test-target-v1",
    )
    row = TrainingRow(
        row_id="finite-link-row",
        game_id=before.observation["game_id"],
        decision_record_id=session.lifecycle.decision_controller.records[-1].record_id,
        policy_artifact_id=provenance.artifact_id,
        policy_provenance=provenance,
        reward_profile_version=provenance.reward_profile_version,
        input_features=(
            TrainingFeature(
                feature_id="decision-option-count",
                source_kind=TrainingFeatureSourceKind.DECISION_CONTEXT,
                value=len(candidates.candidates),
                source_descriptor_ids=("decision:" + before.route.decision_type,),
            ),
        ),
        legal_action_mask=tuple(True for _ in candidates.candidates),
        chosen_action_id=chosen,
        target_value=0.25,
        debug_metadata={"fixture": "finite-training-link"},
    )
    return session, before, row


@pytest.mark.parametrize("position", [0, -1])
def test_training_candidate_link_round_trips_without_changing_row_or_engine(position: int) -> None:
    session, before, row = _training_fixture(position)
    original_row = row.to_payload()
    original_state = session.to_persistence_payload()
    link = FiniteTrainingCandidateLink.from_row(row, context=before)
    payload = link.to_payload()
    loaded = FiniteTrainingCandidateLink.from_payload(
        json.loads(canonical_json(payload)), row=row, context=before
    )
    assert loaded == link
    assert payload["row_id"] == row.row_id
    assert payload["game_id"] == row.game_id
    assert payload["training_row_hash"] == payload_digest(row.to_payload())
    assert payload["candidate_set_hash"] == link.candidate_set.content_hash
    assert payload["chosen_action_index"] == (
        0 if position == 0 else len(link.candidate_set.candidates) - 1
    )
    assert link.candidate_set.candidate_ids[link.chosen_action_index] == row.chosen_action_id
    assert row.schema_version == TRAINING_ROW_SCHEMA_VERSION
    assert row.to_payload() == original_row
    assert session.to_persistence_payload() == original_state
    assert (
        ReplayRunner.from_payload(session.replay_artifact(artifact_id="training-link-replay"))
        .run()
        .reproduced_exactly
    )
    after = PlayerDecisionContext.from_view(
        session.view(viewer_player_id="player-b"), choice_seed=7
    )
    with pytest.raises(TrainingCandidateLinkError, match="binding"):
        link.require_matches(row, context=after)


@pytest.mark.parametrize(
    "drift", ["short", "long", "masked_chosen", "masked_other", "choice", "game"]
)
def test_training_candidate_link_rejects_inconsistent_legacy_row(drift: str) -> None:
    _, before, row = _training_fixture()
    if drift == "short":
        row = replace(row, legal_action_mask=row.legal_action_mask[:-1])
    elif drift == "long":
        row = replace(row, legal_action_mask=(*row.legal_action_mask, True))
    elif drift == "masked_chosen":
        row = replace(row, legal_action_mask=(False, *row.legal_action_mask[1:]))
    elif drift == "masked_other":
        row = replace(row, legal_action_mask=(*row.legal_action_mask[:-1], False))
    elif drift == "choice":
        row = replace(row, chosen_action_id="not-an-issued-candidate")
    else:
        row = replace(row, game_id="different-game")
    # The companion rejects the join; historical TrainingRow semantics stay intact.
    assert TrainingRow.from_payload(row.to_payload()).to_payload() == row.to_payload()
    with pytest.raises(TrainingCandidateLinkError):
        FiniteTrainingCandidateLink.from_row(row, context=before)


@pytest.mark.parametrize("drift", ["record", "target", "provenance", "debug"])
def test_training_candidate_link_commits_to_complete_row_payload(drift: str) -> None:
    _, before, row = _training_fixture()
    link = FiniteTrainingCandidateLink.from_row(row, context=before)
    if drift == "record":
        row = replace(row, decision_record_id="different-record")
    elif drift == "target":
        row = replace(row, target_value=0.5)
    elif drift == "provenance":
        row = replace(row, policy_provenance=replace(row.policy_provenance, engine_version="other"))
    else:
        row.debug_metadata["changed"] = True
    with pytest.raises(TrainingCandidateLinkError, match="row"):
        link.require_matches(row, context=before)


@pytest.mark.parametrize("drift", ["actor", "request", "observation", "order"])
def test_training_candidate_link_rejects_rehashed_candidate_binding_drift(drift: str) -> None:
    _, before, row = _training_fixture()
    link = FiniteTrainingCandidateLink.from_row(row, context=before)
    candidates = link.candidate_set
    if drift == "actor":
        candidates = replace(candidates, actor_id="player-b")
    elif drift == "request":
        candidates = replace(candidates, request_id="different-request")
    elif drift == "observation":
        candidates = replace(candidates, observation_hash="0" * 64)
    else:
        candidates = replace(candidates, candidates=tuple(reversed(candidates.candidates)))
    # Recompute derived hashes and index too; integrity alone cannot replace binding.
    payload = replace(link, candidate_set=candidates).to_payload()
    with pytest.raises(TrainingCandidateLinkError, match="binding"):
        FiniteTrainingCandidateLink.from_payload(payload, row=row, context=before)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("schema_version", "future"),
        ("row_id", "other-row"),
        ("row_id", ""),
        ("game_id", "other-game"),
        ("game_id", None),
        ("training_row_hash", "bad"),
        ("training_row_hash", "0" * 64),
        ("candidate_set_hash", "0" * 64),
        ("candidate_set_hash", "bad"),
        ("chosen_action_id", "other-choice"),
        ("chosen_action_id", None),
        ("chosen_action_index", True),
        ("chosen_action_index", -1),
        ("chosen_action_index", 1000),
        ("candidate_set", None),
        ("unknown", "privileged-state"),
    ],
)
def test_training_candidate_link_loader_rejects_malformed_or_drifted_fields(
    field: str, value: object
) -> None:
    _, before, row = _training_fixture()
    payload: dict[str, object] = dict(
        FiniteTrainingCandidateLink.from_row(row, context=before).to_payload()
    )
    payload[field] = value
    with pytest.raises(TrainingCandidateLinkError):
        FiniteTrainingCandidateLink.from_payload(payload, row=row, context=before)


def test_training_candidate_link_is_detached_immutable_and_strict_about_missing_fields() -> None:
    _, before, row = _training_fixture()
    link = FiniteTrainingCandidateLink.from_row(row, context=before)
    original = link.to_payload()
    detached = link.to_payload()
    detached["candidate_set"]["options"][0]["payload"] = {"changed": True}
    assert link.to_payload() == original
    with pytest.raises(FrozenInstanceError):
        link.row_id = "changed"  # type: ignore[misc]
    malformed: dict[str, object] = dict(original)
    del malformed["candidate_set_hash"]
    with pytest.raises(TrainingCandidateLinkError):
        FiniteTrainingCandidateLink.from_payload(malformed, row=row, context=before)


@pytest.mark.parametrize("target", [float("inf"), float("-inf"), float("nan")])
def test_training_candidate_link_rejects_non_json_safe_row(target: float) -> None:
    _, before, row = _training_fixture()
    with pytest.raises(TrainingCandidateLinkError, match="JSON"):
        FiniteTrainingCandidateLink.from_row(replace(row, target_value=target), context=before)


def test_training_candidate_link_requires_real_typed_inputs() -> None:
    _, before, row = _training_fixture()
    with pytest.raises(TrainingCandidateLinkError, match="TrainingRow"):
        FiniteTrainingCandidateLink.from_row(cast(TrainingRow, object()), context=before)
    link = FiniteTrainingCandidateLink.from_row(row, context=before)
    with pytest.raises(TrainingCandidateLinkError, match="candidate set"):
        replace(link, candidate_set=cast(FiniteCandidateSet, object()))


def test_training_candidate_link_rejects_parameterized_context() -> None:
    _, before, row = _training_fixture()
    view = before.observation
    request = view["pending_decision"]
    assert request is not None
    assert request["interaction"] is not None
    request["is_parameterized"] = True
    request["interaction"]["proposal_kind"] = "deployment_placement"
    context = PlayerDecisionContext.from_view(view, choice_seed=7)
    with pytest.raises(TrainingCandidateLinkError, match="finite decision context"):
        FiniteTrainingCandidateLink.from_row(row, context=context)


@pytest.mark.parametrize("payload", [None, [], "not-a-payload"])
def test_training_candidate_link_rejects_wrong_payload_shape(payload: object) -> None:
    _, before, row = _training_fixture()
    with pytest.raises(TrainingCandidateLinkError, match="fields"):
        FiniteTrainingCandidateLink.from_payload(payload, row=row, context=before)
