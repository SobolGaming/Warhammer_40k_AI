"""FAQ movement clarifications through the actual accepted-distance consumer."""

from math import isclose

import pytest

from tests.support.section02_fixtures import Section02Definitions
from tests.support.section03_fixtures import geometry, native_state, scenario
from tests.support.section03_session import movement_session
from tests.support.section09_fixtures import add_unit, attach_mission, begin
from tests.support.section11_fixtures import modifier, roll, select, session_for, state_case
from tests.support.section21_fixtures import (
    LORD,
    SERPENT,
    enemy_at,
    offer_surge,
    surge_result,
    surge_scene,
)
from warhammer40k_core.core.ruleset_descriptor import MovementMode
from warhammer40k_core.engine.battlefield_state import ModelDisplacementKind
from warhammer40k_core.engine.event_log import validate_json_value
from warhammer40k_core.engine.movement_legality import (
    MovementCapabilitySet,
    MovementLegalityContext,
)
from warhammer40k_core.engine.movement_proposals import (
    MovementProposalPayload,
    MovementProposalRequest,
)
from warhammer40k_core.engine.phase import BattlePhase, LifecycleStatusKind
from warhammer40k_core.engine.phases.shooting_targeting import (
    _heavy_hit_roll_modifier_applies,
)
from warhammer40k_core.engine.rules_units import rules_unit_view_by_id
from warhammer40k_core.geometry.pathing import PathWitness, TerrainPathLegalityContext
from warhammer40k_core.geometry.pose import Pose


@pytest.mark.parametrize(("horizontal", "heavy"), [(2, True), (3, True), (3.001, False)])
def test_flying_vertical_legs_are_excluded_from_actual_heavy_hit_permission(
    section21_definitions: Section02Definitions, horizontal: float, heavy: bool
) -> None:
    d = section21_definitions
    unit = d.unit(SERPENT)
    enemy = d.unit(LORD, army_id="enemy", identity="target")
    state = native_state(d, unit, (Pose.at(10, 10),), enemy=enemy, enemy_poses=(Pose.at(35, 10),))
    attach_mission(state)
    add_unit(state, d.unit(LORD, identity="spare"), (Pose.at(10, 35),))
    session = movement_session(d, state)
    request = begin(session)
    status = session.submit_option(
        request_id=request.request_id, result_id="s21:heavy-unit", option_id=unit.unit_instance_id
    )
    assert status.decision_request is not None
    request = status.decision_request
    assert request is not None
    status = session.submit_option(
        request_id=request.request_id,
        result_id="s21:heavy-flight",
        option_id="normal_move:fly_take_to_skies",
    )
    assert status.decision_request is not None
    request = status.decision_request
    assert request is not None
    proposal = MovementProposalRequest.from_decision_request_payload(request.payload)
    path = PathWitness.for_paths(
        (
            (
                unit.own_model_ids()[0],
                (
                    Pose.at(10, 10),
                    Pose.at(10, 10, 8),
                    Pose.at(10 + horizontal, 10, 8),
                    Pose.at(10 + horizontal, 10),
                ),
            ),
        )
    )
    status = session.submit_parameterized_payload(
        request_id=request.request_id,
        result_id="s21:heavy-path",
        payload=validate_json_value(
            MovementProposalPayload(
                proposal_request_id=request.request_id,
                proposal_kind=proposal.proposal_kind,
                unit_instance_id=unit.unit_instance_id,
                movement_phase_action="normal_move",
                movement_mode="fly_take_to_skies",
                witness=path,
            ).to_payload()
        ),
    )
    assert status.status_kind is not LifecycleStatusKind.INVALID, status.to_payload()
    assert len(state.model_movement_history) == 1
    assert isclose(state.model_movement_history[0].distance_inches, horizontal)
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.SHOOTING)
    assert (
        _heavy_hit_roll_modifier_applies(
            state=state,
            scenario=scenario(state),
            ruleset_descriptor=state.runtime_ruleset_descriptor(),
            rules_unit=rules_unit_view_by_id(state=state, unit_instance_id=unit.unit_instance_id),
            player_id="owner",
            out_of_phase_state=None,
        )
        is heavy
    )


@pytest.mark.parametrize("skies", [False, True])
@pytest.mark.parametrize("gap", [9.99, 10.01, 11.99])
def test_flight_charge_penalty_limits_current_finite_target_options(
    section21_definitions: Section02Definitions, skies: bool, gap: float
) -> None:
    state, unit, enemy = state_case(
        section21_definitions, datasheet=SERPENT, gap=gap, seed="s21-charge"
    )
    modifier(state, unit.unit_instance_id, 12)
    session = session_for(section21_definitions, state)
    request = select(session, unit, skies=skies)
    result = roll(session)
    assert result.value == 12
    assert result.movement_budget.maximum_distance_inches == (10 if skies else 12)
    assert (enemy.unit_instance_id in result.reachable_target_distances_inches) is (
        gap <= (10 if skies else 12)
    )
    if gap <= (10 if skies else 12):
        assert request.decision_type == "select_charge_targets"
        assert any(
            isinstance(o.payload, dict)
            and isinstance(o.payload["target_ids"], list)
            and enemy.unit_instance_id in o.payload["target_ids"]
            for o in request.options
        )
    else:
        assert request.decision_type == "select_charging_unit"
        assert not result.move_available


