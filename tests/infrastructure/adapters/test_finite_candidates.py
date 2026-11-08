from __future__ import annotations

import json
from dataclasses import FrozenInstanceError, replace
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
from warhammer40k_core.ai.semantic_features import (
    FINITE_FEATURE_REGISTRY,
    FeatureInformationScope,
    FeatureUnit,
    FiniteTrainingObservation,
    SemanticFeatureDefinition,
    SemanticFeatureError,
    SemanticFeatureValue,
    SemanticObservation,
)
from warhammer40k_core.ai.training_candidates import (
    FiniteTrainingCandidateLink,
    TrainingCandidateLinkError,
)
from warhammer40k_core.ai.training_targets import (
    LinkedTrainingTarget,
    NamedTrainingTarget,
    TargetEpisodeEnd,
    TargetHorizon,
    TargetMeaning,
    TargetValidity,
    TrainingTargetError,
)
from warhammer40k_core.ai.training_transitions import (
    FiniteAcceptedTransition,
    ParameterizedAcceptedTransition,
    TrainingTransitionError,
)
from warhammer40k_core.core.ruleset_descriptor import (
    BattlePhaseKind,
    BattlePhaseSequenceDescriptor,
    RulesetDescriptor,
)
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.event_log import JsonValue, canonical_json
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


def _declared_local_target(row: TrainingRow) -> NamedTrainingTarget:
    # Deliberately synthetic contract value, never a learned or match-outcome label.
    return NamedTrainingTarget(
        target_id="synthetic-local-reference-v1",
        meaning=TargetMeaning.LOCAL_REFERENCE,
        perspective_player_id="player-b",
        horizon=TargetHorizon.DECISION_COUNT,
        horizon_decisions=1,
        episode_end=TargetEpisodeEnd.TRUNCATED,
        validity=TargetValidity.OBSERVED,
        value=2.0,
        value_unit="reference_points",
        missing_reason=None,
        producer_id="contract-test-producer-v1",
        evidence_hash=payload_digest({"fixture": "synthetic-target-declaration"}),
        reward_profile_version=row.reward_profile_version,
    )


def test_named_target_link_preserves_row_engine_perspective_and_detachment() -> None:
    session, context, row = _training_fixture()
    original_row = row.to_payload()
    original_engine = session.to_persistence_payload()
    link = FiniteTrainingCandidateLink.from_row(row, context=context)
    target = _declared_local_target(row)
    linked = LinkedTrainingTarget.from_link(link, row=row, context=context, target=target)
    payload = linked.to_payload()
    loaded = LinkedTrainingTarget.from_payload(
        json.loads(canonical_json(payload)), link=link, row=row, context=context
    )
    assert loaded == linked
    assert linked.content_hash == payload_digest(payload)
    assert payload["training_candidate_link_hash"] == payload_digest(link.to_payload())
    assert target.perspective_player_id != context.route.actor_id
    assert target.value != row.target_value
    assert row.to_payload() == original_row
    assert session.to_persistence_payload() == original_engine
    payload["target"]["value"] = 7.0
    assert linked.target.value == 2.0
    with pytest.raises(FrozenInstanceError):
        target.value = 4.0  # type: ignore[misc]
    assert (
        ReplayRunner.from_payload(session.replay_artifact(artifact_id="target-contract"))
        .run()
        .reproduced_exactly
    )


@pytest.mark.parametrize(
    ("meaning", "unit", "value"),
    [
        (TargetMeaning.MATCH_UTILITY, "unit_interval", 0),
        (TargetMeaning.MATCH_UTILITY, "unit_interval", 0.5),
        (TargetMeaning.MATCH_UTILITY, "unit_interval", 1),
        (TargetMeaning.VP_MARGIN, "victory_points", -17),
        (TargetMeaning.VP_MARGIN, "victory_points", 0),
        (TargetMeaning.VP_MARGIN, "victory_points", 23),
    ],
)
def test_named_match_target_declared_semantics_round_trip(
    meaning: TargetMeaning, unit: str, value: float
) -> None:
    _, _, row = _training_fixture()
    # A producer assertion only: this setup fixture does not establish a terminal result.
    target = replace(
        _declared_local_target(row),
        meaning=meaning,
        value_unit=unit,
        value=value,
        horizon=TargetHorizon.MATCH_END,
        horizon_decisions=None,
        episode_end=TargetEpisodeEnd.TERMINAL,
    )
    assert NamedTrainingTarget.from_payload(target.to_payload()) == target
    assert target.value == float(value)


