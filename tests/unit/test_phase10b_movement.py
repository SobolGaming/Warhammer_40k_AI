from __future__ import annotations

import json
from dataclasses import replace
from typing import cast

import pytest
from tests.movement_submission_helpers import (
    straight_line_witness_for_unit,
    submit_action_and_movement_proposal,
    submit_default_movement_proposal_if_pending,
)

from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.core.ruleset_descriptor import MovementMode, RulesetDescriptor
from warhammer40k_core.engine.army_mustering import ArmyDefinition, ArmyMusterRequest, muster_army
from warhammer40k_core.engine.battlefield_state import (
    BattlefieldPlacementKind,
    BattlefieldRemovalKind,
    BattlefieldScenario,
    ModelDisplacementKind,
)
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_request import (
    PARAMETERIZED_DECISION_OPTION_ID,
    DecisionRequest,
)
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.game_state import (
    GameConfig,
    GameState,
    SecondaryMissionChoice,
    SecondaryMissionMode,
)
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
    GameLifecycleStage,
    LifecycleStatus,
    LifecycleStatusKind,
)
from warhammer40k_core.engine.phases.movement import (
    SELECT_MOVEMENT_ACTION_DECISION_TYPE,
    SELECT_MOVEMENT_UNIT_DECISION_TYPE,
    MovementDistanceRecord,
    MovementPhaseActionKind,
    MovementPhaseHandler,
    MovementPhaseState,
    MovementPhaseStepKind,
    MovementUnitSelection,
    MovementUnitSelectionPayload,
)
from warhammer40k_core.engine.placement import create_deterministic_battlefield_scenario
from warhammer40k_core.engine.setup_flow import SECONDARY_MISSION_DECISION_TYPE
from warhammer40k_core.engine.stratagems import (
    STRATAGEM_TARGET_PROPOSAL_DECISION_TYPE,
    stratagem_decline_payload,
)
from warhammer40k_core.rules.mission_pack_import import chapter_approved_2026_27_mission_pack


def test_lifecycle_enters_movement_with_real_handler_and_placed_unit_options() -> None:
    lifecycle, status = _advance_to_movement_unit_selection(_config())

    assert status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    request = _decision_request(status)
    assert request.decision_type == SELECT_MOVEMENT_UNIT_DECISION_TYPE
    assert request.actor_id == "player-a"
    assert lifecycle.state is not None
    assert lifecycle.state.current_battle_phase is BattlePhase.MOVEMENT
    assert lifecycle.state.battlefield_state is not None
    assert lifecycle.state.movement_phase_state == MovementPhaseState(
        battle_round=1,
        active_player_id="player-a",
    )
    assert tuple(option.option_id for option in request.options) == (
        "army-alpha:intercessor-unit-1",
        "army-alpha:intercessor-unit-2",
    )
    assert all(
        str(model_id).startswith(option.option_id)
        for option in request.options
        if isinstance(option.payload, dict)
        for model_id in cast(list[object], option.payload["model_instance_ids"])
    )

    event_types = tuple(
        event.event_type for event in lifecycle.decision_controller.event_log.records
    )
    assert event_types.count("battlefield_placement_created") == 1
    assert event_types.count("movement_phase_entered") == 1
    assert "phase_body_placeholder_noop" not in event_types


