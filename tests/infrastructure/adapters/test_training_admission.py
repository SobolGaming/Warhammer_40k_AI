from __future__ import annotations

import json
from dataclasses import FrozenInstanceError, replace
from typing import cast

import pytest

from tests.shared.ai_training_admission_helpers import (
    AdmissionCase,
    DeploymentCase,
    DeploymentTrainingProof,
    TerminalProof,
)
from tests.shared.ai_training_admission_helpers import (
    admit_target as _admit,
)
from tests.shared.ai_training_admission_helpers import (
    automatic_attack_case as _automatic_attack_case,
)
from tests.shared.ai_training_admission_helpers import (
    continuing as continuing,
)
from tests.shared.ai_training_admission_helpers import (
    deployment as deployment,
)
from tests.shared.ai_training_admission_helpers import (
    deployment_training as deployment_training,
)
from tests.shared.ai_training_admission_helpers import (
    local_target as _local_target,
)
from tests.shared.ai_training_admission_helpers import (
    step as _step,
)
from tests.shared.ai_training_admission_helpers import (
    target as _target,
)
from tests.shared.ai_training_admission_helpers import (
    terminal as terminal,
)
from tests.shared.ai_training_admission_helpers import (
    terminal_proofs as terminal_proofs,
)
from tests.shared.category_migration.phase18f_session_commands import (
    _deployment_payload_from_proposal,
    _terminal_progress_option_id,
)
from warhammer40k_core.adapters.access_control import ViewerContext
from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.ai.deployment_candidates import DeploymentPlacementCandidate
from warhammer40k_core.ai.parameterized_training import ParameterizedTrainingCandidateLink
from warhammer40k_core.ai.player_policy import PlayerDecisionContext, PolicyError, payload_digest
from warhammer40k_core.ai.policy_contracts import PolicyProvenanceError, TrainingRow
from warhammer40k_core.ai.training_admission import (
    COMMAND_POINT_BALANCE_TARGET,
    MISSING_TARGET_PRODUCER,
    TERMINAL_TARGET_PRODUCER,
    AdmittedTrainingTarget,
    FiniteEpisodeAdmission,
    MixedEpisodeAdmission,
    TrainingAdmissionError,
    VerifiedEpisodeOrigin,
    VerifiedLocalReference,
)
from warhammer40k_core.ai.training_candidates import (
    FiniteTrainingCandidateLink,
    TrainingCandidateLinkError,
)
from warhammer40k_core.ai.training_targets import (
    LinkedTrainingTarget,
    TargetEpisodeEnd,
    TargetHorizon,
    TargetMeaning,
    TargetValidity,
)
from warhammer40k_core.ai.training_transitions import (
    AcceptedTransition,
    FiniteAcceptedTransition,
    ParameterizedAcceptedTransition,
    TrainingTransitionError,
)
from warhammer40k_core.engine.event_log import JsonValue, canonical_json
from warhammer40k_core.engine.final_scoring import FinalScoringResult
from warhammer40k_core.engine.lifecycle import GameLifecycle
from warhammer40k_core.engine.phase import LifecycleStatusKind


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


def test_parameterized_transition_reproduces_ordinary_viewer_action(
    deployment: DeploymentCase,
) -> None:
    before = deployment.first.after.to_persistence_payload()
    after = deployment.after.to_persistence_payload()
    transition = deployment.proposal_transition()
    payload = transition.to_payload()
    assert payload["schema_version"] == "parameterized-accepted-transition-v1"
    assert payload["proposal_kind"] == "deployment_placement"
    assert payload["viewer_action"]["request_id"] != payload["authoritative_request_id"]
    assert payload["accepted_record_start"] == deployment.transitions[0].accepted_record_stop
    assert payload["accepted_record_stop"] == payload["accepted_record_start"] + len(
        payload["record_hashes"]
    )
    assert (
        ParameterizedAcceptedTransition.from_payload(
            json.loads(canonical_json(payload)),
            action=deployment.action,
            context=deployment.context,
            before=deployment.first.after,
            after=deployment.after,
            trajectory_id="admission-trajectory",
            perspective_player_id="player-a",
            previous=deployment.transitions[0],
        )
        == transition
    )
    payload["viewer_action"]["proposal"] = {}
    payload["record_hashes"].clear()
    assert transition.to_payload()["record_hashes"]
    assert transition.to_payload()["viewer_action"]["proposal"]
    with pytest.raises(FrozenInstanceError):
        transition._evidence_json = "{}"  # type: ignore[misc]
    with pytest.raises(TrainingTransitionError):
        ParameterizedAcceptedTransition()
    assert before == deployment.first.after.to_persistence_payload()
    assert after == deployment.after.to_persistence_payload()