@pytest.mark.parametrize("end", list(TargetEpisodeEnd))
def test_named_match_target_can_be_explicitly_missing(end: TargetEpisodeEnd) -> None:
    _, context, row = _training_fixture()
    target = replace(
        _declared_local_target(row),
        meaning=TargetMeaning.MATCH_UTILITY,
        value_unit="unit_interval",
        horizon=TargetHorizon.MATCH_END,
        horizon_decisions=None,
        episode_end=end,
        validity=TargetValidity.MISSING,
        value=None,
        missing_reason="ordinary-terminal-result-unavailable",
    )
    link = FiniteTrainingCandidateLink.from_row(row, context=context)
    linked = LinkedTrainingTarget.from_link(link, row=row, context=context, target=target)
    assert linked.to_payload()["target"]["value"] is None
    assert NamedTrainingTarget.from_payload(target.to_payload()) == target


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("schema_version", "future"),
        ("discount_convention", "gamma-0.99-per-request"),
        ("meaning", "win_probability"),
        ("horizon", "implicit"),
        ("episode_end", "complete"),
        ("validity", "assumed"),
        ("target_id", ""),
        ("perspective_player_id", None),
        ("producer_id", ""),
        ("reward_profile_version", ""),
        ("evidence_hash", "bad"),
        ("value_unit", ""),
        ("horizon_decisions", None),
        ("horizon_decisions", True),
        ("horizon_decisions", 0),
        ("horizon_decisions", -1),
        ("value", None),
        ("value", True),
        ("value", "2"),
        ("value", float("nan")),
        ("value", float("inf")),
        ("value", float("-inf")),
        ("value", 10**400),
        ("value", 2**60 + 1),
        ("missing_reason", "observed-but-missing"),
        ("episode_end", "aborted"),
        ("episode_end", "unsupported"),
        ("extra", "unvalidated-semantics"),
    ],
)
def test_named_target_loader_rejects_malformed_declarations(field: str, value: object) -> None:
    _, _, row = _training_fixture()
    payload: dict[str, object] = dict(_declared_local_target(row).to_payload())
    payload[field] = value
    with pytest.raises(TrainingTargetError):
        NamedTrainingTarget.from_payload(payload)


@pytest.mark.parametrize(
    "change",
    ["truncated", "utility", "margin", "units", "horizon", "missing-number", "missing-reason"],
)
def test_named_match_target_rejects_inconsistent_semantics(change: str) -> None:
    _, _, row = _training_fixture()
    payload: dict[str, object] = dict(_declared_local_target(row).to_payload())
    payload.update(
        meaning="match_utility",
        horizon="match_end",
        horizon_decisions=None,
        value_unit="unit_interval",
        value=1.0,
        episode_end="terminal",
    )
    if change == "truncated":
        payload["episode_end"] = "truncated"
    elif change == "utility":
        payload["value"] = 0.25
    elif change == "margin":
        payload.update(meaning="vp_margin", value_unit="victory_points", value=0.5)
    elif change == "units":
        payload["value_unit"] = "victory_points"
    elif change == "horizon":
        payload["horizon_decisions"] = 1
    elif change == "missing-number":
        payload.update(validity="missing", missing_reason="not-terminal")
    else:
        payload.update(validity="missing", value=None, missing_reason="")
    with pytest.raises(TrainingTargetError):
        NamedTrainingTarget.from_payload(payload)


@pytest.mark.parametrize("change", ["row", "context", "reward", "perspective", "link"])
def test_named_target_link_rejects_inconsistent_join(change: str) -> None:
    _, context, row = _training_fixture()
    link = FiniteTrainingCandidateLink.from_row(row, context=context)
    target = _declared_local_target(row)
    linked = LinkedTrainingTarget.from_link(link, row=row, context=context, target=target)
    if change == "row":
        row = replace(row, target_value=99)
    elif change == "context":
        view = context.observation
        view["game_id"] = "different-game"
        context = PlayerDecisionContext.from_view(view, choice_seed=7)
    elif change == "reward":
        linked = replace(linked, target=replace(target, reward_profile_version="different-reward"))
    elif change == "perspective":
        linked = replace(linked, target=replace(target, perspective_player_id="not-a-player"))
    else:
        linked = replace(linked, training_candidate_link_hash="0" * 64)
    with pytest.raises(TrainingTargetError):
        LinkedTrainingTarget.from_payload(linked.to_payload(), link=link, row=row, context=context)


