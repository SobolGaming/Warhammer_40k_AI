from __future__ import annotations

import json
from dataclasses import replace
from typing import cast

import pytest

from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.core.ruleset_descriptor import (
    MovementMode,
    RulesetDescriptor,
    TerrainFeatureKind,
)
from warhammer40k_core.core.wargear import Wargear
from warhammer40k_core.core.weapon_profiles import WeaponKeyword, WeaponProfile
from warhammer40k_core.engine.army_mustering import ArmyMusterRequest, muster_army
from warhammer40k_core.engine.battlefield_state import (
    BattlefieldPlacementKind,
    BattlefieldRemovalKind,
    BattlefieldScenario,
    ModelPlacement,
    UnitPlacement,
)
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.dice import DiceRollManager
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.lifecycle import GameLifecycle, GameLifecyclePayload
from warhammer40k_core.engine.list_validation import (
    DetachmentSelection,
    ModelProfileSelection,
    UnitMusterSelection,
)
from warhammer40k_core.engine.movement_proposals import (
    MOVEMENT_PROPOSAL_DECISION_TYPE,
    PLACEMENT_PROPOSAL_DECISION_TYPE,
    MovementProposalPayload,
    MovementProposalRequest,
    PlacementProposalPayload,
)
from warhammer40k_core.engine.phase import (
    BattlePhase,
    GameLifecycleError,
    GameLifecycleStage,
    LifecycleStatus,
    LifecycleStatusKind,
)
from warhammer40k_core.engine.phases.movement import (
    COMPLETE_DISEMBARKS_OPTION_ID,
    DECLINE_EMBARK_OPTION_ID,
    SELECT_DISEMBARK_UNIT_DECISION_TYPE,
    SELECT_EMBARK_TRANSPORT_DECISION_TYPE,
    SELECT_MOVEMENT_ACTION_DECISION_TYPE,
    SELECT_MOVEMENT_UNIT_DECISION_TYPE,
    AdvancedUnitState,
    AdvanceRollRequest,
    AdvanceRollResult,
    FallBackModeKind,
    FellBackUnitState,
    MovementDiceRecord,
    MovementPhaseActionKind,
    MovementPhaseHandler,
    MovementPhaseState,
    MovementUnitSelection,
)
from warhammer40k_core.engine.placement import create_deterministic_battlefield_scenario
from warhammer40k_core.engine.reserves import ReserveKind, ReserveState
from warhammer40k_core.engine.transports import (
    DestroyedTransportDisembark,
    DisembarkedUnitState,
    DisembarkModeKind,
    DisembarkResolution,
    DisembarkSelection,
    EmbarkResolution,
    EmbarkSelection,
    FiringDeckResolution,
    FiringDeckSelection,
    FiringDeckWeaponSelection,
    TransportCapacityProfile,
    TransportCargoState,
    TransportMovementStatus,
    TransportOperationViolation,
    TransportOperationViolationCode,
    TransportRestrictionOverride,
    TransportRestrictionOverrideKind,
    apply_destroyed_transport_disembark_to_battlefield,
    apply_disembark_to_battlefield,
    apply_embark_to_battlefield,
    disembark_mode_kind_from_token,
    resolve_destroyed_transport_disembark,
    resolve_disembark,
    resolve_embark,
    resolve_firing_deck_selection,
    transport_movement_status_from_token,
    transport_operation_violation_code_from_token,
    transport_restriction_override_kind_from_token,
)
from warhammer40k_core.engine.unit_factory import UnitInstance
from warhammer40k_core.geometry.pathing import PathWitness
from warhammer40k_core.geometry.pose import Pose
from warhammer40k_core.geometry.terrain import (
    TerrainFeatureDefinition,
    TerrainFloorDefinition,
    TerrainWallDefinition,
)


def test_embark_removes_unit_to_transport_cargo_and_emits_records() -> None:
    scenario, passenger, transport, _enemy, _catalog = _transport_scenario()
    passenger_placement = scenario.battlefield_state.unit_placement_by_id(
        passenger.unit_instance_id
    )
    transport_placement = scenario.battlefield_state.unit_placement_by_id(
        transport.unit_instance_id
    )
    cargo_state = _cargo_state(transport=transport)

    resolution = resolve_embark(
        scenario=scenario,
        cargo_state=cargo_state,
        selection=EmbarkSelection(
            player_id="player-a",
            battle_round=1,
            unit_instance_id=passenger.unit_instance_id,
            transport_unit_instance_id=transport.unit_instance_id,
            movement_phase_action=TransportMovementStatus.NORMAL_MOVE,
        ),
        unit_placement=passenger_placement,
        transport_placement=transport_placement,
    )

    assert resolution.is_valid
    assert resolution.updated_cargo_state is not None
    assert resolution.updated_cargo_state.embarked_unit_instance_ids == (
        passenger.unit_instance_id,
    )
    assert resolution.transition_batch is not None
    assert {record.removal_kind for record in resolution.transition_batch.removals} == {
        BattlefieldRemovalKind.EMBARK
    }
    assert {record.destination_id for record in resolution.transition_batch.removals} == {
        transport.unit_instance_id
    }

    updated_battlefield = apply_embark_to_battlefield(
        battlefield_state=scenario.battlefield_state,
        embark=resolution,
    )
    assert passenger.unit_instance_id not in {
        placement.unit_instance_id
        for army in updated_battlefield.placed_armies
        for placement in army.unit_placements
    }


def test_embarked_units_are_unavailable_for_movement_selection() -> None:
    scenario, passenger, transport, _enemy, _catalog = _transport_scenario()
    cargo_state = _cargo_state(
        transport=transport,
        embarked_unit_ids=(passenger.unit_instance_id,),
        battle_round=1,
    )
    state = _battle_state(scenario)
    state.battlefield_state = scenario.battlefield_state.without_unit_placement(
        passenger.unit_instance_id
    )
    state.record_transport_cargo_state(cargo_state)
    state.movement_phase_state = MovementPhaseState(
        battle_round=1,
        active_player_id="player-a",
    )
    decisions = DecisionController()

    status = MovementPhaseHandler(ruleset_descriptor=_ruleset()).begin_phase(
        state=state,
        decisions=decisions,
    )

    assert status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    assert status.decision_request is not None
    assert status.decision_request.decision_type == SELECT_MOVEMENT_UNIT_DECISION_TYPE
    assert {option.option_id for option in status.decision_request.options} == {
        transport.unit_instance_id
    }
    assert passenger.unit_instance_id not in state.movement_phase_state.legal_unit_ids(
        BattlefieldScenario(
            armies=tuple(state.army_definitions),
            battlefield_state=state.battlefield_state,
        ),
        accounted_unplaced_model_ids=state.unavailable_model_ids(),
    )


def test_lifecycle_replay_accepts_embarked_models_accounted_by_transport_cargo_state() -> None:
    scenario, passenger, transport, _enemy, _catalog = _transport_scenario()
    state = _battle_state(scenario)
    assert state.battlefield_state is not None
    state.battlefield_state = state.battlefield_state.without_unit_placement(
        passenger.unit_instance_id
    )
    state.record_transport_cargo_state(
        _cargo_state(
            transport=transport,
            embarked_unit_ids=(passenger.unit_instance_id,),
        )
    )
    payload: GameLifecyclePayload = {
        "config": None,
        "parameterized_movement_proposals": True,
        "state": state.to_payload(),
        "decisions": DecisionController().to_payload(),
        "reaction_queue": {"frames": []},
    }

    lifecycle = GameLifecycle.from_payload(payload)

    assert lifecycle.state is not None
    assert lifecycle.state.embarked_model_ids() == tuple(
        model.model_instance_id for model in passenger.own_models
    )


def test_normal_move_ending_near_transport_emits_embark_decision() -> None:
    scenario, passenger, transport, _enemy, _catalog = _embark_ready_scenario()
    state = _battle_state(scenario)
    state.record_transport_cargo_state(_cargo_state(transport=transport))
    handler, decisions, action_request = _movement_action_request_for_unit(
        state=state,
        unit_instance_id=passenger.unit_instance_id,
    )

    status = _submit_action_and_movement_payload(
        handler,
        state=state,
        decisions=decisions,
        request=action_request,
        option_id=MovementPhaseActionKind.NORMAL_MOVE.value,
        unit=passenger,
        movement_phase_action=MovementPhaseActionKind.NORMAL_MOVE,
        movement_mode=MovementMode.NORMAL,
        dx=6.0,
        result_id="phase10q-normal-move",
    )

    request = _decision_request(status)
    assert request.decision_type == SELECT_EMBARK_TRANSPORT_DECISION_TYPE
    assert {option.option_id for option in request.options} == {
        DECLINE_EMBARK_OPTION_ID,
        transport.unit_instance_id,
    }


def test_lifecycle_embark_selection_updates_battlefield_and_cargo_atomically() -> None:
    scenario, passenger, transport, _enemy, _catalog = _embark_ready_scenario()
    state = _battle_state(scenario)
    state.record_transport_cargo_state(_cargo_state(transport=transport))
    handler, decisions, action_request = _movement_action_request_for_unit(
        state=state,
        unit_instance_id=passenger.unit_instance_id,
    )
    embark_request = _decision_request(
        _submit_action_and_movement_payload(
            handler,
            state=state,
            decisions=decisions,
            request=action_request,
            option_id=MovementPhaseActionKind.NORMAL_MOVE.value,
            unit=passenger,
            movement_phase_action=MovementPhaseActionKind.NORMAL_MOVE,
            movement_mode=MovementMode.NORMAL,
            dx=6.0,
            result_id="phase10q-normal-move",
        )
    )

    result = _submit_handler_decision(
        handler,
        state=state,
        decisions=decisions,
        request=embark_request,
        option_id=transport.unit_instance_id,
        result_id="phase10q-embark",
    )

    assert result is None
    assert state.battlefield_state is not None
    assert passenger.unit_instance_id not in _placed_unit_ids(state)
    stored_cargo = state.transport_cargo_state_for_transport(transport.unit_instance_id)
    assert stored_cargo is not None
    assert stored_cargo.embarked_unit_instance_ids == (passenger.unit_instance_id,)
    assert state.movement_phase_state is not None
    assert state.movement_phase_state.moved_unit_ids == (passenger.unit_instance_id,)

    payload: GameLifecyclePayload = {
        "config": None,
        "parameterized_movement_proposals": True,
        "state": state.to_payload(),
        "decisions": decisions.to_payload(),
        "reaction_queue": {"frames": []},
    }
    lifecycle = GameLifecycle.from_payload(payload)
    assert lifecycle.state is not None
    assert lifecycle.state.to_payload() == state.to_payload()


def test_lifecycle_advance_then_embark_replay_preserves_advanced_state() -> None:
    scenario, passenger, transport, _enemy, _catalog = _advance_embark_ready_scenario()
    state = _battle_state(scenario, game_id="phase10q-advance-embark-newer-0002")
    state.record_transport_cargo_state(_cargo_state(transport=transport))
    handler, decisions, action_request = _movement_action_request_for_unit(
        state=state,
        unit_instance_id=passenger.unit_instance_id,
    )

    embark_request = _decision_request(
        _submit_action_and_movement_payload(
            handler,
            state=state,
            decisions=decisions,
            request=action_request,
            option_id=MovementPhaseActionKind.ADVANCE.value,
            unit=passenger,
            movement_phase_action=MovementPhaseActionKind.ADVANCE,
            movement_mode=MovementMode.ADVANCE,
            dx=7.0,
            result_id="phase10q-advance",
        )
    )
    assert embark_request.decision_type == SELECT_EMBARK_TRANSPORT_DECISION_TYPE
    result = _submit_handler_decision(
        handler,
        state=state,
        decisions=decisions,
        request=embark_request,
        option_id=transport.unit_instance_id,
        result_id="phase10q-advance-embark",
    )

    assert result is None
    assert passenger.unit_instance_id not in _placed_unit_ids(state)
    assert (
        state.advanced_unit_state_for_unit(
            player_id="player-a",
            battle_round=1,
            unit_instance_id=passenger.unit_instance_id,
        )
        is not None
    )
    payload: GameLifecyclePayload = {
        "config": None,
        "parameterized_movement_proposals": True,
        "state": state.to_payload(),
        "decisions": decisions.to_payload(),
        "reaction_queue": {"frames": []},
    }
    lifecycle = GameLifecycle.from_payload(payload)
    assert lifecycle.state is not None
    assert lifecycle.state.to_payload() == state.to_payload()


