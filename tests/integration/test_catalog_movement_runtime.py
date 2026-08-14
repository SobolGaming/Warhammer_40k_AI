# pyright: reportPrivateUsage=false
from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from typing import cast

import pytest
from tests.support.catalog_package_fixtures import (
    advance_charge_package,
    advance_charge_unit,
    config_backed_flesh_hounds_armies,
    flesh_hounds_army,
    flesh_hounds_package,
    model_reroll_package,
    split_fall_back_package,
    split_model_reroll_package,
)
from tests.support.catalog_runtime_fixtures import (
    battle_state_with_armies,
    battle_state_with_army,
    bloodcrushers_battlefield_state,
    flesh_hounds_battlefield_state,
    player_ability_index,
    record_by_runtime_clause_suffix,
    set_current_model_wounds,
    single_model_unit_placement,
)
from tests.support.catalog_runtime_fixtures import (
    current_model_ids as fixture_current_model_ids,
)

from warhammer40k_core.core.dice import RerollComponentSelectionPolicy
from warhammer40k_core.core.ruleset_descriptor import RulesetDescriptor
from warhammer40k_core.core.weapon_profiles import (
    AbilityKind,
    RangeProfile,
    WeaponKeyword,
)
from warhammer40k_core.engine.abilities import (
    AbilityCatalogIndex,
    AbilityCatalogRecord,
)
from warhammer40k_core.engine.advance_eligibility_hooks import (
    AdvanceEligibilityContext,
    AdvanceEligibilityHookRegistry,
)
from warhammer40k_core.engine.attached_unit_formation import AttachedUnitFormation
from warhammer40k_core.engine.battlefield_state import (
    BattlefieldPlacementKind,
    BattlefieldRemovalKind,
    ModelPlacement,
    UnitPlacement,
)
from warhammer40k_core.engine.catalog_rule_consumption import (
    CATALOG_IR_ADVANCE_ROLL_REROLL_CONSUMER_ID,
    CATALOG_IR_CAN_ADVANCE_AND_CHARGE_CONSUMER_ID,
    CATALOG_IR_CAN_BE_PLACED_IN_RESERVES_CONSUMER_ID,
    CATALOG_IR_CAN_FALLBACK_AND_SHOOT_CONSUMER_ID,
    CATALOG_IR_CHARGE_ROLL_REROLL_CONSUMER_ID,
    CATALOG_IR_WEAPON_KEYWORD_GRANT_CONSUMER_ID,
    CatalogAdvanceEligibilityRuntime,
    CatalogFallBackEligibilityRuntime,
    _catalog_roll_reroll_permission,
    catalog_advance_roll_reroll_permission_for_unit,
    catalog_charge_roll_reroll_permission_for_unit,
    catalog_rule_ir_consumers_for_rule,
    catalog_rule_ir_hook_ids_for_rule,
    catalog_weapon_keyword_grants_for_unit,
    catalog_weapon_profile_modifier_bindings,
)
from warhammer40k_core.engine.catalog_turn_end_reserves import (
    CATALOG_TURN_END_RESERVES_USED_EVENT,
)
from warhammer40k_core.engine.charge_roll_permissions import charge_reroll_permission_for_unit
from warhammer40k_core.engine.decision_controller import (
    DecisionController,
    DecisionControllerPayload,
)
from warhammer40k_core.engine.decision_record import DecisionRecord
from warhammer40k_core.engine.decision_request import (
    PARAMETERIZED_DECISION_OPTION_ID,
)
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.destruction_provenance import (
    DestructionSourceKind,
    ModelDestructionAttribution,
)
from warhammer40k_core.engine.event_log import EventRecord, JsonValue, validate_json_value
from warhammer40k_core.engine.faction_content.bundle import RuntimeContentBundle
from warhammer40k_core.engine.faction_content.runtime import (
    build_runtime_content_bundle_for_armies,
)
from warhammer40k_core.engine.fall_back_hooks import (
    FallBackEligibilityContext,
    FallBackEligibilityHookRegistry,
)
from warhammer40k_core.engine.game_state import GameConfig, GameState
from warhammer40k_core.engine.healing import HealingEffect, resolve_healing_until_blocked
from warhammer40k_core.engine.healing_revival import (
    apply_healing_revival_placement_decision,
)
from warhammer40k_core.engine.lifecycle import GameLifecycle, GameLifecyclePayload
from warhammer40k_core.engine.movement_proposals import (
    MovementProposalRequest,
    PlacementProposalPayload,
)
from warhammer40k_core.engine.phase import (
    BattlePhase,
    GameLifecycleError,
)
from warhammer40k_core.engine.phases.movement import (
    MovementPhaseHandler,
    MovementPhaseState,
    _advance_reroll_permission_for_unit,
)
from warhammer40k_core.engine.primary_battlefield_departure import (
    primary_battlefield_departure_id,
)
from warhammer40k_core.engine.primary_destruction_evidence import (
    PrimaryUnattributedDestructionCause,
    rules_unit_objective_proximity_witness,
)
from warhammer40k_core.engine.primary_destruction_timeline_integrity import (
    _validated_reserve_deadline_transition_rows,
    validate_full_destruction_transition_timeline,
)
from warhammer40k_core.engine.primary_historical_event_integrity import (
    _rules_unit_components_by_id,
    _scoring_identities_by_id,
    _validate_destroyed_departure_provenance,
)
from warhammer40k_core.engine.primary_historical_events import (
    PRIMARY_RESERVE_ENTRY_MUTATION_EVENT,
    PRIMARY_RESERVE_ENTRY_SOURCE_BINDINGS_KEY,
    record_new_primary_battlefield_departure_events,
    record_new_primary_unit_destruction_events,
)
from warhammer40k_core.engine.primary_reserve_entry_lifecycle_integrity import (
    _closed_json_object,
    _json_object,
    _required_identifier,
    _source_terminal_bindings,
    _source_terminal_reserve_states,
    _unique_identifier_list,
    _validate_ability_source_terminal,
    _validate_active_ability_catalog_authority,
    _validate_active_stratagem_catalog_authority,
    _validate_current_reserve_status,
    _validate_during_battle_reserve_state_reverse_closure,
    _validate_generic_source_terminal,
    _validate_reserve_deadline_destruction,
    _validate_source_binding_reserve_states,
    _validated_reserve_arrival_occurrences,
    validate_primary_reserve_entry_lifecycle_integrity,
)
from warhammer40k_core.engine.primary_reserve_entry_provider import (
    GENERIC_RULE_IR_RESERVE_REMOVAL_PROVIDER_ID,
    GENERIC_STRATAGEM_RESERVE_REMOVAL_RESOLVED_EVENT,
    PrimaryReserveEntryAbilityAuthorityKind,
    PrimaryReserveEntryComponentMatchPolicy,
    PrimaryReserveEntryLifecycleOccurrence,
    PrimaryReserveEntryProvider,
    PrimaryReserveEntryProviderKind,
    primary_reserve_entry_provider_from_accepted_ability_decision,
    primary_reserve_entry_provider_kind_from_token,
    primary_reserve_entry_requirements,
    validate_accepted_primary_reserve_entry_provider,
    validate_primary_reserve_entry_provider_registration,
    validate_primary_reserve_entry_source_terminal_identity,
)
from warhammer40k_core.engine.primary_reserve_entry_provider_defaults import (
    default_primary_reserve_entry_ability_provider_definitions,
)
from warhammer40k_core.engine.primary_reserve_entry_source_integrity import (
    validate_primary_reserve_entry_source_requirements,
    validate_primary_reserve_entry_source_terminal_semantics,
)
from warhammer40k_core.engine.primary_reserve_entry_state_integrity import (
    PrimaryReserveEntryStateOccurrence,
    validate_latest_primary_reserve_entry_states,
)
from warhammer40k_core.engine.primary_turn_start_evidence import (
    build_primary_rules_unit_turn_start_snapshot,
)
from warhammer40k_core.engine.primary_unit_destruction_tracking import (
    record_primary_destroyed_model_departures,
    record_primary_unit_destructions_for_destroyed_models,
)
from warhammer40k_core.engine.reserves import (
    ReserveDestructionTimingPolicy,
    ReserveOrigin,
    ReserveStatus,
    apply_reserve_destruction_to_battlefield,
    resolve_unarrived_reserve_destruction,
)
from warhammer40k_core.engine.rules_units import rules_unit_view_by_id
from warhammer40k_core.engine.runtime_modifiers import (
    RuntimeModifierRegistry,
    WeaponProfileModifierContext,
)
from warhammer40k_core.engine.timing_windows import TimingTriggerKind
from warhammer40k_core.engine.turn_end_hooks import (
    SELECT_FACTION_RULE_TURN_END_OPTION_DECISION_TYPE,
    TurnEndRequestContext,
    TurnEndResultContext,
)
from warhammer40k_core.geometry.pose import Pose
from warhammer40k_core.rules.rule_ir import (
    RuleClause,
    RuleIR,
    RuleIRPayload,
    RuleTargetKind,
)


def _record_surviving_rules_unit_model_destruction(
    *,
    state: GameState,
    decisions: DecisionController,
    destroyed_unit_instance_id: str,
    destroyed_model_instance_id: str,
    destroying_player_id: str,
    source_unit_instance_id: str,
    source_model_instance_id: str,
) -> None:
    """Apply one real casualty and its public Step 3 attribution/evidence chain."""
    phase = state.current_battle_phase
    active_player_id = state.active_player_id
    assert phase is not None
    assert active_player_id is not None
    source_witness = rules_unit_objective_proximity_witness(
        state=state,
        rules_unit_instance_id=source_unit_instance_id,
    )
    destroyed_witness = rules_unit_objective_proximity_witness(
        state=state,
        rules_unit_instance_id=destroyed_unit_instance_id,
    )
    attribution = ModelDestructionAttribution.for_non_attack(
        destroying_player_id=destroying_player_id,
        source_kind=DestructionSourceKind.ABILITY,
        source_rules_unit_instance_id=source_unit_instance_id,
        source_model_instance_id=source_model_instance_id,
    )
    set_current_model_wounds(
        state,
        model_instance_id=destroyed_model_instance_id,
        wounds_remaining=0,
    )
    assert state.battlefield_state is not None
    state.battlefield_state = state.battlefield_state.with_removed_models(
        (destroyed_model_instance_id,)
    )
    destroyed_event = decisions.event_log.append(
        "model_destroyed",
        {
            "game_id": state.game_id,
            "battle_round": state.battle_round,
            "active_player_id": active_player_id,
            "phase": phase.value,
            **attribution.to_payload(),
            "source_rules_unit_objective_proximity_witness": source_witness.to_payload(),
            "destroyed_rules_unit_objective_proximity_witness": destroyed_witness.to_payload(),
            "target_unit_instance_id": destroyed_unit_instance_id,
            "model_instance_id": destroyed_model_instance_id,
        },
    )
    departure_ids_before = tuple(
        departure.departure_id for departure in state.primary_battlefield_departure_states
    )
    source_id = f"core-rules:primary-unit-destruction-tracking:{destroyed_event.event_id}"
    departures = record_primary_destroyed_model_departures(
        state=state,
        destroyed_model_instance_ids=(destroyed_model_instance_id,),
        source_id=source_id,
        occurrence_id=destroyed_event.event_id,
    )
    assert len(departures) == 1
    assert (
        record_primary_unit_destructions_for_destroyed_models(
            state=state,
            destroyed_model_instance_ids=(destroyed_model_instance_id,),
            destruction_attribution=attribution,
            source_model_destroyed_event_id=destroyed_event.event_id,
            source_rules_unit_objective_proximity_witness=source_witness,
            destroyed_rules_unit_objective_proximity_witness=destroyed_witness,
            unattributed_cause=None,
            source_mutation_id=None,
            left_battlefield=False,
            source_id=source_id,
        )
        == ()
    )
    record_new_primary_battlefield_departure_events(
        state=state,
        event_log=decisions.event_log,
        departure_ids_before=departure_ids_before,
    )
    assert state.battlefield_state is not None
    assert destroyed_model_instance_id not in state.battlefield_state.placed_model_ids()
    assert rules_unit_view_by_id(
        state=state,
        unit_instance_id=destroyed_unit_instance_id,
    ).alive_models()


