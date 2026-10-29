"""03.03 and its contiguous-group FAQ, with explicit boundary geometry."""

import pytest

from tests.support.section02_fixtures import CHAOS_SPAWN, Section02Definitions
from tests.support.section03_fixtures import geometry
from warhammer40k_core.core.ruleset_descriptor import RulesetDescriptor
from warhammer40k_core.engine.unit_coherency import UnitCoherencyContext
from warhammer40k_core.geometry.base import CircularBase
from warhammer40k_core.geometry.pose import Pose
from warhammer40k_core.geometry.volume import Model, ModelVolume


@pytest.mark.parametrize(
    ("gap", "vertical", "valid"),
    [(1.999, 0, True), (2, 0, True), (2.001, 0, False), (2, 5, True), (2, 5.001, False)],
)
def test_each_native_member_needs_neighbor_within_both_limits(
    section03_definitions: Section02Definitions, gap: float, vertical: float, valid: bool
) -> None:
    unit = section03_definitions.unit(CHAOS_SPAWN)
    first, second = geometry(unit, (Pose.at(10, 10), Pose.at(15, 10)))
    # Native source-backed equal circular bases; exact edge gaps from their real dimensions.
    assert isinstance(first.base, CircularBase)
    assert isinstance(second.base, CircularBase)
    from dataclasses import replace

    second = replace(
        second,
        pose=Pose.at(
            10 + first.base.radius + second.base.radius + gap,
            10,
            z=first.volume.height + vertical if vertical else 0,
        ),
    )
    result = UnitCoherencyContext.from_ruleset_descriptor(
        RulesetDescriptor.warhammer_40000_eleventh(), unit_instance_id=unit.unit_instance_id
    ).validate_models((first, second))
    assert result.is_coherent is valid
    if not valid:
        assert set(result.offending_model_instance_ids) == {first.model_id, second.model_id}


@pytest.mark.parametrize(
    ("xs", "valid", "code"),
    [
        ((0, 2, 4, 6, 8, 10), True, None),
        ((0, 2, 4, 6, 8, 10.001), False, "unit_span_exceeded"),
        ((0, 1.5, 6, 7.5), False, "unit_coherency_not_single_group"),
        ((0,), True, None),
    ],
)
def test_constructed_span_and_contiguous_group_contract(
    xs: tuple[float, ...], valid: bool, code: str | None
) -> None:
    models = tuple(
        Model(f"contract-{i}", Pose.at(10 + x, 10), CircularBase(radius=0.5), ModelVolume(1))
        for i, x in enumerate(xs)
    )
    result = UnitCoherencyContext.from_ruleset_descriptor(
        RulesetDescriptor.warhammer_40000_eleventh(), unit_instance_id="constructed-group"
    ).validate_models(models)
    assert result.is_coherent is valid
    if code:
        assert code in {v.violation_code for v in result.violations}
