"""Executable Order 97 audit observations, not passing gameplay certificates.

Run ``uv run python -m tests.order97_gap_probes_09_17`` to reproduce the
selected-source discrepancies. The output deliberately records both answers.
"""

from __future__ import annotations

import json
from dataclasses import replace
from typing import cast

from tests.empty_shooting_helpers import SHOOTER, empty_shooting_session
from tests.order85_overhang_helpers import overhang_session
from tests.phase15c_fight_order_helpers import fight_lifecycle
from tests.unit_keyword_helpers import with_unit_keywords
from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.core.ruleset_descriptor import (
    MovementMode,
    RulesetDescriptor,
    TerrainFeatureKind,
)
from warhammer40k_core.core.terrain_display import TerrainDisplayGeometry
from warhammer40k_core.core.visibility import TerrainVisibilityContext
from warhammer40k_core.core.weapon_profiles import WeaponKeyword
from warhammer40k_core.engine.actions import MissionActionState
from warhammer40k_core.engine.battle_shock_state import apply_direct_battle_shock_state
from warhammer40k_core.engine.battlefield_state import (
    ModelDisplacementKind,
    geometry_model_for_placement,
)
from warhammer40k_core.engine.event_log import JsonValue
from warhammer40k_core.engine.movement_legality import MovementLegalityContext
from warhammer40k_core.engine.movement_proposals import MovementProposalRequest
from warhammer40k_core.engine.unit_factory import ModelInstance
from warhammer40k_core.engine.unit_proximity import unit_within_enemy_engagement_range
from warhammer40k_core.geometry.base import CircularBase
from warhammer40k_core.geometry.pathing import PathWitness
from warhammer40k_core.geometry.pose import Pose
from warhammer40k_core.geometry.terrain import TerrainFeatureDefinition, TerrainWallDefinition
from warhammer40k_core.geometry.terrain_classification import TerrainAreaClassification
from warhammer40k_core.geometry.volume import Model, ModelVolume


def _observation(
    requirement_id: str,
    row_id: str,
    owner: str,
    expected: JsonValue,
    observed: JsonValue,
    detail: str,
) -> dict[str, JsonValue]:
    return {
        "requirement_id": requirement_id,
        "row_id": row_id,
        "owner": owner,
        "expected_selected_source_answer": expected,
        "observed_answer": observed,
        "detail": detail,
    }