def test_movement_unit_selection_records_activation_state_and_replay_payloads() -> None:
    lifecycle, status = _advance_to_movement_unit_selection(_config())
    request = _decision_request(status)

    follow_up = _submit_result(
        lifecycle,
        request=request,
        option_id="army-alpha:intercessor-unit-1",
        result_id="phase10b-result-000003",
    )

    assert follow_up.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    action_request = _decision_request(follow_up)
    assert action_request.decision_type == SELECT_MOVEMENT_ACTION_DECISION_TYPE
    assert action_request.actor_id == "player-a"
    assert action_request.payload == {
        "game_id": "phase10b-game",
        "battle_round": 1,
        "phase": BattlePhase.MOVEMENT.value,
        "active_player_id": "player-a",
        "unit_instance_id": "army-alpha:intercessor-unit-1",
    }
    assert lifecycle.state is not None
    assert lifecycle.state.current_battle_phase is BattlePhase.MOVEMENT
    assert lifecycle.decision_controller.queue.pending_requests == (action_request,)
    movement_state = lifecycle.state.movement_phase_state
    assert movement_state is not None
    assert movement_state.selected_unit_ids == ("army-alpha:intercessor-unit-1",)
    assert movement_state.moved_unit_ids == ()
    assert movement_state.active_selection == MovementUnitSelection(
        player_id="player-a",
        battle_round=1,
        unit_instance_id="army-alpha:intercessor-unit-1",
        request_id=request.request_id,
        result_id="phase10b-result-000003",
    )

    selected_event_payloads = [
        event.payload
        for event in lifecycle.decision_controller.event_log.records
        if event.event_type == "movement_unit_selected"
    ]
    assert selected_event_payloads == [
        {
            "game_id": "phase10b-game",
            "battle_round": 1,
            "active_player_id": "player-a",
            "phase": BattlePhase.MOVEMENT.value,
            "unit_instance_id": "army-alpha:intercessor-unit-1",
            "request_id": request.request_id,
            "result_id": "phase10b-result-000003",
            "phase_body_status": "unit_selected",
        }
    ]
    assert _event_index(lifecycle, "movement_unit_selected") < _event_index(
        lifecycle,
        "decision_requested",
        decision_type=SELECT_MOVEMENT_ACTION_DECISION_TYPE,
        start_after="movement_unit_selected",
    )
    payload = cast(
        GameLifecyclePayload,
        json.loads(json.dumps(lifecycle.to_payload(), sort_keys=True)),
    )
    assert GameLifecycle.from_payload(payload).to_payload() == lifecycle.to_payload()


def test_select_movement_action_options_are_standard_phase_actions_only() -> None:
    _lifecycle, action_request = _advance_to_movement_action_request()

    expected_option_ids = (
        MovementPhaseActionKind.REMAIN_STATIONARY.value,
        MovementPhaseActionKind.NORMAL_MOVE.value,
        MovementPhaseActionKind.ADVANCE.value,
    )
    assert {option.option_id for option in action_request.options} == set(expected_option_ids)
    assert tuple(option.option_id for option in action_request.options) == tuple(
        sorted(expected_option_ids)
    )
    assert "fly" not in {option.option_id for option in action_request.options}
    assert "embark" not in {option.option_id for option in action_request.options}
    assert "disembark" not in {option.option_id for option in action_request.options}
    assert "embark_disembark" not in {option.option_id for option in action_request.options}
    assert "terrain_traversal" not in {option.option_id for option in action_request.options}
    assert "engagement_constrained_move" not in {
        option.option_id for option in action_request.options
    }
    for option in action_request.options:
        assert isinstance(option.payload, dict)
        assert "action" not in option.payload
        assert option.payload["movement_phase_action"] == option.option_id


def test_movement_taxonomy_keeps_steps_placements_and_displacements_separate() -> None:
    placement_values = {kind.value for kind in BattlefieldPlacementKind}
    displacement_values = {kind.value for kind in ModelDisplacementKind}
    removal_values = {kind.value for kind in BattlefieldRemovalKind}

    assert MovementPhaseStepKind.REINFORCEMENTS.value not in placement_values
    assert BattlefieldPlacementKind.REDEPLOY.value == "redeploy"
    assert BattlefieldPlacementKind.REDEPLOY.value not in displacement_values
    assert BattlefieldRemovalKind.EMBARK.value == "embark"
    assert BattlefieldPlacementKind.DISEMBARK.value == "disembark"
    assert BattlefieldRemovalKind.EMBARK.value not in placement_values
    assert BattlefieldPlacementKind.DISEMBARK.value not in removal_values


