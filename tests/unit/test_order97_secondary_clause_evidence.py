"""Clause-specific proofs added while curating the Order 97 evidence inventory."""

from __future__ import annotations

import json
from dataclasses import replace
from typing import cast

import pytest
from tests.core_clause_evidence_helpers import assert_persistence_viewers_replay
from tests.empty_shooting_helpers import SHOOTER, empty_shooting_session
from tests.explosives_helpers import explosives_scene
from tests.optional_shooting_helpers import finish_selected_weapons, select_optional_shooting
from tests.phase13b_shooting_declaration_helpers import _proposal_from_request
from tests.unit_keyword_helpers import with_unit_keywords

from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.core.ruleset_descriptor import MovementMode, RulesetDescriptor
from warhammer40k_core.core.terrain_display import TerrainDisplayGeometry
from warhammer40k_core.core.visibility import TerrainVisibilityContext
from warhammer40k_core.core.weapon_profiles import WeaponKeyword
from warhammer40k_core.engine.battlefield_state import ModelDisplacementKind
from warhammer40k_core.engine.event_log import JsonValue
from warhammer40k_core.engine.mission_action_eligibility import (
    mission_action_unit_ineligibility_reason,
)
from warhammer40k_core.engine.movement_legality import MovementLegalityContext
from warhammer40k_core.engine.phase import GameLifecycleError, LifecycleStatusKind
from warhammer40k_core.engine.phases.movement import FellBackUnitState
from warhammer40k_core.engine.runtime_modifiers import RuntimeModifierRegistry
from warhammer40k_core.geometry.base import CircularBase
from warhammer40k_core.geometry.pathing import PathWitness
from warhammer40k_core.geometry.pose import Pose
from warhammer40k_core.geometry.terrain import (
    TerrainFeatureDefinition,
    TerrainFeatureKind,
    TerrainWallDefinition,
)
from warhammer40k_core.geometry.terrain_area_visibility import (
    TerrainVisibilityArea,
    model_intersects_terrain_area,
)
from warhammer40k_core.geometry.terrain_classification import TerrainAreaClassification
from warhammer40k_core.geometry.volume import Model, ModelVolume


@pytest.mark.parametrize("condition", ["AIRCRAFT", "FORTIFICATION", "advanced", "fell_back"])
def test_order97_action_keyword_and_movement_exclusions(condition: str) -> None:
    session = empty_shooting_session(advanced=condition == "advanced")
    state = session.lifecycle.state
    assert state is not None
    if condition in {"AIRCRAFT", "FORTIFICATION"}:
        army = state.army_definitions[0]
        unit = army.unit_by_id(SHOOTER)
        state.replace_army_definitions(
            [
                replace(
                    army,
                    units=tuple(
                        with_unit_keywords(u, keywords=(*unit.keywords, condition))
                        if u.unit_instance_id == SHOOTER
                        else u
                        for u in army.units
                    ),
                ),
                *state.army_definitions[1:],
            ]
        )
    if condition == "fell_back":
        state.record_fell_back_unit_state(
            FellBackUnitState(
                player_id="player-a",
                battle_round=state.battle_round,
                unit_instance_id=SHOOTER,
                desperate_escape_rolls=(),
            )
        )
    reason = mission_action_unit_ineligibility_reason(
        state=state,
        player_id="player-a",
        unit_instance_id=SHOOTER,
        runtime_modifier_registry=RuntimeModifierRegistry.empty(),
    )
    assert reason == f"mission_action_unit_{condition.lower()}"


@pytest.mark.parametrize(("advanced", "engaged"), [(False, False), (True, False), (False, True)])
def test_order97_normal_type_requires_neither_advance_nor_engagement(
    advanced: bool, engaged: bool
) -> None:
    session = empty_shooting_session(
        advanced=advanced, engaged=engaged, keywords=(WeaponKeyword.ASSAULT,)
    )
    request = session.advance_until_decision_or_terminal().decision_request
    assert request is not None
    if SHOOTER not in {o.option_id for o in request.options}:
        assert advanced or engaged
        return
    request = session.submit_option(
        request_id=request.request_id, option_id=SHOOTER, result_id="order97:select"
    ).decision_request
    assert request is not None
    assert ("normal" in {o.option_id for o in request.options}) is (not advanced and not engaged)


def test_order97_assault_uses_attack_host_and_serial_unit_completion() -> None:
    session = empty_shooting_session(
        advanced=True, reachable=True, spare=True, keywords=(WeaponKeyword.ASSAULT,)
    )
    request = select_optional_shooting(session, "assault")
    before = session.to_persistence_payload()
    with pytest.raises(GameLifecycleError, match="cannot answer a parameterized request"):
        session.submit_option(
            request_id=request.request_id,
            option_id="army-alpha:spare",
            result_id="order97:premature-next",
        )
    assert session.to_persistence_payload() == before
    proposal = _proposal_from_request(request=request, target_unit_id="army-beta:enemy")
    payload = cast(dict[str, JsonValue], json.loads(json.dumps(proposal.to_payload())))
    declarations = payload["declarations"]
    assert isinstance(declarations, list)
    for row in declarations:
        assert isinstance(row, dict)
        row["shooting_type"] = "assault"
    status = session.submit_parameterized_payload(
        request_id=request.request_id, payload=payload, result_id="order97:assault"
    )
    assert status.status_kind is not LifecycleStatusKind.INVALID
    finish_selected_weapons(session, "order97:assault")
    next_request = session.advance_until_decision_or_terminal().decision_request
    assert next_request is not None
    assert next_request.decision_type == "select_shooting_unit"
    assert SHOOTER not in {o.option_id for o in next_request.options}
    assert "army-alpha:spare" in {o.option_id for o in next_request.options}
    events = session.lifecycle.decision_controller.event_log.records
    assert any(e.event_type == "attack_sequence_completed" for e in events)
    assert_persistence_viewers_replay(session)


