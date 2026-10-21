"""Core placement restrictions at the exact geometry owner, no mission or charge setup."""

from contextlib import nullcontext
from dataclasses import replace

import pytest

from warhammer40k_core.core.ruleset_descriptor import RulesetDescriptor
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.revival_engagement import (
    validate_revival_engagement_geometry,
)
from warhammer40k_core.engine.revival_phase_start import (
    validate_revival_anchor_coherency,
)
from warhammer40k_core.geometry.base import CircularBase
from warhammer40k_core.geometry.pose import Pose
from warhammer40k_core.geometry.volume import Model, ModelVolume


@pytest.mark.parametrize(
    ("distance", "was_present", "valid"),
    [(3, True, True), (3.001, True, False), (1.5, False, False)],
)
def test_01_02_03_revival_needs_actual_phase_start_neighbor(
    distance: float, was_present: bool, valid: bool
) -> None:
    anchor = Model("anchor", Pose.at(10, 10), CircularBase(0.5), ModelVolume(1))
    returned = replace(anchor, model_id="returned", pose=Pose.at(10 + distance, 10))
    with nullcontext() if valid else pytest.raises(GameLifecycleError, match="phase-start"):
        validate_revival_anchor_coherency(
            returned=returned,
            present_models=(anchor,),
            phase_start_model_ids=("anchor",) if was_present else (),
            ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(),
        )


@pytest.mark.parametrize("same_enemy_unit", [False, True])
def test_01_02_03_return_can_engage_different_model_only_in_same_enemy_unit(
    same_enemy_unit: bool,
) -> None:
    survivor = Model("survivor", Pose.at(10, 10), CircularBase(0.5), ModelVolume(1))
    enemy_near = replace(survivor, model_id="enemy-near", pose=Pose.at(12, 10))
    enemy_far = replace(survivor, model_id="enemy-far", pose=Pose.at(16, 10))
    returned = replace(survivor, model_id="returned", pose=Pose.at(16, 12))
    enemies: dict[str, tuple[Model, ...]] = (
        {"enemy-unit": (enemy_near, enemy_far)}
        if same_enemy_unit
        else {"enemy-unit": (enemy_near,), "new-enemy": (enemy_far,)}
    )
    with nullcontext() if same_enemy_unit else pytest.raises(GameLifecycleError, match="new enemy"):
        evidence = validate_revival_engagement_geometry(
            target_unit_instance_id="return-unit",
            existing_models=(survivor,),
            enemies=enemies,
            returned_model=returned,
            ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(),
        )
        assert (
            evidence["engaged_enemy_rules_unit_ids_before"]
            == evidence["returned_model_engaged_enemy_rules_unit_ids"]
            == ["enemy-unit"]
        )
