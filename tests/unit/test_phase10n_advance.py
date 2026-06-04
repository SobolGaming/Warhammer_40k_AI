from __future__ import annotations

import json
from dataclasses import replace
from typing import cast

import pytest
from tests.movement_submission_helpers import submit_default_movement_proposal_if_pending

from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.core.dice import (
    DiceExpression,
    DiceRollSpec,
    DiceRollState,
    RerollComponentSelectionPolicy,
    RerollPermission,
)
from warhammer40k_core.core.ruleset_descriptor import RulesetDescriptor
from warhammer40k_core.engine.army_mustering import ArmyDefinition, ArmyMusterRequest, muster_army
from warhammer40k_core.engine.battlefield_state import (
    BattlefieldScenario,
    BattlefieldTransitionBatch,
    BattlefieldTransitionBatchPayload,
    ModelDisplacementKind,
)
from warhammer40k_core.engine.decision import DiceRollManager
from warhammer40k_core.engine.decision_request import (
    PARAMETERIZED_DECISION_OPTION_ID,
    DecisionRequest,
)
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.dice import DICE_REROLL_DECISION_TYPE
from warhammer40k_core.engine.game_state import GameConfig, GameState
from warhammer40k_core.engine.lifecycle import GameLifecycle, GameLifecyclePayload
from warhammer40k_core.engine.list_validation import (
    DetachmentSelection,
    ModelProfileSelection,
    UnitMusterSelection,
)
from warhammer40k_core.engine.mission_setup import MissionSetup
from warhammer40k_core.engine.phase import (
    BattlePhase,
    GameLifecycleError,
    LifecycleStatus,
    LifecycleStatusKind,
)
from warhammer40k_core.engine.phases.movement import (
    SELECT_MOVEMENT_ACTION_DECISION_TYPE,
    SELECT_MOVEMENT_UNIT_DECISION_TYPE,
    AdvancedUnitState,
    AdvancedUnitStatePayload,
    AdvanceRollRequest,
    AdvanceRollResult,
    AdvanceRollResultPayload,
    MovementDiceRecord,
    MovementPhaseActionKind,
    MovementPhaseStepKind,
    resolve_advance_move,
)
from warhammer40k_core.engine.placement import create_deterministic_battlefield_scenario
from warhammer40k_core.engine.setup_flow import SECONDARY_MISSION_DECISION_TYPE
from warhammer40k_core.engine.stratagems import (
    STRATAGEM_TARGET_PROPOSAL_DECISION_TYPE,
    stratagem_decline_payload,
)
from warhammer40k_core.engine.unit_factory import UnitInstance
from warhammer40k_core.geometry.pose import Pose
from warhammer40k_core.rules.mission_pack_import import chapter_approved_2025_26_mission_pack


def test_advance_roll_and_advanced_state_payloads_round_trip_without_object_reprs() -> None:
    request = AdvanceRollRequest.for_unit(
        request_id="phase10n-advance-roll",
        game_id="phase10n-game",
        battle_round=1,
        player_id="player-a",
        unit_instance_id="army-alpha:intercessor-unit-1",
    )
    roll_state = DiceRollManager("phase10n-game").roll_fixed(request.spec, [4])
    roll = AdvanceRollResult.from_roll_state(request=request, roll_state=roll_state)
    dice_record = MovementDiceRecord(
        player_id="player-a",
        battle_round=1,
        unit_instance_id="army-alpha:intercessor-unit-1",
        movement_phase_action=MovementPhaseActionKind.ADVANCE,
        advance_roll=roll,
    )
    advanced_state = AdvancedUnitState(
        player_id="player-a",
        battle_round=1,
        unit_instance_id="army-alpha:intercessor-unit-1",
        movement_dice_record=dice_record,
    )

    roll_payload = cast(
        AdvanceRollResultPayload,
        json.loads(json.dumps(roll.to_payload(), sort_keys=True)),
    )
    state_payload = cast(
        AdvancedUnitStatePayload,
        json.loads(json.dumps(advanced_state.to_payload(), sort_keys=True)),
    )
    blob = json.dumps({"roll": roll_payload, "state": state_payload}, sort_keys=True)

    assert "<" not in blob
    assert "object at 0x" not in blob
    assert AdvanceRollResult.from_payload(roll_payload) == roll
    assert AdvancedUnitState.from_payload(state_payload) == advanced_state
    assert not advanced_state.can_shoot
    assert not advanced_state.can_declare_charge