@pytest.mark.parametrize("change", ["schema", "hash", "target", "missing", "extra", "root"])
def test_named_target_link_loader_rejects_malformed_payload(change: str) -> None:
    _, context, row = _training_fixture()
    link = FiniteTrainingCandidateLink.from_row(row, context=context)
    linked = LinkedTrainingTarget.from_link(
        link, row=row, context=context, target=_declared_local_target(row)
    )
    payload: object = cast(dict[str, object], linked.to_payload())
    assert isinstance(payload, dict)
    if change == "schema":
        payload["schema_version"] = "future"
    elif change == "hash":
        payload["training_candidate_link_hash"] = "bad"
    elif change == "target":
        payload["target"] = []
    elif change == "missing":
        del payload["target"]
    elif change == "extra":
        payload["extra"] = None
    else:
        payload = []
    with pytest.raises(TrainingTargetError):
        LinkedTrainingTarget.from_payload(payload, link=link, row=row, context=context)


def test_named_target_direct_construction_requires_typed_entries() -> None:
    _, context, row = _training_fixture()
    target = _declared_local_target(row)
    with pytest.raises(TrainingTargetError, match="typed enum"):
        replace(target, meaning=cast(TargetMeaning, "local_reference"))
    with pytest.raises(TrainingTargetError, match="typed named"):
        LinkedTrainingTarget("0" * 64, cast(NamedTrainingTarget, {}))
    with pytest.raises(TrainingTargetError, match="supported training"):
        LinkedTrainingTarget.from_link(
            cast(FiniteTrainingCandidateLink, None), row=row, context=context, target=target
        )
    payload: dict[str, object] = dict(target.to_payload())
    del payload["meaning"]
    with pytest.raises(TrainingTargetError, match="missing or unknown"):
        NamedTrainingTarget.from_payload(payload)


# Semantic inputs are a closed numeric surface; identity/provenance stays in joins.
@pytest.mark.parametrize("position", [0, -1])
def test_semantic_observation_round_trip_preserves_legacy_row_and_engine(position: int) -> None:
    session, context, row = _training_fixture(position)
    original = row.to_payload()
    state = session.to_persistence_payload()
    link = FiniteTrainingCandidateLink.from_row(row, context=context)
    semantic = FiniteTrainingObservation.from_link(link, row=row, context=context)
    observation = semantic.observation
    assert observation.model_inputs == (len(context.request["options"]),)
    assert observation.features[0].definition == FINITE_FEATURE_REGISTRY[0]
    assert observation.features[0].definition.unit is FeatureUnit.COUNT
    assert observation.features[0].definition.dimensions == ()
    assert (
        observation.features[0].definition.information_scope is FeatureInformationScope.ACTOR_VIEW
    )
    payload = json.loads(canonical_json(semantic.to_payload()))
    assert (
        FiniteTrainingObservation.from_payload(payload, link=link, row=row, context=context)
        == semantic
    )
    assert semantic.content_hash == payload_digest(semantic.to_payload())
    payload["observation"]["features"][0]["value"] = 0
    assert observation.model_inputs == (len(context.request["options"]),)
    assert row.to_payload() == original
    assert session.to_persistence_payload() == state
    assert TrainingRow.from_payload(original).schema_version == TRAINING_ROW_SCHEMA_VERSION


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("feature_id", "unit_id"),
        ("feature_id", "new-required-operator"),
        ("source_kind", "board_state"),
        ("value_kind", "string"),
        ("unit", "inches"),
        ("dimensions", [1]),
        ("dimensions", None),
        ("information_scope", "omniscient"),
        ("vocabulary_version", "arbitrary-names"),
        ("extra", "private_rng_seed"),
    ],
)
def test_semantic_feature_rejects_definition_drift(field: str, value: object) -> None:
    payload: dict[str, object] = dict(FINITE_FEATURE_REGISTRY[0].to_payload())
    payload[field] = value
    with pytest.raises(SemanticFeatureError):
        SemanticFeatureDefinition.from_payload(payload)