def test_lifecycle_fall_back_then_embark_replay_preserves_fell_back_state() -> None:
    scenario, passenger, transport, _enemy, _catalog = _fall_back_embark_ready_scenario()
    state = _battle_state(scenario)
    state.record_transport_cargo_state(_cargo_state(transport=transport))
    handler, decisions, action_request = _movement_action_request_for_unit(
        state=state,
        unit_instance_id=passenger.unit_instance_id,
    )
    fall_back_option_id = (
        f"{MovementPhaseActionKind.FALL_BACK.value}:{FallBackModeKind.ORDERED_RETREAT.value}"
    )
    assert fall_back_option_id in {option.option_id for option in action_request.options}

    embark_request = _decision_request(
        _submit_action_and_movement_payload(
            handler,
            state=state,
            decisions=decisions,
            request=action_request,
            option_id=fall_back_option_id,
            unit=passenger,
            movement_phase_action=MovementPhaseActionKind.FALL_BACK,
            movement_mode=MovementMode.FALL_BACK,
            fall_back_mode=FallBackModeKind.ORDERED_RETREAT,
            dy=6.0,
            result_id="phase10q-fall-back",
        )
    )
    assert embark_request.decision_type == SELECT_EMBARK_TRANSPORT_DECISION_TYPE
    result = _submit_handler_decision(
        handler,
        state=state,
        decisions=decisions,
        request=embark_request,
        option_id=transport.unit_instance_id,
        result_id="phase10q-fall-back-embark",
    )

    assert result is None
    assert passenger.unit_instance_id not in _placed_unit_ids(state)
    assert (
        state.fell_back_unit_state_for_unit(
            player_id="player-a",
            battle_round=1,
            unit_instance_id=passenger.unit_instance_id,
        )
        is not None
    )
    payload: GameLifecyclePayload = {
        "config": None,
        "parameterized_movement_proposals": True,
        "state": state.to_payload(),
        "decisions": decisions.to_payload(),
        "reaction_queue": {"frames": []},
    }
    lifecycle = GameLifecycle.from_payload(payload)
    assert lifecycle.state is not None
    assert lifecycle.state.to_payload() == state.to_payload()


def test_lifecycle_embark_decline_leaves_unit_placed_and_completes_activation() -> None:
    scenario, passenger, transport, _enemy, _catalog = _embark_ready_scenario()
    state = _battle_state(scenario)
    state.record_transport_cargo_state(_cargo_state(transport=transport))
    handler, decisions, action_request = _movement_action_request_for_unit(
        state=state,
        unit_instance_id=passenger.unit_instance_id,
    )
    embark_request = _decision_request(
        _submit_action_and_movement_payload(
            handler,
            state=state,
            decisions=decisions,
            request=action_request,
            option_id=MovementPhaseActionKind.NORMAL_MOVE.value,
            unit=passenger,
            movement_phase_action=MovementPhaseActionKind.NORMAL_MOVE,
            movement_mode=MovementMode.NORMAL,
            dx=6.0,
            result_id="phase10q-normal-move",
        )
    )

    result = _submit_handler_decision(
        handler,
        state=state,
        decisions=decisions,
        request=embark_request,
        option_id=DECLINE_EMBARK_OPTION_ID,
        result_id="phase10q-decline-embark",
    )

    assert result is None
    assert passenger.unit_instance_id in _placed_unit_ids(state)
    stored_cargo = state.transport_cargo_state_for_transport(transport.unit_instance_id)
    assert stored_cargo is not None
    assert stored_cargo.embarked_unit_instance_ids == ()
    assert state.movement_phase_state is not None
    assert state.movement_phase_state.active_selection is None
    assert state.movement_phase_state.moved_unit_ids == (passenger.unit_instance_id,)


def test_invalid_lifecycle_embark_returns_invalid_without_embark_mutation() -> None:
    scenario, passenger, transport, _enemy, _catalog = _embark_ready_scenario()
    state = _battle_state(scenario)
    state.record_transport_cargo_state(_cargo_state(transport=transport))
    handler, decisions, action_request = _movement_action_request_for_unit(
        state=state,
        unit_instance_id=passenger.unit_instance_id,
    )
    embark_request = _decision_request(
        _submit_action_and_movement_payload(
            handler,
            state=state,
            decisions=decisions,
            request=action_request,
            option_id=MovementPhaseActionKind.NORMAL_MOVE.value,
            unit=passenger,
            movement_phase_action=MovementPhaseActionKind.NORMAL_MOVE,
            movement_mode=MovementMode.NORMAL,
            dx=6.0,
            result_id="phase10q-normal-move",
        )
    )
    state.replace_transport_cargo_state(
        replace(
            _cargo_state(transport=transport, battle_round=1),
            capacity_profile=TransportCapacityProfile(
                transport_datasheet_id=transport.datasheet_id,
                max_model_count=1,
                allowed_keywords=("INFANTRY",),
            ),
        )
    )
    before_battlefield = state.battlefield_state
    before_cargo = state.transport_cargo_state_for_transport(transport.unit_instance_id)

    status = _submit_handler_decision(
        handler,
        state=state,
        decisions=decisions,
        request=embark_request,
        option_id=transport.unit_instance_id,
        result_id="phase10q-invalid-embark",
    )

    assert status is not None
    assert status.status_kind is LifecycleStatusKind.INVALID
    assert state.battlefield_state == before_battlefield
    assert state.transport_cargo_state_for_transport(transport.unit_instance_id) == before_cargo
    assert passenger.unit_instance_id in _placed_unit_ids(state)


def test_started_embarked_unit_disembarks_through_movement_decision_lifecycle() -> None:
    scenario, passenger, transport, _enemy, _catalog = _transport_scenario()
    state = _battle_state(scenario)
    assert state.battlefield_state is not None
    state.battlefield_state = state.battlefield_state.without_unit_placement(
        passenger.unit_instance_id
    )
    state.record_transport_cargo_state(
        _cargo_state(
            transport=transport,
            embarked_unit_ids=(passenger.unit_instance_id,),
            started_unit_ids=(passenger.unit_instance_id,),
            battle_round=1,
        )
    )
    state.movement_phase_state = MovementPhaseState(
        battle_round=1,
        active_player_id="player-a",
    )
    handler = MovementPhaseHandler(ruleset_descriptor=_ruleset())
    decisions = DecisionController()

    disembark_request = _decision_request(handler.begin_phase(state=state, decisions=decisions))
    assert disembark_request.decision_type == SELECT_DISEMBARK_UNIT_DECISION_TYPE
    disembark_payload = cast(dict[str, object], disembark_request.payload)
    assert disembark_payload["disembark_mode"] == DisembarkModeKind.TACTICAL_DISEMBARK.value
    selected_payload = cast(
        dict[str, object],
        disembark_request.option_by_id(passenger.unit_instance_id).payload,
    )
    assert selected_payload["disembark_mode"] == DisembarkModeKind.TACTICAL_DISEMBARK.value
    placement_request = _decision_request(
        _submit_handler_decision(
            handler,
            state=state,
            decisions=decisions,
            request=disembark_request,
            option_id=passenger.unit_instance_id,
            result_id="phase10q-select-disembark",
        )
    )
    assert placement_request.decision_type == PLACEMENT_PROPOSAL_DECISION_TYPE

    status = _submit_disembark_placement_payload(
        handler,
        state=state,
        decisions=decisions,
        request=placement_request,
        passenger=passenger,
        transport=transport,
        disembark_mode=DisembarkModeKind.TACTICAL_DISEMBARK,
        transport_movement_status=TransportMovementStatus.NOT_MOVED,
        result_id="phase10q-place-disembark",
    )

    assert status is None
    assert passenger.unit_instance_id in _placed_unit_ids(state)
    stored_cargo = state.transport_cargo_state_for_transport(transport.unit_instance_id)
    assert stored_cargo is not None
    assert stored_cargo.embarked_unit_instance_ids == ()
    assert stored_cargo.disembarked_this_phase_unit_instance_ids == (passenger.unit_instance_id,)
    disembarked_state = state.disembarked_unit_state_for_unit(
        player_id="player-a",
        battle_round=1,
        unit_instance_id=passenger.unit_instance_id,
    )
    assert disembarked_state is not None
    assert disembarked_state.disembark_mode is DisembarkModeKind.TACTICAL_DISEMBARK

    movement_request = _decision_request(handler.begin_phase(state=state, decisions=decisions))
    selection_status = _submit_handler_decision(
        handler,
        state=state,
        decisions=decisions,
        request=movement_request,
        option_id=passenger.unit_instance_id,
        result_id="phase10q-select-disembarked-move",
    )
    assert selection_status is None
    action_request = _decision_request(handler.begin_phase(state=state, decisions=decisions))
    assert MovementPhaseActionKind.REMAIN_STATIONARY.value not in {
        option.option_id for option in action_request.options
    }

    payload: GameLifecyclePayload = {
        "config": None,
        "parameterized_movement_proposals": True,
        "state": state.to_payload(),
        "decisions": decisions.to_payload(),
        "reaction_queue": {"frames": []},
    }
    lifecycle = GameLifecycle.from_payload(payload)
    assert lifecycle.state is not None
    assert lifecycle.state.to_payload() == state.to_payload()


def test_transport_normal_move_emits_post_move_disembark_decision_after_pre_move_decline() -> None:
    scenario, passenger, transport, _enemy, _catalog = _transport_scenario()
    state = _battle_state(scenario)
    assert state.battlefield_state is not None
    state.battlefield_state = state.battlefield_state.without_unit_placement(
        passenger.unit_instance_id
    )
    state.record_transport_cargo_state(
        _cargo_state(
            transport=transport,
            embarked_unit_ids=(passenger.unit_instance_id,),
            started_unit_ids=(passenger.unit_instance_id,),
            battle_round=1,
        )
    )

    handler, decisions, post_move_disembark_request = (
        _rapid_disembark_request_after_transport_normal_move(
            state=state,
            passenger=passenger,
            transport=transport,
        )
    )

    assert handler is not None
    assert decisions is not None
    assert post_move_disembark_request.decision_type == SELECT_DISEMBARK_UNIT_DECISION_TYPE
    post_move_payload = cast(dict[str, object], post_move_disembark_request.payload)
    assert post_move_payload["transport_movement_status"] == (
        TransportMovementStatus.NORMAL_MOVE.value
    )
    assert post_move_payload["disembark_mode"] == DisembarkModeKind.RAPID_DISEMBARK.value
    assert post_move_payload["transport_unit_instance_id"] == transport.unit_instance_id
    assert {option.option_id for option in post_move_disembark_request.options} == {
        COMPLETE_DISEMBARKS_OPTION_ID,
        passenger.unit_instance_id,
    }
    assert state.movement_phase_state is not None
    assert state.movement_phase_state.declined_disembark_unit_ids == (passenger.unit_instance_id,)
    assert state.movement_phase_state.declined_post_normal_move_disembark_unit_ids == ()
    assert state.movement_phase_state.moved_unit_ids == (transport.unit_instance_id,)


