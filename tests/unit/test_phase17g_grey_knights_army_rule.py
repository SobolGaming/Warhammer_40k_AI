from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from typing import cast

import pytest

from warhammer40k_core.core.attributes import Characteristic, CharacteristicValue
from warhammer40k_core.core.datasheet import (
    BaseSizeDefinition,
    CatalogAbilitySourceKind,
    CatalogAbilitySupport,
    DatasheetAbilityDescriptor,
)
from warhammer40k_core.core.ruleset_descriptor import RulesetDescriptor
from warhammer40k_core.engine.army_mustering import (
    ArmyDefinition,
    RosterLegalityReport,
)
from warhammer40k_core.engine.attached_unit_formation import AttachedUnitFormation
from warhammer40k_core.engine.attached_unit_reconciliation import (
    split_attached_rules_unit_if_required,
)
from warhammer40k_core.engine.battlefield_state import (
    BattlefieldPlacementKind,
    BattlefieldRuntimeState,
    ModelPlacement,
    PlacedArmy,
    UnitPlacement,
)
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_request import (
    PARAMETERIZED_DECISION_OPTION_ID,
    DecisionRequest,
)
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.event_log import EventRecord, JsonValue, validate_json_value
from warhammer40k_core.engine.faction_content.warhammer_40000_11th.grey_knights import (
    army_rule,
)
from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.lifecycle import GameLifecycle
from warhammer40k_core.engine.list_validation import BattleSize, DetachmentSelection
from warhammer40k_core.engine.mission_setup import MissionSetup
from warhammer40k_core.engine.movement_proposals import (
    MovementProposalRequest,
    PlacementProposalPayload,
)
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError, GameLifecycleStage
from warhammer40k_core.engine.phases.movement import MovementPhaseHandler, MovementPhaseState
from warhammer40k_core.engine.primary_historical_events import (
    record_new_primary_turn_start_evidence_events,
)
from warhammer40k_core.engine.primary_reserve_entry_provider import (
    PrimaryReserveEntryProvider,
)
from warhammer40k_core.engine.primary_reserve_entry_source_integrity import (
    validate_primary_reserve_entry_source_requirements,
    validate_primary_reserve_entry_source_terminal_semantics,
)
from warhammer40k_core.engine.reserve_arrival_requirements import (
    reposition_destruction_policy,
)
from warhammer40k_core.engine.reserve_state_attached_split import (
    RESERVE_STATE_ATTACHED_SPLIT_EVENT,
)
from warhammer40k_core.engine.reserves import (
    LARGE_MODEL_STRATEGIC_RESERVE_RESTRICTIONS,
    ReserveKind,
    ReserveOrigin,
    ReserveState,
)
from warhammer40k_core.engine.rules_unit_placement import RulesUnitPlacement
from warhammer40k_core.engine.rules_units import rules_unit_identities_share_lineage
from warhammer40k_core.engine.stratagems_generic_metadata import (
    unit_arrived_from_reserves_this_turn,
)
from warhammer40k_core.engine.timing_windows import (
    TimingTriggerKind,
    TimingWindow,
    TimingWindowDescriptor,
)
from warhammer40k_core.engine.turn_end_hooks import (
    SELECT_FACTION_RULE_TURN_END_OPTION_DECISION_TYPE,
    TurnEndHookRegistry,
    TurnEndRequestContext,
    TurnEndResultContext,
)
from warhammer40k_core.engine.unit_factory import ModelInstance, UnitInstance
from warhammer40k_core.geometry.model_geometry import ModelGeometry
from warhammer40k_core.geometry.pose import Pose
from warhammer40k_core.rules.mission_pack_import import (
    warhammer_event_companion_2026_07_mission_pack,
)


def test_gate_of_infinity_runtime_contribution_registers_turn_end_hook() -> None:
    contribution = army_rule.runtime_contribution()

    assert contribution.contribution_id == army_rule.CONTRIBUTION_ID
    assert contribution.contribution_id == army_rule.HOOK_ID
    assert not contribution.contribution_id.endswith(":scaffold")
    assert len(contribution.turn_end_hook_bindings) == 1
    binding = contribution.turn_end_hook_bindings[0]
    assert binding.hook_id == army_rule.HOOK_ID
    assert binding.source_id == army_rule.SOURCE_RULE_ID
    assert binding.request_handler is army_rule.gate_of_infinity_turn_end_request
    assert binding.result_handler is army_rule.apply_gate_of_infinity_turn_end_result


@pytest.mark.parametrize(
    ("battle_size", "expected"),
    [
        (BattleSize.INCURSION, 2),
        (BattleSize.STRIKE_FORCE, 3),
        (BattleSize.ONSLAUGHT, 4),
    ],
)
def test_gate_of_infinity_battle_size_caps(
    battle_size: BattleSize,
    expected: int,
) -> None:
    assert army_rule.gate_of_infinity_max_units_for_battle_size(battle_size) == expected


