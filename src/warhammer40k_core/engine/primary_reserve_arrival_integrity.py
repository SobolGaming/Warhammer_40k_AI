from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, cast

from warhammer40k_core.engine.battlefield_state import (
    BattlefieldTransitionBatch,
)
from warhammer40k_core.engine.decision_record import DecisionRecord
from warhammer40k_core.engine.event_log import EventRecord, JsonValue
from warhammer40k_core.engine.movement_proposals import (
    PLACEMENT_PROPOSAL_DECISION_TYPE,
    MovementProposalRequest,
    PlacementProposalPayload,
    PlacementProposalPayloadPayload,
)
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError
from warhammer40k_core.engine.phases.movement_model import (
    SELECT_MOVEMENT_ACTION_DECISION_TYPE,
    MovementPhaseActionKind,
    MovementUnitLocationKind,
)
from warhammer40k_core.engine.primary_historical_events import reserve_entry_evidence_payload
from warhammer40k_core.engine.primary_reserve_entry_provider import (
    PrimaryReserveEntryLifecycleOccurrence,
)
from warhammer40k_core.engine.primary_reserve_rule_ir_integrity import (
    expected_primary_reserve_stratagem_rule_execution_context,
    validate_exact_primary_reserve_rule_ir_placement_effect,
)
from warhammer40k_core.engine.reserve_arrival_requirements import (
    placement_kinds_for_reserve_state,
    proposal_kind_for_reserve_state,
    source_rule_id_for_placement_kind,
)
from warhammer40k_core.engine.reserves import ReserveState, ReserveStatePayload, ReserveStatus
from warhammer40k_core.engine.rule_execution import scoped_rule_ir_from_execution_payload
from warhammer40k_core.engine.rules_units import (
    current_rules_unit_views_for_identity,
    rules_unit_identities_share_lineage,
)
from warhammer40k_core.engine.stratagem_catalog import eleventh_edition_core_stratagem_index
from warhammer40k_core.engine.stratagems_eligibility import derive_stratagem_use_unit_ids
from warhammer40k_core.engine.stratagems_generic_metadata import (
    generic_rule_ir_execution_target_unit_ids,
)
from warhammer40k_core.engine.stratagems_model import (
    CORE_RAPID_INGRESS_HANDLER_ID,
    GENERIC_INGRESS_MOVE_HANDLER_ID,
    GENERIC_RULE_IR_STRATAGEM_HANDLER_ID,
    STRATAGEM_DECISION_TYPE,
    STRATAGEM_TARGET_PROPOSAL_DECISION_TYPE,
    StratagemCatalogIndex,
    StratagemCatalogRecord,
    StratagemEligibilityContext,
    StratagemUseRecord,
)
from warhammer40k_core.engine.stratagems_selection import (
    stratagem_selection_from_decision_result,
    stratagem_selection_from_target_proposal_result,
)
from warhammer40k_core.engine.unit_abilities import unit_has_deep_strike
from warhammer40k_core.rules.rule_ir import RuleIRError
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    core_movement_phase_2026_08,
)

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState


__all__ = [
    "validate_primary_reserve_arrival_event_authority",
    "validate_primary_reserve_arrival_ingress_use_authority",
    "validate_primary_reserve_arrival_placement_authority",
    "validate_primary_reserve_arrival_request_chain",
    "validate_primary_reserve_arrival_request_source",
]

_INITIAL_RESERVE_SOURCE_EVENT_TYPES = frozenset(
    (
        "aircraft_reserve_declared",
        "prebattle_redeploy_to_strategic_reserves",
        "reserve_unit_declared",
    )
)

_ARRIVAL_EVENT_COMMON_KEYS = frozenset(
    (
        "active_player_id",
        "battle_round",
        "component_unit_instance_ids",
        "game_id",
        "large_model_exception_used",
        "phase",
        "phase_body_status",
        "placement_kind",
        "player_id",
        "post_arrival_restrictions",
        "request_id",
        "result_id",
        "rules_unit_placement",
        "step",
        "transition_batch",
        "unit_instance_id",
    )
)


_GENERIC_RULE_IR_INGRESS_PARAMETERS: dict[str, JsonValue] = {
    "placement_kind": "strategic_reserves",
    "from_start_of_battle": True,
    "placement_scope": "strategic_reserves_only",
    "mark_movement_phase_reinforcement_arrival": True,
}


def validate_primary_reserve_arrival_event_authority(
    *,
    payload: dict[str, JsonValue],
    proposal_request: MovementProposalRequest,
    submitted: PlacementProposalPayload,
    ingress_use: StratagemUseRecord | None,
) -> None:
    """Close route-specific arrival event schema against the accepted result."""
    expected_keys: set[str] = set(_ARRIVAL_EVENT_COMMON_KEYS)
    if ingress_use is None:
        expected_keys.add("movement_phase_action")
        expected_step = "move_units"
        expected_status = "reinforcement_unit_arrived"
    else:
        expected_keys.add("stratagem_use")
        expected_step = "rapid_ingress"
        expected_status = "rapid_ingress_unit_arrived"
    rules_unit_placement = submitted.resolved_rules_unit_placement()
    if (
        set(payload) != expected_keys
        or payload.get("step") != expected_step
        or payload.get("phase_body_status") != expected_status
        or payload.get("component_unit_instance_ids")
        != list(rules_unit_placement.component_unit_instance_ids)
        or payload.get("rules_unit_placement") != rules_unit_placement.to_payload()
        or (ingress_use is None and payload.get("movement_phase_action") != "set_up")
        or (ingress_use is not None and payload.get("stratagem_use") != ingress_use.to_payload())
        or proposal_request.unit_instance_id != rules_unit_placement.rules_unit_instance_id
    ):
        raise GameLifecycleError("Reserve arrival route event authority drift.")