def test_advance_move_consumes_movement_plus_d6() -> None:
    scenario = _scenario()
    unit_placement = scenario.battlefield_state.unit_placement_by_id(
        "army-alpha:intercessor-unit-1"
    )
    advance_roll = _fixed_advance_roll(value=4)

    resolution = resolve_advance_move(
        scenario=scenario,
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(),
        unit_placement=unit_placement,
        advance_roll=advance_roll,
    )

    assert resolution.is_valid
    assert resolution.movement_payload["movement_inches"] == 10.0
    for before, after in zip(
        unit_placement.model_placements,
        resolution.attempted_placement.model_placements,
        strict=True,
    ):
        assert after.pose.position.x == before.pose.position.x + 10.0
        assert after.pose.position.y == before.pose.position.y
    first_distance = resolution.path_validation_results[0].movement_distance_witness
    assert first_distance is not None
    assert first_distance.total_distance_inches == 10.0
    assert first_distance.is_within_budget


def test_lifecycle_advance_roll_is_deterministic_replay_facing_and_marks_restrictions() -> None:
    left = _advance_first_unit()
    right = _advance_first_unit()
    left_state = _state(left)
    right_state = _state(right)
    left_advanced = left_state.advanced_unit_state_for_unit(
        player_id="player-a",
        battle_round=1,
        unit_instance_id="army-alpha:intercessor-unit-1",
    )
    right_advanced = right_state.advanced_unit_state_for_unit(
        player_id="player-a",
        battle_round=1,
        unit_instance_id="army-alpha:intercessor-unit-1",
    )

    assert left_advanced is not None
    assert right_advanced is not None
    assert left_advanced.to_payload() == right_advanced.to_payload()
    assert not left_advanced.can_shoot
    assert not left_advanced.can_declare_charge

    event_types = tuple(event.event_type for event in left.decision_controller.event_log.records)
    assert "advance_roll_requested" in event_types
    assert "dice_rolled" in event_types
    assert "advance_roll_resolved" in event_types
    terminal_event = _last_event_payload(left, "movement_activation_completed")
    batch = _transition_batch_from_event_payload(terminal_event)

    assert terminal_event["movement_phase_action"] == MovementPhaseActionKind.ADVANCE.value
    assert terminal_event["displacement_kind"] == ModelDisplacementKind.ADVANCE.value
    assert terminal_event["advance_roll"] == (
        left_advanced.movement_dice_record.advance_roll.to_payload()
    )
    assert batch.displacements
    assert all(
        displacement.displacement_kind is ModelDisplacementKind.ADVANCE
        for displacement in batch.displacements
    )
    assert all(
        displacement.source_phase == BattlePhase.MOVEMENT.value
        and displacement.source_step == MovementPhaseStepKind.MOVE_UNITS.value
        for displacement in batch.displacements
    )
    payload = _payload_copy(left)
    assert GameLifecycle.from_payload(payload).to_payload() == left.to_payload()


def test_lifecycle_payload_rejects_advanced_state_drift() -> None:
    lifecycle = _advance_first_unit()
    player_drift = _payload_copy(lifecycle)
    _retarget_advanced_state_payload(
        player_drift,
        player_id="player-b",
        battle_round=1,
        unit_instance_id="army-alpha:intercessor-unit-1",
    )
    round_drift = _payload_copy(lifecycle)
    _retarget_advanced_state_payload(
        round_drift,
        player_id="player-a",
        battle_round=2,
        unit_instance_id="army-alpha:intercessor-unit-1",
    )
    unit_drift = _payload_copy(lifecycle)
    _retarget_advanced_state_payload(
        unit_drift,
        player_id="player-a",
        battle_round=1,
        unit_instance_id="army-beta:intercessor-unit-3",
    )

    for payload, message in (
        (player_drift, "player drift"),
        (round_drift, "battle round drift"),
        (unit_drift, "active player's unit"),
    ):
        with pytest.raises(GameLifecycleError, match=message):
            GameLifecycle.from_payload(payload)