def test_gate_of_infinity_choice_moves_unit_to_required_strategic_reserves() -> None:
    state = _grey_knights_state(
        battle_size=BattleSize.STRIKE_FORCE,
        grey_knights_units=(
            _unit("army-grey:terminators-1", "Brotherhood Terminators", has_gate=True),
            _unit("army-grey:terminators-2", "Brotherhood Terminators", has_gate=True),
        ),
        active_player_id="player-opponent",
        grey_xs=(12.0, 18.0),
        opponent_xs=(42.0,),
    )
    decisions = DecisionController()
    registry = TurnEndHookRegistry.from_bindings(
        army_rule.runtime_contribution().turn_end_hook_bindings
    )
    request = _decision_request(
        registry.next_request_for(
            TurnEndRequestContext(
                state=state,
                decisions=decisions,
                completed_phase=BattlePhase.FIGHT,
            )
        )
    )

    assert request.decision_type == SELECT_FACTION_RULE_TURN_END_OPTION_DECISION_TYPE
    assert request.actor_id == "player-grey"
    request_payload = cast(dict[str, JsonValue], request.payload)
    assert request_payload["source_rule_id"] == army_rule.SOURCE_RULE_ID
    assert request_payload["hook_id"] == army_rule.HOOK_ID
    assert request_payload["max_units"] == 3
    assert request_payload["eligible_rules_unit_instance_ids"] == [
        "army-grey:terminators-1",
        "army-grey:terminators-2",
    ]
    assert {option.option_id for option in request.options} == {
        "grey-knights:gate-of-infinity:army-grey:terminators-1:use",
        "grey-knights:gate-of-infinity:army-grey:terminators-2:use",
        "grey-knights:gate-of-infinity:complete",
    }

    result = DecisionResult.for_request(
        result_id="result-gate-of-infinity-use",
        request=request,
        selected_option_id="grey-knights:gate-of-infinity:army-grey:terminators-1:use",
    )
    decisions.request_decision(request)
    decisions.submit_result(result)
    assert (
        registry.apply_result(
            TurnEndResultContext(
                state=state,
                decisions=decisions,
                request=request,
                result=result,
            )
        )
        is True
    )

    reserve_state = state.reserve_state_for_unit("army-grey:terminators-1")
    assert reserve_state is not None
    assert reserve_state.reserve_kind is ReserveKind.STRATEGIC_RESERVES
    assert reserve_state.reserve_origin is ReserveOrigin.DURING_BATTLE_ABILITY
    assert reserve_state.source_rule_ids == (army_rule.SOURCE_RULE_ID,)
    assert reserve_state.required_arrival_battle_round == 2
    assert reserve_state.required_arrival_phase == BattlePhase.MOVEMENT.value
    assert reserve_state.required_arrival_source_rule_id == army_rule.SOURCE_RULE_ID
    assert reserve_state.arrival_is_required_at(battle_round=2, phase=BattlePhase.MOVEMENT)
    assert not reserve_state.arrival_is_eligible_at(
        battle_round=1,
        phase=BattlePhase.MOVEMENT,
    )
    assert state.battlefield_state is not None
    assert all(
        placement.unit_instance_id != "army-grey:terminators-1"
        for placed_army in state.battlefield_state.placed_armies
        for placement in placed_army.unit_placements
    )
    used_payload = _last_event_payload(decisions, army_rule.GATE_OF_INFINITY_USED_EVENT)
    validate_json_value(used_payload)
    assert used_payload["selected_count_after"] == 1
    assert used_payload["max_units"] == 3
    assert used_payload["component_unit_instance_ids"] == ["army-grey:terminators-1"]
    reserve_payloads = cast(list[dict[str, JsonValue]], used_payload["reserve_states"])
    assert reserve_payloads[0]["required_arrival_battle_round"] == 2

    next_request = _decision_request(
        registry.next_request_for(
            TurnEndRequestContext(
                state=state,
                decisions=decisions,
                completed_phase=BattlePhase.FIGHT,
            )
        )
    )
    assert {option.option_id for option in next_request.options} == {
        "grey-knights:gate-of-infinity:army-grey:terminators-2:use",
        "grey-knights:gate-of-infinity:complete",
    }


def test_gate_of_infinity_cap_blocks_additional_requests() -> None:
    state = _grey_knights_state(
        battle_size=BattleSize.INCURSION,
        grey_knights_units=(
            _unit("army-grey:terminators-1", "Brotherhood Terminators", has_gate=True),
            _unit("army-grey:terminators-2", "Brotherhood Terminators", has_gate=True),
            _unit("army-grey:terminators-3", "Brotherhood Terminators", has_gate=True),
        ),
        active_player_id="player-opponent",
        grey_xs=(12.0, 18.0, 24.0),
        opponent_xs=(42.0,),
    )
    decisions = DecisionController()

    first_request = _request_for(state=state, decisions=decisions)
    _apply_result(
        state=state,
        decisions=decisions,
        request=first_request,
        option_id="grey-knights:gate-of-infinity:army-grey:terminators-1:use",
        result_id="result-gate-of-infinity-first",
    )
    second_request = _request_for(state=state, decisions=decisions)
    _apply_result(
        state=state,
        decisions=decisions,
        request=second_request,
        option_id="grey-knights:gate-of-infinity:army-grey:terminators-2:use",
        result_id="result-gate-of-infinity-second",
    )

    assert (
        army_rule.gate_of_infinity_turn_end_request(
            TurnEndRequestContext(
                state=state,
                decisions=decisions,
                completed_phase=BattlePhase.FIGHT,
            )
        )
        is None
    )
    assert state.reserve_state_for_unit("army-grey:terminators-3") is None


def test_gate_of_infinity_completion_records_no_reserve_mutation() -> None:
    state = _grey_knights_state(
        battle_size=BattleSize.STRIKE_FORCE,
        grey_knights_units=(
            _unit("army-grey:terminators-1", "Brotherhood Terminators", has_gate=True),
        ),
        active_player_id="player-opponent",
        grey_xs=(12.0,),
        opponent_xs=(42.0,),
    )
    decisions = DecisionController()
    request = _request_for(state=state, decisions=decisions)

    _apply_result(
        state=state,
        decisions=decisions,
        request=request,
        option_id="grey-knights:gate-of-infinity:complete",
        result_id="result-gate-of-infinity-complete",
    )

    assert state.reserve_state_for_unit("army-grey:terminators-1") is None
    completed_payload = _last_event_payload(
        decisions,
        army_rule.GATE_OF_INFINITY_COMPLETED_EVENT,
    )
    assert completed_payload["use_ability"] is False
    assert (
        army_rule.gate_of_infinity_turn_end_request(
            TurnEndRequestContext(
                state=state,
                decisions=decisions,
                completed_phase=BattlePhase.FIGHT,
            )
        )
        is None
    )


def test_gate_of_infinity_excludes_engaged_or_missing_ability_units() -> None:
    state = _grey_knights_state(
        battle_size=BattleSize.STRIKE_FORCE,
        grey_knights_units=(
            _unit("army-grey:eligible", "Brotherhood Terminators", has_gate=True),
            _unit("army-grey:engaged", "Brotherhood Terminators", has_gate=True),
            _unit("army-grey:no-gate", "Strike Squad", has_gate=False),
        ),
        active_player_id="player-opponent",
        grey_xs=(12.0, 30.0, 36.0),
        opponent_xs=(31.0,),
    )
    decisions = DecisionController()

    request = _request_for(state=state, decisions=decisions)

    request_payload = cast(dict[str, JsonValue], request.payload)
    assert request_payload["eligible_rules_unit_instance_ids"] == ["army-grey:eligible"]
    assert {option.option_id for option in request.options} == {
        "grey-knights:gate-of-infinity:army-grey:eligible:use",
        "grey-knights:gate-of-infinity:complete",
    }


