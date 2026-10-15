from __future__ import annotations

from typing import cast

from tests.shared.category_migration.phase10d_battlefield_transitions import (
    SECONDARY_MISSION_DECISION_TYPE,
    SELECT_MOVEMENT_ACTION_DECISION_TYPE,
    ArmyCatalog,
    ArmyMusterRequest,
    BattlefieldPlacementKind,
    BattlefieldRemovalKind,
    BattlefieldTransitionBatch,
    BattlefieldTransitionBatchPayload,
    BattlePhase,
    DecisionRequest,
    DecisionResult,
    DetachmentSelection,
    GameConfig,
    GameLifecycle,
    LifecycleStatus,
    LifecycleStatusKind,
    MissionSetup,
    ModelDisplacementKind,
    ModelDisplacementRecord,
    ModelDisplacementRecordPayload,
    ModelPlacementRecord,
    ModelPlacementRecordPayload,
    ModelProfileSelection,
    ModelRemovalRecord,
    ModelRemovalRecordPayload,
    MovementMode,
    MovementPhaseActionKind,
    MovementPhaseStepKind,
    PathWitness,
    PlacementError,
    Pose,
    RulesetDescriptor,
    UnitMusterSelection,
    _advance_to_movement_action_request,
    _advance_to_movement_unit_selection,
    _army_muster_request,
    _config,
    _decision_request,
    _displacement_record,
    _event_payloads,
    _last_event_payload,
    _mission_setup,
    _placement_record,
    _removal_record,
    _submit_result,
    _transition_batch_from_event_payload,
    _transition_records,
    _unit_selection,
    chapter_approved_2026_27_mission_pack,
    json,
    pytest,
    straight_line_witness_for_unit,
    submit_action_and_movement_proposal,
    submit_all_deployments_if_pending,
    submit_default_movement_proposal_if_pending,
)


def test_deploy_armies_emits_deployment_placement_records() -> None:
    lifecycle, _status = _advance_to_movement_unit_selection(_config())
    assert lifecycle.state is not None
    battlefield_state = lifecycle.state.battlefield_state
    assert battlefield_state is not None
    placed_model_ids = set(battlefield_state.placed_model_ids())

    payloads = _event_payloads(lifecycle, "battlefield_models_placed")
    batches = tuple(_transition_batch_from_event_payload(payload) for payload in payloads)
    placed_records = tuple(record for batch in batches for record in batch.placements)

    assert len(payloads) == 3
    assert all(payload["game_id"] == "phase10d-game" for payload in payloads)
    assert all(payload["setup_step"] == "deploy_armies" for payload in payloads)
    assert all(
        payload["battlefield_id"]
        == "phase10d-game:take-and-hold-vs-purge-the-foe-layout-3-deployment:battlefield"
        for payload in payloads
    )
    assert all(
        payload["placement_kind"] == BattlefieldPlacementKind.DEPLOYMENT.value
        for payload in payloads
    )
    assert sum(cast(int, payload["placed_model_count"]) for payload in payloads) == len(
        placed_model_ids
    )
    assert len(placed_records) == len(placed_model_ids)
    assert all(batch.removals == () for batch in batches)
    assert all(batch.displacements == () for batch in batches)
    assert {record.model_instance_id for record in placed_records} == placed_model_ids
    for record in placed_records:
        assert record.placement_kind is BattlefieldPlacementKind.DEPLOYMENT
        assert record.source_phase is None
        assert record.source_step == "deploy_armies"
        assert record.source_rule_id == "core_rules_deploy_armies"
        assert record.source_event_id in {
            "phase10d-deploy-000002",
            "phase10d-deploy-000004",
            "phase10d-deploy-000006",
        }
        assert record.pose == battlefield_state.model_placement_by_id(record.model_instance_id).pose


def test_normal_move_emits_displacement_records() -> None:
    lifecycle, action_request = _advance_to_movement_action_request()

    submit_action_and_movement_proposal(
        lifecycle,
        request=action_request,
        option_id=MovementPhaseActionKind.NORMAL_MOVE.value,
        action_result_id="phase10d-result-000004",
        proposal_result_id="phase10d-normal-proposal-000004",
        unit_instance_id="army-alpha:intercessor-unit-1",
        movement_phase_action=MovementPhaseActionKind.NORMAL_MOVE,
        movement_mode=MovementMode.NORMAL,
        witness=straight_line_witness_for_unit(
            lifecycle,
            unit_instance_id="army-alpha:intercessor-unit-1",
            dx=6.0,
        ),
    )

    assert lifecycle.state is not None
    assert lifecycle.state.battlefield_state is not None
    moved_unit = lifecycle.state.battlefield_state.unit_placement_by_id(
        "army-alpha:intercessor-unit-1"
    )
    moved_model_ids = {placement.model_instance_id for placement in moved_unit.model_placements}
    terminal_event = _last_event_payload(lifecycle, "movement_activation_completed")
    batch = _transition_batch_from_event_payload(terminal_event)

    assert batch.placements == ()
    assert batch.removals == ()
    assert len(batch.displacements) == len(moved_model_ids)
    assert {record.model_instance_id for record in batch.displacements} == moved_model_ids
    for record in batch.displacements:
        assert record.displacement_kind is ModelDisplacementKind.NORMAL_MOVE
        assert record.source_phase == BattlePhase.MOVEMENT.value
        assert record.source_step == MovementPhaseStepKind.MOVE_UNITS.value
        assert record.source_rule_id is None
        assert record.source_event_id is None
        assert record.start_pose != record.end_pose
        assert record.path_witness is not None
        assert (
            record.end_pose
            == lifecycle.state.battlefield_state.model_placement_by_id(
                record.model_instance_id
            ).pose
        )


