from __future__ import annotations

from typing import TYPE_CHECKING, cast

from warhammer40k_core.engine.battlefield_state import (
    BattlefieldRemovalKind,
    BattlefieldTransitionBatch,
)
from warhammer40k_core.engine.event_log import EventLog, EventRecord, JsonValue, validate_json_value
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.primary_battlefield_departure import (
    PrimaryBattlefieldDepartureState,
)
from warhammer40k_core.engine.primary_reserve_entry_provider import (
    PRIMARY_RESERVE_ENTRY_PROVIDER_RESOLVED_EVENT,
    PrimaryReserveEntryProvider,
)
from warhammer40k_core.engine.primary_turn_start_evidence import (
    PrimaryRulesUnitTurnStartSnapshot,
)
from warhammer40k_core.engine.reserves import ReserveKind, ReserveState
from warhammer40k_core.engine.scoring import (
    PrimaryObjectiveTurnStartState,
    PrimaryUnitDestructionState,
)

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState


PRIMARY_BATTLEFIELD_DEPARTURE_RECORDED_EVENT = "primary_battlefield_departure_recorded"
PRIMARY_RESERVE_ENTRY_MUTATION_EVENT = "primary_reserve_entry_mutated"
PRIMARY_RESERVE_ENTRY_SOURCE_BINDINGS_KEY = "primary_reserve_entry_bindings"
PRIMARY_TURN_START_EVIDENCE_RECORDED_EVENT = "primary_turn_start_evidence_recorded"
PRIMARY_UNIT_DESTRUCTION_RECORDED_EVENT = "primary_unit_destruction_recorded"


def record_primary_battlefield_departure_event(
    *,
    event_log: EventLog,
    departure: PrimaryBattlefieldDepartureState,
) -> EventRecord:
    """Append the public immutable event that authenticates one departure row."""
    _require_event_log(event_log)
    if type(departure) is not PrimaryBattlefieldDepartureState:
        raise GameLifecycleError(
            "Primary battlefield departure event requires typed departure evidence."
        )
    return event_log.append(
        PRIMARY_BATTLEFIELD_DEPARTURE_RECORDED_EVENT,
        {
            "game_id": departure.game_id,
            "battle_round": departure.battle_round,
            "active_player_id": departure.active_player_id,
            "phase": departure.phase,
            "primary_battlefield_departure_state": departure.to_payload(),
        },
    )


def reserve_entry_evidence_payload(reserve_state: ReserveState) -> dict[str, JsonValue]:
    """Return the immutable fields that identify one during-battle reserve entry."""
    if type(reserve_state) is not ReserveState:
        raise GameLifecycleError("Reserve-entry evidence requires typed ReserveState.")
    if (
        reserve_state.reserve_kind is not ReserveKind.STRATEGIC_RESERVES
        or reserve_state.entered_reserves_battle_round is None
        or reserve_state.entered_reserves_phase is None
    ):
        raise GameLifecycleError(
            "Reserve-entry evidence requires a during-battle Strategic Reserves state."
        )
    return {
        "player_id": reserve_state.player_id,
        "unit_instance_id": reserve_state.unit_instance_id,
        "reserve_origin": reserve_state.reserve_origin.value,
        "reserve_kind": reserve_state.reserve_kind.value,
        "source_rule_ids": list(reserve_state.source_rule_ids),
        "points_contribution": reserve_state.points_contribution,
        "entered_reserves_battle_round": reserve_state.entered_reserves_battle_round,
        "entered_reserves_phase": reserve_state.entered_reserves_phase,
        "required_arrival_battle_round": reserve_state.required_arrival_battle_round,
        "required_arrival_phase": reserve_state.required_arrival_phase,
        "required_arrival_source_rule_id": reserve_state.required_arrival_source_rule_id,
        "required_arrival_placement_kind": reserve_state.required_arrival_placement_kind,
        "destruction_deadline_policy": validate_json_value(
            reserve_state.destruction_deadline_policy.to_payload()
        ),
        "embarked_unit_instance_ids": list(reserve_state.embarked_unit_instance_ids),
    }