def validate_primary_reserve_arrival_request_source(
    *,
    proposal_request: MovementProposalRequest,
    expected_owner_id: str,
    placement_request_order: int,
    reserve_entry_occurrences: tuple[PrimaryReserveEntryLifecycleOccurrence, ...],
    event_records: tuple[EventRecord, ...],
    event_index_by_id: dict[str, int],
) -> None:
    """Bind the request-carried ReserveState to its preceding engine source."""
    proposal_context = proposal_request.context or {}
    raw_reserve_state = proposal_context.get("reserve_state")
    if not isinstance(raw_reserve_state, dict):
        raise GameLifecycleError("Reserve arrival request lacks ReserveState source authority.")
    try:
        carried_reserve_state = ReserveState.from_payload(
            cast(ReserveStatePayload, raw_reserve_state)
        )
    except (KeyError, TypeError, ValueError, GameLifecycleError) as exc:
        raise GameLifecycleError("Reserve arrival request ReserveState source is invalid.") from exc
    preceding_entries = tuple(
        occurrence
        for occurrence in reserve_entry_occurrences
        if occurrence.historical_unit_instance_id == proposal_request.unit_instance_id
        and occurrence.event_order < placement_request_order
    )
    if preceding_entries:
        latest_entry = max(preceding_entries, key=lambda occurrence: occurrence.event_order)
        if latest_entry.reserve_entry_state != reserve_entry_evidence_payload(
            carried_reserve_state
        ):
            raise GameLifecycleError("Reserve arrival request ReserveState source drift.")
        return
    initial_sources = tuple(
        event
        for event in event_records
        if event.event_type in _INITIAL_RESERVE_SOURCE_EVENT_TYPES
        and event_index_by_id[event.event_id] < placement_request_order
        and isinstance(event.payload, dict)
        and event.payload.get("player_id") == expected_owner_id
        and event.payload.get("unit_instance_id") == proposal_request.unit_instance_id
        and event.payload.get("reserve_state") == raw_reserve_state
    )
    if len(initial_sources) != 1:
        raise GameLifecycleError("Reserve arrival request lacks one initial ReserveState source.")


def validate_primary_reserve_arrival_request_chain(
    *,
    proposal_request: MovementProposalRequest,
    placement_decision: DecisionRecord,
    expected_owner_id: str,
    ingress_use: StratagemUseRecord | None,
    event_records: tuple[EventRecord, ...],
    decision_records: tuple[DecisionRecord, ...],
    event_index_by_id: dict[str, int],
) -> None:
    """Close the accepted placement request to its engine-authored predecessor chain.

    The spatial hash is cross-bound to the request-time engine event here.  Snapshot
    restoration cannot reconstruct historical geometry and therefore does not claim
    to recompute that hash; ReplayRunner re-execution owns that stronger check.
    """
    placement_requested = _exact_decision_events(
        event_type="decision_requested",
        payload=placement_decision.request.to_payload(),
        event_records=event_records,
        field_name="Reserve arrival placement request",
    )
    placement_recorded = _exact_decision_events(
        event_type="decision_recorded",
        payload=placement_decision.to_payload(),
        event_records=event_records,
        field_name="Reserve arrival placement result",
    )
    source_events = tuple(
        event
        for event in event_records
        if event.event_type == "placement_proposal_requested"
        and isinstance(event.payload, dict)
        and event.payload.get("request_id") == proposal_request.request_id
    )
    if len(source_events) != 1:
        raise GameLifecycleError("Reserve arrival lacks one placement source event.")
    source_event = source_events[0]
    payload = cast(dict[str, JsonValue], source_event.payload)
    if payload.get("spatial_context_hash") != proposal_request.spatial_context_hash:
        raise GameLifecycleError("Reserve arrival placement request spatial authority drift.")
    expected_source_payload = _expected_placement_source_event_payload(
        proposal_request=proposal_request,
        expected_owner_id=expected_owner_id,
        ingress_use=ingress_use,
        raw_payload=payload,
        event_records=event_records,
        decision_records=decision_records,
        event_index_by_id=event_index_by_id,
        placement_request_order=event_index_by_id[placement_requested.event_id],
    )
    if payload != expected_source_payload:
        raise GameLifecycleError("Reserve arrival placement source event authority drift.")
    placement_request_order = event_index_by_id[placement_requested.event_id]
    source_event_order = event_index_by_id[source_event.event_id]
    placement_recorded_order = event_index_by_id[placement_recorded.event_id]
    if not placement_request_order < source_event_order < placement_recorded_order:
        raise GameLifecycleError("Reserve arrival placement source event ordering drift.")
    if ingress_use is not None:
        return
    _validate_ordinary_arrival_selection_chain(
        proposal_request=proposal_request,
        expected_owner_id=expected_owner_id,
        placement_request_order=placement_request_order,
        event_records=event_records,
        decision_records=decision_records,
        event_index_by_id=event_index_by_id,
    )


