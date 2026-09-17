"""Descriptor-driven completion rolls for an optional single-move keyword grant."""

from __future__ import annotations

from functools import partial
from typing import TYPE_CHECKING, cast

from warhammer40k_core.core.dice import (
    DiceExpression,
    DiceRollSpec,
    DiceRollState,
    DiceRollStatePayload,
)
from warhammer40k_core.engine.battle_shock_state import apply_direct_battle_shock_state
from warhammer40k_core.engine.decision_record import DecisionRecord
from warhammer40k_core.engine.dice import DiceRollManager
from warhammer40k_core.engine.event_log import EventLog, EventRecord, JsonValue, validate_json_value
from warhammer40k_core.engine.move_ability_choices import (
    CHOICE_KEY,
    choice_descriptor,
    choice_fields,
    descriptors_for_move,
    movement_ability_keywords,
)
from warhammer40k_core.engine.move_completion_rule_hooks import MoveCompletionRuleBinding
from warhammer40k_core.engine.movement_proposals import (
    MOVEMENT_PROPOSAL_DECISION_TYPE,
    MovementProposalRequest,
)
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.rules_units import rules_unit_view_by_id
from warhammer40k_core.engine.sequencing import SequencingParticipant, SequencingRequirement
from warhammer40k_core.engine.timing_rule_candidates import TimingRuleCandidate
from warhammer40k_core.engine.unit_move_completed_hooks import UnitMoveCompletedContext
from warhammer40k_core.rules.movement_ability import MovementAbilityDescriptor
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    core_super_heavy_walker_2026_09 as source,
)

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState

MOVE_KEYWORD_ROLL_EVENT = "move_keyword_roll_resolved"


def move_keyword_completion_bindings() -> tuple[MoveCompletionRuleBinding, ...]:
    return tuple(
        MoveCompletionRuleBinding(
            hook_id=f"{descriptor.descriptor_id}:completion",
            source_rule_id=descriptor.source_rule_id,
            participants_at_trigger=partial(_participants, descriptor),
            candidates=partial(_candidates, descriptor),
            resume=partial(_resume, descriptor),
        )
        for descriptor in source.movement_abilities()
    )


def completion_choice(
    *,
    state: GameState,
    event: EventRecord,
    decision_records: tuple[DecisionRecord, ...],
) -> dict[str, JsonValue] | None:
    if event.event_type not in {"movement_activation_completed", "triggered_movement_resolved"}:
        return None
    payload = event.payload
    if not isinstance(payload, dict):
        raise GameLifecycleError("Movement keyword completion requires an object event.")
    if event.event_type == "movement_activation_completed" and payload.get(
        "movement_phase_action"
    ) not in {"normal_move", "advance", "fall_back"}:
        return None
    unit_id = payload.get("unit_instance_id")
    if not isinstance(unit_id, str):
        raise GameLifecycleError("Movement completion requires its moving rules unit.")
    view = rules_unit_view_by_id(state=state, unit_instance_id=unit_id)
    if not movement_ability_keywords(view, include_destroyed=True):
        if CHOICE_KEY in payload:
            raise GameLifecycleError("Movement completion has no source for its keyword grant.")
        return None
    records = tuple(
        record
        for record in decision_records
        if record.request.request_id == payload.get("request_id")
        and record.result.result_id == payload.get("result_id")
    )
    if len(records) != 1:
        raise GameLifecycleError("Movement keyword completion lost its original decision.")
    record = records[0]
    if record.request.decision_type == MOVEMENT_PROPOSAL_DECISION_TYPE:
        proposal = MovementProposalRequest.from_decision_request_payload(record.request.payload)
        context = proposal.context
        if not isinstance(context, dict):
            raise GameLifecycleError("Movement keyword completion lost its proposal context.")
        request_id = context.get("selection_request_id", proposal.source_decision_request_id)
        result_id = context.get("selection_result_id", proposal.source_decision_result_id)
        selections = tuple(
            row
            for row in decision_records
            if row.request.request_id == request_id and row.result.result_id == result_id
        )
        if len(selections) != 1:
            raise GameLifecycleError("Movement completion lost its finite selection.")
        record = selections[0]
        if choice_fields(context) != choice_fields(record.result.payload):
            raise GameLifecycleError("Movement keyword completion differs from its finite choice.")
    selection = record.result.payload
    if not isinstance(selection, dict):
        raise GameLifecycleError("Movement completion requires a finite object selection.")
    mode = selection.get("movement_mode")
    is_surge = False
    if isinstance(selection.get("descriptor"), dict):
        movement = cast(dict[str, JsonValue], selection["descriptor"])
        mode = movement.get("movement_mode")
        is_surge = movement.get("movement_kind") == "surge"
    available = descriptors_for_move(
        movement_ability_keywords(view, include_destroyed=True), str(mode), is_surge=is_surge
    )
    fields = choice_fields(selection)
    if bool(fields) != bool(available):
        raise GameLifecycleError("Movement completion optional keyword source or choice drift.")
    if not fields:
        if CHOICE_KEY in payload:
            raise GameLifecycleError("Movement completion invented a keyword choice.")
        return None
    choice = cast(dict[str, JsonValue], fields[CHOICE_KEY])
    if (
        choice_descriptor(choice) not in available
        or choice["unit_instance_id"] != payload.get("unit_instance_id")
        or record.result.actor_id != view.owner_player_id
    ):
        raise GameLifecycleError("Movement keyword completion moving unit drift.")
    record.result.validate_for_request(record.request)
    return choice


