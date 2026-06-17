from __future__ import annotations

from dataclasses import replace

from tests.deployment_submission_helpers import (
    default_deployment_pose,
    submit_all_deployments_if_pending,
)
from tests.movement_submission_helpers import submit_movement_proposal

from warhammer40k_core.adapters.decisions import submit_option
from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.core.ruleset_descriptor import MovementMode, RulesetDescriptor
from warhammer40k_core.engine.army_mustering import ArmyMusterRequest
from warhammer40k_core.engine.battlefield_state import UnitPlacement
from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.game_state import GameConfig
from warhammer40k_core.engine.lifecycle import GameLifecycle
from warhammer40k_core.engine.list_validation import (
    DetachmentSelection,
    ModelProfileSelection,
    UnitMusterSelection,
)
from warhammer40k_core.engine.mission_setup import MissionSetup
from warhammer40k_core.engine.movement_proposals import MOVEMENT_PROPOSAL_DECISION_TYPE
from warhammer40k_core.engine.phase import LifecycleStatus, LifecycleStatusKind
from warhammer40k_core.engine.phases.movement import (
    SELECT_MOVEMENT_ACTION_DECISION_TYPE,
    SELECT_MOVEMENT_UNIT_DECISION_TYPE,
    MovementPhaseActionKind,
)
from warhammer40k_core.engine.setup_flow import SECONDARY_MISSION_DECISION_TYPE
from warhammer40k_core.geometry.pathing import PathWitness
from warhammer40k_core.geometry.pose import Pose
from warhammer40k_core.rules.mission_pack_import import chapter_approved_2026_27_mission_pack

_MONSTER_UNIT_ID = "army-alpha:vehicle-monster-1"


def test_live_advance_uses_mission_depth_for_large_model_edge() -> None:
    lifecycle, action_request = _advance_to_monster_action_request()
    _place_monster(lifecycle, Pose.at(10.0, 50.0, 0.0, facing_degrees=0.0))

    proposal_status = submit_option(
        lifecycle=lifecycle,
        request_id=action_request.request_id,
        option_id=MovementPhaseActionKind.ADVANCE.value,
        result_id="phase10v-advance-action",
    )
    proposal_request = _decision_request(proposal_status)
    assert proposal_request.decision_type == MOVEMENT_PROPOSAL_DECISION_TYPE
    witness = _single_model_witness_to_pose(
        lifecycle,
        end_pose=Pose.at(5.660714285714285, 54.73214285714286, 0.0, facing_degrees=0.0),
    )

    status = submit_movement_proposal(
        lifecycle,
        request=proposal_request,
        result_id="phase10v-advance-proposal",
        unit_instance_id=_MONSTER_UNIT_ID,
        movement_phase_action=MovementPhaseActionKind.ADVANCE,
        movement_mode=MovementMode.ADVANCE,
        witness=witness,
    )

    assert status.status_kind is not LifecycleStatusKind.INVALID
    assert _movement_invalid_event_codes(lifecycle) == ()


def test_live_advance_still_rejects_true_mission_depth_edge_crossing() -> None:
    lifecycle, action_request = _advance_to_monster_action_request()
    _place_monster(lifecycle, Pose.at(10.0, 50.0, 0.0, facing_degrees=0.0))

    proposal_status = submit_option(
        lifecycle=lifecycle,
        request_id=action_request.request_id,
        option_id=MovementPhaseActionKind.ADVANCE.value,
        result_id="phase10v-invalid-advance-action",
    )
    proposal_request = _decision_request(proposal_status)
    witness = _single_model_witness_to_pose(
        lifecycle,
        end_pose=Pose.at(10.0, 58.0, 0.0, facing_degrees=0.0),
    )

    status = submit_movement_proposal(
        lifecycle,
        request=proposal_request,
        result_id="phase10v-invalid-advance-proposal",
        unit_instance_id=_MONSTER_UNIT_ID,
        movement_phase_action=MovementPhaseActionKind.ADVANCE,
        movement_mode=MovementMode.ADVANCE,
        witness=witness,
    )

    assert status.status_kind is LifecycleStatusKind.INVALID
    assert _status_violation_code(status) == "battlefield_edge_crossed"
    assert _movement_invalid_event_codes(lifecycle) == ("battlefield_edge_crossed",)


def _advance_to_monster_action_request() -> tuple[GameLifecycle, DecisionRequest]:
    lifecycle = GameLifecycle()
    lifecycle.start(_config())
    first_status = lifecycle.advance_until_decision_or_terminal()
    assert _decision_request(first_status).decision_type == SECONDARY_MISSION_DECISION_TYPE
    second_status = submit_option(
        lifecycle=lifecycle,
        request_id=_decision_request(first_status).request_id,
        option_id="fixed:assassination:bring_it_down",
        result_id="phase10v-secondary-player-a",
    )
    assert _decision_request(second_status).decision_type == SECONDARY_MISSION_DECISION_TYPE
    deployment_status = submit_option(
        lifecycle=lifecycle,
        request_id=_decision_request(second_status).request_id,
        option_id="fixed:assassination:bring_it_down",
        result_id="phase10v-secondary-player-b",
    )
    movement_status = submit_all_deployments_if_pending(
        lifecycle,
        deployment_status,
        result_id_prefix="phase10v-deploy",
        pose_factory=_deployment_pose,
    )
    unit_request = _decision_request(movement_status)
    assert unit_request.decision_type == SELECT_MOVEMENT_UNIT_DECISION_TYPE
    action_status = submit_option(
        lifecycle=lifecycle,
        request_id=unit_request.request_id,
        option_id=_MONSTER_UNIT_ID,
        result_id="phase10v-select-monster",
    )
    action_request = _decision_request(action_status)
    assert action_request.decision_type == SELECT_MOVEMENT_ACTION_DECISION_TYPE
    return lifecycle, action_request