@pytest.mark.parametrize(
    "change",
    [
        "actor",
        "request",
        "observation",
        "context",
        "malformed",
        "stale",
        "ruleset",
        "placement",
        "family",
        "endpoint",
        "predecessor",
    ],
)
def test_parameterized_transition_rejects_drift(deployment: DeploymentCase, change: str) -> None:
    action, context = deployment.action, deployment.context
    after = deployment.after
    previous = deployment.transitions[0]
    if change in ("actor", "request", "observation"):
        action = replace(
            action, **{f"{change}_id" if change != "observation" else "observation_hash": "wrong"}
        )
    elif change in ("malformed", "stale", "ruleset", "placement"):
        proposal = json.loads(cast(str, action.proposal_json))
        if change == "malformed":
            proposal.pop("model_placements")
        elif change == "stale":
            proposal["proposal_request_id"] = "stale-proposal"
        elif change == "ruleset":
            proposal["ruleset_descriptor_hash"] = "0" * 64
        else:
            proposal["model_placements"][0]["pose"]["position"]["x"] += 0.25
        action = context.propose(proposal)
    elif change in ("context", "family"):
        view = context.observation
        if change == "context":
            view["battle_round"] += 1
        else:
            pending = view["pending_decision"]
            assert pending is not None
            assert pending["interaction"] is not None
            pending["interaction"]["proposal_kind"] = "movement"
        context = PlayerDecisionContext.from_view(view, choice_seed=7)
        action = context.propose(json.loads(cast(str, action.proposal_json)))
    elif change == "endpoint":
        after = deployment.last.after
    else:
        previous = deployment.transitions[-1]
    with pytest.raises(TrainingTransitionError):
        ParameterizedAcceptedTransition.from_sessions(
            action,
            context=context,
            before=deployment.first.after,
            after=after,
            trajectory_id="admission-trajectory",
            perspective_player_id="player-a",
            previous=previous,
        )


@pytest.mark.parametrize(
    "field",
    [
        "schema_version",
        "viewer_action",
        "proposal_kind",
        "authoritative_record_id",
        "before_checkpoint_hash",
        "record_hashes",
        "accepted_record_stop",
        "unknown",
    ],
)
def test_parameterized_loader_recomputes_complete_evidence(
    deployment: DeploymentCase, field: str
) -> None:
    payload: dict[str, object] = dict(deployment.proposal_transition().to_payload())
    payload[field] = "drifted"
    with pytest.raises(TrainingTransitionError):
        ParameterizedAcceptedTransition.from_payload(
            payload,
            action=deployment.action,
            context=deployment.context,
            before=deployment.first.after,
            after=deployment.after,
            trajectory_id="admission-trajectory",
            perspective_player_id="player-a",
            previous=deployment.transitions[0],
        )


