"""Legal attached-group placement for canonical non-movement fixture roots."""

from warhammer40k_core.engine.army_mustering import ArmyDefinition
from warhammer40k_core.engine.battlefield_state import BattlefieldRuntimeState, ModelPlacement
from warhammer40k_core.engine.rules_units import rules_unit_views_from_armies
from warhammer40k_core.geometry.pose import Pose


def coherent_attached_fixture_battlefield(
    *, armies: tuple[ArmyDefinition, ...], battlefield: BattlefieldRuntimeState
) -> BattlefieldRuntimeState:
    for view in rules_unit_views_from_armies(armies=armies):
        if view.attached_unit is None:
            continue
        placements = tuple(
            battlefield.unit_placement_or_none(component_id)
            for component_id in view.component_unit_instance_ids
        )
        if all(placement is None for placement in placements):
            continue
        assert all(placement is not None for placement in placements)
        anchor = (
            battlefield.unit_placement_by_id(view.attached_unit.bodyguard_unit_instance_id)
            .model_placements[0]
            .pose.position
        )
        index = 0
        for placement in placements:
            assert placement is not None
            updated: list[ModelPlacement] = []
            for model in placement.model_placements:
                updated.append(
                    model.with_pose(
                        Pose.at(anchor.x + 2 * (index % 3), anchor.y + 2 * (index // 3))
                    )
                )
                index += 1
            battlefield = battlefield.with_unit_placement(
                placement.with_model_placements(tuple(updated))
            )
    return battlefield
