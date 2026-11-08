from __future__ import annotations

import json
from dataclasses import FrozenInstanceError, dataclass, replace
from typing import cast

import pytest

from tests.shared.category_migration.phase18f_session_commands import (
    _compact_terminal_config,
    _deployment_payload_from_proposal,
    _terminal_progress_option_id,
)
from warhammer40k_core.adapters.access_control import ViewerContext
from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.adapters.setup_smoke import canonical_setup_prebattle_smoke_config
from warhammer40k_core.ai.finite_candidates import FiniteCandidateSet
from warhammer40k_core.ai.player_policy import PlayerDecisionContext, payload_digest
from warhammer40k_core.ai.policy_contracts import (
    PolicyArtifactKind,
    PolicyProvenance,
    TrainingFeature,
    TrainingFeatureSourceKind,
    TrainingRow,
)
from warhammer40k_core.ai.training_admission import (
    MISSING_TARGET_PRODUCER,
    TERMINAL_TARGET_PRODUCER,
    AdmittedTrainingTarget,
    FiniteEpisodeAdmission,
    TrainingAdmissionError,
    VerifiedEpisodeOrigin,
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
from warhammer40k_core.ai.training_transitions import FiniteAcceptedTransition
from warhammer40k_core.core.ruleset_descriptor import (
    BattlePhaseKind,
    BattlePhaseSequenceDescriptor,
)
from warhammer40k_core.engine.event_log import JsonValue, canonical_json
from warhammer40k_core.engine.game_state import GameConfig
from warhammer40k_core.engine.lifecycle import GameLifecycle
from warhammer40k_core.engine.phase import LifecycleStatusKind


@dataclass(frozen=True)
class AdmissionCase:
    before: LocalGameSession
    after: LocalGameSession
    context: PlayerDecisionContext
    row: TrainingRow

    def transition(
        self,
        row: TrainingRow | None = None,
        *,
        previous: FiniteAcceptedTransition | None = None,
        perspective: str = "player-a",
    ) -> FiniteAcceptedTransition:
        selected = self.row if row is None else row
        return FiniteAcceptedTransition.from_sessions(
            FiniteTrainingCandidateLink.from_row(selected, context=self.context),
            row=selected,
            context=self.context,
            before=self.before,
            after=self.after,
            trajectory_id="admission-trajectory",
            perspective_player_id=perspective,
            previous=previous,
        )

    def episode(
        self,
        *,
        row: TrainingRow | None = None,
        perspective: str = "player-a",
        end: TargetEpisodeEnd = TargetEpisodeEnd.TRUNCATED,
        reason: str | None = "decision-budget",
    ) -> FiniteEpisodeAdmission:
        return FiniteEpisodeAdmission.from_transitions(
            VerifiedEpisodeOrigin.from_session(self.before, config=self.before.lifecycle.config),
            transitions=(self.transition(row, perspective=perspective),),
            final_session=self.after,
            episode_end=end,
            stop_reason=reason,
        )


def _row(
    before: LocalGameSession, after: LocalGameSession, context: PlayerDecisionContext, chosen: str
) -> TrainingRow:
    candidates = FiniteCandidateSet.from_context(context)
    provenance = PolicyProvenance.from_game_config(
        artifact_id="admission-policy",
        artifact_kind=PolicyArtifactKind.RANKER,
        game_config=before.lifecycle.config,
        reward_profile_version="admission-reward-v1",
    )
    return TrainingRow(
        row_id=f"row-{before.decision_record_count()}",
        game_id=before.lifecycle.config.game_id,
        decision_record_id=after.lifecycle.decision_controller.records[
            before.decision_record_count()
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
        debug_metadata={},
    )


def _step(before: LocalGameSession, chosen: str | None = None) -> AdmissionCase:
    request = before.lifecycle.pending_decision_request()
    assert request is not None
    assert request.actor_id is not None
    context = PlayerDecisionContext.from_view(
        before.view(viewer_player_id=request.actor_id), choice_seed=7
    )
    chosen = FiniteCandidateSet.from_context(context).candidate_ids[0] if chosen is None else chosen
    after = before.fork()
    status = after.submit_viewer_option(
        viewer=ViewerContext.for_player(request.actor_id),
        request_id=context.request["request_id"],
        option_id=chosen,
        result_id=f"admission-{before.decision_record_count()}",
    )
    if status.status_kind is LifecycleStatusKind.ADVANCED:
        status = after.advance_until_decision_or_terminal()
    assert status.status_kind in (
        LifecycleStatusKind.WAITING_FOR_DECISION,
        LifecycleStatusKind.TERMINAL,
    )
    return AdmissionCase(before, after, context, _row(before, after, context, chosen))


@pytest.fixture(scope="module")
def continuing() -> AdmissionCase:
    session = LocalGameSession()
    session.start(canonical_setup_prebattle_smoke_config())
    session.advance_until_decision_or_terminal()
    return _step(session)


@pytest.fixture(scope="module")
def terminal() -> AdmissionCase:
    compact = _compact_terminal_config(game_id="admission-terminal")
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
    session = LocalGameSession()
    session.start(config)
    status = session.advance_until_decision_or_terminal()
    for index in range(100):
        request = status.decision_request
        assert request is not None
        assert request.actor_id is not None
        view = session.view(viewer_player_id=request.actor_id)
        if request.is_parameterized_submission_request():
            assert request.decision_type == "submit_deployment_placement"
            pending = view["pending_decision"]
            assert pending is not None
            status = session.submit_viewer_parameterized_payload(
                viewer=ViewerContext.for_player(request.actor_id),
                request_id=pending["request_id"],
                payload=_deployment_payload_from_proposal(view["pending_proposal"]),
                result_id=f"admission-placement-{index}",
            )
        else:
            context = PlayerDecisionContext.from_view(view, choice_seed=7)
            chosen = _terminal_progress_option_id(cast(dict[str, JsonValue], context.request))
            case = _step(session.fork(), chosen)
            session = case.after
            status = session.advance_until_decision_or_terminal()
            if status.status_kind is LifecycleStatusKind.TERMINAL:
                return case
        if status.status_kind is LifecycleStatusKind.ADVANCED:
            status = session.advance_until_decision_or_terminal()
        assert status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    pytest.fail("Terminal admission fixture exceeded its explicit decision budget.")


def _target(
    case: AdmissionCase,
    episode: FiniteEpisodeAdmission,
    *,
    meaning: TargetMeaning = TargetMeaning.MATCH_UTILITY,
    value: float | None = 0.5,
) -> NamedTrainingTarget:
    boundary = episode.to_payload()
    observed = boundary["episode_end"] == "terminal"
    return NamedTrainingTarget(
        target_id="test-match-target",
        meaning=meaning,
        perspective_player_id=boundary["perspective_player_id"],
        horizon=TargetHorizon.MATCH_END,
        horizon_decisions=None,
        episode_end=TargetEpisodeEnd(boundary["episode_end"]),
        validity=TargetValidity.OBSERVED if observed else TargetValidity.MISSING,
        value=value if observed else None,
        value_unit="unit_interval" if meaning is TargetMeaning.MATCH_UTILITY else "victory_points",
        missing_reason=None if observed else boundary["stop_reason"],
        producer_id=TERMINAL_TARGET_PRODUCER if observed else MISSING_TARGET_PRODUCER,
        evidence_hash=payload_digest(boundary["final_result"])
        if observed
        else episode.content_hash,
        reward_profile_version=case.row.reward_profile_version,
    )


def _admit(
    case: AdmissionCase,
    episode: FiniteEpisodeAdmission,
    target: NamedTrainingTarget,
    *,
    row: TrainingRow | None = None,
    config: GameConfig | None = None,
) -> AdmittedTrainingTarget:
    row = case.row if row is None else row
    link = FiniteTrainingCandidateLink.from_row(row, context=case.context)
    return AdmittedTrainingTarget.from_episode(
        LinkedTrainingTarget.from_link(link, row=row, context=case.context, target=target),
        episode=episode,
        transition=case.transition(row, perspective=episode.to_payload()["perspective_player_id"]),
        link=link,
        row=row,
        context=case.context,
        config=case.before.lifecycle.config if config is None else config,
        reward_profile_version=case.row.reward_profile_version,
    )


def test_origin_replays_prefix_and_round_trips_without_mutation(terminal: AdmissionCase) -> None:
    original = terminal.before.to_persistence_payload()
    origin = VerifiedEpisodeOrigin.from_session(
        terminal.before, config=terminal.before.lifecycle.config
    )
    assert origin.to_payload()["prefix_record_count"] > 0
    assert (
        VerifiedEpisodeOrigin.from_payload(
            json.loads(canonical_json(origin.to_payload())),
            session=terminal.before,
            config=terminal.before.lifecycle.config,
        )
        == origin
    )
    detached = origin.to_payload()
    detached["source_identity"]["source_ids"].append("tampered")
    assert detached != origin.to_payload()
    assert origin.content_hash == payload_digest(origin.to_payload())
    assert terminal.before.to_persistence_payload() == original
    with pytest.raises(FrozenInstanceError):
        origin._evidence_json = "{}"  # type: ignore[misc]


@pytest.mark.parametrize("change", ["arbitrary-root", "unreplayed-state", "config"])
def test_origin_rejects_self_consistent_but_unreachable_state(
    continuing: AdmissionCase, change: str
) -> None:
    config = continuing.before.lifecycle.config
    forged = continuing.before.fork()
    if change == "arbitrary-root":
        forged = LocalGameSession(
            lifecycle=GameLifecycle.from_payload(forged.lifecycle.to_payload())
        )
    if change == "config":
        config = replace(config, private_rng_seed="a" * 64)
    else:
        assert forged.lifecycle.state is not None
        forged.lifecycle.state.battle_round += 1
    with pytest.raises(TrainingAdmissionError):
        VerifiedEpisodeOrigin.from_session(forged, config=config)


@pytest.mark.parametrize(
    "kind", [TargetEpisodeEnd.TRUNCATED, TargetEpisodeEnd.ABORTED, TargetEpisodeEnd.UNSUPPORTED]
)
def test_nonterminal_classifications_retain_missing_but_exclude_learning(
    continuing: AdmissionCase, kind: TargetEpisodeEnd
) -> None:
    episode = continuing.episode(end=kind, reason="explicit-stop")
    receipt = _admit(continuing, episode, _target(continuing, episode))
    assert receipt.to_payload()["eligible_for_learning"] is False
    assert episode.to_payload()["final_result"] is None
    assert (
        receipt.to_payload()["accepted_record_stop"] == continuing.transition().accepted_record_stop
    )


def test_contiguous_horizon_counts_engine_records_and_survives_roundtrip(
    continuing: AdmissionCase,
) -> None:
    first = continuing.transition()
    second_case = _step(continuing.after.fork())
    second = second_case.transition(previous=first)
    root = VerifiedEpisodeOrigin.from_session(
        continuing.before, config=continuing.before.lifecycle.config
    )
    episode = FiniteEpisodeAdmission.from_transitions(
        root,
        transitions=(first, second),
        final_session=second_case.after,
        episode_end=TargetEpisodeEnd.TRUNCATED,
        stop_reason="budget",
    )
    assert episode.to_payload()["accepted_record_stop"] == second.accepted_record_stop
    assert second.accepted_record_start == first.accepted_record_stop
    assert (
        FiniteEpisodeAdmission.from_payload(
            episode.to_payload(),
            origin=root,
            transitions=(first, second),
            final_session=second_case.after,
            episode_end=TargetEpisodeEnd.TRUNCATED,
            stop_reason="budget",
        )
        == episode
    )
    assert episode.content_hash == payload_digest(episode.to_payload())


@pytest.mark.parametrize("change", ["duplicate", "reversed", "gap", "endpoint", "root"])
def test_episode_rejects_chain_or_endpoint_drift(continuing: AdmissionCase, change: str) -> None:
    first = continuing.transition()
    second_case = _step(continuing.after.fork())
    second = second_case.transition(previous=first)
    root_session = continuing.before if change != "root" else continuing.after
    root = VerifiedEpisodeOrigin.from_session(root_session, config=root_session.lifecycle.config)
    chains = {"duplicate": (first, first), "reversed": (second, first), "gap": (second,)}
    chain = chains.get(change, (first, second))
    with pytest.raises(TrainingAdmissionError):
        FiniteEpisodeAdmission.from_transitions(
            root,
            transitions=chain,
            final_session=continuing.after if change == "endpoint" else second_case.after,
            episode_end=TargetEpisodeEnd.TRUNCATED,
            stop_reason="budget",
        )


@pytest.mark.parametrize(
    ("end", "reason"),
    [
        (TargetEpisodeEnd.TERMINAL, None),
        (TargetEpisodeEnd.TRUNCATED, None),
        (TargetEpisodeEnd.TRUNCATED, " "),
    ],
)
def test_episode_rejects_false_terminal_and_unexplained_stop(
    continuing: AdmissionCase, end: TargetEpisodeEnd, reason: str | None
) -> None:
    with pytest.raises(TrainingAdmissionError):
        continuing.episode(end=end, reason=reason)


@pytest.mark.parametrize(
    ("meaning", "value"), [(TargetMeaning.MATCH_UTILITY, 0.5), (TargetMeaning.VP_MARGIN, 0.0)]
)
@pytest.mark.parametrize("perspective", ["player-a", "player-b"])
def test_terminal_labels_match_engine_scoring_from_both_perspectives(
    terminal: AdmissionCase, meaning: TargetMeaning, value: float, perspective: str
) -> None:
    episode = terminal.episode(end=TargetEpisodeEnd.TERMINAL, reason=None, perspective=perspective)
    receipt = _admit(terminal, episode, _target(terminal, episode, meaning=meaning, value=value))
    assert receipt.to_payload()["eligible_for_learning"] is True
    assert (
        receipt.to_payload()["accepted_record_stop"] > receipt.to_payload()["accepted_record_start"]
    )
    assert terminal.row.target_value == 0.25


@pytest.mark.parametrize(
    "change", ["value", "producer", "evidence", "perspective", "local-reference"]
)
def test_target_rejects_unverified_value_evidence_producer_and_horizon(
    terminal: AdmissionCase, change: str
) -> None:
    episode = terminal.episode(end=TargetEpisodeEnd.TERMINAL, reason=None)
    target = _target(terminal, episode)
    if change == "value":
        target = replace(target, value=1.0)
    elif change == "producer":
        target = replace(target, producer_id="unauthenticated-producer")
    elif change == "evidence":
        target = replace(target, evidence_hash="a" * 64)
    elif change == "perspective":
        target = replace(target, perspective_player_id="player-b")
    else:
        target = replace(
            target,
            meaning=TargetMeaning.LOCAL_REFERENCE,
            horizon=TargetHorizon.DECISION_COUNT,
            horizon_decisions=1,
        )
    with pytest.raises(TrainingAdmissionError):
        _admit(terminal, episode, target)


@pytest.mark.parametrize("change", ["engine", "catalog", "rules", "reward", "config"])
def test_admission_rejects_source_drift_even_with_rebuilt_valid_links(
    continuing: AdmissionCase, change: str
) -> None:
    row = continuing.row
    provenance = row.policy_provenance
    config = continuing.before.lifecycle.config
    if change == "engine":
        provenance = replace(provenance, engine_version="old-engine")
    elif change == "catalog":
        provenance = replace(
            provenance,
            catalog_packages=(replace(provenance.catalog_packages[0], catalog_hash="f" * 64),),
        )
    elif change == "rules":
        provenance = replace(provenance, ruleset_descriptor_hash="e" * 64)
    elif change == "reward":
        provenance = replace(provenance, reward_profile_version="different-reward")
    else:
        config = replace(config, private_rng_seed="a" * 64)
    row = replace(
        row, policy_provenance=provenance, reward_profile_version=provenance.reward_profile_version
    )
    episode = continuing.episode(row=row)
    target = replace(
        _target(continuing, episode), reward_profile_version=row.reward_profile_version
    )
    # An internally consistent new reward declaration is a separate configuration;
    # admission must be explicitly bound to the experiment's trusted reward profile.
    with pytest.raises(TrainingAdmissionError):
        _admit(continuing, episode, target, row=row, config=config)


@pytest.mark.parametrize("change", ["reason", "producer", "evidence"])
def test_missing_target_must_match_explicit_boundary(
    continuing: AdmissionCase, change: str
) -> None:
    episode = continuing.episode()
    target = _target(continuing, episode)
    if change == "reason":
        target = replace(target, missing_reason="different-stop")
    elif change == "producer":
        target = replace(target, producer_id="unknown-producer")
    else:
        target = replace(target, evidence_hash="a" * 64)
    with pytest.raises(TrainingAdmissionError):
        _admit(continuing, episode, target)


@pytest.mark.parametrize(
    "factory", [VerifiedEpisodeOrigin, FiniteEpisodeAdmission, AdmittedTrainingTarget]
)
def test_admission_factories_are_required(factory: type[object]) -> None:
    with pytest.raises(TrainingAdmissionError):
        factory()


@pytest.mark.parametrize("change", ["unknown", "schema", "build", "index", "hash"])
def test_origin_loader_rejects_resigned_or_unknown_metadata(
    continuing: AdmissionCase, change: str
) -> None:
    config = continuing.before.lifecycle.config
    origin = VerifiedEpisodeOrigin.from_session(continuing.before, config=config)
    payload: dict[str, object] = dict(origin.to_payload())
    field, value = {
        "unknown": ("unexpected", True),
        "schema": ("schema_version", "future"),
        "build": ("engine_build_id", "old-build"),
        "index": ("prefix_record_count", True),
        "hash": ("origin_checkpoint_hash", "f" * 64),
    }[change]
    payload[field] = value
    with pytest.raises(TrainingAdmissionError, match="drifted"):
        VerifiedEpisodeOrigin.from_payload(payload, session=continuing.before, config=config)


@pytest.mark.parametrize("change", ["none", "unknown", "nan", "eligible", "stop"])
def test_target_loader_rechecks_evidence_and_rejects_field_drift(
    continuing: AdmissionCase, change: str
) -> None:
    episode = continuing.episode()
    target = _target(continuing, episode)
    row = continuing.row
    link = FiniteTrainingCandidateLink.from_row(row, context=continuing.context)
    linked = LinkedTrainingTarget.from_link(
        link, row=row, context=continuing.context, target=target
    )
    receipt = _admit(continuing, episode, target)
    kwargs = {
        "linked": linked,
        "episode": episode,
        "transition": continuing.transition(),
        "link": link,
        "row": row,
        "context": continuing.context,
        "config": continuing.before.lifecycle.config,
        "reward_profile_version": row.reward_profile_version,
    }
    assert AdmittedTrainingTarget.from_payload(receipt.to_payload(), **kwargs) == receipt  # type: ignore[arg-type]
    assert receipt.content_hash == payload_digest(receipt.to_payload())
    payload: dict[str, object] = dict(receipt.to_payload())
    if change == "none":
        observed: object = None
    else:
        observed = payload
        key, value = {
            "unknown": ("unknown", 1),
            "nan": ("accepted_record_stop", float("nan")),
            "eligible": ("eligible_for_learning", True),
            "stop": ("accepted_record_stop", 100),
        }[change]
        payload[key] = value
    with pytest.raises(TrainingAdmissionError):
        AdmittedTrainingTarget.from_payload(observed, **kwargs)  # type: ignore[arg-type]


def test_missing_local_horizon_is_unobserved_and_never_eligible(continuing: AdmissionCase) -> None:
    episode = continuing.episode()
    target = replace(
        _target(continuing, episode),
        meaning=TargetMeaning.LOCAL_REFERENCE,
        horizon=TargetHorizon.DECISION_COUNT,
        horizon_decisions=100,
    )
    receipt = _admit(continuing, episode, target)
    assert receipt.to_payload()["accepted_record_stop"] < 100
    assert receipt.to_payload()["eligible_for_learning"] is False


def test_episode_loader_rejects_a_changed_horizon(continuing: AdmissionCase) -> None:
    episode = continuing.episode()
    payload = episode.to_payload()
    payload["accepted_record_stop"] += 1
    root = VerifiedEpisodeOrigin.from_session(
        continuing.before, config=continuing.before.lifecycle.config
    )
    with pytest.raises(TrainingAdmissionError, match="drifted"):
        FiniteEpisodeAdmission.from_payload(
            payload,
            origin=root,
            transitions=(continuing.transition(),),
            final_session=continuing.after,
            episode_end=TargetEpisodeEnd.TRUNCATED,
            stop_reason="decision-budget",
        )


@pytest.mark.parametrize(
    ("end", "reason"),
    [(TargetEpisodeEnd.TRUNCATED, "budget"), (TargetEpisodeEnd.TERMINAL, "budget")],
)
def test_terminal_boundary_cannot_be_reclassified(
    terminal: AdmissionCase, end: TargetEpisodeEnd, reason: str
) -> None:
    with pytest.raises(TrainingAdmissionError):
        terminal.episode(end=end, reason=reason)
