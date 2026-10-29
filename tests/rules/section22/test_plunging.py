"""Per-attacker ranged eligibility at physical height and range boundaries."""

from dataclasses import replace

import pytest

from tests.support.section02_fixtures import Section02Definitions
from tests.support.section03_fixtures import (
    axis_endpoint_within_range,
    geometry,
    native_state,
    scenario,
)
from tests.support.section05_fixtures import replace_unit
from tests.support.section22_fixtures import AVENGERS, LORD, pair, relocate
from tests.unit_keyword_helpers import with_model_keywords, with_unit_keywords
from warhammer40k_core.core.dice import DiceExpression, DiceRollResult, DiceRollSpec
from warhammer40k_core.core.ruleset_descriptor import TerrainFeatureKind
from warhammer40k_core.core.terrain_display import TerrainDisplayGeometry
from warhammer40k_core.engine.attack_sequence_dispatch import resolve_attack_sequence_until_blocked
from warhammer40k_core.engine.attack_sequence_state import AttackSequence
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.dice import DiceRollManager
from warhammer40k_core.engine.phase import BattlePhase
from warhammer40k_core.engine.shooting_targets import (
    PLUNGING_FIRE_RULE_ID,
    shooting_target_candidate_for_model,
    shooting_target_candidates_for_unit,
)
from warhammer40k_core.engine.shooting_types import ShootingType
from warhammer40k_core.engine.weapon_declaration import RangedAttackPool
from warhammer40k_core.engine.weapon_instances import equipped_weapon_profile_instances_for_model
from warhammer40k_core.geometry.base import CircularBase
from warhammer40k_core.geometry.pose import Pose
from warhammer40k_core.geometry.terrain import (
    TerrainFeatureDefinition,
    TerrainFloorDefinition,
    TerrainWallDefinition,
)


def platform(surface: float, *, thickness: float = 0.1) -> TerrainFeatureDefinition:
    display = TerrainDisplayGeometry.axis_aligned_rectangle(
        center_x_inches=10,
        center_y_inches=10,
        width_inches=5,
        depth_inches=5,
        display_template_id="constructed:s22:platform",
    )
    return TerrainFeatureDefinition(
        feature_id="constructed:s22:platform",
        feature_kind=TerrainFeatureKind.RUINS,
        footprint_center_x_inches=10,
        footprint_center_y_inches=10,
        footprint_width_inches=5,
        footprint_depth_inches=5,
        rules_footprint_polygon=display.footprint_polygon,
        display_geometry=display,
        walls=(
            TerrainWallDefinition(
                wall_id="rear",
                center_x_inches=8,
                center_y_inches=10,
                bottom_z_inches=0,
                width_inches=0.1,
                depth_inches=5,
                height_inches=surface,
            ),
        ),
        floors=(
            TerrainFloorDefinition(
                floor_id="upper",
                center_x_inches=10,
                center_y_inches=10,
                bottom_z_inches=surface,
                width_inches=5,
                depth_inches=5,
                thickness_inches=thickness,
            ),
        ),
    )


@pytest.mark.parametrize("height", [2.999, 3.0, 3.001, 6.0])
@pytest.mark.parametrize("target_height", [0, 0.5])
def test_supported_floor_surface_controls_three_inch_eligibility(
    section22_definitions: Section02Definitions, height: float, target_height: float
) -> None:
    state, attacker, target = pair(section22_definitions)
    relocate(state, attacker, 10, height)
    relocate(state, target, 18, target_height)
    feature = platform(height)
    candidates = shooting_target_candidates_for_unit(
        scenario=scenario(state),
        ruleset_descriptor=state.runtime_ruleset_descriptor(),
        attacker_unit=attacker,
        weapon_profile=section22_definitions.weapon(f"{LORD}:bolt-pistol"),
        target_unit_ids=(target.unit_instance_id,),
        terrain_features=(feature,),
    )
    assert candidates[0].is_legal
    assert (PLUNGING_FIRE_RULE_ID in candidates[0].targeting_rule_ids) is (
        height >= 3 and target_height == 0
    )


@pytest.mark.parametrize("distance", [11.999, 12.0, 12.001])
@pytest.mark.parametrize("target_height", [0, 0.5])
def test_towering_branch_uses_range_and_ground_target(
    section22_definitions: Section02Definitions, distance: float, target_height: float
) -> None:
    state, attacker, target = pair(section22_definitions)
    # Explicit Core keyword permission on a native body, not a native Towering datasheet claim.
    attacker = with_unit_keywords(attacker, keywords=(*attacker.keywords, "TOWERING"))
    replace_unit(state, attacker)
    own = geometry(attacker, (Pose.at(10, 10),))[0]
    other = geometry(target, (Pose.at(10, 10),), enemy=True)[0]
    assert isinstance(own.base, CircularBase)
    assert isinstance(other.base, CircularBase)
    x = axis_endpoint_within_range(10, own.base.radius, other.base.radius, distance)
    relocate(state, target, x, target_height)
    weapon = replace(
        section22_definitions.weapon(f"{LORD}:bolt-pistol"),
        range_profile=replace(
            section22_definitions.weapon(f"{LORD}:bolt-pistol").range_profile, distance_inches=36
        ),
    )
    candidate = shooting_target_candidates_for_unit(
        scenario=scenario(state),
        ruleset_descriptor=state.runtime_ruleset_descriptor(),
        attacker_unit=attacker,
        weapon_profile=weapon,
        target_unit_ids=(target.unit_instance_id,),
    )[0]
    assert candidate.is_legal
    assert (PLUNGING_FIRE_RULE_ID in candidate.targeting_rule_ids) is (
        distance <= 12 and target_height == 0
    )


