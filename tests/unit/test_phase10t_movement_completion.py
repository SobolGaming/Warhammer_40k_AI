from __future__ import annotations

import json
from typing import cast

import pytest

from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.core.ruleset_descriptor import RulesetDescriptor
from warhammer40k_core.engine.army_mustering import ArmyMusterRequest
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_request import (
    PARAMETERIZED_DECISION_OPTION_ID,
    DecisionRequest,
)
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.event_log import JsonValue
from warhammer40k_core.engine.game_state import GameConfig
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
    MovementPhaseActionKind,
    MovementPhaseHandler,
    MovementPhaseState,
    MovementPhaseStepKind,
)
from warhammer40k_core.engine.setup_flow import SECONDARY_MISSION_DECISION_TYPE
from warhammer40k_core.engine.stratagems import (
    STRATAGEM_TARGET_PROPOSAL_DECISION_TYPE,
    stratagem_decline_payload,
)
from warhammer40k_core.rules.mission_pack_import import chapter_approved_2025_26_mission_pack


def test_full_movement_phase_completion_exits_to_shooting_after_all_work_is_complete() -> None:
    lifecycle, movement_status = _advance_to_movement_unit_selection()
    first_selection = _decision_request(movement_status)
    first_action_status = _submit_result(
        lifecycle,
        request=first_selection,
        option_id="army-alpha:intercessor-unit-1",
        result_id="phase10t-result-000003",
    )
    first_action = _decision_request(first_action_status)
    assert first_action.decision_type == SELECT_MOVEMENT_ACTION_DECISION_TYPE

    second_selection_status = _submit_result(
        lifecycle,
        request=first_action,
        option_id=MovementPhaseActionKind.NORMAL_MOVE.value,
        result_id="phase10t-result-000004",
    )
    second_selection_status = _decline_optional_stratagem_if_pending(
        lifecycle,
        status=second_selection_status,
        result_id="phase10t-decline-fire-overwatch",
    )
    second_selection = _decision_request(second_selection_status)
    assert second_selection.decision_type == SELECT_MOVEMENT_UNIT_DECISION_TYPE

    second_action_status = _submit_result(
        lifecycle,
        request=second_selection,
        option_id="army-alpha:intercessor-unit-2",
        result_id="phase10t-result-000005",
    )
    second_action = _decision_request(second_action_status)
    completion_status = _submit_result(
        lifecycle,
        request=second_action,
        option_id=MovementPhaseActionKind.REMAIN_STATIONARY.value,
        result_id="phase10t-result-000006",
    )

    assert completion_status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    assert completion_status.decision_request is not None
    assert completion_status.decision_request.decision_type == "select_shooting_unit"
    assert lifecycle.state is not None
    assert lifecycle.state.current_battle_phase is BattlePhase.SHOOTING
    assert lifecycle.state.movement_phase_state is None

    movement_events = _event_payloads(lifecycle, "movement_activation_completed")
    assert len(movement_events) == 2
    normal_move_payload = movement_events[0]
    assert normal_move_payload["movement_phase_action"] == MovementPhaseActionKind.NORMAL_MOVE.value
    assert "transition_batch" in normal_move_payload
    transition_batch = cast(dict[str, object], normal_move_payload["transition_batch"])
    assert transition_batch["displacements"]
    assert movement_events[1]["movement_phase_action"] == (
        MovementPhaseActionKind.REMAIN_STATIONARY.value
    )

    assert _event_index(lifecycle, "movement_activation_completed") < _event_index(
        lifecycle,
        "reinforcements_step_completed",
    )
    assert _last_event_payload(lifecycle, "battle_phase_completed") == {
        "game_id": "phase10t-game",
        "completed_phase": BattlePhase.MOVEMENT.value,
        "battle_round": 1,
        "active_player_id": "player-a",
        "next_phase": BattlePhase.SHOOTING.value,
        "phase_body_status": "reinforcements_complete",
    }
    payload = cast(
        GameLifecyclePayload,
        json.loads(json.dumps(lifecycle.to_payload(), sort_keys=True)),
    )
    assert GameLifecycle.from_payload(payload).to_payload() == lifecycle.to_payload()


def test_reinforcements_step_requires_complete_move_units_step() -> None:
    lifecycle, _movement_status = _advance_to_movement_unit_selection()
    assert lifecycle.state is not None
    lifecycle.state.movement_phase_state = MovementPhaseState(
        battle_round=1,
        active_player_id="player-a",
        step=MovementPhaseStepKind.REINFORCEMENTS,
        selected_unit_ids=("army-alpha:intercessor-unit-1",),
        moved_unit_ids=("army-alpha:intercessor-unit-1",),
    )

    with pytest.raises(GameLifecycleError, match="Move Units step must be complete"):
        MovementPhaseHandler(ruleset_descriptor=_ruleset()).begin_phase(
            state=lifecycle.state,
            decisions=lifecycle.decision_controller,
        )


def test_reinforcements_step_rejects_selected_units_that_have_not_moved() -> None:
    lifecycle, _movement_status = _advance_to_movement_unit_selection()
    assert lifecycle.state is not None
    lifecycle.state.movement_phase_state = MovementPhaseState(
        battle_round=1,
        active_player_id="player-a",
        step=MovementPhaseStepKind.REINFORCEMENTS,
        selected_unit_ids=(
            "army-alpha:intercessor-unit-1",
            "army-alpha:intercessor-unit-2",
        ),
        moved_unit_ids=("army-alpha:intercessor-unit-1",),
    )

    with pytest.raises(GameLifecycleError, match="Move Units step must be complete"):
        MovementPhaseHandler(ruleset_descriptor=_ruleset()).begin_phase(
            state=lifecycle.state,
            decisions=DecisionController(),
        )


