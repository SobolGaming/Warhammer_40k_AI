from __future__ import annotations

from typing import cast

from warhammer40k_core.core.ruleset_descriptor import (
    FightOrderingBandKind,
    FightPhaseStepKind,
)
from warhammer40k_core.engine import lifecycle_state_queries as _lsq
from warhammer40k_core.engine.battlefield_state import BattlefieldScenario, PlacementError
from warhammer40k_core.engine.decision_record import DecisionRecord
from warhammer40k_core.engine.event_log import EventRecord, JsonValue
from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.movement_proposals import (
    PLACEMENT_PROPOSAL_DECISION_TYPE,
    MovementProposalRequest,
    PlacementProposalPayload,
    PlacementProposalPayloadPayload,
)
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError, GameLifecycleStage
from warhammer40k_core.engine.rules_units import (
    current_rules_unit_views_for_canonical_identity,
    rules_unit_views_from_armies,
)
from warhammer40k_core.engine.tactical_disembark_setup_boundary import (
    resolve_pending_tactical_disembark_setup_boundary,
)
from warhammer40k_core.engine.transport_disembark_state import (
    DisembarkedUnitState,
    DisembarkModeKind,
    TransportRestrictionOverrideKind,
    disembarked_unit_state_from_event_payload,
)
from warhammer40k_core.geometry.pose import GeometryError


def validate_fight_phase_state_consistency(
    *,
    state: GameState,
    event_records: tuple[EventRecord, ...],
) -> None:
    fight_state = state.fight_phase_state
    if fight_state is None:
        return
    if state.stage is not GameLifecycleStage.BATTLE:
        raise GameLifecycleError("fight_phase_state requires battle stage.")
    forced_context = fight_state.forced_activation_context
    if forced_context is None:
        if state.current_battle_phase is not BattlePhase.FIGHT:
            raise GameLifecycleError("fight_phase_state requires FIGHT phase.")
    else:
        if state.current_battle_phase is None or (
            state.current_battle_phase.value != forced_context.source_phase.value
        ):
            raise GameLifecycleError("Forced fight_phase_state source phase drift.")
        if fight_state.current_step is not FightPhaseStepKind.FIGHT:
            raise GameLifecycleError("Forced fight_phase_state must remain in the Fight step.")
        if fight_state.pile_in_state is not None or fight_state.consolidate_state is not None:
            raise GameLifecycleError(
                "Forced fight_phase_state cannot carry global movement-step state."
            )
        if fight_state.phase_complete:
            raise GameLifecycleError("Forced fight_phase_state cannot be phase complete.")
    if state.active_player_id is None:
        raise GameLifecycleError("fight_phase_state requires active player.")
    if fight_state.active_player_id != state.active_player_id:
        raise GameLifecycleError("fight_phase_state active player drift.")
    if fight_state.battle_round != state.battle_round:
        raise GameLifecycleError("fight_phase_state battle round drift.")
    if state.battlefield_state is None:
        raise GameLifecycleError("fight_phase_state requires battlefield_state.")
    fight_order_state = fight_state.fight_order_state
    if fight_order_state.next_player_id not in state.player_ids:
        raise GameLifecycleError("fight_phase_state next player is not in this game.")
    unit_owner_by_id = {
        rules_unit.unit_instance_id: rules_unit.owner_player_id
        for rules_unit in rules_unit_views_from_armies(armies=tuple(state.army_definitions))
    }
    historical_attached_owner_by_id = {
        record.attached_unit_instance_id: record.player_id
        for record in state.starting_attached_unit_records
    }
    known_unit_ids = set(unit_owner_by_id) | set(historical_attached_owner_by_id)
    if forced_context is not None:
        _validate_forced_fight_phase_state_consistency(
            state=state,
            event_records=event_records,
            unit_owner_by_id=unit_owner_by_id,
            known_unit_ids=known_unit_ids,
        )
    for unit_id in (
        *fight_order_state.engaged_at_fight_step_start_unit_ids,
        *fight_order_state.selected_to_fight_unit_ids,
        *fight_order_state.fights_first_registry.charged_unit_ids(),
    ):
        if unit_id not in known_unit_ids:
            raise GameLifecycleError("fight_phase_state unit is unknown.")
    for player_id in fight_order_state.passed_player_ids:
        if player_id not in state.player_ids:
            raise GameLifecycleError("fight_phase_state passed player is not in this game.")
    for selection in fight_order_state.activation_selections:
        owner = unit_owner_by_id.get(selection.unit_instance_id)
        if owner is None:
            owner = historical_attached_owner_by_id.get(selection.unit_instance_id)
        if owner is None:
            raise GameLifecycleError("fight_phase_state activation unit is unknown.")
        if owner != selection.player_id:
            raise GameLifecycleError("fight_phase_state activation player drift.")
    for eligible_pass in fight_order_state.eligible_passes:
        if eligible_pass.player_id not in state.player_ids:
            raise GameLifecycleError("fight_phase_state pass player is not in this game.")
        for unit_id in eligible_pass.eligible_unit_ids:
            owner = unit_owner_by_id.get(unit_id)
            if owner is None:
                raise GameLifecycleError("fight_phase_state pass unit is unknown.")
            if owner != eligible_pass.player_id:
                raise GameLifecycleError("fight_phase_state pass unit player drift.")