def test_order97_explosives_rolls_six_and_counts_each_four_plus() -> None:
    lifecycle, _ = explosives_scene()
    session = LocalGameSession(lifecycle)
    request = session.advance_until_decision_or_terminal().decision_request
    assert request is not None
    option = next(o for o in request.options if o.option_id.startswith("use-stratagem:explosives:"))
    status = session.submit_option(
        request_id=request.request_id, option_id=option.option_id, result_id="order97:explosives"
    )
    while (
        status.decision_request is not None
        and status.decision_request.decision_type == "select_mortal_wound_model"
    ):
        request = status.decision_request
        status = session.submit_option(
            request_id=request.request_id,
            option_id=request.options[0].option_id,
            result_id=f"order97:{request.request_id}",
        )
    events = session.lifecycle.decision_controller.event_log.records
    event = next(e.payload for e in events if e.event_type == "explosives_resolved")
    assert isinstance(event, dict)
    roll = event["roll_state"]
    assert isinstance(roll, dict)
    values = roll["current_values"]
    assert isinstance(values, list)
    assert len(values) == 6
    assert event["mortal_wounds"] == sum(cast(int, value) >= 4 for value in values)
    assert_persistence_viewers_replay(session)


def _terrain_feature(classification: TerrainAreaClassification) -> TerrainFeatureDefinition:
    display = TerrainDisplayGeometry.axis_aligned_rectangle(
        center_x_inches=3,
        center_y_inches=1,
        width_inches=2,
        depth_inches=4,
        display_template_id="order97:wall",
    )
    return TerrainFeatureDefinition(
        feature_id="order97:wall",
        feature_kind=TerrainFeatureKind.BATTLEFIELD_DEBRIS_AND_STATUARY,
        footprint_center_x_inches=3,
        footprint_center_y_inches=1,
        footprint_width_inches=2,
        footprint_depth_inches=4,
        rules_footprint_polygon=display.footprint_polygon,
        display_geometry=display,
        classification=classification,
        walls=(
            TerrainWallDefinition(
                wall_id="wall",
                center_x_inches=3,
                center_y_inches=1,
                bottom_z_inches=0,
                width_inches=1,
                depth_inches=4,
                height_inches=4,
            ),
        ),
    )


@pytest.mark.parametrize(
    ("classification", "keyword"),
    [
        (TerrainAreaClassification.LIGHT, "VEHICLE"),
        (TerrainAreaClassification.DENSE, "INFANTRY"),
        (TerrainAreaClassification.DENSE, "BEAST"),
        (TerrainAreaClassification.DENSE, "SWARM"),
    ],
)
def test_order97_terrain_permitted_vertical_transit(
    classification: TerrainAreaClassification, keyword: str
) -> None:
    mover = Model("mover", Pose.at(0, 1), CircularBase(0.25), ModelVolume(1))
    legality = MovementLegalityContext.from_keywords(
        keywords=(keyword,),
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(),
        movement_mode=MovementMode.NORMAL,
        movement_phase_action="normal_move",
        displacement_kind=ModelDisplacementKind.NORMAL_MOVE,
    )
    result = legality.to_terrain_path_legality_context(
        moving_model=mover,
        witness=PathWitness.for_paths((("mover", (mover.pose, Pose.at(3, 1, 2), Pose.at(6, 1))),)),
        terrain=(),
        terrain_features=(_terrain_feature(classification),),
        contact_footprint_available=True,
        sample_interval_inches=0.5,
    ).validate()
    assert result.is_valid
    assert any(s.vertical_distance_inches > 0 for s in result.segments)


@pytest.mark.parametrize(
    ("observer_x", "target_x", "visible"), [(-4.0, 4.0, False), (0.0, 4.0, True), (-4.0, 0.0, True)]
)
def test_order97_obscuring_area_either_endpoint_exception(
    observer_x: float, target_x: float, visible: bool
) -> None:
    area = TerrainVisibilityArea(
        "area",
        ("area",),
        TerrainAreaClassification.DENSE,
        (((-1.0, -2.0), (1.0, -2.0), (1.0, 2.0), (-1.0, 2.0)),),
    )
    observer = Model("observer", Pose.at(observer_x, 0), CircularBase(0.25), ModelVolume(1))
    target = Model("target", Pose.at(target_x, 0), CircularBase(0.25), ModelVolume(1))
    context = TerrainVisibilityContext.from_ruleset_descriptor(
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(),
        los_cache_key="order97:area",
        observer_model=observer,
        target_models=(target,),
        terrain_areas=(area,),
        target_model_keywords=(("target", ("INFANTRY",)),),
    )
    assert context.resolve_line_of_sight().unit_visible is visible


@pytest.mark.parametrize("height", [0.0, 10.0])
def test_order97_terrain_area_membership_is_vertical_projection(height: float) -> None:
    area = TerrainVisibilityArea(
        "area",
        ("area",),
        TerrainAreaClassification.LIGHT,
        (((-1.0, -1.0), (1.0, -1.0), (1.0, 1.0), (-1.0, 1.0)),),
    )
    model = Model("model", Pose.at(0, 0, height), CircularBase(0.25), ModelVolume(1))
    outside = replace(model, pose=Pose.at(2, 0, height))
    assert model_intersects_terrain_area(model, area)
    assert not model_intersects_terrain_area(outside, area)


