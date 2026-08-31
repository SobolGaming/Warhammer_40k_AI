from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, cast

from warhammer40k_core.engine.battlefield_state import BattlefieldRemovalKind
from warhammer40k_core.engine.decision_record import DecisionRecord
from warhammer40k_core.engine.destruction_provenance import ModelDestructionAttribution
from warhammer40k_core.engine.event_log import EventRecord, JsonValue
from warhammer40k_core.engine.movement_proposals import PLACEMENT_PROPOSAL_DECISION_TYPE
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.phases.movement_model import (
    SELECT_DESPERATE_ESCAPE_MODEL_DECISION_TYPE,
)
from warhammer40k_core.engine.primary_battlefield_departure import (
    PrimaryBattlefieldDepartureState,
)
from warhammer40k_core.engine.primary_battlefield_departure_integrity import (
    validate_non_destroyed_battlefield_departure_provenance,
)
from warhammer40k_core.engine.primary_destruction_evidence import (
    PrimaryUnattributedDestructionCause,
    RulesUnitObjectiveProximityWitness,
)
from warhammer40k_core.engine.primary_destruction_timeline_integrity import (
    validate_full_destruction_transition_timeline,
)
from warhammer40k_core.engine.primary_historical_events import (
    PRIMARY_BATTLEFIELD_DEPARTURE_RECORDED_EVENT,
    PRIMARY_TURN_START_EVIDENCE_RECORDED_EVENT,
    PRIMARY_UNIT_DESTRUCTION_RECORDED_EVENT,
)
from warhammer40k_core.engine.scoring import PrimaryUnitDestructionState
from warhammer40k_core.engine.transports import (
    DestroyedTransportDisembark,
    DestroyedTransportDisembarkPayload,
    DisembarkModeKind,
)

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState


_PRIMARY_UNIT_DESTRUCTION_TRACKING_RULE_ID = "core-rules:primary-unit-destruction-tracking"


@dataclass(frozen=True, slots=True)
class _ScoringRulesUnitIdentity:
    rules_unit_instance_id: str
    owner_player_id: str
    component_unit_instance_ids: tuple[str, ...]
    starting_model_instance_ids_by_component: tuple[tuple[str, tuple[str, ...]], ...]

    @property
    def starting_model_instance_ids(self) -> tuple[str, ...]:
        return tuple(
            model_id
            for _component_id, model_ids in self.starting_model_instance_ids_by_component
            for model_id in model_ids
        )

    def component_id_for_model(self, model_instance_id: str) -> str | None:
        for component_id, model_ids in self.starting_model_instance_ids_by_component:
            if model_instance_id in model_ids:
                return component_id
        return None

    def model_ids_for_component(self, component_unit_instance_id: str) -> tuple[str, ...]:
        for component_id, model_ids in self.starting_model_instance_ids_by_component:
            if component_id == component_unit_instance_id:
                return model_ids
        raise GameLifecycleError(
            "Primary destruction departure references a component outside its scoring unit."
        )


@dataclass(frozen=True, slots=True)
class _DestroyedDepartureSource:
    source_key: str
    completion_key: str
    event_order: int
    expected_model_ids_by_component: tuple[tuple[str, tuple[str, ...]], ...]


def validate_primary_historical_event_integrity(
    *,
    state: GameState,
    event_records: tuple[EventRecord, ...],
    decision_records: tuple[DecisionRecord, ...],
    require_muster_event_provenance: bool,
) -> None:
    """Validate persisted Primary destruction evidence against its event graph.

    State-local loaders validate individual rows.  Lifecycle restoration also owns
    the event log, so it can fail closed when a destruction refers to an invented
    event, when a starting Attached Unit is collapsed to one physical component,
    or when its explicit battlefield-departure edges are missing or reused.
    """
    if type(event_records) is not tuple or any(
        type(record) is not EventRecord for record in event_records
    ):
        raise GameLifecycleError("Primary historical event integrity requires typed event records.")
    if type(decision_records) is not tuple or any(
        type(record) is not DecisionRecord for record in decision_records
    ):
        raise GameLifecycleError(
            "Primary historical event integrity requires typed decision records."
        )
    events_by_id = {record.event_id: record for record in event_records}
    if len(events_by_id) != len(event_records):
        raise GameLifecycleError("Primary historical event IDs must be unique.")
    event_index_by_id = {record.event_id: index for index, record in enumerate(event_records)}
    model_ids_by_unit_id = {
        unit.unit_instance_id: tuple(sorted(unit.own_model_ids()))
        for army in state.army_definitions
        for unit in army.units
    }
    rules_unit_components_by_id = _rules_unit_components_by_id(state=state)
    identities_by_id = _scoring_identities_by_id(
        state=state,
        model_ids_by_unit_id=model_ids_by_unit_id,
    )
    destructions = tuple(state.primary_unit_destruction_states)
    departures = tuple(state.primary_battlefield_departure_states)
    if require_muster_event_provenance:
        _validate_starting_attached_unit_muster_events(
            state=state,
            event_records=event_records,
        )
    _validate_turn_start_recorded_events(state=state, event_records=event_records)
    _validate_departure_recorded_events(
        departures=departures,
        event_records=event_records,
    )
    validate_non_destroyed_battlefield_departure_provenance(
        state=state,
        departures=departures,
        event_records=event_records,
        decision_records=decision_records,
    )
    departure_sources = _validate_destroyed_departure_provenance(
        state=state,
        destructions=destructions,
        departures=departures,
        identities_by_id=identities_by_id,
        model_ids_by_unit_id=model_ids_by_unit_id,
        rules_unit_components_by_id=rules_unit_components_by_id,
        event_records=event_records,
        events_by_id=events_by_id,
        event_index_by_id=event_index_by_id,
        decision_records=decision_records,
    )
    for destruction in destructions:
        identity = identities_by_id.get(destruction.destroyed_unit_instance_id)
        if identity is None:
            raise GameLifecycleError(
                "Primary destruction scoring identity is not a starting rules unit."
            )
        if destruction.destruction_attribution is None:
            continue
        _validate_attributed_destruction_events(
            state=state,
            destruction=destruction,
            identity=identity,
            events_by_id=events_by_id,
            model_ids_by_unit_id=model_ids_by_unit_id,
            rules_unit_components_by_id=rules_unit_components_by_id,
        )
    _validate_recorded_destruction_events(
        destructions=destructions,
        event_records=event_records,
    )
    _validate_destruction_departure_links(
        destructions=destructions,
        departures=departures,
        identities_by_id=identities_by_id,
        model_ids_by_unit_id=model_ids_by_unit_id,
        rules_unit_components_by_id=rules_unit_components_by_id,
        events_by_id=events_by_id,
        event_index_by_id=event_index_by_id,
    )
    validate_full_destruction_transition_timeline(
        state=state,
        destructions=destructions,
        departures=departures,
        departure_sources=departure_sources,
        event_records=event_records,
        event_index_by_id=event_index_by_id,
        identities_by_id=identities_by_id,
        decision_records=decision_records,
    )