@pytest.mark.parametrize(
    "mode", [MovementMode.NORMAL, MovementMode.ADVANCE, MovementMode.FALL_BACK, MovementMode.CHARGE]
)
@pytest.mark.parametrize("skies", [False, True])
def test_friendly_vehicle_transit_preserves_faq_other_move_types(
    section21_definitions: Section02Definitions, mode: MovementMode, skies: bool
) -> None:
    d = section21_definitions
    unit = d.unit(SERPENT)
    blocker = d.unit(SERPENT, identity="friendly")
    source = geometry(unit, (Pose.at(10, 10),))[0]
    friend = geometry(blocker, (Pose.at(16, 10),))[0]
    state = native_state(d, unit)
    context = MovementLegalityContext.from_keywords(
        keywords=unit.keywords,
        ruleset_descriptor=state.runtime_ruleset_descriptor(),
        movement_mode=mode,
        movement_phase_action=None,
        displacement_kind=ModelDisplacementKind.NORMAL_MOVE,
        take_to_the_skies=skies,
        unit=unit,
        model_instance_id=unit.own_model_ids()[0],
        current_model_instance_ids=unit.own_model_ids(),
    )
    path = PathWitness.for_paths(((source.model_id, (Pose.at(10, 10), Pose.at(22, 10))),))
    result = context.to_path_validation_context(
        moving_model=source,
        witness=path,
        battlefield_width_inches=60,
        battlefield_depth_inches=44,
        friendly_models=(friend,),
        friendly_vehicle_monster_model_ids=(friend.model_id,),
        movement_distance_budget_inches=12,
    ).validate()
    assert result.is_valid is (skies or mode in (MovementMode.FALL_BACK, MovementMode.CHARGE))


def test_transient_enemy_engagement_during_surge_is_not_endpoint_engagement(
    section21_definitions: Section02Definitions,
) -> None:
    s = surge_scene(section21_definitions, gap=5)
    other = enemy_at(s, "transient", (Pose.at(10, 18),))
    path = PathWitness.for_paths(
        ((s.unit.own_model_ids()[0], (Pose.at(10, 10), Pose.at(13, 16.1), Pose.at(14, 10))),)
    )
    result = surge_result(s, path, maximum=14)
    assert result.is_valid, result.to_payload()
    assert result.movement_payload["surge_target_unit_instance_id"] != other.unit_instance_id


@pytest.mark.parametrize("skies", [False, True])
def test_internal_flight_terrain_capability_round_trips_without_inference(
    section21_definitions: Section02Definitions, skies: bool
) -> None:
    unit = section21_definitions.unit(SERPENT)
    state = native_state(section21_definitions, unit)
    context = MovementLegalityContext.from_keywords(
        keywords=unit.keywords,
        ruleset_descriptor=state.runtime_ruleset_descriptor(),
        movement_mode=MovementMode.NORMAL,
        movement_phase_action=None,
        displacement_kind=ModelDisplacementKind.NORMAL_MOVE,
        take_to_the_skies=skies,
        unit=unit,
        model_instance_id=unit.own_model_ids()[0],
        current_model_instance_ids=unit.own_model_ids(),
    )
    restored = MovementLegalityContext.from_payload(context.to_payload())
    assert restored == context
    assert (
        MovementCapabilitySet.from_payload(context.capabilities.to_payload())
        == context.capabilities
    )
    assert restored.capabilities.can_transit_all_terrain is skies
    model = geometry(unit, (Pose.at(10, 10),))[0]
    path = PathWitness.for_paths(((model.model_id, (model.pose, Pose.at(12, 10))),))
    terrain = context.to_terrain_path_legality_context(moving_model=model, witness=path)
    assert TerrainPathLegalityContext.from_payload(terrain.to_payload()) == terrain
    assert terrain.can_transit_all_terrain is skies


def test_optional_surge_can_be_declined_without_moving(
    section21_definitions: Section02Definitions,
) -> None:
    s = surge_scene(section21_definitions)
    session = s.session()
    request = offer_surge(session, s)
    before = s.state.battlefield_state
    decline = next(
        o for o in request.options if isinstance(o.payload, dict) and o.payload.get("declined")
    )
    status = session.submit_option(
        request_id=request.request_id, result_id="s21:decline", option_id=decline.option_id
    )
    assert status.status_kind is not LifecycleStatusKind.INVALID
    assert s.state.battlefield_state == before
    assert not s.state.phase_movement_history