@pytest.mark.parametrize("enemy_count", [1, 2])
def test_order97_full_fight_optional_movement_once_and_player_sequence(enemy_count: int) -> None:
    from tests.phase15c_fight_order_helpers import fight_lifecycle
    from tests.psychic_modifier_helpers import submit_fixture_request

    from warhammer40k_core.core.army_catalog import ArmyCatalog
    from warhammer40k_core.core.attributes import Characteristic, CharacteristicValue
    from warhammer40k_core.engine.movement_proposals import MovementProposalRequest
    from warhammer40k_core.engine.phase import BattlePhase

    catalog = ArmyCatalog.phase9a_canonical_content_pack()
    catalog = replace(
        catalog,
        datasheets=tuple(
            replace(
                sheet,
                model_profiles=tuple(
                    replace(
                        profile,
                        characteristics=tuple(
                            CharacteristicValue.from_raw(Characteristic.WOUNDS, 100)
                            if value.characteristic is Characteristic.WOUNDS
                            else value
                            for value in profile.characteristics
                        ),
                    )
                    for profile in sheet.model_profiles
                ),
            )
            for sheet in catalog.datasheets
        ),
    )
    lifecycle, units = fight_lifecycle(
        alpha_unit_ids=("one", "two"),
        enemy_unit_ids=("enemy-one", "enemy-two")[:enemy_count],
        origins={
            "one": Pose.at(10, 10),
            "two": Pose.at(10, 12) if enemy_count == 1 else Pose.at(20, 10),
            "enemy-one": Pose.at(12, 10),
            "enemy-two": Pose.at(22, 10),
        },
        game_id="order97-fight-steps",
        datasheet_id="core-character-leader",
        model_profile_id="core-character-leader",
        model_count=1,
        catalog=catalog,
    )
    session = LocalGameSession(lifecycle)
    movement: list[tuple[str, str, str]] = []
    fighters: list[str] = []
    fight_actors: list[str] = []
    for _ in range(100):
        request = session.advance_until_decision_or_terminal().decision_request
        state = lifecycle.state
        assert state is not None
        if state.current_battle_phase is not BattlePhase.FIGHT:
            break
        assert request is not None
        if request.decision_type == "submit_movement_proposal":
            move = MovementProposalRequest.from_decision_request_payload(request.payload)
            assert request.actor_id is not None
            movement.append((move.proposal_kind.value, request.actor_id, move.unit_instance_id))
        if request.decision_type == "select_fight_activation":
            assert all(
                "pass" not in o.option_id and "complete" not in o.option_id for o in request.options
            )
            assert isinstance(request.options[0].payload, dict)
            fighters.append(cast(str, request.options[0].payload["unit_instance_id"]))
            assert request.actor_id is not None
            fight_actors.append(request.actor_id)
        submit_fixture_request(session, request)
    else:
        raise AssertionError("Fight did not complete")
    unit_ids = {unit.unit_instance_id for unit in units.values()}
    assert set(fighters) == unit_ids
    assert len(fighters) == len(unit_ids)
    assert fight_actors == ["player-a", "player-b", "player-a"] + ["player-b"] * (enemy_count - 1)
    assert lifecycle.state is not None
    assert lifecycle.state.current_battle_phase is not BattlePhase.FIGHT
    for kind in ("pile_in", "consolidate"):
        moves = [(actor, unit) for mode, actor, unit in movement if mode == kind]
        assert [actor for actor, _ in moves] == ["player-a"] * 2 + ["player-b"] * enemy_count
        assert {unit for _, unit in moves} == unit_ids
        assert len(moves) == len(unit_ids)
    records = lifecycle.decision_controller.event_log.records
    kinds = [event.event_type for event in records]
    assert (
        kinds.index("pile_in_step_completed")
        < kinds.index("melee_attack_sequence_completed")
        < kinds.index("consolidate_step_completed")
    )
    assert_persistence_viewers_replay(session)


@pytest.mark.parametrize("distance", [6.0, 6.01])
def test_order97_fall_back_uses_model_movement_characteristic(distance: float) -> None:
    from tests.phase15c_fight_order_helpers import fight_lifecycle

    from warhammer40k_core.engine.battlefield_presence import battlefield_scenario_for_state
    from warhammer40k_core.engine.phases.movement import FallBackModeKind, resolve_fall_back_move

    lifecycle, units = fight_lifecycle(
        alpha_unit_ids=("source",),
        enemy_unit_ids=("enemy",),
        origins={"source": Pose.at(10, 10), "enemy": Pose.at(12, 10)},
        game_id="order97-fall-budget",
        datasheet_id="core-character-leader",
        model_profile_id="core-character-leader",
        model_count=1,
    )
    state = lifecycle.state
    assert state is not None
    assert state.battlefield_state is not None
    placement = state.battlefield_state.unit_placement_by_id(units["source"].unit_instance_id)
    initial = placement.model_placements[0]
    result = resolve_fall_back_move(
        scenario=battlefield_scenario_for_state(state=state),
        ruleset_descriptor=state.runtime_ruleset_descriptor(),
        unit_placement=placement,
        fall_back_mode=FallBackModeKind.ORDERED_RETREAT,
        path_witness=PathWitness.for_paths(
            ((initial.model_instance_id, (initial.pose, Pose.at(10 - distance, 10))),)
        ),
    )
    assert result.is_valid is (distance <= 6)
    if distance > 6:
        assert any(
            v.violation_code == "movement_distance_exceeded"
            for p in result.path_validation_results
            for v in p.violations
        )