def test_selected_units_are_excluded_from_legal_movement_unit_set() -> None:
    lifecycle, status = _advance_to_movement_unit_selection(_config())
    request = _decision_request(status)

    _submit_result(
        lifecycle,
        request=request,
        option_id="army-alpha:intercessor-unit-1",
        result_id="phase10b-result-000003",
    )

    assert lifecycle.state is not None
    movement_state = lifecycle.state.movement_phase_state
    assert movement_state is not None
    scenario = _scenario_from_state(lifecycle.state)
    assert movement_state.legal_unit_ids(scenario) == ("army-alpha:intercessor-unit-2",)


def test_movement_phase_requires_complete_placement_before_unit_selection() -> None:
    state = _movement_state_with_partial_placement()
    decisions = DecisionController()

    with pytest.raises(GameLifecycleError, match="complete placed armies"):
        MovementPhaseHandler().begin_phase(state=state, decisions=decisions)

    assert decisions.queue.pending_requests == ()


def test_movement_phase_state_payloads_and_fail_fast_validation() -> None:
    selection = MovementUnitSelection(
        player_id="player-a",
        battle_round=1,
        unit_instance_id="army-alpha:intercessor-unit-1",
        request_id="decision-request-000001",
        result_id="decision-result-000001",
    )
    state = MovementPhaseState(
        battle_round=1,
        active_player_id="player-a",
        selected_unit_ids=("army-alpha:intercessor-unit-1",),
        active_selection=selection,
    )
    completed_state = MovementPhaseState(
        battle_round=1,
        active_player_id="player-a",
        selected_unit_ids=("army-alpha:intercessor-unit-1",),
        moved_unit_ids=("army-alpha:intercessor-unit-1",),
        movement_distance_records=(
            MovementDistanceRecord(
                unit_instance_id="army-alpha:intercessor-unit-1",
                maximum_model_distance_inches=2.5,
            ),
        ),
    )
    selection_payload = cast(
        MovementUnitSelectionPayload,
        json.loads(json.dumps(selection.to_payload(), sort_keys=True)),
    )

    assert MovementUnitSelection.from_payload(selection_payload) == selection
    assert MovementPhaseState.from_payload(state.to_payload()) == state
    assert MovementPhaseState.from_payload(completed_state.to_payload()) == completed_state
    with pytest.raises(
        GameLifecycleError,
        match="movement_distance_records must be in moved_unit_ids",
    ):
        MovementPhaseState(
            battle_round=1,
            active_player_id="player-a",
            selected_unit_ids=("army-alpha:intercessor-unit-1",),
            moved_unit_ids=("army-alpha:intercessor-unit-1",),
            movement_distance_records=(
                MovementDistanceRecord(
                    unit_instance_id="other-unit",
                    maximum_model_distance_inches=1.0,
                ),
            ),
        )
    with pytest.raises(GameLifecycleError, match="must not contain duplicate unit IDs"):
        MovementPhaseState(
            battle_round=1,
            active_player_id="player-a",
            selected_unit_ids=("army-alpha:intercessor-unit-1",),
            moved_unit_ids=("army-alpha:intercessor-unit-1",),
            movement_distance_records=(
                MovementDistanceRecord(
                    unit_instance_id="army-alpha:intercessor-unit-1",
                    maximum_model_distance_inches=1.0,
                ),
                MovementDistanceRecord(
                    unit_instance_id="army-alpha:intercessor-unit-1",
                    maximum_model_distance_inches=2.0,
                ),
            ),
        )
    with pytest.raises(GameLifecycleError, match="duplicates"):
        MovementPhaseState(
            battle_round=1,
            active_player_id="player-a",
            selected_unit_ids=("unit-a", "unit-a"),
        )
    with pytest.raises(GameLifecycleError, match="active_selection must match active_player_id"):
        MovementPhaseState(
            battle_round=1,
            active_player_id="player-b",
            selected_unit_ids=("army-alpha:intercessor-unit-1",),
            active_selection=selection,
        )
    with pytest.raises(GameLifecycleError, match="active_selection must be in selected_unit_ids"):
        MovementPhaseState(
            battle_round=1,
            active_player_id="player-a",
            selected_unit_ids=("other-unit",),
            active_selection=selection,
        )
    with pytest.raises(GameLifecycleError, match="moved_unit_ids must be in selected_unit_ids"):
        MovementPhaseState(
            battle_round=1,
            active_player_id="player-a",
            selected_unit_ids=("army-alpha:intercessor-unit-1",),
            moved_unit_ids=("other-unit",),
        )
    with pytest.raises(GameLifecycleError, match="active_selection must not already be moved"):
        MovementPhaseState(
            battle_round=1,
            active_player_id="player-a",
            selected_unit_ids=("army-alpha:intercessor-unit-1",),
            moved_unit_ids=("army-alpha:intercessor-unit-1",),
            active_selection=selection,
        )