def _expected_placement_source_event_payload(
    *,
    proposal_request: MovementProposalRequest,
    expected_owner_id: str,
    ingress_use: StratagemUseRecord | None,
    raw_payload: dict[str, JsonValue],
    event_records: tuple[EventRecord, ...],
    decision_records: tuple[DecisionRecord, ...],
    event_index_by_id: dict[str, int],
    placement_request_order: int,
) -> dict[str, JsonValue]:
    expected: dict[str, JsonValue] = {
        "game_id": proposal_request.game_id,
        "battle_round": proposal_request.battle_round,
        "active_player_id": (
            expected_owner_id if ingress_use is None else ingress_use.active_player_id
        ),
        "phase": proposal_request.phase,
        "unit_instance_id": proposal_request.unit_instance_id,
        "proposal_kind": proposal_request.proposal_kind.value,
        "placement_kinds": [kind.value for kind in proposal_request.placement_kinds],
        "request_id": proposal_request.request_id,
        "source_decision_request_id": proposal_request.source_decision_request_id,
        "source_decision_result_id": proposal_request.source_decision_result_id,
        "spatial_context_hash": proposal_request.spatial_context_hash,
    }
    previous_request_id = raw_payload.get("previous_proposal_request_id")
    rejected_result_id = raw_payload.get("rejected_result_id")
    is_retry = previous_request_id is not None or rejected_result_id is not None
    if is_retry:
        previous_id = _required_event_identifier(
            previous_request_id,
            field_name="Reserve arrival previous placement request",
        )
        rejected_id = _required_event_identifier(
            rejected_result_id,
            field_name="Reserve arrival rejected placement result",
        )
        _validate_placement_retry_predecessor(
            proposal_request=proposal_request,
            previous_request_id=previous_id,
            rejected_result_id=rejected_id,
            expected_owner_id=expected_owner_id,
            ingress_use=ingress_use,
            event_records=event_records,
            decision_records=decision_records,
            event_index_by_id=event_index_by_id,
            placement_request_order=placement_request_order,
        )
        expected.update(
            {
                "previous_proposal_request_id": previous_id,
                "rejected_result_id": rejected_id,
            }
        )
    if ingress_use is None:
        expected.update(
            {
                "step": "move_units",
                "phase_body_status": "placement_proposal_required",
            }
        )
        return expected
    expected["player_id"] = expected_owner_id
    if is_retry:
        expected["phase_body_status"] = "rapid_ingress_placement_proposal_required"
        return expected
    expected["stratagem_use_id"] = ingress_use.use_id
    if ingress_use.handler_id == CORE_RAPID_INGRESS_HANDLER_ID:
        status = "rapid_ingress_placement_proposal_required"
    elif ingress_use.handler_id == GENERIC_INGRESS_MOVE_HANDLER_ID:
        status = "ingress_move_placement_proposal_required"
    elif ingress_use.handler_id == GENERIC_RULE_IR_STRATAGEM_HANDLER_ID:
        status = "generic_rule_ir_placement_proposal_required"
    else:
        raise GameLifecycleError("Reserve arrival placement source handler is unsupported.")
    expected["phase_body_status"] = status
    return expected


def _validate_placement_retry_predecessor(
    *,
    proposal_request: MovementProposalRequest,
    previous_request_id: str,
    rejected_result_id: str,
    expected_owner_id: str,
    ingress_use: StratagemUseRecord | None,
    event_records: tuple[EventRecord, ...],
    decision_records: tuple[DecisionRecord, ...],
    event_index_by_id: dict[str, int],
    placement_request_order: int,
) -> None:
    predecessors = tuple(
        decision
        for decision in decision_records
        if decision.request.request_id == previous_request_id
        and decision.result.result_id == rejected_result_id
    )
    if len(predecessors) != 1:
        raise GameLifecycleError("Reserve arrival retry lacks one rejected predecessor.")
    predecessor = predecessors[0]
    try:
        previous_proposal = MovementProposalRequest.from_decision_request_payload(
            predecessor.request.payload
        )
        rejected_submission = PlacementProposalPayload.from_payload(
            cast(PlacementProposalPayloadPayload, predecessor.result.payload)
        )
    except (KeyError, TypeError, ValueError, GameLifecycleError) as exc:
        raise GameLifecycleError("Reserve arrival retry predecessor is invalid.") from exc
    if (
        predecessor.request.decision_type != PLACEMENT_PROPOSAL_DECISION_TYPE
        or predecessor.result.decision_type != PLACEMENT_PROPOSAL_DECISION_TYPE
        or predecessor.request.actor_id != expected_owner_id
        or predecessor.result.actor_id != expected_owner_id
        or previous_proposal.request_id != previous_request_id
        or previous_proposal.game_id != proposal_request.game_id
        or previous_proposal.battle_round != proposal_request.battle_round
        or previous_proposal.phase != proposal_request.phase
        or previous_proposal.unit_instance_id != proposal_request.unit_instance_id
        or previous_proposal.proposal_kind is not proposal_request.proposal_kind
        or previous_proposal.source_decision_request_id
        != proposal_request.source_decision_request_id
        or previous_proposal.source_decision_result_id != proposal_request.source_decision_result_id
        or previous_proposal.placement_kinds != proposal_request.placement_kinds
        or previous_proposal.context != proposal_request.context
        or not rejected_submission.validation_result_for_request(previous_proposal).is_valid
    ):
        raise GameLifecycleError("Reserve arrival retry predecessor authority drift.")
    requested = _exact_decision_events(
        event_type="decision_requested",
        payload=predecessor.request.to_payload(),
        event_records=event_records,
        field_name="Reserve arrival retry predecessor request",
    )
    recorded = _exact_decision_events(
        event_type="decision_recorded",
        payload=predecessor.to_payload(),
        event_records=event_records,
        field_name="Reserve arrival retry predecessor result",
    )
    _validate_retry_invalid_event(
        previous_proposal=previous_proposal,
        rejected_submission=rejected_submission,
        rejected_result_id=rejected_result_id,
        expected_owner_id=expected_owner_id,
        ingress_use=ingress_use,
        event_records=event_records,
        event_index_by_id=event_index_by_id,
        predecessor_recorded_order=event_index_by_id[recorded.event_id],
        placement_request_order=placement_request_order,
    )
    if not (
        event_index_by_id[requested.event_id]
        < event_index_by_id[recorded.event_id]
        < placement_request_order
    ):
        raise GameLifecycleError("Reserve arrival retry predecessor ordering drift.")


