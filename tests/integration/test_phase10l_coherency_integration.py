from __future__ import annotations

import json
from dataclasses import replace
from typing import cast

import pytest

from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.core.attributes import Characteristic, CharacteristicValue
from warhammer40k_core.core.ruleset_descriptor import RulesetDescriptor
from warhammer40k_core.engine.army_mustering import ArmyDefinition, ArmyMusterRequest
from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.decision_result import DecisionResult
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
    MovementPhaseActionKind,
)
from warhammer40k_core.engine.setup_flow import SECONDARY_MISSION_DECISION_TYPE
from warhammer40k_core.engine.unit_factory import ModelInstance, UnitInstance
from warhammer40k_core.geometry.pose import Pose
from warhammer40k_core.rules.mission_pack_import import chapter_approved_2025_26_mission_pack


@pytest.mark.integration
def test_lifecycle_from_payload_rejects_incoherent_battlefield_state_after_deploy_armies() -> None:
    lifecycle, _status = _advance_to_movement_unit_selection(_config())
    payload = _payload_copy(lifecycle)
    battlefield_state = payload["state"]["battlefield_state"]
    assert battlefield_state is not None
    first_unit = battlefield_state["placed_armies"][0]["unit_placements"][0]
    first_unit["model_placements"][-1]["pose"] = Pose.at(
        x=80.0,
        y=80.0,
        z=0.0,
        facing_degrees=0.0,
    ).to_payload()

    with pytest.raises(GameLifecycleError, match="battlefield_state is invalid"):
        GameLifecycle.from_payload(payload)


@pytest.mark.integration
def test_invalid_normal_move_does_not_mutate_state_and_keeps_selection_recoverable() -> None:
    lifecycle, action_request = _advance_to_movement_action_request()
    state = _require_state(lifecycle)
    battlefield_state = state.battlefield_state
    assert battlefield_state is not None
    before_battlefield_payload = battlefield_state.to_payload()
    movement_state = state.movement_phase_state
    assert movement_state is not None
    active_selection = movement_state.active_selection
    assert active_selection is not None

    _force_selected_model_movement(lifecycle, movement_inches=30)

    status = _submit_result(
        lifecycle,
        request=action_request,
        option_id=MovementPhaseActionKind.NORMAL_MOVE.value,
        result_id="phase10l-integration-result-000004",
    )

    assert status.status_kind is LifecycleStatusKind.INVALID
    status_payload = cast(dict[str, object], status.payload)
    assert status_payload["phase_body_status"] == "movement_action_invalid"
    assert status_payload["movement_phase_action"] == MovementPhaseActionKind.NORMAL_MOVE.value
    assert lifecycle.state is state
    assert state.battlefield_state is not None
    assert state.battlefield_state.to_payload() == before_battlefield_payload
    assert state.movement_phase_state is not None
    assert state.movement_phase_state.active_selection == active_selection

    invalid_event = _last_event_payload(lifecycle, "movement_action_invalid")
    assert invalid_event["phase_body_status"] == "movement_action_invalid"
    assert invalid_event["violation_code"] == "normal_move_model_movement_witness_drift"
    assert "rollback_record" not in invalid_event

    retry_status = lifecycle.advance_until_decision_or_terminal()
    retry_request = _decision_request(retry_status)
    assert retry_request.decision_type == SELECT_MOVEMENT_ACTION_DECISION_TYPE
    assert retry_request.actor_id == "player-a"
    assert retry_request.payload == {
        "game_id": "phase10l-integration-game",
        "battle_round": 1,
        "phase": BattlePhase.MOVEMENT.value,
        "active_player_id": "player-a",
        "unit_instance_id": active_selection.unit_instance_id,
    }


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
        result_id="phase10l-integration-result-000001",
    )
    assert _decision_request(second_status).decision_type == SECONDARY_MISSION_DECISION_TYPE
    movement_status = _submit_result(
        lifecycle,
        request=_decision_request(second_status),
        option_id="fixed:assassination:bring_it_down",
        result_id="phase10l-integration-result-000002",
    )
    assert _decision_request(movement_status).decision_type == SELECT_MOVEMENT_UNIT_DECISION_TYPE
    return lifecycle, movement_status