def test_lifecycle_from_payload_rejects_battlefield_state_missing_unit_reference() -> None:
    lifecycle, _status = _advance_to_movement_unit_selection(_config())
    payload = _payload_copy(lifecycle)
    battlefield_state = payload["state"]["battlefield_state"]
    assert battlefield_state is not None
    first_unit = battlefield_state["placed_armies"][0]["unit_placements"][0]
    first_unit["unit_instance_id"] = "army-alpha:missing-unit"
    for index, model_placement in enumerate(first_unit["model_placements"]):
        model_placement["unit_instance_id"] = "army-alpha:missing-unit"
        model_placement["model_instance_id"] = f"army-alpha:missing-unit:model-{index + 1}"

    with pytest.raises(GameLifecycleError, match="battlefield_state"):
        GameLifecycle.from_payload(payload)


def test_lifecycle_from_payload_rejects_battlefield_state_with_unplaced_model() -> None:
    lifecycle, _status = _advance_to_movement_unit_selection(_config())
    payload = _payload_copy(lifecycle)
    battlefield_state = payload["state"]["battlefield_state"]
    assert battlefield_state is not None
    battlefield_state["placed_armies"][0]["unit_placements"][0]["model_placements"].pop()

    with pytest.raises(GameLifecycleError, match="battlefield_state"):
        GameLifecycle.from_payload(payload)


def test_lifecycle_from_payload_rejects_missing_battlefield_state_after_deploy() -> None:
    lifecycle, _status = _advance_to_movement_unit_selection(_config())
    payload = _payload_copy(lifecycle)
    payload["state"]["battlefield_state"] = None

    with pytest.raises(GameLifecycleError, match="missing battlefield_state"):
        GameLifecycle.from_payload(payload)


def test_lifecycle_from_payload_rejects_battlefield_state_before_deploy_armies() -> None:
    lifecycle = GameLifecycle()
    lifecycle.start(_config())
    lifecycle.advance_until_decision_or_terminal()
    assert lifecycle.state is not None
    assert lifecycle.state.battlefield_state is None
    assert tuple(lifecycle.state.army_definitions)
    scenario = create_deterministic_battlefield_scenario(
        battlefield_id="phase10b-early-placement",
        armies=tuple(lifecycle.state.army_definitions),
    )
    payload = _payload_copy(lifecycle)
    payload["state"]["battlefield_state"] = scenario.battlefield_state.to_payload()

    with pytest.raises(GameLifecycleError, match="absent before DEPLOY_ARMIES"):
        GameLifecycle.from_payload(payload)


def test_lifecycle_from_payload_rejects_movement_phase_state_outside_movement() -> None:
    lifecycle = _lifecycle_after_movement_unit_selection()
    payload = _payload_copy(lifecycle)
    payload["state"]["battle_phase_index"] = 0

    with pytest.raises(GameLifecycleError, match="MOVEMENT phase"):
        GameLifecycle.from_payload(payload)


def test_lifecycle_from_payload_rejects_movement_phase_state_active_player_drift() -> None:
    lifecycle = _lifecycle_after_movement_unit_selection()
    payload = _payload_copy(lifecycle)
    movement_state = payload["state"]["movement_phase_state"]
    assert movement_state is not None
    movement_state["active_player_id"] = "player-b"
    active_selection = movement_state["active_selection"]
    assert active_selection is not None
    active_selection["player_id"] = "player-b"

    with pytest.raises(GameLifecycleError, match="active player drift"):
        GameLifecycle.from_payload(payload)


