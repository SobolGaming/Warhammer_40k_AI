"""03.02.02 overhang exceptions require whole-model impossibility proofs."""

import pytest

from warhammer40k_core.core.deployment_zones import DeploymentZone
from warhammer40k_core.engine.large_model_setup import deployment_body_containment
from warhammer40k_core.engine.reserve_setup_geometry import (
    append_reserve_body_violations,
    append_strategic_reserves_edge_violations,
)
from warhammer40k_core.engine.reserves import (
    BattlefieldEdge,
    LargeModelReservePlacementException,
    ReservePlacementViolation,
    StrategicReserveRule,
)
from warhammer40k_core.geometry.base import CircularBase
from warhammer40k_core.geometry.model_body import ModelBodyPart
from warhammer40k_core.geometry.pose import Pose
from warhammer40k_core.geometry.volume import Model, ModelVolume


@pytest.mark.parametrize(("body_radius", "expected"), [(2, False), (4, True)])
def test_deployment_overhang_requires_impossible_whole_body_fit(
    body_radius: float, expected: bool
) -> None:
    # Explicit geometry contract: a support base plus a measured-style body part.
    model = Model(
        "constructed-body",
        Pose.at(1, 10),
        CircularBase(1),
        ModelVolume(1),
        (ModelBodyPart("body", CircularBase(body_radius), 0, 0, 0, 1, "constructed:body"),),
    )
    zone = DeploymentZone.rectangle("narrow", "owner", min_x=0, min_y=0, max_x=6, max_y=44)
    in_zone, in_field = deployment_body_containment(
        model=model, zones=(zone,), width=60, depth=44, unrestricted_zone=False
    )
    assert in_zone is expected
    # Battlefield overhang is still avoidable even if deployment-zone fit is impossible.
    assert not in_field


@pytest.mark.parametrize(("radius", "x", "valid"), [(4, 4, True), (4, 4.01, False), (2, 2, False)])
def test_reserve_oversize_exception_proves_size_and_edge_contact(
    radius: float, x: float, valid: bool
) -> None:
    model = Model("constructed-reserve", Pose.at(x, 15), CircularBase(radius), ModelVolume(3))
    violations: list[ReservePlacementViolation] = []
    append_strategic_reserves_edge_violations(
        violations=violations,
        models=(model,),
        battle_round=2,
        battlefield_width_inches=60,
        battlefield_depth_inches=44,
        strategic_reserve_rule=StrategicReserveRule(),
        qualifying_edges=(BattlefieldEdge.WEST,),
        large_model_exceptions=(
            LargeModelReservePlacementException(model.model_id, BattlefieldEdge.WEST),
        ),
    )
    assert (not violations) is valid
    if radius == 4 and not valid:
        assert any(
            v.violation_code.value == "large_model_exception_edge_contact_missing"
            for v in violations
        )


@pytest.mark.parametrize(("body_radius", "valid"), [(4, False), (31, True)])
def test_reserve_body_overhang_allowed_only_when_no_whole_model_fit(
    body_radius: float, valid: bool
) -> None:
    model = Model(
        "constructed-overhang",
        Pose.at(1, 20),
        CircularBase(1),
        ModelVolume(1),
        (ModelBodyPart("body", CircularBase(body_radius), 0, 0, 0, 1, "constructed:body"),),
    )
    violations: list[ReservePlacementViolation] = []
    append_reserve_body_violations(
        violations=violations,
        models=(model,),
        width=60,
        depth=44,
        qualifying_edges=(BattlefieldEdge.WEST,),
        strategic_rule=StrategicReserveRule(),
        exceptions=(),
    )
    assert (not violations) is valid