def _advance_to_movement_action_request() -> tuple[GameLifecycle, DecisionRequest]:
    lifecycle, movement_status = _advance_to_movement_unit_selection(_config())
    action_status = _submit_result(
        lifecycle,
        request=_decision_request(movement_status),
        option_id="army-alpha:intercessor-unit-1",
        result_id="phase10l-integration-result-000003",
    )
    action_request = _decision_request(action_status)
    assert action_request.decision_type == SELECT_MOVEMENT_ACTION_DECISION_TYPE
    assert action_request.option_by_id(MovementPhaseActionKind.NORMAL_MOVE.value)
    return lifecycle, action_request


def _force_selected_model_movement(
    lifecycle: GameLifecycle,
    *,
    movement_inches: int,
) -> None:
    state = _require_state(lifecycle)
    movement_state = state.movement_phase_state
    assert movement_state is not None
    active_selection = movement_state.active_selection
    assert active_selection is not None
    for army_index, army in enumerate(state.army_definitions):
        updated_unit = _unit_with_selected_model_movement(
            army=army,
            unit_instance_id=active_selection.unit_instance_id,
            movement_inches=movement_inches,
        )
        if updated_unit is None:
            continue
        units = tuple(
            updated_unit if unit.unit_instance_id == updated_unit.unit_instance_id else unit
            for unit in army.units
        )
        state.army_definitions[army_index] = replace(army, units=units)
        return
    raise AssertionError("Selected unit was not found in mustered armies.")


def _unit_with_selected_model_movement(
    *,
    army: ArmyDefinition,
    unit_instance_id: str,
    movement_inches: int,
) -> UnitInstance | None:
    for unit in army.units:
        if unit.unit_instance_id != unit_instance_id:
            continue
        selected_model_id = unit.own_models[-1].model_instance_id
        own_models = tuple(
            _model_with_movement(model, movement_inches=movement_inches)
            if model.model_instance_id == selected_model_id
            else model
            for model in unit.own_models
        )
        return replace(unit, own_models=own_models)
    return None


def _model_with_movement(
    model: ModelInstance,
    *,
    movement_inches: int,
) -> ModelInstance:
    characteristics = tuple(
        CharacteristicValue.from_raw(Characteristic.MOVEMENT, movement_inches)
        if characteristic.characteristic is Characteristic.MOVEMENT
        else characteristic
        for characteristic in model.characteristics
    )
    return replace(model, characteristics=characteristics)


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
    return lifecycle.submit_decision(
        DecisionResult.for_request(
            result_id=result_id,
            request=request,
            selected_option_id=option_id,
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


def _require_state(lifecycle: GameLifecycle) -> GameState:
    state = lifecycle.state
    assert state is not None
    return state


def _config() -> GameConfig:
    catalog = ArmyCatalog.phase9a_canonical_content_pack()
    return GameConfig(
        game_id="phase10l-integration-game",
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_tenth(
            descriptor_version="core-v2-phase10l-integration-test"
        ),
        army_catalog=catalog,
        army_muster_requests=(
            _army_muster_request(
                catalog=catalog,
                player_id="player-a",
                army_id="army-alpha",
                unit_selection_id="intercessor-unit-1",
            ),
            _army_muster_request(
                catalog=catalog,
                player_id="player-b",
                army_id="army-beta",
                unit_selection_id="intercessor-unit-2",
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
    unit_selection_id: str,
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
        unit_selections=(
            UnitMusterSelection(
                unit_selection_id=unit_selection_id,
                datasheet_id="core-intercessor-like-infantry",
                model_profile_selections=(
                    ModelProfileSelection(
                        model_profile_id="core-intercessor-like",
                        model_count=5,
                    ),
                ),
            ),
        ),
    )