def test_phase17n_hunters_from_the_warp_repeated_entries_preserve_real_casualties() -> None:
    package = flesh_hounds_package()
    catalog, muster_requests, armies = config_backed_flesh_hounds_armies(
        package=package,
        enemy_unit_selection_id="enemy-flesh-hounds-1",
    )
    army, enemy_army = armies
    unit = army.units[0]
    enemy_unit = enemy_army.units[0]
    state = battle_state_with_armies(
        armies=armies,
        battlefield=flesh_hounds_battlefield_state(
            army=army,
            unit=unit,
            enemy_army=enemy_army,
            enemy_unit=enemy_unit,
            enemy_x=30.0,
        ),
        active_player_id=enemy_army.player_id,
        phase=BattlePhase.FIGHT,
    )
    config = GameConfig(
        game_id=state.game_id,
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(),
        army_catalog=catalog,
        army_muster_requests=muster_requests,
        player_ids=state.player_ids,
        turn_order=state.turn_order,
        fixed_secondary_mission_ids=("assassination", "bring_it_down"),
        mission_setup=state.mission_setup,
        allow_legacy_non_strict_rosters=True,
        model_geometries=package.model_geometries,
    )
    runtime_bundle = build_runtime_content_bundle_for_armies(config=config, armies=armies)

    def restore(payload: GameLifecyclePayload) -> GameLifecycle:
        return GameLifecycle.from_payload(payload, runtime_content_bundle=runtime_bundle)

    player_index = runtime_bundle.ability_indexes_by_player_id[army.player_id]
    records_by_name = {record.definition.name: record for record in player_index.all_records()}
    hunters_record = records_by_name["Hunters from the Warp"]
    replay_payload = hunters_record.definition.replay_payload
    assert isinstance(replay_payload, dict)
    hunters_rule_ir = RuleIR.from_payload(cast(RuleIRPayload, replay_payload["rule_ir"]))
    registry = runtime_bundle.turn_end_hook_registry
    engaged_state = battle_state_with_armies(
        armies=(army, enemy_army),
        battlefield=flesh_hounds_battlefield_state(
            army=army,
            unit=unit,
            enemy_army=enemy_army,
            enemy_unit=enemy_unit,
            enemy_x=12.0,
        ),
        active_player_id=enemy_army.player_id,
        phase=BattlePhase.FIGHT,
    )

    assert hunters_record.definition.timing.trigger_kind is TimingTriggerKind.END_TURN
    assert catalog_rule_ir_consumers_for_rule(hunters_rule_ir) == (
        CATALOG_IR_CAN_BE_PLACED_IN_RESERVES_CONSUMER_ID,
    )
    assert set(catalog_rule_ir_hook_ids_for_rule(hunters_rule_ir)) == {
        CATALOG_IR_CAN_BE_PLACED_IN_RESERVES_CONSUMER_ID,
    }
    assert (
        registry.next_request_for(
            TurnEndRequestContext(
                state=engaged_state,
                decisions=DecisionController(),
                completed_phase=BattlePhase.FIGHT,
            )
        )
        is None
    )

    decisions = DecisionController()
    first_destroyed_model_id = unit.own_models[0].model_instance_id
    second_destroyed_model_id = unit.own_models[1].model_instance_id
    _record_surviving_rules_unit_model_destruction(
        state=state,
        decisions=decisions,
        destroyed_unit_instance_id=unit.unit_instance_id,
        destroyed_model_instance_id=first_destroyed_model_id,
        destroying_player_id=enemy_army.player_id,
        source_unit_instance_id=enemy_unit.unit_instance_id,
        source_model_instance_id=enemy_unit.own_models[0].model_instance_id,
    )
    alive_after_first_casualty = rules_unit_view_by_id(
        state=state,
        unit_instance_id=unit.unit_instance_id,
    ).alive_models()
    assert first_destroyed_model_id not in {
        model.model_instance_id for model in alive_after_first_casualty
    }
    assert len(alive_after_first_casualty) == len(unit.own_models) - 1
    state_before_missing_provider_attempt = deepcopy(state.to_payload())
    with pytest.raises(
        GameLifecycleError,
        match="Repositioned units require a typed reserve provider",
    ):
        state.reposition_unit_to_strategic_reserves(
            decisions=decisions,
            player_id=army.player_id,
            unit_instance_id=unit.unit_instance_id,
            provider=cast(PrimaryReserveEntryProvider, None),
            reserve_origin=ReserveOrigin.DURING_BATTLE_ABILITY,
            source_rule_ids=(hunters_record.definition.source_id,),
        )
    assert state.to_payload() == state_before_missing_provider_attempt

    unauthenticated_provider = PrimaryReserveEntryProvider(
        provider_kind=PrimaryReserveEntryProviderKind.TURN_END_ABILITY,
        provider_id=CATALOG_IR_CAN_BE_PLACED_IN_RESERVES_CONSUMER_ID,
        player_id=army.player_id,
        source_rule_id=hunters_record.definition.source_id,
        target_rules_unit_instance_id=unit.unit_instance_id,
        decision_record_id="decision-record-000001",
        decision_request_id="forged-hunters-request",
        decision_result_id="forged-hunters-result",
        stratagem_use_id=None,
        source_terminal_event_type=CATALOG_TURN_END_RESERVES_USED_EVENT,
    )
    state_before_unauthenticated_attempt = deepcopy(state.to_payload())
    decisions_before_unauthenticated_attempt = deepcopy(decisions.to_payload())
    with pytest.raises(
        GameLifecycleError,
        match="Reserve-entry provider accepted decision is missing",
    ):
        state.reposition_unit_to_strategic_reserves(
            decisions=decisions,
            player_id=army.player_id,
            unit_instance_id=unit.unit_instance_id,
            provider=unauthenticated_provider,
            reserve_origin=ReserveOrigin.DURING_BATTLE_ABILITY,
            source_rule_ids=(hunters_record.definition.source_id,),
        )
    assert state.to_payload() == state_before_unauthenticated_attempt
    assert decisions.to_payload() == decisions_before_unauthenticated_attempt

    request = registry.next_request_for(
        TurnEndRequestContext(
            state=state,
            decisions=decisions,
            completed_phase=BattlePhase.FIGHT,
        )
    )
    assert request is not None
    decisions.request_decision(request)
    use_option = next(option for option in request.options if option.option_id.endswith(":use"))
    result = DecisionResult.for_request(
        result_id="result-flesh-hounds-hunters-use",
        request=request,
        selected_option_id=use_option.option_id,
    )
    decisions.submit_result(result)

    handled = registry.apply_result(
        TurnEndResultContext(
            state=state,
            decisions=decisions,
            request=request,
            result=result,
        )
    )

    reserve_state = state.reserve_state_for_unit(unit.unit_instance_id)
    assert request.decision_type == SELECT_FACTION_RULE_TURN_END_OPTION_DECISION_TYPE
    assert request.actor_id == army.player_id
    assert handled is True
    assert reserve_state is not None
    assert reserve_state.source_rule_ids == (hunters_record.definition.source_id,)
    assert state.battlefield_state is not None
    assert all(
        unit_placement.unit_instance_id != unit.unit_instance_id
        for placed_army in state.battlefield_state.placed_armies
        for unit_placement in placed_army.unit_placements
    )
    used_events = tuple(
        record
        for record in decisions.event_log.records
        if record.event_type == CATALOG_TURN_END_RESERVES_USED_EVENT
    )
    assert len(used_events) == 1
    lifecycle = GameLifecycle(
        state=state,
        decision_controller=decisions,
        _config=config,
        _runtime_content_bundle=runtime_bundle,
    )
    assert restore(lifecycle.to_payload()).to_payload() == lifecycle.to_payload()

    state.active_player_id = army.player_id
    state.battle_round = 2
    state.battle_phase_index = tuple(state.battle_phase_sequence).index(BattlePhase.MOVEMENT)
    state.movement_phase_state = MovementPhaseState(
        battle_round=2,
        active_player_id=army.player_id,
    )
    movement_handler = MovementPhaseHandler(
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh()
    )
    arrival_selection_status = movement_handler.begin_phase(state=state, decisions=decisions)
    assert arrival_selection_status is not None
    assert arrival_selection_status.decision_request is not None
    arrival_selection_request = arrival_selection_status.decision_request
    arrival_selection_result = DecisionResult.for_request(
        result_id="result-flesh-hounds-arrival-select",
        request=arrival_selection_request,
        selected_option_id=unit.unit_instance_id,
    )
    decisions.submit_result(arrival_selection_result)
    arrival_placement_status = movement_handler.apply_decision(
        state=state,
        decisions=decisions,
        result=arrival_selection_result,
    )
    assert arrival_placement_status is not None
    assert arrival_placement_status.decision_request is not None
    arrival_placement_request = arrival_placement_status.decision_request
    arrival_proposal_request = MovementProposalRequest.from_decision_request_payload(
        arrival_placement_request.payload
    )
    arrival_models = rules_unit_view_by_id(
        state=state,
        unit_instance_id=unit.unit_instance_id,
    ).alive_models()
    assert tuple(model.model_instance_id for model in arrival_models) == tuple(
        model.model_instance_id for model in alive_after_first_casualty
    )
    attempted_arrival = UnitPlacement(
        army_id=army.army_id,
        player_id=army.player_id,
        unit_instance_id=unit.unit_instance_id,
        model_placements=tuple(
            ModelPlacement(
                army_id=army.army_id,
                player_id=army.player_id,
                unit_instance_id=unit.unit_instance_id,
                model_instance_id=model.model_instance_id,
                pose=Pose.at(8.0 + (index * 2.5), 2.0),
            )
            for index, model in enumerate(arrival_models)
        ),
    )
    arrival_placement_result = DecisionResult(
        result_id="result-flesh-hounds-arrival-place",
        request_id=arrival_placement_request.request_id,
        decision_type=arrival_placement_request.decision_type,
        actor_id=arrival_placement_request.actor_id,
        selected_option_id=PARAMETERIZED_DECISION_OPTION_ID,
        payload=validate_json_value(
            PlacementProposalPayload(
                proposal_request_id=arrival_proposal_request.request_id,
                proposal_kind=arrival_proposal_request.proposal_kind,
                unit_instance_id=unit.unit_instance_id,
                placement_kind=BattlefieldPlacementKind.STRATEGIC_RESERVES,
                attempted_placement=attempted_arrival,
            ).to_payload()
        ),
    )
    assert (
        movement_handler.invalid_proposal_submission_status(
            state=state,
            request=arrival_placement_request,
            result=arrival_placement_result,
            decisions=decisions,
        )
        is None
    )
    decisions.submit_result(arrival_placement_result)
    arrival_resolution_status = movement_handler.apply_decision(
        state=state,
        decisions=decisions,
        result=arrival_placement_result,
    )
    assert arrival_resolution_status is None
    assert any(
        event.event_type == "reinforcement_unit_arrived"
        and cast(dict[str, JsonValue], event.payload).get("unit_instance_id")
        == unit.unit_instance_id
        for event in decisions.event_log.records
    )
    state.active_player_id = enemy_army.player_id
    state.battle_round = 2
    state.battle_phase_index = tuple(state.battle_phase_sequence).index(BattlePhase.FIGHT)
    state.movement_phase_state = None
    _record_surviving_rules_unit_model_destruction(
        state=state,
        decisions=decisions,
        destroyed_unit_instance_id=unit.unit_instance_id,
        destroyed_model_instance_id=second_destroyed_model_id,
        destroying_player_id=enemy_army.player_id,
        source_unit_instance_id=enemy_unit.unit_instance_id,
        source_model_instance_id=enemy_unit.own_models[0].model_instance_id,
    )
    alive_after_second_casualty = rules_unit_view_by_id(
        state=state,
        unit_instance_id=unit.unit_instance_id,
    ).alive_models()
    assert {first_destroyed_model_id, second_destroyed_model_id}.isdisjoint(
        model.model_instance_id for model in alive_after_second_casualty
    )
    assert len(alive_after_second_casualty) == len(unit.own_models) - 2
    second_request = registry.next_request_for(
        TurnEndRequestContext(
            state=state,
            decisions=decisions,
            completed_phase=BattlePhase.FIGHT,
        )
    )
    assert second_request is not None
    decisions.request_decision(second_request)
    second_use_option = next(
        option for option in second_request.options if option.option_id.endswith(":use")
    )
    second_result = DecisionResult.for_request(
        result_id="result-flesh-hounds-hunters-use-round-2",
        request=second_request,
        selected_option_id=second_use_option.option_id,
    )
    decisions.submit_result(second_result)
    assert registry.apply_result(
        TurnEndResultContext(
            state=state,
            decisions=decisions,
            request=second_request,
            result=second_result,
        )
    )
    repeated_reserve_state = state.reserve_state_for_unit(unit.unit_instance_id)
    assert repeated_reserve_state is not None
    assert repeated_reserve_state.entered_reserves_battle_round == 2
    assert len(state.primary_battlefield_departure_states) == 4
    assert (
        len({departure.departure_id for departure in state.primary_battlefield_departure_states})
        == 4
    )
    assert {
        departure.removed_model_instance_ids
        for departure in state.primary_battlefield_departure_states
        if departure.removal_kind is BattlefieldRemovalKind.DESTROYED
    } == {(first_destroyed_model_id,), (second_destroyed_model_id,)}
    destroyed_model_event_ids: list[str] = []
    for destroyed_event_record in decisions.event_log.records:
        if destroyed_event_record.event_type != "model_destroyed":
            continue
        destroyed_model_event_id = cast(dict[str, JsonValue], destroyed_event_record.payload).get(
            "model_instance_id"
        )
        assert isinstance(destroyed_model_event_id, str)
        destroyed_model_event_ids.append(destroyed_model_event_id)
    assert set(destroyed_model_event_ids) == {
        first_destroyed_model_id,
        second_destroyed_model_id,
    }
    repeated_lifecycle = GameLifecycle(
        state=state,
        decision_controller=decisions,
        _config=config,
        _runtime_content_bundle=runtime_bundle,
    )
    restored_repeated_lifecycle = restore(repeated_lifecycle.to_payload())
    assert restored_repeated_lifecycle.to_payload() == repeated_lifecycle.to_payload()
    restored_state = restored_repeated_lifecycle.state
    assert restored_state is not None
    assert {
        departure.removed_model_instance_ids
        for departure in restored_state.primary_battlefield_departure_states
        if departure.removal_kind is BattlefieldRemovalKind.DESTROYED
    } == {(first_destroyed_model_id,), (second_destroyed_model_id,)}

    baseline_payload = repeated_lifecycle.to_payload()
    _assert_hunters_lifecycle_integrity_boundaries(
        baseline_payload=baseline_payload,
        runtime_bundle=runtime_bundle,
        enemy_player_id=enemy_army.player_id,
    )

    terminal_drift_payload: GameLifecyclePayload = deepcopy(baseline_payload)
    terminal_drift_events = terminal_drift_payload["decisions"]["event_log"]
    terminal_drift_sources = tuple(
        event
        for event in terminal_drift_events
        if event["event_type"] == CATALOG_TURN_END_RESERVES_USED_EVENT
    )
    assert len(terminal_drift_sources) == 2
    terminal_drift_source_payload = cast(
        dict[str, JsonValue],
        terminal_drift_sources[0]["payload"],
    )
    terminal_drift_source_payload["catalog_record_id"] = "forged-catalog-record"
    with pytest.raises(
        GameLifecycleError,
        match="Ability reserve source terminal result identity drift",
    ):
        restore(terminal_drift_payload)

    catalog_authority_drift_payload: GameLifecyclePayload = deepcopy(baseline_payload)
    catalog_authority_record = catalog_authority_drift_payload["decisions"]["records"][0]
    forged_catalog_record_id = "forged-catalog-record"
    cast(dict[str, JsonValue], catalog_authority_record["request"]["payload"])[
        "catalog_record_id"
    ] = forged_catalog_record_id
    selected_option_id = catalog_authority_record["result"]["selected_option_id"]
    selected_option = next(
        option
        for option in catalog_authority_record["request"]["options"]
        if option["option_id"] == selected_option_id
    )
    cast(dict[str, JsonValue], selected_option["payload"])["catalog_record_id"] = (
        forged_catalog_record_id
    )
    cast(dict[str, JsonValue], catalog_authority_record["result"]["payload"])[
        "catalog_record_id"
    ] = forged_catalog_record_id
    catalog_authority_request_id = catalog_authority_record["request"]["request_id"]
    catalog_authority_record_id = catalog_authority_record["record_id"]
    source_rewritten = False
    for event in catalog_authority_drift_payload["decisions"]["event_log"]:
        event_payload = cast(dict[str, JsonValue], event["payload"])
        if (
            event["event_type"] == "decision_requested"
            and event_payload.get("request_id") == catalog_authority_request_id
        ):
            event["payload"] = validate_json_value(deepcopy(catalog_authority_record["request"]))
        if (
            event["event_type"] == "decision_recorded"
            and event_payload.get("record_id") == catalog_authority_record_id
        ):
            event["payload"] = validate_json_value(deepcopy(catalog_authority_record))
        if event["event_type"] == CATALOG_TURN_END_RESERVES_USED_EVENT and not source_rewritten:
            event_payload["catalog_record_id"] = forged_catalog_record_id
            source_rewritten = True
    assert source_rewritten
    with pytest.raises(
        GameLifecycleError,
        match="Catalog reserve-entry active Ability authority drift",
    ):
        restore(catalog_authority_drift_payload)

    missing_request_payload: GameLifecyclePayload = deepcopy(baseline_payload)
    requested_events = tuple(
        event
        for event in missing_request_payload["decisions"]["event_log"]
        if event["event_type"] == "decision_requested"
        and cast(dict[str, JsonValue], event["payload"]).get("decision_type")
        == SELECT_FACTION_RULE_TURN_END_OPTION_DECISION_TYPE
    )
    assert len(requested_events) == 2
    requested_events[0]["event_type"] = "forged_missing_decision_requested"
    with pytest.raises(
        GameLifecycleError,
        match="exact requested and recorded decision events",
    ):
        restore(missing_request_payload)

    missing_record_payload: GameLifecyclePayload = deepcopy(baseline_payload)
    decision_records = missing_record_payload["decisions"]["records"]
    assert len(decision_records) == 4
    decision_records.pop()
    with pytest.raises(
        GameLifecycleError,
        match="Reserve-entry provider DecisionRecord identity drift",
    ):
        restore(missing_record_payload)

    actor_drift_payload: GameLifecyclePayload = deepcopy(baseline_payload)
    actor_drift_record = actor_drift_payload["decisions"]["records"][0]
    actor_drift_record["request"]["actor_id"] = enemy_army.player_id
    actor_drift_record["result"]["actor_id"] = enemy_army.player_id
    actor_drift_request_id = actor_drift_record["request"]["request_id"]
    actor_drift_record_id = actor_drift_record["record_id"]
    for event in actor_drift_payload["decisions"]["event_log"]:
        event_payload = cast(dict[str, JsonValue], event["payload"])
        if (
            event["event_type"] == "decision_requested"
            and event_payload.get("request_id") == actor_drift_request_id
        ):
            event["payload"] = validate_json_value(deepcopy(actor_drift_record["request"]))
        if (
            event["event_type"] == "decision_recorded"
            and event_payload.get("record_id") == actor_drift_record_id
        ):
            event["payload"] = validate_json_value(deepcopy(actor_drift_record))
    with pytest.raises(
        GameLifecycleError,
        match="Reserve-entry provider DecisionRecord identity drift",
    ):
        restore(actor_drift_payload)

    selected_target_drift_payload: GameLifecyclePayload = deepcopy(baseline_payload)
    selected_target_record = selected_target_drift_payload["decisions"]["records"][0]
    selected_option_id = selected_target_record["result"]["selected_option_id"]
    selected_options = selected_target_record["request"]["options"]
    selected_option = next(
        option for option in selected_options if option["option_id"] == selected_option_id
    )
    selected_option_payload = cast(dict[str, JsonValue], selected_option["payload"])
    selected_result_payload = cast(
        dict[str, JsonValue],
        selected_target_record["result"]["payload"],
    )
    selected_option_payload["target_unit_instance_id"] = enemy_unit.unit_instance_id
    selected_result_payload["target_unit_instance_id"] = enemy_unit.unit_instance_id
    selected_target_request_id = selected_target_record["request"]["request_id"]
    selected_target_record_id = selected_target_record["record_id"]
    for event in selected_target_drift_payload["decisions"]["event_log"]:
        event_payload = cast(dict[str, JsonValue], event["payload"])
        if (
            event["event_type"] == "decision_requested"
            and event_payload.get("request_id") == selected_target_request_id
        ):
            event["payload"] = validate_json_value(deepcopy(selected_target_record["request"]))
        if (
            event["event_type"] == "decision_recorded"
            and event_payload.get("record_id") == selected_target_record_id
        ):
            event["payload"] = validate_json_value(deepcopy(selected_target_record))
    with pytest.raises(
        GameLifecycleError,
        match="Ability reserve provider decision context drift",
    ):
        restore(selected_target_drift_payload)

    reordered_payload: GameLifecyclePayload = deepcopy(baseline_payload)
    reordered_events = reordered_payload["decisions"]["event_log"]
    first_source_index = next(
        index
        for index, event in enumerate(reordered_events)
        if event["event_type"] == CATALOG_TURN_END_RESERVES_USED_EVENT
    )
    first_provider_terminal_index = next(
        index
        for index, event in enumerate(reordered_events)
        if event["event_type"] == "primary_reserve_entry_provider_resolved"
    )
    assert first_source_index < first_provider_terminal_index
    source_event = reordered_events[first_source_index]
    provider_terminal_event = reordered_events[first_provider_terminal_index]
    source_event["event_type"], provider_terminal_event["event_type"] = (
        provider_terminal_event["event_type"],
        source_event["event_type"],
    )
    source_event["payload"], provider_terminal_event["payload"] = (
        provider_terminal_event["payload"],
        source_event["payload"],
    )
    with pytest.raises(
        GameLifecycleError,
        match=r"provider terminal event ordering drift|source terminal is not unique",
    ):
        restore(reordered_payload)

    cloned_departure_payload: GameLifecyclePayload = deepcopy(baseline_payload)
    cloned_state_payload = cast(dict[str, JsonValue], cloned_departure_payload["state"])
    departures = cast(
        list[JsonValue],
        cloned_state_payload["primary_battlefield_departure_states"],
    )
    first_departure = cast(dict[str, JsonValue], departures[0])
    cloned_departure = deepcopy(first_departure)
    cloned_occurrence_id = "forged-hunters-occurrence"
    cloned_source_id = "forged-hunters-source"
    cloned_departure["occurrence_id"] = cloned_occurrence_id
    cloned_departure["source_id"] = cloned_source_id
    cloned_departure["departure_id"] = primary_battlefield_departure_id(
        game_id=cast(str, cloned_departure["game_id"]),
        rules_unit_instance_id=cast(str, cloned_departure["rules_unit_instance_id"]),
        affected_component_unit_instance_ids=tuple(
            cast(list[str], cloned_departure["affected_component_unit_instance_ids"])
        ),
        departed_component_unit_instance_ids=tuple(
            cast(list[str], cloned_departure["departed_component_unit_instance_ids"])
        ),
        removed_model_instance_ids=tuple(
            cast(list[str], cloned_departure["removed_model_instance_ids"])
        ),
        battle_round=cast(int, cloned_departure["battle_round"]),
        active_player_id=cast(str, cloned_departure["active_player_id"]),
        phase=cast(str, cloned_departure["phase"]),
        removal_kind=BattlefieldRemovalKind(cast(str, cloned_departure["removal_kind"])),
        occurrence_id=cloned_occurrence_id,
        source_id=cloned_source_id,
    )
    departures.append(cloned_departure)
    cloned_events = cloned_departure_payload["decisions"]["event_log"]
    first_derived_event = next(
        event
        for event in cloned_events
        if event["event_type"] == "primary_battlefield_departure_recorded"
        and cast(dict[str, JsonValue], event["payload"])["primary_battlefield_departure_state"]
        == first_departure
    )
    cloned_derived_event = deepcopy(first_derived_event)
    cloned_derived_event["event_id"] = f"event-{len(cloned_events) + 1:06d}"
    cast(dict[str, JsonValue], cloned_derived_event["payload"])[
        "primary_battlefield_departure_state"
    ] = cloned_departure
    cloned_events.append(cloned_derived_event)
    with pytest.raises(
        GameLifecycleError,
        match=r"authoritative .* mutation event",
    ):
        restore(cloned_departure_payload)