def test_advance_reroll_request_appears_only_with_legal_reroll_source() -> None:
    lifecycle, action_request = _advance_to_movement_action_request()
    no_reroll_status = _submit_result(
        lifecycle,
        request=action_request,
        option_id=MovementPhaseActionKind.ADVANCE.value,
        result_id="phase10n-result-000004",
    )
    no_reroll_status = _decline_optional_stratagem_if_pending(
        lifecycle,
        status=no_reroll_status,
        result_id="phase10n-decline-fire-overwatch-no-reroll",
    )

    assert _decision_request(no_reroll_status).decision_type == SELECT_MOVEMENT_UNIT_DECISION_TYPE

    reroll_lifecycle, movement_status = _advance_to_movement_unit_selection(_config())
    _grant_first_unit_advance_reroll(reroll_lifecycle)
    selected_status = _submit_result(
        reroll_lifecycle,
        request=_decision_request(movement_status),
        option_id="army-alpha:intercessor-unit-1",
        result_id="phase10n-result-000003",
    )
    reroll_action_request = _decision_request(selected_status)

    pending_reroll = _submit_result(
        reroll_lifecycle,
        request=reroll_action_request,
        option_id=MovementPhaseActionKind.ADVANCE.value,
        result_id="phase10n-result-000004",
    )
    reroll_request = _decision_request(pending_reroll)

    assert reroll_request.decision_type == DICE_REROLL_DECISION_TYPE
    assert tuple(option.option_id for option in reroll_request.options) == ("decline", "reroll:0")
    assert isinstance(reroll_request.payload, dict)
    assert reroll_request.payload["permission"] is not None

    follow_up = _submit_result(
        reroll_lifecycle,
        request=reroll_request,
        option_id="reroll:0",
        result_id="phase10n-result-000005",
    )
    advanced = _state(reroll_lifecycle).advanced_unit_state_for_unit(
        player_id="player-a",
        battle_round=1,
        unit_instance_id="army-alpha:intercessor-unit-1",
    )

    assert _decision_request(follow_up).decision_type == SELECT_MOVEMENT_UNIT_DECISION_TYPE
    assert advanced is not None
    assert advanced.movement_dice_record.advance_roll.roll_state.rerolls


def test_advance_roll_resolved_event_uses_final_rerolled_value() -> None:
    lifecycle, movement_status = _advance_to_movement_unit_selection(_config())
    _grant_first_unit_advance_reroll(lifecycle)
    selected_status = _submit_result(
        lifecycle,
        request=_decision_request(movement_status),
        option_id="army-alpha:intercessor-unit-1",
        result_id="phase10n-result-000003",
    )
    pending_reroll = _submit_result(
        lifecycle,
        request=_decision_request(selected_status),
        option_id=MovementPhaseActionKind.ADVANCE.value,
        result_id="phase10n-result-000004",
    )
    reroll_request = _decision_request(pending_reroll)
    reroll_payload = cast(dict[str, object], reroll_request.payload)
    movement_context = cast(dict[str, object], reroll_payload["movement_context"])
    initial_roll_state_payload = cast(dict[str, object], movement_context["advance_roll_state"])

    assert _event_payloads(lifecycle, "advance_roll_resolved") == ()

    _submit_result(
        lifecycle,
        request=reroll_request,
        option_id="reroll:0",
        result_id="phase10n-result-000005",
    )
    advanced = _state(lifecycle).advanced_unit_state_for_unit(
        player_id="player-a",
        battle_round=1,
        unit_instance_id="army-alpha:intercessor-unit-1",
    )
    resolved_payloads = _event_payloads(lifecycle, "advance_roll_resolved")

    assert advanced is not None
    assert len(resolved_payloads) == 1
    assert resolved_payloads[0]["advance_roll"] == (
        advanced.movement_dice_record.advance_roll.to_payload()
    )
    assert advanced.movement_dice_record.advance_roll.roll_state.rerolls
    final_advance_roll_payload = cast(dict[str, object], resolved_payloads[0]["advance_roll"])
    assert final_advance_roll_payload["roll_state"] != initial_roll_state_payload
    assert _first_event_index(lifecycle, "dice_reroll_resolved") < _first_event_index(
        lifecycle,
        "advance_roll_resolved",
    )