@pytest.mark.parametrize("target_gap", [5.0, 5.01])
def test_order97_extra_fight_distance_preserves_target_range(target_gap: float) -> None:
    from tests.phase15c_fight_order_helpers import fight_lifecycle

    from warhammer40k_core.engine.battlefield_presence import battlefield_scenario_for_state
    from warhammer40k_core.engine.effects import EffectExpiration, PersistingEffect
    from warhammer40k_core.engine.fight_activation_abilities import (
        FIGHT_ACTIVATION_MOVEMENT_DISTANCE_EFFECT_KIND,
    )
    from warhammer40k_core.engine.fight_resolution import (
        fight_movement_maximum_distance_inches,
        legal_pile_in_target_unit_ids,
    )
    from warhammer40k_core.engine.movement_proposals import ProposalKind

    life, units = fight_lifecycle(
        alpha_unit_ids=("source",),
        enemy_unit_ids=("enemy",),
        origins={"source": Pose.at(10, 10), "enemy": Pose.at(20, 10)},
        game_id="order97-range",
        datasheet_id="core-character-leader",
        model_profile_id="core-character-leader",
        model_count=1,
    )
    state = life.state
    assert state is not None
    assert state.battlefield_state is not None
    source = units["source"]
    enemy = units["enemy"]
    radius = (
        source.own_models[0].geometry.base_shape().max_radius()
        + enemy.own_models[0].geometry.base_shape().max_radius()
    )
    placement = state.battlefield_state.unit_placement_by_id(enemy.unit_instance_id)
    state.replace_battlefield_state(
        state.battlefield_state.with_unit_placement(
            placement.with_model_placements(
                (placement.model_placements[0].with_pose(Pose.at(10 + radius + target_gap, 10)),)
            )
        )
    )
    state.record_persisting_effect(
        PersistingEffect(
            effect_id="order97:distance",
            source_rule_id="test:order97:distance",
            owner_player_id="player-a",
            target_unit_instance_ids=(source.unit_instance_id,),
            started_battle_round=state.battle_round,
            expiration=EffectExpiration.end_turn(
                battle_round=state.battle_round, player_id="player-a"
            ),
            effect_payload={
                "effect_kind": FIGHT_ACTIVATION_MOVEMENT_DISTANCE_EFFECT_KIND,
                "source_id": "test:order97:distance",
                "pile_in_distance_inches": 6.0,
                "consolidate_distance_inches": 5.0,
            },
        )
    )
    assert (
        fight_movement_maximum_distance_inches(
            state=state,
            unit_instance_id=source.unit_instance_id,
            proposal_kind=ProposalKind.PILE_IN,
        )
        == 6
    )
    assert (
        fight_movement_maximum_distance_inches(
            state=state,
            unit_instance_id=source.unit_instance_id,
            proposal_kind=ProposalKind.CONSOLIDATE,
        )
        == 5
    )
    targets = legal_pile_in_target_unit_ids(
        scenario=battlefield_scenario_for_state(state=state),
        ruleset_descriptor=state.runtime_ruleset_descriptor(),
        unit_instance_id=source.unit_instance_id,
        state=state,
    )
    assert (enemy.unit_instance_id in targets) is (target_gap <= 5)


def test_order97_continuing_engagement_preserves_each_enemy_unit() -> None:
    from tests.phase15d_fight_resolution_helpers import melee_fixture

    from warhammer40k_core.engine.fight_resolution import fight_continuing_engagement_violation

    _, ruleset, scenario, source, _, _ = melee_fixture()
    before = scenario.battlefield_state.unit_placement_by_id(source.unit_instance_id)
    after = before.with_model_placements((before.model_placements[0].with_pose(Pose.at(12, 9)),))
    assert (
        fight_continuing_engagement_violation(
            scenario=scenario, ruleset_descriptor=ruleset, before=before, after=before, state=None
        )
        is None
    )
    assert (
        fight_continuing_engagement_violation(
            scenario=scenario, ruleset_descriptor=ruleset, before=before, after=after, state=None
        )
        == "started_engaged_model_not_engaged_after"
    )