def _scoring_identities_by_id(
    *,
    state: GameState,
    model_ids_by_unit_id: dict[str, tuple[str, ...]],
) -> dict[str, _ScoringRulesUnitIdentity]:
    physical_owner_by_id = {
        unit.unit_instance_id: army.player_id
        for army in state.army_definitions
        for unit in army.units
    }
    component_ids_in_starting_attached_units: set[str] = set()
    identities: dict[str, _ScoringRulesUnitIdentity] = {}
    for record in state.starting_attached_unit_records:
        frozen_models = tuple(
            (component_id, tuple(sorted(model_ids)))
            for component_id, model_ids in record.starting_model_instance_ids_by_component
        )
        if tuple(component_id for component_id, _model_ids in frozen_models) != (
            record.component_unit_instance_ids
        ):
            raise GameLifecycleError(
                "Starting Attached Unit frozen model component identity drifted."
            )
        identities[record.attached_unit_instance_id] = _ScoringRulesUnitIdentity(
            rules_unit_instance_id=record.attached_unit_instance_id,
            owner_player_id=record.player_id,
            component_unit_instance_ids=record.component_unit_instance_ids,
            starting_model_instance_ids_by_component=frozen_models,
        )
        component_ids_in_starting_attached_units.update(record.component_unit_instance_ids)
    for unit_id, model_ids in model_ids_by_unit_id.items():
        if unit_id in component_ids_in_starting_attached_units:
            continue
        identities[unit_id] = _ScoringRulesUnitIdentity(
            rules_unit_instance_id=unit_id,
            owner_player_id=physical_owner_by_id[unit_id],
            component_unit_instance_ids=(unit_id,),
            starting_model_instance_ids_by_component=((unit_id, model_ids),),
        )
    return identities


def _rules_unit_components_by_id(state: GameState) -> dict[str, tuple[str, ...]]:
    components_by_id: dict[str, tuple[str, ...]] = {
        unit.unit_instance_id: (unit.unit_instance_id,)
        for army in state.army_definitions
        for unit in army.units
    }
    for record in state.starting_attached_unit_records:
        components_by_id[record.attached_unit_instance_id] = tuple(
            sorted(record.component_unit_instance_ids)
        )
    for army in state.army_definitions:
        for formation in army.attached_units:
            components = tuple(sorted(formation.component_unit_instance_ids))
            existing = components_by_id.get(formation.attached_unit_instance_id)
            if existing is not None and existing != components:
                raise GameLifecycleError("Current rules-unit component identity is ambiguous.")
            components_by_id[formation.attached_unit_instance_id] = components
    return components_by_id


def _validate_destroyed_departure_provenance(
    *,
    state: GameState,
    destructions: tuple[PrimaryUnitDestructionState, ...],
    departures: tuple[PrimaryBattlefieldDepartureState, ...],
    identities_by_id: dict[str, _ScoringRulesUnitIdentity],
    model_ids_by_unit_id: dict[str, tuple[str, ...]],
    rules_unit_components_by_id: dict[str, tuple[str, ...]],
    event_records: tuple[EventRecord, ...],
    events_by_id: dict[str, EventRecord],
    event_index_by_id: dict[str, int],
    decision_records: tuple[DecisionRecord, ...],
) -> dict[str, _DestroyedDepartureSource]:
    """Bind every DESTROYED departure, including unconsumed partial losses."""
    destroyed_departures = tuple(
        departure
        for departure in departures
        if departure.removal_kind is BattlefieldRemovalKind.DESTROYED
    )
    component_by_model_id = {
        model_id: component_id
        for component_id, model_ids in model_ids_by_unit_id.items()
        for model_id in model_ids
    }
    decisions_by_result_id: dict[str, DecisionRecord] = {}
    for record in decision_records:
        result_id = record.result.result_id
        if result_id in decisions_by_result_id:
            raise GameLifecycleError("Primary destruction decision result IDs must be unique.")
        decisions_by_result_id[result_id] = record
    cleanup_by_id = {cleanup.cleanup_id: cleanup for cleanup in state.end_turn_cleanup_states}
    if len(cleanup_by_id) != len(state.end_turn_cleanup_states):
        raise GameLifecycleError("Primary destruction cleanup source IDs must be unique.")

    source_by_departure_id: dict[str, _DestroyedDepartureSource] = {}
    actual_by_source_key: dict[str, dict[str, list[PrimaryBattlefieldDepartureState]]] = {}
    cached_sources: dict[str, _DestroyedDepartureSource] = {}
    for departure in destroyed_departures:
        identity = identities_by_id.get(departure.rules_unit_instance_id)
        if identity is None:
            raise GameLifecycleError(
                "Primary destroyed departure is not owned by a starting rules unit."
            )
        _validate_destroyed_departure_identity(
            departure=departure,
            identity=identity,
            model_ids_by_unit_id=model_ids_by_unit_id,
            rules_unit_components_by_id=rules_unit_components_by_id,
        )
        component_id = departure.affected_component_unit_instance_ids[0]
        event_id = _event_id_from_departure_source(departure)
        if event_id is not None:
            source_key = f"model-destroyed:{event_id}"
            source = cached_sources.get(source_key)
            if source is None:
                source = _model_destroyed_departure_source(
                    departure=departure,
                    event_id=event_id,
                    events_by_id=events_by_id,
                    event_index_by_id=event_index_by_id,
                    component_by_model_id=component_by_model_id,
                )
                cached_sources[source_key] = source
        else:
            source_base = _departure_source_base(departure)
            if source_base.startswith("core-rules:desperate-escape:"):
                mutation_id = source_base.removeprefix("core-rules:desperate-escape:")
                source_key = f"desperate-escape:{mutation_id}"
                source = cached_sources.get(source_key)
                if source is None:
                    source = _desperate_escape_departure_source(
                        state=state,
                        mutation_id=mutation_id,
                        source_base=source_base,
                        event_records=event_records,
                        event_index_by_id=event_index_by_id,
                        decisions_by_result_id=decisions_by_result_id,
                        component_by_model_id=component_by_model_id,
                    )
                    cached_sources[source_key] = source
            elif source_base.startswith("core-rules:emergency-disembark:"):
                mutation_id = source_base.removeprefix("core-rules:emergency-disembark:")
                source_key = f"emergency-disembark:{mutation_id}"
                source = cached_sources.get(source_key)
                if source is None:
                    source = _emergency_disembark_departure_source(
                        state=state,
                        mutation_id=mutation_id,
                        source_base=source_base,
                        event_records=event_records,
                        event_index_by_id=event_index_by_id,
                        decisions_by_result_id=decisions_by_result_id,
                        component_by_model_id=component_by_model_id,
                    )
                    cached_sources[source_key] = source
            elif source_base in cleanup_by_id:
                source_key = f"unit-coherency:{source_base}"
                source = cached_sources.get(source_key)
                if source is None:
                    source = _unit_coherency_departure_source(
                        state=state,
                        cleanup_id=source_base,
                        event_records=event_records,
                        cleanup=cleanup_by_id[source_base],
                        component_by_model_id=component_by_model_id,
                    )
                    cached_sources[source_key] = source
            else:
                raise GameLifecycleError(
                    "Primary destroyed departure has no authoritative mutation provider."
                )
        source_by_departure_id[departure.departure_id] = source
        actual_by_source_key.setdefault(source.source_key, {}).setdefault(component_id, []).append(
            departure
        )

    for source_key, actual_by_component in actual_by_source_key.items():
        source = cached_sources[source_key]
        expected_by_component = dict(source.expected_model_ids_by_component)
        if set(actual_by_component) != set(expected_by_component):
            raise GameLifecycleError(
                "Primary destroyed departure batch component provenance drift."
            )
        for component_id, expected_model_ids in expected_by_component.items():
            actual = actual_by_component[component_id]
            if len(actual) != 1 or actual[0].removed_model_instance_ids != expected_model_ids:
                raise GameLifecycleError(
                    "Primary destroyed departure batch model provenance drift."
                )
    _validate_no_missing_model_destroyed_departures(
        state=state,
        destructions=destructions,
        destroyed_departures=destroyed_departures,
        identities_by_id=identities_by_id,
        component_by_model_id=component_by_model_id,
        event_records=event_records,
        event_index_by_id=event_index_by_id,
    )
    return source_by_departure_id


