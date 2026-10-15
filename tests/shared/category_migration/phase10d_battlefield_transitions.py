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
from warhammer40k_core.engine.list_validation import DetachmentSelection, UnitMusterSelection
from warhammer40k_core.engine.mission_setup import MissionSetup
from warhammer40k_core.engine.phase import BattlePhase, LifecycleStatus, LifecycleStatusKind
from warhammer40k_core.engine.phases.movement import (
    SELECT_MOVEMENT_ACTION_DECISION_TYPE,
    MovementPhaseActionKind,
    MovementPhaseStepKind,
)
from warhammer40k_core.engine.setup_flow import SECONDARY_MISSION_DECISION_TYPE
from warhammer40k_core.engine.wargear_selections import ModelProfileSelection
from warhammer40k_core.geometry.pathing import PathWitness
from warhammer40k_core.geometry.pose import Pose
from warhammer40k_core.rules.mission_pack_import import chapter_approved_2026_27_mission_pack


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
        attacker_force_disposition_id="take-and-hold",
        defender_player_id="player-b",
        defender_force_disposition_id="purge-the-foe",
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
        force_disposition_id=("take-and-hold" if player_id == "player-a" else "purge-the-foe"),
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


__all__: list[str] = []
__all__ += ["ArmyCatalog", "ArmyMusterRequest", "BattlePhase", "BattlefieldPlacementKind"]
__all__ += ["BattlefieldRemovalKind", "BattlefieldTransitionBatch"]
__all__ += ["BattlefieldTransitionBatchPayload", "DecisionRequest", "DecisionResult"]
__all__ += ["DetachmentSelection", "GameConfig", "GameLifecycle", "LifecycleStatus"]
__all__ += ["LifecycleStatusKind", "MissionSetup", "ModelDisplacementKind"]
__all__ += ["ModelDisplacementRecord", "ModelDisplacementRecordPayload", "ModelPlacementRecord"]
__all__ += ["ModelPlacementRecordPayload", "ModelProfileSelection", "ModelRemovalRecord"]
__all__ += ["ModelRemovalRecordPayload", "MovementMode", "MovementPhaseActionKind"]
__all__ += ["MovementPhaseStepKind", "PathWitness", "PlacementError", "Pose", "RulesetDescriptor"]
__all__ += ["SECONDARY_MISSION_DECISION_TYPE", "SELECT_MOVEMENT_ACTION_DECISION_TYPE"]
__all__ += ["UnitMusterSelection", "_advance_to_movement_action_request"]
__all__ += ["_advance_to_movement_unit_selection", "_army_muster_request", "_config"]
__all__ += ["_decision_request", "_displacement_record", "_event_payloads", "_last_event_payload"]
__all__ += ["_mission_setup", "_placement_record", "_removal_record", "_submit_result"]
__all__ += ["_transition_batch_from_event_payload", "_transition_records", "_unit_selection"]
__all__ += ["cast", "chapter_approved_2026_27_mission_pack", "json", "pytest"]
__all__ += ["straight_line_witness_for_unit", "submit_action_and_movement_proposal"]
__all__ += ["submit_all_deployments_if_pending", "submit_default_movement_proposal_if_pending"]
