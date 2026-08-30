from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, cast

from warhammer40k_core.engine.battlefield_state import (
    BattlefieldPlacementKind,
    BattlefieldTransitionBatch,
    BattlefieldTransitionBatchPayload,
    PlacementError,
)
from warhammer40k_core.engine.decision_record import DecisionRecord
from warhammer40k_core.engine.event_log import EventRecord, JsonValue
from warhammer40k_core.engine.movement_proposals import (
    PLACEMENT_PROPOSAL_DECISION_TYPE,
    MovementProposalRequest,
    PlacementProposalPayload,
    PlacementProposalPayloadPayload,
    ProposalKind,
)
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError
from warhammer40k_core.engine.phases.movement_model import (
    SELECT_MOVEMENT_ACTION_DECISION_TYPE,
    SELECT_MOVEMENT_UNIT_DECISION_TYPE,
    MovementPhaseActionKind,
)
from warhammer40k_core.engine.rules_units import rules_unit_view_from_armies
from warhammer40k_core.engine.transports import (
    DisembarkedUnitState,
    DisembarkedUnitStatePayload,
    DisembarkModeKind,
    TransportCargoState,
    TransportCargoStatePayload,
)
from warhammer40k_core.geometry.pose import GeometryError

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState


@dataclass(frozen=True, slots=True)
class TacticalDisembarkSetupBoundary:
    event: EventRecord
    disembarked_unit_state: DisembarkedUnitState
    proposal_record: DecisionRecord
    action_record: DecisionRecord


