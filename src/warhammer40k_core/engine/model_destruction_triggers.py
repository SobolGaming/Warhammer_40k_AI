from __future__ import annotations

from typing import cast

from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.event_log import EventRecord, JsonValue
from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.model_destruction_cause_authority import (
    consumed_model_destruction_cause_authority_for_event,
)
from warhammer40k_core.engine.model_destruction_primary_events import (
    record_primary_destruction_occurrences,
)
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError, LifecycleStatus
from warhammer40k_core.engine.rule_trigger_state import (
    RuleTrigger,
    RuleTriggerKind,
    complete_rule_trigger,
    observe_rule_trigger,
    release_rule_trigger,
    rule_trigger_history,
)
from warhammer40k_core.engine.rules_units import rules_unit_views_from_armies
from warhammer40k_core.engine.unit_destroyed_hooks import (
    ModelDestroyedContext,
    UnitDestroyedContext,
    UnitDestroyedHookRegistry,
    model_destroyed_events_for_lifecycle_phase,
    physical_component_destruction_completion_events_for_phase,
    unit_destruction_completion_events_for_phase,
)

OCCURRENCE_RECORDED_EVENT = "model_destruction_occurrence_recorded"


def observe_model_destruction(
    *, state: GameState, decisions: DecisionController, event: EventRecord
) -> RuleTrigger:
    consumed_model_destruction_cause_authority_for_event(state=state, event=event)
    phase = state.current_battle_phase
    active = state.effective_active_player_id()
    if phase is None or active is None or state.active_player_id is None:
        raise GameLifecycleError("Model destruction requires its current phase and players.")
    if not decisions.event_log.records or decisions.event_log.records[-1] != event:
        raise GameLifecycleError("Model destruction must be observed at its source event.")
    return observe_rule_trigger(
        decisions=decisions,
        kind=RuleTriggerKind.MODEL_DESTRUCTION,
        context={
            "game_id": state.game_id,
            "battle_round": state.battle_round,
            "phase": phase.value,
            "turn_player_id": state.active_player_id,
            "active_player_id": active,
            "trigger_event_id": event.event_id,
        },
    )


def destruction_source_event(
    *, state: GameState, decisions: DecisionController, trigger: RuleTrigger
) -> EventRecord:
    if trigger.kind is not RuleTriggerKind.MODEL_DESTRUCTION or not isinstance(
        trigger.context, dict
    ):
        raise GameLifecycleError("Destruction requires a typed model-destruction trigger.")
    context = trigger.context
    if set(context) != {
        "game_id",
        "battle_round",
        "phase",
        "turn_player_id",
        "active_player_id",
        "trigger_event_id",
    }:
        raise GameLifecycleError("Model destruction trigger schema drift.")
    events = tuple(
        event
        for event in decisions.event_log.records
        if event.event_id == context["trigger_event_id"]
    )
    if len(events) != 1 or not isinstance(events[0].payload, dict):
        raise GameLifecycleError("Model destruction requires its unique source event.")
    event = events[0]
    payload = cast(dict[str, JsonValue], event.payload)
    consumed_model_destruction_cause_authority_for_event(state=state, event=event)
    if (
        context["game_id"] != state.game_id
        or payload.get("game_id") != context["game_id"]
        or payload.get("battle_round") != context["battle_round"]
        or payload.get("active_player_id") != context["turn_player_id"]
        or context["active_player_id"] not in state.player_ids
        or context["phase"] not in tuple(phase.value for phase in BattlePhase)
    ):
        raise GameLifecycleError("Model destruction trigger source identity drift.")
    source_index = decisions.event_log.records.index(event)
    following = decisions.event_log.records[source_index + 1 : source_index + 2]
    if (
        len(following) != 1
        or following[0].event_type != "rule_trigger_observed"
        or following[0].payload != trigger.to_payload()
    ):
        raise GameLifecycleError("Model destruction trigger lost its exact observation boundary.")
    return event