def test_gate_of_infinity_attached_rules_unit_requires_all_components_and_moves_all() -> None:
    bodyguard = _unit("army-grey:bodyguard", "Brotherhood Terminators", has_gate=True)
    leader = _unit("army-grey:leader", "Brotherhood Captain", has_gate=True)
    state = _grey_knights_state(
        battle_size=BattleSize.STRIKE_FORCE,
        grey_knights_units=(bodyguard, leader),
        active_player_id="player-opponent",
        grey_xs=(12.0, 15.0),
        opponent_xs=(42.0,),
        attached_units=(
            AttachedUnitFormation(
                attached_unit_instance_id="attached-unit:army-grey:terminator-command",
                bodyguard_unit_instance_id=bodyguard.unit_instance_id,
                leader_unit_instance_ids=(leader.unit_instance_id,),
                component_unit_instance_ids=tuple(
                    sorted((bodyguard.unit_instance_id, leader.unit_instance_id))
                ),
                source_id="phase17g:grey-knights:test-attached-unit",
                attachment_source_ids=("phase17g:grey-knights:test-attachment-eligibility",),
            ),
        ),
    )
    decisions = DecisionController()
    request = _request_for(state=state, decisions=decisions)

    assert {option.option_id for option in request.options} == {
        "grey-knights:gate-of-infinity:attached-unit:army-grey:terminator-command:use",
        "grey-knights:gate-of-infinity:complete",
    }
    _apply_result(
        state=state,
        decisions=decisions,
        request=request,
        option_id="grey-knights:gate-of-infinity:attached-unit:army-grey:terminator-command:use",
        result_id="result-gate-of-infinity-attached",
    )

    assert state.reserve_state_for_unit(bodyguard.unit_instance_id) is not None
    assert state.reserve_state_for_unit(leader.unit_instance_id) is not None
    assert state.battlefield_state is not None
    assert all(
        placement.unit_instance_id not in {bodyguard.unit_instance_id, leader.unit_instance_id}
        for placed_army in state.battlefield_state.placed_armies
        for placement in placed_army.unit_placements
    )
    used_payload = _last_event_payload(decisions, army_rule.GATE_OF_INFINITY_USED_EVENT)
    assert used_payload["target_rules_unit_instance_id"] == (
        "attached-unit:army-grey:terminator-command"
    )
    assert used_payload["component_unit_instance_ids"] == [
        "army-grey:bodyguard",
        "army-grey:leader",
    ]


def test_gate_of_infinity_attached_rules_unit_missing_ability_is_not_eligible() -> None:
    bodyguard = _unit("army-grey:bodyguard", "Brotherhood Terminators", has_gate=True)
    leader = _unit("army-grey:leader", "Brotherhood Captain", has_gate=False)
    state = _grey_knights_state(
        battle_size=BattleSize.STRIKE_FORCE,
        grey_knights_units=(bodyguard, leader),
        active_player_id="player-opponent",
        grey_xs=(12.0, 15.0),
        opponent_xs=(42.0,),
        attached_units=(
            AttachedUnitFormation(
                attached_unit_instance_id="attached-unit:army-grey:terminator-command",
                bodyguard_unit_instance_id=bodyguard.unit_instance_id,
                leader_unit_instance_ids=(leader.unit_instance_id,),
                component_unit_instance_ids=tuple(
                    sorted((bodyguard.unit_instance_id, leader.unit_instance_id))
                ),
                source_id="phase17g:grey-knights:test-attached-unit",
                attachment_source_ids=("phase17g:grey-knights:test-attachment-eligibility",),
            ),
        ),
    )
    decisions = DecisionController()

    assert (
        army_rule.gate_of_infinity_turn_end_request(
            TurnEndRequestContext(
                state=state,
                decisions=decisions,
                completed_phase=BattlePhase.FIGHT,
            )
        )
        is None
    )


