"""Physical terrain range contracts and paired per-model marker evidence."""

from dataclasses import replace

import pytest

from tests.support.section02_fixtures import AVENGERS, Section02Definitions
from tests.support.section03_fixtures import scenario
from tests.support.section14_fixtures import objective_state
from warhammer40k_core.core.objectives import ObjectiveMarker
from warhammer40k_core.engine.objective_geometry import (
    ObjectiveGeometry,
    measure_model_to_objective,
    measure_rules_unit_to_objective,
)
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.rules_units import rules_unit_view_by_id
from warhammer40k_core.geometry.base import CircularBase
from warhammer40k_core.geometry.model_body import ModelBodyPart
from warhammer40k_core.geometry.pose import Pose
from warhammer40k_core.geometry.volume import Model, ModelVolume


@pytest.mark.parametrize("z", [0, 12])
def test_constructed_frame_body_membership_matches_existing_area_rule(z: float) -> None:
    # Same declared physical contract as Section13 FAQ34. This is a supported
    # typed geometry query, not proof of native FRAME roster/geometry admission.
    ordinary = Model("constructed:s14:frame", Pose.at(10, 10, z), CircularBase(0.5), ModelVolume(1))
    frame = replace(
        ordinary,
        measures_every_part=True,
        body_parts=(ModelBodyPart("arm", CircularBase(0.5), 0, 3, 0, 1, "constructed:s14:arm"),),
    )
    terrain = ObjectiveGeometry.from_terrain(
        objective_id="terrain",
        footprint_polygons=(((9.0, 12.0), (11.0, 12.0), (11.0, 14.0), (9.0, 14.0)),),
    )
    assert not measure_model_to_objective(model=ordinary, objective=terrain).within_control_range
    result = measure_model_to_objective(model=frame, objective=terrain)
    assert result.within_control_range
    assert result.horizontal_distance_inches == 0


def test_marker_requires_one_physical_model_to_meet_both_axis_limits(
    section14_definitions: Section02Definitions,
) -> None:
    state, unit, _ = objective_state(section14_definitions, subject_sheet=AVENGERS)
    assert state.battlefield_state is not None
    placed = state.battlefield_state.unit_placement_by_id(unit.unit_instance_id)
    state.replace_battlefield_state(
        state.battlefield_state.with_unit_placement(
            replace(
                placed,
                model_placements=tuple(
                    replace(p, pose=Pose.at(10 if i == 0 else 25, 10, 6 if i == 0 else 0))
                    for i, p in enumerate(placed.model_placements)
                ),
            )
        )
    )
    rows = measure_rules_unit_to_objective(
        scenario=scenario(state),
        rules_unit=rules_unit_view_by_id(state=state, unit_instance_id=unit.unit_instance_id),
        objective=ObjectiveGeometry.from_marker(ObjectiveMarker("marker", "Marker", 10, 10)),
    )
    assert any(r.horizontal_distance_inches <= 3 for r in rows)
    assert any(r.vertical_gap_inches <= 5 for r in rows)
    assert not any(r.within_control_range for r in rows)


def test_stale_rules_unit_owner_is_rejected_before_geometry_answer(
    section14_definitions: Section02Definitions,
) -> None:
    state, unit, _ = objective_state(section14_definitions)
    view = rules_unit_view_by_id(state=state, unit_instance_id=unit.unit_instance_id)
    with pytest.raises(GameLifecycleError, match="identity drifted"):
        measure_rules_unit_to_objective(
            scenario=scenario(state),
            rules_unit=replace(view, owner_player_id="opponent"),
            objective=ObjectiveGeometry.from_marker(ObjectiveMarker("marker", "Marker", 10, 10)),
        )