def _assert_hunters_lifecycle_integrity_boundaries(
    *,
    baseline_payload: GameLifecyclePayload,
    runtime_bundle: RuntimeContentBundle,
    enemy_player_id: str,
) -> None:
    state = GameState.from_payload(deepcopy(baseline_payload["state"]))
    decisions = DecisionController.from_payload(deepcopy(baseline_payload["decisions"]))
    event_records = decisions.event_log.records
    decision_records = decisions.records
    ability_indexes = runtime_bundle.ability_indexes_by_player_id
    stratagem_indexes = runtime_bundle.stratagem_indexes_by_player_id

    with pytest.raises(GameLifecycleError, match="requires GameState"):
        validate_primary_reserve_entry_lifecycle_integrity(
            state=cast(GameState, None),
            event_records=event_records,
            decision_records=decision_records,
            stratagem_indexes_by_player_id=stratagem_indexes,
            ability_indexes_by_player_id=ability_indexes,
        )
    with pytest.raises(GameLifecycleError, match="requires EventRecords"):
        validate_primary_reserve_entry_lifecycle_integrity(
            state=state,
            event_records=cast(tuple[EventRecord, ...], list(event_records)),
            decision_records=decision_records,
            stratagem_indexes_by_player_id=stratagem_indexes,
            ability_indexes_by_player_id=ability_indexes,
        )
    with pytest.raises(GameLifecycleError, match="requires DecisionRecords"):
        validate_primary_reserve_entry_lifecycle_integrity(
            state=state,
            event_records=event_records,
            decision_records=cast(tuple[DecisionRecord, ...], list(decision_records)),
            stratagem_indexes_by_player_id=stratagem_indexes,
            ability_indexes_by_player_id=ability_indexes,
        )
    with pytest.raises(GameLifecycleError, match="event IDs are duplicated"):
        validate_primary_reserve_entry_lifecycle_integrity(
            state=state,
            event_records=(*event_records, event_records[-1]),
            decision_records=decision_records,
            stratagem_indexes_by_player_id=stratagem_indexes,
            ability_indexes_by_player_id=ability_indexes,
        )

    source_terminal = next(
        event for event in event_records if event.event_type == CATALOG_TURN_END_RESERVES_USED_EVENT
    )
    source_payload = cast(dict[str, JsonValue], source_terminal.payload)
    bindings = _source_terminal_bindings(source_terminal=source_terminal, generic=False)
    assert len(bindings) == 1
    reserve_states = _source_terminal_reserve_states(source_payload)
    assert len(reserve_states) == 1
    reserve_state = reserve_states[0]
    reserve_state_payload = cast(dict[str, JsonValue], reserve_state.to_payload())
    duplicate_source = EventRecord(
        event_id=f"event-{len(event_records) + 1:06d}",
        event_type=source_terminal.event_type,
        payload=source_terminal.payload,
    )
    with pytest.raises(GameLifecycleError, match="source terminal occurrence is duplicated"):
        validate_primary_reserve_entry_lifecycle_integrity(
            state=state,
            event_records=(*event_records, duplicate_source),
            decision_records=decision_records,
            stratagem_indexes_by_player_id=stratagem_indexes,
            ability_indexes_by_player_id=ability_indexes,
        )

    identity_payload = deepcopy(source_payload)
    identity_bindings = cast(
        list[JsonValue], identity_payload[PRIMARY_RESERVE_ENTRY_SOURCE_BINDINGS_KEY]
    )
    identity_binding = cast(dict[str, JsonValue], identity_bindings[0])
    identity_binding["occurrence_id"] = "forged:hunters-occurrence"
    with pytest.raises(GameLifecycleError, match="source terminal provider identity drift"):
        _source_terminal_bindings(
            source_terminal=EventRecord(
                event_id=source_terminal.event_id,
                event_type=source_terminal.event_type,
                payload=validate_json_value(identity_payload),
            ),
            generic=False,
        )

    with pytest.raises(GameLifecycleError, match="source terminal cardinality drift"):
        _validate_ability_source_terminal(source_terminal=source_terminal, bindings=())

    two_state_payload = deepcopy(source_payload)
    two_state_payload.pop("reserve_state")
    two_state_payload["reserve_states"] = [
        validate_json_value(reserve_state_payload),
        validate_json_value(
            replace(
                reserve_state,
                unit_instance_id=f"{reserve_state.unit_instance_id}:other",
            ).to_payload()
        ),
    ]
    with pytest.raises(GameLifecycleError, match="source terminal state cardinality drift"):
        _validate_ability_source_terminal(
            source_terminal=EventRecord(
                event_id=source_terminal.event_id,
                event_type=source_terminal.event_type,
                payload=validate_json_value(two_state_payload),
            ),
            bindings=bindings,
        )

    malformed_source_payloads: tuple[tuple[dict[str, JsonValue], str], ...] = (
        (
            {
                **deepcopy(source_payload),
                "reserve_states": [validate_json_value(reserve_state_payload)],
            },
            "reserve-state shape drift",
        ),
        (
            {**deepcopy(source_payload), "reserve_state": None, "reserve_states": []},
            "reserve states are malformed",
        ),
        (
            {**deepcopy(source_payload), "reserve_state": "not-a-reserve-state"},
            "ReserveState is malformed",
        ),
        (
            {**deepcopy(source_payload), "reserve_state": {}},
            "ReserveState is invalid",
        ),
        (
            {
                **deepcopy(source_payload),
                "reserve_state": {
                    **reserve_state_payload,
                    "large_model_exception_used": True,
                },
            },
            "must preserve entry-time ReserveState",
        ),
    )
    for malformed_payload, error_match in malformed_source_payloads:
        with pytest.raises(GameLifecycleError, match=error_match):
            _source_terminal_reserve_states(malformed_payload)

    duplicate_state_payload = deepcopy(source_payload)
    duplicate_state_payload.pop("reserve_state")
    duplicate_state_payload["reserve_states"] = [
        validate_json_value(reserve_state_payload),
        validate_json_value(reserve_state_payload),
    ]
    with pytest.raises(GameLifecycleError, match="ReserveState is duplicated"):
        _source_terminal_reserve_states(duplicate_state_payload)

    with pytest.raises(GameLifecycleError, match="state/binding cardinality drift"):
        _validate_source_binding_reserve_states(bindings=bindings, reserve_states=())
    with pytest.raises(GameLifecycleError, match="state/binding target drift"):
        _validate_source_binding_reserve_states(
            bindings=bindings,
            reserve_states=(
                replace(
                    reserve_state,
                    unit_instance_id=f"{reserve_state.unit_instance_id}:other",
                ),
            ),
        )
    with pytest.raises(GameLifecycleError, match="state/binding identity drift"):
        _validate_source_binding_reserve_states(
            bindings=bindings,
            reserve_states=(replace(reserve_state, player_id=enemy_player_id),),
        )

    with pytest.raises(GameLifecycleError, match="provider definition drift"):
        _validate_active_ability_catalog_authority(
            decisions=decisions,
            bindings=(
                replace(
                    bindings[0],
                    provider=replace(bindings[0].provider, provider_id="provider:forged"),
                ),
            ),
            ability_indexes_by_player_id=ability_indexes,
        )
    with pytest.raises(GameLifecycleError, match="requires active Ability catalog authority"):
        _validate_active_ability_catalog_authority(
            decisions=decisions,
            bindings=bindings,
            ability_indexes_by_player_id=None,
        )
    with pytest.raises(GameLifecycleError, match="lacks its active player Ability index"):
        _validate_active_ability_catalog_authority(
            decisions=decisions,
            bindings=bindings,
            ability_indexes_by_player_id={},
        )

    source_authority_payload = deepcopy(source_payload)
    source_authority_payload["ability_name"] = "Forged Hunters from the Warp"
    source_authority_terminal = EventRecord(
        event_id=source_terminal.event_id,
        event_type=source_terminal.event_type,
        payload=validate_json_value(source_authority_payload),
    )
    with pytest.raises(GameLifecycleError, match="active Ability authority drift"):
        _validate_active_ability_catalog_authority(
            decisions=decisions,
            bindings=(replace(bindings[0], source_terminal=source_authority_terminal),),
            ability_indexes_by_player_id=ability_indexes,
        )

    generic_provider = replace(
        bindings[0].provider,
        provider_kind=PrimaryReserveEntryProviderKind.GENERIC_RULE_IR_STRATAGEM,
        provider_id=GENERIC_RULE_IR_RESERVE_REMOVAL_PROVIDER_ID,
        stratagem_use_id="stratagem-use:hunters-boundary",
        source_terminal_event_type=GENERIC_STRATAGEM_RESERVE_REMOVAL_RESOLVED_EVENT,
    )
    generic_source_terminal = EventRecord(
        event_id=source_terminal.event_id,
        event_type=GENERIC_STRATAGEM_RESERVE_REMOVAL_RESOLVED_EVENT,
        payload=source_terminal.payload,
    )
    generic_binding = replace(
        bindings[0],
        occurrence_id=generic_provider.occurrence_id,
        provider=generic_provider,
        source_terminal=generic_source_terminal,
    )
    with pytest.raises(GameLifecycleError, match="use identity drift"):
        _validate_generic_source_terminal(
            state=state,
            source_terminal=generic_source_terminal,
            bindings=(),
        )
    with pytest.raises(GameLifecycleError, match="source terminal use is missing"):
        _validate_generic_source_terminal(
            state=state,
            source_terminal=generic_source_terminal,
            bindings=(generic_binding,),
        )
    with pytest.raises(GameLifecycleError, match="lacks its active player Stratagem index"):
        _validate_active_stratagem_catalog_authority(
            state=state,
            decision_records=decision_records,
            providers=(generic_provider,),
            stratagem_indexes_by_player_id={},
        )
    with pytest.raises(GameLifecycleError, match="accepted decision is missing"):
        _validate_active_stratagem_catalog_authority(
            state=state,
            decision_records=decision_records,
            providers=(replace(generic_provider, decision_record_id="decision-record:forged"),),
            stratagem_indexes_by_player_id=stratagem_indexes,
        )
    with pytest.raises(GameLifecycleError, match="accepted catalog selection is malformed"):
        _validate_active_stratagem_catalog_authority(
            state=state,
            decision_records=decision_records,
            providers=(generic_provider,),
            stratagem_indexes_by_player_id=stratagem_indexes,
        )

    event_index_by_id = {event.event_id: index for index, event in enumerate(event_records)}
    all_source_terminals = tuple(
        event for event in event_records if event.event_type == CATALOG_TURN_END_RESERVES_USED_EVENT
    )
    all_bindings = tuple(
        binding
        for terminal in all_source_terminals
        for binding in _source_terminal_bindings(source_terminal=terminal, generic=False)
    )
    entry_occurrences = tuple(
        PrimaryReserveEntryLifecycleOccurrence(
            event_order=event_index_by_id[binding.source_terminal.event_id],
            historical_unit_instance_id=binding.provider.target_rules_unit_instance_id,
            reserve_entry_state=binding.reserve_entry_state,
        )
        for binding in all_bindings
    )
    arrival_event = next(
        event for event in event_records if event.event_type == "reinforcement_unit_arrived"
    )
    arrival_payload = cast(dict[str, JsonValue], arrival_event.payload)
    arrival_unit_id = cast(str, arrival_payload["unit_instance_id"])
    arrival_request_id = cast(str, arrival_payload["request_id"])
    arrival_result_id = cast(str, arrival_payload["result_id"])
    arrival_decision = next(
        decision
        for decision in decision_records
        if decision.request.request_id == arrival_request_id
        and decision.result.result_id == arrival_result_id
    )

    with pytest.raises(GameLifecycleError, match="occurrence owner identity drift"):
        _validated_reserve_arrival_occurrences(
            state=state,
            event_records=event_records,
            decision_records=decision_records,
            event_index_by_id=event_index_by_id,
            relevant_player_id_by_unit_instance_id={arrival_unit_id: enemy_player_id},
            reserve_entry_occurrences=entry_occurrences,
            stratagem_indexes_by_player_id=stratagem_indexes,
        )

    missing_decision_payload = deepcopy(arrival_payload)
    missing_decision_payload["request_id"] = "forged:arrival-request"
    missing_decision_event = EventRecord(
        event_id=arrival_event.event_id,
        event_type=arrival_event.event_type,
        payload=validate_json_value(missing_decision_payload),
    )
    missing_decision_events = tuple(
        missing_decision_event if event.event_id == arrival_event.event_id else event
        for event in event_records
    )
    with pytest.raises(GameLifecycleError, match="lacks one accepted placement decision"):
        _validated_reserve_arrival_occurrences(
            state=state,
            event_records=missing_decision_events,
            decision_records=decision_records,
            event_index_by_id=event_index_by_id,
            relevant_player_id_by_unit_instance_id={
                arrival_unit_id: bindings[0].provider.player_id
            },
            reserve_entry_occurrences=entry_occurrences,
            stratagem_indexes_by_player_id=stratagem_indexes,
        )

    malformed_placement_decision = replace(
        arrival_decision,
        request=replace(arrival_decision.request, payload={}),
    )
    with pytest.raises(GameLifecycleError, match="placement evidence is invalid"):
        _validated_reserve_arrival_occurrences(
            state=state,
            event_records=event_records,
            decision_records=tuple(
                malformed_placement_decision
                if decision.record_id == arrival_decision.record_id
                else decision
                for decision in decision_records
            ),
            event_index_by_id=event_index_by_id,
            relevant_player_id_by_unit_instance_id={
                arrival_unit_id: bindings[0].provider.player_id
            },
            reserve_entry_occurrences=entry_occurrences,
            stratagem_indexes_by_player_id=stratagem_indexes,
        )

    requested_event = next(
        event
        for event in event_records
        if event.event_type == "decision_requested"
        and event.payload == arrival_decision.request.to_payload()
    )
    events_without_request = tuple(
        event for event in event_records if event.event_id != requested_event.event_id
    )
    with pytest.raises(GameLifecycleError, match="decision request closure drift"):
        _validated_reserve_arrival_occurrences(
            state=state,
            event_records=events_without_request,
            decision_records=decision_records,
            event_index_by_id={
                event.event_id: index for index, event in enumerate(events_without_request)
            },
            relevant_player_id_by_unit_instance_id={
                arrival_unit_id: bindings[0].provider.player_id
            },
            reserve_entry_occurrences=entry_occurrences,
            stratagem_indexes_by_player_id=stratagem_indexes,
        )

    arrival_occurrences = _validated_reserve_arrival_occurrences(
        state=state,
        event_records=event_records,
        decision_records=decision_records,
        event_index_by_id=event_index_by_id,
        relevant_player_id_by_unit_instance_id={arrival_unit_id: bindings[0].provider.player_id},
        reserve_entry_occurrences=entry_occurrences,
        stratagem_indexes_by_player_id=stratagem_indexes,
    )
    assert len(arrival_occurrences) == 1
    arrival_occurrence = arrival_occurrences[0]
    current_reserve_state = state.reserve_state_for_unit(arrival_unit_id)
    assert current_reserve_state is not None
    with pytest.raises(GameLifecycleError, match="decision predates its entry occurrence"):
        _validate_current_reserve_status(
            state=state,
            reserve_state=current_reserve_state,
            entry_order=arrival_occurrence.request_event_order,
            arrival_occurrences=arrival_occurrences,
            event_records=event_records,
            event_index_by_id=event_index_by_id,
        )
    with pytest.raises(GameLifecycleError, match="Unarrived ReserveState"):
        _validate_current_reserve_status(
            state=state,
            reserve_state=current_reserve_state,
            entry_order=-1,
            arrival_occurrences=arrival_occurrences,
            event_records=event_records,
            event_index_by_id=event_index_by_id,
        )
    arrived_state = replace(
        current_reserve_state,
        status=ReserveStatus.ARRIVED,
        arrived_battle_round=arrival_occurrence.battle_round + 1,
        arrived_phase=arrival_occurrence.phase,
    )
    with pytest.raises(GameLifecycleError, match="transition evidence drift"):
        _validate_current_reserve_status(
            state=state,
            reserve_state=arrived_state,
            entry_order=-1,
            arrival_occurrences=arrival_occurrences,
            event_records=event_records,
            event_index_by_id=event_index_by_id,
        )
    destroyed_state = replace(
        current_reserve_state,
        status=ReserveStatus.DESTROYED,
        destroyed_battle_round=5,
    )
    with pytest.raises(GameLifecycleError, match="Destroyed unarrived ReserveState"):
        _validate_current_reserve_status(
            state=state,
            reserve_state=destroyed_state,
            entry_order=-1,
            arrival_occurrences=arrival_occurrences,
            event_records=event_records,
            event_index_by_id=event_index_by_id,
        )

    with pytest.raises(GameLifecycleError, match="authenticated intervening arrival"):
        _validate_during_battle_reserve_state_reverse_closure(
            state=state,
            event_records=event_records,
            occurrences=entry_occurrences,
            arrival_occurrences=(),
            event_index_by_id=event_index_by_id,
        )
    with pytest.raises(GameLifecycleError, match="decision predates its entry occurrence"):
        _validate_during_battle_reserve_state_reverse_closure(
            state=state,
            event_records=event_records,
            occurrences=entry_occurrences,
            arrival_occurrences=(
                replace(
                    arrival_occurrence,
                    request_event_order=min(entry.event_order for entry in entry_occurrences),
                ),
            ),
            event_index_by_id=event_index_by_id,
        )
    drifted_state = deepcopy(state)
    drifted_state.replace_reserve_state(
        replace(current_reserve_state, source_rule_ids=("source-rule:forged",))
    )
    with pytest.raises(GameLifecycleError, match="authoritative entry occurrence"):
        _validate_during_battle_reserve_state_reverse_closure(
            state=drifted_state,
            event_records=event_records,
            occurrences=entry_occurrences,
            arrival_occurrences=arrival_occurrences,
            event_index_by_id=event_index_by_id,
        )

    with pytest.raises(GameLifecycleError, match="fields are malformed"):
        _closed_json_object(
            {},
            field_name="Hunters test payload",
            expected_keys=frozenset(("expected",)),
        )
    with pytest.raises(GameLifecycleError, match="must be an object"):
        _json_object([], field_name="Hunters test payload")
    with pytest.raises(GameLifecycleError, match="must be an identifier"):
        _required_identifier(" ", field_name="Hunters test identifier")
    with pytest.raises(GameLifecycleError, match="must be an identifier list"):
        _unique_identifier_list(None, field_name="Hunters test identifiers")
    with pytest.raises(GameLifecycleError, match="must be an identifier list"):
        _unique_identifier_list([1], field_name="Hunters test identifiers")
    with pytest.raises(GameLifecycleError, match="must not contain duplicates"):
        _unique_identifier_list(["same", "same"], field_name="Hunters test identifiers")