def record_primary_reserve_entry_mutation_event(
    *,
    event_log: EventLog,
    departure: PrimaryBattlefieldDepartureState,
    reserve_state: ReserveState,
    provider: PrimaryReserveEntryProvider | None = None,
    transition_batch: BattlefieldTransitionBatch | None,
) -> EventRecord:
    """Record the engine-owned reserve mutation that precedes derived departure evidence."""
    _require_event_log(event_log)
    if type(departure) is not PrimaryBattlefieldDepartureState or (
        departure.removal_kind is not BattlefieldRemovalKind.INTO_RESERVES
    ):
        raise GameLifecycleError(
            "Reserve-entry mutation event requires typed INTO_RESERVES departure evidence."
        )
    reserve_entry = reserve_entry_evidence_payload(reserve_state)
    if (
        reserve_state.player_id != departure.owner_player_id
        or reserve_state.unit_instance_id != departure.rules_unit_instance_id
        or reserve_state.entered_reserves_battle_round != departure.battle_round
        or reserve_state.entered_reserves_phase != departure.phase
    ):
        raise GameLifecycleError("Reserve-entry mutation identity drifted from its departure.")
    if transition_batch is None:
        if type(provider) is not PrimaryReserveEntryProvider or (
            provider.player_id != departure.owner_player_id
            or provider.target_rules_unit_instance_id != departure.rules_unit_instance_id
            or provider.occurrence_id != departure.occurrence_id
            or departure.source_id != provider.occurrence_id
            or reserve_state.reserve_origin is not provider.reserve_origin
            or reserve_state.source_rule_ids != (provider.source_rule_id,)
        ):
            raise GameLifecycleError("Reserve-entry mutation provider identity drift.")
    elif provider is not None:
        raise GameLifecycleError("Aircraft reserve-entry mutation cannot name an ability provider.")
    transition_payload: JsonValue = None
    if transition_batch is not None:
        if type(transition_batch) is not BattlefieldTransitionBatch:
            raise GameLifecycleError("Reserve-entry transition must be typed.")
        if (
            transition_batch.placements
            or transition_batch.displacements
            or {removal.model_instance_id for removal in transition_batch.removals}
            != set(departure.removed_model_instance_ids)
            or any(
                removal.removal_kind is not BattlefieldRemovalKind.INTO_RESERVES
                for removal in transition_batch.removals
            )
        ):
            raise GameLifecycleError("Reserve-entry transition drifted from its departure.")
        transition_payload = validate_json_value(transition_batch.to_payload())
    return event_log.append(
        PRIMARY_RESERVE_ENTRY_MUTATION_EVENT,
        {
            "game_id": departure.game_id,
            "battle_round": departure.battle_round,
            "active_player_id": departure.active_player_id,
            "phase": departure.phase,
            "occurrence_id": departure.occurrence_id,
            "source_id": departure.source_id,
            "removed_model_instance_ids": list(departure.removed_model_instance_ids),
            "provider": None if provider is None else provider.to_payload(),
            "reserve_entry_state": reserve_entry,
            "transition_batch": transition_payload,
        },
    )


def primary_reserve_entry_source_terminal_bindings_payload(
    entries: tuple[tuple[PrimaryReserveEntryProvider, ReserveState], ...],
) -> dict[str, JsonValue]:
    """Build the standardized binding carried by a real source terminal event."""
    if type(entries) is not tuple or not entries:
        raise GameLifecycleError("Reserve-entry source terminal requires provider entries.")
    bindings: list[JsonValue] = []
    occurrence_ids: set[str] = set()
    for provider, reserve_state in entries:
        if (
            type(provider) is not PrimaryReserveEntryProvider
            or type(reserve_state) is not ReserveState
        ):
            raise GameLifecycleError("Reserve-entry source terminal entries must be typed.")
        if (
            provider.player_id != reserve_state.player_id
            or provider.target_rules_unit_instance_id != reserve_state.unit_instance_id
            or provider.reserve_origin is not reserve_state.reserve_origin
            or reserve_state.source_rule_ids != (provider.source_rule_id,)
        ):
            raise GameLifecycleError("Reserve-entry source terminal binding identity drift.")
        if provider.occurrence_id in occurrence_ids:
            raise GameLifecycleError("Reserve-entry source terminal occurrence is duplicated.")
        occurrence_ids.add(provider.occurrence_id)
        bindings.append(
            {
                "occurrence_id": provider.occurrence_id,
                "provider": provider.to_payload(),
                "reserve_entry_state": reserve_entry_evidence_payload(reserve_state),
            }
        )
    return {PRIMARY_RESERVE_ENTRY_SOURCE_BINDINGS_KEY: bindings}


