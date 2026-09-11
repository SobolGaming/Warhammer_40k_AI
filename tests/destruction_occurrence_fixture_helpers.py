from __future__ import annotations

from typing import cast

from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_record import DecisionRecord, DecisionRecordPayload
from warhammer40k_core.engine.effects import EffectExpiration, PersistingEffect
from warhammer40k_core.engine.event_log import EventLog, EventRecord
from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.rule_model_destruction import destroy_model_with_rule_reactions


def destroy_rule_model_for_fixture(
    *,
    state: GameState,
    decisions: DecisionController,
    model_id: str,
    destroying_player_id: str,
    source_unit_id: str | None,
    source_model_id: str | None,
) -> EventRecord:
    """Create a casualty through the real rule-destruction owner and its evidence."""
    phase = state.current_battle_phase
    assert phase is not None
    assert state.active_player_id is not None
    identity = f"fixture-casualty:{model_id}:{len(state.model_destruction_cause_authorities)}"
    from warhammer40k_core.engine.rules_units import rules_unit_view_by_id

    unit_id = rules_unit_view_by_id(
        state=state, unit_instance_id=state.unit_instance_id_for_model(model_id)
    ).unit_instance_id
    state.record_persisting_effect(
        PersistingEffect(
            effect_id=identity,
            source_rule_id=identity,
            owner_player_id=destroying_player_id,
            target_unit_instance_ids=(unit_id,),
            started_battle_round=state.battle_round,
            started_phase=phase,
            expiration=EffectExpiration.end_phase(
                battle_round=state.battle_round, phase=phase, player_id=state.active_player_id
            ),
            effect_payload={"effect_kind": "fixture_casualties"},
        )
    )
    result = destroy_model_with_rule_reactions(
        state=state,
        decisions=decisions,
        model_instance_id=model_id,
        rules_unit_instance_id=unit_id,
        destroying_player_id=destroying_player_id,
        source_rule_id=identity,
        source_effect_ids=(identity,),
        source_phase=phase,
        source_step="ability_resolution",
        source_result_id=f"{identity}:result",
        completion_event_type="fixture_casualty_resolved",
        completion_event_payload={"model_instance_id": model_id},
        source_rules_unit_instance_id=source_unit_id,
        source_model_instance_id=source_model_id,
    )
    assert result.status is None
    assert result.model_destroyed_event_id is not None
    return next(
        event
        for event in decisions.event_log.records
        if event.event_id == result.model_destroyed_event_id
    )


def destruction_decisions_for_fixture(event_log: EventLog) -> DecisionController:
    """Share the fixture log and its authenticated decision history with the executor."""
    records = [
        DecisionRecord.from_payload(cast(DecisionRecordPayload, event.payload))
        for event in event_log.records
        if event.event_type == "decision_recorded"
    ]
    return DecisionController(event_log=event_log, _records=records)


def finish_core_destructions_for_fixture(
    *, state: GameState, decisions: DecisionController
) -> None:
    """Finish isolated Core casualty occurrences before a fixture changes phase."""
    from warhammer40k_core.engine.model_destruction_triggers import (
        record_model_destruction_occurrences,
        resolve_model_destruction_trigger,
    )
    from warhammer40k_core.engine.rule_trigger_state import RuleTriggerKind, rule_trigger_history
    from warhammer40k_core.engine.unit_destroyed_hooks import UnitDestroyedHookRegistry

    registry = UnitDestroyedHookRegistry.empty()
    record_model_destruction_occurrences(state=state, decisions=decisions, registry=registry)
    while ready := rule_trigger_history(decisions).ready():
        trigger = ready[0]
        assert trigger.kind is RuleTriggerKind.MODEL_DESTRUCTION
        assert (
            resolve_model_destruction_trigger(
                state=state, decisions=decisions, trigger=trigger, registry=registry
            )
            is None
        )