def test_phase17n_primary_reserve_provider_payload_and_definition_boundaries_fail_closed() -> None:
    ability_provider = PrimaryReserveEntryProvider(
        provider_kind=PrimaryReserveEntryProviderKind.TURN_END_ABILITY,
        provider_id=CATALOG_IR_CAN_BE_PLACED_IN_RESERVES_CONSUMER_ID,
        player_id="player-a",
        source_rule_id="source-rule:hunters",
        target_rules_unit_instance_id="unit:hunters",
        decision_record_id="decision-record-000001",
        decision_request_id="decision-request:hunters",
        decision_result_id="decision-result:hunters",
        stratagem_use_id=None,
        source_terminal_event_type=CATALOG_TURN_END_RESERVES_USED_EVENT,
    )
    ability_payload = ability_provider.to_payload()
    assert PrimaryReserveEntryProvider.from_payload(ability_payload) == ability_provider
    assert ability_provider.reserve_origin is ReserveOrigin.DURING_BATTLE_ABILITY
    assert ability_provider.occurrence_id == ("decision-result:hunters:reserve-entry:unit:hunters")
    assert (
        primary_reserve_entry_provider_kind_from_token(
            PrimaryReserveEntryProviderKind.TURN_END_ABILITY
        )
        is PrimaryReserveEntryProviderKind.TURN_END_ABILITY
    )
    assert (
        primary_reserve_entry_provider_kind_from_token("turn_end_ability")
        is PrimaryReserveEntryProviderKind.TURN_END_ABILITY
    )

    stratagem_provider = PrimaryReserveEntryProvider(
        provider_kind=PrimaryReserveEntryProviderKind.GENERIC_RULE_IR_STRATAGEM,
        provider_id=GENERIC_RULE_IR_RESERVE_REMOVAL_PROVIDER_ID,
        player_id="player-a",
        source_rule_id="source-rule:from-beyond-the-veil",
        target_rules_unit_instance_id="unit:bloodcrushers",
        decision_record_id="decision-record-000002",
        decision_request_id="decision-request:from-beyond",
        decision_result_id="decision-result:from-beyond",
        stratagem_use_id="stratagem-use:from-beyond",
        source_terminal_event_type=GENERIC_STRATAGEM_RESERVE_REMOVAL_RESOLVED_EVENT,
    )
    assert PrimaryReserveEntryProvider.from_payload(stratagem_provider.to_payload()) == (
        stratagem_provider
    )
    assert stratagem_provider.reserve_origin is ReserveOrigin.DURING_BATTLE_STRATAGEM
    assert stratagem_provider.occurrence_id == (
        "stratagem-use:from-beyond:reserve-entry:unit:bloodcrushers"
    )

    with pytest.raises(GameLifecycleError, match="payload is malformed"):
        PrimaryReserveEntryProvider.from_payload([])
    missing_key_payload = dict(ability_payload)
    missing_key_payload.pop("provider_id")
    with pytest.raises(GameLifecycleError, match="payload is malformed"):
        PrimaryReserveEntryProvider.from_payload(missing_key_payload)
    extra_key_payload = dict(ability_payload)
    extra_key_payload["forged"] = True
    with pytest.raises(GameLifecycleError, match="payload is malformed"):
        PrimaryReserveEntryProvider.from_payload(extra_key_payload)
    empty_identifier_payload = dict(ability_payload)
    empty_identifier_payload["provider_id"] = ""
    with pytest.raises(GameLifecycleError, match="provider_id"):
        PrimaryReserveEntryProvider.from_payload(empty_identifier_payload)
    with pytest.raises(GameLifecycleError, match="kind must be a string"):
        primary_reserve_entry_provider_kind_from_token(1)
    with pytest.raises(GameLifecycleError, match="kind is unsupported"):
        primary_reserve_entry_provider_kind_from_token("forged-provider-kind")
    with pytest.raises(GameLifecycleError, match="cannot name a Stratagem use"):
        replace(ability_provider, stratagem_use_id="stratagem-use:forged")
    with pytest.raises(GameLifecycleError, match="requires a Stratagem use"):
        replace(stratagem_provider, stratagem_use_id=None)
    with pytest.raises(GameLifecycleError, match="identity drift"):
        replace(stratagem_provider, provider_id="generic:forged-reserve-provider")
    with pytest.raises(GameLifecycleError, match="identity drift"):
        replace(stratagem_provider, source_terminal_event_type="forged_terminal")

    definition = next(
        value
        for value in default_primary_reserve_entry_ability_provider_definitions()
        if value.provider_id == CATALOG_IR_CAN_BE_PLACED_IN_RESERVES_CONSUMER_ID
    )
    assert definition.authority_kind is PrimaryReserveEntryAbilityAuthorityKind.CATALOG_RULE_IR
    with pytest.raises(GameLifecycleError, match="required arrival is incomplete"):
        replace(definition, required_arrival_timing="next_owner_movement_phase")
    with pytest.raises(GameLifecycleError, match="authority kind is invalid"):
        replace(
            definition,
            authority_kind=cast(PrimaryReserveEntryAbilityAuthorityKind, "forged"),
        )
    with pytest.raises(GameLifecycleError, match="Catalog ability provider definition"):
        replace(definition, source_rule_id="source-rule:forged")
    with pytest.raises(GameLifecycleError, match=r"Source-specific.*incomplete"):
        replace(
            definition,
            authority_kind=PrimaryReserveEntryAbilityAuthorityKind.DATASHEET_ABILITY,
        )
    with pytest.raises(GameLifecycleError, match="Only Datasheet ability providers"):
        replace(
            definition,
            component_match_policy=PrimaryReserveEntryComponentMatchPolicy.ALL_COMPONENTS,
        )
    with pytest.raises(GameLifecycleError, match="identity keys must be a tuple"):
        replace(
            definition,
            terminal_request_identity_keys=cast(tuple[str, ...], ["request_id"]),
        )
    with pytest.raises(GameLifecycleError, match="identity keys must be unique"):
        replace(
            definition,
            terminal_result_identity_keys=("result_id", "result_id"),
        )
    with pytest.raises(GameLifecycleError, match="terminal identity must be a tuple"):
        replace(
            definition,
            terminal_static_identity=cast(tuple[tuple[str, JsonValue], ...], []),
        )
    with pytest.raises(GameLifecycleError, match="identity row is malformed"):
        replace(
            definition,
            terminal_static_identity=cast(
                tuple[tuple[str, JsonValue], ...],
                ("not-a-row",),
            ),
        )
    with pytest.raises(GameLifecycleError, match="identity row is malformed"):
        replace(definition, terminal_static_identity=(cast(tuple[str, JsonValue], ("key",)),))
    with pytest.raises(GameLifecycleError, match="identity keys must be unique"):
        replace(
            definition,
            terminal_static_identity=(("key", 1), ("key", 2)),
        )