def _validate_no_missing_model_destroyed_departures(
    *,
    state: GameState,
    destructions: tuple[PrimaryUnitDestructionState, ...],
    destroyed_departures: tuple[PrimaryBattlefieldDepartureState, ...],
    identities_by_id: dict[str, _ScoringRulesUnitIdentity],
    component_by_model_id: dict[str, str],
    event_records: tuple[EventRecord, ...],
    event_index_by_id: dict[str, int],
) -> None:
    event_backed_ids = {
        event_id
        for departure in destroyed_departures
        if (event_id := _event_id_from_departure_source(departure)) is not None
    }
    destruction_record_order_by_id: dict[str, int] = {}
    for index, record in enumerate(event_records):
        if record.event_type != PRIMARY_UNIT_DESTRUCTION_RECORDED_EVENT:
            continue
        payload = _event_payload(record, event_name="primary_unit_destruction_recorded")
        raw_state = payload.get("primary_unit_destruction_state")
        if not isinstance(raw_state, dict):
            raise GameLifecycleError("Primary destruction recorded state is malformed.")
        destruction_id = raw_state.get("destruction_id")
        if type(destruction_id) is not str:
            raise GameLifecycleError("Primary destruction recorded identity is malformed.")
        destruction_record_order_by_id[destruction_id] = index
    destruction_orders_by_identity = {
        identity_id: tuple(
            _required_destruction_record_order(
                destruction=destruction,
                destruction_record_order_by_id=destruction_record_order_by_id,
            )
            for destruction in destructions
            if destruction.destroyed_unit_instance_id == identity_id
        )
        for identity_id in identities_by_id
    }
    phase_boundary_orders = tuple(
        index
        for index, record in enumerate(event_records)
        if record.event_type == "battle_phase_completed"
    )
    identity_id_by_component = {
        component_id: identity.rules_unit_instance_id
        for identity in identities_by_id.values()
        for component_id in identity.component_unit_instance_ids
    }
    for record in event_records:
        if record.event_type != "model_destroyed":
            continue
        payload = _event_payload(record, event_name="model_destroyed")
        if payload.get("game_id") != state.game_id:
            continue
        model_id = payload.get("model_instance_id")
        if type(model_id) is not str:
            raise GameLifecycleError("model_destroyed event model identity is malformed.")
        component_id = component_by_model_id.get(model_id)
        identity_id = None if component_id is None else identity_id_by_component.get(component_id)
        if identity_id is None:
            raise GameLifecycleError("model_destroyed event references no starting lineage.")
        event_order = event_index_by_id[record.event_id]
        has_later_completion = any(
            order > event_order for order in destruction_orders_by_identity[identity_id]
        )
        phase_was_completed = any(order > event_order for order in phase_boundary_orders)
        if (
            has_later_completion or phase_was_completed
        ) and record.event_id not in event_backed_ids:
            raise GameLifecycleError(
                "Processed model_destroyed event lacks its exact battlefield departure."
            )


def _required_destruction_record_order(
    *,
    destruction: PrimaryUnitDestructionState,
    destruction_record_order_by_id: dict[str, int],
) -> int:
    order = destruction_record_order_by_id.get(destruction.destruction_id)
    if order is None:
        raise GameLifecycleError("Primary destruction requires an authoritative recorded event.")
    return order


def _validate_destroyed_departure_identity(
    *,
    departure: PrimaryBattlefieldDepartureState,
    identity: _ScoringRulesUnitIdentity,
    model_ids_by_unit_id: dict[str, tuple[str, ...]],
    rules_unit_components_by_id: dict[str, tuple[str, ...]],
) -> None:
    if len(departure.affected_component_unit_instance_ids) != 1:
        raise GameLifecycleError(
            "Primary destroyed departure must identify one affected physical unit."
        )
    component_id = departure.affected_component_unit_instance_ids[0]
    if (
        departure.owner_player_id != identity.owner_player_id
        or component_id not in identity.component_unit_instance_ids
        or departure.component_unit_instance_ids
        != rules_unit_components_by_id.get(departure.rules_unit_instance_id)
        or not set(departure.departed_component_unit_instance_ids) <= {component_id}
        or not set(departure.removed_model_instance_ids) <= set(model_ids_by_unit_id[component_id])
    ):
        raise GameLifecycleError("Primary destroyed departure physical identity drift.")


def _model_destroyed_departure_source(
    *,
    departure: PrimaryBattlefieldDepartureState,
    event_id: str,
    events_by_id: dict[str, EventRecord],
    event_index_by_id: dict[str, int],
    component_by_model_id: dict[str, str],
) -> _DestroyedDepartureSource:
    event = events_by_id.get(event_id)
    if event is None or event.event_type != "model_destroyed":
        raise GameLifecycleError(
            "Primary destroyed departure references no authoritative model_destroyed event."
        )
    payload = _event_payload(event, event_name="model_destroyed")
    model_id = payload.get("model_instance_id")
    if type(model_id) is not str:
        raise GameLifecycleError("Primary destroyed departure model event is malformed.")
    component_id = component_by_model_id.get(model_id)
    if component_id is None or departure.affected_component_unit_instance_ids != (component_id,):
        raise GameLifecycleError("Primary destroyed departure model component drift.")
    if (
        payload.get("game_id") != departure.game_id
        or payload.get("battle_round") != departure.battle_round
        or payload.get("active_player_id") != departure.active_player_id
    ):
        raise GameLifecycleError("Primary destroyed departure model timing drift.")
    return _DestroyedDepartureSource(
        source_key=f"model-destroyed:{event_id}",
        completion_key=f"model-destroyed:{event_id}",
        event_order=event_index_by_id[event_id],
        expected_model_ids_by_component=((component_id, (model_id,)),),
    )


