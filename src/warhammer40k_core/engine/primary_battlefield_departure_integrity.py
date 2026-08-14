from __future__ import annotations

from typing import TYPE_CHECKING, cast

from warhammer40k_core.engine.battlefield_state import BattlefieldRemovalKind
from warhammer40k_core.engine.decision_record import DecisionRecord
from warhammer40k_core.engine.event_log import EventRecord, JsonValue
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.phases.movement_model import (
    SELECT_EMBARK_TRANSPORT_DECISION_TYPE,
    SELECT_MOVEMENT_ACTION_DECISION_TYPE,
)
from warhammer40k_core.engine.primary_battlefield_departure import (
    PrimaryBattlefieldDepartureState,
)
from warhammer40k_core.engine.primary_historical_events import (
    PRIMARY_BATTLEFIELD_DEPARTURE_RECORDED_EVENT,
    PRIMARY_RESERVE_ENTRY_MUTATION_EVENT,
    reserve_entry_evidence_payload,
)

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState


_EMBARK_MUTATION_EVENT = "unit_embarked"
_TRANSITION_KEYS = frozenset(("placements", "removals", "displacements"))
_REMOVAL_KEYS = frozenset(
    (
        "model_instance_id",
        "removal_kind",
        "source_phase",
        "source_step",
        "source_rule_id",
        "source_event_id",
        "destination_id",
    )
)
_CARGO_KEYS = frozenset(
    (
        "player_id",
        "transport_unit_instance_id",
        "capacity_profile",
        "embarked_unit_instance_ids",
        "phase_battle_round",
        "started_phase_embarked_unit_instance_ids",
        "disembarked_this_phase_unit_instance_ids",
    )
)
_RESERVE_ENTRY_KEYS = frozenset(
    (
        "player_id",
        "unit_instance_id",
        "reserve_origin",
        "reserve_kind",
        "source_rule_ids",
        "points_contribution",
        "entered_reserves_battle_round",
        "entered_reserves_phase",
        "required_arrival_battle_round",
        "required_arrival_phase",
        "required_arrival_source_rule_id",
        "required_arrival_placement_kind",
        "destruction_deadline_policy",
        "embarked_unit_instance_ids",
    )
)


def validate_non_destroyed_battlefield_departure_provenance(
    *,
    state: GameState,
    departures: tuple[PrimaryBattlefieldDepartureState, ...],
    event_records: tuple[EventRecord, ...],
    decision_records: tuple[DecisionRecord, ...],
) -> None:
    """Authenticate every non-destruction departure against its mutation owner.

    A self-consistent departure row and its derived recorded event are not source
    evidence: both can be cloned and re-identified together.  Embark departures
    therefore bind to the accepted transport decision and ``unit_embarked`` event;
    reserve departures bind one-to-one to the engine-owned reserve mutation event,
    the persisted ReserveState, and the movement decision for Aircraft transitions.
    """
    non_destroyed = tuple(
        departure
        for departure in departures
        if departure.removal_kind is not BattlefieldRemovalKind.DESTROYED
    )
    unsupported = tuple(
        departure
        for departure in non_destroyed
        if departure.removal_kind
        not in {BattlefieldRemovalKind.EMBARK, BattlefieldRemovalKind.INTO_RESERVES}
    )
    if unsupported:
        raise GameLifecycleError(
            "Primary battlefield departure has no authoritative mutation provider."
        )
    if state.mission_setup is None:
        if non_destroyed:
            raise GameLifecycleError(
                "Primary battlefield departure evidence requires matched-play mission setup."
            )
        return
    event_index_by_id = {record.event_id: index for index, record in enumerate(event_records)}
    derived_event_by_departure_id = _derived_event_by_departure_id(event_records)
    decision_by_result_id = _decision_by_result_id(decision_records)
    _validate_embark_departures(
        departures=tuple(
            value for value in non_destroyed if value.removal_kind is BattlefieldRemovalKind.EMBARK
        ),
        event_records=event_records,
        event_index_by_id=event_index_by_id,
        derived_event_by_departure_id=derived_event_by_departure_id,
        decision_by_result_id=decision_by_result_id,
    )
    _validate_reserve_departures(
        state=state,
        departures=tuple(
            value
            for value in non_destroyed
            if value.removal_kind is BattlefieldRemovalKind.INTO_RESERVES
        ),
        event_records=event_records,
        event_index_by_id=event_index_by_id,
        derived_event_by_departure_id=derived_event_by_departure_id,
        decision_by_result_id=decision_by_result_id,
    )