@pytest.mark.parametrize("value", [True, 1.0, -1, float("nan"), float("inf"), "opaque-id", {}, []])
def test_semantic_count_rejects_wrong_type_or_range(value: object) -> None:
    with pytest.raises(SemanticFeatureError):
        SemanticFeatureValue(FINITE_FEATURE_REGISTRY[0], cast(int, value))


@pytest.mark.parametrize(
    "field",
    ["schema_version", "registry_version", "actor_id", "request_id", "observation_hash", "extra"],
)
def test_semantic_observation_rejects_shape_version_and_binding_drift(field: str) -> None:
    _, context = _finite_context()
    payload: dict[str, object] = dict(SemanticObservation.from_context(context).to_payload())
    payload[field] = "drift"
    with pytest.raises(SemanticFeatureError):
        SemanticObservation.from_payload(payload, context=context)


@pytest.mark.parametrize("change", ["empty", "duplicate", "value", "unknown", "missing-definition"])
def test_semantic_observation_rejects_feature_drift(change: str) -> None:
    _, context = _finite_context()
    payload = SemanticObservation.from_context(context).to_payload()
    if change == "empty":
        payload["features"] = []
    elif change == "duplicate":
        payload["features"].append(payload["features"][0])
    elif change == "value":
        payload["features"][0]["value"] += 1
    elif change == "unknown":
        payload["features"][0]["definition"]["feature_id"] = "faction-name"
    else:
        del cast(dict[str, object], payload["features"][0])["definition"]
    with pytest.raises(SemanticFeatureError):
        SemanticObservation.from_payload(payload, context=context)


@pytest.mark.parametrize("change", ["feature-id", "source", "value", "descriptors", "extra"])
def test_semantic_training_join_rejects_inconsistent_legacy_inputs(change: str) -> None:
    _, context, row = _training_fixture()
    feature = row.input_features[0]
    if change == "feature-id":
        feature = replace(feature, feature_id="opaque-token")
    elif change == "source":
        feature = replace(feature, source_kind=TrainingFeatureSourceKind.BOARD_STATE)
    elif change == "value":
        feature = replace(feature, value=cast(int, feature.value) + 1)
    elif change == "descriptors":
        feature = replace(feature, source_descriptor_ids=("private-source",))
    features: tuple[TrainingFeature, ...] = () if change == "empty" else (feature,)
    if change == "extra":
        features += (replace(feature, feature_id="display-name"),)
    drifted = replace(row, input_features=features)
    link = FiniteTrainingCandidateLink.from_row(drifted, context=context)
    with pytest.raises(SemanticFeatureError):
        FiniteTrainingObservation.from_link(link, row=drifted, context=context)


@pytest.mark.parametrize("field", ["schema_version", "training_candidate_link_hash", "extra"])
def test_semantic_training_loader_rejects_link_drift(field: str) -> None:
    _, context, row = _training_fixture()
    link = FiniteTrainingCandidateLink.from_row(row, context=context)
    semantic = FiniteTrainingObservation.from_link(link, row=row, context=context)
    payload: dict[str, object] = dict(semantic.to_payload())
    payload[field] = "0" * 64
    with pytest.raises(SemanticFeatureError):
        FiniteTrainingObservation.from_payload(payload, link=link, row=row, context=context)


def test_semantic_inputs_ignore_opaque_option_ids_labels_and_choice_seed() -> None:
    _, context = _finite_context()
    original = SemanticObservation.from_context(context)
    view = context.observation
    request = view["pending_decision"]
    assert request is not None
    request["request_id"] = "different-request"
    for index, option in enumerate(request["options"]):
        option["option_id"] = f"opaque-{index}"
        option["label"] = f"new display name {index}"
        option["payload"] = {"unit_id": f"arbitrary-{index}"}
    changed = SemanticObservation.from_context(
        PlayerDecisionContext.from_view(view, choice_seed=99)
    )
    assert original.model_inputs == changed.model_inputs
    assert original.observation_hash != changed.observation_hash
    assert original.to_payload() != changed.to_payload()


