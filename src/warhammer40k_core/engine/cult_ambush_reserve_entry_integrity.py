from __future__ import annotations

from typing import TYPE_CHECKING, cast

from warhammer40k_core.engine.battlefield_state import BattlefieldPlacementKind
from warhammer40k_core.engine.cult_ambush import (
    RESURGENCE_RESOURCE_KIND,
    SELECT_CULT_AMBUSH_RESURGENCE_DECISION_TYPE,
    SOURCE_RULE_ID,
    TURN_END_HOOK_ID,
    CultAmbushMarker,
    CultAmbushMarkerPayload,
)
from warhammer40k_core.engine.cult_ambush_resurgence import cult_ambush_return_candidate
from warhammer40k_core.engine.decision_record import DecisionRecord
from warhammer40k_core.engine.event_log import EventRecord, JsonValue
from warhammer40k_core.engine.faction_resources import FactionResourceTransactionKind
from warhammer40k_core.engine.movement_proposals import MovementProposalRequest, ProposalKind
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.primary_historical_events import reserve_entry_evidence_payload
from warhammer40k_core.engine.primary_reserve_entry_provider import (
    PrimaryReserveEntryLifecycleOccurrence,
)
from warhammer40k_core.engine.reserves import (
    ReserveOrigin,
    ReserveState,
    ReserveStatePayload,
    ReserveStatus,
)
from warhammer40k_core.engine.turn_end_hooks import (
    SELECT_FACTION_RULE_TURN_END_OPTION_DECISION_TYPE,
)

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState


_RESURGENCE_REQUESTED_EVENT = "genestealer_cults_cult_ambush_resurgence_requested"
_RESURGENCE_SPENT_EVENT = "genestealer_cults_cult_ambush_resurgence_spent"
_SPENT_EVENT_KEYS = frozenset(
    (
        "game_id",
        "battle_round",
        "active_player_id",
        "phase",
        "player_id",
        "request_id",
        "result_id",
        "destroyed_unit_instance_id",
        "replacement_unit_instance_id",
        "resurgence_cost",
        "faction_resource_result",
        "reserve_state",
        "starting_strength_record",
        "source_rule_id",
    )
)
_CULT_AMBUSH_ARRIVAL_CONTEXT_KEYS = frozenset(
    ("source_rule_id", "marker", "active_player_id", "placement_scope")
)