def resolve_pending_tactical_disembark_setup_boundary(
    *,
    state: GameState,
    event_records: tuple[EventRecord, ...],
    decision_records: tuple[DecisionRecord, ...],
) -> TacticalDisembarkSetupBoundary | None:
    """Authenticate the exact Disembark mutation retained by movement phase state."""

    from warhammer40k_core.engine.game_state import GameState

    if type(state) is not GameState:
        raise GameLifecycleError("Tactical Disembark setup boundary requires GameState.")
    if type(event_records) is not tuple or any(
        type(record) is not EventRecord for record in event_records
    ):
        raise GameLifecycleError("Tactical Disembark setup boundary requires EventRecords.")
    if type(decision_records) is not tuple or any(
        type(record) is not DecisionRecord for record in decision_records
    ):
        raise GameLifecycleError("Tactical Disembark setup boundary requires DecisionRecords.")
    movement_state = state.movement_phase_state
    if movement_state is None or movement_state.pending_setup_event_id is None:
        return None
    active_selection = movement_state.active_selection
    if active_selection is None:
        raise GameLifecycleError(
            "Tactical Disembark setup boundary requires active movement selection."
        )
    if state.active_player_id is None:
        raise GameLifecycleError("Tactical Disembark setup boundary requires active player.")
    if state.current_battle_phase is not BattlePhase.MOVEMENT:
        raise GameLifecycleError("Tactical Disembark setup boundary requires Movement phase.")

    event = _exact_event_record(
        event_records,
        event_id=movement_state.pending_setup_event_id,
    )
    if event.event_type != "unit_disembarked":
        raise GameLifecycleError("Tactical Disembark setup boundary event type drift.")
    payload = _json_object(event.payload, label="Tactical Disembark event payload")
    unit_instance_id = active_selection.unit_instance_id
    active_player_id = state.active_player_id
    _require_payload_value(payload, "game_id", state.game_id)
    _require_payload_value(payload, "battle_round", state.battle_round)
    _require_payload_value(payload, "phase", BattlePhase.MOVEMENT.value)
    _require_payload_value(payload, "active_player_id", active_player_id)
    _require_payload_value(payload, "unit_instance_id", unit_instance_id)
    _require_payload_value(
        payload,
        "disembark_mode",
        DisembarkModeKind.TACTICAL_DISEMBARK.value,
    )
    _require_payload_value(payload, "phase_body_status", "unit_disembarked")
    transport_unit_instance_id = _payload_string(payload, "transport_unit_instance_id")

    retained_state = state.disembarked_unit_state_for_unit(
        player_id=active_player_id,
        battle_round=state.battle_round,
        unit_instance_id=unit_instance_id,
    )
    if retained_state is None:
        raise GameLifecycleError(
            "Tactical Disembark setup boundary requires retained DisembarkedUnitState."
        )
    if (
        retained_state.transport_unit_instance_id != transport_unit_instance_id
        or retained_state.disembark_mode is not DisembarkModeKind.TACTICAL_DISEMBARK
    ):
        raise GameLifecycleError("Tactical Disembark retained state drift.")
    event_disembarked_state = _disembarked_unit_state_from_event(payload)
    if event_disembarked_state != retained_state:
        raise GameLifecycleError("Tactical Disembark event retained state drift.")

    canonical_rules_unit = rules_unit_view_from_armies(
        armies=tuple(state.army_definitions),
        unit_instance_id=unit_instance_id,
    )
    if (
        canonical_rules_unit.unit_instance_id != unit_instance_id
        or canonical_rules_unit.owner_player_id != active_player_id
    ):
        raise GameLifecycleError("Tactical Disembark canonical rules-unit identity drift.")

    proposal_record = _exact_decision_record(
        decision_records,
        request_id=_payload_string(payload, "request_id"),
        result_id=_payload_string(payload, "result_id"),
        label="Tactical Disembark proposal",
    )
    if proposal_record.request.decision_type != PLACEMENT_PROPOSAL_DECISION_TYPE:
        raise GameLifecycleError("Tactical Disembark proposal decision type drift.")
    if (
        proposal_record.request.actor_id != active_player_id
        or proposal_record.result.actor_id != active_player_id
    ):
        raise GameLifecycleError("Tactical Disembark proposal actor drift.")
    proposal_request = _proposal_request(proposal_record)
    if (
        proposal_request.request_id != proposal_record.request.request_id
        or proposal_request.decision_type != PLACEMENT_PROPOSAL_DECISION_TYPE
        or proposal_request.actor_id != active_player_id
        or proposal_request.game_id != state.game_id
        or proposal_request.battle_round != state.battle_round
        or proposal_request.phase != BattlePhase.MOVEMENT.value
        or proposal_request.unit_instance_id != unit_instance_id
        or proposal_request.proposal_kind is not ProposalKind.DISEMBARK
        or proposal_request.placement_kinds != (BattlefieldPlacementKind.DISEMBARK,)
    ):
        raise GameLifecycleError("Tactical Disembark proposal request context drift.")
    request_context = _json_object(
        proposal_request.context,
        label="Tactical Disembark proposal context",
    )
    _require_payload_value(
        request_context,
        "transport_unit_instance_id",
        transport_unit_instance_id,
    )
    _require_payload_value(
        request_context,
        "disembark_mode",
        DisembarkModeKind.TACTICAL_DISEMBARK.value,
    )
    component_unit_instance_ids = _identifier_list(
        request_context,
        "component_unit_instance_ids",
    )
    if component_unit_instance_ids != canonical_rules_unit.component_unit_instance_ids:
        raise GameLifecycleError("Tactical Disembark component inventory drift.")
    model_instance_ids = _identifier_list(request_context, "model_instance_ids")

    submitted_proposal = _placement_proposal(proposal_record)
    proposal_validation = submitted_proposal.validation_result_for_request(proposal_request)
    if not proposal_validation.is_valid:
        raise GameLifecycleError("Tactical Disembark accepted proposal lineage is invalid.")
    if (
        submitted_proposal.proposal_request_id != proposal_record.request.request_id
        or submitted_proposal.proposal_kind is not ProposalKind.DISEMBARK
        or submitted_proposal.placement_kind is not BattlefieldPlacementKind.DISEMBARK
        or submitted_proposal.unit_instance_id != unit_instance_id
        or submitted_proposal.transport_unit_instance_id != transport_unit_instance_id
        or submitted_proposal.disembark_mode is not DisembarkModeKind.TACTICAL_DISEMBARK
    ):
        raise GameLifecycleError("Tactical Disembark accepted proposal context drift.")
    rules_unit_placement = submitted_proposal.resolved_rules_unit_placement()
    if (
        rules_unit_placement.rules_unit_instance_id != unit_instance_id
        or rules_unit_placement.player_id != active_player_id
        or rules_unit_placement.component_unit_instance_ids != component_unit_instance_ids
    ):
        raise GameLifecycleError("Tactical Disembark accepted placement component drift.")
    placement_model_ids = tuple(
        sorted(placement.model_instance_id for placement in rules_unit_placement.model_placements)
    )
    if placement_model_ids != model_instance_ids:
        raise GameLifecycleError("Tactical Disembark accepted placement model inventory drift.")
    _validate_transition_batch(
        payload=payload,
        submitted_proposal=submitted_proposal,
        source_rule_id=retained_state.source_rule_id,
    )
    _validate_updated_cargo_state(
        payload=payload,
        active_player_id=active_player_id,
        battle_round=state.battle_round,
        transport_unit_instance_id=transport_unit_instance_id,
        component_unit_instance_ids=component_unit_instance_ids,
    )

    action_record = _exact_decision_record(
        decision_records,
        request_id=proposal_request.source_decision_request_id,
        result_id=proposal_request.source_decision_result_id,
        label="Tactical Disembark action",
    )
    _validate_action_record(
        record=action_record,
        state=state,
        active_player_id=active_player_id,
        unit_instance_id=unit_instance_id,
        transport_unit_instance_id=transport_unit_instance_id,
        transport_movement_status=_payload_string(payload, "transport_movement_status"),
    )
    _validate_active_selection_record(
        state=state,
        decision_records=decision_records,
        active_player_id=active_player_id,
        unit_instance_id=unit_instance_id,
    )
    return TacticalDisembarkSetupBoundary(
        event=event,
        disembarked_unit_state=retained_state,
        proposal_record=proposal_record,
        action_record=action_record,
    )