def _validate_retry_invalid_event(
    *,
    previous_proposal: MovementProposalRequest,
    rejected_submission: PlacementProposalPayload,
    rejected_result_id: str,
    expected_owner_id: str,
    ingress_use: StratagemUseRecord | None,
    event_records: tuple[EventRecord, ...],
    event_index_by_id: dict[str, int],
    predecessor_recorded_order: int,
    placement_request_order: int,
) -> None:
    event_type = (
        "reinforcement_placement_invalid"
        if ingress_use is None
        else "rapid_ingress_placement_invalid"
    )
    matches = tuple(
        event
        for event in event_records
        if event.event_type == event_type
        and isinstance(event.payload, dict)
        and event.payload.get("request_id") == previous_proposal.request_id
        and event.payload.get("result_id") == rejected_result_id
    )
    if len(matches) != 1:
        raise GameLifecycleError("Reserve arrival retry lacks one invalid predecessor event.")
    event = matches[0]
    payload = cast(dict[str, JsonValue], event.payload)
    expected_keys = {
        "active_player_id",
        "battle_round",
        "coherency_result",
        "game_id",
        "phase",
        "phase_body_status",
        "placement_kind",
        "request_id",
        "result_id",
        "unit_instance_id",
        "violations",
    }
    if ingress_use is None:
        expected_keys.add("step")
        expected_active_player_id = expected_owner_id
        expected_status = "reinforcement_placement_invalid"
    else:
        expected_keys.update(("player_id", "proposal_kind"))
        expected_active_player_id = _required_event_identifier(
            ingress_use.active_player_id,
            field_name="Reserve arrival retry active player",
        )
        expected_status = "rapid_ingress_placement_invalid"
    violations = payload.get("violations")
    if (
        set(payload) != expected_keys
        or payload.get("game_id") != previous_proposal.game_id
        or payload.get("battle_round") != previous_proposal.battle_round
        or payload.get("active_player_id") != expected_active_player_id
        or payload.get("phase") != previous_proposal.phase
        or payload.get("unit_instance_id") != previous_proposal.unit_instance_id
        or payload.get("placement_kind") != rejected_submission.placement_kind.value
        or payload.get("phase_body_status") != expected_status
        or not isinstance(violations, list)
        or not violations
        or not isinstance(payload.get("coherency_result"), dict)
        or (ingress_use is None and payload.get("step") != "move_units")
        or (
            ingress_use is not None
            and (
                payload.get("player_id") != expected_owner_id
                or payload.get("proposal_kind") != previous_proposal.proposal_kind.value
            )
        )
    ):
        raise GameLifecycleError("Reserve arrival retry invalid event authority drift.")
    invalid_event_order = event_index_by_id[event.event_id]
    if not predecessor_recorded_order < invalid_event_order < placement_request_order:
        raise GameLifecycleError("Reserve arrival retry invalid event ordering drift.")