def test_gate_of_infinity_arrival_survives_attached_split_and_replay() -> None:
    attached_id = "attached-unit:army-grey:terminator-command"
    bodyguard = _unit("army-grey:bodyguard", "Brotherhood Terminators", has_gate=True)
    leader = _unit("army-grey:leader", "Brotherhood Captain", has_gate=True)
    state = _grey_knights_state(
        battle_size=BattleSize.STRIKE_FORCE,
        grey_knights_units=(bodyguard, leader),
        active_player_id="player-opponent",
        grey_xs=(12.0, 15.0),
        opponent_xs=(42.0,),
        attached_units=(
            AttachedUnitFormation(
                attached_unit_instance_id=attached_id,
                bodyguard_unit_instance_id=bodyguard.unit_instance_id,
                leader_unit_instance_ids=(leader.unit_instance_id,),
                component_unit_instance_ids=tuple(
                    sorted((bodyguard.unit_instance_id, leader.unit_instance_id))
                ),
                source_id="phase17g:grey-knights:test-attached-unit",
                attachment_source_ids=("phase17g:grey-knights:test-attachment-eligibility",),
            ),
        ),
    )
    mission_setup = _mission_setup()
    state.mission_setup = mission_setup
    assert state.battlefield_state is not None
    state.battlefield_state = replace(
        state.battlefield_state,
        battlefield_width_inches=mission_setup.battlefield_width_inches,
        battlefield_depth_inches=mission_setup.battlefield_depth_inches,
        terrain_features=mission_setup.terrain_features,
    )
    decisions = DecisionController()
    request = _request_for(state=state, decisions=decisions)
    _apply_result(
        state=state,
        decisions=decisions,
        request=request,
        option_id=f"grey-knights:gate-of-infinity:{attached_id}:use",
        result_id="result-gate-of-infinity-attached-split",
    )
    _arrive_rules_unit_from_strategic_reserves(
        state=state,
        decisions=decisions,
        rules_unit_instance_id=attached_id,
        component_unit_placements=(
            UnitPlacement(
                army_id="army-grey",
                player_id="player-grey",
                unit_instance_id=bodyguard.unit_instance_id,
                model_placements=(
                    ModelPlacement(
                        army_id="army-grey",
                        player_id="player-grey",
                        unit_instance_id=bodyguard.unit_instance_id,
                        model_instance_id=bodyguard.own_models[0].model_instance_id,
                        pose=Pose.at(15.0, 0.75),
                    ),
                ),
            ),
            UnitPlacement(
                army_id="army-grey",
                player_id="player-grey",
                unit_instance_id=leader.unit_instance_id,
                model_placements=(
                    ModelPlacement(
                        army_id="army-grey",
                        player_id="player-grey",
                        unit_instance_id=leader.unit_instance_id,
                        model_instance_id=leader.own_models[0].model_instance_id,
                        pose=Pose.at(16.5, 0.75),
                    ),
                ),
            ),
        ),
        battle_round=2,
        result_id_prefix="gate-attached-arrival",
    )
    arrived_historical_state = state.reserve_state_for_unit(attached_id)
    assert arrived_historical_state is not None
    assert arrived_historical_state.status.value == "arrived"
    state.movement_phase_state = None
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.FIGHT)
    _destroy_test_unit_model(state=state, unit_instance_id=bodyguard.unit_instance_id)
    state.battlefield_state = state.battlefield_state.with_removed_models(
        (bodyguard.own_models[0].model_instance_id,)
    )

    assert split_attached_rules_unit_if_required(
        state=state,
        event_log=decisions.event_log,
        rules_unit_instance_id=attached_id,
    ) == (leader.unit_instance_id,)
    assert {reserve_state.unit_instance_id for reserve_state in state.reserve_states} == {
        bodyguard.unit_instance_id,
        leader.unit_instance_id,
    }
    destroyed_component_state = state.reserve_state_for_unit(bodyguard.unit_instance_id)
    assert destroyed_component_state is not None
    assert destroyed_component_state.status.value == "arrived"
    transferred_state = state.reserve_state_for_unit(leader.unit_instance_id)
    assert transferred_state is not None
    assert transferred_state.status.value == "arrived"
    assert transferred_state.arrived_battle_round == 2
    assert transferred_state.required_arrival_battle_round == 2
    assert transferred_state.required_arrival_source_rule_id == army_rule.SOURCE_RULE_ID
    assert unit_arrived_from_reserves_this_turn(
        state=state,
        unit_instance_id=leader.unit_instance_id,
    )
    assert not rules_unit_identities_share_lineage(
        state=state,
        first_unit_instance_id=bodyguard.unit_instance_id,
        second_unit_instance_id=leader.unit_instance_id,
    )

    baseline_payload = GameLifecycle(
        state=state,
        decision_controller=decisions,
    ).to_payload()
    restored = GameLifecycle.from_payload(deepcopy(baseline_payload))
    assert restored.to_payload() == baseline_payload
    assert restored.state is not None
    assert unit_arrived_from_reserves_this_turn(
        state=restored.state,
        unit_instance_id=leader.unit_instance_id,
    )

    source_terminal = next(
        event
        for event in decisions.event_log.records
        if event.event_type == army_rule.GATE_OF_INFINITY_USED_EVENT
    )
    source_payload = cast(dict[str, JsonValue], source_terminal.payload)
    binding = cast(list[dict[str, JsonValue]], source_payload["primary_reserve_entry_bindings"])[0]
    provider = PrimaryReserveEntryProvider.from_payload(binding["provider"])
    reserve_entry = cast(dict[str, JsonValue], binding["reserve_entry_state"])
    forged_source_terminal = EventRecord(
        event_id=source_terminal.event_id,
        event_type=source_terminal.event_type,
        payload={**source_payload, "active_player_id": "forged-unknown-player"},
    )
    accepted_gate_decision = decisions.records[0]
    forged_gate_decision = replace(
        accepted_gate_decision,
        request=replace(
            accepted_gate_decision.request,
            payload={
                **cast(dict[str, JsonValue], accepted_gate_decision.request.payload),
                "active_player_id": "forged-unknown-player",
            },
        ),
    )
    with pytest.raises(
        GameLifecycleError,
        match="Reserve-entry source terminal player identity drift",
    ):
        validate_primary_reserve_entry_source_terminal_semantics(
            state=state,
            provider=provider,
            decision=forged_gate_decision,
            reserve_entry=reserve_entry,
            source_terminal=forged_source_terminal,
            event_records=decisions.event_log.records,
        )
    with pytest.raises(
        GameLifecycleError,
        match="Reserve-entry arrival timing player identity drift",
    ):
        validate_primary_reserve_entry_source_requirements(
            state=state,
            provider=provider,
            reserve_entry=reserve_entry,
            source_terminal=forged_source_terminal,
        )

    missing_transfer_payload = deepcopy(baseline_payload)
    missing_transfer_payload["decisions"]["event_log"] = [
        event
        for event in missing_transfer_payload["decisions"]["event_log"]
        if event["event_type"] != RESERVE_STATE_ATTACHED_SPLIT_EVENT
    ]
    with pytest.raises(
        GameLifecycleError,
        match="Historical reserve identity requires an attached split transfer",
    ):
        GameLifecycle.from_payload(missing_transfer_payload)

    tampered_successor_payload = deepcopy(baseline_payload)
    transfer_event = next(
        event
        for event in tampered_successor_payload["decisions"]["event_log"]
        if event["event_type"] == RESERVE_STATE_ATTACHED_SPLIT_EVENT
    )
    successor_payload = cast(
        list[dict[str, JsonValue]],
        cast(dict[str, JsonValue], transfer_event["payload"])["successor_reserve_states"],
    )[0]
    successor_payload["required_arrival_source_rule_id"] = "forged-arrival-source"
    with pytest.raises(
        GameLifecycleError,
        match="Attached split reserve transfer identity drift",
    ):
        GameLifecycle.from_payload(tampered_successor_payload)

    omitted_successor_payload = deepcopy(baseline_payload)
    omitted_transfer_event = next(
        event
        for event in omitted_successor_payload["decisions"]["event_log"]
        if event["event_type"] == RESERVE_STATE_ATTACHED_SPLIT_EVENT
    )
    omitted_transfer_payload = cast(dict[str, JsonValue], omitted_transfer_event["payload"])
    omitted_transfer_payload["successor_reserve_states"] = cast(
        list[JsonValue], omitted_transfer_payload["successor_reserve_states"]
    )[:1]
    with pytest.raises(
        GameLifecycleError,
        match="Attached split reserve successor set drift",
    ):
        GameLifecycle.from_payload(omitted_successor_payload)

    persisted_successor_drift_payload = deepcopy(baseline_payload)
    persisted_state_payload = cast(dict[str, object], persisted_successor_drift_payload["state"])
    persisted_reserve_states = cast(
        list[dict[str, object]], persisted_state_payload["reserve_states"]
    )
    next(
        value
        for value in persisted_reserve_states
        if value["unit_instance_id"] == leader.unit_instance_id
    )["large_model_exception_used"] = True
    with pytest.raises(
        GameLifecycleError,
        match="Attached split ReserveState successor persistence drift",
    ):
        GameLifecycle.from_payload(persisted_successor_drift_payload)

    causal_timing_drift_payload = deepcopy(baseline_payload)
    causal_transfer_event = next(
        event
        for event in causal_timing_drift_payload["decisions"]["event_log"]
        if event["event_type"] == RESERVE_STATE_ATTACHED_SPLIT_EVENT
    )
    causal_transfer_payload = cast(dict[str, JsonValue], causal_transfer_event["payload"])
    causal_transfer_payload["battle_round"] = 1
    causal_transfer_payload["phase"] = BattlePhase.COMMAND.value
    with pytest.raises(
        GameLifecycleError,
        match="Attached split reserve transfer predates its source arrival",
    ):
        GameLifecycle.from_payload(causal_timing_drift_payload)

    _destroy_test_unit_model(state=state, unit_instance_id=leader.unit_instance_id)
    assert state.battlefield_state is not None
    state.battlefield_state = state.battlefield_state.with_removed_models(
        (leader.own_models[0].model_instance_id,)
    )
    later_death_lifecycle = GameLifecycle(
        state=state,
        decision_controller=decisions,
    )
    later_death_payload = later_death_lifecycle.to_payload()
    assert GameLifecycle.from_payload(deepcopy(later_death_payload)).to_payload() == (
        later_death_payload
    )


