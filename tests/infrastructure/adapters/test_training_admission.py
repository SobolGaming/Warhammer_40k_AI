from __future__ import annotations

import json
from dataclasses import FrozenInstanceError, dataclass, replace
from typing import cast

import pytest

from tests.phase13b_shooting_declaration_helpers import _proposal_from_request
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
    COMMAND_POINT_BALANCE_TARGET,
    LOCAL_REFERENCE_PRODUCER,
    MISSING_TARGET_PRODUCER,
    TERMINAL_TARGET_PRODUCER,
    AdmittedTrainingTarget,
    FiniteEpisodeAdmission,
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
from warhammer40k_core.ai.training_transitions import FiniteAcceptedTransition
from warhammer40k_core.core.ruleset_descriptor import (
    BattlePhaseKind,
    BattlePhaseSequenceDescriptor,
)
from warhammer40k_core.engine.event_log import JsonValue, canonical_json, validate_json_value
from warhammer40k_core.engine.game_state import GameConfig
from warhammer40k_core.engine.lifecycle import GameLifecycle
from warhammer40k_core.engine.phase import LifecycleStatusKind
from warhammer40k_core.engine.phases.shooting_model import AvailableWeaponPayload


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


@dataclass(frozen=True)
class TerminalProof:
    transition: FiniteAcceptedTransition
    episode: FiniteEpisodeAdmission


@pytest.fixture(scope="module")
def terminal_proofs(terminal: AdmissionCase) -> tuple[TerminalProof, ...]:
    # Target-only cases share genuinely verified, immutable positive evidence.
    # Origin/loader/boundary tests construct fresh evidence themselves.
    origin = VerifiedEpisodeOrigin.from_session(
        terminal.before, config=terminal.before.lifecycle.config
    )
    proofs: list[TerminalProof] = []
    for perspective in ("player-a", "player-b"):
        transition = terminal.transition(perspective=perspective)
        episode = FiniteEpisodeAdmission.from_transitions(
            origin,
            transitions=(transition,),
            final_session=terminal.after,
            episode_end=TargetEpisodeEnd.TERMINAL,
        )
        proofs.append(TerminalProof(transition, episode))
    return tuple(proofs)


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
            # Prefix choices need ordinary commits, not two full lifecycle
            # reconstructions and a discarded training row per decision.
            before_checkpoint = session.to_persistence_payload()
            status = session.submit_viewer_option(
                viewer=ViewerContext.for_player(request.actor_id),
                request_id=context.request["request_id"],
                option_id=chosen,
                result_id=f"admission-{session.decision_record_count()}",
            )
            if status.status_kind is LifecycleStatusKind.ADVANCED:
                status = session.advance_until_decision_or_terminal()
            if status.status_kind is LifecycleStatusKind.TERMINAL:
                before = LocalGameSession.from_persistence_payload(before_checkpoint)
                return AdmissionCase(
                    before, session, context, _row(before, session, context, chosen)
                )
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
    transition: FiniteAcceptedTransition | None = None,
    final_session: LocalGameSession | None = None,
) -> AdmittedTrainingTarget:
    row = case.row if row is None else row
    link = FiniteTrainingCandidateLink.from_row(row, context=case.context)
    return AdmittedTrainingTarget.from_episode(
        LinkedTrainingTarget.from_link(link, row=row, context=case.context, target=target),
        episode=episode,
        transition=case.transition(row, perspective=episode.to_payload()["perspective_player_id"])
        if transition is None
        else transition,
        link=link,
        row=row,
        context=case.context,
        config=case.before.lifecycle.config if config is None else config,
        reward_profile_version=case.row.reward_profile_version,
        final_session=final_session,
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
    terminal: AdmissionCase,
    terminal_proofs: tuple[TerminalProof, ...],
    meaning: TargetMeaning,
    value: float,
    perspective: str,
) -> None:
    proof = next(p for p in terminal_proofs if p.transition.perspective_player_id == perspective)
    episode = proof.episode
    receipt = _admit(
        terminal,
        episode,
        _target(terminal, episode, meaning=meaning, value=value),
        transition=proof.transition,
    )
    assert receipt.to_payload()["eligible_for_learning"] is True
    assert (
        receipt.to_payload()["accepted_record_stop"] > receipt.to_payload()["accepted_record_start"]
    )
    assert terminal.row.target_value == 0.25