def _validate_forced_fight_phase_state_consistency(
    *,
    state: GameState,
    event_records: tuple[EventRecord, ...],
    unit_owner_by_id: dict[str, str],
    known_unit_ids: set[str],
) -> None:
    fight_state = state.fight_phase_state
    if fight_state is None or fight_state.forced_activation_context is None:
        raise GameLifecycleError("Forced fight_phase_state context is unavailable.")
    forced_context = fight_state.forced_activation_context
    fight_order_state = fight_state.fight_order_state
    if forced_context.selecting_player_id not in state.player_ids:
        raise GameLifecycleError("Forced fight_phase_state selecting player is not in this game.")
    if forced_context.selecting_player_id == state.active_player_id:
        raise GameLifecycleError("Forced fight_phase_state must be selected by the opponent.")
    if forced_context.source_unit_instance_id not in known_unit_ids:
        raise GameLifecycleError("Forced fight_phase_state source unit is unknown.")
    if forced_context.transport_unit_instance_id not in known_unit_ids:
        raise GameLifecycleError("Forced fight_phase_state Transport is unknown.")
    if fight_order_state.next_player_id != forced_context.selecting_player_id:
        raise GameLifecycleError("Forced fight_phase_state selecting player drift.")
    if fight_order_state.ordering_bands != (FightOrderingBandKind.REMAINING_COMBATS,):
        raise GameLifecycleError("Forced fight_phase_state ordering band drift.")
    if fight_order_state.passed_player_ids or fight_order_state.eligible_passes:
        raise GameLifecycleError("Forced fight_phase_state cannot contain Fight passes.")
    if set(fight_order_state.engaged_at_fight_step_start_unit_ids) != set(
        forced_context.eligible_unit_instance_ids
    ):
        raise GameLifecycleError("Forced fight_phase_state eligibility snapshot drift.")
    if not set(fight_order_state.selected_to_fight_unit_ids).issubset(
        forced_context.eligible_unit_instance_ids
    ):
        raise GameLifecycleError("Forced fight_phase_state selected unit drift.")
    for unit_id in forced_context.eligible_unit_instance_ids:
        if unit_owner_by_id.get(unit_id) != forced_context.selecting_player_id:
            raise GameLifecycleError("Forced fight_phase_state eligible unit player drift.")
    trigger_events = tuple(
        event for event in event_records if event.event_id == forced_context.trigger_event_id
    )
    if len(trigger_events) != 1 or trigger_events[0].event_type != "unit_disembarked":
        raise GameLifecycleError("Forced fight_phase_state trigger event is missing or invalid.")
    trigger_payload = trigger_events[0].payload
    if not isinstance(trigger_payload, dict):
        raise GameLifecycleError("Forced fight_phase_state trigger payload must be an object.")
    disembarked_state_payload = trigger_payload.get("disembarked_unit_state")
    if not isinstance(disembarked_state_payload, dict):
        raise GameLifecycleError("Forced fight_phase_state trigger lacks disembarked state.")
    if (
        trigger_payload.get("phase") != forced_context.source_phase.value
        or trigger_payload.get("unit_instance_id") != forced_context.source_unit_instance_id
        or trigger_payload.get("transport_unit_instance_id")
        != forced_context.transport_unit_instance_id
        or disembarked_state_payload.get("source_rule_id") != forced_context.source_rule_id
    ):
        raise GameLifecycleError("Forced fight_phase_state trigger context drift.")
    start_ids = disembarked_state_payload.get("start_engaged_enemy_unit_instance_ids")
    if not isinstance(start_ids, list) or not set(
        forced_context.eligible_unit_instance_ids
    ).issubset(start_ids):
        raise GameLifecycleError("Forced fight_phase_state engagement evidence drift.")
    start_events = tuple(
        event
        for event in event_records
        if event.event_type == "forced_fight_activation_queue_started"
        and isinstance(event.payload, dict)
        and event.payload.get("forced_activation_context") == forced_context.to_payload()
    )
    if len(start_events) != 1:
        raise GameLifecycleError("Forced fight_phase_state requires one exact queue-start event.")


