from __future__ import annotations

from dataclasses import replace
from functools import partial

from warhammer40k_core.engine.actions import MissionActionStatus
from warhammer40k_core.engine.boundary_sequencing import boundary_context
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.mission_action_policies import mission_action_policy_for_id
from warhammer40k_core.engine.mission_decisions import request_tactical_secondary_score
from warhammer40k_core.engine.missions import mission_scoring_policies_from_setup
from warhammer40k_core.engine.objective_control import (
    ObjectiveControlRecord,
    ObjectiveControlTiming,
)
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError, LifecycleStatus
from warhammer40k_core.engine.primary_mission_action_resolution import (
    pending_primary_mission_actions_at_turn_end,
    resolve_primary_mission_action_at_turn_end,
)
from warhammer40k_core.engine.primary_mission_choice_opportunities import (
    primary_action_completion_choice_request,
)
from warhammer40k_core.engine.primary_mission_choices import (
    SELECT_PRIMARY_MISSION_CHOICE_DECISION_TYPE,
    consecrate_choice_request_for_designation,
    pending_consecration_designations,
)
from warhammer40k_core.engine.primary_scoring_boundary import score_primary_player_boundary
from warhammer40k_core.engine.primary_scoring_boundary_inventory import (
    required_primary_scoring_boundaries,
)
from warhammer40k_core.engine.primary_scoring_boundary_lifecycle import (
    PRIMARY_SCORING_PENDING_WINDOW_MISSION_TURN_END,
    mark_pending_primary_scoring_boundaries,
)
from warhammer40k_core.engine.primary_scoring_state_evidence import PrimaryScoringBoundaryKind
from warhammer40k_core.engine.runtime_modifiers import RuntimeModifierRegistry
from warhammer40k_core.engine.scoring import (
    SecondaryMissionCardMode,
    SecondaryMissionCardState,
    SecondaryMissionCardStatus,
)
from warhammer40k_core.engine.secondary_scoring_boundary import (
    score_or_record_secondary_card,
    secondary_card_boundary_award,
)
from warhammer40k_core.engine.sequencing import (
    SequencingConflictContext,
    SequencingParticipant,
    SequencingRequirement,
    SequencingRuleOrigin,
)
from warhammer40k_core.engine.timing_rule_candidates import (
    TimingRuleCandidate,
    resolve_timing_rule_candidates,
)
from warhammer40k_core.engine.timing_windows import TimingTriggerKind
from warhammer40k_core.rules.source_packages.warhammer_40000_11th.core_sequencing_2026_09 import (
    END_TURN_MISSION_ORDER_SOURCE_ID,
)

MISSION_TURN_END_STEP = "mission_rules"


def mission_turn_end_context(state: GameState) -> SequencingConflictContext:
    boundary = boundary_context(state, TimingTriggerKind.END_TURN)
    identifier = f"{boundary.conflict_id}:mission-rules"
    return replace(
        boundary,
        conflict_id=identifier,
        timing_window=replace(
            boundary.timing_window,
            window_id=identifier,
            descriptor=replace(
                boundary.timing_window.descriptor,
                descriptor_id=f"{identifier}:descriptor",
                source_rule_id=END_TURN_MISSION_ORDER_SOURCE_ID,
                source_step=MISSION_TURN_END_STEP,
            ),
        ),
    )


def mission_turn_end_record(state: GameState) -> ObjectiveControlRecord:
    records = tuple(
        record
        for record in state.objective_control_records
        if record.battle_round == state.battle_round
        and record.active_player_id == state.active_player_id
        and record.phase == BattlePhase.FIGHT.value
        and record.timing is ObjectiveControlTiming.TURN_END
    )
    if len(records) != 1 or state.current_battle_phase is not BattlePhase.FIGHT:
        raise GameLifecycleError("Mission turn-end sequencing requires its retained boundary.")
    return records[0]


