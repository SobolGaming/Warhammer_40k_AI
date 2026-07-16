from __future__ import annotations

import json
from typing import cast

import pytest
from tests.deployment_submission_helpers import submit_all_deployments_if_pending
from tests.movement_submission_helpers import (
    straight_line_witness_for_unit,
    submit_action_and_movement_proposal,
    submit_default_movement_proposal_if_pending,
)

from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.core.ruleset_descriptor import MovementMode, RulesetDescriptor
from warhammer40k_core.engine.army_mustering import ArmyMusterRequest
from warhammer40k_core.engine.battlefield_state import (
    BattlefieldPlacementKind,
    BattlefieldRemovalKind,
    BattlefieldTransitionBatch,
    BattlefieldTransitionBatchPayload,
    ModelDisplacementKind,
    ModelDisplacementRecord,
    ModelDisplacementRecordPayload,
    ModelPlacementRecord,
    ModelPlacementRecordPayload,
    ModelRemovalRecord,
    ModelRemovalRecordPayload,
    PlacementError,
)
from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.game_state import GameConfig
from warhammer40k_core.engine.lifecycle import GameLifecycle
from warhammer40k_core.engine.list_validation import (
    DetachmentSelection,
    UnitMusterSelection,
)
from warhammer40k_core.engine.mission_setup import MissionSetup
from warhammer40k_core.engine.phase import BattlePhase, LifecycleStatus, LifecycleStatusKind
from warhammer40k_core.engine.phases.movement import (
    SELECT_MOVEMENT_ACTION_DECISION_TYPE,
    MovementPhaseActionKind,
    MovementPhaseStepKind,
)
from warhammer40k_core.engine.setup_flow import SECONDARY_MISSION_DECISION_TYPE
from warhammer40k_core.engine.wargear_selections import (
    ModelProfileSelection,
)
from warhammer40k_core.geometry.pathing import PathWitness
from warhammer40k_core.geometry.pose import Pose
from warhammer40k_core.rules.mission_pack_import import chapter_approved_2026_27_mission_pack


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


def _transition_records() -> tuple[
    ModelPlacementRecord,
    ModelRemovalRecord,
    ModelDisplacementRecord,
]:
    return (
        _placement_record("army-alpha:unit-1:model-1"),
        _removal_record("army-alpha:unit-1:model-2"),
        _displacement_record("army-alpha:unit-1:model-3"),
    )


def _placement_record(model_instance_id: str) -> ModelPlacementRecord:
    return ModelPlacementRecord(
        model_instance_id=model_instance_id,
        placement_kind=BattlefieldPlacementKind.DEPLOYMENT,
        pose=Pose.at(x=1.0, y=2.0),
        source_phase=None,
        source_step="deploy_armies",
        source_rule_id="phase10a_deterministic_bridge",
        source_event_id=None,
    )


def _removal_record(model_instance_id: str) -> ModelRemovalRecord:
    return ModelRemovalRecord(
        model_instance_id=model_instance_id,
        removal_kind=BattlefieldRemovalKind.EMBARK,
        source_phase=BattlePhase.MOVEMENT.value,
        source_step=MovementPhaseStepKind.MOVE_UNITS.value,
        source_rule_id="transport-test",
        source_event_id="event-000123",
        destination_id="transport-alpha",
    )


def _displacement_record(model_instance_id: str) -> ModelDisplacementRecord:
    start_pose = Pose.at(x=1.0, y=2.0)
    end_pose = Pose.at(x=4.0, y=2.0)
    return ModelDisplacementRecord(
        model_instance_id=model_instance_id,
        displacement_kind=ModelDisplacementKind.NORMAL_MOVE,
        start_pose=start_pose,
        end_pose=end_pose,
        path_witness=PathWitness.for_straight_line_endpoints(
            ((model_instance_id, start_pose, end_pose),)
        ),
        source_phase=BattlePhase.MOVEMENT.value,
        source_step=MovementPhaseStepKind.MOVE_UNITS.value,
        source_rule_id=None,
        source_event_id=None,
    )


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
        result_id="phase10d-result-000001",
    )
    assert _decision_request(second_status).decision_type == SECONDARY_MISSION_DECISION_TYPE
    deployment_status = _submit_result(
        lifecycle,
        request=_decision_request(second_status),
        option_id="fixed:assassination:bring_it_down",
        result_id="phase10d-result-000002",
    )
    movement_status = submit_all_deployments_if_pending(
        lifecycle,
        deployment_status,
        result_id_prefix="phase10d-deploy",
    )
    return lifecycle, movement_status


def _advance_to_movement_action_request() -> tuple[GameLifecycle, DecisionRequest]:
    lifecycle, status = _advance_to_movement_unit_selection(_config())
    request = _decision_request(status)
    action_status = _submit_result(
        lifecycle,
        request=request,
        option_id="army-alpha:intercessor-unit-1",
        result_id="phase10d-result-000003",
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


def _event_payloads(lifecycle: GameLifecycle, event_type: str) -> tuple[dict[str, object], ...]:
    return tuple(
        cast(dict[str, object], event.payload)
        for event in lifecycle.decision_controller.event_log.records
        if event.event_type == event_type
    )


def _transition_batch_from_event_payload(
    payload: dict[str, object],
) -> BattlefieldTransitionBatch:
    transition_payload = cast(BattlefieldTransitionBatchPayload, payload["transition_batch"])
    return BattlefieldTransitionBatch.from_payload(transition_payload)


def _config() -> GameConfig:
    catalog = ArmyCatalog.phase9a_canonical_content_pack()
    return GameConfig(
        game_id="phase10d-game",
        allow_legacy_non_strict_rosters=True,
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(
            descriptor_version="core-v2-phase10d-test"
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
        mission_pool_entry_id="mission-take-and-hold-vs-purge-the-foe-layout-3",
        terrain_layout_id="take-and-hold-vs-purge-the-foe-layout-3",
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
        force_disposition_id="purge-the-foe",
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