def test_post_transport_normal_move_disembark_lifecycle_records_restrictions_and_replay() -> None:
    scenario, passenger, transport, _enemy, _catalog = _transport_scenario()
    state = _battle_state(scenario)
    assert state.battlefield_state is not None
    state.battlefield_state = state.battlefield_state.without_unit_placement(
        passenger.unit_instance_id
    )
    state.record_transport_cargo_state(
        _cargo_state(
            transport=transport,
            embarked_unit_ids=(passenger.unit_instance_id,),
            started_unit_ids=(passenger.unit_instance_id,),
            battle_round=1,
        )
    )
    handler, decisions, post_move_disembark_request = (
        _rapid_disembark_request_after_transport_normal_move(
            state=state,
            passenger=passenger,
            transport=transport,
        )
    )
    placement_request = _decision_request(
        _submit_handler_decision(
            handler,
            state=state,
            decisions=decisions,
            request=post_move_disembark_request,
            option_id=passenger.unit_instance_id,
            result_id="phase10q-select-post-normal-disembark",
        )
    )
    assert placement_request.decision_type == PLACEMENT_PROPOSAL_DECISION_TYPE

    status = _submit_disembark_placement_payload(
        handler,
        state=state,
        decisions=decisions,
        request=placement_request,
        passenger=passenger,
        transport=transport,
        disembark_mode=DisembarkModeKind.RAPID_DISEMBARK,
        transport_movement_status=TransportMovementStatus.NORMAL_MOVE,
        result_id="phase10q-place-post-normal-disembark",
    )

    assert status is None
    assert passenger.unit_instance_id in _placed_unit_ids(state)
    stored_cargo = state.transport_cargo_state_for_transport(transport.unit_instance_id)
    assert stored_cargo is not None
    assert stored_cargo.embarked_unit_instance_ids == ()
    assert stored_cargo.disembarked_this_phase_unit_instance_ids == (passenger.unit_instance_id,)
    disembarked_state = state.disembarked_unit_state_for_unit(
        player_id="player-a",
        battle_round=1,
        unit_instance_id=passenger.unit_instance_id,
    )
    assert disembarked_state is not None
    assert disembarked_state.disembark_mode is DisembarkModeKind.RAPID_DISEMBARK
    assert not disembarked_state.can_move_further
    assert not disembarked_state.can_declare_charge
    assert state.movement_phase_state is not None
    assert state.movement_phase_state.selected_unit_ids == (
        transport.unit_instance_id,
        passenger.unit_instance_id,
    )
    assert state.movement_phase_state.moved_unit_ids == (
        transport.unit_instance_id,
        passenger.unit_instance_id,
    )
    scenario_after = BattlefieldScenario(
        armies=tuple(state.army_definitions),
        battlefield_state=state.battlefield_state,
    )
    assert passenger.unit_instance_id not in state.movement_phase_state.legal_unit_ids(
        scenario_after,
        accounted_unplaced_model_ids=state.unavailable_model_ids(),
    )

    payload: GameLifecyclePayload = {
        "config": None,
        "parameterized_movement_proposals": True,
        "state": state.to_payload(),
        "decisions": decisions.to_payload(),
        "reaction_queue": {"frames": []},
    }
    lifecycle = GameLifecycle.from_payload(payload)
    assert lifecycle.state is not None
    assert lifecycle.state.to_payload() == state.to_payload()


def test_replay_rejects_transport_cargo_when_transport_is_not_placed() -> None:
    scenario, passenger, transport, _enemy, _catalog = _transport_scenario()
    state = _battle_state(scenario)
    assert state.battlefield_state is not None
    state.battlefield_state = state.battlefield_state.without_unit_placement(
        passenger.unit_instance_id
    ).without_unit_placement(transport.unit_instance_id)
    state.record_transport_cargo_state(
        _cargo_state(
            transport=transport,
            embarked_unit_ids=(passenger.unit_instance_id,),
            started_unit_ids=(passenger.unit_instance_id,),
            battle_round=1,
        )
    )
    payload: GameLifecyclePayload = {
        "config": None,
        "parameterized_movement_proposals": True,
        "state": state.to_payload(),
        "decisions": DecisionController().to_payload(),
        "reaction_queue": {"frames": []},
    }

    with pytest.raises(GameLifecycleError, match="transport unit must be placed"):
        GameLifecycle.from_payload(payload)


def test_replay_rejects_transport_cargo_when_transport_model_is_removed() -> None:
    scenario, passenger, transport, _enemy, _catalog = _transport_scenario()
    state = _battle_state(scenario)
    transport_model_id = transport.own_models[0].model_instance_id
    assert state.battlefield_state is not None
    state.battlefield_state = state.battlefield_state.without_unit_placement(
        passenger.unit_instance_id
    ).with_removed_models((transport_model_id,))
    state.record_transport_cargo_state(
        _cargo_state(
            transport=transport,
            embarked_unit_ids=(passenger.unit_instance_id,),
            started_unit_ids=(passenger.unit_instance_id,),
            battle_round=1,
        )
    )
    payload: GameLifecyclePayload = {
        "config": None,
        "parameterized_movement_proposals": True,
        "state": state.to_payload(),
        "decisions": DecisionController().to_payload(),
        "reaction_queue": {"frames": []},
    }

    with pytest.raises(GameLifecycleError, match="transport unit must be placed"):
        GameLifecycle.from_payload(payload)


def test_replay_rejects_advanced_state_for_unplaced_unremoved_unembarked_unit() -> None:
    scenario, passenger, _transport, _enemy, _catalog = _transport_scenario()
    state = _battle_state(scenario)
    assert state.battlefield_state is not None
    state.battlefield_state = state.battlefield_state.without_unit_placement(
        passenger.unit_instance_id
    )
    state.record_reserve_state(
        ReserveState.declared_before_battle(
            player_id="player-a",
            unit_instance_id=passenger.unit_instance_id,
            reserve_kind=ReserveKind.RESERVES,
        )
    )
    state.record_advanced_unit_state(_advanced_unit_state(passenger.unit_instance_id))
    payload: GameLifecyclePayload = {
        "config": None,
        "parameterized_movement_proposals": True,
        "state": state.to_payload(),
        "decisions": DecisionController().to_payload(),
        "reaction_queue": {"frames": []},
    }

    with pytest.raises(GameLifecycleError, match="advanced_unit_states unit"):
        GameLifecycle.from_payload(payload)


def test_replay_rejects_fell_back_state_for_unplaced_unremoved_unembarked_unit() -> None:
    scenario, passenger, _transport, _enemy, _catalog = _transport_scenario()
    state = _battle_state(scenario)
    assert state.battlefield_state is not None
    state.battlefield_state = state.battlefield_state.without_unit_placement(
        passenger.unit_instance_id
    )
    state.record_reserve_state(
        ReserveState.declared_before_battle(
            player_id="player-a",
            unit_instance_id=passenger.unit_instance_id,
            reserve_kind=ReserveKind.RESERVES,
        )
    )
    state.record_fell_back_unit_state(
        FellBackUnitState(
            player_id="player-a",
            battle_round=1,
            unit_instance_id=passenger.unit_instance_id,
        )
    )
    payload: GameLifecyclePayload = {
        "config": None,
        "parameterized_movement_proposals": True,
        "state": state.to_payload(),
        "decisions": DecisionController().to_payload(),
        "reaction_queue": {"frames": []},
    }

    with pytest.raises(GameLifecycleError, match="fell_back_unit_states unit"):
        GameLifecycle.from_payload(payload)


def test_disembark_places_unit_and_applies_after_normal_move_restrictions() -> None:
    scenario, passenger, transport, _enemy, _catalog = _transport_scenario()
    disembark_scenario = _without_unit(scenario, passenger.unit_instance_id)
    cargo_state = _cargo_state(
        transport=transport,
        embarked_unit_ids=(passenger.unit_instance_id,),
        started_unit_ids=(passenger.unit_instance_id,),
        battle_round=1,
    )
    attempted_placement = _unit_placement_at(
        passenger,
        army_id="army-alpha",
        player_id="player-a",
        poses=_disembark_poses(),
    )

    resolution = resolve_disembark(
        scenario=disembark_scenario,
        ruleset_descriptor=_ruleset(),
        cargo_state=cargo_state,
        selection=DisembarkSelection(
            player_id="player-a",
            battle_round=1,
            unit_instance_id=passenger.unit_instance_id,
            transport_unit_instance_id=transport.unit_instance_id,
            attempted_placement=attempted_placement,
            disembark_mode=DisembarkModeKind.RAPID_DISEMBARK,
            transport_movement_status=TransportMovementStatus.NORMAL_MOVE,
        ),
        unit=passenger,
        transport_placement=disembark_scenario.battlefield_state.unit_placement_by_id(
            transport.unit_instance_id
        ),
    )

    assert resolution.is_valid
    assert resolution.disembarked_unit_state is not None
    assert resolution.disembarked_unit_state.disembark_mode is (DisembarkModeKind.RAPID_DISEMBARK)
    assert not resolution.disembarked_unit_state.can_move_further
    assert not resolution.disembarked_unit_state.can_declare_charge
    assert resolution.transition_batch is not None
    assert {record.placement_kind for record in resolution.transition_batch.placements} == {
        BattlefieldPlacementKind.DISEMBARK
    }

    updated_battlefield = apply_disembark_to_battlefield(
        battlefield_state=disembark_scenario.battlefield_state,
        disembark=resolution,
    )
    assert updated_battlefield.unit_placement_by_id(passenger.unit_instance_id)


def test_disembark_endpoint_honors_terrain_top_restrictions() -> None:
    scenario, passenger, transport, _enemy, _catalog = _transport_scenario()
    disembark_scenario = _without_unit(scenario, passenger.unit_instance_id)
    attempted_placement = _unit_placement_at(
        passenger,
        army_id="army-alpha",
        player_id="player-a",
        poses=_disembark_poses(z_inches=1.0),
    )

    result = resolve_disembark(
        scenario=disembark_scenario,
        ruleset_descriptor=_ruleset(),
        cargo_state=_cargo_state(
            transport=transport,
            embarked_unit_ids=(passenger.unit_instance_id,),
            started_unit_ids=(passenger.unit_instance_id,),
            battle_round=1,
        ),
        selection=DisembarkSelection(
            player_id="player-a",
            battle_round=1,
            unit_instance_id=passenger.unit_instance_id,
            transport_unit_instance_id=transport.unit_instance_id,
            attempted_placement=attempted_placement,
            disembark_mode=DisembarkModeKind.TACTICAL_DISEMBARK,
            transport_movement_status=TransportMovementStatus.NOT_MOVED,
        ),
        unit=passenger,
        transport_placement=disembark_scenario.battlefield_state.unit_placement_by_id(
            transport.unit_instance_id
        ),
        terrain_features=(
            _support_feature(
                feature_id="phase10q-barricade",
                feature_kind=TerrainFeatureKind.BARRICADE_AND_FUEL_PIPES,
                center_x_inches=13.5,
                center_y_inches=10.5,
                z_inches=1.0,
                width_inches=6.0,
                depth_inches=5.0,
            ),
        ),
    )

    assert not result.is_valid
    assert TransportOperationViolationCode.TERRAIN_ENDPOINT_ILLEGAL in {
        violation.violation_code for violation in result.violations
    }
    with pytest.raises(GameLifecycleError, match="Invalid DisembarkResolution"):
        apply_disembark_to_battlefield(
            battlefield_state=disembark_scenario.battlefield_state,
            disembark=result,
        )