def test_phase17n_hunters_provider_source_and_state_integrity_fail_closed() -> None:
    package = flesh_hounds_package()
    catalog, muster_requests, armies = config_backed_flesh_hounds_armies(
        package=package,
        enemy_unit_selection_id="enemy-flesh-hounds-1",
    )
    army, enemy_army = armies
    unit = army.units[0]
    enemy_unit = enemy_army.units[0]
    state = battle_state_with_armies(
        armies=armies,
        battlefield=flesh_hounds_battlefield_state(
            army=army,
            unit=unit,
            enemy_army=enemy_army,
            enemy_unit=enemy_unit,
            enemy_x=30.0,
        ),
        active_player_id=enemy_army.player_id,
        phase=BattlePhase.FIGHT,
    )
    config = GameConfig(
        game_id=state.game_id,
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(),
        army_catalog=catalog,
        army_muster_requests=muster_requests,
        player_ids=state.player_ids,
        turn_order=state.turn_order,
        fixed_secondary_mission_ids=("assassination", "bring_it_down"),
        mission_setup=state.mission_setup,
        allow_legacy_non_strict_rosters=True,
        model_geometries=package.model_geometries,
    )
    runtime_bundle = build_runtime_content_bundle_for_armies(config=config, armies=armies)
    hunters_record = next(
        record
        for record in runtime_bundle.ability_indexes_by_player_id[army.player_id].all_records()
        if record.definition.name == "Hunters from the Warp"
    )
    registry = runtime_bundle.turn_end_hook_registry
    decisions = DecisionController()
    request = registry.next_request_for(
        TurnEndRequestContext(
            state=state,
            decisions=decisions,
            completed_phase=BattlePhase.FIGHT,
        )
    )
    assert request is not None
    decisions.request_decision(request)
    use_option = next(option for option in request.options if option.option_id.endswith(":use"))
    result = DecisionResult.for_request(
        result_id="result-hunters-integrity",
        request=request,
        selected_option_id=use_option.option_id,
    )
    decisions.submit_result(result)

    provider = primary_reserve_entry_provider_from_accepted_ability_decision(
        state=state,
        decisions=decisions,
        result=result,
        provider_id=CATALOG_IR_CAN_BE_PLACED_IN_RESERVES_CONSUMER_ID,
        source_rule_id=hunters_record.definition.source_id,
        target_rules_unit_instance_id=unit.unit_instance_id,
        source_terminal_event_type=CATALOG_TURN_END_RESERVES_USED_EVENT,
    )
    validate_primary_reserve_entry_provider_registration(state=state, provider=provider)
    validate_accepted_primary_reserve_entry_provider(
        state=state,
        decisions=decisions,
        provider=provider,
    )
    assert (
        primary_reserve_entry_requirements(
            state=state,
            decisions=decisions,
            provider=provider,
        ).required_arrival_battle_round
        is None
    )

    with pytest.raises(GameLifecycleError, match="requires GameState"):
        primary_reserve_entry_provider_from_accepted_ability_decision(
            state=None,
            decisions=decisions,
            result=result,
            provider_id=provider.provider_id,
            source_rule_id=provider.source_rule_id,
            target_rules_unit_instance_id=provider.target_rules_unit_instance_id,
            source_terminal_event_type=provider.source_terminal_event_type,
        )
    with pytest.raises(GameLifecycleError, match="accepted decision context"):
        primary_reserve_entry_provider_from_accepted_ability_decision(
            state=state,
            decisions=cast(DecisionController, None),
            result=result,
            provider_id=provider.provider_id,
            source_rule_id=provider.source_rule_id,
            target_rules_unit_instance_id=provider.target_rules_unit_instance_id,
            source_terminal_event_type=provider.source_terminal_event_type,
        )
    with pytest.raises(GameLifecycleError, match="result was not accepted"):
        primary_reserve_entry_provider_from_accepted_ability_decision(
            state=state,
            decisions=decisions,
            result=replace(result, result_id="result-hunters-unaccepted"),
            provider_id=provider.provider_id,
            source_rule_id=provider.source_rule_id,
            target_rules_unit_instance_id=provider.target_rules_unit_instance_id,
            source_terminal_event_type=provider.source_terminal_event_type,
        )
    with pytest.raises(GameLifecycleError, match="decision context drift"):
        primary_reserve_entry_provider_from_accepted_ability_decision(
            state=state,
            decisions=decisions,
            result=result,
            provider_id=provider.provider_id,
            source_rule_id="source-rule:forged",
            target_rules_unit_instance_id=provider.target_rules_unit_instance_id,
            source_terminal_event_type=provider.source_terminal_event_type,
        )
    with pytest.raises(GameLifecycleError, match="not registered"):
        validate_primary_reserve_entry_provider_registration(
            state=state,
            provider=replace(provider, provider_id="provider:forged"),
        )
    with pytest.raises(GameLifecycleError, match="target drift"):
        validate_primary_reserve_entry_provider_registration(
            state=state,
            provider=replace(
                provider,
                target_rules_unit_instance_id=enemy_unit.unit_instance_id,
            ),
        )
    with pytest.raises(GameLifecycleError, match="accepted decision is missing"):
        validate_accepted_primary_reserve_entry_provider(
            state=state,
            decisions=decisions,
            provider=replace(provider, decision_result_id="result:forged"),
        )
    with pytest.raises(GameLifecycleError, match="typed provider authority"):
        validate_accepted_primary_reserve_entry_provider(
            state=state,
            decisions=decisions,
            provider=cast(PrimaryReserveEntryProvider, None),
        )

    reordered_payload: DecisionControllerPayload = deepcopy(decisions.to_payload())
    first_event = reordered_payload["event_log"][0]
    second_event = reordered_payload["event_log"][1]
    first_event["event_type"], second_event["event_type"] = (
        second_event["event_type"],
        first_event["event_type"],
    )
    first_event["payload"], second_event["payload"] = (
        second_event["payload"],
        first_event["payload"],
    )
    with pytest.raises(GameLifecycleError, match="decision event ordering drift"):
        validate_accepted_primary_reserve_entry_provider(
            state=state,
            decisions=DecisionController.from_payload(reordered_payload),
            provider=provider,
        )
    accepted_context_payload: DecisionControllerPayload = deepcopy(decisions.to_payload())
    accepted_record_payload = accepted_context_payload["records"][0]
    selected_option_payload = next(
        option
        for option in accepted_record_payload["request"]["options"]
        if option["option_id"] == accepted_record_payload["result"]["selected_option_id"]
    )
    cast(dict[str, JsonValue], selected_option_payload["payload"])["use_ability"] = False
    cast(dict[str, JsonValue], accepted_record_payload["result"]["payload"])["use_ability"] = False
    for event in accepted_context_payload["event_log"]:
        if event["event_type"] == "decision_requested":
            event["payload"] = validate_json_value(deepcopy(accepted_record_payload["request"]))
        elif event["event_type"] == "decision_recorded":
            event["payload"] = validate_json_value(deepcopy(accepted_record_payload))
    with pytest.raises(GameLifecycleError, match="accepted context drift"):
        validate_accepted_primary_reserve_entry_provider(
            state=state,
            decisions=DecisionController.from_payload(accepted_context_payload),
            provider=provider,
        )

    assert registry.apply_result(
        TurnEndResultContext(
            state=state,
            decisions=decisions,
            request=request,
            result=result,
        )
    )
    decision = decisions.record_for_result(result)
    event_records = decisions.event_log.records
    mutation_order, mutation_event = next(
        (index, event)
        for index, event in enumerate(event_records)
        if event.event_type == PRIMARY_RESERVE_ENTRY_MUTATION_EVENT
    )
    source_terminal = next(
        event for event in event_records if event.event_type == CATALOG_TURN_END_RESERVES_USED_EVENT
    )
    mutation_payload = cast(dict[str, JsonValue], mutation_event.payload)
    reserve_entry = cast(dict[str, JsonValue], mutation_payload["reserve_entry_state"])
    mutation_provider = PrimaryReserveEntryProvider.from_payload(mutation_payload["provider"])
    source_payload = cast(dict[str, JsonValue], source_terminal.payload)
    source_bindings = cast(
        list[JsonValue],
        source_payload[PRIMARY_RESERVE_ENTRY_SOURCE_BINDINGS_KEY],
    )
    source_binding = cast(dict[str, JsonValue], source_bindings[0])
    assert mutation_provider == provider
    assert PrimaryReserveEntryProvider.from_payload(source_binding["provider"]) == provider
    assert source_binding["reserve_entry_state"] == reserve_entry

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
    validate_primary_reserve_entry_source_terminal_identity(
        state=state,
        provider=provider,
        decision=decision,
        terminal_payload=source_payload,
        reserve_entry=reserve_entry,
    )
    occurrence = PrimaryReserveEntryStateOccurrence(
        mutation_order=mutation_order,
        historical_unit_instance_id=unit.unit_instance_id,
        reserve_entry=reserve_entry,
    )
    validate_latest_primary_reserve_entry_states(
        state=state,
        occurrences=(occurrence,),
        event_records=event_records,
    )

    def terminal_with_payload(payload: object) -> EventRecord:
        return replace(source_terminal, payload=validate_json_value(payload))

    timing_payload = dict(source_payload)
    timing_payload["active_player_id"] = army.player_id
    with pytest.raises(GameLifecycleError, match="terminal timing drift"):
        validate_primary_reserve_entry_source_terminal_semantics(
            state=state,
            provider=provider,
            decision=decision,
            reserve_entry=reserve_entry,
            source_terminal=terminal_with_payload(timing_payload),
            event_records=event_records,
        )
    binding_payload = dict(source_payload)
    binding_payload[PRIMARY_RESERVE_ENTRY_SOURCE_BINDINGS_KEY] = []
    with pytest.raises(GameLifecycleError, match="binding cardinality drift"):
        validate_primary_reserve_entry_source_terminal_semantics(
            state=state,
            provider=provider,
            decision=decision,
            reserve_entry=reserve_entry,
            source_terminal=terminal_with_payload(binding_payload),
            event_records=event_records,
        )
    ambiguous_target_payload = dict(source_payload)
    ambiguous_target_payload["target_rules_unit_instance_id"] = unit.unit_instance_id
    with pytest.raises(GameLifecycleError, match="target identity is ambiguous"):
        validate_primary_reserve_entry_source_terminal_semantics(
            state=state,
            provider=provider,
            decision=decision,
            reserve_entry=reserve_entry,
            source_terminal=terminal_with_payload(ambiguous_target_payload),
            event_records=event_records,
        )
    context_payload = dict(source_payload)
    context_payload["source_rule_id"] = "source-rule:forged"
    with pytest.raises(GameLifecycleError, match="terminal context drift"):
        validate_primary_reserve_entry_source_terminal_semantics(
            state=state,
            provider=provider,
            decision=decision,
            reserve_entry=reserve_entry,
            source_terminal=terminal_with_payload(context_payload),
            event_records=event_records,
        )
    terminal_identity_payload = dict(source_payload)
    terminal_identity_payload["catalog_record_id"] = "catalog-record:forged"
    with pytest.raises(GameLifecycleError, match="terminal result identity drift"):
        validate_primary_reserve_entry_source_terminal_semantics(
            state=state,
            provider=provider,
            decision=decision,
            reserve_entry=reserve_entry,
            source_terminal=terminal_with_payload(terminal_identity_payload),
            event_records=event_records,
        )
    catalog_identity_payload = dict(source_payload)
    catalog_identity_payload["ability_id"] = "ability:forged"
    with pytest.raises(GameLifecycleError, match="ability identity drift"):
        validate_primary_reserve_entry_source_terminal_semantics(
            state=state,
            provider=provider,
            decision=decision,
            reserve_entry=reserve_entry,
            source_terminal=terminal_with_payload(catalog_identity_payload),
            event_records=event_records,
        )

    two_state_shapes_payload = dict(source_payload)
    two_state_shapes_payload["reserve_states"] = [source_payload["reserve_state"]]
    with pytest.raises(GameLifecycleError, match="reserve-state shape drift"):
        validate_primary_reserve_entry_source_terminal_semantics(
            state=state,
            provider=provider,
            decision=decision,
            reserve_entry=reserve_entry,
            source_terminal=terminal_with_payload(two_state_shapes_payload),
            event_records=event_records,
        )
    malformed_state_payload = dict(source_payload)
    malformed_state_payload["reserve_state"] = 1
    with pytest.raises(GameLifecycleError, match="ReserveState is malformed"):
        validate_primary_reserve_entry_source_terminal_semantics(
            state=state,
            provider=provider,
            decision=decision,
            reserve_entry=reserve_entry,
            source_terminal=terminal_with_payload(malformed_state_payload),
            event_records=event_records,
        )
    invalid_state_payload = dict(source_payload)
    invalid_state_payload["reserve_state"] = {}
    with pytest.raises(GameLifecycleError, match="ReserveState is invalid"):
        validate_primary_reserve_entry_source_terminal_semantics(
            state=state,
            provider=provider,
            decision=decision,
            reserve_entry=reserve_entry,
            source_terminal=terminal_with_payload(invalid_state_payload),
            event_records=event_records,
        )
    wrong_state_payload = dict(source_payload)
    wrong_reserve_state = dict(cast(dict[str, JsonValue], source_payload["reserve_state"]))
    wrong_reserve_state["entered_reserves_phase"] = BattlePhase.SHOOTING.value
    wrong_state_payload["reserve_state"] = wrong_reserve_state
    with pytest.raises(GameLifecycleError, match="ReserveState identity drift"):
        validate_primary_reserve_entry_source_terminal_semantics(
            state=state,
            provider=provider,
            decision=decision,
            reserve_entry=reserve_entry,
            source_terminal=terminal_with_payload(wrong_state_payload),
            event_records=event_records,
        )

    requirements_drift = dict(reserve_entry)
    requirements_drift["required_arrival_phase"] = BattlePhase.MOVEMENT.value
    with pytest.raises(GameLifecycleError, match="source requirements drift"):
        validate_primary_reserve_entry_source_requirements(
            state=state,
            provider=provider,
            reserve_entry=requirements_drift,
            source_terminal=source_terminal,
        )
    with pytest.raises(GameLifecycleError, match="source requirements require typed authority"):
        validate_primary_reserve_entry_source_requirements(
            state=state,
            provider=cast(PrimaryReserveEntryProvider, None),
            reserve_entry=reserve_entry,
            source_terminal=source_terminal,
        )
    with pytest.raises(GameLifecycleError, match="source semantics require typed authority"):
        validate_primary_reserve_entry_source_terminal_semantics(
            state=state,
            provider=provider,
            decision=decision,
            reserve_entry=reserve_entry,
            source_terminal=cast(EventRecord, None),
            event_records=event_records,
        )

    with pytest.raises(GameLifecycleError, match="occurrences are malformed"):
        validate_latest_primary_reserve_entry_states(
            state=state,
            occurrences=cast(tuple[PrimaryReserveEntryStateOccurrence, ...], []),
            event_records=event_records,
        )
    duplicate_state = deepcopy(state)
    duplicate_state.reserve_states.append(deepcopy(duplicate_state.reserve_states[0]))
    with pytest.raises(GameLifecycleError, match="ReserveState identity is duplicated"):
        validate_latest_primary_reserve_entry_states(
            state=duplicate_state,
            occurrences=(occurrence,),
            event_records=event_records,
        )
    missing_state = deepcopy(state)
    missing_state.reserve_states.clear()
    with pytest.raises(GameLifecycleError, match="requires an attached split transfer"):
        validate_latest_primary_reserve_entry_states(
            state=missing_state,
            occurrences=(occurrence,),
            event_records=event_records,
        )
    drift_occurrence = replace(
        occurrence,
        reserve_entry={**reserve_entry, "source_rule_ids": ["source-rule:forged"]},
    )
    with pytest.raises(GameLifecycleError, match="lacks its persisted ReserveState"):
        validate_latest_primary_reserve_entry_states(
            state=state,
            occurrences=(drift_occurrence,),
            event_records=event_records,
        )


