from __future__ import annotations

from collections.abc import Callable, Mapping

# Source event validation is shared with the move-effect owner.
# pyright: reportPrivateUsage=false
from typing import TYPE_CHECKING, cast

from warhammer40k_core.engine import unit_move_completed_hooks as _hooks
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.event_log import EventRecord, JsonValue
from warhammer40k_core.engine.phase import (
    BattlePhase,
    GameLifecycleError,
    LifecycleStatus,
    LifecycleStatusKind,
)
from warhammer40k_core.engine.rule_trigger_state import (
    RuleTrigger,
    RuleTriggerKind,
    complete_rule_trigger,
    observe_rule_trigger,
    release_rule_trigger,
)
from warhammer40k_core.engine.rules_units import rules_unit_view_by_id

if TYPE_CHECKING:
    from warhammer40k_core.engine.abilities import AbilityCatalogIndex
    from warhammer40k_core.engine.battle_shock_hooks import BattleShockHookRegistry
    from warhammer40k_core.engine.game_state import GameState
    from warhammer40k_core.engine.runtime_modifiers import RuntimeModifierRegistry
    from warhammer40k_core.engine.timing_rule_candidates import TimingRuleCandidate


MOVE_COMPLETION_EVENT_TYPES = frozenset(
    {
        "movement_activation_completed",
        "charge_move_completed",
        "reinforcement_unit_arrived",
        "unit_disembarked",
        "triggered_movement_resolved",
        "fight_movement_completed",
        "heroic_intervention_charge_move_completed",
        "catalog_setup_reactive_charge_move_completed",
    }
)
_MOVE_ACTIONS = frozenset(
    {
        "normal_move",
        "advance",
        "fall_back",
        "charge_move",
        "set_up",
        "pile_in",
        "consolidate",
    }
)


def record_move_completion_event(
    *,
    state: GameState,
    decisions: DecisionController,
    event_type: str,
    payload: JsonValue,
) -> EventRecord:
    if event_type not in MOVE_COMPLETION_EVENT_TYPES:
        raise GameLifecycleError("Move-completion recorder requires a supported source event.")
    event = decisions.event_log.append(event_type, payload)
    context = move_trigger_source_context(state=state, decisions=decisions, event=event)
    if context["movement_action"] in _MOVE_ACTIONS:
        observe_rule_trigger(
            decisions=decisions, kind=RuleTriggerKind.MOVE_COMPLETION, context=context
        )
        capture_move_rules(state=state, decisions=decisions, event=event, source_context=context)
    return event


def capture_move_rules(
    *,
    state: GameState,
    decisions: DecisionController,
    event: EventRecord,
    source_context: dict[str, JsonValue],
) -> None:
    from warhammer40k_core.engine.faction_content.unit_move_completed import (
        move_completion_rule_registry,
    )
    from warhammer40k_core.engine.runtime_modifiers import RuntimeModifierRegistry

    if not isinstance(event.payload, dict):
        raise GameLifecycleError("Move rule capture requires its source payload.")
    move_completion_rule_registry().capture_for(
        _hooks.UnitMoveCompletedContext(
            state=state,
            decisions=decisions,
            ruleset_descriptor=state.runtime_ruleset_descriptor(),
            runtime_modifier_registry=RuntimeModifierRegistry.empty(),
            completed_phase=BattlePhase(cast(str, source_context["phase"])),
            trigger_event_id=event.event_id,
            trigger_event_payload=event.payload,
            triggering_unit_instance_id=cast(str, source_context["triggering_unit_instance_id"]),
            triggering_player_id=cast(str, source_context["triggering_player_id"]),
            movement_action=cast(str, source_context["movement_action"]),
        )
    )