def _validate_embark_departures(
    *,
    departures: tuple[PrimaryBattlefieldDepartureState, ...],
    event_records: tuple[EventRecord, ...],
    event_index_by_id: dict[str, int],
    derived_event_by_departure_id: dict[str, EventRecord],
    decision_by_result_id: dict[str, DecisionRecord],
) -> None:
    mutation_by_result_id: dict[str, EventRecord] = {}
    for record in event_records:
        if record.event_type != _EMBARK_MUTATION_EVENT:
            continue
        payload = _event_payload(record, event_name="Embark mutation")
        result_id = _required_string(payload, "result_id", event_name="Embark mutation")
        if result_id in mutation_by_result_id:
            raise GameLifecycleError("Embark mutation result identity is duplicated.")
        mutation_by_result_id[result_id] = record
    expected_result_ids = {departure.source_id for departure in departures}
    if set(mutation_by_result_id) != expected_result_ids:
        raise GameLifecycleError(
            "Primary EMBARK departure requires one authoritative transport mutation event."
        )
    for departure in departures:
        if (
            departure.source_id != departure.occurrence_id
            or departure.affected_component_unit_instance_ids
            != departure.component_unit_instance_ids
            or departure.departed_component_unit_instance_ids
            != departure.component_unit_instance_ids
        ):
            raise GameLifecycleError("Primary EMBARK departure occurrence identity drift.")
        mutation = mutation_by_result_id[departure.source_id]
        payload = _event_payload(mutation, event_name="Embark mutation")
        _validate_common_mutation_identity(payload=payload, departure=departure)
        unit_id = _required_string(payload, "unit_instance_id", event_name="Embark mutation")
        transport_id = _required_string(
            payload,
            "transport_unit_instance_id",
            event_name="Embark mutation",
        )
        request_id = _required_string(payload, "request_id", event_name="Embark mutation")
        if unit_id not in departure.component_unit_instance_ids:
            raise GameLifecycleError("Primary EMBARK mutation selected-unit identity drift.")
        _validate_embark_transition(
            payload=payload.get("transition_batch"),
            departure=departure,
            transport_id=transport_id,
        )
        _validate_embark_cargo(
            payload=payload.get("updated_cargo_state"),
            departure=departure,
            transport_id=transport_id,
        )
        decision = decision_by_result_id.get(departure.source_id)
        if (
            decision is None
            or decision.request.request_id != request_id
            or decision.request.decision_type != SELECT_EMBARK_TRANSPORT_DECISION_TYPE
            or decision.result.decision_type != SELECT_EMBARK_TRANSPORT_DECISION_TYPE
            or decision.result.actor_id != departure.owner_player_id
            or decision.result.selected_option_id != transport_id
        ):
            raise GameLifecycleError(
                "Primary EMBARK departure lacks its accepted transport decision."
            )
        result_payload = _json_object(
            decision.result.payload,
            field_name="Embark decision result payload",
        )
        if (
            result_payload.get("transport_decision") != "embark_unit"
            or result_payload.get("unit_instance_id") != unit_id
            or result_payload.get("transport_unit_instance_id") != transport_id
        ):
            raise GameLifecycleError("Primary EMBARK decision mutation context drift.")
        _require_provider_before_derived(
            provider=mutation,
            derived=derived_event_by_departure_id[departure.departure_id],
            event_index_by_id=event_index_by_id,
            kind="EMBARK",
        )