def _participants(
    descriptor: MovementAbilityDescriptor, context: UnitMoveCompletedContext
) -> tuple[SequencingParticipant, ...]:
    decisions = context.decisions
    if decisions is None:
        raise GameLifecycleError("Movement completion keyword grant requires decisions.")
    sources = tuple(
        event for event in decisions.event_log.records if event.event_id == context.trigger_event_id
    )
    if len(sources) != 1:
        raise GameLifecycleError("Movement completion keyword grant requires its source event.")
    choice = completion_choice(
        state=context.state, event=sources[0], decision_records=decisions.records
    )
    if (
        choice is None
        or not choice["selected"]
        or choice["descriptor_id"] != descriptor.descriptor_id
    ):
        return ()
    return (
        SequencingParticipant(
            participant_id=f"{descriptor.descriptor_id}:{context.trigger_event_id}:completion",
            player_id=context.triggering_player_id,
            source_rule_id=descriptor.source_rule_id,
            requirement=SequencingRequirement.MANDATORY,
            payload={"trigger_event_id": context.trigger_event_id, CHOICE_KEY: choice},
        ),
    )


def _candidates(
    descriptor: MovementAbilityDescriptor, context: UnitMoveCompletedContext
) -> tuple[TimingRuleCandidate, ...]:
    return tuple(
        candidate
        for participant in _participants(descriptor, context)
        if (candidate := _resume(descriptor, context, participant)) is not None
    )


def _resume(
    descriptor: MovementAbilityDescriptor,
    context: UnitMoveCompletedContext,
    participant: SequencingParticipant,
) -> TimingRuleCandidate | None:
    decisions = context.decisions
    if decisions is None or participant not in _participants(descriptor, context):
        raise GameLifecycleError("Movement keyword completion participant drift.")
    resolved = tuple(
        event
        for event in decisions.event_log.records
        if event.event_type == MOVE_KEYWORD_ROLL_EVENT
        and isinstance(event.payload, dict)
        and event.payload.get("trigger_event_id") == context.trigger_event_id
    )
    if resolved:
        if len(resolved) != 1:
            raise GameLifecycleError("Movement keyword completion roll is duplicated.")
        return None
    return TimingRuleCandidate(
        participant=participant, activate=partial(_resolve, descriptor, context, participant)
    )


def completion_roll_spec(
    descriptor: MovementAbilityDescriptor, *, source_event_id: str, player_id: str
) -> DiceRollSpec:
    return DiceRollSpec(
        expression=DiceExpression(quantity=1, sides=6),
        reason=f"{descriptor.descriptor_id} optional movement keyword completion",
        roll_type=f"move_keyword_completion.{descriptor.descriptor_id}.{source_event_id}",
        actor_id=player_id,
    )