def _validate_ordinary_arrival_selection_chain(
    *,
    proposal_request: MovementProposalRequest,
    expected_owner_id: str,
    placement_request_order: int,
    event_records: tuple[EventRecord, ...],
    decision_records: tuple[DecisionRecord, ...],
    event_index_by_id: dict[str, int],
) -> None:
    source_decisions = tuple(
        decision
        for decision in decision_records
        if decision.request.request_id == proposal_request.source_decision_request_id
        and decision.result.result_id == proposal_request.source_decision_result_id
    )
    if len(source_decisions) != 1:
        raise GameLifecycleError("Reserve arrival placement request predecessor drift.")
    source = source_decisions[0]
    raw_reserve_state = (proposal_request.context or {}).get("reserve_state")
    if not isinstance(raw_reserve_state, dict):
        raise GameLifecycleError("Reserve arrival selection lacks ReserveState authority.")
    try:
        reserve_state = ReserveState.from_payload(cast(ReserveStatePayload, raw_reserve_state))
    except (KeyError, TypeError, ValueError, GameLifecycleError) as exc:
        raise GameLifecycleError("Reserve arrival selection ReserveState is invalid.") from exc
    expected_request_payload: dict[str, JsonValue] = {
        "game_id": proposal_request.game_id,
        "battle_round": proposal_request.battle_round,
        "phase": proposal_request.phase,
        "active_player_id": expected_owner_id,
        "unit_instance_id": proposal_request.unit_instance_id,
        "source_rule_id": core_movement_phase_2026_08.MOVE_UNITS_STEP_SOURCE_ID,
    }
    expected_result_payload: dict[str, JsonValue] = {
        "movement_phase_action": MovementPhaseActionKind.INGRESS.value,
        "unit_instance_id": proposal_request.unit_instance_id,
        "unit_location": MovementUnitLocationKind.STRATEGIC_RESERVES.value,
        "reserve_kind": reserve_state.reserve_kind.value,
        "reserve_origin": reserve_state.reserve_origin.value,
    }
    if (
        source.request.decision_type != SELECT_MOVEMENT_ACTION_DECISION_TYPE
        or source.result.decision_type != SELECT_MOVEMENT_ACTION_DECISION_TYPE
        or source.request.actor_id != expected_owner_id
        or source.result.actor_id != expected_owner_id
        or source.request.payload != expected_request_payload
        or source.result.selected_option_id != MovementPhaseActionKind.INGRESS.value
        or source.result.payload != expected_result_payload
    ):
        raise GameLifecycleError("Reserve arrival reinforcement selection authority drift.")
    requested = _exact_decision_events(
        event_type="decision_requested",
        payload=source.request.to_payload(),
        event_records=event_records,
        field_name="Reserve arrival reinforcement selection request",
    )
    recorded = _exact_decision_events(
        event_type="decision_recorded",
        payload=source.to_payload(),
        event_records=event_records,
        field_name="Reserve arrival reinforcement selection result",
    )
    expected_terminal_payload: dict[str, JsonValue] = {
        "game_id": proposal_request.game_id,
        "battle_round": proposal_request.battle_round,
        "active_player_id": expected_owner_id,
        "phase": proposal_request.phase,
        "step": "move_units",
        "unit_instance_id": proposal_request.unit_instance_id,
        "request_id": source.result.request_id,
        "result_id": source.result.result_id,
        "selected_move_type": MovementPhaseActionKind.INGRESS.value,
        "phase_body_status": "reinforcement_unit_selected",
    }
    terminal_events = tuple(
        event
        for event in event_records
        if event.event_type == "reinforcement_unit_selected"
        and event.payload == expected_terminal_payload
    )
    if len(terminal_events) != 1:
        raise GameLifecycleError("Reserve arrival reinforcement selection event closure drift.")
    if not (
        event_index_by_id[requested.event_id]
        < event_index_by_id[recorded.event_id]
        < event_index_by_id[terminal_events[0].event_id]
        < placement_request_order
    ):
        raise GameLifecycleError("Reserve arrival reinforcement selection ordering drift.")


def _exact_decision_events(
    *,
    event_type: str,
    payload: object,
    event_records: tuple[EventRecord, ...],
    field_name: str,
) -> EventRecord:
    matches = tuple(
        event
        for event in event_records
        if event.event_type == event_type and event.payload == payload
    )
    if len(matches) != 1:
        raise GameLifecycleError(f"{field_name} event closure drift.")
    return matches[0]


def _required_event_identifier(value: object, *, field_name: str) -> str:
    if type(value) is not str or not value:
        raise GameLifecycleError(f"{field_name} must be an identifier.")
    return value


def validate_primary_reserve_arrival_ingress_use_authority(
    *,
    state: GameState,
    use: StratagemUseRecord,
    proposal_request: MovementProposalRequest,
    event_records: tuple[EventRecord, ...],
    decision_records: tuple[DecisionRecord, ...],
    event_index_by_id: dict[str, int],
    placement_request_order: int,
    stratagem_indexes_by_player_id: Mapping[str, StratagemCatalogIndex] | None,
) -> None:
    """Authenticate an arrival against its selected active Stratagem and effect."""
    decisions = tuple(
        decision
        for decision in decision_records
        if decision.request.request_id == use.request_id
        and decision.result.result_id == use.result_id
    )
    if len(decisions) != 1:
        raise GameLifecycleError("Ingress use lacks one accepted Stratagem decision.")
    decision = decisions[0]
    if decision.request.decision_type == STRATAGEM_DECISION_TYPE:
        selection = stratagem_selection_from_decision_result(decision.result)
    elif decision.request.decision_type == STRATAGEM_TARGET_PROPOSAL_DECISION_TYPE:
        selection = stratagem_selection_from_target_proposal_result(decision.result)
    else:
        selection = None
    if selection is None:
        raise GameLifecycleError("Ingress use Stratagem selection is malformed.")
    context, selected_record, target_binding, effect_selection = selection
    active_record = _active_selected_stratagem_record(
        player_id=use.player_id,
        selected_record=selected_record,
        stratagem_indexes_by_player_id=stratagem_indexes_by_player_id,
    )
    definition = active_record.definition
    expected_targeted_ids, expected_affected_ids = derive_stratagem_use_unit_ids(
        state=state,
        definition=definition,
        context=context,
        target_binding=target_binding,
        effect_selection=effect_selection,
    )
    target_lineage_ids = set(use.targeted_unit_instance_ids) | set(use.affected_unit_instance_ids)
    proposal_context = proposal_request.context or {}
    authority_checks = (
        ("request actor", decision.request.actor_id == use.player_id),
        ("result actor", decision.result.actor_id == use.player_id),
        ("selected option", decision.result.selected_option_id == use.selected_option_id),
        ("game", context.game_id == state.game_id),
        ("player", context.player_id == use.player_id),
        ("battle round", context.battle_round == use.battle_round),
        ("phase", context.phase is use.phase),
        ("active player", context.active_player_id == use.active_player_id),
        ("timing window", context.timing_window_id == use.timing_window_id),
        ("Stratagem ID", definition.stratagem_id == use.stratagem_id),
        ("source", definition.source_id == use.source_id),
        ("handler", definition.handler_id == use.handler_id),
        ("effect payload", definition.effect_payload == use.effect_payload),
        ("target binding", target_binding == use.target_binding),
        ("effect selection", effect_selection == use.effect_selection),
        ("targeted units", use.targeted_unit_instance_ids == expected_targeted_ids),
        ("affected units", use.affected_unit_instance_ids == expected_affected_ids),
        ("effect resolution", use.effects_resolved),
        (
            "target lineage",
            any(
                rules_unit_identities_share_lineage(
                    state=state,
                    first_unit_instance_id=proposal_request.unit_instance_id,
                    second_unit_instance_id=candidate_id,
                )
                for candidate_id in target_lineage_ids
            ),
        ),
        ("proposal handler", proposal_context.get("stratagem_handler_id") == use.handler_id),
        ("proposal use", proposal_context.get("stratagem_use") == use.to_payload()),
    )
    drift_fields = tuple(field_name for field_name, valid in authority_checks if not valid)
    if drift_fields:
        raise GameLifecycleError(
            "Ingress use accepted Stratagem authority drift: " + ", ".join(drift_fields)
        )
    generic_effect: dict[str, JsonValue] | None = None
    if use.handler_id == GENERIC_INGRESS_MOVE_HANDLER_ID:
        _validate_generic_ingress_proposal_context(use=use, proposal_context=proposal_context)
        _validate_generic_ingress_move_effect(definition.effect_payload)
    elif use.handler_id == GENERIC_RULE_IR_STRATAGEM_HANDLER_ID:
        _validate_generic_ingress_proposal_context(use=use, proposal_context=proposal_context)
        generic_effect = _validate_generic_rule_ir_ingress(
            state=state,
            use=use,
            eligibility_context=context,
            target_player_id=target_binding.target_player_id,
            proposal_context=proposal_context,
            active_effect_payload=definition.effect_payload,
        )
    elif use.handler_id != CORE_RAPID_INGRESS_HANDLER_ID:
        raise GameLifecycleError("Reserve arrival uses an unsupported ingress handler.")
    _validate_ingress_decision_and_event_closure(
        decision=decision,
        use=use,
        generic_effect=generic_effect,
        event_records=event_records,
        event_index_by_id=event_index_by_id,
        placement_request_order=placement_request_order,
    )