def test_lifecycle_from_payload_rejects_movement_phase_state_battle_round_drift() -> None:
    lifecycle = _lifecycle_after_movement_unit_selection()
    payload = _payload_copy(lifecycle)
    movement_state = payload["state"]["movement_phase_state"]
    assert movement_state is not None
    movement_state["battle_round"] = 2
    active_selection = movement_state["active_selection"]
    assert active_selection is not None
    active_selection["battle_round"] = 2

    with pytest.raises(GameLifecycleError, match="battle round drift"):
        GameLifecycle.from_payload(payload)


def test_lifecycle_from_payload_rejects_selected_unit_ids_for_opponent_unit() -> None:
    lifecycle = _lifecycle_after_movement_unit_selection()
    payload = _payload_copy(lifecycle)
    movement_state = payload["state"]["movement_phase_state"]
    assert movement_state is not None
    movement_state["selected_unit_ids"] = ["army-beta:intercessor-unit-3"]
    movement_state["active_selection"] = None

    with pytest.raises(GameLifecycleError, match="selected unit"):
        GameLifecycle.from_payload(payload)


@pytest.mark.parametrize(
    "unit_instance_id",
    [
        "army-beta:intercessor-unit-3",
        "army-alpha:missing-unit",
    ],
)
def test_lifecycle_from_payload_rejects_active_selection_for_wrong_or_missing_unit(
    unit_instance_id: str,
) -> None:
    lifecycle = _lifecycle_after_movement_unit_selection()
    payload = _payload_copy(lifecycle)
    movement_state = payload["state"]["movement_phase_state"]
    assert movement_state is not None
    movement_state["selected_unit_ids"] = [unit_instance_id]
    active_selection = movement_state["active_selection"]
    assert active_selection is not None
    active_selection["unit_instance_id"] = unit_instance_id

    with pytest.raises(GameLifecycleError, match="active player's unit"):
        GameLifecycle.from_payload(payload)


def test_remain_stationary_marks_unit_complete_without_changing_poses() -> None:
    lifecycle, action_request = _advance_to_movement_action_request()
    assert lifecycle.state is not None
    battlefield_state = lifecycle.state.battlefield_state
    assert battlefield_state is not None
    before_payload = battlefield_state.to_payload()

    follow_up = _submit_result(
        lifecycle,
        request=action_request,
        option_id=MovementPhaseActionKind.REMAIN_STATIONARY.value,
        result_id="phase10c-result-000004",
    )

    assert follow_up.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    next_request = _decision_request(follow_up)
    assert next_request.decision_type == SELECT_MOVEMENT_UNIT_DECISION_TYPE
    assert tuple(option.option_id for option in next_request.options) == (
        "army-alpha:intercessor-unit-2",
    )
    assert lifecycle.state.battlefield_state is not None
    assert lifecycle.state.battlefield_state.to_payload() == before_payload
    movement_state = lifecycle.state.movement_phase_state
    assert movement_state is not None
    assert movement_state.selected_unit_ids == ("army-alpha:intercessor-unit-1",)
    assert movement_state.moved_unit_ids == ("army-alpha:intercessor-unit-1",)
    assert movement_state.active_selection is None
    terminal_event = _last_event_payload(lifecycle, "movement_activation_completed")
    assert "action" not in terminal_event
    assert "displacement_kind" not in terminal_event
    assert terminal_event["movement_phase_action"] == (
        MovementPhaseActionKind.REMAIN_STATIONARY.value
    )
    assert terminal_event["witness"] is None
    assert terminal_event["model_movements"] == []
    assert _event_index(lifecycle, "movement_activation_completed") < _event_index(
        lifecycle,
        "decision_requested",
        decision_type=SELECT_MOVEMENT_UNIT_DECISION_TYPE,
        start_after="movement_activation_completed",
    )