def test_disembark_ruins_upper_floor_requires_full_base_support() -> None:
    scenario, passenger, transport, _enemy, _catalog = _transport_scenario(
        passenger_datasheet_id="core-character-leader",
        passenger_model_profile_id="core-character-leader",
        passenger_model_count=1,
        passenger_unit_selection_id="character-passenger",
    )
    disembark_scenario = _without_unit(scenario, passenger.unit_instance_id)
    attempted_placement = _unit_placement_at(
        passenger,
        army_id="army-alpha",
        player_id="player-a",
        poses=(Pose.at(13.5, 10.0, 3.0),),
    )

    result = resolve_disembark(
        scenario=disembark_scenario,
        ruleset_descriptor=_ruleset(),
        cargo_state=_cargo_state(
            transport=transport,
            embarked_unit_ids=(passenger.unit_instance_id,),
            started_unit_ids=(passenger.unit_instance_id,),
            battle_round=1,
        ),
        selection=DisembarkSelection(
            player_id="player-a",
            battle_round=1,
            unit_instance_id=passenger.unit_instance_id,
            transport_unit_instance_id=transport.unit_instance_id,
            attempted_placement=attempted_placement,
            disembark_mode=DisembarkModeKind.TACTICAL_DISEMBARK,
            transport_movement_status=TransportMovementStatus.NOT_MOVED,
        ),
        unit=passenger,
        transport_placement=disembark_scenario.battlefield_state.unit_placement_by_id(
            transport.unit_instance_id
        ),
        terrain_features=(
            _ruins_floor_feature(
                feature_id="phase10q-ruins",
                center_x_inches=13.5,
                center_y_inches=10.0,
                upper_width_inches=0.75,
                upper_depth_inches=0.75,
            ),
        ),
    )

    assert not result.is_valid
    assert TransportOperationViolationCode.TERRAIN_ENDPOINT_ILLEGAL in {
        violation.violation_code for violation in result.violations
    }


def test_disembark_mode_status_pairs_are_fail_fast_and_round_trip() -> None:
    scenario, passenger, transport, _enemy, _catalog = _transport_scenario()
    disembark_scenario = _without_unit(scenario, passenger.unit_instance_id)
    cargo_state = _cargo_state(
        transport=transport,
        embarked_unit_ids=(passenger.unit_instance_id,),
        started_unit_ids=(passenger.unit_instance_id,),
        battle_round=1,
    )
    attempted_placement = _unit_placement_at(
        passenger,
        army_id="army-alpha",
        player_id="player-a",
        poses=_disembark_poses(),
    )

    tactical_selection = DisembarkSelection(
        player_id="player-a",
        battle_round=1,
        unit_instance_id=passenger.unit_instance_id,
        transport_unit_instance_id=transport.unit_instance_id,
        attempted_placement=attempted_placement,
        disembark_mode=DisembarkModeKind.TACTICAL_DISEMBARK,
        transport_movement_status=TransportMovementStatus.NOT_MOVED,
    )
    rapid_normal_selection = DisembarkSelection(
        player_id="player-a",
        battle_round=1,
        unit_instance_id=passenger.unit_instance_id,
        transport_unit_instance_id=transport.unit_instance_id,
        attempted_placement=attempted_placement,
        disembark_mode=DisembarkModeKind.RAPID_DISEMBARK,
        transport_movement_status=TransportMovementStatus.NORMAL_MOVE,
    )
    rapid_ingress_selection = DisembarkSelection(
        player_id="player-a",
        battle_round=1,
        unit_instance_id=passenger.unit_instance_id,
        transport_unit_instance_id=transport.unit_instance_id,
        attempted_placement=attempted_placement,
        disembark_mode=DisembarkModeKind.RAPID_DISEMBARK,
        transport_movement_status=TransportMovementStatus.INGRESS_MOVE,
    )

    assert DisembarkSelection.from_payload(tactical_selection.to_payload()) == tactical_selection
    assert (
        DisembarkSelection.from_payload(rapid_normal_selection.to_payload())
        == rapid_normal_selection
    )
    assert (
        DisembarkSelection.from_payload(rapid_ingress_selection.to_payload())
        == rapid_ingress_selection
    )

    with pytest.raises(GameLifecycleError, match="Tactical Disembark requires an unmoved"):
        resolve_disembark(
            scenario=disembark_scenario,
            ruleset_descriptor=_ruleset(),
            cargo_state=cargo_state,
            selection=DisembarkSelection(
                player_id="player-a",
                battle_round=1,
                unit_instance_id=passenger.unit_instance_id,
                transport_unit_instance_id=transport.unit_instance_id,
                attempted_placement=attempted_placement,
                disembark_mode=DisembarkModeKind.TACTICAL_DISEMBARK,
                transport_movement_status=TransportMovementStatus.NORMAL_MOVE,
            ),
            unit=passenger,
            transport_placement=disembark_scenario.battlefield_state.unit_placement_by_id(
                transport.unit_instance_id
            ),
        )
    with pytest.raises(GameLifecycleError, match="Rapid Disembark requires Normal or Ingress"):
        DisembarkSelection(
            player_id="player-a",
            battle_round=1,
            unit_instance_id=passenger.unit_instance_id,
            transport_unit_instance_id=transport.unit_instance_id,
            attempted_placement=attempted_placement,
            disembark_mode=DisembarkModeKind.RAPID_DISEMBARK,
            transport_movement_status=TransportMovementStatus.NOT_MOVED,
        )
    with pytest.raises(GameLifecycleError, match="Combat Disembark requires a dedicated"):
        DisembarkSelection(
            player_id="player-a",
            battle_round=1,
            unit_instance_id=passenger.unit_instance_id,
            transport_unit_instance_id=transport.unit_instance_id,
            attempted_placement=attempted_placement,
            disembark_mode=DisembarkModeKind.COMBAT_DISEMBARK,
            transport_movement_status=TransportMovementStatus.NOT_MOVED,
        )
    with pytest.raises(GameLifecycleError, match="Combat Disembark requires a dedicated"):
        DisembarkedUnitState.for_mode(
            player_id="player-a",
            battle_round=1,
            unit_instance_id=passenger.unit_instance_id,
            transport_unit_instance_id=transport.unit_instance_id,
            disembark_mode=DisembarkModeKind.COMBAT_DISEMBARK,
            transport_movement_status=TransportMovementStatus.NOT_MOVED,
        )


def test_embark_after_disembark_needs_explicit_override() -> None:
    scenario, passenger, transport, _enemy, _catalog = _transport_scenario()
    disembarked_cargo = _cargo_state(
        transport=transport,
        embarked_unit_ids=(),
        started_unit_ids=(),
        disembarked_unit_ids=(passenger.unit_instance_id,),
        battle_round=1,
    )
    passenger_placement = scenario.battlefield_state.unit_placement_by_id(
        passenger.unit_instance_id
    )
    transport_placement = scenario.battlefield_state.unit_placement_by_id(
        transport.unit_instance_id
    )
    blocked_embark = resolve_embark(
        scenario=scenario,
        cargo_state=disembarked_cargo,
        selection=EmbarkSelection(
            player_id="player-a",
            battle_round=1,
            unit_instance_id=passenger.unit_instance_id,
            transport_unit_instance_id=transport.unit_instance_id,
            movement_phase_action=TransportMovementStatus.NORMAL_MOVE,
        ),
        unit_placement=passenger_placement,
        transport_placement=transport_placement,
    )
    allowed_embark = resolve_embark(
        scenario=scenario,
        cargo_state=disembarked_cargo,
        selection=EmbarkSelection(
            player_id="player-a",
            battle_round=1,
            unit_instance_id=passenger.unit_instance_id,
            transport_unit_instance_id=transport.unit_instance_id,
            movement_phase_action=TransportMovementStatus.NORMAL_MOVE,
            restriction_overrides=(
                TransportRestrictionOverride(
                    override_kind=TransportRestrictionOverrideKind.ALLOW_EMBARK_AFTER_DISEMBARK,
                    source_rule_id="phase10q_override",
                ),
            ),
        ),
        unit_placement=passenger_placement,
        transport_placement=transport_placement,
    )

    assert TransportOperationViolationCode.EMBARK_AFTER_DISEMBARK_FORBIDDEN in {
        violation.violation_code for violation in blocked_embark.violations
    }
    assert allowed_embark.is_valid


def test_embark_reports_all_local_validation_failures_without_mutation_records() -> None:
    scenario, passenger, transport, _enemy, _catalog = _transport_scenario()
    passenger_placement = _unit_placement_at(
        passenger,
        army_id="army-alpha",
        player_id="player-a",
        poses=tuple(
            Pose.at(35.0 + index * 2.0, 10.0) for index in range(len(passenger.own_models))
        ),
    )
    transport_placement = scenario.battlefield_state.unit_placement_by_id(
        transport.unit_instance_id
    )
    result = resolve_embark(
        scenario=scenario,
        cargo_state=TransportCargoState(
            player_id="player-a",
            transport_unit_instance_id=transport.unit_instance_id,
            capacity_profile=TransportCapacityProfile(
                transport_datasheet_id=transport.datasheet_id,
                max_model_count=4,
                allowed_keywords=("MONSTER",),
            ),
            embarked_unit_instance_ids=(passenger.unit_instance_id,),
            phase_battle_round=1,
            started_phase_embarked_unit_instance_ids=(passenger.unit_instance_id,),
        ),
        selection=EmbarkSelection(
            player_id="player-b",
            battle_round=1,
            unit_instance_id="army-alpha:wrong-passenger",
            transport_unit_instance_id=transport.unit_instance_id,
            movement_phase_action=TransportMovementStatus.NORMAL_MOVE,
        ),
        unit_placement=passenger_placement,
        transport_placement=transport_placement,
    )

    assert not result.is_valid
    assert result.updated_cargo_state is None
    assert result.transition_batch is None
    assert {
        TransportOperationViolationCode.UNIT_PLACEMENT_DRIFT,
        TransportOperationViolationCode.FRIENDLY_TRANSPORT_REQUIRED,
        TransportOperationViolationCode.UNIT_ALREADY_EMBARKED,
        TransportOperationViolationCode.CAPACITY_EXCEEDED,
        TransportOperationViolationCode.EMBARK_DISTANCE,
    } <= {violation.violation_code for violation in result.violations}
    with pytest.raises(GameLifecycleError, match="Invalid EmbarkResolution"):
        apply_embark_to_battlefield(
            battlefield_state=scenario.battlefield_state,
            embark=result,
        )


def test_disembark_reports_enemy_range_edge_overlap_and_membership_failures() -> None:
    scenario, passenger, transport, enemy, _catalog = _transport_scenario()
    disembark_scenario = _without_unit(scenario, passenger.unit_instance_id)
    enemy_placement = _unit_placement_at(
        enemy,
        army_id="army-beta",
        player_id="player-b",
        poses=tuple(Pose.at(1.0 + index * 1.0, 1.0) for index in range(len(enemy.own_models))),
    )
    disembark_scenario = BattlefieldScenario(
        armies=disembark_scenario.armies,
        battlefield_state=disembark_scenario.battlefield_state.with_unit_placement(enemy_placement),
    )
    attempted_placement = _unit_placement_at(
        passenger,
        army_id="army-alpha",
        player_id="player-a",
        poses=(Pose.at(0.25, 1.0), Pose.at(0.25, 1.0)),
    )

    result = resolve_disembark(
        scenario=disembark_scenario,
        ruleset_descriptor=_ruleset(),
        cargo_state=_cargo_state(transport=transport),
        selection=DisembarkSelection(
            player_id="player-a",
            battle_round=1,
            unit_instance_id=passenger.unit_instance_id,
            transport_unit_instance_id=transport.unit_instance_id,
            attempted_placement=attempted_placement,
            disembark_mode=DisembarkModeKind.TACTICAL_DISEMBARK,
            transport_movement_status=TransportMovementStatus.NOT_MOVED,
        ),
        unit=enemy,
        transport_placement=disembark_scenario.battlefield_state.unit_placement_by_id(
            transport.unit_instance_id
        ),
    )

    assert not result.is_valid
    assert {
        TransportOperationViolationCode.UNIT_PLACEMENT_DRIFT,
        TransportOperationViolationCode.UNIT_NOT_EMBARKED,
        TransportOperationViolationCode.UNIT_DID_NOT_START_PHASE_EMBARKED,
        TransportOperationViolationCode.DISEMBARK_DISTANCE,
        TransportOperationViolationCode.BATTLEFIELD_EDGE_CROSSED,
        TransportOperationViolationCode.MODEL_OVERLAP,
        TransportOperationViolationCode.ENEMY_ENGAGEMENT_RANGE,
    } <= {violation.violation_code for violation in result.violations}