def validate_movement_phase_state_consistency(
    *,
    state: GameState,
    event_records: tuple[EventRecord, ...],
    decision_records: tuple[DecisionRecord, ...],
) -> None:
    movement_state = state.movement_phase_state
    if movement_state is None:
        return
    if state.stage is not GameLifecycleStage.BATTLE:
        raise GameLifecycleError("movement_phase_state requires battle stage.")
    if state.current_battle_phase is not BattlePhase.MOVEMENT:
        raise GameLifecycleError("movement_phase_state requires MOVEMENT phase.")
    if state.active_player_id is None:
        raise GameLifecycleError("movement_phase_state requires active player.")
    if movement_state.active_player_id != state.active_player_id:
        raise GameLifecycleError("movement_phase_state active player drift.")
    if movement_state.battle_round != state.battle_round:
        raise GameLifecycleError("movement_phase_state battle round drift.")
    if state.battlefield_state is None:
        raise GameLifecycleError("movement_phase_state requires battlefield_state.")
    try:
        scenario = BattlefieldScenario(
            armies=tuple(state.army_definitions),
            battlefield_state=state.battlefield_state,
        )
        scenario.assert_all_mustered_models_placed_or_accounted(state.unavailable_model_ids())
    except PlacementError as exc:
        raise GameLifecycleError("Lifecycle state movement_phase_state is invalid.") from exc

    placed_army = scenario.battlefield_state.placed_army_for_player_or_none(state.active_player_id)
    if placed_army is None:
        active_player_unit_ids: set[str] = set()
    else:
        active_player_unit_ids = {
            placement.unit_instance_id for placement in placed_army.unit_placements
        }
    active_player_embarked_unit_ids = _lsq.embarked_unit_ids_for_player(
        state=state,
        player_id=state.active_player_id,
    )
    active_player_reserve_unit_ids = _lsq.unarrived_reserve_unit_ids_for_player(
        state=state,
        player_id=state.active_player_id,
    )
    fully_removed_active_player_unit_ids = _lsq.fully_removed_unit_ids_for_player(
        state=state,
        player_id=state.active_player_id,
    )
    allowed_physical_unit_ids = (
        active_player_unit_ids
        | fully_removed_active_player_unit_ids
        | active_player_embarked_unit_ids
        | active_player_reserve_unit_ids
    )
    for unit_id in (*movement_state.selected_unit_ids, *movement_state.moved_unit_ids):
        if not canonical_rules_unit_identity_matches_physical_units(
            state=state,
            player_id=state.active_player_id,
            unit_instance_id=unit_id,
            physical_unit_ids=allowed_physical_unit_ids,
        ):
            raise GameLifecycleError(
                "movement_phase_state selected unit is not active player's unit."
            )
    if movement_state.active_selection is None:
        return
    active_unit_id = movement_state.active_selection.unit_instance_id
    if active_unit_id not in movement_state.selected_unit_ids:
        raise GameLifecycleError("movement_phase_state active selection drift.")
    if not canonical_rules_unit_identity_matches_physical_units(
        state=state,
        player_id=state.active_player_id,
        unit_instance_id=active_unit_id,
        physical_unit_ids=allowed_physical_unit_ids,
    ):
        raise GameLifecycleError(
            "movement_phase_state active selection is not active player's unit."
        )
    resolve_pending_tactical_disembark_setup_boundary(
        state=state,
        event_records=event_records,
        decision_records=decision_records,
    )


