from __future__ import annotations

import json
from dataclasses import dataclass, replace
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
from warhammer40k_core.ai.deployment_candidates import DeploymentPlacementCandidate
from warhammer40k_core.ai.finite_candidates import FiniteCandidateSet
from warhammer40k_core.ai.parameterized_training import ParameterizedTrainingCandidateLink
from warhammer40k_core.ai.player_policy import PlayerDecisionContext, PolicyAction, payload_digest
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
    MixedEpisodeAdmission,
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
from warhammer40k_core.ai.training_transitions import (
    AcceptedTransition,
    FiniteAcceptedTransition,
    ParameterizedAcceptedTransition,
)
from warhammer40k_core.core.ruleset_descriptor import (
    BattlePhaseKind,
    BattlePhaseSequenceDescriptor,
)
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.game_state import GameConfig
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
        previous: AcceptedTransition | None = None,
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


def step(before: LocalGameSession, chosen: str | None = None) -> AdmissionCase:
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
    return step(session)


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


def target(
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


def admit_target(
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


def local_target(
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


def automatic_attack_case() -> AdmissionCase:
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
            return step(session)
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


@dataclass(frozen=True)
class DeploymentCase:
    first: AdmissionCase
    context: PlayerDecisionContext
    action: PolicyAction
    after: LocalGameSession
    last: AdmissionCase
    transitions: tuple[AcceptedTransition, ...]
    origin: VerifiedEpisodeOrigin

    def proposal_transition(
        self, action: PolicyAction | None = None
    ) -> ParameterizedAcceptedTransition:
        return ParameterizedAcceptedTransition.from_sessions(
            self.action if action is None else action,
            context=self.context,
            before=self.first.after,
            after=self.after,
            trajectory_id="admission-trajectory",
            perspective_player_id="player-a",
            previous=self.transitions[0],
        )

    def episode(self) -> MixedEpisodeAdmission:
        return MixedEpisodeAdmission.from_transitions(
            self.origin,
            transitions=self.transitions,
            final_session=self.last.after,
            episode_end=TargetEpisodeEnd.TRUNCATED,
            stop_reason="setup-slice",
        )


@pytest.fixture(scope="module")
def deployment() -> DeploymentCase:
    session = LocalGameSession()
    session.start(_compact_terminal_config(game_id="parameterized-admission"))
    status = session.advance_until_decision_or_terminal()
    for index in range(30):
        request = status.decision_request
        assert request is not None
        assert request.actor_id is not None
        if request.decision_type == "select_deployment_unit":
            break
        context = PlayerDecisionContext.from_view(
            session.view(viewer_player_id=request.actor_id), choice_seed=7
        )
        status = session.submit_viewer_option(
            viewer=ViewerContext.for_player(request.actor_id),
            request_id=context.request["request_id"],
            option_id=_terminal_progress_option_id(cast(dict[str, JsonValue], context.request)),
            result_id=f"deployment-prefix-{index}",
        )
        if status.status_kind is LifecycleStatusKind.ADVANCED:
            status = session.advance_until_decision_or_terminal()
        assert status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    else:
        pytest.fail("Ordinary setup did not reach deployment within the declared budget.")
    first = step(session)
    pending = first.after.lifecycle.pending_decision_request()
    assert pending is not None
    assert pending.actor_id is not None
    context = PlayerDecisionContext.from_view(
        first.after.view(viewer_player_id=pending.actor_id), choice_seed=7
    )
    action = context.propose(
        _deployment_payload_from_proposal(context.observation["pending_proposal"])
    )
    after = first.after.fork()
    status = after.submit_viewer_parameterized_payload(
        viewer=ViewerContext.for_player(action.actor_id),
        request_id=action.request_id,
        payload=json.loads(cast(str, action.proposal_json)),
        result_id="accepted-deployment",
    )
    if status.status_kind is LifecycleStatusKind.ADVANCED:
        status = after.advance_until_decision_or_terminal()
    assert status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    first_transition = first.transition()
    placement = ParameterizedAcceptedTransition.from_sessions(
        action,
        context=context,
        before=first.after,
        after=after,
        trajectory_id="admission-trajectory",
        perspective_player_id="player-a",
        previous=first_transition,
    )
    last = step(after)
    return DeploymentCase(
        first,
        context,
        action,
        after,
        last,
        (first_transition, placement, last.transition(previous=placement)),
        VerifiedEpisodeOrigin.from_session(first.before, config=first.before.lifecycle.config),
    )


def deployment_row(
    deployment: DeploymentCase, candidate: DeploymentPlacementCandidate
) -> TrainingRow:
    return replace(
        deployment.first.row,
        row_id="deployment-row",
        decision_record_id=deployment.transitions[1].authoritative_record_id,
        chosen_action_id=candidate.candidate_id,
        legal_action_mask=(True,),
        input_features=(
            TrainingFeature(
                feature_id="submitted-deployment-candidate-count",
                source_kind=TrainingFeatureSourceKind.DECISION_CONTEXT,
                value=1,
                source_descriptor_ids=("decision:submit_deployment_placement",),
            ),
        ),
        debug_metadata={"fixture": "accepted-deployment-singleton"},
    )


@dataclass(frozen=True)
class DeploymentTrainingProof:
    row: TrainingRow
    link: ParameterizedTrainingCandidateLink
    episode: MixedEpisodeAdmission
    target: NamedTrainingTarget

    def linked(self, context: PlayerDecisionContext) -> LinkedTrainingTarget:
        return LinkedTrainingTarget.from_link(
            self.link, row=self.row, context=context, target=self.target
        )


@pytest.fixture(scope="module")
def deployment_training(deployment: DeploymentCase) -> DeploymentTrainingProof:
    candidate = DeploymentPlacementCandidate.from_action(
        deployment.action, context=deployment.context
    )
    row = deployment_row(deployment, candidate)
    transition = cast(ParameterizedAcceptedTransition, deployment.transitions[1])
    link = ParameterizedTrainingCandidateLink.from_row(
        row, candidate=candidate, context=deployment.context, transition=transition
    )
    episode = deployment.episode()
    horizon = episode.to_payload()["accepted_record_stop"] - transition.accepted_record_start
    reference = VerifiedLocalReference.from_episode(
        episode,
        transition=transition,
        final_session=deployment.last.after,
        target_id=COMMAND_POINT_BALANCE_TARGET,
        horizon_decisions=horizon,
    )
    target = NamedTrainingTarget(
        target_id=COMMAND_POINT_BALANCE_TARGET,
        meaning=TargetMeaning.LOCAL_REFERENCE,
        perspective_player_id="player-a",
        horizon=TargetHorizon.DECISION_COUNT,
        horizon_decisions=horizon,
        episode_end=TargetEpisodeEnd.TRUNCATED,
        validity=TargetValidity.OBSERVED,
        value=reference.to_payload()["value"],
        value_unit="command_points",
        missing_reason=None,
        producer_id=LOCAL_REFERENCE_PRODUCER,
        evidence_hash=reference.content_hash,
        reward_profile_version=row.reward_profile_version,
    )
    return DeploymentTrainingProof(row, link, episode, target)
