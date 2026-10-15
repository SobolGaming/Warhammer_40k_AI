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


def test_model_transition_records_round_trip_without_object_reprs() -> None:
    placement, removal, displacement = _transition_records()

    placement_payload = cast(
        ModelPlacementRecordPayload,
        json.loads(json.dumps(placement.to_payload(), sort_keys=True)),
    )
    removal_payload = cast(
        ModelRemovalRecordPayload,
        json.loads(json.dumps(removal.to_payload(), sort_keys=True)),
    )
    displacement_payload = cast(
        ModelDisplacementRecordPayload,
        json.loads(json.dumps(displacement.to_payload(), sort_keys=True)),
    )
    batch_payload = cast(
        BattlefieldTransitionBatchPayload,
        json.loads(
            json.dumps(
                BattlefieldTransitionBatch(
                    placements=(placement,),
                    removals=(removal,),
                    displacements=(displacement,),
                ).to_payload(),
                sort_keys=True,
            )
        ),
    )

    for payload in (placement_payload, removal_payload, displacement_payload, batch_payload):
        blob = json.dumps(payload, sort_keys=True)
        assert "<" not in blob
        assert "object at 0x" not in blob

    assert ModelPlacementRecord.from_payload(placement_payload).to_payload() == placement_payload
    assert ModelRemovalRecord.from_payload(removal_payload).to_payload() == removal_payload
    assert ModelDisplacementRecord.from_payload(displacement_payload).to_payload() == (
        displacement_payload
    )
    assert BattlefieldTransitionBatch.from_payload(batch_payload).to_payload() == batch_payload


def test_model_transition_records_fail_fast_on_invalid_shapes() -> None:
    start_pose = Pose.at(x=1.0, y=2.0)
    end_pose = Pose.at(x=2.0, y=2.0)
    witness = PathWitness.for_straight_line_endpoints(
        (("army-alpha:unit-1:model-1", start_pose, end_pose),)
    )

    with pytest.raises(PlacementError, match="must be a string"):
        ModelPlacementRecord(
            model_instance_id=cast(str, 1),
            placement_kind=BattlefieldPlacementKind.DEPLOYMENT,
            pose=start_pose,
        )
    with pytest.raises(PlacementError, match="stable identity prefix"):
        ModelPlacementRecord(
            model_instance_id="model:army-alpha:unit-1:model-1",
            placement_kind=BattlefieldPlacementKind.DEPLOYMENT,
            pose=start_pose,
        )
    with pytest.raises(PlacementError, match="Unsupported BattlefieldPlacementKind"):
        ModelPlacementRecord(
            model_instance_id="army-alpha:unit-1:model-1",
            placement_kind=cast(BattlefieldPlacementKind, "reinforcements"),
            pose=start_pose,
        )
    with pytest.raises(PlacementError, match="Unsupported BattlefieldRemovalKind"):
        ModelRemovalRecord(
            model_instance_id="army-alpha:unit-1:model-1",
            removal_kind=cast(BattlefieldRemovalKind, "disembark"),
        )
    with pytest.raises(PlacementError, match="Unsupported ModelDisplacementKind"):
        ModelDisplacementRecord(
            model_instance_id="army-alpha:unit-1:model-1",
            displacement_kind=cast(ModelDisplacementKind, "redeploy"),
            start_pose=start_pose,
            end_pose=end_pose,
            path_witness=witness,
        )
    with pytest.raises(PlacementError, match="pose must be a Pose"):
        ModelPlacementRecord(
            model_instance_id="army-alpha:unit-1:model-1",
            placement_kind=BattlefieldPlacementKind.DEPLOYMENT,
            pose=cast(Pose, "not-a-pose"),
        )
    with pytest.raises(PlacementError, match="must differ"):
        ModelDisplacementRecord(
            model_instance_id="army-alpha:unit-1:model-1",
            displacement_kind=ModelDisplacementKind.NORMAL_MOVE,
            start_pose=start_pose,
            end_pose=start_pose,
        )
    with pytest.raises(PlacementError, match="path_witness must be a PathWitness"):
        ModelDisplacementRecord(
            model_instance_id="army-alpha:unit-1:model-1",
            displacement_kind=ModelDisplacementKind.NORMAL_MOVE,
            start_pose=start_pose,
            end_pose=end_pose,
            path_witness=cast(PathWitness | None, "not-a-witness"),
        )
    with pytest.raises(PlacementError, match="must not be empty"):
        ModelPlacementRecord(
            model_instance_id="army-alpha:unit-1:model-1",
            placement_kind=BattlefieldPlacementKind.DEPLOYMENT,
            pose=start_pose,
            source_rule_id="",
        )
    with pytest.raises(PlacementError, match="must not be empty"):
        ModelRemovalRecord(
            model_instance_id="army-alpha:unit-1:model-1",
            removal_kind=BattlefieldRemovalKind.EMBARK,
            destination_id=" ",
        )


