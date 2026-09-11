from __future__ import annotations

from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.destruction_provenance import ModelDestructionAttribution
from warhammer40k_core.engine.event_log import JsonValue
from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.primary_destruction_evidence import RulesUnitObjectiveProximityWitness
from warhammer40k_core.engine.primary_historical_events import (
    record_new_primary_battlefield_departure_events,
    record_new_primary_unit_destruction_events,
)
from warhammer40k_core.engine.primary_unit_destruction_tracking import (
    record_primary_destroyed_model_departures,
    record_primary_unit_destruction_for_logical_completion,
)

_PRIMARY_UNIT_DESTRUCTION_TRACKING_RULE_ID = "core-rules:primary-unit-destruction-tracking"


def record_primary_destruction_occurrences(
    *,
    state: GameState,
    decisions: DecisionController,
    model_destroyed_events: tuple[tuple[int, str, dict[str, JsonValue]], ...],
    physical_component_completion_events: tuple[tuple[str, dict[str, JsonValue]], ...],
    completion_events: tuple[tuple[str, dict[str, JsonValue]], ...],
) -> None:
    if state.mission_setup is None:
        return
    departure_ids_before = tuple(
        value.departure_id for value in state.primary_battlefield_departure_states
    )
    physical_completion_pairs = {
        (event_id, _payload_string(payload, key="target_unit_instance_id"))
        for event_id, payload in physical_component_completion_events
    }
    component_by_model_id = {
        model.model_instance_id: unit.unit_instance_id
        for army in state.army_definitions
        for unit in army.units
        for model in unit.own_models
    }
    for _event_order, event_id, payload in model_destroyed_events:
        model_id = _payload_string(payload, key="model_instance_id")
        component_unit_id = component_by_model_id.get(model_id)
        if component_unit_id is None:
            raise GameLifecycleError("model_destroyed event references an unknown model.")
        record_primary_destroyed_model_departures(
            state=state,
            destroyed_model_instance_ids=(model_id,),
            source_id=f"{_PRIMARY_UNIT_DESTRUCTION_TRACKING_RULE_ID}:{event_id}",
            occurrence_id=event_id,
            fully_departed_component_unit_instance_ids=(
                (component_unit_id,)
                if (event_id, component_unit_id) in physical_completion_pairs
                else ()
            ),
        )
    record_new_primary_battlefield_departure_events(
        state=state,
        event_log=decisions.event_log,
        departure_ids_before=departure_ids_before,
    )
    for event_id, payload in completion_events:
        attribution = ModelDestructionAttribution.from_model_destroyed_payload(payload)
        if "source_rules_unit_objective_proximity_witness" not in payload:
            raise GameLifecycleError(
                "model_destroyed event lacks source objective proximity evidence."
            )
        raw_source_witness = payload["source_rules_unit_objective_proximity_witness"]
        source_witness = (
            None
            if raw_source_witness is None
            else RulesUnitObjectiveProximityWitness.from_payload(raw_source_witness)
        )
        if "destroyed_rules_unit_objective_proximity_witness" not in payload:
            raise GameLifecycleError(
                "model_destroyed event lacks destroyed-unit objective proximity evidence."
            )
        RulesUnitObjectiveProximityWitness.from_payload(
            payload["destroyed_rules_unit_objective_proximity_witness"]
        )
        destruction_ids_before = tuple(
            value.destruction_id for value in state.primary_unit_destruction_states
        )
        record_primary_unit_destruction_for_logical_completion(
            state=state,
            destruction_attribution=attribution,
            source_model_destroyed_event_id=event_id,
            source_rules_unit_objective_proximity_witness=source_witness,
            unattributed_cause=None,
            source_mutation_id=None,
            destroyed_unit_instance_id=_payload_string(
                payload,
                key="target_unit_instance_id",
            ),
            source_id=f"{_PRIMARY_UNIT_DESTRUCTION_TRACKING_RULE_ID}:{event_id}",
        )
        record_new_primary_unit_destruction_events(
            state=state,
            event_log=decisions.event_log,
            destruction_ids_before=destruction_ids_before,
        )


def _payload_string(payload: dict[str, JsonValue], *, key: str) -> str:
    if key not in payload:
        raise GameLifecycleError(f"Unit-destroyed event payload missing {key}.")
    return IdentifierValidator(GameLifecycleError)(key, payload[key])