def _validate_reserve_departures(
    *,
    state: GameState,
    departures: tuple[PrimaryBattlefieldDepartureState, ...],
    event_records: tuple[EventRecord, ...],
    event_index_by_id: dict[str, int],
    derived_event_by_departure_id: dict[str, EventRecord],
    decision_by_result_id: dict[str, DecisionRecord],
) -> None:
    mutation_by_occurrence: dict[tuple[str, str], EventRecord] = {}
    for record in event_records:
        if record.event_type != PRIMARY_RESERVE_ENTRY_MUTATION_EVENT:
            continue
        payload = _event_payload(record, event_name="Reserve-entry mutation")
        key = (
            _required_string(payload, "occurrence_id", event_name="Reserve-entry mutation"),
            _required_string(payload, "source_id", event_name="Reserve-entry mutation"),
        )
        if key in mutation_by_occurrence:
            raise GameLifecycleError("Reserve-entry mutation occurrence is duplicated.")
        mutation_by_occurrence[key] = record
    expected_keys = {(departure.occurrence_id, departure.source_id) for departure in departures}
    if set(mutation_by_occurrence) != expected_keys:
        raise GameLifecycleError(
            "Primary INTO_RESERVES departure requires one authoritative reserve mutation event."
        )
    latest_by_unit_id: dict[str, tuple[int, dict[str, JsonValue]]] = {}
    for departure in departures:
        mutation = mutation_by_occurrence[(departure.occurrence_id, departure.source_id)]
        payload = _event_payload(mutation, event_name="Reserve-entry mutation")
        _validate_common_mutation_identity(payload=payload, departure=departure)
        removed_ids = _string_list(
            payload.get("removed_model_instance_ids"),
            field_name="Reserve-entry removed_model_instance_ids",
        )
        if tuple(sorted(removed_ids)) != departure.removed_model_instance_ids:
            raise GameLifecycleError("Primary reserve-entry removed-model identity drift.")
        reserve_entry = _closed_json_object(
            payload.get("reserve_entry_state"),
            field_name="Reserve-entry state",
            expected_keys=_RESERVE_ENTRY_KEYS,
        )
        if (
            reserve_entry.get("player_id") != departure.owner_player_id
            or reserve_entry.get("unit_instance_id") != departure.rules_unit_instance_id
            or reserve_entry.get("entered_reserves_battle_round") != departure.battle_round
            or reserve_entry.get("entered_reserves_phase") != departure.phase
            or reserve_entry.get("reserve_kind") != "strategic_reserves"
        ):
            raise GameLifecycleError("Primary reserve-entry state identity drift.")
        transition = payload.get("transition_batch")
        if transition is None:
            expected_source = (
                f"{departure.game_id}:reposition-reserve:round-{departure.battle_round:02d}:"
                f"{departure.phase}:{departure.rules_unit_instance_id}"
            )
            if departure.source_id != expected_source or departure.occurrence_id != expected_source:
                raise GameLifecycleError("Primary reserve-entry mutation source identity drift.")
        else:
            _validate_aircraft_reserve_transition(
                payload=transition,
                departure=departure,
            )
            decision = decision_by_result_id.get(departure.source_id)
            if (
                departure.occurrence_id != departure.source_id
                or decision is None
                or decision.request.decision_type != SELECT_MOVEMENT_ACTION_DECISION_TYPE
                or decision.result.decision_type != SELECT_MOVEMENT_ACTION_DECISION_TYPE
                or decision.result.actor_id != departure.owner_player_id
                or decision.result.selected_option_id != "normal_move"
            ):
                raise GameLifecycleError(
                    "Primary Aircraft reserve departure lacks its accepted movement decision."
                )
        mutation_index = event_index_by_id[mutation.event_id]
        prior = latest_by_unit_id.get(departure.rules_unit_instance_id)
        if prior is None or mutation_index > prior[0]:
            latest_by_unit_id[departure.rules_unit_instance_id] = (mutation_index, reserve_entry)
        _require_provider_before_derived(
            provider=mutation,
            derived=derived_event_by_departure_id[departure.departure_id],
            event_index_by_id=event_index_by_id,
            kind="INTO_RESERVES",
        )
    reserve_state_by_unit_id = {value.unit_instance_id: value for value in state.reserve_states}
    for unit_id, (_index, entry_payload) in latest_by_unit_id.items():
        reserve_state = reserve_state_by_unit_id.get(unit_id)
        if reserve_state is None or reserve_entry_evidence_payload(reserve_state) != entry_payload:
            raise GameLifecycleError(
                "Primary reserve-entry mutation lacks its persisted ReserveState."
            )