def test_advance_roll_resolved_event_after_reroll_decline_matches_original_value() -> None:
    lifecycle, movement_status = _advance_to_movement_unit_selection(_config())
    _grant_first_unit_advance_reroll(lifecycle)
    selected_status = _submit_result(
        lifecycle,
        request=_decision_request(movement_status),
        option_id="army-alpha:intercessor-unit-1",
        result_id="phase10n-result-000003",
    )
    pending_reroll = _submit_result(
        lifecycle,
        request=_decision_request(selected_status),
        option_id=MovementPhaseActionKind.ADVANCE.value,
        result_id="phase10n-result-000004",
    )
    reroll_request = _decision_request(pending_reroll)
    reroll_payload = cast(dict[str, object], reroll_request.payload)
    movement_context = cast(dict[str, object], reroll_payload["movement_context"])
    initial_roll_state_payload = cast(dict[str, object], movement_context["advance_roll_state"])
    original_values = tuple(cast(list[int], reroll_payload["current_values"]))

    assert _event_payloads(lifecycle, "advance_roll_resolved") == ()

    _submit_result(
        lifecycle,
        request=reroll_request,
        option_id="decline",
        result_id="phase10n-result-000005",
    )
    advanced = _state(lifecycle).advanced_unit_state_for_unit(
        player_id="player-a",
        battle_round=1,
        unit_instance_id="army-alpha:intercessor-unit-1",
    )
    resolved_payloads = _event_payloads(lifecycle, "advance_roll_resolved")

    assert advanced is not None
    assert len(resolved_payloads) == 1
    assert resolved_payloads[0]["advance_roll"] == (
        advanced.movement_dice_record.advance_roll.to_payload()
    )
    assert advanced.movement_dice_record.advance_roll.roll_state.current_values == original_values
    assert advanced.movement_dice_record.advance_roll.roll_state.rerolls == ()
    final_advance_roll_payload = cast(dict[str, object], resolved_payloads[0]["advance_roll"])
    assert final_advance_roll_payload["roll_state"] == initial_roll_state_payload
    assert _first_event_index(lifecycle, "dice_reroll_declined") < _first_event_index(
        lifecycle,
        "advance_roll_resolved",
    )


def test_advance_reroll_decline_keeps_original_roll() -> None:
    lifecycle, movement_status = _advance_to_movement_unit_selection(_config())
    _grant_first_unit_advance_reroll(lifecycle)
    selected_status = _submit_result(
        lifecycle,
        request=_decision_request(movement_status),
        option_id="army-alpha:intercessor-unit-1",
        result_id="phase10n-result-000003",
    )
    action_request = _decision_request(selected_status)
    pending_reroll = _submit_result(
        lifecycle,
        request=action_request,
        option_id=MovementPhaseActionKind.ADVANCE.value,
        result_id="phase10n-result-000004",
    )
    reroll_request = _decision_request(pending_reroll)
    reroll_payload = cast(dict[str, object], reroll_request.payload)
    original_values = tuple(cast(list[int], reroll_payload["current_values"]))

    _submit_result(
        lifecycle,
        request=reroll_request,
        option_id="decline",
        result_id="phase10n-result-000005",
    )
    advanced = _state(lifecycle).advanced_unit_state_for_unit(
        player_id="player-a",
        battle_round=1,
        unit_instance_id="army-alpha:intercessor-unit-1",
    )

    assert advanced is not None
    assert advanced.movement_dice_record.advance_roll.roll_state.current_values == original_values
    assert advanced.movement_dice_record.advance_roll.roll_state.rerolls == ()
    assert "dice_reroll_declined" in {
        event.event_type for event in lifecycle.decision_controller.event_log.records
    }


def test_invalid_advance_does_not_mutate_battlefield_state() -> None:
    lifecycle, action_request = _advance_to_movement_action_request()
    state = _state(lifecycle)
    assert state.battlefield_state is not None
    selected = state.battlefield_state.unit_placement_by_id("army-alpha:intercessor-unit-1")
    near_edge = selected.with_model_placements(
        tuple(
            placement.with_pose(
                Pose.at(
                    x=58.0,
                    y=6.0 + index,
                    z=placement.pose.position.z,
                    facing_degrees=placement.pose.facing.degrees,
                )
            )
            for index, placement in enumerate(selected.model_placements)
        )
    )
    state.battlefield_state = state.battlefield_state.with_unit_placement(near_edge)
    before_payload = state.battlefield_state.to_payload()

    status = _submit_result(
        lifecycle,
        request=action_request,
        option_id=MovementPhaseActionKind.ADVANCE.value,
        result_id="phase10n-result-000004",
    )

    assert status.status_kind is LifecycleStatusKind.INVALID
    status_payload = cast(dict[str, object], status.payload)
    assert status_payload["movement_phase_action"] == MovementPhaseActionKind.ADVANCE.value
    assert status_payload["violation_code"] == "battlefield_edge_crossed"
    assert state.battlefield_state is not None
    assert state.battlefield_state.to_payload() == before_payload

    scenario = BattlefieldScenario(
        armies=tuple(state.army_definitions),
        battlefield_state=state.battlefield_state,
    )
    resolution = resolve_advance_move(
        scenario=scenario,
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(),
        unit_placement=near_edge,
        advance_roll=_fixed_advance_roll(value=1),
    )
    with pytest.raises(GameLifecycleError, match="Invalid Advance"):
        resolution.transition_batch(before=near_edge)