def test_phase17n_real_destroy_restore_hunters_entry_orders_before_deadline_timeline() -> None:
    package = flesh_hounds_package()
    catalog, muster_requests, armies = config_backed_flesh_hounds_armies(
        package=package,
        enemy_unit_selection_id="enemy-flesh-hounds-timeline",
    )
    army, enemy_army = armies
    unit = army.units[0]
    enemy_unit = enemy_army.units[0]
    state = battle_state_with_armies(
        armies=armies,
        battlefield=flesh_hounds_battlefield_state(
            army=army,
            unit=unit,
            enemy_army=enemy_army,
            enemy_unit=enemy_unit,
            enemy_x=30.0,
        ),
        active_player_id=enemy_army.player_id,
        phase=BattlePhase.FIGHT,
    )
    config = GameConfig(
        game_id=state.game_id,
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(),
        army_catalog=catalog,
        army_muster_requests=muster_requests,
        player_ids=state.player_ids,
        turn_order=state.turn_order,
        fixed_secondary_mission_ids=("assassination", "bring_it_down"),
        mission_setup=state.mission_setup,
        allow_legacy_non_strict_rosters=True,
        model_geometries=package.model_geometries,
    )
    runtime_bundle = build_runtime_content_bundle_for_armies(config=config, armies=armies)
    player_index = runtime_bundle.ability_indexes_by_player_id[army.player_id]
    hunters_record = next(
        record
        for record in player_index.all_records()
        if record.definition.name == "Hunters from the Warp"
    )
    registry = runtime_bundle.turn_end_hook_registry
    decisions = DecisionController()
    lifecycle = GameLifecycle(
        state=state,
        decision_controller=decisions,
        _config=config,
        _runtime_content_bundle=runtime_bundle,
    )
    assert state.battlefield_state is not None
    destroyed_model_id = unit.own_models[0].model_instance_id
    return_placement = state.battlefield_state.model_placement_by_id(destroyed_model_id)
    return_placement = return_placement.with_pose(Pose.at(x=10.0, y=12.0))
    source_witness = rules_unit_objective_proximity_witness(
        state=state,
        rules_unit_instance_id=enemy_unit.unit_instance_id,
    )
    destroyed_witness = rules_unit_objective_proximity_witness(
        state=state,
        rules_unit_instance_id=unit.unit_instance_id,
    )
    attribution = ModelDestructionAttribution.for_non_attack(
        destroying_player_id=enemy_army.player_id,
        source_kind=DestructionSourceKind.ABILITY,
        source_rules_unit_instance_id=enemy_unit.unit_instance_id,
        source_model_instance_id=enemy_unit.own_models[0].model_instance_id,
    )
    set_current_model_wounds(
        state,
        model_instance_id=destroyed_model_id,
        wounds_remaining=0,
    )
    state.battlefield_state = state.battlefield_state.with_removed_models((destroyed_model_id,))
    destroyed_event = decisions.event_log.append(
        "model_destroyed",
        {
            "game_id": state.game_id,
            "battle_round": state.battle_round,
            "active_player_id": state.active_player_id,
            "phase": BattlePhase.FIGHT.value,
            **attribution.to_payload(),
            "source_rules_unit_objective_proximity_witness": source_witness.to_payload(),
            "destroyed_rules_unit_objective_proximity_witness": destroyed_witness.to_payload(),
            "target_unit_instance_id": unit.unit_instance_id,
            "model_instance_id": destroyed_model_id,
        },
    )
    departure_ids_before = tuple(
        departure.departure_id for departure in state.primary_battlefield_departure_states
    )
    tracking_source_id = f"core-rules:primary-unit-destruction-tracking:{destroyed_event.event_id}"
    record_primary_destroyed_model_departures(
        state=state,
        destroyed_model_instance_ids=(destroyed_model_id,),
        source_id=tracking_source_id,
        occurrence_id=destroyed_event.event_id,
    )
    assert (
        record_primary_unit_destructions_for_destroyed_models(
            state=state,
            destroyed_model_instance_ids=(destroyed_model_id,),
            destruction_attribution=attribution,
            source_model_destroyed_event_id=destroyed_event.event_id,
            source_rules_unit_objective_proximity_witness=source_witness,
            destroyed_rules_unit_objective_proximity_witness=destroyed_witness,
            unattributed_cause=None,
            source_mutation_id=None,
            left_battlefield=False,
            source_id=tracking_source_id,
        )
        == ()
    )
    record_new_primary_battlefield_departure_events(
        state=state,
        event_log=decisions.event_log,
        departure_ids_before=departure_ids_before,
    )

    healing_effect = HealingEffect(
        effect_id="phase17n-hunters-timeline-restoration",
        target_unit_instance_id=unit.unit_instance_id,
        amount=1,
        opposing_player_id=enemy_army.player_id,
        source_rule_id="phase17n:test-authenticated-restoration",
        phase_start_model_ids=unit.own_model_ids(),
    )
    blocked_effect, placement_request = resolve_healing_until_blocked(
        state=state,
        decisions=decisions,
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(),
        effect=healing_effect,
    )
    assert placement_request is not None
    placement_result = DecisionResult(
        result_id="phase17n-hunters-timeline-restoration-result",
        request_id=placement_request.request_id,
        decision_type=placement_request.decision_type,
        actor_id=placement_request.actor_id,
        selected_option_id=PARAMETERIZED_DECISION_OPTION_ID,
        payload=validate_json_value(
            {
                "proposal_request_id": placement_request.request_id,
                "proposal_kind": "healing_revival_placement",
                "unit_instance_id": return_placement.unit_instance_id,
                "placement_kind": BattlefieldPlacementKind.RETURN_TO_BATTLEFIELD.value,
                "attempted_placement": UnitPlacement(
                    army_id=return_placement.army_id,
                    player_id=return_placement.player_id,
                    unit_instance_id=return_placement.unit_instance_id,
                    model_placements=(return_placement,),
                ).to_payload(),
            }
        ),
    )
    resolved_effect, follow_up = apply_healing_revival_placement_decision(
        state=state,
        decisions=decisions,
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(),
        effect=blocked_effect,
        result=placement_result,
    )
    assert resolved_effect.is_complete()
    assert follow_up is None
    assert state.battlefield_state is not None
    assert destroyed_model_id in state.battlefield_state.placed_model_ids()

    hunters_request = registry.next_request_for(
        TurnEndRequestContext(
            state=state,
            decisions=decisions,
            completed_phase=BattlePhase.FIGHT,
        )
    )
    assert hunters_request is not None
    decisions.request_decision(hunters_request)
    hunters_result = DecisionResult.for_request(
        result_id="phase17n-hunters-timeline-entry-result",
        request=hunters_request,
        selected_option_id=next(
            option.option_id
            for option in hunters_request.options
            if option.option_id.endswith(":use")
        ),
    )
    decisions.submit_result(hunters_result)
    assert registry.apply_result(
        TurnEndResultContext(
            state=state,
            decisions=decisions,
            request=hunters_request,
            result=hunters_result,
        )
    )
    reserve_state = state.reserve_state_for_unit(unit.unit_instance_id)
    assert reserve_state is not None
    assert reserve_state.source_rule_ids == (hunters_record.definition.source_id,)
    actual_payload = lifecycle.to_payload()
    assert (
        GameLifecycle.from_payload(
            deepcopy(actual_payload),
            runtime_content_bundle=runtime_bundle,
        ).to_payload()
        == actual_payload
    )
    # No supported source-backed matched-play pack destroys this during-battle
    # Strategic Reserves entry: Chapter Approved explicitly excludes it.  The
    # deadline policy below is test-only and drives only the generic chronology
    # validator after the entire destroy/restore/provider-entry chain above was real.
    core_policy = ReserveDestructionTimingPolicy.core_rules_default()
    state.replace_reserve_state(replace(reserve_state, destruction_deadline_policy=core_policy))
    state.battle_round = 5
    state.record_primary_rules_unit_turn_start_snapshot(
        build_primary_rules_unit_turn_start_snapshot(state=state)
    )
    deadline_result = resolve_unarrived_reserve_destruction(
        reserve_states=tuple(state.reserve_states),
        armies=tuple(state.army_definitions),
        battlefield_state=state.battlefield_state,
        policy=core_policy,
        battle_round=5,
        end_of_battle=True,
    )
    assert len(deadline_result.destroyed_model_instance_ids) == len(unit.own_models)
    state.battlefield_state = apply_reserve_destruction_to_battlefield(
        battlefield_state=state.battlefield_state,
        destruction=deadline_result,
    )
    state.reserve_states = list(deadline_result.updated_reserve_states)
    mutation_id = f"{core_policy.source_id}:round-05:end-of-battle"
    destruction_ids_before = tuple(
        destruction.destruction_id for destruction in state.primary_unit_destruction_states
    )
    deadline_destructions = record_primary_unit_destructions_for_destroyed_models(
        state=state,
        destroyed_model_instance_ids=deadline_result.destroyed_model_instance_ids,
        destruction_attribution=None,
        source_model_destroyed_event_id=None,
        source_rules_unit_objective_proximity_witness=None,
        destroyed_rules_unit_objective_proximity_witness=None,
        unattributed_cause=PrimaryUnattributedDestructionCause.RESERVE_DEADLINE,
        source_mutation_id=mutation_id,
        left_battlefield=False,
        source_id=mutation_id,
    )
    assert len(deadline_destructions) == 1
    record_new_primary_unit_destruction_events(
        state=state,
        event_log=decisions.event_log,
        destruction_ids_before=destruction_ids_before,
    )
    event_records = decisions.event_log.records
    event_index_by_id = {event.event_id: index for index, event in enumerate(event_records)}
    destroyed_reserve_state = state.reserve_state_for_unit(unit.unit_instance_id)
    assert destroyed_reserve_state is not None
    entry_source_terminal = next(
        event
        for event in reversed(event_records)
        if event.event_type == CATALOG_TURN_END_RESERVES_USED_EVENT
    )
    entry_order = event_index_by_id[entry_source_terminal.event_id]
    _validate_reserve_deadline_destruction(
        state=state,
        reserve_state=destroyed_reserve_state,
        entry_order=entry_order,
        event_records=event_records,
        event_index_by_id=event_index_by_id,
    )
    assert (
        _validate_current_reserve_status(
            state=state,
            reserve_state=destroyed_reserve_state,
            entry_order=entry_order,
            arrival_occurrences=(),
            event_records=event_records,
            event_index_by_id=event_index_by_id,
        )
        is None
    )
    with pytest.raises(GameLifecycleError, match="lacks its destruction round"):
        _validate_reserve_deadline_destruction(
            state=state,
            reserve_state=reserve_state,
            entry_order=entry_order,
            event_records=event_records,
            event_index_by_id=event_index_by_id,
        )
    missing_destruction_events = tuple(
        event for event in event_records if event.event_type != "primary_unit_destruction_recorded"
    )
    with pytest.raises(GameLifecycleError, match="destruction event closure drift"):
        _validate_reserve_deadline_destruction(
            state=state,
            reserve_state=destroyed_reserve_state,
            entry_order=entry_order,
            event_records=missing_destruction_events,
            event_index_by_id={
                event.event_id: index for index, event in enumerate(missing_destruction_events)
            },
        )
    model_ids_by_unit_id = {
        candidate.unit_instance_id: tuple(sorted(candidate.own_model_ids()))
        for definition in state.army_definitions
        for candidate in definition.units
    }
    identities_by_id = _scoring_identities_by_id(
        state=state,
        model_ids_by_unit_id=model_ids_by_unit_id,
    )
    departures = tuple(state.primary_battlefield_departure_states)
    destructions = tuple(state.primary_unit_destruction_states)
    departure_sources = _validate_destroyed_departure_provenance(
        state=state,
        destructions=destructions,
        departures=departures,
        identities_by_id=identities_by_id,
        model_ids_by_unit_id=model_ids_by_unit_id,
        rules_unit_components_by_id=_rules_unit_components_by_id(state=state),
        event_records=event_records,
        events_by_id={event.event_id: event for event in event_records},
        event_index_by_id=event_index_by_id,
        decision_records=decisions.records,
    )
    validate_full_destruction_transition_timeline(
        state=state,
        destructions=destructions,
        departures=departures,
        departure_sources=departure_sources,
        event_records=event_records,
        event_index_by_id=event_index_by_id,
        identities_by_id=identities_by_id,
        decision_records=decisions.records,
    )
    destroyed_departure = next(
        departure
        for departure in departures
        if departure.removal_kind is BattlefieldRemovalKind.DESTROYED
    )
    destroyed_source = departure_sources[destroyed_departure.departure_id]
    from warhammer40k_core.engine.primary_destruction_timeline_integrity import (
        _restorations_with_transition_order,
    )
    from warhammer40k_core.engine.unit_destroyed_hooks import (
        model_restoration_events_for_event_log_interval,
    )

    restorations = _restorations_with_transition_order(
        raw_restorations=model_restoration_events_for_event_log_interval(
            state=state,
            event_log=decisions.event_log,
            start_order_exclusive=-1,
            decision_records=decisions.records,
        )
    )
    deadline_rows = _validated_reserve_deadline_transition_rows(
        state=state,
        destructions=destructions,
        identities_by_id=identities_by_id,
        event_records=event_records,
        event_index_by_id=event_index_by_id,
        prior_transition_rows=(
            (
                (destroyed_source.event_order, 1),
                (f"primary-transition:{destroyed_departure.departure_id}:{destroyed_model_id}"),
                {
                    "game_id": state.game_id,
                    "model_instance_id": destroyed_model_id,
                    "target_unit_instance_id": unit.unit_instance_id,
                },
                destroyed_source.completion_key,
            ),
        ),
        restorations=restorations,
    )
    assert [row[2]["model_instance_id"] for row in deadline_rows].count(destroyed_model_id) == 1