def test_normal_move_consumes_movement_base_size_current_pose_and_updates_placement() -> None:
    lifecycle, action_request = _advance_to_movement_action_request()
    assert lifecycle.state is not None
    scenario = _scenario_from_state(lifecycle.state)
    before_placement = scenario.battlefield_state.unit_placement_by_id(
        "army-alpha:intercessor-unit-1"
    )
    before_poses = {
        placement.model_instance_id: placement.pose
        for placement in before_placement.model_placements
    }
    normal_option = action_request.option_by_id(MovementPhaseActionKind.NORMAL_MOVE.value)
    assert isinstance(normal_option.payload, dict)
    normal_payload = cast(dict[str, object], normal_option.payload)
    assert "action" not in normal_payload
    assert normal_payload["movement_phase_action"] == MovementPhaseActionKind.NORMAL_MOVE.value
    assert set(normal_payload) == {"movement_phase_action", "unit_instance_id", "movement_mode"}

    follow_up = submit_action_and_movement_proposal(
        lifecycle,
        request=action_request,
        option_id=MovementPhaseActionKind.NORMAL_MOVE.value,
        action_result_id="phase10c-result-000004",
        proposal_result_id="phase10c-normal-proposal-000004",
        unit_instance_id=before_placement.unit_instance_id,
        movement_phase_action=MovementPhaseActionKind.NORMAL_MOVE,
        movement_mode=MovementMode.NORMAL,
        witness=straight_line_witness_for_unit(
            lifecycle,
            unit_instance_id=before_placement.unit_instance_id,
            dx=6.0,
        ),
    )

    assert follow_up.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    assert lifecycle.state.battlefield_state is not None
    after_scenario = _scenario_from_state(lifecycle.state)
    after_placement = after_scenario.battlefield_state.unit_placement_by_id(
        "army-alpha:intercessor-unit-1"
    )
    for placement in after_placement.model_placements:
        start = before_poses[placement.model_instance_id]
        assert placement.pose.position.x == start.position.x + 6
        assert placement.pose.position.y == start.position.y
        assert placement.pose.position.z == start.position.z
        assert placement.pose.facing == start.facing

    terminal_event = _last_event_payload(lifecycle, "movement_activation_completed")
    assert "action" not in terminal_event
    assert terminal_event["movement_phase_action"] == MovementPhaseActionKind.NORMAL_MOVE.value
    assert terminal_event["displacement_kind"] == ModelDisplacementKind.NORMAL_MOVE.value
    assert terminal_event["movement_inches"] == 6
    witness = terminal_event["witness"]
    assert isinstance(witness, dict)
    witness_payload = cast(dict[str, object], witness)
    model_paths_raw = witness_payload["model_paths"]
    assert isinstance(model_paths_raw, list)
    model_paths = cast(list[object], model_paths_raw)
    assert len(model_paths) == 5
    for model_path_raw in model_paths:
        assert isinstance(model_path_raw, dict)
        model_path = cast(dict[str, object], model_path_raw)
        poses_raw = model_path["poses"]
        assert isinstance(poses_raw, list)
        poses = cast(list[object], poses_raw)
        assert len(poses) == 3
        final_pose = poses[-1]
        model_id = model_path["model_id"]
        assert type(model_id) is str
        assert (
            final_pose
            == after_scenario.battlefield_state.model_placement_by_id(model_id).pose.to_payload()
        )
    assert GameLifecycle.from_payload(_payload_copy(lifecycle)).to_payload() == (
        lifecycle.to_payload()
    )