def test_reinforcements_step_accepts_when_only_inactive_units_remain_unselected() -> None:
    lifecycle, _movement_status = _advance_to_movement_unit_selection()
    assert lifecycle.state is not None
    lifecycle.state.movement_phase_state = MovementPhaseState(
        battle_round=1,
        active_player_id="player-a",
        step=MovementPhaseStepKind.REINFORCEMENTS,
        selected_unit_ids=(
            "army-alpha:intercessor-unit-1",
            "army-alpha:intercessor-unit-2",
        ),
        moved_unit_ids=(
            "army-alpha:intercessor-unit-1",
            "army-alpha:intercessor-unit-2",
        ),
    )
    decisions = DecisionController()

    status = MovementPhaseHandler(ruleset_descriptor=_ruleset()).begin_phase(
        state=lifecycle.state,
        decisions=decisions,
    )

    assert status.status_kind is LifecycleStatusKind.ADVANCED
    assert isinstance(status.payload, dict)
    assert status.payload["phase_body_status"] == "reinforcements_complete"
    assert lifecycle.state.movement_phase_state.reinforcements_completed
    assert _event_payloads_from_decisions(decisions, "reinforcements_step_completed")


def test_lifecycle_payload_rejects_reinforcements_state_before_move_units_complete() -> None:
    lifecycle, _movement_status = _advance_to_movement_unit_selection()
    payload = _payload_copy(lifecycle)
    movement_state = payload["state"]["movement_phase_state"]
    assert movement_state is not None
    movement_state["step"] = MovementPhaseStepKind.REINFORCEMENTS.value
    movement_state["selected_unit_ids"] = ["army-alpha:intercessor-unit-1"]
    movement_state["moved_unit_ids"] = ["army-alpha:intercessor-unit-1"]
    movement_state["active_selection"] = None

    with pytest.raises(GameLifecycleError, match="Move Units step is incomplete"):
        GameLifecycle.from_payload(payload)


def _advance_to_movement_unit_selection() -> tuple[GameLifecycle, LifecycleStatus]:
    lifecycle = GameLifecycle()
    lifecycle.start(_config())
    first_status = lifecycle.advance_until_decision_or_terminal()
    assert _decision_request(first_status).decision_type == SECONDARY_MISSION_DECISION_TYPE
    second_status = _submit_result(
        lifecycle,
        request=_decision_request(first_status),
        option_id="fixed:assassination:bring_it_down",
        result_id="phase10t-result-000001",
    )
    assert _decision_request(second_status).decision_type == SECONDARY_MISSION_DECISION_TYPE
    movement_status = _submit_result(
        lifecycle,
        request=_decision_request(second_status),
        option_id="fixed:assassination:bring_it_down",
        result_id="phase10t-result-000002",
    )
    assert _decision_request(movement_status).decision_type == SELECT_MOVEMENT_UNIT_DECISION_TYPE
    return lifecycle, movement_status


def _submit_result(
    lifecycle: GameLifecycle,
    *,
    request: DecisionRequest,
    option_id: str,
    result_id: str,
) -> LifecycleStatus:
    return lifecycle.submit_decision(
        DecisionResult.for_request(
            result_id=result_id,
            request=request,
            selected_option_id=option_id,
        )
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


def _payload_copy(lifecycle: GameLifecycle) -> GameLifecyclePayload:
    return cast(
        GameLifecyclePayload,
        json.loads(json.dumps(lifecycle.to_payload(), sort_keys=True)),
    )


def _event_payloads(
    lifecycle: GameLifecycle,
    event_type: str,
) -> tuple[dict[str, JsonValue], ...]:
    return tuple(
        cast(dict[str, JsonValue], event.payload)
        for event in lifecycle.decision_controller.event_log.records
        if event.event_type == event_type
    )


def _event_payloads_from_decisions(
    decisions: DecisionController,
    event_type: str,
) -> tuple[dict[str, JsonValue], ...]:
    return tuple(
        cast(dict[str, JsonValue], event.payload)
        for event in decisions.event_log.records
        if event.event_type == event_type
    )


def _last_event_payload(lifecycle: GameLifecycle, event_type: str) -> dict[str, JsonValue]:
    payloads = _event_payloads(lifecycle, event_type)
    if not payloads:
        raise AssertionError(f"Missing event type: {event_type}")
    return payloads[-1]


def _event_index(lifecycle: GameLifecycle, event_type: str) -> int:
    for index, event in enumerate(lifecycle.decision_controller.event_log.records):
        if event.event_type == event_type:
            return index
    raise AssertionError(f"Missing event type: {event_type}")


def _config() -> GameConfig:
    catalog = ArmyCatalog.phase9a_canonical_content_pack()
    return GameConfig(
        game_id="phase10t-game",
        ruleset_descriptor=_ruleset(),
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


def _ruleset() -> RulesetDescriptor:
    return RulesetDescriptor.warhammer_40000_tenth(descriptor_version="core-v2-phase10t-test")


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
            UnitMusterSelection(
                unit_selection_id=unit_selection_id,
                datasheet_id="core-intercessor-like-infantry",
                model_profile_selections=(
                    ModelProfileSelection(
                        model_profile_id="core-intercessor-like",
                        model_count=5,
                    ),
                ),
            )
            for unit_selection_id in unit_selection_ids
        ),
    )