def record_primary_reserve_entry_provider_terminal_event(
    *,
    event_log: EventLog,
    provider: PrimaryReserveEntryProvider,
    reserve_state: ReserveState,
    source_terminal_event: EventRecord,
) -> EventRecord:
    """Close one provider occurrence after its real semantic terminal event."""
    _require_event_log(event_log)
    if (
        type(provider) is not PrimaryReserveEntryProvider
        or type(reserve_state) is not ReserveState
        or type(source_terminal_event) is not EventRecord
    ):
        raise GameLifecycleError("Reserve-entry provider terminal requires typed evidence.")
    if source_terminal_event.event_type != provider.source_terminal_event_type:
        raise GameLifecycleError("Reserve-entry source terminal event type drift.")
    if source_terminal_event not in event_log.records:
        raise GameLifecycleError("Reserve-entry source terminal is not in the event log.")
    expected_payload = primary_reserve_entry_source_terminal_bindings_payload(
        ((provider, reserve_state),)
    )
    raw_expected_bindings = expected_payload[PRIMARY_RESERVE_ENTRY_SOURCE_BINDINGS_KEY]
    if not isinstance(raw_expected_bindings, list) or len(raw_expected_bindings) != 1:
        raise GameLifecycleError("Reserve-entry source terminal binding builder drift.")
    expected_binding = raw_expected_bindings[0]
    source_payload = source_terminal_event.payload
    if not isinstance(source_payload, dict):
        raise GameLifecycleError("Reserve-entry source terminal payload must be an object.")
    raw_bindings = source_payload.get(PRIMARY_RESERVE_ENTRY_SOURCE_BINDINGS_KEY)
    if not isinstance(raw_bindings, list) or raw_bindings.count(expected_binding) != 1:
        raise GameLifecycleError("Reserve-entry source terminal lacks its exact provider binding.")
    return event_log.append(
        PRIMARY_RESERVE_ENTRY_PROVIDER_RESOLVED_EVENT,
        {
            "occurrence_id": provider.occurrence_id,
            "provider": provider.to_payload(),
            "reserve_entry_state": reserve_entry_evidence_payload(reserve_state),
            "source_terminal_event_id": source_terminal_event.event_id,
            "source_terminal_event_type": source_terminal_event.event_type,
        },
    )


def record_primary_turn_start_evidence_event(
    *,
    event_log: EventLog,
    objective_state: PrimaryObjectiveTurnStartState,
    position_snapshot: PrimaryRulesUnitTurnStartSnapshot,
) -> EventRecord:
    """Bind one turn-start objective result to its exact spatial snapshot."""
    _require_event_log(event_log)
    if type(objective_state) is not PrimaryObjectiveTurnStartState:
        raise GameLifecycleError("Primary turn-start event requires typed objective evidence.")
    if type(position_snapshot) is not PrimaryRulesUnitTurnStartSnapshot:
        raise GameLifecycleError("Primary turn-start event requires a typed position snapshot.")
    if (
        objective_state.game_id != position_snapshot.game_id
        or objective_state.active_player_id != position_snapshot.active_player_id
        or objective_state.battle_round != position_snapshot.battle_round
    ):
        raise GameLifecycleError(
            "Primary turn-start objective and position evidence occurrence drift."
        )
    return event_log.append(
        PRIMARY_TURN_START_EVIDENCE_RECORDED_EVENT,
        {
            "game_id": objective_state.game_id,
            "battle_round": objective_state.battle_round,
            "active_player_id": objective_state.active_player_id,
            "primary_objective_turn_start_state": objective_state.to_payload(),
            "primary_rules_unit_turn_start_snapshot": position_snapshot.to_payload(),
        },
    )


def record_primary_unit_destruction_event(
    *,
    event_log: EventLog,
    destruction: PrimaryUnitDestructionState,
) -> EventRecord:
    """Append the public immutable event that authenticates one destruction row."""
    _require_event_log(event_log)
    if type(destruction) is not PrimaryUnitDestructionState:
        raise GameLifecycleError(
            "Primary unit destruction event requires typed destruction evidence."
        )
    return event_log.append(
        PRIMARY_UNIT_DESTRUCTION_RECORDED_EVENT,
        {
            "game_id": destruction.game_id,
            "battle_round": destruction.battle_round,
            "active_player_id": destruction.active_player_id,
            "phase": destruction.phase,
            "source_model_destroyed_event_id": (destruction.source_model_destroyed_event_id),
            "primary_unit_destruction_state": destruction.to_payload(),
        },
    )


def record_new_primary_battlefield_departure_events(
    *,
    state: GameState,
    event_log: EventLog,
    departure_ids_before: tuple[str, ...],
) -> tuple[EventRecord, ...]:
    """Record precisely the departure rows created by one accepted mutation."""
    known_ids = _identifier_set(
        departure_ids_before,
        field_name="Primary departure prior IDs",
    )
    new_departures = tuple(
        departure
        for departure in state.primary_battlefield_departure_states
        if departure.departure_id not in known_ids
    )
    return tuple(
        record_primary_battlefield_departure_event(
            event_log=event_log,
            departure=departure,
        )
        for departure in new_departures
    )