def canonical_rules_unit_identity_matches_physical_units(
    *,
    state: GameState,
    player_id: str,
    unit_instance_id: str,
    physical_unit_ids: set[str],
) -> bool:
    known_canonical_ids = {
        view.unit_instance_id
        for view in rules_unit_views_from_armies(armies=tuple(state.army_definitions))
    } | {record.attached_unit_instance_id for record in state.starting_attached_unit_records}
    if unit_instance_id not in known_canonical_ids:
        return False
    views = current_rules_unit_views_for_canonical_identity(
        state=state,
        unit_instance_id=unit_instance_id,
    )
    return all(view.owner_player_id == player_id for view in views) and any(
        set(view.component_unit_instance_ids).intersection(physical_unit_ids) for view in views
    )


def validate_disembarked_unit_state_consistency(
    *,
    state: GameState,
    event_records: tuple[EventRecord, ...],
    decision_records: tuple[DecisionRecord, ...],
) -> None:
    if type(state) is not GameState:
        raise GameLifecycleError("Disembarked unit state validation requires GameState.")
    if not state.disembarked_unit_states:
        return
    if state.stage is not GameLifecycleStage.BATTLE:
        raise GameLifecycleError("disembarked_unit_states require battle stage.")
    if state.active_player_id is None:
        raise GameLifecycleError("disembarked_unit_states require an active battle turn.")
    for disembarked_state in state.disembarked_unit_states:
        if disembarked_state.battle_round != state.battle_round:
            raise GameLifecycleError("disembarked_unit_states battle round drift.")
        if disembarked_state.turn_player_id != state.active_player_id:
            raise GameLifecycleError("disembarked_unit_states turn player drift.")
        views = current_rules_unit_views_for_canonical_identity(
            state=state,
            unit_instance_id=disembarked_state.unit_instance_id,
        )
        if any(view.owner_player_id != disembarked_state.player_id for view in views):
            raise GameLifecycleError("disembarked_unit_states player drift.")
        transport_views = current_rules_unit_views_for_canonical_identity(
            state=state,
            unit_instance_id=disembarked_state.transport_unit_instance_id,
        )
        if any(view.owner_player_id != disembarked_state.player_id for view in transport_views):
            raise GameLifecycleError("disembarked_unit_states transport owner drift.")
        _validate_disembarked_unit_state_history(
            state=state,
            disembarked_state=disembarked_state,
            event_records=event_records,
            decision_records=decision_records,
        )