def test_order97_overrun_new_enemy_gets_both_types_and_fights_first() -> None:
    from tests.phase15c_fight_order_helpers import fight_lifecycle
    from tests.psychic_modifier_helpers import submit_fixture_request

    from warhammer40k_core.engine.movement_proposals import MovementProposalRequest
    from warhammer40k_core.engine.phase import BattlePhase

    lifecycle, units = fight_lifecycle(
        alpha_unit_ids=("source",),
        enemy_unit_ids=("enemy",),
        origins={"source": Pose.at(10, 10), "enemy": Pose.at(14, 10)},
        game_id="order97-overrun",
        datasheet_id="core-character-leader",
        model_profile_id="core-character-leader",
        model_count=1,
        charge_fights_first_unit_keys=("source",),
        fights_first_unit_keys=("enemy",),
    )
    session = LocalGameSession(lifecycle)
    selected = False
    for _ in range(50):
        request = session.advance_until_decision_or_terminal().decision_request
        assert request is not None
        state = lifecycle.state
        assert state is not None
        assert state.current_battle_phase is BattlePhase.FIGHT
        if request.decision_type == "select_fight_activation":
            assert isinstance(request.payload, dict)
            if request.actor_id == "player-b":
                assert request.payload["ordering_band"] == "fights_first"
                assert {
                    cast(str, cast(dict[str, JsonValue], option.payload)["fight_type"])
                    for option in request.options
                } == {"normal", "overrun"}
                break
            assert {
                cast(str, cast(dict[str, JsonValue], option.payload)["fight_type"])
                for option in request.options
            } == {"overrun"}
            selected = True
        elif request.decision_type == "submit_movement_proposal" and selected:
            move = MovementProposalRequest.from_decision_request_payload(request.payload)
            assert state.battlefield_state is not None
            placement = state.battlefield_state.unit_placement_by_id(
                units["source"].unit_instance_id
            ).model_placements[0]
            result = session.submit_parameterized_payload(
                request_id=request.request_id,
                result_id="order97:overrun-move",
                payload={
                    "proposal_request_id": move.request_id,
                    "proposal_kind": move.proposal_kind.value,
                    "unit_instance_id": move.unit_instance_id,
                    "movement_phase_action": move.movement_phase_action,
                    "movement_mode": "pile_in",
                    "pile_in_target_unit_instance_ids": [units["enemy"].unit_instance_id],
                    "witness": cast(
                        JsonValue,
                        PathWitness.for_paths(
                            ((placement.model_instance_id, (placement.pose, Pose.at(10.6, 10))),)
                        ).to_payload(),
                    ),
                },
            )
            assert result.status_kind is not LifecycleStatusKind.INVALID
            continue
        submit_fixture_request(session, request)
    else:
        raise AssertionError("Newly engaged enemy never received a Fight choice")
    assert_persistence_viewers_replay(session)


def test_order97_action_history_blocks_second_start_after_interruption() -> None:
    from warhammer40k_core.engine.actions import MissionActionState
    from warhammer40k_core.engine.activity_restrictions import record_action_restriction

    session = empty_shooting_session()
    state = session.lifecycle.state
    assert state is not None
    action = MissionActionState.start(
        action_id="order97:action",
        mission_action_id="cleanse-objective",
        player_id="player-a",
        unit_instance_id=SHOOTER,
        target_id="objective",
        condition_target_id=None,
        mission_id="cleanse",
        battle_round=state.battle_round,
        phase="shooting",
        start_timing="shooting_phase",
        completion_timing="turn_end",
        eligible_unit_instance_ids=(SHOOTER,),
        interruption_conditions=("unit_moved",),
        scoring_source_id="test:order97:action",
        victory_points=0,
    )
    record_action_restriction(state=state, action=action)
    action = action.interrupt(reason="unit_moved")
    assert action.status.value == "interrupted"
    assert (
        mission_action_unit_ineligibility_reason(
            state=state,
            player_id="player-a",
            unit_instance_id=SHOOTER,
            runtime_modifier_registry=RuntimeModifierRegistry.empty(),
        )
        == "mission_action_unit_already_started_action"
    )


def test_order97_climbing_counts_both_ascent_and_descent() -> None:
    from warhammer40k_core.geometry.pose import Point3
    from warhammer40k_core.geometry.terrain import TerrainVolume

    mover = Model("mover", Pose.at(1, 1), CircularBase(0.25), ModelVolume(1))
    terrain = TerrainVolume("stack", Point3(3, 1, 0), width=1, depth=1, height=3)
    legality = MovementLegalityContext.from_keywords(
        keywords=("VEHICLE",),
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(),
        movement_mode=MovementMode.NORMAL,
        movement_phase_action="normal_move",
        displacement_kind=ModelDisplacementKind.NORMAL_MOVE,
    )
    result = legality.to_terrain_path_legality_context(
        moving_model=mover,
        witness=PathWitness.for_paths(
            (
                (
                    "mover",
                    (
                        mover.pose,
                        Pose.at(2.25, 1),
                        Pose.at(2.25, 1, 3),
                        Pose.at(3.75, 1, 3),
                        Pose.at(3.75, 1),
                        Pose.at(5, 1),
                    ),
                ),
            )
        ),
        terrain=(terrain,),
        terrain_features=(),
        contact_footprint_available=True,
        sample_interval_inches=0.25,
    ).validate()
    assert result.is_valid
    assert result.segments[0].vertical_distance_inches == 6
    assert (
        result.segments[0].counted_distance_inches
        == result.segments[0].horizontal_distance_inches + 6
    )


def test_order97_natural_double_one_has_no_charge_target() -> None:
    from tests.phase15a_charge_declaration_helpers import charge_lifecycle, compact_test_unit_poses

    from warhammer40k_core.engine.charge_declaration import ChargeRollRequest, ChargeRollResult
    from warhammer40k_core.engine.dice import DiceRollManager
    from warhammer40k_core.engine.phases.charge import _reachable_charge_target_distances
    from warhammer40k_core.engine.unit_proximity import unit_within_enemy_engagement_range

    lifecycle, units = charge_lifecycle(
        alpha_unit_ids=("charger",),
        enemy_model_poses=compact_test_unit_poses(origin=Pose.at(20, 20), model_count=5),
        game_id="order97-double-one",
    )
    state = lifecycle.state
    assert state is not None
    charger = units["charger"].unit_instance_id
    request = ChargeRollRequest(
        request_id="order97:roll",
        game_id=state.game_id,
        battle_round=1,
        player_id="player-a",
        unit_instance_id=charger,
        source_decision_request_id="order97:select",
        source_decision_result_id="order97:selected",
    )
    roll = DiceRollManager(state.game_id).roll_fixed(request.spec, [1, 1])
    assert not unit_within_enemy_engagement_range(state=state, unit_instance_id=charger)
    targets = _reachable_charge_target_distances(
        state=state,
        unit_instance_id=charger,
        maximum_distance_inches=request.resolve_roll(roll).final_value,
        ruleset_descriptor=state.runtime_ruleset_descriptor(),
    )
    result = ChargeRollResult.from_roll_state(
        request=request, roll_state=roll, reachable_target_distances_inches=targets
    )
    assert result.value == 2
    assert result.reachable_target_distances_inches == {}
    assert not result.move_available