def validate_primary_reserve_arrival_placement_authority(
    *,
    state: GameState,
    proposal_request: MovementProposalRequest,
    submitted: PlacementProposalPayload,
    transition: BattlefieldTransitionBatch,
    expected_owner_id: str,
) -> None:
    """Re-run immutable request/result and ReserveState placement authority."""
    if type(submitted) is not PlacementProposalPayload:
        raise GameLifecycleError("Reserve arrival placement submission is malformed.")
    if type(transition) is not BattlefieldTransitionBatch:
        raise GameLifecycleError("Reserve arrival transition is malformed.")
    validation = submitted.validation_result_for_request(proposal_request)
    if not validation.is_valid:
        raise GameLifecycleError("Reserve arrival request/result proposal authority drift.")
    proposal_context = proposal_request.context or {}
    raw_reserve_state = proposal_context.get("reserve_state")
    if not isinstance(raw_reserve_state, dict):
        raise GameLifecycleError("Reserve arrival request lacks ReserveState authority.")
    try:
        reserve_state = ReserveState.from_payload(cast(ReserveStatePayload, raw_reserve_state))
    except (KeyError, TypeError, ValueError, GameLifecycleError) as exc:
        raise GameLifecycleError("Reserve arrival request ReserveState is invalid.") from exc
    current_views = current_rules_unit_views_for_identity(
        state=state,
        unit_instance_id=proposal_request.unit_instance_id,
    )
    owner_ids = {view.owner_player_id for view in current_views}
    components = {
        component.unit.unit_instance_id: component.unit
        for view in current_views
        for component in view.components
    }
    expected_placement_kinds = placement_kinds_for_reserve_state(
        reserve_state,
        all_components_have_deep_strike=all(
            unit_has_deep_strike(unit) for unit in components.values()
        ),
    )
    expected_proposal_kind = proposal_kind_for_reserve_state(reserve_state)
    submitted_rules_unit = submitted.resolved_rules_unit_placement()
    submitted_model_ids = {
        placement.model_instance_id for placement in submitted_rules_unit.model_placements
    }
    context_component_ids = _identifier_list(
        proposal_context.get("component_unit_instance_ids"),
        field_name="Reserve arrival request component IDs",
    )
    context_model_ids = _identifier_list(
        proposal_context.get("model_instance_ids"),
        field_name="Reserve arrival request model IDs",
    )
    authoritative_model_ids = {
        model.model_instance_id for unit in components.values() for model in unit.own_models
    }
    authoritative_model_ids_by_component = {
        unit_instance_id: {model.model_instance_id for model in unit.own_models}
        for unit_instance_id, unit in components.items()
    }
    authoritative_army_id_by_component = {
        unit.unit_instance_id: army.army_id
        for army in state.army_definitions
        if army.player_id == expected_owner_id
        for unit in army.units
        if unit.unit_instance_id in components
    }
    currently_alive_model_ids = {
        model.model_instance_id
        for unit in components.values()
        for model in unit.own_models
        if model.is_alive
    }
    handler_id = proposal_context.get("stratagem_handler_id")
    expected_context_keys = {
        "component_unit_instance_ids",
        "model_instance_ids",
        "reserve_state",
    }
    if handler_id is None:
        expected_context_keys.add("step")
    else:
        expected_context_keys.update(("stratagem_handler_id", "stratagem_use"))
        if handler_id in {
            GENERIC_INGRESS_MOVE_HANDLER_ID,
            GENERIC_RULE_IR_STRATAGEM_HANDLER_ID,
        }:
            expected_context_keys.update(
                (
                    "from_start_of_battle",
                    "mark_movement_phase_reinforcement_arrival",
                    "placement_scope",
                )
            )
        if handler_id == GENERIC_RULE_IR_STRATAGEM_HANDLER_ID:
            expected_context_keys.update(("generic_rule_effect", "generic_rule_execution_result"))
    expected_transition_source_rule_id = source_rule_id_for_placement_kind(submitted.placement_kind)
    expected_component_ids = tuple(sorted(components))
    submitted_component_authority = all(
        placement.army_id == authoritative_army_id_by_component.get(placement.unit_instance_id)
        and placement.player_id == expected_owner_id
        and {model.model_instance_id for model in placement.model_placements}.issubset(
            authoritative_model_ids_by_component.get(placement.unit_instance_id, set())
        )
        for placement in submitted_rules_unit.component_unit_placements
    )
    authority_checks = (
        ("reserve status", reserve_state.status is ReserveStatus.IN_RESERVES),
        ("reserve owner", reserve_state.player_id == expected_owner_id),
        (
            "reserve unit identity",
            reserve_state.unit_instance_id == proposal_request.unit_instance_id,
        ),
        ("current owner", owner_ids == {expected_owner_id}),
        ("current components", bool(components)),
        ("rules-unit owner", submitted_rules_unit.player_id == expected_owner_id),
        (
            "rules-unit identity",
            submitted_rules_unit.rules_unit_instance_id == proposal_request.unit_instance_id,
        ),
        (
            "submitted components",
            submitted_rules_unit.component_unit_instance_ids == expected_component_ids
            and submitted_component_authority,
        ),
        ("proposal kind", proposal_request.proposal_kind is expected_proposal_kind),
        ("placement kinds", proposal_request.placement_kinds == expected_placement_kinds),
        ("context schema", set(proposal_context) == expected_context_keys),
        (
            "context components",
            context_component_ids == expected_component_ids,
        ),
        (
            "context models",
            context_model_ids == tuple(sorted(submitted_model_ids)),
        ),
        ("submitted models", bool(submitted_model_ids)),
        (
            "submitted model authority",
            submitted_model_ids.issubset(authoritative_model_ids),
        ),
        (
            "alive model coverage",
            currently_alive_model_ids.issubset(submitted_model_ids),
        ),
        (
            "required arrival timing",
            not reserve_state.has_required_arrival
            or (
                reserve_state.required_arrival_battle_round == proposal_request.battle_round
                and reserve_state.required_arrival_phase == proposal_request.phase
            ),
        ),
    )
    drift_fields = tuple(field_name for field_name, valid in authority_checks if not valid)
    if drift_fields:
        raise GameLifecycleError(
            "Reserve arrival request ReserveState authority drift: " + ", ".join(drift_fields)
        )
    if any(
        placement.source_phase != BattlePhase.MOVEMENT.value
        or placement.source_step != "move_units"
        or placement.source_rule_id != expected_transition_source_rule_id
        or placement.source_event_id is not None
        for placement in transition.placements
    ):
        raise GameLifecycleError("Reserve arrival transition source authority drift.")
    current_view_ids = {view.unit_instance_id for view in current_views}
    current_reserve_states = tuple(
        stored for stored in state.reserve_states if stored.unit_instance_id in current_view_ids
    )
    battlefield_state = state.battlefield_state
    if (
        state.battle_round == proposal_request.battle_round
        and state.current_battle_phase is BattlePhase.MOVEMENT
        and current_reserve_states
        and all(
            stored.status is ReserveStatus.ARRIVED
            and stored.arrived_battle_round == proposal_request.battle_round
            and stored.arrived_phase == proposal_request.phase
            for stored in current_reserve_states
        )
        and (
            battlefield_state is None
            or any(
                battlefield_state.model_placement_or_none(placement.model_instance_id) != placement
                for placement in submitted_rules_unit.model_placements
            )
        )
    ):
        raise GameLifecycleError("Reserve arrival final battlefield placement drift.")