def test_semantic_inputs_ignore_hidden_opponent_selection_and_future_rng() -> None:
    observations: list[SemanticObservation] = []
    for index, selected in enumerate(
        ("fixed:assassination:bring_it_down", "fixed:assassination:cleanse")
    ):
        config = replace(
            canonical_setup_prebattle_smoke_config(), private_rng_seed=f"{index + 11:064x}"
        )
        session = LocalGameSession()
        session.start(config)
        session.advance_until_decision_or_terminal()
        context = PlayerDecisionContext.from_view(
            session.view(viewer_player_id="player-a"), choice_seed=7
        )
        session.submit_viewer_option(
            viewer=ViewerContext.for_player("player-a"),
            request_id=context.request["request_id"],
            option_id=selected,
            result_id="hidden-selection",
        )
        session.advance_until_decision_or_terminal()
        other = PlayerDecisionContext.from_view(
            session.view(viewer_player_id="player-b"), choice_seed=9
        )
        observations.append(SemanticObservation.from_context(other))
    assert observations[0] == observations[1]


@pytest.mark.parametrize("bad", [[], ("bad",)])
def test_semantic_observation_requires_immutable_typed_features(bad: object) -> None:
    _, context = _finite_context()
    original = SemanticObservation.from_context(context)
    with pytest.raises(SemanticFeatureError):
        replace(original, features=cast(tuple[SemanticFeatureValue, ...], bad))


def test_finite_accepted_transition_reproduces_commit_without_mutating_inputs() -> None:
    origin, _ = _finite_context()
    session, context, row = _training_fixture()
    before = origin.to_persistence_payload()
    after = session.to_persistence_payload()
    link = FiniteTrainingCandidateLink.from_row(row, context=context)
    transition = FiniteAcceptedTransition.from_sessions(
        link,
        row=row,
        context=context,
        before=origin,
        after=session,
        trajectory_id="finite-trajectory-v1",
        perspective_player_id="player-b",
    )
    assert transition.accepted_record_start == 0
    assert transition.accepted_record_stop == 1
    assert transition.actor_id == "player-a"
    assert transition.perspective_player_id == "player-b"
    assert transition.authoritative_record_id == row.decision_record_id
    assert transition.authoritative_request_id != context.request["request_id"]
    assert transition.to_payload()["outcome"] == "continuing"
    assert transition.content_hash == payload_digest(transition.to_payload())
    assert (
        FiniteAcceptedTransition.from_payload(
            json.loads(canonical_json(transition.to_payload())),
            link=link,
            row=row,
            context=context,
            before=origin,
            after=session,
            trajectory_id="finite-trajectory-v1",
            perspective_player_id="player-b",
        )
        == transition
    )
    assert before == origin.to_persistence_payload()
    assert after == session.to_persistence_payload()
    assert row.to_payload() == TrainingRow.from_payload(row.to_payload()).to_payload()


@pytest.mark.parametrize("change", ["record", "after", "context", "perspective", "row"])
def test_finite_transition_rejects_invalid_engine_joins(change: str) -> None:
    origin, _ = _finite_context()
    session, context, row = _training_fixture()
    if change == "record":
        row = replace(row, decision_record_id="decision-record-999999")
    elif change == "after":
        session = origin.fork()
    elif change == "context":
        view = context.observation
        view["battle_round"] += 1
        context = PlayerDecisionContext.from_view(view, choice_seed=7)
    elif change == "row":
        row = replace(row, game_id="different-game")
    link = FiniteTrainingCandidateLink.from_row(row, context=context) if change != "row" else None
    with pytest.raises(TrainingTransitionError):
        FiniteAcceptedTransition.from_sessions(
            cast(FiniteTrainingCandidateLink, link),
            row=row,
            context=context,
            before=origin,
            after=session,
            trajectory_id="finite-trajectory-v1",
            perspective_player_id="outsider" if change == "perspective" else "player-a",
        )


@pytest.mark.parametrize(
    "field",
    [
        "schema_version",
        "time_convention",
        "trajectory_id",
        "accepted_record_start",
        "accepted_record_stop",
        "previous_transition_hash",
        "training_candidate_link_hash",
        "before_checkpoint_hash",
        "after_checkpoint_hash",
        "before_observation_hash",
        "after_observation_hash",
        "actor_id",
        "perspective_player_id",
        "authoritative_record_id",
        "authoritative_request_id",
        "authoritative_option_id",
        "result_id",
        "record_hashes",
        "before_position",
        "after_position",
        "outcome",
        "extra",
    ],
)
def test_finite_transition_loader_rejects_tampered_evidence(field: str) -> None:
    origin, _ = _finite_context()
    session, context, row = _training_fixture()
    link = FiniteTrainingCandidateLink.from_row(row, context=context)
    transition = FiniteAcceptedTransition.from_sessions(
        link,
        row=row,
        context=context,
        before=origin,
        after=session,
        trajectory_id="finite-trajectory-v1",
        perspective_player_id="player-b",
    )
    payload: dict[str, object] = dict(transition.to_payload())
    payload[field] = "tampered"
    with pytest.raises(TrainingTransitionError):
        FiniteAcceptedTransition.from_payload(
            payload,
            link=link,
            row=row,
            context=context,
            before=origin,
            after=session,
            trajectory_id="finite-trajectory-v1",
            perspective_player_id="player-b",
        )