def _resolve(
    descriptor: MovementAbilityDescriptor,
    context: UnitMoveCompletedContext,
    participant: SequencingParticipant,
) -> None:
    state, decisions = context.state, context.decisions
    if decisions is None or not isinstance(participant.payload, dict):
        raise GameLifecycleError("Movement keyword completion requires its participant payload.")
    roll = DiceRollManager(state.game_id, event_log=decisions.event_log).roll(
        completion_roll_spec(
            descriptor,
            source_event_id=context.trigger_event_id,
            player_id=context.triggering_player_id,
        ),
    )
    result_id = f"{participant.participant_id}:result"
    view = rules_unit_view_by_id(state=state, unit_instance_id=context.triggering_unit_instance_id)
    state_update = "not_required"
    if roll.current_total in descriptor.battle_shocked_roll_values and view.alive_models():
        state_update = apply_direct_battle_shock_state(
            state=state,
            player_id=context.triggering_player_id,
            unit_instance_id=view.unit_instance_id,
            source_result_id=result_id,
            battle_round=state.battle_round,
        )
    decisions.event_log.append(
        MOVE_KEYWORD_ROLL_EVENT,
        {
            "game_id": state.game_id,
            "battle_round": state.battle_round,
            "active_player_id": state.active_player_id,
            "phase": context.completed_phase.value,
            "player_id": context.triggering_player_id,
            "unit_instance_id": view.unit_instance_id,
            "source_rule_id": descriptor.source_rule_id,
            "trigger_event_id": context.trigger_event_id,
            "participant_id": participant.participant_id,
            "result_id": result_id,
            CHOICE_KEY: participant.payload[CHOICE_KEY],
            "roll_state": validate_json_value(roll.to_payload()),
            "state_update": state_update,
        },
    )


def validate_completion_roll_event(
    *,
    state: GameState,
    event_records: tuple[EventRecord, ...],
    decision_records: tuple[DecisionRecord, ...],
    event_index: int,
) -> tuple[dict[str, JsonValue], DiceRollState]:
    event = event_records[event_index]
    payload = event.payload
    if (
        event.event_type != MOVE_KEYWORD_ROLL_EVENT
        or not isinstance(payload, dict)
        or set(payload)
        != {
            "game_id",
            "battle_round",
            "active_player_id",
            "phase",
            "player_id",
            "unit_instance_id",
            "source_rule_id",
            "trigger_event_id",
            "participant_id",
            "result_id",
            CHOICE_KEY,
            "roll_state",
            "state_update",
        }
    ):
        raise GameLifecycleError("Movement keyword roll event is invalid.")
    sources = tuple(
        (i, item)
        for i, item in enumerate(event_records[:event_index])
        if item.event_id == payload.get("trigger_event_id")
    )
    if len(sources) != 1:
        raise GameLifecycleError("Movement keyword roll lost its completed move.")
    source_index, source = sources[0]
    choice = completion_choice(state=state, event=source, decision_records=decision_records)
    if choice is None or not choice["selected"] or payload.get(CHOICE_KEY) != choice:
        raise GameLifecycleError("Movement keyword roll lacks a selected finite grant.")
    descriptor = choice_descriptor(choice)
    source_payload = source.payload
    if not isinstance(source_payload, dict):
        raise GameLifecycleError("Movement keyword source payload is invalid.")
    player_id = payload.get("player_id")
    if not isinstance(player_id, str) or player_id not in state.player_ids:
        raise GameLifecycleError("Movement keyword completion player drift.")
    participant_id = f"{descriptor.descriptor_id}:{source.event_id}:completion"
    if (
        payload.get("game_id") != state.game_id
        or payload.get("unit_instance_id") != choice["unit_instance_id"]
        or payload.get("source_rule_id") != descriptor.source_rule_id
        or payload.get("participant_id") != participant_id
        or payload.get("result_id") != f"{participant_id}:result"
        or any(
            payload.get(key) != source_payload.get(key)
            for key in ("battle_round", "phase", "active_player_id")
        )
    ):
        raise GameLifecycleError("Movement keyword completion occurrence drift.")
    raw_roll = payload.get("roll_state")
    if not isinstance(raw_roll, dict):
        raise GameLifecycleError("Movement keyword completion requires its dice evidence.")
    roll = DiceRollState.from_payload(cast(DiceRollStatePayload, raw_roll))
    expected_spec = completion_roll_spec(
        descriptor, source_event_id=source.event_id, player_id=player_id
    )
    if (
        roll.original_result.spec != expected_spec
        or roll.rerolls
        or roll.result_override is not None
    ):
        raise GameLifecycleError("Movement keyword completion dice authority drift.")
    if (
        event_index == 0
        or event_records[event_index - 1].event_type != "dice_rolled"
        or event_records[event_index - 1].payload != roll.original_result.to_payload()
    ):
        raise GameLifecycleError("Movement keyword completion lost its exact dice event.")
    prefix = EventLog.from_payload([row.to_payload() for row in event_records[: event_index - 1]])
    expected_roll = DiceRollManager(state.game_id, event_log=prefix).roll(expected_spec)
    if roll != expected_roll:
        raise GameLifecycleError(
            "Movement keyword completion dice differs from deterministic history."
        )
    if any(
        item.event_type == MOVE_KEYWORD_ROLL_EVENT
        and isinstance(item.payload, dict)
        and item.payload.get("trigger_event_id") == source.event_id
        for item in event_records[source_index + 1 : event_index]
    ):
        raise GameLifecycleError("Movement keyword completion roll is duplicated.")
    return payload, roll