def test_phase17k_datasheet_advance_charge_text_uses_generic_advance_eligibility() -> None:
    package = advance_charge_package()
    unit = advance_charge_unit(package=package)
    army = flesh_hounds_army(package=package, unit=unit)
    player_index = player_ability_index(package=package, army=army)
    records_by_name = {record.definition.name: record for record in player_index.all_records()}
    advance_charge_record = records_by_name["Bounding Advance"]
    replay_payload = advance_charge_record.definition.replay_payload
    assert isinstance(replay_payload, dict)
    rule_ir = RuleIR.from_payload(cast(RuleIRPayload, replay_payload["rule_ir"]))
    runtime = CatalogAdvanceEligibilityRuntime(
        ability_indexes_by_player_id={army.player_id: player_index},
        armies=(army,),
    )
    registry = AdvanceEligibilityHookRegistry.from_bindings(runtime.bindings())
    state = battle_state_with_army(
        army=army,
        battlefield=bloodcrushers_battlefield_state(army=army, unit=unit),
    )

    grants = registry.grants_for(
        AdvanceEligibilityContext(
            state=state,
            player_id=army.player_id,
            battle_round=state.battle_round,
            unit_instance_id=unit.unit_instance_id,
            movement_request_id="phase17k-advance-charge-request",
            movement_result_id="phase17k-advance-charge-result",
        )
    )

    assert advance_charge_record.definition.timing.trigger_kind is TimingTriggerKind.PASSIVE_QUERY
    assert rule_ir.is_supported
    assert catalog_rule_ir_consumers_for_rule(rule_ir) == (
        CATALOG_IR_CAN_ADVANCE_AND_CHARGE_CONSUMER_ID,
    )
    assert set(catalog_rule_ir_hook_ids_for_rule(rule_ir)) == {
        CATALOG_IR_CAN_ADVANCE_AND_CHARGE_CONSUMER_ID,
    }
    assert tuple(binding.hook_id for binding in registry.all_bindings()) == (
        CATALOG_IR_CAN_ADVANCE_AND_CHARGE_CONSUMER_ID,
    )
    assert len(grants) == 1
    assert grants[0].hook_id == CATALOG_IR_CAN_ADVANCE_AND_CHARGE_CONSUMER_ID
    assert grants[0].can_declare_charge is True
    assert grants[0].can_shoot is False
    assert grants[0].replay_payload == {
        "ability": "can_advance_and_charge",
        "ability_ids": [advance_charge_record.definition.ability_id],
        "catalog_record_ids": [advance_charge_record.record_id],
        "source_rule_ids": [advance_charge_record.definition.source_id],
    }


def test_phase17k_datasheet_fall_back_shoot_text_uses_generic_fall_back_eligibility() -> None:
    package = advance_charge_package()
    unit = advance_charge_unit(package=package)
    army = flesh_hounds_army(package=package, unit=unit)
    player_index = player_ability_index(package=package, army=army)
    records_by_name = {record.definition.name: record for record in player_index.all_records()}
    fall_back_shoot_record = records_by_name["Slip Away"]
    replay_payload = fall_back_shoot_record.definition.replay_payload
    assert isinstance(replay_payload, dict)
    rule_ir = RuleIR.from_payload(cast(RuleIRPayload, replay_payload["rule_ir"]))
    runtime = CatalogFallBackEligibilityRuntime(
        ability_indexes_by_player_id={army.player_id: player_index},
        armies=(army,),
    )
    registry = FallBackEligibilityHookRegistry.from_bindings(runtime.bindings())
    state = battle_state_with_army(
        army=army,
        battlefield=bloodcrushers_battlefield_state(army=army, unit=unit),
    )

    grants = registry.grants_for(
        FallBackEligibilityContext(
            state=state,
            player_id=army.player_id,
            battle_round=state.battle_round,
            unit_instance_id=unit.unit_instance_id,
            movement_request_id="phase17k-fall-back-shoot-request",
            movement_result_id="phase17k-fall-back-shoot-result",
        )
    )

    assert fall_back_shoot_record.definition.timing.trigger_kind is TimingTriggerKind.PASSIVE_QUERY
    assert rule_ir.is_supported
    assert catalog_rule_ir_consumers_for_rule(rule_ir) == (
        CATALOG_IR_CAN_FALLBACK_AND_SHOOT_CONSUMER_ID,
    )
    assert set(catalog_rule_ir_hook_ids_for_rule(rule_ir)) == {
        CATALOG_IR_CAN_FALLBACK_AND_SHOOT_CONSUMER_ID,
    }
    assert tuple(binding.hook_id for binding in registry.all_bindings()) == (
        CATALOG_IR_CAN_FALLBACK_AND_SHOOT_CONSUMER_ID,
    )
    assert len(grants) == 1
    assert grants[0].hook_id == CATALOG_IR_CAN_FALLBACK_AND_SHOOT_CONSUMER_ID
    assert grants[0].can_shoot is True
    assert grants[0].can_declare_charge is False
    assert grants[0].replay_payload == {
        "ability": "can_fall_back_and_shoot",
        "ability_ids": [fall_back_shoot_record.definition.ability_id],
        "catalog_record_ids": [fall_back_shoot_record.record_id],
        "source_rule_ids": [fall_back_shoot_record.definition.source_id],
    }


def test_phase17k_fall_back_shoot_runtime_uses_scoped_catalog_clause_record() -> None:
    package = split_fall_back_package()
    unit = advance_charge_unit(package=package)
    army = flesh_hounds_army(package=package, unit=unit)
    player_index = player_ability_index(package=package, army=army)
    split_records = tuple(
        record
        for record in player_index.all_records()
        if record.definition.name == "Split Slip Away"
    )
    unrelated_record = record_by_runtime_clause_suffix(split_records, suffix=":clause:001")
    fall_back_record = record_by_runtime_clause_suffix(split_records, suffix=":clause:002")
    runtime = CatalogFallBackEligibilityRuntime(
        ability_indexes_by_player_id={army.player_id: player_index},
        armies=(army,),
    )
    registry = FallBackEligibilityHookRegistry.from_bindings(runtime.bindings())
    state = battle_state_with_army(
        army=army,
        battlefield=bloodcrushers_battlefield_state(army=army, unit=unit),
    )

    grants = registry.grants_for(
        FallBackEligibilityContext(
            state=state,
            player_id=army.player_id,
            battle_round=state.battle_round,
            unit_instance_id=unit.unit_instance_id,
            movement_request_id="phase17k-split-fall-back-shoot-request",
            movement_result_id="phase17k-split-fall-back-shoot-result",
        )
    )

    assert len(split_records) == 2
    assert unrelated_record.definition.timing.trigger_kind is TimingTriggerKind.PASSIVE_QUERY
    assert fall_back_record.definition.timing.trigger_kind is TimingTriggerKind.PASSIVE_QUERY
    assert len(grants) == 1
    assert grants[0].hook_id == CATALOG_IR_CAN_FALLBACK_AND_SHOOT_CONSUMER_ID
    grant_payload = grants[0].replay_payload
    assert isinstance(grant_payload, dict)
    catalog_record_ids = grant_payload["catalog_record_ids"]
    assert isinstance(catalog_record_ids, list)
    assert catalog_record_ids == [fall_back_record.record_id]
    assert unrelated_record.record_id not in catalog_record_ids