def _validate_generic_ingress_proposal_context(
    *,
    use: StratagemUseRecord,
    proposal_context: dict[str, JsonValue],
) -> None:
    if (
        proposal_context.get("from_start_of_battle") is not True
        or proposal_context.get("placement_scope") != "strategic_reserves_only"
        or proposal_context.get("mark_movement_phase_reinforcement_arrival")
        is not (use.active_player_id == use.player_id)
    ):
        raise GameLifecycleError("Generic ingress proposal context authority drift.")


def _active_selected_stratagem_record(
    *,
    player_id: str,
    selected_record: object,
    stratagem_indexes_by_player_id: Mapping[str, StratagemCatalogIndex] | None,
) -> StratagemCatalogRecord:
    if type(selected_record) is not StratagemCatalogRecord:
        raise GameLifecycleError("Ingress selected Stratagem record is malformed.")
    if selected_record.definition.handler_id == CORE_RAPID_INGRESS_HANDLER_ID:
        authority_index = eleventh_edition_core_stratagem_index()
    else:
        if stratagem_indexes_by_player_id is None:
            raise GameLifecycleError("Ingress requires active runtime Stratagem catalog authority.")
        player_index = stratagem_indexes_by_player_id.get(player_id)
        if type(player_index) is not StratagemCatalogIndex:
            raise GameLifecycleError("Ingress lacks its active player Stratagem index.")
        authority_index = player_index
    active_records = tuple(
        record
        for record in authority_index.all_records()
        if record.record_id == selected_record.record_id
    )
    if (
        len(active_records) != 1
        or active_records[0].to_payload() != selected_record.to_payload()
        or active_records[0].disabled
    ):
        raise GameLifecycleError("Ingress active Stratagem catalog authority drift.")
    return active_records[0]