def test_order97_absent_unit_is_not_offered_to_shoot() -> None:
    session = empty_shooting_session(spare=True)
    state = session.lifecycle.state
    assert state is not None
    assert state.battlefield_state is not None
    removed_ids = tuple(
        m.model_instance_id for m in state.army_definitions[0].unit_by_id(SHOOTER).own_models
    )
    state.replace_battlefield_state(state.battlefield_state.with_removed_models(removed_ids))
    request = session.advance_until_decision_or_terminal().decision_request
    assert request is not None
    assert request.decision_type == "select_shooting_unit"
    assert SHOOTER not in {o.option_id for o in request.options}
    assert "army-alpha:spare" in {o.option_id for o in request.options}


@pytest.mark.parametrize("dx", [-0.5, 0.5])
def test_order97_unreachable_objective_still_requires_moved_model_to_approach(dx: float) -> None:
    from tests.phase15d_fight_resolution_helpers import melee_fixture

    from warhammer40k_core.core.objectives import ObjectiveMarker
    from warhammer40k_core.core.ruleset_descriptor import ConsolidationModeKind
    from warhammer40k_core.engine.consolidation_model_constraints import (
        consolidation_model_violation,
    )
    from warhammer40k_core.engine.fight_resolution import (
        CONSOLIDATE_ACTION,
        FightMovementProposal,
        build_fight_movement_request,
    )
    from warhammer40k_core.engine.movement_proposals import MovementProposalRequest, ProposalKind

    _, ruleset, scenario, unit, _, _ = melee_fixture(
        target_a_pose=Pose.at(30, 30), target_b_pose=Pose.at(40, 30)
    )
    before = scenario.battlefield_state.unit_placement_by_id(unit.unit_instance_id).model_placements
    after = tuple(p.with_pose(Pose.at(p.pose.position.x + dx, p.pose.position.y)) for p in before)
    marker = ObjectiveMarker(
        objective_marker_id="order97:far-objective", name="Far objective", x_inches=20, y_inches=10
    )
    request = MovementProposalRequest.from_decision_request_payload(
        build_fight_movement_request(
            state_game_id="order97-objective",
            battle_round=1,
            active_player_id="player-a",
            request_id="order97:request",
            actor_id="player-a",
            unit_instance_id=unit.unit_instance_id,
            proposal_kind=ProposalKind.CONSOLIDATE,
            source_decision_request_id="order97:source",
            source_decision_result_id="order97:result",
            spatial_context_hash="0" * 64,
            context={"objective_markers": [cast(JsonValue, marker.to_payload())]},
        ).payload
    )
    proposal = FightMovementProposal(
        proposal_request_id=request.request_id,
        proposal_kind=ProposalKind.CONSOLIDATE,
        unit_instance_id=unit.unit_instance_id,
        movement_phase_action=CONSOLIDATE_ACTION,
        movement_mode=MovementMode.CONSOLIDATE,
        consolidation_mode=ConsolidationModeKind.OBJECTIVE,
        objective_id=marker.objective_marker_id,
        witness=PathWitness.for_paths(
            tuple(
                (a.model_instance_id, (a.pose, b.pose)) for a, b in zip(before, after, strict=True)
            )
        ),
    )
    violation = consolidation_model_violation(
        scenario=scenario,
        ruleset_descriptor=ruleset,
        proposal_request=request,
        proposal=proposal,
        before=before,
        after=after,
        state=None,
    )
    assert violation == (None if dx > 0 else "objective_consolidation_model_not_closer")


def test_order97_hazardous_casualty_may_be_a_non_weapon_bearer() -> None:
    from tests.optional_shooting_helpers import optional_payload
    from tests.order97_gap_probes_09_17 import hazardous_nonbearer_session

    session, nonbearer = hazardous_nonbearer_session()
    state = session.lifecycle.state
    assert state is not None
    request = select_optional_shooting(session)
    status = session.submit_parameterized_payload(
        request_id=request.request_id,
        payload=optional_payload(request),
        result_id="order97:nonbearer",
    )
    allocation = status.decision_request
    assert allocation is not None
    assert allocation.decision_type == "select_mortal_wound_model"
    assert nonbearer.wargear_ids == ()
    assert nonbearer.model_instance_id in {option.option_id for option in allocation.options}
    result = session.submit_option(
        request_id=allocation.request_id,
        option_id=nonbearer.model_instance_id,
        result_id="order97:allocate-nonbearer",
    )
    assert result.status_kind is not LifecycleStatusKind.INVALID
    after = (
        state.army_definitions[0].unit_by_id(SHOOTER).own_model_by_id(nonbearer.model_instance_id)
    )
    assert after.current_wounds < nonbearer.current_wounds