def test_advanced_state_clears_at_end_of_active_player_turn() -> None:
    lifecycle, action_request = _advance_to_movement_action_request()
    next_status = _submit_result(
        lifecycle,
        request=action_request,
        option_id=MovementPhaseActionKind.ADVANCE.value,
        result_id="phase10n-result-000004",
    )
    next_status = _decline_optional_stratagem_if_pending(
        lifecycle,
        status=next_status,
        result_id="phase10n-decline-fire-overwatch",
    )
    second_unit_status = _submit_result(
        lifecycle,
        request=_decision_request(next_status),
        option_id="army-alpha:intercessor-unit-2",
        result_id="phase10n-result-000005",
    )
    action_status = _submit_result(
        lifecycle,
        request=_decision_request(second_unit_status),
        option_id=MovementPhaseActionKind.REMAIN_STATIONARY.value,
        result_id="phase10n-result-000006",
    )
    action_status = _decline_optional_stratagem_if_pending(
        lifecycle,
        status=action_status,
        result_id="phase10n-decline-end-movement-fire-overwatch",
    )

    assert action_status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    status_payload = cast(dict[str, object], action_status.payload)
    assert status_payload["phase"] == "shooting"
    state = _state(lifecycle)
    assert state.current_battle_phase is BattlePhase.SHOOTING
    assert state.advanced_unit_states

    state.advance_to_next_battle_phase()
    state.advance_to_next_battle_phase()
    state.advance_to_next_battle_phase()

    updated_state = _state(lifecycle)
    assert updated_state.active_player_id == "player-b"
    assert updated_state.current_battle_phase is BattlePhase.COMMAND
    assert updated_state.advanced_unit_states == []
    assert updated_state.movement_phase_state is None