def test_destroyed_transport_emergency_destroys_unplaceable_models_and_battleshocks_unit() -> None:
    scenario, passenger, transport, _enemy, _catalog = _transport_scenario()
    disembark_scenario = _without_unit(scenario, passenger.unit_instance_id)
    partial_placement = _unit_placement_at(
        passenger,
        army_id="army-alpha",
        player_id="player-a",
        poses=_disembark_poses()[:-1],
    )

    result = resolve_destroyed_transport_disembark(
        scenario=disembark_scenario,
        ruleset_descriptor=_ruleset(),
        cargo_state=_cargo_state(
            transport=transport,
            embarked_unit_ids=(passenger.unit_instance_id,),
            started_unit_ids=(passenger.unit_instance_id,),
            battle_round=1,
        ),
        selection=DisembarkSelection(
            player_id="player-a",
            battle_round=1,
            unit_instance_id=passenger.unit_instance_id,
            transport_unit_instance_id=transport.unit_instance_id,
            attempted_placement=partial_placement,
            disembark_mode=DisembarkModeKind.EMERGENCY_DISEMBARK,
            transport_movement_status=TransportMovementStatus.NOT_MOVED,
        ),
        unit=passenger,
        transport_placement=disembark_scenario.battlefield_state.unit_placement_by_id(
            transport.unit_instance_id
        ),
        dice_manager=DiceRollManager(10),
    )

    assert result.placement.is_valid
    assert result.roll_threshold == 3
    assert len(result.model_rolls) == len(partial_placement.model_placements)
    assert result.destroyed_model_instance_ids == (passenger.own_models[-1].model_instance_id,)
    assert result.disembarked_unit_state is not None
    assert result.disembarked_unit_state.battle_shocked_until == (
        "controller_next_command_phase_start"
    )
    assert result.disembarked_unit_state.disembark_mode is (DisembarkModeKind.EMERGENCY_DISEMBARK)
    updated_battlefield = apply_destroyed_transport_disembark_to_battlefield(
        battlefield_state=disembark_scenario.battlefield_state,
        disembark=result,
    )
    assert passenger.own_models[-1].model_instance_id in updated_battlefield.removed_model_ids


def test_firing_deck_selects_ranged_non_one_shot_weapons_and_marks_units_ineligible() -> None:
    _scenario, passenger, transport, _enemy, catalog = _transport_scenario()
    profile = _first_weapon_profile(catalog, passenger)
    cargo_state = _cargo_state(
        transport=transport,
        embarked_unit_ids=(passenger.unit_instance_id,),
        started_unit_ids=(passenger.unit_instance_id,),
        battle_round=1,
    )
    selection = FiringDeckSelection(
        player_id="player-a",
        battle_round=1,
        transport_unit_instance_id=transport.unit_instance_id,
        firing_deck_value=1,
        weapon_selections=(
            FiringDeckWeaponSelection(
                embarked_unit_instance_id=passenger.unit_instance_id,
                model_instance_id=passenger.own_models[0].model_instance_id,
                wargear_id=passenger.wargear_selections[0].wargear_ids[0],
                weapon_profile=profile,
            ),
        ),
    )

    result = resolve_firing_deck_selection(
        cargo_state=cargo_state,
        selection=selection,
        embarked_units=(passenger,),
    )
    duplicate_model_result = resolve_firing_deck_selection(
        cargo_state=cargo_state,
        selection=replace(
            selection,
            firing_deck_value=2,
            weapon_selections=(selection.weapon_selections[0], selection.weapon_selections[0]),
        ),
        embarked_units=(passenger,),
    )
    one_shot_result = resolve_firing_deck_selection(
        cargo_state=cargo_state,
        selection=replace(
            selection,
            weapon_selections=(
                replace(
                    selection.weapon_selections[0],
                    weapon_profile=replace(
                        profile,
                        keywords=(*profile.keywords, WeaponKeyword.ONE_SHOT),
                    ),
                ),
            ),
        ),
        embarked_units=(passenger,),
    )

    assert result.is_valid
    assert result.temporary_weapon_profiles == (profile,)
    assert result.ineligible_unit_instance_ids == (passenger.unit_instance_id,)
    assert TransportOperationViolationCode.FIRING_DECK_DUPLICATE_MODEL_SELECTION in {
        violation.violation_code for violation in duplicate_model_result.violations
    }
    assert TransportOperationViolationCode.FIRING_DECK_ONE_SHOT_WEAPON in {
        violation.violation_code for violation in one_shot_result.violations
    }


def test_firing_deck_reports_capacity_membership_shot_model_and_melee_failures() -> None:
    _scenario, passenger, transport, _enemy, catalog = _transport_scenario()
    ranged_profile = _first_weapon_profile(catalog, passenger)
    melee_profile = _wargear_by_id(catalog, "core-leader-blade").weapon_profiles[0]

    result = resolve_firing_deck_selection(
        cargo_state=_cargo_state(
            transport=transport,
            embarked_unit_ids=(passenger.unit_instance_id,),
            started_unit_ids=(passenger.unit_instance_id,),
            battle_round=1,
        ),
        selection=FiringDeckSelection(
            player_id="player-a",
            battle_round=1,
            transport_unit_instance_id=transport.unit_instance_id,
            firing_deck_value=1,
            weapon_selections=(
                FiringDeckWeaponSelection(
                    embarked_unit_instance_id="army-alpha:not-embarked",
                    model_instance_id="army-alpha:not-embarked:model-001",
                    wargear_id="core-bolt-rifle",
                    weapon_profile=ranged_profile,
                ),
                FiringDeckWeaponSelection(
                    embarked_unit_instance_id=passenger.unit_instance_id,
                    model_instance_id="army-alpha:passenger-unit:model-999",
                    wargear_id="core-leader-blade",
                    weapon_profile=melee_profile,
                ),
            ),
            already_shot_unit_instance_ids=(passenger.unit_instance_id,),
        ),
        embarked_units=(passenger,),
    )

    assert not result.is_valid
    assert {
        TransportOperationViolationCode.FIRING_DECK_CAPACITY_EXCEEDED,
        TransportOperationViolationCode.FIRING_DECK_UNIT_NOT_EMBARKED,
        TransportOperationViolationCode.FIRING_DECK_UNIT_ALREADY_SHOT,
        TransportOperationViolationCode.FIRING_DECK_MODEL_DRIFT,
        TransportOperationViolationCode.FIRING_DECK_MELEE_WEAPON,
    } <= {violation.violation_code for violation in result.violations}


def test_transport_payloads_round_trip_without_python_reprs() -> None:
    scenario, passenger, transport, _enemy, catalog = _transport_scenario()
    profile = _first_weapon_profile(catalog, passenger)
    override = TransportRestrictionOverride(
        override_kind=TransportRestrictionOverrideKind.ALLOW_EMBARK_AFTER_DISEMBARK,
        source_rule_id="phase10q_override",
    )
    violation = TransportOperationViolation(
        violation_code=TransportOperationViolationCode.EMBARK_DISTANCE,
        message="Payload test violation.",
        unit_instance_id=passenger.unit_instance_id,
        model_instance_id=passenger.own_models[0].model_instance_id,
        blocker_id=transport.unit_instance_id,
        source_rule_id="phase10q_payload",
    )
    cargo_state = _cargo_state(
        transport=transport,
        embarked_unit_ids=(passenger.unit_instance_id,),
        started_unit_ids=(passenger.unit_instance_id,),
        battle_round=1,
    )
    selection = FiringDeckSelection(
        player_id="player-a",
        battle_round=1,
        transport_unit_instance_id=transport.unit_instance_id,
        firing_deck_value=1,
        weapon_selections=(
            FiringDeckWeaponSelection(
                embarked_unit_instance_id=passenger.unit_instance_id,
                model_instance_id=passenger.own_models[0].model_instance_id,
                wargear_id=passenger.wargear_selections[0].wargear_ids[0],
                weapon_profile=profile,
            ),
        ),
    )
    embark_resolution = resolve_embark(
        scenario=scenario,
        cargo_state=_cargo_state(transport=transport),
        selection=EmbarkSelection(
            player_id="player-a",
            battle_round=1,
            unit_instance_id=passenger.unit_instance_id,
            transport_unit_instance_id=transport.unit_instance_id,
            movement_phase_action=TransportMovementStatus.NORMAL_MOVE,
        ),
        unit_placement=scenario.battlefield_state.unit_placement_by_id(passenger.unit_instance_id),
        transport_placement=scenario.battlefield_state.unit_placement_by_id(
            transport.unit_instance_id
        ),
    )
    disembark_resolution = resolve_disembark(
        scenario=_without_unit(scenario, passenger.unit_instance_id),
        ruleset_descriptor=_ruleset(),
        cargo_state=cargo_state,
        selection=DisembarkSelection(
            player_id="player-a",
            battle_round=1,
            unit_instance_id=passenger.unit_instance_id,
            transport_unit_instance_id=transport.unit_instance_id,
            attempted_placement=_unit_placement_at(
                passenger,
                army_id="army-alpha",
                player_id="player-a",
                poses=_disembark_poses(),
            ),
            disembark_mode=DisembarkModeKind.TACTICAL_DISEMBARK,
            transport_movement_status=TransportMovementStatus.NOT_MOVED,
        ),
        unit=passenger,
        transport_placement=scenario.battlefield_state.unit_placement_by_id(
            transport.unit_instance_id
        ),
    )
    destroyed_resolution = resolve_destroyed_transport_disembark(
        scenario=_without_unit(scenario, passenger.unit_instance_id),
        ruleset_descriptor=_ruleset(),
        cargo_state=cargo_state,
        selection=replace(
            disembark_resolution.selection,
            disembark_mode=DisembarkModeKind.DESTROYED_TRANSPORT,
        ),
        unit=passenger,
        transport_placement=scenario.battlefield_state.unit_placement_by_id(
            transport.unit_instance_id
        ),
        dice_manager=DiceRollManager(10),
    )
    firing_deck_resolution = resolve_firing_deck_selection(
        cargo_state=cargo_state,
        selection=selection,
        embarked_units=(passenger,),
    )

    cargo_blob = json.dumps(cargo_state.to_payload(), sort_keys=True)
    selection_blob = json.dumps(selection.to_payload(), sort_keys=True)
    violation_blob = json.dumps(violation.to_payload(), sort_keys=True)

    assert "<" not in cargo_blob
    assert "object at 0x" not in cargo_blob
    assert "<" not in selection_blob
    assert "object at 0x" not in selection_blob
    assert "<" not in violation_blob
    assert "object at 0x" not in violation_blob
    assert TransportRestrictionOverride.from_payload(override.to_payload()) == override
    assert TransportOperationViolation.from_payload(violation.to_payload()) == violation
    assert TransportCargoState.from_payload(cargo_state.to_payload()) == cargo_state
    assert FiringDeckSelection.from_payload(selection.to_payload()) == selection
    assert EmbarkResolution.from_payload(embark_resolution.to_payload()) == embark_resolution
    assert DisembarkResolution.from_payload(disembark_resolution.to_payload()) == (
        disembark_resolution
    )
    assert (
        DestroyedTransportDisembark.from_payload(destroyed_resolution.to_payload())
        == destroyed_resolution
    )
    assert (
        FiringDeckResolution.from_payload(firing_deck_resolution.to_payload())
        == firing_deck_resolution
    )
    assert EmbarkSelection.from_payload(
        EmbarkSelection(
            player_id="player-a",
            battle_round=1,
            unit_instance_id=passenger.unit_instance_id,
            transport_unit_instance_id=transport.unit_instance_id,
            movement_phase_action=TransportMovementStatus.NORMAL_MOVE,
            restriction_overrides=(override,),
        ).to_payload()
    ).restriction_overrides == (override,)
    assert (
        DisembarkSelection.from_payload(
            DisembarkSelection(
                player_id="player-a",
                battle_round=1,
                unit_instance_id=passenger.unit_instance_id,
                transport_unit_instance_id=transport.unit_instance_id,
                attempted_placement=_unit_placement_at(
                    passenger,
                    army_id="army-alpha",
                    player_id="player-a",
                    poses=_disembark_poses(),
                ),
                disembark_mode=DisembarkModeKind.TACTICAL_DISEMBARK,
                transport_movement_status=TransportMovementStatus.NOT_MOVED,
            ).to_payload()
        ).transport_movement_status
        is TransportMovementStatus.NOT_MOVED
    )