def test_next_movement_unit_is_queued_only_after_activation_terminal_event() -> None:
    lifecycle, action_request = _advance_to_movement_action_request()

    status = submit_action_and_movement_proposal(
        lifecycle,
        request=action_request,
        option_id=MovementPhaseActionKind.NORMAL_MOVE.value,
        action_result_id="phase10c-result-000004",
        proposal_result_id="phase10c-normal-proposal-000004",
        unit_instance_id="army-alpha:intercessor-unit-1",
        movement_phase_action=MovementPhaseActionKind.NORMAL_MOVE,
        movement_mode=MovementMode.NORMAL,
        witness=straight_line_witness_for_unit(
            lifecycle,
            unit_instance_id="army-alpha:intercessor-unit-1",
            dx=6.0,
        ),
    )
    _decline_optional_stratagem_if_pending(
        lifecycle,
        status=status,
        result_id="phase10c-decline-fire-overwatch",
    )

    terminal_index = _event_index(lifecycle, "movement_activation_completed")
    next_unit_request_index = _event_index(
        lifecycle,
        "decision_requested",
        decision_type=SELECT_MOVEMENT_UNIT_DECISION_TYPE,
        start_after="movement_activation_completed",
    )
    assert terminal_index < next_unit_request_index


def test_advance_movement_mode_completes_activation_and_queues_next_unit() -> None:
    lifecycle, action_request = _advance_to_movement_action_request()
    assert lifecycle.state is not None

    status = submit_action_and_movement_proposal(
        lifecycle,
        request=action_request,
        option_id=MovementPhaseActionKind.ADVANCE.value,
        action_result_id="phase10c-result-000004",
        proposal_result_id="phase10c-advance-proposal-000004",
        unit_instance_id="army-alpha:intercessor-unit-1",
        movement_phase_action=MovementPhaseActionKind.ADVANCE,
        movement_mode=MovementMode.ADVANCE,
        witness=straight_line_witness_for_unit(
            lifecycle,
            unit_instance_id="army-alpha:intercessor-unit-1",
            dx=6.0,
        ),
    )
    status = _decline_optional_stratagem_if_pending(
        lifecycle,
        status=status,
        result_id="phase10c-decline-fire-overwatch",
    )

    assert status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    assert _decision_request(status).decision_type == SELECT_MOVEMENT_UNIT_DECISION_TYPE
    assert lifecycle.state.battlefield_state is not None
    movement_state = lifecycle.state.movement_phase_state
    assert movement_state is not None
    assert movement_state.moved_unit_ids == ("army-alpha:intercessor-unit-1",)
    assert movement_state.active_selection is None
    advanced_state = lifecycle.state.advanced_unit_state_for_unit(
        player_id="player-a",
        battle_round=1,
        unit_instance_id="army-alpha:intercessor-unit-1",
    )
    assert advanced_state is not None
    assert not advanced_state.can_shoot
    assert not advanced_state.can_declare_charge
    terminal_payload = _last_event_payload(lifecycle, "movement_activation_completed")
    assert terminal_payload["movement_phase_action"] == MovementPhaseActionKind.ADVANCE.value


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
        result_id="phase10b-result-000001",
    )
    assert _decision_request(second_status).decision_type == SECONDARY_MISSION_DECISION_TYPE
    movement_status = _submit_result(
        lifecycle,
        request=_decision_request(second_status),
        option_id="fixed:assassination:bring_it_down",
        result_id="phase10b-result-000002",
    )
    return lifecycle, movement_status


def _lifecycle_after_movement_unit_selection() -> GameLifecycle:
    lifecycle, status = _advance_to_movement_unit_selection(_config())
    request = _decision_request(status)
    _submit_result(
        lifecycle,
        request=request,
        option_id="army-alpha:intercessor-unit-1",
        result_id="phase10b-result-000003",
    )
    return lifecycle


def _advance_to_movement_action_request() -> tuple[GameLifecycle, DecisionRequest]:
    lifecycle, status = _advance_to_movement_unit_selection(_config())
    request = _decision_request(status)
    action_status = _submit_result(
        lifecycle,
        request=request,
        option_id="army-alpha:intercessor-unit-1",
        result_id="phase10b-result-000003",
    )
    action_request = _decision_request(action_status)
    assert action_request.decision_type == SELECT_MOVEMENT_ACTION_DECISION_TYPE
    return lifecycle, action_request


def _payload_copy(lifecycle: GameLifecycle) -> GameLifecyclePayload:
    return cast(
        GameLifecyclePayload,
        json.loads(json.dumps(lifecycle.to_payload(), sort_keys=True)),
    )


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