def test_advance_domain_objects_fail_fast_on_drift() -> None:
    request = AdvanceRollRequest.for_unit(
        request_id="phase10n-validation-roll",
        game_id="phase10n-game",
        battle_round=1,
        player_id="player-a",
        unit_instance_id="army-alpha:intercessor-unit-1",
    )
    roll_state = DiceRollManager("phase10n-game").roll_fixed(request.spec, [3])
    roll = AdvanceRollResult.from_roll_state(request=request, roll_state=roll_state)
    dice_record = MovementDiceRecord(
        player_id="player-a",
        battle_round=1,
        unit_instance_id="army-alpha:intercessor-unit-1",
        movement_phase_action=MovementPhaseActionKind.ADVANCE,
        advance_roll=roll,
    )

    with pytest.raises(GameLifecycleError, match="spec"):
        AdvanceRollRequest(
            request_id="bad",
            game_id="phase10n-game",
            battle_round=1,
            player_id="player-a",
            unit_instance_id="army-alpha:intercessor-unit-1",
            spec=cast(DiceRollSpec, "bad"),
        )
    with pytest.raises(GameLifecycleError, match="unmodified D6"):
        AdvanceRollRequest(
            request_id="bad",
            game_id="phase10n-game",
            battle_round=1,
            player_id="player-a",
            unit_instance_id="army-alpha:intercessor-unit-1",
            spec=DiceRollSpec(
                expression=DiceExpression(quantity=2, sides=6),
                reason="Advance validation",
                roll_type="advance_roll",
                actor_id="army-alpha:intercessor-unit-1",
            ),
        )
    with pytest.raises(GameLifecycleError, match="owner"):
        AdvanceRollRequest.for_unit(
            request_id="bad-owner",
            game_id="phase10n-game",
            battle_round=1,
            player_id="player-a",
            unit_instance_id="army-alpha:intercessor-unit-1",
            reroll_permission=RerollPermission(
                source_id="bad-owner",
                timing_window="after_roll_before_modifiers",
                owning_player_id="player-b",
                eligible_roll_type="advance_roll",
                component_selection_policy=RerollComponentSelectionPolicy.WHOLE_ROLL,
            ),
        )
    with pytest.raises(GameLifecycleError, match="target"):
        AdvanceRollRequest.for_unit(
            request_id="bad-target",
            game_id="phase10n-game",
            battle_round=1,
            player_id="player-a",
            unit_instance_id="army-alpha:intercessor-unit-1",
            reroll_permission=RerollPermission(
                source_id="bad-target",
                timing_window="after_roll_before_modifiers",
                owning_player_id="player-a",
                eligible_roll_type="charge_roll",
                component_selection_policy=RerollComponentSelectionPolicy.WHOLE_ROLL,
            ),
        )
    with pytest.raises(GameLifecycleError, match="value"):
        AdvanceRollResult(request=request, roll_state=roll_state, value=4)
    with pytest.raises(GameLifecycleError, match="request"):
        AdvanceRollResult(
            request=cast(AdvanceRollRequest, "bad"),
            roll_state=roll_state,
            value=roll_state.current_total,
        )
    with pytest.raises(GameLifecycleError, match="roll_state"):
        AdvanceRollResult(
            request=request,
            roll_state=cast(DiceRollState, "bad"),
            value=roll_state.current_total,
        )
    other_request = AdvanceRollRequest.for_unit(
        request_id="phase10n-other-roll",
        game_id="phase10n-game",
        battle_round=1,
        player_id="player-a",
        unit_instance_id="army-alpha:intercessor-unit-2",
    )
    with pytest.raises(GameLifecycleError, match="spec"):
        AdvanceRollResult(
            request=other_request,
            roll_state=roll_state,
            value=roll_state.current_total,
        )
    with pytest.raises(GameLifecycleError, match="only Advance"):
        MovementDiceRecord(
            player_id="player-a",
            battle_round=1,
            unit_instance_id="army-alpha:intercessor-unit-1",
            movement_phase_action=MovementPhaseActionKind.NORMAL_MOVE,
            advance_roll=roll,
        )
    with pytest.raises(GameLifecycleError, match="player_id drift"):
        MovementDiceRecord(
            player_id="player-b",
            battle_round=1,
            unit_instance_id="army-alpha:intercessor-unit-1",
            movement_phase_action=MovementPhaseActionKind.ADVANCE,
            advance_roll=roll,
        )
    with pytest.raises(GameLifecycleError, match="battle_round drift"):
        MovementDiceRecord(
            player_id="player-a",
            battle_round=2,
            unit_instance_id="army-alpha:intercessor-unit-1",
            movement_phase_action=MovementPhaseActionKind.ADVANCE,
            advance_roll=roll,
        )
    with pytest.raises(GameLifecycleError, match="unit_instance_id drift"):
        MovementDiceRecord(
            player_id="player-a",
            battle_round=1,
            unit_instance_id="army-alpha:other",
            movement_phase_action=MovementPhaseActionKind.ADVANCE,
            advance_roll=roll,
        )
    with pytest.raises(GameLifecycleError, match="advance_roll"):
        MovementDiceRecord(
            player_id="player-a",
            battle_round=1,
            unit_instance_id="army-alpha:intercessor-unit-1",
            movement_phase_action=MovementPhaseActionKind.ADVANCE,
            advance_roll=cast(AdvanceRollResult, "bad"),
        )
    with pytest.raises(GameLifecycleError, match="movement_dice_record"):
        AdvancedUnitState(
            player_id="player-a",
            battle_round=1,
            unit_instance_id="army-alpha:intercessor-unit-1",
            movement_dice_record=cast(MovementDiceRecord, "bad"),
        )
    with pytest.raises(GameLifecycleError, match="player_id drift"):
        AdvancedUnitState(
            player_id="player-b",
            battle_round=1,
            unit_instance_id="army-alpha:intercessor-unit-1",
            movement_dice_record=dice_record,
        )
    with pytest.raises(GameLifecycleError, match="battle_round drift"):
        AdvancedUnitState(
            player_id="player-a",
            battle_round=2,
            unit_instance_id="army-alpha:intercessor-unit-1",
            movement_dice_record=dice_record,
        )
    with pytest.raises(GameLifecycleError, match="unit drift"):
        AdvancedUnitState(
            player_id="player-a",
            battle_round=1,
            unit_instance_id="army-alpha:other",
            movement_dice_record=dice_record,
        )
    with pytest.raises(GameLifecycleError, match="can_shoot"):
        AdvancedUnitState(
            player_id="player-a",
            battle_round=1,
            unit_instance_id="army-alpha:intercessor-unit-1",
            movement_dice_record=dice_record,
            can_shoot=cast(bool, "yes"),
        )
    with pytest.raises(GameLifecycleError, match="can_declare_charge"):
        AdvancedUnitState(
            player_id="player-a",
            battle_round=1,
            unit_instance_id="army-alpha:intercessor-unit-1",
            movement_dice_record=dice_record,
            can_declare_charge=cast(bool, "yes"),
        )
    with pytest.raises(GameLifecycleError, match="cleanup_point"):
        AdvancedUnitState(
            player_id="player-a",
            battle_round=1,
            unit_instance_id="army-alpha:intercessor-unit-1",
            movement_dice_record=dice_record,
            cleanup_point="start_of_next_turn",
        )


def _advance_first_unit() -> GameLifecycle:
    lifecycle, action_request = _advance_to_movement_action_request()
    _submit_result(
        lifecycle,
        request=action_request,
        option_id=MovementPhaseActionKind.ADVANCE.value,
        result_id="phase10n-result-000004",
    )
    return lifecycle


