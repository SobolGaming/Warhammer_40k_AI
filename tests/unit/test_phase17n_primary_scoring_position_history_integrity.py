from __future__ import annotations

from typing import Literal

from tests.shared.category_migration.phase17n_primary_scoring_position_history_integrity import (
    BattlePhase,
    DecisionController,
    GameLifecycle,
    GameLifecycleError,
    GameLifecyclePayload,
    ObjectiveControlContext,
    ObjectiveControlTiming,
    ObjectiveMarkerRole,
    Pose,
    append_authenticated_normal_move,
    bound_primary_scoring_commit_checkpoint,
    build_current_primary_rules_unit_memberships,
    build_primary_scoring_state_evidence,
    canonical_payload_sha256,
    deepcopy,
    emit_primary_scoring_commit_checkpoint,
    mission_scoring_policies_from_setup,
    phase17n_event_setup,
    phase17n_state_with_setup,
    pytest,
    record_primary_scoring_state_evidence,
    resolve_objective_control,
    resolve_primary_scoring_boundary_lifecycle,
    scoring_position_lifecycle_payload,
    with_model_offsets,
)


@pytest.mark.parametrize(
    "cleared_field",
    ["evaluated_models", "terrain_areas", "objective_witnesses"],
)
def test_restore_rejects_rehashed_incomplete_primary_position_witness(
    scoring_position_lifecycle_payload: GameLifecyclePayload,
    cleared_field: Literal["evaluated_models", "terrain_areas", "objective_witnesses"],
) -> None:
    payload = deepcopy(scoring_position_lifecycle_payload)
    evidence = payload["state"]["primary_scoring_state_evidence_records"][0]
    did_clear = False
    for witness in evidence["current_rules_unit_position_witnesses"]:
        for component in witness["rules_unit_membership"]["component_memberships"]:
            if cleared_field == "evaluated_models" and component["evaluated_model_instance_ids"]:
                component["evaluated_model_instance_ids"] = []
                component["objective_marker_witnesses"] = []
                did_clear = True
                break
            if cleared_field == "terrain_areas" and component["logical_terrain_area_ids"]:
                component["logical_terrain_area_ids"] = []
                did_clear = True
                break
            if cleared_field == "objective_witnesses" and component["objective_marker_witnesses"]:
                component["objective_marker_witnesses"] = []
                did_clear = True
                break
        if did_clear:
            break
    assert did_clear
    old_evidence_id = evidence["evidence_id"]
    content = {
        key: value for key, value in evidence.items() if key not in {"evidence_id", "evidence_hash"}
    }
    digest = canonical_payload_sha256(content)
    evidence["evidence_id"] = f"primary-scoring-state-evidence:{digest}"
    evidence["evidence_hash"] = digest
    for ledger in payload["state"]["victory_point_ledgers"]:
        for transaction in ledger["transactions"]:
            metadata = transaction["metadata"]
            if not isinstance(metadata, dict):
                continue
            if metadata.get("primary_scoring_state_evidence_id") != old_evidence_id:
                continue
            metadata["primary_scoring_state_evidence_id"] = evidence["evidence_id"]
            metadata["primary_scoring_state_evidence_hash"] = digest
    for row in payload["state"]["primary_scoring_boundary_lifecycles"]:
        if row["evidence_id"] != old_evidence_id:
            continue
        row["evidence_id"] = evidence["evidence_id"]
        lifecycle_content = {
            key: value
            for key, value in row.items()
            if key not in {"lifecycle_id", "lifecycle_hash"}
        }
        lifecycle_digest = canonical_payload_sha256(lifecycle_content)
        row["lifecycle_id"] = f"primary-scoring-boundary-lifecycle:{lifecycle_digest}"
        row["lifecycle_hash"] = lifecycle_digest

    with pytest.raises(
        GameLifecycleError,
        match="position witness drifted from authoritative boundary history",
    ):
        GameLifecycle.from_payload(payload)


def test_restore_uses_historical_boundary_positions_before_later_authenticated_move(
    scoring_position_lifecycle_payload: GameLifecyclePayload,
) -> None:
    lifecycle = GameLifecycle.from_payload(deepcopy(scoring_position_lifecycle_payload))
    state = lifecycle.state
    assert state is not None
    state.battle_round = 3
    state.active_player_id = "player-a"
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.MOVEMENT)
    moved_unit = next(
        unit
        for army in state.army_definitions
        if army.player_id == "player-a"
        for unit in army.units
    )
    append_authenticated_normal_move(
        state=state,
        decisions=lifecycle.decision_controller,
        unit_instance_id=moved_unit.unit_instance_id,
        suffix="after-primary-scoring-boundary",
        pose_transform=lambda pose: Pose.at(
            pose.position.x,
            pose.position.y + 6.0,
            pose.position.z,
            facing_degrees=pose.facing.degrees,
        ),
    )
    historical = state.primary_scoring_state_evidence_records[0].position_witness_for_rules_unit(
        moved_unit.unit_instance_id
    )
    current = next(
        membership
        for membership in build_current_primary_rules_unit_memberships(state=state)
        if membership.rules_unit_instance_id == moved_unit.unit_instance_id
    )
    assert current != historical.rules_unit_membership

    restored = GameLifecycle.from_payload(lifecycle.to_payload())
    assert restored.state is not None
    assert restored.state.primary_scoring_state_evidence_records == (
        state.primary_scoring_state_evidence_records
    )


__all__: list[str] = []
__all__ += ["DecisionController", "ObjectiveControlContext", "ObjectiveControlTiming"]
__all__ += ["ObjectiveMarkerRole", "bound_primary_scoring_commit_checkpoint"]
__all__ += ["build_primary_scoring_state_evidence", "emit_primary_scoring_commit_checkpoint"]
__all__ += ["mission_scoring_policies_from_setup", "phase17n_event_setup"]
__all__ += ["phase17n_state_with_setup", "record_primary_scoring_state_evidence"]
__all__ += ["resolve_objective_control", "resolve_primary_scoring_boundary_lifecycle"]
__all__ += ["scoring_position_lifecycle_payload", "with_model_offsets"]