def validated_primary_reserve_entry_occurrences(
    *,
    state: GameState,
    event_records: tuple[EventRecord, ...],
    decision_records: tuple[DecisionRecord, ...],
    event_index_by_id: dict[str, int],
) -> tuple[PrimaryReserveEntryLifecycleOccurrence, ...]:
    """Authenticate Cult Ambush reserve entries against their accepted spend chain."""
    from warhammer40k_core.engine.game_state import GameState

    if type(state) is not GameState:
        raise GameLifecycleError("Cult Ambush reserve integrity requires GameState.")
    decisions_by_result_id: dict[str, DecisionRecord] = {}
    for recorded_decision in decision_records:
        if (
            recorded_decision.request.decision_type != SELECT_CULT_AMBUSH_RESURGENCE_DECISION_TYPE
            and recorded_decision.result.decision_type
            != SELECT_CULT_AMBUSH_RESURGENCE_DECISION_TYPE
        ):
            continue
        result_id = recorded_decision.result.result_id
        if result_id in decisions_by_result_id:
            raise GameLifecycleError("Cult Ambush decision result identity is duplicated.")
        decisions_by_result_id[result_id] = recorded_decision
    occurrences: list[PrimaryReserveEntryLifecycleOccurrence] = []
    replacement_ids: set[str] = set()
    for spent_event in event_records:
        if spent_event.event_type != _RESURGENCE_SPENT_EVENT:
            continue
        payload = _closed_object(
            spent_event.payload,
            field_name="Cult Ambush resurgence-spent event",
            expected_keys=_SPENT_EVENT_KEYS,
        )
        result_id = _identifier(payload.get("result_id"), field_name="Cult Ambush result_id")
        request_id = _identifier(
            payload.get("request_id"),
            field_name="Cult Ambush request_id",
        )
        player_id = _identifier(payload.get("player_id"), field_name="Cult Ambush player_id")
        destroyed_unit_id = _identifier(
            payload.get("destroyed_unit_instance_id"),
            field_name="Cult Ambush destroyed unit",
        )
        replacement_unit_id = _identifier(
            payload.get("replacement_unit_instance_id"),
            field_name="Cult Ambush replacement unit",
        )
        if replacement_unit_id in replacement_ids:
            raise GameLifecycleError("Cult Ambush replacement reserve identity is duplicated.")
        replacement_ids.add(replacement_unit_id)
        decision = decisions_by_result_id.get(result_id)
        if decision is None:
            raise GameLifecycleError("Cult Ambush reserve entry lacks its accepted decision.")
        current_resurgence_points = _validate_decision_and_events(
            state=state,
            event_records=event_records,
            event_index_by_id=event_index_by_id,
            spent_event=spent_event,
            decision=decision,
            request_id=request_id,
            result_id=result_id,
            player_id=player_id,
            destroyed_unit_id=destroyed_unit_id,
            payload=payload,
        )
        reserve_state = _entry_reserve_state(payload.get("reserve_state"))
        return_candidate = cult_ambush_return_candidate(
            state,
            destroyed_unit_instance_id=destroyed_unit_id,
        )
        if return_candidate is None:
            raise GameLifecycleError("Cult Ambush destroyed-unit authority drift.")
        expected_source_rule_ids = tuple(
            sorted((SOURCE_RULE_ID, *return_candidate.source_rule_ids))
        )
        active_player_id = _identifier(
            payload.get("active_player_id"),
            field_name="Cult Ambush active_player_id",
        )
        if (
            payload.get("game_id") != state.game_id
            or active_player_id not in state.player_ids
            or active_player_id not in state.turn_order
            or payload.get("battle_round") != reserve_state.entered_reserves_battle_round
            or payload.get("phase") != reserve_state.entered_reserves_phase
            or payload.get("source_rule_id") != SOURCE_RULE_ID
            or reserve_state.player_id != player_id
            or reserve_state.unit_instance_id != replacement_unit_id
            or reserve_state.reserve_origin is not ReserveOrigin.DURING_BATTLE_ABILITY
            or reserve_state.source_rule_ids != expected_source_rule_ids
        ):
            raise GameLifecycleError("Cult Ambush reserve-entry identity drift.")
        starting_strength = state.starting_strength_record_for_unit(replacement_unit_id)
        if (
            starting_strength.source_id != SOURCE_RULE_ID
            or starting_strength.player_id != player_id
            or payload.get("starting_strength_record") != starting_strength.to_payload()
        ):
            raise GameLifecycleError("Cult Ambush replacement starting-strength drift.")
        _validate_resource_spend(
            state=state,
            payload=payload,
            player_id=player_id,
            result_id=result_id,
            current_resurgence_points=current_resurgence_points,
        )
        occurrences.append(
            PrimaryReserveEntryLifecycleOccurrence(
                event_order=event_index_by_id[spent_event.event_id],
                historical_unit_instance_id=replacement_unit_id,
                reserve_entry_state=reserve_entry_evidence_payload(reserve_state),
            )
        )
    return tuple(occurrences)