def _config() -> GameConfig:
    catalog = ArmyCatalog.phase9a_canonical_content_pack()
    return GameConfig(
        game_id="phase10v-game",
        allow_legacy_non_strict_rosters=True,
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(
            descriptor_version="core-v2-phase10v-mission-geometry"
        ),
        army_catalog=catalog,
        army_muster_requests=(
            _army_muster_request(
                catalog=catalog,
                player_id="player-a",
                army_id="army-alpha",
                unit_selection_id="vehicle-monster-1",
            ),
            _army_muster_request(
                catalog=catalog,
                player_id="player-b",
                army_id="army-beta",
                unit_selection_id="vehicle-monster-2",
            ),
        ),
        player_ids=("player-a", "player-b"),
        turn_order=("player-a", "player-b"),
        fixed_secondary_mission_ids=("assassination", "bring_it_down", "cleanse"),
        mission_setup=replace(_mission_setup(), terrain_features=()),
    )


def _mission_setup() -> MissionSetup:
    mission_pack = chapter_approved_2026_27_mission_pack()
    implemented_setup = MissionSetup.from_mission_pack(
        mission_pack=mission_pack,
        mission_pool_entry_id="mission-take-and-hold-vs-purge-the-foe-layout-3",
        terrain_layout_id="take-and-hold-vs-purge-the-foe-layout-3",
        attacker_player_id="player-a",
        defender_player_id="player-b",
    )
    typed_layout = mission_pack.battlefield_layout("take-and-hold-vs-take-and-hold-layout-3")
    typed_deployment_map = mission_pack.deployment_map(typed_layout.deployment_map_id)
    return replace(
        implemented_setup,
        battlefield_layout_id=typed_layout.battlefield_layout_id,
        deployment_map_id=typed_layout.deployment_map_id,
        terrain_layout_id=typed_layout.terrain_layout_id,
        battlefield_width_inches=typed_layout.battlefield_width_inches,
        battlefield_depth_inches=typed_layout.battlefield_depth_inches,
        objective_markers=typed_layout.objective_markers,
        deployment_zones=typed_deployment_map.deployment_zones_for_players(
            attacker_player_id="player-a",
            defender_player_id="player-b",
        ),
        battlefield_regions=typed_layout.battlefield_regions,
        terrain_areas=typed_layout.terrain_areas,
        terrain_features=(),
        objective_terrain_areas=typed_layout.objective_terrain_areas,
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
            detachment_ids=("core-combined-arms",),
        ),
        unit_selections=(
            UnitMusterSelection(
                unit_selection_id=unit_selection_id,
                datasheet_id="core-vehicle-monster",
                model_profile_selections=(
                    ModelProfileSelection(
                        model_profile_id="core-vehicle-monster",
                        model_count=1,
                    ),
                ),
            ),
        ),
    )


def _deployment_pose(index: int, player_id: str, model_instance_id: str) -> Pose:
    if model_instance_id.startswith(_MONSTER_UNIT_ID):
        return Pose.at(10.0, 42.0, 0.0, facing_degrees=0.0)
    if model_instance_id.startswith("army-beta:vehicle-monster-2"):
        return Pose.at(34.0, 18.0, 0.0, facing_degrees=180.0)
    return default_deployment_pose(index, player_id, model_instance_id)


def _place_monster(lifecycle: GameLifecycle, pose: Pose) -> None:
    state = lifecycle.state
    assert state is not None
    battlefield_state = state.battlefield_state
    assert battlefield_state is not None
    unit_placement = battlefield_state.unit_placement_by_id(_MONSTER_UNIT_ID)
    state.replace_battlefield_state(
        battlefield_state.with_unit_placement(_single_model_unit_with_pose(unit_placement, pose))
    )


def _single_model_unit_with_pose(unit_placement: UnitPlacement, pose: Pose) -> UnitPlacement:
    placement = unit_placement.model_placements[0]
    return unit_placement.with_model_placements((placement.with_pose(pose),))


def _single_model_witness_to_pose(
    lifecycle: GameLifecycle,
    *,
    end_pose: Pose,
) -> PathWitness:
    state = lifecycle.state
    assert state is not None
    assert state.battlefield_state is not None
    unit_placement = state.battlefield_state.unit_placement_by_id(_MONSTER_UNIT_ID)
    placement = unit_placement.model_placements[0]
    start = placement.pose
    midpoint = Pose.at(
        (start.position.x + end_pose.position.x) / 2.0,
        (start.position.y + end_pose.position.y) / 2.0,
        (start.position.z + end_pose.position.z) / 2.0,
        facing_degrees=(start.facing.degrees + end_pose.facing.degrees) / 2.0,
    )
    return PathWitness.for_paths(((placement.model_instance_id, (start, midpoint, end_pose)),))


def _decision_request(status: LifecycleStatus) -> DecisionRequest:
    assert status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    assert status.decision_request is not None
    return status.decision_request


def _status_violation_code(status: LifecycleStatus) -> str:
    payload = status.payload
    assert isinstance(payload, dict)
    violation_code = payload["violation_code"]
    assert isinstance(violation_code, str)
    return violation_code


def _movement_invalid_event_codes(lifecycle: GameLifecycle) -> tuple[str, ...]:
    codes: list[str] = []
    for event in lifecycle.decision_controller.event_log.records:
        if event.event_type != "movement_proposal_invalid":
            continue
        payload = event.payload
        assert isinstance(payload, dict)
        violation_code = payload["violation_code"]
        assert isinstance(violation_code, str)
        codes.append(violation_code)
    return tuple(codes)
