"""Authenticate Charge contact capabilities from accepted source and physical history."""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING, cast

from warhammer40k_core.engine.abilities import AbilityCatalogIndex
from warhammer40k_core.engine.aura_applications import persisting_effects_for_lineage
from warhammer40k_core.engine.charge_declaration import ChargeRollResult, ChargeRollResultPayload
from warhammer40k_core.engine.charge_endpoint_history import charge_component_at_physical_boundary
from warhammer40k_core.engine.charge_move_event_authority import (
    validate_charge_move_completed_event_authority,
)
from warhammer40k_core.engine.charge_path_contexts import charge_model_path_contexts
from warhammer40k_core.engine.generic_effect_history import (
    HistoricalEffectAuthority,
    historical_generic_effect_inventory,
)
from warhammer40k_core.engine.interrupted_charge import charge_turn_owner_at_event
from warhammer40k_core.engine.movement_proposals import MovementProposalRequest
from warhammer40k_core.engine.mutation_decision_authority import validate_mutation_decision_closure
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError
from warhammer40k_core.engine.rules_units import RulesUnitView, rules_unit_views_from_armies
from warhammer40k_core.engine.take_to_the_skies import flight_selection
from warhammer40k_core.engine.unit_split_views import split_effect_predecessor_ids

if TYPE_CHECKING:
    from warhammer40k_core.engine.decision_record import DecisionRecord
    from warhammer40k_core.engine.event_log import EventRecord, JsonValue
    from warhammer40k_core.engine.faction_content.bundle import RuntimeContentBundle
    from warhammer40k_core.engine.game_state import GameState
    from warhammer40k_core.engine.primary_mission_boundary_physical_authority import (
        PhysicalModelAuthority,
    )
    from warhammer40k_core.engine.unit_factory import UnitInstance
    from warhammer40k_core.geometry.movement_reachability import MovementReachabilityQuery