def test_prebattle_arrival_attached_split_requires_persisted_transfer() -> None:
    attached_id = "attached-unit:army-grey:prebattle-command"
    bodyguard = _unit("army-grey:prebattle-bodyguard", "Brotherhood Terminators", has_gate=True)
    leader = _unit("army-grey:prebattle-leader", "Brotherhood Captain", has_gate=True)
    state = _grey_knights_state(
        battle_size=BattleSize.STRIKE_FORCE,
        grey_knights_units=(bodyguard, leader),
        active_player_id="player-grey",
        grey_xs=(12.0, 15.0),
        opponent_xs=(42.0,),
        phase=BattlePhase.MOVEMENT,
        attached_units=(
            AttachedUnitFormation(
                attached_unit_instance_id=attached_id,
                bodyguard_unit_instance_id=bodyguard.unit_instance_id,
                leader_unit_instance_ids=(leader.unit_instance_id,),
                component_unit_instance_ids=tuple(
                    sorted((bodyguard.unit_instance_id, leader.unit_instance_id))
                ),
                source_id="phase17g:grey-knights:test-prebattle-attached-unit",
                attachment_source_ids=(
                    "phase17g:grey-knights:test-prebattle-attachment-eligibility",
                ),
            ),
        ),
    )
    mission_setup = _mission_setup()
    state.mission_setup = mission_setup
    assert state.battlefield_state is not None
    state.battlefield_state = replace(
        state.battlefield_state,
        battlefield_width_inches=mission_setup.battlefield_width_inches,
        battlefield_depth_inches=mission_setup.battlefield_depth_inches,
        terrain_features=mission_setup.terrain_features,
    )
    decisions = DecisionController()
    declared_state = ReserveState.declared_before_battle(
        player_id="player-grey",
        unit_instance_id=attached_id,
        reserve_kind=ReserveKind.STRATEGIC_RESERVES,
        points_contribution=200,
        destruction_deadline_policy=reposition_destruction_policy(
            mission_setup=state.mission_setup,
            destruction_deadline_policy=None,
        ),
    )
    arrived_state = declared_state.mark_arrived(
        battle_round=1,
        phase=BattlePhase.MOVEMENT,
        large_model_exception_used=True,
        post_arrival_restrictions=LARGE_MODEL_STRATEGIC_RESERVE_RESTRICTIONS,
    )
    state.record_reserve_state(arrived_state)
    decisions.event_log.append(
        "reserve_unit_declared",
        {
            "game_id": state.game_id,
            "player_id": "player-grey",
            "unit_instance_id": attached_id,
            "reserve_state": declared_state.to_payload(),
        },
    )
    _destroy_test_unit_model(state=state, unit_instance_id=bodyguard.unit_instance_id)
    assert state.battlefield_state is not None
    state.battlefield_state = state.battlefield_state.with_removed_models(
        (bodyguard.own_models[0].model_instance_id,)
    )
    assert split_attached_rules_unit_if_required(
        state=state,
        event_log=decisions.event_log,
        rules_unit_instance_id=attached_id,
    ) == (leader.unit_instance_id,)

    baseline_payload = GameLifecycle(
        state=state,
        decision_controller=decisions,
    ).to_payload()
    assert GameLifecycle.from_payload(deepcopy(baseline_payload)).to_payload() == baseline_payload

    deleted_transfer_payload = deepcopy(baseline_payload)
    deleted_transfer_payload["decisions"]["event_log"] = [
        event
        for event in deleted_transfer_payload["decisions"]["event_log"]
        if event["event_type"] != RESERVE_STATE_ATTACHED_SPLIT_EVENT
    ]
    cast(dict[str, object], deleted_transfer_payload["state"])["reserve_states"] = []
    with pytest.raises(
        GameLifecycleError,
        match="Split prebattle ARRIVED ReserveState requires its transfer event",
    ):
        GameLifecycle.from_payload(deleted_transfer_payload)

    turn_end_window_id = (
        f"timing-window:{state.game_id}:round-01:turn:{arrived_state.player_id}:end"
    )
    turn_end_window = TimingWindow(
        window_id=turn_end_window_id,
        descriptor=TimingWindowDescriptor(
            descriptor_id=f"{turn_end_window_id}:descriptor",
            trigger_kind=TimingTriggerKind.END_TURN,
            source_rule_id="core-rules:lifecycle-timing-windows",
            source_step="player_turn",
        ),
        game_id=state.game_id,
        battle_round=1,
        active_player_id=arrived_state.player_id,
    )
    premature_expiry_payload = deepcopy(baseline_payload)
    premature_state_payload = cast(dict[str, object], premature_expiry_payload["state"])
    for reserve_payload in cast(list[dict[str, object]], premature_state_payload["reserve_states"]):
        reserve_payload["post_arrival_restrictions"] = []
        reserve_payload["restriction_battle_round"] = None
    premature_events = premature_expiry_payload["decisions"]["event_log"]
    premature_events.append(
        {
            "event_id": f"event-{len(premature_events) + 1:06d}",
            "event_type": "timing_window_resolved",
            "payload": validate_json_value(
                {
                    "timing_window": turn_end_window.to_payload(),
                    "resolution_order": [],
                }
            ),
        }
    )
    with pytest.raises(
        GameLifecycleError,
        match="Attached split ReserveState successor persistence drift",
    ):
        GameLifecycle.from_payload(premature_expiry_payload)

    objective_state_ids_before = tuple(
        value.state_id for value in state.primary_objective_turn_start_states
    )
    snapshot_ids_before = tuple(
        value.snapshot_id for value in state.primary_rules_unit_turn_start_snapshots
    )
    for _phase in range(3):
        state.advance_to_next_battle_phase()
    assert state.current_battle_phase is BattlePhase.FIGHT
    decisions.event_log.append(
        "timing_window_resolved",
        {
            "timing_window": turn_end_window.to_payload(),
            "resolution_order": [],
        },
    )
    state.advance_to_next_battle_phase()
    record_new_primary_turn_start_evidence_events(
        state=state,
        event_log=decisions.event_log,
        objective_state_ids_before=objective_state_ids_before,
        snapshot_ids_before=snapshot_ids_before,
    )
    assert state.active_player_id == "player-opponent"
    assert all(
        not reserve_state.post_arrival_restrictions for reserve_state in state.reserve_states
    )
    expired_payload = GameLifecycle(
        state=state,
        decision_controller=decisions,
    ).to_payload()
    assert GameLifecycle.from_payload(deepcopy(expired_payload)).to_payload() == expired_payload