def test_finite_transition_links_consecutive_actors_and_rejects_gaps() -> None:
    origin, _ = _finite_context()
    session, context, row = _training_fixture()
    first_link = FiniteTrainingCandidateLink.from_row(row, context=context)
    first = FiniteAcceptedTransition.from_sessions(
        first_link,
        row=row,
        context=context,
        before=origin,
        after=session,
        trajectory_id="consecutive-trajectory-v1",
        perspective_player_id="player-a",
    )
    middle = session.fork()
    other = PlayerDecisionContext.from_view(
        session.view(viewer_player_id="player-b"), choice_seed=9
    )
    candidates = FiniteCandidateSet.from_context(other)
    status = session.submit_viewer_option(
        viewer=ViewerContext.for_player("player-b"),
        request_id=other.request["request_id"],
        option_id=candidates.candidate_ids[-1],
        result_id="second-transition",
    )
    if status.status_kind is LifecycleStatusKind.ADVANCED:
        session.advance_until_decision_or_terminal()
    second_row = replace(
        row,
        row_id="second-row",
        chosen_action_id=candidates.candidate_ids[-1],
        decision_record_id=session.lifecycle.decision_controller.records[
            middle.decision_record_count()
        ].record_id,
        input_features=(
            replace(
                row.input_features[0],
                value=len(candidates.candidates),
                source_descriptor_ids=("decision:" + other.route.decision_type,),
            ),
        ),
        legal_action_mask=tuple(True for _ in candidates.candidates),
    )
    second_link = FiniteTrainingCandidateLink.from_row(second_row, context=other)
    second = FiniteAcceptedTransition.from_sessions(
        second_link,
        row=second_row,
        context=other,
        before=middle,
        after=session,
        trajectory_id="consecutive-trajectory-v1",
        perspective_player_id="player-a",
        previous=first,
    )
    assert second.actor_id != first.actor_id
    assert second.accepted_record_start == first.accepted_record_stop
    assert second.accepted_record_stop == second.accepted_record_start + len(
        second.to_payload()["record_hashes"]
    )
    assert second.to_payload()["previous_transition_hash"] == first.content_hash
    assert (
        second.to_payload()["origin_checkpoint_hash"]
        == first.to_payload()["before_checkpoint_hash"]
    )
    assert (
        FiniteAcceptedTransition.from_payload(
            second.to_payload(),
            link=second_link,
            row=second_row,
            context=other,
            before=middle,
            after=session,
            trajectory_id="consecutive-trajectory-v1",
            perspective_player_id="player-a",
            previous=first,
        )
        == second
    )
    for predecessor in (None, second):
        with pytest.raises(TrainingTransitionError):
            FiniteAcceptedTransition.from_payload(
                second.to_payload(),
                link=second_link,
                row=second_row,
                context=other,
                before=middle,
                after=session,
                trajectory_id="consecutive-trajectory-v1",
                perspective_player_id="player-a",
                previous=predecessor,
            )
    with pytest.raises(TrainingTransitionError, match="continuity"):
        FiniteAcceptedTransition.from_sessions(
            second_link,
            row=second_row,
            context=other,
            before=middle,
            after=session,
            trajectory_id="different-trajectory-v1",
            perspective_player_id="player-a",
            previous=first,
        )
    detached = second.to_payload()
    detached["record_hashes"].clear()
    detached["before_position"]["battle_round"] = 999
    assert second.to_payload()["record_hashes"]
    assert second.to_payload()["before_position"]["battle_round"] != 999
    with pytest.raises(FrozenInstanceError):
        second._evidence_json = "{}"  # type: ignore[misc]
    assert (
        ReplayRunner.from_payload(session.replay_artifact(artifact_id="transition-chain"))
        .run()
        .reproduced_exactly
    )