def test_plunging_eligibility_belongs_to_each_native_physical_attacker(
    section22_definitions: Section02Definitions,
) -> None:
    from warhammer40k_core.engine.shooting_targets import (
        _attacker_model_on_plunging_fire_terrain,  # pyright: ignore[reportPrivateUsage]
    )

    attacker = section22_definitions.unit(AVENGERS)
    poses = tuple(
        Pose.at(10, 10 + i * 1.5, 3 if i < 2 else 0) for i in range(len(attacker.own_models))
    )
    # Exact pure owner used by _plunging_fire_applies. Visibility is independently
    # exercised by the single-model public queries above and bounded actual-BS
    # attack controls. Do not reconstruct a five-observer quantified visibility
    # problem merely to assert this physical terrain predicate.
    results = [
        _attacker_model_on_plunging_fire_terrain(
            attacker_model=model, terrain_features=(platform(3),)
        )
        for model in geometry(attacker, poses)
    ]
    assert results == [True, True, False, False, False]


@pytest.mark.parametrize(
    ("towering_index", "attacking_index", "expected_bs"),
    [(None, 1, 3), (0, 0, 2), (0, 1, 3), (1, 1, 2)],
)
def test_towering_keyword_stays_with_physical_attacker_through_actual_hit(
    section22_definitions: Section02Definitions,
    towering_index: int | None,
    attacking_index: int,
    expected_bs: int,
) -> None:
    # Native equipment/bodies; the heterogeneous Core keyword input is explicit.
    # No named model-only provider or complete legal roster/setup admission claim.
    d = section22_definitions
    source = d.unit(AVENGERS, identity="towering-physical")
    source = replace(
        source,
        own_models=tuple(
            with_model_keywords(model, keywords=(*model.keywords, "TOWERING"))
            if index == towering_index
            else model
            for index, model in enumerate(source.own_models)
        ),
    )
    target = d.unit(LORD, identity="towering-target", army_id="enemy")
    state = native_state(
        d,
        source,
        tuple(Pose.at(10, 10 + index * 1.3) for index in range(len(source.own_models))),
        enemy=target,
        enemy_poses=(Pose.at(18, 10),),
    )
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.SHOOTING)
    attacker = source.own_models[attacking_index]
    equipped = next(
        weapon
        for weapon in equipped_weapon_profile_instances_for_model(
            model=attacker, army_catalog=d.package.army_catalog
        )
        if weapon.weapon_profile.profile_id.startswith(f"{AVENGERS}:avenger-shuriken-catapult")
    )
    profile = equipped.weapon_profile
    assert profile.skill.final == 3
    candidate = shooting_target_candidate_for_model(
        scenario=scenario(state),
        ruleset_descriptor=state.runtime_ruleset_descriptor(),
        attacker_unit=source,
        attacker_model_instance_id=attacker.model_instance_id,
        weapon_profile=profile,
        target_unit_id=target.unit_instance_id,
    )
    assert candidate.is_legal
    assert candidate.observer_model_id == attacker.model_instance_id
    assert (PLUNGING_FIRE_RULE_ID in candidate.targeting_rule_ids) is (
        attacking_index == towering_index
    )
    pool = RangedAttackPool(
        weapon_instance_id=equipped.weapon_instance_id,
        attacker_model_instance_id=attacker.model_instance_id,
        wargear_id=equipped.wargear_id,
        weapon_profile_id=profile.profile_id,
        weapon_profile=profile,
        target_unit_instance_id=target.unit_instance_id,
        shooting_type=ShootingType.NORMAL,
        attacks=1,
        target_visible_model_ids=candidate.target_visible_model_ids,
        target_in_range_model_ids=candidate.target_in_range_model_ids,
        targeting_rule_ids=candidate.targeting_rule_ids,
    )
    sequence_id = "section22:physical-towering"
    attack_id = f"{sequence_id}:pool-001:attack-001"
    rolls = tuple(
        DiceRollResult.from_values(
            roll_id=f"section22:fixed:{kind}",
            spec=DiceRollSpec(
                expression=DiceExpression(quantity=1, sides=6),
                reason=f"{kind.capitalize()} roll for {profile.profile_id} attack {attack_id}",
                roll_type=f"attack_sequence.{kind}",
                actor_id="owner",
            ),
            values=(value,),
            source="fixed",
        )
        for kind, value in (("hit", 2), ("wound", 1))
    )
    decisions = DecisionController()
    resolve_attack_sequence_until_blocked(
        state=state,
        decisions=decisions,
        ruleset_descriptor=state.runtime_ruleset_descriptor(),
        attack_sequence=AttackSequence.start(
            sequence_id=sequence_id,
            attacker_player_id="owner",
            attacking_unit_instance_id=source.unit_instance_id,
            attack_pools=(pool,),
        ),
        already_allocated_model_ids=(),
        dice_manager=DiceRollManager(
            sequence_id, event_log=decisions.event_log, injected_results=rolls
        ),
    )
    steps = [
        event.payload
        for event in decisions.event_log.records
        if event.event_type == "attack_sequence_step"
    ]
    hits = [step for step in steps if isinstance(step, dict) and step["step"] == "hit"]
    assert len(hits) == 1
    step = hits[0]
    assert isinstance(step, dict)
    hit = step["payload"]
    assert isinstance(hit, dict)
    assert hit["unmodified_roll"] == 2
    assert hit["target_number"] == expected_bs
    assert hit["successful"] is (expected_bs <= 2)
