"""Mandatory, sequenced Aircraft departures at the opponent's turn end."""

from __future__ import annotations

from functools import partial

from warhammer40k_core.engine.aircraft_rules import MOVEMENT_SOURCE_ID
from warhammer40k_core.engine.battlefield_state import (
    BattlefieldRemovalKind,
    BattlefieldTransitionBatch,
    ModelRemovalRecord,
)
from warhammer40k_core.engine.boundary_sequencing import boundary_context
from warhammer40k_core.engine.event_log import validate_json_value
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError
from warhammer40k_core.engine.primary_battlefield_departure import (
    record_primary_battlefield_departure,
)
from warhammer40k_core.engine.primary_historical_events import (
    record_new_primary_battlefield_departure_events,
    record_primary_reserve_entry_mutation_event,
)
from warhammer40k_core.engine.reserve_arrival_requirements import reposition_destruction_policy
from warhammer40k_core.engine.reserves import ReserveKind, ReserveState
from warhammer40k_core.engine.rules_units import RulesUnitView, placed_alive_rules_unit_views
from warhammer40k_core.engine.sequencing import SequencingParticipant, SequencingRequirement
from warhammer40k_core.engine.timing_rule_candidates import TimingRuleCandidate
from warhammer40k_core.engine.timing_windows import TimingTriggerKind
from warhammer40k_core.engine.turn_end_hooks import TurnEndHookBinding, TurnEndRequestContext

AIRCRAFT_RETURN_EVENT = "aircraft_opponent_turn_end_departure"


def aircraft_turn_end_binding() -> TurnEndHookBinding:
    return TurnEndHookBinding(
        hook_id=MOVEMENT_SOURCE_ID,
        source_id=MOVEMENT_SOURCE_ID,
        candidate_handler=_candidates,
    )


def _aircraft(context: TurnEndRequestContext, owner: str) -> tuple[RulesUnitView, ...]:
    return tuple(
        unit
        for unit in placed_alive_rules_unit_views(state=context.state)
        if unit.owner_player_id == owner and "AIRCRAFT" in unit.keywords
    )


def _candidates(context: TurnEndRequestContext) -> tuple[TimingRuleCandidate, ...]:
    if context.trigger_kind is not TimingTriggerKind.END_TURN:
        return ()
    state = context.state
    if state.active_player_id is None:
        raise GameLifecycleError("Aircraft return requires an active turn owner.")
    window = boundary_context(state, TimingTriggerKind.END_TURN).timing_window.window_id
    return tuple(
        TimingRuleCandidate(
            participant=SequencingParticipant(
                participant_id=f"{window}:{MOVEMENT_SOURCE_ID}:{owner}",
                player_id=owner,
                source_rule_id=MOVEMENT_SOURCE_ID,
                requirement=SequencingRequirement.MANDATORY,
                payload={"player_id": owner, "source_rule_id": MOVEMENT_SOURCE_ID},
            ),
            activate=partial(_return_aircraft, context, owner),
        )
        for owner in state.player_ids
        if owner != state.active_player_id and _aircraft(context, owner)
    )


def _return_aircraft(context: TurnEndRequestContext, owner: str) -> None:
    state = context.state
    if owner == state.active_player_id or context.completed_phase is not BattlePhase.FIGHT:
        raise GameLifecycleError("Aircraft return must resolve at the opponent's turn end.")
    for unit in _aircraft(context, owner):
        battlefield = state.battlefield_state
        if battlefield is None:
            raise GameLifecycleError("Aircraft return requires battlefield authority.")
        placements = tuple(
            battlefield.unit_placement_by_id(component_id)
            for component_id in unit.component_unit_instance_ids
            if battlefield.is_unit_placed(component_id)
        )
        model_ids = tuple(
            sorted(
                model.model_instance_id
                for placement in placements
                for model in placement.model_placements
            )
        )
        cargo_ids = tuple(
            sorted(
                {
                    cargo_id
                    for cargo in state.transport_cargo_states
                    if cargo.transport_unit_instance_id in unit.component_unit_instance_ids
                    for cargo_id in cargo.embarked_unit_instance_ids
                }
            )
        )
        reserve = ReserveState.entered_during_battle(
            player_id=owner,
            unit_instance_id=unit.unit_instance_id,
            reserve_kind=ReserveKind.STRATEGIC_RESERVES,
            battle_round=state.battle_round,
            phase=BattlePhase.FIGHT,
            source_rule_ids=(MOVEMENT_SOURCE_ID,),
            embarked_unit_instance_ids=cargo_ids,
            destruction_deadline_policy=reposition_destruction_policy(
                mission_setup=state.mission_setup,
                destruction_deadline_policy=None,
            ),
        )
        source = context.decisions.event_log.append(
            AIRCRAFT_RETURN_EVENT,
            {
                "game_id": state.game_id,
                "battle_round": state.battle_round,
                "active_player_id": state.active_player_id,
                "player_id": owner,
                "phase": BattlePhase.FIGHT.value,
                "source_rule_id": MOVEMENT_SOURCE_ID,
                "unit_instance_id": unit.unit_instance_id,
                "component_unit_instance_ids": list(unit.component_unit_instance_ids),
                "model_instance_ids": list(model_ids),
                "reserve_state": validate_json_value(reserve.to_payload()),
            },
        )
        batch = BattlefieldTransitionBatch(
            removals=tuple(
                ModelRemovalRecord(
                    model_instance_id=model_id,
                    removal_kind=BattlefieldRemovalKind.INTO_RESERVES,
                    source_phase=BattlePhase.FIGHT.value,
                    source_step="player_turn_end",
                    source_rule_id=MOVEMENT_SOURCE_ID,
                    source_event_id=source.event_id,
                    destination_id="strategic_reserves",
                )
                for model_id in model_ids
            )
        )
        for placement in placements:
            battlefield = battlefield.without_unit_placement(placement.unit_instance_id)
        state.replace_battlefield_state(battlefield)
        if state.reserve_state_for_unit(unit.unit_instance_id) is None:
            state.record_reserve_state(reserve)
        else:
            state.replace_reserve_state(reserve)
        before = tuple(row.departure_id for row in state.primary_battlefield_departure_states)
        departure = record_primary_battlefield_departure(
            state=state,
            rules_unit_instance_id=unit.unit_instance_id,
            affected_component_unit_instance_ids=unit.component_unit_instance_ids,
            departed_component_unit_instance_ids=unit.component_unit_instance_ids,
            removed_model_instance_ids=model_ids,
            removal_kind=BattlefieldRemovalKind.INTO_RESERVES,
            occurrence_id=source.event_id,
            source_id=source.event_id,
        )
        if departure is None:
            raise GameLifecycleError("Aircraft return requires departure evidence.")
        record_primary_reserve_entry_mutation_event(
            event_log=context.decisions.event_log,
            departure=departure,
            reserve_state=reserve,
            transition_batch=batch,
        )
        record_new_primary_battlefield_departure_events(
            state=state,
            event_log=context.decisions.event_log,
            departure_ids_before=before,
        )
