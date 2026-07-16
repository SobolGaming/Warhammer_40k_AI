from __future__ import annotations

from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.core.ruleset_descriptor import RulesetDescriptor
from warhammer40k_core.engine.army_mustering import ArmyMusterRequest, muster_army
from warhammer40k_core.engine.battlefield_state import BattlefieldScenario, UnitPlacement
from warhammer40k_core.engine.decision import DiceRollManager
from warhammer40k_core.engine.list_validation import (
    DetachmentSelection,
    UnitMusterSelection,
)
from warhammer40k_core.engine.phases.movement import (
    AdvanceMoveResolution,
    AdvanceRollRequest,
    AdvanceRollResult,
    resolve_advance_move,
)
from warhammer40k_core.engine.placement import create_deterministic_battlefield_scenario
from warhammer40k_core.engine.wargear_selections import (
    ModelProfileSelection,
)
from warhammer40k_core.geometry.pathing import PathWitness
from warhammer40k_core.geometry.pose import Pose

_MONSTER_UNIT_ID = "army-alpha:vehicle-monster-1"


def test_advance_resolver_uses_explicit_battlefield_depth_for_large_model_edge() -> None:
    valid_scenario = _monster_scenario_with_active_pose(
        Pose.at(10.0, 50.0, 0.0, facing_degrees=0.0),
        battlefield_width_inches=44.0,
        battlefield_depth_inches=60.0,
    )
    invalid_scenario = _monster_scenario_with_active_pose(
        Pose.at(10.0, 50.0, 0.0, facing_degrees=0.0),
        battlefield_width_inches=44.0,
        battlefield_depth_inches=44.0,
    )
    unit_placement = valid_scenario.battlefield_state.unit_placement_by_id(_MONSTER_UNIT_ID)
    witness = _single_model_witness_to_pose(
        unit_placement,
        end_pose=Pose.at(5.660714285714285, 54.73214285714286, 0.0, facing_degrees=0.0),
    )

    valid_on_mission_depth = resolve_advance_move(
        scenario=valid_scenario,
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(),
        unit_placement=unit_placement,
        advance_roll=_fixed_advance_roll(value=1),
        path_witness=witness,
    )
    invalid_unit_placement = invalid_scenario.battlefield_state.unit_placement_by_id(
        _MONSTER_UNIT_ID
    )
    invalid_on_stale_depth = resolve_advance_move(
        scenario=invalid_scenario,
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(),
        unit_placement=invalid_unit_placement,
        advance_roll=_fixed_advance_roll(value=1),
        path_witness=witness,
    )

    assert valid_on_mission_depth.is_valid
    assert "battlefield_edge_crossed" not in _violation_codes(valid_on_mission_depth)
    assert not invalid_on_stale_depth.is_valid
    assert "battlefield_edge_crossed" in _violation_codes(invalid_on_stale_depth)


def _monster_scenario_with_active_pose(
    pose: Pose,
    *,
    battlefield_width_inches: float,
    battlefield_depth_inches: float,
) -> BattlefieldScenario:
    catalog = ArmyCatalog.phase9a_canonical_content_pack()
    scenario = create_deterministic_battlefield_scenario(
        battlefield_id="phase10v-mission-geometry",
        battlefield_width_inches=battlefield_width_inches,
        battlefield_depth_inches=battlefield_depth_inches,
        armies=(
            muster_army(
                catalog=catalog,
                request=_army_muster_request(
                    catalog=catalog,
                    player_id="player-a",
                    army_id="army-alpha",
                    unit_selection_id="vehicle-monster-1",
                ),
            ),
            muster_army(
                catalog=catalog,
                request=_army_muster_request(
                    catalog=catalog,
                    player_id="player-b",
                    army_id="army-beta",
                    unit_selection_id="vehicle-monster-2",
                ),
            ),
        ),
    )
    unit_placement = scenario.battlefield_state.unit_placement_by_id(_MONSTER_UNIT_ID)
    updated_state = scenario.battlefield_state.with_unit_placement(
        _single_model_unit_with_pose(unit_placement, pose)
    )
    return BattlefieldScenario(armies=scenario.armies, battlefield_state=updated_state)


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
        force_disposition_id="purge-the-foe",
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


def _single_model_unit_with_pose(unit_placement: UnitPlacement, pose: Pose) -> UnitPlacement:
    placement = unit_placement.model_placements[0]
    return unit_placement.with_model_placements((placement.with_pose(pose),))


def _single_model_witness_to_pose(
    unit_placement: UnitPlacement,
    *,
    end_pose: Pose,
) -> PathWitness:
    placement = unit_placement.model_placements[0]
    start = placement.pose
    midpoint = Pose.at(
        (start.position.x + end_pose.position.x) / 2.0,
        (start.position.y + end_pose.position.y) / 2.0,
        (start.position.z + end_pose.position.z) / 2.0,
        facing_degrees=(start.facing.degrees + end_pose.facing.degrees) / 2.0,
    )
    return PathWitness.for_paths(((placement.model_instance_id, (start, midpoint, end_pose)),))


def _fixed_advance_roll(*, value: int) -> AdvanceRollResult:
    request = AdvanceRollRequest.for_unit(
        request_id="phase10v-fixed-advance-roll",
        game_id="phase10v-game",
        battle_round=1,
        player_id="player-a",
        unit_instance_id=_MONSTER_UNIT_ID,
    )
    roll_state = DiceRollManager("phase10v-game").roll_fixed(request.spec, [value])
    return AdvanceRollResult.from_roll_state(request=request, roll_state=roll_state)


def _violation_codes(resolution: AdvanceMoveResolution) -> set[str]:
    return {
        violation.violation_code
        for path_result in resolution.path_validation_results
        for violation in path_result.violations
    }