def _validate_common_mutation_identity(
    *,
    payload: dict[str, JsonValue],
    departure: PrimaryBattlefieldDepartureState,
) -> None:
    if (
        payload.get("game_id") != departure.game_id
        or payload.get("battle_round") != departure.battle_round
        or payload.get("active_player_id") != departure.active_player_id
        or payload.get("phase") != departure.phase
    ):
        raise GameLifecycleError("Primary battlefield departure mutation timing drift.")


def _validate_embark_transition(
    *,
    payload: JsonValue,
    departure: PrimaryBattlefieldDepartureState,
    transport_id: str,
) -> None:
    transition = _closed_json_object(
        payload,
        field_name="Embark transition_batch",
        expected_keys=_TRANSITION_KEYS,
    )
    if transition["placements"] != [] or transition["displacements"] != []:
        raise GameLifecycleError("Primary EMBARK transition contains non-removal mutation.")
    removals = _json_object_list(transition["removals"], field_name="Embark removals")
    model_ids: list[str] = []
    for removal in removals:
        _require_exact_keys(removal, field_name="Embark removal", expected_keys=_REMOVAL_KEYS)
        model_ids.append(_required_string(removal, "model_instance_id", event_name="Embark"))
        if (
            removal.get("removal_kind") != BattlefieldRemovalKind.EMBARK.value
            or removal.get("source_phase") != departure.phase
            or removal.get("destination_id") != transport_id
        ):
            raise GameLifecycleError("Primary EMBARK transition removal identity drift.")
    if tuple(sorted(model_ids)) != departure.removed_model_instance_ids:
        raise GameLifecycleError("Primary EMBARK transition removed-model identity drift.")


def _validate_embark_cargo(
    *,
    payload: JsonValue,
    departure: PrimaryBattlefieldDepartureState,
    transport_id: str,
) -> None:
    cargo = _closed_json_object(
        payload,
        field_name="Embark updated_cargo_state",
        expected_keys=_CARGO_KEYS,
    )
    embarked_ids = set(
        _string_list(
            cargo.get("embarked_unit_instance_ids"),
            field_name="Embark cargo unit IDs",
        )
    )
    if (
        cargo.get("player_id") != departure.owner_player_id
        or cargo.get("transport_unit_instance_id") != transport_id
        or not set(departure.component_unit_instance_ids) <= embarked_ids
    ):
        raise GameLifecycleError("Primary EMBARK cargo mutation identity drift.")


def _validate_aircraft_reserve_transition(
    *,
    payload: JsonValue,
    departure: PrimaryBattlefieldDepartureState,
) -> None:
    transition = _closed_json_object(
        payload,
        field_name="Aircraft reserve transition_batch",
        expected_keys=_TRANSITION_KEYS,
    )
    if transition["placements"] != [] or transition["displacements"] != []:
        raise GameLifecycleError("Aircraft reserve transition contains non-removal mutation.")
    removals = _json_object_list(
        transition["removals"],
        field_name="Aircraft reserve removals",
    )
    model_ids: list[str] = []
    for removal in removals:
        _require_exact_keys(
            removal,
            field_name="Aircraft reserve removal",
            expected_keys=_REMOVAL_KEYS,
        )
        model_ids.append(
            _required_string(removal, "model_instance_id", event_name="Aircraft reserve")
        )
        if (
            removal.get("removal_kind") != BattlefieldRemovalKind.INTO_RESERVES.value
            or removal.get("source_phase") != departure.phase
            or removal.get("source_event_id") != departure.source_id
        ):
            raise GameLifecycleError("Aircraft reserve transition removal identity drift.")
    if tuple(sorted(model_ids)) != departure.removed_model_instance_ids:
        raise GameLifecycleError("Aircraft reserve transition removed-model identity drift.")