def test_resolution_payloads_reject_destroyed_transport_and_firing_deck_drift() -> None:
    scenario, passenger, transport, _enemy, catalog = _transport_scenario()
    cargo_state = _cargo_state(
        transport=transport,
        embarked_unit_ids=(passenger.unit_instance_id,),
        started_unit_ids=(passenger.unit_instance_id,),
        battle_round=1,
    )
    disembark_selection = DisembarkSelection(
        player_id="player-a",
        battle_round=1,
        unit_instance_id=passenger.unit_instance_id,
        transport_unit_instance_id=transport.unit_instance_id,
        attempted_placement=_unit_placement_at(
            passenger,
            army_id="army-alpha",
            player_id="player-a",
            poses=_disembark_poses(),
        ),
        disembark_mode=DisembarkModeKind.DESTROYED_TRANSPORT,
        transport_movement_status=TransportMovementStatus.NOT_MOVED,
    )
    destroyed_resolution = resolve_destroyed_transport_disembark(
        scenario=_without_unit(scenario, passenger.unit_instance_id),
        ruleset_descriptor=_ruleset(),
        cargo_state=cargo_state,
        selection=disembark_selection,
        unit=passenger,
        transport_placement=scenario.battlefield_state.unit_placement_by_id(
            transport.unit_instance_id
        ),
        dice_manager=DiceRollManager(10),
    )
    bad_mortal_wound_roll = replace(
        destroyed_resolution.model_rolls[0],
        mortal_wound_inflicted=not destroyed_resolution.model_rolls[0].mortal_wound_inflicted,
    )
    with pytest.raises(GameLifecycleError, match="mortal wound roll drift"):
        DestroyedTransportDisembark(
            player_id=destroyed_resolution.player_id,
            battle_round=destroyed_resolution.battle_round,
            unit_instance_id=destroyed_resolution.unit_instance_id,
            transport_unit_instance_id=destroyed_resolution.transport_unit_instance_id,
            disembark_mode=destroyed_resolution.disembark_mode,
            placement=destroyed_resolution.placement,
            roll_threshold=destroyed_resolution.roll_threshold,
            model_rolls=(bad_mortal_wound_roll, *destroyed_resolution.model_rolls[1:]),
            destroyed_model_instance_ids=destroyed_resolution.destroyed_model_instance_ids,
        )
    bad_model_roll = replace(
        destroyed_resolution.model_rolls[0],
        model_instance_id="army-alpha:passenger-unit:model-999",
    )
    with pytest.raises(GameLifecycleError, match="roll model drift"):
        DestroyedTransportDisembark(
            player_id=destroyed_resolution.player_id,
            battle_round=destroyed_resolution.battle_round,
            unit_instance_id=destroyed_resolution.unit_instance_id,
            transport_unit_instance_id=destroyed_resolution.transport_unit_instance_id,
            disembark_mode=destroyed_resolution.disembark_mode,
            placement=destroyed_resolution.placement,
            roll_threshold=destroyed_resolution.roll_threshold,
            model_rolls=(bad_model_roll, *destroyed_resolution.model_rolls[1:]),
            destroyed_model_instance_ids=destroyed_resolution.destroyed_model_instance_ids,
        )
    destroyed_payload = destroyed_resolution.to_payload()
    destroyed_payload["mortal_wound_count"] += 1
    with pytest.raises(GameLifecycleError, match="mortal wound count drift"):
        DestroyedTransportDisembark.from_payload(destroyed_payload)

    profile = _first_weapon_profile(catalog, passenger)
    firing_deck_resolution = resolve_firing_deck_selection(
        cargo_state=cargo_state,
        selection=FiringDeckSelection(
            player_id="player-a",
            battle_round=1,
            transport_unit_instance_id=transport.unit_instance_id,
            firing_deck_value=1,
            weapon_selections=(
                FiringDeckWeaponSelection(
                    embarked_unit_instance_id=passenger.unit_instance_id,
                    model_instance_id=passenger.own_models[0].model_instance_id,
                    wargear_id=passenger.wargear_selections[0].wargear_ids[0],
                    weapon_profile=profile,
                ),
            ),
        ),
        embarked_units=(passenger,),
    )
    firing_payload = firing_deck_resolution.to_payload()
    firing_payload["temporary_weapon_profiles"][0] = {
        **firing_payload["temporary_weapon_profiles"][0],
        "name": "Drifted Temporary Weapon",
    }
    with pytest.raises(GameLifecycleError, match="weapon profile drift"):
        FiringDeckResolution.from_payload(firing_payload)


def test_transport_token_parsers_reject_invalid_values() -> None:
    with pytest.raises(GameLifecycleError, match="TransportMovementStatus token"):
        transport_movement_status_from_token(123)
    with pytest.raises(GameLifecycleError, match="Unsupported TransportMovementStatus"):
        transport_movement_status_from_token("bad-status")
    with pytest.raises(GameLifecycleError, match="TransportRestrictionOverrideKind token"):
        transport_restriction_override_kind_from_token(None)
    with pytest.raises(GameLifecycleError, match="Unsupported TransportRestrictionOverrideKind"):
        transport_restriction_override_kind_from_token("bad-override")
    with pytest.raises(GameLifecycleError, match="DisembarkModeKind token"):
        disembark_mode_kind_from_token(False)
    with pytest.raises(GameLifecycleError, match="Unsupported DisembarkModeKind"):
        disembark_mode_kind_from_token("bad-disembark")
    with pytest.raises(GameLifecycleError, match="TransportOperationViolationCode token"):
        transport_operation_violation_code_from_token(3.14)
    with pytest.raises(GameLifecycleError, match="Unsupported TransportOperationViolationCode"):
        transport_operation_violation_code_from_token("bad-violation")


def test_transport_cargo_state_rejects_invalid_direct_operations() -> None:
    _scenario, passenger, transport, _enemy, _catalog = _transport_scenario()
    cargo_state = _cargo_state(
        transport=transport,
        embarked_unit_ids=(passenger.unit_instance_id,),
    )

    with pytest.raises(GameLifecycleError, match="already embarked"):
        cargo_state.with_embarked_unit(passenger.unit_instance_id)
    with pytest.raises(GameLifecycleError, match="not embarked"):
        _cargo_state(transport=transport).with_disembarked_unit(passenger.unit_instance_id)
    with pytest.raises(GameLifecycleError, match="UnitInstance"):
        cargo_state.capacity_profile.allows_unit(cast(UnitInstance, object()))


def test_transport_resolvers_fail_fast_on_wrong_domain_objects() -> None:
    scenario, passenger, transport, _enemy, _catalog = _transport_scenario()
    passenger_placement = scenario.battlefield_state.unit_placement_by_id(
        passenger.unit_instance_id
    )
    transport_placement = scenario.battlefield_state.unit_placement_by_id(
        transport.unit_instance_id
    )
    cargo_state = _cargo_state(transport=transport)
    embark_selection = EmbarkSelection(
        player_id="player-a",
        battle_round=1,
        unit_instance_id=passenger.unit_instance_id,
        transport_unit_instance_id=transport.unit_instance_id,
        movement_phase_action=TransportMovementStatus.NORMAL_MOVE,
    )

    with pytest.raises(GameLifecycleError, match="BattlefieldScenario"):
        resolve_embark(
            scenario=cast(BattlefieldScenario, object()),
            cargo_state=cargo_state,
            selection=embark_selection,
            unit_placement=passenger_placement,
            transport_placement=transport_placement,
        )
    with pytest.raises(GameLifecycleError, match="TransportCargoState"):
        resolve_embark(
            scenario=scenario,
            cargo_state=cast(TransportCargoState, object()),
            selection=embark_selection,
            unit_placement=passenger_placement,
            transport_placement=transport_placement,
        )
    with pytest.raises(GameLifecycleError, match="EmbarkSelection"):
        resolve_embark(
            scenario=scenario,
            cargo_state=cargo_state,
            selection=cast(EmbarkSelection, object()),
            unit_placement=passenger_placement,
            transport_placement=transport_placement,
        )
    with pytest.raises(GameLifecycleError, match="unit_placement"):
        resolve_embark(
            scenario=scenario,
            cargo_state=cargo_state,
            selection=embark_selection,
            unit_placement=cast(UnitPlacement, object()),
            transport_placement=transport_placement,
        )
    with pytest.raises(GameLifecycleError, match="transport_placement"):
        resolve_embark(
            scenario=scenario,
            cargo_state=cargo_state,
            selection=embark_selection,
            unit_placement=passenger_placement,
            transport_placement=cast(UnitPlacement, object()),
        )


def test_disembarked_units_use_shared_movement_decision_path_restrictions() -> None:
    scenario, passenger, transport, _enemy, _catalog = _transport_scenario()
    state = _battle_state(scenario)
    disembarked_state = resolve_disembark(
        scenario=_without_unit(scenario, passenger.unit_instance_id),
        ruleset_descriptor=_ruleset(),
        cargo_state=_cargo_state(
            transport=transport,
            embarked_unit_ids=(passenger.unit_instance_id,),
            started_unit_ids=(passenger.unit_instance_id,),
            battle_round=1,
        ),
        selection=DisembarkSelection(
            player_id="player-a",
            battle_round=1,
            unit_instance_id=passenger.unit_instance_id,
            transport_unit_instance_id=transport.unit_instance_id,
            attempted_placement=scenario.battlefield_state.unit_placement_by_id(
                passenger.unit_instance_id
            ),
            disembark_mode=DisembarkModeKind.TACTICAL_DISEMBARK,
            transport_movement_status=TransportMovementStatus.NOT_MOVED,
        ),
        unit=passenger,
        transport_placement=scenario.battlefield_state.unit_placement_by_id(
            transport.unit_instance_id
        ),
    ).disembarked_unit_state
    assert disembarked_state is not None
    state.record_disembarked_unit_state(disembarked_state)
    state.movement_phase_state = MovementPhaseState(
        battle_round=1,
        active_player_id="player-a",
        selected_unit_ids=(passenger.unit_instance_id,),
        active_selection=MovementUnitSelection(
            player_id="player-a",
            battle_round=1,
            unit_instance_id=passenger.unit_instance_id,
            request_id="phase10q-select-passenger",
            result_id="phase10q-select-passenger-result",
        ),
    )

    status = MovementPhaseHandler(ruleset_descriptor=_ruleset()).begin_phase(
        state=state,
        decisions=DecisionController(),
    )

    assert status.decision_request is not None
    assert status.decision_request.decision_type == SELECT_MOVEMENT_ACTION_DECISION_TYPE
    assert MovementPhaseActionKind.REMAIN_STATIONARY.value not in {
        option.option_id for option in status.decision_request.options
    }


def _embark_ready_scenario() -> tuple[
    BattlefieldScenario,
    UnitInstance,
    UnitInstance,
    UnitInstance,
    ArmyCatalog,
]:
    scenario, passenger, transport, enemy, catalog = _transport_scenario()
    post_move_poses = (
        Pose.at(8.6, 13.0),
        Pose.at(10.0, 13.0),
        Pose.at(11.4, 13.0),
        Pose.at(9.3, 14.2),
        Pose.at(10.7, 14.2),
    )
    battlefield = scenario.battlefield_state.with_unit_placement(
        _unit_placement_at(
            passenger,
            army_id="army-alpha",
            player_id="player-a",
            poses=tuple(
                Pose.at(
                    pose.position.x - 6.0,
                    pose.position.y,
                    pose.position.z,
                    facing_degrees=pose.facing.degrees,
                )
                for pose in post_move_poses
            ),
        )
    )
    return (
        BattlefieldScenario(armies=scenario.armies, battlefield_state=battlefield),
        passenger,
        transport,
        enemy,
        catalog,
    )