def validate_charge_contact_permissions(
    *,
    state: GameState,
    unit: UnitInstance,
    physical: tuple[PhysicalModelAuthority, ...],
    query: MovementReachabilityQuery,
    payload: dict[str, JsonValue],
    events: tuple[EventRecord, ...],
    decisions: tuple[DecisionRecord, ...],
    event_index: int,
    runtime_content_bundle: RuntimeContentBundle,
) -> None:
    if payload["movement_mode"] != "charge":
        raise GameLifecycleError("Deemed contact Charge movement mode drifted.")
    ruleset = state.runtime_ruleset_descriptor()
    if events[event_index].event_type == "charge_move_completed":
        authority = validate_charge_move_completed_event_authority(
            event_records=events,
            decision_records=decisions,
            event_index=event_index,
            payload=payload,
            ruleset_descriptor=ruleset,
        )
        roll = authority.charge_roll_result
    else:
        record = validate_mutation_decision_closure(
            event_records=events,
            decision_records=decisions,
            mutation_index=event_index,
            request_id=cast(str, payload["request_id"]),
            result_id=cast(str, payload["result_id"]),
        )
        proposal = MovementProposalRequest.from_decision_request_payload(record.request.payload)
        if not isinstance(proposal.context, dict) or not isinstance(
            proposal.context.get("charge_roll"), dict
        ):
            raise GameLifecycleError("Reactive Charge contact lacks accepted roll authority.")
        roll = ChargeRollResult.from_payload(
            cast(ChargeRollResultPayload, proposal.context["charge_roll"])
        )
        selection_record = validate_mutation_decision_closure(
            event_records=events,
            decision_records=decisions,
            mutation_index=event_index,
            request_id=proposal.source_decision_request_id,
            result_id=proposal.source_decision_result_id,
        )
        source = selection_record.result.payload
        if (
            not isinstance(source, dict)
            or proposal.context.get("source_context") != source
            or source.get("source_unit_instance_id") != proposal.unit_instance_id
            or source.get("action") != "charge"
            or proposal.unit_instance_id != payload.get("unit_instance_id")
            or proposal.game_id != payload.get("game_id")
            or proposal.battle_round != payload.get("battle_round")
            or proposal.phase != payload.get("phase")
            or proposal.actor_id != selection_record.result.actor_id
            or roll.request.game_id != proposal.game_id
            or roll.request.battle_round != proposal.battle_round
            or roll.request.unit_instance_id != proposal.unit_instance_id
            or roll.request.player_id != proposal.actor_id
            or roll.request.source_decision_request_id != proposal.source_decision_request_id
            or roll.request.source_decision_result_id != proposal.source_decision_result_id
        ):
            raise GameLifecycleError("Reactive Charge contact source decision drifted.")
        roll_events = tuple(
            (i, event)
            for i, event in enumerate(events[:event_index])
            if event.event_type == "catalog_setup_reactive_charge_roll_resolved"
            and isinstance(event.payload, dict)
            and event.payload.get("request_id") == proposal.source_decision_request_id
            and event.payload.get("result_id") == proposal.source_decision_result_id
        )
        if len(roll_events) != 1:
            raise GameLifecycleError("Reactive Charge contact roll event is ambiguous.")
        roll_index, roll_event = roll_events[0]
        roll_payload = roll_event.payload
        if not isinstance(roll_payload, dict) or any(
            roll_payload.get(key) != value
            for key, value in {
                "game_id": proposal.game_id,
                "battle_round": proposal.battle_round,
                "phase": proposal.phase,
                "active_player_id": payload["active_player_id"],
                "source_context": source,
                "roll_result": roll.to_payload(),
                "target_unit_instance_id": proposal.context["target_unit_instance_id"],
            }.items()
        ):
            raise GameLifecycleError("Reactive Charge contact roll event drifted.")
        validate_mutation_decision_closure(
            event_records=events,
            decision_records=decisions,
            mutation_index=roll_index,
            request_id=proposal.source_decision_request_id,
            result_id=proposal.source_decision_result_id,
        )
    selection = validate_mutation_decision_closure(
        event_records=events,
        decision_records=decisions,
        mutation_index=event_index,
        request_id=roll.request.source_decision_request_id,
        result_id=roll.request.source_decision_result_id,
    )
    if (
        flight_selection(selection.result.payload) != roll.request.take_to_the_skies
        or flight_selection(payload["fly_charge_policy"]) != roll.request.take_to_the_skies
    ):
        raise GameLifecycleError("Deemed contact Charge flight differs from its accepted choice.")
    present = {p.model_instance_id for p in physical}
    armies = tuple(
        replace(
            army,
            units=tuple(
                charge_component_at_physical_boundary(unit=u, physical=physical)
                for u in army.units
                if any(m.model_instance_id in present for m in u.own_models)
            ),
        )
        for army in state.army_definitions
    )
    units = {m.model_instance_id: u for army in armies for u in army.units for m in u.own_models}
    context = query.path_context
    unit = units[context.moving_model.model_id]
    owner = next(army.player_id for army in armies if unit in army.units)

    def source_view(uid: str, creation_index: int) -> RulesUnitView:
        from warhammer40k_core.engine.primary_mission_boundary_physical_authority import (
            physical_model_authority_before_event,
        )

        creation_physical = physical_model_authority_before_event(
            state=state,
            event_records=events,
            decision_records=decisions,
            event_index=creation_index,
        )
        creation_ids = {p.model_instance_id for p in creation_physical}
        creation_armies = tuple(
            replace(
                army,
                units=tuple(
                    charge_component_at_physical_boundary(unit=u, physical=creation_physical)
                    for u in army.units
                    if any(m.model_instance_id in creation_ids for m in u.own_models)
                ),
            )
            for army in state.army_definitions
        )
        matches = tuple(
            view
            for view in rules_unit_views_from_armies(armies=creation_armies)
            if view.unit_instance_id == uid or uid in view.component_unit_instance_ids
        )
        if len(matches) != 1:
            raise GameLifecycleError("Charge historical ability source identity is ambiguous.")
        return matches[0]

    turn_owner = charge_turn_owner_at_event(
        event_records=events,
        event_index=event_index,
        actor_id=cast(str, payload["active_player_id"]),
    )
    historical = HistoricalEffectAuthority(
        game_id=state.game_id,
        player_ids=tuple(state.player_ids),
        turn_order=tuple(state.turn_order),
        battle_phase_sequence=tuple(state.battle_phase_sequence),
        armies=armies,
        event_records=events,
        decision_records=decisions,
        boundary_event_index=event_index,
        player_id=owner,
        battle_round=cast(int, payload["battle_round"]),
        active_player_id=turn_owner,
        phase=BattlePhase(cast(str, payload["phase"])),
        rules_unit_at_event=source_view,
    )
    effects = historical_generic_effect_inventory(
        historical=historical,
        runtime_content_bundle=runtime_content_bundle,
        matches_payload=_movement_permission,
    )
    applicable = persisting_effects_for_lineage(
        list(effects),
        split_effect_predecessor_ids(
            armies=armies,
            unit_instance_id=cast(str, payload["unit_instance_id"]),
        ),
    )
    indexes = runtime_content_bundle.ability_indexes_by_player_id
    ability_index = indexes[owner] if owner in indexes else AbilityCatalogIndex.from_records(())
    budget = context.movement_distance_budget_inches
    if budget is None:
        raise GameLifecycleError("Charge contact budget is absent.")
    expected_path, expected_terrain = charge_model_path_contexts(
        unit=unit,
        moving_model=context.moving_model,
        witness=context.witness,
        ruleset=ruleset,
        owner_player_id=owner,
        current_model_instance_ids=tuple(
            sorted(
                m.model_instance_id
                for m in unit.own_models
                if any(
                    p.model_instance_id == m.model_instance_id and p.presence == "battlefield"
                    for p in physical
                )
            )
        ),
        take_to_the_skies=roll.request.take_to_the_skies,
        ability_index=ability_index,
        effects=applicable,
        battlefield_width_inches=context.battlefield_width_inches,
        battlefield_depth_inches=context.battlefield_depth_inches,
        friendly_models=context.friendly_models,
        enemy_models=context.enemy_models,
        units_by_model_id=units,
        retained_model_ids=frozenset(
            p.model_instance_id for p in physical if p.presence == "retained_destroyed"
        ),
        maximum_distance_inches=budget,
        terrain=query.terrain_context.terrain,
        terrain_features=query.terrain_context.terrain_features,
    )
    if expected_path != context or expected_terrain != query.terrain_context:
        raise GameLifecycleError("Deemed contact Charge movement capabilities drifted.")


def _movement_permission(payload: dict[str, JsonValue]) -> bool:
    effect = payload.get("effect")
    return isinstance(effect, dict) and effect.get("kind") == "movement_transit_permission"