def _fixed_advance_roll(*, value: int) -> AdvanceRollResult:
    request = AdvanceRollRequest.for_unit(
        request_id="phase10n-fixed-advance-roll",
        game_id="phase10n-game",
        battle_round=1,
        player_id="player-a",
        unit_instance_id="army-alpha:intercessor-unit-1",
    )
    roll_state: DiceRollState = DiceRollManager("phase10n-game").roll_fixed(request.spec, [value])
    return AdvanceRollResult.from_roll_state(request=request, roll_state=roll_state)


def _advance_to_movement_unit_selection(
    config: GameConfig,
) -> tuple[GameLifecycle, LifecycleStatus]:
    lifecycle = GameLifecycle()
    lifecycle.start(config)
    first_status = lifecycle.advance_until_decision_or_terminal()
    assert _decision_request(first_status).decision_type == SECONDARY_MISSION_DECISION_TYPE
    second_status = _submit_result(
        lifecycle,
        request=_decision_request(first_status),
        option_id="fixed:assassination:bring_it_down",
        result_id="phase10n-result-000001",
    )
    assert _decision_request(second_status).decision_type == SECONDARY_MISSION_DECISION_TYPE
    movement_status = _submit_result(
        lifecycle,
        request=_decision_request(second_status),
        option_id="fixed:assassination:bring_it_down",
        result_id="phase10n-result-000002",
    )
    assert _decision_request(movement_status).decision_type == SELECT_MOVEMENT_UNIT_DECISION_TYPE
    return lifecycle, movement_status


def _advance_to_movement_action_request() -> tuple[GameLifecycle, DecisionRequest]:
    lifecycle, movement_status = _advance_to_movement_unit_selection(_config())
    action_status = _submit_result(
        lifecycle,
        request=_decision_request(movement_status),
        option_id="army-alpha:intercessor-unit-1",
        result_id="phase10n-result-000003",
    )
    action_request = _decision_request(action_status)
    assert action_request.decision_type == SELECT_MOVEMENT_ACTION_DECISION_TYPE
    return lifecycle, action_request


def _submit_result(
    lifecycle: GameLifecycle,
    *,
    request: DecisionRequest,
    option_id: str,
    result_id: str,
) -> LifecycleStatus:
    status = lifecycle.submit_decision(
        DecisionResult.for_request(
            result_id=result_id,
            request=request,
            selected_option_id=option_id,
        )
    )
    return submit_default_movement_proposal_if_pending(
        lifecycle,
        status,
        result_id=f"{result_id}-proposal",
    )


def _decline_optional_stratagem_if_pending(
    lifecycle: GameLifecycle,
    *,
    status: LifecycleStatus,
    result_id: str,
) -> LifecycleStatus:
    request = _decision_request(status)
    if request.decision_type != STRATAGEM_TARGET_PROPOSAL_DECISION_TYPE:
        return status
    return lifecycle.submit_decision(
        DecisionResult(
            result_id=result_id,
            request_id=request.request_id,
            decision_type=STRATAGEM_TARGET_PROPOSAL_DECISION_TYPE,
            actor_id=request.actor_id,
            selected_option_id=PARAMETERIZED_DECISION_OPTION_ID,
            payload=stratagem_decline_payload(),
        )
    )


def _decision_request(status: LifecycleStatus) -> DecisionRequest:
    assert status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    assert status.decision_request is not None
    return status.decision_request


def _state(lifecycle: GameLifecycle) -> GameState:
    assert lifecycle.state is not None
    return lifecycle.state


def _payload_copy(lifecycle: GameLifecycle) -> GameLifecyclePayload:
    return cast(
        GameLifecyclePayload,
        json.loads(json.dumps(lifecycle.to_payload(), sort_keys=True)),
    )


def _retarget_advanced_state_payload(
    payload: GameLifecyclePayload,
    *,
    player_id: str,
    battle_round: int,
    unit_instance_id: str,
) -> None:
    advanced_state = payload["state"]["advanced_unit_states"][0]
    dice_record = advanced_state["movement_dice_record"]
    advance_roll = dice_record["advance_roll"]
    advance_request = advance_roll["request"]
    roll_state_spec = advance_roll["roll_state"]["original_result"]["spec"]
    advanced_state["player_id"] = player_id
    advanced_state["battle_round"] = battle_round
    advanced_state["unit_instance_id"] = unit_instance_id
    dice_record["player_id"] = player_id
    dice_record["battle_round"] = battle_round
    dice_record["unit_instance_id"] = unit_instance_id
    advance_request["player_id"] = player_id
    advance_request["battle_round"] = battle_round
    advance_request["unit_instance_id"] = unit_instance_id
    advance_request["spec"]["reason"] = f"Advance roll for {unit_instance_id}"
    advance_request["spec"]["actor_id"] = unit_instance_id
    roll_state_spec["reason"] = f"Advance roll for {unit_instance_id}"
    roll_state_spec["actor_id"] = unit_instance_id