def validate_cult_ambush_reserve_arrival_source(
    *,
    state: GameState,
    proposal_request: MovementProposalRequest,
    arrival_event: EventRecord,
    event_records: tuple[EventRecord, ...],
    decision_records: tuple[DecisionRecord, ...],
    event_index_by_id: dict[str, int],
    placement_request_order: int,
) -> str:
    """Authenticate opponent-turn marker ingress and return its active player."""
    if proposal_request.proposal_kind is not ProposalKind.CULT_AMBUSH:
        raise GameLifecycleError("Cult Ambush arrival requires its typed proposal kind.")
    arrival_payload = _object(
        arrival_event.payload,
        field_name="Cult Ambush arrival event",
    )
    proposal_context = _closed_object(
        proposal_request.context,
        field_name="Cult Ambush arrival proposal context",
        expected_keys=_CULT_AMBUSH_ARRIVAL_CONTEXT_KEYS,
    )
    marker_payload = _object(
        proposal_context.get("marker"),
        field_name="Cult Ambush arrival marker",
    )
    try:
        marker = CultAmbushMarker.from_payload(cast(CultAmbushMarkerPayload, marker_payload))
    except (KeyError, TypeError, ValueError, GameLifecycleError) as exc:
        raise GameLifecycleError("Cult Ambush arrival marker is invalid.") from exc
    active_player_id = _identifier(
        proposal_context.get("active_player_id"),
        field_name="Cult Ambush arrival active player",
    )
    owner_player_id = _identifier(
        arrival_payload.get("player_id"),
        field_name="Cult Ambush arrival owner",
    )
    if (
        active_player_id not in state.player_ids
        or active_player_id not in state.turn_order
        or active_player_id == owner_player_id
        or marker.player_id != owner_player_id
        or marker.replacement_unit_instance_id != proposal_request.unit_instance_id
        or proposal_context.get("source_rule_id") != SOURCE_RULE_ID
        or proposal_context.get("placement_scope") != "cult_ambush_marker"
        or proposal_request.actor_id != owner_player_id
        or arrival_payload.get("active_player_id") != active_player_id
        or arrival_payload.get("source_rule_id") != SOURCE_RULE_ID
        or arrival_payload.get("step") != "cult_ambush_marker"
        or arrival_payload.get("placement_kind") != BattlefieldPlacementKind.CULT_AMBUSH.value
    ):
        raise GameLifecycleError("Cult Ambush arrival source context drift.")
    source_decisions = tuple(
        decision
        for decision in decision_records
        if decision.request.request_id == proposal_request.source_decision_request_id
        and decision.result.result_id == proposal_request.source_decision_result_id
    )
    if len(source_decisions) != 1:
        raise GameLifecycleError("Cult Ambush arrival lacks one accepted source decision.")
    source_decision = source_decisions[0]
    request_payload = _object(
        source_decision.request.payload,
        field_name="Cult Ambush ingress-selection request",
    )
    result_payload = _object(
        source_decision.result.payload,
        field_name="Cult Ambush ingress-selection result",
    )
    eligible_unit_ids = request_payload.get("eligible_unit_instance_ids")
    selected_options = tuple(
        option
        for option in source_decision.request.options
        if option.option_id == source_decision.result.selected_option_id
    )
    if (
        source_decision.request.decision_type != SELECT_FACTION_RULE_TURN_END_OPTION_DECISION_TYPE
        or source_decision.result.decision_type != SELECT_FACTION_RULE_TURN_END_OPTION_DECISION_TYPE
        or source_decision.request.actor_id != owner_player_id
        or source_decision.result.actor_id != owner_player_id
        or request_payload.get("source_rule_id") != SOURCE_RULE_ID
        or request_payload.get("hook_id") != TURN_END_HOOK_ID
        or request_payload.get("selection_kind") != "cult_ambush_marker_ingress"
        or request_payload.get("marker") != marker.to_payload()
        or request_payload.get("battle_round") != proposal_request.battle_round
        or request_payload.get("phase") != proposal_request.phase
        or request_payload.get("active_player_id") != active_player_id
        or not isinstance(eligible_unit_ids, list)
        or eligible_unit_ids.count(proposal_request.unit_instance_id) != 1
        or len(selected_options) != 1
        or selected_options[0].payload != result_payload
        or result_payload.get("selection") != "ingress"
        or result_payload.get("source_rule_id") != SOURCE_RULE_ID
        or result_payload.get("marker_id") != marker.marker_id
        or result_payload.get("unit_instance_id") != proposal_request.unit_instance_id
    ):
        raise GameLifecycleError("Cult Ambush arrival source decision drift.")
    requested_events = tuple(
        event
        for event in event_records
        if event.event_type == "decision_requested"
        and event.payload == source_decision.request.to_payload()
    )
    recorded_events = tuple(
        event
        for event in event_records
        if event.event_type == "decision_recorded" and event.payload == source_decision.to_payload()
    )
    companion_payload: dict[str, JsonValue] = {
        "game_id": state.game_id,
        "battle_round": proposal_request.battle_round,
        "active_player_id": active_player_id,
        "player_id": owner_player_id,
        "phase": proposal_request.phase,
        "unit_instance_id": proposal_request.unit_instance_id,
        "marker_id": marker.marker_id,
        "request_id": arrival_payload.get("request_id"),
        "result_id": arrival_payload.get("result_id"),
        "transition_batch": arrival_payload.get("transition_batch"),
        "source_rule_id": SOURCE_RULE_ID,
    }
    companion_events = tuple(
        event
        for event in event_records
        if event.event_type == "genestealer_cults_cult_ambush_unit_arrived"
        and event.payload == companion_payload
    )
    if len(requested_events) != 1 or len(recorded_events) != 1 or len(companion_events) != 1:
        raise GameLifecycleError("Cult Ambush arrival decision/event closure drift.")
    ordered = (
        event_index_by_id[requested_events[0].event_id],
        event_index_by_id[recorded_events[0].event_id],
        placement_request_order,
        event_index_by_id[arrival_event.event_id],
        event_index_by_id[companion_events[0].event_id],
    )
    if tuple(sorted(ordered)) != ordered or len(set(ordered)) != len(ordered):
        raise GameLifecycleError("Cult Ambush arrival event ordering drift.")
    return active_player_id