def _advance_embark_ready_scenario() -> tuple[
    BattlefieldScenario,
    UnitInstance,
    UnitInstance,
    UnitInstance,
    ArmyCatalog,
]:
    scenario, passenger, transport, enemy, catalog = _transport_scenario()
    battlefield = scenario.battlefield_state.with_unit_placement(
        _unit_placement_at(
            passenger,
            army_id="army-alpha",
            player_id="player-a",
            poses=(
                Pose.at(1.6, 9.0),
                Pose.at(3.0, 9.0),
                Pose.at(4.4, 9.0),
                Pose.at(2.3, 10.2),
                Pose.at(3.7, 10.2),
            ),
        )
    ).with_unit_placement(
        _unit_placement_at(
            transport,
            army_id="army-alpha",
            player_id="player-a",
            poses=(Pose.at(14.0, 10.0),),
        )
    )
    return (
        BattlefieldScenario(armies=scenario.armies, battlefield_state=battlefield),
        passenger,
        transport,
        enemy,
        catalog,
    )


def _fall_back_embark_ready_scenario() -> tuple[
    BattlefieldScenario,
    UnitInstance,
    UnitInstance,
    UnitInstance,
    ArmyCatalog,
]:
    scenario, passenger, transport, enemy, catalog = _transport_scenario()
    battlefield = (
        scenario.battlefield_state.with_unit_placement(
            _unit_placement_at(
                passenger,
                army_id="army-alpha",
                player_id="player-a",
                poses=(
                    Pose.at(2.6, 9.0),
                    Pose.at(4.0, 9.0),
                    Pose.at(5.4, 9.0),
                    Pose.at(3.3, 10.2),
                    Pose.at(4.7, 10.2),
                ),
            )
        )
        .with_unit_placement(
            _unit_placement_at(
                transport,
                army_id="army-alpha",
                player_id="player-a",
                poses=(Pose.at(4.0, 19.0),),
            )
        )
        .with_unit_placement(
            _unit_placement_at(
                enemy,
                army_id="army-beta",
                player_id="player-b",
                poses=(
                    Pose.at(2.6, 7.5),
                    Pose.at(35.0, 35.0),
                    Pose.at(37.0, 35.0),
                    Pose.at(39.0, 35.0),
                    Pose.at(41.0, 35.0),
                ),
            )
        )
    )
    return (
        BattlefieldScenario(armies=scenario.armies, battlefield_state=battlefield),
        passenger,
        transport,
        enemy,
        catalog,
    )


def _movement_action_request_for_unit(
    *,
    state: GameState,
    unit_instance_id: str,
) -> tuple[MovementPhaseHandler, DecisionController, DecisionRequest]:
    state.movement_phase_state = MovementPhaseState(
        battle_round=state.battle_round,
        active_player_id="player-a",
    )
    handler = MovementPhaseHandler(ruleset_descriptor=_ruleset())
    decisions = DecisionController()
    selection_request = _decision_request(handler.begin_phase(state=state, decisions=decisions))
    if selection_request.decision_type == SELECT_DISEMBARK_UNIT_DECISION_TYPE:
        decline_status = _submit_handler_decision(
            handler,
            state=state,
            decisions=decisions,
            request=selection_request,
            option_id=COMPLETE_DISEMBARKS_OPTION_ID,
            result_id=f"{unit_instance_id}:decline-pre-move-disembark",
        )
        assert decline_status is None
        selection_request = _decision_request(handler.begin_phase(state=state, decisions=decisions))
    assert selection_request.decision_type == SELECT_MOVEMENT_UNIT_DECISION_TYPE
    selection_status = _submit_handler_decision(
        handler,
        state=state,
        decisions=decisions,
        request=selection_request,
        option_id=unit_instance_id,
        result_id=f"{unit_instance_id}:select-move",
    )
    assert selection_status is None
    action_request = _decision_request(handler.begin_phase(state=state, decisions=decisions))
    assert action_request.decision_type == SELECT_MOVEMENT_ACTION_DECISION_TYPE
    return handler, decisions, action_request


def _rapid_disembark_request_after_transport_normal_move(
    *,
    state: GameState,
    passenger: UnitInstance,
    transport: UnitInstance,
) -> tuple[MovementPhaseHandler, DecisionController, DecisionRequest]:
    state.movement_phase_state = MovementPhaseState(
        battle_round=state.battle_round,
        active_player_id="player-a",
    )
    handler = MovementPhaseHandler(ruleset_descriptor=_ruleset())
    decisions = DecisionController()
    pre_move_disembark_request = _decision_request(
        handler.begin_phase(state=state, decisions=decisions)
    )
    assert pre_move_disembark_request.decision_type == SELECT_DISEMBARK_UNIT_DECISION_TYPE
    assert passenger.unit_instance_id in {
        option.option_id for option in pre_move_disembark_request.options
    }
    pre_move_decline_status = _submit_handler_decision(
        handler,
        state=state,
        decisions=decisions,
        request=pre_move_disembark_request,
        option_id=COMPLETE_DISEMBARKS_OPTION_ID,
        result_id="phase10q-decline-pre-move-disembark",
    )
    assert pre_move_decline_status is None
    movement_request = _decision_request(handler.begin_phase(state=state, decisions=decisions))
    assert movement_request.decision_type == SELECT_MOVEMENT_UNIT_DECISION_TYPE
    transport_selection_status = _submit_handler_decision(
        handler,
        state=state,
        decisions=decisions,
        request=movement_request,
        option_id=transport.unit_instance_id,
        result_id="phase10q-select-transport-normal-move",
    )
    assert transport_selection_status is None
    action_request = _decision_request(handler.begin_phase(state=state, decisions=decisions))
    assert action_request.decision_type == SELECT_MOVEMENT_ACTION_DECISION_TYPE
    post_move_disembark_status = _submit_handler_decision(
        handler,
        state=state,
        decisions=decisions,
        request=action_request,
        option_id=MovementPhaseActionKind.NORMAL_MOVE.value,
        result_id="phase10q-transport-normal-move",
    )
    movement_proposal_request = _decision_request(post_move_disembark_status)
    assert movement_proposal_request.decision_type == MOVEMENT_PROPOSAL_DECISION_TYPE
    post_move_disembark_status = _submit_transport_normal_move_payload(
        handler=handler,
        state=state,
        decisions=decisions,
        request=movement_proposal_request,
        transport=transport,
        result_id="phase10q-transport-normal-move-proposal",
    )
    return handler, decisions, _decision_request(post_move_disembark_status)


def _submit_handler_decision(
    handler: MovementPhaseHandler,
    *,
    state: GameState,
    decisions: DecisionController,
    request: DecisionRequest,
    option_id: str,
    result_id: str,
) -> LifecycleStatus | None:
    result = DecisionResult.for_request(
        result_id=result_id,
        request=request,
        selected_option_id=option_id,
    )
    decisions.submit_result(result)
    return handler.apply_decision(
        state=state,
        result=result,
        decisions=decisions,
    )


def _submit_action_and_movement_payload(
    handler: MovementPhaseHandler,
    *,
    state: GameState,
    decisions: DecisionController,
    request: DecisionRequest,
    option_id: str,
    unit: UnitInstance,
    movement_phase_action: MovementPhaseActionKind,
    movement_mode: MovementMode,
    dx: float = 0.0,
    dy: float = 0.0,
    fall_back_mode: FallBackModeKind | None = None,
    result_id: str,
) -> LifecycleStatus | None:
    proposal_status = _submit_handler_decision(
        handler,
        state=state,
        decisions=decisions,
        request=request,
        option_id=option_id,
        result_id=result_id,
    )
    proposal_request = _decision_request(proposal_status)
    assert proposal_request.decision_type == MOVEMENT_PROPOSAL_DECISION_TYPE
    proposal = MovementProposalRequest.from_decision_request_payload(proposal_request.payload)
    assert state.battlefield_state is not None
    unit_placement = state.battlefield_state.unit_placement_by_id(unit.unit_instance_id)
    payload = MovementProposalPayload(
        proposal_request_id=proposal.request_id,
        proposal_kind=proposal.proposal_kind,
        unit_instance_id=unit.unit_instance_id,
        movement_phase_action=movement_phase_action.value,
        witness=_shift_witness(unit_placement, dx=dx, dy=dy),
        movement_mode=movement_mode.value,
        fall_back_mode=None if fall_back_mode is None else fall_back_mode.value,
    ).to_payload()
    return _submit_parameterized_handler_payload(
        handler=handler,
        state=state,
        decisions=decisions,
        request=proposal_request,
        payload=validate_json_value(payload),
        result_id=f"{result_id}-proposal",
    )


def _submit_transport_normal_move_payload(
    *,
    handler: MovementPhaseHandler,
    state: GameState,
    decisions: DecisionController,
    request: DecisionRequest,
    transport: UnitInstance,
    result_id: str,
) -> LifecycleStatus | None:
    proposal = MovementProposalRequest.from_decision_request_payload(request.payload)
    assert state.battlefield_state is not None
    transport_placement = state.battlefield_state.unit_placement_by_id(transport.unit_instance_id)
    payload = MovementProposalPayload(
        proposal_request_id=proposal.request_id,
        proposal_kind=proposal.proposal_kind,
        unit_instance_id=transport.unit_instance_id,
        movement_phase_action=MovementPhaseActionKind.NORMAL_MOVE.value,
        witness=_shift_witness(transport_placement, dx=-0.5),
        movement_mode=MovementMode.NORMAL.value,
    ).to_payload()
    return _submit_parameterized_handler_payload(
        handler=handler,
        state=state,
        decisions=decisions,
        request=request,
        payload=validate_json_value(payload),
        result_id=result_id,
    )


def _submit_disembark_placement_payload(
    handler: MovementPhaseHandler,
    *,
    state: GameState,
    decisions: DecisionController,
    request: DecisionRequest,
    passenger: UnitInstance,
    transport: UnitInstance,
    disembark_mode: DisembarkModeKind,
    transport_movement_status: TransportMovementStatus,
    result_id: str,
) -> LifecycleStatus | None:
    proposal = MovementProposalRequest.from_decision_request_payload(request.payload)
    poses = _disembark_poses()[: len(passenger.own_models)]
    if transport_movement_status is TransportMovementStatus.NORMAL_MOVE:
        poses = tuple(
            Pose.at(
                pose.position.x - 0.5,
                pose.position.y,
                pose.position.z,
                facing_degrees=pose.facing.degrees,
            )
            for pose in poses
        )
    placement = _unit_placement_at(
        passenger,
        army_id="army-alpha",
        player_id="player-a",
        poses=poses,
    )
    payload = PlacementProposalPayload(
        proposal_request_id=proposal.request_id,
        proposal_kind=proposal.proposal_kind,
        unit_instance_id=passenger.unit_instance_id,
        placement_kind=BattlefieldPlacementKind.DISEMBARK,
        attempted_placement=placement,
        transport_unit_instance_id=transport.unit_instance_id,
        disembark_mode=disembark_mode,
        transport_movement_status=transport_movement_status,
    ).to_payload()
    return _submit_parameterized_handler_payload(
        handler=handler,
        state=state,
        decisions=decisions,
        request=request,
        payload=validate_json_value(payload),
        result_id=result_id,
    )


def _submit_parameterized_handler_payload(
    *,
    handler: MovementPhaseHandler,
    state: GameState,
    decisions: DecisionController,
    request: DecisionRequest,
    payload: JsonValue,
    result_id: str,
) -> LifecycleStatus | None:
    result = DecisionResult(
        result_id=result_id,
        request_id=request.request_id,
        decision_type=request.decision_type,
        actor_id=request.actor_id,
        selected_option_id="submit_parameterized_payload",
        payload=payload,
    )
    invalid_status = handler.invalid_proposal_submission_status(
        state=state,
        request=request,
        result=result,
        decisions=decisions,
    )
    if invalid_status is not None:
        return invalid_status
    decisions.submit_result(result)
    return handler.apply_decision(state=state, result=result, decisions=decisions)