def _validate_action_record(
    *,
    record: DecisionRecord,
    state: GameState,
    active_player_id: str,
    unit_instance_id: str,
    transport_unit_instance_id: str,
    transport_movement_status: str,
) -> None:
    if (
        record.request.decision_type != SELECT_MOVEMENT_ACTION_DECISION_TYPE
        or record.request.actor_id != active_player_id
        or record.result.actor_id != active_player_id
        or record.result.selected_option_id != MovementPhaseActionKind.DISEMBARK.value
    ):
        raise GameLifecycleError("Tactical Disembark source action lineage drift.")
    request_payload = _json_object(
        record.request.payload,
        label="Tactical Disembark action request payload",
    )
    for key, expected in (
        ("game_id", state.game_id),
        ("battle_round", state.battle_round),
        ("phase", BattlePhase.MOVEMENT.value),
        ("active_player_id", active_player_id),
        ("unit_instance_id", unit_instance_id),
    ):
        _require_payload_value(request_payload, key, expected)
    result_payload = _json_object(
        record.result.payload,
        label="Tactical Disembark action result payload",
    )
    for key, expected in (
        ("movement_phase_action", MovementPhaseActionKind.DISEMBARK.value),
        ("unit_instance_id", unit_instance_id),
        ("transport_unit_instance_id", transport_unit_instance_id),
        ("disembark_mode", DisembarkModeKind.TACTICAL_DISEMBARK.value),
        ("transport_movement_status", transport_movement_status),
    ):
        _require_payload_value(result_payload, key, expected)


def _validate_active_selection_record(
    *,
    state: GameState,
    decision_records: tuple[DecisionRecord, ...],
    active_player_id: str,
    unit_instance_id: str,
) -> None:
    movement_state = state.movement_phase_state
    if movement_state is None or movement_state.active_selection is None:
        raise GameLifecycleError("Tactical Disembark active selection is missing.")
    selection = movement_state.active_selection
    record = _exact_decision_record(
        decision_records,
        request_id=selection.request_id,
        result_id=selection.result_id,
        label="Tactical Disembark unit selection",
    )
    if (
        record.request.decision_type != SELECT_MOVEMENT_UNIT_DECISION_TYPE
        or record.request.actor_id != active_player_id
        or record.result.actor_id != active_player_id
        or record.result.selected_option_id != unit_instance_id
    ):
        raise GameLifecycleError("Tactical Disembark active selection lineage drift.")


def _validate_transition_batch(
    *,
    payload: dict[str, JsonValue],
    submitted_proposal: PlacementProposalPayload,
    source_rule_id: str,
) -> None:
    raw_transition = payload.get("transition_batch")
    if not isinstance(raw_transition, dict):
        raise GameLifecycleError("Tactical Disembark event transition batch is missing.")
    try:
        transition = BattlefieldTransitionBatch.from_payload(
            cast(BattlefieldTransitionBatchPayload, raw_transition)
        )
    except (GeometryError, PlacementError, KeyError, TypeError) as exc:
        raise GameLifecycleError("Tactical Disembark event transition batch is malformed.") from exc
    placement = submitted_proposal.resolved_rules_unit_placement()
    expected_by_model_id = {
        model_placement.model_instance_id: model_placement
        for model_placement in placement.model_placements
    }
    if (
        transition.removals
        or transition.displacements
        or (
            tuple(sorted(record.model_instance_id for record in transition.placements))
            != tuple(sorted(expected_by_model_id))
        )
    ):
        raise GameLifecycleError("Tactical Disembark transition inventory drift.")
    for record in transition.placements:
        expected = expected_by_model_id[record.model_instance_id]
        if (
            record.placement_kind is not BattlefieldPlacementKind.DISEMBARK
            or record.pose != expected.pose
            or record.source_phase != BattlePhase.MOVEMENT.value
            or record.source_step != "move_units"
            or record.source_rule_id != source_rule_id
            or record.source_event_id is not None
        ):
            raise GameLifecycleError("Tactical Disembark transition record drift.")