def probe_action_battle_shock() -> dict[str, JsonValue]:
    session = empty_shooting_session()
    state = session.lifecycle.state
    assert state is not None
    action = MissionActionState.start(
        action_id="order97:audit-action",
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
    state.record_mission_action_state(action)
    apply_direct_battle_shock_state(
        state=state,
        player_id="player-a",
        unit_instance_id=SHOOTER,
        source_result_id="order97:shock",
        battle_round=state.battle_round,
    )
    return _observation(
        "faq-bbe268a2-b1fd-43ab-8b24-fd4363730c3f-shock-interrupt",
        "faq:bbe268a2-b1fd-43ab-8b24-fd4363730c3f",
        "src/warhammer40k_core/engine/battle_shock_state.py:apply_direct_battle_shock_state",
        {"action_status": "interrupted", "shocked": True},
        {
            "action_status": state.mission_action_state_by_id(action.action_id).status.value,
            "shocked": SHOOTER in state.battle_shocked_unit_ids,
        },
        "The real status mutation leaves the active action STARTED instead of "
        "terminally interrupting it.",
    )


def probe_based_frame_measurement() -> dict[str, JsonValue]:
    session = overhang_session(start_y=8)
    state = session.lifecycle.state
    assert state is not None
    assert state.battlefield_state is not None
    army = state.army_definitions[1]
    unit = army.units[0]
    unit = with_unit_keywords(unit, keywords=(*unit.keywords, "FRAME"))
    state.replace_army_definitions([state.army_definitions[0], replace(army, units=(unit,))])
    source = state.army_definitions[0].units[0]
    a = geometry_model_for_placement(
        model=source.own_models[0],
        placement=state.battlefield_state.unit_placement_by_id(
            source.unit_instance_id
        ).model_placements[0],
    )
    b = geometry_model_for_placement(
        model=unit.own_models[0],
        placement=state.battlefield_state.unit_placement_by_id(
            unit.unit_instance_id
        ).model_placements[0],
    )
    return _observation(
        "17.02-measurement",
        "rule:17:17.02:1",
        "src/warhammer40k_core/engine/battlefield_state.py:geometry_model_for_placement",
        {"engaged": True},
        {
            "engaged": unit_within_enemy_engagement_range(
                state=state, unit_instance_id=source.unit_instance_id
            ),
            "support_base_edge_distance_inches": a.range_to(b),
            "body_edge_distance_inches": 6
            - a.base.max_radius()
            - b.body_parts[0].base.max_radius(),
        },
        "Canonical based FRAME overhang: support-base range exceeds two inches "
        "while its body is within two inches.",
    )


def probe_friendly_transit() -> dict[str, JsonValue]:
    answers: dict[str, JsonValue] = {}
    expected: dict[str, JsonValue] = {}
    for mode in (
        MovementMode.FALL_BACK,
        MovementMode.CHARGE,
        MovementMode.PILE_IN,
        MovementMode.CONSOLIDATE,
    ):
        context = MovementLegalityContext.from_keywords(
            keywords=("VEHICLE",),
            ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(),
            movement_mode=mode,
            movement_phase_action=None,
            displacement_kind=ModelDisplacementKind(
                mode.value if mode is not MovementMode.CHARGE else "charge_move"
            ),
        )
        mover = Model("mover", Pose.at(5, 5), CircularBase(0.5), ModelVolume(1))
        friendly = Model("friendly", Pose.at(7, 5), CircularBase(0.5), ModelVolume(1))
        result = context.to_path_validation_context(
            moving_model=mover,
            witness=PathWitness.for_paths((("mover", (mover.pose, Pose.at(9, 5))),)),
            battlefield_width_inches=40,
            battlefield_depth_inches=40,
            friendly_models=(friendly,),
            friendly_vehicle_monster_model_ids=("friendly",),
        ).validate()
        expected[mode.value] = True
        answers[mode.value] = {
            "is_valid": result.is_valid,
            "violations": [v.violation_code for v in result.violations],
        }
    return _observation(
        "faq-9b1c81f5-2ea0-40eb-9015-6a005367cd75-friendly-transit",
        "faq:9b1c81f5-2ea0-40eb-9015-6a005367cd75",
        ""
        ""
        ""
        "src/warhammer40k_core/engine/movement_legality.py:MovementLegalityContext.to_path_validation_context",
        expected,
        answers,
        "The Normal/Advance exception incorrectly blocks ordinary friendly-model "
        "transit for all four other movement modes.",
    )


def enclosed_window_feature() -> TerrainFeatureDefinition:
    display = TerrainDisplayGeometry.axis_aligned_rectangle(
        center_x_inches=0,
        center_y_inches=0,
        width_inches=4,
        depth_inches=4,
        display_template_id="order97-window",
    )

    def wall(
        name: str, y: float, bottom: float, depth: float, height: float
    ) -> TerrainWallDefinition:
        return TerrainWallDefinition(
            wall_id=name,
            center_x_inches=1,
            center_y_inches=y,
            bottom_z_inches=bottom,
            width_inches=0.1,
            depth_inches=depth,
            height_inches=height,
        )

    return TerrainFeatureDefinition(
        feature_id="order97-window",
        feature_kind=TerrainFeatureKind.BATTLEFIELD_DEBRIS_AND_STATUARY,
        classification=TerrainAreaClassification.DENSE,
        footprint_center_x_inches=0,
        footprint_center_y_inches=0,
        footprint_width_inches=4,
        footprint_depth_inches=4,
        rules_footprint_polygon=display.footprint_polygon,
        display_geometry=display,
        walls=(
            wall("left", -1.5, 0, 1, 4),
            wall("right", 1.5, 0, 1, 4),
            wall("sill", 0, 0, 2, 1),
            wall("lintel", 0, 2, 2, 2),
        ),
    )


def probe_solid_window() -> dict[str, JsonValue]:
    observer = Model("observer", Pose.at(0, 0, 1.4), CircularBase(0.1), ModelVolume(0.2))
    target = Model("target", Pose.at(3, 0, 1.4), CircularBase(0.1), ModelVolume(0.2))
    context = TerrainVisibilityContext.from_ruleset_descriptor(
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(),
        los_cache_key="order97-window",
        observer_model=observer,
        target_models=(target,),
        target_model_keywords=(("target", ("INFANTRY",)),),
        terrain_features=(enclosed_window_feature(),),
    )
    return _observation(
        "13.11-solid",
        "rule:13:13.11:1",
        "src/warhammer40k_core/core/visibility.py:TerrainVisibilityContext",
        {"visible": False},
        {"visible": context.resolve_line_of_sight().unit_visible},
        "Fully enclosed window from z=1 to2in; observer inside the terrain area "
        "excludes Obscuring, isolating Solid.",
    )


def probe_vertical_contact() -> dict[str, JsonValue]:
    mover = Model("mover", Pose.at(-4, 0), CircularBase(0.1), ModelVolume(0.2))
    legality = MovementLegalityContext.from_keywords(
        keywords=("INFANTRY",),
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(),
        movement_mode=MovementMode.NORMAL,
        movement_phase_action="normal_move",
        displacement_kind=ModelDisplacementKind.NORMAL_MOVE,
    )
    result = legality.to_terrain_path_legality_context(
        moving_model=mover,
        witness=PathWitness.for_paths(
            (("mover", (mover.pose, Pose.at(-4, 0, 3), Pose.at(-3, 0, 3), Pose.at(-3, 0))),)
        ),
        terrain=(),
        terrain_features=(enclosed_window_feature(),),
        contact_footprint_available=True,
        sample_interval_inches=0.5,
    ).validate()
    return _observation(
        "13.06-vertical-contact",
        "rule:13:13.06:1",
        "src/warhammer40k_core/geometry/pathing.py:TerrainPathLegalityContext.validate",
        {"is_valid": False},
        {"is_valid": result.is_valid, "violations": [v.violation_code for v in result.violations]},
        "The path climbs and descends three inches more than half an inch from all "
        "physical feature surfaces.",
    )


def probe_pile_in_attainable_engagement() -> dict[str, JsonValue]:
    lifecycle, units = fight_lifecycle(
        alpha_unit_ids=("source",),
        enemy_unit_ids=("enemy",),
        origins={"source": Pose.at(10, 10), "enemy": Pose.at(12, 10)},
        game_id="order97-pile-mandatory",
        enemy_unit_specs={"enemy": ("core-character-leader", "core-character-leader", 1)},
        poses_by_unit_key={
            "source": (
                Pose.at(10, 10),
                Pose.at(10, 13),
                Pose.at(8.5, 10),
                Pose.at(8.5, 13),
                Pose.at(7, 11.5),
            ),
            "enemy": (Pose.at(12, 10),),
        },
    )
    session = LocalGameSession(lifecycle)
    request = session.advance_until_decision_or_terminal().decision_request
    assert request is not None
    baseline = session.to_persistence_payload()
    move = MovementProposalRequest.from_decision_request_payload(request.payload)
    state = lifecycle.state
    assert state is not None
    assert state.battlefield_state is not None
    placement = state.battlefield_state.unit_placement_by_id(units["source"].unit_instance_id)
    paths = tuple(
        (p.model_instance_id, (p.pose, Pose.at(p.pose.position.x + 0.1, p.pose.position.y)))
        for p in placement.model_placements
    )
    payload: dict[str, JsonValue] = {
        "proposal_request_id": move.request_id,
        "proposal_kind": move.proposal_kind.value,
        "unit_instance_id": move.unit_instance_id,
        "movement_phase_action": move.movement_phase_action,
        "movement_mode": "pile_in",
        "pile_in_target_unit_instance_ids": [units["enemy"].unit_instance_id],
        "witness": cast(JsonValue, PathWitness.for_paths(paths).to_payload()),
    }
    outcome = session.submit_parameterized_payload(
        request_id=request.request_id, result_id="order97:pile", payload=payload
    )
    a = state.battlefield_state.unit_placement_by_id(
        units["source"].unit_instance_id
    ).model_placements[1]
    b = state.battlefield_state.unit_placement_by_id(
        units["enemy"].unit_instance_id
    ).model_placements[0]
    ga = geometry_model_for_placement(model=units["source"].own_models[1], placement=a)
    gb = geometry_model_for_placement(model=units["enemy"].own_models[0], placement=b)
    alternate = LocalGameSession.from_persistence_payload(baseline)
    paths2 = tuple(
        (mid, (poses[0], Pose.at(11, 12.5) if mid == a.model_instance_id else poses[1]))
        for mid, poses in paths
    )
    payload["witness"] = cast(JsonValue, PathWitness.for_paths(paths2).to_payload())
    legal = alternate.submit_parameterized_payload(
        request_id=request.request_id, result_id="order97:engaging-alternative", payload=payload
    )
    return _observation(
        "12.03-attainable-engagement",
        "rule:12:12.03:1",
        "src/warhammer40k_core/engine/fight_resolution.py:_pile_in_endpoint_validation",
        {"nonengaging_move": "invalid", "engaging_alternative": "waiting_for_decision"},
        {
            "nonengaging_move": outcome.status_kind.value,
            "engaging_alternative": legal.status_kind.value,
            "nonengaging_model_distance_inches": ga.range_to(gb),
            "engagement_limit_inches": 2.0,
        },
        "A moved trailing model remains outside Engagement Range despite an "
        "accepted legal engaging alternative from the identical baseline.",
    )


def probe_frame_terrain_membership() -> dict[str, JsonValue]:
    from warhammer40k_core.geometry.terrain_area_visibility import (
        TerrainVisibilityArea,
        model_intersects_terrain_area,
    )

    session = overhang_session(start_y=8)
    state = session.lifecycle.state
    assert state is not None
    assert state.battlefield_state is not None
    army = state.army_definitions[1]
    frame = with_unit_keywords(army.units[0], keywords=(*army.units[0].keywords, "FRAME"))
    state.replace_army_definitions([state.army_definitions[0], replace(army, units=(frame,))])
    model = geometry_model_for_placement(
        model=frame.own_models[0],
        placement=state.battlefield_state.unit_placement_by_id(
            frame.unit_instance_id
        ).model_placements[0],
    )
    area = TerrainVisibilityArea(
        "frame-area",
        ("frame-area",),
        TerrainAreaClassification.LIGHT,
        (((9.5, 10.25), (10.5, 10.25), (10.5, 10.75), (9.5, 10.75)),),
    )
    return _observation(
        "faq-603e9b2f-cc24-498c-ac2e-08ad3068f257-frame-membership",
        "faq:603e9b2f-cc24-498c-ac2e-08ad3068f257",
        "src/warhammer40k_core/geometry/terrain_area_visibility.py:model_intersects_terrain_area",
        {"within_terrain_area": True},
        {"within_terrain_area": model_intersects_terrain_area(model, area)},
        "An eight-inch body centred at (10,14) projects into y10.25..10.75; "
        "its support base does not.",
    )


def probe_solid_window_endpoint() -> dict[str, JsonValue]:
    from warhammer40k_core.engine.endpoint_placement import terrain_endpoint_placement_violation

    session = empty_shooting_session()
    state = session.lifecycle.state
    assert state is not None
    unit = state.army_definitions[0].unit_by_id(SHOOTER)
    model = Model(
        unit.own_models[0].model_instance_id,
        Pose.at(1, 0, 1.4),
        CircularBase(0.1),
        ModelVolume(0.2),
    )
    result = terrain_endpoint_placement_violation(
        model=model,
        unit=unit,
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(),
        terrain_features=(enclosed_window_feature(),),
        violation_code="order97-solid",
        placement_label="audit",
    )
    return _observation(
        "13.06.01-solid-endpoint",
        "rule:13:13.06.01:1",
        "src/warhammer40k_core/engine/endpoint_placement.py:terrain_endpoint_placement_violation",
        {"legal": False},
        {"legal": result is None},
        "An Infantry model occupies the enclosed window below three inches; "
        "physical wall volumes alone allow it.",
    )


def probe_zero_oc_unit_control() -> dict[str, JsonValue]:
    from warhammer40k_core.engine.objective_control import (
        ObjectiveControlContribution,
        ObjectiveControlResult,
    )
    from warhammer40k_core.engine.stratagems_targeting import _objective_control_result_has_unit

    contributors = tuple(
        ObjectiveControlContribution(
            player_id="player-a",
            unit_instance_id=unit,
            model_instance_id=unit + ":model",
            objective_control=oc,
            effective_objective_control=oc,
            battle_shocked=False,
            horizontal_distance_inches=1,
            vertical_gap_inches=0,
        )
        for unit, oc in (("zero-unit", 0), ("positive-unit", 2))
    )
    result = ObjectiveControlResult.from_contributors(
        objective_id="objective", contributors=contributors
    )
    return _observation(
        "14.02-controlling-unit",
        "rule:14:14.02:1",
        "src/warhammer40k_core/engine/stratagems_targeting.py:_objective_control_result_has_unit",
        {"zero_unit_controls": False},
        {
            "zero_unit_controls": _objective_control_result_has_unit(
                result=result, unit_instance_id="zero-unit"
            ),
            "player_controller": result.controlled_by_player_id,
        },
        "The selected-unit objective-control consumer accepts the zero-OC "
        "contributor solely from membership.",
    )


def probe_extra_distance_overrun_window() -> dict[str, JsonValue]:
    from tests.psychic_modifier_helpers import submit_fixture_request
    from warhammer40k_core.engine.effects import EffectExpiration, PersistingEffect
    from warhammer40k_core.engine.fight_activation_abilities import (
        FIGHT_ACTIVATION_MOVEMENT_DISTANCE_EFFECT_KIND,
    )

    lifecycle, units = fight_lifecycle(
        alpha_unit_ids=("source",),
        enemy_unit_ids=("enemy",),
        origins={"source": Pose.at(10, 10), "enemy": Pose.at(14, 10)},
        game_id="order97-overrun-distance",
        datasheet_id="core-character-leader",
        model_profile_id="core-character-leader",
        model_count=1,
        charge_fights_first_unit_keys=("source",),
    )
    state = lifecycle.state
    assert state is not None
    state.record_persisting_effect(
        PersistingEffect(
            effect_id="order97:extra-distance",
            source_rule_id="test:order97:extra-distance",
            owner_player_id="player-a",
            target_unit_instance_ids=(units["source"].unit_instance_id,),
            started_battle_round=1,
            expiration=EffectExpiration.end_turn(battle_round=1, player_id="player-a"),
            effect_payload={
                "effect_kind": FIGHT_ACTIVATION_MOVEMENT_DISTANCE_EFFECT_KIND,
                "source_id": "test:order97:extra-distance",
                "pile_in_distance_inches": 6.0,
                "consolidate_distance_inches": 3.0,
            },
        )
    )
    session = LocalGameSession(lifecycle)
    selected = False
    for _ in range(20):
        request = session.advance_until_decision_or_terminal().decision_request
        assert request is not None
        if selected and request.decision_type == "submit_movement_proposal":
            move = MovementProposalRequest.from_decision_request_payload(request.payload)
            assert move.context is not None
            return _observation(
                "faq-9657bb5d-72da-4d42-9927-731c9fc0e315-distance-window",
                "faq:9657bb5d-72da-4d42-9927-731c9fc0e315",
                ""
                ""
                "src/warhammer40k_core/engine/fight_resolution.py:fight_movement_maximum_distance_inches",
                {"overrun_pile_in_maximum_inches": 3.0},
                {"overrun_pile_in_maximum_inches": move.context["maximum_distance_inches"]},
                "A generic extra-distance permission also enlarges the Overrun Pile In "
                "during the Fight step.",
            )
        if request.decision_type == "select_fight_activation":
            selected = True
        submit_fixture_request(session, request)
    raise AssertionError("Expected Overrun Pile In request was not emitted")


def probe_dense_floor_crossing() -> dict[str, JsonValue]:
    from warhammer40k_core.geometry.terrain import TerrainFloorDefinition

    feature = replace(
        enclosed_window_feature(),
        walls=(),
        floors=(
            TerrainFloorDefinition(
                floor_id="ceiling",
                center_x_inches=1,
                center_y_inches=0,
                bottom_z_inches=3,
                width_inches=2,
                depth_inches=4,
                thickness_inches=0.2,
            ),
        ),
    )
    mover = Model("mover", Pose.at(1, 0), CircularBase(0.25), ModelVolume(1))
    context = MovementLegalityContext.from_keywords(
        keywords=("VEHICLE",),
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(),
        movement_mode=MovementMode.NORMAL,
        movement_phase_action="normal_move",
        displacement_kind=ModelDisplacementKind.NORMAL_MOVE,
    )
    result = context.to_terrain_path_legality_context(
        moving_model=mover,
        witness=PathWitness.for_paths(
            (("mover", (mover.pose, Pose.at(1, 0, 5), Pose.at(4, 0, 5), Pose.at(4, 0))),)
        ),
        terrain=(),
        terrain_features=(feature,),
        contact_footprint_available=True,
        sample_interval_inches=0.5,
    ).validate()
    return _observation(
        "13.06-dense-floor-crossing",
        "rule:13:13.06:1",
        "src/warhammer40k_core/geometry/pathing.py:TerrainPathLegalityContext.validate",
        {"is_valid": False},
        {"is_valid": result.is_valid, "violations": [v.violation_code for v in result.violations]},
        "A Vehicle ascends through a Dense floor at z3in; the thin floor is "
        "treated as freely traversable.",
    )


def probe_exposed_category() -> dict[str, JsonValue]:
    from warhammer40k_core.geometry.terrain_classification import (
        TerrainClassificationError,
        terrain_area_classification_from_token,
    )

    outcome: JsonValue
    try:
        outcome = terrain_area_classification_from_token("exposed").value
    except TerrainClassificationError as error:
        outcome = {"domain_error": str(error)}
    return _observation(
        "13.06-exposed-traversal",
        "rule:13:13.06:1",
        ""
        "src/warhammer40k_core/geometry/terrain_classification.py:terrain_area_classification_from_token",
        {"category": "exposed", "unrestricted_horizontal_vertical_transit": True},
        outcome,
        "The selected-source Exposed category has no explicit typed "
        "representation; Unknown is not its source-backed alias.",
    )


def probe_pile_in_closest_target() -> dict[str, JsonValue]:
    from tests.phase15d_fight_resolution_helpers import melee_fixture
    from warhammer40k_core.engine.fight_resolution import (
        fight_moved_models_closer_to_targets_violation,
    )

    _, _, scenario, unit, target, other = melee_fixture(
        target_a_pose=Pose.at(13.9, 10), target_b_pose=Pose.at(10, 14.3)
    )
    before = scenario.battlefield_state.unit_placement_by_id(unit.unit_instance_id)
    after = before.with_model_placements((before.model_placements[0].with_pose(Pose.at(10, 12.7)),))
    violation = fight_moved_models_closer_to_targets_violation(
        scenario=scenario,
        before=before,
        after=after,
        target_unit_instance_ids=(target.unit_instance_id, other.unit_instance_id),
        state=None,
    )
    return _observation(
        "12.03-closest-target",
        "rule:12:12.03:1",
        ""
        "src/warhammer40k_core/engine/fight_resolution.py:fight_moved_models_closer_to_targets_violation",
        {"legal": False},
        {"legal": violation is None, "violation": violation},
        "The model moves away from the initially closest target at(13.9,10), "
        "approaching the other target at(10,14.3).",
    )


def hazardous_nonbearer_session() -> tuple[LocalGameSession, ModelInstance]:
    """Canonical firing squad with a weaponless legal Hazardous recipient."""
    session = empty_shooting_session(
        reachable=True,
        spare=True,
        model_count=3,
        keywords=(WeaponKeyword.HAZARDOUS,),
        game_id="order97-nonbearer-1",
    )
    state = session.lifecycle.state
    assert state is not None
    army = state.army_definitions[0]
    unit = army.unit_by_id(SHOOTER)
    nonbearer = replace(unit.own_models[-1], wargear_ids=())
    state.replace_army_definitions(
        [
            replace(
                army,
                units=tuple(
                    replace(u, own_models=(*u.own_models[:-1], nonbearer))
                    if u.unit_instance_id == SHOOTER
                    else u
                    for u in army.units
                ),
            ),
            state.army_definitions[1],
        ]
    )
    return session, nonbearer


def probe_mortal_allocation_trigger() -> dict[str, JsonValue]:
    from tests.optional_shooting_helpers import optional_payload, select_optional_shooting

    session, nonbearer = hazardous_nonbearer_session()
    state = session.lifecycle.state
    assert state is not None
    request = select_optional_shooting(session)
    status = session.submit_parameterized_payload(
        request_id=request.request_id,
        payload=optional_payload(request),
        result_id="order97:allocation-probe-fire",
    )
    allocation = status.decision_request
    assert allocation is not None
    assert allocation.decision_type == "select_mortal_wound_model"
    session.submit_option(
        request_id=allocation.request_id,
        option_id=nonbearer.model_instance_id,
        result_id="order97:allocation-probe-select",
    )
    after = (
        state.army_definitions[0].unit_by_id(SHOOTER).own_model_by_id(nonbearer.model_instance_id)
    )
    occurrences = [
        e
        for e in session.lifecycle.decision_controller.event_log.records
        if e.event_type == "mortal_wound_model_allocated"
    ]
    return _observation(
        "faq-e58d31bc-b6eb-4db1-b319-dc27dd60154f-obligation-01",
        "faq:e58d31bc-b6eb-4db1-b319-dc27dd60154f",
        "src/warhammer40k_core/engine/mortal_wound_model_allocation.py:resolve_mortal_wound_model_decision",
        {"allocation_timing_occurrence_count": 1},
        {
            "allocation_timing_occurrence_count": len(occurrences),
            "wounds_before": nonbearer.current_wounds,
            "wounds_after": after.current_wounds,
        },
        "The facade selects and damages a real recipient with no Feel No Pain; "
        "no allocation timing occurrence is emitted. The only occurrence producer "
        "is conditional on optional or multiple Feel No Pain sources, and the "
        "timing-trigger enum has no general allocation trigger.",
    )


def observations() -> list[dict[str, JsonValue]]:
    return [
        probe_action_battle_shock(),
        probe_pile_in_attainable_engagement(),
        probe_pile_in_closest_target(),
        probe_solid_window(),
        probe_vertical_contact(),
        probe_based_frame_measurement(),
        probe_friendly_transit(),
        probe_frame_terrain_membership(),
        probe_solid_window_endpoint(),
        probe_zero_oc_unit_control(),
        probe_extra_distance_overrun_window(),
        probe_dense_floor_crossing(),
        probe_exposed_category(),
        probe_mortal_allocation_trigger(),
    ]


if __name__ == "__main__":
    print(json.dumps(observations(), indent=2, sort_keys=True))