def request_mission_turn_end_rules(
    *,
    state: GameState,
    decisions: DecisionController,
    runtime_modifier_registry: RuntimeModifierRegistry,
) -> LifecycleStatus | None:
    outcome = resolve_timing_rule_candidates(
        decisions=decisions,
        context=mission_turn_end_context(state),
        discover=partial(
            mission_turn_end_candidates,
            state=state,
            decisions=decisions,
            runtime_modifier_registry=runtime_modifier_registry,
        ),
        next_request_id=state.next_decision_request_id,
    )
    if outcome is None:
        return None
    if isinstance(outcome, DecisionRequest):
        decisions.request_decision(outcome)
        if outcome.decision_type == SELECT_PRIMARY_MISSION_CHOICE_DECISION_TYPE:
            decisions.event_log.append(
                "primary_mission_choice_requested",
                {
                    "game_id": state.game_id,
                    "battle_round": state.battle_round,
                    "phase": BattlePhase.FIGHT.value,
                    "request_id": outcome.request_id,
                    "decision_type": outcome.decision_type,
                    "actor_id": outcome.actor_id,
                },
            )
        status = LifecycleStatus.waiting_for_decision(
            stage=state.stage,
            decision_request=outcome,
            payload={"phase_body_status": PRIMARY_SCORING_PENDING_WINDOW_MISSION_TURN_END},
        )
    else:
        status = outcome
    if status.decision_request is not None:
        mark_pending_primary_scoring_boundaries(
            state=state,
            pending_window=PRIMARY_SCORING_PENDING_WINDOW_MISSION_TURN_END,
            pending_decision_request_id=status.decision_request.request_id,
        )
    return status


def mission_turn_end_candidates(
    *,
    state: GameState,
    decisions: DecisionController,
    runtime_modifier_registry: RuntimeModifierRegistry,
) -> tuple[TimingRuleCandidate, ...]:
    """Discover owned mission rules after the source-explicit non-mission stage."""
    record = mission_turn_end_record(state)
    if state.mission_setup is None:
        raise GameLifecycleError("Mission timing requires MissionSetup.")
    policies = mission_scoring_policies_from_setup(state.mission_setup)
    candidates: list[TimingRuleCandidate] = []
    pending_action_ids = {
        action.action_id for action in pending_primary_mission_actions_at_turn_end(state)
    }
    for action in state.mission_action_states:
        if action.action_id not in pending_action_ids and not (
            action.status is MissionActionStatus.COMPLETED
            and action.player_id == state.active_player_id
            and action.completed_battle_round == state.battle_round
            and action.completed_phase == BattlePhase.FIGHT.value
            and primary_action_completion_choice_request(
                state=state,
                decisions=decisions,
                action_id=action.action_id,
                request_id=f"mission-action-template:{action.action_id}",
            )
            is not None
        ):
            continue
        policy = mission_action_policy_for_id(action.mission_action_id)
        candidates.append(
            TimingRuleCandidate(
                participant=SequencingParticipant(
                    participant_id=f"primary-action:{action.action_id}",
                    player_id=action.player_id,
                    source_rule_id=policy.source_id,
                    requirement=SequencingRequirement.MANDATORY,
                    origin=SequencingRuleOrigin.MISSION,
                    payload={"action_id": action.action_id},
                ),
                activate=partial(
                    _resolve_action,
                    state=state,
                    decisions=decisions,
                    record=record,
                    action_id=action.action_id,
                    runtime_modifier_registry=runtime_modifier_registry,
                ),
            )
        )
    for kind, player_id in required_primary_scoring_boundaries(
        policies=policies,
        record=record,
        turn_order=state.turn_order,
    ):
        if kind is not PrimaryScoringBoundaryKind.ORDINARY or any(
            evidence.objective_control_record_id == record.record_id
            and evidence.scoring_boundary_kind is kind
            and evidence.scoring_player_id == player_id
            for evidence in state.primary_scoring_state_evidence_records
        ):
            continue
        primary_policy = policies.policy_for_player(player_id)
        candidates.append(
            TimingRuleCandidate(
                participant=SequencingParticipant(
                    participant_id=f"primary-scoring:{player_id}:{record.record_id}",
                    player_id=player_id,
                    source_rule_id=primary_policy.source_id,
                    requirement=SequencingRequirement.MANDATORY,
                    origin=SequencingRuleOrigin.MISSION,
                    payload={
                        "primary_mission_id": primary_policy.primary_mission_id,
                        "objective_control_record_id": record.record_id,
                    },
                ),
                activate=partial(
                    score_primary_player_boundary,
                    state=state,
                    record=record,
                    scoring_player_id=player_id,
                    end_of_battle=False,
                    event_log=decisions.event_log,
                    runtime_modifier_registry=runtime_modifier_registry,
                ),
            )
        )
    for designation in pending_consecration_designations(state=state):
        template = consecrate_choice_request_for_designation(
            state=state,
            decisions=decisions,
            designation_id=designation.designation_id,
            request_id=f"consecration-template:{designation.designation_id}",
            runtime_modifier_registry=runtime_modifier_registry,
        )
        if template is None:
            raise GameLifecycleError("Pending Consecration lost its mission source.")
        candidates.append(
            TimingRuleCandidate(
                participant=SequencingParticipant(
                    participant_id=f"consecration:{designation.designation_id}",
                    player_id=designation.owner_player_id,
                    source_rule_id=designation.source_rule_id,
                    requirement=SequencingRequirement.OPTIONAL,
                    origin=SequencingRuleOrigin.MISSION,
                    payload={"designation_id": designation.designation_id},
                ),
                activate=partial(
                    consecrate_choice_request_for_designation,
                    state=state,
                    decisions=decisions,
                    designation_id=designation.designation_id,
                    runtime_modifier_registry=runtime_modifier_registry,
                ),
                request_template=template,
            )
        )
    for card in state.secondary_mission_card_states:
        if card.status is not SecondaryMissionCardStatus.ACTIVE:
            continue
        discovered = secondary_card_boundary_award(state=state, record=record, card=card)
        if discovered is None:
            continue
        _, award = discovered
        metadata = award.metadata
        if not isinstance(metadata, dict) or not isinstance(
            metadata.get("scoring_rule_source_ids"), list
        ):
            raise GameLifecycleError("Achieved Secondary mission lacks source authority.")
        source_ids = metadata["scoring_rule_source_ids"]
        if not isinstance(source_ids, list) or not source_ids or not isinstance(source_ids[0], str):
            raise GameLifecycleError("Achieved Secondary mission lacks source authority.")
        candidates.append(
            TimingRuleCandidate(
                participant=SequencingParticipant(
                    participant_id=f"secondary-scoring:{card.player_id}:{card.secondary_mission_id}:{record.record_id}",
                    player_id=card.player_id,
                    source_rule_id=source_ids[0],
                    requirement=(
                        SequencingRequirement.MANDATORY
                        if card.mode is SecondaryMissionCardMode.FIXED
                        else SequencingRequirement.OPTIONAL
                    ),
                    origin=SequencingRuleOrigin.MISSION,
                    payload={
                        "secondary_mission_id": card.secondary_mission_id,
                        "objective_control_record_id": record.record_id,
                        "mode": card.mode.value,
                    },
                ),
                activate=partial(
                    _resolve_secondary, state=state, decisions=decisions, record=record, card=card
                ),
            )
        )
    return tuple(candidates)