def move_trigger_source_context(
    *,
    state: GameState,
    decisions: DecisionController,
    event: EventRecord,
) -> dict[str, JsonValue]:
    payload = event.payload
    if not isinstance(payload, dict):
        raise GameLifecycleError("Move completion requires an object source event.")
    if event.event_type not in MOVE_COMPLETION_EVENT_TYPES:
        raise GameLifecycleError("Move completion has no supported source event.")
    unit_id = _hooks._payload_string(payload, "unit_instance_id")
    action: str
    if event.event_type in {
        "fight_movement_completed",
        "heroic_intervention_charge_move_completed",
        "catalog_setup_reactive_charge_move_completed",
    }:
        from warhammer40k_core.engine.movement_proposals import (
            MOVEMENT_PROPOSAL_DECISION_TYPE,
            MovementProposalRequest,
            ProposalKind,
        )

        records = tuple(
            record
            for record in decisions.records
            if record.request.request_id == payload.get("proposal_request_id")
        )
        if len(records) != 1 or records[0].request.decision_type != MOVEMENT_PROPOSAL_DECISION_TYPE:
            raise GameLifecycleError("Move completion requires its unique proposal decision.")
        proposal = MovementProposalRequest.from_decision_request_payload(records[0].request.payload)
        allowed = (
            {ProposalKind.PILE_IN, ProposalKind.CONSOLIDATE}
            if event.event_type == "fight_movement_completed"
            else {ProposalKind.CHARGE_MOVE}
        )
        if proposal.proposal_kind not in allowed or proposal.unit_instance_id != unit_id:
            raise GameLifecycleError("Move completion proposal kind or unit drift.")
        if "result_id" in payload and payload["result_id"] != records[0].result.result_id:
            raise GameLifecycleError("Move completion proposal result drift.")
        owner = records[0].result.actor_id
        action = proposal.proposal_kind.value
    elif event.event_type == "triggered_movement_resolved":
        from warhammer40k_core.engine.movement_proposals import (
            MOVEMENT_PROPOSAL_DECISION_TYPE,
            MovementProposalRequest,
        )
        from warhammer40k_core.engine.triggered_movement import (
            TriggeredMovementDescriptor,
            TriggeredMovementDescriptorPayload,
            _descriptor_from_proposal_request,
        )

        records = tuple(
            record
            for record in decisions.records
            if record.result.result_id == payload.get("result_id")
        )
        if len(records) != 1 or not isinstance(records[0].request.payload, dict):
            raise GameLifecycleError("Reactive move completion requires its recorded decision.")
        source = records[0].request.payload
        if records[0].request.decision_type == MOVEMENT_PROPOSAL_DECISION_TYPE:
            proposal = MovementProposalRequest.from_decision_request_payload(source)
            if proposal.unit_instance_id != unit_id:
                raise GameLifecycleError("Reactive move completion proposal unit drift.")
            descriptor = _descriptor_from_proposal_request(proposal)
        else:
            descriptor_payload = source.get("descriptor")
            if not isinstance(descriptor_payload, dict):
                raise GameLifecycleError("Reactive move completion lacks its movement descriptor.")
            descriptor = TriggeredMovementDescriptor.from_payload(
                cast(TriggeredMovementDescriptorPayload, descriptor_payload)
            )
        owner = records[0].result.actor_id
        if (
            records[0].request.request_id != payload.get("request_id")
            or descriptor.displacement_kind.value != payload.get("displacement_kind")
            or descriptor.source_rule_id != payload.get("source_rule_id")
            or owner != rules_unit_view_by_id(state=state, unit_instance_id=unit_id).owner_player_id
        ):
            raise GameLifecycleError("Reactive move completion source identity drift.")
        action = (
            "normal_move"
            if descriptor.movement_mode.value == "normal"
            else descriptor.displacement_kind.value
        )
    else:
        owner = _hooks._triggering_player_id_from_move_completion_payload(
            payload, event_type=event.event_type
        )
        action = _hooks._movement_action_from_payload(payload, event_type=event.event_type)
    if payload.get("game_id") != state.game_id or type(payload.get("battle_round")) is not int:
        raise GameLifecycleError("Move completion source game or round drift.")
    phase = _hooks._battle_phase_from_token(payload.get("phase"))
    turn_player_id = _hooks._payload_string(payload, "active_player_id")
    if owner not in state.player_ids or turn_player_id not in state.player_ids:
        raise GameLifecycleError("Move completion source player is invalid.")
    return {
        "game_id": state.game_id,
        "battle_round": payload["battle_round"],
        "phase": phase.value,
        "trigger_event_id": event.event_id,
        "event_type": event.event_type,
        "triggering_unit_instance_id": unit_id,
        "triggering_player_id": owner,
        "turn_player_id": turn_player_id,
        "movement_action": action,
    }


def observe_move_completion(context: _hooks.UnitMoveCompletedContext) -> RuleTrigger:
    decisions = context.decisions
    if decisions is None:
        raise GameLifecycleError("Move completion requires decisions.")
    source = tuple(
        event for event in decisions.event_log.records if event.event_id == context.trigger_event_id
    )
    if len(source) != 1:
        raise GameLifecycleError("Move completion requires its unique source event.")
    payload = move_trigger_source_context(state=context.state, decisions=decisions, event=source[0])
    if (
        payload["triggering_unit_instance_id"] != context.triggering_unit_instance_id
        or payload["triggering_player_id"] != context.triggering_player_id
        or payload["movement_action"] != context.movement_action
        or payload["phase"] != context.completed_phase.value
        or source[0].payload != context.trigger_event_payload
    ):
        raise GameLifecycleError("Move completion source context drift.")
    return observe_rule_trigger(
        decisions=decisions, kind=RuleTriggerKind.MOVE_COMPLETION, context=payload
    )


