from __future__ import annotations

from warhammer40k_core.engine.army_mustering import ArmyDefinition
from warhammer40k_core.engine.battlefield_state import (
    BattlefieldRuntimeState,
    BattlefieldScenario,
    ModelPlacement,
    PlacedArmy,
    PlacementError,
    UnitPlacement,
)
from warhammer40k_core.engine.unit_factory import UnitInstance
from warhammer40k_core.geometry.pose import Pose
from warhammer40k_core.geometry.terrain import TerrainFeatureDefinition

DETERMINISTIC_BRIDGE_BATTLEFIELD_WIDTH_INCHES = 60.0
DETERMINISTIC_BRIDGE_BATTLEFIELD_DEPTH_INCHES = 44.0


def create_deterministic_battlefield_scenario(
    *,
    battlefield_id: str,
    armies: tuple[ArmyDefinition, ...],
    battlefield_width_inches: float = DETERMINISTIC_BRIDGE_BATTLEFIELD_WIDTH_INCHES,
    battlefield_depth_inches: float = DETERMINISTIC_BRIDGE_BATTLEFIELD_DEPTH_INCHES,
    terrain_features: tuple[TerrainFeatureDefinition, ...] = (),
) -> BattlefieldScenario:
    """Create a minimal deterministic placement bridge for vertical-slice tests.

    This is not deployment. It places every mustered runtime model in predictable
    rows so movement tests have real model instances, base sizes, characteristics,
    and poses to consume.
    """
    if type(armies) is not tuple:
        raise PlacementError("armies must be a tuple.")
    if not armies:
        raise PlacementError("armies must not be empty.")
    for army in armies:
        if type(army) is not ArmyDefinition:
            raise PlacementError("armies must contain ArmyDefinition values.")
    placed_armies = tuple(
        _placed_army_for_index(army=army, army_index=army_index)
        for army_index, army in enumerate(sorted(armies, key=lambda item: item.player_id))
    )
    return BattlefieldScenario(
        armies=armies,
        battlefield_state=BattlefieldRuntimeState(
            battlefield_id=battlefield_id,
            battlefield_width_inches=battlefield_width_inches,
            battlefield_depth_inches=battlefield_depth_inches,
            terrain_features=terrain_features,
            placed_armies=placed_armies,
        ),
    )


def _placed_army_for_index(*, army: ArmyDefinition, army_index: int) -> PlacedArmy:
    if type(army) is not ArmyDefinition:
        raise PlacementError("armies must contain ArmyDefinition values.")
    unit_placements = tuple(
        _unit_placement_for_index(
            army=army,
            unit_index=unit_index,
            unit=unit,
            army_index=army_index,
        )
        for unit_index, unit in enumerate(army.units)
    )
    return PlacedArmy(
        army_id=army.army_id,
        player_id=army.player_id,
        unit_placements=unit_placements,
    )


def _unit_placement_for_index(
    *,
    army: ArmyDefinition,
    unit_index: int,
    unit: UnitInstance,
    army_index: int,
) -> UnitPlacement:
    if unit not in army.units:
        raise PlacementError("unit must belong to army.")
    model_placements = tuple(
        ModelPlacement(
            army_id=army.army_id,
            player_id=army.player_id,
            unit_instance_id=unit.unit_instance_id,
            model_instance_id=model.model_instance_id,
            pose=_pose_for_model(
                army_index=army_index,
                unit_index=unit_index,
                model_index=model_index,
            ),
        )
        for model_index, model in enumerate(unit.own_models)
    )
    return UnitPlacement(
        army_id=army.army_id,
        player_id=army.player_id,
        unit_instance_id=unit.unit_instance_id,
        model_placements=model_placements,
    )


def _pose_for_model(*, army_index: int, unit_index: int, model_index: int) -> Pose:
    base_x = 6.0 + (army_index * 36.0)
    base_y = 6.0 + (unit_index * 8.0)
    x = base_x + ((model_index % 5) * 2.0)
    y = base_y + ((model_index // 5) * 2.0)
    facing_degrees = 0.0 if army_index == 0 else 180.0
    return Pose.at(x=x, y=y, z=0.0, facing_degrees=facing_degrees)