def _derived_event_by_departure_id(
    event_records: tuple[EventRecord, ...],
) -> dict[str, EventRecord]:
    derived: dict[str, EventRecord] = {}
    for record in event_records:
        if record.event_type != PRIMARY_BATTLEFIELD_DEPARTURE_RECORDED_EVENT:
            continue
        payload = _event_payload(record, event_name="Primary departure")
        state_payload = _json_object(
            payload.get("primary_battlefield_departure_state"),
            field_name="Primary departure state",
        )
        departure_id = _required_string(
            state_payload,
            "departure_id",
            event_name="Primary departure",
        )
        if departure_id in derived:
            raise GameLifecycleError("Primary departure recorded event is duplicated.")
        derived[departure_id] = record
    return derived


def _decision_by_result_id(
    decision_records: tuple[DecisionRecord, ...],
) -> dict[str, DecisionRecord]:
    decisions: dict[str, DecisionRecord] = {}
    for record in decision_records:
        result_id = record.result.result_id
        if result_id in decisions:
            raise GameLifecycleError("Historical mutation decision result IDs must be unique.")
        decisions[result_id] = record
    return decisions


def _require_provider_before_derived(
    *,
    provider: EventRecord,
    derived: EventRecord,
    event_index_by_id: dict[str, int],
    kind: str,
) -> None:
    if event_index_by_id[provider.event_id] >= event_index_by_id[derived.event_id]:
        raise GameLifecycleError(
            f"Primary {kind} departure was recorded before its authoritative mutation event."
        )


def _event_payload(record: EventRecord, *, event_name: str) -> dict[str, JsonValue]:
    return _json_object(record.payload, field_name=f"{event_name} event payload")


def _json_object(value: object, *, field_name: str) -> dict[str, JsonValue]:
    if not isinstance(value, dict):
        raise GameLifecycleError(f"{field_name} must be an object.")
    return cast(dict[str, JsonValue], value)


def _closed_json_object(
    value: object,
    *,
    field_name: str,
    expected_keys: frozenset[str],
) -> dict[str, JsonValue]:
    payload = _json_object(value, field_name=field_name)
    _require_exact_keys(payload, field_name=field_name, expected_keys=expected_keys)
    return payload


def _require_exact_keys(
    payload: dict[str, JsonValue],
    *,
    field_name: str,
    expected_keys: frozenset[str],
) -> None:
    if set(payload) != set(expected_keys):
        raise GameLifecycleError(f"{field_name} fields are malformed.")


def _required_string(
    payload: dict[str, JsonValue],
    key: str,
    *,
    event_name: str,
) -> str:
    value = payload.get(key)
    if type(value) is not str or not value.strip():
        raise GameLifecycleError(f"{event_name} {key} must be an identifier.")
    return value


def _string_list(value: object, *, field_name: str) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise GameLifecycleError(f"{field_name} must be a string list.")
    raw_values = cast(list[object], value)
    if any(type(item) is not str for item in raw_values):
        raise GameLifecycleError(f"{field_name} must be a string list.")
    identifiers = tuple(cast(str, item) for item in raw_values)
    if len(set(identifiers)) != len(identifiers):
        raise GameLifecycleError(f"{field_name} must not contain duplicates.")
    return identifiers


def _json_object_list(value: object, *, field_name: str) -> tuple[dict[str, JsonValue], ...]:
    if not isinstance(value, list):
        raise GameLifecycleError(f"{field_name} must be a list.")
    return tuple(
        _json_object(item, field_name=f"{field_name} item") for item in cast(list[object], value)
    )


__all__ = ("validate_non_destroyed_battlefield_departure_provenance",)