def test_gate_of_infinity_rejects_stale_component_drift_before_mutation() -> None:
    bodyguard = _unit("army-grey:bodyguard", "Brotherhood Terminators", has_gate=True)
    leader = _unit("army-grey:leader", "Brotherhood Captain", has_gate=True)
    replacement_leader = _unit(
        "army-grey:replacement-leader",
        "Brotherhood Librarian",
        has_gate=True,
    )
    state = _grey_knights_state(
        battle_size=BattleSize.STRIKE_FORCE,
        grey_knights_units=(bodyguard, leader, replacement_leader),
        active_player_id="player-opponent",
        grey_xs=(12.0, 15.0, 18.0),
        opponent_xs=(42.0,),
        attached_units=(
            AttachedUnitFormation(
                attached_unit_instance_id="attached-unit:army-grey:terminator-command",
                bodyguard_unit_instance_id=bodyguard.unit_instance_id,
                leader_unit_instance_ids=(leader.unit_instance_id,),
                component_unit_instance_ids=tuple(
                    sorted((bodyguard.unit_instance_id, leader.unit_instance_id))
                ),
                source_id="phase17g:grey-knights:test-attached-unit",
                attachment_source_ids=("phase17g:grey-knights:test-attachment-eligibility",),
            ),
        ),
    )
    decisions = DecisionController()
    request = _request_for(state=state, decisions=decisions)
    state.army_definitions = [
        replace(
            army,
            attached_units=(
                AttachedUnitFormation(
                    attached_unit_instance_id="attached-unit:army-grey:terminator-command",
                    bodyguard_unit_instance_id=bodyguard.unit_instance_id,
                    leader_unit_instance_ids=(replacement_leader.unit_instance_id,),
                    component_unit_instance_ids=tuple(
                        sorted(
                            (
                                bodyguard.unit_instance_id,
                                replacement_leader.unit_instance_id,
                            )
                        )
                    ),
                    source_id="phase17g:grey-knights:test-attached-unit",
                    attachment_source_ids=("phase17g:grey-knights:test-attachment-eligibility",),
                ),
            ),
        )
        if army.player_id == "player-grey"
        else army
        for army in state.army_definitions
    ]
    result = DecisionResult.for_request(
        result_id="result-gate-of-infinity-stale",
        request=request,
        selected_option_id="grey-knights:gate-of-infinity:attached-unit:army-grey:terminator-command:use",
    )

    with pytest.raises(GameLifecycleError, match="component drift"):
        army_rule.apply_gate_of_infinity_turn_end_result(
            TurnEndResultContext(
                state=state,
                decisions=decisions,
                request=request,
                result=result,
            )
        )
    assert state.reserve_state_for_unit(bodyguard.unit_instance_id) is None
    assert state.reserve_state_for_unit(leader.unit_instance_id) is None
    assert state.reserve_state_for_unit(replacement_leader.unit_instance_id) is None


def test_gate_of_infinity_does_not_prompt_outside_opponent_fight_phase() -> None:
    own_turn_state = _grey_knights_state(
        battle_size=BattleSize.STRIKE_FORCE,
        grey_knights_units=(
            _unit("army-grey:terminators-1", "Brotherhood Terminators", has_gate=True),
        ),
        active_player_id="player-grey",
        phase=BattlePhase.FIGHT,
        grey_xs=(12.0,),
        opponent_xs=(42.0,),
    )
    shooting_state = _grey_knights_state(
        battle_size=BattleSize.STRIKE_FORCE,
        grey_knights_units=(
            _unit("army-grey:terminators-1", "Brotherhood Terminators", has_gate=True),
        ),
        active_player_id="player-opponent",
        phase=BattlePhase.SHOOTING,
        grey_xs=(12.0,),
        opponent_xs=(42.0,),
    )
    decisions = DecisionController()

    assert (
        army_rule.gate_of_infinity_turn_end_request(
            TurnEndRequestContext(
                state=own_turn_state,
                decisions=decisions,
                completed_phase=BattlePhase.FIGHT,
            )
        )
        is None
    )
    assert (
        army_rule.gate_of_infinity_turn_end_request(
            TurnEndRequestContext(
                state=shooting_state,
                decisions=decisions,
                completed_phase=BattlePhase.SHOOTING,
            )
        )
        is None
    )