def _desperate_escape_departure_source(
    *,
    state: GameState,
    mutation_id: str,
    source_base: str,
    event_records: tuple[EventRecord, ...],
    event_index_by_id: dict[str, int],
    decisions_by_result_id: dict[str, DecisionRecord],
    component_by_model_id: dict[str, str],
) -> _DestroyedDepartureSource:
    decision = _require_source_decision(
        mutation_id=mutation_id,
        expected_decision_type=SELECT_DESPERATE_ESCAPE_MODEL_DECISION_TYPE,
        decisions_by_result_id=decisions_by_result_id,
        event_records=event_records,
    )
    result_payload = _json_object(decision.result.payload, name="Desperate Escape result")
    decision_model_ids = _json_identifier_list(
        result_payload.get("destroyed_model_ids"), name="Desperate Escape destroyed_model_ids"
    )
    applied = tuple(
        record
        for record in event_records
        if record.event_type == "fall_back_move_applied"
        and isinstance(record.payload, dict)
        and record.payload.get("desperate_escape_source_mutation_id") == mutation_id
    )
    completed = tuple(
        record
        for record in event_records
        if record.event_type == "movement_activation_completed"
        and isinstance(record.payload, dict)
        and record.payload.get("desperate_escape_source_mutation_id") == mutation_id
    )
    if len(applied) > 1 or len(completed) > 1 or (not applied and len(completed) != 1):
        raise GameLifecycleError(
            "Desperate Escape departure requires one authoritative movement terminal event."
        )
    if applied:
        terminal = applied[0]
    elif completed:
        terminal = completed[0]
    else:
        raise GameLifecycleError(
            "Desperate Escape departure requires one authoritative movement terminal event."
        )
    payload = _event_payload(terminal, event_name=terminal.event_type)
    terminal_model_ids = _json_identifier_list(
        payload.get("destroyed_model_ids"), name="Desperate Escape terminal destroyed_model_ids"
    )
    if (
        terminal_model_ids != decision_model_ids
        or payload.get("game_id") != state.game_id
        or payload.get("active_player_id") != decision.result.actor_id
        or payload.get("movement_phase_action") != "fall_back"
    ):
        raise GameLifecycleError("Desperate Escape departure terminal evidence drift.")
    _validate_destroyed_transition_batch(
        payload.get("transition_batch"), expected_model_ids=terminal_model_ids
    )
    if applied and completed:
        completed_payload = _event_payload(completed[0], event_name="movement_activation_completed")
        if completed_payload.get("destroyed_model_ids") != list(
            terminal_model_ids
        ) or completed_payload.get("transition_batch") != payload.get("transition_batch"):
            raise GameLifecycleError("Desperate Escape completion evidence drifted.")
    return _DestroyedDepartureSource(
        source_key=f"desperate-escape:{mutation_id}",
        completion_key=f"desperate-escape:{mutation_id}",
        event_order=event_index_by_id[terminal.event_id],
        expected_model_ids_by_component=_model_ids_grouped_by_component(
            terminal_model_ids, component_by_model_id=component_by_model_id
        ),
    )


def _emergency_disembark_departure_source(
    *,
    state: GameState,
    mutation_id: str,
    source_base: str,
    event_records: tuple[EventRecord, ...],
    event_index_by_id: dict[str, int],
    decisions_by_result_id: dict[str, DecisionRecord],
    component_by_model_id: dict[str, str],
) -> _DestroyedDepartureSource:
    decision = _require_source_decision(
        mutation_id=mutation_id,
        expected_decision_type=PLACEMENT_PROPOSAL_DECISION_TYPE,
        decisions_by_result_id=decisions_by_result_id,
        event_records=event_records,
    )
    matching = tuple(
        record
        for record in event_records
        if record.event_type == "unit_disembarked"
        and isinstance(record.payload, dict)
        and record.payload.get("result_id") == mutation_id
        and record.payload.get("disembark_mode") == DisembarkModeKind.EMERGENCY_DISEMBARK.value
    )
    if len(matching) != 1:
        raise GameLifecycleError(
            "Emergency Disembark departure requires one authoritative terminal event."
        )
    terminal = matching[0]
    payload = _event_payload(terminal, event_name="unit_disembarked")
    raw_disembark = payload.get("destroyed_transport_disembark")
    if not isinstance(raw_disembark, dict):
        raise GameLifecycleError(
            "Emergency Disembark terminal event lacks typed destruction evidence."
        )
    disembark = DestroyedTransportDisembark.from_payload(
        cast(DestroyedTransportDisembarkPayload, raw_disembark)
    )
    result_payload = _json_object(decision.result.payload, name="Emergency Disembark result")
    if (
        payload.get("game_id") != state.game_id
        or payload.get("active_player_id") != decision.result.actor_id
        or disembark.disembark_mode is not DisembarkModeKind.EMERGENCY_DISEMBARK
        or disembark.player_id != decision.result.actor_id
        or result_payload.get("unit_instance_id") != disembark.unit_instance_id
        or payload.get("unit_instance_id") != disembark.unit_instance_id
    ):
        raise GameLifecycleError("Emergency Disembark departure terminal evidence drift.")
    return _DestroyedDepartureSource(
        source_key=f"emergency-disembark:{mutation_id}",
        completion_key=f"emergency-disembark:{mutation_id}",
        event_order=event_index_by_id[terminal.event_id],
        expected_model_ids_by_component=_model_ids_grouped_by_component(
            disembark.destroyed_model_instance_ids,
            component_by_model_id=component_by_model_id,
        ),
    )


def _unit_coherency_departure_source(
    *,
    state: GameState,
    cleanup_id: str,
    event_records: tuple[EventRecord, ...],
    cleanup: object,
    component_by_model_id: dict[str, str],
) -> _DestroyedDepartureSource:
    from warhammer40k_core.engine.turn_cleanup import EndTurnCleanupState

    if type(cleanup) is not EndTurnCleanupState:
        raise GameLifecycleError("Unit Coherency departure requires typed cleanup evidence.")
    if cleanup.game_id != state.game_id:
        raise GameLifecycleError("Unit Coherency departure cleanup game drift.")
    source_orders = tuple(
        source_index
        for source_index, source_record in enumerate(event_records)
        if _recorded_departure_source_id(source_record) is not None
        and cast(str, _recorded_departure_source_id(source_record)).startswith(f"{cleanup_id}:")
    )
    if not source_orders:
        raise GameLifecycleError("Unit Coherency departure lacks its recorded departure events.")
    terminal_order = next(
        (
            index
            for index, record in enumerate(event_records)
            if record.event_type == "battle_phase_completed" and index > max(source_orders)
        ),
        None,
    )
    if terminal_order is None:
        raise GameLifecycleError(
            "Unit Coherency departure requires an authoritative phase-boundary event."
        )
    return _DestroyedDepartureSource(
        source_key=f"unit-coherency:{cleanup_id}",
        completion_key=f"unit-coherency:{cleanup_id}",
        event_order=terminal_order,
        expected_model_ids_by_component=_model_ids_grouped_by_component(
            cleanup.removed_model_instance_ids,
            component_by_model_id=component_by_model_id,
        ),
    )


def _recorded_departure_source_id(record: EventRecord) -> str | None:
    if record.event_type != PRIMARY_BATTLEFIELD_DEPARTURE_RECORDED_EVENT or not isinstance(
        record.payload, dict
    ):
        return None
    raw_state = record.payload.get("primary_battlefield_departure_state")
    if not isinstance(raw_state, dict):
        return None
    source_id = raw_state.get("source_id")
    return source_id if type(source_id) is str else None


def _require_source_decision(
    *,
    mutation_id: str,
    expected_decision_type: str,
    decisions_by_result_id: dict[str, DecisionRecord],
    event_records: tuple[EventRecord, ...],
) -> DecisionRecord:
    decision = decisions_by_result_id.get(mutation_id)
    if decision is None or decision.result.decision_type != expected_decision_type:
        raise GameLifecycleError("Primary destruction mutation decision provenance drift.")
    matching_events = tuple(
        record
        for record in event_records
        if record.event_type == "decision_recorded" and record.payload == decision.to_payload()
    )
    if len(matching_events) != 1:
        raise GameLifecycleError(
            "Primary destruction mutation requires one authoritative decision event."
        )
    return decision


def _departure_source_base(departure: PrimaryBattlefieldDepartureState) -> str:
    component_id = departure.affected_component_unit_instance_ids[0]
    suffix = f":{component_id}"
    if not departure.source_id.endswith(suffix) or not departure.occurrence_id.endswith(suffix):
        raise GameLifecycleError("Primary destroyed departure mutation source identity drift.")
    source_base = departure.source_id[: -len(suffix)]
    occurrence_base = departure.occurrence_id[: -len(suffix)]
    if source_base != occurrence_base:
        raise GameLifecycleError("Primary destroyed departure mutation occurrence drift.")
    return source_base