def test_transition_batch_rejects_duplicates_and_overlaps() -> None:
    placement = _placement_record("army-alpha:unit-1:model-1")
    duplicate_placement = _placement_record("army-alpha:unit-1:model-1")
    removal = _removal_record("army-alpha:unit-1:model-2")
    duplicate_removal = _removal_record("army-alpha:unit-1:model-2")
    displacement = _displacement_record("army-alpha:unit-1:model-3")
    duplicate_displacement = _displacement_record("army-alpha:unit-1:model-3")

    with pytest.raises(PlacementError, match="ModelPlacementRecord model_instance_id"):
        BattlefieldTransitionBatch(placements=(placement, duplicate_placement))
    with pytest.raises(PlacementError, match="ModelRemovalRecord model_instance_id"):
        BattlefieldTransitionBatch(removals=(removal, duplicate_removal))
    with pytest.raises(PlacementError, match="ModelDisplacementRecord model_instance_id"):
        BattlefieldTransitionBatch(displacements=(displacement, duplicate_displacement))
    with pytest.raises(PlacementError, match="placed and removed"):
        BattlefieldTransitionBatch(
            placements=(_placement_record("army-alpha:unit-1:model-4"),),
            removals=(_removal_record("army-alpha:unit-1:model-4"),),
        )
    with pytest.raises(PlacementError, match="placed and displaced"):
        BattlefieldTransitionBatch(
            placements=(_placement_record("army-alpha:unit-1:model-5"),),
            displacements=(_displacement_record("army-alpha:unit-1:model-5"),),
        )
    with pytest.raises(PlacementError, match="removed and displaced"):
        BattlefieldTransitionBatch(
            removals=(_removal_record("army-alpha:unit-1:model-6"),),
            displacements=(_displacement_record("army-alpha:unit-1:model-6"),),
        )


__all__: list[str] = []
__all__ += ["ArmyCatalog", "ArmyMusterRequest", "BattlePhase", "DecisionRequest"]
__all__ += ["DecisionResult", "DetachmentSelection", "GameConfig", "GameLifecycle"]
__all__ += ["LifecycleStatus", "LifecycleStatusKind", "MissionSetup", "ModelProfileSelection"]
__all__ += ["MovementMode", "MovementPhaseActionKind", "MovementPhaseStepKind"]
__all__ += ["SECONDARY_MISSION_DECISION_TYPE", "RulesetDescriptor"]
__all__ += ["SELECT_MOVEMENT_ACTION_DECISION_TYPE", "UnitMusterSelection"]
__all__ += ["_advance_to_movement_action_request", "_advance_to_movement_unit_selection"]
__all__ += ["_army_muster_request", "_config", "_decision_request", "_event_payloads"]
__all__ += ["_last_event_payload", "_mission_setup", "_submit_result"]
__all__ += ["_transition_batch_from_event_payload", "_unit_selection"]
__all__ += ["chapter_approved_2026_27_mission_pack", "straight_line_witness_for_unit"]
__all__ += ["submit_action_and_movement_proposal", "submit_all_deployments_if_pending"]
__all__ += ["submit_default_movement_proposal_if_pending"]