def test_rule_rejected_deployment_preserves_request_and_allows_ordinary_retry(
    deployment: DeploymentCase,
) -> None:
    before = deployment.first.after
    proposal = json.loads(cast(str, deployment.action.proposal_json))
    for placement in proposal["model_placements"]:
        placement["pose"]["position"]["x"] = -1000.0
    rejected = before.fork()
    status = rejected.submit_viewer_parameterized_payload(
        viewer=ViewerContext.for_player(deployment.action.actor_id),
        request_id=deployment.action.request_id,
        payload=proposal,
        result_id="rejected-placement",
    )
    assert status.status_kind is LifecycleStatusKind.INVALID
    assert isinstance(status.payload, dict)
    assert status.payload["invalid_reason"] == "deployment_placement_invalid"
    assert rejected.to_persistence_payload() == before.to_persistence_payload()
    retry = rejected.lifecycle.pending_decision_request()
    assert retry is not None
    assert retry == before.lifecycle.pending_decision_request()
    with pytest.raises(TrainingTransitionError, match="no new engine decision record"):
        ParameterizedAcceptedTransition.from_sessions(
            deployment.context.propose(proposal),
            context=deployment.context,
            before=before,
            after=rejected,
            trajectory_id="admission-trajectory",
            perspective_player_id="player-a",
            previous=deployment.transitions[0],
        )
    # Deployment rejects before recording; an ordinary legal retry uses the same request.
    assert retry.actor_id is not None
    context = PlayerDecisionContext.from_view(
        rejected.view(viewer_player_id=retry.actor_id), choice_seed=7
    )
    valid = _deployment_payload_from_proposal(context.observation["pending_proposal"])
    accepted = rejected.fork()
    status = accepted.submit_viewer_parameterized_payload(
        viewer=ViewerContext.for_player(retry.actor_id),
        request_id=context.request["request_id"],
        payload=valid,
        result_id="legal-placement-retry",
    )
    if status.status_kind is LifecycleStatusKind.ADVANCED:
        status = accepted.advance_until_decision_or_terminal()
    assert status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    transition = ParameterizedAcceptedTransition.from_sessions(
        context.propose(valid),
        context=context,
        before=rejected,
        after=accepted,
        trajectory_id="retry-slice",
        perspective_player_id="player-a",
    )
    assert transition.accepted_record_start == 0
    assert (
        transition.accepted_record_stop
        == accepted.decision_record_count() - rejected.decision_record_count()
    )
    episode = MixedEpisodeAdmission.from_transitions(
        VerifiedEpisodeOrigin.from_session(rejected, config=rejected.lifecycle.config),
        transitions=(transition,),
        final_session=accepted,
        episode_end=TargetEpisodeEnd.TRUNCATED,
        stop_reason="retry-slice-end",
    )
    assert episode.to_payload()["origin"]["prefix_record_count"] == rejected.decision_record_count()


def test_mixed_episode_reaches_exact_local_reference_horizon(deployment: DeploymentCase) -> None:
    episode = deployment.episode()
    assert episode.to_payload()["schema_version"] == "mixed-episode-admission-v1"
    assert (
        MixedEpisodeAdmission.from_payload(
            episode.to_payload(),
            origin=deployment.origin,
            transitions=deployment.transitions,
            final_session=deployment.last.after,
            episode_end=TargetEpisodeEnd.TRUNCATED,
            stop_reason="setup-slice",
        )
        == episode
    )
    for transition in deployment.transitions:
        horizon = episode.to_payload()["accepted_record_stop"] - transition.accepted_record_start
        reference = VerifiedLocalReference.from_episode(
            episode,
            transition=transition,
            final_session=deployment.last.after,
            target_id=COMMAND_POINT_BALANCE_TARGET,
            horizon_decisions=horizon,
        )
        state = deployment.last.after.lifecycle.state
        assert state is not None
        assert reference.to_payload()["value"] == state.command_point_total("player-a")
        assert reference.to_payload()["accepted_record_start"] == transition.accepted_record_start
        assert (
            VerifiedLocalReference.from_payload(
                reference.to_payload(),
                episode=episode,
                transition=transition,
                final_session=deployment.last.after,
                target_id=COMMAND_POINT_BALANCE_TARGET,
                horizon_decisions=horizon,
            )
            == reference
        )
        with pytest.raises(TrainingAdmissionError, match="horizon"):
            VerifiedLocalReference.from_episode(
                episode,
                transition=transition,
                final_session=deployment.last.after,
                target_id=COMMAND_POINT_BALANCE_TARGET,
                horizon_decisions=horizon + 1,
            )
    with pytest.raises(TrainingAdmissionError):
        FiniteEpisodeAdmission.from_transitions(
            deployment.origin,
            transitions=cast(tuple[FiniteAcceptedTransition, ...], deployment.transitions),
            final_session=deployment.last.after,
            episode_end=TargetEpisodeEnd.TRUNCATED,
            stop_reason="setup-slice",
        )


