"""Combat's direct status occurs once, after accepted setup and completed hazard."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from warhammer40k_core.engine.battle_shock import BattleShockedUnitState
from warhammer40k_core.engine.battle_shock_state import (
    BATTLE_SHOCK_STATE_ALREADY,
    BATTLE_SHOCK_STATE_NOT_REQUIRED,
    BATTLE_SHOCK_STATE_RECORDED,
    apply_direct_battle_shock_state,
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
from warhammer40k_core.engine.mutation_decision_authority import validate_mutation_decision_closure
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError
from warhammer40k_core.engine.primary_mission_boundary_physical_authority import (
    physical_model_authority_before_event,
)
from warhammer40k_core.engine.rules_units import current_rules_unit_views_for_canonical_identity
from warhammer40k_core.engine.transports import (
    TRANSPORT_HAZARD_MORTAL_WOUNDS_EVENT_TYPE,
    CombatDisembark,
    DisembarkModeKind,
    TransportHazardMortalWounds,
    TransportHazardMortalWoundsPayload,
)

if TYPE_CHECKING:
    from warhammer40k_core.engine.decision_controller import DecisionController
    from warhammer40k_core.engine.game_state import GameState
    from warhammer40k_core.engine.phases.movement_rules_unit_disembark import (
        RulesUnitCombatDisembarkResolution,
    )

COMBAT_DISEMBARK_BATTLE_SHOCK_EVENT = "combat_disembark_battle_shock_applied"
COMBAT_DISEMBARK_SOURCE_RULE_ID = "core_rules_combat_disembark"


def complete_combat_disembark_battle_shock(
    *,
    state: GameState,
    decisions: DecisionController,
) -> None:
    """Use the just-recorded completed hazard; Emergency has its own acceptance."""
    events = tuple(decisions.event_log.records)
    if not events:
        raise GameLifecycleError("Combat Battle-shock requires its completed hazard event.")
    hazard_index = len(events) - 1
    hazard = _combat_hazard(events[hazard_index])
    if hazard is None:
        return
    _source_index, source = _setup_source(events, hazard_index, hazard)
    base = _occurrence_payload(state, events[hazard_index], source)
    if any(
        event.event_type == COMBAT_DISEMBARK_BATTLE_SHOCK_EVENT
        and isinstance(event.payload, dict)
        and event.payload.get("hazard_event_id") == base["hazard_event_id"]
        for event in events
    ):
        raise GameLifecycleError("Combat Battle-shock completion is duplicated.")
    unit_id = cast(str, base["unit_instance_id"])
    views = current_rules_unit_views_for_canonical_identity(state=state, unit_instance_id=unit_id)
    surviving = any(model.is_alive for view in views for model in view.own_models)
    update = BATTLE_SHOCK_STATE_NOT_REQUIRED
    if surviving:
        update = apply_direct_battle_shock_state(
            state=state,
            decisions=decisions,
            player_id=cast(str, base["player_id"]),
            unit_instance_id=unit_id,
            source_result_id=cast(str, base["result_id"]),
            battle_round=cast(int, base["battle_round"]),
        )
    decisions.event_log.append(
        COMBAT_DISEMBARK_BATTLE_SHOCK_EVENT, {**base, "state_update": update}
    )


def replay_combat_disembark_battle_shock(
    *,
    state: GameState,
    event_records: tuple[EventRecord, ...],
    decision_records: tuple[DecisionRecord, ...],
    event_index: int,
    replayed_states: dict[str, BattleShockedUnitState],
    owner_by_unit_id: dict[str, str],
    model_ids_by_unit_id: dict[str, tuple[str, ...]],
) -> None:
    event = event_records[event_index]
    payload = _object(event.payload)
    matches = tuple(
        (index, candidate)
        for index, candidate in enumerate(event_records[:event_index])
        if candidate.event_id == payload.get("hazard_event_id")
    )
    if len(matches) != 1:
        raise GameLifecycleError("Combat Battle-shock hazard occurrence drift.")
    hazard_index, hazard_event = matches[0]
    hazard = _combat_hazard(hazard_event)
    if hazard is None:
        raise GameLifecycleError("Combat Battle-shock requires Combat hazard authority.")
    source_index, source = _setup_source(event_records, hazard_index, hazard)
    expected_base = _occurrence_payload(state, hazard_event, source)
    if payload != {**expected_base, "state_update": payload.get("state_update")}:
        raise GameLifecycleError("Combat Battle-shock occurrence schema or source drift.")
    record = validate_mutation_decision_closure(
        event_records=event_records,
        decision_records=decision_records,
        mutation_index=source_index,
        request_id=cast(str, expected_base["request_id"]),
        result_id=cast(str, expected_base["result_id"]),
    )
    proposal = MovementProposalRequest.from_decision_request_payload(record.request.payload)
    submitted = PlacementProposalPayload.from_payload(
        cast(PlacementProposalPayloadPayload, _object(record.result.payload))
    )
    placement = _combat_disembark(hazard).placement
    if (
        record.request.decision_type != PLACEMENT_PROPOSAL_DECISION_TYPE
        or proposal.proposal_kind is not ProposalKind.DISEMBARK
        or not submitted.validation_result_for_request(proposal).is_valid
        or submitted.disembark_mode is not DisembarkModeKind.COMBAT_DISEMBARK
        or proposal.unit_instance_id != placement.selection.unit_instance_id
        or proposal.actor_id != placement.selection.player_id
        or proposal.game_id != expected_base["game_id"]
        or proposal.battle_round != expected_base["battle_round"]
        or proposal.phase != BattlePhase.MOVEMENT.value
        or submitted.transport_unit_instance_id != placement.selection.transport_unit_instance_id
        or submitted.resolved_rules_unit_placement().model_placements
        != placement.selection.attempted_placement.model_placements
    ):
        raise GameLifecycleError("Combat Battle-shock accepted setup decision drift.")
    unit_id = cast(str, expected_base["unit_instance_id"])
    player_id = cast(str, expected_base["player_id"])
    if owner_by_unit_id.get(unit_id) != player_id or unit_id not in model_ids_by_unit_id:
        raise GameLifecycleError("Combat Battle-shock canonical historical identity drift.")
    physical = physical_model_authority_before_event(
        state=state,
        event_records=event_records,
        decision_records=decision_records,
        event_index=event_index,
    )
    living_placed_ids = {
        row.model_instance_id
        for row in physical
        if row.wounds_remaining > 0 and row.presence == "battlefield"
    }
    surviving = bool(living_placed_ids.intersection(model_ids_by_unit_id[unit_id]))
    expected_update = (
        (BATTLE_SHOCK_STATE_ALREADY if unit_id in replayed_states else BATTLE_SHOCK_STATE_RECORDED)
        if surviving
        else BATTLE_SHOCK_STATE_NOT_REQUIRED
    )
    if payload.get("state_update") != expected_update:
        raise GameLifecycleError("Combat Battle-shock historical mutation drift.")
    if expected_update == BATTLE_SHOCK_STATE_RECORDED:
        replayed_states[unit_id] = BattleShockedUnitState(
            player_id=player_id,
            unit_instance_id=unit_id,
            model_instance_ids=model_ids_by_unit_id[unit_id],
            source_result_id=cast(str, expected_base["result_id"]),
            battle_round_started=cast(int, expected_base["battle_round"]),
        )


def validate_combat_battle_shock_completions(events: tuple[EventRecord, ...]) -> None:
    """Every completed Combat hazard has exactly one later direct-status occurrence."""
    for index, event in enumerate(events):
        if event.event_type != TRANSPORT_HAZARD_MORTAL_WOUNDS_EVENT_TYPE:
            continue
        hazard = _combat_hazard(event)
        if hazard is None:
            continue
        matches = tuple(
            candidate
            for candidate in events[index + 1 :]
            if candidate.event_type == COMBAT_DISEMBARK_BATTLE_SHOCK_EVENT
            and isinstance(candidate.payload, dict)
            and candidate.payload.get("hazard_event_id") == event.event_id
        )
        if len(matches) != 1:
            raise GameLifecycleError("Combat hazard lacks unique direct Battle-shock completion.")


def _combat_hazard(event: EventRecord) -> TransportHazardMortalWounds | None:
    if event.event_type != TRANSPORT_HAZARD_MORTAL_WOUNDS_EVENT_TYPE:
        raise GameLifecycleError("Combat Battle-shock requires a hazard completion.")
    payload = _object(event.payload)
    if payload.get("disembark_mode") != DisembarkModeKind.COMBAT_DISEMBARK.value:
        return None
    result = TransportHazardMortalWounds.from_payload(
        cast(TransportHazardMortalWoundsPayload, payload)
    )
    if result.pending_mortal_wound_request is not None:
        raise GameLifecycleError("Pending Combat hazard cannot apply Battle-shock.")
    return result


def _combat_disembark(
    hazard: TransportHazardMortalWounds,
) -> CombatDisembark | RulesUnitCombatDisembarkResolution:
    from warhammer40k_core.engine.phases.movement_rules_unit_disembark import (
        RulesUnitCombatDisembarkResolution,
    )

    disembark = hazard.disembark
    if not isinstance(disembark, (CombatDisembark, RulesUnitCombatDisembarkResolution)):
        raise GameLifecycleError("Combat Battle-shock requires typed Combat setup.")
    return disembark


def _setup_source(
    events: tuple[EventRecord, ...],
    hazard_index: int,
    hazard: TransportHazardMortalWounds,
) -> tuple[int, EventRecord]:
    disembark = _combat_disembark(hazard)
    placement = disembark.placement
    matches = tuple(
        (index, event)
        for index, event in enumerate(events[:hazard_index])
        if event.event_type == "unit_disembarked"
        and isinstance(event.payload, dict)
        and event.payload.get("unit_instance_id") == disembark.unit_instance_id
        and event.payload.get("battle_round") == disembark.battle_round
        and event.payload.get("disembark_mode") == DisembarkModeKind.COMBAT_DISEMBARK.value
        and event.payload.get("disembarked_unit_state")
        == (
            None
            if placement.disembarked_unit_state is None
            else placement.disembarked_unit_state.to_payload()
        )
        and event.payload.get("transition_batch")
        == (None if placement.transition_batch is None else placement.transition_batch.to_payload())
        and event.payload.get("updated_cargo_state")
        == (
            None
            if placement.updated_cargo_state is None
            else placement.updated_cargo_state.to_payload()
        )
    )
    if len(matches) != 1:
        raise GameLifecycleError("Combat Battle-shock lacks unique accepted setup occurrence.")
    return matches[0]


def _occurrence_payload(
    state: GameState, hazard: EventRecord, source: EventRecord
) -> dict[str, JsonValue]:
    payload = _object(source.payload)
    disembarked = _object(payload.get("disembarked_unit_state"))
    if (
        payload.get("game_id") != state.game_id
        or disembarked.get("source_rule_id") != COMBAT_DISEMBARK_SOURCE_RULE_ID
        or disembarked.get("disembark_mode") != DisembarkModeKind.COMBAT_DISEMBARK.value
        or payload.get("phase") != BattlePhase.MOVEMENT.value
        or payload.get("battle_round") != disembarked.get("battle_round")
        or payload.get("unit_instance_id") != disembarked.get("unit_instance_id")
        or payload.get("transport_unit_instance_id")
        != disembarked.get("transport_unit_instance_id")
        or payload.get("active_player_id") != disembarked.get("player_id")
    ):
        raise GameLifecycleError("Combat Battle-shock source rule or occurrence drift.")
    for key in ("request_id", "result_id"):
        if type(payload.get(key)) is not str or not payload[key]:
            raise GameLifecycleError("Combat Battle-shock accepted decision identity is invalid.")
    return {
        "game_id": state.game_id,
        "battle_round": payload["battle_round"],
        "player_id": disembarked["player_id"],
        "unit_instance_id": disembarked["unit_instance_id"],
        "source_rule_id": COMBAT_DISEMBARK_SOURCE_RULE_ID,
        "request_id": payload["request_id"],
        "result_id": payload["result_id"],
        "disembark_event_id": source.event_id,
        "hazard_event_id": hazard.event_id,
    }


def _object(value: JsonValue) -> dict[str, JsonValue]:
    if not isinstance(value, dict):
        raise GameLifecycleError("Combat Battle-shock requires an object payload.")
    return value