def test_order97_visible_target_filter_uses_rule_owner_as_observer() -> None:
    from warhammer40k_core.engine.stratagems_geometry import visible_enemy_unit_ids_for_source

    session = empty_shooting_session(spare=True, reachable=True)
    state = session.lifecycle.state
    assert state is not None
    battlefield = state.battlefield_state
    assert battlefield is not None
    spare = battlefield.unit_placement_by_id("army-alpha:spare")
    battlefield = battlefield.with_unit_placement(
        spare.with_model_placements(
            tuple(p.with_pose(Pose.at(10, 45)) for p in spare.model_placements)
        )
    )
    display = TerrainDisplayGeometry.axis_aligned_rectangle(
        center_x_inches=20,
        center_y_inches=35,
        width_inches=2,
        depth_inches=2,
        display_template_id="order97:observer-blocker",
    )
    feature = TerrainFeatureDefinition(
        feature_id="order97:observer-blocker",
        feature_kind=TerrainFeatureKind.BATTLEFIELD_DEBRIS_AND_STATUARY,
        footprint_center_x_inches=20,
        footprint_center_y_inches=35,
        footprint_width_inches=2,
        footprint_depth_inches=2,
        rules_footprint_polygon=display.footprint_polygon,
        display_geometry=display,
        classification=TerrainAreaClassification.DENSE,
        walls=(
            TerrainWallDefinition(
                wall_id="order97:screen",
                center_x_inches=20,
                center_y_inches=35,
                bottom_z_inches=0,
                width_inches=2,
                depth_inches=2,
                height_inches=10,
            ),
        ),
    )
    state.replace_battlefield_state(replace(battlefield, terrain_features=(feature,)))
    assert (
        visible_enemy_unit_ids_for_source(
            state=state,
            player_id="player-a",
            source_unit_instance_id=SHOOTER,
            range_inches=48,
        )
        == ()
    )
    assert visible_enemy_unit_ids_for_source(
        state=state,
        player_id="player-a",
        source_unit_instance_id="army-alpha:spare",
        range_inches=48,
    ) == ("army-beta:enemy",)