def test_finite_transition_rejects_a_record_without_engine_application() -> None:
    origin, context = _finite_context()
    _, _, row = _training_fixture()
    recorded = origin.fork()
    request = recorded.lifecycle.pending_decision_request()
    assert request is not None
    # A structural DecisionRecord is deliberately insufficient evidence. This
    # invokes no engine applier; ordinary re-execution must reject the join.
    result = DecisionResult.for_request(
        result_id="record-only",
        request=request,
        selected_option_id=row.chosen_action_id,
    )
    record = recorded.lifecycle.decision_controller.submit_result(result)
    row = replace(row, decision_record_id=record.record_id)
    link = FiniteTrainingCandidateLink.from_row(row, context=context)
    assert link.chosen_action_id == row.chosen_action_id
    with pytest.raises(TrainingTransitionError):
        FiniteAcceptedTransition.from_sessions(
            link,
            row=row,
            context=context,
            before=origin,
            after=recorded,
            trajectory_id="record-only-v1",
            perspective_player_id="player-a",
        )


@pytest.mark.parametrize("value", [True, 1.0, -1, None])
def test_finite_transition_rejects_lossy_temporal_indices(value: object) -> None:
    origin, _ = _finite_context()
    session, context, row = _training_fixture()
    link = FiniteTrainingCandidateLink.from_row(row, context=context)
    transition = FiniteAcceptedTransition.from_sessions(
        link,
        row=row,
        context=context,
        before=origin,
        after=session,
        trajectory_id="finite-trajectory-v1",
        perspective_player_id="player-a",
    )
    payload: dict[str, object] = dict(transition.to_payload())
    payload["accepted_record_stop"] = value
    with pytest.raises(TrainingTransitionError):
        FiniteAcceptedTransition.from_payload(
            payload,
            link=link,
            row=row,
            context=context,
            before=origin,
            after=session,
            trajectory_id="finite-trajectory-v1",
            perspective_player_id="player-a",
        )


def test_finite_transition_reproduces_an_ordinary_terminal_boundary() -> None:
    # This compact canonical configuration uses Command/Shooting/Fight phases. It
    # verifies a boundary contract; it is not a competitive full-game workload.
    session = LocalGameSession()
    compact = _compact_terminal_config(game_id="finite-transition-terminal")
    config = replace(
        compact,
        ruleset_descriptor=replace(
            compact.ruleset_descriptor,
            descriptor_hash="",
            battle_phase_sequence=BattlePhaseSequenceDescriptor(
                phases=(BattlePhaseKind.COMMAND, BattlePhaseKind.SHOOTING, BattlePhaseKind.FIGHT)
            ),
        ),
    )
    session.start(config)
    status = session.advance_until_decision_or_terminal()
    last_finite: tuple[LocalGameSession, FiniteCandidateSet, str, PlayerDecisionContext] | None = (
        None
    )
    for index in range(100):
        request = status.decision_request
        assert request is not None
        assert request.actor_id is not None
        view = session.view(viewer_player_id=request.actor_id)
        context = PlayerDecisionContext.from_view(view, choice_seed=7)
        if request.is_parameterized_submission_request():
            assert request.decision_type == "submit_deployment_placement"
            status = session.submit_viewer_parameterized_payload(
                viewer=ViewerContext.for_player(request.actor_id),
                request_id=context.request["request_id"],
                payload=_deployment_payload_from_proposal(view["pending_proposal"]),
                result_id=f"terminal-placement-{index}",
            )
        else:
            origin = session.fork()
            candidates = FiniteCandidateSet.from_context(context)
            chosen = _terminal_progress_option_id(cast(dict[str, JsonValue], context.request))
            assert chosen in candidates.candidate_ids
            last_finite = origin, candidates, chosen, context
            status = session.submit_viewer_option(
                viewer=ViewerContext.for_player(request.actor_id),
                request_id=context.request["request_id"],
                option_id=chosen,
                result_id=f"terminal-finite-{index}",
            )
        if status.status_kind is LifecycleStatusKind.ADVANCED:
            status = session.advance_until_decision_or_terminal()
        assert status.status_kind in (
            LifecycleStatusKind.WAITING_FOR_DECISION,
            LifecycleStatusKind.TERMINAL,
        )
        if status.status_kind is LifecycleStatusKind.TERMINAL:
            break
    else:
        pytest.fail("Compact terminal fixture exceeded its explicit decision budget.")
    assert not request.is_parameterized_submission_request()
    assert last_finite is not None
    origin, candidates, chosen, context = last_finite
    provenance = PolicyProvenance.from_game_config(
        artifact_id="terminal-contract-v1",
        artifact_kind=PolicyArtifactKind.RANKER,
        game_config=config,
        reward_profile_version="terminal-contract-reward-v1",
    )
    row = TrainingRow(
        row_id="terminal-row",
        game_id=config.game_id,
        decision_record_id=session.lifecycle.decision_controller.records[
            origin.decision_record_count()
        ].record_id,
        policy_artifact_id=provenance.artifact_id,
        policy_provenance=provenance,
        reward_profile_version=provenance.reward_profile_version,
        input_features=(
            TrainingFeature(
                feature_id="decision-option-count",
                source_kind=TrainingFeatureSourceKind.DECISION_CONTEXT,
                value=len(candidates.candidates),
                source_descriptor_ids=("decision:" + context.route.decision_type,),
            ),
        ),
        legal_action_mask=tuple(True for _ in candidates.candidates),
        chosen_action_id=chosen,
        target_value=0.25,
        debug_metadata={"fixture": "compact-terminal-contract"},
    )
    link = FiniteTrainingCandidateLink.from_row(row, context=context)
    transition = FiniteAcceptedTransition.from_sessions(
        link,
        row=row,
        context=context,
        before=origin,
        after=session,
        trajectory_id="terminal-contract-v1",
        perspective_player_id="player-a",
    )
    assert transition.to_payload()["outcome"] == "terminal"
    assert transition.to_payload()["after_position"]["stage"] == "complete"
    assert transition.accepted_record_stop == (
        session.decision_record_count() - origin.decision_record_count()
    )
    assert (
        ReplayRunner.from_payload(session.replay_artifact(artifact_id="finite-terminal"))
        .run()
        .reproduced_exactly
    )