@pytest.mark.parametrize(
    "change", ["gap", "reverse", "duplicate", "origin", "endpoint", "terminal", "payload"]
)
def test_mixed_episode_rejects_discontinuous_or_drifted_evidence(
    deployment: DeploymentCase, change: str
) -> None:
    transitions, origin, final = deployment.transitions, deployment.origin, deployment.last.after
    end = TargetEpisodeEnd.TRUNCATED
    if change == "gap":
        transitions = transitions[:1] + transitions[2:]
    elif change == "reverse":
        transitions = tuple(reversed(transitions))
    elif change == "duplicate":
        transitions = transitions + transitions[-1:]
    elif change == "origin":
        origin = VerifiedEpisodeOrigin.from_session(
            deployment.first.after, config=deployment.first.after.lifecycle.config
        )
    elif change == "endpoint":
        final = deployment.after
    elif change == "terminal":
        end = TargetEpisodeEnd.TERMINAL
    payload = dict(deployment.episode().to_payload())
    if change == "payload":
        payload["accepted_record_stop"] = 999
    with pytest.raises(TrainingAdmissionError):
        MixedEpisodeAdmission.from_payload(
            payload,
            origin=origin,
            transitions=transitions,
            final_session=final,
            episode_end=end,
            stop_reason="setup-slice",
        )


def test_deployment_candidate_is_detached_actor_view_evidence(deployment: DeploymentCase) -> None:
    context = deployment.context
    candidate = DeploymentPlacementCandidate.from_action(deployment.action, context=context)
    payload = candidate.to_payload()
    assert payload["actor_id"] == context.route.actor_id
    assert payload["request_id"] == context.request["request_id"]
    assert payload["request_id"] != deployment.transitions[1].authoritative_request_id
    assert payload["proposal"] == json.loads(cast(str, deployment.action.proposal_json))
    assert set(payload) == {
        "schema_version",
        "candidate_id",
        "actor_id",
        "request_id",
        "observation_hash",
        "proposal",
    }
    assert candidate.content_hash == payload_digest(payload)
    assert candidate.select(context) == context.propose(payload["proposal"])
    assert (
        DeploymentPlacementCandidate.from_payload(
            json.loads(canonical_json(payload)), context=context
        )
        == candidate
    )
    equivalent = replace(deployment.action, proposal_json=json.dumps(payload["proposal"], indent=4))
    assert DeploymentPlacementCandidate.from_action(equivalent, context=context) == candidate
    payload["proposal"] = {}
    assert candidate.to_payload()["proposal"]
    with pytest.raises(FrozenInstanceError):
        candidate._action_json = "{}"  # type: ignore[misc]
    with pytest.raises(PolicyError):
        DeploymentPlacementCandidate()
    with pytest.raises(PolicyError):
        candidate.select(deployment.last.context)
    with pytest.raises(PolicyError):
        DeploymentPlacementCandidate.from_action(
            replace(deployment.action, actor_id="other-player"), context=context
        )
    with pytest.raises(PolicyError):
        DeploymentPlacementCandidate.from_action(
            deployment.first.context.select_option(deployment.first.row.chosen_action_id),
            context=deployment.first.context,
        )