@pytest.mark.parametrize(
    "change", ["value", "producer", "evidence", "perspective", "local-reference"]
)
def test_target_rejects_unverified_value_evidence_producer_and_horizon(
    terminal: AdmissionCase, terminal_proofs: tuple[TerminalProof, ...], change: str
) -> None:
    proof = terminal_proofs[0]
    episode = proof.episode
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
        _admit(terminal, episode, target, transition=proof.transition)


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
    "factory",
    [VerifiedEpisodeOrigin, FiniteEpisodeAdmission, AdmittedTrainingTarget, VerifiedLocalReference],
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


def _local_target(
    case: AdmissionCase,
    episode: FiniteEpisodeAdmission,
    transition: FiniteAcceptedTransition,
    final_session: LocalGameSession,
) -> tuple[NamedTrainingTarget, VerifiedLocalReference]:
    reference = VerifiedLocalReference.from_episode(
        episode,
        transition=transition,
        final_session=final_session,
        target_id=COMMAND_POINT_BALANCE_TARGET,
        horizon_decisions=episode.to_payload()["accepted_record_stop"]
        - transition.accepted_record_start,
    )
    evidence = reference.to_payload()
    target = NamedTrainingTarget(
        target_id=COMMAND_POINT_BALANCE_TARGET,
        meaning=TargetMeaning.LOCAL_REFERENCE,
        perspective_player_id=evidence["perspective_player_id"],
        horizon=TargetHorizon.DECISION_COUNT,
        horizon_decisions=evidence["horizon_decisions"],
        episode_end=TargetEpisodeEnd(episode.to_payload()["episode_end"]),
        validity=TargetValidity.OBSERVED,
        value=evidence["value"],
        value_unit=evidence["value_unit"],
        missing_reason=None,
        producer_id=LOCAL_REFERENCE_PRODUCER,
        evidence_hash=reference.content_hash,
        reward_profile_version=case.row.reward_profile_version,
    )
    return target, reference


@pytest.mark.parametrize("perspective", ["player-a", "player-b"])
def test_local_resource_target_recomputes_terminal_balance_without_mutation(
    terminal: AdmissionCase, terminal_proofs: tuple[TerminalProof, ...], perspective: str
) -> None:
    proof = next(p for p in terminal_proofs if p.transition.perspective_player_id == perspective)
    episode = proof.episode
    transition = proof.transition
    original = terminal.after.to_persistence_payload()
    views = [terminal.after.view(viewer_player_id=player) for player in ("player-a", "player-b")]
    target, reference = _local_target(terminal, episode, transition, terminal.after)
    assert terminal.after.lifecycle.state is not None
    assert target.value == terminal.after.lifecycle.state.command_point_total(perspective)
    assert target.value is not None
    assert target.value > 0
    receipt = _admit(terminal, episode, target, transition=transition, final_session=terminal.after)
    assert receipt.to_payload()["eligible_for_learning"] is True
    assert terminal.row.target_value == 0.25
    assert terminal.after.to_persistence_payload() == original
    assert [terminal.after.view(viewer_player_id=p) for p in ("player-a", "player-b")] == views
    assert reference.to_payload()["time_convention"] == "accepted-engine-records-from-origin-v1"
    detached = reference.to_payload()
    detached["value"] += 1
    assert detached != reference.to_payload()
    with pytest.raises(FrozenInstanceError):
        reference._evidence_json = "{}"  # type: ignore[misc]