def record_new_primary_unit_destruction_events(
    *,
    state: GameState,
    event_log: EventLog,
    destruction_ids_before: tuple[str, ...],
) -> tuple[EventRecord, ...]:
    """Record precisely the destruction rows created by one accepted mutation."""
    known_ids = _identifier_set(
        destruction_ids_before,
        field_name="Primary destruction prior IDs",
    )
    new_destructions = tuple(
        destruction
        for destruction in state.primary_unit_destruction_states
        if destruction.destruction_id not in known_ids
    )
    return tuple(
        record_primary_unit_destruction_event(
            event_log=event_log,
            destruction=destruction,
        )
        for destruction in new_destructions
    )


def record_new_primary_turn_start_evidence_events(
    *,
    state: GameState,
    event_log: EventLog,
    objective_state_ids_before: tuple[str, ...],
    snapshot_ids_before: tuple[str, ...],
) -> tuple[EventRecord, ...]:
    """Record every objective/snapshot pair created by one turn boundary."""
    known_objective_ids = _identifier_set(
        objective_state_ids_before,
        field_name="Primary turn-start prior objective-state IDs",
    )
    known_snapshot_ids = _identifier_set(
        snapshot_ids_before,
        field_name="Primary turn-start prior snapshot IDs",
    )
    new_objective_states = tuple(
        state_value
        for state_value in state.primary_objective_turn_start_states
        if state_value.state_id not in known_objective_ids
    )
    new_snapshots = tuple(
        snapshot
        for snapshot in state.primary_rules_unit_turn_start_snapshots
        if snapshot.snapshot_id not in known_snapshot_ids
    )
    if len(new_objective_states) != len(new_snapshots):
        raise GameLifecycleError(
            "Primary turn-start mutation produced unpaired objective and position evidence."
        )
    snapshots_by_occurrence = {
        (snapshot.game_id, snapshot.active_player_id, snapshot.battle_round): snapshot
        for snapshot in new_snapshots
    }
    if len(snapshots_by_occurrence) != len(new_snapshots):
        raise GameLifecycleError(
            "Primary turn-start mutation produced duplicate position occurrences."
        )
    records: list[EventRecord] = []
    for objective_state in new_objective_states:
        occurrence = (
            objective_state.game_id,
            objective_state.active_player_id,
            objective_state.battle_round,
        )
        position_snapshot = snapshots_by_occurrence.get(occurrence)
        if position_snapshot is None:
            raise GameLifecycleError(
                "Primary turn-start mutation produced mismatched objective and position evidence."
            )
        records.append(
            record_primary_turn_start_evidence_event(
                event_log=event_log,
                objective_state=objective_state,
                position_snapshot=position_snapshot,
            )
        )
    return tuple(records)


def _require_event_log(value: object) -> EventLog:
    if type(value) is not EventLog:
        raise GameLifecycleError("Primary historical evidence requires EventLog.")
    return value


def _identifier_set(value: object, *, field_name: str) -> set[str]:
    if type(value) is not tuple:
        raise GameLifecycleError(f"{field_name} must be an identifier tuple.")
    raw_identifiers = cast(tuple[object, ...], value)
    if any(type(identifier) is not str or not identifier.strip() for identifier in raw_identifiers):
        raise GameLifecycleError(f"{field_name} must be an identifier tuple.")
    identifiers = {cast(str, identifier) for identifier in raw_identifiers}
    if len(identifiers) != len(raw_identifiers):
        raise GameLifecycleError(f"{field_name} must be unique.")
    return identifiers


__all__ = (
    "PRIMARY_BATTLEFIELD_DEPARTURE_RECORDED_EVENT",
    "PRIMARY_RESERVE_ENTRY_MUTATION_EVENT",
    "PRIMARY_RESERVE_ENTRY_SOURCE_BINDINGS_KEY",
    "PRIMARY_TURN_START_EVIDENCE_RECORDED_EVENT",
    "PRIMARY_UNIT_DESTRUCTION_RECORDED_EVENT",
    "primary_reserve_entry_source_terminal_bindings_payload",
    "record_new_primary_battlefield_departure_events",
    "record_new_primary_turn_start_evidence_events",
    "record_new_primary_unit_destruction_events",
    "record_primary_battlefield_departure_event",
    "record_primary_reserve_entry_mutation_event",
    "record_primary_reserve_entry_provider_terminal_event",
    "record_primary_turn_start_evidence_event",
    "record_primary_unit_destruction_event",
    "reserve_entry_evidence_payload",
)