def destroyed_unit_context(
    *, state: GameState, decisions: DecisionController, trigger: RuleTrigger
) -> UnitDestroyedContext | None:
    event = destruction_source_event(state=state, decisions=decisions, trigger=trigger)
    if not isinstance(trigger.context, dict):
        raise GameLifecycleError("Model destruction context must be an object.")
    phase = BattlePhase(cast(str, trigger.context["phase"]))
    if (
        phase is not state.current_battle_phase
        or trigger.context["battle_round"] != state.battle_round
    ):
        raise GameLifecycleError("Unresolved model destruction escaped its source phase.")
    completions = tuple(
        payload
        for event_id, payload in unit_destruction_completion_events_for_phase(
            state=state, event_log=decisions.event_log, completed_phase=phase
        )
        if event_id == event.event_id
    )
    if not completions:
        return None
    if len(completions) != 1:
        raise GameLifecycleError("Model destruction has ambiguous logical completion.")
    payload = completions[0]
    unit_id = payload["target_unit_instance_id"]
    destroyer = payload["destroying_player_id"]
    if type(unit_id) is not str or type(destroyer) is not str:
        raise GameLifecycleError("Unit destruction requires typed unit and player identities.")
    owners = {
        view.owner_player_id
        for view in rules_unit_views_from_armies(armies=tuple(state.army_definitions))
        if view.unit_instance_id == unit_id
    } | {
        record.player_id
        for record in state.starting_attached_unit_records
        if record.attached_unit_instance_id == unit_id
    }
    if len(owners) != 1:
        raise GameLifecycleError("Destroyed logical unit requires exactly one owner.")
    owner = next(iter(owners))
    if destroyer == owner:
        return None
    return UnitDestroyedContext(
        state=state,
        decisions=decisions,
        completed_phase=phase,
        model_destroyed_event_id=event.event_id,
        model_destroyed_payload=payload,
        destroying_player_id=destroyer,
        destroyed_unit_instance_id=unit_id,
        destroyed_player_id=owner,
        sequencing_active_player_id=cast(str, state.effective_active_player_id()),
    )


def record_model_destruction_occurrences(
    *, state: GameState, decisions: DecisionController, registry: UnitDestroyedHookRegistry
) -> None:
    history = rule_trigger_history(decisions)
    recorded = recorded_model_destruction_occurrences(decisions)
    for trigger in history.observed:
        if trigger.kind is not RuleTriggerKind.MODEL_DESTRUCTION or trigger.trigger_id in recorded:
            continue
        event = destruction_source_event(state=state, decisions=decisions, trigger=trigger)
        context = destroyed_unit_context(state=state, decisions=decisions, trigger=trigger)
        phase = state.current_battle_phase
        if phase is None:
            raise GameLifecycleError("Model destruction occurrence requires its source phase.")
        record_primary_destruction_occurrences(
            state=state,
            decisions=decisions,
            model_destroyed_events=tuple(
                item
                for item in model_destroyed_events_for_lifecycle_phase(
                    state=state, event_log=decisions.event_log, completed_phase=phase
                )
                if item[1] == event.event_id
            ),
            physical_component_completion_events=tuple(
                item
                for item in physical_component_destruction_completion_events_for_phase(
                    state=state, event_log=decisions.event_log, completed_phase=phase
                )
                if item[0] == event.event_id
            ),
            completion_events=tuple(
                item
                for item in unit_destruction_completion_events_for_phase(
                    state=state, event_log=decisions.event_log, completed_phase=phase
                )
                if item[0] == event.event_id
            ),
        )
        registry.record_model_occurrence(
            ModelDestroyedContext(
                state=state,
                decisions=decisions,
                phase=phase,
                event=event,
            )
        )
        if context is not None:
            registry.record_occurrence(context)
        decisions.event_log.append(OCCURRENCE_RECORDED_EVENT, {"trigger_id": trigger.trigger_id})