def move_context_for_trigger(
    *,
    state: GameState,
    decisions: DecisionController,
    trigger: RuleTrigger,
    runtime_modifiers: RuntimeModifierRegistry,
    ability_indexes: Mapping[str, AbilityCatalogIndex],
) -> _hooks.UnitMoveCompletedContext:
    if trigger.kind is not RuleTriggerKind.MOVE_COMPLETION or not isinstance(trigger.context, dict):
        raise GameLifecycleError("Move completion requires its typed trigger.")
    payload = trigger.context
    events = tuple(
        event
        for event in decisions.event_log.records
        if event.event_id == payload.get("trigger_event_id")
    )
    if len(events) != 1 or payload != move_trigger_source_context(
        state=state, decisions=decisions, event=events[0]
    ):
        raise GameLifecycleError("Move completion trigger source authority drift.")
    event = events[0]
    source_index = decisions.event_log.records.index(event)
    observations = tuple(
        (index, record)
        for index, record in enumerate(decisions.event_log.records)
        if record.event_type == "rule_trigger_observed"
        and isinstance(record.payload, dict)
        and record.payload.get("trigger_id") == trigger.trigger_id
    )
    if len(observations) != 1 or observations[0][0] != source_index + 1:
        raise GameLifecycleError("Move trigger must retain its source event's parent timing batch.")
    if not isinstance(event.payload, dict):
        raise GameLifecycleError("Move completion event payload must be an object.")
    return _hooks.UnitMoveCompletedContext(
        state=state,
        decisions=decisions,
        ruleset_descriptor=state.runtime_ruleset_descriptor(),
        runtime_modifier_registry=runtime_modifiers,
        completed_phase=BattlePhase(cast(str, payload["phase"])),
        trigger_event_id=event.event_id,
        trigger_event_payload=event.payload,
        triggering_unit_instance_id=cast(str, payload["triggering_unit_instance_id"]),
        triggering_player_id=cast(str, payload["triggering_player_id"]),
        movement_action=cast(str, payload["movement_action"]),
        ability_indexes_by_player_id=ability_indexes,
    )


def resolve_move_trigger(
    *,
    context: _hooks.UnitMoveCompletedContext,
    trigger: RuleTrigger,
    mortal_wound_hooks: _hooks.UnitMoveCompletedMortalWoundHookRegistry,
    battle_shock_move_hooks: _hooks.UnitMoveCompletedBattleShockHookRegistry | None,
    battle_shock_hooks: BattleShockHookRegistry | None,
    additional_candidates: Callable[
        [_hooks.UnitMoveCompletedContext], tuple[TimingRuleCandidate, ...]
    ]
    | None = None,
) -> LifecycleStatus | None:
    from warhammer40k_core.engine.move_completion_sequencing import (
        move_completion_timing_context,
        resolve_move_completion_now,
    )
    from warhammer40k_core.engine.timing_batch_runtime import timing_batches_for_context

    decisions = context.decisions
    if decisions is None:
        raise GameLifecycleError("Move completion requires decisions.")
    if not release_rule_trigger(decisions=decisions, trigger=trigger):
        from warhammer40k_core.engine.rule_trigger_state import unreleased_rule_trigger_status

        return unreleased_rule_trigger_status(
            decisions=decisions, trigger=trigger, stage=context.state.stage
        )
    if (
        not isinstance(trigger.context, dict)
        or trigger.context["battle_round"] != context.state.battle_round
        or context.state.current_battle_phase is not context.completed_phase
    ):
        raise GameLifecycleError("Move completion escaped its source timing window.")
    status = resolve_move_completion_now(
        additional_candidates=additional_candidates,
        context=context,
        mortal_wound_hooks=mortal_wound_hooks,
        battle_shock_move_hooks=battle_shock_move_hooks,
        battle_shock_hooks=battle_shock_hooks,
    )
    batches = timing_batches_for_context(decisions, move_completion_timing_context(context))
    if status is None or (
        status.status_kind is LifecycleStatusKind.ADVANCED
        and batches
        and batches[-1].current_batch_complete
    ):
        complete_rule_trigger(decisions=decisions, trigger=trigger)
    return status
