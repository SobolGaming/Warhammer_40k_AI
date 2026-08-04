from __future__ import annotations

from dataclasses import dataclass
from typing import cast

from warhammer40k_core.core.ruleset_descriptor import BattlePhaseKind
from warhammer40k_core.engine.attack_sequence_completion_hooks import (
    AttackSequenceCompletedContext,
)
from warhammer40k_core.engine.catalog_rule_consumption import (
    CATALOG_IR_POST_SHOOT_HIT_TARGET_EFFECT_CONSUMER_ID,
)
from warhammer40k_core.engine.catalog_selected_target_decisions import (
    SelectedTargetGroup,
    post_shoot_group_identity_payload,
    post_shoot_group_participant_id,
)
from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.event_log import validate_json_value
from warhammer40k_core.engine.phase import (
    BattlePhase,
    GameLifecycleError,
    GameLifecycleStage,
    LifecycleStatus,
)
from warhammer40k_core.engine.sequencing import (
    SequencingConflictContext,
    SequencingDecision,
    SequencingDecisionPayload,
    SequencingParticipant,
    create_sequencing_decision_request,
)
from warhammer40k_core.engine.timing_windows import (
    TimingTriggerKind,
    TimingWindow,
    TimingWindowDescriptor,
)


@dataclass(frozen=True, slots=True)
class PostShootSequencingResolution:
    ordered_groups: tuple[SelectedTargetGroup, ...] | None
    pending_status: LifecycleStatus | None

    def __post_init__(self) -> None:
        if (self.ordered_groups is None) == (self.pending_status is None):
            raise GameLifecycleError(
                "Catalog post-shoot sequencing must resolve an order or await a decision."
            )


def resolve_post_shoot_group_order(
    *,
    context: AttackSequenceCompletedContext,
    groups: tuple[SelectedTargetGroup, ...],
) -> PostShootSequencingResolution:
    if len(groups) < 2:
        return PostShootSequencingResolution(
            ordered_groups=groups,
            pending_status=None,
        )
    conflict = _post_shoot_sequencing_conflict(context=context)
    matching_decisions: list[SequencingDecision] = []
    for event in context.decisions.event_log.records:
        if event.event_type != "sequencing_order_resolved":
            continue
        if not isinstance(event.payload, dict):
            raise GameLifecycleError("Sequencing order event payload is malformed.")
        payload = cast(dict[str, object], event.payload)
        if payload.get("conflict_id") != conflict.conflict_id:
            continue
        matching_decisions.append(
            SequencingDecision.from_payload(cast(SequencingDecisionPayload, payload))
        )
    if not matching_decisions:
        return PostShootSequencingResolution(
            ordered_groups=None,
            pending_status=_request_post_shoot_sequencing(
                context=context,
                groups=groups,
                conflict=conflict,
            ),
        )
    if len(matching_decisions) != 1:
        raise GameLifecycleError("Catalog post-shoot sequencing decision is duplicated.")
    decision = matching_decisions[0]
    if decision.timing_window != conflict.timing_window:
        raise GameLifecycleError("Catalog post-shoot sequencing timing window drifted.")
    groups_by_participant_id = {post_shoot_group_participant_id(group): group for group in groups}
    if len(groups_by_participant_id) != len(groups):
        raise GameLifecycleError("Catalog post-shoot sequencing participants are duplicated.")
    if set(decision.ordered_participant_ids) != set(groups_by_participant_id):
        raise GameLifecycleError("Catalog post-shoot sequencing participants drifted.")
    return PostShootSequencingResolution(
        ordered_groups=tuple(
            groups_by_participant_id[participant_id]
            for participant_id in decision.ordered_participant_ids
        ),
        pending_status=None,
    )


def _request_post_shoot_sequencing(
    *,
    context: AttackSequenceCompletedContext,
    groups: tuple[SelectedTargetGroup, ...],
    conflict: SequencingConflictContext,
) -> LifecycleStatus:
    request = _post_shoot_sequencing_request(
        context=context,
        groups=groups,
        conflict=conflict,
    )
    context.decisions.request_decision(request)
    context.decisions.event_log.append(
        "catalog_post_shoot_effect_sequencing_requested",
        validate_json_value(
            {
                "game_id": context.state.game_id,
                "battle_round": context.state.battle_round,
                "phase": BattlePhase.SHOOTING.value,
                "active_player_id": context.state.active_player_id,
                "attack_sequence_id": context.attack_sequence.sequence_id,
                "attack_sequence_completed_event_id": (context.attack_sequence_completed_event_id),
                "request_id": request.request_id,
                "participant_ids": [post_shoot_group_participant_id(group) for group in groups],
                "phase_body_status": "catalog_post_shoot_effect_sequencing_pending",
            }
        ),
    )
    return LifecycleStatus.waiting_for_decision(
        stage=GameLifecycleStage.BATTLE,
        decision_request=request,
        payload=validate_json_value(
            {
                "phase": BattlePhase.SHOOTING.value,
                "battle_round": context.state.battle_round,
                "active_player_id": context.state.active_player_id,
                "pending_request_id": request.request_id,
                "phase_body_status": "catalog_post_shoot_effect_sequencing_pending",
            }
        ),
    )


def _post_shoot_sequencing_request(
    *,
    context: AttackSequenceCompletedContext,
    groups: tuple[SelectedTargetGroup, ...],
    conflict: SequencingConflictContext,
) -> DecisionRequest:
    if len(groups) < 2:
        raise GameLifecycleError("Catalog post-shoot sequencing requires multiple groups.")
    participants = tuple(
        SequencingParticipant(
            participant_id=post_shoot_group_participant_id(group),
            player_id=group.player_id,
            source_rule_id=group.record.definition.source_id,
            payload=post_shoot_group_identity_payload(group),
        )
        for group in groups
    )
    return create_sequencing_decision_request(
        request_id=context.state.next_decision_request_id(),
        context=conflict,
        participants=participants,
    )


def _post_shoot_sequencing_conflict(
    *,
    context: AttackSequenceCompletedContext,
) -> SequencingConflictContext:
    conflict_id = (
        "catalog-post-shoot-order:"
        f"{context.attack_sequence_completed_event_id}:"
        f"{context.attack_sequence.sequence_id}"
    )
    timing_window = TimingWindow(
        window_id=f"timing-window:{conflict_id}",
        descriptor=TimingWindowDescriptor(
            descriptor_id="catalog-post-shoot-hit-target-effect-order",
            trigger_kind=TimingTriggerKind.JUST_AFTER_FRIENDLY_UNIT_HAS_SHOT,
            source_rule_id=CATALOG_IR_POST_SHOOT_HIT_TARGET_EFFECT_CONSUMER_ID,
            phase=BattlePhaseKind.SHOOTING,
            source_step="attack_sequence_completed",
            metadata=validate_json_value(
                {
                    "attack_sequence_id": context.attack_sequence.sequence_id,
                    "attack_sequence_completed_event_id": (
                        context.attack_sequence_completed_event_id
                    ),
                }
            ),
        ),
        game_id=context.state.game_id,
        battle_round=context.state.battle_round,
        active_player_id=context.state.active_player_id,
        phase=BattlePhaseKind.SHOOTING,
        trigger_event_id=context.attack_sequence_completed_event_id,
    )
    return SequencingConflictContext(
        conflict_id=conflict_id,
        game_id=context.state.game_id,
        timing_window=timing_window,
        player_ids=context.state.player_ids,
        active_player_id=context.state.active_player_id,
    )