@pytest.mark.parametrize(
    "field",
    [
        "schema_version",
        "candidate_id",
        "actor_id",
        "request_id",
        "observation_hash",
        "proposal",
        "unknown",
    ],
)
def test_deployment_candidate_loader_rejects_drift(deployment: DeploymentCase, field: str) -> None:
    candidate = DeploymentPlacementCandidate.from_action(
        deployment.action, context=deployment.context
    )
    payload: dict[str, object] = dict(candidate.to_payload())
    payload[field] = "drifted"
    with pytest.raises(PolicyError):
        DeploymentPlacementCandidate.from_payload(payload, context=deployment.context)
    payload = dict(candidate.to_payload())
    payload.pop("candidate_id")
    with pytest.raises(PolicyError):
        DeploymentPlacementCandidate.from_payload(payload, context=deployment.context)


def test_accepted_deployment_row_roundtrips_without_changing_legacy_row(
    deployment: DeploymentCase, deployment_training: DeploymentTrainingProof
) -> None:
    proof = deployment_training
    row, link = proof.row, proof.link
    original = canonical_json(row.to_payload())
    link.require_matches(row, context=deployment.context)
    assert link.chosen_action_id == row.chosen_action_id == link.candidate.candidate_id
    assert link.chosen_action_index == 0
    assert link.to_payload()["accepted_transition_hash"] == deployment.transitions[1].content_hash
    assert (
        ParameterizedTrainingCandidateLink.from_payload(
            json.loads(canonical_json(link.to_payload())),
            row=row,
            context=deployment.context,
            transition=link.transition,
        )
        == link
    )
    assert TrainingRow.from_payload(row.to_payload()).to_payload() == row.to_payload()
    payload = link.to_payload()
    payload["candidate"]["proposal"] = {}
    assert link.to_payload()["candidate"]["proposal"]
    assert canonical_json(row.to_payload()) == original
    assert row.target_value == 0.25
    with pytest.raises(FrozenInstanceError):
        link._evidence_json = "{}"  # type: ignore[misc]
    with pytest.raises(TrainingCandidateLinkError):
        ParameterizedTrainingCandidateLink()


@pytest.mark.parametrize(
    "change",
    [
        "row",
        "record",
        "game",
        "chosen",
        "false-mask",
        "wide-mask",
        "feature",
        "scalar",
        "metadata",
        "context",
        "proposal",
        "malformed",
        "rejected",
        "transition",
    ],
)
def test_deployment_training_row_rejects_drift(
    deployment: DeploymentCase, deployment_training: DeploymentTrainingProof, change: str
) -> None:
    proof = deployment_training
    row, context, candidate, transition = (
        proof.row,
        deployment.context,
        proof.link.candidate,
        proof.link.transition,
    )
    if change == "row":
        row = replace(row, row_id="other-row")
    elif change == "record":
        row = replace(row, decision_record_id=deployment.transitions[0].authoritative_record_id)
    elif change == "game":
        row = replace(row, game_id="other-game")
    elif change == "chosen":
        row = replace(row, chosen_action_id="other-candidate")
    elif change == "false-mask":
        with pytest.raises(PolicyProvenanceError, match="at least one legal"):
            replace(row, legal_action_mask=(False,))
        return
    elif change == "wide-mask":
        row = replace(row, legal_action_mask=(True, True))
    elif change == "feature":
        row = replace(row, input_features=(replace(row.input_features[0], value=2),))
    elif change == "scalar":
        row = replace(row, target_value=0.75)
    elif change == "metadata":
        row = replace(row, debug_metadata={"changed": True})
    elif change == "context":
        view = context.observation
        view["battle_round"] += 1
        context = PlayerDecisionContext.from_view(view, choice_seed=7)
    elif change in ("proposal", "malformed", "rejected"):
        proposal = json.loads(cast(str, deployment.action.proposal_json))
        if change == "malformed":
            proposal.pop("model_placements")
        else:
            proposal["model_placements"][0]["pose"]["position"]["x"] += (
                -1000.0 if change == "rejected" else 0.25
            )
        candidate = DeploymentPlacementCandidate.from_action(
            context.propose(proposal), context=context
        )
        row = replace(row, chosen_action_id=candidate.candidate_id)
    else:
        transition = cast(ParameterizedAcceptedTransition, deployment.transitions[0])
    if change in ("proposal", "malformed", "rejected", "transition"):
        with pytest.raises(TrainingCandidateLinkError):
            ParameterizedTrainingCandidateLink.from_row(
                row, candidate=candidate, context=context, transition=transition
            )
    else:
        with pytest.raises(TrainingCandidateLinkError):
            proof.link.require_matches(row, context=context)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("schema_version", "future"),
        ("row_id", "wrong"),
        ("game_id", "wrong"),
        ("training_row_hash", "0" * 64),
        ("candidate_hash", "0" * 64),
        ("candidate", {}),
        ("chosen_action_id", "wrong"),
        ("chosen_action_index", True),
        ("chosen_action_index", 0.0),
        ("chosen_action_index", 1),
        ("accepted_transition_hash", "0" * 64),
        ("unknown", None),
    ],
)
def test_deployment_training_loader_checks_complete_evidence(
    deployment: DeploymentCase,
    deployment_training: DeploymentTrainingProof,
    field: str,
    value: object,
) -> None:
    proof = deployment_training
    payload: dict[str, object] = dict(proof.link.to_payload())
    payload[field] = value
    with pytest.raises(TrainingCandidateLinkError):
        ParameterizedTrainingCandidateLink.from_payload(
            payload, row=proof.row, context=deployment.context, transition=proof.link.transition
        )