def _validate_generic_ingress_move_effect(effect_payload: JsonValue) -> None:
    if not isinstance(effect_payload, dict):
        raise GameLifecycleError("Ingress move effect must be an object.")
    if (
        effect_payload.get("effect_kind") != "ingress_move"
        or effect_payload.get("from_start_of_battle") is not True
        or effect_payload.get("placement_scope") != "strategic_reserves_only"
    ):
        raise GameLifecycleError("Ingress move effect authority drift.")


def _validate_generic_rule_ir_ingress(
    *,
    state: GameState,
    use: StratagemUseRecord,
    eligibility_context: StratagemEligibilityContext,
    target_player_id: str | None,
    proposal_context: dict[str, JsonValue],
    active_effect_payload: JsonValue,
) -> dict[str, JsonValue]:
    try:
        rule_ir = scoped_rule_ir_from_execution_payload(active_effect_payload)
    except RuleIRError as exc:
        raise GameLifecycleError("Ingress active RuleIR is invalid.") from exc
    execution = _json_object(
        proposal_context.get("generic_rule_execution_result"),
        field_name="Ingress RuleIR execution result",
    )
    generic_effect = _json_object(
        proposal_context.get("generic_rule_effect"),
        field_name="Ingress RuleIR effect",
    )
    validated_effect = validate_exact_primary_reserve_rule_ir_placement_effect(
        rule_ir=rule_ir,
        executed_effect_payload=generic_effect,
    )
    expected_execution_targets = generic_rule_ir_execution_target_unit_ids(
        state=state,
        use_record=use,
    )
    expected_effect_context = expected_primary_reserve_stratagem_rule_execution_context(
        state=state,
        use=use,
        eligibility_context=eligibility_context,
        target_player_id=target_player_id,
        target_unit_instance_ids=expected_execution_targets,
    )
    if (
        execution.get("rule_id") != rule_ir.rule_id
        or execution.get("source_id") != rule_ir.source_id
        or execution.get("rule_ir_hash") != rule_ir.ir_hash()
        or execution.get("status") != "applied"
        or execution.get("reason") is not None
        or execution.get("applied_clause_ids") != [generic_effect["clause_id"]]
        or execution.get("effect_payloads") != [generic_effect]
        or generic_effect.get("context") != expected_effect_context
        or validated_effect.parameters != _GENERIC_RULE_IR_INGRESS_PARAMETERS
        or set(validated_effect.target_unit_instance_ids) != set(expected_execution_targets)
        or len(validated_effect.target_unit_instance_ids) != len(expected_execution_targets)
    ):
        raise GameLifecycleError("Ingress RuleIR placement authority drift.")
    return generic_effect


def _validate_ingress_decision_and_event_closure(
    *,
    decision: DecisionRecord,
    use: StratagemUseRecord,
    generic_effect: dict[str, JsonValue] | None,
    event_records: tuple[EventRecord, ...],
    event_index_by_id: dict[str, int],
    placement_request_order: int,
) -> None:
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
    use_events = tuple(
        event
        for event in event_records
        if event.event_type == "stratagem_used" and event.payload == use.to_payload()
    )
    effect_events = (
        ()
        if generic_effect is None
        else tuple(
            event
            for event in event_records
            if event.event_type == "rule_execution_effect_applied"
            and event.payload == generic_effect
        )
    )
    expected_effect_count = 0 if generic_effect is None else 1
    if (
        len(requested_events) != 1
        or len(recorded_events) != 1
        or len(use_events) != 1
        or len(effect_events) != expected_effect_count
    ):
        raise GameLifecycleError("Ingress use decision/event closure drift.")
    ordered_event_ids = [
        requested_events[0].event_id,
        recorded_events[0].event_id,
        use_events[0].event_id,
    ]
    if effect_events:
        ordered_event_ids.append(effect_events[0].event_id)
    ordered_event_indexes = [event_index_by_id[event_id] for event_id in ordered_event_ids]
    if ordered_event_indexes != sorted(ordered_event_indexes) or (
        ordered_event_indexes[-1] >= placement_request_order
    ):
        raise GameLifecycleError("Ingress use decision/event ordering drift.")


def _json_object(value: object, *, field_name: str) -> dict[str, JsonValue]:
    if not isinstance(value, dict):
        raise GameLifecycleError(f"{field_name} must be an object.")
    return cast(dict[str, JsonValue], value)


def _identifier_list(value: object, *, field_name: str) -> tuple[str, ...]:
    if type(value) is not list:
        raise GameLifecycleError(f"{field_name} must be an identifier list.")
    raw_items = cast(list[object], value)
    if any(type(item) is not str or not item for item in raw_items):
        raise GameLifecycleError(f"{field_name} must be an identifier list.")
    identifiers = tuple(cast(str, item) for item in raw_items)
    if len(set(identifiers)) != len(identifiers):
        raise GameLifecycleError(f"{field_name} must not contain duplicates.")
    return identifiers