def _validate_decision_and_events(
    *,
    state: GameState,
    event_records: tuple[EventRecord, ...],
    event_index_by_id: dict[str, int],
    spent_event: EventRecord,
    decision: DecisionRecord,
    request_id: str,
    result_id: str,
    player_id: str,
    destroyed_unit_id: str,
    payload: dict[str, JsonValue],
) -> int:
    request_payload = _object(decision.request.payload, field_name="Cult Ambush request payload")
    result_payload = _object(decision.result.payload, field_name="Cult Ambush result payload")
    model_destroyed_event_id = _identifier(
        request_payload.get("model_destroyed_event_id"),
        field_name="Cult Ambush source destruction event",
    )
    cost = payload.get("resurgence_cost")
    current_points = request_payload.get("current_resurgence_points")
    battle_round = payload.get("battle_round")
    phase = payload.get("phase")
    active_player_id = payload.get("active_player_id")
    selected_options = tuple(
        option
        for option in decision.request.options
        if option.option_id == decision.result.selected_option_id
    )
    if (
        type(cost) is not int
        or cost <= 0
        or type(current_points) is not int
        or current_points < cost
        or type(battle_round) is not int
        or battle_round <= 0
        or type(phase) is not str
        or not phase
        or type(active_player_id) is not str
        or active_player_id not in state.player_ids
        or active_player_id not in state.turn_order
        or decision.request.request_id != request_id
        or decision.result.result_id != result_id
        or decision.request.decision_type != SELECT_CULT_AMBUSH_RESURGENCE_DECISION_TYPE
        or decision.result.decision_type != SELECT_CULT_AMBUSH_RESURGENCE_DECISION_TYPE
        or decision.request.actor_id != player_id
        or decision.result.actor_id != player_id
        or request_payload.get("source_rule_id") != SOURCE_RULE_ID
        or request_payload.get("destroyed_unit_instance_id") != destroyed_unit_id
        or request_payload.get("destroyed_player_id") != player_id
        or request_payload.get("battle_round") != battle_round
        or request_payload.get("phase") != phase
        or request_payload.get("resurgence_cost") != cost
        or len(selected_options) != 1
        or selected_options[0].payload != result_payload
        or result_payload.get("selection") != "spend"
        or result_payload.get("source_rule_id") != SOURCE_RULE_ID
        or result_payload.get("destroyed_unit_instance_id") != destroyed_unit_id
        or result_payload.get("model_destroyed_event_id") != model_destroyed_event_id
        or result_payload.get("resurgence_cost") != cost
    ):
        raise GameLifecycleError("Cult Ambush accepted decision context drift.")
    requested_events = tuple(
        event
        for event in event_records
        if event.event_type == "decision_requested"
        and event.payload == decision.request.to_payload()
    )
    recorded_events = tuple(
        event
        for event in event_records
        if event.event_type == "decision_recorded" and event.payload == decision.to_payload()
    )
    expected_source_requested_payload: dict[str, JsonValue] = {
        "game_id": state.game_id,
        "battle_round": battle_round,
        "active_player_id": active_player_id,
        "phase": phase,
        "player_id": player_id,
        "request_id": request_id,
        "destroyed_unit_instance_id": destroyed_unit_id,
        "model_destroyed_event_id": model_destroyed_event_id,
        "resurgence_cost": cost,
        "current_resurgence_points": current_points,
        "source_rule_id": SOURCE_RULE_ID,
    }
    source_requested_events = tuple(
        event
        for event in event_records
        if event.event_type == _RESURGENCE_REQUESTED_EVENT
        and event.payload == expected_source_requested_payload
    )
    destruction_events = tuple(
        event
        for event in event_records
        if event.event_id == model_destroyed_event_id
        and event.event_type == "model_destroyed"
        and isinstance(event.payload, dict)
        and event.payload.get("target_unit_instance_id") == destroyed_unit_id
        and event.payload.get("game_id") == state.game_id
        and event.payload.get("battle_round") == battle_round
        and event.payload.get("active_player_id") == active_player_id
    )
    if (
        len(requested_events) != 1
        or len(recorded_events) != 1
        or len(source_requested_events) != 1
        or len(destruction_events) != 1
    ):
        raise GameLifecycleError("Cult Ambush reserve entry decision/event closure drift.")
    ordered = (
        event_index_by_id[destruction_events[0].event_id],
        event_index_by_id[requested_events[0].event_id],
        event_index_by_id[source_requested_events[0].event_id],
        event_index_by_id[recorded_events[0].event_id],
        event_index_by_id[spent_event.event_id],
    )
    if tuple(sorted(ordered)) != ordered or len(set(ordered)) != len(ordered):
        raise GameLifecycleError("Cult Ambush reserve entry event ordering drift.")
    return current_points


