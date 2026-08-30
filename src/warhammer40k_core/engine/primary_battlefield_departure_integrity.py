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
    PRIMARY_RESERVE_ENTRY_SOURCE_BINDINGS_KEY,
)
from warhammer40k_core.engine.primary_reserve_entry_provider import (
    PRIMARY_RESERVE_ENTRY_PROVIDER_RESOLVED_EVENT,
    PrimaryReserveEntryProvider,
    PrimaryReserveEntryProviderKind,
    validate_primary_reserve_entry_provider_registration,
)
from warhammer40k_core.engine.primary_reserve_entry_source_integrity import (
    validate_primary_reserve_entry_source_requirements,
    validate_primary_reserve_entry_source_terminal_semantics,
)
from warhammer40k_core.engine.primary_reserve_entry_state_integrity import (
    PrimaryReserveEntryStateOccurrence,
    validate_latest_primary_reserve_entry_states,
)
from warhammer40k_core.engine.primary_reserve_rule_ir_integrity import (
    expected_primary_reserve_stratagem_rule_execution_context,
    validate_exact_primary_reserve_rule_ir_placement_effect,
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
_PROVIDER_TERMINAL_KEYS = frozenset(
    (
        "occurrence_id",
        "provider",
        "reserve_entry_state",
        "source_terminal_event_id",
        "source_terminal_event_type",
    )
)
_PROVIDER_BINDING_KEYS = frozenset(("occurrence_id", "provider", "reserve_entry_state"))


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
        if unit_id != departure.rules_unit_instance_id:
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
        _validate_accepted_decision_event_closure(
            decision=decision,
            terminal_event=mutation,
            event_records=event_records,
            event_index_by_id=event_index_by_id,
            authority_name="Primary EMBARK departure",
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
    provider_terminal_by_occurrence = _provider_terminal_by_occurrence(event_records)
    expected_provider_occurrence_ids: set[str] = set()
    stratagem_provider_targets_by_use_id: dict[str, set[str]] = {}
    state_occurrences: list[PrimaryReserveEntryStateOccurrence] = []
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
            provider = PrimaryReserveEntryProvider.from_payload(payload.get("provider"))
            if (
                provider.occurrence_id != departure.occurrence_id
                or departure.source_id != provider.occurrence_id
                or provider.player_id != departure.owner_player_id
                or provider.target_rules_unit_instance_id != departure.rules_unit_instance_id
                or reserve_entry.get("reserve_origin") != provider.reserve_origin.value
                or reserve_entry.get("source_rule_ids") != [provider.source_rule_id]
            ):
                raise GameLifecycleError("Primary reserve-entry provider identity drift.")
            validate_primary_reserve_entry_provider_registration(
                state=state,
                provider=provider,
            )
            decision = _validate_reserve_provider_decision(
                state=state,
                provider=provider,
                mutation=mutation,
                event_records=event_records,
                event_index_by_id=event_index_by_id,
                decision_by_result_id=decision_by_result_id,
            )
            terminal = provider_terminal_by_occurrence.get(provider.occurrence_id)
            if terminal is None:
                raise GameLifecycleError("Primary reserve-entry provider lacks its terminal event.")
            _validate_reserve_provider_terminal(
                state=state,
                provider=provider,
                decision=decision,
                reserve_entry=reserve_entry,
                mutation=mutation,
                derived=derived_event_by_departure_id[departure.departure_id],
                terminal=terminal,
                event_records=event_records,
                event_index_by_id=event_index_by_id,
            )
            expected_provider_occurrence_ids.add(provider.occurrence_id)
            if provider.provider_kind is PrimaryReserveEntryProviderKind.GENERIC_RULE_IR_STRATAGEM:
                if provider.stratagem_use_id is None:
                    raise GameLifecycleError("Stratagem reserve provider use identity is missing.")
                stratagem_provider_targets_by_use_id.setdefault(
                    provider.stratagem_use_id, set()
                ).add(provider.target_rules_unit_instance_id)
        else:
            if payload.get("provider") is not None:
                raise GameLifecycleError(
                    "Aircraft reserve-entry mutation names an ability provider."
                )
            _validate_aircraft_reserve_transition(
                payload=transition,
                departure=departure,
            )
            aircraft_decision = decision_by_result_id.get(departure.source_id)
            if (
                departure.occurrence_id != departure.source_id
                or aircraft_decision is None
                or aircraft_decision.request.decision_type != SELECT_MOVEMENT_ACTION_DECISION_TYPE
                or aircraft_decision.result.decision_type != SELECT_MOVEMENT_ACTION_DECISION_TYPE
                or aircraft_decision.result.actor_id != departure.owner_player_id
                or aircraft_decision.result.selected_option_id != "normal_move"
            ):
                raise GameLifecycleError(
                    "Primary Aircraft reserve departure lacks its accepted movement decision."
                )
            _validate_accepted_decision_event_closure(
                decision=aircraft_decision,
                terminal_event=mutation,
                event_records=event_records,
                event_index_by_id=event_index_by_id,
                authority_name="Primary Aircraft reserve departure",
            )
        mutation_index = event_index_by_id[mutation.event_id]
        state_occurrences.append(
            PrimaryReserveEntryStateOccurrence(
                mutation_order=mutation_index,
                historical_unit_instance_id=departure.rules_unit_instance_id,
                reserve_entry=reserve_entry,
            )
        )
        _require_provider_before_derived(
            provider=mutation,
            derived=derived_event_by_departure_id[departure.departure_id],
            event_index_by_id=event_index_by_id,
            kind="INTO_RESERVES",
        )
    if set(provider_terminal_by_occurrence) != expected_provider_occurrence_ids:
        raise GameLifecycleError("Primary reserve-entry provider terminal occurrence drift.")
    _validate_stratagem_provider_target_sets(
        state=state,
        provider_targets_by_use_id=stratagem_provider_targets_by_use_id,
        event_records=event_records,
    )
    validate_latest_primary_reserve_entry_states(
        state=state,
        occurrences=tuple(state_occurrences),
        event_records=event_records,
    )


def _validate_stratagem_provider_target_sets(
    *,
    state: GameState,
    provider_targets_by_use_id: dict[str, set[str]],
    event_records: tuple[EventRecord, ...],
) -> None:
    from warhammer40k_core.engine.stratagems_generic_metadata import (
        generic_rule_ir_execution_target_unit_ids,
    )

    use_by_id = {use.use_id: use for use in state.stratagem_use_records}
    for use_id, provider_target_ids in provider_targets_by_use_id.items():
        use = use_by_id.get(use_id)
        if use is None:
            raise GameLifecycleError("Stratagem reserve provider use identity is missing.")
        expected_target_ids = set(
            generic_rule_ir_execution_target_unit_ids(state=state, use_record=use)
        )
        if provider_target_ids != expected_target_ids:
            raise GameLifecycleError("Stratagem reserve provider target-set completeness drift.")
        terminals = tuple(
            event
            for event in event_records
            if event.event_type == "generic_stratagem_reserve_removal_resolved"
            and isinstance(event.payload, dict)
            and event.payload.get("stratagem_use") == use.to_payload()
        )
        if len(terminals) != 1:
            raise GameLifecycleError("Stratagem reserve source terminal is not unique.")
        terminal_payload = _event_payload(
            terminals[0], event_name="Stratagem reserve source terminal"
        )
        raw_states = terminal_payload.get("reserve_states")
        if not isinstance(raw_states, list):
            raise GameLifecycleError("Stratagem reserve source terminal states are malformed.")
        from warhammer40k_core.engine.reserves import ReserveState, ReserveStatePayload

        try:
            terminal_target_ids = {
                ReserveState.from_payload(cast(ReserveStatePayload, raw_state)).unit_instance_id
                for raw_state in raw_states
                if isinstance(raw_state, dict)
            }
        except (KeyError, TypeError, ValueError) as exc:
            raise GameLifecycleError("Stratagem reserve source terminal state is invalid.") from exc
        if (
            len(terminal_target_ids) != len(raw_states)
            or terminal_target_ids != expected_target_ids
        ):
            raise GameLifecycleError("Stratagem reserve source terminal target-set drift.")
        raw_bindings = terminal_payload.get(PRIMARY_RESERVE_ENTRY_SOURCE_BINDINGS_KEY)
        if not isinstance(raw_bindings, list):
            raise GameLifecycleError("Stratagem reserve source bindings are malformed.")
        occurrence_ids = tuple(
            binding.get("occurrence_id") for binding in raw_bindings if isinstance(binding, dict)
        )
        expected_occurrence_ids = {
            f"{use_id}:reserve-entry:{target_id}" for target_id in expected_target_ids
        }
        if (
            len(occurrence_ids) != len(raw_bindings)
            or set(occurrence_ids) != expected_occurrence_ids
        ):
            raise GameLifecycleError("Stratagem reserve source binding target-set drift.")


def _provider_terminal_by_occurrence(
    event_records: tuple[EventRecord, ...],
) -> dict[str, EventRecord]:
    terminals: dict[str, EventRecord] = {}
    for record in event_records:
        if record.event_type != PRIMARY_RESERVE_ENTRY_PROVIDER_RESOLVED_EVENT:
            continue
        payload = _closed_json_object(
            record.payload,
            field_name="Reserve-entry provider terminal",
            expected_keys=_PROVIDER_TERMINAL_KEYS,
        )
        occurrence_id = _required_string(
            payload,
            "occurrence_id",
            event_name="Reserve-entry provider terminal",
        )
        if occurrence_id in terminals:
            raise GameLifecycleError("Reserve-entry provider terminal is duplicated.")
        terminals[occurrence_id] = record
    return terminals


def _validate_reserve_provider_decision(
    *,
    state: GameState,
    provider: PrimaryReserveEntryProvider,
    mutation: EventRecord,
    event_records: tuple[EventRecord, ...],
    event_index_by_id: dict[str, int],
    decision_by_result_id: dict[str, DecisionRecord],
) -> DecisionRecord:
    decision = decision_by_result_id.get(provider.decision_result_id)
    if (
        decision is None
        or decision.record_id != provider.decision_record_id
        or decision.request.request_id != provider.decision_request_id
        or decision.result.request_id != provider.decision_request_id
        or decision.result.result_id != provider.decision_result_id
        or decision.result.actor_id != provider.player_id
    ):
        raise GameLifecycleError("Reserve-entry provider DecisionRecord identity drift.")
    _, recorded_event = _validate_accepted_decision_event_closure(
        decision=decision,
        terminal_event=mutation,
        event_records=event_records,
        event_index_by_id=event_index_by_id,
        authority_name="Reserve-entry provider",
    )
    if provider.provider_kind is PrimaryReserveEntryProviderKind.TURN_END_ABILITY:
        _validate_ability_provider_decision(
            state=state,
            provider=provider,
            decision=decision,
            mutation=mutation,
        )
    else:
        _validate_stratagem_provider_decision(
            state=state,
            provider=provider,
            decision=decision,
            mutation=mutation,
            event_records=event_records,
            event_index_by_id=event_index_by_id,
            recorded_decision_event=recorded_event,
        )
    return decision


def _validate_accepted_decision_event_closure(
    *,
    decision: DecisionRecord,
    terminal_event: EventRecord,
    event_records: tuple[EventRecord, ...],
    event_index_by_id: dict[str, int],
    authority_name: str,
) -> tuple[EventRecord, EventRecord]:
    requested_events = tuple(
        record
        for record in event_records
        if record.event_type == "decision_requested"
        and record.payload == decision.request.to_payload()
    )
    recorded_events = tuple(
        record
        for record in event_records
        if record.event_type == "decision_recorded" and record.payload == decision.to_payload()
    )
    if len(requested_events) != 1 or len(recorded_events) != 1:
        raise GameLifecycleError(
            f"{authority_name} requires exact requested and recorded decision events."
        )
    requested_event = requested_events[0]
    recorded_event = recorded_events[0]
    if not (
        event_index_by_id[requested_event.event_id]
        < event_index_by_id[recorded_event.event_id]
        < event_index_by_id[terminal_event.event_id]
    ):
        raise GameLifecycleError(f"{authority_name} decision ordering drift.")
    return requested_event, recorded_event


def _validate_ability_provider_decision(
    *,
    state: GameState,
    provider: PrimaryReserveEntryProvider,
    decision: DecisionRecord,
    mutation: EventRecord,
) -> None:
    from warhammer40k_core.engine.rules_units import rules_unit_identities_share_lineage
    from warhammer40k_core.engine.turn_end_hooks import (
        SELECT_FACTION_RULE_TURN_END_OPTION_DECISION_TYPE,
    )

    if (
        decision.request.decision_type != SELECT_FACTION_RULE_TURN_END_OPTION_DECISION_TYPE
        or decision.result.decision_type != SELECT_FACTION_RULE_TURN_END_OPTION_DECISION_TYPE
    ):
        raise GameLifecycleError("Ability reserve provider decision type drift.")
    request_payload = _json_object(
        decision.request.payload,
        field_name="Ability reserve request payload",
    )
    result_payload = _json_object(
        decision.result.payload,
        field_name="Ability reserve result payload",
    )
    selected_target_id = _ability_target_id(result_payload)
    mutation_payload = _event_payload(mutation, event_name="Reserve-entry mutation")
    if (
        request_payload.get("game_id") != mutation_payload.get("game_id")
        or request_payload.get("battle_round") != mutation_payload.get("battle_round")
        or request_payload.get("active_player_id") != mutation_payload.get("active_player_id")
        or request_payload.get("phase") != mutation_payload.get("phase")
        or request_payload.get("source_rule_id") != provider.source_rule_id
        or request_payload.get("hook_id") != provider.provider_id
        or result_payload.get("source_rule_id") != provider.source_rule_id
        or result_payload.get("hook_id") != provider.provider_id
        or result_payload.get("player_id") != provider.player_id
        or result_payload.get("use_ability") is not True
        or not rules_unit_identities_share_lineage(
            state=state,
            first_unit_instance_id=selected_target_id,
            second_unit_instance_id=provider.target_rules_unit_instance_id,
        )
    ):
        raise GameLifecycleError("Ability reserve provider decision context drift.")


def _validate_stratagem_provider_decision(
    *,
    state: GameState,
    provider: PrimaryReserveEntryProvider,
    decision: DecisionRecord,
    mutation: EventRecord,
    event_records: tuple[EventRecord, ...],
    event_index_by_id: dict[str, int],
    recorded_decision_event: EventRecord,
) -> None:
    from warhammer40k_core.engine.rules_units import rules_unit_identities_share_lineage
    from warhammer40k_core.engine.stratagems_eligibility import (
        derive_recorded_stratagem_use_unit_ids,
    )
    from warhammer40k_core.engine.stratagems_model import (
        GENERIC_RULE_IR_STRATAGEM_HANDLER_ID,
        STRATAGEM_DECISION_TYPE,
        STRATAGEM_TARGET_PROPOSAL_DECISION_TYPE,
    )
    from warhammer40k_core.engine.stratagems_selection import (
        stratagem_selection_from_decision_result,
        stratagem_selection_from_target_proposal_result,
    )

    if provider.stratagem_use_id is None or decision.request.decision_type not in {
        STRATAGEM_DECISION_TYPE,
        STRATAGEM_TARGET_PROPOSAL_DECISION_TYPE,
    }:
        raise GameLifecycleError("Stratagem reserve provider decision type drift.")
    uses = tuple(
        use for use in state.stratagem_use_records if use.use_id == provider.stratagem_use_id
    )
    if len(uses) != 1:
        raise GameLifecycleError("Stratagem reserve provider use identity is missing.")
    use = uses[0]
    if decision.request.decision_type == STRATAGEM_DECISION_TYPE:
        selection = stratagem_selection_from_decision_result(decision.result)
    elif decision.request.decision_type == STRATAGEM_TARGET_PROPOSAL_DECISION_TYPE:
        selection = stratagem_selection_from_target_proposal_result(decision.result)
    else:
        selection = None
    if selection is None:
        raise GameLifecycleError("Stratagem reserve provider accepted selection is malformed.")
    context, catalog_record, target_binding, effect_selection = selection
    if decision.request.decision_type == STRATAGEM_TARGET_PROPOSAL_DECISION_TYPE:
        _validate_stratagem_target_proposal_request(
            decision=decision,
            context=context,
            catalog_record=catalog_record,
        )
    definition = catalog_record.definition
    expected_targeted_ids, expected_affected_ids = derive_recorded_stratagem_use_unit_ids(
        state=state,
        definition=definition,
        context=context,
        target_binding=target_binding,
        effect_selection=effect_selection,
        recorded_targeted_unit_ids=use.targeted_unit_instance_ids,
        recorded_affected_unit_ids=use.affected_unit_instance_ids,
    )
    mutation_payload = _event_payload(mutation, event_name="Reserve-entry mutation")
    recorded_target_ids = set(use.targeted_unit_instance_ids) | set(use.affected_unit_instance_ids)
    if (
        decision.result.decision_type != decision.request.decision_type
        or use.request_id != provider.decision_request_id
        or use.result_id != provider.decision_result_id
        or use.selected_option_id != decision.result.selected_option_id
        or use.player_id != provider.player_id
        or use.battle_round != mutation_payload.get("battle_round")
        or use.phase.value != mutation_payload.get("phase")
        or use.active_player_id != mutation_payload.get("active_player_id")
        or context.game_id != state.game_id
        or context.player_id != use.player_id
        or context.battle_round != use.battle_round
        or context.phase is not use.phase
        or context.active_player_id != use.active_player_id
        or context.timing_window_id != use.timing_window_id
        or definition.stratagem_id != use.stratagem_id
        or definition.source_id != use.source_id
        or definition.handler_id != GENERIC_RULE_IR_STRATAGEM_HANDLER_ID
        or definition.effect_payload != use.effect_payload
        or target_binding != use.target_binding
        or effect_selection != use.effect_selection
        or use.targeted_unit_instance_ids != expected_targeted_ids
        or use.affected_unit_instance_ids != expected_affected_ids
        or use.handler_id != GENERIC_RULE_IR_STRATAGEM_HANDLER_ID
        or not use.effects_resolved
        or not any(
            rules_unit_identities_share_lineage(
                state=state,
                first_unit_instance_id=provider.target_rules_unit_instance_id,
                second_unit_instance_id=target_id,
            )
            for target_id in recorded_target_ids
        )
    ):
        raise GameLifecycleError("Stratagem reserve provider use context drift.")
    use_events = tuple(
        record
        for record in event_records
        if record.event_type == "stratagem_used" and record.payload == use.to_payload()
    )
    if len(use_events) != 1 or not (
        event_index_by_id[recorded_decision_event.event_id]
        < event_index_by_id[use_events[0].event_id]
        < event_index_by_id[mutation.event_id]
    ):
        raise GameLifecycleError("Stratagem reserve provider use event ordering drift.")
    from warhammer40k_core.engine.stratagems_generic_metadata import (
        generic_rule_ir_execution_target_unit_ids,
    )

    _validate_stratagem_reserve_removal_effect(
        state=state,
        use=use,
        eligibility_context=context,
        target_player_id=target_binding.target_player_id,
        effect_payload=use.effect_payload,
        source_rule_id=provider.source_rule_id,
        event_records=event_records,
        event_index_by_id=event_index_by_id,
        use_event=use_events[0],
        mutation=mutation,
        expected_target_ids=generic_rule_ir_execution_target_unit_ids(
            state=state,
            use_record=use,
        ),
    )


def _validate_stratagem_target_proposal_request(
    *,
    decision: DecisionRecord,
    context: object,
    catalog_record: object,
) -> None:
    from warhammer40k_core.engine.stratagems_model import (
        StratagemTargetProposal,
        StratagemTargetProposalPayload,
    )

    request_payload = _json_object(
        decision.request.payload,
        field_name="Stratagem reserve target proposal request",
    )
    raw_proposal = request_payload.get("proposal_request")
    if not isinstance(raw_proposal, dict):
        raise GameLifecycleError("Stratagem reserve target proposal request is malformed.")
    try:
        request_proposal = StratagemTargetProposal.from_payload(
            cast(StratagemTargetProposalPayload, raw_proposal)
        )
    except (KeyError, GameLifecycleError) as exc:
        raise GameLifecycleError("Stratagem reserve target proposal request is malformed.") from exc
    if (
        request_proposal.target_binding is not None
        or request_proposal.context != context
        or request_proposal.catalog_record != catalog_record
    ):
        raise GameLifecycleError("Stratagem reserve target proposal request context drift.")


def _validate_stratagem_reserve_removal_effect(
    *,
    state: GameState,
    use: object,
    eligibility_context: object,
    target_player_id: str | None,
    effect_payload: JsonValue,
    source_rule_id: str,
    event_records: tuple[EventRecord, ...],
    event_index_by_id: dict[str, int],
    use_event: EventRecord,
    mutation: EventRecord,
    expected_target_ids: tuple[str, ...],
) -> None:
    from warhammer40k_core.engine.rule_execution import scoped_rule_ir_from_execution_payload
    from warhammer40k_core.engine.stratagems_model import (
        StratagemEligibilityContext,
        StratagemUseRecord,
    )
    from warhammer40k_core.rules.rule_ir import (
        RuleEffectKind,
        RuleIRError,
        parameter_payload,
    )

    try:
        rule_ir = scoped_rule_ir_from_execution_payload(effect_payload)
    except RuleIRError as exc:
        raise GameLifecycleError("Stratagem reserve provider RuleIR is invalid.") from exc
    matching_effects = tuple(
        (clause, index, effect)
        for clause in rule_ir.clauses
        for index, effect in enumerate(clause.effects)
        if effect.kind is RuleEffectKind.PLACEMENT_PERMISSION
        and parameter_payload(effect.parameters).get("placement_kind") == "strategic_reserves"
        and parameter_payload(effect.parameters).get("operation") == "remove_to_reserves"
        and parameter_payload(effect.parameters).get("reserve_origin") == "during_battle_stratagem"
    )
    if rule_ir.source_id != source_rule_id or len(matching_effects) != 1:
        raise GameLifecycleError("Stratagem reserve provider RuleIR authority drift.")
    clause, effect_index, effect = matching_effects[0]
    if (
        type(use) is not StratagemUseRecord
        or type(eligibility_context) is not StratagemEligibilityContext
    ):
        raise GameLifecycleError("Stratagem reserve provider execution context is malformed.")
    expected_context = expected_primary_reserve_stratagem_rule_execution_context(
        state=state,
        use=use,
        eligibility_context=eligibility_context,
        target_player_id=target_player_id,
        target_unit_instance_ids=expected_target_ids,
    )
    matching_events = tuple(
        record
        for record in event_records
        if record.event_type == "rule_execution_effect_applied"
        and isinstance(record.payload, dict)
        and record.payload.get("rule_id") == rule_ir.rule_id
        and record.payload.get("source_id") == rule_ir.source_id
        and record.payload.get("rule_ir_hash") == rule_ir.ir_hash()
        and record.payload.get("clause_id") == clause.clause_id
        and record.payload.get("effect_index") == effect_index
    )
    if len(matching_events) != 1:
        raise GameLifecycleError("Stratagem reserve provider execution event drift.")
    matching_payload = _json_object(
        matching_events[0].payload,
        field_name="Stratagem reserve provider execution event",
    )
    executed_effect = validate_exact_primary_reserve_rule_ir_placement_effect(
        rule_ir=rule_ir,
        executed_effect_payload=matching_payload,
    )
    if (
        executed_effect.parameters != parameter_payload(effect.parameters)
        or executed_effect.target_unit_instance_ids != expected_target_ids
        or matching_payload.get("context") != expected_context
        or not (
            event_index_by_id[use_event.event_id]
            < event_index_by_id[matching_events[0].event_id]
            < event_index_by_id[mutation.event_id]
        )
    ):
        raise GameLifecycleError("Stratagem reserve provider execution event drift.")


def _validate_reserve_provider_terminal(
    *,
    state: GameState,
    provider: PrimaryReserveEntryProvider,
    decision: DecisionRecord,
    reserve_entry: dict[str, JsonValue],
    mutation: EventRecord,
    derived: EventRecord,
    terminal: EventRecord,
    event_records: tuple[EventRecord, ...],
    event_index_by_id: dict[str, int],
) -> None:
    terminal_payload = _closed_json_object(
        terminal.payload,
        field_name="Reserve-entry provider terminal",
        expected_keys=_PROVIDER_TERMINAL_KEYS,
    )
    if (
        terminal_payload.get("occurrence_id") != provider.occurrence_id
        or terminal_payload.get("provider") != provider.to_payload()
        or terminal_payload.get("reserve_entry_state") != reserve_entry
        or terminal_payload.get("source_terminal_event_type") != provider.source_terminal_event_type
    ):
        raise GameLifecycleError("Reserve-entry provider terminal identity drift.")
    source_terminal_event_id = _required_string(
        terminal_payload,
        "source_terminal_event_id",
        event_name="Reserve-entry provider terminal",
    )
    source_terminals = tuple(
        record
        for record in event_records
        if record.event_type == provider.source_terminal_event_type
        and _source_terminal_has_provider_binding(
            record=record,
            provider=provider,
            reserve_entry=reserve_entry,
        )
    )
    if len(source_terminals) != 1 or source_terminals[0].event_id != source_terminal_event_id:
        raise GameLifecycleError("Reserve-entry provider source terminal is not unique.")
    source_terminal = source_terminals[0]
    validate_primary_reserve_entry_source_terminal_semantics(
        state=state,
        provider=provider,
        decision=decision,
        reserve_entry=reserve_entry,
        source_terminal=source_terminal,
        event_records=event_records,
    )
    validate_primary_reserve_entry_source_requirements(
        state=state,
        provider=provider,
        reserve_entry=reserve_entry,
        source_terminal=source_terminal,
    )
    if not (
        event_index_by_id[mutation.event_id]
        < event_index_by_id[derived.event_id]
        < event_index_by_id[source_terminal.event_id]
        < event_index_by_id[terminal.event_id]
    ):
        raise GameLifecycleError("Reserve-entry provider terminal ordering drift.")


def _source_terminal_has_provider_binding(
    *,
    record: EventRecord,
    provider: PrimaryReserveEntryProvider,
    reserve_entry: dict[str, JsonValue],
) -> bool:
    if not isinstance(record.payload, dict):
        return False
    bindings = record.payload.get(PRIMARY_RESERVE_ENTRY_SOURCE_BINDINGS_KEY)
    if not isinstance(bindings, list):
        return False
    expected: JsonValue = {
        "occurrence_id": provider.occurrence_id,
        "provider": provider.to_payload(),
        "reserve_entry_state": reserve_entry,
    }
    return bindings.count(expected) == 1


def _ability_target_id(payload: dict[str, JsonValue]) -> str:
    targets = tuple(
        value
        for key in ("target_unit_instance_id", "target_rules_unit_instance_id")
        if type(value := payload.get(key)) is str
    )
    if len(targets) != 1:
        raise GameLifecycleError("Ability reserve target identity is ambiguous.")
    return _required_identifier_value(targets[0], field_name="ability reserve target")


def _required_identifier_value(value: object, *, field_name: str) -> str:
    if type(value) is not str or not value.strip():
        raise GameLifecycleError(f"{field_name} must be an identifier.")
    return value


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