def _validate_disembarked_unit_state_history(
    *,
    state: GameState,
    disembarked_state: DisembarkedUnitState,
    event_records: tuple[EventRecord, ...],
    decision_records: tuple[DecisionRecord, ...],
) -> None:
    matching_events: list[tuple[EventRecord, dict[str, JsonValue], DisembarkedUnitState]] = []
    for event_record in event_records:
        if event_record.event_type != "unit_disembarked":
            continue
        candidate_event_payload = event_record.payload
        if not isinstance(candidate_event_payload, dict):
            raise GameLifecycleError("unit_disembarked event payload must be an object.")
        event_state = disembarked_unit_state_from_event_payload(candidate_event_payload)
        if (
            event_state.player_id == disembarked_state.player_id
            and event_state.battle_round == disembarked_state.battle_round
            and event_state.turn_player_id == disembarked_state.turn_player_id
            and event_state.unit_instance_id == disembarked_state.unit_instance_id
        ):
            matching_events.append((event_record, candidate_event_payload, event_state))
    if len(matching_events) != 1:
        raise GameLifecycleError(
            "Retained disembarked unit state requires exactly one authenticated event."
        )
    disembark_event_record, authenticated_event_payload, event_state = matching_events[0]
    if event_state != disembarked_state:
        raise GameLifecycleError("Retained disembarked unit state event drift.")
    if (
        authenticated_event_payload.get("game_id") != state.game_id
        or authenticated_event_payload.get("battle_round") != disembarked_state.battle_round
        or authenticated_event_payload.get("active_player_id") != disembarked_state.turn_player_id
        or authenticated_event_payload.get("unit_instance_id") != disembarked_state.unit_instance_id
        or authenticated_event_payload.get("transport_unit_instance_id")
        != disembarked_state.transport_unit_instance_id
        or authenticated_event_payload.get("disembark_mode")
        != disembarked_state.disembark_mode.value
    ):
        raise GameLifecycleError("Retained disembarked unit state event context drift.")
    request_id = authenticated_event_payload.get("request_id")
    result_id = authenticated_event_payload.get("result_id")
    matching_decisions = tuple(
        record
        for record in decision_records
        if record.request.request_id == request_id and record.result.result_id == result_id
    )
    if len(matching_decisions) != 1:
        raise GameLifecycleError(
            "Retained disembarked unit state requires exactly one authenticated decision."
        )
    decision_record = matching_decisions[0]
    if decision_record.request.decision_type != PLACEMENT_PROPOSAL_DECISION_TYPE:
        raise GameLifecycleError("Retained disembarked unit state decision type drift.")
    request_events = tuple(
        record
        for record in event_records
        if record.event_type == "decision_requested"
        and record.payload == decision_record.request.to_payload()
    )
    decision_events = tuple(
        record
        for record in event_records
        if record.event_type == "decision_recorded"
        and record.payload == decision_record.to_payload()
    )
    if len(request_events) != 1 or len(decision_events) != 1:
        raise GameLifecycleError("Retained disembarked unit state decision history drift.")
    if not (
        event_records.index(request_events[0])
        < event_records.index(decision_events[0])
        < event_records.index(disembark_event_record)
    ):
        raise GameLifecycleError("Retained disembarked unit state decision ordering drift.")
    try:
        proposal_request = MovementProposalRequest.from_decision_request_payload(
            decision_record.request.payload
        )
    except KeyError as exc:
        raise GameLifecycleError("Disembark placement request payload is malformed.") from exc
    result_payload = decision_record.result.payload
    if not isinstance(result_payload, dict):
        raise GameLifecycleError("Disembark placement result payload must be an object.")
    try:
        proposal = PlacementProposalPayload.from_payload(
            cast(PlacementProposalPayloadPayload, result_payload)
        )
    except (GeometryError, KeyError, PlacementError, TypeError) as exc:
        raise GameLifecycleError("Disembark placement result payload is malformed.") from exc
    proposal_validation = proposal.validation_result_for_request(proposal_request)
    if not proposal_validation.is_valid:
        raise GameLifecycleError("Retained disembarked unit state proposal history drift.")
    if (
        proposal_request.actor_id != disembarked_state.player_id
        or proposal_request.game_id != state.game_id
        or proposal_request.battle_round != disembarked_state.battle_round
        or proposal_request.unit_instance_id != disembarked_state.unit_instance_id
        or proposal.unit_instance_id != disembarked_state.unit_instance_id
        or proposal.transport_unit_instance_id != disembarked_state.transport_unit_instance_id
        or proposal.disembark_mode is not disembarked_state.disembark_mode
        or authenticated_event_payload.get("phase") != proposal_request.phase
        or authenticated_event_payload.get("transport_movement_status")
        != (
            None
            if proposal.transport_movement_status is None
            else proposal.transport_movement_status.value
        )
    ):
        raise GameLifecycleError("Retained disembarked unit state decision context drift.")
    event_overrides = authenticated_event_payload.get("restriction_overrides")
    proposal_overrides = [override.to_payload() for override in proposal.restriction_overrides]
    if event_overrides != proposal_overrides:
        raise GameLifecycleError("Retained disembarked unit state restriction override drift.")
    event_start_engagements = authenticated_event_payload.get(
        "start_engaged_enemy_unit_instance_ids"
    )
    proposal_start_engagements = proposal.start_engaged_enemy_unit_instance_ids or ()
    if disembarked_state.disembark_mode is DisembarkModeKind.SHOCK_DISEMBARK:
        if (
            event_start_engagements != list(proposal_start_engagements)
            or proposal_start_engagements != disembarked_state.start_engaged_enemy_unit_instance_ids
        ):
            raise GameLifecycleError("Retained disembarked unit state engagement snapshot drift.")
    elif (
        event_start_engagements not in (None, [])
        or proposal_start_engagements
        or disembarked_state.start_engaged_enemy_unit_instance_ids
    ):
        raise GameLifecycleError("Non-Shock disembark carries an engagement snapshot.")
    assault_permission_sources = tuple(
        override.source_rule_id
        for override in proposal.restriction_overrides
        if override.override_kind
        is TransportRestrictionOverrideKind.ALLOW_ASSAULT_DISEMBARK_AFTER_NORMAL_MOVE
    )
    shock_permission_sources = tuple(
        override.source_rule_id
        for override in proposal.restriction_overrides
        if override.override_kind
        is TransportRestrictionOverrideKind.ALLOW_SHOCK_DISEMBARK_AFTER_ADVANCE
    )
    if disembarked_state.disembark_mode is DisembarkModeKind.ASSAULT_DISEMBARK:
        if assault_permission_sources != (disembarked_state.permission_source_rule_id,):
            raise GameLifecycleError("Assault Disembark permission source history drift.")
    elif assault_permission_sources:
        raise GameLifecycleError("Non-Assault disembark carries Assault permission history.")
    if disembarked_state.disembark_mode is DisembarkModeKind.SHOCK_DISEMBARK:
        if shock_permission_sources != (disembarked_state.permission_source_rule_id,):
            raise GameLifecycleError("Shock Disembark permission source history drift.")
        _validate_shock_disembark_fight_history(
            state=state,
            disembarked_state=disembarked_state,
            disembark_event=disembark_event_record,
            event_records=event_records,
        )
    elif shock_permission_sources:
        raise GameLifecycleError("Non-Shock disembark carries Shock permission history.")


