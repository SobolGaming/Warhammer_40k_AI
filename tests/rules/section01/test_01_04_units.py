"""Native model geometry feeds closest and unit range semantics without game setup."""

from dataclasses import replace

import pytest

from tests.support.section01_fixtures import minimal_state, place_units
from tests.support.section02_fixtures import LORD_EXULTANT, Section02Definitions
from warhammer40k_core.engine.battlefield_presence import battlefield_scenario_for_state
from warhammer40k_core.engine.battlefield_state import geometry_model_for_placement
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.stratagems_geometry import _units_are_within_range_inches
from warhammer40k_core.engine.surge_movement import (
    closest_surge_targets,
    validate_surge_target,
)
from warhammer40k_core.geometry.pose import Pose


@pytest.mark.parametrize("offset", [-0.001, 0, 0.001])
def test_01_04_01_only_one_native_member_needed_within_range(
    section01_definitions: Section02Definitions, offset: float
) -> None:
    source = section01_definitions.unit(identity="source")
    target = section01_definitions.unit(identity="target")
    state = minimal_state(section01_definitions, source, target)
    place_units(state)
    assert state.battlefield_state is not None
    first = state.battlefield_state.unit_placement_by_id(source.unit_instance_id)
    second = state.battlefield_state.unit_placement_by_id(target.unit_instance_id)
    # Same native circular footprint; derive its radius rather than editing it.
    geometry = geometry_model_for_placement(
        model=source.own_models[0], placement=first.model_placements[0]
    )
    from warhammer40k_core.geometry.base import CircularBase

    assert isinstance(geometry.base, CircularBase)
    radius = geometry.base.radius
    pose = first.model_placements[0].pose.position
    near = replace(
        second.model_placements[0],
        pose=Pose.at(pose.x - 2 * radius - 1 - offset, pose.y),
    )
    far = tuple(
        replace(m, pose=Pose.at(40 + i * 2, 30)) for i, m in enumerate(second.model_placements[1:])
    )
    state.battlefield_state = state.battlefield_state.with_unit_placement(
        replace(second, model_placements=(near, *far))
    )
    assert _units_are_within_range_inches(
        state=state,
        first_unit_instance_id=source.unit_instance_id,
        second_unit_instance_id=target.unit_instance_id,
        distance_inches=1,
    ) is (offset <= 0)


@pytest.mark.parametrize("selected", ["left", "right"])
def test_01_04_02_closest_tie_keeps_both_choices_and_excludes_farther(
    section01_definitions: Section02Definitions, selected: str
) -> None:
    source = section01_definitions.unit(LORD_EXULTANT, identity="source")
    enemies = tuple(
        section01_definitions.unit(LORD_EXULTANT, identity=i, army_id="enemies")
        for i in ("left", "right", "far")
    )
    state = minimal_state(section01_definitions, source)
    state.army_definitions.append(
        replace(
            state.army_definitions[0],
            army_id="enemies",
            player_id="opponent",
            units=enemies,
        )
    )
    place_units(state)
    assert state.battlefield_state is not None
    for unit, x in ((source, 20), *zip(enemies, (15, 25, 30), strict=True)):
        placement = state.battlefield_state.unit_placement_by_id(unit.unit_instance_id)
        state.battlefield_state = state.battlefield_state.with_unit_placement(
            replace(
                placement,
                model_placements=(replace(placement.model_placements[0], pose=Pose.at(x, 10)),),
            )
        )
    scenario = battlefield_scenario_for_state(state=state)
    assert closest_surge_targets(scenario=scenario, unit_instance_id=source.unit_instance_id) == (
        "enemies:left",
        "enemies:right",
    )
    for invalid in (None, "enemies:far"):
        with pytest.raises(GameLifecycleError, match="ties require a finite choice"):
            validate_surge_target(
                scenario=scenario,
                unit_instance_id=source.unit_instance_id,
                target_id=invalid,
            )
    assert (
        validate_surge_target(
            scenario=scenario,
            unit_instance_id=source.unit_instance_id,
            target_id=f"enemies:{selected}",
        )
        == f"enemies:{selected}"
    )