def test_deployment_named_and_admitted_targets_roundtrip(
    deployment: DeploymentCase, deployment_training: DeploymentTrainingProof
) -> None:
    proof = deployment_training
    linked = proof.linked(deployment.context)
    assert (
        LinkedTrainingTarget.from_payload(
            linked.to_payload(), link=proof.link, row=proof.row, context=deployment.context
        )
        == linked
    )
    original = deployment.last.after.to_persistence_payload()
    receipt = AdmittedTrainingTarget.from_episode(
        linked,
        episode=proof.episode,
        transition=proof.link.transition,
        link=proof.link,
        row=proof.row,
        context=deployment.context,
        config=deployment.first.before.lifecycle.config,
        reward_profile_version=proof.row.reward_profile_version,
        final_session=deployment.last.after,
    )
    assert receipt.to_payload()["schema_version"] == "mixed-target-admission-v1"
    assert receipt.to_payload()["eligible_for_learning"]
    assert (
        receipt.to_payload()["accepted_record_start"] == proof.link.transition.accepted_record_start
    )
    assert (
        AdmittedTrainingTarget.from_payload(
            receipt.to_payload(),
            linked=linked,
            episode=proof.episode,
            transition=proof.link.transition,
            link=proof.link,
            row=proof.row,
            context=deployment.context,
            config=deployment.first.before.lifecycle.config,
            reward_profile_version=proof.row.reward_profile_version,
            final_session=deployment.last.after,
        )
        == receipt
    )
    assert original == deployment.last.after.to_persistence_payload()
    detached = receipt.to_payload()
    detached["eligible_for_learning"] = False
    with pytest.raises(TrainingAdmissionError):
        AdmittedTrainingTarget.from_payload(
            detached,
            linked=linked,
            episode=proof.episode,
            transition=proof.link.transition,
            link=proof.link,
            row=proof.row,
            context=deployment.context,
            config=deployment.first.before.lifecycle.config,
            reward_profile_version=proof.row.reward_profile_version,
            final_session=deployment.last.after,
        )