def test_remain_stationary_emits_no_transition_records() -> None:
    lifecycle, action_request = _advance_to_movement_action_request()
    assert lifecycle.state is not None
    battlefield_state = lifecycle.state.battlefield_state
    assert battlefield_state is not None
    before_payload = battlefield_state.to_payload()

    _submit_result(
        lifecycle,
        request=action_request,
        option_id=MovementPhaseActionKind.REMAIN_STATIONARY.value,
        result_id="phase10d-result-000004",
    )

    assert lifecycle.state.battlefield_state is not None
    assert lifecycle.state.battlefield_state.to_payload() == before_payload
    terminal_event = _last_event_payload(lifecycle, "movement_activation_completed")
    if "transition_batch" in terminal_event:
        batch = _transition_batch_from_event_payload(terminal_event)
        assert batch.to_payload() == {
            "placements": [],
            "removals": [],
            "displacements": [],
        }


def test_advance_emits_displacement_records() -> None:
    lifecycle, action_request = _advance_to_movement_action_request()

    submit_action_and_movement_proposal(
        lifecycle,
        request=action_request,
        option_id=MovementPhaseActionKind.ADVANCE.value,
        action_result_id="phase10d-result-000004",
        proposal_result_id="phase10d-advance-proposal-000004",
        unit_instance_id="army-alpha:intercessor-unit-1",
        movement_phase_action=MovementPhaseActionKind.ADVANCE,
        movement_mode=MovementMode.ADVANCE,
        witness=straight_line_witness_for_unit(
            lifecycle,
            unit_instance_id="army-alpha:intercessor-unit-1",
            dx=6.0,
        ),
    )

    assert lifecycle.state is not None
    assert lifecycle.state.battlefield_state is not None
    moved_unit = lifecycle.state.battlefield_state.unit_placement_by_id(
        "army-alpha:intercessor-unit-1"
    )
    moved_model_ids = {placement.model_instance_id for placement in moved_unit.model_placements}
    terminal_event = _last_event_payload(lifecycle, "movement_activation_completed")
    batch = _transition_batch_from_event_payload(terminal_event)

    assert batch.placements == ()
    assert batch.removals == ()
    assert len(batch.displacements) == len(moved_model_ids)
    assert {record.model_instance_id for record in batch.displacements} == moved_model_ids
    for record in batch.displacements:
        assert record.displacement_kind is ModelDisplacementKind.ADVANCE
        assert record.source_phase == BattlePhase.MOVEMENT.value
        assert record.source_step == MovementPhaseStepKind.MOVE_UNITS.value
        assert record.source_rule_id is None
        assert record.source_event_id is None
        assert record.start_pose != record.end_pose
        assert record.path_witness is not None


__all__: list[str] = []
__all__ += ["ArmyCatalog", "ArmyMusterRequest", "BattlefieldRemovalKind"]
__all__ += ["BattlefieldTransitionBatch", "BattlefieldTransitionBatchPayload", "DecisionRequest"]
__all__ += ["DecisionResult", "DetachmentSelection", "GameConfig", "GameLifecycle"]
__all__ += ["LifecycleStatus", "LifecycleStatusKind", "MissionSetup", "ModelDisplacementRecord"]
__all__ += ["ModelDisplacementRecordPayload", "ModelPlacementRecord"]
__all__ += ["ModelPlacementRecordPayload", "ModelProfileSelection", "ModelRemovalRecord"]
__all__ += ["ModelRemovalRecordPayload", "PathWitness", "PlacementError", "Pose"]
__all__ += ["SECONDARY_MISSION_DECISION_TYPE", "RulesetDescriptor"]
__all__ += ["SELECT_MOVEMENT_ACTION_DECISION_TYPE", "UnitMusterSelection", "_army_muster_request"]
__all__ += ["_decision_request", "_displacement_record", "_mission_setup", "_placement_record"]
__all__ += ["_removal_record", "_transition_records", "_unit_selection"]
__all__ += ["chapter_approved_2026_27_mission_pack", "json", "pytest"]
__all__ += ["submit_all_deployments_if_pending", "submit_default_movement_proposal_if_pending"]