def validate_move_keyword_history(*, state: GameState, decisions: object) -> None:
    from warhammer40k_core.engine.decision_controller import DecisionController

    if type(decisions) is not DecisionController:
        raise GameLifecycleError("Movement keyword history requires DecisionController.")
    from warhammer40k_core.engine.timing_batch_runtime import (
        TIMING_BATCH_EVENT_TYPE,
        timing_batch_from_event,
    )

    records = decisions.event_log.records
    _validate_recorded_membership(state=state, decisions=decisions)
    required: dict[str, str] = {}
    completed: set[str] = set()
    resolved: set[str] = set()
    for index, event in enumerate(records):
        if event.event_type in {"movement_activation_completed", "triggered_movement_resolved"}:
            choice = completion_choice(state=state, event=event, decision_records=decisions.records)
            if choice is not None and choice["selected"]:
                identifier = f"{choice['descriptor_id']}:{event.event_id}:completion"
                required[identifier] = event.event_id
        elif event.event_type == TIMING_BATCH_EVENT_TYPE:
            batch = timing_batch_from_event(event)
            completed.update(batch.completed_participant_ids)
        if event.event_type == MOVE_KEYWORD_ROLL_EVENT:
            payload, _ = validate_completion_roll_event(
                state=state,
                event_records=records,
                decision_records=decisions.records,
                event_index=index,
            )
            resolved.add(cast(str, payload["participant_id"]))
    if any(identifier in completed and identifier not in resolved for identifier in required):
        raise GameLifecycleError("Completed movement keyword participant lost its required roll.")


def _validate_recorded_membership(*, state: GameState, decisions: object) -> None:
    from warhammer40k_core.engine.decision_controller import DecisionController
    from warhammer40k_core.engine.primary_mission_boundary_physical_authority import (
        physical_model_authority_before_event,
    )

    if type(decisions) is not DecisionController:
        raise GameLifecycleError("Movement keyword history requires DecisionController.")
    for record in decisions.records:
        fields = choice_fields(record.result.payload)
        if not fields:
            continue
        choice = cast(dict[str, JsonValue], fields[CHOICE_KEY])
        indices = tuple(
            index
            for index, event in enumerate(decisions.event_log.records)
            if event.event_type == "decision_recorded" and event.payload == record.to_payload()
        )
        if len(indices) != 1:
            raise GameLifecycleError("Movement keyword choice lost its exact recorded occurrence.")
        view = rules_unit_view_by_id(
            state=state, unit_instance_id=cast(str, choice["unit_instance_id"])
        )
        model_ids = {model.model_instance_id for model in view.own_models}
        alive_ids = sorted(
            row.model_instance_id
            for row in physical_model_authority_before_event(
                state=state,
                event_records=decisions.event_log.records,
                decision_records=decisions.records,
                event_index=indices[0],
            )
            if row.wounds_remaining > 0 and row.model_instance_id in model_ids
        )
        if choice["model_instance_ids"] != alive_ids:
            raise GameLifecycleError("Movement keyword historical all-model membership drift.")