def _validate_shock_disembark_fight_history(
    *,
    state: GameState,
    disembarked_state: DisembarkedUnitState,
    disembark_event: EventRecord,
    event_records: tuple[EventRecord, ...],
) -> None:
    started_events = tuple(
        event
        for event in event_records
        if event.event_type == "forced_fight_activation_queue_started"
        and isinstance(event.payload, dict)
        and isinstance(event.payload.get("forced_activation_context"), dict)
        and cast(
            dict[str, JsonValue],
            event.payload["forced_activation_context"],
        ).get("trigger_event_id")
        == disembark_event.event_id
    )
    skipped_events = tuple(
        event
        for event in event_records
        if event.event_type == "forced_fight_activation_queue_skipped"
        and isinstance(event.payload, dict)
        and event.payload.get("trigger_event_id") == disembark_event.event_id
    )
    if len(started_events) + len(skipped_events) != 1:
        raise GameLifecycleError("Shock Disembark requires one forced-Fight queue disposition.")
    if skipped_events:
        if event_records.index(skipped_events[0]) <= event_records.index(disembark_event):
            raise GameLifecycleError("Shock Disembark skipped queue event ordering drift.")
        return
    started_event = started_events[0]
    if event_records.index(started_event) <= event_records.index(disembark_event):
        raise GameLifecycleError("Shock Disembark queue-start event ordering drift.")
    started_payload = started_event.payload
    if not isinstance(started_payload, dict):
        raise GameLifecycleError("Shock Disembark queue-start payload is malformed.")
    context_payload = started_payload.get("forced_activation_context")
    if not isinstance(context_payload, dict):
        raise GameLifecycleError("Shock Disembark queue-start context is malformed.")
    if (
        context_payload.get("source_rule_id") != disembarked_state.source_rule_id
        or context_payload.get("source_phase") != BattlePhase.MOVEMENT.value
        or context_payload.get("source_unit_instance_id") != disembarked_state.unit_instance_id
        or context_payload.get("transport_unit_instance_id")
        != disembarked_state.transport_unit_instance_id
    ):
        raise GameLifecycleError("Shock Disembark queue-start context drift.")
    completion_events = tuple(
        event
        for event in event_records
        if event.event_type == "forced_fight_activation_queue_completed"
        and isinstance(event.payload, dict)
        and event.payload.get("forced_activation_context") == context_payload
    )
    active_context = (
        None
        if state.fight_phase_state is None
        else state.fight_phase_state.forced_activation_context
    )
    if active_context is not None and active_context.to_payload() == context_payload:
        if completion_events:
            raise GameLifecycleError("Active Shock Disembark queue cannot already be completed.")
        return
    if len(completion_events) != 1:
        raise GameLifecycleError("Resolved Shock Disembark queue requires one completion event.")
    if event_records.index(completion_events[0]) <= event_records.index(started_event):
        raise GameLifecycleError("Shock Disembark queue completion ordering drift.")