def _last_event_payload(lifecycle: GameLifecycle, event_type: str) -> dict[str, object]:
    for event in reversed(lifecycle.decision_controller.event_log.records):
        if event.event_type == event_type:
            assert isinstance(event.payload, dict)
            return cast(dict[str, object], event.payload)
    raise AssertionError(f"Missing event type: {event_type}")


def _event_index(
    lifecycle: GameLifecycle,
    event_type: str,
    *,
    decision_type: str | None = None,
    start_after: str | None = None,
) -> int:
    records = lifecycle.decision_controller.event_log.records
    start_index = 0
    if start_after is not None:
        start_index = _event_index(lifecycle, start_after) + 1
    for index, event in enumerate(records[start_index:], start=start_index):
        if event.event_type != event_type:
            continue
        if decision_type is None:
            return index
        if isinstance(event.payload, dict) and event.payload.get("decision_type") == decision_type:
            return index
    raise AssertionError(f"Missing event type: {event_type}")


def _config() -> GameConfig:
    catalog = ArmyCatalog.phase9a_canonical_content_pack()
    return GameConfig(
        game_id="phase10b-game",
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(
            descriptor_version="core-v2-phase10b-test"
        ),
        army_catalog=catalog,
        army_muster_requests=(
            _army_muster_request(
                catalog=catalog,
                player_id="player-a",
                army_id="army-alpha",
                unit_selections=(
                    _unit_selection(unit_selection_id="intercessor-unit-1"),
                    _unit_selection(unit_selection_id="intercessor-unit-2"),
                ),
            ),
            _army_muster_request(
                catalog=catalog,
                player_id="player-b",
                army_id="army-beta",
                unit_selections=(_unit_selection(unit_selection_id="intercessor-unit-3"),),
            ),
        ),
        player_ids=("player-a", "player-b"),
        turn_order=("player-a", "player-b"),
        fixed_secondary_mission_ids=(
            "assassination",
            "bring_it_down",
            "cleanse",
        ),
        mission_setup=_mission_setup(),
    )


def _mission_setup() -> MissionSetup:
    return MissionSetup.from_mission_pack(
        mission_pack=chapter_approved_2026_27_mission_pack(),
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
            detachment_ids=("core-combined-arms",),
        ),
        unit_selections=unit_selections,
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


def _scenario_from_state(state: GameState) -> BattlefieldScenario:
    assert state.battlefield_state is not None
    return BattlefieldScenario(
        armies=tuple(state.army_definitions),
        battlefield_state=state.battlefield_state,
    )


def _movement_state_with_partial_placement() -> GameState:
    config = _config()
    state = GameState.from_config(config)
    armies = _mustered_armies(config)
    for army in armies:
        state.record_army_definition(army)
    scenario = create_deterministic_battlefield_scenario(
        battlefield_id="phase10b-partial-placement",
        armies=armies,
    )
    first_army = scenario.battlefield_state.placed_armies[0]
    second_army = scenario.battlefield_state.placed_armies[1]
    first_unit = first_army.unit_placements[0]
    partial_first_unit = replace(
        first_unit,
        model_placements=first_unit.model_placements[:-1],
    )
    partial_battlefield = replace(
        scenario.battlefield_state,
        placed_armies=(
            replace(first_army, unit_placements=(partial_first_unit,)),
            second_army,
        ),
    )
    state.record_battlefield_state(partial_battlefield)
    for player_id in state.player_ids:
        state.record_secondary_mission_choice(
            SecondaryMissionChoice(
                player_id=player_id,
                mode=SecondaryMissionMode.FIXED,
                fixed_mission_ids=("assassination", "bring_it_down"),
            )
        )
    while state.stage is GameLifecycleStage.SETUP:
        state.complete_current_setup_step()
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.MOVEMENT)
    return state


def _mustered_armies(config: GameConfig) -> tuple[ArmyDefinition, ...]:
    return tuple(
        muster_army(catalog=config.army_catalog, request=request)
        for request in config.army_muster_requests
    )