def test_phase17k_leading_model_reroll_text_uses_generic_advance_charge_rerolls() -> None:
    package = advance_charge_package()
    unit = advance_charge_unit(package=package)
    army = flesh_hounds_army(package=package, unit=unit)
    player_index = player_ability_index(package=package, army=army)
    records_by_name = {record.definition.name: record for record in player_index.all_records()}
    reroll_record = records_by_name["Lead the Hunt"]
    replay_payload = reroll_record.definition.replay_payload
    assert isinstance(replay_payload, dict)
    rule_ir = RuleIR.from_payload(cast(RuleIRPayload, replay_payload["rule_ir"]))
    battlefield = bloodcrushers_battlefield_state(army=army, unit=unit)
    state = battle_state_with_army(army=army, battlefield=battlefield)
    current_model_ids = fixture_current_model_ids(battlefield=battlefield, unit=unit)
    advance_permission = catalog_advance_roll_reroll_permission_for_unit(
        ability_index=player_index,
        unit=unit,
        current_model_instance_ids=current_model_ids,
        player_id=army.player_id,
    )
    charge_permission = catalog_charge_roll_reroll_permission_for_unit(
        ability_index=player_index,
        unit=unit,
        current_model_instance_ids=current_model_ids,
        player_id=army.player_id,
    )
    advance_phase_permission = _advance_reroll_permission_for_unit(
        state=state,
        unit=unit,
        unit_instance_id=unit.unit_instance_id,
        player_id=army.player_id,
        keywords=unit.keywords,
        ability_index=player_index,
        current_model_instance_ids=current_model_ids,
    )
    charge_phase_permission = charge_reroll_permission_for_unit(
        state=state,
        player_id=army.player_id,
        unit_instance_id=unit.unit_instance_id,
        ability_index=player_index,
    )
    keyword_permission = _advance_reroll_permission_for_unit(
        state=state,
        unit=unit,
        unit_instance_id=unit.unit_instance_id,
        player_id=army.player_id,
        keywords=("ADVANCE_REROLL",),
        ability_index=AbilityCatalogIndex.from_records(()),
        current_model_instance_ids=(),
    )
    empty_index = AbilityCatalogIndex.from_records(())
    duplicate_index = AbilityCatalogIndex.from_records(
        (
            *player_index.all_records(),
            replace(reroll_record, record_id=f"{reroll_record.record_id}:duplicate"),
        )
    )

    assert reroll_record.definition.timing.trigger_kind is TimingTriggerKind.AFTER_DICE_ROLL
    assert rule_ir.is_supported
    assert catalog_rule_ir_consumers_for_rule(rule_ir) == (
        CATALOG_IR_ADVANCE_ROLL_REROLL_CONSUMER_ID,
        CATALOG_IR_CHARGE_ROLL_REROLL_CONSUMER_ID,
    )
    assert set(catalog_rule_ir_hook_ids_for_rule(rule_ir)) == {
        CATALOG_IR_ADVANCE_ROLL_REROLL_CONSUMER_ID,
        CATALOG_IR_CHARGE_ROLL_REROLL_CONSUMER_ID,
    }
    assert advance_permission is not None
    assert advance_permission.eligible_roll_type == "advance_roll"
    assert advance_permission.timing_window == "after_advance_roll"
    assert advance_permission.owning_player_id == army.player_id
    assert (
        advance_permission.component_selection_policy is RerollComponentSelectionPolicy.WHOLE_ROLL
    )
    assert charge_permission is not None
    assert charge_permission.eligible_roll_type == "charge_roll"
    assert charge_permission.timing_window == "after_charge_roll"
    assert charge_permission.owning_player_id == army.player_id
    assert charge_permission.component_selection_policy is RerollComponentSelectionPolicy.WHOLE_ROLL
    assert advance_phase_permission == advance_permission
    assert charge_phase_permission == charge_permission
    assert keyword_permission is not None
    assert keyword_permission.source_id == f"{unit.unit_instance_id}:advance-reroll"
    assert keyword_permission.eligible_roll_type == "advance_roll"
    assert (
        catalog_advance_roll_reroll_permission_for_unit(
            ability_index=empty_index,
            unit=unit,
            current_model_instance_ids=current_model_ids,
            player_id=army.player_id,
        )
        is None
    )
    with pytest.raises(GameLifecycleError, match="Multiple catalog roll reroll permissions"):
        catalog_advance_roll_reroll_permission_for_unit(
            ability_index=duplicate_index,
            unit=unit,
            current_model_instance_ids=current_model_ids,
            player_id=army.player_id,
        )
    with pytest.raises(GameLifecycleError, match="requires an ability record"):
        _catalog_roll_reroll_permission(
            record=cast(AbilityCatalogRecord, object()),
            clause=rule_ir.clauses[0],
            effect_index=0,
            player_id=army.player_id,
            roll_type="advance_roll",
            timing_window="after_advance_roll",
        )
    with pytest.raises(GameLifecycleError, match="requires a rule clause"):
        _catalog_roll_reroll_permission(
            record=reroll_record,
            clause=cast(RuleClause, object()),
            effect_index=0,
            player_id=army.player_id,
            roll_type="advance_roll",
            timing_window="after_advance_roll",
        )
    with pytest.raises(GameLifecycleError, match="effect_index must be non-negative"):
        _catalog_roll_reroll_permission(
            record=reroll_record,
            clause=rule_ir.clauses[0],
            effect_index=-1,
            player_id=army.player_id,
            roll_type="advance_roll",
            timing_window="after_advance_roll",
        )


def test_phase17k_this_model_reroll_text_uses_generic_advance_charge_rerolls() -> None:
    package = model_reroll_package()
    unit = advance_charge_unit(package=package)
    army = flesh_hounds_army(package=package, unit=unit)
    player_index = player_ability_index(package=package, army=army)
    records_by_name = {record.definition.name: record for record in player_index.all_records()}
    reroll_record = records_by_name["Swift Instincts"]
    replay_payload = reroll_record.definition.replay_payload
    assert isinstance(replay_payload, dict)
    rule_ir = RuleIR.from_payload(cast(RuleIRPayload, replay_payload["rule_ir"]))
    battlefield = bloodcrushers_battlefield_state(army=army, unit=unit)
    current_model_ids = fixture_current_model_ids(battlefield=battlefield, unit=unit)
    advance_permission = catalog_advance_roll_reroll_permission_for_unit(
        ability_index=player_index,
        unit=unit,
        current_model_instance_ids=current_model_ids,
        player_id=army.player_id,
    )
    charge_permission = catalog_charge_roll_reroll_permission_for_unit(
        ability_index=player_index,
        unit=unit,
        current_model_instance_ids=current_model_ids,
        player_id=army.player_id,
    )
    clause = rule_ir.clauses[0]

    assert reroll_record.definition.timing.trigger_kind is TimingTriggerKind.AFTER_DICE_ROLL
    assert rule_ir.is_supported
    assert clause.target is not None
    assert clause.target.kind is RuleTargetKind.THIS_MODEL
    assert catalog_rule_ir_consumers_for_rule(rule_ir) == (
        CATALOG_IR_ADVANCE_ROLL_REROLL_CONSUMER_ID,
        CATALOG_IR_CHARGE_ROLL_REROLL_CONSUMER_ID,
    )
    assert set(catalog_rule_ir_hook_ids_for_rule(rule_ir)) == {
        CATALOG_IR_ADVANCE_ROLL_REROLL_CONSUMER_ID,
        CATALOG_IR_CHARGE_ROLL_REROLL_CONSUMER_ID,
    }
    assert advance_permission is not None
    assert advance_permission.eligible_roll_type == "advance_roll"
    assert advance_permission.timing_window == "after_advance_roll"
    assert advance_permission.owning_player_id == army.player_id
    assert (
        advance_permission.component_selection_policy is RerollComponentSelectionPolicy.WHOLE_ROLL
    )
    assert charge_permission is not None
    assert charge_permission.eligible_roll_type == "charge_roll"
    assert charge_permission.timing_window == "after_charge_roll"
    assert charge_permission.owning_player_id == army.player_id
    assert charge_permission.component_selection_policy is RerollComponentSelectionPolicy.WHOLE_ROLL


def test_phase17k_model_reroll_runtime_uses_scoped_catalog_clause_record() -> None:
    package = split_model_reroll_package()
    unit = advance_charge_unit(package=package)
    army = flesh_hounds_army(package=package, unit=unit)
    player_index = player_ability_index(package=package, army=army)
    split_records = tuple(
        record
        for record in player_index.all_records()
        if record.definition.name == "Split Swift Instincts"
    )
    unrelated_record = record_by_runtime_clause_suffix(split_records, suffix=":clause:001")
    reroll_record = record_by_runtime_clause_suffix(split_records, suffix=":clause:002")
    battlefield = bloodcrushers_battlefield_state(army=army, unit=unit)
    current_model_ids = fixture_current_model_ids(battlefield=battlefield, unit=unit)

    advance_permission = catalog_advance_roll_reroll_permission_for_unit(
        ability_index=player_index,
        unit=unit,
        current_model_instance_ids=current_model_ids,
        player_id=army.player_id,
    )
    charge_permission = catalog_charge_roll_reroll_permission_for_unit(
        ability_index=player_index,
        unit=unit,
        current_model_instance_ids=current_model_ids,
        player_id=army.player_id,
    )

    assert len(split_records) == 2
    assert unrelated_record.definition.timing.trigger_kind is TimingTriggerKind.AFTER_DICE_ROLL
    assert reroll_record.definition.timing.trigger_kind is TimingTriggerKind.AFTER_DICE_ROLL
    assert advance_permission is not None
    assert advance_permission.eligible_roll_type == "advance_roll"
    assert advance_permission.source_id.startswith(f"{reroll_record.record_id}:")
    assert not advance_permission.source_id.startswith(f"{unrelated_record.record_id}:")
    assert charge_permission is not None
    assert charge_permission.eligible_roll_type == "charge_roll"
    assert charge_permission.source_id.startswith(f"{reroll_record.record_id}:")
    assert not charge_permission.source_id.startswith(f"{unrelated_record.record_id}:")


def test_phase17k_leading_model_weapon_keyword_text_modifies_scoped_weapon_profiles() -> None:
    package = advance_charge_package()
    unit = advance_charge_unit(package=package)
    bodyguard = advance_charge_unit(
        package=package,
        unit_selection_id="advance-charge-bodyguard-1",
    )
    attached_id = "attached-unit:army-daemons:advance-charge-test"
    formation = AttachedUnitFormation(
        attached_unit_instance_id=attached_id,
        bodyguard_unit_instance_id=bodyguard.unit_instance_id,
        leader_unit_instance_ids=(unit.unit_instance_id,),
        component_unit_instance_ids=tuple(
            sorted((bodyguard.unit_instance_id, unit.unit_instance_id))
        ),
        source_id="test:phase17k:leading-weapon-grant",
        attachment_source_ids=("test:phase17k:leading-weapon-grant:eligibility",),
    )
    army = replace(
        flesh_hounds_army(package=package, unit=unit),
        units=(unit, bodyguard),
        attached_units=(formation,),
    )
    player_index = player_ability_index(package=package, army=army)
    records_by_name = {record.definition.name: record for record in player_index.all_records()}
    weapon_grant_record = records_by_name["Pack Killers"]
    replay_payload = weapon_grant_record.definition.replay_payload
    assert isinstance(replay_payload, dict)
    rule_ir = RuleIR.from_payload(cast(RuleIRPayload, replay_payload["rule_ir"]))
    battlefield = bloodcrushers_battlefield_state(army=army, unit=unit)
    placed_army = battlefield.placed_armies[0]
    battlefield = replace(
        battlefield,
        placed_armies=(
            replace(
                placed_army,
                unit_placements=(
                    *placed_army.unit_placements,
                    single_model_unit_placement(army, bodyguard, x=14.0),
                ),
            ),
        ),
    )
    state = battle_state_with_army(army=army, battlefield=battlefield)
    current_model_ids = fixture_current_model_ids(battlefield=battlefield, unit=unit)
    swift_claws = next(
        wargear
        for wargear in package.army_catalog.wargear
        if wargear.wargear_id == "test-advance-charge-unit:swift-claws"
    )
    melee_profile = swift_claws.weapon_profiles[0]
    ranged_profile = replace(
        melee_profile,
        profile_id=f"{melee_profile.profile_id}:ranged-copy",
        range_profile=RangeProfile.distance(12),
    )
    grants = catalog_weapon_keyword_grants_for_unit(
        ability_index=player_index,
        unit=unit,
        current_model_instance_ids=current_model_ids,
    )
    bindings = catalog_weapon_profile_modifier_bindings(
        ability_indexes_by_player_id={army.player_id: player_index},
        armies=(army,),
    )
    registry = RuntimeModifierRegistry.from_bindings(
        weapon_profile_modifier_bindings=bindings,
    )
    attacker_model_id = unit.own_models[0].model_instance_id
    melee_context = WeaponProfileModifierContext(
        state=state,
        source_phase=BattlePhase.FIGHT,
        attacking_unit_instance_id=attached_id,
        attacker_model_instance_id=attacker_model_id,
        target_unit_instance_id=attached_id,
        weapon_profile=melee_profile,
    )
    ranged_context = replace(melee_context, weapon_profile=ranged_profile)
    modified_melee = registry.modified_weapon_profile(melee_context)
    modified_ranged = registry.modified_weapon_profile(ranged_context)

    assert weapon_grant_record.definition.timing.trigger_kind is TimingTriggerKind.PASSIVE_QUERY
    assert rule_ir.is_supported
    assert catalog_rule_ir_consumers_for_rule(rule_ir) == (
        CATALOG_IR_WEAPON_KEYWORD_GRANT_CONSUMER_ID,
        "catalog-ir:weapon-keyword-grant:lethal-hits",
    )
    assert set(catalog_rule_ir_hook_ids_for_rule(rule_ir)) == {
        CATALOG_IR_WEAPON_KEYWORD_GRANT_CONSUMER_ID,
        "catalog-ir:weapon-keyword-grant:lethal-hits",
    }
    assert tuple(binding.modifier_id for binding in bindings) == (
        CATALOG_IR_WEAPON_KEYWORD_GRANT_CONSUMER_ID,
    )
    assert len(grants) == 1
    assert grants[0].keyword is WeaponKeyword.LETHAL_HITS
    assert grants[0].weapon_scope == "melee"
    assert grants[0].ability is not None
    assert grants[0].ability.ability_kind is AbilityKind.LETHAL_HITS
    assert WeaponKeyword.LETHAL_HITS in modified_melee.keywords
    assert any(
        ability.ability_kind is AbilityKind.LETHAL_HITS for ability in modified_melee.abilities
    )
    assert grants[0].source_id in modified_melee.source_ids
    assert modified_ranged == ranged_profile