def test_finite_transition_requires_verifying_factories() -> None:
    with pytest.raises(TrainingTransitionError, match="reproduction"):
        FiniteAcceptedTransition()


def test_recorded_invalid_movement_is_outside_parameterized_admission_scope() -> None:
    # Ordinary reachable movement supplies a real recorded rejection. This is an
    # exclusion control, not certification of accepted movement transition evidence.
    compact = _compact_terminal_config(game_id="unsupported-movement-admission")
    session = LocalGameSession()
    session.start(replace(compact, ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh()))
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
                result_id=f"unsupported-prefix-{index}",
            )
        else:
            candidates = FiniteCandidateSet.from_context(context)
            chosen = _terminal_progress_option_id(cast(dict[str, JsonValue], context.request))
            if context.route.decision_type == "select_movement_unit":
                chosen = candidates.candidate_ids[0]
            elif context.route.decision_type == "select_movement_action":
                chosen = "normal_move"
            status = session.submit_viewer_option(
                viewer=ViewerContext.for_player(request.actor_id),
                request_id=context.request["request_id"],
                option_id=chosen,
                result_id=f"unsupported-prefix-{index}",
            )
        if status.status_kind is LifecycleStatusKind.ADVANCED:
            status = session.advance_until_decision_or_terminal()
        assert status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    else:
        pytest.fail("Ordinary setup did not reach movement within the declared budget.")
    proposal = context.observation["pending_proposal"]
    assert isinstance(proposal, dict)
    payload: dict[str, JsonValue] = {
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
    rejected = session.fork()
    status = rejected.submit_viewer_parameterized_payload(
        viewer=ViewerContext.for_player(context.route.actor_id),
        request_id=context.request["request_id"],
        payload=payload,
        result_id="recorded-invalid-movement",
    )
    assert status.status_kind is LifecycleStatusKind.INVALID
    assert rejected.decision_record_count() == session.decision_record_count() + 1
    assert (
        rejected.lifecycle.pending_decision_request()
        != session.lifecycle.pending_decision_request()
    )
    with pytest.raises(TrainingTransitionError, match="Only deployment"):
        ParameterizedAcceptedTransition.from_sessions(
            context.propose(payload),
            context=context,
            before=session,
            after=rejected,
            trajectory_id="unsupported-recorded-attempt",
            perspective_player_id="player-a",
        )