def _validate_updated_cargo_state(
    *,
    payload: dict[str, JsonValue],
    active_player_id: str,
    battle_round: int,
    transport_unit_instance_id: str,
    component_unit_instance_ids: tuple[str, ...],
) -> None:
    raw_cargo = payload.get("updated_cargo_state")
    if not isinstance(raw_cargo, dict):
        raise GameLifecycleError("Tactical Disembark updated cargo state is missing.")
    try:
        cargo_state = TransportCargoState.from_payload(cast(TransportCargoStatePayload, raw_cargo))
    except (GameLifecycleError, KeyError, TypeError) as exc:
        raise GameLifecycleError("Tactical Disembark updated cargo state is malformed.") from exc
    if (
        cargo_state.player_id != active_player_id
        or cargo_state.transport_unit_instance_id != transport_unit_instance_id
        or cargo_state.phase_battle_round != battle_round
        or any(cargo_state.contains_unit(unit_id) for unit_id in component_unit_instance_ids)
        or any(
            not cargo_state.unit_disembarked_this_phase(unit_id)
            for unit_id in component_unit_instance_ids
        )
    ):
        raise GameLifecycleError("Tactical Disembark updated cargo state drift.")


def _proposal_request(record: DecisionRecord) -> MovementProposalRequest:
    try:
        return MovementProposalRequest.from_decision_request_payload(record.request.payload)
    except (GameLifecycleError, KeyError, TypeError) as exc:
        raise GameLifecycleError("Tactical Disembark proposal request is malformed.") from exc


def _placement_proposal(record: DecisionRecord) -> PlacementProposalPayload:
    raw_payload = _json_object(
        record.result.payload,
        label="Tactical Disembark proposal result payload",
    )
    try:
        return PlacementProposalPayload.from_payload(
            cast(PlacementProposalPayloadPayload, raw_payload)
        )
    except (GameLifecycleError, GeometryError, PlacementError, KeyError, TypeError) as exc:
        raise GameLifecycleError("Tactical Disembark proposal result is malformed.") from exc


def _disembarked_unit_state_from_event(
    payload: dict[str, JsonValue],
) -> DisembarkedUnitState:
    raw_state = payload.get("disembarked_unit_state")
    if not isinstance(raw_state, dict):
        raise GameLifecycleError("Tactical Disembark event retained state is missing.")
    try:
        return DisembarkedUnitState.from_payload(cast(DisembarkedUnitStatePayload, raw_state))
    except (GameLifecycleError, KeyError, TypeError) as exc:
        raise GameLifecycleError("Tactical Disembark event retained state is malformed.") from exc


def _exact_event_record(
    records: tuple[EventRecord, ...],
    *,
    event_id: str,
) -> EventRecord:
    matches = tuple(record for record in records if record.event_id == event_id)
    if len(matches) != 1:
        raise GameLifecycleError(
            "Tactical Disembark setup boundary must resolve exactly one EventRecord."
        )
    return matches[0]


def _exact_decision_record(
    records: tuple[DecisionRecord, ...],
    *,
    request_id: str,
    result_id: str,
    label: str,
) -> DecisionRecord:
    request_matches = tuple(record for record in records if record.request.request_id == request_id)
    result_matches = tuple(record for record in records if record.result.result_id == result_id)
    if (
        len(request_matches) != 1
        or len(result_matches) != 1
        or request_matches[0] is not result_matches[0]
    ):
        raise GameLifecycleError(f"{label} must resolve exactly one accepted DecisionRecord.")
    return request_matches[0]


def _identifier_list(payload: dict[str, JsonValue], key: str) -> tuple[str, ...]:
    raw_values = payload.get(key)
    if not isinstance(raw_values, list) or not raw_values:
        raise GameLifecycleError(f"Tactical Disembark {key} must be a non-empty list.")
    if any(type(value) is not str or not value.strip() for value in raw_values):
        raise GameLifecycleError(f"Tactical Disembark {key} must contain identifiers.")
    values = cast(list[str], raw_values)
    if len(set(values)) != len(values) or values != sorted(values):
        raise GameLifecycleError(f"Tactical Disembark {key} must be unique and sorted.")
    return tuple(values)


def _json_object(value: object, *, label: str) -> dict[str, JsonValue]:
    if not isinstance(value, dict):
        raise GameLifecycleError(f"{label} must be an object.")
    return cast(dict[str, JsonValue], value)


def _payload_string(payload: dict[str, JsonValue], key: str) -> str:
    value = payload.get(key)
    if type(value) is not str or not value.strip():
        raise GameLifecycleError(f"Tactical Disembark event missing string {key}.")
    return value


def _require_payload_value(
    payload: dict[str, JsonValue],
    key: str,
    expected: JsonValue,
) -> None:
    if payload.get(key) != expected:
        raise GameLifecycleError(f"Tactical Disembark {key} drift.")