def resolve_model_destruction_trigger(
    *,
    state: GameState,
    decisions: DecisionController,
    trigger: RuleTrigger,
    registry: UnitDestroyedHookRegistry,
) -> LifecycleStatus | None:
    from warhammer40k_core.engine.unit_destruction_sequencing import (
        resolve_unit_destroyed_candidates,
    )

    if not release_rule_trigger(decisions=decisions, trigger=trigger):
        from warhammer40k_core.engine.rule_trigger_state import unreleased_rule_trigger_status

        return unreleased_rule_trigger_status(
            decisions=decisions, trigger=trigger, stage=state.stage
        )
    context = destroyed_unit_context(state=state, decisions=decisions, trigger=trigger)
    status = (
        None
        if context is None
        else resolve_unit_destroyed_candidates(context=context, registry=registry)
    )
    from warhammer40k_core.engine.phase import LifecycleStatusKind
    from warhammer40k_core.engine.timing_batch_runtime import timing_batches_for_context
    from warhammer40k_core.engine.unit_destruction_sequencing import unit_destruction_timing_context

    batches = (
        ()
        if context is None
        else timing_batches_for_context(decisions, unit_destruction_timing_context(context))
    )
    if status is None or (
        status.status_kind is LifecycleStatusKind.ADVANCED
        and batches
        and batches[-1].current_batch_complete
    ):
        complete_rule_trigger(decisions=decisions, trigger=trigger)
    return status


def advance_model_destruction_triggers(
    *, state: GameState, decisions: DecisionController, registry: UnitDestroyedHookRegistry
) -> LifecycleStatus | None:
    record_model_destruction_occurrences(state=state, decisions=decisions, registry=registry)
    if decisions.queue.pending_requests:
        return None
    while ready := rule_trigger_history(decisions).ready():
        if ready[0].kind is not RuleTriggerKind.MODEL_DESTRUCTION:
            return None
        status = resolve_model_destruction_trigger(
            state=state,
            decisions=decisions,
            trigger=ready[0],
            registry=registry,
        )
        if status is not None:
            return status
    return None


def recorded_model_destruction_occurrences(decisions: DecisionController) -> tuple[str, ...]:
    observed: set[str] = set()
    recorded: list[str] = []
    for event in decisions.event_log.records:
        if event.event_type == "rule_trigger_observed":
            if not isinstance(event.payload, dict):
                raise GameLifecycleError("Trigger observation must have an object payload.")
            if event.payload.get("kind") == RuleTriggerKind.MODEL_DESTRUCTION.value:
                identifier = event.payload.get("trigger_id")
                if type(identifier) is not str:
                    raise GameLifecycleError("Model occurrence lacks trigger identity.")
                observed.add(identifier)
        elif event.event_type == OCCURRENCE_RECORDED_EVENT:
            if not isinstance(event.payload, dict) or set(event.payload) != {"trigger_id"}:
                raise GameLifecycleError("Model occurrence record schema drift.")
            identifier = event.payload["trigger_id"]
            if type(identifier) is not str or identifier not in observed or identifier in recorded:
                raise GameLifecycleError("Model occurrence record requires a unique prior trigger.")
            recorded.append(identifier)
    return tuple(recorded)


def validate_model_destruction_observations(
    *, state: GameState, decisions: DecisionController
) -> None:
    history = rule_trigger_history(decisions)
    triggers = tuple(
        trigger for trigger in history.observed if trigger.kind is RuleTriggerKind.MODEL_DESTRUCTION
    )
    observed_events = tuple(
        destruction_source_event(state=state, decisions=decisions, trigger=trigger).event_id
        for trigger in triggers
    )
    actual_events = tuple(
        event.event_id
        for event in decisions.event_log.records
        if event.event_type == "model_destroyed"
    )
    if observed_events != actual_events:
        raise GameLifecycleError(
            "Model destruction source events require exact trigger observations."
        )
    recorded_model_destruction_occurrences(decisions)
