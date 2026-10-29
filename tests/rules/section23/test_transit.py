"""Every continuous move family may cross Aircraft; endpoints keep collision rules."""

import pytest

from tests.support.section02_fixtures import Section02Definitions
from tests.support.section03_fixtures import geometry, paths
from tests.support.section23_fixtures import LORD
from tests.unit_keyword_helpers import with_unit_keywords
from warhammer40k_core.core.ruleset_descriptor import MovementMode, RulesetDescriptor
from warhammer40k_core.engine.movement_legality import MovementLegalityContext
from warhammer40k_core.geometry.pose import Pose


@pytest.mark.parametrize("mode", list(MovementMode))
@pytest.mark.parametrize("friendly", [False, True])
def test_native_models_transit_aircraft_but_cannot_end_overlapping_it(
    section23_definitions: Section02Definitions, mode: MovementMode, friendly: bool
) -> None:
    d = section23_definitions
    mover = d.unit(LORD)
    blocker = with_unit_keywords(
        d.unit(LORD, identity="blocker", army_id="section02" if friendly else "enemy"),
        keywords=("AIRCRAFT", "FLY"),
    )
    moving = geometry(mover, (Pose.at(10, 15),))[0]
    blocking = geometry(blocker, (Pose.at(13, 15),), enemy=not friendly)[0]
    context = MovementLegalityContext.from_keywords(
        keywords=mover.keywords,
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(),
        movement_mode=mode,
        movement_phase_action=None,
        displacement_kind="normal_move",
    )
    for endpoint, legal in ((18, True), (13, False)):
        witness = paths(mover, (Pose.at(10, 15),), (Pose.at(endpoint, 15),))
        result = context.to_path_validation_context(
            moving_model=moving,
            witness=witness,
            battlefield_width_inches=60,
            battlefield_depth_inches=44,
            friendly_models=(blocking,) if friendly else (),
            enemy_models=() if friendly else (blocking,),
            aircraft_model_ids=(blocking.model_id,),
        ).validate()
        assert result.is_valid is legal
        if not legal:
            assert "end_on_model_overlap" in {v.violation_code for v in result.violations}