def _decision_request(status: LifecycleStatus | None) -> DecisionRequest:
    assert status is not None
    assert status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    assert status.decision_request is not None
    return status.decision_request


def _placed_unit_ids(state: GameState) -> set[str]:
    assert state.battlefield_state is not None
    return {
        placement.unit_instance_id
        for army in state.battlefield_state.placed_armies
        for placement in army.unit_placements
    }


def _advanced_unit_state(unit_instance_id: str) -> AdvancedUnitState:
    request = AdvanceRollRequest.for_unit(
        request_id="phase10q-invalid-advanced-state-roll",
        game_id="phase10q-game",
        battle_round=1,
        player_id="player-a",
        unit_instance_id=unit_instance_id,
    )
    roll_state = DiceRollManager("phase10q-invalid-advanced-state").roll_fixed(
        request.spec,
        [3],
    )
    advance_roll = AdvanceRollResult.from_roll_state(request=request, roll_state=roll_state)
    return AdvancedUnitState(
        player_id="player-a",
        battle_round=1,
        unit_instance_id=unit_instance_id,
        movement_dice_record=MovementDiceRecord(
            player_id="player-a",
            battle_round=1,
            unit_instance_id=unit_instance_id,
            movement_phase_action=MovementPhaseActionKind.ADVANCE,
            advance_roll=advance_roll,
        ),
    )


def _transport_scenario(
    *,
    passenger_datasheet_id: str = "core-intercessor-like-infantry",
    passenger_model_profile_id: str = "core-intercessor-like",
    passenger_model_count: int = 5,
    passenger_unit_selection_id: str = "passenger-unit",
) -> tuple[BattlefieldScenario, UnitInstance, UnitInstance, UnitInstance, ArmyCatalog]:
    catalog = ArmyCatalog.phase9a_canonical_content_pack()
    alpha_request = _army_muster_request(
        catalog=catalog,
        player_id="player-a",
        army_id="army-alpha",
        unit_selections=(
            _unit_selection(
                unit_selection_id=passenger_unit_selection_id,
                datasheet_id=passenger_datasheet_id,
                model_profile_id=passenger_model_profile_id,
                model_count=passenger_model_count,
            ),
            _unit_selection(
                unit_selection_id="transport-1",
                datasheet_id="core-transport",
                model_profile_id="core-transport",
                model_count=1,
            ),
        ),
    )
    beta_request = _army_muster_request(
        catalog=catalog,
        player_id="player-b",
        army_id="army-beta",
        unit_selections=(
            _unit_selection(
                unit_selection_id="enemy-unit",
                datasheet_id="core-intercessor-like-infantry",
                model_profile_id="core-intercessor-like",
                model_count=5,
            ),
        ),
    )
    armies = (
        muster_army(catalog=catalog, request=alpha_request),
        muster_army(catalog=catalog, request=beta_request),
    )
    scenario = create_deterministic_battlefield_scenario(
        battlefield_id="phase10q-battlefield",
        armies=armies,
    )
    passenger = armies[0].unit_by_id(f"army-alpha:{passenger_unit_selection_id}")
    transport = armies[0].unit_by_id("army-alpha:transport-1")
    enemy = armies[1].unit_by_id("army-beta:enemy-unit")
    battlefield = scenario.battlefield_state
    battlefield = battlefield.with_unit_placement(
        _unit_placement_at(
            passenger,
            army_id="army-alpha",
            player_id="player-a",
            poses=_disembark_poses()[: len(passenger.own_models)],
        )
    )
    battlefield = battlefield.with_unit_placement(
        _unit_placement_at(
            transport,
            army_id="army-alpha",
            player_id="player-a",
            poses=(Pose.at(10.0, 10.0),),
        )
    )
    battlefield = battlefield.with_unit_placement(
        _unit_placement_at(
            enemy,
            army_id="army-beta",
            player_id="player-b",
            poses=tuple(
                Pose.at(35.0 + index * 2.0, 35.0) for index in range(len(enemy.own_models))
            ),
        )
    )
    return (
        BattlefieldScenario(armies=armies, battlefield_state=battlefield),
        passenger,
        transport,
        enemy,
        catalog,
    )


def _ruleset() -> RulesetDescriptor:
    return RulesetDescriptor.warhammer_40000_eleventh()


def _battle_state(
    scenario: BattlefieldScenario,
    *,
    game_id: str = "phase10q-game",
) -> GameState:
    ruleset = _ruleset()
    return GameState(
        game_id=game_id,
        ruleset_descriptor_hash=ruleset.descriptor_hash,
        stage=GameLifecycleStage.BATTLE,
        setup_sequence=tuple(ruleset.setup_sequence.steps),
        battle_phase_sequence=tuple(ruleset.battle_phase_sequence.phases),
        player_ids=("player-a", "player-b"),
        turn_order=("player-a", "player-b"),
        tactical_secondary_draw_count=2,
        setup_step_index=None,
        battle_phase_index=tuple(ruleset.battle_phase_sequence.phases).index(BattlePhase.MOVEMENT),
        battle_round=1,
        active_player_id="player-a",
        army_definitions=list(scenario.armies),
        battlefield_state=scenario.battlefield_state,
    )


def _army_muster_request(
    *,
    catalog: ArmyCatalog,
    player_id: str,
    army_id: str,
    unit_selections: tuple[UnitMusterSelection, ...],
) -> ArmyMusterRequest:
    return ArmyMusterRequest(
        army_id=army_id,
        player_id=player_id,
        catalog_id=catalog.catalog_id,
        source_package_id=catalog.source_package_id,
        ruleset_id=catalog.ruleset_id,
        detachment_selection=DetachmentSelection(
            faction_id="core-marine-force",
            detachment_id="core-combined-arms",
        ),
        unit_selections=unit_selections,
    )


def _unit_selection(
    *,
    unit_selection_id: str,
    datasheet_id: str,
    model_profile_id: str,
    model_count: int,
) -> UnitMusterSelection:
    return UnitMusterSelection(
        unit_selection_id=unit_selection_id,
        datasheet_id=datasheet_id,
        model_profile_selections=(
            ModelProfileSelection(
                model_profile_id=model_profile_id,
                model_count=model_count,
            ),
        ),
    )


def _cargo_state(
    *,
    transport: UnitInstance,
    embarked_unit_ids: tuple[str, ...] = (),
    started_unit_ids: tuple[str, ...] = (),
    disembarked_unit_ids: tuple[str, ...] = (),
    battle_round: int | None = None,
) -> TransportCargoState:
    return TransportCargoState(
        player_id="player-a",
        transport_unit_instance_id=transport.unit_instance_id,
        capacity_profile=TransportCapacityProfile(
            transport_datasheet_id=transport.datasheet_id,
            max_model_count=10,
            allowed_keywords=("INFANTRY",),
        ),
        embarked_unit_instance_ids=embarked_unit_ids,
        phase_battle_round=battle_round,
        started_phase_embarked_unit_instance_ids=started_unit_ids,
        disembarked_this_phase_unit_instance_ids=disembarked_unit_ids,
    )


def _without_unit(scenario: BattlefieldScenario, unit_instance_id: str) -> BattlefieldScenario:
    return BattlefieldScenario(
        armies=scenario.armies,
        battlefield_state=scenario.battlefield_state.without_unit_placement(unit_instance_id),
    )


def _unit_placement_at(
    unit: UnitInstance,
    *,
    army_id: str,
    player_id: str,
    poses: tuple[Pose, ...],
) -> UnitPlacement:
    if len(poses) > len(unit.own_models):
        raise AssertionError("Test placement has too many poses.")
    return UnitPlacement(
        army_id=army_id,
        player_id=player_id,
        unit_instance_id=unit.unit_instance_id,
        model_placements=tuple(
            ModelPlacement(
                army_id=army_id,
                player_id=player_id,
                unit_instance_id=unit.unit_instance_id,
                model_instance_id=model.model_instance_id,
                pose=pose,
            )
            for model, pose in zip(unit.own_models, poses, strict=False)
        ),
    )


def _shift_witness(
    unit_placement: UnitPlacement,
    *,
    dx: float,
    dy: float = 0.0,
) -> PathWitness:
    model_paths: list[tuple[str, tuple[Pose, ...]]] = []
    for placement in unit_placement.model_placements:
        start = placement.pose
        end = Pose.at(
            start.position.x + dx,
            start.position.y + dy,
            start.position.z,
            facing_degrees=start.facing.degrees,
        )
        midpoint = Pose.at(
            start.position.x + (dx / 2.0),
            start.position.y + (dy / 2.0),
            start.position.z,
            facing_degrees=start.facing.degrees,
        )
        model_paths.append((placement.model_instance_id, (start, midpoint, end)))
    return PathWitness.for_paths(tuple(model_paths))


def _disembark_poses(*, z_inches: float = 0.0) -> tuple[Pose, ...]:
    return (
        Pose.at(13.1, 8.5, z_inches),
        Pose.at(14.0, 9.8, z_inches),
        Pose.at(14.0, 11.2, z_inches),
        Pose.at(13.1, 12.5, z_inches),
        Pose.at(12.8, 10.5, z_inches),
    )


def _support_feature(
    *,
    feature_id: str,
    feature_kind: TerrainFeatureKind,
    center_x_inches: float,
    center_y_inches: float,
    z_inches: float,
    width_inches: float,
    depth_inches: float,
) -> TerrainFeatureDefinition:
    return TerrainFeatureDefinition(
        feature_id=feature_id,
        feature_kind=feature_kind,
        footprint_center_x_inches=center_x_inches,
        footprint_center_y_inches=center_y_inches,
        footprint_width_inches=width_inches,
        footprint_depth_inches=depth_inches,
        floors=(
            TerrainFloorDefinition(
                floor_id="top",
                center_x_inches=center_x_inches,
                center_y_inches=center_y_inches,
                bottom_z_inches=z_inches,
                width_inches=width_inches,
                depth_inches=depth_inches,
                thickness_inches=0.12,
            ),
        ),
    )


def _ruins_floor_feature(
    *,
    feature_id: str,
    center_x_inches: float,
    center_y_inches: float,
    upper_width_inches: float,
    upper_depth_inches: float,
) -> TerrainFeatureDefinition:
    return TerrainFeatureDefinition(
        feature_id=feature_id,
        feature_kind=TerrainFeatureKind.RUINS,
        footprint_center_x_inches=center_x_inches,
        footprint_center_y_inches=center_y_inches,
        footprint_width_inches=6.0,
        footprint_depth_inches=6.0,
        walls=(
            TerrainWallDefinition(
                wall_id="north-wall",
                center_x_inches=center_x_inches,
                center_y_inches=center_y_inches + 2.94,
                bottom_z_inches=0.0,
                width_inches=6.0,
                depth_inches=0.12,
                height_inches=3.0,
            ),
        ),
        floors=(
            TerrainFloorDefinition(
                floor_id="ground",
                center_x_inches=center_x_inches,
                center_y_inches=center_y_inches,
                bottom_z_inches=0.0,
                width_inches=6.0,
                depth_inches=6.0,
                thickness_inches=0.12,
            ),
            TerrainFloorDefinition(
                floor_id="upper",
                center_x_inches=center_x_inches,
                center_y_inches=center_y_inches,
                bottom_z_inches=3.0,
                width_inches=upper_width_inches,
                depth_inches=upper_depth_inches,
                thickness_inches=0.12,
            ),
        ),
    )


def _first_weapon_profile(catalog: ArmyCatalog, unit: UnitInstance) -> WeaponProfile:
    wargear_id = unit.wargear_selections[0].wargear_ids[0]
    wargear = _wargear_by_id(catalog, wargear_id)
    return wargear.weapon_profiles[0]


def _wargear_by_id(catalog: ArmyCatalog, wargear_id: str) -> Wargear:
    for wargear in catalog.wargear:
        if wargear.wargear_id == wargear_id:
            return wargear
    raise AssertionError(f"Missing test wargear: {wargear_id}")