def test_local_horizon_is_relative_to_selected_row_in_contiguous_slice(
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
    assert second.accepted_record_start > 0
    for case, transition in ((continuing, first), (second_case, second)):
        target, reference = _local_target(case, episode, transition, second_case.after)
        receipt = _admit(
            case, episode, target, transition=transition, final_session=second_case.after
        )
        assert receipt.to_payload()["eligible_for_learning"] is True
        assert target.horizon_decisions == (
            second.accepted_record_stop - transition.accepted_record_start
        )
        assert reference.to_payload()["accepted_record_start"] == transition.accepted_record_start
        assert target.horizon_decisions is not None
        with pytest.raises(TrainingAdmissionError, match="horizon"):
            _admit(
                case,
                episode,
                replace(target, horizon_decisions=target.horizon_decisions + 1),
                transition=transition,
                final_session=second_case.after,
            )
    first_target, _ = _local_target(continuing, episode, first, second_case.after)
    with pytest.raises(TrainingAdmissionError, match="horizon"):
        _admit(
            continuing,
            episode,
            replace(first_target, horizon_decisions=1),
            final_session=second_case.after,
        )


@pytest.mark.parametrize(
    "change", ["calculator", "unit", "producer", "value", "evidence", "missing-endpoint"]
)
def test_local_target_rejects_unverified_declarations(
    continuing: AdmissionCase, change: str
) -> None:
    episode = continuing.episode()
    target, _ = _local_target(continuing, episode, continuing.transition(), continuing.after)
    final_session: LocalGameSession | None = continuing.after
    if change == "calculator":
        target = replace(target, target_id="unknown-reference-v1")
    elif change == "unit":
        target = replace(target, value_unit="victory_points")
    elif change == "producer":
        target = replace(target, producer_id="external-calculator")
    elif change == "value":
        assert target.value is not None
        target = replace(target, value=target.value + 1)
    elif change == "evidence":
        target = replace(target, evidence_hash="e" * 64)
    else:
        final_session = None
    with pytest.raises(TrainingAdmissionError):
        _admit(continuing, episode, target, final_session=final_session)


@pytest.mark.parametrize("end", [TargetEpisodeEnd.ABORTED, TargetEpisodeEnd.UNSUPPORTED])
def test_local_calculator_excludes_aborted_and_unsupported(
    continuing: AdmissionCase, end: TargetEpisodeEnd
) -> None:
    episode = continuing.episode(end=end)
    with pytest.raises(TrainingAdmissionError, match="unobserved"):
        _local_target(continuing, episode, continuing.transition(), continuing.after)
    missing = replace(
        _target(continuing, episode),
        target_id=COMMAND_POINT_BALANCE_TARGET,
        meaning=TargetMeaning.LOCAL_REFERENCE,
        horizon=TargetHorizon.DECISION_COUNT,
        horizon_decisions=1,
        value_unit="command_points",
    )
    assert _admit(continuing, episode, missing).to_payload()["eligible_for_learning"] is False


@pytest.mark.parametrize("horizon", [0, -1, True, 1.0, None])
def test_local_calculator_requires_exact_positive_integer_horizon(
    continuing: AdmissionCase, horizon: object
) -> None:
    with pytest.raises(TrainingAdmissionError, match="positive decision horizon"):
        VerifiedLocalReference.from_episode(
            continuing.episode(),
            transition=continuing.transition(),
            final_session=continuing.after,
            target_id=COMMAND_POINT_BALANCE_TARGET,
            horizon_decisions=cast(int, horizon),
        )


@pytest.mark.parametrize("change", ["checkpoint", "config", "transition"])
def test_local_calculator_rejects_endpoint_and_membership_drift(
    continuing: AdmissionCase, change: str
) -> None:
    episode = continuing.episode()
    endpoint = continuing.after.fork()
    transition = continuing.transition()
    if change == "checkpoint":
        assert endpoint.lifecycle.state is not None
        endpoint.lifecycle.state.battle_round += 1
    elif change == "config":
        endpoint = LocalGameSession()
        endpoint.start(replace(continuing.before.lifecycle.config, private_rng_seed="b" * 64))
        endpoint.advance_until_decision_or_terminal()
    else:
        transition = _step(continuing.after.fork()).transition()
    with pytest.raises(TrainingAdmissionError, match="drifted"):
        VerifiedLocalReference.from_episode(
            episode,
            transition=transition,
            final_session=endpoint,
            target_id=COMMAND_POINT_BALANCE_TARGET,
            horizon_decisions=1,
        )


@pytest.mark.parametrize("change", ["value", "horizon", "perspective", "unknown", "schema"])
def test_local_evidence_and_receipt_loaders_repeat_calculation(
    continuing: AdmissionCase, change: str
) -> None:
    episode = continuing.episode()
    transition = continuing.transition()
    target, reference = _local_target(continuing, episode, transition, continuing.after)
    reference_args = {
        "episode": episode,
        "transition": transition,
        "final_session": continuing.after,
        "target_id": COMMAND_POINT_BALANCE_TARGET,
        "horizon_decisions": target.horizon_decisions,
    }
    assert (
        VerifiedLocalReference.from_payload(
            json.loads(canonical_json(reference.to_payload())),
            **reference_args,  # type: ignore[arg-type]
        )
        == reference
    )
    payload: dict[str, object] = dict(reference.to_payload())
    field, value = {
        "value": ("value", 999),
        "horizon": ("horizon_decisions", 999),
        "perspective": ("perspective_player_id", "player-b"),
        "unknown": ("unknown", "data"),
        "schema": ("schema_version", "future"),
    }[change]
    payload[field] = value
    with pytest.raises(TrainingAdmissionError, match="drifted"):
        VerifiedLocalReference.from_payload(payload, **reference_args)  # type: ignore[arg-type]
    link = FiniteTrainingCandidateLink.from_row(continuing.row, context=continuing.context)
    linked = LinkedTrainingTarget.from_link(
        link, row=continuing.row, context=continuing.context, target=target
    )
    receipt = _admit(continuing, episode, target, final_session=continuing.after)
    args = {
        "linked": linked,
        "episode": episode,
        "transition": transition,
        "link": link,
        "row": continuing.row,
        "context": continuing.context,
        "config": continuing.before.lifecycle.config,
        "reward_profile_version": continuing.row.reward_profile_version,
        "final_session": continuing.after,
    }
    assert AdmittedTrainingTarget.from_payload(receipt.to_payload(), **args) == receipt  # type: ignore[arg-type]
    # Even a correctly re-signed caller value cannot bypass the calculator.
    forged_target = replace(target, value=999, evidence_hash=payload_digest(payload))
    args["linked"] = LinkedTrainingTarget.from_link(
        link, row=continuing.row, context=continuing.context, target=forged_target
    )
    with pytest.raises(TrainingAdmissionError):
        AdmittedTrainingTarget.from_payload(receipt.to_payload(), **args)  # type: ignore[arg-type]


def test_early_terminal_does_not_shorten_a_local_horizon(
    terminal: AdmissionCase, terminal_proofs: tuple[TerminalProof, ...]
) -> None:
    proof = terminal_proofs[0]
    episode = proof.episode
    target, _ = _local_target(terminal, episode, proof.transition, terminal.after)
    assert target.horizon_decisions is not None
    with pytest.raises(TrainingAdmissionError, match="exact endpoint"):
        _admit(
            terminal,
            episode,
            replace(target, horizon_decisions=target.horizon_decisions + 1),
            transition=proof.transition,
            final_session=terminal.after,
        )


def _automatic_attack_case() -> AdmissionCase:
    # Explicit synthetic open board/close deployment; ordinary startup, placements
    # and shooting only. This is a timing fixture, not source-layout qualification.
    config = _compact_terminal_config(game_id="admission-auto")
    mission = config.mission_setup
    assert mission is not None
    enemy = config.army_muster_requests[1]
    config = replace(
        config,
        ruleset_descriptor=replace(
            config.ruleset_descriptor,
            descriptor_hash="",
            battle_phase_sequence=BattlePhaseSequenceDescriptor(
                phases=(BattlePhaseKind.COMMAND, BattlePhaseKind.SHOOTING, BattlePhaseKind.FIGHT)
            ),
        ),
        army_muster_requests=(
            config.army_muster_requests[0],
            replace(
                enemy,
                unit_selections=(
                    *enemy.unit_selections,
                    replace(enemy.unit_selections[0], unit_selection_id="terminal-unit-c"),
                ),
            ),
        ),
        mission_setup=replace(
            mission,
            deployment_map_id="admission-synthetic-close-zones",
            terrain_layout_id="admission-synthetic-open-board",
            battlefield_layout_id=None,
            terrain_features=(),
            terrain_areas=(),
            objective_terrain_areas=(),
            deployment_zones=tuple(
                replace(
                    zone,
                    shape=replace(
                        zone.shape,
                        polygons=tuple(
                            replace(
                                polygon,
                                vertices=tuple(
                                    replace(
                                        point,
                                        x=point.x + (12 if zone.player_id == "player-a" else -12),
                                    )
                                    for point in polygon.vertices
                                ),
                            )
                            for polygon in zone.shape.polygons
                        ),
                    ),
                )
                for zone in mission.deployment_zones
            ),
        ),
    )
    session = LocalGameSession()
    session.start(config)
    status = session.advance_until_decision_or_terminal()
    for index in range(20):
        request = status.decision_request
        assert request is not None
        assert request.actor_id is not None
        if request.decision_type == "select_resolve_target_unit":
            return _step(session)
        if request.decision_type == "submit_deployment_placement":
            view = session.view(viewer_player_id=request.actor_id)
            pending = view["pending_decision"]
            assert pending is not None
            payload = _deployment_payload_from_proposal(view["pending_proposal"])
            for placement in cast(list[dict[str, JsonValue]], payload["model_placements"]):
                pose = cast(dict[str, JsonValue], placement["pose"])
                position = cast(dict[str, JsonValue], pose["position"])
                if request.actor_id == "player-a":
                    position["x"] = cast(float, position["x"]) + 12
                if placement["unit_instance_id"] == "army-beta:terminal-unit-c":
                    position["y"] = cast(float, position["y"]) + 9
            status = session.submit_viewer_parameterized_payload(
                viewer=ViewerContext.for_player(request.actor_id),
                request_id=pending["request_id"],
                result_id=f"auto-prefix-{index}",
                payload=payload,
            )
        elif request.decision_type == "submit_shooting_declaration":
            proposal = _proposal_from_request(
                request=request, target_unit_id="army-beta:terminal-unit-b"
            )
            first = proposal.declarations[0]
            envelope = cast(dict[str, JsonValue], request.payload)
            offered = cast(dict[str, JsonValue], envelope["proposal_request"])
            weapon = next(
                item
                for item in cast(list[AvailableWeaponPayload], offered["available_weapons"])
                if item["model_instance_id"] != first.attacker_model_instance_id
            )
            second = replace(
                first,
                attacker_model_instance_id=weapon["model_instance_id"],
                weapon_instance_id=weapon["weapon_instance_id"],
                wargear_id=weapon["wargear_id"],
                weapon_profile_id=weapon["weapon_profile_id"],
                target_unit_instance_id="army-beta:terminal-unit-c",
            )
            status = session.submit_parameterized_payload(
                request_id=request.request_id,
                result_id=f"auto-prefix-{index}",
                payload=validate_json_value(
                    replace(proposal, declarations=(first, second)).to_payload()
                ),
            )
        else:
            chosen = {
                "select_shooting_unit": "army-alpha:terminal-unit-a",
                "select_shooting_type": "normal",
            }.get(request.decision_type)
            if chosen is None:
                chosen = _terminal_progress_option_id(
                    cast(dict[str, JsonValue], request.to_payload())
                )
            status = session.submit_option(
                request_id=request.request_id, result_id=f"auto-prefix-{index}", option_id=chosen
            )
        if status.status_kind is LifecycleStatusKind.ADVANCED:
            status = session.advance_until_decision_or_terminal()
        assert status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION, status
    pytest.fail("Automatic attack fixture exceeded its explicit prefix budget.")


def test_local_horizon_counts_automatic_records_and_rejects_interior_boundary() -> None:
    case = _automatic_attack_case()
    transition = case.transition()
    episode = case.episode()
    records = case.after.lifecycle.decision_controller.records[
        case.before.decision_record_count() :
    ]
    assert len(records) == 2
    assert records[1].result.result_id.endswith(":auto-result")
    assert transition.accepted_record_start == 0
    assert transition.accepted_record_stop == 2
    assert episode.to_payload()["origin"]["prefix_record_count"] > 0
    target, reference = _local_target(case, episode, transition, case.after)
    assert target.horizon_decisions == 2
    assert reference.to_payload()["value"] == 1
    assert case.before.lifecycle.state is not None
    assert case.before.lifecycle.state.command_point_total("player-a") == target.value
    assert _admit(case, episode, target, final_session=case.after).to_payload()[
        "eligible_for_learning"
    ]
    for unavailable in (1, 3):
        with pytest.raises(TrainingAdmissionError, match="exact endpoint"):
            _admit(
                case,
                episode,
                replace(target, horizon_decisions=unavailable),
                final_session=case.after,
            )
