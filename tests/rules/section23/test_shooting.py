"""Aircraft suppresses Plunging Fire before the shared actual Hit resolver."""

from dataclasses import replace

import pytest

from tests.support.section02_fixtures import Section02Definitions
from tests.support.section03_fixtures import native_state, scenario
from tests.support.section23_fixtures import AVENGERS, LORD
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
)
from warhammer40k_core.engine.shooting_types import ShootingType
from warhammer40k_core.engine.weapon_declaration import RangedAttackPool
from warhammer40k_core.engine.weapon_instances import equipped_weapon_profile_instances_for_model
from warhammer40k_core.geometry.pose import Pose
from warhammer40k_core.geometry.terrain import (
    TerrainFeatureDefinition,
    TerrainFloorDefinition,
    TerrainWallDefinition,
)


@pytest.mark.parametrize("aircraft_side", ["neither", "attacker", "target"])
@pytest.mark.parametrize("branch", ["towering", "floor"])
def test_aircraft_exclusion_reaches_actual_hit_for_both_plunging_branches(
    section23_definitions: Section02Definitions, aircraft_side: str, branch: str
) -> None:
    d = section23_definitions
    own = d.unit(AVENGERS)
    attacker_id = own.own_models[0].model_instance_id
    if branch == "towering":
        own = replace(
            own,
            own_models=tuple(
                with_model_keywords(model, keywords=(*model.keywords, "TOWERING"))
                if model.model_instance_id == attacker_id
                else model
                for model in own.own_models
            ),
        )
    target = d.unit(LORD, army_id="enemy", identity="target")
    if aircraft_side == "attacker":
        own = with_unit_keywords(own, keywords=(*own.keywords, "AIRCRAFT"))
    if aircraft_side == "target":
        target = with_unit_keywords(target, keywords=(*target.keywords, "AIRCRAFT"))
    height = 3 if branch == "floor" else 0
    state = native_state(
        d,
        own,
        tuple(Pose.at(15, 15 + i * 1.5, height) for i in range(len(own.own_models))),
        enemy=target,
        enemy_poses=(Pose.at(23, 15),),
    )
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.SHOOTING)
    features: tuple[TerrainFeatureDefinition, ...] = ()
    if branch == "floor":
        display = TerrainDisplayGeometry.axis_aligned_rectangle(
            center_x_inches=15,
            center_y_inches=18,
            width_inches=5,
            depth_inches=12,
            display_template_id="constructed:s23:platform",
        )
        features = (
            TerrainFeatureDefinition(
                feature_id="constructed:s23:platform",
                feature_kind=TerrainFeatureKind.RUINS,
                footprint_center_x_inches=15,
                footprint_center_y_inches=18,
                footprint_width_inches=5,
                footprint_depth_inches=12,
                rules_footprint_polygon=display.footprint_polygon,
                display_geometry=display,
                walls=(
                    TerrainWallDefinition(
                        wall_id="rear",
                        center_x_inches=13,
                        center_y_inches=18,
                        bottom_z_inches=0,
                        width_inches=0.1,
                        depth_inches=12,
                        height_inches=3,
                    ),
                ),
                floors=(
                    TerrainFloorDefinition(
                        floor_id="upper",
                        center_x_inches=15,
                        center_y_inches=18,
                        bottom_z_inches=3,
                        width_inches=5,
                        depth_inches=12,
                        thickness_inches=0.1,
                    ),
                ),
            ),
        )
    assert state.battlefield_state is not None
    state.replace_battlefield_state(replace(state.battlefield_state, terrain_features=features))
    equipped = next(
        w
        for w in equipped_weapon_profile_instances_for_model(
            model=own.own_models[0], army_catalog=d.package.army_catalog
        )
        if w.wargear_id == f"{AVENGERS}:avenger-shuriken-catapult"
    )
    profile = equipped.weapon_profile
    assert profile.skill is not None
    assert profile.skill.final == 3
    candidate = shooting_target_candidate_for_model(
        scenario=scenario(state),
        ruleset_descriptor=state.runtime_ruleset_descriptor(),
        attacker_unit=own,
        attacker_model_instance_id=attacker_id,
        weapon_profile=profile,
        target_unit_id=target.unit_instance_id,
        terrain_features=features,
    )
    assert candidate.is_legal
    assert (PLUNGING_FIRE_RULE_ID in candidate.targeting_rule_ids) is (aircraft_side == "neither")
    pool = RangedAttackPool(
        weapon_instance_id=equipped.weapon_instance_id,
        attacker_model_instance_id=attacker_id,
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
    sequence_id = "s23:plunging"
    attack_id = f"{sequence_id}:pool-001:attack-001"
    rolls = tuple(
        DiceRollResult.from_values(
            roll_id=f"s23:fixed:{kind}",
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
            attacking_unit_instance_id=own.unit_instance_id,
            attack_pools=(pool,),
        ),
        already_allocated_model_ids=(),
        dice_manager=DiceRollManager(
            sequence_id, event_log=decisions.event_log, injected_results=rolls
        ),
    )
    hits = [
        e.payload
        for e in decisions.event_log.records
        if e.event_type == "attack_sequence_step"
        and isinstance(e.payload, dict)
        and e.payload["step"] == "hit"
    ]
    assert len(hits) == 1
    step = hits[0]
    assert isinstance(step, dict)
    assert isinstance(step["payload"], dict)
    assert step["payload"]["target_number"] == (2 if aircraft_side == "neither" else 3)
    assert step["payload"]["successful"] is (aircraft_side == "neither")