def _request_for(*, state: GameState, decisions: DecisionController) -> DecisionRequest:
    return _decision_request(
        army_rule.gate_of_infinity_turn_end_request(
            TurnEndRequestContext(
                state=state,
                decisions=decisions,
                completed_phase=BattlePhase.FIGHT,
            )
        )
    )


def _apply_result(
    *,
    state: GameState,
    decisions: DecisionController,
    request: DecisionRequest,
    option_id: str,
    result_id: str,
) -> None:
    result = DecisionResult.for_request(
        result_id=result_id,
        request=request,
        selected_option_id=option_id,
    )
    decisions.request_decision(request)
    decisions.submit_result(result)
    handled = army_rule.apply_gate_of_infinity_turn_end_result(
        TurnEndResultContext(
            state=state,
            decisions=decisions,
            request=request,
            result=result,
        )
    )
    assert handled is True


def _grey_knights_state(
    *,
    battle_size: BattleSize,
    grey_knights_units: tuple[UnitInstance, ...],
    active_player_id: str,
    grey_xs: tuple[float, ...],
    opponent_xs: tuple[float, ...],
    phase: BattlePhase = BattlePhase.FIGHT,
    attached_units: tuple[AttachedUnitFormation, ...] = (),
) -> GameState:
    enemy_units = tuple(
        _unit(f"army-opponent:enemy-{index + 1}", "Enemy Unit", has_gate=False)
        for index in range(len(opponent_xs))
    )
    descriptor = RulesetDescriptor.warhammer_40000_eleventh()
    battle_phase_sequence = tuple(descriptor.battle_phase_sequence.phases)
    grey_army = _army(
        army_id="army-grey",
        player_id="player-grey",
        faction_id=army_rule.GREY_KNIGHTS_FACTION_ID,
        battle_size=battle_size,
        units=grey_knights_units,
        attached_units=attached_units,
    )
    enemy_army = _army(
        army_id="army-opponent",
        player_id="player-opponent",
        faction_id="adeptus-astartes",
        battle_size=battle_size,
        units=enemy_units,
    )
    state = GameState(
        game_id="phase17g-grey-knights-game",
        ruleset_descriptor_hash=descriptor.descriptor_hash,
        stage=GameLifecycleStage.BATTLE,
        setup_sequence=tuple(descriptor.setup_sequence.steps),
        battle_phase_sequence=battle_phase_sequence,
        player_ids=("player-grey", "player-opponent"),
        turn_order=("player-grey", "player-opponent"),
        tactical_secondary_draw_count=2,
        setup_step_index=None,
        battle_phase_index=battle_phase_sequence.index(phase),
        battle_round=1,
        active_player_id=active_player_id,
    )
    state.record_army_definition(grey_army)
    state.record_army_definition(enemy_army)
    state.battlefield_state = BattlefieldRuntimeState(
        battlefield_id="phase17g-grey-knights-battlefield",
        battlefield_width_inches=60.0,
        battlefield_depth_inches=44.0,
        placed_armies=(
            _placed_army(army=grey_army, units=grey_knights_units, xs=grey_xs, y=12.0),
            _placed_army(army=enemy_army, units=enemy_units, xs=opponent_xs, y=12.0),
        ),
    )
    return state


def _army(
    *,
    army_id: str,
    player_id: str,
    faction_id: str,
    battle_size: BattleSize,
    units: tuple[UnitInstance, ...],
    attached_units: tuple[AttachedUnitFormation, ...] = (),
) -> ArmyDefinition:
    ruleset_id = _ruleset_descriptor().ruleset_id
    return ArmyDefinition(
        army_id=army_id,
        player_id=player_id,
        catalog_id=f"{army_id}-catalog",
        source_package_id="phase17g-grey-knights-test-package",
        ruleset_id=ruleset_id,
        detachment_selection=DetachmentSelection(
            faction_id=faction_id,
            detachment_ids=("phase17g-test-detachment",),
        ),
        force_disposition_id="purge-the-foe",
        units=units,
        attached_units=attached_units,
        roster_legality_report=RosterLegalityReport(battle_size=battle_size),
        battle_size=battle_size,
    )


def _unit(unit_instance_id: str, name: str, *, has_gate: bool) -> UnitInstance:
    datasheet_id = f"{unit_instance_id}:datasheet"
    model = _model(
        model_instance_id=f"{unit_instance_id}:model-1",
        datasheet_id=datasheet_id,
        model_profile_id=f"{unit_instance_id}:profile",
        name=f"{name} model",
    )
    return UnitInstance(
        unit_instance_id=unit_instance_id,
        datasheet_id=datasheet_id,
        name=name,
        keywords=("INFANTRY",),
        faction_keywords=("GREY KNIGHTS",) if has_gate else ("ADEPTUS ASTARTES",),
        datasheet_abilities=(_gate_of_infinity_ability(),) if has_gate else (),
        datasheet_source_ids=(f"source:{datasheet_id}",),
        own_models=(model,),
        wargear_selections=(),
    )


def _model(
    *,
    model_instance_id: str,
    datasheet_id: str,
    model_profile_id: str,
    name: str,
) -> ModelInstance:
    base_size = BaseSizeDefinition.circular(32.0)
    return ModelInstance(
        model_instance_id=model_instance_id,
        datasheet_id=datasheet_id,
        model_profile_id=model_profile_id,
        name=name,
        characteristics=(
            CharacteristicValue.from_raw(Characteristic.WOUNDS, 2),
            CharacteristicValue.from_raw(Characteristic.SAVE, 2),
            CharacteristicValue.from_raw(Characteristic.OBJECTIVE_CONTROL, 1),
        ),
        base_size=base_size,
        geometry=ModelGeometry.from_base_size(
            base_size,
            keywords=("INFANTRY",),
            geometry_source_id=model_profile_id,
        ),
        starting_wounds=2,
        wounds_remaining=2,
        wargear_ids=(),
        source_ids=(f"source:{model_profile_id}",),
    )