@pytest.mark.parametrize(
    "change",
    [
        "horizon",
        "value",
        "perspective",
        "producer",
        "evidence",
        "transition",
        "source",
        "reward",
        "endpoint",
    ],
)
def test_deployment_target_admission_rejects_wrong_joins(
    deployment: DeploymentCase, deployment_training: DeploymentTrainingProof, change: str
) -> None:
    proof = deployment_training
    target = proof.target
    if change == "horizon":
        target = replace(target, horizon_decisions=cast(int, target.horizon_decisions) + 1)
    elif change == "value":
        target = replace(target, value=cast(float, target.value) + 1)
    elif change == "perspective":
        target = replace(target, perspective_player_id="player-b")
    elif change == "producer":
        target = replace(target, producer_id="unverified")
    elif change == "evidence":
        target = replace(target, evidence_hash="0" * 64)
    linked = LinkedTrainingTarget.from_link(
        proof.link, row=proof.row, context=deployment.context, target=target
    )
    config = deployment.first.before.lifecycle.config
    with pytest.raises(TrainingAdmissionError):
        AdmittedTrainingTarget.from_episode(
            linked,
            episode=proof.episode,
            transition=deployment.transitions[0]
            if change == "transition"
            else proof.link.transition,
            link=proof.link,
            row=proof.row,
            context=deployment.context,
            config=replace(config, game_id="wrong-game") if change == "source" else config,
            reward_profile_version="wrong"
            if change == "reward"
            else proof.row.reward_profile_version,
            final_session=deployment.after if change == "endpoint" else deployment.last.after,
        )


def test_deployment_missing_target_is_excluded_and_finite_targets_join_mixed_episode(
    deployment: DeploymentCase, deployment_training: DeploymentTrainingProof
) -> None:
    proof = deployment_training
    missing = replace(
        proof.target,
        validity=TargetValidity.MISSING,
        value=None,
        missing_reason="setup-slice",
        producer_id=MISSING_TARGET_PRODUCER,
        evidence_hash=proof.episode.content_hash,
    )
    finite = deployment.last
    finite_link = FiniteTrainingCandidateLink.from_row(finite.row, context=finite.context)
    for link, row, context, transition in (
        (proof.link, proof.row, deployment.context, proof.link.transition),
        (finite_link, finite.row, finite.context, deployment.transitions[-1]),
    ):
        linked = LinkedTrainingTarget.from_link(link, row=row, context=context, target=missing)
        receipt = AdmittedTrainingTarget.from_episode(
            linked,
            episode=proof.episode,
            transition=transition,
            link=link,
            row=row,
            context=context,
            config=deployment.first.before.lifecycle.config,
            reward_profile_version=row.reward_profile_version,
        )
        assert not receipt.to_payload()["eligible_for_learning"]
        assert receipt.to_payload()["schema_version"] == "mixed-target-admission-v1"