def _scenario() -> BattlefieldScenario:
    config = _config()
    return create_deterministic_battlefield_scenario(
        battlefield_id="phase10n-battlefield",
        armies=tuple(
            muster_army(catalog=config.army_catalog, request=request)
            for request in config.army_muster_requests
        ),
    )


def _config() -> GameConfig:
    catalog = ArmyCatalog.phase9a_canonical_content_pack()
    return GameConfig(
        game_id="phase10n-game",
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(
            descriptor_version="core-v2-phase10n-test"
        ),
        army_catalog=catalog,
        army_muster_requests=(
            _army_muster_request(
                catalog=catalog,
                player_id="player-a",
                army_id="army-alpha",
                unit_selection_ids=("intercessor-unit-1", "intercessor-unit-2"),
            ),
            _army_muster_request(
                catalog=catalog,
                player_id="player-b",
                army_id="army-beta",
                unit_selection_ids=("intercessor-unit-3",),
            ),
        ),
        player_ids=("player-a", "player-b"),
        turn_order=("player-a", "player-b"),
        fixed_secondary_mission_ids=("assassination", "bring_it_down", "cleanse"),
        mission_setup=_mission_setup(),
    )


def _mission_setup() -> MissionSetup:
    return MissionSetup.from_mission_pack(
        mission_pack=chapter_approved_2025_26_mission_pack(),
        mission_pool_entry_id="mission-a",
        terrain_layout_id="layout-1",
        attacker_player_id="player-a",
        defender_player_id="player-b",
    )


def _army_muster_request(
    *,
    catalog: ArmyCatalog,
    player_id: str,
    army_id: str,
    unit_selection_ids: tuple[str, ...],
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
        unit_selections=tuple(
            _unit_selection(unit_selection_id=unit_selection_id)
            for unit_selection_id in unit_selection_ids
        ),
    )


def _unit_selection(*, unit_selection_id: str) -> UnitMusterSelection:
    return UnitMusterSelection(
        unit_selection_id=unit_selection_id,
        datasheet_id="core-intercessor-like-infantry",
        model_profile_selections=(
            ModelProfileSelection(
                model_profile_id="core-intercessor-like",
                model_count=5,
            ),
        ),
    )


def _grant_first_unit_advance_reroll(lifecycle: GameLifecycle) -> None:
    state = _state(lifecycle)
    updated_armies: list[ArmyDefinition] = []
    for army in state.army_definitions:
        updated_units = tuple(
            _unit_with_advance_reroll(unit)
            if unit.unit_instance_id == "army-alpha:intercessor-unit-1"
            else unit
            for unit in army.units
        )
        updated_armies.append(replace(army, units=updated_units))
    state.army_definitions = updated_armies


def _unit_with_advance_reroll(unit: UnitInstance) -> UnitInstance:
    return replace(unit, keywords=(*unit.keywords, "ADVANCE_REROLL"))


def _last_event_payload(lifecycle: GameLifecycle, event_type: str) -> dict[str, object]:
    for event in reversed(lifecycle.decision_controller.event_log.records):
        if event.event_type == event_type:
            assert isinstance(event.payload, dict)
            return cast(dict[str, object], event.payload)
    raise AssertionError(f"Missing event type: {event_type}")


def _event_payloads(lifecycle: GameLifecycle, event_type: str) -> tuple[dict[str, object], ...]:
    payloads: list[dict[str, object]] = []
    for event in lifecycle.decision_controller.event_log.records:
        if event.event_type == event_type:
            assert isinstance(event.payload, dict)
            payloads.append(cast(dict[str, object], event.payload))
    return tuple(payloads)


def _first_event_index(lifecycle: GameLifecycle, event_type: str) -> int:
    for index, event in enumerate(lifecycle.decision_controller.event_log.records):
        if event.event_type == event_type:
            return index
    raise AssertionError(f"Missing event type: {event_type}")


def _transition_batch_from_event_payload(
    payload: dict[str, object],
) -> BattlefieldTransitionBatch:
    transition_payload = cast(BattlefieldTransitionBatchPayload, payload["transition_batch"])
    return BattlefieldTransitionBatch.from_payload(transition_payload)