def _gate_of_infinity_ability() -> DatasheetAbilityDescriptor:
    return DatasheetAbilityDescriptor(
        ability_id=army_rule.GATE_OF_INFINITY_ABILITY_ID,
        name=army_rule.GATE_OF_INFINITY_ABILITY_NAME,
        source_id=army_rule.SOURCE_RULE_ID,
        support=CatalogAbilitySupport.DESCRIPTOR_ONLY,
        source_kind=CatalogAbilitySourceKind.DATASHEET,
        effect_description="Select this unit for Gate of Infinity.",
        timing_tags=("end_turn",),
        parameter_tokens=("strategic_reserves",),
    )


def _placed_army(
    *,
    army: ArmyDefinition,
    units: tuple[UnitInstance, ...],
    xs: tuple[float, ...],
    y: float,
) -> PlacedArmy:
    if len(units) != len(xs):
        raise AssertionError("test fixture units and positions must match")
    return PlacedArmy(
        army_id=army.army_id,
        player_id=army.player_id,
        unit_placements=tuple(
            _unit_placement(army=army, unit=unit, x=x, y=y)
            for unit, x in zip(units, xs, strict=True)
        ),
    )


def _unit_placement(
    *,
    army: ArmyDefinition,
    unit: UnitInstance,
    x: float,
    y: float,
) -> UnitPlacement:
    return UnitPlacement(
        army_id=army.army_id,
        player_id=army.player_id,
        unit_instance_id=unit.unit_instance_id,
        model_placements=(
            ModelPlacement(
                army_id=army.army_id,
                player_id=army.player_id,
                unit_instance_id=unit.unit_instance_id,
                model_instance_id=unit.own_models[0].model_instance_id,
                pose=Pose.at(x=x, y=y, facing_degrees=0.0),
            ),
        ),
    )


def _ruleset_descriptor() -> RulesetDescriptor:
    return RulesetDescriptor.warhammer_40000_eleventh()


def _mission_setup() -> MissionSetup:
    return MissionSetup.from_mission_pack(
        mission_pack=warhammer_event_companion_2026_07_mission_pack(),
        mission_pool_entry_id="mission-purge-the-foe-vs-purge-the-foe-layout-1",
        terrain_layout_id="purge-the-foe-vs-purge-the-foe-layout-1",
        attacker_player_id="player-grey",
        attacker_force_disposition_id="purge-the-foe",
        defender_player_id="player-opponent",
        defender_force_disposition_id="purge-the-foe",
    )


def _destroy_test_unit_model(*, state: GameState, unit_instance_id: str) -> None:
    state.army_definitions = [
        replace(
            army,
            units=tuple(
                replace(
                    unit,
                    own_models=tuple(
                        replace(model, wounds_remaining=0) for model in unit.own_models
                    ),
                )
                if unit.unit_instance_id == unit_instance_id
                else unit
                for unit in army.units
            ),
        )
        if any(unit.unit_instance_id == unit_instance_id for unit in army.units)
        else army
        for army in state.army_definitions
    ]


def _arrive_rules_unit_from_strategic_reserves(
    *,
    state: GameState,
    decisions: DecisionController,
    rules_unit_instance_id: str,
    component_unit_placements: tuple[UnitPlacement, ...],
    battle_round: int,
    result_id_prefix: str,
) -> None:
    state.battle_round = battle_round
    state.active_player_id = "player-grey"
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.MOVEMENT)
    state.movement_phase_state = MovementPhaseState(
        battle_round=battle_round,
        active_player_id="player-grey",
    )
    handler = MovementPhaseHandler(ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh())
    selection_status = handler.begin_phase(state=state, decisions=decisions)
    assert selection_status is not None
    assert selection_status.decision_request is not None
    selection_request = selection_status.decision_request
    selection_result = DecisionResult.for_request(
        result_id=f"{result_id_prefix}-select",
        request=selection_request,
        selected_option_id=rules_unit_instance_id,
    )
    decisions.submit_result(selection_result)
    placement_status = handler.apply_decision(
        state=state,
        decisions=decisions,
        result=selection_result,
    )
    assert placement_status is not None
    assert placement_status.decision_request is not None
    placement_request = placement_status.decision_request
    proposal_request = MovementProposalRequest.from_decision_request_payload(
        placement_request.payload
    )
    placement_result = DecisionResult(
        result_id=f"{result_id_prefix}-place",
        request_id=placement_request.request_id,
        decision_type=placement_request.decision_type,
        actor_id=placement_request.actor_id,
        selected_option_id=PARAMETERIZED_DECISION_OPTION_ID,
        payload=validate_json_value(
            PlacementProposalPayload(
                proposal_request_id=proposal_request.request_id,
                proposal_kind=proposal_request.proposal_kind,
                unit_instance_id=rules_unit_instance_id,
                placement_kind=BattlefieldPlacementKind.STRATEGIC_RESERVES,
                attempted_rules_unit_placement=RulesUnitPlacement(
                    rules_unit_instance_id=rules_unit_instance_id,
                    component_unit_placements=component_unit_placements,
                ),
            ).to_payload()
        ),
    )
    assert (
        handler.invalid_proposal_submission_status(
            state=state,
            request=placement_request,
            result=placement_result,
            decisions=decisions,
        )
        is None
    )
    decisions.submit_result(placement_result)
    assert (
        handler.apply_decision(
            state=state,
            decisions=decisions,
            result=placement_result,
        )
        is None
    )
    assert any(
        event.event_type == "reinforcement_unit_arrived"
        and cast(dict[str, JsonValue], event.payload).get("unit_instance_id")
        == rules_unit_instance_id
        for event in decisions.event_log.records
    )


def _decision_request(request: DecisionRequest | None) -> DecisionRequest:
    if request is None:
        raise AssertionError("Expected Gate of Infinity request.")
    return request


def _last_event_payload(
    decisions: DecisionController,
    event_type: str,
) -> dict[str, JsonValue]:
    for record in reversed(decisions.event_log.records):
        if record.event_type == event_type:
            return cast(dict[str, JsonValue], record.payload)
    raise AssertionError(f"Missing event {event_type}.")
