from __future__ import annotations

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
    AttachedUnitFormation,
    RosterLegalityReport,
)
from warhammer40k_core.engine.battlefield_state import (
    BattlefieldRuntimeState,
    ModelPlacement,
    PlacedArmy,
    UnitPlacement,
)
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.faction_content.warhammer_40000_11th.grey_knights import (
    army_rule,
)
from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.list_validation import BattleSize, DetachmentSelection
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError, GameLifecycleStage
from warhammer40k_core.engine.reserves import ReserveKind, ReserveOrigin
from warhammer40k_core.engine.turn_end_hooks import (
    SELECT_FACTION_RULE_TURN_END_OPTION_DECISION_TYPE,
    TurnEndHookRegistry,
    TurnEndRequestContext,
    TurnEndResultContext,
)
from warhammer40k_core.engine.unit_factory import ModelInstance, UnitInstance
from warhammer40k_core.geometry.model_geometry import ModelGeometry
from warhammer40k_core.geometry.pose import Pose


def test_gate_of_infinity_runtime_contribution_registers_turn_end_hook() -> None:
    contribution = army_rule.runtime_contribution()

    assert contribution.contribution_id == army_rule.CONTRIBUTION_ID
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