@pytest.mark.parametrize("use_buff", [False, True])
def test_order97_unit_targeted_stratagem_buff_survives_into_retained_melee(use_buff: bool) -> None:
    from tests.phase15c_fight_order_helpers import fight_lifecycle
    from tests.psychic_modifier_helpers import pending_request, submit_fixture_request
    from tests.retained_attack_helpers import lethal_retained_attack_catalog

    from warhammer40k_core.core.detachment import StratagemDefinition
    from warhammer40k_core.engine.attack_completion_authority import completed_attack_sequence
    from warhammer40k_core.engine.command_points import CommandPointSourceKind
    from warhammer40k_core.engine.damage_allocation import (
        DestructionReactionKind,
        DestructionReactionSource,
    )
    from warhammer40k_core.engine.faction_content.warhammer_40000_11th.chaos_daemons.detachments.daemonic_incursion import (  # noqa: E501
        stratagems,
    )
    from warhammer40k_core.engine.lifecycle import GameLifecycle
    from warhammer40k_core.engine.phase import BattlePhase
    from warhammer40k_core.engine.retained_destruction_state import retained_destructions
    from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
        faction_daemonic_incursion_ir_support_2026_27 as sources,
    )

    record = next(
        row
        for row in stratagems.runtime_contribution().stratagem_records
        if row.definition.stratagem_id == sources.DRAUGHT_OF_TERROR_STRATAGEM_ID
        and row.definition.timing.phase is BattlePhase.FIGHT
    )
    profile = record.definition
    assert isinstance(profile.effect_payload, dict)
    effect_ir = profile.effect_payload["rule_ir"]
    assert isinstance(effect_ir, dict)
    effect_source_id = effect_ir["source_id"]
    catalog = lethal_retained_attack_catalog()
    detachment = replace(
        catalog.detachments[0],
        canonical_detachment_id=sources.DAEMONIC_INCURSION_DETACHMENT_ID,
        detachment_id=sources.DAEMONIC_INCURSION_DETACHMENT_ID,
        name="Retained unit buff consumer fixture",
        faction_id="chaos-daemons",
        stratagem_ids=(profile.stratagem_id,),
    )
    catalog = replace(
        catalog,
        detachments=(*catalog.detachments, detachment),
        factions=(
            *catalog.factions,
            replace(
                catalog.factions[0],
                faction_id="chaos-daemons",
                name="Chaos Daemons",
                faction_keywords=("LEGIONES DAEMONICA",),
            ),
        ),
        datasheets=tuple(
            replace(
                sheet,
                keywords=replace(
                    sheet.keywords,
                    faction_keywords=(*sheet.keywords.faction_keywords, "LEGIONES DAEMONICA"),
                ),
            )
            for sheet in catalog.datasheets
        ),
        stratagems=(
            *catalog.stratagems,
            StratagemDefinition(
                stratagem_id=profile.stratagem_id,
                name=profile.name,
                source_id=profile.source_id,
                command_point_cost=profile.command_point_cost,
            ),
        ),
    )
    lifecycle, units = fight_lifecycle(
        alpha_unit_ids=("intercessor-1",),
        enemy_unit_ids=("enemy",),
        origins={"intercessor-1": Pose.at(10, 10), "enemy": Pose.at(12, 10)},
        game_id="order56-retained-fight-0",
        model_count=1,
        datasheet_id="core-character-leader",
        model_profile_id="core-character-leader",
        catalog=catalog,
        fights_first_unit_keys=("enemy",),
        alpha_faction_id="chaos-daemons",
        alpha_detachment_ids=(sources.DAEMONIC_INCURSION_DETACHMENT_ID,),
        record_deployment=True,
    )
    state = lifecycle.state
    assert state is not None
    model_id = units["intercessor-1"].own_models[0].model_instance_id
    state.record_model_destruction_reaction_sources(
        model_instance_id=model_id,
        sources=(
            DestructionReactionSource(
                source_id="order97:fight-on-death",
                source_rule_id="order97:fight-on-death",
                reaction_kind=DestructionReactionKind.FIGHT_ON_DEATH,
            ),
        ),
    )
    state.gain_command_points(
        player_id="player-a",
        amount=1,
        source_id="order97:starting-cp",
        source_kind=CommandPointSourceKind.OTHER,
    )
    from tests.dice_result_semantics_helpers import open_phase

    from warhammer40k_core.engine.phases import fight as fight_phase
    from warhammer40k_core.engine.stratagems import (
        StratagemCatalogIndex,
        StratagemEligibilityContext,
        create_stratagem_use_decision_request,
        stratagem_decline_option,
        stratagem_use_options_from_index,
    )
    from warhammer40k_core.engine.timing_windows import TimingTriggerKind

    # The fixture starts at the legal Fight boundary with the source-backed
    # Stratagem request pending; the facade owns its choice and effect mutation.
    open_phase(lifecycle)
    fight_phase._ensure_fight_phase_state(  # pyright: ignore[reportPrivateUsage]
        state=state,
        decisions=lifecycle.decision_controller,
        policy=lifecycle.config.ruleset_descriptor.fight_policy,
    )
    context = StratagemEligibilityContext.from_state(
        state=state,
        player_id="player-a",
        trigger_kind=TimingTriggerKind.START_PHASE,
    )
    options = stratagem_use_options_from_index(
        state=state,
        context=context,
        index=StratagemCatalogIndex.from_records((record,)),
    )
    assert len(options) == 1
    lifecycle.decision_controller.request_decision(
        create_stratagem_use_decision_request(
            state=state,
            context=context,
            options=(*options, stratagem_decline_option()),
        )
    )
    session = LocalGameSession(GameLifecycle.from_payload(lifecycle.to_payload()))
    buff_offered = False
    retained_melee = False
    for _ in range(100):
        request = pending_request(session)
        buff_options = tuple(
            option
            for option in request.options
            if option.option_id.startswith(f"use-stratagem:{profile.stratagem_id}:")
        )
        if buff_options:
            buff_offered = True
            option_id = buff_options[0].option_id if use_buff else "decline_stratagem_window"
            status = session.submit_option(
                request_id=request.request_id,
                option_id=option_id,
                result_id=f"{request.request_id}:buff",
            )
            assert status.status_kind is not LifecycleStatusKind.INVALID
        elif request.decision_type == "select_destruction_reaction":
            status = session.submit_option(
                request_id=request.request_id,
                result_id=f"{request.request_id}:retain",
                option_id="order97:fight-on-death",
            )
            assert status.status_kind is not LifecycleStatusKind.INVALID
        elif request.decision_type == "submit_stratagem_target_proposal":
            from warhammer40k_core.engine.stratagems import stratagem_decline_payload

            status = session.submit_parameterized_payload(
                request_id=request.request_id,
                result_id=f"{request.request_id}:decline",
                payload=stratagem_decline_payload(),
            )
            assert status.status_kind is not LifecycleStatusKind.INVALID
        elif request.decision_type == "use_stratagem":
            status = session.submit_option(
                request_id=request.request_id,
                result_id=f"{request.request_id}:decline",
                option_id="decline_stratagem_window",
            )
            assert status.status_kind is not LifecycleStatusKind.INVALID
        else:
            state = session.lifecycle.state
            assert state is not None
            if request.decision_type == "submit_melee_declaration" and any(
                r.model_instance_id == model_id and r.is_retained
                for r in retained_destructions(state=state)
            ):
                retained_melee = True
                assert (
                    state.army_definitions[0]
                    .unit_by_id("army-alpha:intercessor-1")
                    .own_models[0]
                    .current_wounds
                    == 0
                )
                assert (
                    any(
                        effect.source_rule_id == effect_source_id
                        and "army-alpha:intercessor-1" in effect.target_unit_instance_ids
                        for effect in state.persisting_effects
                    )
                    is use_buff
                )
                checkpoint = json.loads(json.dumps(session.to_persistence_payload()))
                restored = LocalGameSession.from_persistence_payload(checkpoint)
                assert restored.to_persistence_payload() == checkpoint
                session = restored
            submit_fixture_request(session, request)
        state = session.lifecycle.state
        assert state is not None
        assert state.battlefield_state is not None
        if model_id in state.battlefield_state.removed_model_ids:
            break
    else:
        raise AssertionError("Retained melee did not finish.")
    assert buff_offered
    assert retained_melee
    assert (
        any(
            record.stratagem_id == profile.stratagem_id
            and record.targeted_unit_instance_ids == ("army-alpha:intercessor-1",)
            for record in state.stratagem_use_records
        )
        is use_buff
    )
    events = session.lifecycle.decision_controller.event_log.records
    sequences = tuple(
        completed_attack_sequence(
            event_records=events, sequence_id=cast(str, e.payload["sequence_id"])
        )
        for e in events
        if e.event_type == "attack_sequence_completed" and isinstance(e.payload, dict)
    )
    retained_pools = tuple(
        pool
        for sequence in sequences
        for pool in sequence.attack_pools
        if pool.attacker_model_instance_id == model_id
    )
    assert len(retained_pools) == 1
    assert retained_pools[0].attacks == 1
    assert retained_pools[0].weapon_profile.armor_penetration.final == (-11 if use_buff else -10)
    assert_persistence_viewers_replay(session)