def _validate_resource_spend(
    *,
    state: GameState,
    payload: dict[str, JsonValue],
    player_id: str,
    result_id: str,
    current_resurgence_points: int,
) -> None:
    result = _object(
        payload.get("faction_resource_result"),
        field_name="Cult Ambush faction-resource result",
    )
    transaction_payload = _object(
        result.get("transaction"),
        field_name="Cult Ambush faction-resource transaction",
    )
    cost = payload.get("resurgence_cost")
    source_id = f"{SOURCE_RULE_ID}:resurgence:{result_id}"
    ledger = state.faction_resource_ledger_for_player(player_id)
    ledger_matches = tuple(
        (index, transaction)
        for index, transaction in enumerate(ledger.transactions)
        if transaction.to_payload() == transaction_payload
    )
    prior_total = 0
    if len(ledger_matches) == 1:
        for transaction in ledger.transactions[: ledger_matches[0][0]]:
            if transaction.resource_kind != RESURGENCE_RESOURCE_KIND:
                continue
            if transaction.transaction_kind is FactionResourceTransactionKind.GAIN:
                prior_total += transaction.amount
            else:
                prior_total -= transaction.amount
    if (
        result.get("player_id") != player_id
        or result.get("battle_round") != payload.get("battle_round")
        or result.get("resource_kind") != RESURGENCE_RESOURCE_KIND
        or result.get("transaction_kind") != FactionResourceTransactionKind.SPEND.value
        or result.get("requested_amount") != cost
        or result.get("applied_amount") != cost
        or result.get("status") != "applied"
        or result.get("source_id") != source_id
        or result.get("insufficient_reason") is not None
        or len(ledger_matches) != 1
        or prior_total != current_resurgence_points
    ):
        raise GameLifecycleError("Cult Ambush resurgence resource-spend drift.")


def _entry_reserve_state(value: JsonValue) -> ReserveState:
    if not isinstance(value, dict):
        raise GameLifecycleError("Cult Ambush reserve entry must be an object.")
    try:
        reserve_state = ReserveState.from_payload(cast(ReserveStatePayload, value))
    except (KeyError, TypeError, ValueError, GameLifecycleError) as exc:
        raise GameLifecycleError("Cult Ambush reserve entry is invalid.") from exc
    if (
        reserve_state.status is not ReserveStatus.IN_RESERVES
        or reserve_state.arrived_battle_round is not None
        or reserve_state.arrived_phase is not None
        or reserve_state.destroyed_battle_round is not None
        or reserve_state.post_arrival_restrictions
        or reserve_state.restriction_battle_round is not None
        or reserve_state.large_model_exception_used
    ):
        raise GameLifecycleError("Cult Ambush event must preserve entry-time ReserveState.")
    return reserve_state


def _closed_object(
    value: object,
    *,
    field_name: str,
    expected_keys: frozenset[str],
) -> dict[str, JsonValue]:
    payload = _object(value, field_name=field_name)
    if set(payload) != set(expected_keys):
        raise GameLifecycleError(f"{field_name} fields are malformed.")
    return payload


def _object(value: object, *, field_name: str) -> dict[str, JsonValue]:
    if not isinstance(value, dict):
        raise GameLifecycleError(f"{field_name} must be an object.")
    return cast(dict[str, JsonValue], value)


def _identifier(value: object, *, field_name: str) -> str:
    if type(value) is not str or not value.strip():
        raise GameLifecycleError(f"{field_name} must be an identifier.")
    return value


__all__ = ("validated_primary_reserve_entry_occurrences",)
