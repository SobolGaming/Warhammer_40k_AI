"""Triggered source authority, closest choice, each-model endpoints and locks."""

from typing import cast

import pytest

from tests.support.section02_fixtures import Section02Definitions
from tests.support.section03_fixtures import scenario
from tests.support.section21_fixtures import (
    descriptor,
    enemy_at,
    offer_surge,
    surge_path,
    surge_result,
    surge_scene,
)
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError
from warhammer40k_core.engine.phase_movement_history import PhaseMovementRecord
from warhammer40k_core.engine.surge_movement import closest_surge_targets, surge_ineligibility
from warhammer40k_core.engine.triggered_movement import TriggeredMovementEligibleUnit
from warhammer40k_core.engine.triggered_movement_selection import (
    triggered_movement_unit_selection_request,
)
from warhammer40k_core.geometry.pose import Pose


def test_recorded_trigger_is_required_before_offering_surge(
    section21_definitions: Section02Definitions,
) -> None:
    s = surge_scene(section21_definitions)
    session = s.session()
    d = descriptor(s)
    with pytest.raises(GameLifecycleError, match="recorded granting trigger"):
        triggered_movement_unit_selection_request(
            state=s.state,
            decisions=session.lifecycle.decision_controller,
            player_id="owner",
            descriptor=d,
            eligible_units=(
                TriggeredMovementEligibleUnit(
                    s.unit.unit_instance_id, "s21:hook", d.source_rule_id
                ),
            ),
        )
    assert not session.lifecycle.decision_controller.queue.pending_requests
    assert len(offer_surge(session, s).options) == 2


@pytest.mark.parametrize(
    ("condition", "reason"),
    [
        ("shocked", "battle_shocked_surge_forbidden"),
        ("engaged", "engagement_range_surge_forbidden"),
        ("moved", "surge_prior_move_this_phase"),
        ("clear", None),
    ],
)
def test_all_surge_eligibility_conditions_are_conjunctive(
    section21_definitions: Section02Definitions, condition: str, reason: str | None
) -> None:
    s = surge_scene(section21_definitions, gap=1 if condition == "engaged" else 8)
    if condition == "shocked":
        s.state.battle_shocked_unit_ids.append(s.unit.unit_instance_id)
    if condition == "moved":
        s.state.phase_movement_history.append(
            PhaseMovementRecord(
                "explicit:s21:prior-move",
                1,
                "owner",
                BattlePhase.SHOOTING,
                s.unit.unit_instance_id,
                s.unit.own_model_ids(),
                False,
                False,
                None,
            )
        )
    assert surge_ineligibility(s.state, s.unit.unit_instance_id) == reason
    session = s.session()
    request = offer_surge(session, s)
    assert len([o for o in request.options if o.option_id.startswith("surge:")]) == (
        1 if reason is None else 0
    )


@pytest.mark.parametrize("prior_occurrence", ["same", "other_phase", "other_turn", "other_round"])
def test_prior_move_is_scoped_to_actual_phase_occurrence(
    section21_definitions: Section02Definitions, prior_occurrence: str
) -> None:
    s = surge_scene(section21_definitions)
    s.state.battle_round = 2
    s.state.phase_movement_history.append(
        PhaseMovementRecord(
            "s21:history",
            1 if prior_occurrence == "other_round" else 2,
            "opponent" if prior_occurrence == "other_turn" else "owner",
            BattlePhase.MOVEMENT if prior_occurrence == "other_phase" else BattlePhase.SHOOTING,
            s.unit.unit_instance_id,
            s.unit.own_model_ids(),
            False,
            False,
            None,
        )
    )
    assert surge_ineligibility(s.state, s.unit.unit_instance_id) == (
        "surge_prior_move_this_phase" if prior_occurrence == "same" else None
    )


@pytest.mark.parametrize("tied", [False, True])
def test_closest_enemy_is_selected_before_path_and_ties_are_finite(
    section21_definitions: Section02Definitions, tied: bool
) -> None:
    s = surge_scene(section21_definitions, gap=6)
    assert s.state.battlefield_state is not None
    target_x = (
        s.state.battlefield_state.unit_placement_by_id(s.target.unit_instance_id)
        .model_placements[0]
        .pose.position.x
    )
    second = enemy_at(s, "second", (Pose.at(20 - target_x if tied else 40, 10),))
    expected = (
        tuple(sorted((s.target.unit_instance_id, second.unit_instance_id)))
        if tied
        else (s.target.unit_instance_id,)
    )
    assert (
        closest_surge_targets(scenario=scenario(s.state), unit_instance_id=s.unit.unit_instance_id)
        == expected
    )
    session = s.session()
    request = offer_surge(session, s)
    assert (
        tuple(
            sorted(
                cast(str, o.payload["surge_target_unit_instance_id"])
                for o in request.options
                if isinstance(o.payload, dict) and not o.payload.get("declined")
            )
        )
        == expected
    )
    if not tied:
        with pytest.raises(GameLifecycleError, match="committed closest"):
            surge_result(s, surge_path(s, (4,)), target_id=second.unit_instance_id)


@pytest.mark.parametrize("multi", [False, True])
@pytest.mark.parametrize(
    ("gap", "distance", "valid", "code"),
    [
        (4.5, 3, True, None),
        (4.5, 2, False, "surge_engagement_not_reached"),
        (9, 4, True, None),
        (9, 3, False, "surge_maximum_approach_not_reached"),
        (9, 4.01, False, "movement_distance_exceeded"),
    ],
)
def test_each_survivor_must_engage_or_reach_certified_maximum_approach(
    section21_definitions: Section02Definitions,
    multi: bool,
    gap: float,
    distance: float,
    valid: bool,
    code: str | None,
) -> None:
    s = surge_scene(section21_definitions, multi=multi, gap=gap)
    before = s.state.to_payload()
    result = surge_result(s, surge_path(s, (distance,) * len(s.unit.own_models)))
    assert result.is_valid is valid
    payload = result.movement_payload
    if code is not None:
        assert code in str(result.to_payload())
    if valid:
        endpoints = payload["surge_model_endpoints"]
        assert isinstance(endpoints, list)
        assert len(endpoints) == len(s.unit.own_models)
    assert s.state.to_payload() == before


def test_one_models_approach_cannot_satisfy_another_model(
    section21_definitions: Section02Definitions,
) -> None:
    s = surge_scene(section21_definitions, multi=True, gap=9)
    result = surge_result(s, surge_path(s, (4, 3)))
    assert not result.is_valid
    assert "surge_maximum_approach_not_reached" in str(result.to_payload())
    assert result.coherency_result.is_coherent


def test_approach_never_waives_endpoint_coherency(
    section21_definitions: Section02Definitions,
) -> None:
    s = surge_scene(section21_definitions, multi=True, gap=9)
    result = surge_result(s, surge_path(s, (4, 0)))
    assert not result.is_valid
    assert not result.coherency_result.is_coherent
    assert result.rollback_record is not None


def test_surge_cannot_end_engaged_with_a_non_target(
    section21_definitions: Section02Definitions,
) -> None:
    s = surge_scene(section21_definitions, gap=5)
    enemy_at(s, "non-target", (Pose.at(16, 12.9),))
    result = surge_result(s, surge_path(s, (4,)))
    assert not result.is_valid
    assert "surge_non_target_engagement" in str(result.to_payload())