def _model_ids_grouped_by_component(
    model_ids: tuple[str, ...],
    *,
    component_by_model_id: dict[str, str],
) -> tuple[tuple[str, tuple[str, ...]], ...]:
    grouped: dict[str, list[str]] = {}
    for model_id in model_ids:
        component_id = component_by_model_id.get(model_id)
        if component_id is None:
            raise GameLifecycleError("Primary destruction mutation references an unknown model.")
        grouped.setdefault(component_id, []).append(model_id)
    return tuple(
        (component_id, tuple(sorted(grouped[component_id]))) for component_id in sorted(grouped)
    )


def _json_object(value: JsonValue, *, name: str) -> dict[str, JsonValue]:
    if not isinstance(value, dict):
        raise GameLifecycleError(f"{name} must be an object.")
    return value


def _json_identifier_list(value: JsonValue | object, *, name: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not value:
        raise GameLifecycleError(f"{name} must be a non-empty list.")
    raw_values = cast(list[object], value)
    if any(type(item) is not str or not item.strip() for item in raw_values):
        raise GameLifecycleError(f"{name} must contain identifiers.")
    identifiers = tuple(cast(str, item) for item in raw_values)
    if len(set(identifiers)) != len(identifiers):
        raise GameLifecycleError(f"{name} must not repeat identifiers.")
    return tuple(sorted(identifiers))


def _validate_destroyed_transition_batch(
    value: JsonValue | object,
    *,
    expected_model_ids: tuple[str, ...],
) -> None:
    batch = _json_object(cast(JsonValue, value), name="Destruction transition_batch")
    raw_removals = batch.get("removals")
    if not isinstance(raw_removals, list):
        raise GameLifecycleError("Destruction transition_batch removals must be a list.")
    destroyed_ids: list[str] = []
    for raw_removal in raw_removals:
        if not isinstance(raw_removal, dict):
            raise GameLifecycleError("Destruction transition removal must be an object.")
        if raw_removal.get("removal_kind") != BattlefieldRemovalKind.DESTROYED.value:
            continue
        model_id = raw_removal.get("model_instance_id")
        if type(model_id) is not str:
            raise GameLifecycleError("Destruction transition removal model is malformed.")
        destroyed_ids.append(model_id)
    if tuple(sorted(destroyed_ids)) != tuple(sorted(expected_model_ids)):
        raise GameLifecycleError("Destruction transition batch model provenance drift.")


def _validate_attributed_destruction_events(
    *,
    state: GameState,
    destruction: PrimaryUnitDestructionState,
    identity: _ScoringRulesUnitIdentity,
    events_by_id: dict[str, EventRecord],
    model_ids_by_unit_id: dict[str, tuple[str, ...]],
    rules_unit_components_by_id: dict[str, tuple[str, ...]],
) -> None:
    model_destroyed_event_id = destruction.source_model_destroyed_event_id
    if model_destroyed_event_id is None:
        raise GameLifecycleError(
            "Attributed Primary destruction requires a model_destroyed event ID."
        )
    model_destroyed_event = events_by_id.get(model_destroyed_event_id)
    if model_destroyed_event is None or model_destroyed_event.event_type != "model_destroyed":
        raise GameLifecycleError(
            "Attributed Primary destruction references no authoritative model_destroyed event."
        )
    payload = _event_payload(model_destroyed_event, event_name="model_destroyed")
    attribution = ModelDestructionAttribution.from_model_destroyed_payload(payload)
    if attribution != destruction.destruction_attribution:
        raise GameLifecycleError(
            "Attributed Primary destruction attribution drifted from model_destroyed evidence."
        )
    if "source_rules_unit_objective_proximity_witness" not in payload:
        raise GameLifecycleError(
            "Attributed Primary destruction model_destroyed evidence lacks a source witness."
        )
    raw_source_witness = payload["source_rules_unit_objective_proximity_witness"]
    event_source_witness = (
        None
        if raw_source_witness is None
        else RulesUnitObjectiveProximityWitness.from_payload(raw_source_witness)
    )
    if event_source_witness != destruction.source_rules_unit_objective_proximity_witness:
        raise GameLifecycleError(
            "Attributed Primary destruction source witness drifted from model_destroyed evidence."
        )
    if "destroyed_rules_unit_objective_proximity_witness" not in payload:
        raise GameLifecycleError(
            "Attributed Primary destruction model_destroyed evidence lacks a destroyed witness."
        )
    destroyed_witness = RulesUnitObjectiveProximityWitness.from_payload(
        payload["destroyed_rules_unit_objective_proximity_witness"]
    )
    destroyed_model_id = payload.get("model_instance_id")
    if type(destroyed_model_id) is not str:
        raise GameLifecycleError(
            "Attributed Primary destruction model drifted from model_destroyed evidence."
        )
    final_component_id = identity.component_id_for_model(destroyed_model_id)
    if final_component_id is None:
        raise GameLifecycleError(
            "Attributed Primary destruction model drifted from its starting rules unit."
        )
    _validate_destroyed_witness_identity(
        state=state,
        identity=identity,
        final_component_id=final_component_id,
        witness=destroyed_witness,
        model_ids_by_unit_id=model_ids_by_unit_id,
        rules_unit_components_by_id=rules_unit_components_by_id,
    )
    if payload.get("game_id") != destruction.game_id:
        raise GameLifecycleError(
            "Attributed Primary destruction game drifted from model_destroyed evidence."
        )
    if (
        payload.get("battle_round") != destruction.battle_round
        or type(payload.get("battle_round")) is not int
    ):
        raise GameLifecycleError(
            "Attributed Primary destruction battle round drifted from model_destroyed evidence."
        )
    if payload.get("active_player_id") != destruction.active_player_id:
        raise GameLifecycleError(
            "Attributed Primary destruction active player drifted from model_destroyed evidence."
        )
    target_unit_id = payload.get("target_unit_instance_id")
    if type(target_unit_id) is not str or not _rules_unit_identity_is_valid_for_component(
        rules_unit_instance_id=target_unit_id,
        final_component_id=final_component_id,
        scoring_identity=identity,
        rules_unit_components_by_id=rules_unit_components_by_id,
    ):
        raise GameLifecycleError(
            "Attributed Primary destruction target drifted from model_destroyed evidence."
        )
    expected_source_id = (
        f"{_PRIMARY_UNIT_DESTRUCTION_TRACKING_RULE_ID}:"
        f"{model_destroyed_event_id}:{identity.rules_unit_instance_id}"
    )
    if destruction.source_id != expected_source_id:
        raise GameLifecycleError("Attributed Primary destruction tracking source identity drift.")


def _validate_destroyed_witness_identity(
    *,
    state: GameState,
    identity: _ScoringRulesUnitIdentity,
    final_component_id: str,
    witness: RulesUnitObjectiveProximityWitness,
    model_ids_by_unit_id: dict[str, tuple[str, ...]],
    rules_unit_components_by_id: dict[str, tuple[str, ...]],
) -> None:
    if not _rules_unit_identity_is_valid_for_component(
        rules_unit_instance_id=witness.rules_unit_instance_id,
        final_component_id=final_component_id,
        scoring_identity=identity,
        rules_unit_components_by_id=rules_unit_components_by_id,
    ):
        raise GameLifecycleError(
            "Attributed Primary destruction destroyed witness rules-unit identity drift."
        )
    expected_components = rules_unit_components_by_id[witness.rules_unit_instance_id]
    if witness.component_unit_instance_ids != expected_components:
        raise GameLifecycleError(
            "Attributed Primary destruction destroyed witness component identity drift."
        )
    known_model_ids = {
        model_id
        for component_id in expected_components
        for model_id in model_ids_by_unit_id[component_id]
    }
    if any(
        model_id not in known_model_ids
        for marker_witness in witness.objective_marker_witnesses
        for model_id in marker_witness.model_instance_ids
    ):
        raise GameLifecycleError(
            "Attributed Primary destruction destroyed witness model identity drift."
        )
    known_marker_ids = {
        marker.objective_marker_id
        for marker in (() if state.mission_setup is None else state.mission_setup.objective_markers)
    }
    if any(
        marker_witness.objective_marker_id not in known_marker_ids
        for marker_witness in witness.objective_marker_witnesses
    ):
        raise GameLifecycleError(
            "Attributed Primary destruction destroyed witness objective identity drift."
        )


def _rules_unit_identity_is_valid_for_component(
    *,
    rules_unit_instance_id: str,
    final_component_id: str,
    scoring_identity: _ScoringRulesUnitIdentity,
    rules_unit_components_by_id: dict[str, tuple[str, ...]],
) -> bool:
    components = rules_unit_components_by_id.get(rules_unit_instance_id)
    if components is None:
        return False
    component_set = set(components)
    return final_component_id in component_set and component_set <= set(
        scoring_identity.component_unit_instance_ids
    )


def _validate_destruction_departure_links(
    *,
    destructions: tuple[PrimaryUnitDestructionState, ...],
    departures: tuple[PrimaryBattlefieldDepartureState, ...],
    identities_by_id: dict[str, _ScoringRulesUnitIdentity],
    model_ids_by_unit_id: dict[str, tuple[str, ...]],
    rules_unit_components_by_id: dict[str, tuple[str, ...]],
    events_by_id: dict[str, EventRecord],
    event_index_by_id: dict[str, int],
) -> None:
    departures_by_id = {departure.departure_id: departure for departure in departures}
    if len(departures_by_id) != len(departures):
        raise GameLifecycleError("Primary battlefield departure IDs must be unique.")
    consumption_by_departure_id: dict[str, str] = {}
    linked_by_destruction_id: dict[str, tuple[PrimaryBattlefieldDepartureState, ...]] = {}
    for destruction in destructions:
        identity = identities_by_id[destruction.destroyed_unit_instance_id]
        linked: list[PrimaryBattlefieldDepartureState] = []
        for departure_id in destruction.source_battlefield_departure_ids:
            departure = departures_by_id.get(departure_id)
            if departure is None:
                raise GameLifecycleError(
                    "Primary destruction references no authoritative battlefield departure."
                )
            prior_consumer = consumption_by_departure_id.get(departure_id)
            if prior_consumer is not None:
                raise GameLifecycleError(
                    "Primary battlefield departure cannot evidence multiple destructions."
                )
            consumption_by_departure_id[departure_id] = destruction.destruction_id
            _validate_linked_departure(
                destruction=destruction,
                identity=identity,
                departure=departure,
                model_ids_by_unit_id=model_ids_by_unit_id,
                rules_unit_components_by_id=rules_unit_components_by_id,
            )
            linked.append(departure)
        if destruction.unattributed_cause is PrimaryUnattributedDestructionCause.RESERVE_DEADLINE:
            if linked:
                raise GameLifecycleError(
                    "Reserve-deadline Primary destruction cannot have "
                    "battlefield-departure evidence."
                )
        elif not linked:
            raise GameLifecycleError(
                "Primary destruction requires explicit DESTROYED battlefield-departure evidence."
            )
        linked_by_destruction_id[destruction.destruction_id] = tuple(linked)

    for destruction in destructions:
        if destruction.unattributed_cause is PrimaryUnattributedDestructionCause.RESERVE_DEADLINE:
            continue
        identity = identities_by_id[destruction.destroyed_unit_instance_id]
        linked_departures = linked_by_destruction_id[destruction.destruction_id]
        _validate_completion_edge(
            destruction=destruction,
            identity=identity,
            linked_departures=linked_departures,
            events_by_id=events_by_id,
            event_index_by_id=event_index_by_id,
        )
        if (
            len(
                tuple(
                    candidate
                    for candidate in destructions
                    if candidate.destroyed_unit_instance_id == identity.rules_unit_instance_id
                )
            )
            == 1
        ):
            linked_model_ids = {
                model_id
                for departure in linked_departures
                for model_id in departure.removed_model_instance_ids
            }
            if not set(identity.starting_model_instance_ids) <= linked_model_ids:
                raise GameLifecycleError(
                    "Primary destruction departure edges do not cover its starting rules unit."
                )
        _validate_no_omitted_event_backed_departures(
            destruction=destruction,
            identity=identity,
            all_departures=departures,
            linked_departures=linked_departures,
            consumption_by_departure_id=consumption_by_departure_id,
            destructions=destructions,
            events_by_id=events_by_id,
            event_index_by_id=event_index_by_id,
            rules_unit_components_by_id=rules_unit_components_by_id,
        )


def _validate_linked_departure(
    *,
    destruction: PrimaryUnitDestructionState,
    identity: _ScoringRulesUnitIdentity,
    departure: PrimaryBattlefieldDepartureState,
    model_ids_by_unit_id: dict[str, tuple[str, ...]],
    rules_unit_components_by_id: dict[str, tuple[str, ...]],
) -> None:
    if departure.removal_kind is not BattlefieldRemovalKind.DESTROYED:
        raise GameLifecycleError(
            "Primary destruction departure edge must reference a DESTROYED occurrence."
        )
    if departure.owner_player_id != destruction.destroyed_player_id:
        raise GameLifecycleError("Primary destruction departure owner identity drift.")
    if len(departure.affected_component_unit_instance_ids) != 1:
        raise GameLifecycleError(
            "Primary destruction departure must identify one affected physical unit."
        )
    component_id = departure.affected_component_unit_instance_ids[0]
    if component_id not in identity.component_unit_instance_ids:
        raise GameLifecycleError(
            "Primary destruction departure lies outside its starting rules unit."
        )
    departure_rules_components = rules_unit_components_by_id.get(departure.rules_unit_instance_id)
    if (
        departure_rules_components is None
        or departure.component_unit_instance_ids != departure_rules_components
        or not set(departure.affected_component_unit_instance_ids)
        <= set(departure_rules_components)
        or not set(departure.departed_component_unit_instance_ids)
        <= set(departure.affected_component_unit_instance_ids)
        or not set(departure_rules_components) <= set(identity.component_unit_instance_ids)
    ):
        raise GameLifecycleError("Primary destruction departure rules-unit identity drift.")
    removed_model_ids = set(departure.removed_model_instance_ids)
    if not removed_model_ids <= set(model_ids_by_unit_id[component_id]):
        raise GameLifecycleError(
            "Primary destruction departure references a model outside its physical unit."
        )
    if not removed_model_ids.intersection(identity.model_ids_for_component(component_id)):
        raise GameLifecycleError("Primary destruction departure does not contain a starting model.")
    if not departure.source_id.endswith(f":{component_id}"):
        raise GameLifecycleError("Primary destruction departure source identity drift.")
    if not departure.occurrence_id.endswith(f":{component_id}"):
        raise GameLifecycleError("Primary destruction departure occurrence identity drift.")


def _validate_completion_edge(
    *,
    destruction: PrimaryUnitDestructionState,
    identity: _ScoringRulesUnitIdentity,
    linked_departures: tuple[PrimaryBattlefieldDepartureState, ...],
    events_by_id: dict[str, EventRecord],
    event_index_by_id: dict[str, int],
) -> None:
    source_suffix = f":{identity.rules_unit_instance_id}"
    if not destruction.source_id.endswith(source_suffix):
        raise GameLifecycleError("Primary destruction scoring source identity drift.")
    occurrence_source_id = destruction.source_id[: -len(source_suffix)]
    final_model_id: str | None = None
    final_component_id: str | None = None
    if destruction.destruction_attribution is not None:
        event_id = destruction.source_model_destroyed_event_id
        if event_id is None or event_id not in event_index_by_id:
            raise GameLifecycleError(
                "Attributed Primary destruction completion event identity drift."
            )
        expected_occurrence_source_id = f"{_PRIMARY_UNIT_DESTRUCTION_TRACKING_RULE_ID}:{event_id}"
        if occurrence_source_id != expected_occurrence_source_id:
            raise GameLifecycleError("Attributed Primary destruction completion source drift.")
        final_event = events_by_id[event_id]
        final_model_payload = _event_payload(final_event, event_name="model_destroyed")
        raw_final_model_id = final_model_payload.get("model_instance_id")
        if type(raw_final_model_id) is not str:
            raise GameLifecycleError(
                "Attributed Primary destruction lacks its final model identity."
            )
        final_model_id = raw_final_model_id
        final_component_id = identity.component_id_for_model(final_model_id)
        if final_component_id is None:
            raise GameLifecycleError(
                "Attributed Primary destruction final model lies outside its starting unit."
            )
    final_candidates = tuple(
        departure
        for departure in linked_departures
        for component_id in departure.affected_component_unit_instance_ids
        if departure.source_id == f"{occurrence_source_id}:{component_id}"
        and (final_component_id is None or component_id == final_component_id)
        and (final_model_id is None or final_model_id in departure.removed_model_instance_ids)
    )
    if destruction.destruction_attribution is not None and len(final_candidates) != 1:
        raise GameLifecycleError(
            "Primary destruction requires exactly one final battlefield-departure edge."
        )
    if destruction.destruction_attribution is None and not final_candidates:
        raise GameLifecycleError(
            "Unattributed Primary destruction requires a final battlefield-departure edge."
        )
    if any(
        departure.battle_round != destruction.battle_round
        or departure.active_player_id != destruction.active_player_id
        or departure.phase != destruction.phase
        for departure in final_candidates
    ):
        raise GameLifecycleError("Primary destruction final battlefield-departure timing drift.")


def _validate_no_omitted_event_backed_departures(
    *,
    destruction: PrimaryUnitDestructionState,
    identity: _ScoringRulesUnitIdentity,
    all_departures: tuple[PrimaryBattlefieldDepartureState, ...],
    linked_departures: tuple[PrimaryBattlefieldDepartureState, ...],
    consumption_by_departure_id: dict[str, str],
    destructions: tuple[PrimaryUnitDestructionState, ...],
    events_by_id: dict[str, EventRecord],
    event_index_by_id: dict[str, int],
    rules_unit_components_by_id: dict[str, tuple[str, ...]],
) -> None:
    final_event_id = destruction.source_model_destroyed_event_id
    if final_event_id is None:
        return
    final_index = event_index_by_id[final_event_id]
    prior_consumed_ids = {
        departure_id
        for departure_id, consumer_id in consumption_by_departure_id.items()
        for consumer in destructions
        if consumer.destruction_id == consumer_id
        and consumer.source_model_destroyed_event_id is not None
        and event_index_by_id[consumer.source_model_destroyed_event_id] < final_index
    }
    expected_ids = {
        departure.departure_id
        for departure in all_departures
        if departure.removal_kind is BattlefieldRemovalKind.DESTROYED
        and set(departure.affected_component_unit_instance_ids)
        <= set(identity.component_unit_instance_ids)
        and departure.departure_id not in prior_consumed_ids
        and (event_id := _event_id_from_departure_source(departure)) is not None
        and event_id in event_index_by_id
        and event_index_by_id[event_id] <= final_index
    }
    linked_event_backed_ids = {
        departure.departure_id
        for departure in linked_departures
        if _event_id_from_departure_source(departure) is not None
    }
    if linked_event_backed_ids != expected_ids:
        raise GameLifecycleError(
            "Primary destruction omitted or invented event-backed departure edges."
        )
    for departure in linked_departures:
        event_id = _event_id_from_departure_source(departure)
        if event_id is None:
            continue
        event = events_by_id.get(event_id)
        if event is None or event.event_type != "model_destroyed":
            raise GameLifecycleError(
                "Primary destruction departure references no model_destroyed event."
            )
        payload = _event_payload(event, event_name="model_destroyed")
        model_id = payload.get("model_instance_id")
        if type(model_id) is not str or departure.removed_model_instance_ids != (model_id,):
            raise GameLifecycleError("Primary destruction departure model event identity drift.")
        component_id = identity.component_id_for_model(model_id)
        target_id = payload.get("target_unit_instance_id")
        if (
            component_id is None
            or type(target_id) is not str
            or not _rules_unit_identity_is_valid_for_component(
                rules_unit_instance_id=target_id,
                final_component_id=component_id,
                scoring_identity=identity,
                rules_unit_components_by_id=rules_unit_components_by_id,
            )
        ):
            raise GameLifecycleError("Primary destruction departure logical target identity drift.")


def _event_id_from_departure_source(
    departure: PrimaryBattlefieldDepartureState,
) -> str | None:
    if len(departure.affected_component_unit_instance_ids) != 1:
        return None
    component_id = departure.affected_component_unit_instance_ids[0]
    prefix = f"{_PRIMARY_UNIT_DESTRUCTION_TRACKING_RULE_ID}:"
    suffix = f":{component_id}"
    if (
        not departure.source_id.startswith(prefix)
        or not departure.source_id.endswith(suffix)
        or not departure.occurrence_id.endswith(suffix)
    ):
        return None
    event_id = departure.occurrence_id[: -len(suffix)]
    if departure.source_id != f"{prefix}{event_id}{suffix}":
        return None
    return event_id or None


def _validate_turn_start_recorded_events(
    *,
    state: GameState,
    event_records: tuple[EventRecord, ...],
) -> None:
    objective_states_by_occurrence = {
        (value.game_id, value.active_player_id, value.battle_round): value
        for value in state.primary_objective_turn_start_states
    }
    snapshots_by_occurrence = {
        (value.game_id, value.active_player_id, value.battle_round): value
        for value in state.primary_rules_unit_turn_start_snapshots
    }
    if len(objective_states_by_occurrence) != len(state.primary_objective_turn_start_states) or len(
        snapshots_by_occurrence
    ) != len(state.primary_rules_unit_turn_start_snapshots):
        raise GameLifecycleError("Primary turn-start evidence occurrence is duplicated.")
    if set(objective_states_by_occurrence) != set(snapshots_by_occurrence):
        raise GameLifecycleError(
            "Primary turn-start objective and position evidence occurrences are unpaired."
        )
    events_by_occurrence: dict[tuple[str, str, int], list[EventRecord]] = {}
    for record in event_records:
        if record.event_type != PRIMARY_TURN_START_EVIDENCE_RECORDED_EVENT:
            continue
        payload = _event_payload(record, event_name="primary turn-start evidence")
        game_id = payload.get("game_id")
        active_player_id = payload.get("active_player_id")
        battle_round = payload.get("battle_round")
        if (
            type(game_id) is not str
            or type(active_player_id) is not str
            or type(battle_round) is not int
        ):
            raise GameLifecycleError(
                "Primary turn-start recorded event occurrence identity is malformed."
            )
        occurrence = (game_id, active_player_id, battle_round)
        events_by_occurrence.setdefault(occurrence, []).append(record)
    if set(events_by_occurrence) != set(objective_states_by_occurrence):
        raise GameLifecycleError(
            "Primary turn-start evidence requires one authoritative recorded event."
        )
    for occurrence, objective_state in objective_states_by_occurrence.items():
        matching = events_by_occurrence[occurrence]
        if len(matching) != 1:
            raise GameLifecycleError(
                "Primary turn-start evidence requires exactly one recorded event."
            )
        snapshot = snapshots_by_occurrence[occurrence]
        expected_payload: dict[str, JsonValue] = {
            "game_id": objective_state.game_id,
            "battle_round": objective_state.battle_round,
            "active_player_id": objective_state.active_player_id,
            "primary_objective_turn_start_state": cast(
                dict[str, JsonValue], objective_state.to_payload()
            ),
            "primary_rules_unit_turn_start_snapshot": cast(
                dict[str, JsonValue], snapshot.to_payload()
            ),
        }
        if matching[0].payload != expected_payload:
            raise GameLifecycleError("Primary turn-start recorded-event payload drift.")


def _validate_starting_attached_unit_muster_events(
    *,
    state: GameState,
    event_records: tuple[EventRecord, ...],
) -> None:
    state_records_by_id = {
        record.attached_unit_instance_id: record for record in state.starting_attached_unit_records
    }
    event_payload_by_id: dict[str, tuple[str, dict[str, JsonValue]]] = {}
    for event in event_records:
        if event.event_type != "army_mustered":
            continue
        payload = _event_payload(event, event_name="army_mustered")
        if payload.get("game_id") != state.game_id:
            raise GameLifecycleError("Starting Attached Unit muster event game drift.")
        player_id = payload.get("player_id")
        raw_records = payload.get("starting_attached_unit_records")
        if type(player_id) is not str or not isinstance(raw_records, list):
            raise GameLifecycleError("Starting Attached Unit muster event payload is malformed.")
        for raw_record in raw_records:
            if not isinstance(raw_record, dict):
                raise GameLifecycleError("Starting Attached Unit muster event record is malformed.")
            attached_unit_id = raw_record.get("attached_unit_instance_id")
            if type(attached_unit_id) is not str:
                raise GameLifecycleError(
                    "Starting Attached Unit muster event lacks an attached-unit ID."
                )
            if attached_unit_id in event_payload_by_id:
                raise GameLifecycleError(
                    "Starting Attached Unit has duplicate army_mustered provenance."
                )
            event_payload_by_id[attached_unit_id] = (player_id, raw_record)
    if set(event_payload_by_id) != set(state_records_by_id):
        raise GameLifecycleError("Starting Attached Unit requires exact army_mustered provenance.")
    for attached_unit_id, state_record in state_records_by_id.items():
        player_id, event_record_payload = event_payload_by_id[attached_unit_id]
        if player_id != state_record.player_id:
            raise GameLifecycleError("Starting Attached Unit muster owner drift.")
        if event_record_payload != state_record.to_payload():
            raise GameLifecycleError("Starting Attached Unit muster mapping drift.")


def _validate_departure_recorded_events(
    *,
    departures: tuple[PrimaryBattlefieldDepartureState, ...],
    event_records: tuple[EventRecord, ...],
) -> None:
    departures_by_id = {departure.departure_id: departure for departure in departures}
    events_by_departure_id: dict[str, list[EventRecord]] = {}
    for record in event_records:
        if record.event_type != PRIMARY_BATTLEFIELD_DEPARTURE_RECORDED_EVENT:
            continue
        payload = _event_payload(record, event_name="primary battlefield departure")
        raw_departure = payload.get("primary_battlefield_departure_state")
        if not isinstance(raw_departure, dict):
            raise GameLifecycleError(
                "Primary battlefield departure recorded event requires a state payload."
            )
        departure_id = raw_departure.get("departure_id")
        if type(departure_id) is not str:
            raise GameLifecycleError(
                "Primary battlefield departure recorded event requires a departure ID."
            )
        events_by_departure_id.setdefault(departure_id, []).append(record)
    if set(events_by_departure_id) != set(departures_by_id):
        raise GameLifecycleError(
            "Primary battlefield departure requires one authoritative recorded event."
        )
    for departure_id, departure in departures_by_id.items():
        matching = events_by_departure_id[departure_id]
        if len(matching) != 1:
            raise GameLifecycleError(
                "Primary battlefield departure requires exactly one recorded event."
            )
        expected_payload: dict[str, JsonValue] = {
            "game_id": departure.game_id,
            "battle_round": departure.battle_round,
            "active_player_id": departure.active_player_id,
            "phase": departure.phase,
            "primary_battlefield_departure_state": cast(
                dict[str, JsonValue], departure.to_payload()
            ),
        }
        if matching[0].payload != expected_payload:
            raise GameLifecycleError("Primary battlefield departure recorded-event payload drift.")


def _validate_recorded_destruction_events(
    *,
    destructions: tuple[PrimaryUnitDestructionState, ...],
    event_records: tuple[EventRecord, ...],
) -> None:
    destructions_by_id = {destruction.destruction_id: destruction for destruction in destructions}
    events_by_destruction_id: dict[str, list[EventRecord]] = {}
    for record in event_records:
        if record.event_type != PRIMARY_UNIT_DESTRUCTION_RECORDED_EVENT:
            continue
        payload = _event_payload(record, event_name="primary_unit_destruction_recorded")
        raw_state = payload.get("primary_unit_destruction_state")
        if not isinstance(raw_state, dict):
            raise GameLifecycleError("Primary destruction recorded event requires a state payload.")
        destruction_id = raw_state.get("destruction_id")
        if type(destruction_id) is not str:
            raise GameLifecycleError(
                "Primary destruction recorded event requires a destruction ID."
            )
        events_by_destruction_id.setdefault(destruction_id, []).append(record)
    if set(events_by_destruction_id) != set(destructions_by_id):
        raise GameLifecycleError("Primary destruction requires one authoritative recorded event.")
    for destruction_id, destruction in destructions_by_id.items():
        matching = events_by_destruction_id[destruction_id]
        if len(matching) != 1:
            raise GameLifecycleError(
                "Primary destruction historical state requires exactly one recorded event."
            )
        expected_payload: dict[str, JsonValue] = {
            "game_id": destruction.game_id,
            "battle_round": destruction.battle_round,
            "active_player_id": destruction.active_player_id,
            "phase": destruction.phase,
            "source_model_destroyed_event_id": (destruction.source_model_destroyed_event_id),
            "primary_unit_destruction_state": cast(dict[str, JsonValue], destruction.to_payload()),
        }
        if matching[0].payload != expected_payload:
            raise GameLifecycleError("Primary destruction recorded-event payload drift.")


def _event_payload(record: EventRecord, *, event_name: str) -> dict[str, JsonValue]:
    if not isinstance(record.payload, dict):
        raise GameLifecycleError(f"{event_name} event payload must be an object.")
    return record.payload


__all__ = ("validate_primary_historical_event_integrity",)