def test_deployment_row_target_survives_ordinary_terminal_continuation(
    deployment: DeploymentCase, deployment_training: DeploymentTrainingProof
) -> None:
    # This compact canonical Command/Fight workload proves target plumbing,
    # not a competitive game or general proposal-family coverage.
    proof = deployment_training
    perspective = next(
        player
        for player in deployment.context.observation["player_ids"]
        if player != deployment.action.actor_id
    )
    selected = ParameterizedAcceptedTransition.from_sessions(
        deployment.action,
        context=deployment.context,
        before=deployment.first.after,
        after=deployment.after,
        trajectory_id="deployment-terminal-target",
        perspective_player_id=perspective,
    )
    transitions: list[AcceptedTransition] = [selected]
    session = deployment.after
    for index in range(100):
        request = session.lifecycle.pending_decision_request()
        assert request is not None
        assert request.actor_id is not None
        context = PlayerDecisionContext.from_view(
            session.view(viewer_player_id=request.actor_id), choice_seed=7
        )
        before = session
        if context.route.proposal_kind is not None:
            proposal = _deployment_payload_from_proposal(context.observation["pending_proposal"])
            session = before.fork()
            status = session.submit_viewer_parameterized_payload(
                viewer=ViewerContext.for_player(context.route.actor_id),
                request_id=context.request["request_id"],
                payload=proposal,
                result_id=f"deployment-target-continuation-{index}",
            )
            if status.status_kind is LifecycleStatusKind.ADVANCED:
                status = session.advance_until_decision_or_terminal()
            next_transition: AcceptedTransition = ParameterizedAcceptedTransition.from_sessions(
                context.propose(proposal),
                context=context,
                before=before,
                after=session,
                trajectory_id="deployment-terminal-target",
                perspective_player_id=perspective,
                previous=transitions[-1],
            )
        else:
            chosen = _terminal_progress_option_id(cast(dict[str, JsonValue], context.request))
            case = _step(before, chosen)
            session = case.after
            next_transition = FiniteAcceptedTransition.from_sessions(
                FiniteTrainingCandidateLink.from_row(case.row, context=context),
                row=case.row,
                context=context,
                before=before,
                after=session,
                trajectory_id="deployment-terminal-target",
                perspective_player_id=perspective,
                previous=transitions[-1],
            )
        transitions.append(next_transition)
        if next_transition.to_payload()["outcome"] == "terminal":
            break
    else:
        pytest.fail("Compact deployment target continuation exceeded its declared budget.")
    episode = MixedEpisodeAdmission.from_transitions(
        VerifiedEpisodeOrigin.from_session(
            deployment.first.after, config=deployment.first.after.lifecycle.config
        ),
        transitions=tuple(transitions),
        final_session=session,
        episode_end=TargetEpisodeEnd.TERMINAL,
    )
    result_payload = episode.to_payload()["final_result"]
    assert result_payload is not None
    result = FinalScoringResult.from_payload(result_payload)
    value = 0.5 if result.is_draw else float(perspective in result.winner_player_ids)
    target = replace(
        proof.target,
        target_id="deployment-terminal-match-utility",
        meaning=TargetMeaning.MATCH_UTILITY,
        perspective_player_id=perspective,
        horizon=TargetHorizon.MATCH_END,
        horizon_decisions=None,
        episode_end=TargetEpisodeEnd.TERMINAL,
        value=value,
        value_unit="unit_interval",
        producer_id=TERMINAL_TARGET_PRODUCER,
        evidence_hash=payload_digest(result_payload),
    )
    link = ParameterizedTrainingCandidateLink.from_row(
        proof.row, candidate=proof.link.candidate, context=deployment.context, transition=selected
    )
    linked = LinkedTrainingTarget.from_link(
        link, row=proof.row, context=deployment.context, target=target
    )
    receipt = AdmittedTrainingTarget.from_episode(
        linked,
        episode=episode,
        transition=selected,
        link=link,
        row=proof.row,
        context=deployment.context,
        config=deployment.first.before.lifecycle.config,
        reward_profile_version=proof.row.reward_profile_version,
    )
    assert selected.actor_id != selected.perspective_player_id == target.perspective_player_id
    assert receipt.to_payload()["eligible_for_learning"]
    assert (
        receipt.to_payload()["accepted_record_stop"] == episode.to_payload()["accepted_record_stop"]
    )


def test_deployment_candidate_rejects_untyped_context(deployment: DeploymentCase) -> None:
    candidate = DeploymentPlacementCandidate.from_action(
        deployment.action, context=deployment.context
    )
    invalid = cast(PlayerDecisionContext, None)
    with pytest.raises(PolicyError, match="typed player context"):
        candidate.select(invalid)
    with pytest.raises(PolicyError, match="typed player context"):
        DeploymentPlacementCandidate.from_payload(candidate.to_payload(), context=invalid)


def test_deployment_row_mask_rejects_numeric_booleans(
    deployment_training: DeploymentTrainingProof,
) -> None:
    with pytest.raises(PolicyProvenanceError, match="bool"):
        replace(deployment_training.row, legal_action_mask=cast(tuple[bool, ...], (1,)))