def _resolve_action(
    *,
    state: GameState,
    decisions: DecisionController,
    record: ObjectiveControlRecord,
    action_id: str,
    runtime_modifier_registry: RuntimeModifierRegistry,
) -> DecisionRequest | None:
    if any(
        action.action_id == action_id
        for action in pending_primary_mission_actions_at_turn_end(state)
    ):
        resolve_primary_mission_action_at_turn_end(
            state=state,
            decisions=decisions,
            action_id=action_id,
            completed_phase=BattlePhase.FIGHT,
            turn_end_record=record,
            runtime_modifier_registry=runtime_modifier_registry,
        )
    return primary_action_completion_choice_request(
        state=state, decisions=decisions, action_id=action_id
    )


def _resolve_secondary(
    *,
    state: GameState,
    decisions: DecisionController,
    record: ObjectiveControlRecord,
    card: SecondaryMissionCardState,
) -> LifecycleStatus | None:
    score_or_record_secondary_card(state=state, record=record, card=card)
    if card.mode is SecondaryMissionCardMode.FIXED:
        return None
    contexts = tuple(
        context
        for context in state.tactical_secondary_achievement_contexts
        if context.player_id == card.player_id
        and context.secondary_mission_id == card.secondary_mission_id
        and context.card_battle_round == card.battle_round
    )
    if len(contexts) != 1:
        raise GameLifecycleError("Selected Tactical mission requires its achieved rule context.")
    return request_tactical_secondary_score(
        state=state, decisions=decisions, achievement_context=contexts[0]
    )
